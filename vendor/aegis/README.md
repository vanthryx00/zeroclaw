# Aegis — offline AI copilot for a security-focused Linux distro

Aegis is a local-first AI assistant that lives inside a custom Ubuntu-based
distribution ("AegisOS"). It runs a language model **entirely on your machine**
(no cloud, no API keys, no telemetry), understands your system, and can run
shell commands for you — under a configurable safety model with an audit trail.

It is built for two things:

1. **Learning cybersecurity** — Aegis explains concepts, walks through
   methodology, and can demonstrate tools on a lab box while teaching.
2. **Everyday task automation** — file management, system inspection, log
   triage, packaging work, and running your own scripts.

---

## Why offline

- **Privacy** — prompts, command output, and findings never leave the machine.
- **Availability** — works on an air-gapped lab network with no internet.
- **No keys, no bills** — you run the model locally.

---

## Architecture at a glance

```
┌──────────────────────────────────────────────────────────────┐
│  Front-ends:  CLI  ·  TUI (Textual)  ·  GUI (PySide6)         │
└───────────────┬──────────────────────────────────────────────┘
                │
        ┌───────▼────────┐      ┌───────────────────────────────┐
        │  Agent loop    │◄────►│  Memory (transcript+lessons)   │
        │  (ReAct-style) │      └───────────────────────────────┘
        └───┬────────┬───┘
            │        │
   ┌────────▼──┐  ┌──▼─────────────┐
   │  Backend  │  │  Safety engine │
   │  router   │  │  classify()    │
   │  ┌─────┐  │  │  decide()      │
   │  │Ollama│ │  └──┬─────────────┘
   │  ├─────┤  │     │
   │  │llama│  │  ┌──▼─────────────┐   ┌──────────────┐
   │  │.cpp │  │  │  Executor      │──►│  Audit log   │
   │  └─────┘  │  │  (subprocess)  │   │  (JSONL)     │
   └───────────┘  └────────────────┘   └──────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for detail.

---

## Quick start (on an existing Ubuntu/Debian machine)

```bash
# 1. Install a local model runtime
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b

# 2. Install Aegis
cd aegis
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[tui]'          # add ,gui for the desktop app

# 3. Check everything
aegis doctor

# 4. Run
aegis "what security tools are installed on this box?"
aegis                            # interactive session
```

### Using the llama.cpp fallback

If you prefer GGUF files with no daemon:

```bash
# start the OpenAI-compatible server
llama-server -m /path/to/model.gguf --port 8080
# Aegis will auto-detect it; set backends = ["llamacpp","ollama"] to prefer it
```

---

## Smart coding + conversation, and a memory that grows

Aegis is built to get **smarter as you use it**, and to work **on Linux, macOS,
and Windows** (it detects the OS and uses the native shell).

### The agent can act in six ways

| Block | Effect |
|-------|--------|
| ```` ```aegis-command ```` | run a shell command |
| ```` ```aegis-file path=… ```` | write a file inside the workspace |
| ```` ```aegis-snippet title=… lang=… tags=… ```` | save reusable code |
| ```` ```aegis-remember tags=… ```` | record a lesson for future sessions |
| ```` ```aegis-screenshot ```` | capture the desktop (read-only) |
| ```` ```aegis-gui ```` | one desktop GUI action (`gui:click x,y` …) |

File writes are sandboxed to `~/aegis-workspace` (path escapes are refused),
and every command still flows through the safety classifier and audit log.

GUI actions (`aegis-gui`, `aegis-screenshot`) go through the same gates —
see [`docs/DESKTOP.md`](docs/DESKTOP.md). Typed text is redacted in the
audit log, credential-shaped or destructive typed text is hard-blocked, and
screenshot is read-only.

### It remembers

Before each reply, a BM25 retrieval step ranks your saved snippets, lessons,
and preferences against the current request and folds the best matches into the
prompt. No embeddings, no network — just an accumulating local knowledge base
under the platform data directory.

```bash
aegis snippet save --title "parse jsonl" --lang python --tags io --code "..."
aegis snippet save --file ./script.py --title "my scanner"
aegis snippet list | search <query> | get <id> | export
aegis learn remember "always test on a lab VM" --tags safety
aegis learn prefer "use uv over pip"
aegis learn stats | search <q> | lessons | forget <id>
```

In-session: `:snippets`, `:learn`. The agent also recognises **intent**
(coding vs security vs troubleshooting) and adjusts its style accordingly.

### Cross-platform

`aegis/platform.py` centralises OS detection, shell selection (sh/zsh on Unix,
PowerShell/cmd on Windows), and config/data directories (XDG, `~/Library/…`,
`%APPDATA%`). `safety.py` classifies **Windows commands too** — `Get-ChildItem`
is read-only, `Stop-Process` is risky, and `format C:` / `rd /s /q C:\` /
`vssadmin delete shadows` are hard-blocked.

## Privacy, anonymity, and rescue

AegisOS also ships a **privacy-hardened, Tor-routed, amnesic** variant for use
as a bootable USB, plus a **rescue mode** that repairs a broken machine.

```bash
aegis privacy status        # leak audit: DNS, swap, IPv6, MAC, Tor, hostname
aegis privacy tor           # which Tor ports are open
aegis privacy plan          # the exact commands that would fix each finding
aegis privacy harden        # apply the plan (each command classified + audited)

