"""End-to-end agent loop test with a scripted (mock) backend.

Proves: command extraction -> safety classification -> execution -> observation
-> follow-up -> final answer, without needing a real model.

Run:  python3 tests/test_agent_loop.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.agent import Agent, COMMAND_RE
from aegis.brain.base import Backend
from aegis.config import Config


class ScriptedBackend(Backend):
    """Returns pre-scripted replies in order."""

    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen_messages = []

    def available(self):
        return True

    def generate(self, messages, **kwargs):
        self.seen_messages.append(messages)
        return self.replies.pop(0)


class ScriptedRouter:
    def __init__(self, replies):
        self.backend = ScriptedBackend(replies)

    def generate(self, messages, **kwargs):
        return self.backend.generate(messages, **kwargs)

    def select(self):
        return self.backend

    def status(self):
        return "scripted"


def main():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-test-")
    workspace = os.path.join(tmp, "aegis-workspace")
    os.makedirs(workspace, exist_ok=True)

    cfg = Config()
    cfg.safety.mode = "auto_safe"  # pwd is read-only -> auto-runs
    cfg.safety.workspace_root = workspace
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    cfg.interface.history_file = os.path.join(tmp, "history")
    cfg.validate()

    replies = [
        "Let me check where we are.\n\n```aegis-command\npwd\n```",
        "You are in the workspace. All done.",
    ]
    agent = Agent(cfg, router=ScriptedRouter(replies))

    collected = []
    commands = []

    def on_text(prose):
        collected.append(prose)

    def on_command(command, result):
        commands.append((command, result.ran, result.exit_code))

    resp = agent.ask("where am i?", on_text=on_text, on_command=on_command)

    print("steps:", [s.kind for s in resp.steps])
    print("commands run:", commands)
    print("final:", resp.final[:80])

    # 1. Exactly one command was executed and it ran.
    if len(commands) != 1 or not commands[0][1]:
        failures += 1
        print("FAIL expected exactly one executed command")
    else:
        print("PASS command executed")

    # 2. The observation was fed back (backend saw a 3rd message set including it).
    backend = agent.router.backend
    last_messages = backend.seen_messages[-1]
    joined = "\n".join(m.content for m in last_messages)
    if "OBSERVATION" not in joined:
        failures += 1
        print("FAIL observation not fed back to model")
    else:
        print("PASS observation fed back")

    # 3. Final answer returned and no leftover command block.
    if "All done" not in resp.final:
        failures += 1
        print("FAIL final answer missing")
    else:
        print("PASS final answer returned")

    # 4. Audit log recorded the run.
    audit = open(cfg.interface.audit_log).read()
    if '"command": "pwd"' not in audit:
        failures += 1
        print("FAIL audit log missing the command")
    else:
        print("PASS audit log recorded the command")

    # 5. A blocked command is refused and never run.
    blocked_agent = Agent(
        cfg,
        router=ScriptedRouter([
            "```aegis-command\nrm -rf /\n```",
            "I cannot run that.",
        ]),
    )
    ran = []
    blocked_agent.ask("wipe", on_command=lambda c, r: ran.append(r.ran))
    if any(ran):
        failures += 1
        print("FAIL blocked command ran")
    else:
        print("PASS blocked command refused")

    print()
    print(f"TOTAL FAILURES: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
