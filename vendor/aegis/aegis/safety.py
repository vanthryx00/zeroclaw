"""Command safety classification and authorization guardrails.

Every command Aegis wants to run passes through :func:`classify`. The
classifier returns a :class:`Verdict` describing:

* ``level``     — how dangerous the command is
* ``allowed``   — whether the current safety mode permits auto-execution
* ``reason``    — human-readable explanation shown to the user

Design goals:
  * Fail closed. Unknown commands are treated as ``RISKY``.
  * Hard-block genuinely catastrophic patterns regardless of mode.
  * Require the target of an offensive tool to be inside the user's declared
    authorized scope (``safety.authorized_targets``).
"""

from __future__ import annotations

import ipaddress
import re
import shlex
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Sequence


class Level(IntEnum):
    READ_ONLY = 0      # inspecting state, no side effects
    SAFE_WRITE = 1     # writes confined to the workspace
    RISKY = 2          # destructive / system-wide / hard to undo
    OFFENSIVE = 3      # security tooling aimed at a target
    BLOCKED = 4        # never allowed


LEVEL_LABEL = {
    Level.READ_ONLY: "read-only",
    Level.SAFE_WRITE: "safe-write",
    Level.RISKY: "risky",
    Level.OFFENSIVE: "offensive",
    Level.BLOCKED: "BLOCKED",
}


@dataclass
class Verdict:
    level: Level
    allowed: bool
    reason: str
    command: str
    matched_rule: Optional[str] = None
    targets: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return LEVEL_LABEL[self.level]


# --------------------------------------------------------------------------
# Rule tables
# --------------------------------------------------------------------------

READ_ONLY_BINARIES = {
    "ls", "cat", "head", "tail", "less", "more", "grep", "rg", "find", "fd",
    "stat", "file", "wc", "sort", "uniq", "cut", "awk", "sed", "diff", "tree",
    "pwd", "whoami", "id", "groups", "env", "printenv", "date", "uptime",
    "uname", "hostname", "lscpu", "lsblk", "lsusb", "lspci", "df", "du",
    "free", "ps", "top", "htop", "pgrep", "ss", "netstat", "ip", "ifconfig",
    "route", "arp", "dig", "nslookup", "host", "ping", "traceroute", "tracert",
    "journalctl", "dmesg", "systemctl", "service", "which", "type", "whereis",
    "man", "help", "history", "git", "docker", "podman", "kubectl", "jq",
    "sha256sum", "md5sum", "strings", "xxd", "hexdump", "od", "base64",
    "curl", "wget", "openssl", "gpg", "tar", "zipinfo", "unzip", "readelf",
    "objdump", "nm", "ldd", "strace", "ltrace", "lsof", "vmstat", "iostat",
    "nproc", "getcap", "getfacl", "capsh", "sestatus", "ausearch",
}

SAFE_WRITE_BINARIES = {
    "mkdir", "touch", "cp", "mv", "ln", "tee", "chmod", "chown", "tar", "zip",
    "unzip", "gzip", "gunzip", "bzip2", "xz", "install", "rsync",
}

RISKY_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\brm\b", "file deletion"),
    (r"\bdd\b", "raw disk write"),
    (r"\bmkfs(\.\w+)?\b", "filesystem format"),
    (r"\bfdisk\b|\bparted\b|\bgdisk\b", "partition table edit"),
    (r"\bshred\b", "secure erase"),
    (r":\(\)\s*\{.*\}\s*;?\s*:", "fork bomb"),
    (r"\bchmod\s+(-R\s+)?777\b", "world-writable permissions"),
    (r"\bchown\s+(-R\s+)?root\b", "ownership change to root"),
    (r"\bkill(all)?\b|\bpkill\b", "process termination"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", "service shutdown"),
    (r"\bshutdown\b|\breboot\b|\bpoweroff\b|\bhalt\b", "system power state"),
    (r"\biptables\b|\bnft\b|\bufw\b", "firewall modification"),
    (r"\bmount\b|\bumount\b", "mount/unmount"),
    (r"\bmodprobe\b|\binsmod\b|\brmmod\b", "kernel module load/unload"),
    (r"\bcrontab\b", "scheduled task modification"),
    (r"\buseradd\b|\buserdel\b|\busermod\b|\bpasswd\b", "account modification"),
    (r">\s*/dev/sd[a-z]", "write to raw block device"),
    (r"\bhistory\s+-c\b", "shell history wipe"),
)

