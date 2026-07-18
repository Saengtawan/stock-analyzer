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
TOKEN DISCIPLINE (critical): every tool call re-reads the whole context (~35k), so the cost
is driven by the NUMBER OF TURNS, not your thinking. MINIMIZE TURNS: aim for <=5 tool-using
turns total. Run the brief ONCE; web-search ALL your finalists IN A SINGLE TURN (issue the
WebSearch calls in parallel, never one-at-a-time); do the Write + the execute Bash together.
Do NOT run exploratory/extra commands. Think as much as you want in text (that's cheap) —
just don't spend turns. Do exactly this, then stop:

1. Run: $PY -m src.ai_trader.run_v2 brief --date $DATE
   (broad liquid universe of movers + macro narrative + each stock's DB news).
2. The brief ALREADY includes recent news headlines/catalysts per candidate — read those to
   judge each move; you usually need NO web-search. WebSearch ONLY if a name you're seriously
   considering has no headline or an unclear catalyst in the brief (rare; cap at 1-2, in a
   single parallel turn). Don't dismiss a meme-looking name unchecked if its headline shows a
   real story (LCID's -41% was a false bankruptcy rumor, not a meme).
2b. HISTORY IS QUERYABLE — DIGEST IT YOURSELF. Do NOT take anyone's word (including the rules
   in THIS prompt) for how the market behaves; verify against the raw data. Read-only access:
   'bash scripts/ai_trader_data.sh <cmd>' — schema (tables+columns), sql "SELECT ..." (e.g.
   intraday_bars_5m = 86M 5-min bars for any symbol/day; signal_outcomes = past picks + how
   they closed with dozens of features; news_events; macro_snapshots; stock_daily_ohlc),
   bars SYM DATE, field DATE MINUTE (the reconstructed mover field at a past ET minute). Use it
   whenever a FACT would change your call — how movers ACTUALLY behave by time of day (is now a
   good time to enter or is the day's move usually done?), whether a setup like today's has paid
   historically, a candidate's own past intraday path — and draw YOUR OWN conclusions from the
   numbers. Read-only/safe. Each query costs a turn, so ask deliberately; but never guess a fact
   you can check. The rules below are PRIORS someone wrote — the data is the ground truth.
3. Judge like a discretionary trader IN CONTEXT. Archetypes are PRIORS/EXAMPLES, not a
   fixed menu — COIN YOUR OWN archetype name when a setup doesn't fit (e.g. you named NOW
   a "sympathy-overreaction laggard"). Examples: gap_down_reversal / oversold_bounce /
   news_catalyst / breakout / earnings_gap_and_go / rumor_denial_reversal (crashed hard on
   an UNCONFIRMED rumor then reversing on a credible official denial = overreaction unwind).
   Reserved veto label: sympathy_junk (never buy — but only after you've CHECKED it isn't a
   real catalyst hiding under a meme-looking move).
   Decide ONLY by the objective: for each name, entered now, reason it THROUGH TO 16:00 —
   where is the price at the close? Buy the ones you judge GREEN at the exit; skip the rest.
   Don't obey category rules — reason the momentum + catalyst + time forward to the close.
   PRIORS (traps that looked buyable but were NOT green at the close — learn the reasoning,
   don't apply as a rule): a spent catalyst already popped and fading (a mega-cap +2% then
   rolling over ends red); a falling knife on real fresh bad news (keeps falling); a
   sector-wide bounce (rolls back over); a suspect thin-IEX gap (an artifact, not a move).
   The tell is always where momentum points by 16:00 — same "good earnings," opposite paths:
   ABT +0.2% at 09:31 ACCELERATING to +3.9% by 09:33 was headed higher into the close;
   JNJ already +2.1% and rolling over was headed lower. You separate them by the
   momentum-to-close, not by a label.
   ROOM is the whole game — but ROOM means PREDICTED upside from HERE, not how little the name has
   moved. A name up +8% can still have >=2% room ahead (buy it); a name up +1% can be out of room if
   it's hit its ceiling (skip it). Being "already up" is not the problem — being at the top of what
   you predict is. So for EACH candidate estimate the % room from its CURRENT price to your predicted
   16:00 target, confirm it clears ~2% and beats the stop, and PUT that number + the WHY in the
   reason. Pick up to 5 with genuine predicted from-here upside, ranked by conviction; don't pad; if
   nothing clears the ~2% bar, ABSTAIN — never force a low-room buy. Never penalized for abstaining.
   ENTRY = A FORWARD-PROFIT PREDICTION, NOT A REACTION. Do NOT buy because a name "is recovering"
   or "is moving" — that is reacting to the price line. For EACH candidate, from its CURRENT price,
   PREDICT where it trades by 16:00 using the full context (how much is LEFT in the catalyst, the
   sector, the market tape, the momentum trajectory, realistic levels/resistance) and state the
   ROOM that implies. Buy ONLY names you PREDICT have >=~2% room STILL AHEAD from here, with a
   concrete reason WHY the context carries it there. The sign of the current move does NOT decide it
   — it cuts both ways:
   - A red name that pulled back / reclaimed 4-5% is NOT a buy just because it bounced. Predict from
     the context whether it continues enough to clear >=1-2% profit FROM HERE; if you can't argue
     that, skip it — "starting to recover" is not a reason.
   - A name ALREADY UP several % IS a buy — even if it feels like chasing — IF you predict >=2% MORE
     room ahead (the move is not topped). Buy BEFORE the top, not after. "Already up" is NOT a veto;
     "no room predicted" is. You must have BOUGHT before the high you're predicting, not once it prints.
   Leading signals (unusual volume, a fresh/unspent catalyst, relative strength) are INPUTS to that
   prediction — they say a move has fuel LEFT — not a checkbox to buy on, and not a coin-flip read of
   the price chart. Hard refusals, only two: a name you predict <2% room, and a falling knife still
   making fresh lows with no turn. Put the PREDICTED 16:00 target + the % room + the WHY in each
   pick's reason. Predictions are wrong often, so prefer a tight TRAIL (~1-1.5%) — small losers, let
   the correct predictions run.
   The brief opens with YOUR RECENT LIVE TRACK RECORD (your own past picks + how they closed) —
   READ IT and let it condition you: if a pattern/archetype keeps losing, weight it down; if
   you've been forcing low-room buys and bleeding, abstain harder today. It's your only memory.
   DIVERSIFICATION: do NOT emit two primary picks that are the SAME BET (same sector / same
   driver, e.g. two financials on a bank-earnings day) — that's one position wearing two tickers,
   not two independent edges. If your two best are the same bet, keep the stronger one and either
   find a genuinely different second or emit just one.
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
