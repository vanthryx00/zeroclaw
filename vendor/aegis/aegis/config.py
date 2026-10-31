"""Configuration loading and defaults for Aegis.

Config lives at ~/.config/aegis/config.toml (user) with system defaults at
/etc/aegis/config.toml. Environment variables override file values so the
distro can ship sane defaults while users tune per machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # Python 3.11+
    import tomllib as _toml
    _HAS_TOML = True
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.9/3.10
    try:
        import tomli as _toml  # type: ignore
        _HAS_TOML = True
    except ModuleNotFoundError:
        _HAS_TOML = False


VALID_MODES = ("confirm", "auto_safe", "auto_full", "dry_run")


def _data_path(name: str) -> str:
    """Platform-correct default location for a data file."""
    from .platform import data_dir
    return str(data_dir() / name)


def _config_path(name: str = "config.toml") -> str:
    from .platform import config_dir
    return str(config_dir() / name)

# Directories Aegis is allowed to touch by default. Anything outside the
# workspace root is treated as protected and requires explicit override.
DEFAULT_WORKSPACE = str(Path.home() / "aegis-workspace")


@dataclass
class ModelConfig:
    # Backend selection order. The router tries these in order.
    backends: List[str] = field(default_factory=lambda: ["ollama", "llamacpp"])
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    # llama.cpp: either an OpenAI-compatible server URL or a local llama-cli path
    llamacpp_server: str = "http://127.0.0.1:8080"
    llamacpp_model_path: str = "/usr/share/aegis/models/aegis-coder.gguf"
    llamacpp_cli: str = "llama-cli"
    temperature: float = 0.2
    max_tokens: int = 2048
    request_timeout: float = 120.0
    # Number of tool/observation round-trips allowed in one agent turn.
    max_tool_rounds: int = 6


@dataclass
class SafetyConfig:
    mode: str = "auto_safe"  # one of VALID_MODES
    workspace_root: str = DEFAULT_WORKSPACE
    # Authorized targets for offensive tools (IPs, CIDRs, hostnames). Empty
    # means offensive commands are blocked until the user declares scope.
    authorized_targets: List[str] = field(default_factory=list)
    allow_sudo: bool = False
    command_timeout: float = 120.0
    # Commands the user chose "always allow" for. A standing authorisation, so
    # it is revocable in one place: `aegis allow list` / `aegis allow rm <id>`.
    allowlist_file: str = field(default_factory=lambda: _data_path("allowlist.jsonl"))
    # Hard-blocked patterns can never run, even in auto_full.
    protected_paths: List[str] = field(
        default_factory=lambda: ["/", "/boot", "/etc", "/usr", "/var", "/dev", "/sys", "/proc"]
    )


@dataclass
class InterfaceConfig:
    theme: str = "aegis"
    show_reasoning: bool = True
    # Render assistant replies token by token as they arrive.
    stream: bool = True
    audit_log: str = field(default_factory=lambda: _data_path("audit.jsonl"))
    history_file: str = field(default_factory=lambda: _data_path("history"))


@dataclass
class PrivacyConfig:
    # Amnesic mode: root/home on RAM, nothing written to the USB stick.
    amnesic: bool = False
    # Force all traffic through Tor (transparent proxy + DNS).
    force_tor: bool = False
    # Randomize MAC addresses on boot.
    randomize_mac: bool = True
    # Send DNS through Tor, not a public resolver.
    dns_over_tor: bool = True
    # Overwrite RAM on shutdown to defeat cold-boot attacks.
    wipe_memory_on_shutdown: bool = True
    # Keep the clock in UTC (a local timezone is a fingerprint).
    timezone_utc: bool = True
    # Optional upstream proxy, e.g. socks5://127.0.0.1:9050
    proxy: str = ""
    # Run Whonix Gateway + Workstation VMs for compartmentalization.
    whonix_enabled: bool = False
    # Tor ports.
    tor_socks_port: int = 9050
    tor_trans_port: int = 9040
    tor_dns_port: int = 5353
    tor_control_port: int = 9051
    # Optional Tor control password (HashedControlPassword). Empty means no auth.
    tor_control_password: str = ""
    # Panic action: "poweroff" | "halt" | "reboot" | "network"
    panic_action: str = "poweroff"


@dataclass
class LearningConfig:
    """Controls the accumulating local knowledge base."""
    enabled: bool = True
    # Record every successful command as a reusable experience.
    autosave_commands: bool = False
    # Record a task outcome when the agent finishes a multi-step request.
    autosave_successes: bool = True
    # How many learned items to fold into the prompt each turn.
    max_context_items: int = 5
    snippet_file: str = field(default_factory=lambda: _data_path("snippets.jsonl"))
    experience_file: str = field(default_factory=lambda: _data_path("experiences.jsonl"))


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    interface: InterfaceConfig = field(default_factory=InterfaceConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    source: Optional[str] = None  # path the config was loaded from

    # -- construction -----------------------------------------------------
    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        cfg = cls()
        candidates = []
        if path:
            candidates.append(Path(path).expanduser())
        candidates += [
            Path(os.environ.get("AEGIS_CONFIG", "")).expanduser()
            if os.environ.get("AEGIS_CONFIG")
            else None,
            Path(_config_path("config.toml")),
            Path("/etc/aegis/config.toml"),
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                cfg._merge_file(candidate)
                cfg.source = str(candidate)
                break
        cfg._merge_env()
        cfg.validate()
        return cfg

    def _merge_file(self, path: Path) -> None:
        if not _HAS_TOML:
            return
        try:
            with path.open("rb") as fh:
                data = _toml.load(fh)
        except Exception:
            return
        self._apply(data)

    def _merge_env(self) -> None:
        env = os.environ
        if env.get("AEGIS_MODE"):
            self.safety.mode = env["AEGIS_MODE"]
        if env.get("AEGIS_OLLAMA_MODEL"):
            self.model.ollama_model = env["AEGIS_OLLAMA_MODEL"]
        if env.get("AEGIS_OLLAMA_HOST"):
            self.model.ollama_host = env["AEGIS_OLLAMA_HOST"]
        if env.get("AEGIS_AUTHORIZED_TARGETS"):
            self.safety.authorized_targets = [
                t.strip() for t in env["AEGIS_AUTHORIZED_TARGETS"].split(",") if t.strip()
            ]
        if env.get("AEGIS_WORKSPACE"):
            self.safety.workspace_root = env["AEGIS_WORKSPACE"]
        if env.get("AEGIS_ALLOW_SUDO"):
            self.safety.allow_sudo = env["AEGIS_ALLOW_SUDO"].lower() in ("1", "true", "yes")
        if env.get("AEGIS_AMNESIC"):
            self.privacy.amnesic = env["AEGIS_AMNESIC"].lower() in ("1", "true", "yes")
        if env.get("AEGIS_FORCE_TOR"):
            self.privacy.force_tor = env["AEGIS_FORCE_TOR"].lower() in ("1", "true", "yes")
        if env.get("AEGIS_PROXY"):
            self.privacy.proxy = env["AEGIS_PROXY"]
        if env.get("AEGIS_LEARNING"):
            self.learning.enabled = env["AEGIS_LEARNING"].lower() in ("1", "true", "yes")

    def _apply(self, data: Dict[str, Any]) -> None:
        for section, obj in (
            ("model", self.model),
            ("safety", self.safety),
            ("interface", self.interface),
            ("privacy", self.privacy),
            ("learning", self.learning),
        ):
            values = data.get(section, {})
            if not isinstance(values, dict):
                continue
            for key, val in values.items():
                if hasattr(obj, key):
                    setattr(obj, key, val)

    # -- validation -------------------------------------------------------
    def validate(self) -> None:
        if self.safety.mode not in VALID_MODES:
            self.safety.mode = "auto_safe"
        self.safety.workspace_root = os.path.expanduser(self.safety.workspace_root)
        self.interface.audit_log = os.path.expanduser(self.interface.audit_log)
        self.interface.history_file = os.path.expanduser(self.interface.history_file)
        self.learning.snippet_file = os.path.expanduser(self.learning.snippet_file)
        self.learning.experience_file = os.path.expanduser(self.learning.experience_file)
        if self.model.max_tool_rounds < 1:
            self.model.max_tool_rounds = 1
        if self.learning.max_context_items < 0:
            self.learning.max_context_items = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": asdict(self.model),
            "safety": asdict(self.safety),
            "interface": asdict(self.interface),
            "privacy": asdict(self.privacy),
            "learning": asdict(self.learning),
            "source": self.source,
        }

    def describe(self) -> str:
        flags = []
        if self.privacy.amnesic:
            flags.append("amnesic")
        if self.privacy.force_tor:
            flags.append("tor")
        privacy = ("  privacy=" + "+".join(flags)) if flags else ""
        learn = "  learning=on" if self.learning.enabled else "  learning=off"
        return (
            f"mode={self.safety.mode}  backend={self.model.backends[0]}  "
            f"model={self.model.ollama_model}  workspace={self.safety.workspace_root}  "
            f"targets={self.safety.authorized_targets or 'none declared'}{privacy}{learn}"
        )