aegis rescue scan           # list disks and probable OS partitions
aegis rescue mount /dev/sda2
aegis rescue diagnose       # disk/inode/bootloader/initramfs/fstab checks
aegis rescue plan /dev/sda  # suggested repairs
# bootloader repair: detect + plan first, --apply to execute
aegis rescue bootloader /dev/sda --esp /dev/sda1
aegis rescue bootloader /dev/sda --esp /dev/sda1 --apply
aegis rescue chroot "systemctl --failed"
aegis rescue unmount
```

Build scripts (`build/privacy/`) install Tor with a Tails-style transparent
proxy, MAC randomization, IPv6 disable, no-swap, UTC clock, tmpfs scratch, a
shutdown memory wipe, and optional Whonix Gateway + Workstation VMs.

The USB writer (`build/usb/make-usb.sh`) refuses to touch your system disk and
supports optional encrypted-style persistence or fully amnesic (`toram`) boots.

> **Be clear about the threat model.** Tails' and Whonix's guarantees come from
their architecture, not a checklist. AegisOS gives you real amnesia (RAM-only,
no swap, memory wipe) and real Tor routing — but it is *not* Tails, and Tor does
not hide who you log in as. Read [`docs/PRIVACY.md`](docs/PRIVACY.md) before
relying on it. See also [`docs/RESCUE.md`](docs/RESCUE.md) and
[`docs/USB.md`](docs/USB.md).

## Safety model

Every command Aegis proposes is classified, then decided against the current
**mode**:

| Mode | Behaviour |
|------|-----------|
| `confirm` | Ask before running anything |
| `auto_safe` *(default)* | Auto-run read-only + workspace writes; ask for the rest |
| `auto_full` | Run everything except hard-blocked patterns |
| `dry_run` | Never execute — only show what *would* run |

Command **levels**:

| Level | Examples |
|-------|----------|
| `read-only` | `ls`, `ip a`, `ss -tulpn`, `nmap` (in scope) |
| `safe-write` | writes/deletes confined to `~/aegis-workspace` |
| `risky` | `rm` outside the workspace, `dd`, `chmod 777`, service stops |
| `offensive` | security tools aimed at a target |
| `BLOCKED` | `rm -rf /`, fork bombs, reverse shells, remote `curl \| bash` |

**Hard blocks** can never run, in any mode. **Offensive tools** are refused
unless their target is in your declared scope:

```bash
aegis scope add 10.0.0.0/24
aegis scope add '*.lab.example.com'
aegis scope list
```

Everything Aegis runs is written to an append-only audit log:

```bash
aegis audit -n 50
```

See [`docs/SAFETY.md`](docs/SAFETY.md).

---

## Building the distro (AegisOS)

The `build/` directory contains Cubic chroot scripts that turn an Ubuntu ISO
into AegisOS with the toolset and the copilot baked in. Full walkthrough:
[`build/cubic/README.md`](build/cubic/README.md).

```bash
sudo cubic                    # select Ubuntu ISO, enter chroot
cd /build/cubic
bash 00-base-packages.sh
bash 10-install-ollama.sh
bash 20-install-aegis.sh
bash 30-install-tools.sh
bash 40-models.sh             # optional: pre-bundle a model
bash 50-desktop-branding.sh
```

---

## Command reference

```bash
aegis                          # interactive session
aegis "<request>"              # one-shot
aegis setup                    # first-boot wizard (profile + model sizing)
aegis setup --show --auto      # preview the plan without changing anything
aegis status                   # backend + config health
aegis doctor                   # diagnose the local model setup
aegis mode auto_safe           # change safety mode
aegis scope add 10.0.0.0/24    # declare authorized targets
aegis audit show -n 20         # recent audit entries
aegis audit verify             # check the tamper-evident hash chain
aegis audit seal --out s.json  # pin the current head hash
aegis privacy status           # privacy/leak audit
aegis privacy leaktest --live  # real DNS leak probe
aegis privacy newid            # fresh Tor circuits
aegis privacy panic            # emergency plan (add --yes to run)
aegis rescue scan              # find disks + broken systems
aegis diag                     # hardware diagnostics (SMART, temps, disk)
aegis finding add "..." --severity high --target 10.0.0.5
aegis finding summary          # counts by severity / open high+
aegis note add "Lab notes" --body "..." --tags lab
aegis task plan "recon; enumerate; document"
aegis task list                # checklist + progress
aegis report --diag --out report.md
aegis report --format html --out report.html
aegis snippet list             # saved code snippets
aegis learn stats              # what Aegis remembers
aegis-tui                      # terminal UI (replies stream in live)
aegis-gui                      # desktop UI (replies stream in live)
```

All three front-ends stream the assistant's reply token by token. The agent
runs off the UI thread in the TUI (Textual worker) and GUI (`QThread`), and
action blocks are filtered out before a token ever reaches the screen.

All three also support **interactive command approval**. When a command needs
confirmation, the CLI prompts at the terminal, the TUI shows the command and
waits for a typed answer, and the GUI opens a modal with Run / Deny buttons.
Approvals are fail-closed: a timeout, a closed window or an unreachable UI all
deny rather than approve.

Approving a command also offers **"always allow"** (TUI: type `a`; GUI:
*Always allow*). The decision is persisted as a per-command rule, so the same
command runs without prompting from then on. An allowlist is a standing
authorisation, so the rules are deliberately conservative:

```
aegis allow list                 # show remembered commands and their hit counts
aegis allow add "mount /dev/sdb1 /mnt"
aegis allow add "systemctl status" --prefix   # broader, and labelled as such
aegis allow rm alw-1a12a430aba3483
aegis allow clear
```

- **Exact matching by default**, on a whitespace-normalised command, so
  allowing `mount /dev/sdb1 /mnt` never authorises
  `mount /dev/sdb1 /mnt && rm -rf /`. Prefix rules are opt-in and labelled.
- **OFFENSIVE and BLOCKED commands can never be remembered.** Authorisation for
  security tooling is a declared *scope* (`aegis scope add`), revocable in one
  place — not a one-off click. The GUI disables *Always allow* for those levels.
- **A rule stops applying if the command later classifies higher**, so a new
  safety rule cannot be silently outvoted by an old approval.
- The store is user-writable, so it is treated as untrusted: a hand-edited rule
  can never bless a BLOCKED command.

### Findings, notes, tasks and reports

Results stop living in scrollback. `aegis finding` records structured findings
(severity, target, evidence, status); `aegis note` keeps a research journal;
`aegis task` tracks multi-step work as a checklist. `aegis report` renders it all
into Markdown or a self-contained HTML file, optionally with a live hardware
diagnostic summary.

### Tamper-evident audit

Every audited command is hash-chained to the previous record, so an edit or
deletion is detectable: `aegis audit verify` walks the chain and names the first
broken record. `aegis audit seal` writes the current head hash to a file you can
copy elsewhere — that's what makes tampering provable rather than merely
detectable.

### First-boot wizard

`aegis setup` detects your RAM, CPU, disk, and boot type, then:

1. **Picks a privacy profile** — `workstation`, `amnesic`, or `rescue` — and
   writes the matching `[privacy]`/`[safety]` config plus enables the right
   systemd services. `--auto` chooses from the boot environment (toram/live →
   amnesic, installed → workstation).
2. **Sizes the Ollama model to your RAM** — it subtracts a realistic OS +
   working-memory reserve and picks the largest model that actually fits, with
   extra headroom in amnesic/toram mode where the OS also lives in RAM.

| RAM | Model chosen |
|-----|--------------|
| < 4 GB | `qwen2.5-coder:1.5b` |
| 4–8 GB | `qwen2.5-coder:3b` |
| 8–16 GB | `qwen2.5-coder:7b` |
| 16–32 GB | `qwen2.5-coder:14b` |
| 32 GB+ | `qwen2.5-coder:32b` |

```bash
aegis setup --show                 # preview only
aegis setup --profile amnesic      # force a profile
aegis setup --model qwen2.5-coder:3b --no-pull
```

In-session: `:help`, `:status`, `:mode <mode>`, `:clear`, `:quit`.

---

## Configuration

System defaults: `/etc/aegis/config.toml`
User overrides: `~/.config/aegis/config.toml`
Environment: `AEGIS_MODE`, `AEGIS_OLLAMA_MODEL`, `AEGIS_OLLAMA_HOST`,
`AEGIS_AUTHORIZED_TARGETS`, `AEGIS_WORKSPACE`, `AEGIS_ALLOW_SUDO`

See [`build/etc/aegis/config.toml`](build/etc/aegis/config.toml) for the schema.

---

## Repository layout

```
aegis/                     Python package
  config.py                config loading + defaults
  safety.py                command classifier + authorization
  executor.py              the only place a shell is spawned
  agent.py                 ReAct-style orchestration loop
  context.py               system snapshot for the prompt
  memory.py                transcript + lesson store
  prompts.py               system prompt
  brain/                   Ollama + llama.cpp backends + router
  cli.py / tui.py / gui.py three front-ends
  privacy.py               leak audit + Tor controller
  rescue.py                disk scan, diagnosis, repair planner
  platform.py              cross-platform detection, shell, dirs
  snippets.py              code snippet library
  learning.py              experience store + prompt-context injection
  retrieval.py             BM25 (offline keyword ranking)
  files.py                 sandboxed file read/write
  store.py                 shared JSONL record store
  findings.py              structured findings (severity/target/evidence)
  notes.py                 research journal
  tasks.py                 multi-step task planner
  report.py                Markdown / HTML report builder
  diag.py                  hardware + system diagnostics
  audit.py                 tamper-evident hash-chained audit log
  knowledge/               offline learning notes (bundled into the image)
build/                     Cubic distro build
  cubic/                   numbered chroot scripts
  privacy/                 Tor, network hardening, amnesia, Whonix
  usb/make-usb.sh          USB writer with optional persistence
  etc/aegis/config.toml    system defaults
  systemd/                 first-boot + model-server units
tests/                     safety, agent-loop, privacy, rescue tests
docs/                      architecture, safety, privacy, rescue, usb, roadmap
```

---

## Ethics

Aegis is for systems **you own or are authorized in writing to test**. It
refuses offensive tooling outside your declared scope and hard-blocks
catastrophic commands. The guardrails are not a license — staying legal is your
responsibility. See [`aegis/knowledge/05-ethics-and-scope.md`](aegis/knowledge/05-ethics-and-scope.md).

## License

MIT.
