#!/usr/bin/env bash
# ai_trader v2 — daily AI-brain run via headless Claude Code (NON-expiring, no API key,
# no Alpaca orders). Invoked by SYSTEM cron each weekday ET morning. Claude reads the
# broad universe + news, web-searches catalysts, writes the decision, and executes
# (emit + log only — you place the buy yourself).
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
PY="$HOME/.pyenv/versions/issara/bin/python3"

read -r -d '' PROMPT <<EOF
You are the AI brain of the ai_trader v2 system (intraday, paper, forward-tracking).
Today (ET) is $DATE. Work in $(pwd).
YOUR JOB — the whole of it: find the stock(s) that, bought now and HELD to the 16:00 ET close
(no stop, no trail — you ride the entire day), will FINISH the day UP MORE THAN 2% at the close.
The exit is fixed: hold to 16:00. So you are NOT hunting an intraday spike — a name that pops
+8% at 11:00 then closes red is a LOSS. You want names that are GREEN AT THE CLOSE by >2%. Buy
those; pass on everything else. This prompt does NOT tell you HOW to find them, what a "good
setup" is, which signals matter, or when to sit out — that judgment is entirely YOURS, formed
from the data. No rules to obey, none to override; just the goal (green >2% at the CLOSE) and the tools.

OPERATIONAL (cost only, not trading advice): each tool call re-reads ~35k of context, so cost
scales with NUMBER OF TURNS. Keep it tight — aim <=6 tool turns: run the brief once; batch any
web-searches into a single parallel turn; do the Write + execute together. Think freely in text
(that's cheap); just don't burn turns.

1. Run: $PY -m src.ai_trader.run_v2 brief --date $DATE
   It prints RAW FACTS and interprets nothing: THE WHOLE UNIVERSE of movers (every one, per-stock
   numbers, no slice or ranking done for you), the macro backdrop, and your own recent realized
   picks. YOU filter the universe. You do all the judging.
2. Tools are available — use them however YOU see fit, or not at all. Nothing about how to use them
   is prescribed. WebSearch a name's catalyst; and read-only data:
   'bash scripts/ai_trader_data.sh <schema | sql "SELECT ..." | bars SYM DATE | field DATE MINUTE |
   winners DATE [minpct]>' (intraday_bars_5m, signal_outcomes, news_events, macro_snapshots,
   stock_daily_ohlc, and past days' actual EOD winners with their entry-time look). Conclusions are yours.
3. Decide: from the universe, pick the name(s) YOU judge will CLOSE >2% up (bought at 09:32, held
   to 16:00, no stop). The method, the signals, the reasoning are entirely yours to determine. Give
   each pick an archetype in your OWN words. 0 picks (abstain) is a valid, unpenalized outcome.
4. In ONE turn, both: (a) Write plans/decisions/$DATE.json (picks ordered best-first, up to 5)
   with keys: date, regime (one line), picks (each: sym, archetype, reason, exit_style
   [always "hold_eod" — you hold to the close], hard_stop [null], trail_pct [null]),
   abstain_reason (string if no picks else null); AND (b) run
   'bash scripts/ai_trader_run.sh v2execute $DATE'.
5. Print: regime (1 line); the TOP 2 picks each with a one-line why; then a one-line BENCH
   list of any rank 3-5 names (sym + archetype only). Or why you abstained.
EOF

# A5 — the whole day rides on this single shot: bound it, capture it, and ALERT loudly on
# failure (timeout / non-zero exit / session-limit / no decision written) so a silent miss
# can't pass for a genuine abstain.
ALERT="logs/ai_trader_ALERT.log"
OUT=$(timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash WebSearch Write" 2>&1)
RC=$?
echo "$OUT"

fail=""
[ $RC -eq 124 ] && fail="TIMEOUT (>600s) — headless claude hung"
[ $RC -ne 0 ] && [ $RC -ne 124 ] && fail="claude exited $RC"
echo "$OUT" | grep -qi "hit your session limit\|usage limit\|rate limit" && fail="SESSION/RATE LIMIT — run blocked before it could decide"
[ ! -f "plans/decisions/$DATE.json" ] && fail="${fail:+$fail; }NO decision file written for $DATE"

if [ -n "$fail" ]; then
  MSG="[$(TZ=America/New_York date '+%F %H:%M ET')] ai_trader morning FAILED: $fail"
  echo "🔴🔴🔴 $MSG" | tee -a "$ALERT"
  command -v notify-send >/dev/null 2>&1 && notify-send -u critical "ai_trader FAILED" "$fail" || true
  exit 1
fi
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] ai_trader morning OK ($DATE)" >> logs/ai_trader_v2_ai.log
