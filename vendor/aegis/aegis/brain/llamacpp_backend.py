"""llama.cpp backend.

Two transports, tried in order:
  1. OpenAI-compatible HTTP server (``llama-server`` on :8080).
  2. Direct ``llama-cli`` subprocess against a local GGUF file.

Both support incremental streaming.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Iterator, List

from .base import Backend, BackendError, Message

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore


def _decode(line) -> str:
    return line.decode("utf-8", "replace") if isinstance(line, bytes) else line


class LlamaCppBackend(Backend):
    name = "llamacpp"

    def __init__(self, server: str, model_path: str, cli: str = "llama-cli"):
        self.server = server.rstrip("/")
        self.model_path = model_path
        self.cli = cli

    # -- availability ---------------------------------------------------
    def _server_up(self) -> bool:
        if httpx is None:
            return False
        try:
            resp = httpx.get(f"{self.server}/health", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    def _cli_present(self) -> bool:
        from shutil import which
        return which(self.cli) is not None and os.path.isfile(self.model_path)

    def available(self) -> bool:
        return self._server_up() or self._cli_present()

    # -- generation -----------------------------------------------------
    def generate(self, messages: List[Message], *, temperature=0.2,
                 max_tokens=2048, timeout=120.0) -> str:
        if self._server_up():
            return self._generate_server(messages, temperature, max_tokens, timeout)
        if self._cli_present():
            return self._generate_cli(messages, temperature, max_tokens, timeout)
        raise BackendError("llama.cpp is not available (no server, no CLI+model)")

    def generate_stream(self, messages: List[Message], *, temperature=0.2,
                        max_tokens=2048, timeout=120.0) -> Iterator[str]:
        if self._server_up():
            yield from self._stream_server(messages, temperature, max_tokens, timeout)
            return
        if self._cli_present():
            yield from self._stream_cli(messages, temperature, max_tokens, timeout)
            return
        raise BackendError("llama.cpp is not available (no server, no CLI+model)")

    # -- server transport -----------------------------------------------
    def _payload(self, messages, temperature, max_tokens, stream) -> dict:
        return {
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def _generate_server(self, messages, temperature, max_tokens, timeout) -> str:
        try:
            resp = httpx.post(f"{self.server}/v1/chat/completions",
                              json=self._payload(messages, temperature, max_tokens, False),
                              timeout=timeout)
            resp.raise_for_status()
        except Exception as exc:
            raise BackendError(f"llama.cpp server request failed: {exc}") from exc
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _stream_server(self, messages, temperature, max_tokens, timeout) -> Iterator[str]:
        payload = self._payload(messages, temperature, max_tokens, True)
        try:
            with httpx.stream("POST", f"{self.server}/v1/chat/completions",
                              json=payload, timeout=timeout) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    line = _decode(raw).strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        obj = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or [{}]
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"llama.cpp stream failed: {exc}") from exc

    # -- CLI transport ---------------------------------------------------
    def _cli_command(self, messages, temperature, max_tokens) -> List[str]:
        return [
            self.cli, "-m", self.model_path, "-p", _flatten(messages),
            "-n", str(max_tokens), "--temp", str(temperature),
            "-no-cnv", "--log-disable",
        ]

    def _generate_cli(self, messages, temperature, max_tokens, timeout) -> str:
        try:
            proc = subprocess.run(self._cli_command(messages, temperature, max_tokens),
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise BackendError("llama-cli timed out") from exc
        if proc.returncode != 0:
            raise BackendError(f"llama-cli failed: {proc.stderr[:400]}")
        return proc.stdout.strip()

    def _stream_cli(self, messages, temperature, max_tokens, timeout) -> Iterator[str]:
        """Stream stdout line by line. llama-cli emits per-token output when it
        is not buffering, so this gives coarse but real incremental text."""
        try:
            proc = subprocess.Popen(
                self._cli_command(messages, temperature, max_tokens),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
        except OSError as exc:
            raise BackendError(f"llama-cli could not start: {exc}") from exc

        produced = False
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if line:
                    produced = True
                    yield line
        finally:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise BackendError("llama-cli timed out")
            if proc.returncode != 0 and not produced:
                err = proc.stderr.read() if proc.stderr else ""
                raise BackendError(f"llama-cli failed: {err[:400]}")

    def info(self) -> str:
        if self._server_up():
            return f"llamacpp(server) @ {self.server}"
        return f"llamacpp(cli):{self.model_path}"


def _flatten(messages: List[Message]) -> str:
    """Render messages into a single prompt for the CLI transport."""
    parts = []
    for m in messages:
        if m.role == "system":
            parts.append(f"[SYSTEM]\n{m.content}\n")
        elif m.role == "user":
            parts.append(f"[USER]\n{m.content}\n")
        else:
            parts.append(f"[ASSISTANT]\n{m.content}\n")
    parts.append("[ASSISTANT]\n")
    return "\n".join(parts)
