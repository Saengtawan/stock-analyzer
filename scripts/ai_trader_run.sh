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
import statistics as s
rows, base = journal.report_v2(live_only=True)   # LIVE only — dev re-runs (mode='replay') excluded
print(f"{'date':11} {'sym':6} {'archetype':18} {'status':10} {'out':>7}")
for d,sym,arch,st,out,reason,mode in rows:
    o=f"{out:+.2f}" if out is not None else "-"
    print(f"{d:11} {sym or '-':6} {arch or '-':18} {st:10} {o:>7}")
tot=[out for d,sym,arch,st,out,reason,mode in rows if st=='closed' and out is not None and sym]
if tot:
    print(f"\nAI closed N={len(tot)} avg{s.mean(tot):+.2f}% WR{sum(x>0 for x in tot)/len(tot)*100:.0f}% total{sum(tot):+.1f}%")
if base:
    for kind in ('spy','field_reclaim'):
        b=[o for d,k,sym,o in base if k==kind and o is not None]
        if b: print(f"baseline[{kind:13}] N={len(b)} avg{s.mean(b):+.2f}% WR{sum(x>0 for x in b)/len(b)*100:.0f}%")
    print("  (AI has an edge only if its avg/WR beats BOTH baselines over N)")
EOF
  ;;
  v2fill)    "$PY" - "$DATE" "${3:-}" "${4:-}" <<'EOF'
import sys
from src.ai_trader import journal
d, sym, px = sys.argv[1], sys.argv[2], sys.argv[3]
if not sym or not px:
    print("usage: ai_trader_run.sh v2fill <date> <SYM> <actual_entry_price>"); raise SystemExit(1)
n=journal.record_fill(d, sym, float(px))
print(f"recorded actual fill: {d} {sym.upper()} @ {px}  ({n} row updated)" if n
      else f"no journal row for {d} {sym.upper()} (did you execute that date?)")
EOF
  ;;
  status)  "$PY" - <<'EOF'
import os, glob, json, subprocess, datetime, zoneinfo
ET=zoneinfo.ZoneInfo("America/New_York"); now=datetime.datetime.now(ET)
print("="*64); print(f"  ai_trader — SYSTEM STATUS   |  ET {now:%F %H:%M %a}"); print("="*64)
# latest decision
ds=sorted(glob.glob("plans/decisions/*.json"))
if ds:
    d=json.load(open(ds[-1])); dt=os.path.basename(ds[-1])[:-5]; pk=d.get("picks") or []
    print(f"\n▸ LATEST DECISION  ({dt})")
    print(f"   regime: {(d.get('regime') or '')[:100]}")
    if pk:
        for p in pk[:5]: print(f"   PICK {p['sym']:6} [{p.get('archetype','')[:34]}] stop{p.get('hard_stop')}")
    else: print(f"   ABSTAIN — {(d.get('abstain_reason') or '')[:100]}")
# forward record + lessons (the AI's brain)
try:
    m=open("data/ai_trader_memory.md").read()
    fr=[l for l in m.splitlines() if l.strip() and l[:4].isdigit()]
    print(f"\n▸ FORWARD RECORD (last 5 of {len(fr)}):")
    for l in fr[-5:]: print("   "+l[:110])
    les=m.split("## Lessons",1)
    if len(les)>1: print(f"   lessons on file: {les[1].count(chr(10)+'- ')}")
except Exception as e: print("  (no memory yet)")
# gate state today
try:
    g=subprocess.run(["bash","scripts/ai_trader_data.sh","gates",now.strftime('%F')],capture_output=True,text=True,timeout=30).stdout
    st=[l for l in g.splitlines() if "gate" in l.lower() or "STATE" in l or "tilt" in l.lower()]
    print("\n▸ GATE STATE today:"); [print("   "+l.strip()[:100]) for l in st[:3]]
except Exception: pass
# alert
if os.path.exists("logs/ai_trader_ALERT.log") and os.path.getsize("logs/ai_trader_ALERT.log")>0:
    print("\n▸ ⚠️ ALERTS (last line):"); print("   "+open("logs/ai_trader_ALERT.log").read().strip().splitlines()[-1][:100])
else: print("\n▸ alerts: none")
# schedule
print("\n▸ SCHEDULE (ET): 09:32 morning decide  |  16:30 review->memory   (Mon-Fri)")
print("="*64)
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
