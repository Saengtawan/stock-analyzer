#!/bin/bash
# Run EVERYTHING - Web + Auto Trading + Gap Scanner
# ไม่มี systemd ไม่มี boot auto-start แค่รันแล้ว auto หมด

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo ""
echo "======================================"
echo "  🚀 STOCK ANALYZER - FULL SYSTEM"
echo "======================================"
echo ""

# Check if already running
if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    echo "⚠️  Auto Trading Engine already running!"
    ps aux | grep "auto_trading_engine.py" | grep -v grep
    echo ""
fi

if pgrep -f "python.*run_app.py" > /dev/null; then
    echo "⚠️  Web App already running!"
    ps aux | grep "run_app.py" | grep -v grep
    echo ""
fi

# Check .env
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Create it with:"
    echo "  ALPACA_API_KEY=your_key"
    echo "  ALPACA_SECRET_KEY=your_secret"
    echo "  ALPACA_PAPER=true"
    exit 1
fi

# Create logs dir
mkdir -p logs data/logs

echo "Starting services..."
echo ""

# 1. Start Auto Trading Engine (Gap Scanner + Trading)
if ! pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    echo "1️⃣ Starting Auto Trading Engine..."
    nohup python src/auto_trading_engine.py > logs/auto_trading_engine.log 2>&1 &
    sleep 2
    if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
        echo "   ✅ Auto Trading Engine started"
        echo "      - Pre-market Gap Scanner (6:00-9:30 AM)"
        echo "      - Rapid Rotation Scanner"
        echo "      - Order execution"
    else
        echo "   ❌ Failed to start"
        exit 1
    fi
fi

echo ""

# 2. Start Web App (UI + Portfolio Monitor)
if ! pgrep -f "python.*run_app.py" > /dev/null; then
    echo "2️⃣ Starting Web App..."
    nohup python src/run_app.py > logs/web_app.log 2>&1 &
    sleep 3
    if pgrep -f "python.*run_app.py" > /dev/null; then
        echo "   ✅ Web App started"
        echo "      - Web UI (http://localhost:5000)"
        echo "      - Portfolio Monitor (every 5 min)"
        echo "      - Price Streamer (real-time)"
        echo "      - Universe Cleanup (daily 2 AM)"
    else
        echo "   ❌ Failed to start"
        exit 1
    fi
fi

echo ""
echo "======================================"
echo "  ✅ ALL SYSTEMS RUNNING"
echo "======================================"
echo ""
echo "📊 Web UI:  http://localhost:5000"
echo ""
echo "🔍 Services Running:"
echo "   • Auto Trading Engine (Gap Scanner)"
echo "   • Rapid Rotation Scanner"
echo "   • Portfolio Monitor"
echo "   • Price Streamer"
echo "   • Health Checker"
echo "   • Universe Maintenance"
echo ""
echo "📋 Daily Schedule:"
echo "   02:00 AM - Universe cleanup"
echo "   06:00 AM - Gap scanner starts"
echo "   09:30 AM - Market open, trading begins"
echo "   16:00 PM - Market close"
echo ""
echo "📝 Logs:"
echo "   tail -f logs/auto_trading_engine.log"
echo "   tail -f logs/web_app.log"
echo ""
echo "🛑 Stop All:"
echo "   ./scripts/stop_all.sh"
echo ""
echo "======================================"
echo ""
