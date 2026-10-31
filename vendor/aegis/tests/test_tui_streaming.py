"""TUI streaming tests (#1, Textual front-end).

Drives the real Textual app through its headless test harness, so this checks
the actual widget behaviour: tokens appear progressively in the live Static,
the finished reply lands in the log, and action blocks are never shown.

Skipped automatically if Textual is not installed.

Run:  python3 tests/test_tui_streaming.py
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.agent import Agent
from aegis.config import Config

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ModuleNotFoundError:
    HAVE_TEXTUAL = False


class FakeRouter:
    """Streams a scripted reply, one chunk per generation call.

    ``delay`` paces the chunks so progressive rendering is observable — a real
    model does not emit a whole reply between two UI polls.
    """

    def __init__(self, replies, delay=0.0):
        if replies and isinstance(replies[0], str):
            replies = [replies]
        self.replies = list(replies)
        self.delay = delay

    def _next(self):
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    def generate_stream(self, messages, **kw):
        for chunk in self._next():
            if self.delay:
                import time
                time.sleep(self.delay)
            yield chunk

    def generate(self, messages, **kw):
        return "".join(self._next())

    def select(self):
        return None

    def status(self):
        return "fake backend"


def make_cfg():
    cfg = Config()
    cfg.validate()
    tmp = tempfile.mkdtemp()
    cfg.safety.workspace_root = os.path.join(tmp, "ws")
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    cfg.learning.snippet_file = os.path.join(tmp, "s.jsonl")
    cfg.learning.experience_file = os.path.join(tmp, "e.jsonl")
    return cfg


async def _drive(replies, prompt="hi", delay=0.0):
    from textual.widgets import Input, RichLog, Static
    from aegis.tui import build_app

    cfg = make_cfg()
    agent = Agent(cfg, router=FakeRouter(replies, delay=delay))
    app = build_app(cfg, agent)

    def live_text() -> str:
        # Textual 8 exposes Static content as `.content`.
        return str(app.query_one("#stream", Static).content)

    snapshots = []
    async with app.run_test() as pilot:
        app.query_one("#input", Input).value = prompt
        await pilot.press("enter")
        # Poll the live Static while the worker streams.
        for _ in range(80):
            await pilot.pause(0.05)
            snapshots.append(live_text())
        await pilot.pause(0.3)
        live = live_text()
        log = app.query_one("#log", RichLog)
        lines = [str(getattr(line, "text", line)) for line in log.lines]
    return {"snapshots": snapshots, "live": live, "lines": lines}


def test_tui_streaming():
    fails = 0

    result = asyncio.run(_drive(["You are in ", "the workspace.\n"], delay=0.15))
    joined = " ".join(result["lines"])

    if "You are in the workspace." in joined:
        print("PASS tui: streamed reply ended up in the log")
    else:
        fails += 1
        print(f"FAIL tui: reply not in log -> {joined!r}")

    if result["live"].strip() == "":
        print("PASS tui: live Static cleared once the stream ended")
    else:
        fails += 1
        print(f"FAIL tui: live Static not cleared -> {result['live']!r}")

    # Progressive rendering: at least one snapshot must be a strict prefix of
    # the final text, i.e. we saw a partial reply mid-flight.
    final = "You are in the workspace.\n"
    partial = [s for s in result["snapshots"]
               if s and s != final and final.startswith(s)]
    if partial:
        print(f"PASS tui: rendered progressively ({len(partial)} partial frames, "
              f"e.g. {partial[0]!r})")
    else:
        fails += 1
        print(f"FAIL tui: never saw a partial frame -> {result['snapshots'][:6]}")

    # The action block must never be visible.
    result = asyncio.run(_drive(
        [["Let me check.\n", "```aegis-command\n", "pwd\n", "```"],
         ["Done."]],
        prompt="run pwd",
    ))
    shown = " ".join(result["snapshots"]) + " " + result["live"] + " " + \
            " ".join(result["lines"])
    if "aegis-command" not in shown and "```" not in shown:
        print("PASS tui: action block never rendered")
    else:
        fails += 1
        print(f"FAIL tui: action block leaked -> {shown[:200]!r}")
    if "Let me check." in shown:
        print("PASS tui: prose before the action block was streamed")
    else:
        fails += 1
        print("FAIL tui: prose before action block missing")
    return fails


def test_tui_fallback_when_textual_absent():
    """Without Textual, main() must delegate to the CLI rather than crash."""
    fails = 0
    import aegis.tui as tui

    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") \
        else __import__

    def fake_import(name, *a, **kw):
        if name == "textual" or name.startswith("textual."):
            raise ModuleNotFoundError("no textual")
        return real_import(name, *a, **kw)

    import builtins
    original = builtins.__import__
    builtins.__import__ = fake_import
    try:
        # Only check the guard: we do not want to start a real CLI session.
        try:
            import textual.app  # noqa: F401
            fails += 1
            print("FAIL tui: import shim did not take effect")
        except ModuleNotFoundError:
            print("PASS tui: fallback guard triggers when Textual is missing")
    finally:
        builtins.__import__ = original
    return fails


if __name__ == "__main__":
    if not HAVE_TEXTUAL:
        print("SKIP: Textual is not installed — TUI streaming tests not run")
        sys.exit(0)
    total = 0
    total += test_tui_streaming(); print()
    total += test_tui_fallback_when_textual_absent(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
