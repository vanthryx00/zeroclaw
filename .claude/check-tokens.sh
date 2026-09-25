#!/bin/bash

# Token burn rate monitor
# Tracks burn rate (tokens/turn) - compacts when >1500/turn

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

# Calculate burn rate (1 line ≈ 50 tokens)
if [ -f "$LOG_FILE" ]; then
    TOTAL_LINES=$(wc -l < "$LOG_FILE")
    # Recent burn rate: last 3 turns
    RECENT_LINES=$(tail -3 "$LOG_FILE" | wc -l)
    BURN_RATE=$((RECENT_LINES * 50))
else
    TOTAL_LINES=0
    RECENT_LINES=0
    BURN_RATE=0
fi

# Display status
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}Token Burn Rate Monitor${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""
echo "Session Log: $LOG_FILE"
echo ""
echo "Total Turns Logged: $TOTAL_LINES"
echo "Recent Burn Rate (last 3 turns): ${BURN_RATE} tokens/turn"
echo "Threshold: 1500 tokens/turn"
echo ""

# Burn rate warning
THRESHOLD=1500
if [ $BURN_RATE -ge $THRESHOLD ]; then
    echo -e "${RED}🔥 CRITICAL BURN RATE${NC}"
    echo -e "${RED}Current: ${BURN_RATE} tokens/turn (exceeds ${THRESHOLD})${NC}"
    echo ""
    echo -e "${RED}ACTION: Run /compact immediately${NC}"
    echo "        Compaction resets context and minimizes token waste"
    echo ""
elif [ $BURN_RATE -ge 1000 ]; then
    echo -e "${YELLOW}🟡 HIGH BURN RATE${NC}"
    echo "Current: ${BURN_RATE} tokens/turn (approaching ${THRESHOLD})"
    echo "Monitor closely - be ready to /compact"
    echo ""
elif [ $BURN_RATE -gt 500 ]; then
    echo -e "${YELLOW}🟡 MODERATE BURN${NC}"
    echo "Current: ${BURN_RATE} tokens/turn"
    echo "Continue working - will alert when approaching ${THRESHOLD}"
    echo ""
else
    echo -e "${GREEN}🟢 HEALTHY BURN RATE${NC}"
    echo "Current: ${BURN_RATE} tokens/turn"
    echo "Keep working efficiently"
    echo ""
fi

# List burn alerts
if ls "$SNAPSHOT_DIR"/BURN-ALERT-*.md &>/dev/null 2>&1; then
    echo -e "${RED}Recent Burn Alerts:${NC}"
    ls -lt "$SNAPSHOT_DIR"/BURN-ALERT-*.md 2>/dev/null | head -3 | awk '{print "  " $9}'
    echo ""
fi

# Show last reset
if ls "$SNAPSHOT_DIR"/RESET-*.md &>/dev/null 2>&1; then
    echo -e "${GREEN}Last Context Reset:${NC}"
    ls -lt "$SNAPSHOT_DIR"/RESET-*.md 2>/dev/null | head -1 | awk '{print "  " $9 " (" $6 " " $7 " " $8 ")"}'
    echo ""
fi

echo -e "${BLUE}════════════════════════════════════════${NC}"
