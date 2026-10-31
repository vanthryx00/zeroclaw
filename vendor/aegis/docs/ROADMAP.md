# Roadmap

## Phase 1 — Core + CLI ✅ (this build)
- [x] Config system (TOML + env, system/user layering)
- [x] Safety classifier with hard blocks, scope enforcement, modes
- [x] Executor with audit logging
- [x] Ollama backend + llama.cpp backend + failover router
- [x] ReAct-style agent loop
- [x] CLI (interactive + one-shot + subcommands)
- [x] System context gathering (non-sensitive)
- [x] Offline knowledge base
- [x] Cubic distro build scripts
- [x] Safety test suite

## Phase 1.5 — Privacy, amnesia, rescue ✅
- [x] Privacy/leak auditor (DNS, swap, IPv6, MAC, Tor, hostname, TZ, firewall, proxychains)
- [x] Tor controller + transparent-proxy firewall rules
- [x] Amnesic mode (tmpfs, no swap, memory wipe on shutdown)
- [x] MAC randomization + network hardening scripts
- [x] Whonix Gateway + Workstation bundle script
- [x] Rescue mode: disk scan, diagnosis, repair planner, chroot helper
- [x] USB writer with optional persistence (`build/usb/make-usb.sh`)
- [x] `aegis privacy` and `aegis rescue` CLI + in-session `:privacy` / `:tor`
- [x] Honest threat-model docs (`docs/PRIVACY.md`, `RESCUE.md`, `USB.md`)

## Phase 1.75 — First-boot wizard ✅
- [x] Hardware detection (RAM/CPU/disk/live/toram/UEFI)
- [x] Three privacy profiles: workstation / amnesic / rescue
- [x] RAM-aware Ollama model sizing with OS + working-memory reserve
- [x] Extra headroom in amnesic/toram mode; 7b cap in rescue mode
- [x] Config renderer + round-trip; service enablement; `--auto`/`--show`/`--dry-run`
- [x] `aegis setup` CLI + unattended `aegis-firstboot.sh` integration

## Phase 1.9 — Smart coding, memory, cross-platform ✅
- [x] Cross-platform: OS detection, native shell, XDG/AppData/Library dirs
- [x] Windows command classification (read-only / risky / blocked)
- [x] Snippet library: save, search, tag, get, export, language auto-detect
- [x] Learning engine: experiences, preferences, corrections, BM25 retrieval
- [x] Learned context folded into every prompt; preferences always included
- [x] Agent action protocols: `aegis-file`, `aegis-snippet`, `aegis-remember`
- [x] Sandboxed file read/write (path escapes refused)
- [x] Intent detection (coding / security / troubleshooting)
- [x] CLI: `aegis snippet …`, `aegis learn …`, in-session `:snippets` / `:learn`

## Phase 1.95 — Findings, reports, tamper-evidence, cross-platform rescue ✅
- [x] Findings manager with severity/target/evidence/status (`aegis finding`)
- [x] Notes / research journal (`aegis note`)
- [x] Multi-step task planner (`aegis task`)
- [x] Report builder: Markdown + self-contained HTML (`aegis report`)
- [x] Hardware diagnostics: SMART, temps, disk, inodes, kernel, units (`aegis diag`)
- [x] Tamper-evident audit log (hash chain) with `verify` and `seal`
- [x] Panic button: network cut + swap off + RAM wipe + poweroff
- [x] Tor new-identity via the control port
- [x] DNS leak test (config analysis + optional live probe)
- [x] Cross-platform rescue: Windows (ntfsfix/bcdboot) and macOS (diskutil)
- [x] Auto-diagnose on rescue boot (`rescue.auto_diagnose`)
- [x] Full 40-item backlog documented in `docs/UPGRADES.md`

## Phase 2 — Streaming ✅ (complete)
- [x] `Backend.generate_stream` on base (default), Ollama (NDJSON), llama.cpp (SSE + CLI)
- [x] `BackendRouter.generate_stream` with pre-stream failover; mid-stream errors surface
- [x] `_StreamFilter` streams prose live but never leaks an `aegis-*` action block
- [x] Agent `on_token` / `on_stream_end` callbacks; non-streaming front-ends unchanged
- [x] CLI renders tokens progressively (`markup=False`, so `[brackets]` survive)
- [x] TUI: Textual thread worker + live `#stream` Static, moved into the log on end
- [x] GUI: `token` / `stream_end` Qt signals, `QTextCursor` insertion via `StreamAssembler`

## Phase 2b — TUI + deeper tooling (next)
- [x] Textual TUI (basic)
- [ ] Streaming token output in all front-ends
- [ ] Knowledge-base retrieval (embed + search local notes)
- [ ] Session save/load with named sessions
- [ ] `aegis run <script>` batch mode
- [ ] Richer tool-call protocol (JSON schema for models that support it)
- [ ] Interactive scope editor with CIDR validation

## Phase 3 — GUI + polish
- [x] PySide6 GUI (basic)
- [ ] GUI approval flow with per-command allowlist ("remember this")
- [ ] Findings manager: auto-file scan output into a report
- [ ] Report export (Markdown → PDF)
- [ ] Model manager UI (list/pull/switch models)
- [ ] Theming

## Phase 4 — Distro maturity
- [ ] Reproducible ISO build via CI
- [ ] Signed ISO + checksums
- [ ] Auto-update mechanism for the Aegis package only
- [ ] Encrypted persistence option for the live image
- [ ] Hardware compatibility matrix (especially wireless)
- [ ] First-boot wizard: set default authorized scope interactively
      (profile + model sizing is done)
- [ ] LUKS-encrypted persistence option in the USB writer
- [ ] Onion-service (`.onion`) reachability checker in `aegis privacy`
- [ ] Rescue: live "ask Aegis to fix it" loop that reads `diagnose` findings
      and proposes/executes the repair plan step by step

## Ideas / backlog
- Voice interface (offline STT/TTS) for hands-free lab work
- "Explain this output" hotkey that pipes the last command's output to Aegis
- Local RAG over your own notes and the knowledge base
- Per-target engagement profiles (scope + notes + findings bundled)
- Integration with a local CTF scoreboard / lab orchestrator
