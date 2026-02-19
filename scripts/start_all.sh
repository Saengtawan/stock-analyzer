#!/bin/bash
# Start both Web App + Auto Trading Engine

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🚀 Starting Stock Analyzer System..."
echo ""

# 1. Start Auto Trading Engine
echo "1️⃣ Starting Auto Trading Engine..."
./scripts/start_auto_trading.sh
echo ""

# 2. Start Web App
echo "2️⃣ Starting Web App..."
if pgrep -f "python.*run_app.py" > /dev/null; then
    echo "⚠️  Web app already running"
else
    nohup python src/run_app.py > logs/web_app.log 2>&1 &
    sleep 2
    echo "✅ Web app started at http://localhost:5000"
fi

echo ""
echo "=================================="
echo "  ALL SYSTEMS RUNNING"
echo "=================================="
echo ""
echo "Web UI:  http://localhost:5000"
echo "Logs:    tail -f logs/*.log"
echo "Stop:    pkill -f 'auto_trading_engine|run_app'"
echo ""
