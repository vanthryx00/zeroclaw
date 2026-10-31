"""Aegis desktop GUI (phase 3 interface) built on PySide6.

A chat window with:
  * a transcript pane,
  * a safety sidebar (mode / scope / backend),
  * a modal approval dialog for commands that need confirmation.

Assistant replies stream token by token. The agent runs on a ``QThread`` and
emits each chunk over a Qt signal, so the transcript updates progressively
without blocking the UI.

Two details matter here:

* Tokens are inserted with a ``QTextCursor`` and a ``QTextCharFormat`` rather
  than ``append()``. ``append`` starts a new block on every call, which would
  put each token on its own line.
* The *decision* of when a stream starts and ends lives in
  :class:`StreamAssembler`, which is framework-agnostic and unit-tested. Only
  the drawing is Qt-specific.

Run with:  aegis-gui
Requires:  pip install 'aegis[gui]'
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from .agent import Agent
from .approval import ApprovalGate, ApprovalOutcome, ApprovalRequest
from .config import Config
from .plan import plan_verdict

AEGIS_FG = "#d8ffe8"
AEGIS_LABEL = "#8affc1"
#: How long the GUI waits for a modal answer before denying.
APPROVAL_TIMEOUT = 300.0


class StreamAssembler:
    """Tracks stream state and tells a sink what to render.

    The sink is called with ``(kind, text)`` where ``kind`` is one of:

    * ``"begin"`` — the first chunk of a reply; the sink should open a new
      block and emit the label. Text is empty.
    * ``"chunk"`` — body text to append to the open block.
    * ``"end"`` — the reply finished; the sink should close the block.

    Keeping this out of the Qt layer means the "start once, end once, ignore
    empty chunks, tolerate a missing end" behaviour can be tested directly.
    """

    def __init__(self, sink: Callable[[str, str], None]):
        self._sink = sink
        self.active = False

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        if not self.active:
            self.active = True
            self._sink("begin", "")
        self._sink("chunk", chunk)

    def end(self) -> None:
        if not self.active:
            return
        self.active = False
        self._sink("end", "")


def build_window(cfg, agent=None):
    """Build the main window. A ``QApplication`` must already exist.

    Separate from :func:`main` so tests can construct and drive the window
    offscreen. Raises ``ModuleNotFoundError`` if PySide6 is unavailable.
    """
    from PySide6 import QtCore, QtGui, QtWidgets

    def _move_to_end(cursor) -> None:
        """Tolerate both the scoped (Qt6) and flat (Qt5) enum spellings."""
        move = getattr(QtGui.QTextCursor, "MoveOperation", QtGui.QTextCursor)
        cursor.movePosition(move.End)

    def _bold() -> "QtGui.QFont.Weight":
        weight = getattr(QtGui.QFont, "Weight", None)
        return weight.Bold if weight is not None else QtGui.QFont.Bold

    class Worker(QtCore.QThread):
        text = QtCore.Signal(str)
        token = QtCore.Signal(str)
        stream_end = QtCore.Signal()
        command = QtCore.Signal(str, str, bool, str)  # cmd, decision, ran, output
        # Emitted from the worker thread; delivered on the UI thread.
        approval = QtCore.Signal(object)

        def __init__(self, agent: Agent, prompt: str, gate: ApprovalGate):
            super().__init__()
            self.agent = agent
            self.prompt = prompt
            self.gate = gate

        def run(self) -> None:
            # The confirm callback runs on this thread; the gate blocks it and
            # asks the UI to show the modal.
            self.gate.on_request = lambda req: self.approval.emit(req)
            self.agent.executor.confirm = self.gate.ask
            # Whole-plan approval (#47) reuses the gate and the ApprovalDialog:
            # the rendered plan is the request text, the highest step
            # classification the level line.
            self.agent.plan_confirm = (
                lambda plan: self.gate.ask(plan_verdict(plan),
                                           plan.render()))

            def on_token(chunk):
                if chunk:
                    self.token.emit(chunk)

            def on_stream_end():
                self.stream_end.emit()

            def on_text(prose):
                # Only reached when nothing streamed (e.g. backend errors).
                if prose:
                    self.text.emit(prose)

            def on_command(command, result):
                body = (result.stdout or result.stderr or "").strip()
                self.command.emit(command, result.decision, result.ran, body[:4000])

            try:
                self.agent.ask(self.prompt, on_token=on_token,
                               on_stream_end=on_stream_end,
                               on_text=on_text, on_command=on_command)
            finally:
                # Guarantees the UI closes an open block even on error.
                self.stream_end.emit()
                self.text.emit("__DONE__")

    class ApprovalDialog(QtWidgets.QDialog):
        def __init__(self, command: str, level: str, reason: str, parent=None,
                     rememberable: bool = True):
            super().__init__(parent)
            self.setWindowTitle("Approve command")
            self.result_outcome = ApprovalOutcome.DENY
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(QtWidgets.QLabel(f"<b>Level:</b> {level}"))
            layout.addWidget(QtWidgets.QLabel(f"<b>Reason:</b> {reason}"))
            code = QtWidgets.QPlainTextEdit(command)
            code.setReadOnly(True)
            layout.addWidget(code)

            buttons = QtWidgets.QDialogButtonBox()
            run_btn = buttons.addButton("Run once",
                                        QtWidgets.QDialogButtonBox.AcceptRole)
            always_btn = buttons.addButton("Always allow",
                                           QtWidgets.QDialogButtonBox.ActionRole)
            buttons.addButton("Deny", QtWidgets.QDialogButtonBox.RejectRole)
            run_btn.clicked.connect(self._once)
            always_btn.clicked.connect(self._always)
            buttons.rejected.connect(self.reject)
            if not rememberable:
                # Offensive and blocked commands are never a standing rule.
                always_btn.setEnabled(False)
                always_btn.setToolTip(
                    "This level cannot be remembered. Offensive tooling is "
                    "authorised with `aegis scope add`."
                )
            layout.addWidget(buttons)

        def _once(self):
            self.result_outcome = ApprovalOutcome.ALLOW
            self.accept()

        def _always(self):
            self.result_outcome = ApprovalOutcome.ALLOW_ALWAYS
            self.accept()

    class Window(QtWidgets.QMainWindow):
        def __init__(self, cfg, agent):
            super().__init__()
            self.setWindowTitle("Aegis — offline security copilot")
            self.resize(1000, 700)
            self.cfg = cfg
            self.agent = agent
            self.worker: Optional[Worker] = None
            #: Set by tests to auto-answer a modal without showing it.
            #: Accepts a bool or an ApprovalOutcome.
            self.auto_approve = None
            self.approval = ApprovalGate(timeout=APPROVAL_TIMEOUT)

            self._body_fmt = QtGui.QTextCharFormat()
            self._body_fmt.setForeground(QtGui.QColor(AEGIS_FG))
            self._label_fmt = QtGui.QTextCharFormat()
            self._label_fmt.setForeground(QtGui.QColor(AEGIS_LABEL))
            self._label_fmt.setFontWeight(_bold())

            self.stream = StreamAssembler(self._render)

            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            layout = QtWidgets.QHBoxLayout(central)

            self.sidebar = QtWidgets.QLabel(self._sidebar())
            self.sidebar.setFixedWidth(280)
            self.sidebar.setWordWrap(True)
            self.sidebar.setStyleSheet("background:#12161f;color:#cfe;padding:12px;")
            layout.addWidget(self.sidebar)

            right = QtWidgets.QVBoxLayout()
            self.transcript = QtWidgets.QTextBrowser()
            right.addWidget(self.transcript)

            row = QtWidgets.QHBoxLayout()
            self.input = QtWidgets.QLineEdit()
            self.input.setPlaceholderText("Ask Aegis…")
            self.input.returnPressed.connect(self.send)
            send_btn = QtWidgets.QPushButton("Send")
            send_btn.clicked.connect(self.send)
            row.addWidget(self.input)
            row.addWidget(send_btn)
            right.addLayout(row)
            layout.addLayout(right)

        def _sidebar(self) -> str:
            return (
                f"<h3>Aegis</h3>"
                f"<b>mode</b><br>{self.cfg.safety.mode}<br><br>"
                f"<b>scope</b><br>{', '.join(self.cfg.safety.authorized_targets) or 'none'}<br><br>"
                f"<pre>{self.agent.router.status()}</pre>"
            )

        def append(self, who: str, text: str) -> None:
            color = {"you": "#4da3ff", "aegis": AEGIS_LABEL, "cmd": "#ffd479",
                     "err": "#ff8080"}.get(who, "#ddd")
            self.transcript.append(
                f'<div style="color:{color}"><b>{who}</b>: '
                f"{text.replace(chr(10), '<br>')}</div>"
            )

        # -- rendering (called by StreamAssembler) ------------------------
        def _render(self, kind: str, text: str) -> None:
            cursor = self.transcript.textCursor()
            _move_to_end(cursor)
            if kind == "begin":
                cursor.insertText("\naegis: ", self._label_fmt)
            elif kind == "chunk":
                cursor.insertText(text, self._body_fmt)
            elif kind == "end":
                cursor.insertText("\n")
            self.transcript.setTextCursor(cursor)
            self.transcript.ensureCursorVisible()

        # -- signals -------------------------------------------------------
        def _on_token(self, chunk: str) -> None:
            self.stream.feed(chunk)

        def _on_stream_end(self) -> None:
            self.stream.end()

        def _on_text(self, prose: str) -> None:
            if prose == "__DONE__":
                return
            # Unstreamed prose (errors, or a backend without streaming) still
            # belongs in the transcript.
            self.stream.end()
            self.append("aegis", prose)

        def _on_command(self, command: str, decision: str, ran: bool, output: str) -> None:
            self.stream.end()
            self.append("cmd", f"[{decision}] {command}")
            if output:
                self.append("aegis" if ran else "err", output)

        # -- command approval ----------------------------------------------
        def _on_approval_request(self, req: ApprovalRequest) -> None:
            """Runs on the UI thread; blocks it while the modal is open."""
            self.stream.end()
            if self.auto_approve is not None:
                # Test hook: no modal is shown.
                outcome = self.auto_approve
                if isinstance(outcome, bool):
                    outcome = (ApprovalOutcome.ALLOW if outcome
                               else ApprovalOutcome.DENY)
            else:
                dialog = ApprovalDialog(req.command, req.level, req.reason,
                                        parent=self,
                                        rememberable=req.rememberable)
                dialog.exec()
                outcome = dialog.result_outcome

            if outcome is ApprovalOutcome.ALLOW_ALWAYS:
                label = "✔ always allowed"
            elif outcome is ApprovalOutcome.ALLOW:
                label = "✔ approved"
            else:
                label = "✘ denied"
            self.append("cmd", f"{label}: {req.command}")
            if not self.approval.resolve_outcome(outcome):
                self.append("err", "no command was waiting for an answer")

        # -- turn lifecycle -------------------------------------------------
        def send(self) -> None:
            text = self.input.text().strip()
            if not text or self.worker is not None:
                return
            self.input.clear()
            self.append("you", text)

            self.stream.end()  # close anything left open by a previous turn
            self.approval.reset()  # re-arm after any previous cancel
            self.worker = Worker(self.agent, text, self.approval)
            self.worker.text.connect(self._on_text)
            self.worker.token.connect(self._on_token)
            self.worker.stream_end.connect(self._on_stream_end)
            self.worker.command.connect(self._on_command)
            self.worker.approval.connect(self._on_approval_request)
            self.worker.finished.connect(self._on_finished)
            self.worker.start()

        def _on_finished(self) -> None:
            self.stream.end()
            self.worker = None

        def closeEvent(self, event) -> None:
            # Unblock a worker waiting on a prompt that can no longer be shown.
            self.approval.cancel()
            super().closeEvent(event)

    if agent is None:
        agent = Agent(cfg)
    win = Window(cfg, agent)
    #: Exposed so tests can exercise the dialog's safety affordances directly
    #: (e.g. "Always allow" must be disabled for a non-rememberable level).
    win._approval_dialog_class = ApprovalDialog
    return win


def main(argv=None) -> int:
    try:
        from PySide6 import QtWidgets
    except ModuleNotFoundError:
        print("PySide6 is not installed. Install with: pip install 'aegis[gui]'")
        print("Falling back to the CLI session.")
        from .cli import main as cli_main
        return cli_main(argv)

    cfg = Config.load()
    app = QtWidgets.QApplication(sys.argv)
    win = build_window(cfg)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