# --------------------------------------------------------------------------
# Bootloader / firmware repair (rescue mode, #33)
# --------------------------------------------------------------------------
# These are legitimate during rescue but they rewrite the boot path, so the
# order here matters: read-only inspection is recognised *before* the generic
# risky patterns (e.g. `parted -l` lists, `parted /dev/sda` edits).

BOOT_READ_ONLY_PATTERNS: Sequence[tuple[str, str]] = (
    (r"^efibootmgr\s*(-v)?\s*$", "list EFI boot entries"),
    (r"^efibootmgr\s+-v\s+-u\s*$", "list EFI boot entries"),
    (r"^bootctl(\s+(status|list|is-installed|--version))?\s*$", "inspect systemd-boot"),
    (r"^os-prober\s*$", "probe for installed systems"),
    (r"^grub-probe\b", "probe the GRUB device map"),
    (r"^lsblk\b", "list block devices"),
    (r"^blkid\b", "identify block devices"),
    (r"^findmnt\b", "list mounted filesystems"),
    (r"^(fdisk|sfdisk|gdisk|sgdisk|parted)\s+(-l|--list)\b", "list partitions"),
    (r"^dumpe2fs\s+-h\b", "read a filesystem superblock"),
    (r"^tune2fs\s+-l\b", "read filesystem parameters"),
    (r"^lsinitramfs\b", "list initramfs contents"),
    (r"^bcdedit\s*$", "list the Windows boot configuration"),
)

BOOT_RISKY_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\bgrub-install\b|\bgrub2-install\b", "rewrite the GRUB bootloader"),
    (r"\bupdate-grub\b|\bgrub-mkconfig\b|\bgrub2-mkconfig\b", "regenerate the GRUB config"),
    (r"\bgrub-mkstandalone\b|\bgrub-editenv\b", "modify the GRUB environment"),
    (r"\bbootctl\s+(install|update|remove|set-default|set-oneshot)\b", "modify systemd-boot"),
    (r"\befibootmgr\b[^\n]*\s-[cBbontapA]\b", "modify EFI boot entries"),
    (r"\bbcdboot\b", "rewrite the Windows boot files"),
    (r"\bbootrec\b|\bbootsect\b|\bbcdedit\b", "repair the Windows boot record"),
    (r"\bupdate-initramfs\b|\bmkinitcpio\b|\bdracut\b", "rebuild the initramfs"),
)

# Genuinely catastrophic: wiping the ESP removes *every* OS's bootloader, and
# zeroing the first sectors of a disk destroys the partition table.
BOOT_BLOCKED_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\brm\s+-rf?\b[^\n]*(/boot/efi|/boot/EFI)(\s|/|$)",
     "delete the EFI system partition contents"),
    (r"\bmkfs(\.\w+)?\s+[^\n]*/boot/efi", "format the EFI system partition"),
    (r"\bdd\b[^\n]*of=[^\n]*/boot/efi", "overwrite the EFI system partition"),
    (r"\bdd\b[^\n]*of=/dev/(sd[a-z]|nvme\d+n\d+|vd[a-z])\b[^\n]*\bcount=1\b",
     "zero the disk partition table"),
    (r"\bwipefs\b[^\n]*\s-a\b", "wipe filesystem signatures"),
    (r"\bsgdisk\b[^\n]*--zap-all\b", "zap the partition table"),
)

