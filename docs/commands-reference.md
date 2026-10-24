# MegaZero Commands Reference

This reference is derived from the current CLI surface (`mega-zero --help`).

Last verified: **April 2, 2026**.

## Top-Level Commands

| Command | Purpose |
|---|---|
| `onboard` | Initialize workspace/config quickly or interactively |
| `agent` | Run interactive chat or single-message mode |
| `prime` | Run Prime Zero (hybrid orchestrator over the native agent with Empire goals + Companion task context) |
| `gateway` | Start webhook and WhatsApp HTTP gateway |
| `daemon` | Start supervised runtime (gateway + channels + optional heartbeat/scheduler) |
| `service` | Manage user-level OS service lifecycle |
| `doctor` | Run diagnostics and freshness checks |
| `status` | Print current configuration and system summary |
| `cron` | Manage scheduled tasks |
| `models` | Refresh provider model catalogs |
| `providers` | List provider IDs, aliases, and active provider |
| `channel` | Manage channels and channel health checks |
| `integrations` | Inspect integration details |
| `skills` | List/install/remove skills |
| `migrate` | Import from external runtimes (currently OpenClaw) |
| `config` | Export machine-readable config schema |
| `completions` | Generate shell completion scripts to stdout |
| `auth` | Manage provider auth profiles and the local secret key |
| `hardware` | Discover and introspect USB hardware |
| `peripheral` | Configure and flash peripherals |

## Command Groups

### `onboard`

- `mega-zero onboard`
- `mega-zero onboard --interactive`
- `mega-zero onboard --channels-only`
- `mega-zero onboard --force`
- `mega-zero onboard --api-key <KEY> --provider <ID> --memory <sqlite|lucid|markdown|none>`
- `mega-zero onboard --api-key <KEY> --provider <ID> --model <MODEL_ID> --memory <sqlite|lucid|markdown|none>`
- `mega-zero onboard --api-key <KEY> --provider <ID> --model <MODEL_ID> --memory <sqlite|lucid|markdown|none> --force`

`onboard` safety behavior:

- If `config.toml` already exists, `onboard` asks for explicit confirmation before overwrite.
- In non-interactive environments, existing `config.toml` causes a safe refusal unless `--force` is passed.
- Use `mega-zero onboard --channels-only` when you only need to rotate channel tokens/allowlists.

### `agent`

- `mega-zero agent`
- `mega-zero agent -m "Hello"`
- `mega-zero agent --provider <ID> --model <MODEL> --temperature <0.0-2.0>`
- `mega-zero agent --peripheral <board:path>`

### `prime`

- `mega-zero prime` — interactive session (default)
- `mega-zero prime -m "Build a REST API"` — single message, then exit
- `mega-zero prime -m "..." -i` — send a message, then stay interactive
- `mega-zero prime --provider ollama --model llama3.2` — fully offline
- `mega-zero prime --mission "<statement>"` — set/update the persisted Empire mission

Behavior:

- Provider fallback chain: selected primary, then remaining of Anthropic → Gemini → Ollama.
- Uses SQLite memory and injects `<workspace>/mindset.toml` into the system prompt; state persists in `<workspace>/empire.toml` and `<workspace>/companion_tasks.toml`.
- Each turn is enriched with current Empire goals and enabled Companion tasks.
- Session commands: `/status`, `/metrics` (estimated cost), `/goal <title> | <desc>`, `/done <ID>`, `/active <ID>`, `/blocked <ID>`, `/note <ID> <text>`, `/help`, `/quit`.

### `gateway` / `daemon`

- `mega-zero gateway [--host <HOST>] [--port <PORT>]`
- `mega-zero daemon [--host <HOST>] [--port <PORT>]`

### `service`

- `mega-zero service install`
- `mega-zero service start`
- `mega-zero service stop`
- `mega-zero service restart`
- `mega-zero service status`
- `mega-zero service uninstall`

### `cron`

- `mega-zero cron list`
- `mega-zero cron add <expr> [--tz <IANA_TZ>] <command>`
- `mega-zero cron add-at <rfc3339_timestamp> <command>`
- `mega-zero cron add-every <every_ms> <command>`
- `mega-zero cron once <delay> <command>`
- `mega-zero cron add-agent <prompt> (--cron <expr> | --at <rfc3339_timestamp> | --every-ms <ms>) [--tz <IANA_TZ>] [--name <name>] [--model <model>] [--session-target isolated|main] [--deliver-channel <channel>] [--deliver-to <target>] [--delete-after-run]`
- `mega-zero cron remove <id>`
- `mega-zero cron pause <id>`
- `mega-zero cron resume <id>`

