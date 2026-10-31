#!/usr/bin/env python3
"""
JARVIS VOICE SERVER — Debian companion for JARVIS v3  (v1.0.0)
================================================================
Runs on the Debian drive (PROJECT-STINGRAY). Gives the JARVIS page
a TRUE-OFFLINE voice: Whisper hears, Piper speaks, both local.
Binds 127.0.0.1 ONLY — nothing on this box talks to the network.

Endpoints (exactly what JARVIS v3's Voice Lab expects):
  GET  /health      -> {"ok": true, "whisper": "ready|missing|off",
                        "piper": "ready|missing", "model": "tiny"}
  POST /inference   -> multipart form, field "file" (audio) -> {"text": "..."}
  POST /tts         -> JSON {"text": "..."} -> audio/wav bytes

Config (env):
  JARVIS_VOICE_PORT   port to bind            (default 8999)
  JARVIS_WHISPER_MODEL faster-whisper size    (default "tiny" — CPU box;
                        set "base" for accuracy at ~4x the wait)
  JARVIS_PIPER_MODEL  path to the .onnx voice (default: alongside this
                        file under voices/en_US-lessac-medium.onnx)

Deps (installed by install-voice-server.sh into a local venv):
  faster-whisper, piper-tts. ffmpeg not required (PyAV decodes).

Run manually:  python3 jarvis-voice-server.py
Run as a service: jarvis-voice.service (installed by the installer).
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("JARVIS_VOICE_PORT", "8999"))
WHISPER_SIZE = os.environ.get("JARVIS_WHISPER_MODEL", "tiny")
HERE = os.path.dirname(os.path.abspath(__file__))
PIPER_MODEL = os.environ.get(
    "JARVIS_PIPER_MODEL",
    os.path.join(HERE, "voices", "en_US-lessac-medium.onnx"))
PIPER_BIN = os.path.join(os.path.dirname(sys.executable), "piper")
MAX_TEXT = 600           # chars per TTS request — JARVIS sends sentences
MAX_AUDIO = 25 * 1024 * 1024

_whisper = None
_whisper_lock = threading.Lock()


def whisper_status():
    try:
        import faster_whisper  # noqa: F401
        return "ready"
    except Exception:
        return "missing"


def piper_status():
    if os.path.isfile(PIPER_BIN) and os.path.isfile(PIPER_MODEL):
        return "ready"
    return "missing"


def get_whisper():
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel
            _whisper = WhisperModel(WHISPER_SIZE, device="cpu",
                                    compute_type="int8")
        return _whisper


def transcribe(audio_bytes, filename):
    model = get_whisper()
    suffix = os.path.splitext(filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(audio_bytes)
        path = tf.name
    try:
        segments, _info = model.transcribe(path, beam_size=1,
                                           vad_filter=True)
        return "".join(s.text for s in segments).strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def synthesize(text):
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("empty text")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        out = tf.name
    try:
        proc = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", out],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError("piper failed: " +
                               proc.stderr.decode("utf-8", "replace")[:200])
        with open(out, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def parse_multipart(body, content_type):
    """Minimal multipart/form-data extractor: {field: (filename, bytes)}."""
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[len("boundary="):].strip('"')
    if not boundary:
        raise ValueError("no boundary")
    delim = b"--" + boundary.encode()
    fields = {}
    for chunk in body.split(delim):
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        if chunk.endswith(b"--"):
            chunk = chunk[:-2].rstrip(b"\r\n")
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep:
            continue
        head = head.decode("utf-8", "replace")
        name = None
        filename = None
        for token in head.split(";"):
            token = token.strip()
            if token.startswith('name="'):
                name = token[6:-1]
            elif token.startswith('filename="'):
                filename = token[10:-1]
        if name:
            fields[name] = (filename, data)
    return fields


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[voice] %s\n" % (fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", ""):
            self._json(200, {"ok": True,
                             "whisper": whisper_status(),
                             "piper": piper_status(),
                             "model": WHISPER_SIZE,
                             "bind": "127.0.0.1"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_AUDIO:
            return self._json(413, {"error": "payload too large"})
        body = self.rfile.read(length) if length else b""

        if self.path.rstrip("/") == "/inference":
            if whisper_status() != "ready":
                return self._json(503, {"error": "faster-whisper not installed"})
            try:
                fields = parse_multipart(
                    body, self.headers.get("Content-Type", ""))
                if "file" not in fields:
                    return self._json(400, {"error": "missing file field"})
                filename, data = fields["file"]
                text = transcribe(data, filename)
                return self._json(200, {"text": text})
            except Exception as exc:
                return self._json(500, {"error": str(exc)[:300]})

        if self.path.rstrip("/") == "/tts":
            if piper_status() != "ready":
                return self._json(503, {"error": "piper or voice model missing"})
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                wav = synthesize(payload.get("text", ""))
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav)))
                self._cors()
                self.end_headers()
                self.wfile.write(wav)
                return
            except Exception as exc:
                return self._json(500, {"error": str(exc)[:300]})

        return self._json(404, {"error": "not found"})


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("JARVIS voice server on http://127.0.0.1:%d" % PORT)
    print("  whisper: %s (model %s)   piper: %s" %
          (whisper_status(), WHISPER_SIZE, piper_status()))
    print("  JARVIS Voice Lab -> whisper: http://127.0.0.1:%d/inference" % PORT)
    print("  JARVIS Voice Lab -> piper:   http://127.0.0.1:%d/tts" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
