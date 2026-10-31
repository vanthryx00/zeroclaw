"""Per-command "always allow" allowlist.

Covers the store's safety rules, Executor integration, the CLI, and the
three-way approval flow in both front-ends.

Run:  python3 tests/test_allowlist.py
"""

import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.allowlist import (MATCH_EXACT, MATCH_PREFIX, AllowStore,
                             is_rememberable, normalize)
from aegis.approval import (ApprovalGate, ApprovalOutcome, coerce_outcome,
                            parse_answer)
from aegis.executor import Executor
from aegis.safety import Level


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def make_cfg(mode="auto_safe"):
    from aegis.config import Config
    cfg = Config()
    cfg.validate()
    tmp = tempfile.mkdtemp()
    cfg.safety.mode = mode
    cfg.safety.workspace_root = os.path.join(tmp, "ws")
    os.makedirs(cfg.safety.workspace_root, exist_ok=True)
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    cfg.safety.allowlist_file = os.path.join(tmp, "allow.jsonl")
    cfg.learning.snippet_file = os.path.join(tmp, "s.jsonl")
    cfg.learning.experience_file = os.path.join(tmp, "e.jsonl")
    return cfg


class FakeVerdict:
    def __init__(self, level=Level.RISKY):
        self.level = level
        self.label = level.name.lower()
        self.reason = "test"


class FakeRouter:
    """Serves a queue of reply-chunks; the last reply repeats."""

    def __init__(self, replies):
        self.replies = [list(r) for r in replies]

    def _next(self):
        if len(self.replies) > 1:
            return self.replies.pop(0)
        return self.replies[0]

    def generate(self, messages, **kw):
        return "".join(self._next())

    def generate_stream(self, messages, **kw):
        for chunk in self._next():
            yield chunk

    def status(self):
        return "fake backend"


RISKY_REPLY = ["Let me check.\n", "```aegis-command\n", "mount\n", "```"]
DONE_REPLY = ["All done."]


# --------------------------------------------------------------------------
# store
# --------------------------------------------------------------------------

def test_store_basics():
    fails = 0
    tmp = tempfile.mkdtemp()
    store = AllowStore(os.path.join(tmp, "allow.jsonl"))

    if store.count() == 0 and not store.permits("mount", Level.RISKY):
        print("PASS store: starts empty and permits nothing")
    else:
        fails += 1
        print("FAIL store: empty store permitted something")

    rule = store.add("mount /dev/sdb1 /mnt", Level.RISKY)
    if rule and rule.pattern == "mount /dev/sdb1 /mnt":
        print("PASS store: a risky command can be remembered")
    else:
        fails += 1
        print(f"FAIL store: add -> {rule}")

    if store.permits("mount /dev/sdb1 /mnt", Level.RISKY):
        print("PASS store: the remembered command is permitted")
    else:
        fails += 1
        print("FAIL store: remembered command not permitted")

    # Re-remembering refreshes rather than duplicating.
    store.add("mount /dev/sdb1 /mnt", Level.RISKY)
    if store.count() == 1:
        print("PASS store: re-remembering refreshes instead of duplicating")
    else:
        fails += 1
        print(f"FAIL store: duplicate rule ({store.count()} entries)")

    found = store.find("mount /dev/sdb1 /mnt", Level.RISKY)
    store.record_hit(found.id)
    if store.get(found.id).hits == 1:
        print("PASS store: hits are counted so the CLI can show what is used")
    else:
        fails += 1
        print("FAIL store: hit not counted")

    if store.revoke(rule.id) and store.count() == 0:
        print("PASS store: revoke removes the rule")
    else:
        fails += 1
        print("FAIL store: revoke did not remove the rule")

    store.add("mount /dev/sdb1 /mnt", Level.RISKY)
    if store.clear() == 1 and store.count() == 0:
        print("PASS store: clear empties the allowlist")
    else:
        fails += 1
        print("FAIL store: clear did not empty the allowlist")

    if "No remembered commands" in store.render():
        print("PASS store: an empty allowlist renders a helpful message")
    else:
        fails += 1
        print("FAIL store: empty render")

    store.add("mount /dev/sdb1 /mnt", Level.RISKY)
    if "mount /dev/sdb1 /mnt" in store.render():
        print("PASS store: render lists the remembered command")
    else:
        fails += 1
        print("FAIL store: render missing the rule")

    return fails


