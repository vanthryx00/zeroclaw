# AegisOS — Project State (compacted)

> Single-file compressed context for this project. Read this first to resume
> work without the full conversation history.

## What this is

**AegisOS** = a custom Ubuntu/Cubic-based Linux distribution with an **offline
AI copilot ("Aegis")** for cybersecurity learning, everyday automation, privacy,
and system rescue. No cloud, no API keys, no telemetry.

## Decisions locked in (from the conversation)

| Decision | Choice |
|----------|--------|
| Base distro | Ubuntu + Cubic |
| AI runtime | Ollama (default) + llama.cpp (fallback), auto-failover router |
| Execution | configurable modes: `confirm` / `auto_safe` / `auto_full` / `dry_run` |
| Interfaces | phased: CLI → TUI (Textual) → GUI (PySide6) — all present |
| Privacy | amnesic + Tor-routed + Whonix variant for USB use |
| Rescue | diagnose/repair an installed system from the live USB |
| Setup | first-boot wizard: privacy profile + RAM-sized model |

## Phase 1.95 additions (findings / reports / tamper-evidence / rescue)

New modules: `store.py` (shared JSONL store), `findings.py`, `notes.py`,
`tasks.py`, `report.py` (Markdown + self-contained HTML), `diag.py` (hardware
diagnostics). `audit.py` is now hash-chained (each record stores `prev` + `hash`;
`verify()` names the first broken record, `seal()` pins the head hash).
`privacy.py` gained `dns_leak_test()`, `TorController.new_identity()` and
`PanicController`. `rescue.py` gained `guess_os()`, `detect_installed_os()`,
`diagnose_windows()`, `diagnose_macos()` and `auto_diagnose()`.

New CLI: `finding`, `note`, `task`, `report`, `diag`; `audit show|verify|seal`;
`privacy newid|leaktest|panic`. Full 40-item backlog in `docs/UPGRADES.md`.

## Module map (`aegis/aegis/`)

| File | Role |
|------|------|
| `config.py` | TOML+env config, 4 sections: model/safety/interface/privacy |
| `safety.py` | command classifier (read-only/safe-write/risky/offensive/BLOCKED), scope enforcement, mode decision |
| `executor.py` | **only** shell choke point; confirm + allowlist + audit every run |
| `approval.py` | `ApprovalGate`: bridges worker-thread confirms to the UI thread; `ApprovalOutcome` (deny/allow/allow-always) |
| `allowlist.py` | per-command "always allow" rules; exact-match by default, level-aware, refuses offensive/BLOCKED |
| `store.py` | shared `JsonlStore` + `new_id()` used by findings/notes/tasks/allowlist |
| `audit.py` | append-only JSONL log, hash-chained (`verify`/`seal`) |
| `findings.py` `notes.py` `tasks.py` `report.py` `diag.py` | engagement records, notes, task board, report renderer, hardware diagnostics |
| `agent.py` | ReAct loop: model → ```` ```aegis-command ```` block → execute → observe → answer |
| `context.py` | non-sensitive system snapshot for the prompt |
| `memory.py` | bounded transcript + lesson store |
| `prompts.py` | system prompt (incl. privacy/rescue guidance + ethics) |
| `privacy.py` | leak auditor (10 checks) + `TorController` (rules generator) |
| `rescue.py` | disk scan, diagnosis, repair planner, mount/chroot/fsck |
| `setup.py` | first-boot wizard: hardware detect, profiles, RAM model sizing |
| `platform.py` | cross-platform detection, native shell, config/data dirs |
| `snippets.py` | code snippet library (save/search/tag/export, lang detect) |
| `learning.py` | experience store + `context_for()` prompt injection |
| `retrieval.py` | BM25 offline keyword ranking |
| `files.py` | sandboxed `FileWorkspace` (path escapes refused) |
| `brain/` | `ollama_backend`, `llamacpp_backend`, `router` (failover) |
| `cli.py` / `tui.py` / `gui.py` | three front-ends |
| `knowledge/` | 6 offline teaching notes |

## Agent action protocols

The model acts by emitting ONE fenced block:

| Block | Effect |
|-------|--------|
| ```` ```aegis-command ```` | run a shell command (safety-classified, audited) |
| ```` ```aegis-file path=… ```` | write a file inside the workspace |
| ```` ```aegis-snippet title=… lang=… tags=… ```` | save reusable code |
| ```` ```aegis-remember tags=… ```` | record a lesson for future sessions |

## Smart / memory features

- BM25 retrieval ranks saved snippets + experiences against each request and
  injects the best matches into the prompt (`learning.context_for`).
- Preferences are always included regardless of ranking.
- Intent detection (`agent._intent_hint`) tunes style: coding / security /
  troubleshooting / neutral.
- Cross-platform: `platform.shell_argv` picks sh/zsh or PowerShell/cmd;
  `safety.py` classifies Windows commands too.

## CLI surface

```
aegis                      interactive session
aegis "..."                one-shot
aegis setup [--profile P] [--model M] [--auto] [--show] [--no-pull]
aegis status | doctor | mode <m> | scope add|list|clear
aegis audit show|verify|seal
aegis privacy status|tor|plan|harden|wipe|newid|leaktest|panic
aegis rescue scan|mount|diagnose|plan|chroot|fsck|unmount
             bootloader <dev> [--root R] [--esp E] [--apply]   # #33, dry-run default