# Offensive tooling. These are legitimate in a lab, but must target only
# authorized scope. Maps binary -> flag style used to extract a target.
OFFENSIVE_TOOLS = {
    "nmap", "masscan", "zmap", "unicornscan",
    "nikto", "gobuster", "feroxbuster", "dirb", "dirbuster", "ffuf", "wfuzz",
    "sqlmap", "wpscan", "joomscan", "droopescan",
    "hydra", "medusa", "patator", "ncrack", "john", "hashcat",
    "aircrack-ng", "airodump-ng", "aireplay-ng", "reaver", "bettercap",
    "msfconsole", "msfvenom", "armitage", "beef", "responder",
    "burpsuite", "zaproxy", "setoolkit", "mitmproxy",
    "ettercap", "dsniff", "arpspoof", "yersinia",
    "crackmapexec", "impacket", "bloodhound", "evil-winrm",
    "theHarvester", "recon-ng", "dnsrecon", "dnsenum", "fierce",
    "enum4linux", "smbclient", "smbmap", "rpcclient", "ldapsearch",
    "tcpdump", "tshark", "wireshark",
    "searchsploit", "exploitdb",
}

# --------------------------------------------------------------------------
# Windows / PowerShell
# --------------------------------------------------------------------------

WINDOWS_READ_ONLY = {
    "dir", "type", "more", "findstr", "where", "ipconfig", "systeminfo",
    "tasklist", "getmac", "whoami", "hostname", "netstat", "route",
    "nslookup", "ping", "tracert", "pathping", "wmic", "ver", "set",
    "get-childitem", "get-content", "get-process", "get-service",
    "get-help", "get-command", "get-item", "get-itemproperty",
    "select-string", "measure-object", "compare-object", "resolve-dnsname",
    "test-connection", "test-path", "get-eventlog", "get-ciminstance",
}

WINDOWS_SAFE_WRITE = {
    "copy", "xcopy", "robocopy", "move", "mkdir", "md", "new-item",
    "set-content", "add-content", "out-file", "compress-archive",
    "expand-archive", "tee-object",
}

WINDOWS_RISKY_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\bdel\b|\berase\b", "file deletion"),
    (r"\brd\b|\brmdir\b", "directory removal"),
    (r"\bformat\b", "drive format"),
    (r"\bdiskpart\b", "disk partitioning"),
    (r"\breg\s+(delete|add|import)\b", "registry modification"),
    (r"\bRemove-Item\b|\bRemove-ItemProperty\b", "PowerShell removal"),
    (r"\bStop-Process\b|\bStop-Service\b", "process/service stop"),
    (r"\bStop-Computer\b|\bRestart-Computer\b", "system power state"),
    (r"\bSet-ExecutionPolicy\b", "execution policy change"),
    (r"\bnet\s+(user|localgroup)\b", "account modification"),
    (r"\bNew-LocalUser\b|\bAdd-LocalGroupMember\b|\bRemove-LocalUser\b", "account modification"),
    (r"\bbcdedit\b", "boot configuration"),
    (r"\bschtasks\b", "scheduled task modification"),
    (r"\btakeown\b|\bicacls\b", "ownership/permission change"),
    (r"\bcipher\s+/w\b", "free-space wipe"),
    (r"\bvssadmin\b", "shadow copy management"),
)

