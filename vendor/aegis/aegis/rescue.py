"""Rescue mode: diagnose and repair an installed system from the live USB.

Use case: a machine will not boot, a partition is full, a service is failing,
or the bootloader is broken. You boot AegisOS from USB, let Aegis scan the
disks, mount the broken root, and walk you through the fix.

Read-only enumeration (lsblk, df, file reads) is done directly. Every
*mutating* action (mount, chroot, fsck, grub-install) is emitted as a command
and run through the Executor, so it is classified, confirmed, and audited.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

RESCUE_MOUNT = "/mnt/aegis-rescue"


def _run(cmd: List[str], timeout: float = 10.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


@dataclass
class Partition:
    device: str
    size: str
    fstype: str
    label: str
    mountpoint: str

    def is_probable_system(self) -> bool:
        return self.fstype in LINUX_FS | WINDOWS_FS | MAC_FS and \
            self.mountpoint in ("", "/")

    @property
    def os_hint(self) -> str:
        return guess_os(self.fstype)


@dataclass
class Disk:
    name: str
    size: str
    model: str
    removable: bool
    partitions: List[Partition] = field(default_factory=list)


@dataclass
class Finding:
    severity: str  # "info" | "warn" | "critical"
    category: str
    summary: str
    detail: str = ""
    fix: str = ""

    @property
    def icon(self) -> str:
        return {"info": "i", "warn": "!", "critical": "✘"}.get(self.severity, "?")


class RescueScanner:
    # -- enumeration ----------------------------------------------------
    def list_disks(self) -> List[Disk]:
        raw = _run(["lsblk", "-J", "-b", "-o",
                    "NAME,SIZE,MODEL,RM,TYPE,FSTYPE,LABEL,MOUNTPOINT"])
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        disks: List[Disk] = []
        for dev in data.get("blockdevices", []):
            if dev.get("type") != "disk":
                continue
            disk = Disk(
                name=dev.get("name", ""),
                size=_human(dev.get("size")),
                model=(dev.get("model") or "").strip(),
                removable=bool(dev.get("rm")),
            )
            for child in dev.get("children", []) or []:
                disk.partitions.append(Partition(
                    device=f"/dev/{child.get('name','')}",
                    size=_human(child.get("size")),
                    fstype=child.get("fstype") or "",
                    label=child.get("label") or "",
                    mountpoint=child.get("mountpoint") or "",
                ))
            disks.append(disk)
        return disks

    def find_systems(self) -> List[Partition]:
        systems = []
        for disk in self.list_disks():
            for part in disk.partitions:
                if part.is_probable_system():
                    systems.append(part)
        return systems

    # -- diagnosis ------------------------------------------------------
    def diagnose(self, mountpoint: str = RESCUE_MOUNT) -> List[Finding]:
        findings: List[Finding] = []
        if not os.path.ismount(mountpoint):
            return [Finding("warn", "mount", f"{mountpoint} is not mounted",
                            "mount the target root first",
                            f"aegis rescue mount <device>")]

        findings += self._check_space(mountpoint)
        findings += self._check_inodes(mountpoint)
        findings += self._check_readonly(mountpoint)
        findings += self._check_bootloader(mountpoint)
        findings += self._check_initramfs(mountpoint)
        findings += self._check_fstab(mountpoint)
        findings += self._check_pkg_locks(mountpoint)
        findings += self._check_failed_units(mountpoint)
        if not findings:
            findings.append(Finding("info", "general", "no obvious problems found",
                                    "the system looks structurally healthy"))
        return findings

    def _check_space(self, mp: str) -> List[Finding]:
        out = _run(["df", "-P", mp])
        lines = out.splitlines()
        if len(lines) < 2:
            return []
        parts = lines[1].split()
        try:
            pct = int(parts[4].rstrip("%"))
        except (IndexError, ValueError):
            return []
        if pct >= 95:
            return [Finding("critical", "disk", f"root filesystem {pct}% full",
                            f"only {parts[3]} free — services will fail to start",
                            "clear space: apt clean; journalctl --vacuum-size=100M; "
                            "find /var/log -type f -delete")]
        if pct >= 85:
            return [Finding("warn", "disk", f"root filesystem {pct}% full",
                            f"{parts[3]} free", "consider clearing caches and old logs")]
        return []

    def _check_inodes(self, mp: str) -> List[Finding]:
        out = _run(["df", "-Pi", mp])
        lines = out.splitlines()
        if len(lines) < 2:
            return []
        parts = lines[1].split()
        try:
            pct = int(parts[4].rstrip("%"))
        except (IndexError, ValueError):
            return []
        if pct >= 90:
            return [Finding("warn", "inodes", f"inode usage {pct}%",
                            "many small files; new files may fail to create",
                            "find the directory with the most files and prune it")]
        return []

    def _check_readonly(self, mp: str) -> List[Finding]:
        out = _run(["findmnt", "-n", "-o", "OPTIONS", mp])
        if out and "ro" in out.split(","):
            return [Finding("critical", "filesystem", "root is mounted read-only",
                            "the kernel remounted it after an I/O error",
                            "check dmesg for I/O errors; back up data; run fsck")]
        return []

    def _check_bootloader(self, mp: str) -> List[Finding]:
        bios = os.path.exists(os.path.join(mp, "boot/grub/grub.cfg")) or \
            os.path.exists(os.path.join(mp, "boot/grub2/grub.cfg"))
        efi = os.path.exists(os.path.join(mp, "boot/efi/EFI")) or \
            os.path.exists(os.path.join(mp, "boot/EFI"))
        if not bios and not efi:
            return [Finding("critical", "bootloader", "no bootloader found",
                            "neither GRUB config nor an EFI system partition is present",
                            "reinstall GRUB for the target disk (see the plan below)")]
        return []

    def _check_initramfs(self, mp: str) -> List[Finding]:
        boot = os.path.join(mp, "boot")
        if not os.path.isdir(boot):
            return []
        try:
            names = os.listdir(boot)
        except OSError:
            return []
        has_kernel = any(n.startswith("vmlinuz") for n in names)
        has_initrd = any(n.startswith(("initrd", "initramfs")) for n in names)
        if has_kernel and not has_initrd:
            return [Finding("critical", "initramfs", "kernel present but no initramfs",
                            "the system will not boot without an initramfs",
                            "regenerate it (see the plan below)")]
        return []

    def _check_fstab(self, mp: str) -> List[Finding]:
        fstab = os.path.join(mp, "etc/fstab")
        if not os.path.isfile(fstab):
            return []
        problems = []
        for line in _read(fstab).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            device, target = parts[0], parts[1]
            if target in ("/", "none", "swap"):
                continue
            if device.startswith("UUID=") or device.startswith("LABEL=") or \
                    device.startswith("/dev/"):
                if device.startswith("/dev/") and not os.path.exists(device):
                    problems.append(f"{device} -> {target} (device missing)")
        if problems:
            return [Finding("warn", "fstab", "fstab references missing devices",
                            "; ".join(problems),
                            "boot will stall ~90s per entry; fix /etc/fstab")]
        return []

    def _check_pkg_locks(self, mp: str) -> List[Finding]:
        locks = [
            "var/lib/dpkg/lock", "var/lib/dpkg/lock-frontend",
            "var/lib/apt/lists/lock", "var/cache/apt/archives/lock",
        ]
        present = [l for l in locks if os.path.exists(os.path.join(mp, l))]
        if present:
            return [Finding("info", "package", "package manager lock files present",
                            "harmless unless a previous apt run was interrupted",
                            "remove stale locks only if no apt process is running")]
        return []

    def _check_failed_units(self, mp: str) -> List[Finding]:
        # Requires the target's systemd; only meaningful if we chroot. Do a
        # best-effort read of the target's journal for the previous boot.
        journal = os.path.join(mp, "var/log/journal")
        if not os.path.isdir(journal):
            return []
        return [Finding("info", "services", "system journal present",
                        "chroot in to run `systemctl --failed` for the real list",
                        "aegis rescue chroot systemctl --failed")]

    # -- repair plan ----------------------------------------------------
    def repair_plan(self, findings: List[Finding], device: str = "<device>") -> List[str]:
        plan: List[str] = []
        for f in findings:
            if f.severity in ("warn", "critical") and f.fix and \
                    f.fix.startswith(FIX_PREFIXES):
                plan.append(f.fix)
        # Structural repairs need the target mounted at RESCUE_MOUNT.
        if any(f.category == "bootloader" for f in findings):
            plan += [
                f"mount --bind /dev {RESCUE_MOUNT}/dev",
                f"mount --bind /proc {RESCUE_MOUNT}/proc",
                f"mount --bind /sys {RESCUE_MOUNT}/sys",
                f"chroot {RESCUE_MOUNT} grub-install {device}",
                f"chroot {RESCUE_MOUNT} update-grub",
            ]
        if any(f.category == "initramfs" for f in findings):
            plan.append(f"chroot {RESCUE_MOUNT} update-initramfs -u -k all")
        return plan


class RescueActions:
    """Mutating rescue operations, routed through the Executor for audit."""

    def __init__(self, executor, mountpoint: str = RESCUE_MOUNT):
        self.executor = executor
        self.mountpoint = mountpoint

    def mount(self, device: str) -> str:
        os.makedirs(self.mountpoint, exist_ok=True)
        result = self.executor.run(f"mount {device} {self.mountpoint}")
        return self._fmt(result)

    def unmount(self) -> str:
        result = self.executor.run(f"umount {self.mountpoint}")
        return self._fmt(result)

    def bind_mounts(self) -> str:
        out = []
        for fs in ("dev", "proc", "sys", "run"):
            src = f"/{fs}"
            dst = f"{self.mountpoint}/{fs}"
            out.append(self._fmt(self.executor.run(f"mount --bind {src} {dst}")))
        return "\n".join(out)

    def chroot(self, command: str) -> str:
        result = self.executor.run(f"chroot {self.mountpoint} {command}")
        return self._fmt(result)

    def fsck(self, device: str) -> str:
        result = self.executor.run(f"fsck -y {device}")
        return self._fmt(result)

    @staticmethod
    def _fmt(result) -> str:
        if not result.ran:
            return f"[{result.decision}] {result.command}: {result.verdict.reason}"
        return (result.stdout or result.stderr or "").strip() or f"(exit {result.exit_code})"


def _human(size) -> str:
    try:
        n = float(size)
    except (TypeError, ValueError):
        return str(size)
    for unit in ("B", "K", "M", "G", "T", "P"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}E"


# ---------------------------------------------------------------------------
# Cross-platform OS detection and diagnosis
# ---------------------------------------------------------------------------

LINUX_FS = {"ext4", "ext3", "ext2", "xfs", "btrfs", "f2fs", "reiserfs"}
WINDOWS_FS = {"ntfs", "ntfs3", "fuseblk"}
MAC_FS = {"apfs", "hfsplus", "hfs"}
EFI_FS = {"vfat", "fat32", "fat16", "msdos"}

FIX_PREFIXES = (
    "apt", "find", "journalctl", "grub", "fsck", "ntfsfix", "smartctl",
    "chkdsk", "bcdedit", "bootsect", "bootrec", "diskutil", "fsck_apfs",
    "mount", "swapoff",
)


def guess_os(fstype: str) -> str:
    f = (fstype or "").lower()
    if f in LINUX_FS:
        return "linux"
    if f in WINDOWS_FS:
        return "windows"
    if f in MAC_FS:
        return "macos"
    if f in EFI_FS:
        return "efi"
    return "unknown"


def detect_installed_os(mountpoint: str) -> dict:
    """Identify what OS lives at a mountpoint by its on-disk landmarks."""
    mp = mountpoint.rstrip("/")
    def has(rel: str) -> bool:
        return os.path.exists(os.path.join(mp, rel))

    if has("etc/os-release"):
        info = {"kind": "linux", "name": "Linux"}
        try:
            with open(os.path.join(mp, "etc/os-release"), encoding="utf-8",
                      errors="replace") as fh:
                for line in fh:
                    if line.startswith("PRETTY_NAME="):
                        info["name"] = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("ID="):
                        info["id"] = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return info

    if has("Windows/System32/config/SYSTEM") or has("windows/system32"):
        return {"kind": "windows", "name": "Windows"}

    if has("System/Library/CoreServices/SystemVersion.plist"):
        name = "macOS"
        try:
            with open(os.path.join(mp, "System/Library/CoreServices/SystemVersion.plist"),
                      encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for key in ("ProductName", "ProductVersion"):
                marker = f"<key>{key}</key>"
                if marker in text:
                    tail = text.split(marker, 1)[1]
                    if "<string>" in tail:
                        val = tail.split("<string>", 1)[1].split("</string>", 1)[0]
                        if key == "ProductName":
                            name = val
                        else:
                            name = f"{name} {val}"
        except OSError:
            pass
        return {"kind": "macos", "name": name}

    return {"kind": "unknown", "name": "Unrecognised system"}


def diagnose_windows(mountpoint: str) -> List[Finding]:
    mp = mountpoint.rstrip("/")
    out: List[Finding] = []
    def has(rel: str) -> bool:
        return os.path.exists(os.path.join(mp, rel))

    if has("hiberfil.sys"):
        out.append(Finding(
            "warn", "windows-hibernation",
            "Windows is in a hibernated or fast-startup state",
            "hiberfil.sys exists. Do not write to this filesystem until Windows "
            "resumes cleanly, or you risk corrupting the NTFS journal.",
            "",
        ))
    if has("Windows/System32/config/SYSTEM"):
        out.append(Finding("info", "windows-registry", "Windows registry hives found",
                           "SYSTEM hive present; offline registry edits are possible.", ""))
    else:
        out.append(Finding("warn", "windows-registry", "Windows registry hives missing",
                           "Expected Windows/System32/config/SYSTEM was not found.", ""))
    if not (has("bootmgr") or has("EFI/Microsoft")):
        out.append(Finding("critical", "bootloader", "Windows boot files not found",
                           "Neither bootmgr nor EFI/Microsoft is present.",
                           f"bcdboot {mp}/Windows /s {mp}/EFI"))
    else:
        out.append(Finding("info", "bootloader", "Windows boot files present", "", ""))
    out.append(Finding("info", "windows-fsck", "Run an NTFS consistency check",
                       "Checks the NTFS journal for inconsistency.",
                       f"ntfsfix -d {mp}"))
    return out


def diagnose_macos(mountpoint: str) -> List[Finding]:
    mp = mountpoint.rstrip("/")
    out: List[Finding] = []
    def has(rel: str) -> bool:
        return os.path.exists(os.path.join(mp, rel))

    if has("System/Library/CoreServices/SystemVersion.plist"):
        out.append(Finding("info", "macos-system", "macOS system found", "", ""))
    if has("System/Library/Extensions"):
        out.append(Finding("info", "macos-kexts", "System extensions present", "", ""))
    if not has("System/Volumes/Data") and not has("Users"):
        out.append(Finding("warn", "macos-data", "Data volume not visible",
                           "On APFS, the Data volume may be a separate container.", ""))
    out.append(Finding("info", "macos-fsck", "Verify the APFS container",
                       "Runs a read-only verification.",
                       f"diskutil verifyVolume {mp}"))
    return out


def auto_diagnose(scanner: "RescueScanner", mountpoint: str) -> dict:
    """Detect the installed OS at a mountpoint and run the right checks.

    Returns {"os": {...}, "findings": [...], "plan": [...]}. This is what the
    rescue boot calls automatically when it finds exactly one candidate system.
    """
    info = detect_installed_os(mountpoint)
    kind = info.get("kind", "unknown")
    if kind == "windows":
        findings = diagnose_windows(mountpoint)
    elif kind == "macos":
        findings = diagnose_macos(mountpoint)
    elif kind == "linux":
        findings = scanner.diagnose(mountpoint)
    else:
        findings = [Finding("warn", "unknown", "Unrecognised operating system",
                            f"No known OS landmarks under {mountpoint}.", "")]
    plan = scanner.repair_plan(findings)
    return {"os": info, "findings": findings, "plan": plan}


# ---------------------------------------------------------------------------
# Bootloader detection and repair (#33)
# ---------------------------------------------------------------------------
#
# A broken bootloader is the single most common reason a working system will
# not start. Repairing it means writing to the boot path, which is exactly the
# kind of change that turns "will not boot" into "cannot be recovered" if it
# lands on the wrong disk. So this section separates three things strictly:
#
#   detect_bootloader()        read-only, never writes anything
#   plan_bootloader_repair()   pure: computes commands, runs nothing
#   BootRepairRunner.run()     the only path that writes, via the Executor
#
# The plan *is* the dry run. `--apply` asks for it to be attempted; it does not
# bypass the safety mode, confirmation prompts, or the audit log.

BOOT_GRUB_EFI = "grub-efi"
BOOT_GRUB_BIOS = "grub-bios"
BOOT_SYSTEMD = "systemd-boot"
BOOT_WINDOWS = "windows-bootmgr"
BOOT_APPLE = "apple-boot"
BOOT_UNKNOWN = "unknown"

BOOT_LABELS = {
    BOOT_GRUB_EFI: "GRUB (UEFI)",
    BOOT_GRUB_BIOS: "GRUB (BIOS/MBR)",
    BOOT_SYSTEMD: "systemd-boot (UEFI)",
    BOOT_WINDOWS: "Windows Boot Manager",
    BOOT_APPLE: "Apple bootloader",
    BOOT_UNKNOWN: "unrecognised or missing",
}

# ESP vendor directory -> the bootloader it implies.
EFI_VENDOR_KINDS = {
    "ubuntu": BOOT_GRUB_EFI, "debian": BOOT_GRUB_EFI, "fedora": BOOT_GRUB_EFI,
    "centos": BOOT_GRUB_EFI, "rhel": BOOT_GRUB_EFI, "arch": BOOT_GRUB_EFI,
    "grub": BOOT_GRUB_EFI, "opensuse": BOOT_GRUB_EFI, "pop": BOOT_GRUB_EFI,
    "kali": BOOT_GRUB_EFI, "linuxmint": BOOT_GRUB_EFI,
    "systemd": BOOT_SYSTEMD,
    "microsoft": BOOT_WINDOWS,
    "apple": BOOT_APPLE,
}


def _safe_listdir(path: str) -> List[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


@dataclass
class BootloaderInfo:
    """What bootloader lives on a mounted system. Purely descriptive."""

    kind: str = BOOT_UNKNOWN
    efi: bool = False
    root: str = ""
    device: str = ""
    esp_device: str = ""
    esp_mount: str = ""
    vendors: List[str] = field(default_factory=list)
    entries: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    confidence: str = "low"

    @property
    def label(self) -> str:
        return BOOT_LABELS.get(self.kind, self.kind)

    @property
    def healthy(self) -> bool:
        return self.kind != BOOT_UNKNOWN and not self.issues

    def summary(self) -> str:
        lines = [
            f"bootloader : {self.label}  (confidence: {self.confidence})",
            f"firmware   : {'UEFI' if self.efi else 'BIOS / legacy'}",
            f"root       : {self.root}",
        ]
        if self.esp_device:
            where = self.esp_mount or "(not mounted)"
            lines.append(f"ESP        : {self.esp_device} -> {where}")
        if self.device:
            lines.append(f"target disk: {self.device}")
        if self.vendors:
            lines.append(f"ESP dirs   : {', '.join(self.vendors)}")
        if self.entries:
            lines.append("entries    : " + ", ".join(self.entries[:6]))
        for issue in self.issues:
            lines.append(f"  ! {issue}")
        return "\n".join(lines)


def detect_bootloader(root: str, *, device: str = "",
                      esp_device: str = "") -> BootloaderInfo:
    """Identify the bootloader on a mounted system without writing anything.

    Works on a *mounted* root (typically ``/mnt/aegis-rescue``). It only stats
    and lists paths, so it is safe to run against any filesystem you can read.
    """
    mp = root.rstrip("/") or "/"
    info = BootloaderInfo(root=mp, device=device, esp_device=esp_device)

    def has(rel: str) -> bool:
        return os.path.exists(os.path.join(mp, rel))

    def isdir(rel: str) -> bool:
        return os.path.isdir(os.path.join(mp, rel))

    # --- EFI system partition -------------------------------------------
    for cand in ("boot/efi", "boot/EFI", "efi", "EFI"):
        base = os.path.join(mp, cand)
        efi_dir = os.path.join(base, "EFI")
        scan = efi_dir if os.path.isdir(efi_dir) else (
            base if os.path.isdir(base) and os.path.basename(cand) == "EFI" else "")
        if not scan:
            continue
        info.efi = True
        info.esp_mount = base
        info.vendors = [n for n in _safe_listdir(scan)
                        if os.path.isdir(os.path.join(scan, n))]
        if os.path.exists(os.path.join(scan, "BOOT", "BOOTX64.EFI")):
            info.entries.append("EFI/BOOT/BOOTX64.EFI (removable fallback)")
        break

    # --- systemd-boot -----------------------------------------------------
    loader_entries: List[str] = []
    for cand in ("boot/loader/entries", "loader/entries"):
        if isdir(cand):
            loader_entries = _safe_listdir(os.path.join(mp, cand))
            break
    has_loader_conf = has("boot/loader/loader.conf") or has("loader/loader.conf")

    # --- GRUB -------------------------------------------------------------
    grub_cfg = has("boot/grub/grub.cfg") or has("boot/grub2/grub.cfg")
    grub_modules = isdir("boot/grub/i386-pc") or isdir("boot/grub/x86_64-efi")

    # --- Windows / Apple ---------------------------------------------------
    vendors_lower = [v.lower() for v in info.vendors]
    win_bios = has("bootmgr") or has("Boot/BCD")
    win_efi = "microsoft" in vendors_lower
    apple = "apple" in vendors_lower
    grub_on_esp = any(EFI_VENDOR_KINDS.get(v) == BOOT_GRUB_EFI
                      for v in vendors_lower)

    kernels = [n for n in _safe_listdir(os.path.join(mp, "boot"))
               if n.startswith("vmlinuz") or n.startswith("vmlinux")]

    # --- Decide ------------------------------------------------------------
    if win_efi or (win_bios and not grub_cfg and not has_loader_conf
                   and not grub_on_esp):
        info.kind = BOOT_WINDOWS
        info.confidence = "high"
        if win_efi:
            info.entries.append("EFI/Microsoft/Boot/bootmgfw.efi")
    elif has_loader_conf or loader_entries:
        info.kind = BOOT_SYSTEMD
        info.efi = True
        info.confidence = "high" if has_loader_conf else "medium"
        info.entries += [f"loader entry: {e}" for e in loader_entries[:6]]
    elif info.efi and (grub_on_esp or grub_cfg or grub_modules):
        info.kind = BOOT_GRUB_EFI
        info.confidence = "high" if grub_cfg else "medium"
    elif apple:
        info.kind = BOOT_APPLE
        info.confidence = "medium"
    elif grub_cfg or grub_modules:
        info.kind = BOOT_GRUB_BIOS
        info.confidence = "high" if grub_cfg else "medium"

    # --- Issues worth surfacing --------------------------------------------
    if info.kind == BOOT_UNKNOWN:
        info.issues.append("no bootloader found on this system")
    if info.efi and not info.esp_mount:
        info.issues.append("UEFI system, but no EFI system partition is mounted")
    if info.kind == BOOT_GRUB_EFI and not grub_cfg:
        info.issues.append("GRUB EFI modules present but grub.cfg is missing")
    if info.kind == BOOT_SYSTEMD and not has_loader_conf:
        info.issues.append("systemd-boot entries present but loader.conf is missing")
    if info.kind in (BOOT_GRUB_EFI, BOOT_GRUB_BIOS, BOOT_SYSTEMD) and not kernels:
        info.issues.append("no kernel image found under /boot")
    if info.kind == BOOT_WINDOWS and not has("Windows/System32/config/SYSTEM"):
        info.issues.append("Windows registry hives not found where expected")
    return info


def _parent_disk(device: str) -> str:
    """Map a partition device to its parent disk.

    /dev/nvme0n1p2 -> /dev/nvme0n1, /dev/sda2 -> /dev/sda, /dev/mmcblk0p1 ->
    /dev/mmcblk0. Non-partition input is returned unchanged.
    """
    dev = (device or "").strip()
    if not dev.startswith("/dev/"):
        return ""
    m = re.match(r"(/dev/(?:nvme\d+n\d+|mmcblk\d+|loop\d+|md\d+))p\d+$", dev)
    if m:
        return m.group(1)
    m = re.match(r"(/dev/(?:sd[a-z]+|vd[a-z]+|hd[a-z]+|xvd[a-z]+))\d+$", dev)
    if m:
        return m.group(1)
    return dev


def live_root_disk() -> str:
    """The disk backing the *running* root filesystem, or '' if unknown.

    /proc/mounts is preferred because it needs no extra binaries, but on live
    media the root is usually an overlay or squashfs, which tells us nothing
    about the underlying device. In that case fall back to findmnt.
    """
    for line in _read("/proc/mounts").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "/" and parts[0].startswith("/dev/"):
            return _parent_disk(parts[0])
    source = _run(["findmnt", "-no", "SOURCE", "/"]).strip()
    if source.startswith("/dev/"):
        return _parent_disk(source)
    return ""


def guard_live_disk(device: str) -> Optional[str]:
    """Refuse to write a bootloader to the disk we are running from.

    This is the classic way to brick a machine: the running kernel has the old
    block mapping cached, and installing a bootloader onto the live disk can
    land the write in the wrong place — or make the rescue system itself
    unbootable mid-repair. A non-None return is a veto.
    """
    if not device:
        return None
    live = live_root_disk()
    if live and _parent_disk(device) == live:
        return (f"refusing to write a bootloader to {device}: it is the disk that "
                f"hosts the running system ({live}). Boot AegisOS from separate "
                f"media and repair the target disk from there.")
    return None


@dataclass
class BootStep:
    """One command in a bootloader repair plan."""

    command: str
    reason: str
    destructive: bool = False   # rewrites the boot path
    in_chroot: bool = False     # must run inside the mounted target

    def render(self) -> str:
        mark = "!" if self.destructive else "-"
        where = "  [chroot]" if self.in_chroot else ""
        return f"{mark} {self.command}{where}"


@dataclass
class BootPlan:
    """A computed, not-yet-applied bootloader repair."""

    info: BootloaderInfo
    steps: List[BootStep] = field(default_factory=list)
    refusal: str = ""

    @property
    def destructive(self) -> List[BootStep]:
        return [s for s in self.steps if s.destructive]

    @property
    def applicable(self) -> bool:
        return not self.refusal and bool(self.steps)

    def render(self) -> str:
        lines = [self.info.summary(), "", "Repair plan:"]
        if self.refusal:
            lines.append(f"  REFUSED  {self.refusal}")
            return "\n".join(lines)
        if not self.steps:
            lines.append("  (nothing to do)")
            return "\n".join(lines)
        for i, step in enumerate(self.steps, 1):
            lines.append(f"  {i:2d}. {step.render()}")
            lines.append(f"      {step.reason}")
        lines.append("")
        lines.append(f"{len(self.steps)} steps; {len(self.destructive)} rewrite "
                     f"the boot path.")
        lines.append("Nothing has been run yet. Re-run with --apply to execute.")
        return "\n".join(lines)


def plan_bootloader_repair(
    info: BootloaderInfo,
    *,
    device: str = "",
    esp_device: str = "",
    mountpoint: str = RESCUE_MOUNT,
    loader_id: str = "aegis",
) -> BootPlan:
    """Build an ordered, idempotent repair plan. Pure — runs nothing.

    Every plan starts with read-only inspection so you can see the current
    state before anything changes, and ends by verifying the result.
    """
    mp = mountpoint.rstrip("/") or RESCUE_MOUNT
    dev = device or info.device
    esp = esp_device or info.esp_device
    plan = BootPlan(info=info)

    def add(command: str, reason: str, *, destructive: bool = False,
            in_chroot: bool = False) -> None:
        plan.steps.append(BootStep(command, reason, destructive, in_chroot))

    def bind_mounts() -> None:
        for fs, why in (("dev", "device nodes"), ("proc", "/proc"),
                        ("sys", "/sys"), ("run", "/run")):
            add(f"mount --bind /{fs} {mp}/{fs}",
                f"give the chroot access to {why}")

    add("lsblk -f", "confirm the block-device layout before changing it")
    if info.efi:
        add("efibootmgr -v", "record the current EFI boot entries")

    if info.kind == BOOT_GRUB_EFI:
        bind_mounts()
        if not info.esp_mount:
            add(f"mount {esp} {mp}/boot/efi", "mount the EFI system partition")
        add(f"grub-install --target=x86_64-efi --efi-directory=/boot/efi "
            f"--bootloader-id={loader_id} --recheck",
            "reinstall the GRUB UEFI bootloader and its modules",
            destructive=True, in_chroot=True)
        add("update-grub", "regenerate grub.cfg from the installed kernels",
            destructive=True, in_chroot=True)
        add("update-initramfs -u -k all", "rebuild the initramfs for every kernel",
            destructive=True, in_chroot=True)
        if dev:
            add(f"efibootmgr -c -d {dev} -L {loader_id} "
                f"-l \\\\EFI\\\\{loader_id}\\\\grubx64.efi",
                "re-add the firmware boot entry if it was lost",
                destructive=True)
        add("efibootmgr -v", "verify the boot entry now exists")
        add(f"umount {mp}/boot/efi", "unmount the ESP cleanly")

    elif info.kind == BOOT_GRUB_BIOS:
        bind_mounts()
        add(f"grub-install --target=i386-pc --recheck {dev}",
            "reinstall the GRUB stage-1 bootloader into the MBR",
            destructive=True, in_chroot=True)
        add("update-grub", "regenerate grub.cfg", destructive=True, in_chroot=True)
        add("update-initramfs -u -k all", "rebuild the initramfs",
            destructive=True, in_chroot=True)

    elif info.kind == BOOT_SYSTEMD:
        bind_mounts()
        if not info.esp_mount:
            add(f"mount {esp} {mp}/boot", "mount the ESP at /boot for systemd-boot")
        add("bootctl install", "reinstall systemd-boot into the ESP",
            destructive=True, in_chroot=True)
        add("bootctl update", "refresh the systemd-boot binary",
            destructive=True, in_chroot=True)
        add("update-initramfs -u -k all", "rebuild the initramfs",
            destructive=True, in_chroot=True)
        add("bootctl status", "verify the installed bootloader")

    elif info.kind == BOOT_WINDOWS:
        target = esp or "<ESP device>"
        add(f"bcdboot {mp}/Windows /s {target} /f UEFI",
            "rewrite the Windows UEFI boot files", destructive=True)
        add(f"ntfsfix -d {mp}",
            "clear the NTFS dirty flag so Windows boots cleanly",
            destructive=True)
        add(f"bcdedit /store {mp}/Windows/System32/config/BCD /enum",
            "verify the Windows boot store")

    else:
        # Nothing identifiable. Assume UEFI+GRUB, but say so plainly.
        bind_mounts()
        add(f"grub-install --target=x86_64-efi --efi-directory=/boot/efi "
            f"--bootloader-id={loader_id} --recheck",
            "no bootloader detected; install GRUB assuming UEFI",
            destructive=True, in_chroot=True)
        add("update-grub", "regenerate grub.cfg", destructive=True, in_chroot=True)

    # Final veto, applied last so it covers every branch.
    plan.refusal = guard_live_disk(dev) or ""
    return plan


class BootRepairRunner:
    """Applies a :class:`BootPlan` through the Executor.

    ``--apply`` does not bypass anything: each step still goes through normal
    classification, the configured safety mode, interactive confirmation, and
    the audit log. A refused plan never runs at all. Execution stops at the
    first blocked or denied step, because a half-applied bootloader repair is
    worse than none.
    """

    def __init__(self, executor, mountpoint: str = RESCUE_MOUNT):
        self.executor = executor
        self.mountpoint = mountpoint

    def run(
        self,
        plan: BootPlan,
        *,
        on_step: Optional[Callable[[BootStep, object], None]] = None,
    ) -> List[Tuple[str, object]]:
        if plan.refusal:
            return [("REFUSED", plan.refusal)]

        results: List[Tuple[str, object]] = []
        for step in plan.steps:
            command = step.command
            if step.in_chroot and not command.startswith("chroot "):
                command = f"chroot {self.mountpoint} {command}"
            result = self.executor.run(command)
            results.append((command, result))
            if on_step:
                on_step(step, result)
            if not result.ran and result.decision in ("blocked", "denied"):
                break
        return results
