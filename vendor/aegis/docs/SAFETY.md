# Safety Model

Aegis runs shell commands on your machine. This document describes exactly how
it decides what is allowed.

## Layers

```
command string
   │
   ▼
1. Hard blocks          ──► BLOCKED (never runs, any mode)
   │
   ▼
2. Offensive tools      ──► OFFENSIVE (needs target in declared scope)
   │
   ▼
3. Risky patterns       ──► RISKY (rm, dd, mkfs, service stops, ...)
   │
   ▼
4. Protected paths      ──► RISKY (writes to /etc, /boot, /usr, ...)
   │
   ▼
5. Known binaries       ──► READ_ONLY or SAFE_WRITE
   │
   ▼
6. Unknown binaries     ──► RISKY (fail closed)
   │
   ▼
mode decision  ──► auto-run | ask | deny | dry-run
```

## Levels

| Level | Meaning | Auto in `auto_safe`? |
|-------|---------|----------------------|
| `READ_ONLY` | inspects state | yes |
| `SAFE_WRITE` | writes only inside the workspace | yes |
| `RISKY` | destructive or system-wide | no — asks |
| `OFFENSIVE` | security tool vs a target | no — asks (and needs scope) |
| `BLOCKED` | catastrophic | never |

## Modes

| Mode | Auto-runs | Asks about | Blocks |
|------|-----------|------------|--------|
| `confirm` | nothing | everything allowed | hard blocks |
| `auto_safe` | read-only, safe-write | risky, offensive | hard blocks |
| `auto_full` | everything | — | hard blocks |
| `dry_run` | nothing | — | everything (shows only) |

## Hard-blocked patterns (excerpt)

These are refused in every mode, including `auto_full`:

- `rm -rf /` and `rm -rf /*`
- `dd ... of=/dev/sda|nvme0n1|vda|mmcblk*` (raw disk overwrite)
- `mkfs.* /dev/sd*`
- fork bombs (`:(){ :|:& };:`)
- `curl … | bash` / `wget … | bash` (pipe remote script to shell)
- reverse shells (`nc -e`, `bash -i >& /dev/tcp/…`)
- writes to `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`

The full tables live in `aegis/safety.py` (`BLOCKED_PATTERNS`,
`RISKY_PATTERNS`, `OFFENSIVE_TOOLS`).

## Authorized scope

Offensive tools (`nmap`, `sqlmap`, `hydra`, `msfconsole`, …) extract their
target and compare it to your declared scope:

```bash
aegis scope add 10.0.0.0/24
aegis scope add '*.lab.example.com'
```

* IP targets are matched by CIDR containment (`10.0.0.5` ∈ `10.0.0.0/24`).
* Hostnames match exactly, or by `*.domain` wildcard.
* If the target is outside scope, the command is **refused** and the reason is
  shown. If no scope is declared, offensive tools are refused entirely.

## sudo

`sudo` is disabled unless `safety.allow_sudo = true` (or `AEGIS_ALLOW_SUDO=1`).
Even when enabled, a sudo command still passes through classification.

## Audit log

Every decision is appended to `~/.local/share/aegis/audit.jsonl`:

```json
{"ts": 1712345678.9, "event": "execute", "command": "nmap -sV 10.0.0.5",
 "level": "offensive", "mode": "auto_safe", "decision": "confirmed",
 "reason": "nmap against authorized target(s): 10.0.0.5",
 "exit_code": 0, "duration": 4.2, "output_preview": "..."}
```

View it with `aegis audit -n 50`. The log is append-only; Aegis never rewrites
history.

## GUI actions

Desktop actions (`gui:click …`, `gui:type …`, …) are classified by their own
rules in `safety.classify`, before the shell patterns:

| GUI action | Level |
|---|---|
| `gui:screenshot`, `gui:size`, `gui:move_to` | READ_ONLY |
| `gui:click`, `gui:type`, `gui:key`, `gui:hotkey`, `gui:scroll`, `gui:drag` | RISKY |
| `gui:type` with credential-shaped text (`password=…`, API keys, tokens, private keys) | BLOCKED |
| `gui:type` with destructive text (`rm -rf`, `mkfs`, `format C:`, …) | BLOCKED |
| unknown `gui:` verb, unparseable coordinates | RISKY (fail closed) |

GUI actions are executed by `GuiExecutor`, which mirrors `Executor`:
classify → decide → confirm → execute → audit (`event="gui"`). Typed text
is redacted in the audit log (`gui:type <redacted>`). See
[`DESKTOP.md`](DESKTOP.md).

## What the guardrails are NOT

They are **not** a sandbox. Aegis runs as your user with your privileges. A
cleverly constructed command could still do damage. Treat `auto_full` as
dangerous, review commands before approving them, and keep backups. The
guardrails reduce accidents and enforce your declared scope; they do not
replace judgment or authorization.

## Reporting a bypass

If you find a pattern that should be blocked but is not, add it to
`BLOCKED_PATTERNS` in `aegis/safety.py` and add a test case to
`tests/test_safety.py`.
