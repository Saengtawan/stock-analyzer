#!/bin/bash
# riser_capture.sh — Z1 riser lane, multi-scan accumulate + display (2026-06-12).
# Captures H12-A Z1 candidates every minute 09:31:30 → 09:37:30 ET (7 scans),
# accumulates per-symbol (latest gain/win_p/price), then right after the last scan
# (~09:37:45) ranks by gain_from_open and prints the top-1 RISER (pool: cell-ok +
# win_p>=0.68 + gain>0 = the validated peak_bt pool). Buy at display — matches backtest entry.
# Read-only (suggest pick; does NOT trade). Disable: RISER_ENABLED=0 or remove cron.
set -u
cd "$(dirname "$0")/.."
# cron has no .env (systemd services load it via EnvironmentFile; cron doesn't).
# Load ONLY riser/h12a feature-flags from .env so RISER_MIN_GAIN etc. take effect under cron.
if [[ -f .env ]]; then
  while IFS= read -r _l; do
    case "$_l" in RISER_*=*|H12A_*=*) export "$_l" ;; esac
  done < .env
fi
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
# gain>=RISER_MIN_GAIN (default 0 = legacy gain>0). Set RISER_MIN_GAIN=2 to drop low-gain
# "duds" — validated 2026-06-16 (gauntlet PASS: fold-split foldA+0.94/foldB+1.55, remove-top5,
# per-quarter 4/4; WR 54->57, avg +0.43->+0.66, trades 71% of days). Reversible: unset/=0.
# BAND + GAP deploy 2026-06-16 (gauntlet-locked: fold-split/remove-top/plateau/per-Q).
#   RISER_MAX_GAIN=3.5  upper cap -> drop froth (extended movers fade). plateau 3.0-3.75.
#   RISER_GAP_CAP=0.5   drop big overnight gaps (gap-fade). plateau 0.2-0.8.
#   Two orthogonal root causes (extension vs gap-fade); both needed (gap-alone fails foldA).
#   Locked: avg/pick +0.01->+0.46, worst -16.5->-11.6, every sub-period >=+0.42, ret/DD 3.5.
#   Pairs with RISER_EXIT_DYNAMIC=0 (hold-EOD): band picks are calm, trail clips U-recovery.
#   Reversible: unset RISER_MAX_GAIN/RISER_GAP_CAP -> legacy. BACKTEST-validated; track fwd.
_MIN_GAIN=float(os.environ.get('RISER_MIN_GAIN','0'))
_MAX_GAIN=float(os.environ.get('RISER_MAX_GAIN','999'))
_gc=os.environ.get('RISER_GAP_CAP','')
_GAP_CAP=float(_gc) if _gc not in ('','off') else None
def _riser_ok(r):
    g=(r.get('gain') or -99)
    if not (_MIN_GAIN < g <= _MAX_GAIN): return False
    if _GAP_CAP is not None and r.get('gap') is not None and r['gap'] > _GAP_CAP: return False
    return True
