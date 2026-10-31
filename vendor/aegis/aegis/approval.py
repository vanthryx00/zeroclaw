"""Thread-safe handoff between a worker-thread confirmation and the UI.

The Executor calls its ``confirm`` callback while the agent is generating, which
in the TUI and GUI happens on a **worker thread**. But a prompt can only be
drawn on the **UI thread**. This module is the bridge:

    worker thread                     UI thread
    -------------                     ---------
    gate.ask(verdict, cmd)  ──┐
       (blocks on Event)      │  on_request(req) ──▶  show modal / prompt
                              │                            │
       returns True/False  ◀──┘  gate.resolve(bool) ◀──────┘

Two properties matter for safety:

* **Deny by default.** If nothing answers, if the window closes, or if the
  request times out, the answer is ``False``. A hang must never turn into an
  accidental approval.
* **One request at a time.** Only one command is ever pending, so a stray
  ``resolve`` cannot approve a command the user never saw.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from .allowlist import is_rememberable

#: How long a worker waits for an answer before giving up and denying.
DEFAULT_TIMEOUT = 300.0

APPROVE_WORDS = {"y", "yes", "approve", "approved", "run", "ok", "allow"}
#: Answers that mean "and remember this command from now on".
ALWAYS_WORDS = {"a", "always", "all", "remember", "remember-this", "always-allow"}


class ApprovalOutcome(str, Enum):
    """What the user decided about a command.

    ``ALLOW_ALWAYS`` is a standing authorisation and is only ever produced by
    an explicit choice; nothing defaults to it.
    """

    DENY = "deny"
    ALLOW = "allow"
    ALLOW_ALWAYS = "allow_always"

    @property
    def approved(self) -> bool:
        return self is not ApprovalOutcome.DENY


def coerce_outcome(value) -> ApprovalOutcome:
    """Normalise a confirm-callback return value.

    A plain ``True``/``False`` still works, so third-party callbacks keep
    functioning; anything unrecognised denies.
    """
    if isinstance(value, ApprovalOutcome):
        return value
    if value is True:
        return ApprovalOutcome.ALLOW
    if value is False or value is None:
        return ApprovalOutcome.DENY
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ALWAYS_WORDS:
            return ApprovalOutcome.ALLOW_ALWAYS
        if text in APPROVE_WORDS:
            return ApprovalOutcome.ALLOW
    return ApprovalOutcome.DENY


@dataclass
class ApprovalRequest:
    """What the UI needs in order to ask the user."""

    command: str
    level: str
    reason: str
    #: False for levels that may never become a standing rule (offensive,
    #: blocked) — the UI must not offer "always allow" for those.
    rememberable: bool = True

    def prompt(self) -> str:
        return (f"command ({self.level}): {self.command}\n"
                f"  reason: {self.reason}")


class ApprovalGate:
    """Blocks a worker thread until the UI answers, or the timeout expires."""

    def __init__(self, on_request: Optional[Callable[[ApprovalRequest], None]] = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self.on_request = on_request
        self.timeout = timeout
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._answer = ApprovalOutcome.DENY
        self._request: Optional[ApprovalRequest] = None
        self._cancelled = False

    # -- worker side ----------------------------------------------------
    @property
    def pending(self) -> bool:
        with self._lock:
            return self._request is not None

    @property
    def request(self) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._request

    def ask(self, verdict, command: str) -> ApprovalOutcome:
        """Executor confirm callback. Blocks the calling (worker) thread."""
        level = getattr(verdict, "level", None)
        req = ApprovalRequest(
            command=command,
            level=getattr(verdict, "label", str(verdict)),
            reason=getattr(verdict, "reason", ""),
            rememberable=is_rememberable(level) if level is not None else False,
        )
        with self._lock:
            if self._cancelled:
                return ApprovalOutcome.DENY
            self._request = req
            self._answer = ApprovalOutcome.DENY
            self._event.clear()

        notify = self.on_request
        if notify is None:
            with self._lock:
                self._request = None
            return ApprovalOutcome.DENY
        try:
            notify(req)
        except Exception:
            # A UI that cannot be reached must never mean "approved".
            with self._lock:
                self._request = None
            return ApprovalOutcome.DENY

        if not self._event.wait(self.timeout):
            with self._lock:
                self._request = None
            return ApprovalOutcome.DENY  # timeout denies

        with self._lock:
            answer = self._answer
            self._request = None
        return answer

    # -- UI side --------------------------------------------------------
    def resolve(self, approved: bool) -> bool:
        """Answer the pending request yes/no. False if none was pending."""
        return self.resolve_outcome(
            ApprovalOutcome.ALLOW if approved else ApprovalOutcome.DENY)

    def resolve_outcome(self, outcome: ApprovalOutcome) -> bool:
        """Answer the pending request. Returns False if none was pending."""
        outcome = coerce_outcome(outcome)
        with self._lock:
            if self._request is None:
                return False
            self._answer = outcome
        self._event.set()
        return True

    def cancel(self) -> None:
        """Unblock any waiter and deny from now on (window closing)."""
        with self._lock:
            self._cancelled = True
            self._answer = ApprovalOutcome.DENY
            self._request = None
        self._event.set()

    def reset(self) -> None:
        """Re-arm after a cancel, so a later turn can prompt again."""
        with self._lock:
            self._cancelled = False
            self._answer = ApprovalOutcome.DENY
            self._request = None
        self._event.clear()


def is_approval(text: str) -> bool:
    """Interpret a typed answer. Anything unrecognised denies."""
    return text.strip().lower() in APPROVE_WORDS


def parse_answer(text: str) -> ApprovalOutcome:
    """Interpret a typed answer. Anything unrecognised denies.

    'a'/'always' is the standing authorisation; it is never the default, so it
    has to be typed on purpose.
    """
    word = text.strip().lower()
    if word in ALWAYS_WORDS:
        return ApprovalOutcome.ALLOW_ALWAYS
    if word in APPROVE_WORDS:
        return ApprovalOutcome.ALLOW
    return ApprovalOutcome.DENY
