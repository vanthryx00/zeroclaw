#!/usr/bin/env bash
#
# MegaZero sync kit — apply MegaZero identity files to a set of repos.
#
# For each repo it: clones, drops in CLAUDE.md + README.md (profile template,
# rendered with the repo's name/owner/description), commits on a branch, and
# (optionally) pushes and opens a PR.
#
# SAFE BY DEFAULT: without --push it only renders + shows the plan (dry run).
# It never force-pushes and never commits straight to the default branch
# unless you pass --direct.
#
# Usage:
#   ./sync.sh                         # dry run over repos.txt
#   ./sync.sh --push                  # push a sync branch to each repo
#   ./sync.sh --push --pr             # ...and open a PR for each
#   ./sync.sh --push --direct         # commit to the default branch directly
#   ./sync.sh --repos "a/b c/d" --push
#   ./sync.sh --only-readme --push    # skip CLAUDE.md, sync README only
#   ./sync.sh --only-claude --push    # skip README, sync CLAUDE.md only
#
# Repo list: one "owner/repo" per line in repos.txt (# comments allowed),
# or pass --repos "owner/repo owner/repo".
#
# Requires: git, and (for cloning private repos / --pr) the gh CLI, authed.
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSETS="$KIT_DIR/assets"
BRANCH="chore/megazero-sync"
PUSH=0; OPEN_PR=0; DIRECT=0; ONLY_README=0; ONLY_CLAUDE=0
REPOS_ARG=""

die() { echo "error: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH=1 ;;
    --pr) OPEN_PR=1 ;;
    --direct) DIRECT=1 ;;
    --only-readme) ONLY_README=1 ;;
    --only-claude) ONLY_CLAUDE=1 ;;
    --branch) shift; BRANCH="${1:?--branch needs a value}" ;;
    --repos) shift; REPOS_ARG="${1:?--repos needs a value}" ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) die "unknown flag: $1" ;;
  esac
  shift
done

[ -f "$ASSETS/CLAUDE.md" ] || die "missing $ASSETS/CLAUDE.md"
[ -f "$ASSETS/PROFILE_README.md" ] || die "missing $ASSETS/PROFILE_README.md"
command -v git >/dev/null || die "git not found"

# Build the repo list.
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

clone_url() {  # prefer gh (handles auth); fall back to https
  if command -v gh >/dev/null; then echo "gh:$1"; else echo "https://github.com/$1.git"; fi
}

render_readme() {  # $1=owner $2=repo -> stdout
  local owner="$1" repo="$2"
  sed -e "s|{{OWNER}}|$owner|g" \
      -e "s|{{REPO}}|$repo|g" \
      -e "s|{{DESCRIPTION}}|Part of the MegaZero stack.|g" \
      "$ASSETS/PROFILE_README.md"
}

echo "== MegaZero sync =="
echo "mode: $([ "$PUSH" = 1 ] && echo PUSH || echo 'DRY RUN (no push)')$([ "$DIRECT" = 1 ] && echo ' +direct' || true)$([ "$OPEN_PR" = 1 ] && echo ' +pr' || true)"
echo "branch: $BRANCH"
echo "files: $([ "$ONLY_README" = 1 ] || echo CLAUDE.md) $([ "$ONLY_CLAUDE" = 1 ] || echo README.md)"
echo "repos: ${repos[*]}"
echo

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
rc=0

for full in "${repos[@]}"; do
  owner="${full%%/*}"; repo="${full##*/}"
  [ "$owner" != "$full" ] && [ -n "$repo" ] || { echo "SKIP $full (not owner/repo)"; rc=1; continue; }
  echo "--- $full ---"
  dest="$work/$repo"

  if [ "$PUSH" = 0 ]; then
    # Dry run: just show what would be written, and prove templating works.
    echo "  would clone $full"
    [ "$ONLY_README" = 1 ] || echo "  would write CLAUDE.md ($(wc -l < "$ASSETS/CLAUDE.md") lines)"
    if [ "$ONLY_CLAUDE" = 0 ]; then
      echo "  would write README.md; preview:"
      render_readme "$owner" "$repo" | sed 's/^/    | /' | head -6
    fi
    echo "  would commit on '$BRANCH'$([ "$DIRECT" = 1 ] && echo ' (direct to default)' || true)$([ "$OPEN_PR" = 1 ] && echo ' and open a PR' || true)"
    continue
  fi

  url="$(clone_url "$full")"
  if [ "${url#gh:}" != "$url" ]; then
    gh repo clone "${url#gh:}" "$dest" -- --depth 1 >/dev/null 2>&1 || { echo "  FAILED clone"; rc=1; continue; }
  else
    git clone --depth 1 "$url" "$dest" >/dev/null 2>&1 || { echo "  FAILED clone"; rc=1; continue; }
  fi

  git -C "$dest" checkout -b "$BRANCH" >/dev/null 2>&1 || \
    { [ "$DIRECT" = 1 ] || { echo "  FAILED branch (exists?)"; rc=1; continue; }; }

  [ "$ONLY_README" = 1 ] || cp "$ASSETS/CLAUDE.md" "$dest/CLAUDE.md"
  [ "$ONLY_CLAUDE" = 1 ] || render_readme "$owner" "$repo" > "$dest/README.md"

  if git -C "$dest" diff --quiet; then
    echo "  no changes (already in sync)"; continue
  fi
  git -C "$dest" add CLAUDE.md README.md 2>/dev/null || git -C "$dest" add -A
  git -C "$dest" -c user.name="MegaZero Sync" -c user.email="mega_zero_bot@users.noreply.github.com" \
    commit -q -m "chore: sync MegaZero identity (CLAUDE.md + README)"
  target_branch="$BRANCH"; [ "$DIRECT" = 1 ] && target_branch="$(git -C "$dest" symbolic-ref --short HEAD)"
  git -C "$dest" push -u origin "$target_branch" >/dev/null 2>&1 || { echo "  FAILED push"; rc=1; continue; }
  echo "  pushed $target_branch"

  if [ "$OPEN_PR" = 1 ] && [ "$DIRECT" = 0 ] && command -v gh >/dev/null; then
    gh -R "$full" pr create --fill --head "$BRANCH" >/dev/null 2>&1 && echo "  opened PR" || echo "  PR step skipped"
  fi
done

echo
[ "$rc" = 0 ] && echo "== done ==" || echo "== done with errors (see above) =="
exit "$rc"