WINDOWS_BLOCKED_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\bformat\s+[a-zA-Z]:", "format a drive"),
    (r"\brd\s+(?:/[a-z]+\s+)*[a-zA-Z]:\\?\s*($|[;&|])", "recursive delete of a drive root"),
    (r"\bdel\s+(?:/[a-z]+\s+)*[a-zA-Z]:\\?\*", "recursive delete of a drive root"),
    (r"\bRemove-Item\b[^\n]*-Recurse[^\n]*-Force[^\n]*[a-zA-Z]:\\?\s*($|[;&|])",
     "recursive delete of a drive root"),
    (r"\bRemove-Item\b[^\n]*C:\\Windows", "delete Windows directory"),
    (r"\bvssadmin\s+delete\s+shadows", "delete shadow copies (ransomware behaviour)"),
    (r"\bbcdedit\s+/set[^\n]*recoveryenabled\s+no", "disable recovery"),
    (r"\bcipher\s+/w:[a-zA-Z]:", "wipe free space on a drive"),
    (r"\bIEX\b|\bInvoke-Expression\b[^\n]*\|", "pipe remote script to expression"),
)

WINDOWS_PROTECTED = [
    r"C:\\Windows", r"C:\\Program Files", r"C:\\Program Files \(x86\)",
    r"C:\\ProgramData", r"C:\\Users\\Default",
]

# Catastrophic patterns that are never allowed.
BLOCKED_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\brm\s+-rf?\s+/\s*($|[;&|])", "recursive delete of root"),
    (r"\brm\s+-rf?\s+/\*", "recursive delete of root contents"),
    (r"\bdd\b[^\n]*\bof=/dev/(sd[a-z]|nvme\d+n\d+|vd[a-z]|mmcblk\d+)\b", "overwrite system disk"),
    (r"\bmkfs(\.\w+)?\s+/dev/(sd[a-z]|nvme\d+n\d+)\b", "format system disk"),
    (r":\(\)\s*\{.*\};\s*:", "fork bomb"),
    (r"\bcurl\b[^\n|]*\|\s*(ba)?sh\b", "pipe remote script to shell"),
    (r"\bwget\b[^\n|]*\|\s*(ba)?sh\b", "pipe remote script to shell"),
    (r"\b(nc|ncat|netcat)\b\s+[^\n]*-e\s", "reverse/bind shell"),
    (r"\bbash\s+-i\s+>&\s*/dev/tcp/", "reverse shell"),
    (r"/dev/tcp/\d", "raw TCP shell"),
    (r"\bchmod\s+(-R\s+)?[0-7]*s[0-7]*\s+/(\s|$)", "suid on root"),
    (r"\bchattr\s+[+-]i\s+/(etc|bin|sbin|usr)\b", "immutable system files"),
    (r"\becho\b.*>\s*/etc/(passwd|shadow|sudoers)", "overwrite auth files"),
    (r"\bmv\b\s+/\s+/dev/null", "move root to null"),
    (r"\bshred\b.*/dev/sd[a-z]", "shred system disk"),
    (r"\bhistory\s+-c\b\s*&&\s*", "history wipe chain"),
)

_TARGET_FLAG_RE = re.compile(
    r"(?<!\S)(?:-h|--host|-u|--url|-t|--target|--hosts|-d|--domain)\s+(\S+)"
)
_URL_RE = re.compile(r"https?://([^/\s:]+)")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
_HOSTNAME_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")


# --------------------------------------------------------------------------
# GUI actions (eyes + hands)
# --------------------------------------------------------------------------
# GUI descriptors look like ``gui:click 500,300``. They are classified here,
# before the shell patterns: a ``gui:type`` body is *text to be typed*, not a
# command to run, so the shell rule tables must never see it raw.

#: Verbs that only inspect state — safe to auto-run in auto_safe.
GUI_READ_ONLY_VERBS = {"screenshot", "move_to", "size"}

#: Verbs that change desktop state — need confirmation in confirm mode.
GUI_STATE_VERBS = {
    "click", "double_click", "right_click", "type", "key", "hotkey",
    "scroll", "drag",
}

_GUI_COORD_RE = re.compile(r"^\s*-?\d+\s*,\s*-?\d+\s*$")