def test_store_matching():
    """Exact matching is the whole safety value: an allow for one command must
    never authorise a longer command that appends something destructive."""
    fails = 0
    tmp = tempfile.mkdtemp()
    store = AllowStore(os.path.join(tmp, "allow.jsonl"))
    store.add("mount /dev/sdb1 /mnt", Level.RISKY)

    if not store.permits("mount /dev/sdb1 /mnt && rm -rf /", Level.RISKY):
        print("PASS match: exact rule rejects an appended command")
    else:
        fails += 1
        print("FAIL match: exact rule matched a chained command")

    if not store.permits("mount /dev/sdc1 /mnt", Level.RISKY):
        print("PASS match: exact rule rejects a different command")
    else:
        fails += 1
        print("FAIL match: exact rule matched a different command")

    if store.permits("  mount   /dev/sdb1    /mnt  ", Level.RISKY):
        print("PASS match: whitespace differences still match")
    else:
        fails += 1
        print("FAIL match: whitespace normalisation broken")

    # Prefix matching is opt-in and must be labelled as broader.
    p = store.add("systemctl status", Level.RISKY, match=MATCH_PREFIX)
    if p and p.match == MATCH_PREFIX and \
            store.permits("systemctl status nginx", Level.RISKY):
        print("PASS match: prefix rule matches a longer command (opt-in)")
    else:
        fails += 1
        print("FAIL match: prefix rule did not match")

    if "prefix" in p.describe():
        print("PASS match: prefix rules are labelled in the listing")
    else:
        fails += 1
        print("FAIL match: prefix rule not labelled")

    q = store.add("ls /tmp", Level.READ_ONLY, match="whatever")
    if q and q.match == MATCH_EXACT:
        print("PASS match: an unknown match type falls back to exact")
    else:
        fails += 1
        print("FAIL match: unknown match type was not normalised")

    if normalize("  a   b  ") == "a b":
        print("PASS match: normalize collapses whitespace")
    else:
        fails += 1
        print("FAIL match: normalize")

    return fails


def test_store_level_escalation():
    """A rule remembered at a lower level must stop applying if the command
    later classifies higher, or a new safety rule silently loses."""
    fails = 0
    tmp = tempfile.mkdtemp()
    store = AllowStore(os.path.join(tmp, "allow.jsonl"))
    store.add("nmap -sV host", Level.RISKY)

    if store.permits("nmap -sV host", Level.RISKY):
        print("PASS escalate: rule applies at the level it was remembered")
    else:
        fails += 1
        print("FAIL escalate: rule did not apply at remembered level")

    if not store.permits("nmap -sV host", Level.OFFENSIVE):
        print("PASS escalate: rule stops applying when reclassified higher")
    else:
        fails += 1
        print("FAIL escalate: a RISKY rule authorised an OFFENSIVE command")

    if not store.permits("nmap -sV host", Level.BLOCKED):
        print("PASS escalate: rule never applies to a BLOCKED command")
    else:
        fails += 1
        print("FAIL escalate: a rule authorised a BLOCKED command")

    # An unparseable level must not be trusted.
    store._store.add({"pattern": "echo hi", "match": "exact",
                      "level": "bogus", "hits": 0}, id_prefix="alw")
    if not store.permits("echo hi", Level.RISKY):
        print("PASS escalate: an unparseable rule is not trusted")
    else:
        fails += 1
        print("FAIL escalate: unparseable rule was trusted")

    return fails


def test_store_refuses_unrememberable():
    fails = 0
    tmp = tempfile.mkdtemp()
    store = AllowStore(os.path.join(tmp, "allow.jsonl"))

    for level in (Level.OFFENSIVE, Level.BLOCKED):
        if store.add("nmap -sV host", level) is None:
            print(f"PASS refuse: {level.name} can never be remembered")
        else:
            fails += 1
            print(f"FAIL refuse: {level.name} was remembered")

    if is_rememberable(Level.RISKY) and is_rememberable(Level.SAFE_WRITE) \
            and not is_rememberable(Level.BLOCKED):
        print("PASS refuse: only read-only/safe-write/risky are rememberable")
    else:
        fails += 1
        print("FAIL refuse: is_rememberable")

    if store.add("", Level.RISKY) is None:
        print("PASS refuse: an empty command is not remembered")
    else:
        fails += 1
        print("FAIL refuse: empty command was remembered")

    # A hand-edited or legacy allowlist must not be able to bless a BLOCKED
    # command. This is the adversarial case: the file is user-writable.
    path = os.path.join(tmp, "tampered.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "alw-evil", "pattern": "rm -rf /",
                             "match": "exact", "level": "risky",
                             "hits": 0, "created": 0.0}) + "\n")
    tampered = AllowStore(path)
    if not tampered.permits("rm -rf /", Level.BLOCKED):
        print("PASS refuse: a hand-edited rule cannot bless a BLOCKED command")
    else:
        fails += 1
        print("FAIL refuse: a tampered rule authorised a BLOCKED command")

    return fails


