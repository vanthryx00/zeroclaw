"""Eyes: screenshot capture and vision description.

Screenshot capture is READ_ONLY — it inspects state and has no side effects
beyond writing the PNG file the operator asked for. Vision description is
best-effort: if no vision-capable backend is configured, :func:`describe`
returns a clear message instead of raising, so the agent can keep working
with just the saved screenshot path.

Optional dependencies (all lazy — importing this module never fails because
one is missing):

* ``mss`` — fast screenshot capture (preferred).
* ``Pillow`` — image handling and the ``ImageGrab`` fallback.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from typing import Optional

try:
    from PIL import Image as _PILImage
except ModuleNotFoundError:  # pragma: no cover - Pillow absent
    _PILImage = None  # type: ignore

#: Prompt sent to the vision backend with every screenshot.
DESCRIBE_PROMPT = (
    "Describe what is visible on this desktop screenshot: open windows, "
    "their titles, buttons and text fields, and what the user appears to "
    "be doing. Be concrete. If a dialog is open, quote its text."
)

#: What describe() returns when no vision-capable backend is configured.
NO_VISION_MESSAGE = (
    "No vision backend is configured — the screenshot was saved, but I "
    "cannot describe it without a vision-capable model (e.g. an Ollama "
    "vision model such as llava or moondream). Open the saved file to see it."
)


class ScreenError(RuntimeError):
    """Raised when no screenshot backend works (no display, no deps)."""


def _require_pil():
    if _PILImage is None:
        raise ScreenError(
            "Pillow is not installed — run: pip install Pillow"
        )
    return _PILImage


def default_screenshot_path() -> str:
    """A fresh temp path for a screenshot PNG (never overwrites)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(
        tempfile.gettempdir(), f"aegis-screenshot-{stamp}-{os.getpid()}.png"
    )


def capture(path: Optional[str] = None):
    """Capture the primary monitor and save it as a PNG.

    Tries ``mss`` first, falls back to ``PIL.ImageGrab``. Returns the
    ``PIL.Image``; the PNG is written to *path* (a fresh temp file when
    *path* is ``None``). Raises :class:`ScreenError` if neither backend
    works (headless machine, no display, missing deps).
    """
    Image = _require_pil()
    target = path or default_screenshot_path()

    # Preferred backend: mss (fast, no display server round-trip beyond X).
    try:
        import mss  # lazy: optional dependency

        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])  # monitors[0] is "all"
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            img.save(target, "PNG")
            return img
    except Exception:
        pass  # fall through to ImageGrab

    # Fallback: Pillow's ImageGrab (X11 / macOS / Windows).
    try:
        from PIL import ImageGrab  # lazy: only needed on this path

        img = ImageGrab.grab()
        img.save(target, "PNG")
        return img
    except Exception as exc:
        raise ScreenError(
            f"screenshot failed (mss and ImageGrab both failed): {exc}"
        ) from exc


def screenshot_b64(path: Optional[str] = None) -> str:
    """Capture the screen and return the PNG as a base64 string."""
    img = capture(path)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def describe(image, brain=None, prompt: str = DESCRIBE_PROMPT) -> str:
    """Ask a vision-capable backend to describe a screenshot.

    *image* is a ``PIL.Image`` (or a base64 PNG string). *brain* is
    anything exposing ``describe_image(image_b64, prompt)`` — the
    :class:`~aegis.brain.router.BackendRouter` does. With no vision backend
    configured this returns :data:`NO_VISION_MESSAGE` instead of raising.
    Backend failures are also downgraded to a message: a failed description
    must never crash the agent loop.
    """
    if brain is None:
        return NO_VISION_MESSAGE
    describe_image = getattr(brain, "describe_image", None)
    if describe_image is None:
        return NO_VISION_MESSAGE
    try:
        if hasattr(image, "save"):
            buf = io.BytesIO()
            image.save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        else:
            b64 = str(image)
        return describe_image(b64, prompt)
    except Exception as exc:
        return f"Vision description failed: {exc}"
