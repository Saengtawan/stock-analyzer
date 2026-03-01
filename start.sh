#!/bin/bash
# start.sh — Kill existing engine/app then start fresh (no duplicate processes)
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

# --- 1. Kill existing processes ---
echo ""
echo "[1/4] Stopping existing processes..."

if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
    echo "  Killing auto_trading_engine..."
    pkill -TERM -f "python.*auto_trading_engine.py" || true
    sleep 3
    if pgrep -f "python.*auto_trading_engine.py" > /dev/null; then
        pkill -KILL -f "python.*auto_trading_engine.py" || true
        sleep 1
    fi
    echo "  Engine stopped."
else
    echo "  Engine: not running."
fi

if pgrep -f "python.*(run_app|web/app)\.py" > /dev/null; then
    echo "  Killing web app..."
    pkill -TERM -f "python.*(run_app|web/app)\.py" || true
    sleep 2
    if pgrep -f "python.*(run_app|web/app)\.py" > /dev/null; then
        pkill -KILL -f "python.*(run_app|web/app)\.py" || true
        sleep 1
    fi
    echo "  Web app stopped."
else
    echo "  Web app: not running."
fi

# --- 2. Activate Python environment ---
echo ""
echo "[2/4] Activating Python environment..."
if command -v pyenv > /dev/null 2>&1; then
    eval "$(pyenv init -)"
    eval "$(pyenv virtualenv-init -)" 2>/dev/null || true
    pyenv activate cc 2>/dev/null || true
fi
echo "  Python: $(python --version 2>&1)"

# --- 3. Verify prerequisites ---
echo ""
echo "[3/4] Checking prerequisites..."
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    exit 1
fi
mkdir -p logs data/logs
echo "  OK"

# --- 4. Start processes ---
echo ""
echo "[4/4] Starting processes..."

if [ "$APP_ONLY" = false ]; then
    echo "  Starting Auto Trading Engine..."
    nohup python src/auto_trading_engine.py >> src/nohup_app.out 2>&1 &
    ENGINE_PID=$!
    sleep 3
    if ps -p $ENGINE_PID > /dev/null 2>&1; then
        echo "  Engine started (PID: $ENGINE_PID)"
    else
        echo "ERROR: Engine failed to start — check src/nohup_app.out"
        exit 1
    fi
fi

if [ "$ENGINE_ONLY" = false ]; then
    echo "  Starting Web App..."
    nohup python src/web/app.py >> nohup_webapp.out 2>&1 &
    APP_PID=$!
    sleep 3
    if ps -p $APP_PID > /dev/null 2>&1; then
        echo "  Web app started (PID: $APP_PID)"
    else
        echo "ERROR: Web app failed to start — check nohup_webapp.out"
        exit 1
    fi
fi

echo ""
echo "======================================"
echo "  ALL SYSTEMS RUNNING"
echo "======================================"
echo "Web UI:  http://localhost:5000"
echo "Engine:  tail -f src/nohup_app.out"
echo "App:     tail -f nohup_webapp.out"
echo "Stop:    ./scripts/stop_all.sh"
echo ""
