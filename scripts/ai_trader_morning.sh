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
Today (ET) is $DATE. Work in $(pwd). Do exactly this, then stop:

1. Run: $PY -m src.ai_trader.run_v2 brief --date $DATE
   (broad liquid universe of movers + macro narrative + each stock's DB news).
2. For down/gapped movers that look like genuine setups but have no DB news, use
   WebSearch: "why is <SYM> stock down/up today" to learn the real catalyst. NEVER label a
   name "meme" or "junk" and dismiss it WITHOUT web-searching its catalyst first — LCID
   looked like a meme EV squeeze but was actually a false-bankruptcy-rumor washout (-41%)
   reversing on the company's official DENIAL = a real, tradeable rumor-denial reversal.
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
   Pick up to 5 names you judge green-at-close, ranked by conviction; don't pad; if only 2
   (or fewer) clear the bar, return that many; abstain entirely if none does — never penalized.
4. Write plans/decisions/$DATE.json (picks ordered best-first, up to 5) with keys:
   date, regime (one line), picks (each: sym, archetype, reason, exit_style
   ["hold_eod"|"trail"], hard_stop [negative %], trail_pct [number if trail else null]),
   abstain_reason (string if no picks else null).
5. Run: bash scripts/ai_trader_run.sh v2execute $DATE   (shows the top 2, benches the rest)
6. Print: regime (1 line); the TOP 2 picks each with a one-line why; then a one-line
   BENCH list of any rank 3-5 names (sym + archetype only). Or why you abstained.
EOF

claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash WebSearch Write Read"
