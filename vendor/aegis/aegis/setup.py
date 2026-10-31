"""First-boot wizard: choose a privacy profile and size the local model to RAM.

Two jobs:

1. **Pick a privacy profile** — ``workstation``, ``amnesic``, or ``rescue`` —
   and write the matching ``[privacy]`` / ``[safety]`` config plus enable the
   right systemd services.

2. **Size the Ollama model to the machine.** A 32B model on a 4 GB laptop is
   not "more capable", it is a machine that swaps itself to death. This module
   measures total/available RAM, subtracts a realistic OS + working-memory
   reserve, and picks the largest model that actually fits — with extra
   headroom when the OS itself lives in RAM (``toram`` / amnesic mode).

Run interactively with ``aegis setup`` or unattended with ``aegis setup --auto``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# --------------------------------------------------------------------------
# Model catalog: (name, approx resident size in MB)
# --------------------------------------------------------------------------
MODEL_CATALOG = [
    ("qwen2.5-coder:1.5b", 1100),
    ("qwen2.5-coder:3b", 2000),
    ("qwen2.5-coder:7b", 4700),
    ("qwen2.5-coder:14b", 9000),
    ("qwen2.5-coder:32b", 20000),
]

# Base headroom for the OS, desktop, and the model's own working memory
# (context window, KV cache). This is deliberately generous: running out of
# RAM mid-inference is worse than running a smaller model.
RESERVE_MB = 1800
# Extra headroom when the whole OS is loaded into RAM (toram / amnesic): the
# squashfs image, tmpfs scratch, and the live overlay all live there too.
AMNESIC_EXTRA_RESERVE_MB = 1800
# Rescue mode favours responsiveness over raw capability.
RESCUE_MAX_MODEL = "qwen2.5-coder:7b"


# --------------------------------------------------------------------------
# Hardware
# --------------------------------------------------------------------------

@dataclass
class HardwareProfile:
    total_ram_mb: int
    available_ram_mb: int
    cpu_count: int
    disk_free_gb: int
    is_live: bool
    toram: bool
    is_uefi: bool

    def summary(self) -> str:
        env = "live USB" if self.is_live else "installed system"
        if self.toram:
            env += " (toram — OS in RAM)"
        return (
            f"RAM: {self.total_ram_mb} MiB total / {self.available_ram_mb} MiB free\n"
            f"CPU: {self.cpu_count} cores\n"
            f"Disk free: {self.disk_free_gb} GiB\n"
            f"Boot: {env}, {'UEFI' if self.is_uefi else 'BIOS'}"
        )


def _meminfo() -> Dict[str, int]:
    info: Dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    info[key] = int(parts[0])  # kB
    except OSError:
        pass
    return info


def detect_hardware() -> HardwareProfile:
    mem = _meminfo()
    total_mb = mem.get("MemTotal", 0) // 1024
    avail_mb = mem.get("MemAvailable", mem.get("MemTotal", 0)) // 1024

    try:
        free_gb = shutil.disk_usage("/").free // (1024 ** 3)
    except OSError:
        free_gb = 0

    cmdline = ""
    try:
        with open("/proc/cmdline", encoding="utf-8") as fh:
            cmdline = fh.read()
    except OSError:
        pass

    # A live environment usually mounts an overlay and has /run/live or /lib/live.
    is_live = (
        "boot=casper" in cmdline
        or os.path.isdir("/run/live")
        or os.path.isdir("/lib/live")
        or os.path.exists("/casper")
    )

    return HardwareProfile(
        total_ram_mb=total_mb,
        available_ram_mb=avail_mb,
        cpu_count=os.cpu_count() or 1,
        disk_free_gb=free_gb,
        is_live=is_live,
        toram="toram" in cmdline,
        is_uefi=os.path.isdir("/sys/firmware/efi"),
    )


# --------------------------------------------------------------------------
# Model recommendation
# --------------------------------------------------------------------------

@dataclass
class ModelRecommendation:
    model: str
    size_mb: int
    reserve_mb: int
    reason: str

    @property
    def fits(self) -> bool:
        return self.size_mb <= max(0, self.size_mb)  # always true; kept for API


def recommend_model(hw: HardwareProfile, profile_key: str,
                    override: Optional[str] = None) -> ModelRecommendation:
    reserve = RESERVE_MB
    notes: List[str] = []

    if profile_key == "amnesic" or hw.toram:
        reserve += AMNESIC_EXTRA_RESERVE_MB
        notes.append("+1800 MiB headroom because the OS is in RAM (amnesic/toram)")

    usable = hw.total_ram_mb - reserve

    if override:
        size = dict(MODEL_CATALOG).get(override, 0)
        return ModelRecommendation(
            override, size, reserve,
            f"operator override ({size} MiB)"
            + (" — WARNING: may not fit" if size > usable else ""),
        )

    # Candidates that fit, largest first.
    fitting = [(name, size) for name, size in MODEL_CATALOG if size <= usable]

    if not fitting:
        name, size = MODEL_CATALOG[0]
        return ModelRecommendation(
            name, size, reserve,
            f"no model fits comfortably (usable ~{usable} MiB after "
            f"{reserve} MiB reserve); smallest selected — expect swapping",
        )

    name, size = fitting[-1]

    # Rescue mode caps the size for responsiveness.
    if profile_key == "rescue":
        cap = dict(MODEL_CATALOG)[RESCUE_MAX_MODEL]
        if size > cap:
            fitting = [(n, s) for n, s in fitting if s <= cap]
            if fitting:
                name, size = fitting[-1]
                notes.append("capped at 7b for rescue-mode responsiveness")

    reason = (
        f"{size} MiB model fits in ~{usable} MiB usable "
        f"(total {hw.total_ram_mb} MiB − {reserve} MiB reserve)"
    )
    if notes:
        reason += "; " + "; ".join(notes)
    return ModelRecommendation(name, size, reserve, reason)


# --------------------------------------------------------------------------
# Privacy profiles
# --------------------------------------------------------------------------

@dataclass
class Profile:
    key: str
    title: str
    description: str
    privacy: Dict[str, object] = field(default_factory=dict)
    safety: Dict[str, object] = field(default_factory=dict)
    services_enable: List[str] = field(default_factory=list)


PROFILES: Dict[str, Profile] = {
    "workstation": Profile(
        key="workstation",
        title="Workstation",
        description=(
            "Everyday persistent security workstation. Full tooling, no forced "
            "Tor, normal networking. Best when this is your main machine."
        ),
        privacy={
            "amnesic": False,
            "force_tor": False,
            "randomize_mac": True,
            "dns_over_tor": False,
            "wipe_memory_on_shutdown": False,
            "timezone_utc": False,
        },
        safety={"mode": "auto_safe"},
        services_enable=["aegis-randomize-mac.service"],
    ),
    "amnesic": Profile(
        key="amnesic",
        title="Amnesic",
        description=(
            "RAM-only, Tor-forced, leaves no trace. Nothing is written to the "
            "USB stick; memory is wiped on shutdown. For sensitive work."
        ),
        privacy={
            "amnesic": True,
            "force_tor": True,
            "randomize_mac": True,
            "dns_over_tor": True,
            "wipe_memory_on_shutdown": True,
            "timezone_utc": True,
        },
        safety={"mode": "auto_safe"},
        services_enable=[
            "tor.service",
            "aegis-tor-firewall.service",
            "aegis-randomize-mac.service",
            "aegis-memwipe.service",
        ],
    ),
    "rescue": Profile(
        key="rescue",
        title="Rescue",
        description=(
            "Diagnose and repair a broken system. No forced Tor (you often need "
            "direct network to fetch packages), and every command is confirmed "
            "because you are modifying someone else's machine."
        ),
        privacy={
            "amnesic": False,
            "force_tor": False,
            "randomize_mac": False,
            "dns_over_tor": False,
            "wipe_memory_on_shutdown": False,
            "timezone_utc": True,
        },
        safety={"mode": "confirm", "workspace_root": "/root/aegis-rescue"},
        services_enable=[],
    ),
}


def auto_profile(hw: HardwareProfile) -> str:
    """Pick a sensible profile with no operator input."""
    if hw.toram:
        return "amnesic"
    if hw.is_live:
        return "amnesic"
    return "workstation"


# --------------------------------------------------------------------------
# Plan + apply
# --------------------------------------------------------------------------

@dataclass
class SetupPlan:
    profile: Profile
    model: ModelRecommendation
    hardware: HardwareProfile
    config_path: str

    def render(self) -> str:
        lines = [
            "Detected hardware:",
            _indent(self.hardware.summary()),
            "",
            f"Privacy profile: {self.profile.title}  ({self.profile.key})",
            _indent(self.profile.description),
            "",
            f"Recommended model: {self.model.model}  (~{self.model.size_mb} MiB)",
            _indent(self.model.reason),
            "",
            f"Config will be written to: {self.config_path}",
        ]
        if self.profile.services_enable:
            lines.append("Services to enable:")
            for svc in self.profile.services_enable:
                lines.append(f"  - {svc}")
        return "\n".join(lines)


def build_plan(hw: HardwareProfile, profile_key: str,
               model_override: Optional[str] = None,
               config_path: Optional[str] = None) -> SetupPlan:
    if profile_key not in PROFILES:
        profile_key = auto_profile(hw)
    profile = PROFILES[profile_key]
    model = recommend_model(hw, profile_key, model_override)
    if config_path is None:
        config_path = os.path.expanduser("~/.config/aegis/config.toml")
    return SetupPlan(profile, model, hw, config_path)


def apply_plan(plan: SetupPlan, *, pull: bool = True, enable_services: bool = True,
               dry_run: bool = False,
               on_log: Optional[Callable[[str], None]] = None) -> List[str]:
    """Write the config, optionally pull the model and enable services.

    Returns a list of human-readable log lines describing what happened.
    """
    log: List[str] = []

    def emit(msg: str) -> None:
        log.append(msg)
        if on_log:
            on_log(msg)

    # 1. Write config ------------------------------------------------------
    if dry_run:
        emit(f"[dry-run] would write {plan.config_path}")
    else:
        try:
            _write_config(plan)
            emit(f"wrote {plan.config_path}")
        except OSError as exc:
            emit(f"ERROR writing config: {exc}")
            return log

    # 2. Pull the model ----------------------------------------------------
    if pull:
        if _ollama_available():
            if dry_run:
                emit(f"[dry-run] would run: ollama pull {plan.model.model}")
            else:
                emit(f"pulling model {plan.model.model} (this can take a while)...")
                ok = _pull_model(plan.model.model, on_log)
                emit(f"model pull {'succeeded' if ok else 'FAILED'}: {plan.model.model}")
        else:
            emit("ollama not found; skipping model pull "
                 "(install it, then run: ollama pull " + plan.model.model + ")")

    # 3. Enable services ---------------------------------------------------
    if enable_services and plan.profile.services_enable:
        if os.geteuid() != 0:
            emit("not running as root; run these to enable services:")
            for svc in plan.profile.services_enable:
                emit(f"  sudo systemctl enable --now {svc}")
        elif dry_run:
            for svc in plan.profile.services_enable:
                emit(f"[dry-run] would enable {svc}")
        else:
            for svc in plan.profile.services_enable:
                ok = _systemctl("enable", "--now", svc)
                emit(f"systemctl enable --now {svc}: {'ok' if ok else 'failed'}")

    return log


def _write_config(plan: SetupPlan) -> None:
    """Merge the plan's deltas into the user config and write it out."""
    from .config import Config

    cfg = Config.load()
    for key, val in plan.profile.privacy.items():
        if hasattr(cfg.privacy, key):
            setattr(cfg.privacy, key, val)
    for key, val in plan.profile.safety.items():
        if hasattr(cfg.safety, key):
            setattr(cfg.safety, key, val)
    cfg.model.ollama_model = plan.model.model

    os.makedirs(os.path.dirname(plan.config_path), exist_ok=True)
    with open(plan.config_path, "w", encoding="utf-8") as fh:
        fh.write(_render_toml(cfg, plan))


