#!/bin/bash
# Stop all services

echo "Stopping all services..."
echo ""

# Stop Auto Trading Engine
if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    echo "🛑 Stopping Auto Trading Engine..."
    pkill -f "python.*auto_trading_engine.py"
    sleep 2
    echo "   ✅ Stopped"
fi

# Stop Web App
if pgrep -f "python.*(run_app|web/app)\.py" > /dev/null; then
    echo "🛑 Stopping Web App..."
    pkill -f "python.*(run_app|web/app)\.py"
    sleep 2
    echo "   ✅ Stopped"
fi

echo ""
echo "======================================"
echo "  All services stopped"
echo "======================================"
echo ""

# Verify
if pgrep -f "python.*(auto_trading_engine|run_app|web/app)" > /dev/null; then
    echo "⚠️  Some processes still running:"
    ps aux | grep -E "auto_trading_engine|run_app|web/app" | grep -v grep
else
    echo "✅ All processes stopped"
fi
echo ""
