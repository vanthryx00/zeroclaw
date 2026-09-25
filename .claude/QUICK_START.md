# Token Monitoring Quick Start

## One-Line Check
```bash
bash .claude/check-tokens.sh
```

## Status Indicators
- 🟢 **Green** (<50%): All good, keep working
- 🟡 **Yellow** (50-75%): Monitor usage, be ready to compact
- 🟡 **Orange** (75-90%): Compact soon
- 🔴 **Red** (>90%): **Compact now!** (`/compact`)

## What Auto-Triggers

| Event | Action |
|-------|--------|
| Tool use (Bash, Read, Edit, Write) | Logs activity + checks capacity |
| Message submission | Logs + calculates token estimate |
| Capacity >75% | Auto-creates snapshot with recommendations |
| Run `/compact` | Resets log, creates post-compact snapshot |

## Snapshots Location
All snapshots and logs stored in: `~/.claude/session-snapshots/`

View recent ones:
```bash
ls -lt ~/.claude/session-snapshots/*.md | head -5
```

## Current Setup
- **Context Window**: ~100,000 tokens
- **Alert Level**: 75,000 tokens (~75%)
- **Activity Tracking**: PreToolUse + UserPromptSubmit hooks
- **Auto-snapshot**: When capacity approaches limits

## Full Documentation
See `TOKEN_MONITORING.md` for detailed configuration and troubleshooting.
