"""Tests for eyes + hands: screen capture, GUI classification, GuiExecutor.

Covers: screenshot capture with mocked backends, describe() graceful
degradation, GUI action classification levels, GuiExecutor audit logging,
fail-closed behaviour for unknown gui: commands, and the agent loop driving
a screenshot + a GUI click.

Run:  python3 tests/test_desktop.py
"""

import base64
import io
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.agent import Agent
from aegis.brain.base import Backend
from aegis.config import Config
from aegis import safety
from aegis import screen as screen_mod
from aegis import desktop
from aegis.desktop import GuiExecutor, parse_action, DesktopError
from aegis.plan import Plan, PlanError


def make_cfg(mode="auto_safe", tmp=None):
    cfg = Config()
    cfg.safety.mode = mode
    cfg.safety.workspace_root = tmp or tempfile.mkdtemp(prefix="aegis-test-")
    cfg.interface.audit_log = os.path.join(cfg.safety.workspace_root, "audit.jsonl")
    cfg.interface.history_file = os.path.join(cfg.safety.workspace_root, "history")
    cfg.validate()
    return cfg


def read_audit(cfg):
    try:
        with open(cfg.interface.audit_log) as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except OSError:
        return []


# ---------------------------------------------------------------------------
# 1. GUI classification
# ---------------------------------------------------------------------------

GUI_CASES = [
    ("gui:screenshot", safety.Level.READ_ONLY, "screenshot read-only"),
    ("gui:move_to 100,200", safety.Level.READ_ONLY, "move read-only"),
    ("gui:size", safety.Level.READ_ONLY, "size read-only"),
    ("gui:click 500,300", safety.Level.RISKY, "click risky"),
    ("gui:double_click 1,2", safety.Level.RISKY, "double-click risky"),
    ("gui:right_click 1,2", safety.Level.RISKY, "right-click risky"),
    ("gui:type hello world", safety.Level.RISKY, "plain type risky"),
    ("gui:key enter", safety.Level.RISKY, "key risky"),
    ("gui:hotkey ctrl+c", safety.Level.RISKY, "hotkey risky"),
    ("gui:scroll -3", safety.Level.RISKY, "scroll risky"),
    ("gui:drag 0,0 10,10", safety.Level.RISKY, "drag risky"),
    ("gui:type password= hunter2", safety.Level.BLOCKED, "credential type blocked"),
    ("gui:type api_key: abc123", safety.Level.BLOCKED, "api key type blocked"),
    ("gui:type -----BEGIN RSA PRIVATE KEY-----", safety.Level.BLOCKED, "private key blocked"),
    ("gui:type rm -rf /", safety.Level.BLOCKED, "destructive type blocked"),
    ("gui:type mkfs.ext4 /dev/sda", safety.Level.BLOCKED, "mkfs type blocked"),
    ("gui:explode 1,2", safety.Level.RISKY, "unknown verb fails closed"),
    ("gui:click banana", safety.Level.RISKY, "bad coords fail closed"),
    ("gui:drag 1,2", safety.Level.RISKY, "drag needs two pairs"),
    ("gui:", safety.Level.RISKY, "empty gui action fails closed"),
    ("click 500,300", safety.Level.RISKY, "no gui: prefix is unknown command"),
]


def test_classify_gui():
    cfg = make_cfg()
    failures = 0
    for descriptor, expected, note in GUI_CASES:
        v = safety.classify(descriptor, cfg)
        ok = v.level == expected
        if not ok:
            failures += 1
        print(f"{'PASS' if ok else 'FAIL'}  [{v.label:>11}] {descriptor!r}  ({note})")
        if not ok:
            print(f"        expected {safety.LEVEL_LABEL[expected]}, got {v.label}: {v.reason}")
    return failures


# ---------------------------------------------------------------------------
# 2. Screen capture (mocked backends) + describe()
# ---------------------------------------------------------------------------

class _FakeShot:
    size = (2, 2)
    bgra = bytes(16)  # 2x2 pixels x 4 bytes (BGRX)


class _FakeSCT:
    monitors = [None, (0, 0, 2, 2)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, monitor):
        return _FakeShot()


