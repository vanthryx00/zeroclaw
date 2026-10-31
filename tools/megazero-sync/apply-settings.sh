#!/usr/bin/env bash
#
# MegaZero sync kit — apply repo-level GitHub settings (description + topics).
#
# Uses the gh CLI (`gh repo edit`). SAFE BY DEFAULT: prints the commands it
# would run; pass --apply to actually run them.
#
# Usage:
#   ./apply-settings.sh                 # dry run over repos.txt
#   ./apply-settings.sh --apply
#   ./apply-settings.sh --repos "a/b c/d" --apply
#   ./apply-settings.sh --desc "Custom description" --apply
#
# Note: GitHub's social-preview IMAGE cannot be set via gh/API — do that in
# each repo's Settings > General > Social preview (upload mega-zero.png).
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLY=0
DESC="Part of the MegaZero stack — a Rust-first autonomous agent runtime. Zero overhead. Zero compromise."
TOPICS="megazero,rust,ai-agent,autonomous-agent"
REPOS_ARG=""

die() { echo "error: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --desc) shift; DESC="${1:?--desc needs a value}" ;;
    --topics) shift; TOPICS="${1:?--topics needs a value}" ;;
    --repos) shift; REPOS_ARG="${1:?--repos needs a value}" ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) die "unknown flag: $1" ;;
  esac
  shift
done

command -v gh >/dev/null || die "gh CLI not found (needed for repo settings)"

repos=()
if [ -n "$REPOS_ARG" ]; then
  # shellcheck disable=SC2206
  repos=($REPOS_ARG)
elif [ -f "$KIT_DIR/repos.txt" ]; then
  while IFS= read -r line; do
    line="${line%%#*}"; line="$(echo "$line" | xargs || true)"
    [ -n "$line" ] && repos+=("$line")
  done < "$KIT_DIR/repos.txt"
fi
[ "${#repos[@]}" -gt 0 ] || die "no repos: fill repos.txt or pass --repos"

topic_args=()
IFS=',' read -ra t <<< "$TOPICS"
for x in "${t[@]}"; do x="$(echo "$x" | xargs)"; [ -n "$x" ] && topic_args+=(--add-topic "$x"); done

echo "== MegaZero settings =="
echo "mode: $([ "$APPLY" = 1 ] && echo APPLY || echo 'DRY RUN')"
echo "desc: $DESC"
echo "topics: $TOPICS"
echo

rc=0
for full in "${repos[@]}"; do
  echo "--- $full ---"
  cmd=(gh repo edit "$full" --description "$DESC" "${topic_args[@]}")
  if [ "$APPLY" = 1 ]; then
    "${cmd[@]}" >/dev/null 2>&1 && echo "  updated" || { echo "  FAILED"; rc=1; }
  else
    printf '  would run: '; printf '%q ' "${cmd[@]}"; echo
  fi
done

echo
[ "$rc" = 0 ] && echo "== done ==" || echo "== done with errors =="
echo "Reminder: upload the social-preview image manually (Settings > General)."
exit "$rc"
