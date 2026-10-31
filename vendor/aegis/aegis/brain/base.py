"""Model backend abstraction.

Backends expose two generation paths:

* :meth:`Backend.generate` — blocking, returns the whole reply.
* :meth:`Backend.generate_stream` — yields text chunks as they are produced.

The default :meth:`generate_stream` is *not* a stub: it calls ``generate`` and
yields the result once, so every backend supports streaming even if it has no
native incremental transport. Backends that can stream (Ollama, llama.cpp
server/CLI) override it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class BackendError(RuntimeError):
    pass


class Backend:
    """Base class for a local inference backend."""

    name = "base"

    #: Whether this backend can take an image (vision model). Backends that
    #: can describe images set this and implement :meth:`describe_image`.
    supports_vision = False

    def available(self) -> bool:
        raise NotImplementedError

    def generate(
        self,
        messages: List[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> str:
        raise NotImplementedError

    def generate_stream(
        self,
        messages: List[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> Iterator[str]:
        """Yield reply chunks. Default: generate fully, then yield once.

        Errors must be raised as :class:`BackendError` — either before the first
        chunk (so the router can fail over) or mid-stream (surfaced to the user).
        """
        yield self.generate(
            messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout
        )

    def describe_image(self, image_b64: str, prompt: str,
                       *, temperature: float = 0.2,
                       max_tokens: int = 2048,
                       timeout: float = 120.0) -> str:
        """Describe a base64-encoded PNG. Vision backends override this."""
        raise BackendError(f"backend {self.name} has no vision support")

    def info(self) -> str:
        return self.name
