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
YOUR JOB — the whole of it: from now to the 16:00 ET close, find the stock(s) that, bought now
and exited by the close, will gain MORE THAN 2% intraday. Buy those; pass on everything else.
This prompt does NOT tell you HOW to find them, what a "good setup" is, which signals matter,
when in the day to act, or when to sit out — that judgment is entirely YOURS, formed from the
data. There are no rules here to obey and none to override; just the goal and the tools.

OPERATIONAL (cost only, not trading advice): each tool call re-reads ~35k of context, so cost
scales with NUMBER OF TURNS. Keep it tight — aim <=6 tool turns: run the brief once; batch any
web-searches into a single parallel turn; do the Write + execute together. Think freely in text
(that's cheap); just don't burn turns.

1. Run: $PY -m src.ai_trader.run_v2 brief --date $DATE
   It prints RAW FACTS and interprets nothing: the field of movers (per-stock numbers), each
   one's recent news, the macro backdrop, and your own recent realized picks. You do the judging.
2. LEARN FROM WHAT ACTUALLY WON, don't guess. Before you decide, STUDY how past winners really
   behaved at entry time — run 'bash scripts/ai_trader_data.sh winners YYYY-MM-DD [minpct]' for a
   few RECENT past days: it lists the stocks that actually gained >=minpct% intraday and what each
   looked like at 09:35 (gain-from-open, gap, early relative volume). Calibrate from that what a
   09:32 winner ACTUALLY looks like at entry, then match today's field against it. Your own past
   picks are in the brief — if they lost, the winners table shows you what you should have been
   looking at instead. Also available (read-only): schema, sql "SELECT ...", bars SYM DATE, field
   DATE MINUTE (intraday_bars_5m = 86M 5-min bars, signal_outcomes, news_events, macro_snapshots,
   stock_daily_ohlc), and WebSearch for an unclear catalyst. Measure, don't assume; conclusions are yours.
3. Decide. For each name you buy you must be able to state why you expect >2% before the close —
   but the method, the reasoning, and the signals are entirely yours to determine from the data.
   Give each pick an archetype in your OWN words. 0 picks (abstain) is a valid, unpenalized
   outcome if nothing clears the >2% bar.
4. In ONE turn, both: (a) Write plans/decisions/$DATE.json (picks ordered best-first, up to 5)
   with keys: date, regime (one line), picks (each: sym, archetype, reason, exit_style
   ["hold_eod"|"trail"], hard_stop [negative %], trail_pct [number if trail else null]),
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
