# Eyes + Hands — Desktop GUI Control

Aegis can now see the desktop and operate it, under the same safety model
as shell commands. Nothing here bypasses classification, confirmation, or
the audit log.

## What it is

| Part | Module | Does |
|------|--------|------|
| Eyes | `aegis/screen.py` | Screenshot capture (`mss`, `Pillow` fallback), vision description via a configured vision model |
| Hands | `aegis/desktop.py` | Mouse/keyboard primitives (`pyautogui`) + `GuiExecutor` |
| Brain | `aegis/brain/*` | `describe_image()` on vision-capable backends (Ollama `/api/chat` `images`) |

## Install

```bash
pip install 'aegis[desktop]'   # mss + pyautogui + Pillow
```

All three are optional. Importing `aegis` never fails because one is
missing — calling a primitive without its dependency raises a clear error
naming the `pip install` command. Screenshot capture without a display
raises `ScreenError` instead of crashing.

A vision model is needed for *descriptions* (screenshots still save without
one). Any Ollama vision model works, e.g.:

```bash
ollama pull llava
```

## Agent tools

The agent loop gains two action blocks:

````markdown
```aegis-screenshot
```
````

Captures the desktop, saves the PNG, and — if a vision backend is
configured — describes what is on screen. Read-only. Without a vision
backend the observation says so and carries the saved path.

````markdown
```aegis-gui
gui:click 500,300
```
````

One GUI action. Descriptors:

| Descriptor | Effect | Level |
|---|---|---|
| `gui:screenshot` | capture + save PNG | READ_ONLY |
| `gui:size` | report screen size | READ_ONLY |
| `gui:move_to x,y` | move mouse | READ_ONLY |
| `gui:click x,y` | left click | RISKY |
| `gui:double_click x,y` | double click | RISKY |
| `gui:right_click x,y` | right click | RISKY |
| `gui:type <text>` | type text | RISKY |
| `gui:key <key>` | press a key (`enter`, `tab`, …) | RISKY |
| `gui:hotkey <key+key>` | chord (`ctrl+c`) | RISKY |
| `gui:scroll <n>` | scroll (negative = down) | RISKY |
| `gui:drag x1,y1 x2,y2` | click-drag | RISKY |

Plans gain `## gui` and `## screenshot` steps, classified at parse time
like command steps. Typical loop: screenshot → describe → click the thing
you actually saw → screenshot again to verify.

## Safety model for GUI actions

GUI actions flow through the exact same gates as shell commands:

```
descriptor
   │
   ▼
classify (gui: rules) ──► BLOCKED / READ_ONLY / RISKY
   │
   ▼
decide (mode) ──► auto | ask | deny | dry-run
   │
   ▼
confirm (if needed) ──► operator approves / denies
   │
   ▼
execute ──► audit record (event="gui")
```

Specifics:

* **Typed text is redacted in the audit log.** The audit records
  `gui:type <redacted>`, never the text. The operator still sees the full
  text in the confirmation prompt, so they can verify what is about to be
  typed.
* **`gui:type` with credential-shaped text is BLOCKED.** `password=…`,
  `api_key: …`, auth tokens, private-key material — never typed, any mode.
* **`gui:type` with destructive text is BLOCKED.** `rm -rf`, `mkfs`,
  `format C:`, `shutdown`, etc. — text typed into a focused terminal would
  execute, so it is treated as the destructive command it would become.
* **Unknown `gui:` verbs fail closed** (RISKY, never executed).
  Unparseable coordinates fail closed too.
* **A bare password has no marker** and cannot be detected. Typing a
  password into a login field relies on the operator reading the
  confirmation prompt. When in doubt, deny.
* The allowlist works for GUI actions the same way it does for shell
  commands (`gui:` descriptors are matched as strings). BLOCKED actions can
  never be allowlisted.

## Python API

```python
from aegis.config import Config
from aegis.desktop import GuiExecutor

cfg = Config.load()
gui = GuiExecutor(cfg, confirm=lambda verdict, action: True)
result = gui.run("gui:click 500,300")   # ExecutionResult, like Executor.run

from aegis import screen
img = screen.capture()                  # PIL image, PNG saved to temp file
print(screen.describe(img, router))     # vision description or graceful note
```

## Limits

* Coordinates are absolute screen pixels — the agent must screenshot first
  and never guess them.
* Vision description needs a vision model; a text-only model fails the
  describe call and the agent falls back to the saved screenshot path.
* `pyautogui` needs a real display (X11/Wayland/Windows/macOS). Headless
  machines can import everything but cannot click anything.
