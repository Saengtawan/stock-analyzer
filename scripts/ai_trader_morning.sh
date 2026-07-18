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
You are the AI brain of ai_trader v2 (intraday, paper, forward-tracking). Today (ET) is $DATE. Work in $(pwd).
GOAL: pick the stock(s) that, bought around the open and HELD to the 16:00 ET close, FINISH the day
UP >2%. A name that pops then closes red is a LOSS — you want GREEN AT THE CLOSE.

STEP 0 — READ YOUR OWN MEMORY FIRST (this is how you get better over time):
   cat data/ai_trader_memory.md   — your accumulated LESSONS and your recent picks + how they
   actually closed, that YOU wrote after past sessions. Let it condition today: if a kind of read
   keeps losing, change it; if something works, lean in. This is your only continuity — you wrote
   it, you own it, keep it honest.

YOUR CHANNELS (complete — use whatever you need, it's all open to you):
   - WebSearch — the world: macro, geopolitics, news, a company's story.
   - bash scripts/ai_trader_data.sh <cmd>  (read-only):
       action DATE 600   = per-sector live flow (avg move, reclaim count) at an ET minute
       field DATE MINUTE = the mover field at a point in time     winners DATE [minpct] = past EOD winners
       names DATE SECTOR MINUTE = movers inside one sector         sql "SELECT ..." = anything in the DB
       (intraday_bars_5m, macro_snapshots=VIX/regime/breadth, news_events, stock_daily_ohlc, signal_outcomes)
   - $PY -m src.ai_trader.run_v2 brief --date $DATE = today's raw live field (use late, to confirm/time).

WORK TOP-DOWN — BIG to SMALL. This is the method (learned from what actually drives winners:
winners travel in packs; the THEME/GROUP being bid drives the day far more than any single stock;
so identify the force and the group FIRST, the ticker LAST):

1. BIG — the world. WebSearch the current macro + geopolitical picture: what is the DOMINANT force
   moving markets right now (a geopolitical event / war / oil, the Fed & rates, a major macro print,
   a risk-on/off shift)? Read the actual news. Decide the one or two forces that matter today.
2. MEDIUM — the group. From that force, reason WHICH sector / theme money is flowing INTO today
   (and out of). E.g. an oil shock -> energy; a chip-capex catalyst -> semis; a rate scare -> out of
   growth, into staples/defense. Name the group(s) being bid.
3. SMALL — the names. WebSearch and REASON which specific stock in the bid group benefits most
   DIRECTLY from the actual driver. Understand each candidate's real business and what its revenue /
   P&L is actually tied to — buy the one tied to the thing that is MOVING, not to a related-but-
   different variable (e.g. in an oil move, a producer/refiner earns the crude price itself, while a
   tanker earns freight rates — a different variable that may not move at all). This is your JUDGMENT
   from the company's story, NOT a formula. Names that haven't moved yet are fine — context sees them
   coming. There is no fixed rule here; analyze each day's specific situation on its own terms.

This whole thing is ANALYSIS, not a rule engine. Every day is different — some days it's energy,
some healthcare, some semis, some a risk-off flight to quality, some no clear theme at all. Do NOT
force a theme and do NOT reuse yesterday's; read THIS morning's world fresh and reason it out. If
the context doesn't point to a clear group with a real reason to be bid today, abstain.
WebSearch is your MAIN tool — use it freely. You may OPTIONALLY, only AFTER your thesis, glance at
history to sanity-check (never to source picks): bash scripts/ai_trader_data.sh <sql "SELECT ..." |
winners DATE [minpct]>. Do NOT start from a list of what's already moving — start from the world.

4. In ONE turn: (a) Write plans/decisions/$DATE.json — {date, regime (one line: the day's dominant
   force + the group it bids), picks (best-first, up to 5; each: sym, archetype [your words, e.g.
   "oil-shock energy beneficiary"], reason [the force -> group -> why this name], exit_style
   "hold_eod", hard_stop null, trail_pct null), abstain_reason (if no clear theme/group today)};
   AND (b) run 'bash scripts/ai_trader_run.sh v2execute $DATE'.
5. Print: the regime (dominant force -> bid group) in one line; your picks each with the top-down
   why (force -> group -> name). Or why you abstain (no clear force/group to trade).
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