# --------------------------------------------------------------------------
# executor integration
# --------------------------------------------------------------------------

def test_executor_allowlisted():
    fails = 0
    cfg = make_cfg("auto_safe")
    store = AllowStore(cfg.safety.allowlist_file)
    store.add("mount", Level.RISKY)

    calls = []
    ex = Executor(cfg, confirm=lambda v, c: calls.append(c) or False,
                  allowlist=store)
    res = ex.run("mount")

    if not calls:
        print("PASS executor: an allowlisted command skips the prompt")
    else:
        fails += 1
        print(f"FAIL executor: still prompted for {calls}")

    if res.decision == "allowlisted":
        print("PASS executor: decision is recorded as 'allowlisted'")
    else:
        fails += 1
        print(f"FAIL executor: decision -> {res.decision!r}")

    # A near-miss must still prompt.
    calls.clear()
    ex.run("mount /dev/sdc1 /mnt")
    if calls:
        print("PASS executor: a non-matching command still prompts")
    else:
        fails += 1
        print("FAIL executor: a non-matching command was auto-approved")

    return fails


def test_executor_allow_always_persists():
    fails = 0
    cfg = make_cfg("auto_safe")
    store = AllowStore(cfg.safety.allowlist_file)

    ex = Executor(cfg, confirm=lambda v, c: ApprovalOutcome.ALLOW_ALWAYS,
                  allowlist=store)
    res = ex.run("mount")

    if store.count() == 1 and store.permits("mount", Level.RISKY):
        print("PASS executor: 'always allow' persists a rule")
    else:
        fails += 1
        print(f"FAIL executor: rule not persisted ({store.count()} entries)")

    # The first run *was* confirmed by the user; the rule is for next time.
    # Recording it as "allowlisted" here would overstate what happened.
    if res.decision == "confirmed":
        print("PASS executor: the first 'always allow' run is recorded as confirmed")
    else:
        fails += 1
        print(f"FAIL executor: decision -> {res.decision!r}")

    # Second time round it must not ask again.
    calls = []
    ex2 = Executor(cfg, confirm=lambda v, c: calls.append(c) or False,
                   allowlist=AllowStore(cfg.safety.allowlist_file))
    ex2.run("mount")
    if not calls:
        print("PASS executor: the rule applies on the next run")
    else:
        fails += 1
        print(f"FAIL executor: prompted again despite the rule ({calls})")

    return fails


def test_executor_blocked_wins():
    """The allowlist must never outrank a hard block."""
    fails = 0
    cfg = make_cfg("auto_full")
    path = cfg.safety.allowlist_file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "alw-evil", "pattern": "rm -rf /",
                             "match": "exact", "level": "risky",
                             "hits": 0, "created": 0.0}) + "\n")

    ex = Executor(cfg, confirm=lambda v, c: True,
                  allowlist=AllowStore(path))
    res = ex.run("rm -rf /")

    if res.decision == "blocked" and not res.ran:
        print("PASS executor: BLOCKED still wins over an allowlist rule")
    else:
        fails += 1
        print(f"FAIL executor: blocked command -> {res.decision!r} ran={res.ran}")

    return fails


# --------------------------------------------------------------------------
# approval outcome plumbing
# --------------------------------------------------------------------------

