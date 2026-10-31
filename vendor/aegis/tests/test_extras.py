"""Tests for the upgrade batch: findings, notes, tasks, reports, diagnostics,
the tamper-evident audit chain, panic/leak-test, and cross-platform rescue.

Run:  python3 tests/test_extras.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.audit import AuditLog, GENESIS
from aegis.config import Config
from aegis.diag import run_all, worst
from aegis.findings import FindingStore
from aegis.notes import NoteStore
from aegis.tasks import TaskStore
from aegis.report import ReportBuilder
from aegis import privacy as privacy_mod
from aegis import rescue as rescue_mod


def tmpdir(prefix):
    return tempfile.mkdtemp(prefix=f"aegis-{prefix}-")


def make_cfg(tmp):
    cfg = Config()
    cfg.validate()
    cfg.safety.workspace_root = os.path.join(tmp, "ws")
    cfg.interface.audit_log = os.path.join(tmp, "audit.jsonl")
    return cfg


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

def test_findings():
    failures = 0
    store = FindingStore(os.path.join(tmpdir("fnd"), "f.jsonl"))
    a = store.add_finding("Open DNS resolver", severity="high", target="10.0.0.5",
                          tags=["dns"], detail="points at 8.8.8.8")
    store.add_finding("Missing firewall", severity="medium", tags=["fw"])
    store.add_finding("Banner leak", severity="low")

    if len(store.findings()) == 3:
        print("PASS findings: three recorded")
    else:
        failures += 1
        print("FAIL findings count")

    high = store.search(severity="high")
    if len(high) == 1 and high[0].id == a.id:
        print("PASS findings: severity filter")
    else:
        failures += 1
        print(f"FAIL severity filter -> {[f.id for f in high]}")

    if store.search("dns") and store.search("dns")[0].id == a.id:
        print("PASS findings: text search")
    else:
        failures += 1
        print("FAIL text search")

    if store.search(tag="fw") and len(store.search(tag="fw")) == 1:
        print("PASS findings: tag filter")
    else:
        failures += 1
        print("FAIL tag filter")

    # ordering: high before medium before low
    ordered = [f.severity for f in store.findings()]
    if ordered == ["high", "medium", "low"]:
        print("PASS findings: sorted by severity")
    else:
        failures += 1
        print(f"FAIL ordering -> {ordered}")

    store.set_status(a.id, "fixed")
    if store.get_finding(a.id).status == "fixed":
        print("PASS findings: status update")
    else:
        failures += 1
        print("FAIL status update")

    s = store.summary()
    if s["total"] == 3 and s["by_severity"]["high"] == 1 and s["open_high_plus"] == 0:
        print("PASS findings: summary reflects status")
    else:
        failures += 1
        print(f"FAIL summary -> {s}")
    return failures


# --------------------------------------------------------------------------
# notes and tasks
# --------------------------------------------------------------------------

def test_notes():
    failures = 0
    store = NoteStore(os.path.join(tmpdir("note"), "n.jsonl"))
    n = store.add_note("Lab notes", "range 10.0.0.0/24", tags=["lab"])
    store.append_to(n.id, "snapshot taken")
    got = store.get_note(n.id)
    if "snapshot taken" in got.body and "range" in got.body:
        print("PASS notes: append")
    else:
        failures += 1
        print(f"FAIL note append -> {got.body!r}")

    if store.search("range") and store.search("lab"):
        print("PASS notes: search")
    else:
        failures += 1
        print("FAIL note search")
    return failures


def test_tasks():
    failures = 0
    store = TaskStore(os.path.join(tmpdir("task"), "t.jsonl"))
    made = store.add_plan(["Recon", "Enumerate", "Document"])
    if len(made) == 3:
        print("PASS tasks: plan created")
    else:
        failures += 1
        print("FAIL plan")

    if store.next_task().title == "Recon":
        print("PASS tasks: next is first todo")
    else:
        failures += 1
        print("FAIL next")

    store.set_status(made[0].id, "done")
    p = store.progress()
    if p["done"] == 1 and p["remaining"] == 2 and store.next_task().title == "Enumerate":
        print("PASS tasks: progress and next advance")
    else:
        failures += 1
        print(f"FAIL progress -> {p}")

    urgent = store.add_task("Patch now", priority="urgent")
    if store.tasks()[0].id == urgent.id:
        print("PASS tasks: urgent sorts first among todos")
    else:
        failures += 1
        print(f"FAIL priority sort -> {[t.title for t in store.tasks()]}")
    return failures


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def test_report():
    failures = 0
    base = tmpdir("rep")
    findings = FindingStore(os.path.join(base, "f.jsonl"))
    notes = NoteStore(os.path.join(base, "n.jsonl"))
    tasks = TaskStore(os.path.join(base, "t.jsonl"))

    findings.add_finding("Weak SSH config", severity="high", target="10.0.0.9",
                         detail="PermitRootLogin yes", evidence="PermitRootLogin yes")
    notes.add_note("Context", "This is a lab box.")
    tasks.add_task("Fix SSH")

    report = ReportBuilder(findings, notes, tasks).build("Test Report",
                                                         meta={"mode": "auto_safe"})
    md = report.to_markdown()
    if "# Test Report" in md and "Weak SSH config" in md and "| High | 1 |" in md:
        print("PASS report: markdown has title, finding and counts")
    else:
        failures += 1
        print("FAIL report markdown")

    html = report.to_html()
    if html.startswith("<!doctype html>") and "Weak SSH config" in html and "<style>" in html:
        print("PASS report: self-contained html")
    else:
        failures += 1
        print("FAIL report html")

    filtered = ReportBuilder(findings, notes, tasks).build("T", min_severity="critical")
    if not filtered.findings:
        print("PASS report: min-severity filters out lower findings")
    else:
        failures += 1
        print("FAIL min-severity filter")
    return failures


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------

def test_diag():
    failures = 0
    results = run_all()
    if results and all(r.severity in ("info", "warn", "critical") for r in results):
        print(f"PASS diag: {len(results)} checks ran with valid severities")
    else:
        failures += 1
        print("FAIL diag results")

    if all(r.one_line() for r in results):
        print("PASS diag: every result renders a line")
    else:
        failures += 1
        print("FAIL diag rendering")

    if worst(results) in ("info", "warn", "critical"):
        print("PASS diag: worst() works")
    else:
        failures += 1
        print("FAIL worst()")
    return failures


# --------------------------------------------------------------------------
# tamper-evident audit chain
# --------------------------------------------------------------------------

def test_audit_chain():
    failures = 0
    path = os.path.join(tmpdir("audit"), "a.jsonl")
    log = AuditLog(path)
    log.record(command="ls", decision="ran")
    log.record(command="pwd", decision="ran")
    log.record(command="id", decision="ran")

    ok, idx, msg = log.verify()
    if ok and idx == -1:
        print("PASS audit: intact chain verifies")
    else:
        failures += 1
        print(f"FAIL verify on clean chain -> {ok} {idx} {msg}")

    # genesis link on the first record
    first = log.read_all()[0]
    if first.get("prev") == GENESIS:
        print("PASS audit: first record links to genesis")
    else:
        failures += 1
        print("FAIL genesis link")

    # tamper with the middle record
    lines = open(path).read().splitlines()
    rec = json.loads(lines[1])
    rec["decision"] = "blocked"  # silent edit
    lines[1] = json.dumps(rec)
    open(path, "w").write("\n".join(lines) + "\n")

    ok, idx, msg = log.verify()
    if not ok and idx == 1:
        print(f"PASS audit: tampering detected at record {idx}")
    else:
        failures += 1
        print(f"FAIL tamper not detected -> {ok} {idx} {msg}")

    # a deleted record breaks the link too
    path2 = os.path.join(tmpdir("audit"), "b.jsonl")
    log2 = AuditLog(path2)
    for i in range(4):
        log2.record(command=f"cmd{i}")
    lines = open(path2).read().splitlines()
    del lines[1]
    open(path2, "w").write("\n".join(lines) + "\n")
    ok, idx, msg = log2.verify()
    if not ok:
        print("PASS audit: deletion detected")
    else:
        failures += 1
        print("FAIL deletion not detected")

    seal_path = os.path.join(tmpdir("audit"), "seal.json")
    log.seal(seal_path)
    if os.path.isfile(seal_path) and "head" in json.load(open(seal_path)):
        print("PASS audit: seal writes head hash")
    else:
        failures += 1
        print("FAIL seal")
    return failures


# --------------------------------------------------------------------------
# privacy: leak test + panic
# --------------------------------------------------------------------------

def test_privacy_extras():
    failures = 0
    cfg = make_cfg(tmpdir("priv"))

    if privacy_mod._parse_nameservers("nameserver 127.0.0.1\nnameserver 8.8.8.8\n") == \
            ["127.0.0.1", "8.8.8.8"]:
        print("PASS privacy: nameserver parsing")
    else:
        failures += 1
        print("FAIL nameserver parsing")

    q = privacy_mod._build_dns_query("example.com")
    if q[:2] == b"\x1a\x2b" and b"example" in q and q.endswith(b"\x00\x01\x00\x01"):
        print("PASS privacy: DNS query built correctly")
    else:
        failures += 1
        print("FAIL DNS query")

    result = privacy_mod.dns_leak_test(cfg, live=False)
    if result.verdict in ("OK", "LIKELY_OK", "LEAK", "UNKNOWN"):
        print(f"PASS privacy: leak test returns a verdict ({result.verdict})")
    else:
        failures += 1
        print("FAIL leak test verdict")

    panic = privacy_mod.PanicController(cfg)
    plan = panic.plan()
    joined = "\n".join(plan)
    if "swapoff" in joined and "poweroff" in joined and "sdmem" in joined:
        print("PASS privacy: panic plan cuts network, swap, ram and powers off")
    else:
        failures += 1
        print(f"FAIL panic plan -> {joined}")

    cfg.privacy.panic_action = "network"
    if "nmcli networking off" in "\n".join(panic.plan()):
        print("PASS privacy: panic_action=network is honoured")
    else:
        failures += 1
        print("FAIL panic_action network")
    return failures


# --------------------------------------------------------------------------
# cross-platform rescue
# --------------------------------------------------------------------------

def test_rescue_os_detection():
    failures = 0
    if rescue_mod.guess_os("ntfs") == "windows" and \
            rescue_mod.guess_os("apfs") == "macos" and \
            rescue_mod.guess_os("ext4") == "linux" and \
            rescue_mod.guess_os("vfat") == "efi":
        print("PASS rescue: filesystem -> OS mapping")
    else:
        failures += 1
        print("FAIL guess_os")

    # linux landmark
    lin = tmpdir("lin")
    os.makedirs(os.path.join(lin, "etc"))
    open(os.path.join(lin, "etc", "os-release"), "w").write('PRETTY_NAME="Test Linux"\n')
    if rescue_mod.detect_installed_os(lin)["kind"] == "linux":
        print("PASS rescue: detects Linux")
    else:
        failures += 1
        print("FAIL linux detect")

    # windows landmark
    win = tmpdir("win")
    os.makedirs(os.path.join(win, "Windows", "System32", "config"))
    open(os.path.join(win, "Windows", "System32", "config", "SYSTEM"), "w").write("x")
    open(os.path.join(win, "hiberfil.sys"), "w").write("x")
    info = rescue_mod.detect_installed_os(win)
    if info["kind"] == "windows":
        print("PASS rescue: detects Windows")
    else:
        failures += 1
        print(f"FAIL windows detect -> {info}")

    findings = rescue_mod.diagnose_windows(win)
    cats = {f.category for f in findings}
    if "windows-hibernation" in cats and any(f.category == "windows-fsck" for f in findings):
        print("PASS rescue: Windows diagnosis flags hibernation + suggests ntfsfix")
    else:
        failures += 1
        print(f"FAIL windows diagnosis -> {cats}")

    # macos landmark
    mac = tmpdir("mac")
    os.makedirs(os.path.join(mac, "System", "Library", "CoreServices"))
    open(os.path.join(mac, "System", "Library", "CoreServices", "SystemVersion.plist"),
         "w").write("<key>ProductName</key><string>Mac OS X</string>"
                    "<key>ProductVersion</key><string>14.5</string>")
    info = rescue_mod.detect_installed_os(mac)
    if info["kind"] == "macos" and "14.5" in info["name"]:
        print(f"PASS rescue: detects macOS ({info['name']})")
    else:
        failures += 1
        print(f"FAIL macos detect -> {info}")

    mac_findings = rescue_mod.diagnose_macos(mac)
    if any("diskutil" in f.fix for f in mac_findings):
        print("PASS rescue: macOS diagnosis suggests diskutil")
    else:
        failures += 1
        print("FAIL macos diagnosis")

    # auto_diagnose dispatches by OS
    scanner = rescue_mod.RescueScanner()
    auto = rescue_mod.auto_diagnose(scanner, win)
    if auto["os"]["kind"] == "windows" and auto["findings"]:
        print("PASS rescue: auto_diagnose dispatches on detected OS")
    else:
        failures += 1
        print("FAIL auto_diagnose")
    return failures


if __name__ == "__main__":
    total = 0
    total += test_findings(); print()
    total += test_notes(); print()
    total += test_tasks(); print()
    total += test_report(); print()
    total += test_diag(); print()
    total += test_audit_chain(); print()
    total += test_privacy_extras(); print()
    total += test_rescue_os_detection(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
