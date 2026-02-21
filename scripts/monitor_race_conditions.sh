#!/bin/bash
#
# Race Condition Monitoring Script (v6.41)
# Monitors logs for signs of race conditions in production
#
# Usage: ./scripts/monitor_race_conditions.sh [interval_seconds]
#

INTERVAL=${1:-60}  # Default: check every 60 seconds
LOG_FILE="logs/auto_trading.log"
ALERT_FILE="logs/race_condition_alerts.log"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Race Condition Monitor (v6.41)"
echo "=========================================="
echo "Monitoring: $LOG_FILE"
echo "Alerts: $ALERT_FILE"
echo "Interval: ${INTERVAL}s"
echo "Press Ctrl+C to stop"
echo ""

# Create alert file if doesn't exist
touch "$ALERT_FILE"

# Counters
TOTAL_CHECKS=0
ALERTS_FOUND=0

while true; do
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    echo "[$TIMESTAMP] Check #$TOTAL_CHECKS"

    # Check for each race condition pattern
    FOUND_ISSUES=0

    # 1. Double-buy race
    DOUBLE_BUY=$(tail -n 1000 "$LOG_FILE" 2>/dev/null | grep -c "double-buy race detected")
    if [ "$DOUBLE_BUY" -gt 0 ]; then
        echo -e "${RED}⚠️  ALERT: Double-buy race detected ($DOUBLE_BUY occurrences)${NC}"
        echo "[$TIMESTAMP] Double-buy race: $DOUBLE_BUY occurrences" >> "$ALERT_FILE"
        FOUND_ISSUES=$((FOUND_ISSUES + 1))
    fi

    # 2. Queue duplicate execution
    QUEUE_DUP=$(tail -n 1000 "$LOG_FILE" 2>/dev/null | grep -c "duplicate execution race detected")
    if [ "$QUEUE_DUP" -gt 0 ]; then
        echo -e "${RED}⚠️  ALERT: Queue duplicate execution ($QUEUE_DUP occurrences)${NC}"
        echo "[$TIMESTAMP] Queue duplicate: $QUEUE_DUP occurrences" >> "$ALERT_FILE"
        FOUND_ISSUES=$((FOUND_ISSUES + 1))
    fi

    # 3. DB rollback (position creation failed)
    ROLLBACK=$(tail -n 1000 "$LOG_FILE" 2>/dev/null | grep -c "ROLLBACK")
    if [ "$ROLLBACK" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  WARNING: DB rollback detected ($ROLLBACK occurrences)${NC}"
        echo "[$TIMESTAMP] DB rollback: $ROLLBACK occurrences" >> "$ALERT_FILE"
        FOUND_ISSUES=$((FOUND_ISSUES + 1))
    fi

    # 4. Scan lock stuck
    SCAN_STUCK=$(tail -n 1000 "$LOG_FILE" 2>/dev/null | grep -c "SCAN LOCK STUCK")
    if [ "$SCAN_STUCK" -gt 0 ]; then
        echo -e "${RED}⚠️  ALERT: Scan lock stuck ($SCAN_STUCK occurrences)${NC}"
        echo "[$TIMESTAMP] Scan lock stuck: $SCAN_STUCK occurrences" >> "$ALERT_FILE"
        FOUND_ISSUES=$((FOUND_ISSUES + 1))
    fi

    # 5. RuntimeError (iteration issues)
    RUNTIME_ERR=$(tail -n 1000 "$LOG_FILE" 2>/dev/null | grep -c "RuntimeError")
    if [ "$RUNTIME_ERR" -gt 0 ]; then
        echo -e "${RED}⚠️  ALERT: RuntimeError detected ($RUNTIME_ERR occurrences)${NC}"
        echo "[$TIMESTAMP] RuntimeError: $RUNTIME_ERR occurrences" >> "$ALERT_FILE"
        FOUND_ISSUES=$((FOUND_ISSUES + 1))
    fi

    # 6. Opening window stagger violations
    STAGGER_VIOL=$(tail -n 1000 "$LOG_FILE" 2>/dev/null | grep "Opening stagger: buy" | wc -l)
    if [ "$STAGGER_VIOL" -gt 2 ]; then
        echo -e "${YELLOW}⚠️  WARNING: Unusual opening window activity ($STAGGER_VIOL buys)${NC}"
    fi

    # 7. UI socket/polling race (check browser console logs if available)
    # This requires manual browser inspection

    # Summary
    if [ "$FOUND_ISSUES" -eq 0 ]; then
        echo -e "${GREEN}✅ No race conditions detected${NC}"
    else
        ALERTS_FOUND=$((ALERTS_FOUND + FOUND_ISSUES))
        echo -e "${RED}❌ Found $FOUND_ISSUES issue(s) - Check $ALERT_FILE${NC}"
    fi

    echo "Total alerts since start: $ALERTS_FOUND"
    echo ""

    # Wait for next check
    sleep "$INTERVAL"
done
