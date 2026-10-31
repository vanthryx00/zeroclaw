# AegisOS — Upgrade Backlog (70 items)

Status legend: **✅ shipped** · **⏳ planned** · **🔬 research**

**Batch 1** (items 1–40): findings, reports, notes, tasks, tamper-evident audit,
Tor new identity, DNS leak test, panic button, hardware diagnostics,
cross-platform rescue, streaming — implemented and tested. Also shipped outside
the numbered backlog: bootloader repair, interactive command approval in the TUI
and GUI, and the per-command "always allow" allowlist (`aegis allow`).

**Batch 2** (items 41–70): added below, extending the same four tiers with
capability, safety and platform work. Nothing here is implemented yet.

---

## Tier 1 — Intelligence

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 1 | Streaming token output (CLI/TUI/GUI) | ✅ | `generate_stream` on all backends + router; CLI, TUI and GUI all render progressively |
| 2 | Task-based model router (small classify → big reason) | ⏳ | big speed win on 4–8 GB boxes |
| 3 | Context summarization / rolling window | ⏳ | extends long sessions |
| 4 | RAG over bundled `knowledge/` | ⏳ | BM25 already exists in `retrieval.py` |
| 5 | Optional embedding retrieval | 🔬 | behind the BM25 default |
| 6 | GPU auto-detect (CUDA / ROCm / Metal) | ⏳ | Ollama offload tuning |
| 7 | Response cache + speculative decode | ⏳ | repeat queries instant |
| 8 | Prompt template library (`.aegis/prompts/`) | ⏳ | reusable flows |
| 9 | Model manager (pull / resume / hash-verify) | ⏳ | resilient offline installs |
| 10 | Self-critique pass before proposing a command | ⏳ | safer `auto_full` |

## Tier 2 — Agent tools & workflow

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 11 | Findings manager | ✅ | `aegis finding` · `findings.py` |
| 12 | Report generator (Markdown / HTML) | ✅ | `aegis report` · `report.py` |
| 13 | Notes / journal | ✅ | `aegis note` · `notes.py` |
| 14 | Task planner | ✅ | `aegis task` · `tasks.py` |
| 15 | `aegis snippet run <id>` | ⏳ | run saved code through the Executor |
| 16 | Scheduled tasks (`--cron`) | ⏳ | "scan my lab nightly" |
| 17 | Watch mode (`watch --file X --cmd Y`) | ⏳ | react to logs/config |
| 18 | Diff / patch mode | ⏳ | edit files, not overwrite |
| 19 | Code review mode | ⏳ | static checks + model review |
| 20 | Test-runner loop (fix until green) | ⏳ | autonomous coding |

## Tier 3 — Privacy & security

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 21 | LUKS-encrypted persistence | ⏳ | the real gap vs Tails |
| 22 | Panic button (network off + RAM wipe + poweroff) | ✅ | `aegis privacy panic` |
| 23 | Encrypted vault for snippets/secrets | ⏳ | age / gpg |
| 24 | Tamper-evident audit log (hash chain) | ✅ | `aegis audit verify` / `seal` |
| 25 | Tor "new identity" via control port | ✅ | `aegis privacy newid` |
| 26 | Real DNS leak test | ✅ | `aegis privacy leaktest [--live]` |
| 27 | WireGuard VPN + kill switch | ⏳ | alternative to Tor |
| 28 | MAC randomization verification (OUI check) | ⏳ | catch bad vendor MACs |
| 29 | Secure-delete helpers (`shred`/`sdmem`) | ⏳ | clean removal |
| 30 | Whonix health monitor | ⏳ | verify isolation |

## Tier 4 — Rescue & system

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 31 | Windows rescue (chkdsk / bcdedit / diskpart) | ✅ | `rescue.py` `diagnose_windows` |
| 32 | macOS rescue (diskutil / APFS) | ✅ | `rescue.py` `diagnose_macos` |
| 33 | Bootloader repair automation | ✅ | `aegis rescue bootloader` · `rescue.py` detect/plan/apply |
| 34 | Filesystem recovery (testdisk/photorec) | ⏳ | deleted-file rescue |
| 35 | Backup / restore (rsync + borg) | ⏳ | save data first |
| 36 | Hardware diagnostics (SMART, temps, memory) | ✅ | `aegis diag` · `diag.py` |
| 37 | Auto-diagnose on rescue boot | ✅ | `rescue.auto_diagnose` |
| 38 | Network rescue (DNS / DHCP / wifi) | ⏳ | common live-USB fix |
| 39 | Password-reset helper (chroot passwd) | ⏳ | own-machine recovery |
| 40 | Rescue report export | ✅ | `aegis report --diag` |

