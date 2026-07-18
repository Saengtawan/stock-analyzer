#!/usr/bin/env bash
# ai_trader after-close REVIEW — the learning half of the loop. Fills today's outcomes, then the
# AI compares what it predicted vs what actually happened and appends an honest lesson to its own
# memory (data/ai_trader_memory.md) that it will read next morning. Run by cron ~16:20 ET.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer
DATE=$(TZ=America/New_York date +%F)

# 1) fill realized outcomes for today's picks
bash scripts/ai_trader_run.sh v2outcome "$DATE" >> logs/ai_trader_v2.log 2>&1 || true

read -r -d '' PROMPT <<EOF || true
You are the ai_trader v2 brain, reviewing your OWN trading day after the close. Today (ET) is $DATE. Work in $(pwd).
This is how you get better: compare what you predicted this morning to what actually happened, and teach your future self.

1. Read this morning's decision + reasoning: cat plans/decisions/$DATE.json
2. Read what your picks ACTUALLY did (realized, held to close): bash scripts/ai_trader_run.sh v2report
   (and per name if you want: bash scripts/ai_trader_data.sh winners $DATE  and sql on intraday_bars_5m).
3. Read your current memory: cat data/ai_trader_memory.md
4. Ask honestly: where was my read RIGHT, where WRONG, and WHY? Did I chase the loud story? buy the
   extended leader? misjudge the regime/knife? Was the theme even knowable pre-open?
5. APPEND to data/ai_trader_memory.md: (a) one line under "Forward record" = the date, picks, and how
   each closed; (b) if today taught something real, a concise dated lesson under "Lessons" — and PRUNE
   any lesson the forward record now contradicts. Keep the file tight and honest; it is your only
   continuity. Do not rewrite history or inflate results — the forward record is the one thing you trust.
Print a 2-3 line summary of what you learned today.
EOF

OUT=$(timeout 500 claude -p "$PROMPT" --permission-mode bypassPermissions --allowedTools "Bash Write" 2>&1)
echo "$OUT"
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] ai_trader review done ($DATE)" >> logs/ai_trader_v2.log
