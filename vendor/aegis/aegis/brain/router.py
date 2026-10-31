"""Backend router with failover.

Builds the configured backends and picks the first available one. If the
preferred backend fails *before* producing any output, generation fails over to
the next. A failure mid-stream is surfaced instead of silently truncating the
reply — a half answer that looks complete is worse than an error.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from .base import Backend, BackendError, Message
from .ollama_backend import OllamaBackend
from .llamacpp_backend import LlamaCppBackend


class BackendRouter:
    def __init__(self, cfg):
        self.cfg = cfg
        self.backends: List[Backend] = []
        self.active: Optional[Backend] = None
        self._build()

    def _build(self) -> None:
        m = self.cfg.model
        for name in m.backends:
            if name == "ollama":
                self.backends.append(OllamaBackend(m.ollama_host, m.ollama_model))
            elif name == "llamacpp":
                self.backends.append(
                    LlamaCppBackend(m.llamacpp_server, m.llamacpp_model_path, m.llamacpp_cli)
                )

    def select(self) -> Optional[Backend]:
        for backend in self.backends:
            if backend.available():
                self.active = backend
                return backend
        return None

    def _order(self) -> List[Backend]:
        if self.active is None:
            self.select()
        return [b for b in ([self.active] + [x for x in self.backends if x is not self.active])
                if b is not None]

    def _kwargs(self, kwargs: dict) -> dict:
        return {
            "temperature": kwargs.get("temperature", self.cfg.model.temperature),
            "max_tokens": kwargs.get("max_tokens", self.cfg.model.max_tokens),
            "timeout": kwargs.get("timeout", self.cfg.model.request_timeout),
        }

    def generate(self, messages: List[Message], **kwargs) -> str:
        last_error: Optional[Exception] = None
        for backend in self._order():
            try:
                return backend.generate(messages, **self._kwargs(kwargs))
            except BackendError as exc:
                last_error = exc
                continue
        raise BackendError(
            f"no backend could generate a response: {last_error or 'none available'}"
        )

    def generate_stream(self, messages: List[Message], **kwargs) -> Iterator[str]:
        """Stream from the first backend that produces a first chunk.

        Failover happens only before the first chunk. Once tokens are flowing we
        commit to that backend: restarting mid-reply would duplicate text.
        """
        last_error: Optional[Exception] = None
        for backend in self._order():
            stream = backend.generate_stream(messages, **self._kwargs(kwargs))
            try:
                first = next(stream)
            except StopIteration:
                return  # backend returned an empty reply successfully
            except BackendError as exc:
                last_error = exc
                continue
            yield first
            yield from stream  # mid-stream BackendError propagates deliberately
            return
        raise BackendError(
            f"no backend could generate a response: {last_error or 'none available'}"
        )

    def describe_image(self, image_b64: str, prompt: str, **kwargs) -> str:
        """Describe a screenshot via the first vision-capable backend."""
        last_error: Optional[Exception] = None
        for backend in self.backends:
            if not getattr(backend, "supports_vision", False):
                continue
            try:
                return backend.describe_image(image_b64, prompt,
                                              **self._kwargs(kwargs))
            except BackendError as exc:
                last_error = exc
                continue
        raise BackendError(
            f"no vision-capable backend: {last_error or 'none configured'}"
        )

    def status(self) -> str:
        lines = []
        for backend in self.backends:
            mark = "up" if backend.available() else "down"
            lines.append(f"  [{mark}] {backend.info()}")
        if self.active:
            lines.append(f"active: {self.active.info()}")
        else:
            lines.append("active: none (is the local model server running?)")
        return "\n".join(lines)
