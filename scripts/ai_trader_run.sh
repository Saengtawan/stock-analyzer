#!/usr/bin/env bash
# ai_trader daily runner — NEW system, separate from riser/ml_filter.
#
#   pre-open (cron ~09:00 ET):  ai_trader_run.sh brief   -> prints morning brief;
#                               a Claude session reads it and, if a real risk-off
#                               catalyst exists, appends to plans/llm_verdicts.json.
#   pre-open (cron ~09:15 ET):  ai_trader_run.sh plan     -> writes plans/<date>.json
#   at-open  (cron ~09:36 ET):  ai_trader_run.sh names    -> surfaces the gap-down cell;
#                               a Claude session reads each name's catalyst (knowledge +
#                               web) and writes plans/name_verdicts/<date>.json (picks/skip)
#   at-open  (cron ~09:37 ET):  ai_trader_run.sh open     -> decides pick, logs journal
#   post-close (cron ~16:10 ET):ai_trader_run.sh outcome  -> fills realized outcomes
#   any time:                   ai_trader_run.sh report   -> journal so far
#
# All backtest-stage / paper. The AI layer (headline judgment) is validated forward here.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$HOME/.pyenv/versions/issara/bin/python3"
DATE="${2:-$(TZ=America/New_York date +%F)}"
CMD="${1:-report}"

case "$CMD" in
  # --- v2 (AI-first: broad universe -> AI reasons -> execute) ---
  v2brief)   "$PY" -m src.ai_trader.run_v2 brief --date "$DATE" ;;
  v2decide)  "$PY" -m src.ai_trader.decide_ai --date "$DATE" ;;   # headless AI (needs ANTHROPIC_API_KEY)
  v2execute) "$PY" -m src.ai_trader.run_v2 execute --date "$DATE" ;;
  v2outcome) "$PY" -m src.ai_trader.run_v2 outcome --date "$DATE" ;;
  v2bench)   "$PY" - "$DATE" <<'EOF'
import sys, json
d=sys.argv[1]
try: raw=json.load(open(f"plans/decisions/{d}.json"))
except Exception as e: print("no decision:",e); raise SystemExit
print(f"regime: {raw.get('regime')}")
for i,p in enumerate(raw.get('picks',[])):
    tier="PICK" if i<2 else "bench"
    ex=f"trail {p.get('trail_pct')}%" if p.get('exit_style')=='trail' else 'hold-EOD'
    print(f"\n[{tier} #{i+1}] {p['sym']} [{p['archetype']}] exit={ex} stop{p.get('hard_stop')}%")
    print(f"  {p.get('reason')}")
if not raw.get('picks'): print("ABSTAIN:", raw.get('abstain_reason'))
EOF
  ;;
  v2report)  "$PY" - <<'EOF'
from src.ai_trader import journal
rows=journal.report_v2(); tot=[]
print(f"{'date':11} {'sym':6} {'archetype':18} {'status':10} {'out':>7}")
for d,sym,arch,st,out,reason in rows:
    o=f"{out:+.2f}" if out is not None else "-"
    if out is not None: tot.append(out)
    print(f"{d:11} {sym or '-':6} {arch or '-':18} {st:10} {o:>7}")
if tot:
    import statistics as s
    print(f"\nclosed N={len(tot)} avg{s.mean(tot):+.2f}% WR{sum(x>0 for x in tot)/len(tot)*100:.0f}% total{sum(tot):+.1f}%")
EOF
  ;;
  # --- v1 (classify + rule gate) ---
  brief)   "$PY" -m src.ai_trader.premarket_brief --date "$DATE" ;;
  plan)    "$PY" -m src.ai_trader.premarket_ai --date "$DATE" --backend llm ;;
  names)   "$PY" -m src.ai_trader.run_open --date "$DATE" --surface ;;
  open)    "$PY" -m src.ai_trader.run_open --date "$DATE" --backend llm ;;
  outcome) "$PY" -m src.ai_trader.outcome ${2:+--date "$DATE"} ;;
  report)  "$PY" - <<'EOF'
from src.ai_trader import journal
rows = journal.report()
print(f"{'date':11} {'status':10} {'risk':8} {'sym':6} {'gain':>6} {'outcome':>8}  regime")
tot=[]
for d,st,risk,sym,gain,out,reg in rows:
    g=f"{gain:+.2f}" if gain is not None else "-"
    o=f"{out:+.2f}" if out is not None else "-"
    if out is not None: tot.append(out)
    print(f"{d:11} {st:10} {risk:8} {sym or '-':6} {g:>6} {o:>8}  {reg}")
if tot:
    import statistics as s
    print(f"\nclosed picks N={len(tot)}  avg{s.mean(tot):+.2f}%  "
          f"WR{sum(x>0 for x in tot)/len(tot)*100:.0f}%  total{sum(tot):+.1f}%")
EOF
  ;;
  *) echo "usage: ai_trader_run.sh {brief|plan|open|outcome|report} [date]"; exit 1 ;;
esac
