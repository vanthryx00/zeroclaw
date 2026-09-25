#!/bin/bash

# Token burn monitoring utility
# Shows current session token usage and capacity

set -e

SNAPSHOT_DIR="$HOME/.claude/session-snapshots"
LOG_FILE="$SNAPSHOT_DIR/token-burn.log"

mkdir -p "$SNAPSHOT_DIR"

# Color codes
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Calculate rough token estimate (1 line ≈ 50 tokens average)
if [ -f "$LOG_FILE" ]; then
    LINES=$(wc -l < "$LOG_FILE")
    APPROX_TOKENS=$((LINES * 50))
else
    LINES=0
    APPROX_TOKENS=0
fi

# Context window estimate (approximately 100k token window)
WINDOW_SIZE=100000
CAPACITY_PERCENT=$((APPROX_TOKENS * 100 / WINDOW_SIZE))
REMAINING=$((WINDOW_SIZE - APPROX_TOKENS))

# Display status
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}Token Burn Status${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""
echo "Session Log File: $LOG_FILE"
echo "Snapshot Directory: $SNAPSHOT_DIR"
echo ""
echo "Activity Log Lines: $LINES"
echo "Approx. Tokens Used: $APPROX_TOKENS / $WINDOW_SIZE"
echo "Capacity Used: $CAPACITY_PERCENT%"
echo "Remaining Capacity: $REMAINING tokens"
echo ""

# Capacity warning
if [ $CAPACITY_PERCENT -ge 90 ]; then
    echo -e "${RED}🔴 CRITICAL: >90% capacity${NC} - Compact immediately!"
    echo "   Run: /compact"
elif [ $CAPACITY_PERCENT -ge 75 ]; then
    echo -e "${YELLOW}🟡 WARNING: >75% capacity${NC} - Consider compacting soon"
elif [ $CAPACITY_PERCENT -ge 50 ]; then
    echo -e "${YELLOW}🟡 HIGH: >50% capacity${NC} - Monitor usage"
else
    echo -e "${GREEN}🟢 OK: <50% capacity${NC}"
fi

echo ""

# List recent snapshots
if ls "$SNAPSHOT_DIR"/*.md &>/dev/null; then
    echo -e "${BLUE}Recent Snapshots:${NC}"
    ls -lt "$SNAPSHOT_DIR"/*.md | head -5 | awk '{print "  " $9 " (" $6 " " $7 " " $8 ")"}'
    echo ""
fi

# Show tail of log if in high capacity
if [ $CAPACITY_PERCENT -ge 50 ]; then
    echo -e "${BLUE}Recent Activity:${NC}"
    tail -5 "$LOG_FILE" | sed 's/^/  /'
    echo ""
fi

echo -e "${BLUE}════════════════════════════════════════${NC}"
