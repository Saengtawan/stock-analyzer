#!/bin/bash
# Stop all services

echo "Stopping all services..."
echo ""

# Stop Auto Trading Engine (systemd-managed)
if systemctl --user is-active auto-trading.service > /dev/null 2>&1; then
    echo "Stopping auto-trading.service..."
    systemctl --user stop auto-trading.service
    sleep 2
    echo "   Stopped"
elif pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    echo "Stopping orphan auto_trading_engine..."
    pkill -f "python.*auto_trading_engine.py"
    sleep 2
    echo "   Stopped"
else
    echo "Engine: not running."
fi

# Stop Web App (systemd-managed)
if systemctl --user is-active stock-webapp.service > /dev/null 2>&1; then
    echo "Stopping stock-webapp.service..."
    systemctl --user stop stock-webapp.service
    sleep 2
    echo "   Stopped"
elif pgrep -f "python.*(run_app|web/app)\.py" > /dev/null; then
    echo "Stopping orphan web app..."
    pkill -f "python.*(run_app|web/app)\.py"
    sleep 2
    echo "   Stopped"
else
    echo "Web App: not running."
fi

echo ""
echo "======================================"
echo "  All services stopped"
echo "======================================"
echo ""

# Verify
ENGINE_RUNNING=false
APP_RUNNING=false

if systemctl --user is-active auto-trading.service > /dev/null 2>&1 || \
   pgrep -f "python.*auto_trading_engine" > /dev/null; then
    ENGINE_RUNNING=true
fi
if systemctl --user is-active stock-webapp.service > /dev/null 2>&1 || \
   pgrep -f "python.*(run_app|web/app)" > /dev/null; then
    APP_RUNNING=true
fi

if $ENGINE_RUNNING || $APP_RUNNING; then
    echo "WARNING: Some processes still running:"
    systemctl --user status auto-trading.service --no-pager -n 0 2>/dev/null | grep "Active:"
    ps aux | grep -E "auto_trading_engine|run_app|web/app" | grep -v grep
else
    echo "All processes stopped"
fi
echo ""
