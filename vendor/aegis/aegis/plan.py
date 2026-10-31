"""Whole-plan approval (#47).

Generalizes the rescue module's detect -> plan -> execute pattern to the
agent: the model may emit a single ```aegis-plan fenced block describing an
ordered list of steps. Nothing runs until the operator approves the whole
plan exactly once.

Plan format (inside the fence — one step per ``## <kind>`` header)::

    ```aegis-plan
    ## command
    ls /tmp
    ## file path=notes/todo.txt
    buy milk
    ## snippet title="greet" lang=python tags=demo
    print("hi")
    ## remember tags=workflow
    check disk space before installs
    ```

Safety properties:

* every step is classified at parse time (commands go through
  :func:`aegis.safety.classify`; file/snippet/remember steps are local,
  workspace-confined writes; gui steps are classified as ``gui:`` actions);
* approval never bypasses BLOCKED — the executor hard-blocks those steps and
  the plan halts there;
* fail-closed: unparseable plans, empty plans, unknown step kinds, text
  outside any step, and steps missing required attributes are refused before
  anything runs;
* a denied plan runs nothing at all;
* plans are capped at ``MAX_PLAN_STEPS`` steps.

Step bodies must not contain triple backticks (the fence would terminate
early); a line starting with ``## `` followed by one of the four step kinds
always starts a new step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .safety import LEVEL_LABEL, Level, Verdict, classify

#: Fence the model emits to propose a plan. Non-greedy so the first closing
#: fence ends the block.
PLAN_FENCE_RE = re.compile(r"```aegis-plan\s*\n(.*?)```", re.DOTALL)

#: A step header line: ``## <kind>`` plus optional ``key=value`` attributes.
_STEP_RE = re.compile(r"^##\s+(command|file|snippet|remember|gui|screenshot)\b(.*)$")

_ATTR_RE = re.compile(r"(\w+)=(\"[^\"]*\"|'[^']*'|\S+)")

_STEP_KINDS = ("command", "file", "snippet", "remember", "gui", "screenshot")

#: Hard cap — a plan longer than this is refused, not truncated.
MAX_PLAN_STEPS = 20

# Callback signature: (plan) -> bool. Any exception or ambiguity denies.
PlanConfirmFn = Callable[["Plan"], bool]


class PlanError(ValueError):
    """Raised when a proposed plan cannot be parsed or is unsafe to accept."""


def _parse_attrs(raw: str) -> dict:
    out = {}
    for key, val in _ATTR_RE.findall(raw or ""):
        out[key.lower()] = val.strip("\"'")
    return out


@dataclass
class PlanStep:
    """One step of a plan, classified at parse time."""

    kind: str  # "command" | "file" | "snippet" | "remember" | "gui" | "screenshot"
    content: str
    attrs: Dict[str, str] = field(default_factory=dict)
    level: Level = Level.READ_ONLY
    reason: str = ""

    @property
    def label(self) -> str:
        return LEVEL_LABEL[self.level]

    def headline(self) -> str:
        """One-line human summary used by render() and the audit log."""
        if self.kind in ("command", "gui", "remember"):
            one_line = " ".join(self.content.split())
            return one_line if len(one_line) <= 80 else one_line[:77] + "..."
        if self.kind == "screenshot":
            return "screenshot"
        if self.kind == "file":
            path = self.attrs.get("path", "?")
            return f"{path} ({len(self.content.encode('utf-8'))} bytes)"
        if self.kind == "snippet":
            title = self.attrs.get("title", "snippet")
            lang = self.attrs.get("lang", "")
            return f'"{title}"' + (f" [{lang}]" if lang else "")
        if self.kind == "remember":
            one_line = " ".join(self.content.split())
            return one_line if len(one_line) <= 80 else one_line[:77] + "..."
        return self.kind

    def describe(self) -> dict:
        """Compact dict for the audit log (bodies are previewed, not dumped)."""
        preview = self.content[:200]
        return {
            "kind": self.kind,
            "level": self.label,
            "reason": self.reason,
            "attrs": self.attrs,
            "headline": self.headline(),
            "content_preview": preview,
        }


@dataclass
class Plan:
    """An ordered, classified, operator-approved-or-not list of steps."""

    steps: List[PlanStep] = field(default_factory=list)

    # ------------------------------------------------------------------
    @classmethod
    def parse(cls, body: str, cfg) -> "Plan":
        """Parse a plan body into classified steps. Raises PlanError."""
        steps: List[PlanStep] = []
        cur_kind: Optional[str] = None
        cur_attrs: Dict[str, str] = {}
        cur_lines: List[str] = []

        def flush() -> None:
            if cur_kind is None:
                return
            content = "\n".join(cur_lines).strip("\n")
            steps.append(cls._make_step(cur_kind, cur_attrs, content, cfg))

        for lineno, line in enumerate(body.splitlines(), start=1):
            match = _STEP_RE.match(line)
            if match:
                flush()
                cur_kind = match.group(1)
                cur_attrs = _parse_attrs(match.group(2))
                cur_lines = []
                continue
            if line.startswith("## "):
                # Looks like a step header but the kind is unknown — refuse,
                # never silently skip.
                raise PlanError(
                    f"line {lineno}: unknown step {line.strip()!r}; "
                    f"steps must be one of: {', '.join(_STEP_KINDS)}"
                )
            if cur_kind is None:
                if not line.strip():
                    continue
                raise PlanError(
                    f"line {lineno}: text outside any step "
                    f"({line.strip()[:60]!r}); every step must start with "
                    "'## <kind>'"
                )
            cur_lines.append(line)
        flush()

        if not steps:
            raise PlanError("plan has no steps")
        if len(steps) > MAX_PLAN_STEPS:
            raise PlanError(
                f"plan has {len(steps)} steps, over the limit of "
                f"{MAX_PLAN_STEPS}; split it into smaller plans"
            )
        return cls(steps)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_step(kind: str, attrs: Dict[str, str], content: str,
                   cfg) -> PlanStep:
        if kind == "command":
            text = content.strip()
            if not text:
                raise PlanError("a '## command' step has an empty command")
            verdict = classify(text, cfg)
            return PlanStep(kind=kind, content=text, attrs=attrs,
                            level=verdict.level, reason=verdict.reason)
        if kind == "file":
            path = attrs.get("path", "")
            if not path:
                raise PlanError("a '## file' step needs path=<relative path>")
            return PlanStep(kind=kind, content=content, attrs=attrs,
                            level=Level.SAFE_WRITE,
                            reason="workspace-confined file write")
        if kind == "snippet":
            return PlanStep(kind=kind, content=content, attrs=attrs,
                            level=Level.SAFE_WRITE,
                            reason="local snippet-library write")
        if kind == "remember":
            if not content.strip():
                raise PlanError("a '## remember' step has empty content")
            return PlanStep(kind=kind, content=content.strip(), attrs=attrs,
                            level=Level.SAFE_WRITE,
                            reason="local lesson-store write")
        if kind == "gui":
            text = content.strip()
            if not text:
                raise PlanError("a '## gui' step has an empty action")
            if not text.startswith("gui:"):
                raise PlanError(
                    "a '## gui' step must start with 'gui:', "
                    "e.g. '## gui' + 'gui:click 500,300'")
            verdict = classify(text, cfg)
            return PlanStep(kind=kind, content=text, attrs=attrs,
                            level=verdict.level, reason=verdict.reason)
        if kind == "screenshot":
            return PlanStep(kind=kind, content="", attrs=attrs,
                            level=Level.READ_ONLY,
                            reason="screen capture (read-only)")
        raise PlanError(f"unknown step kind: {kind!r}")  # unreachable

    # ------------------------------------------------------------------
    @property
    def max_level(self) -> Level:
        return max((s.level for s in self.steps), default=Level.READ_ONLY)

    @property
    def max_level_label(self) -> str:
        return LEVEL_LABEL[self.max_level]

    @property
    def has_blocked(self) -> bool:
        return any(s.level == Level.BLOCKED for s in self.steps)

    # ------------------------------------------------------------------
    def render(self) -> str:
        """Human-readable plan for the approval prompt."""
        lines = [
            f"Plan: {len(self.steps)} step(s) — "
            f"highest classification: {self.max_level_label}"
        ]
        for i, step in enumerate(self.steps, start=1):
            lines.append(f"  {i}. [{step.label}] {step.kind}: {step.headline()}")
            if step.reason:
                lines.append(f"     reason: {step.reason}")
        if self.has_blocked:
            lines.append(
                "  !! This plan contains BLOCKED step(s): they will be "
                "refused even if you approve the plan."
            )
        return "\n".join(lines)


def plan_verdict(plan: Plan) -> Verdict:
    """Build a :class:`aegis.safety.Verdict` describing the whole plan.

    Lets the TUI/GUI reuse their existing :class:`aegis.approval.ApprovalGate`
    prompt unchanged: the rendered plan becomes the request text and the
    highest step classification becomes the level line.
    """
    level = plan.max_level
    return Verdict(
        level=level,
        allowed=level != Level.BLOCKED,
        reason=(f"whole-plan approval: {len(plan.steps)} step(s), highest "
                f"classification {LEVEL_LABEL[level]}"),
        command=f"aegis-plan ({len(plan.steps)} steps)",
        matched_rule="plan",
    )
