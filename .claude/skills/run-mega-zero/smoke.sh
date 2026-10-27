#!/usr/bin/env bash
# Smoke driver for the mega-zero CLI.
# Builds (if needed) and drives the binary through offline-safe subcommands,
# asserting exit codes. No network or API keys required.
#
# Usage:
#   .claude/skills/run-mega-zero/smoke.sh          # use/append debug build
#   MZ_BIN=target/release/mega-zero  smoke.sh      # drive a prebuilt binary
#
# Exits non-zero on the first failing check.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
BIN="${MZ_BIN:-target/debug/mega-zero}"

if [ ! -x "$BIN" ]; then
  echo ">> building $BIN (first build can exceed 2 min — run in background if it times out)"
  cargo build || { echo "BUILD FAILED"; exit 1; }
fi

fail=0
out="$(mktemp)"

# check <expected_exit> <command...>
check() {
  local want="$1"; shift
  timeout 30 "$BIN" "$@" </dev/null >"$out" 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'ok   (exit %s) %s\n' "$got" "$*"
  else
    printf 'FAIL (exit %s, wanted %s) %s\n' "$got" "$want" "$*"
    sed 's/^/     | /' "$out" | head -8
    fail=1
  fi
}

# grep_out <pattern> <label> — assert last captured output contains pattern
grep_out() {
  if grep -qE "$1" "$out"; then printf 'ok   output contains: %s\n' "$2"
  else printf 'FAIL output missing: %s\n' "$2"; fail=1; fi
}

echo "== mega-zero smoke =="
check 0 --version;         grep_out 'mega_zero [0-9]' 'version string'
check 0 --help;            grep_out 'The fastest, smallest AI assistant' 'help banner'
check 0 providers;         grep_out 'Supported providers' 'provider list'
check 0 status
check 0 doctor;            grep_out 'MegaZero Doctor' 'doctor banner'
check 0 config schema;     grep_out '"' 'schema output'
check 0 completions bash;  grep_out '_mega_zero' 'bash completion function'

# Negative checks: bare subcommands that require a sub-subcommand -> clap exit 2
check 2 models
check 2 integrations

rm -f "$out"
if [ "$fail" -eq 0 ]; then echo "== ALL PASS =="; else echo "== FAILURES ABOVE =="; fi
exit "$fail"
