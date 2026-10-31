"""Tests for the first-boot wizard: profile selection, RAM-based model sizing,
config rendering round-trip, and dry-run safety.

Run:  python3 tests/test_setup.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.config import Config
from aegis.setup import (
    HardwareProfile, PROFILES, auto_profile, build_plan, recommend_model,
    apply_plan, detect_hardware, _write_config, MODEL_CATALOG,
)


def hw(ram_mb, toram=False, live=False, cpu=4, disk=100):
    return HardwareProfile(
        total_ram_mb=ram_mb, available_ram_mb=ram_mb, cpu_count=cpu,
        disk_free_gb=disk, is_live=live, toram=toram, is_uefi=True,
    )


def test_model_sizing():
    failures = 0
    cases = [
        # (ram_mb, profile, toram, expected_model, note)
        (4000, "workstation", False, "qwen2.5-coder:3b", "4GB -> 3b"),
        (8000, "workstation", False, "qwen2.5-coder:7b", "8GB -> 7b"),
        (16000, "workstation", False, "qwen2.5-coder:14b", "16GB -> 14b"),
        (64000, "workstation", False, "qwen2.5-coder:32b", "64GB -> 32b"),
        (2000, "workstation", False, "qwen2.5-coder:1.5b", "2GB -> smallest"),
        (8000, "amnesic", True, "qwen2.5-coder:3b", "8GB amnesic loses a tier"),
        (16000, "rescue", False, "qwen2.5-coder:7b", "rescue capped at 7b"),
    ]
    for ram, profile, toram, expected, note in cases:
        rec = recommend_model(hw(ram, toram=toram), profile)
        if rec.model == expected:
            print(f"PASS {note}: {rec.model}")
        else:
            failures += 1
            print(f"FAIL {note}: got {rec.model}, expected {expected} ({rec.reason})")
    return failures


def test_amnesic_uses_more_reserve():
    failures = 0
    plain = recommend_model(hw(8000), "workstation")
    amn = recommend_model(hw(8000), "amnesic")
    if amn.reserve_mb > plain.reserve_mb:
        print(f"PASS amnesic reserve {amn.reserve_mb} > workstation {plain.reserve_mb}")
    else:
        failures += 1
        print("FAIL amnesic did not increase the reserve")
    return failures


def test_override():
    failures = 0
    rec = recommend_model(hw(4000), "workstation", override="qwen2.5-coder:32b")
    if rec.model == "qwen2.5-coder:32b" and "WARNING" in rec.reason:
        print("PASS override honored and flagged as too large")
    else:
        failures += 1
        print(f"FAIL override not handled: {rec.model} / {rec.reason}")
    return failures


def test_auto_profile():
    failures = 0
    if auto_profile(hw(8000, toram=True)) == "amnesic":
        print("PASS toram -> amnesic")
    else:
        failures += 1
        print("FAIL toram did not select amnesic")
    if auto_profile(hw(8000, live=True)) == "amnesic":
        print("PASS live USB -> amnesic")
    else:
        failures += 1
        print("FAIL live USB did not select amnesic")
    if auto_profile(hw(8000)) == "workstation":
        print("PASS installed -> workstation")
    else:
        failures += 1
        print("FAIL installed did not select workstation")
    return failures


def test_config_roundtrip():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-setup-")
    path = os.path.join(tmp, "config.toml")
    plan = build_plan(hw(16000, toram=True), "amnesic", config_path=path)

    _write_config(plan)
    if not os.path.isfile(path):
        failures += 1
        print("FAIL config not written")
        return failures

    cfg = Config.load(path)
    checks = [
        (cfg.privacy.amnesic is True, "amnesic=true persisted"),
        (cfg.privacy.force_tor is True, "force_tor=true persisted"),
        (cfg.privacy.wipe_memory_on_shutdown is True, "memwipe persisted"),
        (cfg.model.ollama_model == plan.model.model, "model persisted"),
        (cfg.safety.mode == "auto_safe", "safety mode persisted"),
    ]
    for ok, label in checks:
        if ok:
            print(f"PASS {label}")
        else:
            failures += 1
            print(f"FAIL {label}")
    return failures


def test_rescue_profile_config():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-setup-")
    path = os.path.join(tmp, "config.toml")
    plan = build_plan(hw(16000), "rescue", config_path=path)
    _write_config(plan)
    cfg = Config.load(path)
    if cfg.safety.mode == "confirm":
        print("PASS rescue profile sets confirm mode")
    else:
        failures += 1
        print(f"FAIL rescue mode = {cfg.safety.mode}")
    if cfg.privacy.force_tor is False:
        print("PASS rescue profile does not force Tor")
    else:
        failures += 1
        print("FAIL rescue forced Tor")
    return failures


def test_dry_run_writes_nothing():
    failures = 0
    tmp = tempfile.mkdtemp(prefix="aegis-setup-")
    path = os.path.join(tmp, "config.toml")
    plan = build_plan(hw(8000), "workstation", config_path=path)
    logs = apply_plan(plan, pull=False, enable_services=False, dry_run=True)
    if os.path.exists(path):
        failures += 1
        print("FAIL dry-run created a config file")
    else:
        print("PASS dry-run wrote nothing")
    if any("dry-run" in line for line in logs):
        print("PASS dry-run logged its intent")
    else:
        failures += 1
        print("FAIL dry-run produced no log")
    return failures


def test_catalog_is_ordered():
    failures = 0
    sizes = [s for _, s in MODEL_CATALOG]
    if sizes == sorted(sizes):
        print("PASS model catalog is ascending by size")
    else:
        failures += 1
        print("FAIL model catalog is not ordered")
    return failures


def test_cli_dispatch():
    from aegis.cli import build_parser, _normalize_argv
    failures = 0
    parser = build_parser()
    for argv in (["setup"], ["setup", "--auto"], ["setup", "--profile", "amnesic"]):
        ns = parser.parse_args(_normalize_argv(argv))
        if ns.command == "setup":
            print(f"PASS {argv} -> setup")
        else:
            failures += 1
            print(f"FAIL {argv} -> {ns.command}")
    return failures


def test_detect_hardware_real():
    failures = 0
    h = detect_hardware()
    if h.total_ram_mb > 0 and h.cpu_count >= 1:
        print(f"PASS detect_hardware: {h.total_ram_mb} MiB, {h.cpu_count} cores, "
              f"live={h.is_live}, toram={h.toram}")
    else:
        failures += 1
        print("FAIL detect_hardware returned zeros")
    return failures


if __name__ == "__main__":
    total = 0
    total += test_model_sizing(); print()
    total += test_amnesic_uses_more_reserve(); print()
    total += test_override(); print()
    total += test_auto_profile(); print()
    total += test_config_roundtrip(); print()
    total += test_rescue_profile_config(); print()
    total += test_dry_run_writes_nothing(); print()
    total += test_catalog_is_ordered(); print()
    total += test_cli_dispatch(); print()
    total += test_detect_hardware_real(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
