"""Ollama backend (default). Talks to the local Ollama daemon over HTTP."""

from __future__ import annotations

import json
from typing import Iterator, List

from .base import Backend, BackendError, Message

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore


def _decode(line) -> str:
    return line.decode("utf-8", "replace") if isinstance(line, bytes) else line


class OllamaBackend(Backend):
    name = "ollama"

    #: Ollama's /api/chat accepts an ``images`` list per message. Whether the
    #: *configured model* can use it depends on the model — a text-only model
    #: answers with an error, which describe_image surfaces as BackendError.
    supports_vision = True

    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    def available(self) -> bool:
        if httpx is None:
            return False
        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        if httpx is None:
            return []
        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=5.0)
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception:
            return []

    def _payload(self, messages: List[Message], temperature: float,
                 max_tokens: int, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

    def generate(self, messages: List[Message], *, temperature=0.2,
                 max_tokens=2048, timeout=120.0) -> str:
        if httpx is None:
            raise BackendError("httpx is not installed")
        try:
            resp = httpx.post(f"{self.host}/api/chat",
                              json=self._payload(messages, temperature, max_tokens, False),
                              timeout=timeout)
            resp.raise_for_status()
        except Exception as exc:
            raise BackendError(f"ollama request failed: {exc}") from exc
        data = resp.json()
        return (data.get("message") or {}).get("content", "")

    def generate_stream(self, messages: List[Message], *, temperature=0.2,
                        max_tokens=2048, timeout=120.0) -> Iterator[str]:
        if httpx is None:
            raise BackendError("httpx is not installed")
        payload = self._payload(messages, temperature, max_tokens, True)
        try:
            with httpx.stream("POST", f"{self.host}/api/chat", json=payload,
                              timeout=timeout) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    line = _decode(raw).strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise BackendError(f"ollama error: {data['error']}")
                    chunk = (data.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"ollama stream failed: {exc}") from exc

    def describe_image(self, image_b64: str, prompt: str,
                         *, temperature: float = 0.2,
                         max_tokens: int = 2048,
                         timeout: float = 120.0) -> str:
        """Send one screenshot to the configured model and return its reply.

        Uses Ollama's ``/api/chat`` ``images`` field. The configured model
        must be a vision model (e.g. llava, moondream); a text-only model
        fails here and the caller degrades gracefully.
        """
        if httpx is None:
            raise BackendError("httpx is not installed")
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            resp = httpx.post(f"{self.host}/api/chat", json=payload,
                              timeout=timeout)
            resp.raise_for_status()
        except Exception as exc:
            raise BackendError(f"ollama vision request failed: {exc}") from exc
        data = resp.json()
        if data.get("error"):
            raise BackendError(f"ollama vision error: {data['error']}")
        return (data.get("message") or {}).get("content", "")

    def info(self) -> str:
        return f"ollama:{self.model} @ {self.host}"
