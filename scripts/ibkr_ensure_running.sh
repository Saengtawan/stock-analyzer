#!/bin/bash
# Ensure IB Gateway is running. If port 4002 not listening, run auto-login.
# Idempotent — safe to run from cron every minute or so.

LOGFILE=/home/saengtawan/ibc/logs/ensure.log
mkdir -p "$(dirname $LOGFILE)"
exec >> "$LOGFILE" 2>&1
echo "=== $(date) ==="

# Already running?
if ss -tln 2>/dev/null | grep -q ':4002 '; then
    echo "Port 4002 already listening — OK"
    exit 0
fi

echo "Port 4002 closed → run auto-login"
/home/saengtawan/.pyenv/versions/cc/bin/python /home/saengtawan/work/project/cc/stock-analyzer/scripts/ibkr_auto_login_v3.py

# After login, dismiss accept dialog + disable read-only (in case settings reset)
sleep 5
/home/saengtawan/.pyenv/versions/cc/bin/python <<'PY'
import os, time
os.environ['DISPLAY']=':99'
import pyautogui
pyautogui.FAILSAFE = False
# Click "I understand and accept" button (paper warning)
pyautogui.click(640, 510)
time.sleep(2)
PY

# Verify
sleep 3
if ss -tln 2>/dev/null | grep -q ':4002 '; then
    echo "✅ Port 4002 OPEN"
else
    echo "❌ Port 4002 still closed after login attempt"
    exit 1
fi
