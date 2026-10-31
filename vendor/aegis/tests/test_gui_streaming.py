"""GUI streaming tests (#1, PySide6 front-end).

Two layers:

* :class:`aegis.gui.StreamAssembler` is framework-agnostic, so the streaming
  state machine is tested directly with no Qt present.
* A live Qt integration test runs only when PySide6 can actually load (it needs
  system GL libraries such as libEGL). When Qt is unavailable the integration
  part reports SKIP rather than passing silently.

Run:  python3 tests/test_gui_streaming.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.gui import StreamAssembler


# --------------------------------------------------------------------------
# Framework-agnostic state machine
# --------------------------------------------------------------------------

def test_stream_assembler():
    fails = 0

    events = []
    s = StreamAssembler(lambda kind, text: events.append((kind, text)))

    s.feed("Hello")
    s.feed(" world")
    s.end()

    if events == [("begin", ""), ("chunk", "Hello"), ("chunk", " world"),
                   ("end", "")]:
        print("PASS gui/asm: one begin, one chunk per token, one end")
    else:
        fails += 1
        print(f"FAIL gui/asm: {events}")

    # Empty chunks must not open a block.
    events = []
    s = StreamAssembler(lambda kind, text: events.append((kind, text)))
    s.feed("")
    s.feed("")
    s.end()
    if events == []:
        print("PASS gui/asm: empty chunks produce no output")
    else:
        fails += 1
        print(f"FAIL gui/asm: empty chunks -> {events}")

    # end() twice must not emit a second terminator.
    events = []
    s = StreamAssembler(lambda kind, text: events.append((kind, text)))
    s.feed("x")
    s.end()
    s.end()
    if [k for k, _ in events] == ["begin", "chunk", "end"]:
        print("PASS gui/asm: repeated end() is idempotent")
    else:
        fails += 1
        print(f"FAIL gui/asm: repeated end -> {events}")

    # A second reply after a completed one must open a new block.
    events = []
    s = StreamAssembler(lambda kind, text: events.append((kind, text)))
    s.feed("one")
    s.end()
    s.feed("two")
    s.end()
    if [k for k, _ in events] == ["begin", "chunk", "end", "begin", "chunk", "end"]:
        print("PASS gui/asm: a second reply opens a fresh block")
    else:
        fails += 1
        print(f"FAIL gui/asm: two replies -> {events}")

    # Re-feeding after end without an explicit end must still work.
    events = []
    s = StreamAssembler(lambda kind, text: events.append((kind, text)))
    s.feed("a")
    s.end()
    s.feed("b")   # no end() this time
    if events[-1] == ("chunk", "b") and s.active:
        print("PASS gui/asm: a new stream after end() re-activates")
    else:
        fails += 1
        print(f"FAIL gui/asm: re-activation -> {events} active={s.active}")
    return fails


# --------------------------------------------------------------------------
# Live Qt integration (optional)
# --------------------------------------------------------------------------

def _qt_available():
    """True only if PySide6 can actually load, not merely be imported."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6 import QtWidgets, QtGui  # noqa: F401
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        return app is not None
    except Exception as exc:  # ImportError on libEGL, etc.
        _qt_available.reason = f"{type(exc).__name__}: {exc}"
        return False


def test_qt_integration():
    """Verify real cursor insertion into a QTextBrowser."""
    from PySide6 import QtWidgets, QtGui

    fails = 0
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    browser = QtWidgets.QTextBrowser()

    body = QtGui.QTextCharFormat()
    body.setForeground(QtGui.QColor("#d8ffe8"))
    label = QtGui.QTextCharFormat()
    label.setForeground(QtGui.QColor("#8affc1"))
    move = getattr(QtGui.QTextCursor, "MoveOperation", QtGui.QTextCursor)

    def render(kind, text):
        cursor = browser.textCursor()
        cursor.movePosition(move.End)
        if kind == "begin":
            cursor.insertText("\naegis: ", label)
        elif kind == "chunk":
            cursor.insertText(text, body)
        else:
            cursor.insertText("\n")
        browser.setTextCursor(cursor)

    s = StreamAssembler(render)
    for chunk in ["You are ", "in the ", "workspace."]:
        s.feed(chunk)
    s.end()

    text = browser.toPlainText()
    if "aegis: You are in the workspace." in text:
        print("PASS gui/qt: streamed tokens assembled on one line")
    else:
        fails += 1
        print(f"FAIL gui/qt: transcript -> {text!r}")

    if text.count("aegis:") == 1:
        print("PASS gui/qt: exactly one label for one reply")
    else:
        fails += 1
        print(f"FAIL gui/qt: label count -> {text.count('aegis:')}")

    # The assembler is deliberately a pass-through: hiding action blocks is the
    # agent's job (aegis.agent._StreamFilter, covered in test_streaming.py), so
    # by the time a chunk reaches the GUI it is already safe to show.
    browser.clear()
    s2 = StreamAssembler(render)
    for chunk in ["visible ", "prose"]:
        s2.feed(chunk)
    s2.end()
    if "aegis: visible prose" in browser.toPlainText():
        print("PASS gui/qt: assembler renders chunks verbatim")
    else:
        fails += 1
        print(f"FAIL gui/qt: pass-through -> {browser.toPlainText()!r}")

    # A reply split across many tiny tokens must not gain line breaks.
    browser.clear()
    s3 = StreamAssembler(render)
    for ch in "token by token":
        s3.feed(ch)
    s3.end()
    text3 = browser.toPlainText().strip()
    if text3 == "aegis: token by token":
        print("PASS gui/qt: character-level tokens stay on one line")
    else:
        fails += 1
        print(f"FAIL gui/qt: char tokens -> {text3!r}")
    return fails


if __name__ == "__main__":
    total = 0
    total += test_stream_assembler(); print()

    if _qt_available():
        total += test_qt_integration(); print()
    else:
        print(f"SKIP: PySide6 cannot load here ({_qt_available.reason});")
        print("      the Qt cursor-insertion integration test was not run.")
        print()

    print(f"TOTAL FAILURES: {total}")
    sys.exit(1 if total else 0)
