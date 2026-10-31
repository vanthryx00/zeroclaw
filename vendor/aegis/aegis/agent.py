"""The Aegis agent loop.

Implements a bounded ReAct-style cycle with four action protocols the model can
emit in a fenced block:

* ```` ```aegis-command ```` — run a shell command
* ```` ```aegis-file path=… ```` — write a file inside the workspace
* ```` ```aegis-snippet title=… lang=… tags=… ```` — save a reusable code snippet
* ```` ```aegis-remember tags=… ```` — record a lesson for future sessions
* ```` ```aegis-screenshot ```` — capture the desktop and describe it
* ```` ```aegis-gui ```` — perform one desktop GUI action (``gui:click x,y`` …)

Before each turn the learning engine folds relevant snippets, lessons, and
preferences into the prompt, so the assistant accumulates context over time.
The loop is deliberately small and auditable: it never executes anything the
:class:`~aegis.executor.Executor` (or :class:`~aegis.desktop.GuiExecutor`)
refuses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import context as context_mod
from . import screen as screen_mod
from .allowlist import AllowStore
from .brain import BackendError, BackendRouter, Message
from .desktop import GuiExecutor
from .executor import ExecutionResult, Executor
from .files import FileWorkspace, WorkspaceError
from .learning import LearningEngine
from .memory import Memory
from .plan import (PLAN_FENCE_RE, Plan, PlanConfirmFn, PlanError,
                   _parse_attrs)
from .prompts import build_system_prompt

ACTION_RE = re.compile(
    r"```aegis-(command|file|snippet|remember|screenshot|gui)([^\n]*)\n(.*?)```",
    re.DOTALL,
)
COMMAND_RE = re.compile(r"```aegis-command\s*\n(.*?)```", re.DOTALL)


@dataclass
class Step:
    kind: str  # "reply" | "command" | "file" | "snippet" | "remember" | "screenshot" | "gui" | "observation" | "error"
    content: str
    result: Optional[ExecutionResult] = None


@dataclass
class AgentResponse:
    final: str
    steps: List[Step] = field(default_factory=list)


OnText = Callable[[str], None]
OnCommand = Callable[[str, ExecutionResult], None]
OnGui = Callable[[str, ExecutionResult], None]
OnNote = Callable[[str, str], None]  # (kind, human summary)
OnToken = Callable[[str], None]       # one streamed chunk of assistant prose
OnStreamEnd = Callable[[], None]      # the current stream finished


class _StreamFilter:
    """Forwards assistant prose to the UI while hiding action blocks.

    Action blocks are machine instructions, not something to show mid-stream.
    We hold back a short lookahead window so a marker split across two chunks is
    never emitted, and once a marker appears we go silent for the rest of the
    stream. Ordinary fenced code (```python, ```bash) streams normally.
    """

    MARKER = "```aegis-"

    def __init__(self, emit: Callable[[str], None]):
        self._emit = emit
        self._buf = ""
        self.suppressed = False

    def feed(self, token: str) -> None:
        if self.suppressed or not token:
            return
        self._buf += token
        idx = self._buf.find(self.MARKER)
        if idx != -1:
            if idx > 0:
                self._emit(self._buf[:idx])
            self._buf = ""
            self.suppressed = True
            return
        hold = len(self.MARKER) - 1
        if len(self._buf) > hold:
            self._emit(self._buf[:-hold])
            self._buf = self._buf[-hold:]

    def flush(self) -> None:
        if not self.suppressed and self._buf:
            self._emit(self._buf)
        self._buf = ""


def _intent_hint(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("code", "function", "script", "bug", "refactor",
                            "implement", "class ", "def ", "api", "compile",
                            "traceback", "stack trace", "unit test", "regex")):
        return ("Intent: CODING. Prefer concrete, runnable code; explain the key "
                "lines; save anything reusable with an `aegis-snippet` block.")
    if any(k in t for k in ("scan", "exploit", "payload", "enum", "recon",
                            "vuln", "nmap", "cve", "privilege escalation")):
        return ("Intent: SECURITY. Verify the target is in authorized scope, "
                "prefer read-only recon, and teach the methodology.")
    if any(k in t for k in ("broken", "won't boot", "wont boot", "repair",
                            "crash", "failed", "log", "error", "fix")):
        return ("Intent: TROUBLESHOOTING. Gather evidence before changing "
                "anything; explain what the evidence means.")
    return ""


class Agent:
    def __init__(self, cfg, router: Optional[BackendRouter] = None,
                 executor: Optional[Executor] = None, memory: Optional[Memory] = None,
                 learning: Optional[LearningEngine] = None,
                 plan_confirm: Optional[PlanConfirmFn] = None):
        self.cfg = cfg
        self.router = router or BackendRouter(cfg)
        self.allowlist = AllowStore(cfg.safety.allowlist_file)
        # An injected executor keeps its own allowlist, so callers can supply a
        # pre-configured one (tests, or an embedding application).
        self.executor = executor or Executor(cfg, allowlist=self.allowlist)
        # GUI actions share the same allowlist and audit log. Front-ends that
        # set agent.executor.confirm get the handler picked up per call (see
        # _execute_step), so one wiring covers both executors.
        self.gui_executor = GuiExecutor(cfg, allowlist=self.allowlist)
        self.memory = memory or Memory(cfg.interface.history_file)
        self.learning = learning or LearningEngine(cfg)
        self.workspace = FileWorkspace(cfg.safety.workspace_root)
        self.plan_confirm = plan_confirm
        self._system_context = context_mod.gather(cfg.safety.workspace_root).to_prompt()

    # ------------------------------------------------------------------
    def refresh_context(self) -> None:
        self._system_context = context_mod.gather(self.cfg.safety.workspace_root).to_prompt()

    def _system_prompt(self, query: str = "") -> str:
        scope = self.cfg.safety.authorized_targets
        scope_line = (
            "Authorized scope (only these may be targeted with offensive tools): "
            + (", ".join(scope) if scope else "NONE DECLARED — offensive tools will be refused.")
        )
        parts = [
            scope_line,
            f"Current safety mode: {self.cfg.safety.mode}.",
            f"Workspace root: {self.cfg.safety.workspace_root}",
        ]
        hint = _intent_hint(query)
        if hint:
            parts.append(hint)
        learned = self.learning.context_for(query) if query else ""
        if learned:
            parts.append(learned)
        return build_system_prompt(self._system_context, "\n\n".join(parts))

    # ------------------------------------------------------------------
    def ask(
        self,
        user_input: str,
        *,
        on_text: Optional[OnText] = None,
        on_command: Optional[OnCommand] = None,
        on_gui: Optional[OnGui] = None,
        on_note: Optional[OnNote] = None,
        on_token: Optional[OnToken] = None,
        on_stream_end: Optional[OnStreamEnd] = None,
    ) -> AgentResponse:
        self.memory.add("user", user_input)
        steps: List[Step] = []
        ran_commands: List[str] = []

        for _round in range(self.cfg.model.max_tool_rounds):
            messages = self.memory.messages(self._system_prompt(user_input))
            streamed = False
            try:
                if on_token is not None:
                    reply = self._generate_streaming(
                        messages, on_token, on_stream_end)
                    streamed = True
                else:
                    reply = self.router.generate(messages)
            except BackendError as exc:
                if on_stream_end:
                    on_stream_end()
                msg = (
                    f"[backend error] {exc}\n"
                    "No local model is reachable. Start one with `ollama serve` "
                    "(then `ollama pull qwen2.5-coder:7b`) or a llama.cpp server, "
                    "and check `aegis doctor`."
                )
                if on_text:
                    on_text(msg)
                steps.append(Step("error", msg))
                return AgentResponse(msg, steps)

            action = self._extract_action(reply)
            prose = ACTION_RE.sub("", reply).strip()
            # When streaming, the prose already reached the user token by token.
            if prose and on_text and not streamed:
                on_text(prose)

            if action is None:
                final_text = reply.strip()
                self.memory.add("assistant", reply)
                steps.append(Step("reply", reply))
                self._maybe_autosave(user_input, ran_commands)
                return AgentResponse(final_text, steps)

            kind, attrs, body = action
            self.memory.add("assistant", reply)
            steps.append(Step("reply", prose))

            observation = self._handle_action(
                kind, attrs, body, steps, on_command, on_note, ran_commands,
                on_gui=on_gui)
            self.memory.add("user", observation)
            steps.append(Step("observation", observation))

        final_text = (
            "I reached the maximum number of action steps for one request. "
            "Here is where things stand — ask me to continue if needed."
        )
        if on_text:
            on_text(final_text)
        steps.append(Step("reply", final_text))
        return AgentResponse(final_text, steps)

    # ------------------------------------------------------------------
    def _generate_streaming(
        self,
        messages,
        on_token: OnToken,
        on_stream_end: Optional[OnStreamEnd],
    ) -> str:
        """Stream a reply, forwarding prose to ``on_token``.

        The full reply is still accumulated and returned, because action-block
        parsing needs the complete text.
        """
        filt = _StreamFilter(on_token)
        parts: List[str] = []
        try:
            for chunk in self.router.generate_stream(messages):
                parts.append(chunk)
                filt.feed(chunk)
        finally:
            filt.flush()
            if on_stream_end:
                on_stream_end()
        return "".join(parts)

    # ------------------------------------------------------------------
    def _handle_action(self, kind, attrs, body, steps, on_command, on_note,
                       ran_commands, on_gui=None) -> str:
        if kind == "plan":
            return self._handle_plan(body, steps, on_command, on_note,
                                     ran_commands, on_gui=on_gui)
        observation, _ok = self._execute_step(
            kind, attrs, body, steps, on_command, on_note, ran_commands,
            on_gui=on_gui)
        return observation

    def _execute_step(self, kind, attrs, body, steps, on_command, on_note,
                      ran_commands, confirmed: bool = False, on_gui=None):
        """Run a single action. Returns ``(observation, ok)``.

        ``confirmed=True`` means the operator already approved this step (as
        part of a whole plan); it is passed straight to the executor, which
        still hard-blocks BLOCKED commands, still enforces dry-run mode and
        the sudo gate, and still audits the run.
        """
        if kind == "command":
            cmd = body.strip()
            result = self.executor.run(cmd, confirmed=confirmed)
            steps.append(Step("command", cmd, result))
            if on_command:
                on_command(cmd, result)
            if result.ran and result.exit_code == 0:
                ran_commands.append(cmd)
                if self.cfg.learning.autosave_commands:
                    self.learning.record_success(cmd,
                                                 (result.stdout or "")[:200])
                return self._format_observation(cmd, result), True
            return self._format_observation(cmd, result), False

        if kind == "screenshot":
            return self._execute_screenshot(steps, on_note)

        if kind == "gui":
            descriptor = body.strip()
            # Pick up the shell executor's confirm handler at call time, so
            # front-ends wire confirmation once and it covers both executors.
            result = self.gui_executor.run(
                descriptor, confirmed=confirmed,
                confirm=self.executor.confirm)
            steps.append(Step("gui", descriptor, result))
            if on_gui:
                on_gui(descriptor, result)
            if result.ran:
                return (f"OBSERVATION: GUI action `{descriptor}` ran "
                        f"({result.stdout or 'done'})."), True
            return (f"OBSERVATION: GUI action `{descriptor}` did NOT run.\n"
                    f"Safety decision: {result.decision}. "
                    f"Reason: {result.stderr or result.verdict.reason}\n"
                    "Try a safer alternative, or explain the limitation."), False

        if kind == "file":
            path = attrs.get("path", "")
            try:
                written = self.workspace.write(path, body)
                summary = f"wrote {written}"
                if on_note:
                    on_note("file", summary)
                steps.append(Step("file", summary))
                return (f"OBSERVATION: wrote file '{path}' "
                        f"({len(body)} bytes) inside the workspace."), True
            except WorkspaceError as exc:
                steps.append(Step("file", f"refused: {exc}"))
                return (f"OBSERVATION: file write REFUSED. {exc}\n"
                        "Choose a path inside the workspace."), False

        if kind == "snippet":
            try:
                title = attrs.get("title", "snippet")
                language = attrs.get("lang") or attrs.get("language") or None
                tags = [t for t in attrs.get("tags", "").split(",") if t]
                snippet = self.learning.save_snippet(
                    title, body, language=language, tags=tags, source="agent")
                summary = (f"saved snippet [{snippet.id}] {snippet.title} "
                           f"({snippet.language})")
                if on_note:
                    on_note("snippet", summary)
                steps.append(Step("snippet", summary))
                return (f"OBSERVATION: saved snippet [{snippet.id}] "
                        f"'{snippet.title}' as {snippet.language}. It will be "
                        "available in future sessions."), True
            except Exception as exc:
                steps.append(Step("snippet", f"failed: {exc}"))
                return f"OBSERVATION: snippet save FAILED: {exc}", False

        if kind == "remember":
            try:
                tags = [t for t in attrs.get("tags", "").split(",") if t]
                title = attrs.get("title", body.strip()[:80])
                exp = self.learning.record_lesson(body.strip(), tags,
                                                  title=title)
                summary = f"remembered [{exp.id}] {exp.title}"
                if on_note:
                    on_note("remember", summary)
                steps.append(Step("remember", summary))
                return (f"OBSERVATION: recorded lesson [{exp.id}]. "
                        "It will be recalled in future sessions."), True
            except Exception as exc:
                steps.append(Step("remember", f"failed: {exc}"))
                return f"OBSERVATION: lesson record FAILED: {exc}", False

        return "OBSERVATION: unknown action.", False

    def _execute_screenshot(self, steps, on_note):
        """Capture the desktop, describe it via a vision backend if any.

        Screenshot is READ_ONLY. A missing display or missing vision backend
        is reported as an observation, never raised — the agent keeps working
        with whatever it can see.
        """
        try:
            path = screen_mod.default_screenshot_path()
            image = screen_mod.capture(path)
        except Exception as exc:
            steps.append(Step("screenshot", f"failed: {exc}"))
            return (f"OBSERVATION: screenshot FAILED: {exc}\n"
                    "Proceed without seeing the screen, or ask the operator "
                    "what is visible."), False
        description = screen_mod.describe(image, self.router)
        summary = f"screenshot saved to {path}"
        if on_note:
            on_note("screenshot", summary)
        steps.append(Step("screenshot", summary))
        return f"OBSERVATION: {summary}.\n{description}", True

    # ------------------------------------------------------------------
    def _handle_plan(self, body, steps, on_command, on_note,
                     ran_commands, on_gui=None) -> str:
        """Whole-plan approval (#47): parse, approve once, execute in order.

        A denied plan — or a plan with no approval handler configured — runs
        nothing. Approval never bypasses BLOCKED: the executor refuses those
        steps and the plan halts there like any other failed step.
        """
        audit = self.executor.audit
        try:
            plan = Plan.parse(body, self.cfg)
        except PlanError as exc:
            steps.append(Step("plan", f"refused: {exc}"))
            audit.record(event="plan_refused", reason=str(exc))
            return (f"OBSERVATION: plan REFUSED before approval: {exc}\n"
                    "Fix the plan and try again, or act step by step.")

        steps.append(Step("plan", plan.render()))
        audit.record(event="plan_proposed",
                     steps=[s.describe() for s in plan.steps],
                     max_level=plan.max_level_label)

        if self.plan_confirm is None:
            audit.record(event="plan_decision", approved=False,
                         reason="no plan approval handler configured")
            return ("OBSERVATION: plan NOT approved — this interface has no "
                    "plan approval handler configured. Nothing ran. Act step "
                    "by step instead.")

        try:
            approved = bool(self.plan_confirm(plan))
        except Exception as exc:
            # Fail closed: a broken approval handler must never mean "go".
            audit.record(event="plan_decision", approved=False,
                         reason=f"approval handler raised: {exc}")
            return ("OBSERVATION: plan approval failed closed "
                    f"({exc}). Nothing ran.")

        audit.record(event="plan_decision", approved=approved,
                     steps=len(plan.steps), max_level=plan.max_level_label)
        if not approved:
            steps.append(Step("plan", "denied by operator"))
            return "OBSERVATION: plan DENIED by the operator. Nothing ran."

        for index, pstep in enumerate(plan.steps, start=1):
            observation, ok = self._execute_step(
                pstep.kind, pstep.attrs, pstep.content,
                steps, on_command, on_note, ran_commands, confirmed=True,
                on_gui=on_gui)
            if pstep.kind != "command":
                # Command steps are audited by the executor itself; record
                # the local-only steps here so the whole plan is traceable.
                audit.record(event="plan_step", kind=pstep.kind,
                             step=f"{index}/{len(plan.steps)}",
                             summary=pstep.headline(), ok=ok)
            if not ok:
                audit.record(event="plan_halted", at_step=index,
                             total=len(plan.steps))
                steps.append(Step("plan", f"halted at step {index}"))
                return (f"OBSERVATION: plan HALTED at step {index} of "
                        f"{len(plan.steps)} — remaining steps did not run.\n"
                        f"{observation}")
        audit.record(event="plan_completed", steps=len(plan.steps))
        steps.append(Step("plan", f"completed ({len(plan.steps)} steps)"))
        return (f"OBSERVATION: plan COMPLETED — all {len(plan.steps)} steps "
                "executed successfully.")

    # ------------------------------------------------------------------
    def _maybe_autosave(self, user_input: str, ran_commands: List[str]) -> None:
        if not self.cfg.learning.autosave_successes or not ran_commands:
            return
        # Only remember multi-step or clearly useful sequences, to avoid bloat.
        if len(ran_commands) < 2:
            return
        body = "\n".join(ran_commands)
        self.learning.record_success(
            title=user_input[:80], summary=body,
            tags=["autosaved", "workflow"])

    @staticmethod
    def _extract_action(reply: str):
        # A plan block takes precedence: it is the whole action for the turn.
        # Any other fenced blocks in the same reply are ignored.
        plan_matches = PLAN_FENCE_RE.findall(reply)
        if plan_matches:
            return "plan", {}, plan_matches[-1]
        matches = ACTION_RE.findall(reply)
        if not matches:
            return None
        kind, raw_attrs, body = matches[-1]
        return kind, _parse_attrs(raw_attrs), body

    @staticmethod
    def _format_observation(command: str, result: ExecutionResult) -> str:
        if not result.ran:
            return (
                f"OBSERVATION: the command `{command}` did NOT run.\n"
                f"Safety decision: {result.decision}. Reason: {result.verdict.reason}\n"
                f"Try a safer or in-scope alternative, or explain the limitation."
            )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if len(out) > 4000:
            out = out[:4000] + "\n...[truncated]"
        if len(err) > 1500:
            err = err[:1500] + "\n...[truncated]"
        return (
            f"OBSERVATION for `{command}` (exit {result.exit_code}):\n"
            f"--- stdout ---\n{out or '(empty)'}\n"
            f"--- stderr ---\n{err or '(empty)'}"
        )

    # ------------------------------------------------------------------
    def status(self) -> str:
        active = self.router.select()
        lines = [
            f"config: {self.cfg.describe()}",
            f"backend: {active.info() if active else 'NONE available'}",
            f"learning: {self.learning.stats()}",
        ]
        return "\n".join(lines)
