"""Bootloader detection + repair planning tests (#33).

Builds synthetic filesystem trees on disk (no root, no real disks) and checks
that detection, planning, safety classification, and the live-disk veto all
behave. Nothing here executes a repair.

Run:  python3 tests/test_bootloader.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.rescue import (
    BOOT_GRUB_BIOS, BOOT_GRUB_EFI, BOOT_SYSTEMD, BOOT_UNKNOWN, BOOT_WINDOWS,
    BootPlan, BootRepairRunner, BootloaderInfo, detect_bootloader,
    guard_live_disk, plan_bootloader_repair, _parent_disk,
)
from aegis.safety import Level, classify
from aegis.config import Config


def mk(root, *paths):
    for rel in paths:
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write("x")


def mkd(root, *paths):
    for rel in paths:
        os.makedirs(os.path.join(root, rel), exist_ok=True)


# --------------------------------------------------------------------------

def test_detection():
    fails = 0

    # GRUB on UEFI: ESP with a ubuntu vendor dir + grub.cfg + a kernel
    r = tempfile.mkdtemp()
    mkd(r, "boot/efi/EFI/ubuntu", "boot/grub/x86_64-efi")
    mk(r, "boot/grub/grub.cfg", "boot/vmlinuz-6.8.0-generic",
       "boot/efi/EFI/BOOT/BOOTX64.EFI")
    info = detect_bootloader(r, device="/dev/sda")
    if info.kind == BOOT_GRUB_EFI and info.efi and info.confidence == "high":
        print("PASS detect: GRUB on UEFI")
    else:
        fails += 1
        print(f"FAIL grub-efi -> {info.kind} efi={info.efi} conf={info.confidence}")
    if "BOOTX64.EFI" in " ".join(info.entries):
        print("PASS detect: removable fallback loader recorded")
    else:
        fails += 1
        print(f"FAIL fallback entry -> {info.entries}")

    # GRUB on BIOS: no ESP, grub.cfg present
    r = tempfile.mkdtemp()
    mkd(r, "boot/grub/i386-pc")
    mk(r, "boot/grub/grub.cfg", "boot/vmlinuz-6.8.0")
    info = detect_bootloader(r, device="/dev/sda")
    if info.kind == BOOT_GRUB_BIOS and not info.efi:
        print("PASS detect: GRUB on BIOS/MBR")
    else:
        fails += 1
        print(f"FAIL grub-bios -> {info.kind} efi={info.efi}")

    # systemd-boot
    r = tempfile.mkdtemp()
    mkd(r, "boot/efi/EFI/systemd", "boot/loader/entries")
    mk(r, "boot/efi/EFI/systemd/systemd-bootx64.efi", "boot/loader/loader.conf",
       "boot/loader/entries/aegis.conf", "boot/vmlinuz-6.8.0")
    info = detect_bootloader(r)
    if info.kind == BOOT_SYSTEMD and info.efi:
        print("PASS detect: systemd-boot")
    else:
        fails += 1
        print(f"FAIL systemd -> {info.kind}")

    # Windows Boot Manager on UEFI
    r = tempfile.mkdtemp()
    mkd(r, "boot/efi/EFI/Microsoft/Boot", "Windows/System32/config")
    mk(r, "boot/efi/EFI/Microsoft/Boot/bootmgfw.efi",
       "Windows/System32/config/SYSTEM")
    info = detect_bootloader(r)
    if info.kind == BOOT_WINDOWS:
        print("PASS detect: Windows Boot Manager")
    else:
        fails += 1
        print(f"FAIL windows -> {info.kind}")

    # Nothing at all
    r = tempfile.mkdtemp()
    info = detect_bootloader(r)
    if info.kind == BOOT_UNKNOWN and not info.healthy and info.issues:
        print("PASS detect: empty tree reported as unknown with an issue")
    else:
        fails += 1
        print(f"FAIL unknown -> {info.kind} issues={info.issues}")

    # Broken GRUB EFI: modules but no grub.cfg -> issue recorded
    r = tempfile.mkdtemp()
    mkd(r, "boot/efi/EFI/ubuntu", "boot/grub/x86_64-efi")
    mk(r, "boot/vmlinuz-6.8.0")
    info = detect_bootloader(r)
    if any("grub.cfg is missing" in i for i in info.issues):
        print("PASS detect: missing grub.cfg flagged")
    else:
        fails += 1
        print(f"FAIL missing grub.cfg -> {info.issues}")
    return fails


def test_plans():
    fails = 0

    def plan_for(kind, efi, device="/dev/sda", esp="/dev/sda1"):
        info = BootloaderInfo(kind=kind, efi=efi, root="/mnt/aegis-rescue",
                              device=device, esp_device=esp)
        return plan_bootloader_repair(info, device=device, esp_device=esp)

    p = plan_for(BOOT_GRUB_EFI, True)
    cmds = " | ".join(s.command for s in p.steps)
    if ("grub-install --target=x86_64-efi" in cmds and "update-grub" in cmds
            and "update-initramfs" in cmds and "efibootmgr -c" in cmds):
        print("PASS plan: GRUB UEFI has install + update-grub + initramfs + efibootmgr")
    else:
        fails += 1
        print(f"FAIL grub-efi plan -> {cmds}")

    if all(s.in_chroot for s in p.steps if s.command.startswith("grub-install")):
        print("PASS plan: grub-install runs inside the chroot")
    else:
        fails += 1
        print("FAIL grub-install not chrooted")

    if p.steps[0].command == "lsblk -f" and not p.steps[0].destructive:
        print("PASS plan: starts with a read-only inspection step")
    else:
        fails += 1
        print(f"FAIL first step -> {p.steps[0].command}")

    p = plan_for(BOOT_GRUB_BIOS, False)
    cmds = " | ".join(s.command for s in p.steps)
    if "grub-install --target=i386-pc --recheck /dev/sda" in cmds:
        print("PASS plan: GRUB BIOS targets the disk, not the ESP")
    else:
        fails += 1
        print(f"FAIL grub-bios plan -> {cmds}")

    p = plan_for(BOOT_SYSTEMD, True)
    cmds = " | ".join(s.command for s in p.steps)
    if "bootctl install" in cmds and "bootctl update" in cmds:
        print("PASS plan: systemd-boot uses bootctl install/update")
    else:
        fails += 1
        print(f"FAIL systemd plan -> {cmds}")

    p = plan_for(BOOT_WINDOWS, True, esp="/dev/sda1")
    cmds = " | ".join(s.command for s in p.steps)
    if "bcdboot /mnt/aegis-rescue/Windows /s /dev/sda1 /f UEFI" in cmds \
            and "ntfsfix -d" in cmds:
        print("PASS plan: Windows uses bcdboot + ntfsfix")
    else:
        fails += 1
        print(f"FAIL windows plan -> {cmds}")

    p = plan_for(BOOT_UNKNOWN, True)
    if any("no bootloader detected" in s.reason for s in p.steps):
        print("PASS plan: unknown falls back to GRUB and says so")
    else:
        fails += 1
        print("FAIL unknown fallback")

    # render() must be honest about not having run anything
    text = p.render()
    if "Nothing has been run yet" in text and "boot path" in text:
        print("PASS plan: render() states nothing was executed")
    else:
        fails += 1
        print(f"FAIL render text -> {text[:200]!r}")
    return fails


def test_live_disk_guard():
    fails = 0

    if _parent_disk("/dev/nvme0n1p2") == "/dev/nvme0n1" and \
            _parent_disk("/dev/sda2") == "/dev/sda" and \
            _parent_disk("/dev/mmcblk0p1") == "/dev/mmcblk0":
        print("PASS guard: partition -> parent disk mapping")
    else:
        fails += 1
        print("FAIL parent disk mapping")

    # A device that is definitely not the live root must not be refused.
    if guard_live_disk("/dev/definitely-not-the-live-disk") is None:
        print("PASS guard: an unrelated disk is not refused")
    else:
        fails += 1
        print("FAIL unrelated disk was refused")

    # Empty device -> no opinion (nothing to write to).
    if guard_live_disk("") is None:
        print("PASS guard: empty device is a no-op")
    else:
        fails += 1
        print("FAIL empty device refused")

    # If the live root disk is known, writing to it must be vetoed.
    from aegis import rescue
    live = rescue.live_root_disk()
    if live:
        msg = guard_live_disk(live)
        if msg and "refusing" in msg.lower():
            print(f"PASS guard: live root disk {live} is vetoed")
        else:
            fails += 1
            print(f"FAIL live disk {live} was not vetoed")
        # ...and the veto must appear on the plan.
        info = BootloaderInfo(kind=BOOT_GRUB_BIOS, efi=False, root="/mnt/x",
                              device=live)
        p = plan_bootloader_repair(info, device=live)
        if p.refusal and not p.applicable:
            print("PASS guard: a refused plan is not applicable")
        else:
            fails += 1
            print("FAIL refused plan still applicable")
    else:
        print("SKIP guard: could not determine the live root disk here")
    return fails


def test_safety_classification():
    fails = 0
    cfg = Config()
    cfg.validate()

    cases = [
        ("lsblk -f", Level.READ_ONLY),
        ("efibootmgr -v", Level.READ_ONLY),
        ("bootctl status", Level.READ_ONLY),
        ("fdisk -l /dev/sda", Level.READ_ONLY),
        ("parted -l", Level.READ_ONLY),
        ("os-prober", Level.READ_ONLY),
        ("grub-install --target=x86_64-efi --efi-directory=/boot/efi --recheck",
         Level.RISKY),
        ("update-grub", Level.RISKY),
        ("update-initramfs -u -k all", Level.RISKY),
        ("bootctl install", Level.RISKY),
        ("efibootmgr -c -d /dev/sda -L aegis -l \\EFI\\aegis\\grubx64.efi",
         Level.RISKY),
        ("bcdboot /mnt/aegis-rescue/Windows /s /dev/sda1 /f UEFI", Level.RISKY),
        ("rm -rf /boot/efi", Level.BLOCKED),
        ("dd if=/dev/zero of=/dev/sda bs=512 count=1", Level.BLOCKED),
        ("wipefs -a /dev/sda", Level.BLOCKED),
    ]
    for command, expected in cases:
        got = classify(command, cfg).level
        if got == expected:
            print(f"PASS safety: {expected.name:<10} {command[:52]}")
        else:
            fails += 1
            print(f"FAIL safety: {command[:52]} -> {got.name}, want {expected.name}")
    return fails


def test_runner_halts_on_denial():
    """A denied step must stop the run — a half-applied repair is worse."""
    fails = 0
    from aegis.executor import Executor

    cfg = Config()
    cfg.validate()
    cfg.safety.mode = "confirm"          # everything risky needs confirmation
    cfg.interface.audit_log = os.path.join(tempfile.mkdtemp(), "audit.jsonl")

    executor = Executor(cfg, confirm=lambda verdict, command: False)  # deny all

    info = BootloaderInfo(kind=BOOT_GRUB_EFI, efi=True, root="/mnt/aegis-rescue",
                          device="/dev/sdb", esp_device="/dev/sdb1")
    plan = plan_bootloader_repair(info, device="/dev/sdb", esp_device="/dev/sdb1")
    results = BootRepairRunner(executor, "/mnt/aegis-rescue").run(plan)

    ran = [c for c, r in results if getattr(r, "ran", False)]
    if not ran and results:
        print("PASS runner: denied confirmation stops execution entirely")
    else:
        fails += 1
        print(f"FAIL runner executed {len(ran)} step(s) despite denial")

    # Refused plans never touch the executor at all.
    refused = BootPlan(info=info, steps=[], refusal="nope")
    out = BootRepairRunner(executor, "/mnt/aegis-rescue").run(refused)
    if out == [("REFUSED", "nope")]:
        print("PASS runner: a refused plan returns without executing")
    else:
        fails += 1
        print(f"FAIL refused plan -> {out}")
    return fails


def test_argv_routing():
    """Regression: a global flag before a subcommand must not become a prompt.

    `_normalize_argv` used to check only argv[0], so `aegis --mode dry_run
    privacy tor` was rewritten to `ask privacy tor` and silently ran a chat
    prompt instead of the privacy command.
    """
    fails = 0
    from aegis.cli import _normalize_argv as norm

    cases = [
        ([], ["ask"]),
        (["what is tor?"], ["ask", "what is tor?"]),
        (["--yes", "do a thing"], ["--yes", "ask", "do a thing"]),
        (["--mode", "dry_run", "explain ls"],
         ["--mode", "dry_run", "ask", "explain ls"]),
        (["--version"], ["--version"]),
        # the bug: a subcommand after a global flag must stay a subcommand
        (["--mode", "dry_run", "privacy", "tor"],
         ["--mode", "dry_run", "privacy", "tor"]),
        (["--mode", "dry_run", "setup", "--profile", "workstation"],
         ["--mode", "dry_run", "setup", "--profile", "workstation"]),
        (["--yes", "rescue", "scan"], ["--yes", "rescue", "scan"]),
        (["rescue", "scan"], ["rescue", "scan"]),
    ]
    for given, want in cases:
        got = norm(list(given))
        if got == want:
            print(f"PASS argv: {given} -> {got}")
        else:
            fails += 1
            print(f"FAIL argv: {given} -> {got}, want {want}")
    return fails


if __name__ == "__main__":
    total = 0
    total += test_detection(); print()
    total += test_plans(); print()
    total += test_live_disk_guard(); print()
    total += test_safety_classification(); print()
    total += test_runner_halts_on_denial(); print()
    total += test_argv_routing(); print()
    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
