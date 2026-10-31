"""Hands: desktop GUI control primitives and the audited GuiExecutor.

This module is the GUI counterpart of :mod:`aegis.executor`. GUI actions
are expressed as descriptor strings — ``gui:click 500,300``,
``gui:type <text>``, ``gui:screenshot`` — and flow through the exact same
gates as shell commands: :func:`aegis.safety.classify` → :func:`aegis.safety.decide`
→ optional operator confirmation → execute → audit log.

Two safety details specific to GUI actions:

* Typed text is **redacted in the audit log**. ``gui:type`` can carry
  passwords and other secrets; the audit records ``gui:type <redacted>``
  instead of the text. (The operator still sees the full text in the
  confirmation prompt, so they can verify what is about to be typed.)
* ``pyautogui`` is an optional dependency, imported lazily. Importing this
  module never fails because it is missing; calling a primitive without it
  raises :class:`DesktopError` with the install command.

NOTE: this is not ``aegis.gui`` — that module is the PySide6 chat
front-end. This module is the agent's hands.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from .approval import ApprovalOutcome, coerce_outcome
from .audit import AuditLog
from . import safety
from .executor import ExecutionResult
from .safety import Level, Verdict

# Callback signature: (verdict, descriptor) -> bool | ApprovalOutcome
ConfirmFn = Callable[[Verdict, str], object]


class DesktopError(RuntimeError):
    """Raised when a GUI action cannot run (missing dep, bad descriptor)."""


# --------------------------------------------------------------------------
# Lazy pyautogui
# --------------------------------------------------------------------------

_pyautogui = None


def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None:
        try:
            import pyautogui as pag
        except ModuleNotFoundError as exc:
            raise DesktopError(
                "pyautogui is not installed — run: pip install pyautogui"
            ) from exc
        _pyautogui = pag
    return _pyautogui


# --------------------------------------------------------------------------
# Primitives (thin wrappers — one pyautogui call each, no policy here)
# --------------------------------------------------------------------------

def screen_size() -> Tuple[int, int]:
    """Return ``(width, height)`` of the primary monitor in pixels."""
    w, h = _get_pyautogui().size()
    return int(w), int(h)


def move_to(x: int, y: int) -> None:
    _get_pyautogui().moveTo(int(x), int(y))


def click(x: int, y: int) -> None:
    _get_pyautogui().click(int(x), int(y))


def double_click(x: int, y: int) -> None:
    _get_pyautogui().doubleClick(int(x), int(y))


def right_click(x: int, y: int) -> None:
    _get_pyautogui().rightClick(int(x), int(y))


def type_text(text: str) -> None:
    _get_pyautogui().typewrite(str(text), interval=0.01)


def press(key: str) -> None:
    _get_pyautogui().press(str(key))


def hotkey(*keys: str) -> None:
    _get_pyautogui().hotkey(*[str(k) for k in keys])


def scroll(amount: int) -> None:
    _get_pyautogui().scroll(int(amount))


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    pag = _get_pyautogui()
    pag.moveTo(int(x1), int(y1))
    pag.dragTo(int(x2), int(y2), duration=0.3)


# --------------------------------------------------------------------------
# Descriptor parsing
# --------------------------------------------------------------------------

#: Verbs a ``gui:`` descriptor may carry.
GUI_VERBS = (
    "screenshot", "move_to", "click", "double_click", "right_click",
    "type", "key", "hotkey", "scroll", "drag", "size",
)

_COORD_RE = re.compile(r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*$")


def parse_action(descriptor: str) -> Tuple[str, str]:
    """Parse ``gui:<verb> <args>`` into ``(verb, args)``.

    Raises :class:`DesktopError` for a missing ``gui:`` prefix, an empty
    action, or an unknown verb — callers treat that as a denial, never as
    permission to guess.
    """
    text = (descriptor or "").strip()
    if not text.startswith("gui:"):
        raise DesktopError(f"GUI action must start with 'gui:': {descriptor!r}")
    rest = text[4:].strip()
    if not rest:
        raise DesktopError("empty GUI action")
    parts = rest.split(None, 1)
    verb = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    if verb not in GUI_VERBS:
        raise DesktopError(f"unknown GUI action {verb!r}")
    return verb, args


def parse_coords(args: str) -> Tuple[int, int]:
    """Parse ``x,y`` pixel coordinates. Raises :class:`DesktopError`."""
    match = _COORD_RE.match(args or "")
    if not match:
        raise DesktopError(f"expected coordinates like '500,300', got {args!r}")
    return int(match.group(1)), int(match.group(2))


def audit_action(descriptor: str) -> str:
    """The audit-log form of a descriptor — typed text is redacted."""
    try:
        verb, _args = parse_action(descriptor)
    except DesktopError:
        return descriptor
    if verb == "type":
        return "gui:type <redacted>"
    return descriptor


# --------------------------------------------------------------------------
# GuiExecutor — same gates as Executor, for GUI actions
# --------------------------------------------------------------------------

class GuiExecutor:
    """Run one GUI action through classify → decide → confirm → audit."""

    def __init__(self, cfg, confirm: Optional[ConfirmFn] = None, allowlist=None):
        self.cfg = cfg
        self.confirm = confirm
        self.audit = AuditLog(cfg.interface.audit_log)
        self.allowlist = allowlist

    # ------------------------------------------------------------------
    def run(self, descriptor: str, *, confirmed: bool = False,
            confirm: Optional[ConfirmFn] = None) -> ExecutionResult:
        """Execute one ``gui:`` descriptor, mirroring :meth:`Executor.run`.

        Returns an :class:`~aegis.executor.ExecutionResult` so agent-loop
        code treats GUI and shell actions uniformly. ``confirm`` overrides
        the executor's confirm handler for this call (the agent passes the
        shell executor's handler so front-ends wire both the same way).
        """
        cfg = self.cfg
        verdict = safety.classify(descriptor, cfg)
        mode = cfg.safety.mode
        confirm_fn = confirm if confirm is not None else self.confirm

        # Hard block.
        if verdict.level == Level.BLOCKED:
            self.audit.record(
                event="gui", action=audit_action(descriptor),
                level=verdict.label, mode=mode,
                decision="blocked", reason=verdict.reason,
            )
            return ExecutionResult(descriptor, False, None, "", verdict.reason,
                                   0.0, verdict, "blocked")

        # Dry run never executes.
        if mode == "dry_run":
            self.audit.record(
                event="gui", action=audit_action(descriptor),
                level=verdict.label, mode=mode,
                decision="dry-run", reason=verdict.reason,
            )
            return ExecutionResult(descriptor, False, None, "",
                                   "dry-run: not executed", 0.0, verdict, "dry-run")

        auto = safety.decide(verdict, mode)
        rule = None
        if auto and not confirmed:
            decision = "auto"
        elif confirmed:
            decision = "confirmed"
        else:
            # A standing authorisation is checked *before* prompting, same as
            # shell commands.
            if self.allowlist is not None:
                rule = self.allowlist.find(descriptor, verdict.level)
            if rule is not None:
                decision = "allowlisted"
            else:
                if confirm_fn is None:
                    self.audit.record(
                        event="gui", action=audit_action(descriptor),
                        level=verdict.label, mode=mode, decision="denied",
                        reason="no confirmation handler; " + verdict.reason,
                    )
                    return ExecutionResult(descriptor, False, None, "",
                                           "denied: confirmation required",
                                           0.0, verdict, "denied")
                outcome = coerce_outcome(confirm_fn(verdict, descriptor))
                if outcome is ApprovalOutcome.DENY:
                    self.audit.record(
                        event="gui", action=audit_action(descriptor),
                        level=verdict.label, mode=mode, decision="denied",
                        reason=verdict.reason,
                    )
                    return ExecutionResult(descriptor, False, None, "",
                                           "denied by user", 0.0,
                                           verdict, "denied")
                if outcome is ApprovalOutcome.ALLOW_ALWAYS:
                    if self.allowlist is not None:
                        self.allowlist.add(descriptor, verdict.level)
                decision = "confirmed"

        if rule is not None and self.allowlist is not None:
            self.allowlist.record_hit(rule.id)

        return self._dispatch(descriptor, verdict, decision)

    # ------------------------------------------------------------------
    def _dispatch(self, descriptor: str, verdict: Verdict,
                  decision: str) -> ExecutionResult:
        start = time.time()
        try:
            verb, args = parse_action(descriptor)
        except DesktopError as exc:
            duration = time.time() - start
            self.audit.record(
                event="gui", action=audit_action(descriptor),
                level=verdict.label, mode=self.cfg.safety.mode,
                decision="denied", reason=str(exc),
            )
            return ExecutionResult(descriptor, False, None, "", str(exc),
                                   duration, verdict, "denied")
        try:
            detail = self._execute_verb(verb, args)
        except DesktopError as exc:
            duration = time.time() - start
            self.audit.record(
                event="gui", action=audit_action(descriptor),
                level=verdict.label, mode=self.cfg.safety.mode,
                decision="error", reason=str(exc), duration=duration,
            )
            return ExecutionResult(descriptor, False, None, "", str(exc),
                                   duration, verdict, "error")
        except Exception as exc:  # pyautogui failures (no display, etc.)
            duration = time.time() - start
            detail_err = f"{type(exc).__name__}: {exc}"
            self.audit.record(
                event="gui", action=audit_action(descriptor),
                level=verdict.label, mode=self.cfg.safety.mode,
                decision="error", reason=detail_err, duration=duration,
            )
            return ExecutionResult(descriptor, False, None, "", detail_err,
                                   duration, verdict, "error")

        duration = time.time() - start
        self.audit.record(
            event="gui", action=audit_action(descriptor),
            level=verdict.label, mode=self.cfg.safety.mode,
            decision=decision, reason=verdict.reason,
            duration=duration, detail=detail,
        )
        return ExecutionResult(descriptor, True, 0, detail, "",
                               duration, verdict, decision)

    # ------------------------------------------------------------------
    def _execute_verb(self, verb: str, args: str) -> str:
        """Run one parsed verb. Returns a human-readable detail string.

        Never logs typed text: callers use :func:`audit_action` for the log.
        """
        if verb == "screenshot":
            from . import screen as screen_mod

            path = screen_mod.default_screenshot_path()
            screen_mod.capture(path)
            return f"screenshot saved to {path}"
        if verb == "size":
            w, h = screen_size()
            return f"screen is {w}x{h}"
        if verb == "move_to":
            x, y = parse_coords(args)
            move_to(x, y)
            return f"moved to {x},{y}"
        if verb == "click":
            x, y = parse_coords(args)
            click(x, y)
            return f"clicked {x},{y}"
        if verb == "double_click":
            x, y = parse_coords(args)
            double_click(x, y)
            return f"double-clicked {x},{y}"
        if verb == "right_click":
            x, y = parse_coords(args)
            right_click(x, y)
            return f"right-clicked {x},{y}"
        if verb == "type":
            type_text(args)
            return f"typed {len(args)} characters"
        if verb == "key":
            key = args.strip()
            if not key:
                raise DesktopError("gui:key needs a key name, e.g. 'gui:key enter'")
            press(key)
            return f"pressed {key}"
        if verb == "hotkey":
            keys = [k for k in re.split(r"[\s+]+", args.strip()) if k]
            if not keys:
                raise DesktopError(
                    "gui:hotkey needs keys, e.g. 'gui:hotkey ctrl+c'")
            hotkey(*keys)
            return "hotkey " + "+".join(keys)
        if verb == "scroll":
            try:
                amount = int(args.strip())
            except ValueError as exc:
                raise DesktopError(
                    f"gui:scroll needs an integer amount, got {args!r}"
                ) from exc
            scroll(amount)
            return f"scrolled {amount}"
        if verb == "drag":
            parts = args.split()
            if len(parts) != 2:
                raise DesktopError(
                    "gui:drag needs two coordinate pairs, "
                    "e.g. 'gui:drag 100,200 300,400'"
                )
            x1, y1 = parse_coords(parts[0])
            x2, y2 = parse_coords(parts[1])
            drag(x1, y1, x2, y2)
            return f"dragged {x1},{y1} -> {x2},{y2}"
        raise DesktopError(f"unknown GUI action {verb!r}")  # unreachable

    # ------------------------------------------------------------------
    def preview(self, descriptor: str) -> Verdict:
        return safety.classify(descriptor, self.cfg)
