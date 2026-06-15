#!/bin/bash
# z1_multiscan.sh — Z1 1-minute multi-scan capture + Δwin_p top-1 (2026-06-11).
# Scans every minute 09:31–09:39 ET, dumps each scan's per-candidate win_p+price,
# then at 09:40 aggregates the win_p trajectory and shows Z1 top-1 by:
#   (a) win_p at last scan, (b) win_p_last + 2·Δwin_p (the conviction-trajectory tilt).
# Purpose: live-test the user's idea (re-scan carries info) on Z1, which the 5-min
# backtest can't represent. Read-only — does NOT trade.
#
# Run tomorrow morning (or via cron at 09:30 ET). Manual:  bash scripts/z1_multiscan.sh
set -u
cd "$(dirname "$0")/.."
PY="/home/saengtawan/.pyenv/versions/issara/bin/python3"; [[ -x "$PY" ]] || PY=python3
OUT=/tmp/z1_multiscan; mkdir -p "$OUT"; rm -f "$OUT"/*.jsonl

et_secs() { read -r h m s < <(TZ=America/New_York date '+%H %M %S'); echo $((10#$h*3600+10#$m*60+10#$s)); }

for MIN in 31 32 33 34 35 36 37 38 39; do
  TARGET=$((9*3600 + MIN*60 + 35))          # HH:MM:35 ET (bar closed + buffer)
  while [[ "$(et_secs)" -lt "$TARGET" ]]; do sleep 2; done
  rm -f /tmp/h12a_dump.jsonl
  H12A_DUMP=1 "$PY" -m src.scan.engine ml_filter >/dev/null 2>&1
  [[ -f /tmp/h12a_dump.jsonl ]] && cp /tmp/h12a_dump.jsonl "$OUT/min_09${MIN}.jsonl"
  echo "[z1_multiscan] captured 09:$MIN"
done

echo "=== aggregating Δwin_p (09:40) ==="
"$PY" - <<'PYEOF'
import json, glob, os
ROOT='/home/saengtawan/work/project/cc/stock-analyzer'
files=sorted(glob.glob('/tmp/z1_multiscan/min_*.jsonl'))
# Z1 = mfo 0-9. collect win_p per (sym) per minute
traj={}; price={}; sec={}
for f in files:
    mn=os.path.basename(f).replace('min_','').replace('.jsonl','')
    for ln in open(f):
        r=json.loads(ln)
        if not (0<=r.get('mfo',99)<=9): continue   # Z1 only
        s=r['sym']; traj.setdefault(s,{})[mn]=r.get('win_p',0)
        price[s]=r.get('price',0); sec[s]=r.get('sec','')[:10]
rows=[]
for s,t in traj.items():
    ks=sorted(t);
    if len(ks)<2: continue
    wp_first=t[ks[0]]; wp_last=t[ks[-1]]; dwp=wp_last-wp_first
    rows.append((s,wp_first,wp_last,dwp,price[s],sec[s],len(ks)))
if not rows:
    print('  ไม่มี Z1 candidate (ตลาดอาจแดง/ไม่มีตัวถึง threshold)'); raise SystemExit
print(f"{'sym':<6}{'wp_first':>9}{'wp_last':>9}{'Δwp':>8}{'price':>9}{'nscan':>6}  sec")
for s,wf,wl,dw,p,sc,n in sorted(rows,key=lambda x:-x[2])[:12]:
    print(f"  {s:<6}{wf:>8.3f}{wl:>8.3f}{dw:>+8.3f}{p:>9.2f}{n:>6}  {sc}")
print('\n--- top-1 ที่ 09:40 ---')
by_last=max(rows,key=lambda x:x[2]); by_tilt=max(rows,key=lambda x:x[2]+2*x[3])
print(f"  by win_p_last      : {by_last[0]} (wp {by_last[2]:.3f}, Δ{by_last[3]:+.3f}, ${by_last[4]:.2f})")
print(f"  by win_p+2·Δwp     : {by_tilt[0]} (wp {by_tilt[2]:.3f}, Δ{by_tilt[3]:+.3f}, ${by_tilt[4]:.2f})")
print('  (ถ้าต่างกัน = Δwp tilt เลือกตัวที่ model มั่นใจขึ้น)')
PYEOF
