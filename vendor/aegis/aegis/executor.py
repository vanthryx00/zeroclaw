"""Command execution with safety classification and audit logging.

The executor is the only place in Aegis that actually spawns a shell. Every
request flows through :mod:`aegis.safety`, is decided against the configured
mode, optionally confirmed by the user, then logged.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from .audit import AuditLog
from .approval import ApprovalOutcome, coerce_outcome
from . import safety
from . import platform as aegis_platform
from .safety import Level, Verdict


@dataclass
class ExecutionResult:
    command: str
    ran: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration: float
    verdict: Verdict
    # "auto", "confirmed", "allowlisted", "denied", "blocked", "dry-run"
    decision: str


# Callback signature: (verdict, command) -> bool | ApprovalOutcome
ConfirmFn = Callable[[Verdict, str], object]


class Executor:
    def __init__(self, cfg, confirm: Optional[ConfirmFn] = None, allowlist=None):
        self.cfg = cfg
        self.confirm = confirm
        self.audit = AuditLog(cfg.interface.audit_log)
        self.allowlist = allowlist

    # ------------------------------------------------------------------
    def run(self, command: str, *, confirmed: bool = False) -> ExecutionResult:
        cfg = self.cfg
        verdict = safety.classify(command, cfg)
        mode = cfg.safety.mode

        # Hard block.
        if verdict.level == Level.BLOCKED:
            self.audit.record(
                event="execute", command=command, level=verdict.label, mode=mode,
                decision="blocked", reason=verdict.reason,
            )
            return ExecutionResult(command, False, None, "", verdict.reason, 0.0,
                                   verdict, "blocked")

        # Dry run never executes.
        if mode == "dry_run":
            self.audit.record(
                event="execute", command=command, level=verdict.label, mode=mode,
                decision="dry-run", reason=verdict.reason,
            )
            return ExecutionResult(command, False, None, "", "dry-run: not executed",
                                   0.0, verdict, "dry-run")

        auto = safety.decide(verdict, mode)
        rule = None
        if auto and not confirmed:
            decision = "auto"
        elif confirmed:
            decision = "confirmed"
        else:
            # A standing authorisation is checked *before* prompting, so a
            # command the user already blessed runs without asking again.
            if self.allowlist is not None:
                rule = self.allowlist.find(command, verdict.level)
            if rule is not None:
                decision = "allowlisted"
            else:
                # Need interactive confirmation.
                if self.confirm is None:
                    self.audit.record(
                        event="execute", command=command, level=verdict.label,
                        mode=mode, decision="denied",
                        reason="no confirmation handler; " + verdict.reason,
                    )
                    return ExecutionResult(command, False, None, "",
                                           "denied: confirmation required", 0.0,
                                           verdict, "denied")
                outcome = coerce_outcome(self.confirm(verdict, command))
                if outcome is ApprovalOutcome.DENY:
                    self.audit.record(
                        event="execute", command=command, level=verdict.label,
                        mode=mode, decision="denied", reason=verdict.reason,
                    )
                    return ExecutionResult(command, False, None, "",
                                           "denied by user", 0.0,
                                           verdict, "denied")
                if outcome is ApprovalOutcome.ALLOW_ALWAYS:
                    # Only reached by an explicit choice. A level that may not
                    # be remembered is simply not stored; the command still runs.
                    if self.allowlist is not None:
                        self.allowlist.add(command, verdict.level)
                decision = "confirmed"

        if rule is not None and self.allowlist is not None:
            self.allowlist.record_hit(rule.id)

        # sudo gate.
        if "sudo" in command.split() and not cfg.safety.allow_sudo:
            msg = "sudo is disabled (set safety.allow_sudo=true to enable)"
            self.audit.record(
                event="execute", command=command, level=verdict.label, mode=mode,
                decision="denied", reason=msg,
            )
            return ExecutionResult(command, False, None, "", msg, 0.0, verdict, "denied")

        return self._spawn(command, verdict, decision)

    # ------------------------------------------------------------------
    def _spawn(self, command: str, verdict: Verdict, decision: str) -> ExecutionResult:
        start = time.time()
        try:
            # Run through the native shell (sh on POSIX, PowerShell/cmd on
            # Windows) without shell=True, so the command string is passed
            # exactly once and quoting is predictable.
            argv = aegis_platform.shell_argv(command)
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.cfg.safety.command_timeout,
                cwd=self.cfg.safety.workspace_root
                if os.path.isdir(self.cfg.safety.workspace_root)
                else None,
            )
            duration = time.time() - start
            self.audit.record(
                event="execute", command=command, level=verdict.label,
                mode=self.cfg.safety.mode, decision=decision, reason=verdict.reason,
                exit_code=proc.returncode, duration=duration,
                output_preview=(proc.stdout or "") + (proc.stderr or ""),
            )
            return ExecutionResult(command, True, proc.returncode, proc.stdout,
                                   proc.stderr, duration, verdict, decision)
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            self.audit.record(
                event="execute", command=command, level=verdict.label,
                mode=self.cfg.safety.mode, decision=decision,
                reason="timeout after %.0fs" % self.cfg.safety.command_timeout,
                exit_code=None, duration=duration, output_preview=out,
            )
            return ExecutionResult(command, True, None, out,
                                   f"timeout after {self.cfg.safety.command_timeout:.0f}s",
                                   duration, verdict, decision)
        except OSError as exc:
            duration = time.time() - start
            self.audit.record(
                event="execute", command=command, level=verdict.label,
                mode=self.cfg.safety.mode, decision=decision, reason=str(exc),
                exit_code=None, duration=duration,
            )
            return ExecutionResult(command, True, None, "", str(exc), duration,
                                   verdict, decision)

    # ------------------------------------------------------------------
    def preview(self, command: str) -> Verdict:
        return safety.classify(command, self.cfg)
