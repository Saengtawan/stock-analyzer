#!/bin/bash
# riser_capture.sh — Z1 riser lane, multi-scan accumulate + display (2026-06-12).
# Captures H12-A Z1 candidates every minute 09:31:30 → 09:37:30 ET (7 scans),
# accumulates per-symbol (latest gain/win_p/price), then right after the last scan
# (~09:37:45) ranks by gain_from_open and prints the top-1 RISER (pool: cell-ok +
# win_p>=0.68 + gain>0 = the validated peak_bt pool). Buy at display — matches backtest entry.
# Read-only (suggest pick; does NOT trade). Disable: RISER_ENABLED=0 or remove cron.
set -u
cd "$(dirname "$0")/.."
PY="/home/saengtawan/.pyenv/versions/issara/bin/python3"; [[ -x "$PY" ]] || PY=python3
OUT=/tmp/riser_capture; mkdir -p "$OUT"; rm -f "$OUT"/*.jsonl

if [[ "${RISER_ENABLED:-1}" != "1" ]]; then echo "[riser] RISER_ENABLED=0 — skip"; exit 0; fi

et_secs() { read -r h m s < <(TZ=America/New_York date '+%H %M %S'); echo $((10#$h*3600+10#$m*60+10#$s)); }

# Capture window: 09:31:30, 09:32:30, ... 09:37:30 (mfo 1..7, all Z1)
for MIN in 31 32 33 34 35 36 37; do
  TARGET=$((9*3600 + MIN*60 + 30))               # HH:MM:30 ET
  while [[ "$(et_secs)" -lt "$TARGET" ]]; do sleep 2; done
  rm -f /tmp/h12a_dump.jsonl
  H12A_DUMP=1 "$PY" -m src.scan.engine ml_filter >/dev/null 2>&1
  [[ -f /tmp/h12a_dump.jsonl ]] && cp /tmp/h12a_dump.jsonl "$OUT/min_09${MIN}.jsonl"
done

# Display IMMEDIATELY after the last (09:37:30) scan — same info as waiting to 09:38:00
# (scan takes ~10s -> display ~09:37:45; closer to scan price = less drift). 2026-06-12.

"$PY" - <<'PYEOF'
import json, glob, os
from datetime import datetime
from zoneinfo import ZoneInfo
ET=ZoneInfo('America/New_York'); now=datetime.now(ET)
# accumulate per-symbol latest record across the 7 scans (Z1 only = mfo 0-9)
acc={}
for f in sorted(glob.glob('/tmp/riser_capture/min_*.jsonl')):
    for ln in open(f):
        r=json.loads(ln)
        if not (0<=r.get('mfo',99)<=9): continue
        acc[r['sym']]=r  # latest wins (files sorted by minute)
# POOL: gain>0 only — NO win_p filter (user decision 2026-06-12: revert the wp>=0.68
# filter; peak-metric favors unfiltered in recent fold WR69 vs 64, avgPeak +3.08 vs
# +2.65. Trade-off accepted: avgEOD 26H1 -0.28 if held to EOD).
risers=[r for r in acc.values() if (r.get('gain') or -99) > 0]
print(f"=== riser_momentum @ {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
if not risers:
    print("Status: no_picks — no Z1 riser (none cell-ok + wp>=0.68 + up across 09:31-37 scans)"); raise SystemExit
risers.sort(key=lambda r: -r['gain'])
top=risers[0]
print(f"Status: active — top RISER by gain among {len(risers)} Z1 candidates (accumulated 09:31:30-09:37:30)")
print()
print(f"  BUY  {top['sym']}  @ ${top.get('price',0):.2f}")
print(f"       gain +{top['gain']:.1f}%  win_p {top.get('win_p',0):.3f}  sec {str(top.get('sec',''))[:12]}  spy_intra {top.get('spy_intra',0):+.2f}")
print(f"       rank-by-gain top-1 | BUY NOW (at display, no wait) | win=peak>=1% | hold-EOD")
print()
print(f"  รองลงมา: " + " ".join(f"{r['sym']}+{r['gain']:.1f}%(wp{r.get('win_p',0):.2f})" for r in risers[1:6]))
# journal the suggested pick for forward tracking
try:
    import sqlite3
    db=sqlite3.connect(os.path.join(os.path.dirname(__file__) if '__file__' in dir() else '.','/home/saengtawan/work/project/cc/stock-analyzer/data/scan_journal.db'))
    db.execute("""CREATE TABLE IF NOT EXISTS riser_picks(scan_date TEXT, scan_ts TEXT, symbol TEXT, price REAL, gain REAL, win_p REAL, sector TEXT, n_cand INT)""")
    db.execute("INSERT INTO riser_picks VALUES(?,?,?,?,?,?,?,?)",(now.strftime('%Y-%m-%d'),now.strftime('%Y-%m-%d %H:%M:%S'),top['sym'],top.get('price',0),top['gain'],top.get('win_p',0),top.get('sec',''),len(risers)))
    db.commit(); db.close()
    print(f"\n  [journaled -> riser_picks]")
except Exception as e:
    print(f"\n  [journal skip: {e}]")
PYEOF

# --- Auto-launch exit tracker for the riser pick (2026-06-14) ---
# exit_loop -> exit_check -> cli auto-routes risers to the dynamic VIX/own_range exit.
# Background (nohup), survives shell close. Disable: RISER_TRACK=0.
if [[ "${RISER_TRACK:-1}" == "1" ]]; then
  LOG_DIR="data/exit_loops"; mkdir -p "$LOG_DIR"
  ET_DATE="$(TZ=America/New_York date '+%Y-%m-%d')"
  IFS='|' read -r RSYM RPRICE < <(sqlite3 data/scan_journal.db \
    "SELECT symbol, price FROM riser_picks WHERE scan_date='$ET_DATE' ORDER BY scan_ts DESC LIMIT 1" 2>/dev/null)
  if [[ -n "${RSYM:-}" ]]; then
    if pgrep -f "exit_loop.sh $RSYM " >/dev/null 2>&1; then
      echo "[riser] $RSYM exit-tracker already running — skip"
    else
      LOG="$LOG_DIR/${RSYM}_${ET_DATE}_riser.log"
      nohup bash scripts/exit_loop.sh "$RSYM" "$RPRICE" 09:38 "$ET_DATE" > "$LOG" 2>&1 < /dev/null &
      disown 2>/dev/null || true
      echo "[riser] launched exit-tracker: $RSYM @ \$$RPRICE (riser dynamic exit) -> $LOG"
    fi
  fi
fi
