#!/usr/bin/env python3
"""
JARVIS COMMAND BRIDGE — Debian companion for JARVIS v3.1  (v1.0.0)
==================================================================
Gives JARVIS hands on THIS machine, behind three gates:

  READ tier   curated read-only commands run immediately
              (df, free, uptime, ls, systemctl status, ollama list…)
  WRITE tier  state-changing commands run ONLY with approved=true
              in the request — JARVIS shows Dubbz an approval card
              first. No approval, no execution. No exceptions.
  DENY tier   hard-refused, approval cannot override: shells,
              interpreters, sudo, destructive disk tools, user
              management, package installs, shell metacharacters.

Design rules:
  - Binds 127.0.0.1 only. One command at a time. No shell — argv
    only (subprocess, shell=False). Single simple commands: no
    pipes, redirects, or chaining, ever.
  - File-reading/writing commands are path-guarded to $HOME, /tmp,
    /var/log, and sensitive files (.env, keys, shadow…) are denied
    by name even inside allowed roots.
  - EVERY request is appended to audit.log beside this file:
    time, command, tier, decision, exit code.

Endpoints:
  GET  /health  -> {"ok": true, "commands_run": N, "tiers": {...}}
  GET  /audit   -> {"entries": [ ...last 50 audit records... ]}
  POST /run     -> {"command": "df -h", "approved": false}
                -> {"ok": true, "tier": "read", "exit_code": 0,
                    "stdout": "...", "stderr": "..."}
                -> {"needs_approval": true, "tier": "write", ...}
                -> {"denied": true, "reason": "..."}

Config (env): JARVIS_BRIDGE_PORT (default 9000).
Stdlib only. No venv. Run via jarvis-bridge.service.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("JARVIS_BRIDGE_PORT", "9000"))
HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_PATH = os.path.join(HERE, "audit.log")
ALLOWED_ROOTS = (HOME, "/tmp", "/var/log")
SENSITIVE = (".env", "id_rsa", "id_ed25519", "id_ecdsa", "shadow",
             "gshadow", ".ssh", ".aws", "credentials", ".gnupg")
MAX_OUT = 8000
_exec_lock = threading.Lock()
_counters = {"ran": 0, "denied": 0, "needs_approval": 0}

READ_BINARIES = {"df", "free", "uptime", "uname", "hostname", "whoami",
                 "id", "date", "ls", "lsblk", "ss", "ps", "du",
                 "cat", "head", "tail", "grep"}
WRITE_BINARIES = {"mkdir", "touch", "cp", "mv", "git"}
DENY_BINARIES = {"rm", "dd", "shred", "mkfs", "fdisk", "parted", "sudo",
                 "su", "passwd", "useradd", "userdel", "usermod", "chown",
                 "chmod", "mount", "umount", "shutdown", "reboot",
                 "poweroff", "halt", "apt", "apt-get", "dpkg", "snap",
                 "pip", "pip3", "python", "python3", "bash", "sh", "zsh",
                 "perl", "ruby", "node", "curl", "wget", "nc", "ncat",
                 "socat", "iptables", "nft", "crontab", "at", "kill",
                 "killall", "pkill", "xargs", "find", "tee", "eval",
                 "exec", "env", "printenv"}
META_CHARS = set(";&|><`$\\!\n\r")
SYSTEMCTL_READ = {"status", "is-active", "is-enabled", "show", "cat"}
SYSTEMCTL_WRITE = {"start", "stop", "restart", "enable", "disable"}
WRITABLE_UNITS = {"ollama", "ollama.service",
                  "jarvis-voice", "jarvis-voice.service"}
OLLAMA_READ = {"list", "ps", "show"}
OLLAMA_WRITE = {"pull", "rm", "cp"}
GIT_READ = {"status", "log", "diff", "branch", "remote"}
GIT_WRITE = {"pull", "add", "commit", "checkout", "stash", "fetch"}
PATH_GUARDED = {"cat", "head", "tail", "grep", "ls", "du",
                "mkdir", "touch", "cp", "mv"}


def audit(command, tier, decision, exit_code=None):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "command": command, "tier": tier, "decision": decision,
           "exit_code": exit_code}
    try:
        with open(AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    return rec


def path_ok(arg):
    """True if a path-like arg resolves inside allowed roots and is
    not a sensitive file. Non-path args pass."""
    if not arg or arg.startswith("-"):
        return True
    p = arg
    if p.startswith("~"):
        p = HOME + p[1:]
    real = os.path.realpath(os.path.join(HOME, p) if not os.path.isabs(p) else p)
    base = os.path.basename(real)
    if base in SENSITIVE or any(s in real.split(os.sep) for s in (".ssh", ".aws", ".gnupg")):
        return False
    return any(real == r or real.startswith(r + os.sep) for r in ALLOWED_ROOTS)


def classify(argv):
    """-> (tier, reason) where tier in read|write|deny."""
    if not argv:
        return "deny", "empty command"
    raw = " ".join(argv)
    if any(c in META_CHARS for c in raw):
        return "deny", "shell metacharacters are not allowed — one simple command only"
    binary = os.path.basename(argv[0])
    args = argv[1:]
    if binary in DENY_BINARIES:
        return "deny", "'%s' is on the hard denylist (shells, interpreters, sudo, destructive and system tools)" % binary
    if binary == "systemctl":
        verb = args[0] if args else ""
        if verb in SYSTEMCTL_READ:
            return "read", ""
        if verb in SYSTEMCTL_WRITE:
            unit = args[1] if len(args) > 1 else ""
            if unit in WRITABLE_UNITS:
                return "write", ""
            return "deny", "only these units may be changed: ollama, jarvis-voice"
        return "deny", "systemctl verb not allowed: %s" % verb
    if binary == "ollama":
        verb = args[0] if args else ""
        if verb in OLLAMA_READ:
            return "read", ""
        if verb in OLLAMA_WRITE:
            return "write", ""
        return "deny", "ollama verb not allowed: %s" % verb
    if binary == "git":
        gargs = list(args)
        if gargs[:1] == ["-C"] and len(gargs) >= 2:
            if not path_ok(gargs[1]):
                return "deny", "git -C path outside allowed roots: %s" % gargs[1]
            gargs = gargs[2:]
        verb = gargs[0] if gargs else ""
        if verb in GIT_READ:
            return "read", ""
        if verb in GIT_WRITE:
            return "write", ""
        return "deny", "git verb not allowed: %s" % verb
    if binary == "ping":
        return "read", ""
    if binary == "journalctl":
        return "read", ""
    if binary in PATH_GUARDED:
        for a in args:
            if not path_ok(a):
                return "deny", "path outside allowed roots or sensitive file: %s" % a
        if binary in WRITE_BINARIES:
            return "write", ""
        return "read", ""
    if binary in READ_BINARIES:
        return "read", ""
    if binary in WRITE_BINARIES:
        return "write", ""
    return "deny", "'%s' is not on the command allowlist" % binary


def normalize(binary, args):
    """Small transparent fix-ups, visible in the audit via argv echo."""
    args = list(args)
    if binary == "ping" and "-c" not in args:
        args = ["-c", "3"] + args
    if binary == "ping" and "-c" in args:
        i = args.index("-c")
        try:
            if int(args[i + 1]) > 5:
                args[i + 1] = "5"
        except (ValueError, IndexError):
            pass
    if binary == "journalctl":
        if "--no-pager" not in args:
            args.append("--no-pager")
        if "-n" not in args and "--lines" not in args:
            args += ["-n", "50"]
    return args


TIMEOUTS = {"ollama": 600}
DEFAULT_TIMEOUT = 30


def run_command(command, approved):
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        audit(command, "deny", "parse-error")
        _counters["denied"] += 1
        return {"denied": True, "reason": "could not parse: %s" % exc}
    tier, reason = classify(argv)
    if tier == "deny":
        audit(command, "deny", reason)
        _counters["denied"] += 1
        return {"denied": True, "reason": reason}
    if tier == "write" and not approved:
        audit(command, "write", "needs-approval")
        _counters["needs_approval"] += 1
        return {"needs_approval": True, "tier": "write",
                "command": command,
                "note": "state-changing command — the user must approve it in JARVIS first"}
    binary = os.path.basename(argv[0])
    args = normalize(binary, argv[1:])
    timeout = TIMEOUTS.get(binary, DEFAULT_TIMEOUT)
    started = time.time()
    with _exec_lock:
        try:
            proc = subprocess.run([binary] + args, shell=False, cwd=HOME,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  timeout=timeout)
            out = proc.stdout.decode("utf-8", "replace")[:MAX_OUT]
            err = proc.stderr.decode("utf-8", "replace")[:MAX_OUT]
            code = proc.returncode
        except subprocess.TimeoutExpired:
            out, err, code = "", "timed out after %ds" % timeout, -1
        except FileNotFoundError:
            out, err, code = "", "binary not found: %s" % binary, 127
        except Exception as exc:  # never crash the bridge on one command
            out, err, code = "", str(exc)[:300], -1
    _counters["ran"] += 1
    audit(" ".join([binary] + args), tier,
          "approved-ran" if (tier == "write") else "ran", code)
    return {"ok": code == 0, "tier": tier, "exit_code": code,
            "stdout": out, "stderr": err,
            "duration_ms": int((time.time() - started) * 1000)}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] %s\n" % (fmt % args))

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
        path = self.path.rstrip("/")
        if path in ("/health", ""):
            return self._json(200, {
                "ok": True, "bind": "127.0.0.1",
                "commands_run": _counters["ran"],
                "denied": _counters["denied"],
                "approvals_requested": _counters["needs_approval"],
                "tiers": {"read_binaries": sorted(READ_BINARIES |
                            {"systemctl", "ollama", "git", "ping",
                             "journalctl"}),
                          "write_binaries": sorted(WRITE_BINARIES),
                          "writable_units": sorted(WRITABLE_UNITS)}})
        if path == "/audit":
            entries = []
            try:
                with open(AUDIT_PATH, encoding="utf-8") as fh:
                    lines = fh.readlines()[-50:]
                entries = [json.loads(l) for l in lines if l.strip()]
            except OSError:
                entries = []
            return self._json(200, {"entries": entries})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/run":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            return self._json(400, {"error": "bad json"})
        command = (payload.get("command") or "").strip()
        if not command:
            return self._json(400, {"error": "missing command"})
        if len(command) > 500:
            return self._json(400, {"error": "command too long"})
        result = run_command(command, bool(payload.get("approved")))
        return self._json(200, result)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("JARVIS command bridge on http://127.0.0.1:%d" % PORT)
    print("  tiers: read=%d commands free, write needs approval, deny is hard" %
          len(READ_BINARIES))
    print("  audit: %s" % AUDIT_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
