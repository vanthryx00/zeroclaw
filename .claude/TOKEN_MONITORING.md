# Token Burn Monitoring Setup

## Overview
This project is configured with automatic token-burn hooks that monitor Claude Code session usage and trigger auto-summarization when capacity approaches limits.

## How It Works

### Hooks Configuration
Three hooks are active in `.claude/settings.json`:

1. **PreToolUse Hook** (Bash, Read, Edit, Write, Grep, Glob)
   - Logs each tool invocation with timestamp
   - Monitors for approaching token limits
   - Stored in: `~/.claude/session-snapshots/token-burn.log`

2. **UserPromptSubmit Hook**
   - Logs each message submission
   - Calculates approximate token usage (rough estimate: ~50 tokens per activity line)
   - Triggers snapshot when capacity exceeds 75% (~75k tokens)
   - Auto-creates snapshot files with analysis and recommendations

3. **PostCompact Hook**
   - Resets token burn log after conversation compaction
   - Creates post-compact snapshot for audit trail
   - Allows fresh monitoring cycle

### Capacity Thresholds

| Capacity | Status | Action |
|----------|--------|--------|
| < 50% | ✅ OK | Normal operation |
| 50-75% | 🟡 HIGH | Monitor usage closely |
| 75-90% | 🟡 WARNING | Consider compacting soon |
| > 90% | 🔴 CRITICAL | Compact immediately |

## Checking Token Status

Run the token monitoring utility anytime:
```bash
bash .claude/check-tokens.sh
```

This shows:
- Current token estimate
- Capacity percentage
- Recent activity log
- List of saved snapshots
- Recommendations for action

## Session Snapshots

Automatic snapshots are saved to `~/.claude/session-snapshots/`:

- **snapshot-YYYYMMDD-HHMMSS.md** - Auto-triggered when >75% capacity
- **post-compact-YYYYMMDD-HHMMSS.md** - Created after running `/compact`
- **token-burn.log** - Activity log (automatically reset after compaction)

Each snapshot includes:
- Token burn analysis
- Capacity usage percentage
- Recent activity log
- Recommended actions (compact, new session, etc.)

## Integration with `/compact`

The setup integrates with Claude Code's built-in `/compact` command:

1. When you run `/compact`, the PostCompact hook triggers
2. Token burn log is reset to zero
3. A post-compact snapshot is saved for audit trail
4. Monitoring resumes with a fresh context window

## Manual Compaction Trigger

If approaching >75% capacity and hooks haven't created a snapshot yet:

```bash
# View current status
bash .claude/check-tokens.sh

# If high capacity, compact the conversation
# (Type this in Claude Code's prompt)
/compact

# Verify reset
bash .claude/check-tokens.sh
```

## Customization

To adjust thresholds, edit `.claude/settings.json`:

- **Hook timeout**: Change `"timeout": 5` to adjust maximum wait
- **Threshold**: Edit the `[ $APPROX_TOKENS -gt 75000 ]` condition
  - 75000 = 75% of ~100k token window
  - Adjust based on your actual window size

### Window Size Estimation

The current setup assumes:
- ~100k token context window
- ~50 tokens per activity line (rough estimate)
- Adjust the multiplier if your model has different limits

To fine-tune:
```bash
# Check lines in current log
wc -l ~/.claude/session-snapshots/token-burn.log

# Adjust multiplier in hooks if needed
# (multiply by different factor to match actual token estimates)
```

## Examples

### Scenario 1: Normal Operation
```
$ bash .claude/check-tokens.sh

Approx. Tokens Used: 15,000 / 100,000
Capacity Used: 15%
🟢 OK: <50% capacity
```

### Scenario 2: Approaching Limit
```
$ bash .claude/check-tokens.sh

Approx. Tokens Used: 78,000 / 100,000
Capacity Used: 78%
🟡 WARNING: >75% capacity - Consider compacting soon

Recent Snapshots:
  ~/.claude/session-snapshots/snapshot-20260925-143022.md
```

### Scenario 3: After Compaction
```
# After running /compact:
$ bash .claude/check-tokens.sh

Approx. Tokens Used: 500 / 100,000
Capacity Used: 0%
🟢 OK: <50% capacity

Recent Snapshots:
  ~/.claude/session-snapshots/post-compact-20260925-143500.md
  ~/.claude/session-snapshots/snapshot-20260925-143022.md
```

## Files Reference

- `.claude/settings.json` - Hook definitions
- `.claude/check-tokens.sh` - Status checking utility
- `.claude/.gitignore` - Excludes snapshots and logs from git
- `~/.claude/session-snapshots/` - Snapshot storage directory
- `~/.claude/session-snapshots/token-burn.log` - Activity log

## Tips

1. **Check status regularly**: Run `bash .claude/check-tokens.sh` every few turns if working on complex tasks
2. **Watch for warnings**: Act before reaching critical capacity
3. **Use snapshots for audit**: Save and archive snapshots if tracking work history
4. **Adjust thresholds**: Tune the 75% threshold up/down based on your workflow
5. **Multiple sessions**: Each session gets its own token tracking (fresh context window per session)

## Troubleshooting

### Hooks not running?
- Ensure `.claude/settings.json` is valid JSON: `jq . .claude/settings.json`
- Open `/hooks` to reload configuration
- Check hook output with: `tail -f ~/.claude/session-snapshots/token-burn.log`

### Snapshots not creating?
- Verify directory exists: `mkdir -p ~/.claude/session-snapshots`
- Check permissions: `ls -la ~/.claude/session-snapshots`
- Manually test hooks: `bash .claude/check-tokens.sh`

### Inaccurate token estimates?
- Current estimate: 50 tokens per activity line
- Adjust multiplier in hook commands if tokens are significantly over/under
- Compare with actual Claude Code `/cost` output to calibrate
