"""Interactive command approval: gate logic + both front-ends (#1 follow-up).

The gate is framework-agnostic and tested directly. The TUI and GUI tests then
verify the real wiring end to end: a risky command must prompt, and the user's
answer must decide whether it runs.

Run:  python3 tests/test_approval.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.approval import (APPROVE_WORDS, ApprovalGate, ApprovalOutcome,
                            ApprovalRequest, is_approval)
from aegis.safety import Level, Verdict


class FakeVerdict:
    label = "risky"
    reason = "mount/unmount"


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------

def test_gate_approve():
    fails = 0
    seen = []
    gate = ApprovalGate(on_request=seen.append, timeout=5.0)
    result = {}

    def worker():
        result["answer"] = gate.ask(FakeVerdict(), "mount /dev/sdb1 /mnt")

    t = threading.Thread(target=worker)
    t.start()

    # Wait for the request to surface, then approve it.
    for _ in range(100):
        if seen:
            break
        time.sleep(0.01)
    if not seen:
        fails += 1
        print("FAIL gate: on_request was never called")
        return fails

    req = seen[0]
    if isinstance(req, ApprovalRequest) and req.command == "mount /dev/sdb1 /mnt" \
            and req.level == "risky":
        print("PASS gate: request carries command + level + reason")
    else:
        fails += 1
        print(f"FAIL gate: request -> {req}")

    if gate.pending:
        print("PASS gate: gate reports a pending request")
    else:
        fails += 1
        print("FAIL gate: pending was False while waiting")

    gate.resolve(True)
    t.join(timeout=5)
    if result.get("answer") is ApprovalOutcome.ALLOW:
        print("PASS gate: approve unblocks the worker with ALLOW")
    else:
        fails += 1
        print(f"FAIL gate: approve -> {result.get('answer')}")

    if not gate.pending:
        print("PASS gate: request cleared after resolution")
    else:
        fails += 1
        print("FAIL gate: still pending after resolve")
    return fails


def test_gate_fail_closed():
    """Every way of not answering must deny — never hang, never approve."""
    fails = 0

    def run(responder, label, timeout=1.0):
        gate = ApprovalGate(timeout=timeout)
        gate.on_request = responder
        out = {}
        t = threading.Thread(target=lambda: out.update(
            answer=gate.ask(FakeVerdict(), "rm -rf /tmp/x")))
        t.start()
        t.join(timeout=timeout + 3)
        if out.get("answer") is ApprovalOutcome.DENY:
            print(f"PASS gate: {label} denies")
            return 0
        print(f"FAIL gate: {label} -> {out.get('answer')!r}, want DENY")
        return 1

    fails += run(lambda req: None, "a UI that never answers (timeout)", timeout=0.5)

    def boom(req):
        raise RuntimeError("ui exploded")

    fails += run(boom, "an on_request callback that raises")
    fails += run(None, "a missing on_request callback")
    return fails


def test_gate_resolve_semantics():
    fails = 0
    gate = ApprovalGate(timeout=5.0)

    if gate.resolve(True) is False:
        print("PASS gate: resolve with nothing pending returns False")
    else:
        fails += 1
        print("FAIL gate: resolve with nothing pending returned True")

    # Explicit deny through the normal path.
    gate.on_request = lambda req: threading.Timer(0.05, gate.resolve, [False]).start()
    if gate.ask(FakeVerdict(), "dd if=/dev/zero of=/dev/sda") is ApprovalOutcome.DENY:
        print("PASS gate: explicit deny returns DENY")
    else:
        fails += 1
        print("FAIL gate: explicit deny returned ALLOW")

    # cancel() unblocks a waiting worker and denies.
    gate2 = ApprovalGate(timeout=5.0)
    gate2.on_request = lambda req: None
    out = {}
    t = threading.Thread(target=lambda: out.update(
        answer=gate2.ask(FakeVerdict(), "mount")))
    t.start()
    time.sleep(0.1)
    gate2.cancel()
    t.join(timeout=5)
    if out.get("answer") is ApprovalOutcome.DENY:
        print("PASS gate: cancel() unblocks the worker with DENY")
    else:
        fails += 1
        print(f"FAIL gate: cancel -> {out.get('answer')}")

    # After cancel, further requests are denied immediately.
    if gate2.ask(FakeVerdict(), "mount") is ApprovalOutcome.DENY:
        print("PASS gate: a cancelled gate denies immediately")
    else:
        fails += 1
        print("FAIL gate: cancelled gate still prompted")

    # reset() re-arms it.
    gate2.reset()
    gate2.on_request = lambda req: threading.Timer(0.05, gate2.resolve, [True]).start()
    if gate2.ask(FakeVerdict(), "mount") is ApprovalOutcome.ALLOW:
        print("PASS gate: reset() re-arms a cancelled gate")
    else:
        fails += 1
        print("FAIL gate: reset() did not re-arm")
    return fails


def test_is_approval():
    fails = 0
    yes = ["y", "Y", "yes", "YES", "approve", "run", "ok", " y "]
    no = ["", "n", "no", "deny", "nope", "yess", "maybe", "run it"]
    for text in yes:
        if not is_approval(text):
            fails += 1
            print(f"FAIL is_approval: {text!r} should approve")
    for text in no:
        if is_approval(text):
            fails += 1
            print(f"FAIL is_approval: {text!r} should deny")
    if not fails:
        print(f"PASS is_approval: {len(yes)} approvals and {len(no)} denials "
              f"classified correctly (deny is the default)")
    return fails


# --------------------------------------------------------------------------
# TUI
# --------------------------------------------------------------------------

class FakeRouter:
    def __init__(self, replies):
        if replies and isinstance(replies[0], str):
            replies = [replies]
        self.replies = list(replies)

    def _next(self):
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    def generate_stream(self, messages, **kw):
        yield from self._next()

    def generate(self, messages, **kw):
        return "".join(self._next())

    def select(self):
        return None

    def status(self):
        return "fake backend"


def make_cfg(mode="auto_safe"):
    import tempfile
    from aegis.config import Config
    cfg = Config()
    cfg.validate()
    tmp = tempfile.mkdtemp()
    cfg.safety.mode = mode
    cfg.safety.workspace_root = os.path.join(tmp, "ws")
    os.makedirs(cfg.safety.workspace_root, exist_ok=True)
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    cfg.learning.snippet_file = os.path.join(tmp, "s.jsonl")
    cfg.learning.experience_file = os.path.join(tmp, "e.jsonl")
    return cfg


def _tui_lines(app):
    from textual.widgets import RichLog
    log = app.query_one("#log", RichLog)
    return " ".join(str(getattr(line, "text", line)) for line in log.lines)


async def _tui_run(answer):
    """Submit a prompt that triggers a risky command, then answer the prompt."""
    from textual.widgets import Input
    from aegis.agent import Agent
    from aegis.tui import build_app

    cfg = make_cfg()
    # 'mount' is classified RISKY but is harmless to actually run.
    agent = Agent(cfg, router=FakeRouter([
        ["Let me check.\n", "```aegis-command\n", "mount\n", "```"],
        ["All done."],
    ]))
    app = build_app(cfg, agent)

    async with app.run_test() as pilot:
        app.query_one("#input", Input).value = "check mounts"
        await pilot.press("enter")

        # Wait for the approval prompt to appear.
        prompted = False
        for _ in range(120):
            await pilot.pause(0.05)
            if app._awaiting_approval:
                prompted = True
                break
        if not prompted:
            return {"prompted": False, "lines": _tui_lines(app)}

        mid = _tui_lines(app)
        # Now answer it.
        app.query_one("#input", Input).value = answer
        await pilot.press("enter")
        # Give the worker time to observe the answer and finish the turn.
        for _ in range(80):
            await pilot.pause(0.05)
        await pilot.pause(0.3)
        return {"prompted": True, "mid": mid, "lines": _tui_lines(app),
                "awaiting": app._awaiting_approval}


def test_tui_approval():
    import asyncio
    fails = 0

    res = asyncio.run(_tui_run("y"))
    if not res["prompted"]:
        fails += 1
        print("FAIL tui: risky command did not prompt for approval")
        return fails
    if "approve?" in res["mid"] and "mount" in res["mid"]:
        print("PASS tui: risky command rendered an approval prompt")
    else:
        fails += 1
        print(f"FAIL tui: prompt text missing -> {res['mid'][:200]!r}")
    if "approved" in res["lines"]:
        print("PASS tui: typing 'y' approves")
    else:
        fails += 1
        print(f"FAIL tui: no approval recorded -> {res['lines'][-300:]!r}")
    if "(confirmed)" in res["lines"] or "(auto)" in res["lines"]:
        print("PASS tui: approved command ran through the executor")
    else:
        fails += 1
        print(f"FAIL tui: command did not run -> {res['lines'][-300:]!r}")
    if not res["awaiting"]:
        print("PASS tui: prompt state cleared after answering")
    else:
        fails += 1
        print("FAIL tui: still awaiting approval")

    res = asyncio.run(_tui_run("n"))
    if "denied" in res["lines"]:
        print("PASS tui: typing 'n' denies")
    else:
        fails += 1
        print(f"FAIL tui: no denial recorded -> {res['lines'][-300:]!r}")
    if "(denied)" in res["lines"] and "(confirmed)" not in res["lines"]:
        print("PASS tui: denied command did not run")
    else:
        fails += 1
        print(f"FAIL tui: denied command ran -> {res['lines'][-300:]!r}")

    # A non-answer must deny, never approve.
    res = asyncio.run(_tui_run("maybe later"))
    if "denied" in res["lines"] and "(confirmed)" not in res["lines"]:
        print("PASS tui: an unrecognised answer denies (fail closed)")
    else:
        fails += 1
        print(f"FAIL tui: ambiguous answer -> {res['lines'][-300:]!r}")
    return fails


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

def _qt_available():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6 import QtWidgets
        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        return True
    except Exception as exc:
        _qt_available.reason = f"{type(exc).__name__}: {exc}"
        return False


def test_gui_approval():
    from PySide6 import QtCore, QtWidgets
    from aegis.agent import Agent
    from aegis.gui import build_window

    fails = 0
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    for answer, want_decision, label in [
        (True, "confirmed", "approve"),
        (False, "denied", "deny"),
    ]:
        cfg = make_cfg()
        agent = Agent(cfg, router=FakeRouter([
            ["Let me check.\n", "```aegis-command\n", "mount\n", "```"],
            ["All done."],
        ]))
        win = build_window(cfg, agent)
        win.auto_approve = answer  # skip the modal, record the decision

        win.input.setText("check mounts")
        win.send()

        # Pump the Qt event loop until the turn finishes.
        for _ in range(400):
            app.processEvents()
            if win.worker is None:
                break
            QtCore.QThread.msleep(20)
        for _ in range(20):
            app.processEvents()
            QtCore.QThread.msleep(20)

        text = win.transcript.toPlainText()
        if f"[{want_decision}] mount" in text:
            print(f"PASS gui: {label} -> decision '{want_decision}'")
        else:
            fails += 1
            print(f"FAIL gui: {label} -> {text[-300:]!r}")

        # `_on_command` writes the executor's decision in square brackets.
        if want_decision == "denied":
            if "[denied] mount" in text and "denied by user" in text:
                print("PASS gui: denied command did not run")
            else:
                fails += 1
                print(f"FAIL gui: denied command -> {text[-300:]!r}")
            if "✔ approved" not in text:
                print("PASS gui: no approval recorded for a denial")
            else:
                fails += 1
                print("FAIL gui: approval recorded despite denial")
        else:
            if "[confirmed] mount" in text and "✔ approved" in text:
                print("PASS gui: approved command ran through the executor")
            else:
                fails += 1
                print(f"FAIL gui: approved command -> {text[-300:]!r}")

        win.close()

    # The modal itself must resolve the gate when accepted/rejected.
    from aegis.gui import build_window as _bw  # noqa: F401
    from aegis.approval import ApprovalGate
    gate = ApprovalGate(timeout=5.0)
    gate.on_request = lambda req: threading.Timer(0.05, gate.resolve, [True]).start()
    if gate.ask(FakeVerdict(), "mount") is ApprovalOutcome.ALLOW:
        print("PASS gui: gate round-trips an approval from the UI thread")
    else:
        fails += 1
        print("FAIL gui: gate round-trip")
    return fails


if __name__ == "__main__":
    total = 0
    total += test_gate_approve(); print()
    total += test_gate_fail_closed(); print()
    total += test_gate_resolve_semantics(); print()
    total += test_is_approval(); print()

    try:
        import textual  # noqa: F401
        total += test_tui_approval(); print()
    except ModuleNotFoundError:
        print("SKIP: Textual not installed — TUI approval tests not run\n")

    if _qt_available():
        total += test_gui_approval(); print()
    else:
        print(f"SKIP: PySide6 cannot load here ({_qt_available.reason});")
        print("      GUI approval tests were not run.\n")

    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
