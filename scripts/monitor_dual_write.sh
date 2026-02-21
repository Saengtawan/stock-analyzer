#!/bin/bash
# Monitor Dual-Write Phase 1B
# Compare JSON vs DB to ensure consistency

set -e

DB_PATH="data/trade_history.db"

echo "========================================"
echo "Phase 1B: Dual-Write Monitoring"
echo "========================================"
echo ""
echo "Date: $(date)"
echo ""

# ========================================
# 1. Signals Count Comparison
# ========================================
echo "📊 1. SIGNALS COUNT COMPARISON"
echo "----------------------------------------"

# JSON count
if [ -f "data/cache/rapid_signals.json" ]; then
    JSON_ACTIVE=$(cat data/cache/rapid_signals.json | jq '.count // 0')
    JSON_WAITING=$(cat data/cache/rapid_signals.json | jq '.waiting_signals | length // 0')
    echo "JSON:"
    echo "  Active: $JSON_ACTIVE"
    echo "  Waiting: $JSON_WAITING"
else
    echo "JSON: File not found"
    JSON_ACTIVE=0
    JSON_WAITING=0
fi

# DB count
DB_ACTIVE=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM trading_signals WHERE status='active'" 2>/dev/null || echo "0")
DB_WAITING=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM trading_signals WHERE status='waiting'" 2>/dev/null || echo "0")
echo ""
echo "DB:"
echo "  Active: $DB_ACTIVE"
echo "  Waiting: $DB_WAITING"
echo ""

# Compare
if [ "$JSON_ACTIVE" -eq "$DB_ACTIVE" ] && [ "$JSON_WAITING" -eq "$DB_WAITING" ]; then
    echo "✅ Signals count MATCH"
else
    echo "❌ Signals count MISMATCH!"
    echo "   Active: JSON=$JSON_ACTIVE, DB=$DB_ACTIVE"
    echo "   Waiting: JSON=$JSON_WAITING, DB=$DB_WAITING"
fi
echo ""

# ========================================
# 2. Queue Count Comparison
# ========================================
echo "📋 2. QUEUE COUNT COMPARISON"
echo "----------------------------------------"

# JSON queue count
if [ -f "data/signal_queue.json" ]; then
    JSON_QUEUE=$(cat data/signal_queue.json | jq '.count // 0')
    echo "JSON Queue: $JSON_QUEUE"
else
    echo "JSON Queue: File not found"
    JSON_QUEUE=0
fi

# DB queue count
DB_QUEUE=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM signal_queue WHERE status='waiting'" 2>/dev/null || echo "0")
echo "DB Queue: $DB_QUEUE"
echo ""

# Compare
if [ "$JSON_QUEUE" -eq "$DB_QUEUE" ]; then
    echo "✅ Queue count MATCH"
else
    echo "❌ Queue count MISMATCH!"
    echo "   JSON=$JSON_QUEUE, DB=$DB_QUEUE"
fi
echo ""

# ========================================
# 3. Latest Scan Session
# ========================================
echo "🔍 3. LATEST SCAN SESSION"
echo "----------------------------------------"

LATEST_SCAN=$(sqlite3 "$DB_PATH" "SELECT session_type, datetime(scan_time, 'localtime'), signal_count, waiting_count FROM scan_sessions ORDER BY scan_time DESC LIMIT 1" 2>/dev/null || echo "")

if [ -n "$LATEST_SCAN" ]; then
    echo "$LATEST_SCAN" | awk -F'|' '{printf "Type: %s\nTime: %s\nSignals: %s active, %s waiting\n", $1, $2, $3, $4}'
else
    echo "No scan sessions found"
fi
echo ""

# ========================================
# 4. Execution History (Last 1 Hour)
# ========================================
echo "📝 4. EXECUTION HISTORY (Last 1 Hour)"
echo "----------------------------------------"

EXEC_SUMMARY=$(sqlite3 "$DB_PATH" "
SELECT
    action,
    COUNT(*) as count
FROM execution_history
WHERE timestamp >= datetime('now', '-1 hour')
GROUP BY action
ORDER BY count DESC
" 2>/dev/null || echo "")

if [ -n "$EXEC_SUMMARY" ]; then
    echo "$EXEC_SUMMARY" | awk -F'|' '{printf "  %s: %s\n", $1, $2}'
else
    echo "  No executions in last hour"
fi
echo ""

# ========================================
# 5. Database Size
# ========================================
echo "💾 5. DATABASE SIZE"
echo "----------------------------------------"

if [ -f "$DB_PATH" ]; then
    DB_SIZE=$(du -h "$DB_PATH" | awk '{print $1}')
    echo "  Trade History DB: $DB_SIZE"
fi

# Table row counts
echo ""
echo "  Row counts:"
sqlite3 "$DB_PATH" "
SELECT '  - trading_signals: ' || COUNT(*) FROM trading_signals
UNION ALL SELECT '  - execution_history: ' || COUNT(*) FROM execution_history
UNION ALL SELECT '  - signal_queue: ' || COUNT(*) FROM signal_queue
UNION ALL SELECT '  - scan_sessions: ' || COUNT(*) FROM scan_sessions
" 2>/dev/null || echo "  Error reading counts"
echo ""

# ========================================
# 6. Error Check
# ========================================
echo "🔍 6. ERROR CHECK (Last 100 Lines)"
echo "----------------------------------------"

if [ -f "nohup.out" ]; then
    ERROR_COUNT=$(tail -100 nohup.out | grep -c "DB.*failed\|DB.*error" || echo "0")
    echo "  DB errors in last 100 log lines: $ERROR_COUNT"

    if [ "$ERROR_COUNT" -gt "0" ]; then
        echo ""
        echo "  Recent DB errors:"
        tail -100 nohup.out | grep "DB.*failed\|DB.*error" | tail -5 | sed 's/^/    /'
    fi
else
    echo "  nohup.out not found"
fi
echo ""

# ========================================
# Summary
# ========================================
echo "========================================"
echo "SUMMARY"
echo "========================================"

ISSUES=0

if [ "$JSON_ACTIVE" -ne "$DB_ACTIVE" ] || [ "$JSON_WAITING" -ne "$DB_WAITING" ]; then
    echo "❌ Signals count mismatch"
    ISSUES=$((ISSUES + 1))
else
    echo "✅ Signals count OK"
fi

if [ "$JSON_QUEUE" -ne "$DB_QUEUE" ]; then
    echo "❌ Queue count mismatch"
    ISSUES=$((ISSUES + 1))
else
    echo "✅ Queue count OK"
fi

if [ "$ERROR_COUNT" -gt "0" ]; then
    echo "⚠️  DB errors detected ($ERROR_COUNT)"
    ISSUES=$((ISSUES + 1))
else
    echo "✅ No DB errors"
fi

echo ""
if [ "$ISSUES" -eq "0" ]; then
    echo "✅ All checks passed - Dual-write working correctly"
    exit 0
else
    echo "❌ $ISSUES issue(s) detected - Review above"
    exit 1
fi
