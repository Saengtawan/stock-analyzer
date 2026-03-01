#!/bin/bash
# start.sh — Restart engine (via systemd) and/or web app (via nohup)
# Usage:
#   ./start.sh              — restart both engine and app
#   ./start.sh --engine-only
#   ./start.sh --app-only

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

ENGINE_ONLY=false
APP_ONLY=false
for arg in "$@"; do
    case $arg in
        --engine-only) ENGINE_ONLY=true ;;
        --app-only)    APP_ONLY=true ;;
    esac
done

echo "======================================"
echo "  STOCK ANALYZER — START"
echo "  $(date)"
echo "======================================"

# --- 1. Verify prerequisites ---
echo ""
echo "[1/3] Checking prerequisites..."
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    exit 1
fi
mkdir -p logs data/logs
echo "  OK"

# --- 2. Restart Engine (systemd-managed) ---
echo ""
echo "[2/3] Engine..."

if [ "$APP_ONLY" = false ]; then
    if systemctl --user is-active auto-trading.service > /dev/null 2>&1; then
        echo "  Restarting auto-trading.service..."
        systemctl --user restart auto-trading.service
    else
        echo "  Starting auto-trading.service..."
        systemctl --user start auto-trading.service
    fi
    sleep 3
    if systemctl --user is-active auto-trading.service > /dev/null 2>&1; then
        ENGINE_PID=$(pgrep -f "python.*auto_trading_engine" | head -1)
        echo "  Engine running (PID: ${ENGINE_PID:-unknown})"
    else
        echo "ERROR: Engine failed to start — check:"
        echo "  journalctl --user -u auto-trading.service -n 20"
        exit 1
    fi
else
    echo "  Skipped (--app-only)"
fi

# --- 3. Restart Web App (nohup) ---
echo ""
echo "[3/3] Web App..."

if [ "$ENGINE_ONLY" = false ]; then
    # Kill existing webapp (pkill is safe here — no systemd restart for app)
    if pgrep -f "python.*(web/app)\.py" > /dev/null; then
        echo "  Stopping existing web app..."
        pkill -TERM -f "python.*(web/app)\.py" || true
        sleep 2
        pkill -KILL -f "python.*(web/app)\.py" > /dev/null 2>&1 || true
    fi

    # Activate pyenv if available
    if command -v pyenv > /dev/null 2>&1; then
        eval "$(pyenv init -)"
        eval "$(pyenv virtualenv-init -)" 2>/dev/null || true
        pyenv activate cc 2>/dev/null || true
    fi

    echo "  Starting Web App..."
    nohup python src/web/app.py >> nohup_webapp.out 2>&1 &
    APP_PID=$!
    sleep 3
    if ps -p $APP_PID > /dev/null 2>&1; then
        echo "  Web app running (PID: $APP_PID)"
    else
        echo "ERROR: Web app failed to start — check nohup_webapp.out"
        exit 1
    fi
else
    echo "  Skipped (--engine-only)"
fi

echo ""
echo "======================================"
echo "  ALL SYSTEMS RUNNING"
echo "======================================"
echo "Web UI:  http://localhost:5000"
echo "Engine:  tail -f logs/auto_trading_engine_error.log"
echo "App:     tail -f nohup_webapp.out"
echo "Stop:    ./scripts/stop_all.sh"
echo ""