def _install_fake_mss():
    mod = types.ModuleType("mss")
    mod.mss = lambda: _FakeSCT()
    sys.modules["mss"] = mod
    return mod


def test_screen_capture():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-test-shot-")
    path = os.path.join(tmp, "shot.png")

    # mss path.
    _install_fake_mss()
    try:
        img = screen_mod.capture(path)
        if img.size != (2, 2):
            failures += 1
            print(f"FAIL capture size {img.size}")
        elif not os.path.exists(path):
            failures += 1
            print("FAIL capture did not save file")
        else:
            print("PASS capture via mocked mss")
    finally:
        sys.modules.pop("mss", None)

    # ImageGrab fallback (mss import fails).
    import PIL.ImageGrab as _grab_mod
    real_grab = _grab_mod.grab
    try:
        _grab_mod.grab = lambda: screen_mod._PILImage.new("RGB", (3, 3))
        img = screen_mod.capture(path)
        if img.size != (3, 3):
            failures += 1
            print(f"FAIL ImageGrab fallback size {img.size}")
        else:
            print("PASS capture via ImageGrab fallback")
    finally:
        _grab_mod.grab = real_grab

    # Both fail -> ScreenError, not a crash.
    _install_fake_mss()
    sys.modules["mss"].mss = lambda: (_ for _ in ()).throw(RuntimeError("no display"))
    try:
        _grab_mod.grab = lambda: (_ for _ in ()).throw(RuntimeError("no display"))
        try:
            screen_mod.capture(path)
            failures += 1
            print("FAIL capture should raise when both backends fail")
        except screen_mod.ScreenError:
            print("PASS capture raises ScreenError when both backends fail")
    finally:
        sys.modules.pop("mss", None)
        _grab_mod.grab = real_grab

    # screenshot_b64 is valid PNG base64.
    _install_fake_mss()
    try:
        b64 = screen_mod.screenshot_b64(path)
        raw = base64.b64decode(b64)
        if not raw.startswith(b"\x89PNG"):
            failures += 1
            print("FAIL screenshot_b64 is not PNG")
        else:
            print("PASS screenshot_b64 returns PNG bytes")
    finally:
        sys.modules.pop("mss", None)

    return failures


class _FakeVisionRouter:
    def describe_image(self, b64, prompt):
        return "A window with a button labelled OK."


class _FailingVisionRouter:
    def describe_image(self, b64, prompt):
        raise RuntimeError("vision backend exploded")


def test_describe():
    failures = 0
    img = screen_mod._PILImage.new("RGB", (2, 2))
    out = screen_mod.describe(img, None)
    if "No vision backend" not in out:
        failures += 1
        print(f"FAIL describe with no brain: {out!r}")
    else:
        print("PASS describe with no brain degrades gracefully")

    out = screen_mod.describe(img, _FakeVisionRouter())
    if "button labelled OK" not in out:
        failures += 1
        print(f"FAIL describe with vision backend: {out!r}")
    else:
        print("PASS describe with vision backend")

    out = screen_mod.describe(img, _FailingVisionRouter())
    if "Vision description failed" not in out:
        failures += 1
        print(f"FAIL describe with failing backend: {out!r}")
    else:
        print("PASS describe with failing backend degrades gracefully")
    return failures


# ---------------------------------------------------------------------------
# 3. GuiExecutor: gates + audit + redaction
# ---------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


