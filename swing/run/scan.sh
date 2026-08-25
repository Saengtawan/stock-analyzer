#!/usr/bin/env bash
# swing/run/scan.sh — ON-DEMAND swing scan (VCP/TTM-squeeze pool -> AI judgment).
# NOT on cron. Run it manually whenever you want a medium-term (1w-1m) shortlist.
# Mirrors resonance/run/premarket.sh but is fully separate: separate pool, separate DB (data/swing.db),
# separate plans dir. Touches NOTHING in resonance/.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE="${1:-$(TZ=America/New_York date +%F)}"
mkdir -p swing/plans logs

# 1) mechanical layer -> raw pool (compressed + strong + trending)
if ! python -m swing.screen.pool "$DATE"; then
  echo "🔴 swing pool build failed for $DATE" ; exit 1
fi

# 2) AI judgment (direction + catalyst + regime). Optional: skip with SWING_NO_AI=1 to just get the pool.
if [ "${SWING_NO_AI:-0}" = "1" ]; then
  echo "[swing] pool only (SWING_NO_AI=1). Judge swing/pool/$DATE.json yourself."
  exit 0
fi
PROMPT="Today (ET) is $DATE. You are the swing brain. The raw pool is at swing/pool/$DATE.json.
Execute the selection exactly as written below.
$(sed "s/<DATE>/$DATE/g" swing/brain/decide.md)"
timeout 1200 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "swing/plans/$DATE.txt"
echo "[swing] done ($DATE) -> swing/plans/$DATE.txt"
