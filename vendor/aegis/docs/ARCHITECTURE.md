# Architecture

## Data flow of a single request

```
user text
   │
   ▼
Memory.add("user", text)
   │
   ▼
┌───────────────────────── Agent.ask() loop ─────────────────────────┐
│                                                                    │
│  messages = system_prompt + transcript                             │
│      │                                                             │
│      ▼                                                             │
│  BackendRouter.generate(messages)                                  │
│      │  (tries ollama, then llama.cpp; fails over on error)        │
│      ▼                                                             │
│  model reply                                                       │
│      │                                                             │
│      ├── no ```aegis-command``` block ──► final answer, return     │
│      │                                                             │
│      └── command block found                                       │
│             │                                                      │
│             ▼                                                      │
│          Executor.run(cmd)                                         │
│             │                                                      │
│             ├─ safety.classify()  ──► Verdict(level, reason)       │
│             ├─ safety.decide()    ──► auto / needs confirm         │
│             ├─ confirm callback   ──► user y/n                     │
│             ├─ subprocess.run(shell=True, timeout=...)             │
│             └─ audit.record(...)                                   │
│             │                                                      │
│             ▼                                                      │
│          observation appended to transcript                        │
│             │                                                      │
│             └────────────► loop (max_tool_rounds)                  │
└────────────────────────────────────────────────────────────────────┘
```

## Why a text protocol instead of native tool-calling

Local models vary widely in whether they support structured function calling.
A fenced-block protocol (` ```aegis-command `) works across Ollama and
llama.cpp models alike, is trivially auditable, and keeps the loop small. A
future version can add native tool-calling for models that support it.

## Modules

| Module | Responsibility | Depends on |
|--------|----------------|------------|
| `config.py` | Load TOML + env, validate, defaults | stdlib |
| `safety.py` | Classify commands, enforce scope, decide | stdlib |
| `executor.py` | The **only** shell spawn; audit every run | safety, audit |
| `audit.py` | Append-only JSONL log | stdlib |
| `context.py` | Non-sensitive system snapshot | stdlib |
| `memory.py` | Transcript + lesson store | brain |
| `prompts.py` | System prompt | — |
| `brain/base.py` | Backend interface | — |
| `brain/ollama_backend.py` | Ollama HTTP transport | httpx |
| `brain/llamacpp_backend.py` | llama.cpp server/CLI transport | httpx, subprocess |
| `brain/router.py` | Selection + failover | backends |
| `agent.py` | Orchestration loop | all of the above |
| `cli.py` / `tui.py` / `gui.py` | Front-ends | agent |

## Extension points

* **New backend**: subclass `brain.base.Backend`, register in `router._build`.
* **New command categories**: extend the rule tables in `safety.py`.
* **New front-end**: drive `Agent.ask(text, on_text=..., on_command=...)`.
* **Knowledge**: drop `.md` files into `aegis/knowledge/` (bundled) or
  `~/.local/share/aegis/knowledge/` (user).

## Security properties

1. **Single choke point** — only `Executor._spawn` calls `subprocess`. Auditing
   and classification cannot be bypassed by a front-end.
2. **Fail closed** — unknown binaries classify as `RISKY`, so `auto_safe` will
   not auto-run them.
3. **Immutable hard blocks** — evaluated before any mode logic.
4. **Scope enforcement** — offensive tools parse their target and compare
   against the declared scope (IP/CIDR containment + wildcard hostnames).
5. **No secret harvesting** — `context.py` never reads arbitrary environment
   variables, only a small whitelist (`USER`, `SHELL`).

## Performance notes

* `qwen2.5-coder:7b` is a good default balance (≈4.5 GB, runs on 8 GB RAM with
  a quantised build). Use `qwen2.5-coder:1.5b` for low-RAM machines.
* `max_tool_rounds` bounds the number of model↔shell round-trips per request to
  keep latency predictable.
* `command_timeout` caps any single command (default 120 s).