def test_gui_executor():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-test-gui-")

    # Mock the primitives so nothing touches a real display.
    saved = {name: getattr(desktop, name) for name in
             ("click", "move_to", "type_text", "screen_size")}
    saved_capture = screen_mod.capture
    screen_mod.capture = lambda path: screen_mod._PILImage.new("RGB", (2, 2))
    rec = _Recorder()
    desktop.click = lambda x, y: rec(f"click", x, y)
    desktop.move_to = lambda x, y: rec(f"move_to", x, y)
    desktop.type_text = lambda t: rec(f"type", t)
    desktop.screen_size = lambda: (1920, 1080)
    try:
        # auto_safe: screenshot auto-runs.
        cfg = make_cfg(mode="auto_safe", tmp=tmp)
        ex = GuiExecutor(cfg)
        res = ex.run("gui:screenshot")
        if not res.ran or res.decision != "auto":
            failures += 1
            print(f"FAIL screenshot should auto-run in auto_safe: {res}")
        else:
            print("PASS screenshot auto-runs in auto_safe")
        audit = read_audit(cfg)
        if not any(r.get("event") == "gui" and r.get("action") == "gui:screenshot"
                   for r in audit):
            failures += 1
            print("FAIL audit missing gui screenshot record")
        else:
            print("PASS audit records gui screenshot")

        # auto_safe + no confirm handler: click is denied, never executed.
        res = ex.run("gui:click 500,300")
        if res.ran or res.decision != "denied":
            failures += 1
            print(f"FAIL click should be denied without confirm: {res}")
        elif any(c[0] == "click" for c in rec.calls):
            failures += 1
            print("FAIL denied click still executed")
        else:
            print("PASS click denied in auto_safe without confirm handler")

        # confirm mode with an approving handler: click runs.
        cfg2 = make_cfg(mode="confirm", tmp=tmp)
        ex2 = GuiExecutor(cfg2, confirm=lambda v, d: True)
        res = ex2.run("gui:click 500,300")
        if not res.ran or res.decision != "confirmed":
            failures += 1
            print(f"FAIL click should run after confirmation: {res}")
        elif ("click", 500, 300) not in rec.calls:
            failures += 1
            print(f"FAIL click not dispatched: {rec.calls}")
        else:
            print("PASS click runs after confirmation")

        # confirm mode with a denying handler: click does not run.
        ex3 = GuiExecutor(cfg2, confirm=lambda v, d: False)
        before = len(rec.calls)
        res = ex3.run("gui:click 1,2")
        if res.ran or res.decision != "denied" or len(rec.calls) != before:
            failures += 1
            print(f"FAIL denied click ran: {res}")
        else:
            print("PASS click denied by operator")

        # auto_full: blocked type never runs.
        cfg4 = make_cfg(mode="auto_full", tmp=tmp)
        ex4 = GuiExecutor(cfg4)
        res = ex4.run("gui:type rm -rf /")
        if res.ran or res.decision != "blocked":
            failures += 1
            print(f"FAIL destructive type should be blocked: {res}")
        else:
            print("PASS destructive type blocked in auto_full")

        # auto_full: typed text is redacted in the audit log.
        res = ex4.run("gui:type hello secret world")
        if not res.ran:
            failures += 1
            print(f"FAIL plain type should run in auto_full: {res}")
        audit = read_audit(cfg4)
        type_recs = [r for r in audit if r.get("action", "").startswith("gui:type")]
        if not type_recs:
            failures += 1
            print("FAIL audit missing gui:type record")
        elif any("hello secret world" in json.dumps(r) for r in type_recs):
            failures += 1
            print("FAIL typed text leaked into audit log")
        elif not any(r.get("action") == "gui:type <redacted>" for r in type_recs):
            failures += 1
            print("FAIL audit did not use redacted action")
        else:
            print("PASS typed text redacted in audit log")

        # dry_run never executes.
        cfg5 = make_cfg(mode="dry_run", tmp=tmp)
        ex5 = GuiExecutor(cfg5)
        before = len(rec.calls)
        res = ex5.run("gui:click 9,9")
        if res.ran or res.decision != "dry-run" or len(rec.calls) != before:
            failures += 1
            print(f"FAIL dry_run should not execute: {res}")
        else:
            print("PASS dry_run blocks GUI execution")

        # Unknown gui: verb fails closed (denied, never executed).
        res = ex4.run("gui:explode 1,2")
        if res.ran:
            failures += 1
            print(f"FAIL unknown gui verb ran: {res}")
        else:
            print("PASS unknown gui verb fails closed")
    finally:
        for name, fn in saved.items():
            setattr(desktop, name, fn)
        screen_mod.capture = saved_capture
    return failures


# ---------------------------------------------------------------------------
# 4. Agent loop: screenshot + gui click, and a gui plan
# ---------------------------------------------------------------------------