def _render_toml(cfg, plan: SetupPlan) -> str:
    """Render a complete, human-readable config.toml (tomllib is read-only)."""
    p = cfg.privacy
    s = cfg.safety
    m = cfg.model

    def b(v: bool) -> str:
        return "true" if v else "false"

    lines = [
        "# AegisOS configuration — written by `aegis setup`",
        f"# profile: {plan.profile.key}",
        "",
        "[model]",
        f'backends = [{", ".join(chr(34) + x + chr(34) for x in m.backends)}]',
        f'ollama_host = "{m.ollama_host}"',
        f'ollama_model = "{m.ollama_model}"',
        f'llamacpp_server = "{m.llamacpp_server}"',
        f'llamacpp_model_path = "{m.llamacpp_model_path}"',
        f'llamacpp_cli = "{m.llamacpp_cli}"',
        f"temperature = {m.temperature}",
        f"max_tokens = {m.max_tokens}",
        f"request_timeout = {m.request_timeout}",
        f"max_tool_rounds = {m.max_tool_rounds}",
        "",
        "[safety]",
        f'mode = "{s.mode}"',
        f'workspace_root = "{s.workspace_root}"',
        "authorized_targets = []",
        f"allow_sudo = {b(s.allow_sudo)}",
        f"command_timeout = {s.command_timeout}",
        "",
        "[interface]",
        f'theme = "{cfg.interface.theme}"',
        f"show_reasoning = {b(cfg.interface.show_reasoning)}",
        f'audit_log = "{cfg.interface.audit_log}"',
        f'history_file = "{cfg.interface.history_file}"',
        "",
        "[learning]",
        f"enabled = {b(bool(cfg.learning.enabled))}",
        f"autosave_commands = {b(bool(cfg.learning.autosave_commands))}",
        f"autosave_successes = {b(bool(cfg.learning.autosave_successes))}",
        f"max_context_items = {cfg.learning.max_context_items}",
        "",
        "[privacy]",
        f"amnesic = {b(bool(p.amnesic))}",
        f"force_tor = {b(bool(p.force_tor))}",
        f"randomize_mac = {b(bool(p.randomize_mac))}",
        f"dns_over_tor = {b(bool(p.dns_over_tor))}",
        f"wipe_memory_on_shutdown = {b(bool(p.wipe_memory_on_shutdown))}",
        f"timezone_utc = {b(bool(p.timezone_utc))}",
        f'proxy = "{p.proxy}"',
        f"whonix_enabled = {b(bool(p.whonix_enabled))}",
        f"tor_socks_port = {p.tor_socks_port}",
        f"tor_trans_port = {p.tor_trans_port}",
        f"tor_dns_port = {p.tor_dns_port}",
        "",
    ]
    return "\n".join(lines)


