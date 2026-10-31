"""Aegis TUI (phase 2 interface) built on Textual.

Falls back to the plain CLI session if Textual is not installed.

Assistant replies stream token by token. Because ``agent.ask()`` is blocking,
it runs in a Textual *thread worker* and every UI update is marshalled back to
the event loop with ``call_from_thread``. The in-progress reply is rendered into
a dedicated ``#stream`` Static (a RichLog cannot append to a partial line); when
the stream ends the text is moved into the log and the Static is cleared.

Run with:  aegis-tui   (or)  python -m aegis.tui
"""

from __future__ import annotations

import sys

from .agent import Agent
from .approval import (ApprovalGate, ApprovalOutcome, ApprovalRequest,
                       parse_answer)
from .config import Config
from .plan import plan_verdict


def build_app(cfg, agent):
    """Build a ready-to-run AegisTUI bound to *cfg* and *agent*.

    Separate from :func:`main` so tests can drive the app through Textual's
    ``run_test`` harness without a terminal. Raises ``ModuleNotFoundError`` if
    Textual is absent.
    """
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, RichLog, Static

    class AegisTUI(App):
        CSS = """
        #sidebar { width: 34; border: round $accent; padding: 1; }
        #right { width: 1fr; }
        #log { border: round $primary; height: 1fr; }
        #stream { height: auto; max-height: 14; color: $success; padding: 0 1; }
        #input { dock: bottom; }
        """
        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("ctrl+l", "clear_log", "Clear"),
        ]
        # NOTE: no y/n key bindings — they would fight the text input. The user
        # types 'y' and presses enter, which keeps the input box unambiguous.

        def __init__(self):
            super().__init__()
            # Buffer for the reply currently being streamed.
            self._stream_buf: list = []
            # True while a risky command is waiting for a typed y/n.
            self._awaiting_approval = False
            self.approval = ApprovalGate()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                yield Static(self._sidebar_text(), id="sidebar")
                with Vertical(id="right"):
                    yield RichLog(id="log", highlight=True, markup=True)
                    yield Static("", id="stream")
            yield Input(placeholder="Ask Aegis… (enter to send)", id="input")
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#log", RichLog).write(
                "[b blue]Aegis[/b blue] — offline security copilot\n"
                f"{cfg.describe()}\n"
            )
            self.query_one("#input", Input).focus()

        def on_unmount(self) -> None:
            # Never leave a worker thread blocked on a prompt that can no
            # longer be answered.
            self.approval.cancel()

        # -- rendering helpers (always called on the event loop) ----------
        def _write(self, text: str) -> None:
            self.query_one("#log", RichLog).write(text)

        def _append_token(self, chunk: str) -> None:
            self._stream_buf.append(chunk)
            self.query_one("#stream", Static).update("".join(self._stream_buf))

        def _finish_stream(self) -> None:
            if not self._stream_buf:
                return
            text = "".join(self._stream_buf)
            self._stream_buf = []
            self.query_one("#stream", Static).update("")
            if text.strip():
                self._write(text)

        def _safe_call(self, fn, *args) -> None:
            """Marshalling that tolerates the app shutting down mid-stream."""
            try:
                self.call_from_thread(fn, *args)
            except Exception:
                pass

        # -- sidebar ------------------------------------------------------
        def _sidebar_text(self) -> str:
            status = agent.router.status()
            return (
                "[b]Aegis[/b]\n\n"
                f"mode: [b]{cfg.safety.mode}[/b]\n"
                f"scope: {', '.join(cfg.safety.authorized_targets) or 'none'}\n\n"
                f"{status}"
            )

        # -- command approval ---------------------------------------------
        def _show_approval(self, req: ApprovalRequest) -> None:
            """Runs on the event loop: render the prompt and arm the input."""
            self._awaiting_approval = True
            self._write(
                f"[yellow]⚠ approve? ({req.level})[/yellow] {req.command}\n"
                f"  reason: {req.reason}\n"
                "  [b]y[/b] = run once · [b]a[/b] = always allow · "
                "anything else denies"
            )
            box = self.query_one("#input", Input)
            box.placeholder = "y = once · a = always · other = deny"
            box.focus()

        def _answer_approval(self, text: str) -> None:
            """Runs on the event loop: hand the user's answer to the worker."""
            self._awaiting_approval = False
            box = self.query_one("#input", Input)
            box.placeholder = "Ask Aegis… (enter to send)"
            outcome = parse_answer(text)
            if outcome is ApprovalOutcome.ALLOW_ALWAYS:
                self._write("[green]✔ always allowed[/green]")
            elif outcome is ApprovalOutcome.ALLOW:
                self._write("[green]✔ approved (once)[/green]")
            else:
                self._write("[red]✘ denied[/red]")
            if not self.approval.resolve_outcome(outcome):
                self._write("[dim](no command was waiting for an answer)[/dim]")

        # -- the agent turn (runs on a worker thread) ---------------------
        def _ask(self, text: str) -> None:
            def on_token(chunk):
                if chunk:
                    self._safe_call(self._append_token, chunk)

            def on_stream_end():
                self._safe_call(self._finish_stream)

            def on_text(prose):
                # Only reached when nothing was streamed (e.g. backend errors).
                if prose:
                    self._safe_call(self._write, prose)

            def on_command(command, result):
                color = "green" if result.ran else "red"
                self._safe_call(
                    self._write,
                    f"[{color}]▸ {command} ({result.decision})[/{color}]",
                )
                body = (result.stdout or result.stderr or "").strip()
                if body:
                    self._safe_call(self._write, body[:3000])

            # Risky commands block this worker thread until the user answers.
            self.approval.on_request = \
                lambda req: self._safe_call(self._show_approval, req)
            agent.executor.confirm = self.approval.ask
            # Whole-plan approval (#47) reuses the same gate and prompt: the
            # rendered plan becomes the request text, the highest step
            # classification becomes the level line.
            agent.plan_confirm = (
                lambda plan: self.approval.ask(plan_verdict(plan),
                                               plan.render()))
            try:
                agent.ask(text, on_token=on_token, on_stream_end=on_stream_end,
                          on_text=on_text, on_command=on_command)
            finally:
                self._safe_call(self._finish_stream)

        # -- events -------------------------------------------------------
        def on_input_submitted(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            self.query_one("#input", Input).value = ""

            # While a command is pending, Enter answers the prompt rather than
            # starting a new turn.
            if self._awaiting_approval:
                self._answer_approval(text)
                return

            if not text:
                return
            self._stream_buf = []
            self._write(f"[b blue]you ›[/b blue] {text}")

            # Blocking work must not run on the event loop, or the UI cannot
            # repaint between tokens.
            if hasattr(self, "run_worker"):
                self.run_worker(lambda: self._ask(text), thread=True,
                                exclusive=True)
            else:  # very old Textual: correct, just not progressive
                self._ask(text)

        def action_clear_log(self) -> None:
            self._stream_buf = []
            self.query_one("#stream", Static).update("")
            self.query_one("#log", RichLog).clear()


    return AegisTUI()


def main(argv=None) -> int:
    try:
        import textual.app  # noqa: F401  (probe only)
    except ModuleNotFoundError:
        print("Textual is not installed; falling back to the CLI session.")
        from .cli import main as cli_main
        return cli_main(argv)

    cfg = Config.load()
    agent = Agent(cfg)
    build_app(cfg, agent).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