aegis diag
aegis finding add|list|show|status|summary|rm
aegis note add|list|show|append
aegis task add|list|done|start|next|plan|clear
aegis report [--format md|html] [--out FILE] [--min-severity S] [--diag]
aegis snippet save|list|search|get|export
aegis learn stats|remember|prefer|search|lessons|forget
aegis allow list|add <cmd>|rm <id>|clear [--prefix]     # standing approvals
aegis-tui | aegis-gui
```
In-session: `:help :status :mode :privacy :tor :snippets :learn :clear :quit`

## Privacy profiles

| Profile | Amnesic | Tor | Memwipe | Safety mode | Services |
|---------|---------|-----|---------|-------------|----------|
| workstation | no | no | no | auto_safe | mac-randomize |
| amnesic | yes | yes | yes | auto_safe | tor, tor-fw, mac, memwipe |
| rescue | no | no | no | **confirm** | none |

## Model sizing (RAM → model)

Reserve = 1800 MiB (+1800 more if amnesic/toram). Rescue capped at 7b.

| RAM | Model |
|-----|-------|
| < 4 GB | `qwen2.5-coder:1.5b` |
| 4–8 GB | `qwen2.5-coder:3b` |
| 8–16 GB | `qwen2.5-coder:7b` |
| 16–32 GB | `qwen2.5-coder:14b` |
| 32 GB+ | `qwen2.5-coder:32b` |

## Build layer (`build/`)

- `cubic/00..50` — base, Ollama, Aegis install, tools, models, branding
- `privacy/10-tor.sh` — Tor + Tails-style transparent proxy (fail-closed)
- `privacy/20-network-hardening.sh` — MAC random, no IPv6, no swap, UTC, ufw
- `privacy/30-amnesia.sh` — tmpfs, shutdown memory wipe, volatile logs
- `privacy/40-whonix.sh` — Whonix Gateway + Workstation VMs (KVM)
- `usb/make-usb.sh` — USB writer; refuses system disk; optional persistence
- `systemd/` + `usr/local/bin/aegis-firstboot.sh` — first boot runs `aegis setup --auto --yes`

## Tests (all passing)

| Suite | Checks |
|-------|--------|
| `tests/test_safety.py` | 20 — classifier, scope, modes |
| `tests/test_agent_loop.py` | 5 — end-to-end loop w/ mock backend |
| `tests/test_privacy_rescue.py` | 22 — auditor, Tor rules, rescue, CLI dispatch |
| `tests/test_setup.py` | 26 — sizing tiers, profiles, TOML round-trip, dry-run |
| `tests/test_smart.py` | 43 — snippets, BM25, learning, files sandbox, Windows safety, agent protocols |
| `tests/test_extras.py` | 36 — findings, notes, tasks, reports, diag, audit hash chain, panic/leak test, Windows/macOS rescue |
| `tests/test_streaming.py` | 10 — `_StreamFilter`, backend stream contract, router failover, agent `on_token` |
| `tests/test_bootloader.py` | 46 — bootloader detect/plan/veto, boot safety classes, argv routing |
| `tests/test_tui_streaming.py` | 6 — drives the real Textual app headlessly (progressive frames, action-block suppression) |
| `tests/test_gui_streaming.py` | 9 — `StreamAssembler` state machine + live Qt cursor insertion |
| `tests/test_approval.py` | 26 — `ApprovalGate` (fail-closed, cancel, timeout) + TUI/GUI approval flows |
| `tests/test_allowlist.py` | 57 — store safety rules, level escalation, tampered-file refusal, Executor integration, CLI, TUI/GUI always-allow |

Total: **306 checks**, 0 failing, 0 skipped. ~10,600 Python LOC, 95 files.

The TUI and GUI suites skip themselves cleanly when Textual / PySide6 are
absent; both were run for real during development (Textual 8.2.8, PySide6
6.11.2).

Run: `make test`. Byte-compile needs `PYTHONPYCACHEPREFIX=/tmp/pycache`
(the workspace mount cannot create `__pycache__`).

## Known constraints / gotchas

- Workspace is S3-backed: **no `__pycache__` writes**, no `rm`, no exec bit.
  Build scripts must be `bash`-run, not executed in place.
- `argparse`: a subparser positional named `command` clobbers the top-level
  `command` dest — the rescue parser uses `chroot_cmd` for this reason.
- `_normalize_argv` must scan **past** leading global flags to find the
  subcommand. Checking only `argv[0]` turned `aegis --mode dry_run privacy tor`
  into `ask privacy tor` — silently running a chat prompt instead of the
  command. Fixed and regression-tested.
- The audit log is itself a forensic artifact; in amnesic mode it dies with RAM.
- The Executor's `confirm` callback runs on a **worker thread** in the TUI and
  GUI, but a prompt must be drawn on the **UI thread**. `aegis/approval.py`
  bridges them; every failure mode (timeout, missing callback, callback that
  raises, window closed) **denies**. Never make a hang mean "approved".

## Honest limits (do not overstate)

- AegisOS is **not Tails**. It has real amnesia + Tor routing, not Tails'
  audited uniform-fingerprint model.
- Tor does not hide *who you log in as*; memory wipe is best-effort.
- Guardrails are not a sandbox; Aegis runs with the user's privileges.
- Aegis refuses out-of-scope offensive tooling and refuses to help cover tracks
  on systems the operator does not own.

## Next up (see `docs/UPGRADES.md` for all 70)

1. LUKS-encrypted persistence option in the USB writer (#21).
2. seccomp/Landlock sandbox around the Executor (#57) — the highest-value
   safety work left, since guardrails are still only a classifier.
4. Whole-plan approval before execution (#47) — pairs with the bootloader plan.
5. "Ask Aegis to fix it" rescue loop — read `diagnose` → propose → execute.
6. `aegis snippet run <id>` through the executor (#15).

Shipped in phase 1.95: findings (#11), reports (#12), notes (#13), tasks (#14),
panic (#22), audit hash chain (#24), Tor new identity (#25), DNS leak test (#26),
Windows rescue (#31), macOS rescue (#32), hardware diagnostics (#36), auto-diagnose (#37).

Shipped later: token streaming (#1) in all three front-ends, bootloader repair
(#33), interactive command approval (TUI + GUI), and the per-command
"remember this" allowlist (`aegis allow`).

### Allowlist design rules (do not weaken)

- Only **read-only / safe-write / risky** commands may be remembered.
  **OFFENSIVE** and **BLOCKED** can never become a standing rule: authorisation
  for security tooling is a declared *scope* (`aegis scope add`), revocable in
  one place, not a one-off click.
- Matching is **exact** on a whitespace-normalised command by default, so
  allowing `mount /dev/sdb1 /mnt` can never authorise
  `mount /dev/sdb1 /mnt && rm -rf /`. Prefix matching is explicit opt-in and is
  labelled in the listing.
- Each rule records the level seen at approval time and stops applying if the
  command later classifies **higher**. Remembering "risky" must not silently
  become "always allow anything".
- The store is a **user-writable file**, so it is treated as untrusted input:
  a hand-edited rule can never bless a BLOCKED command.
- The first `always allow` run is recorded as `confirmed` (the user did confirm
  it); the rule governs *subsequent* runs, which record `allowlisted`.