risers=[r for r in acc.values() if _riser_ok(r)]
# --- v2 GATES (2026-06-21): vix<20 (regime, rediscover H12-A) + identity (ticker track record).
#     Validated OOS correct-label: vix<20+identity(n>=8) net -0.04->+0.64, maxDD 93->47, CI[+0.09,+1.18]
#     SIG+, fold both +, rmT3 +0.43. Reversible: RISER_VIX_GATE=0 / RISER_IDENTITY_GATE=0. ---
_VIX_GATE=os.environ.get('RISER_VIX_GATE','0')=='1'
_ID_GATE=os.environ.get('RISER_IDENTITY_GATE','0')=='1'
if _VIX_GATE or _ID_GATE:
    _tg=now.strftime('%Y-%m-%d'); _vix=None
    if _VIX_GATE:
        try:
            import sqlite3 as _s3
            _th=_s3.connect('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
            _row=_th.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone(); _th.close()
            _vix=_row[0] if _row else None
        except Exception: _vix=None
    _STRg=None
    if _ID_GATE:
        try:
            import sys as _s2; _s2.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
            from src.scan import stock_track_record as _STRg
        except Exception: _STRg=None
    def _gate_ok(r):
        if _VIX_GATE and _vix is not None and _vix>=20: return False
        if _ID_GATE and _STRg is not None and not _STRg.passes_gate(r['sym'],_tg,min_n=8): return False
        return True
    _pre=len(risers); risers=[r for r in risers if _gate_ok(r)]
    print(f"[v2-gates] vix_gate={('ON vix=%.1f'%_vix) if (_VIX_GATE and _vix is not None) else 'off'} | id_gate={'ON(n>=8)' if _ID_GATE else 'off'} -> {len(risers)}/{_pre} candidates pass")
print(f"=== riser_momentum @ {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
if not risers:
    print(f"Status: no_picks — no Z1 riser in band (gain {_MIN_GAIN}-{_MAX_GAIN}, gap<={_GAP_CAP}) across 09:31-37 scans"); raise SystemExit
risers.sort(key=lambda r: -r['gain'])
top=risers[0]
print(f"Status: active — top RISER by gain in band({_MIN_GAIN}-{_MAX_GAIN},gap<={_GAP_CAP}) among {len(risers)} Z1 candidates (09:31:30-09:37:30)")
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
    # 2026-06-16: add gap+range_exp for forward verification of the band+gap filter (idempotent).
    for _c in ('gap REAL','range_exp REAL'):
        try: db.execute(f"ALTER TABLE riser_picks ADD COLUMN {_c}")
        except Exception: pass
    db.execute("INSERT INTO riser_picks(scan_date,scan_ts,symbol,price,gain,win_p,sector,n_cand,gap,range_exp) VALUES(?,?,?,?,?,?,?,?,?,?)",(now.strftime('%Y-%m-%d'),now.strftime('%Y-%m-%d %H:%M:%S'),top['sym'],top.get('price',0),top['gain'],top.get('win_p',0),top.get('sec',''),len(risers),top.get('gap'),top.get('range_exp')))
    db.commit(); db.close()
    print(f"\n  [journaled -> riser_picks]")
except Exception as e:
    print(f"\n  [journal skip: {e}]")

# --- Identity-gate SHADOW (2026-06-20, LOG-ONLY, zero trade impact). Disable: RISER_IDENTITY_SHADOW=0 ---
# Identity edge sig at population (p=0.010 on live-faithful label) but pick-level CI still crosses 0
# -> shadow to accumulate forward N before switching. Does NOT change the live pick/trade.
if os.environ.get('RISER_IDENTITY_SHADOW','1')=='1':
    try:
        import sys as _sys; _sys.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
        from src.scan import stock_track_record as _STR
        _today=now.strftime('%Y-%m-%d')
        _tg=_STR.passes_gate(top['sym'],_today); _n,_avg=_STR.prior_stats(top['sym'],_today)
        _ident=next((r for r in risers if _STR.passes_gate(r['sym'],_today)),None)
        print(f"\n  [identity-shadow] live-pick {top['sym']} gate={'PASS' if _tg else 'BLOCK'} (prior_n={_n} avg={(_avg if _avg is not None else float('nan')):+.2f})")
        print(f"  [identity-shadow] identity-pick: {(_ident['sym']+' +%.1f%%'%_ident['gain']) if _ident else 'ABSTAIN (no gate-pass today)'}")
        import sqlite3 as _sq
        _db=_sq.connect('/home/saengtawan/work/project/cc/stock-analyzer/data/scan_journal.db')
        _db.execute("CREATE TABLE IF NOT EXISTS riser_identity_shadow(scan_date TEXT,scan_ts TEXT,live_sym TEXT,live_gate INT,live_prior_n INT,live_prior_avg REAL,identity_sym TEXT,identity_gain REAL)")
        _db.execute("INSERT INTO riser_identity_shadow VALUES(?,?,?,?,?,?,?,?)",(_today,now.strftime('%Y-%m-%d %H:%M:%S'),top['sym'],int(_tg),_n,_avg,(_ident['sym'] if _ident else None),(_ident['gain'] if _ident else None)))
        _db.commit(); _db.close()
    except Exception as _e:
        print(f"  [identity-shadow skip: {_e}]")
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