def test_outcome_plumbing():
    fails = 0

    cases = [("a", ApprovalOutcome.ALLOW_ALWAYS),
             ("always", ApprovalOutcome.ALLOW_ALWAYS),
             ("y", ApprovalOutcome.ALLOW),
             ("n", ApprovalOutcome.DENY),
             ("", ApprovalOutcome.DENY),
             ("maybe", ApprovalOutcome.DENY)]
    ok = True
    for text, want in cases:
        got = parse_answer(text)
        if got is not want:
            ok = False
            print(f"FAIL answer: {text!r} -> {got} want {want}")
    if ok:
        print("PASS answer: y/a/n/other map to the right outcome (deny by default)")
    else:
        fails += 1

    if coerce_outcome(True) is ApprovalOutcome.ALLOW and \
            coerce_outcome(False) is ApprovalOutcome.DENY and \
            coerce_outcome(None) is ApprovalOutcome.DENY and \
            coerce_outcome("always") is ApprovalOutcome.ALLOW_ALWAYS:
        print("PASS answer: plain bools from old confirm callbacks still work")
    else:
        fails += 1
        print("FAIL answer: coerce_outcome")

    # The gate must carry ALLOW_ALWAYS through, not flatten it to a bool.
    gate = ApprovalGate(timeout=5.0)
    gate.on_request = lambda req: threading.Timer(
        0.05, gate.resolve_outcome, [ApprovalOutcome.ALLOW_ALWAYS]).start()
    if gate.ask(FakeVerdict(), "mount") is ApprovalOutcome.ALLOW_ALWAYS:
        print("PASS answer: the gate round-trips ALLOW_ALWAYS")
    else:
        fails += 1
        print("FAIL answer: gate flattened the outcome")

    # A non-rememberable level must be flagged on the request.
    gate2 = ApprovalGate(timeout=5.0)
    seen = {}
    gate2.on_request = lambda req: (
        seen.update(rememberable=req.rememberable),
        gate2.resolve(False))
    gate2.ask(FakeVerdict(Level.BLOCKED), "rm -rf /")
    if seen.get("rememberable") is False:
        print("PASS answer: a BLOCKED request is marked non-rememberable")
    else:
        fails += 1
        print(f"FAIL answer: rememberable -> {seen.get('rememberable')}")

    gate3 = ApprovalGate(timeout=5.0)
    gate3.on_request = lambda req: gate3.resolve(False)
    if gate3.ask(FakeVerdict(Level.RISKY), "mount") is not None:
        seen2 = {}
        gate3.on_request = lambda req: (
            seen2.update(rememberable=req.rememberable), gate3.resolve(False))
        gate3.reset()
        gate3.ask(FakeVerdict(Level.RISKY), "mount")
        if seen2.get("rememberable") is True:
            print("PASS answer: a RISKY request is marked rememberable")
        else:
            fails += 1
            print(f"FAIL answer: risky rememberable -> {seen2.get('rememberable')}")

    return fails


# --------------------------------------------------------------------------
# TUI
# --------------------------------------------------------------------------

def _tui_lines(app):
    from textual.widgets import RichLog
    log = app.query_one("#log", RichLog)
    return " ".join(str(getattr(line, "text", line)) for line in log.lines)


async def _tui_run(cfg, agent, answer, expect_prompt=True):
    from textual.widgets import Input
    from aegis.tui import build_app

    app = build_app(cfg, agent)
    async with app.run_test() as pilot:
        app.query_one("#input", Input).value = "check mounts"
        await pilot.press("enter")

        prompted = False
        for _ in range(120):
            await pilot.pause(0.05)
            if app._awaiting_approval:
                prompted = True
                break

        mid = _tui_lines(app)
        if prompted:
            app.query_one("#input", Input).value = answer
            await pilot.press("enter")

        for _ in range(120):
            await pilot.pause(0.05)
        await pilot.pause(0.3)
        return {"prompted": prompted, "mid": mid,
                "lines": _tui_lines(app),
                "awaiting": app._awaiting_approval}


