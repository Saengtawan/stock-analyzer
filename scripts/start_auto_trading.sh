#!/bin/bash
#
# Start Auto Trading Engine
# Usage: ./scripts/start_auto_trading.sh
#

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=================================="
echo "  AUTO TRADING ENGINE STARTUP"
echo "=================================="
echo ""
echo "Project: $PROJECT_DIR"
echo "Time: $(date)"
echo ""

# Check if already running
if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    echo "⚠️  Auto Trading Engine already running!"
    echo ""
    echo "Current process:"
    ps aux | grep "auto_trading_engine.py" | grep -v grep
    echo ""
    echo "To restart:"
    echo "  1. Kill: pkill -f auto_trading_engine.py"
    echo "  2. Start: ./scripts/start_auto_trading.sh"
    exit 1
fi

# Check Python environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  No virtual environment active"
    echo "Activating pyenv environment..."

    if command -v pyenv &> /dev/null; then
        eval "$(pyenv init -)"
        pyenv activate cc 2>/dev/null || true
    fi
fi

# Check .env file
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Please create .env with:"
    echo "  ALPACA_API_KEY=your_key"
    echo "  ALPACA_SECRET_KEY=your_secret"
    echo "  ALPACA_PAPER=true"
    exit 1
fi

# Check logs directory
mkdir -p logs data/logs

# Start engine
echo "🚀 Starting Auto Trading Engine..."
echo ""

nohup python src/auto_trading_engine.py > logs/auto_trading_engine.log 2>&1 &
ENGINE_PID=$!

sleep 3

# Check if started successfully
if ps -p $ENGINE_PID > /dev/null; then
    echo "✅ Auto Trading Engine started (PID: $ENGINE_PID)"
    echo ""
    echo "📊 Monitoring:"
    echo "  Logs:   tail -f logs/auto_trading_engine.log"
    echo "  Status: ps aux | grep auto_trading_engine"
    echo "  Stop:   pkill -f auto_trading_engine.py"
    echo ""
    echo "Gap Scanner:"
    echo "  Active:  6:00 AM - 9:30 AM ET"
    echo "  Buy:     9:30 AM (market open)"
    echo "  Sell:    4:00 PM (market close)"
    echo ""
    echo "=================================="
    echo "  ENGINE RUNNING"
    echo "=================================="
else
    echo "❌ Failed to start Auto Trading Engine"
    echo ""
    echo "Check logs:"
    echo "  tail logs/auto_trading_engine.log"
    exit 1
fi
