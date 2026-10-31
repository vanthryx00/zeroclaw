"""Tests for the smart features: snippets, learning/retrieval, file workspace,
cross-platform safety, and the new agent action protocols.

Run:  python3 tests/test_smart.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.config import Config
from aegis import safety
from aegis.files import FileWorkspace, WorkspaceError
from aegis.learning import LearningEngine
from aegis.retrieval import BM25
from aegis.snippets import SnippetStore, detect_language
from aegis.agent import Agent, _intent_hint, _parse_attrs
from aegis.brain.base import Backend


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def make_cfg(tmp):
    cfg = Config()
    cfg.validate()
    cfg.safety.workspace_root = os.path.join(tmp, "ws")
    cfg.learning.snippet_file = os.path.join(tmp, "snippets.jsonl")
    cfg.learning.experience_file = os.path.join(tmp, "exp.jsonl")
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    cfg.interface.history_file = os.path.join(tmp, "history")
    cfg.validate()
    return cfg


class ScriptedBackend(Backend):
    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def available(self):
        return True

    def generate(self, messages, **kwargs):
        self.seen.append(messages)
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


# --------------------------------------------------------------------------
# snippets
# --------------------------------------------------------------------------

def test_language_detection():
    failures = 0
    cases = [
        ("foo.py", "", "python"),
        ("x.ps1", "", "powershell"),
        ("", "#!/bin/bash\necho hi", "bash"),
        ("", "package main\nfunc main(){}", "go"),
        ("notes.md", "", "markdown"),
    ]
    for filename, code, expected in cases:
        got = detect_language(filename, code)
        if got == expected:
            print(f"PASS detect {filename or code[:20]!r} -> {got}")
        else:
            failures += 1
            print(f"FAIL detect {filename or code[:20]!r}: got {got}, want {expected}")
    return failures


def test_snippet_store():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-snip-")
    store = SnippetStore(os.path.join(tmp, "s.jsonl"))

    a = store.save("reverse linked list", "def rev(head):\n    prev=None\n",
                   language="python", tags=["algorithms", "linked-list"])
    b = store.save("http get in go", "resp, _ := http.Get(url)\n", tags=["http"])

    if len(store.all()) == 2:
        print("PASS saved two snippets")
    else:
        failures += 1
        print("FAIL snippet count wrong")

    hits = store.search("linked list reverse")
    if hits and hits[0].id == a.id:
        print("PASS search ranks the linked-list snippet first")
    else:
        failures += 1
        print(f"FAIL search returned {[h.title for h in hits]}")

    if store.get(a.id) and store.get(a.id).language == "python":
        print("PASS get by id")
    else:
        failures += 1
        print("FAIL get by id")

    store.bump(a.id)
    if store.get(a.id).uses == 1:
        print("PASS use counter bumps")
    else:
        failures += 1
        print("FAIL use counter")

    if store.search("", tag="http") and store.search("", tag="http")[0].id == b.id:
        print("PASS tag filter")
    else:
        failures += 1
        print("FAIL tag filter")

    if store.delete(b.id) and len(store.all()) == 1:
        print("PASS delete")
    else:
        failures += 1
        print("FAIL delete")

    dest = os.path.join(tmp, "out")
    written = store.export(dest)
    if written and os.path.isfile(written[0]):
        print(f"PASS export wrote {len(written)} file(s)")
    else:
        failures += 1
        print("FAIL export")
    return failures


# --------------------------------------------------------------------------
# retrieval + learning
# --------------------------------------------------------------------------

def test_bm25():
    failures = 0
    docs = [
        ("d1", "python script to reverse a linked list recursively"),
        ("d2", "how to bake sourdough bread at home"),
        ("d3", "nmap port scanning and service enumeration"),
    ]
    idx = BM25(docs)
    top = idx.search("reverse linked list python")
    if top and top[0][0] == "d1":
        print("PASS BM25 ranks the right doc first")
    else:
        failures += 1
        print(f"FAIL BM25 ranked {top}")
    if not idx.search("completely unrelated zzz"):
        print("PASS BM25 returns nothing for no overlap")
    else:
        failures += 1
        print("FAIL BM25 returned a match for gibberish")
    return failures


def test_learning_context():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-learn-")
    cfg = make_cfg(tmp)
    engine = LearningEngine(cfg)

    engine.save_snippet("port scanner", "import socket\ns=socket.socket()\n",
                        language="python", tags=["network", "scan"])
    engine.record_lesson("always declare scope before scanning", ["security"])
    engine.record_preference("prefers dark mode and short answers")

    ctx = engine.context_for("how do I scan a port in python")
    if "port scanner" in ctx and "socket" in ctx:
        print("PASS learned context recalls the snippet")
    else:
        failures += 1
        print(f"FAIL snippet not recalled:\n{ctx[:300]}")

    if "operator preference" in ctx and "dark mode" in ctx:
        print("PASS preferences always included")
    else:
        failures += 1
        print("FAIL preferences missing from context")

    empty = LearningEngine(make_cfg(tempfile.mkdtemp())).context_for("anything")
    if empty == "":
        print("PASS empty store yields no context block")
    else:
        failures += 1
        print("FAIL empty store produced context")
    return failures


def test_learning_feedback():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-fb-")
    cfg = make_cfg(tmp)
    engine = LearningEngine(cfg)
    exp = engine.record_lesson("use rsync for large transfers", ["backup"])
    engine.experiences.feedback(exp.id, +1)
    got = [e for e in engine.experiences.all() if e.id == exp.id][0]
    if got.score == 1:
        print("PASS feedback adjusts score")
    else:
        failures += 1
        print("FAIL feedback")
    if engine.experiences.delete(exp.id) and not engine.experiences.all():
        print("PASS forget deletes")
    else:
        failures += 1
        print("FAIL forget")
    return failures


# --------------------------------------------------------------------------
# file workspace
# --------------------------------------------------------------------------

def test_file_workspace():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-fs-")
    ws = FileWorkspace(os.path.join(tmp, "ws"))

    path = ws.write("code/hello.py", "print('hi')\n")
    if path.is_file() and "hi" in ws.read("code/hello.py"):
        print("PASS write + read inside workspace")
    else:
        failures += 1
        print("FAIL write/read")

    ws.append("code/hello.py", "# appended\n")
    if "appended" in ws.read("code/hello.py"):
        print("PASS append")
    else:
        failures += 1
        print("FAIL append")

    try:
        ws.write("../../etc/evil", "x")
        failures += 1
        print("FAIL escape was allowed!")
    except WorkspaceError:
        print("PASS path escape refused")

    try:
        ws.write("/tmp/absolute-escape-aegis", "x")
        failures += 1
        print("FAIL absolute escape allowed")
    except WorkspaceError:
        print("PASS absolute path outside workspace refused")

    listing = ws.list()
    if "code/" in listing:
        print("PASS list")
    else:
        failures += 1
        print(f"FAIL list -> {listing}")
    return failures


# --------------------------------------------------------------------------
# cross-platform safety
# --------------------------------------------------------------------------

def test_windows_safety():
    failures = 0
    cfg = Config()
    cfg.validate()
    cases = [
        ("Get-ChildItem C:\\Users", safety.Level.READ_ONLY, "powershell read"),
        ("ipconfig /all", safety.Level.READ_ONLY, "ipconfig"),
        ("Stop-Process -Name notepad", safety.Level.RISKY, "stop process"),
        ("reg delete HKLM\\Software\\Foo", safety.Level.RISKY, "registry delete"),
        ("format C:", safety.Level.BLOCKED, "format drive"),
        ("rd /s /q C:\\", safety.Level.BLOCKED, "rd drive root"),
        ("del /f /s /q C:\\*", safety.Level.BLOCKED, "del drive root"),
        ("Remove-Item -Recurse -Force C:\\", safety.Level.BLOCKED, "rm drive root"),
        ("vssadmin delete shadows /all", safety.Level.BLOCKED, "shadow delete"),
    ]
    for command, expected, note in cases:
        v = safety.classify(command, cfg)
        if v.level == expected:
            print(f"PASS [{v.label:>11}] {command}  ({note})")
        else:
            failures += 1
            print(f"FAIL {command}: got {v.label}, want {safety.LEVEL_LABEL[expected]}")
    return failures


# --------------------------------------------------------------------------
# agent protocols
# --------------------------------------------------------------------------

def test_parse_attrs():
    failures = 0
    attrs = _parse_attrs(' path=foo/bar.py mode=w')
    if attrs.get("path") == "foo/bar.py":
        print("PASS attr parsing")
    else:
        failures += 1
        print(f"FAIL attr parsing -> {attrs}")
    quoted = _parse_attrs(' title="hello world" tags=a,b')
    if quoted.get("title") == "hello world":
        print("PASS quoted attr parsing")
    else:
        failures += 1
        print(f"FAIL quoted attr -> {quoted}")
    return failures


def test_intent_hint():
    failures = 0
    if "CODING" in _intent_hint("write a python function to parse json"):
        print("PASS coding intent")
    else:
        failures += 1
        print("FAIL coding intent")
    if "SECURITY" in _intent_hint("how do I enumerate SMB shares"):
        print("PASS security intent")
    else:
        failures += 1
        print("FAIL security intent")
    if _intent_hint("hello there") == "":
        print("PASS neutral intent")
    else:
        failures += 1
        print("FAIL neutral intent")
    return failures


def test_agent_file_protocol():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-agent-file-")
    cfg = make_cfg(tmp)
    replies = [
        "Writing the file.\n```aegis-file path=scripts/hello.py\nprint('hello aegis')\n```",
        "Done.",
    ]
    agent = Agent(cfg, router=ScriptedRouter(replies))
    notes = []
    agent.ask("create hello.py", on_note=lambda k, s: notes.append((k, s)))
    target = os.path.join(cfg.safety.workspace_root, "scripts", "hello.py")
    if os.path.isfile(target) and "hello aegis" in open(target).read():
        print("PASS agent wrote a file via aegis-file")
    else:
        failures += 1
        print("FAIL agent file protocol")
    if any(k == "file" for k, _ in notes):
        print("PASS file note emitted")
    else:
        failures += 1
        print("FAIL file note")
    return failures


def test_agent_snippet_and_remember():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-agent-snip-")
    cfg = make_cfg(tmp)

    replies = [
        '```aegis-snippet title="add two" lang=python tags=math\nreturn a + b\n```',
        "Saved it.",
    ]
    agent = Agent(cfg, router=ScriptedRouter(replies))
    agent.ask("save a helper")
    snips = agent.learning.snippets.all()
    if snips and snips[0].title == "add two" and snips[0].language == "python":
        print("PASS agent saved a snippet via aegis-snippet")
    else:
        failures += 1
        print(f"FAIL agent snippet -> {[s.title for s in snips]}")

    replies2 = [
        "```aegis-remember tags=preference\nprefers tabs over spaces\n```",
        "Noted.",
    ]
    agent2 = Agent(cfg, router=ScriptedRouter(replies2))
    agent2.ask("remember my preference")
    exps = agent2.learning.experiences.all()
    if exps and "tabs" in exps[0].content:
        print("PASS agent recorded a lesson via aegis-remember")
    else:
        failures += 1
        print(f"FAIL agent remember -> {[e.content for e in exps]}")
    return failures


def test_learned_context_reaches_prompt():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-ctx-")
    cfg = make_cfg(tmp)
    agent = Agent(cfg, router=ScriptedRouter(["hi", "done"]))
    agent.learning.save_snippet("quicksort", "def qs(a): ...\n",
                                language="python", tags=["sorting"])
    agent.ask("implement quicksort")
    # the second generate call's messages should contain the learned block
    sent = agent.router.backend.seen[0]
    joined = "\n".join(m.content for m in sent)
    if "Learned context" in joined and "quicksort" in joined:
        print("PASS learned context injected into the prompt")
    else:
        failures += 1
        print("FAIL learned context not in prompt")
    return failures


if __name__ == "__main__":
    total = 0
    total += test_language_detection(); print()
    total += test_snippet_store(); print()
    total += test_bm25(); print()
    total += test_learning_context(); print()
    total += test_learning_feedback(); print()
    total += test_file_workspace(); print()
    total += test_windows_safety(); print()
    total += test_parse_attrs(); print()
    total += test_intent_hint(); print()
    total += test_agent_file_protocol(); print()
    total += test_agent_snippet_and_remember(); print()
    total += test_learned_context_reaches_prompt(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
