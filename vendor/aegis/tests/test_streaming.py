"""Streaming tests: backend stream contract, router failover, agent integration.

Run:  python3 tests/test_streaming.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.agent import Agent, _StreamFilter
from aegis.brain.base import Backend, BackendError, Message
from aegis.brain.router import BackendRouter
from aegis.config import Config


# --------------------------------------------------------------------------

class FakeBackend(Backend):
    name = "fake"

    def __init__(self, chunks=None, fail_before=False, fail_mid=False):
        self.chunks = chunks or []
        self.fail_before = fail_before
        self.fail_mid = fail_mid
        self.streamed = False

    def available(self):
        return True

    def generate(self, messages, **kw):
        if self.fail_before:
            raise BackendError("nope")
        return "".join(self.chunks)

    def generate_stream(self, messages, **kw):
        self.streamed = True
        if self.fail_before:
            raise BackendError("nope")
        for i, c in enumerate(self.chunks):
            if self.fail_mid and i == 1:
                raise BackendError("died mid-stream")
            yield c


def make_cfg(tmp):
    cfg = Config()
    cfg.validate()
    cfg.safety.workspace_root = os.path.join(tmp, "ws")
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    cfg.learning.snippet_file = os.path.join(tmp, "s.jsonl")
    cfg.learning.experience_file = os.path.join(tmp, "e.jsonl")
    return cfg


# --------------------------------------------------------------------------
# _StreamFilter
# --------------------------------------------------------------------------

def test_stream_filter():
    failures = 0

    out = []
    f = _StreamFilter(out.append)
    for t in ["Hello ", "world. ", "```aegis-", "command\nls\n", "```"]:
        f.feed(t)
    f.flush()
    if "".join(out) == "Hello world. " and f.suppressed:
        print("PASS filter: prose streamed, action block suppressed")
    else:
        failures += 1
        print(f"FAIL action suppression -> {''.join(out)!r}")

    # a marker split across chunk boundaries must not leak
    out2 = []
    f2 = _StreamFilter(out2.append)
    for t in ["answer ", "```aeg", "is-command\nid\n", "```"]:
        f2.feed(t)
    f2.flush()
    if "".join(out2) == "answer " and "aeg" not in "".join(out2):
        print("PASS filter: split marker never leaks a partial")
    else:
        failures += 1
        print(f"FAIL split marker -> {''.join(out2)!r}")

    # ordinary fenced code must pass through
    out3 = []
    f3 = _StreamFilter(out3.append)
    for t in ["Here:\n```python\n", "x = 1\n", "```\n"]:
        f3.feed(t)
    f3.flush()
    if "```python" in "".join(out3) and "x = 1" in "".join(out3):
        print("PASS filter: normal code blocks stream through")
    else:
        failures += 1
        print(f"FAIL code block passthrough -> {''.join(out3)!r}")
    return failures


# --------------------------------------------------------------------------
# backend + router
# --------------------------------------------------------------------------

def test_backend_default_stream():
    failures = 0
    b = FakeBackend(chunks=["whole ", "reply"])

    class Plain(Backend):
        name = "plain"

        def available(self):
            return True

        def generate(self, messages, **kw):
            return "whole reply"

    got = list(Plain().generate_stream([Message("user", "hi")]))
    if got == ["whole reply"]:
        print("PASS backend: default generate_stream yields the full reply once")
    else:
        failures += 1
        print(f"FAIL default stream -> {got}")
    return failures


def test_router_failover():
    failures = 0
    cfg = make_cfg(tempfile.mkdtemp())

    # fail before the first chunk -> next backend is used
    router = BackendRouter(cfg)
    good = FakeBackend(chunks=["a", "b", "c"])
    router.backends = [FakeBackend(fail_before=True), good]
    router.active = router.backends[0]
    got = "".join(router.generate_stream([Message("user", "hi")]))
    if got == "abc" and good.streamed:
        print("PASS router: fails over before the first chunk")
    else:
        failures += 1
        print(f"FAIL pre-stream failover -> {got!r}")

    # fail mid-stream -> error propagates, no silent truncation
    router2 = BackendRouter(cfg)
    router2.backends = [FakeBackend(chunks=["a", "b", "c"], fail_mid=True)]
    router2.active = router2.backends[0]
    try:
        "".join(router2.generate_stream([Message("user", "hi")]))
        failures += 1
        print("FAIL mid-stream error was swallowed")
    except BackendError:
        print("PASS router: mid-stream error propagates (no silent truncation)")

    # empty reply is a success, not a failure
    router3 = BackendRouter(cfg)
    router3.backends = [FakeBackend(chunks=[])]
    router3.active = router3.backends[0]
    if "".join(router3.generate_stream([Message("user", "hi")])) == "":
        print("PASS router: empty stream returns cleanly")
    else:
        failures += 1
        print("FAIL empty stream")
    return failures


# --------------------------------------------------------------------------
# agent integration
# --------------------------------------------------------------------------

class FakeRouter:
    """Serves a queue of replies, one per generation call.

    A single reply list is reused forever; pass a list of lists to script a
    multi-round conversation (e.g. an action block, then a final answer).
    """

    def __init__(self, replies):
        if replies and isinstance(replies[0], str):
            replies = [replies]
        self.replies = list(replies)

    def _next(self):
        if len(self.replies) > 1:
            return self.replies.pop(0)
        return self.replies[0]

    def generate_stream(self, messages, **kw):
        yield from self._next()

    def generate(self, messages, **kw):
        return "".join(self._next())

    def select(self):
        return None

    def status(self):
        return "fake"


def test_agent_streaming():
    failures = 0
    tmp = tempfile.mkdtemp()
    cfg = make_cfg(tmp)
    tokens, ended, notes = [], [], []

    agent = Agent(cfg, router=FakeRouter(["You are in ", "the workspace.\n"]))
    agent.ask("where am i?", on_token=tokens.append,
              on_stream_end=lambda: ended.append(True),
              on_note=lambda k, s: notes.append((k, s)))
    if "".join(tokens) == "You are in the workspace.\n" and ended:
        print("PASS agent: prose streamed and stream-end signalled")
    else:
        failures += 1
        print(f"FAIL agent streaming -> {''.join(tokens)!r} ended={ended}")

    # an action block is suppressed but still executed
    tmp2 = tempfile.mkdtemp()
    cfg2 = make_cfg(tmp2)
    tokens2 = []
    agent2 = Agent(cfg2, router=FakeRouter([
        ["Let me check.\n", "```aegis-command\n", "pwd\n", "```"],
        ["You are in /home."],
    ]))
    ran = []
    agent2.ask("run pwd", on_token=tokens2.append,
               on_command=lambda c, r: ran.append((c, r.ran)))
    if "".join(tokens2) == "Let me check.\nYou are in /home." and len(ran) == 1 \
            and ran[0][0] == "pwd":
        print("PASS agent: action block suppressed but command still ran")
    else:
        failures += 1
        print(f"FAIL suppressed action -> tokens={''.join(tokens2)!r} ran={ran}")

    # without on_token, prose falls back to on_text (TUI/GUI path)
    tmp3 = tempfile.mkdtemp()
    cfg3 = make_cfg(tmp3)
    seen = []
    agent3 = Agent(cfg3, router=FakeRouter([["plain answer"]]))
    agent3.ask("hi", on_text=seen.append)
    if "plain answer" in "".join(seen):
        print("PASS agent: non-streaming front-ends still get on_text")
    else:
        failures += 1
        print(f"FAIL on_text fallback -> {seen}")
    return failures


if __name__ == "__main__":
    total = 0
    total += test_stream_filter(); print()
    total += test_backend_default_stream(); print()
    total += test_router_failover(); print()
    total += test_agent_streaming(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