def test_tui_always_allow():
    import asyncio
    from aegis.agent import Agent

    fails = 0
    cfg = make_cfg("auto_safe")

    agent = Agent(cfg, router=FakeRouter([RISKY_REPLY, DONE_REPLY]))
    res = asyncio.run(_tui_run(cfg, agent, "a"))

    if res["prompted"]:
        print("PASS tui: risky command prompted with the three-way choice")
    else:
        fails += 1
        print("FAIL tui: no prompt")
        return fails

    if "always" in res["mid"]:
        print("PASS tui: the prompt advertises the 'always allow' option")
    else:
        fails += 1
        print(f"FAIL tui: prompt text -> {res['mid'][:200]!r}")

    if "always allowed" in res["lines"]:
        print("PASS tui: typing 'a' records an always-allow")
    else:
        fails += 1
        print(f"FAIL tui: no always-allow recorded -> {res['lines'][-300:]!r}")

    store = AllowStore(cfg.safety.allowlist_file)
    if store.count() == 1 and store.permits("mount", Level.RISKY):
        print("PASS tui: the rule was persisted to the allowlist")
    else:
        fails += 1
        print(f"FAIL tui: rule not persisted ({store.count()} entries)")

    # Second turn, same config: the prompt must not appear again.
    agent2 = Agent(cfg, router=FakeRouter([RISKY_REPLY, DONE_REPLY]))
    res2 = asyncio.run(_tui_run(cfg, agent2, "", expect_prompt=False))

    if not res2["prompted"]:
        print("PASS tui: the remembered command no longer prompts")
    else:
        fails += 1
        print("FAIL tui: prompted again despite the rule")

    if "(allowlisted)" in res2["lines"] or "allowlisted" in res2["lines"]:
        print("PASS tui: the second run is recorded as allowlisted")
    else:
        fails += 1
        print(f"FAIL tui: second run -> {res2['lines'][-300:]!r}")

    # A plain 'y' must NOT create a rule.
    cfg3 = make_cfg("auto_safe")
    agent3 = Agent(cfg3, router=FakeRouter([RISKY_REPLY, DONE_REPLY]))
    asyncio.run(_tui_run(cfg3, agent3, "y"))
    if AllowStore(cfg3.safety.allowlist_file).count() == 0:
        print("PASS tui: a one-off 'y' approval does not create a rule")
    else:
        fails += 1
        print("FAIL tui: 'y' created a standing rule")

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


