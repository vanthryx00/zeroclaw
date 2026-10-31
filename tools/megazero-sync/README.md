# MegaZero Sync Kit

Apply the **MegaZero** identity to many repos at once: a `CLAUDE.md`
engineering protocol, a profile `README.md`, and GitHub repo settings
(description + topics).

Everything is **dry-run by default** and never force-pushes.

## Contents

| File | Purpose |
| --- | --- |
| `sync.sh` | Clone each repo, drop in `CLAUDE.md` + `README.md`, commit on a branch, optionally push / open PR |
| `apply-settings.sh` | Set each repo's description + topics via `gh repo edit` |
| `assets/CLAUDE.md` | The MegaZero engineering protocol (copied verbatim into each repo) |
| `assets/PROFILE_README.md` | Profile README template (`{{OWNER}}` / `{{REPO}}` / `{{DESCRIPTION}}` placeholders) |
| `repos.txt` | Your target list — one `owner/repo` per line |

## Prerequisites

- `git`
- [`gh`](https://cli.github.com/) CLI, authenticated (`gh auth login`) —
  required for cloning private repos, for `--pr`, and for `apply-settings.sh`.

## Usage

1. List your repos in `repos.txt` (one `owner/repo` per line).
2. Preview (no writes):
   ```bash
   ./sync.sh
   ./apply-settings.sh
   ```
3. Apply the files — pushes a `chore/megazero-sync` branch to each repo:
   ```bash
   ./sync.sh --push          # add --pr to also open a PR per repo
   ```
   Or commit straight to the default branch (no branch/PR):
   ```bash
   ./sync.sh --push --direct
   ```
4. Apply settings:
   ```bash
   ./apply-settings.sh --apply
   ```

### Handy flags

- `sync.sh --only-readme` / `--only-claude` — sync just one file.
- `sync.sh --branch <name>` — use a different branch name.
- `sync.sh --repos "a/b c/d"` — override `repos.txt` inline.
- `apply-settings.sh --desc "..." --topics "a,b,c"` — override defaults.

## Notes

- **Social-preview image** can't be set via `gh`/API — upload
  `mega-zero.png` manually in each repo's *Settings → General → Social
  preview*. `apply-settings.sh` reminds you.
- The kit respects an existing repo: `sync.sh` reports "no changes" when the
  files already match, and never overwrites history.
- Editing the templates in `assets/` changes what every future sync writes.
