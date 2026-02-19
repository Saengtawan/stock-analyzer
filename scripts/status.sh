#!/bin/bash
# Check status of all services

echo ""
echo "======================================"
echo "  SYSTEM STATUS"
echo "======================================"
echo ""

# Auto Trading Engine
echo "🤖 Auto Trading Engine:"
if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    PID=$(pgrep -f "python.*auto_trading_engine.py")
    echo "   ✅ Running (PID: $PID)"
    ps aux | grep "auto_trading_engine.py" | grep -v grep | awk '{print "      CPU: "$3"% | MEM: "$4"% | Started: "$9}'
else
    echo "   ❌ Not running"
fi

echo ""

# Web App
echo "🌐 Web App:"
if pgrep -f "python.*run_app.py" > /dev/null; then
    PID=$(pgrep -f "python.*run_app.py")
    echo "   ✅ Running (PID: $PID)"
    ps aux | grep "run_app.py" | grep -v grep | awk '{print "      CPU: "$3"% | MEM: "$4"% | Started: "$9}'
    echo "   🔗 http://localhost:5000"
else
    echo "   ❌ Not running"
fi

echo ""
echo "======================================"
echo "  AUTOMATED JOBS"
echo "======================================"
echo ""

# Check if engine log exists and show last gap scan
if [ -f "logs/auto_trading_engine.log" ]; then
    LAST_GAP=$(grep -i "premarket\|gap" logs/auto_trading_engine.log 2>/dev/null | tail -1)
    if [ ! -z "$LAST_GAP" ]; then
        echo "📊 Last Gap Scan:"
        echo "   $LAST_GAP"
    fi
fi

echo ""

# List all auto jobs from run_app.py
echo "🔄 Auto Jobs (from run_app.py):"
echo "   • Portfolio Monitor - every 5 minutes"
echo "   • Price Streamer - real-time WebSocket"
echo "   • Health Checker - every 5 minutes"
echo "   • Universe Cleanup - daily at 2:00 AM"

echo ""

echo "🔄 Auto Jobs (from auto_trading_engine.py):"
echo "   • Pre-market Gap Scanner - 6:00-9:30 AM ET"
echo "   • Rapid Rotation Scanner - continuous during market"
echo "   • Order Execution - automatic"
echo "   • Position Monitoring - continuous"

echo ""
echo "======================================"
echo ""
