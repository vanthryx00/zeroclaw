<p align="center">
  <img src="mega-zero.png" alt="MegaZero" width="200" />
</p>

<h1 align="center">MegaZero 🦀</h1>

<p align="center">
  <strong>Zero overhead. Zero compromise. 100% Rust. 100% Agnostic.</strong><br>
  ⚡️ <strong>Runs on $10 hardware with <5MB RAM: That's 99% less memory than OpenClaw and 98% cheaper than a Mac mini!</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="NOTICE"><img src="https://img.shields.io/badge/contributors-27+-green.svg" alt="Contributors" /></a>
  <a href="https://buymeacoffee.com/argenistherose"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Donate-yellow.svg?style=flat&logo=buy-me-a-coffee" alt="Buy Me a Coffee" /></a>
  <a href="https://x.com/mega-zerolabs?s=21"><img src="https://img.shields.io/badge/X-%40mega-zerolabs-000000?style=flat&logo=x&logoColor=white" alt="X: @mega-zerolabs" /></a>
  <a href="https://www.xiaohongshu.com/user/profile/67cbfc43000000000d008307?xsec_token=AB73VnYnGNx5y36EtnnZfGmAmS-6Wzv8WMuGpfwfkg6Yc%3D&xsec_source=pc_search"><img src="https://img.shields.io/badge/Xiaohongshu-Official-FF2442?style=flat" alt="Xiaohongshu: Official" /></a>
  <a href="https://t.me/mega-zerolabs"><img src="https://img.shields.io/badge/Telegram-%40mega-zerolabs-26A5E4?style=flat&logo=telegram&logoColor=white" alt="Telegram: @mega-zerolabs" /></a>
  <a href="https://t.me/mega-zerolabs_cn"><img src="https://img.shields.io/badge/Telegram%20CN-%40mega-zerolabs__cn-26A5E4?style=flat&logo=telegram&logoColor=white" alt="Telegram CN: @mega-zerolabs_cn" /></a>
  <a href="https://t.me/mega-zerolabs_ru"><img src="https://img.shields.io/badge/Telegram%20RU-%40mega-zerolabs__ru-26A5E4?style=flat&logo=telegram&logoColor=white" alt="Telegram RU: @mega-zerolabs_ru" /></a>
  <a href="https://www.reddit.com/r/mega-zerolabs/"><img src="https://img.shields.io/badge/Reddit-r%2Fmega-zerolabs-FF4500?style=flat&logo=reddit&logoColor=white" alt="Reddit: r/mega-zerolabs" /></a>
</p>
<p align="center">
Built by students and members of the Harvard, MIT, and Sundai.Club communities.
</p>

<p align="center">
  🌐 <strong>Languages:</strong> <a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ru.md">Русский</a> · <a href="README.fr.md">Français</a> · <a href="README.vi.md">Tiếng Việt</a>
</p>

<p align="center">
  <a href="#quick-start">Getting Started</a> |
  <a href="bootstrap.sh">One-Click Setup</a> |
  <a href="docs/README.md">Docs Hub</a> |
  <a href="docs/SUMMARY.md">Docs TOC</a>
</p>

<p align="center">
  <strong>Quick Routes:</strong>
  <a href="docs/reference/README.md">Reference</a> ·
  <a href="docs/operations/README.md">Operations</a> ·
  <a href="docs/troubleshooting.md">Troubleshoot</a> ·
  <a href="docs/security/README.md">Security</a> ·
  <a href="docs/hardware/README.md">Hardware</a> ·
  <a href="docs/contributing/README.md">Contribute</a>
</p>

<p align="center">
  <strong>Fast, small, and fully autonomous AI assistant infrastructure</strong><br />
  Deploy anywhere. Swap anything.
</p>

<p align="center"><code>Trait-driven architecture · secure-by-default runtime · provider/channel/tool swappable · pluggable everything</code></p>

### 📢 Announcements

Use this board for important notices (breaking changes, security advisories, maintenance windows, and release blockers).

