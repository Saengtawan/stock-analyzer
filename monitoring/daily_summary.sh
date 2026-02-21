#!/bin/bash
# Daily Trading Summary Report

WORK_DIR="/home/saengtawan/work/project/cc/stock-analyzer"
cd "$WORK_DIR"

DATE=$(date +%Y-%m-%d)
REPORT_FILE="/tmp/daily_summary_${DATE}.txt"

echo "==========================================" > "$REPORT_FILE"
echo "📊 Daily Trading Summary - $DATE" >> "$REPORT_FILE"
echo "==========================================" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Market Alert Status
echo "🔔 Market Status Alert:" >> "$REPORT_FILE"
python3 "$WORK_DIR/monitoring/alert_market_ready.py" >> "$REPORT_FILE" 2>&1
echo "" >> "$REPORT_FILE"

# Validation Monitor
echo "📈 Validation Progress:" >> "$REPORT_FILE"
python3 "$WORK_DIR/monitoring/monitor_validation.py" >> "$REPORT_FILE" 2>&1
echo "" >> "$REPORT_FILE"

# Active Positions
echo "💼 Active Positions:" >> "$REPORT_FILE"
sqlite3 "$WORK_DIR/data/trade_history.db" "SELECT symbol, entry_date, entry_price, stop_loss, day_held FROM active_positions;" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Recent Trades (Today)
echo "📋 Today's Trades:" >> "$REPORT_FILE"
sqlite3 "$WORK_DIR/data/trade_history.db" "SELECT action, symbol, date, price, pnl_pct FROM trades WHERE date = '$DATE' ORDER BY timestamp;" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Engine Status
echo "🟢 Engine Status:" >> "$REPORT_FILE"
if pgrep -f "auto_trading_engine.py" > /dev/null; then
    PID=$(pgrep -f "auto_trading_engine.py")
    echo "✅ Running (PID: $PID)" >> "$REPORT_FILE"
else
    echo "❌ NOT RUNNING!" >> "$REPORT_FILE"
fi
echo "" >> "$REPORT_FILE"

echo "==========================================" >> "$REPORT_FILE"
echo "Report generated: $(date)" >> "$REPORT_FILE"
echo "==========================================" >> "$REPORT_FILE"

# Display report
cat "$REPORT_FILE"

# Keep for 7 days, then delete
find /tmp -name "daily_summary_*.txt" -mtime +7 -delete
