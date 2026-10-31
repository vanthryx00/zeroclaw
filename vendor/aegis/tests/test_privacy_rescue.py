"""Tests for the privacy auditor, Tor controller, and rescue planner.

Run:  python3 tests/test_privacy_rescue.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.config import Config
from aegis.privacy import PrivacyAuditor, TorController, _is_locally_administered
from aegis.rescue import RescueScanner, Finding, Partition, _human


def make_cfg():
    cfg = Config()
    cfg.validate()
    return cfg


def test_privacy_audit_structure():
    failures = 0
    report = PrivacyAuditor(make_cfg()).audit()
    valid = {"ok", "warn", "fail", "unknown"}

    if not report.findings:
        failures += 1
        print("FAIL auditor returned no findings")
    else:
        print(f"PASS auditor returned {len(report.findings)} findings")

    if not all(f.status in valid for f in report.findings):
        failures += 1
        print("FAIL a finding has an invalid status")
    else:
        print("PASS all statuses valid")

    if not (0 <= report.score <= 100):
        failures += 1
        print(f"FAIL score out of range: {report.score}")
    else:
        print(f"PASS score in range: {report.score}")

    if not all(f.key and f.label for f in report.findings):
        failures += 1
        print("FAIL a finding is missing key/label")
    else:
        print("PASS findings are well-formed")
    return failures


def test_mac_detection():
    failures = 0
    # 0x02 -> locally administered (randomized)
    if not _is_locally_administered("02:11:22:33:44:55"):
        failures += 1
        print("FAIL 02:.. should be locally administered")
    else:
        print("PASS randomized MAC detected")
    # 0x00 -> globally unique (vendor)
    if _is_locally_administered("00:1a:2b:3c:4d:5e"):
        failures += 1
        print("FAIL 00:.. should NOT be locally administered")
    else:
        print("PASS vendor MAC detected")
    return failures


def test_tor_rules():
    failures = 0
    rules = TorController(make_cfg()).transparent_rules()
    joined = "\n".join(rules)
    checks = [
        ("REDIRECT --to-ports 9040" in joined, "TCP redirect to trans port"),
        ("--dport 53" in joined, "DNS redirect"),
        ("-j DROP" in joined, "fail-closed drop rule"),
        ("--uid-owner" in joined, "Tor process exempted"),
    ]
    for ok, label in checks:
        if ok:
            print(f"PASS {label}")
        else:
            failures += 1
            print(f"FAIL {label}")
    return failures


def test_rescue_helpers():
    failures = 0
    if _human("1024") != "1K":
        failures += 1
        print(f"FAIL _human('1024') = {_human('1024')}")
    else:
        print("PASS _human formats sizes")

    ext4 = Partition("/dev/sda2", "100G", "ext4", "", "")
    efi = Partition("/dev/sda1", "512M", "vfat", "EFI", "")
    if ext4.is_probable_system() and not efi.is_probable_system():
        print("PASS partition classification")
    else:
        failures += 1
        print("FAIL partition classification wrong")
    return failures


def test_rescue_unmounted():
    failures = 0
    findings = RescueScanner().diagnose("/mnt/definitely-not-mounted-aegis")
    if findings and findings[0].category == "mount":
        print("PASS unmounted target reported")
    else:
        failures += 1
        print("FAIL unmounted target not reported")
    return failures


def test_repair_plan():
    failures = 0
    findings = [
        Finding("critical", "bootloader", "no bootloader found", "", "reinstall GRUB"),
        Finding("critical", "initramfs", "no initramfs", "", "regenerate it"),
        Finding("critical", "disk", "95% full", "", "apt clean"),
    ]
    plan = RescueScanner().repair_plan(findings, "/dev/sda")
    joined = "\n".join(plan)
    checks = [
        ("grub-install /dev/sda" in joined, "grub-install in plan"),
        ("update-initramfs" in joined, "initramfs regen in plan"),
        ("apt clean" in joined, "space cleanup in plan"),
        ("chroot" in joined, "chroot used for structural fixes"),
    ]
    for ok, label in checks:
        if ok:
            print(f"PASS {label}")
        else:
            failures += 1
            print(f"FAIL {label}")
    return failures


def test_cli_dispatch():
    """Ensure privacy/rescue subcommands actually dispatch (regression: the
    rescue positional once clobbered the top-level `command` dest)."""
    from aegis.cli import build_parser, _normalize_argv
    failures = 0
    parser = build_parser()
    cases = [
        (["privacy", "status"], "privacy"),
        (["privacy", "tor"], "privacy"),
        (["rescue", "scan"], "rescue"),
        (["rescue", "diagnose"], "rescue"),
        (["rescue", "mount", "/dev/sda2"], "rescue"),
    ]
    for argv, expected in cases:
        ns = parser.parse_args(_normalize_argv(argv))
        if ns.command == expected:
            print(f"PASS {argv} -> command={ns.command}")
        else:
            failures += 1
            print(f"FAIL {argv} -> command={ns.command} (expected {expected})")
    return failures


if __name__ == "__main__":
    total = 0
    total += test_privacy_audit_structure(); print()
    total += test_mac_detection(); print()
    total += test_tor_rules(); print()
    total += test_rescue_helpers(); print()
    total += test_rescue_unmounted(); print()
    total += test_repair_plan(); print()
    total += test_cli_dispatch(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