def _ollama_available() -> bool:
    return shutil.which("ollama") is not None


def _pull_model(model: str, on_log: Optional[Callable[[str], None]]) -> bool:
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if on_log:
                on_log("  " + line.rstrip())
        proc.wait(timeout=3600)
        return proc.returncode == 0
    except Exception as exc:
        if on_log:
            on_log(f"  pull error: {exc}")
        return False


def _systemctl(*args: str) -> bool:
    try:
        proc = subprocess.run(["systemctl", *args], capture_output=True, text=True,
                              timeout=30)
        return proc.returncode == 0
    except Exception:
        return False


def _indent(text: str) -> str:
    return "\n".join("  " + line for line in text.splitlines())


# --------------------------------------------------------------------------
# Interactive wizard
# --------------------------------------------------------------------------

def run_wizard(*, profile: Optional[str] = None, model: Optional[str] = None,
               auto: bool = False, pull: bool = True, yes: bool = False,
               show_only: bool = False, config_path: Optional[str] = None,
               on_log: Optional[Callable[[str], None]] = None) -> int:
    """Entry point used by the CLI and the first-boot service."""
    hw = detect_hardware()

    if profile is None:
        profile = auto_profile(hw) if auto else _ask_profile(hw)

    plan = build_plan(hw, profile, model, config_path)

    _say(on_log, plan.render())

    if show_only:
        return 0

    if not (yes or auto or _confirm(on_log, "Apply this configuration?")):
        _say(on_log, "aborted; nothing changed.")
        return 1

    logs = apply_plan(plan, pull=pull, enable_services=True, on_log=on_log)
    _say(on_log, "")
    _say(on_log, "Done.")
    _say(on_log, "Verify with:  aegis status && aegis privacy status")
    return 0


def _ask_profile(hw: HardwareProfile) -> str:
    default = auto_profile(hw)
    print()
    print("Choose a privacy profile:")
    order = ["workstation", "amnesic", "rescue"]
    for i, key in enumerate(order, 1):
        p = PROFILES[key]
        mark = " (recommended)" if key == default else ""
        print(f"  {i}) {p.title}{mark}")
        for line in _wrap(p.description, 66):
            print(f"       {line}")
    print()
    while True:
        try:
            choice = input(f"Profile [1-3, default {order.index(default)+1}]: ").strip()
        except EOFError:
            return default
        if not choice:
            return default
        if choice in ("1", "2", "3"):
            return order[int(choice) - 1]
        if choice in PROFILES:
            return choice
        print("  enter 1, 2, or 3")


def _confirm(on_log, prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def _say(on_log, msg: str) -> None:
    if on_log:
        on_log(msg)
    else:
        print(msg)


def _wrap(text: str, width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
