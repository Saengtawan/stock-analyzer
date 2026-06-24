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

# Capture window: 09:31:30 .. last scan (default 09:36:30 = display 1 bar earlier, 2026-06-23).
# Display uses the LAST scan record; ending at :36:30 (vs old :37:30) shows the pick ~1 min
# earlier (uses the 09:35 bar / ~09:36 price instead of ~09:37). Revert: RISER_LAST_MIN=37.
for MIN in $(seq 31 "${RISER_LAST_MIN:-36}"); do
  TARGET=$((9*3600 + MIN*60 + 30))               # HH:MM:30 ET
  while [[ "$(et_secs)" -lt "$TARGET" ]]; do sleep 2; done
  rm -f /tmp/h12a_dump.jsonl
  H12A_DUMP=1 "$PY" -m src.scan.engine ml_filter >/dev/null 2>&1
  [[ -f /tmp/h12a_dump.jsonl ]] && cp /tmp/h12a_dump.jsonl "$OUT/min_09${MIN}.jsonl"
done

# PERSIST the per-minute candidate dumps (2026-06-24). /tmp/riser_capture is wiped each run;
# this keeps the REAL cell-ok Z1 candidate set per day so forward entry-selection experiments
# (win_p / tiebreak / min-gain filter) can be tested on the SAME population as live — which
# historical reconstruction could NOT match. Disable: RISER_PERSIST_DUMP=0.
if [[ "${RISER_PERSIST_DUMP:-1}" == "1" ]]; then
  _PDATE=$(TZ=America/New_York date '+%Y-%m-%d'); _PDIR="data/riser_dumps/$_PDATE"
  mkdir -p "$_PDIR" && cp "$OUT"/*.jsonl "$_PDIR"/ 2>/dev/null \
    && echo "[riser] persisted $(ls "$_PDIR"/*.jsonl 2>/dev/null | wc -l) candidate dumps -> $_PDIR"
fi

# Display IMMEDIATELY after the last (09:37:30) scan — same info as waiting to 09:38:00
# (scan takes ~10s -> display ~09:37:45; closer to scan price = less drift). 2026-06-12.

"$PY" - <<'PYEOF'
import json, glob, os
from datetime import datetime
from zoneinfo import ZoneInfo
ET=ZoneInfo('America/New_York'); now=datetime.now(ET)
# accumulate per-symbol latest record across the 7 scans (Z1 only = mfo 0-9)
acc={}; _mingain={}
for f in sorted(glob.glob('/tmp/riser_capture/min_*.jsonl')):
    for ln in open(f):
        r=json.loads(ln)
        if not (0<=r.get('mfo',99)<=9): continue
        acc[r['sym']]=r  # latest wins (files sorted by minute)
        _g=r.get('gain')
        if _g is not None: _mingain[r['sym']]=min(_mingain.get(r['sym'],_g),_g)  # min gain across the 6 scans
for _s in acc: acc[_s]['min_gain']=_mingain.get(_s)
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
# --- v2 REGIME-ADAPTIVE GATES (2026-06-21, drilled vs user + 2 independent AIs, full 2021+ N).
#     SEASON DETERMINANT = VIX-20d (20-day avg of prior-day VIX, slow regime). Validated net-of-cost
#     ACROSS TWO INDEPENDENT ERAS (2021-22 bear + 2025-26):
#       VIX-20d < 22 -> identity gate WORKS (net +0.11..+0.62 both eras).
#       VIX-20d >= 22 (storm) -> NO rule tradeable (gain/identity/anti/beta all lose >=1 era) -> abstain.
#     Drilled-away artifacts: instantaneous-vix (noise), VIX-20d 24-26 "junk-mania" (1 melt-up day,
#     2025-04-09 tariff-pause), sub-buckets (thin-N single-big-beta-day). Reversible: flags below. ---
_ID_GATE=os.environ.get('RISER_IDENTITY_GATE','0')=='1'
_VIX20_MAX=float(os.environ.get('RISER_VIX20_MAX','99'))   # abstain whole day if VIX-20d >= this (storm)
if _ID_GATE or _VIX20_MAX<99:
    _tg=now.strftime('%Y-%m-%d'); _vix20=None
    try:
        import sqlite3 as _s3
        _th=_s3.connect('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
        _rows=_th.execute("SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 20").fetchall(); _th.close()
        if len(_rows)>=20: _vix20=sum(x[0] for x in _rows)/20.0
    except Exception: _vix20=None
    # STORM regime: VIX-20d >= max -> no tradeable edge -> abstain entire day
    if _vix20 is not None and _vix20>=_VIX20_MAX:
        print(f"[v2-gates] VIX-20d={_vix20:.1f} >= {_VIX20_MAX} (storm, no-edge regime) -> ABSTAIN")
        risers=[]
    else:
        _STRg=None
        if _ID_GATE:
            try:
                import sys as _s2; _s2.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
                from src.scan import stock_track_record as _STRg
            except Exception: _STRg=None
        def _gate_ok(r):
            if _ID_GATE and _STRg is not None and not _STRg.passes_gate(r['sym'],_tg,min_n=8): return False
            return True
        _pre=len(risers); risers=[r for r in risers if _gate_ok(r)]
        print(f"[v2-gates] VIX-20d={('%.1f'%_vix20) if _vix20 is not None else 'na'}<{_VIX20_MAX} | id_gate={'ON(n>=8)' if _ID_GATE else 'off'} -> {len(risers)}/{_pre} pass")
print(f"=== riser_momentum @ {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
if not risers:
    print(f"Status: no_picks — no Z1 riser in band (gain {_MIN_GAIN}-{_MAX_GAIN}, gap<={_GAP_CAP}) across 09:31-36 scans"); raise SystemExit
# ENTRY-QUALITY (2026-06-24, user deploy — reversible flags). min-gain = lowest gain-from-open
# across the 6 scans (path cleanliness). BACKTEST (on reconstructed pool, NOT exactly live —
# verify on persisted real dumps forward): RISER_MINGAIN_FILTER drops dippers (min<0); RISER_TIEBREAK_WIN
# picks highest min-gain among near-ties. Cut worst -27->-17, net-neutral, catches HOOD-type. Disable: =0.
if os.environ.get('RISER_MINGAIN_FILTER','0')=='1':
    _clean=[r for r in risers if (r.get('min_gain') is None or r['min_gain']>=0)]
    if _clean: risers=_clean   # drop negative-dip candidates; if ALL dip, keep all (don't abstain)
risers.sort(key=lambda r: -r['gain'])
top=risers[0]
_tw=float(os.environ.get('RISER_TIEBREAK_WIN','0') or 0)
if _tw>0 and len(risers)>1:
    _tie=[r for r in risers if r['gain']>=risers[0]['gain']-_tw]
    top=max(_tie, key=lambda r:(r.get('min_gain') if r.get('min_gain') is not None else -99))
print(f"Status: active — top RISER by gain in band({_MIN_GAIN}-{_MAX_GAIN},gap<={_GAP_CAP}) among {len(risers)} Z1 candidates (09:31:30-09:36:30)")
print()
print(f"  BUY  {top['sym']}  @ ${top.get('price',0):.2f}")
print(f"       gain +{top['gain']:.1f}%  min-gain {(('%+.1f%%'%top['min_gain']) if top.get('min_gain') is not None else 'na')}  win_p {top.get('win_p',0):.3f}  sec {str(top.get('sec',''))[:12]}  spy_intra {top.get('spy_intra',0):+.2f}")
print(f"       rank-by-gain top-1 | win=peak>=1%")
# ENTRY: chase MARKET immediately (2026-06-24 refit). The limit-dip idea LOSES once measured
# realistically: the pick is only visible ~09:37, so the 09:37-38 pullback that justified a
# limit is ALREADY PAST -> chase@09:37 (-1.18) beats static-limit (-1.36)/walking-limit (-1.25);
# entry-timing 09:33-40 = pure noise. All entry mechanics cluster +-0.2 = pool cost not a lever.
# Revive limit only if you can act before ~09:36. (set RISER_LIMIT_DISCOUNT to re-show the limit.)
_px=top.get('price',0); _disc=float(os.environ.get('RISER_LIMIT_DISCOUNT','0') or 0)
if _disc>0:
    print(f"       ENTRY: LIMIT @ ${_px*(1-_disc/100):.2f} (display −{_disc:.1f}%) — runner ไม่ fill → market @ ${_px:.2f}")
else:
    print(f"       ENTRY: chase MARKET ทันที @ ~${_px:.2f} (อย่ารอ limit — ย่อผ่านไปแล้วตอนเห็น pick)")
# exit-plan from AT-SCAN SPY intraday (2026-06-24 refit): market green->hold-EOD / red->exit~10:05.
# Uses top's spy_intra (already shown in the BUY line) = the same signal inference_riser keys on.
# Informational at entry; actual exit logic in inference_riser (RISER_REGIME_EXIT/SPYINTRA_EXIT).
_exit_plan='hold-EOD (default)'
if os.environ.get('RISER_REGIME_EXIT','0')=='1':
    _si=top.get('spy_intra')
    if _si is None: _exit_plan='hold-EOD (spy_intra n/a)'
    elif _si>0:     _exit_plan=f'hold-EOD (SPY {_si:+.2f}% green, sustain)'
    else:           _exit_plan=f'exit~10:05 (SPY {_si:+.2f}% red, pump-fade)'
    print(f"       EXIT-PLAN: {_exit_plan}  [+ peak-fade reactive]")
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

# Identity-gate SHADOW removed 2026-06-24 (cleanup): identity is now a LIVE GATE
# (RISER_IDENTITY_GATE=1) so the shadow A/B is moot; identity-pick recompute-able from the
# persisted candidate dumps (data/riser_dumps/) if revisited.

# win_p-v3 SHADOW removed 2026-06-24 (cleanup): win_p entry-gate is NOT the deployed path
# (modest + abstain trade-off — disaster-money is at EXIT). Recompute-able any time from the
# persisted candidate dumps (data/riser_dumps/) via src.scan.riser_winp if revisited on real data.
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
      nohup bash scripts/exit_loop.sh "$RSYM" "$RPRICE" 09:37 "$ET_DATE" > "$LOG" 2>&1 < /dev/null &
      disown 2>/dev/null || true
      echo "[riser] launched exit-tracker: $RSYM @ \$$RPRICE (riser dynamic exit) -> $LOG"
    fi
    # --- Entry-fill monitor (2026-06-24): only relevant when a LIMIT is suggested. We now chase
    # market by default (RISER_LIMIT_DISCOUNT=0) -> nothing to watch, monitor is skipped. It re-arms
    # automatically if you set RISER_LIMIT_DISCOUNT>0. Logs to *_entry.log. Force-off: RISER_FILL_WATCH=0.
    _DISC="${RISER_LIMIT_DISCOUNT:-0}"
    if [[ "${RISER_FILL_WATCH:-1}" == "1" && -n "$_DISC" && "$_DISC" != "0" ]]; then
      _LIM=$(awk -v p="$RPRICE" -v d="$_DISC" 'BEGIN{printf "%.2f", p*(1-d/100)}')
      ELOG="$LOG_DIR/${RSYM}_${ET_DATE}_entry.log"
      if ! pgrep -f "entry_fill_watch.py $RSYM " >/dev/null 2>&1; then
        nohup "$PY" scripts/entry_fill_watch.py "$RSYM" "$_LIM" "$RPRICE" "$ET_DATE" > "$ELOG" 2>&1 < /dev/null &
        disown 2>/dev/null || true
        echo "[riser] launched entry-fill monitor: $RSYM LIMIT \$$_LIM -> $ELOG"
      fi
    fi
  fi
fi
