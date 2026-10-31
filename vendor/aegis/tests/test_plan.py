"""Whole-plan approval (#47): parse, render, approve/deny, safety invariants.

* ```aegis-plan fenced blocks parse into classified steps
* one approval runs the whole plan; a denial runs nothing
* approval NEVER bypasses BLOCKED — the executor refuses and the plan halts
* a failed step stops the plan; nothing after it runs
* plan proposal / decision / step / halt / completion all hit the audit log

Run:  python3 tests/test_plan.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.agent import Agent
from aegis.plan import (MAX_PLAN_STEPS, PLAN_FENCE_RE, Plan, PlanError,
                        plan_verdict)
from aegis.safety import LEVEL_LABEL, Level


# --------------------------------------------------------------------------
# helpers (same shape as tests/test_approval.py)

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
    cfg._tmp = tmp
    return cfg


def read_audit(cfg):
    events = []
    path = cfg.interface.audit_log
    if not os.path.exists(path):
        return events
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def audit_events(cfg):
    return [e.get("event") for e in read_audit(cfg)]


PLAN_BODY = """## command
ls /tmp
## file path=plan-out.txt
hello plan
## snippet title="greet" lang=python tags=demo
print("hi")
## remember tags=workflow
check disk space before installs
"""


def plan_reply(body=PLAN_BODY, prose="Here is my plan."):
    return f"{prose}\n```aegis-plan\n{body}```"


# --------------------------------------------------------------------------
# parsing

def test_parse_plan():
    fails = 0
    cfg = make_cfg()
    plan = Plan.parse(PLAN_BODY, cfg)
    if len(plan.steps) == 4:
        print("PASS parse: 4 steps parsed")
    else:
        fails += 1
        print(f"FAIL parse: {len(plan.steps)} steps, want 4")

    kinds = [s.kind for s in plan.steps]
    if kinds == ["command", "file", "snippet", "remember"]:
        print("PASS parse: step kinds in order")
    else:
        fails += 1
        print(f"FAIL parse: kinds -> {kinds}")

    if plan.steps[0].level == Level.READ_ONLY:
        print("PASS parse: 'ls /tmp' classified read-only")
    else:
        fails += 1
        print(f"FAIL parse: ls level -> {plan.steps[0].label}")

    if plan.steps[1].attrs.get("path") == "plan-out.txt" \
            and plan.steps[1].content == "hello plan":
        print("PASS parse: file step attrs + content")
    else:
        fails += 1
        print(f"FAIL parse: file step -> {plan.steps[1].attrs!r} "
              f"{plan.steps[1].content!r}")

    if plan.steps[2].attrs.get("title") == "greet" \
            and plan.steps[2].attrs.get("lang") == "python":
        print("PASS parse: snippet attrs (quoted title handled)")
    else:
        fails += 1
        print(f"FAIL parse: snippet attrs -> {plan.steps[2].attrs!r}")

    if plan.steps[3].attrs.get("tags") == "workflow":
        print("PASS parse: remember tags")
    else:
        fails += 1
        print(f"FAIL parse: remember attrs -> {plan.steps[3].attrs!r}")

    if plan.max_level == Level.SAFE_WRITE:
        print("PASS parse: max_level is safe-write")
    else:
        fails += 1
        print(f"FAIL parse: max_level -> {plan.max_level_label}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_parse_rejects():
    fails = 0
    cfg = make_cfg()

    cases = [
        ("empty plan", "", "no steps"),
        ("blank plan", "\n\n  \n", "no steps"),
        ("unknown kind", "## frobnicate\nx\n", "unknown step"),
        ("text outside steps", "hello\n## command\nls\n", "outside any step"),
        ("file without path", "## file\nbody\n", "needs path"),
        ("empty command", "## command\n\n", "empty command"),
        ("empty remember", "## remember tags=x\n\n", "empty content"),
    ]
    for label, body, hint in cases:
        try:
            Plan.parse(body, cfg)
            fails += 1
            print(f"FAIL parse-reject: {label} parsed without error")
        except PlanError as exc:
            if hint in str(exc):
                print(f"PASS parse-reject: {label} refused ({exc})")
            else:
                fails += 1
                print(f"FAIL parse-reject: {label} wrong reason: {exc}")

    too_many = "".join(f"## command\nls /tmp\n" for _ in range(MAX_PLAN_STEPS + 1))
    try:
        Plan.parse(too_many, cfg)
        fails += 1
        print("FAIL parse-reject: over-limit plan parsed")
    except PlanError as exc:
        print(f"PASS parse-reject: over-limit refused ({exc})")

    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_blocked_classified_at_parse():
    fails = 0
    cfg = make_cfg()
    plan = Plan.parse("## command\nrm -rf /\n", cfg)
    step = plan.steps[0]
    if step.level == Level.BLOCKED:
        print("PASS parse: 'rm -rf /' classified BLOCKED at parse time")
    else:
        fails += 1
        print(f"FAIL parse: rm -rf / level -> {step.label}")
    if plan.has_blocked and plan.max_level_label == "BLOCKED":
        print("PASS parse: plan reports has_blocked / max label")
    else:
        fails += 1
        print("FAIL parse: has_blocked/max_level_label wrong")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


# --------------------------------------------------------------------------
# rendering + verdict

def test_render():
    fails = 0
    cfg = make_cfg()
    plan = Plan.parse("## command\nls /tmp\n## command\nrm -rf /\n", cfg)
    text = plan.render()
    checks = [
        ("step count", "2 step(s)" in text),
        ("numbered steps", "1." in text and "2." in text),
        ("labels", "[read-only]" in text and "[BLOCKED]" in text),
        ("reasons", "reason:" in text),
        ("blocked warning", "BLOCKED step(s)" in text),
        ("headlines", "ls /tmp" in text),
    ]
    for label, ok in checks:
        if ok:
            print(f"PASS render: {label}")
        else:
            fails += 1
            print(f"FAIL render: {label}\n---\n{text}\n---")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_plan_verdict():
    fails = 0
    cfg = make_cfg()
    plan = Plan.parse("## command\nmount /dev/sdb1 /mnt\n", cfg)
    verdict = plan_verdict(plan)
    if verdict.level == Level.RISKY and verdict.label == "risky":
        print("PASS verdict: level/label follow the hottest step")
    else:
        fails += 1
        print(f"FAIL verdict: {verdict.level} {verdict.label}")
    if verdict.allowed and "whole-plan approval" in verdict.reason:
        print("PASS verdict: allowed + reason for the gate prompt")
    else:
        fails += 1
        print(f"FAIL verdict: allowed={verdict.allowed} reason={verdict.reason!r}")

    blocked = Plan.parse("## command\nrm -rf /\n", cfg)
    bv = plan_verdict(blocked)
    if bv.level == Level.BLOCKED and not bv.allowed:
        print("PASS verdict: BLOCKED plan is not 'allowed' (gate shows it raw)")
    else:
        fails += 1
        print(f"FAIL verdict: blocked plan -> {bv.level} allowed={bv.allowed}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


# --------------------------------------------------------------------------
# agent execution

def _agent_with_plan(cfg, body, confirm):
    agent = Agent(cfg, router=FakeRouter([[plan_reply(body)], ["All done."]]),
                  plan_confirm=confirm)
    return agent


def test_approve_executes_all():
    fails = 0
    cfg = make_cfg()
    agent = _agent_with_plan(cfg, PLAN_BODY, lambda plan: True)
    agent.ask("do the plan")

    out = os.path.join(cfg.safety.workspace_root, "plan-out.txt")
    if os.path.exists(out) and open(out).read() == "hello plan":
        print("PASS approve: file step executed")
    else:
        fails += 1
        print("FAIL approve: plan-out.txt missing or wrong")

    saved = [s.title for s in agent.learning.snippets.all()]
    if "greet" in saved:
        print("PASS approve: snippet step executed")
    else:
        fails += 1
        print(f"FAIL approve: snippet not saved -> {saved}")

    remembered = [e.title for e in agent.learning.experiences.by_kind("lesson")]
    if remembered:
        print("PASS approve: remember step executed")
    else:
        fails += 1
        print("FAIL approve: lesson not recorded")
    events = audit_events(cfg)
    for want in ("plan_proposed", "plan_decision", "plan_completed"):
        if want in events:
            print(f"PASS approve: audit has {want}")
        else:
            fails += 1
            print(f"FAIL approve: audit missing {want} -> {events}")
    decisions = [e for e in read_audit(cfg)
                 if e.get("event") == "plan_decision"]
    if decisions and decisions[-1].get("approved") is True:
        print("PASS approve: plan_decision recorded approved=True")
    else:
        fails += 1
        print(f"FAIL approve: plan_decision -> {decisions}")
    if "plan_halted" in events:
        fails += 1
        print("FAIL approve: plan_halted present on a good run")
    else:
        print("PASS approve: no halt on a good run")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_deny_runs_nothing():
    fails = 0
    cfg = make_cfg()
    agent = _agent_with_plan(cfg, PLAN_BODY, lambda plan: False)
    resp = agent.ask("do the plan")

    out = os.path.join(cfg.safety.workspace_root, "plan-out.txt")
    if not os.path.exists(out):
        print("PASS deny: file step did not run")
    else:
        fails += 1
        print("FAIL deny: plan-out.txt was written despite denial")

    observations = " ".join(s.content for s in resp.steps
                          if s.kind == "observation")
    if "DENIED" in observations:
        print("PASS deny: observation reports the denial")
    else:
        fails += 1
        print(f"FAIL deny: observations -> {observations[:200]!r}")

    events = audit_events(cfg)
    if "plan_decision" in events and "plan_completed" not in events:
        print("PASS deny: decision audited, no completion")
    else:
        fails += 1
        print(f"FAIL deny: events -> {events}")
    # No command executions at all on a denied plan.
    if "execute" not in events:
        print("PASS deny: executor never ran")
    else:
        fails += 1
        print(f"FAIL deny: executor ran -> {events}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_blocked_refused_when_approved():
    fails = 0
    cfg = make_cfg()
    body = ("## command\nls /tmp\n"
            "## command\nrm -rf /\n"
            "## file path=should-not-exist.txt\nafter blocked\n")
    agent = _agent_with_plan(cfg, body, lambda plan: True)
    resp = agent.ask("do the plan")

    observations = " ".join(s.content for s in resp.steps
                          if s.kind == "observation")
    if "HALTED at step 2" in observations:
        print("PASS blocked: plan halted at the BLOCKED step")
    else:
        fails += 1
        print(f"FAIL blocked: observations -> {observations[:300]!r}")

    after = os.path.join(cfg.safety.workspace_root, "should-not-exist.txt")
    if not os.path.exists(after):
        print("PASS blocked: steps after the BLOCKED step did not run")
    else:
        fails += 1
        print("FAIL blocked: step 3 ran despite the halt")

    blocked_runs = [e for e in read_audit(cfg)
                    if e.get("event") == "execute"
                    and e.get("decision") == "blocked"]
    if blocked_runs:
        print("PASS blocked: executor hard-blocked it (audit decision=blocked)")
    else:
        fails += 1
        print("FAIL blocked: no blocked execute event in audit")

    halts = [e for e in read_audit(cfg) if e.get("event") == "plan_halted"]
    if halts and halts[0].get("at_step") == 2:
        print("PASS blocked: plan_halted audited at step 2")
    else:
        fails += 1
        print(f"FAIL blocked: plan_halted -> {halts}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_midplan_failure_stops():
    fails = 0
    cfg = make_cfg()
    body = ("## command\nls /definitely/not/a/real/dir-xyz\n"
            "## file path=should-not-exist-2.txt\nafter failure\n")
    agent = _agent_with_plan(cfg, body, lambda plan: True)
    resp = agent.ask("do the plan")

    observations = " ".join(s.content for s in resp.steps
                          if s.kind == "observation")
    if "HALTED at step 1" in observations:
        print("PASS midplan: halted at the failing step")
    else:
        fails += 1
        print(f"FAIL midplan: observations -> {observations[:300]!r}")

    after = os.path.join(cfg.safety.workspace_root, "should-not-exist-2.txt")
    if not os.path.exists(after):
        print("PASS midplan: later steps did not run after failure")
    else:
        fails += 1
        print("FAIL midplan: step 2 ran despite step 1 failing")

    events = audit_events(cfg)
    if "plan_halted" in events and "plan_completed" not in events:
        print("PASS midplan: halt audited, no false completion")
    else:
        fails += 1
        print(f"FAIL midplan: events -> {events}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_no_handler_denies():
    fails = 0
    cfg = make_cfg()
    agent = Agent(cfg, router=FakeRouter([[plan_reply()], ["All done."]]))
    resp = agent.ask("do the plan")

    out = os.path.join(cfg.safety.workspace_root, "plan-out.txt")
    if not os.path.exists(out):
        print("PASS no-handler: nothing ran without an approval handler")
    else:
        fails += 1
        print("FAIL no-handler: file was written with no handler")

    observations = " ".join(s.content for s in resp.steps
                          if s.kind == "observation")
    if "no plan approval handler" in observations:
        print("PASS no-handler: observation explains the refusal")
    else:
        fails += 1
        print(f"FAIL no-handler: observations -> {observations[:200]!r}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_plan_wins_over_action_blocks():
    fails = 0
    cfg = make_cfg()
    reply = (plan_reply("## file path=plan.txt\nfrom plan\n")
             + "\n```aegis-command\nls /tmp\n```")
    agent = Agent(cfg, router=FakeRouter([[reply], ["All done."]]),
                  plan_confirm=lambda plan: True)
    agent.ask("do it")

    ws = cfg.safety.workspace_root
    if os.path.exists(os.path.join(ws, "plan.txt")):
        print("PASS precedence: plan steps executed")
    else:
        fails += 1
        print("FAIL precedence: plan file missing")

    # The standalone command block in the same reply must be ignored; only
    # the plan's single file step ran, so no command executions happened.
    cmds = [e for e in read_audit(cfg) if e.get("event") == "execute"]
    if not cmds:
        print("PASS precedence: standalone action block ignored")
    else:
        fails += 1
        print(f"FAIL precedence: standalone command ran -> {cmds}")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


def test_fence_regex():
    fails = 0
    m = PLAN_FENCE_RE.findall("x\n```aegis-plan\n## command\nls\n```\ny")
    if m and m[0].strip().startswith("## command"):
        print("PASS fence: plan block extracted")
    else:
        fails += 1
        print(f"FAIL fence: -> {m}")
    if not PLAN_FENCE_RE.search("```aegis-command\nls\n```"):
        print("PASS fence: ordinary action blocks do not match")
    else:
        fails += 1
        print("FAIL fence: matched a non-plan block")
    assert fails == 0, f"{fails} check(s) failed"
    return fails


if __name__ == "__main__":
    total = 0
    total += test_parse_plan(); print()
    total += test_parse_rejects(); print()
    total += test_blocked_classified_at_parse(); print()
    total += test_render(); print()
    total += test_plan_verdict(); print()
    total += test_approve_executes_all(); print()
    total += test_deny_runs_nothing(); print()
    total += test_blocked_refused_when_approved(); print()
    total += test_midplan_failure_stops(); print()
    total += test_no_handler_denies(); print()
    total += test_plan_wins_over_action_blocks(); print()
    total += test_fence_regex(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