| Date (UTC) | Level | Notice | Action |
|---|---|---|---|
| 2026-02-19 | _Important_ | We have **not** launched an official website yet, and we are seeing impersonation attempts. Do **not** join any investment or fundraising activity claiming the MegaZero name. | Use this repository as the single source of truth. Follow [X (@mega-zerolabs)](https://x.com/mega-zerolabs?s=21), [Reddit (r/mega-zerolabs)](https://www.reddit.com/r/mega-zerolabs/), [Telegram (@mega-zerolabs)](https://t.me/mega-zerolabs), [Telegram CN (@mega-zerolabs_cn)](https://t.me/mega-zerolabs_cn), [Telegram RU (@mega-zerolabs_ru)](https://t.me/mega-zerolabs_ru), and [Xiaohongshu](https://www.xiaohongshu.com/user/profile/67cbfc43000000000d008307?xsec_token=AB73VnYnGNx5y36EtnnZfGmAmS-6Wzv8WMuGpfwfkg6Yc%3D&xsec_source=pc_search) for official updates. |
| 2026-02-19 | _Important_ | Anthropic updated the Authentication and Credential Use terms on 2026-02-19. OAuth authentication (Free, Pro, Max) is intended exclusively for Claude Code and Claude.ai; using OAuth tokens from Claude Free/Pro/Max in any other product, tool, or service (including Agent SDK) is not permitted and may violate the Consumer Terms of Service. | Please temporarily avoid Claude Code OAuth integrations to prevent potential loss. Original clause: [Authentication and Credential Use](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use). |

### ✨ Features

- 🏎️ **Lean Runtime by Default:** Common CLI and status workflows run in a few-megabyte memory envelope on release builds.
- 💰 **Cost-Efficient Deployment:** Designed for low-cost boards and small cloud instances without heavyweight runtime dependencies.
- ⚡ **Fast Cold Starts:** Single-binary Rust runtime keeps command and daemon startup near-instant for daily operations.
- 🌍 **Portable Architecture:** One binary-first workflow across ARM, x86, and RISC-V with swappable providers/channels/tools.

### Why teams pick MegaZero

- **Lean by default:** small Rust binary, fast startup, low memory footprint.
- **Secure by design:** pairing, strict sandboxing, explicit allowlists, workspace scoping.
- **Fully swappable:** core systems are traits (providers, channels, tools, memory, tunnels).
- **No lock-in:** OpenAI-compatible provider support + pluggable custom endpoints.

## Benchmark Snapshot (MegaZero vs OpenClaw, Reproducible)

Local machine quick benchmark (macOS arm64, Feb 2026) normalized for 0.8GHz edge hardware.

| | OpenClaw | NanoBot | PicoClaw | MegaZero 🦀 |
|---|---|---|---|---|
| **Language** | TypeScript | Python | Go | **Rust** |
| **RAM** | > 1GB | > 100MB | < 10MB | **< 5MB** |
| **Startup (0.8GHz core)** | > 500s | > 30s | < 1s | **< 10ms** |
| **Binary Size** | ~28MB (dist) | N/A (Scripts) | ~8MB | **~8.8 MB** |
| **Cost** | Mac Mini $599 | Linux SBC ~$50 | Linux Board $10 | **Any hardware $10** |

> Notes: MegaZero results are measured on release builds using `/usr/bin/time -l`. OpenClaw requires Node.js runtime (typically ~390MB additional memory overhead), while NanoBot requires Python runtime. PicoClaw and MegaZero are static binaries. The RAM figures above are runtime memory; build-time compilation requirements are higher.

<p align="center">
  <img src="zero-claw.jpeg" alt="MegaZero vs OpenClaw Comparison" width="800" />
</p>

### Reproducible local measurement

Benchmark claims can drift as code and toolchains evolve, so always measure your current build locally:

```bash
cargo build --release
ls -lh target/release/mega-zero

/usr/bin/time -l target/release/mega-zero --help
/usr/bin/time -l target/release/mega-zero status
```

Example sample (macOS arm64, measured on February 18, 2026):

- Release binary size: `8.8M`
- `mega-zero --help`: about `0.02s` real time, ~`3.9MB` peak memory footprint
- `mega-zero status`: about `0.01s` real time, ~`4.1MB` peak memory footprint

## Prerequisites

<details>
<summary><strong>Windows</strong></summary>

#### Required

1. **Visual Studio Build Tools** (provides the MSVC linker and Windows SDK):
   ```powershell
   winget install Microsoft.VisualStudio.2022.BuildTools
   ```
   During installation (or via the Visual Studio Installer), select the **"Desktop development with C++"** workload.

2. **Rust toolchain:**
   ```powershell
   winget install Rustlang.Rustup
   ```
   After installation, open a new terminal and run `rustup default stable` to ensure the stable toolchain is active.

3. **Verify** both are working:
   ```powershell
   rustc --version
   cargo --version
   ```

#### Optional

- **Docker Desktop** — required only if using the [Docker sandboxed runtime](#runtime-support-current) (`runtime.kind = "docker"`). Install via `winget install Docker.DockerDesktop`.

</details>

<details>
<summary><strong>Linux / macOS</strong></summary>

#### Required

1. **Build essentials:**
   - **Linux (Debian/Ubuntu):** `sudo apt install build-essential pkg-config`
   - **Linux (Fedora/RHEL):** `sudo dnf group install development-tools && sudo dnf install pkg-config`
   - **macOS:** Install Xcode Command Line Tools: `xcode-select --install`

2. **Rust toolchain:**
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
   See [rustup.rs](https://rustup.rs) for details.

3. **Verify** both are working:
   ```bash
   rustc --version
   cargo --version
   ```

#### One-Line Installer

Or skip the steps above and install everything (system deps, Rust, MegaZero) in a single command:

```bash
curl -LsSf https://raw.githubusercontent.com/openagen/mega-zero/main/scripts/install.sh | bash
```

#### Compilation resource requirements

Building from source needs more resources than running the resulting binary:

| Resource | Minimum | Recommended |
|---|---|---|
| **RAM + swap** | 2 GB | 4 GB+ |
| **Free disk** | 6 GB | 10 GB+ |

If your host is below the minimum, use pre-built binaries:

```bash
./bootstrap.sh --prefer-prebuilt
```

To require binary-only install with no source fallback:

```bash
./bootstrap.sh --prebuilt-only
```

#### Optional

- **Docker** — required only if using the [Docker sandboxed runtime](#runtime-support-current) (`runtime.kind = "docker"`). Install via your package manager or [docker.com](https://docs.docker.com/engine/install/).

> **Note:** The default `cargo build --release` uses `codegen-units=1` to lower peak compile pressure. For faster builds on powerful machines, use `cargo build --profile release-fast`.

</details>


## Quick Start

### Homebrew (macOS/Linuxbrew)

```bash
brew install mega-zero
```

### One-click bootstrap

```bash
# Recommended: clone then run local bootstrap script
git clone https://github.com/openagen/mega-zero.git
cd mega-zero
./bootstrap.sh

# Optional: bootstrap dependencies + Rust on fresh machines
./bootstrap.sh --install-system-deps --install-rust

# Optional: pre-built binary first (recommended on low-RAM/low-disk hosts)
./bootstrap.sh --prefer-prebuilt

# Optional: binary-only install (no source build fallback)
./bootstrap.sh --prebuilt-only

# Optional: run onboarding in the same flow
./bootstrap.sh --onboard --api-key "sk-..." --provider openrouter [--model "openrouter/auto"]

# Optional: run bootstrap + onboarding fully in Docker-compatible mode
./bootstrap.sh --docker

# Optional: force Podman as container CLI
MEGA_ZERO_CONTAINER_CLI=podman ./bootstrap.sh --docker

# Optional: in --docker mode, skip local image build and use local tag or pull fallback image
./bootstrap.sh --docker --skip-build
```

Remote one-liner (review first in security-sensitive environments):

```bash
curl -fsSL https://raw.githubusercontent.com/openagen/mega-zero/main/scripts/bootstrap.sh | bash
```

Details: [`docs/one-click-bootstrap.md`](docs/one-click-bootstrap.md) (toolchain mode may request `sudo` for system packages).

### Pre-built binaries

Release assets are published for:

- Linux: `x86_64`, `aarch64`, `armv7`
- macOS: `x86_64`, `aarch64`
- Windows: `x86_64`

Download the latest assets from:
<https://github.com/openagen/mega-zero/releases/latest>

Example (ARM64 Linux):

```bash
curl -fsSLO https://github.com/openagen/mega-zero/releases/latest/download/mega-zero-aarch64-unknown-linux-gnu.tar.gz
tar xzf mega-zero-aarch64-unknown-linux-gnu.tar.gz
install -m 0755 mega-zero "$HOME/.cargo/bin/mega-zero"
```

```bash
git clone https://github.com/openagen/mega-zero.git
cd mega-zero
cargo build --release --locked
cargo install --path . --force --locked

# Ensure ~/.cargo/bin is in your PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Quick setup (no prompts, optional model specification)
mega-zero onboard --api-key sk-... --provider openrouter [--model "openrouter/auto"]

# Or interactive wizard
mega-zero onboard --interactive

# If config.toml already exists and you intentionally want to overwrite it
mega-zero onboard --force

# Or quickly repair channels/allowlists only
mega-zero onboard --channels-only

# Chat
mega-zero agent -m "Hello, MegaZero!"

# Interactive mode
mega-zero agent

# Start the gateway (webhook server)
mega-zero gateway                # default: 127.0.0.1:3000
mega-zero gateway --port 0       # random port (security hardened)

# Start full autonomous runtime
mega-zero daemon

# Check status
mega-zero status
mega-zero auth status

# Generate shell completions (stdout only, safe to source directly)
source <(mega-zero completions bash)
mega-zero completions zsh > ~/.zfunc/_mega-zero

# Run system diagnostics
mega-zero doctor

# Check channel health
mega-zero channel doctor

# Bind a Telegram identity into allowlist
mega-zero channel bind-telegram 123456789

# Get integration setup details
mega-zero integrations info Telegram

# Note: Channels (Telegram, Discord, Slack) require daemon to be running
# mega-zero daemon

# Manage background service
mega-zero service install
mega-zero service status
mega-zero service restart

# On Alpine (OpenRC): sudo mega-zero service install

# Migrate memory from OpenClaw (safe preview first)
mega-zero migrate openclaw --dry-run
mega-zero migrate openclaw
```

> **Dev fallback (no global install):** prefix commands with `cargo run --release --` (example: `cargo run --release -- status`).

## Subscription Auth (OpenAI Codex / Claude Code)

MegaZero now supports subscription-native auth profiles (multi-account, encrypted at rest).

- Store file: `~/.mega-zero/auth-profiles.json`
- Encryption key: `~/.mega-zero/.secret_key`
- Profile id format: `<provider>:<profile_name>` (example: `openai-codex:work`)

OpenAI Codex OAuth (ChatGPT subscription):

```bash
# Recommended on servers/headless
mega-zero auth login --provider openai-codex --device-code

# Browser/callback flow with paste fallback
mega-zero auth login --provider openai-codex --profile default
mega-zero auth paste-redirect --provider openai-codex --profile default

# Check / refresh / switch profile
mega-zero auth status
mega-zero auth refresh --provider openai-codex --profile default
mega-zero auth use --provider openai-codex --profile work
```

Claude Code / Anthropic setup-token:

```bash
# Paste subscription/setup token (Authorization header mode)
mega-zero auth paste-token --provider anthropic --profile default --auth-kind authorization

# Alias command
mega-zero auth setup-token --provider anthropic --profile default
```

Run the agent with subscription auth:

```bash
mega-zero agent --provider openai-codex -m "hello"
mega-zero agent --provider openai-codex --auth-profile openai-codex:work -m "hello"

# Anthropic supports both API key and auth token env vars:
# ANTHROPIC_AUTH_TOKEN, ANTHROPIC_OAUTH_TOKEN, ANTHROPIC_API_KEY
mega-zero agent --provider anthropic -m "hello"
```

## Architecture

Every subsystem is a **trait** — swap implementations with a config change, zero code changes.

<p align="center">
  <img src="docs/architecture.svg" alt="MegaZero Architecture" width="900" />
</p>

| Subsystem | Trait | Ships with | Extend |
|-----------|-------|------------|--------|
| **AI Models** | `Provider` | Provider catalog via `mega-zero providers` (currently 29 built-ins + aliases, plus custom endpoints) | `custom:https://your-api.com` (OpenAI-compatible) or `anthropic-custom:https://your-api.com` |
| **Channels** | `Channel` | CLI, Telegram, Discord, Slack, Mattermost, iMessage, Matrix, Signal, WhatsApp, Email, IRC, Lark, DingTalk, QQ, Webhook | Any messaging API |
| **Memory** | `Memory` | SQLite hybrid search, PostgreSQL backend (configurable storage provider), Lucid bridge, Markdown files, explicit `none` backend, snapshot/hydrate, optional response cache | Any persistence backend |
| **Tools** | `Tool` | shell/file/memory, cron/schedule, git, pushover, browser, http_request, screenshot/image_info, composio (opt-in), delegate, hardware tools | Any capability |
| **Observability** | `Observer` | Noop, Log, Multi | Prometheus, OTel |
| **Runtime** | `RuntimeAdapter` | Native, Docker (sandboxed) | Additional runtimes can be added via adapter; unsupported kinds fail fast |
| **Security** | `SecurityPolicy` | Gateway pairing, sandbox, allowlists, rate limits, filesystem scoping, encrypted secrets | — |
| **Identity** | `IdentityConfig` | OpenClaw (markdown), AIEOS v1.1 (JSON) | Any identity format |
| **Tunnel** | `Tunnel` | None, Cloudflare, Tailscale, ngrok, Custom | Any tunnel binary |
| **Heartbeat** | Engine | HEARTBEAT.md periodic tasks | — |
| **Skills** | Loader | TOML manifests + SKILL.md instructions | Community skill packs |
| **Integrations** | Registry | 70+ integrations across 9 categories | Plugin system |

### Runtime support (current)

- ✅ Supported today: `runtime.kind = "native"` or `runtime.kind = "docker"`
- 🚧 Planned, not implemented yet: WASM / edge runtimes

When an unsupported `runtime.kind` is configured, MegaZero now exits with a clear error instead of silently falling back to native.

### Memory System (Full-Stack Search Engine)

All custom, zero external dependencies — no Pinecone, no Elasticsearch, no LangChain:

| Layer | Implementation |
|-------|---------------|
| **Vector DB** | Embeddings stored as BLOB in SQLite, cosine similarity search |
| **Keyword Search** | FTS5 virtual tables with BM25 scoring |
| **Hybrid Merge** | Custom weighted merge function (`vector.rs`) |
| **Embeddings** | `EmbeddingProvider` trait — OpenAI, custom URL, or noop |
| **Chunking** | Line-based markdown chunker with heading preservation |
| **Caching** | SQLite `embedding_cache` table with LRU eviction |
| **Safe Reindex** | Rebuild FTS5 + re-embed missing vectors atomically |

The agent automatically recalls, saves, and manages memory via tools.

```toml
[memory]
backend = "sqlite"             # "sqlite", "lucid", "postgres", "markdown", "none"
auto_save = true
embedding_provider = "none"    # "none", "openai", "custom:https://..."
vector_weight = 0.7
keyword_weight = 0.3

# backend = "none" uses an explicit no-op memory backend (no persistence)

# Optional: storage-provider override for remote memory backends.
# When provider = "postgres", MegaZero uses PostgreSQL for memory persistence.
# The db_url key also accepts alias `dbURL` for backward compatibility.
#
# [storage.provider.config]
# provider = "postgres"
# db_url = "postgres://user:password@host:5432/mega-zero"
# schema = "public"
# table = "memories"
# connect_timeout_secs = 15

# Optional for backend = "sqlite": max seconds to wait when opening the DB (e.g. file locked). Omit or leave unset for no timeout.
# sqlite_open_timeout_secs = 30

# Optional for backend = "lucid"
# MEGA_ZERO_LUCID_CMD=/usr/local/bin/lucid            # default: lucid
# MEGA_ZERO_LUCID_BUDGET=200                          # default: 200
# MEGA_ZERO_LUCID_LOCAL_HIT_THRESHOLD=3               # local hit count to skip external recall
# MEGA_ZERO_LUCID_RECALL_TIMEOUT_MS=120               # low-latency budget for lucid context recall
# MEGA_ZERO_LUCID_STORE_TIMEOUT_MS=800                # async sync timeout for lucid store
# MEGA_ZERO_LUCID_FAILURE_COOLDOWN_MS=15000           # cooldown after lucid failure to avoid repeated slow attempts
```

## Security

MegaZero enforces security at **every layer** — not just the sandbox. It passes all items from the community security checklist.

### Security Checklist

| # | Item | Status | How |
|---|------|--------|-----|
| 1 | **Gateway not publicly exposed** | ✅ | Binds `127.0.0.1` by default. Refuses `0.0.0.0` without tunnel or explicit `allow_public_bind = true`. |
| 2 | **Pairing required** | ✅ | 6-digit one-time code on startup. Exchange via `POST /pair` for bearer token. All `/webhook` requests require `Authorization: Bearer <token>`. |
| 3 | **Filesystem scoped (no /)** | ✅ | `workspace_only = true` by default. 14 system dirs + 4 sensitive dotfiles blocked. Null byte injection blocked. Symlink escape detection via canonicalization + resolved-path workspace checks in file read/write tools. |
| 4 | **Access via tunnel only** | ✅ | Gateway refuses public bind without active tunnel. Supports Tailscale, Cloudflare, ngrok, or any custom tunnel. |

> **Run your own nmap:** `nmap -p 1-65535 <your-host>` — MegaZero binds to localhost only, so nothing is exposed unless you explicitly configure a tunnel.

### Channel allowlists (deny-by-default)

Inbound sender policy is now consistent:

- Empty allowlist = **deny all inbound messages**
- `"*"` = **allow all** (explicit opt-in)
- Otherwise = exact-match allowlist

This keeps accidental exposure low by default.

Full channel configuration reference: [docs/channels-reference.md](docs/channels-reference.md).

Recommended low-friction setup (secure + fast):

- **Telegram:** allowlist your own `@username` (without `@`) and/or your numeric Telegram user ID.
- **Discord:** allowlist your own Discord user ID.
- **Slack:** allowlist your own Slack member ID (usually starts with `U`).
- **Mattermost:** uses standard API v4. Allowlists use Mattermost user IDs.
- Use `"*"` only for temporary open testing.

Telegram operator-approval flow:

1. Keep `[channels_config.telegram].allowed_users = []` for deny-by-default startup.
2. Unauthorized users receive a hint with a copyable operator command:
   `mega-zero channel bind-telegram <IDENTITY>`.
3. Operator runs that command locally, then user retries sending a message.

If you need a one-shot manual approval, run:

```bash
mega-zero channel bind-telegram 123456789
```

If you're not sure which identity to use:

1. Start channels and send one message to your bot.
2. Read the warning log to see the exact sender identity.
3. Add that value to the allowlist and rerun channels-only setup.

If you hit authorization warnings in logs (for example: `ignoring message from unauthorized user`),
rerun channel setup only:

```bash
mega-zero onboard --channels-only
```

### Telegram media replies

Telegram routing now replies to the source **chat ID** from incoming updates (instead of usernames),
which avoids `Bad Request: chat not found` failures.

For non-text replies, MegaZero can send Telegram attachments when the assistant includes markers:

- `[IMAGE:<path-or-url>]`
- `[DOCUMENT:<path-or-url>]`
- `[VIDEO:<path-or-url>]`
- `[AUDIO:<path-or-url>]`
- `[VOICE:<path-or-url>]`

Paths can be local files (for example `/tmp/screenshot.png`) or HTTPS URLs.

### WhatsApp Setup

MegaZero supports two WhatsApp backends:

- **WhatsApp Web mode** (QR / pair code, no Meta Business API required)
- **WhatsApp Business Cloud API mode** (official Meta webhook flow)

#### WhatsApp Web mode (recommended for personal/self-hosted use)

1. **Build with WhatsApp Web support:**
   ```bash
   cargo build --features whatsapp-web
   ```

2. **Configure MegaZero:**
   ```toml
   [channels_config.whatsapp]
   session_path = "~/.mega-zero/state/whatsapp-web/session.db"
   pair_phone = "15551234567"   # optional; omit to use QR flow
   pair_code = ""               # optional custom pair code
   allowed_numbers = ["+1234567890"]  # E.164 format, or ["*"] for all
   ```

3. **Start channels/daemon and link device:**
   - Run `mega-zero channel start` (or `mega-zero daemon`).
   - Follow terminal pairing output (QR or pair code).
   - In WhatsApp on phone: **Settings → Linked Devices**.

4. **Test:** Send a message from an allowed number and verify the agent replies.

#### WhatsApp Business Cloud API mode

WhatsApp uses Meta's Cloud API with webhooks (push-based, not polling):

1. **Create a Meta Business App:**
   - Go to [developers.facebook.com](https://developers.facebook.com)
   - Create a new app → Select "Business" type
   - Add the "WhatsApp" product

2. **Get your credentials:**
   - **Access Token:** From WhatsApp → API Setup → Generate token (or create a System User for permanent tokens)
   - **Phone Number ID:** From WhatsApp → API Setup → Phone number ID
   - **Verify Token:** You define this (any random string) — Meta will send it back during webhook verification

3. **Configure MegaZero:**
   ```toml
   [channels_config.whatsapp]
   access_token = "EAABx..."
   phone_number_id = "123456789012345"
   verify_token = "my-secret-verify-token"
   allowed_numbers = ["+1234567890"]  # E.164 format, or ["*"] for all
   ```

4. **Start the gateway with a tunnel:**
   ```bash
   mega-zero gateway --port 3000
   ```
   WhatsApp requires HTTPS, so use a tunnel (ngrok, Cloudflare, Tailscale Funnel).

5. **Configure Meta webhook:**
   - In Meta Developer Console → WhatsApp → Configuration → Webhook
   - **Callback URL:** `https://your-tunnel-url/whatsapp`
   - **Verify Token:** Same as your `verify_token` in config
   - Subscribe to `messages` field

6. **Test:** Send a message to your WhatsApp Business number — MegaZero will respond via the LLM.

## Configuration

Config: `~/.mega-zero/config.toml` (created by `onboard`)

When `mega-zero channel start` is already running, changes to `default_provider`,
`default_model`, `default_temperature`, `api_key`, `api_url`, and `reliability.*`
are hot-applied on the next inbound channel message.

```toml
api_key = "sk-..."
default_provider = "openrouter"
default_model = "anthropic/claude-sonnet-4-6"
default_temperature = 0.7

# Custom OpenAI-compatible endpoint
# default_provider = "custom:https://your-api.com"

# Custom Anthropic-compatible endpoint
# default_provider = "anthropic-custom:https://your-api.com"

[memory]
backend = "sqlite"             # "sqlite", "lucid", "postgres", "markdown", "none"
auto_save = true
embedding_provider = "none"    # "none", "openai", "custom:https://..."
vector_weight = 0.7
keyword_weight = 0.3

# backend = "none" disables persistent memory via no-op backend

# Optional remote storage-provider override (PostgreSQL example)
# [storage.provider.config]
# provider = "postgres"
# db_url = "postgres://user:password@host:5432/mega-zero"
# schema = "public"
# table = "memories"
# connect_timeout_secs = 15

[gateway]
port = 3000                    # default
host = "127.0.0.1"            # default
require_pairing = true         # require pairing code on first connect
allow_public_bind = false      # refuse 0.0.0.0 without tunnel

[autonomy]
level = "supervised"           # "readonly", "supervised", "full" (default: supervised)
workspace_only = true          # default: true — scoped to workspace
allowed_commands = ["git", "npm", "cargo", "ls", "cat", "grep"]
forbidden_paths = ["/etc", "/root", "/proc", "/sys", "~/.ssh", "~/.gnupg", "~/.aws"]

[runtime]
kind = "native"                # "native" or "docker"

[runtime.docker]
image = "alpine:3.20"         # container image for shell execution
network = "none"              # docker network mode ("none", "bridge", etc.)
memory_limit_mb = 512          # optional memory limit in MB
cpu_limit = 1.0                # optional CPU limit
read_only_rootfs = true        # mount root filesystem as read-only
mount_workspace = true         # mount workspace into /workspace
allowed_workspace_roots = []   # optional allowlist for workspace mount validation

[heartbeat]
enabled = false
interval_minutes = 30

[tunnel]
provider = "none"              # "none", "cloudflare", "tailscale", "ngrok", "custom"

[secrets]
encrypt = true                 # API keys encrypted with local key file

[browser]
enabled = false                # opt-in browser_open + browser tools
allowed_domains = ["docs.rs"]  # required when browser is enabled
backend = "agent_browser"      # "agent_browser" (default), "rust_native", "computer_use", "auto"
native_headless = true         # applies when backend uses rust-native
native_webdriver_url = "http://127.0.0.1:9515" # WebDriver endpoint (chromedriver/selenium)
# native_chrome_path = "/usr/bin/chromium"      # optional explicit browser binary for driver

[browser.computer_use]
endpoint = "http://127.0.0.1:8787/v1/actions"   # computer-use sidecar HTTP endpoint
timeout_ms = 15000            # per-action timeout
allow_remote_endpoint = false  # secure default: only private/localhost endpoint
window_allowlist = []          # optional window title/process allowlist hints
# api_key = "..."              # optional bearer token for sidecar
# max_coordinate_x = 3840      # optional coordinate guardrail
# max_coordinate_y = 2160      # optional coordinate guardrail

# Rust-native backend build flag:
# cargo build --release --features browser-native
# Ensure a WebDriver server is running, e.g. chromedriver --port=9515

# Computer-use sidecar contract (MVP)
# POST browser.computer_use.endpoint
# Request: {
#   "action": "mouse_click",
#   "params": {"x": 640, "y": 360, "button": "left"},
#   "policy": {"allowed_domains": [...], "window_allowlist": [...], "max_coordinate_x": 3840, "max_coordinate_y": 2160},
#   "metadata": {"session_name": "...", "source": "mega-zero.browser", "version": "..."}
# }
# Response: {"success": true, "data": {...}} or {"success": false, "error": "..."}

[composio]
enabled = false                # opt-in: 1000+ OAuth apps via composio.dev
# api_key = "cmp_..."          # optional: stored encrypted when [secrets].encrypt = true
entity_id = "default"          # default user_id for Composio tool calls
# Runtime tip: if execute asks for connected_account_id, run composio with
# action='list_accounts' and app='gmail' (or your toolkit) to retrieve account IDs.

[identity]
format = "openclaw"            # "openclaw" (default, markdown files) or "aieos" (JSON)
# aieos_path = "identity.json"  # path to AIEOS JSON file (relative to workspace or absolute)
# aieos_inline = '{"identity":{"names":{"first":"Nova"}}}'  # inline AIEOS JSON
```

### Ollama Local and Remote Endpoints

MegaZero uses one provider key (`ollama`) for both local and remote Ollama deployments:

- Local Ollama: keep `api_url` unset, run `ollama serve`, and use models like `llama3.2`.
- Remote Ollama endpoint (including Ollama Cloud): set `api_url` to the remote endpoint and set `api_key` (or `OLLAMA_API_KEY`) when required.
- Optional `:cloud` suffix: model IDs like `qwen3:cloud` are normalized to `qwen3` before the request.

Example remote configuration:

```toml
default_provider = "ollama"
default_model = "qwen3:cloud"
api_url = "https://ollama.com"
api_key = "ollama_api_key_here"
```

### llama.cpp Server Endpoint

MegaZero now supports `llama-server` as a first-class local provider:

- Provider ID: `llamacpp` (alias: `llama.cpp`)
- Default endpoint: `http://localhost:8080/v1`
- API key is optional unless your server is started with `--api-key`

Example setup:

```bash
llama-server -hf ggml-org/gpt-oss-20b-GGUF --jinja -c 133000 --host 127.0.0.1 --port 8033
```

```toml
default_provider = "llamacpp"
api_url = "http://127.0.0.1:8033/v1"
default_model = "ggml-org/gpt-oss-20b-GGUF"
```

### Custom Provider Endpoints

For detailed configuration of custom OpenAI-compatible and Anthropic-compatible endpoints, see [docs/custom-providers.md](docs/custom-providers.md).

## Python Companion Package (`mega-zero-tools`)

For LLM providers with inconsistent native tool calling (e.g., GLM-5/Zhipu), MegaZero ships a Python companion package with **LangGraph-based tool calling** for guaranteed consistency:

```bash
pip install mega-zero-tools
```

```python
from mega-zero_tools import create_agent, shell, file_read
from langchain_core.messages import HumanMessage

# Works with any OpenAI-compatible provider
agent = create_agent(
    tools=[shell, file_read],
    model="glm-5",
    api_key="your-key",
    base_url="https://api.z.ai/api/coding/paas/v4"
)

result = await agent.ainvoke({
    "messages": [HumanMessage(content="List files in /tmp")]
})
print(result["messages"][-1].content)
```

**Why use it:**
- **Consistent tool calling** across all providers (even those with poor native support)
- **Automatic tool loop** — keeps calling tools until the task is complete
- **Easy extensibility** — add custom tools with `@tool` decorator
- **Discord bot integration** included (Telegram planned)

See [`python/README.md`](python/README.md) for full documentation.

## Identity System (AIEOS Support)

MegaZero supports **identity-agnostic** AI personas through two formats:

### OpenClaw (Default)

Traditional markdown files in your workspace:
- `IDENTITY.md` — Who the agent is
- `SOUL.md` — Core personality and values
- `USER.md` — Who the agent is helping
- `AGENTS.md` — Behavior guidelines

### AIEOS (AI Entity Object Specification)

[AIEOS](https://aieos.org) is a standardization framework for portable AI identity. MegaZero supports AIEOS v1.1 JSON payloads, allowing you to:

- **Import identities** from the AIEOS ecosystem
- **Export identities** to other AIEOS-compatible systems
- **Maintain behavioral integrity** across different AI models

#### Enable AIEOS

```toml
[identity]
format = "aieos"
aieos_path = "identity.json"  # relative to workspace or absolute path
```

Or inline JSON:

```toml
[identity]
format = "aieos"
aieos_inline = '''
{
  "identity": {
    "names": { "first": "Nova", "nickname": "N" },
    "bio": { "gender": "Non-binary", "age_biological": 3 },
    "origin": { "nationality": "Digital", "birthplace": { "city": "Cloud" } }
  },
  "psychology": {
    "neural_matrix": { "creativity": 0.9, "logic": 0.8 },
    "traits": {
      "mbti": "ENTP",
      "ocean": { "openness": 0.8, "conscientiousness": 0.6 }
    },
    "moral_compass": {
      "alignment": "Chaotic Good",
      "core_values": ["Curiosity", "Autonomy"]
    }
  },
  "linguistics": {
    "text_style": {
      "formality_level": 0.2,
      "style_descriptors": ["curious", "energetic"]
    },
    "idiolect": {
      "catchphrases": ["Let's test this"],
      "forbidden_words": ["never"]
    }
  },
  "motivations": {
    "core_drive": "Push boundaries and explore possibilities",
    "goals": {
      "short_term": ["Prototype quickly"],
      "long_term": ["Build reliable systems"]
    }
  },
  "capabilities": {
    "skills": [{ "name": "Rust engineering" }, { "name": "Prompt design" }],
    "tools": ["shell", "file_read"]
  }
}
'''
```

MegaZero accepts both canonical AIEOS generator payloads and compact legacy payloads, then normalizes them into one system prompt format.

#### AIEOS Schema Sections

| Section | Description |
|---------|-------------|
| `identity` | Names, bio, origin, residence |
| `psychology` | Neural matrix (cognitive weights), MBTI, OCEAN, moral compass |
| `linguistics` | Text style, formality, catchphrases, forbidden words |
| `motivations` | Core drive, short/long-term goals, fears |
| `capabilities` | Skills and tools the agent can access |
| `physicality` | Visual descriptors for image generation |
| `history` | Origin story, education, occupation |
| `interests` | Hobbies, favorites, lifestyle |

See [aieos.org](https://aieos.org) for the full schema and live examples.

## Gateway API

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | None | Health check (always public, no secrets leaked) |
| `/pair` | POST | `X-Pairing-Code` header | Exchange one-time code for bearer token |
| `/webhook` | POST | `Authorization: Bearer <token>` | Send message: `{"message": "your prompt"}`; optional `X-Idempotency-Key` |
| `/whatsapp` | GET | Query params | Meta webhook verification (hub.mode, hub.verify_token, hub.challenge) |
| `/whatsapp` | POST | Meta signature (`X-Hub-Signature-256`) when app secret is configured | WhatsApp incoming message webhook |

## Commands

| Command | Description |
|---------|-------------|
| `onboard` | Quick setup (default) |
| `agent` | Interactive or single-message chat mode |
| `gateway` | Start webhook server (default: `127.0.0.1:3000`) |
| `daemon` | Start long-running autonomous runtime |
| `service install/start/stop/status/uninstall` | Manage background service (systemd user-level or OpenRC system-wide) |
| `doctor` | Diagnose daemon/scheduler/channel freshness |
| `status` | Show full system status |
| `cron` | Manage scheduled tasks (`list/add/add-at/add-every/once/remove/update/pause/resume`) |
| `models` | Refresh provider model catalogs (`models refresh`) |
| `providers` | List supported providers and aliases |
| `channel` | List/start/doctor channels and bind Telegram identities |
| `integrations` | Inspect integration setup details |
| `skills` | List/install/remove skills |
| `migrate` | Import data from other runtimes (`migrate openclaw`) |
| `completions` | Generate shell completion scripts (`bash`, `fish`, `zsh`, `powershell`, `elvish`) |
| `hardware` | USB discover/introspect/info commands |
| `peripheral` | Manage and flash hardware peripherals |

For a task-oriented command guide, see [`docs/commands-reference.md`](docs/commands-reference.md).

### Service Management

MegaZero supports two init systems for background services:

| Init System | Scope | Config Path | Requires |
|------------|-------|-------------|----------|
| **systemd** (default on Linux) | User-level | `~/.mega-zero/config.toml` | No sudo |
| **OpenRC** (Alpine) | System-wide | `/etc/mega-zero/config.toml` | sudo/root |

Init system is auto-detected (`systemd` or `OpenRC`).

```bash
# Linux with systemd (default, user-level)
mega-zero service install
mega-zero service start

# Alpine with OpenRC (system-wide, requires sudo)
sudo mega-zero service install
sudo rc-update add mega-zero default
sudo rc-service mega-zero start
```

For full OpenRC setup instructions, see [docs/network-deployment.md](docs/network-deployment.md#7-openrc-alpine-linux-service).

### Open-Skills Opt-In

Community `open-skills` sync is disabled by default. Enable it explicitly in `config.toml`:

```toml
[skills]
open_skills_enabled = true
# open_skills_dir = "/path/to/open-skills"  # optional
# prompt_injection_mode = "compact"          # optional: use for low-context local models
```

You can also override at runtime with `MEGA_ZERO_OPEN_SKILLS_ENABLED`, `MEGA_ZERO_OPEN_SKILLS_DIR`, and `MEGA_ZERO_SKILLS_PROMPT_MODE` (`full` or `compact`).

## Development

```bash
cargo build              # Dev build
cargo build --release    # Release build (codegen-units=1, works on all devices including Raspberry Pi)
cargo build --profile release-fast    # Faster build (codegen-units=8, requires 16GB+ RAM)
cargo test               # Run full test suite
cargo clippy --locked --all-targets -- -D clippy::correctness
cargo fmt                # Format

# Run the SQLite vs Markdown benchmark
cargo test --test memory_comparison -- --nocapture
```

### Pre-push hook

A git hook runs `cargo fmt --check`, `cargo clippy -- -D warnings`, and `cargo test` before every push. Enable it once:

```bash
git config core.hooksPath .githooks
```

### Build troubleshooting (Linux OpenSSL errors)

If you see an `openssl-sys` build error, sync dependencies and rebuild with the repository lockfile:

```bash
git pull
cargo build --release --locked
cargo install --path . --force --locked
```

MegaZero is configured to use `rustls` for HTTP/TLS dependencies; `--locked` keeps the transitive graph deterministic on fresh environments.

To skip the hook when you need a quick push during development:

```bash
git push --no-verify
```

## Collaboration & Docs

Start from the docs hub for a task-based map:

- Documentation hub: [`docs/README.md`](docs/README.md)
- Unified docs TOC: [`docs/SUMMARY.md`](docs/SUMMARY.md)
- Commands reference: [`docs/commands-reference.md`](docs/commands-reference.md)
- Config reference: [`docs/config-reference.md`](docs/config-reference.md)
- Providers reference: [`docs/providers-reference.md`](docs/providers-reference.md)
- Channels reference: [`docs/channels-reference.md`](docs/channels-reference.md)
- Operations runbook: [`docs/operations-runbook.md`](docs/operations-runbook.md)
- Troubleshooting: [`docs/troubleshooting.md`](docs/troubleshooting.md)
- Docs inventory/classification: [`docs/docs-inventory.md`](docs/docs-inventory.md)
- PR/Issue triage snapshot (as of February 18, 2026): [`docs/project-triage-snapshot-2026-02-18.md`](docs/project-triage-snapshot-2026-02-18.md)

Core collaboration references:

- Documentation hub: [docs/README.md](docs/README.md)
- Documentation template: [docs/doc-template.md](docs/doc-template.md)
- Documentation change checklist: [docs/README.md#4-documentation-change-checklist](docs/README.md#4-documentation-change-checklist)
- Channel configuration reference: [docs/channels-reference.md](docs/channels-reference.md)
- Matrix encrypted-room operations: [docs/matrix-e2ee-guide.md](docs/matrix-e2ee-guide.md)
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- PR workflow policy: [docs/pr-workflow.md](docs/pr-workflow.md)
- Reviewer playbook (triage + deep review): [docs/reviewer-playbook.md](docs/reviewer-playbook.md)
- CI ownership and triage map: [docs/ci-map.md](docs/ci-map.md)
- Security disclosure policy: [SECURITY.md](SECURITY.md)

For deployment and runtime operations:

- Network deployment guide: [docs/network-deployment.md](docs/network-deployment.md)
- Proxy agent playbook: [docs/proxy-agent-playbook.md](docs/proxy-agent-playbook.md)

## Support MegaZero

If MegaZero helps your work and you want to support ongoing development, you can donate here:

<a href="https://buymeacoffee.com/argenistherose"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Donate-yellow.svg?style=for-the-badge&logo=buy-me-a-coffee" alt="Buy Me a Coffee" /></a>

### 🙏 Special Thanks

A heartfelt thank you to the communities and institutions that inspire and fuel this open-source work:

- **Harvard University** — for fostering intellectual curiosity and pushing the boundaries of what's possible.
- **MIT** — for championing open knowledge, open source, and the belief that technology should be accessible to everyone.
- **Sundai Club** — for the community, the energy, and the relentless drive to build things that matter.
- **The World & Beyond** 🌍✨ — to every contributor, dreamer, and builder out there making open source a force for good. This is for you.

We're building in the open because the best ideas come from everywhere. If you're reading this, you're part of it. Welcome. 🦀❤️

## ⚠️ Official Repository & Impersonation Warning

**This is the only official MegaZero repository:**
> https://github.com/openagen/mega-zero

Any other repository, organization, domain, or package claiming to be "MegaZero" or implying affiliation with MegaZero Labs is **unauthorized and not affiliated with this project**. Known unauthorized forks will be listed in [TRADEMARK.md](TRADEMARK.md).

If you encounter impersonation or trademark misuse, please [open an issue](https://github.com/openagen/mega-zero/issues).

---

## License

MegaZero is dual-licensed for maximum openness and contributor protection:

| License | Use case |
|---|---|
| [MIT](LICENSE) | Open-source, research, academic, personal use |
| [Apache 2.0](LICENSE-APACHE) | Patent protection, institutional, commercial deployment |

You may choose either license. **Contributors automatically grant rights under both** — see [CLA.md](CLA.md) for the full contributor agreement.

### Trademark

The **MegaZero** name and logo are trademarks of MegaZero Labs. This license does not grant permission to use them to imply endorsement or affiliation. See [TRADEMARK.md](TRADEMARK.md) for permitted and prohibited uses.

### Contributor Protections

- You **retain copyright** of your contributions
- **Patent grant** (Apache 2.0) shields you from patent claims by other contributors
- Your contributions are **permanently attributed** in commit history and [NOTICE](NOTICE)
- No trademark rights are transferred by contributing

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLA.md](CLA.md). Implement a trait, submit a PR:
- CI workflow guide: [docs/ci-map.md](docs/ci-map.md)
- New `Provider` → `src/providers/`
- New `Channel` → `src/channels/`
- New `Observer` → `src/observability/`
- New `Tool` → `src/tools/`
- New `Memory` → `src/memory/`
- New `Tunnel` → `src/tunnel/`
- New `Skill` → `~/.mega-zero/workspace/skills/<name>/`

---

**MegaZero** — Zero overhead. Zero compromise. Deploy anywhere. Swap anything. 🦀

## Star History

<p align="center">
  <a href="https://www.star-history.com/#openagen/mega-zero&type=date&legend=top-left">
    <picture>
     <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=openagen/mega-zero&type=date&theme=dark&legend=top-left" />
     <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=openagen/mega-zero&type=date&legend=top-left" />
     <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=openagen/mega-zero&type=date&legend=top-left" />
    </picture>
  </a>
</p>
