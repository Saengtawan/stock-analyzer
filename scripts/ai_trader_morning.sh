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
   ROOM is the whole game. Prefer a name EARLY in its move with runway LEFT — a fresh reversal
   reclaiming off its low with the gap still to fill, or a laggard not yet caught up — over a
   name already NEAR its peak ('near peak, never red' = most of the move banked = buying high =
   thin room). Avoid both the spent/fading end AND the near-peak end; the edge is in between.
   For EACH candidate estimate the % room from its CURRENT price to a realistic 16:00 target
   and confirm it beats the stop; PUT that estimate in the reason. Pick up to 5 with genuine
   from-here upside, ranked by conviction; don't pad; if the only candidates are near-peak/
   thin-room, ABSTAIN — never force a low-room buy. Never penalized for abstaining.
   ENTRY TIMING — buy on LEADING signals, do NOT wait for price to confirm. By the time a move
   is "confirmed" (Δ10m already big + broken out + already +2-6% from open) the room is GONE —
   you'd be buying high, late, chasing. That confirmation is a LAGGING signal. The edge is to
   enter EARLY (+0 to ~+1.5% from open, or still reclaiming) on signals that PRECEDE the price
   move: (1) VOLUME ACCUMULATION — rv>=1.5 while the price is still flat/small = someone is
   accumulating BEFORE the move (this is the HIGH-VOLUME ACCUMULATION section — the BJRI case:
   flat -0.2% at 09:32 on rv 2.9x, then ran +5%; buying the volume tell at -0.2% got full room);
   (2) a FRESH catalyst not yet fully priced; (3) early RELATIVE STRENGTH — green while its
   whole sector is red = real conviction before the breakout. Price direction alone is ~a coin
   flip — the leading signal (WHO is accumulating and WHY) is the edge, not the price line, so
   do not predict from the price chart. Because early entries have MORE false starts, this only
   works WITH a tight TRAIL: prefer exit_style "trail" ~1-1.5% on these. The math is asymmetric
   and that's the point — buy 5 early leading-signal setups, ~3 fizzle (trail out ~-1% each) and
   ~2 run (+5%+), net positive — which BEATS one late "confirmed" +4% name with thin room left.
   Still ABSTAIN if there is no leading signal at all (no accumulation, no catalyst, no rel-
   strength) — early entry means early on a REASON, not early on nothing.
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