Notes:

- Mutating schedule/cron actions require `cron.enabled = true`.
- Shell command payloads for schedule creation (`create` / `add` / `once`) are validated by security command policy before job persistence.
- `add-agent` creates a self-contained autonomous job: on each firing it runs the given prompt through the agent (no manual trigger needed) and, if `--deliver-channel`/`--deliver-to` are set, posts the result to an already-configured channel (`telegram`, `discord`, `slack`, `mattermost`) via `mode: "announce"` delivery. Exactly one of `--cron`, `--at`, or `--every-ms` must be provided.

### `models`

- `mega-zero models refresh`
- `mega-zero models refresh --provider <ID>`
- `mega-zero models refresh --force`

`models refresh` currently supports live catalog refresh for provider IDs: `openrouter`, `openai`, `anthropic`, `groq`, `mistral`, `deepseek`, `xai`, `together-ai`, `gemini`, `ollama`, `llamacpp`, `astrai`, `venice`, `fireworks`, `cohere`, `moonshot`, `glm`, `zai`, `qwen`, and `nvidia`.

### `channel`

- `mega-zero channel list`
- `mega-zero channel start`
- `mega-zero channel doctor`
- `mega-zero channel bind-telegram <IDENTITY>`
- `mega-zero channel add <type> <json>`
- `mega-zero channel remove <name>`

Runtime in-chat commands (Telegram/Discord while channel server is running):

- `/models`
- `/models <provider>`
- `/model`
- `/model <model-id>`

Channel runtime also watches `config.toml` and hot-applies updates to:
- `default_provider`
- `default_model`
- `default_temperature`
- `api_key` / `api_url` (for the default provider)
- `reliability.*` provider retry settings

`add/remove` currently route you back to managed setup/manual config paths (not full declarative mutators yet).

### `integrations`

- `mega-zero integrations info <name>`

### `skills`

- `mega-zero skills list`
- `mega-zero skills install <source>`
- `mega-zero skills remove <name>`

`<source>` accepts git remotes (`https://...`, `http://...`, `ssh://...`, and `git@host:owner/repo.git`) or a local filesystem path.

Skill manifests (`SKILL.toml`) support `prompts` and `[[tools]]`; both are injected into the agent system prompt at runtime, so the model can follow skill instructions without manually reading skill files.

### `migrate`

- `mega-zero migrate openclaw [--source <path>] [--dry-run]`

### `config`

- `mega-zero config schema`

`config schema` prints a JSON Schema (draft 2020-12) for the full `config.toml` contract to stdout.

### `completions`

- `mega-zero completions bash`
- `mega-zero completions fish`
- `mega-zero completions zsh`
- `mega-zero completions powershell`
- `mega-zero completions elvish`

`completions` is stdout-only by design so scripts can be sourced directly without log/warning contamination.

### `hardware`

- `mega-zero hardware discover`
- `mega-zero hardware introspect <path>`
- `mega-zero hardware info [--chip <chip_name>]`

### `peripheral`

- `mega-zero peripheral list`
- `mega-zero peripheral add <board> <path>`
- `mega-zero peripheral flash [--port <serial_port>]`
- `mega-zero peripheral setup-uno-q [--host <ip_or_host>]`
- `mega-zero peripheral flash-nucleo`

### `auth`

- `mega-zero auth login --provider openai-codex [--device-code]`
- `mega-zero auth paste-redirect --provider openai-codex [--input <URL_OR_CODE>]`
- `mega-zero auth paste-token --provider <ID> [--token <TOKEN>] [--auth-kind <KIND>]`
- `mega-zero auth setup-token --provider <ID>` *(alias for `paste-token`, interactive)*
- `mega-zero auth refresh --provider openai-codex [--profile <NAME>]`
- `mega-zero auth logout --provider <ID> [--profile <NAME>]`
- `mega-zero auth use --provider <ID> --profile <NAME>`
- `mega-zero auth list`
- `mega-zero auth status`
- `mega-zero auth reset-key [--yes]`

`auth reset-key` manages the master secret key used to encrypt stored API keys and tokens:

- Without `--yes`: prints the paths of the secret key file, config, and auth-profiles store so you can locate your credentials.
- With `--yes`: deletes `~/.mega-zero/.secret_key`. A fresh key is generated automatically on the next encryption operation. Any values already encrypted in `config.toml` or `auth-profiles.json` cannot be decrypted with the new key and must be re-entered (via `auth paste-token`, `onboard`, or by editing `config.toml` directly).

## Validation Tip

To verify docs against your current binary quickly:

```bash
mega-zero --help
mega-zero <command> --help
```
