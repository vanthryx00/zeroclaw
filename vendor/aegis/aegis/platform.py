"""Cross-platform detection and path helpers.

Aegis is meant to run on Linux, macOS, and Windows. This module centralises
every place that would otherwise hard-code a POSIX assumption: OS detection,
shell selection, and the config/data directories.
"""

from __future__ import annotations

import os
import platform as _pyplatform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class PlatformInfo:
    system: str          # "Linux" | "Darwin" | "Windows"
    release: str
    machine: str
    python: str
    shell: str
    package_managers: List[str] = field(default_factory=list)

    @property
    def is_windows(self) -> bool:
        return self.system == "Windows"

    @property
    def is_macos(self) -> bool:
        return self.system == "Darwin"

    @property
    def is_linux(self) -> bool:
        return self.system == "Linux"

    @property
    def family(self) -> str:
        if self.is_windows:
            return "windows"
        if self.is_macos:
            return "macos"
        return "linux"

    def summary(self) -> str:
        return (
            f"{self.system} {self.release} ({self.machine}), "
            f"shell={self.shell}, python={self.python}"
        )


def detect() -> PlatformInfo:
    system = _pyplatform.system()
    shell = _default_shell(system)
    return PlatformInfo(
        system=system,
        release=_pyplatform.release(),
        machine=_pyplatform.machine(),
        python=_pyplatform.python_version(),
        shell=shell,
        package_managers=_package_managers(system),
    )


def _default_shell(system: str) -> str:
    if system == "Windows":
        if shutil.which("pwsh"):
            return "pwsh"
        if shutil.which("powershell"):
            return "powershell"
        return "cmd"
    return os.environ.get("SHELL") or "sh"


def _package_managers(system: str) -> List[str]:
    if system == "Darwin":
        candidates = ["brew", "port", "mas"]
    elif system == "Windows":
        candidates = ["winget", "choco", "scoop"]
    else:
        candidates = ["apt", "dnf", "pacman", "zypper", "apk", "snap", "flatpak"]
    return [c for c in candidates if shutil.which(c)]


# --------------------------------------------------------------------------
# Directories
# --------------------------------------------------------------------------

def _home() -> Path:
    return Path.home()


def config_dir(app: str = "aegis") -> Path:
    system = _pyplatform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(_home() / "AppData" / "Roaming")
        return Path(base) / app
    if system == "Darwin":
        return _home() / "Library" / "Application Support" / app
    base = os.environ.get("XDG_CONFIG_HOME") or str(_home() / ".config")
    return Path(base) / app


def data_dir(app: str = "aegis") -> Path:
    system = _pyplatform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(_home() / "AppData" / "Local")
        return Path(base) / app
    if system == "Darwin":
        return _home() / "Library" / "Application Support" / app
    base = os.environ.get("XDG_DATA_HOME") or str(_home() / ".local" / "share")
    return Path(base) / app


# --------------------------------------------------------------------------
# Shell invocation
# --------------------------------------------------------------------------

def shell_argv(command: str) -> List[str]:
    """Return the argv used to run *command* through the native shell."""
    system = _pyplatform.system()
    if system == "Windows":
        if shutil.which("pwsh"):
            return ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command]
        if shutil.which("powershell"):
            return ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        return ["cmd", "/c", command]
    shell = os.environ.get("SHELL") or "/bin/sh"
    return [shell, "-c", command]


def is_windows() -> bool:
    return _pyplatform.system() == "Windows"


def path_sep() -> str:
    return "\\" if is_windows() else "/"