class _ScriptedBackend(Backend):
    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def available(self):
        return True

    def generate(self, messages, **kwargs):
        self.seen.append(messages)
        return self.replies.pop(0)


class _ScriptedRouter:
    def __init__(self, replies):
        self.backend = _ScriptedBackend(replies)

    def generate(self, messages, **kwargs):
        return self.backend.generate(messages, **kwargs)

    def select(self):
        return self.backend

    def status(self):
        return "scripted"


def test_agent_gui_loop():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-test-agent-gui-")
    cfg = make_cfg(mode="auto_full", tmp=tmp)

    # Mock screen capture (no display) and the click primitive.
    saved_capture = screen_mod.capture
    saved_click = desktop.click
    clicks = []
    screen_mod.capture = lambda path: screen_mod._PILImage.new("RGB", (2, 2))
    desktop.click = lambda x, y: clicks.append((x, y))
    try:
        replies = [
            "Let me look at the screen.\n\n```aegis-screenshot\n```",
            "I see the desktop. Clicking the button.\n\n```aegis-gui\ngui:click 100,200\n```",
            "Clicked it. All done.",
        ]
        agent = Agent(cfg, router=_ScriptedRouter(replies))
        resp = agent.ask("click the OK button")

        kinds = [s.kind for s in resp.steps]
        if "screenshot" not in kinds or "gui" not in kinds:
            failures += 1
            print(f"FAIL agent steps missing screenshot/gui: {kinds}")
        else:
            print("PASS agent ran screenshot + gui steps")

        if clicks != [(100, 200)]:
            failures += 1
            print(f"FAIL click not dispatched with (100,200): {clicks}")
        else:
            print("PASS agent click dispatched")

        audit = read_audit(cfg)
        if not any(r.get("event") == "gui" for r in audit):
            failures += 1
            print("FAIL audit missing gui event from agent run")
        else:
            print("PASS agent gui action audited")

        # Observation fed back: the follow-up prompt must mention the screenshot.
        joined = "\n".join(m.content for m in agent.router.backend.seen[-1])
        if "screenshot saved to" not in joined:
            failures += 1
            print("FAIL screenshot observation not fed back")
        else:
            print("PASS screenshot observation fed back")
    finally:
        screen_mod.capture = saved_capture
        desktop.click = saved_click

    # A plan with gui + screenshot steps executes in order.
    saved_capture = screen_mod.capture
    saved_click = desktop.click
    clicks = []
    screen_mod.capture = lambda path: screen_mod._PILImage.new("RGB", (2, 2))
    desktop.click = lambda x, y: clicks.append((x, y))
    try:
        plan_body = (
            "## screenshot\n"
            "## gui\ngui:click 7,8\n"
        )
        replies = [
            "Plan:\n\n```aegis-plan\n" + plan_body + "```",
            "Plan ran. Done.",
        ]
        agent = Agent(cfg, router=_ScriptedRouter(replies),
                      plan_confirm=lambda plan: True)
        resp = agent.ask("screenshot then click")
        if clicks != [(7, 8)]:
            failures += 1
            print(f"FAIL plan gui step did not click: {clicks}")
        elif "plan COMPLETED" not in resp.final and "COMPLETED" not in "\n".join(
                s.content for s in resp.steps):
            failures += 1
            print("FAIL plan with gui steps did not complete")
        else:
            print("PASS plan with screenshot + gui steps completes")

        # A plan with a blocked gui step is refused at that step.
        bad_plan = "## gui\ngui:type rm -rf /\n"
        try:
            plan = Plan.parse(bad_plan, cfg)
            if not plan.has_blocked:
                failures += 1
                print("FAIL plan with blocked gui step not flagged")
            else:
                print("PASS plan flags blocked gui step")
        except PlanError as exc:
            failures += 1
            print(f"FAIL plan parse raised unexpectedly: {exc}")
    finally:
        screen_mod.capture = saved_capture
        desktop.click = saved_click
    return failures


def main():
    failures = 0
    failures += test_classify_gui()
    failures += test_screen_capture()
    failures += test_describe()
    failures += test_gui_executor()
    failures += test_agent_gui_loop()
    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURES'}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