## Tier 5 — Model & inference depth

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 41 | Speculative decoding with a draft model | ⏳ | small model proposes, big verifies |
| 42 | LoRA / adapter hot-swap per task | ⏳ | swap a security-tuned adapter without reloading |
| 43 | Local embedding index over user files | ⏳ | semantic search of your own notes/snippets |
| 44 | Self-consistency voting (N samples, majority) | ⏳ | better answers on tiny models |
| 45 | Schema-constrained output (grammar/JSON) | ⏳ | makes action blocks near-unbreakable |
| 46 | Action-block validator + auto-repair retry | ⏳ | re-prompt once on malformed YAML/attrs |

## Tier 6 — Agent autonomy & workflow

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 47 | Whole-plan approval before any execution | ✅ | show every step, approve once |
| 48 | Undo / rollback for file writes | ⏳ | snapshot before `aegis-file` writes |
| 49 | Session resume (`aegis --continue`) | ⏳ | pick up a saved conversation |
| 50 | Background job manager | ⏳ | long commands + `aegis job status` |
| 51 | Sub-agent delegation | ⏳ | bounded worker for a scoped subtask |
| 52 | Deterministic replay of an audited session | ⏳ | reproduce exactly what ran |
| 53 | Token / time / energy accounting | ⏳ | know what a session cost |

## Tier 7 — Hardening & isolation

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 54 | USB / rootfs tamper detection at boot | ⏳ | verify the image signature |
| 55 | Verified boot chain (Secure Boot + signed kernel) | 🔬 | needs a signing key and MOK |
| 56 | Network namespace isolation for risky commands | ⏳ | run untrusted tools with no net |
| 57 | seccomp / Landlock sandbox in the Executor | ⏳ | contain what a command can touch |
| 58 | Tor bridge wizard (obfs4 / snowflake) | ⏳ | usable on censored networks |
| 59 | Onion service manager | ⏳ | self-host behind a v3 address |

## Tier 8 — Deeper rescue

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 60 | Remote rescue over SSH | ⏳ | repair a headless machine |
| 61 | LUKS unlock + chroot recovery flow | ⏳ | FDE box that will not boot |
| 62 | Btrfs / ZFS snapshot rollback helper | ⏳ | undo a bad upgrade |
| 63 | Boot-time memory test integration | ⏳ | memtest86+ from the USB menu |
| 64 | SMART health trend tracking | ⏳ | catch a dying disk early |
| 65 | Offline malware scan (bundled ClamAV signatures) | ⏳ | no network needed |
| 66 | Offline Windows registry editor | ⏳ | hivex / chntpw for boot repair |

## Tier 9 — Platform & accessibility

| # | Upgrade | Status | Notes |
|---|---------|--------|-------|
| 67 | Package-manager repair (dpkg/apt/rpm breakage) | ⏳ | the other classic unbootable cause |
| 68 | systemd unit authoring / repair assistant | ⏳ | generate and validate units |
| 69 | Offline package cache (install without network) | ⏳ | pair with rescue mode |
| 70 | Accessibility: screen reader, high contrast, keyboard-only TUI | ⏳ | usable by everyone |

## Packaging & polish (bonus)

Shell completions (bash/zsh/fish) · man page · `aegis config edit` TUI · plugin
system · themes · i18n · Docker/podman image · signed releases (minisign) ·
reproducible ISO builds.

---

## Suggested next batch

**#1 remainder (TUI + GUI streaming)** and **#21 (LUKS persistence)** are the
two highest-impact remaining items: one finishes the interaction work already
started, the other closes the real privacy gap versus Tails.

After that, in rough order of value:

1. **#57 seccomp/Landlock sandbox** — turns the guardrails from a classifier
   into actual containment. Highest-value safety work outstanding.
2. **#47 whole-plan approval** — the natural companion to the bootloader plan
   already built; makes multi-step autonomy reviewable.
3. **#67 package-manager repair** — the other half of "system will not boot".
4. **#43 local embedding index** — makes the offline copilot feel like it knows
   your machine.

**Recently closed:** #1 (CLI), #33 (bootloader repair), plus a routing bug in
`_normalize_argv` where a global flag before a subcommand silently turned the
command into a chat prompt.
