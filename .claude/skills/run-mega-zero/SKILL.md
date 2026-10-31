---
name: run-mega-zero
description: Build, launch, and drive the mega-zero CLI. Use when asked to run, start, build, smoke-test, or check the mega-zero binary and its subcommands (doctor, status, providers, config, completions).
---

# Run mega-zero

`mega-zero` is a Rust CLI (the workspace root binary, package `mega-zero`).
It is driven by running the compiled binary with a subcommand and asserting
exit code + output. The agent path is the smoke driver
`.claude/skills/run-mega-zero/smoke.sh`, which builds if needed and exercises
the offline-safe subcommands.

Paths below are relative to the repo root (`<unit>/`).

## Prerequisites

The container's default Rust toolchain is enough — no extra `apt-get` was
needed. Commands that reach models/channels need network + API keys; the
smoke set below avoids those entirely.

## Build

```bash
cargo build            # debug; first clean build can exceed 2 min
```

The first full build does not finish inside a 120 s foreground limit — run it
in the background and wait, or expect the driver's inline build to take a
while. The debug binary lands at `target/debug/mega-zero` (~385 MB).
`cargo build --release` likewise exceeds 120 s; background it too.

## Run (agent path)

```bash
.claude/skills/run-mega-zero/smoke.sh
```

Builds `target/debug/mega-zero` if absent, then checks each subcommand's exit
code and key output. Prints `== ALL PASS ==` and exits 0 on success; exits 1
with the offending output on any failure. To drive a prebuilt binary (e.g. a
release build) without rebuilding:

```bash
MZ_BIN=target/release/mega-zero .claude/skills/run-mega-zero/smoke.sh
```

Individually, the verified offline-safe commands (all exit 0):

```bash
target/debug/mega-zero --version          # -> mega_zero 0.1.0
target/debug/mega-zero --help             # command list
target/debug/mega-zero providers          # 42 providers table
target/debug/mega-zero status             # runtime status snapshot
target/debug/mega-zero doctor             # config/workspace/channel diagnostics
target/debug/mega-zero config schema      # full config JSON Schema
target/debug/mega-zero completions bash   # shell completion script
```

## Run (human path)

`cargo run -- <subcommand>` works but recompiles; for repeated runs use the
built binary directly as above. `mega-zero agent`, `prime`, `gateway`, and
`daemon` start interactive/long-running sessions that need a provider API key
or bound ports — not useful headless without config.

## Gotchas

- **`config loaded` log line pollutes stdout.** Several subcommands
  (`providers`, `config schema`, `doctor`) emit an INFO tracing line before
  their real output. `config schema` is therefore **not** parseable as JSON
  straight from line 1 — strip the leading log line before piping to a JSON
  parser.
- **Piping to `head` shows exit 101, not a real failure.** `providers` and
  `config schema` print 40+ lines; `… | head` closes the pipe early and the
  binary dies on SIGPIPE (exit 101). Capture to a file, then truncate — the
  driver does this.
- **Bare `models` / `config` / `integrations` exit 2.** They require a
  sub-subcommand (`models refresh`, `config schema`, `integrations info
  <name>`). Exit 2 is clap's usage error, expected — the driver asserts it.
- **`models refresh` hits the network** to fetch provider catalogs; excluded
  from the offline smoke set.
- **Binary is ~385 MB (debug)** and the full build is slow; always background
  a clean build.

## Troubleshooting

- **`could not compile mega-zero`** after a branch merge: check `src/prime/`
  and `src/offline/empire.rs` for API drift, and `src/main.rs` for duplicated
  `Prime` subcommand variants. The bin re-declares modules locally
  (`mod config; mod prime; …`) but re-exports a few from the lib crate
  (`mod offline { pub use mega_zero::offline::* }`); mixing a bin-local module
  with a lib-exported one yields "multiple different versions of crate
  `mega_zero`" type mismatches — keep a module's siblings on the same side.
- **`cargo build` exits 0 but no binary**: you piped to `tail`/`head`; check
  `${PIPESTATUS[0]}`, not `$?`.
