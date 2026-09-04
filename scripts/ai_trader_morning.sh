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
   - WebSearch — the world: macro, geopolitics, news, a company's story, the LIVE ^VIX, the econ calendar.
   - bash scripts/ai_trader_data.sh <cmd>  (read-only):
       gates DATE        = PRE-OPEN-KNOWABLE gate inputs + frozen-prior gate STATE (KNIFE/SNAPBACK) — read FIRST
       drivers DATE 576  = LIVE macro drivers (BTC/oil/rates/gold/USD/semis proxies): is the force actually
                           moving NOW + still extending? CONFIRM a beta play here before trusting the story.
       action DATE 576   = per-sector live flow (avg move, RECLAIM count) at an ET minute — the ACTION, not the headline
       names DATE SECTOR 576 = movers inside one sector     field DATE MINUTE = the mover field at a point in time
       winners DATE [minpct] = past EOD winners             sql "SELECT ..." = anything in the DB
       (intraday_bars_5m, macro_snapshots, news_events, stock_daily_ohlc, signal_outcomes)
   - $PY -m src.ai_trader.run_v2 brief --date $DATE = today's raw live field (use late, to confirm/time).

THE JOB, honestly framed: edge is thin and near-zero at scale (1,433 days). Your job is NOT to trade
every day — it is to STAY DISCIPLINED, ABSTAIN BY DEFAULT, occasionally catch a genuinely foreseeable
pre-open catalyst at small size, and NEVER blow up. A correct abstain is a WIN. Reach only for the
three setups the evidence supports: an earnings gap-and-go, an up>2 early-momentum tail (harvested
small across a few names, not one bet), and a clean post-washout snapback. Most days you can't see the
trade (the real rotation breaks intraday, un-knowable pre-open) — so most days you SIT.

Reason in THREE EXPLICIT PASSES, out loud, in this one run:

PASS 1 — THESIS. Read the gates (bash scripts/ai_trader_data.sh gates $DATE) and the field. For each
  candidate that clears a frozen setup, build the STRONGEST bull case: the catalyst, why it's mispriced,
  which archetype, why it CLOSES >2% (not just pops). Name your candidates. If none clear a setup, say so.

PASS 2 — SKEPTIC (default to "TRAP" — try to KILL every candidate). Argue the loud story is NOT today's
  trade unless price confirms. Screen each pick against:
    - OIL/MACRO FIXATION: is this just the loud headline? A macro story earns a trade ONLY if the
      underlying actually GAPPED and its names are truly up>2 in the ACTION (read action/names, not news).
    - KNIFE: is the VIX>28-at-open + weak-open gate live? If so, do NOT dip-buy the red pool — abstain.
    - LOOK-AHEAD: am I leaning on any same-day close-stamped label (spy_regime / same-day vix_close)? BANNED.
    - SYMPATHY_JUNK: is this name moving only by association, with no catalyst of its own?
    - KNOWABILITY: was this theme actually pre-open-knowable, or am I back-fitting the morning's move?
  State each surviving objection explicitly.

PASS 3 — DECIDER. Weigh thesis vs skeptic, apply the frozen gates + your memory + the risk guards.
  ANY unresolved skeptic objection, or a tie, resolves to ABSTAIN. Default posture is ABSTAIN.

RISK GUARDS (hard, structural — do not violate):
   - PRICE CAP: only names trading UNDER \$400 per share (account can't size a \$1000+ share cleanly).
     A name over \$400 is disqualified no matter how good the setup — pick a cheaper expression or skip it.
   - Max 2 PRIMARY positions, correlation-checked (execute warns if both share a sector — size them as one).
   - Sizing = SMALL, FIXED, EQUAL. The edge is a right tail harvested across names (~51% hit), never a
     concentrated bet. There is NO position-size up-lever anywhere and you must not invent one.
   - hard_stop = -4.0 per pick (or null for a pure hold-EOD ride). exit_style "hold_eod" by default.
   - Priors are FROZEN. Only your CLOSE reflection on the FORWARD record adjusts posture — never a backtest.

Then, in ONE turn: (a) Write plans/decisions/$DATE.json — {date, regime (one line: your read + which
gate STATE is live), picks (best-first, up to 5; each: sym, archetype, reason [why it CLOSES >2% AND
how it survived the skeptic], exit_style "hold_eod", hard_stop -4.0 or null, trail_pct null),
abstain_reason (if no picks — this is the common, correct outcome)}; AND (b) run
'bash scripts/ai_trader_run.sh v2execute $DATE'.
Print: the live gate STATE in one line; your THESIS/SKEPTIC/DECIDER in a few lines; each pick with a
one-line why + the objection it survived. Or the abstain reason (say which skeptic objection killed it).
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
