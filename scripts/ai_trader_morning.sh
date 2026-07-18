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
   It prints RAW FACTS and interprets nothing: the field of movers (per-stock numbers), each
   one's recent news, the macro backdrop, and your own recent realized picks. You do the judging.
2. LEARN FROM WHAT ACTUALLY CLOSED GREEN, don't guess. Before you decide, STUDY the past EOD
   winners at entry time — run 'bash scripts/ai_trader_data.sh winners YYYY-MM-DD [minpct]' for a
   few RECENT past days: it lists the stocks that, held from 09:35 to the close, FINISHED >=minpct%
   up (fwd_close), and what each looked like at 09:35 (gain-from-open, gap, early relative volume;
   fwd_max_gain is the intraday high for contrast — a big fwd_max with a small fwd_close is a
   pump-and-fade you do NOT want). Calibrate from that what a name that CLOSES green actually looks
   like at 09:32, then match today's field against it. Your own past picks are in the brief — if
   they lost, the winners table shows what you should have been looking at. Also read-only: schema,
   sql "SELECT ...", bars SYM DATE, field DATE MINUTE (intraday_bars_5m 86M rows, signal_outcomes,
   news_events, macro_snapshots, stock_daily_ohlc), + WebSearch. Measure, don't assume; conclusions are yours.
3. Decide — and RUN A ROOM CHECK on every pick. The target is >2% above YOUR 09:32 ENTRY at the
   close, so what matters is the room LEFT from the 09:32 price, not how strong the name looks. A
   name that has already run several % from the open by 09:32 has usually SPENT its room — it is
   near where it's going and tends to close flat-or-DOWN from your entry (you'd be buying its high;
   that is exactly what sank the extended picks that closed red). For EACH candidate, state the room
   from the 09:32 price to a realistic close and WHY it is not already near its ceiling. If it has
   already run and you can't argue >2% MORE from here, DON'T buy it — the room usually lives in the
   names that have NOT moved yet at 09:32 (flat, or still red and reclaiming, the whole move ahead).
   Verify against the winners table: what was past EOD closers' actual gain_at_0935 — extended, or
   flat/red? Match that, don't fight it. Method and signals are yours; give each pick an archetype
   in your OWN words + its room estimate. 0 picks (abstain) is valid if nothing has >2% room left.
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
