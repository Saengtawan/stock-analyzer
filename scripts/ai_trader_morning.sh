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
   WebSearch: "why is <SYM> stock down today" to learn the real catalyst.
3. Judge like a discretionary trader IN CONTEXT. Archetypes are PRIORS/EXAMPLES, not a
   fixed menu — COIN YOUR OWN archetype name when a setup doesn't fit (e.g. you named NOW
   a "sympathy-overreaction laggard"). Examples: gap_down_reversal / oversold_bounce /
   news_catalyst / breakout. Reserved veto label: sympathy_junk (never buy).
   CRITICAL — this is an INTRADAY system (buy ~09:37, flat by 16:00). The buy reason MUST
   be an intraday move that will happen TODAY and HASN'T happened yet — UNRESOLVED edge:
   a mismatch not yet reclaimed, a laggard not yet caught up, a reversal not yet bounced.
   A multi-day / fundamental catalyst by itself (cheap valuation, "re-rates over days") is a
   SWING thesis, not intraday. If the day's reaction is already SPENT — ran far from the open
   and now flattening/fading, e.g. a low-vol mega-cap +2% then rolling over (JNJ) — SKIP it.
   BUT a fresh EARNINGS GAP-AND-GO ("earnings_gap_and_go") IS a valid BUY: gapped up on a
   real SAME-DAY catalyst (earnings/guidance) and STILL ACCELERATING early from the open
   (from-open positive and RISING, not yet extended) — the continuation is happening NOW and
   is unresolved. The line between gap-and-go and spent is momentum + how far it has run:
   still building early in the session = buy; already ran a lot and flattening/fading = skip.
   (ABT today: +0.2% from open at 09:31 then +3.9% by 09:33 = accelerating = gap-and-go BUY;
   JNJ yesterday: +2.1% already and rolling over = spent = skip.)
   Find up to 5 GENUINE setups with intraday juice LEFT, RANKED best-first. Do NOT pad —
   only real reversals/mismatches, not falling knives, sector de-rates, or thin-IEX gap
   artifacts. If only 2 (or fewer) are clean, return that many. Abstain entirely if the
   tape is a real risk-off or nothing has live intraday edge — never penalized.
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
