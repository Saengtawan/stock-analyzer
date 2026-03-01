#!/bin/bash
# start.sh — Restart engine and web app (both via systemd)
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

# --- 3. Restart Web App (systemd-managed) ---
echo ""
echo "[3/3] Web App..."

if [ "$ENGINE_ONLY" = false ]; then
    if systemctl --user is-active stock-webapp.service > /dev/null 2>&1; then
        echo "  Restarting stock-webapp.service..."
        systemctl --user restart stock-webapp.service
    else
        echo "  Starting stock-webapp.service..."
        systemctl --user start stock-webapp.service
    fi
    sleep 3
    if systemctl --user is-active stock-webapp.service > /dev/null 2>&1; then
        APP_PID=$(pgrep -f "python.*web/app" | head -1)
        echo "  Web app running (PID: ${APP_PID:-unknown})"
    else
        echo "ERROR: Web app failed to start — check:"
        echo "  journalctl --user -u stock-webapp.service -n 20"
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
echo "App:     tail -f logs/web_app.log"
echo "Stop:    ./scripts/stop_all.sh"
echo ""