#: Destructive patterns in typed text. A ``gui:type`` body is typed into
#: whatever app has focus — which may be a terminal — so text that would
#: destroy data if executed is hard-blocked rather than trusted.
GUI_TYPE_BLOCKED_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\brm\s+-rf?\b", "recursive delete"),
    (r"\bmkfs(\.\w+)?\b", "filesystem format"),
    (r"\bdd\b[^\n]*\bof=/dev/", "raw disk write"),
    (r"\bformat\s+[a-zA-Z]:", "drive format"),
    (r"\bdel\s+/[a-z]+\s+[a-zA-Z]:", "forced delete"),
    (r"\bshutdown\b|\breboot\b|\bpoweroff\b|\bhalt\b", "system power state"),
    (r"\bRemove-Item\b[^\n]*-Recurse", "recursive delete"),
    (r"\bvssadmin\s+delete\s+shadows", "delete shadow copies"),
    (r"\bIEX\b|\bInvoke-Expression\b", "pipe script to expression"),
    (r"\bcurl\b[^\n|]*\|\s*(ba)?sh\b", "pipe remote script to shell"),
    (r"\bwget\b[^\n|]*\|\s*(ba)?sh\b", "pipe remote script to shell"),
)

#: Credential-shaped typed text. A bare password typed into a login field
#: has no marker and cannot be detected — that case is what confirmation is
#: for. But an *assignment* (``password=…``, ``api_key: …``) is almost
#: certainly a secret being typed where it does not belong.
GUI_CREDENTIAL_PATTERNS: Sequence[tuple[str, str]] = (
    (r"(?i)\b(password|passwd|pwd)\s*[:=]", "password assignment"),
    (r"(?i)\b(api[_-]?key|apikey)\s*[:=]", "API key assignment"),
    (r"(?i)\b(secret|client[_-]?secret)\s*[:=]", "secret assignment"),
    (r"(?i)\b(access[_-]?token|auth[_-]?token|bearer)\s*[:=]?", "auth token"),
    (r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key material"),
)


def _classify_gui(command: str, cfg) -> Verdict:
    """Classify a ``gui:`` descriptor. Fail closed on anything unparseable."""
    text = command.strip()
    rest = text[4:].strip()
    if not rest:
        return Verdict(Level.RISKY, False, "empty GUI action", command,
                       "gui:empty")
    parts = rest.split(None, 1)
    verb = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    if verb in GUI_READ_ONLY_VERBS:
        if verb in ("move_to",) and args and not _GUI_COORD_RE.match(args):
            return Verdict(Level.RISKY, False,
                           f"gui:move_to needs coordinates like '500,300', "
                           f"got {args!r}", command, "gui:bad-coords")
        return Verdict(Level.READ_ONLY, False,
                       f"read-only GUI action: gui:{verb}", command,
                       f"gui:{verb}")

    if verb in GUI_STATE_VERBS:
        if verb in ("click", "double_click", "right_click") and not _GUI_COORD_RE.match(args):
            return Verdict(Level.RISKY, False,
                           f"gui:{verb} needs coordinates like '500,300', "
                           f"got {args!r}", command, "gui:bad-coords")
        if verb == "drag":
            pairs = args.split()
            if len(pairs) != 2 or not all(
                    _GUI_COORD_RE.match(p) for p in pairs):
                return Verdict(Level.RISKY, False,
                               "gui:drag needs two coordinate pairs, "
                               "e.g. 'gui:drag 100,200 300,400'",
                               command, "gui:bad-coords")
        if verb == "type":
            for pattern, reason in GUI_CREDENTIAL_PATTERNS:
                if re.search(pattern, args):
                    return Verdict(Level.BLOCKED, False,
                                   f"hard-blocked: gui:type text looks like "
                                   f"a credential ({reason})",
                                   command, "gui:credential")
            for pattern, reason in GUI_TYPE_BLOCKED_PATTERNS:
                if re.search(pattern, args, re.IGNORECASE):
                    return Verdict(Level.BLOCKED, False,
                                   f"hard-blocked: gui:type text would be "
                                   f"destructive if executed ({reason})",
                                   command, "gui:destructive-type")
        return Verdict(Level.RISKY, False,
                       f"state-changing GUI action: gui:{verb}", command,
                       f"gui:{verb}")

    # Unknown verb — fail closed. Never guess what an unknown action does.
    return Verdict(Level.RISKY, False,
                   f"unknown GUI action 'gui:{verb}'", command, "gui:unknown")


def _first_token(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if not parts:
        return ""
    token = parts[0]
    # strip env prefixes like FOO=bar and sudo
    idx = 0
    while idx < len(parts) and ("=" in parts[idx] and not parts[idx].startswith("-")):
        idx += 1
    if idx < len(parts):
        token = parts[idx]
    if token in ("sudo", "doas"):
        idx += 1
        token = parts[idx] if idx < len(parts) else token
    # handle POSIX and Windows paths, and .exe suffixes
    token = token.replace("\\", "/").rsplit("/", 1)[-1]
    if token.lower().endswith(".exe"):
        token = token[:-4]
    return token.lower()


def extract_targets(command: str) -> List[str]:
    """Pull candidate network targets out of a command string."""
    targets: List[str] = []
    for match in _TARGET_FLAG_RE.findall(command):
        targets.append(match.strip("'\""))
    for match in _URL_RE.findall(command):
        targets.append(match.split(":")[0])
    for match in _IP_RE.findall(command):
        targets.append(match)
    for match in _HOSTNAME_RE.findall(command):
        # skip common non-target tokens
        if match not in ("localhost",) and not match.endswith(".local"):
            targets.append(match)
    # de-dupe, preserve order
    seen = set()
    out = []
    for t in targets:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _target_authorized(target: str, scope: Sequence[str]) -> bool:
    """Return True if *target* falls inside the declared authorized scope."""
    if not scope:
        return False
    t = target.strip()
    # try IP / CIDR containment
    try:
        t_ip = ipaddress.ip_network(t, strict=False)
        for entry in scope:
            try:
                net = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                continue
            if t_ip.subnet_of(net) or t_ip == net:
                return True
    except ValueError:
        pass
    # hostname / exact match (allow wildcard *.example.com)
    for entry in scope:
        e = entry.strip()
        if t == e:
            return True
        if e.startswith("*.") and t.endswith(e[1:]):
            return True
    return False


def _path_is_protected(command: str, protected: Sequence[str]) -> Optional[str]:
    """Flag writes to protected top-level paths outside the workspace."""
    for match in re.findall(r"(?<!\S)(/(?:[A-Za-z0-9._-]+/?)+)", command):
        norm = "/" + match.strip("/").split("/")[0]
        if norm in protected:
            return norm
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def classify(command: str, cfg) -> Verdict:
    """Classify *command* against the loaded :class:`~aegis.config.Config`."""
    cmd = command.strip()
    if not cmd:
        return Verdict(Level.BLOCKED, False, "empty command", cmd)

    # 0. GUI descriptors are classified by their own rules — a gui:type body
    #    is text to be typed, not a command, so shell patterns never see it.
    if cmd.startswith("gui:"):
        return _classify_gui(cmd, cfg)

    # 1. Hard blocks first — never allowed (POSIX + Windows).
    for pattern, reason in (BLOCKED_PATTERNS + WINDOWS_BLOCKED_PATTERNS
                            + BOOT_BLOCKED_PATTERNS):
        if re.search(pattern, cmd, re.IGNORECASE):
            return Verdict(Level.BLOCKED, False, f"hard-blocked: {reason}", cmd, pattern)

    # 1b. Protected Windows paths.
    for pattern in WINDOWS_PROTECTED:
        if re.search(pattern, cmd, re.IGNORECASE) and re.search(
                r"\b(del|rd|rmdir|Remove-Item|format|copy|move|New-Item|Set-Content)\b",
                cmd, re.IGNORECASE):
            return Verdict(Level.RISKY, False,
                           f"writes to protected Windows path ({pattern})", cmd, pattern)

    binary = _first_token(cmd)
    targets = extract_targets(cmd)

    # 2. Offensive tooling — must have an authorized target.
    if binary in OFFENSIVE_TOOLS:
        if not targets:
            # Some tools scan localhost by default (tcpdump, hashcat on files).
            if binary in ("hashcat", "john", "tcpdump", "tshark", "wireshark",
                          "searchsploit", "exploitdb"):
                return Verdict(Level.OFFENSIVE, False,
                               f"{binary} runs locally but needs explicit approval",
                               cmd, binary, targets)
            return Verdict(Level.OFFENSIVE, False,
                           f"{binary} has no declared target", cmd, binary, targets)
        bad = [t for t in targets if not _target_authorized(t, cfg.safety.authorized_targets)]
        if bad:
            return Verdict(
                Level.OFFENSIVE, False,
                f"{binary} targets outside authorized scope: {', '.join(bad)}. "
                f"Declare scope with `aegis scope add <target>`.",
                cmd, binary, targets,
            )
        return Verdict(Level.OFFENSIVE, False,
                       f"{binary} against authorized target(s): {', '.join(targets)}",
                       cmd, binary, targets)

    # 2b. Boot inspection is read-only even though it names block devices.
    for pattern, reason in BOOT_READ_ONLY_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return Verdict(Level.READ_ONLY, False, f"read-only: {reason}",
                           cmd, pattern, targets)

    # 3. Risky patterns (POSIX + Windows + bootloader writes).
    for pattern, reason in (RISKY_PATTERNS + WINDOWS_RISKY_PATTERNS
                            + BOOT_RISKY_PATTERNS):
        if re.search(pattern, cmd, re.IGNORECASE):
            # rm inside the workspace is downgraded to safe-write.
            if pattern == r"\brm\b" and _within_workspace(cmd, cfg.safety.workspace_root):
                return Verdict(Level.SAFE_WRITE, False,
                               "deletion confined to workspace", cmd, pattern, targets)
            return Verdict(Level.RISKY, False, f"risky: {reason}", cmd, pattern, targets)

    # 4. Protected path writes.
    protected = _path_is_protected(cmd, cfg.safety.protected_paths)
    if protected and re.search(r"\b(cp|mv|rm|dd|tee|chmod|chown|>\s*)\b", cmd):
        return Verdict(Level.RISKY, False,
                       f"writes to protected path {protected}", cmd, "protected-path", targets)

    # 5. Safe write vs read only (POSIX + Windows).
    if binary in SAFE_WRITE_BINARIES or binary in WINDOWS_SAFE_WRITE:
        return Verdict(Level.SAFE_WRITE, False, "workspace write", cmd, binary, targets)
    if binary in READ_ONLY_BINARIES or binary in WINDOWS_READ_ONLY:
        return Verdict(Level.READ_ONLY, False, "read-only inspection", cmd, binary, targets)

    # 6. Unknown — fail closed.
    return Verdict(Level.RISKY, False, f"unrecognized command '{binary}'", cmd, "unknown", targets)


def _within_workspace(command: str, workspace: str) -> bool:
    paths = re.findall(r"(?<!\S)(/[^\s;|&]+)", command)
    if not paths:
        return False
    ws = workspace.rstrip("/")
    return all(p.startswith(ws) for p in paths)


def decide(verdict: Verdict, mode: str) -> bool:
    """Given a verdict and safety mode, return whether to auto-execute."""
    if verdict.level == Level.BLOCKED:
        return False
    if mode == "dry_run":
        return False
    if mode == "confirm":
        return False
    if mode == "auto_safe":
        return verdict.level in (Level.READ_ONLY, Level.SAFE_WRITE)
    if mode == "auto_full":
        return verdict.level != Level.BLOCKED
    return False