def test_gui_always_allow():
    from PySide6 import QtCore, QtWidgets
    from aegis.agent import Agent
    from aegis.gui import build_window

    fails = 0
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    cfg = make_cfg("auto_safe")
    agent = Agent(cfg, router=FakeRouter([RISKY_REPLY, DONE_REPLY]))
    win = build_window(cfg, agent)
    win.auto_approve = ApprovalOutcome.ALLOW_ALWAYS

    win.input.setText("check mounts")
    win.send()

    for _ in range(400):
        app.processEvents()
        if win.worker is None:
            break
        QtCore.QThread.msleep(20)
    for _ in range(20):
        app.processEvents()
        QtCore.QThread.msleep(20)

    text = win.transcript.toPlainText()
    if "always allowed" in text:
        print("PASS gui: 'Always allow' is recorded in the transcript")
    else:
        fails += 1
        print(f"FAIL gui: no always-allow note -> {text[-300:]!r}")

    store = AllowStore(cfg.safety.allowlist_file)
    if store.count() == 1 and store.permits("mount", Level.RISKY):
        print("PASS gui: the rule was persisted to the allowlist")
    else:
        fails += 1
        print(f"FAIL gui: rule not persisted ({store.count()} entries)")

    win.close()

    # Second run with the same config must not prompt or run the modal.
    agent2 = Agent(cfg, router=FakeRouter([RISKY_REPLY, DONE_REPLY]))
    win2 = build_window(cfg, agent2)
    prompted = []
    win2.auto_approve = lambda *a: prompted.append(1) or False

    win2.input.setText("check mounts")
    win2.send()
    for _ in range(400):
        app.processEvents()
        if win2.worker is None:
            break
        QtCore.QThread.msleep(20)
    for _ in range(20):
        app.processEvents()
        QtCore.QThread.msleep(20)

    text2 = win2.transcript.toPlainText()
    if not prompted and "[allowlisted] mount" in text2:
        print("PASS gui: the remembered command skips the dialog")
    else:
        fails += 1
        print(f"FAIL gui: prompted={bool(prompted)} -> {text2[-300:]!r}")
    win2.close()

    # The dialog must not offer a standing authorisation for a level that may
    # never be remembered, and must offer it for one that may.
    dlg_cls = build_window(make_cfg(), None)._approval_dialog_class

    def _always_button(rememberable):
        dlg = dlg_cls("cmd", "risky", "reason", rememberable=rememberable)
        btns = [b for b in dlg.findChildren(QtWidgets.QPushButton)
                if "Always" in b.text()]
        state = btns[0].isEnabled() if btns else None
        dlg.close()
        return state

    if _always_button(False) is False:
        print("PASS gui: 'Always allow' is disabled for a non-rememberable level")
    else:
        fails += 1
        print("FAIL gui: 'Always allow' enabled for a BLOCKED command")

    if _always_button(True) is True:
        print("PASS gui: 'Always allow' is offered for a rememberable level")
    else:
        fails += 1
        print("FAIL gui: 'Always allow' disabled for a risky command")

    return fails


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_allow():
    import argparse
    from aegis.cli import cmd_allow

    fails = 0
    cfg = make_cfg("auto_safe")
    store = AllowStore(cfg.safety.allowlist_file)

    def ns(**kw):
        return argparse.Namespace(**kw)

    if cmd_allow(cfg, ns(allow_action="list")) == 0:
        print("PASS cli: 'allow list' works on an empty allowlist")
    else:
        fails += 1
        print("FAIL cli: empty list returned non-zero")

    if cmd_allow(cfg, ns(allow_action="add", allow_arg="mount",
                         prefix=False)) == 0 and store.count() == 1:
        print("PASS cli: 'allow add <command>' remembers a risky command")
    else:
        fails += 1
        print("FAIL cli: add did not persist")

    # Offensive tooling must be refused with a pointer to `aegis scope`.
    if cmd_allow(cfg, ns(allow_action="add",
                         allow_arg="nmap -sV 10.0.0.1",
                         prefix=False)) == 1:
        print("PASS cli: an offensive command is refused")
    else:
        fails += 1
        print("FAIL cli: offensive command was remembered")

    if store.count() == 1:
        print("PASS cli: the refused command was not stored")
    else:
        fails += 1
        print(f"FAIL cli: allowlist grew to {store.count()}")

    rid = store.all()[0].id
    if cmd_allow(cfg, ns(allow_action="rm", allow_arg=rid)) == 0 \
            and store.count() == 0:
        print("PASS cli: 'allow rm <id>' revokes a rule")
    else:
        fails += 1
        print("FAIL cli: rm did not revoke")

    cmd_allow(cfg, ns(allow_action="add", allow_arg="mount", prefix=False))
    if cmd_allow(cfg, ns(allow_action="clear")) == 0 and store.count() == 0:
        print("PASS cli: 'allow clear' empties the allowlist")
    else:
        fails += 1
        print("FAIL cli: clear did not empty")

    # Use a RISKY command: a rule remembered at a lower level deliberately
    # refuses to cover a higher one, so a read-only prefix rule would not
    # (and must not) authorise anything risky.
    cmd_allow(cfg, ns(allow_action="add", allow_arg="mount", prefix=True))
    rule = store.all()[0]
    if rule.match == MATCH_PREFIX and \
            store.permits("mount /dev/sdb1 /mnt", Level.RISKY):
        print("PASS cli: --prefix creates a labelled prefix rule")
    else:
        fails += 1
        print(f"FAIL cli: --prefix -> {rule.match!r} level={rule.level!r}")

    # A read-only prefix rule must not silently cover a risky command.
    cfg2 = make_cfg("auto_safe")
    s2 = AllowStore(cfg2.safety.allowlist_file)
    s2.add("systemctl status", Level.READ_ONLY, match=MATCH_PREFIX)
    if not s2.permits("systemctl status nginx", Level.RISKY):
        print("PASS cli: a read-only prefix rule does not cover a risky command")
    else:
        fails += 1
        print("FAIL cli: read-only prefix rule escalated to risky")

    return fails


if __name__ == "__main__":
    total = 0
    total += test_store_basics(); print()
    total += test_store_matching(); print()
    total += test_store_level_escalation(); print()
    total += test_store_refuses_unrememberable(); print()
    total += test_executor_allowlisted(); print()
    total += test_executor_allow_always_persists(); print()
    total += test_executor_blocked_wins(); print()
    total += test_outcome_plumbing(); print()

    try:
        import textual  # noqa: F401
        total += test_tui_always_allow(); print()
    except ModuleNotFoundError:
        print("SKIP: Textual not installed — TUI allowlist tests not run\n")

    if _qt_available():
        total += test_gui_always_allow(); print()
    else:
        print(f"SKIP: PySide6 cannot load here ({_qt_available.reason});")
        print("      GUI allowlist tests were not run.\n")

    total += test_cli_allow(); print()

    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
