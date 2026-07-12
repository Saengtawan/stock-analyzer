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
    case "$_l" in
      RISER_*=*|H12A_*=*)
        _vn="${_l%%=*}"
        # command-line/inherited env wins over .env (lets a per-run override + replay work)
        [[ -z "${!_vn+x}" ]] && export "$_l"
        ;;
    esac
  done < .env
fi
PY="/home/saengtawan/.pyenv/versions/issara/bin/python3"; [[ -x "$PY" ]] || PY=python3
OUT=/tmp/riser_capture; mkdir -p "$OUT"; rm -f "$OUT"/*.jsonl

if [[ "${RISER_ENABLED:-1}" != "1" ]]; then echo "[riser] RISER_ENABLED=0 — skip"; exit 0; fi

et_secs() { read -r h m s < <(TZ=America/New_York date '+%H %M %S'); echo $((10#$h*3600+10#$m*60+10#$s)); }

# Capture window: 09:31:30 .. last scan (default 09:36:30 = display 1 bar earlier, 2026-06-23).
# Display uses the LAST scan record; ending at :36:30 (vs old :37:30) shows the pick ~1 min
# earlier (uses the 09:35 bar / ~09:36 price instead of ~09:37). Revert: RISER_LAST_MIN=37.
# REPLAY (test/validation only): RISER_REPLAY_DATE set -> skip the live capture loop + persist +
# exit-tracker launch; the Python block reads the archived dump for that date instead.
if [[ -n "${RISER_REPLAY_DATE:-}" ]]; then RISER_TRACK=0; export RISER_TRACK; fi
if [[ -z "${RISER_REPLAY_DATE:-}" ]]; then
for MIN in $(seq 31 "${RISER_LAST_MIN:-36}"); do
  TARGET=$((9*3600 + MIN*60 + 30))               # HH:MM:30 ET
  while [[ "$(et_secs)" -lt "$TARGET" ]]; do sleep 2; done
  rm -f /tmp/h12a_dump.jsonl
  H12A_DUMP=1 "$PY" -m src.scan.engine ml_filter >/dev/null 2>&1
  [[ -f /tmp/h12a_dump.jsonl ]] && cp /tmp/h12a_dump.jsonl "$OUT/min_09${MIN}.jsonl"
done
fi

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
# REPLAY hook (test/validation only): RISER_REPLAY_DATE=YYYY-MM-DD overrides `now` to that trading
# day 09:37 ET and reads the archived dump at data/riser_dumps/<date>/ -> the 1-min/ETF fetches then
# pull that day's real historical bars. Lets the ACTUAL deployed code path be replayed off-market.
_rpd=os.environ.get('RISER_REPLAY_DATE','')
_dumpglob='/tmp/riser_capture/min_*.jsonl'
if _rpd:
    _rpt=os.environ.get('RISER_REPLAY_TIME','09:37')  # HH:MM (bar window end / eval time)
    now=datetime(int(_rpd[:4]),int(_rpd[5:7]),int(_rpd[8:10]),int(_rpt[:2]),int(_rpt[3:5]),0,tzinfo=ET)
    _dumpglob=f'/home/saengtawan/work/project/cc/stock-analyzer/data/riser_dumps/{_rpd}/min_*.jsonl'
    print(f"[REPLAY] now={now.isoformat()} dumps={_dumpglob}")
# accumulate per-symbol latest record across the 7 scans (Z1 only = mfo 0-9)
acc={}; _mingain={}; _gser={}
for f in sorted(glob.glob(_dumpglob)):
    for ln in open(f):
        r=json.loads(ln)
        if not (0<=r.get('mfo',99)<=9): continue
        acc[r['sym']]=r  # latest wins (files sorted by minute)
        _g=r.get('gain')
        if _g is not None:
            _mingain[r['sym']]=min(_mingain.get(r['sym'],_g),_g)  # min gain across the 6 scans
            _gser.setdefault(r['sym'],[]).append(_g)              # gain path across scans (time order)
for _s in acc:
    acc[_s]['min_gain']=_mingain.get(_s)
    _gs=_gser.get(_s,[])                                          # maxDD = biggest giveback from running peak
    if len(_gs)>=2:
        _pk=_gs[0]; _dd=0.0
        for _v in _gs[1:]:
            _pk=max(_pk,_v); _dd=max(_dd,_pk-_v)
        acc[_s]['maxdd']=_dd
    else:
        acc[_s]['maxdd']=None
    acc[_s]['n_read']=len(_gs)
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
# 2026-07-08 (user): operational price cap — drop candidates priced > RISER_MAX_PRICE (affordability/
# position-sizing; price is orthogonal to the % pop outcome so no edge lost). off/unset = no cap.
_mp=os.environ.get('RISER_MAX_PRICE','')
_MAX_PRICE=float(_mp) if _mp not in ('','off') else None
# 2026-07-11 (user deploy LIVE): STEADY mode widens the pool to gain 0.5-6 (the low-gain-RISING
# stocks are the edge — high-gain=froth that fades). The rising filter + sector-strength rank in the
# 'steady' rank branch does the real selection. Only widens when RISER_RANK_MODE=steady.
if os.environ.get('RISER_RANK_MODE') in ('steady','pmgap'):
    _MIN_GAIN=0.5; _MAX_GAIN=6.0
def _riser_ok(r):
    g=(r.get('gain') or -99)
    if not (_MIN_GAIN < g <= _MAX_GAIN): return False
    if _GAP_CAP is not None and r.get('gap') is not None and r['gap'] > _GAP_CAP: return False
    if _MAX_PRICE is not None and r.get('price') and r['price'] > _MAX_PRICE: return False
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
_abstain_reason=None   # set when a GATE empties risers (vs genuinely empty band) -> honest status msg
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
        risers=[]; _abstain_reason=f"VIX-20d storm ({_vix20:.1f}>={_VIX20_MAX:.0f}) — no-edge regime"
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
        if not risers and _pre>0: _abstain_reason=f"all {_pre} band candidates failed identity gate (n>=8 & avg>0)"
# SPX-GEX gate (2026-06-25). Abstain on a fragile MARKET day: prior-day SPX GEX < 0 = dealers short
# gamma (past the gamma-flip at 0) = they AMPLIFY moves -> reversal-prone. Validated 15yr (GEX<0 ->
# next-day |move| 2.4x; 16/20 worst days were prior-day GEX<0) and ORTHOGONAL to spy_intra (39% of
# GEX<0 days are SPY-green) -> catches "green-but-fragile" days the direction/exit signals miss
# (+1.27% on SPY-green days, +0.97% beyond the VIX-20d gate). On GEX<0 days even exit@10:05 loses
# -0.83% so ABSTAIN beats trade-and-exit. Free SqueezeMetrics CSV, prior-day = lookahead-safe,
# graceful on fetch fail (cached). 0 = gamma flip = mechanical threshold, not a fitted number.
# Disable: RISER_SPXGEX_GATE=0.
if os.environ.get('RISER_SPXGEX_GATE','0')=='1' and risers:
    try:
        import sys as _sg; _sg.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
        from src.scan.spx_gex import latest_spx_gex
        _sgd,_sgv=latest_spx_gex(now.strftime('%Y-%m-%d'))
        if _sgv is not None and _sgv<0:
            print(f"[spx-gex] SPX GEX {_sgv/1e9:+.2f}B < 0 ({_sgd}, fragile/short-gamma market) -> ABSTAIN")
            risers=[]; _abstain_reason=f"SPX-GEX {_sgv/1e9:+.2f}B<0 ({_sgd}) — fragile/short-gamma market"
        else:
            print(f"[spx-gex] SPX GEX {(_sgv/1e9 if _sgv is not None else 0):+.2f}B ({_sgd or 'n/a'}) >= 0 -> ok")
    except Exception as _sge:
        print(f"[spx-gex] skip (fetch/err): {_sge}")
# WIN_P GATE (2026-06-24, user deploy on LIVE evidence). Keep only win_p >= RISER_WINP_MIN, then
# rank-by-gain among survivors. Empty -> abstain (faithful to "low win_p = likely fade"; don't pick
# a likely loser). Live N=7 showed perfect win_p->ret separation (corr +0.89; >=0.55 WR100% vs <0.55
# WR0%) BUT N tiny + backtest fold-split previously REJECTED a win_p gate -> HIGH-RISK bet, tracked
# vs winp_ab_shadow. The lane had run gain-only (NO win_p filter) since 2026-06-12; this re-adds it.
# Reversible: RISER_WINP_MIN=0 (or unset) -> gain-only. Tune threshold via the same flag.
_WINP_MIN=float(os.environ.get('RISER_WINP_MIN','0') or 0)
if _WINP_MIN>0:
    _pw=len(risers); risers=[r for r in risers if (r.get('win_p') or 0)>=_WINP_MIN]
    print(f"[winp-gate] win_p>={_WINP_MIN} -> {len(risers)}/{_pw} pass" + ("  (ABSTAIN: none qualify)" if not risers else ""))
    if not risers and _pw>0: _abstain_reason=f"all {_pw} in-band candidates below win_p>={_WINP_MIN}"
print(f"=== riser_momentum @ {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ===")
if not risers:
    if _abstain_reason:
        print(f"Status: abstain — {_abstain_reason}  (band HAD candidates; gated out, NOT an empty band)"); raise SystemExit
    print(f"Status: no_picks — no Z1 riser in band (gain {_MIN_GAIN}-{_MAX_GAIN}, gap<={_GAP_CAP}) across 09:31-36 scans"); raise SystemExit
# ENTRY-QUALITY (2026-06-24, user deploy — reversible flags). min-gain = lowest gain-from-open
# across the 6 scans (path cleanliness). BACKTEST (on reconstructed pool, NOT exactly live —
# verify on persisted real dumps forward): RISER_MINGAIN_FILTER drops dippers (min<0); RISER_TIEBREAK_WIN
# picks highest min-gain among near-ties. Cut worst -27->-17, net-neutral, catches HOOD-type. Disable: =0.
if os.environ.get('RISER_MINGAIN_FILTER','0')=='1':
    _clean=[r for r in risers if (r.get('min_gain') is None or r['min_gain']>=0)]
    if _clean: risers=_clean   # drop negative-dip candidates; if ALL dip, keep all (don't abstain)
# CLEAN-PATH filter (2026-06-24, user deploy). Drop choppy risers = maxDD from the running peak
# across scans > RISER_MAXDD_CAP, assessed only when seen >= RISER_MAXDD_MINREAD times (late-entrants
# exempt, can't judge). Keep-all if it empties (don't abstain on cleanliness alone). CAVEAT: conflicts
# with the vol-IS-momentum finding (choppy may = the real mover) + barely binds -> track forward.
# Reversible: RISER_MAXDD_CAP unset/=0 -> off. Tune cap / RISER_MAXDD_MINREAD.
_ddcap=float(os.environ.get('RISER_MAXDD_CAP','0') or 0)
_ddmin=int(os.environ.get('RISER_MAXDD_MINREAD','3'))
if _ddcap>0:
    def _path_ok(r):
        _dd=r.get('maxdd')
        if _dd is None or r.get('n_read',0)<_ddmin: return True   # too few readings -> exempt
        return _dd<=_ddcap
    _cp=[r for r in risers if _path_ok(r)]
    print(f"[clean-path] maxDD<={_ddcap} (n>={_ddmin}) -> {len(_cp)}/{len(risers)} pass")
    if _cp: risers=_cp
# ROLLOVER filter (2026-06-25). The dump's per-scan gain is SPARSE and missed ALAB's 09:35 +4.4%
# peak -> dump-maxDD wrongly read 0 ("clean"). Fix: pull the REAL 1-min bars (09:30->now) at the
# pick and compute giveback = peak_gain - current_gain. Drop candidates that ROLLED OVER before
# entry (giveback > RISER_ROLLOVER_CAP). Validated 06-24: ALAB giveback 1.7% (peak +4.4 -> entry
# +2.7) = the worst pick -4.1%; winners EXPE/ABNB sat at their highs (giveback ~0). No bars -> pass;
# keep-all if empty; giveback stored on picks. Reversible: RISER_ROLLOVER_CAP=0.
_rocap=os.environ.get('RISER_ROLLOVER_CAP','0')
if _rocap not in ('0','off',''):
    _rocap=float(_rocap)
    try:
        import requests as _rq, zoneinfo as _zi
        _kk={}
        for _l in open('/home/saengtawan/work/project/cc/stock-analyzer/.env'):
            _l=_l.strip()
            if _l and not _l.startswith('#') and '=' in _l:
                _k,_v=_l.split('=',1); _kk[_k.strip()]=_v.strip().strip('\"\'')
        _hdr={'APCA-API-KEY-ID':_kk.get('ALPACA_API_KEY'),'APCA-API-SECRET-KEY':_kk.get('ALPACA_SECRET_KEY')}
        _u0=now.replace(hour=9,minute=30,second=0,microsecond=0).astimezone(_zi.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
        _u1=now.astimezone(_zi.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
        _rr=_rq.get('https://data.alpaca.markets/v2/stocks/bars',headers=_hdr,
            params={'symbols':','.join(r['sym'] for r in risers),'timeframe':'1Min','start':_u0,'end':_u1,'feed':'iex','limit':5000},timeout=15)
        _bd=_rr.json().get('bars',{})
        def _giveback(r):
            _b=_bd.get(r['sym'],[])
            if len(_b)<2: return None
            _op=_b[0]['o']
            if _op<=0: return None
            return ((max(x['h'] for x in _b)/_op-1)-(_b[-1]['c']/_op-1))*100
        for r in risers: r['giveback']=_giveback(r)
        _ro=[r for r in risers if (r.get('giveback') is None or r['giveback']<=_rocap)]
        _rdrop=[r['sym'] for r in risers if r.get('giveback') is not None and r['giveback']>_rocap]
        print(f"[rollover] giveback<={_rocap}% -> {len(_ro)}/{len(risers)} pass" + (f" (drop {_rdrop})" if _rdrop else ""))
        if _ro: risers=_ro
    except Exception as _roe:
        print(f"[rollover] skip: {_roe}")
# GEX filter (2026-06-25, user deploy). Drop NEG-GEX (put-heavy = dealer short gamma = fade-risk)
# candidates. gex_live reads the cached prior-day chain (OI is prior-day, doesn't change intraday)
# and recomputes gamma with the live price -> <100ms, no API, available at the 09:37 pick. Sign from
# the 06-24 cross-section (POS-GEX +1.94% vs NEG-GEX -0.30%, N=19, 1 DAY -> UNVALIDATED, may be
# inverted: historical SPY GEX skewed all-negative). Candidates with no cached chain pass through;
# keep-all if the filter empties (don't abstain on GEX). gex stored on each pick. RISER_GEX_FILTER=0 -> off.
if os.environ.get('RISER_GEX_FILTER','0')=='1':
    try:
        import sys as _gxs; _gxs.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
        from src.scan.gex_live import gex_live as _gxl
        _gxd=now.strftime('%Y-%m-%d')
        def _gex_ok(r):
            _g=_gxl(r['sym'], r.get('price') or 0, _gxd); r['gex']=_g
            return (_g is None) or (_g>=0)   # no cache -> pass; NEG-GEX -> drop
        _gf=[r for r in risers if _gex_ok(r)]
        _ncov=sum(1 for r in risers if r.get('gex') is not None)
        print(f"[gex-filter] drop NEG-GEX -> {len(_gf)}/{len(risers)} pass ({_ncov} had cache)")
        if _gf: risers=_gf
    except Exception as _gee:
        print(f"[gex-filter] skip: {_gee}")
# RANKING (2026-06-24). RISER_RANK_MODE = gain (default) | gainwinp | mean.
#   mean = average of gain-rank and win_p-rank (both 1=best). Ranks are BOUNDED (1..N) so a huge gain
#     can't dominate a low win_p (froth resistance: ARM gain6.2/winp0.43 lands mid-pack, NOT #1 the
#     way gain×win_p would put it), while a low-gain HIGH-win_p name can still rise (ABNB winp#1 ->
#     top despite gain#6). Needs to be good in BOTH. Pairs with a LIGHT win_p floor (RISER_WINP_MIN
#     ~0.45) that blocks only the worst (ARM) and abstains when the whole pool is bad.
#   gainwinp = gain*win_p (REVERTED as default: high gain dominates low win_p -> picks froth losers).
#   gain = pure momentum + min-gain tiebreak (original). Reversible: RISER_RANK_MODE=gain.
_rankmode=os.environ.get('RISER_RANK_MODE','gain')
if _rankmode=='mean':
    _bg=sorted(risers,key=lambda r:-r['gain']); _gr={id(r):i+1 for i,r in enumerate(_bg)}
    _bw=sorted(risers,key=lambda r:-(r.get('win_p') or 0)); _wr={id(r):i+1 for i,r in enumerate(_bw)}
    risers.sort(key=lambda r:(_gr[id(r)]+_wr[id(r)])/2.0)
    top=risers[0]; _rankdesc='mean-rank(gain,win_p)'
elif _rankmode=='idavg':
    # 2026-07-03: STATISTICS over ML. mean-rank(gain, id-avg) — id-avg = per-stock prior avg
    # (track record), robust +0.51/4-of-4-yrs vs win_p coin-flip (AUC~0.50, anti-predictive on
    # risers). win_p kept only as a LIGHT froth-floor (RISER_WINP_MIN 0.30). Reversible: =mean.
    try:
        import sys as _si; _si.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
        from src.scan import stock_track_record as _STRi
    except Exception: _STRi=None
    _dd=now.strftime('%Y-%m-%d')
    def _ida(r):
        if _STRi is None: return -99.0
        try:
            _n,_a=_STRi.prior_stats(r['sym'],_dd); return _a if _a is not None else -99.0
        except Exception: return -99.0
    _bg=sorted(risers,key=lambda r:-r['gain']); _gr={id(r):i+1 for i,r in enumerate(_bg)}
    _bi=sorted(risers,key=lambda r:-_ida(r)); _ir={id(r):i+1 for i,r in enumerate(_bi)}
    risers.sort(key=lambda r:(_gr[id(r)]+_ir[id(r)])/2.0)
    top=risers[0]; _rankdesc='mean-rank(gain,id-avg)'
elif _rankmode=='idavg_sector':
    # 2026-07-08 (user deploy LIVE): mean-rank(gain, id-avg, own-sector-ETF). own-sector = the
    # candidate's sector ETF gain (open->09:36). Backtest robust: median +0.41->+0.70, WR 55->57,
    # rmTop5 up, fold both+, 4/4 yrs (FIXES current idavg's weak foldA +0.02 / 2024 +0.0). own-sector
    # is live-faithful (ml_filter fetches sector ETFs via etf_intraday, same path as spy_intra).
    # IN-SAMPLE (not forward) -> TRACK. Does NOT help 07-07-type coin-flips, helps the average.
    # Reversible: RISER_RANK_MODE=idavg (drops the sector dimension).
    try:
        import sys as _si2; _si2.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
        from src.scan import stock_track_record as _STRi2
    except Exception: _STRi2=None
    _dd2=now.strftime('%Y-%m-%d')
    def _ida2(r):
        if _STRi2 is None: return -99.0
        try:
            _n,_a=_STRi2.prior_stats(r['sym'],_dd2); return _a if _a is not None else -99.0
        except Exception: return -99.0
    _sec2etf={'Energy':'XLE','Technology':'XLK','Financial Services':'XLF','Financials':'XLF','Healthcare':'XLV','Industrials':'XLI','Consumer Cyclical':'XLY','Consumer Defensive':'XLP','Basic Materials':'XLB','Utilities':'XLU','Real Estate':'XLRE','Communication Services':'XLC'}
    _etfg={}
    try:
        import requests as _rq2, zoneinfo as _zi2
        _kk2={}
        for _l in open('/home/saengtawan/work/project/cc/stock-analyzer/.env'):
            _l=_l.strip()
            if _l and not _l.startswith('#') and '=' in _l:
                _k,_v=_l.split('=',1); _kk2[_k.strip()]=_v.strip().strip('\"\'')
        _hdr2={'APCA-API-KEY-ID':_kk2.get('ALPACA_API_KEY'),'APCA-API-SECRET-KEY':_kk2.get('ALPACA_SECRET_KEY')}
        _u0b=now.replace(hour=9,minute=30,second=0,microsecond=0).astimezone(_zi2.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
        _u1b=now.astimezone(_zi2.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
        _etfs=sorted(set(_sec2etf.get(r.get('sec')) for r in risers if _sec2etf.get(r.get('sec'))))
        if _etfs:
            _rr2=_rq2.get('https://data.alpaca.markets/v2/stocks/bars',headers=_hdr2,params={'symbols':','.join(_etfs),'timeframe':'1Min','start':_u0b,'end':_u1b,'feed':'iex','limit':5000},timeout=15)
            _bd2=_rr2.json().get('bars',{})
            for _e in _etfs:
                _b=_bd2.get(_e,[])
                if len(_b)>=1 and _b[0]['o']>0: _etfg[_e]=(_b[-1]['c']/_b[0]['o']-1)*100
        print(f"[own-sector] ETF gains @09:36: {{{', '.join('%s:%+.2f'%(k,v) for k,v in sorted(_etfg.items()))}}}")
    except Exception as _see:
        print(f"[own-sector] fetch skip (fall back to gain+id): {_see}")
    def _secstr(r):
        _e=_sec2etf.get(r.get('sec')); return _etfg.get(_e,-99.0) if _e else -99.0
    _bg=sorted(risers,key=lambda r:-r['gain']); _gr={id(r):i+1 for i,r in enumerate(_bg)}
    _bi=sorted(risers,key=lambda r:-_ida2(r)); _ir={id(r):i+1 for i,r in enumerate(_bi)}
    _bs=sorted(risers,key=lambda r:-_secstr(r)); _sr={id(r):i+1 for i,r in enumerate(_bs)}
    risers.sort(key=lambda r:(_gr[id(r)]+_ir[id(r)]+_sr[id(r)])/3.0)
    top=risers[0]; _rankdesc='mean-rank(gain,id-avg,own-sector)'
elif _rankmode=='pmgap':
    # 2026-07-12 (user): PREMARKET GAP-REVERSAL. Prefer candidates that GAPPED DOWN premarket
    # (pm_gap<0) in a STRONG sector (own-sector ETF >0) — "bad overnight news, idiosyncratic, in a
    # healthy sector -> real buyers step in -> reverses & runs". Validated 2024-25 (N=59): WR 75%,
    # median +0.83, per-year robust; out-of-sample July-2026 6-day fwd +0.48 vs steady -0.06.
    # VERIFIED no-lookahead (pm_gap = first 4AM premarket bar open / prev daily close, all pre-09:30)
    # and SIP-faithful (backfill == SIP recompute exact). MUST use feed=SIP (IEX premarket is empty).
    # Filter: pm_gap<0 AND own>0 -> fallback pm_gap<0 -> fallback all; rank by gain. IN-SAMPLE-ish
    # (small N) -> track forward. Rollback: RISER_RANK_MODE=steady.
    import requests as _rqp, sqlite3 as _s3p, zoneinfo as _zip
    _sec2etf_p={'Energy':'XLE','Technology':'XLK','Financial Services':'XLF','Financials':'XLF','Healthcare':'XLV','Industrials':'XLI','Consumer Cyclical':'XLY','Consumer Defensive':'XLP','Basic Materials':'XLB','Utilities':'XLU','Real Estate':'XLRE','Communication Services':'XLC'}
    _kkp={}
    for _l in open('/home/saengtawan/work/project/cc/stock-analyzer/.env'):
        _l=_l.strip()
        if _l and not _l.startswith('#') and '=' in _l:
            _k,_v=_l.split('=',1); _kkp[_k.strip()]=_v.strip().strip('\"\'')
    _hdrp={'APCA-API-KEY-ID':_kkp.get('ALPACA_API_KEY'),'APCA-API-SECRET-KEY':_kkp.get('ALPACA_SECRET_KEY')}
    _thp=_s3p.connect('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
    _dds=now.strftime('%Y-%m-%d')
    def _prevclose(sym):
        try:
            r=_thp.execute("SELECT close FROM stock_daily_ohlc WHERE symbol=? AND date<? ORDER BY date DESC LIMIT 1",(sym,_dds)).fetchone()
            return r[0] if r else None
        except Exception: return None
    # premarket 4AM(ET)->09:30, SIP. 4AM ET = 08:00 UTC (EDT) — use wide window, first bar = premarket
    _u0p=now.replace(hour=4,minute=0,second=0,microsecond=0).astimezone(_zip.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
    _u1p=now.replace(hour=9,minute=37,second=0,microsecond=0).astimezone(_zip.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
    def _pmgap(sym):
        try:
            pc=_prevclose(sym)
            if not pc: return None
            r=_rqp.get('https://data.alpaca.markets/v2/stocks/bars',headers=_hdrp,params={'symbols':sym,'timeframe':'5Min','start':_u0p,'end':_u1p,'feed':'sip','limit':300},timeout=15).json()
            b=r.get('bars',{}).get(sym,[])
            if not b: return None
            return (b[0]['o']/pc-1)*100   # first premarket bar open vs prev close
        except Exception: return None
    # own-sector ETF gain @09:36 (SIP, 1min open->09:36)
    _etfsp=sorted(set(_sec2etf_p.get(r.get('sec')) for r in risers if _sec2etf_p.get(r.get('sec'))))
    _etfgp={}
    try:
        _u0e=now.replace(hour=9,minute=30,second=0,microsecond=0).astimezone(_zip.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
        _re=_rqp.get('https://data.alpaca.markets/v2/stocks/bars',headers=_hdrp,params={'symbols':','.join(_etfsp),'timeframe':'1Min','start':_u0e,'end':_u1p,'feed':'sip','limit':2000},timeout=15).json().get('bars',{}) if _etfsp else {}
        for _e in _etfsp:
            _bb=_re.get(_e,[])
            if _bb and _bb[0]['o']>0: _etfgp[_e]=(_bb[-1]['c']/_bb[0]['o']-1)*100
    except Exception as _ee: print(f"[pmgap] ETF skip: {_ee}")
    for r in risers:
        r['pmgap']=_pmgap(r['sym']); r['own']=_etfgp.get(_sec2etf_p.get(r.get('sec')),None)
    _have=[r for r in risers if r.get('pmgap') is not None]
    # FILTER thresholds (A/B knobs). Default 0/0 = validated version. In-sample 2024-25 (NOT out-of-sample
    # verified — fetch failed) suggests DEEPER gap-down is better + monotonic: pm_gap<-1.0 -> WR 75->84,
    # median +0.83->+1.21, both years; own>0.2 -> WR 76. Track fwd before making these the default.
    _PGMAX=float(os.environ.get('RISER_PMGAP_MAX','0'))     # candidate must have pm_gap < this
    _OWNMIN=float(os.environ.get('RISER_PMGAP_OWNMIN','0')) # own-sector must be > this
    _elig=[r for r in _have if r['pmgap']<_PGMAX and (r.get('own') is not None and r['own']>_OWNMIN)]
    _gapdn=[r for r in _have if r['pmgap']<_PGMAX]
    _pool=_elig if _elig else (_gapdn if _gapdn else (_have if _have else risers))
    _tag='gap<0+sec>0' if _elig else ('gap<0' if _gapdn else 'fallback')
    print(f"[pmgap] {len(_have)} w/ pm_gap | {len(_gapdn)} gap<0 | {len(_elig)} gap<0+sec>0 -> pool={_tag}")
    # RANK within the filtered pool = gain (forward-validated). 2026-07-12: RANK IS NOISE HERE — the
    # FILTER (gap<0+own>0) is the whole edge. Ablation N=32 (2024-25) said gain-rank worst / pm_gap-
    # most-down & RANDOM better; but the July-2026 6-day OUT-OF-SAMPLE said the OPPOSITE (gain +0.50 vs
    # pm_gap-most-down -0.06 — gain caught MRNA +1.49 on 07-02). Two small samples disagree = rank
    # doesn't reliably matter. Keep gain (simplest, out-of-sample-validated). Don't over-tune on N=32.
    _pool.sort(key=lambda r:-r['gain'])
    risers=_pool; top=risers[0]; _rankdesc=f'pm_gap-reversal ({_tag}, gain-ranked)'
elif _rankmode=='steady':
    # 2026-07-11 (user deploy LIVE, no shadow): STEADY-RISER. On weak-Tech / rotation days the
    # high-gain band is froth that fades; the edge is LOW-GAIN stocks RISING STEADILY in the strong
    # sector (energy/materials/defensive incl). Pool widened to gain 0.5-6 (_riser_ok floor -> 0.5 for
    # this mode). Two-part selection:
    #   1. RISING filter — near intraday high + accelerating: giveback<0.4 (close within 0.4% of the
    #      09:30-now high) AND 2nd-half slope>0 (still climbing). Kills faders/toppers.
    #   2. RANK = mean(own-sector-ETF-strength, rising-strength[=-giveback], id-avg). Picks the
    #      steady-climber in the strongest sector with the best track record.
    # Validated vs current idavg_sector (wf_1min replay, relative): median +0.40->+0.57, mean
    # +0.41->+0.94, WR 54->61, Sharpe 0.10->0.29, rmTop20 Δ still +0.55 (distributional NOT fat-tail),
    # worst -11.1->-6.1, deep-losers 54->20, 9/11 quarters, sector-diversified (14% defensive/energy).
    # IN-SAMPLE -> track forward. Rollback: RISER_RANK_MODE=idavg_sector (floor auto reverts to 1.8).
    import sys as _si3; _si3.path.insert(0,'/home/saengtawan/work/project/cc/stock-analyzer')
    try:
        from src.scan import stock_track_record as _STR3
    except Exception: _STR3=None
    _dd3=now.strftime('%Y-%m-%d')
    def _ida3(r):
        if _STR3 is None: return None
        try:
            _n,_a=_STR3.prior_stats(r['sym'],_dd3); return _a
        except Exception: return None
    _sec2etf3={'Energy':'XLE','Technology':'XLK','Financial Services':'XLF','Financials':'XLF','Healthcare':'XLV','Industrials':'XLI','Consumer Cyclical':'XLY','Consumer Defensive':'XLP','Basic Materials':'XLB','Utilities':'XLU','Real Estate':'XLRE','Communication Services':'XLC'}
    _etfg3={}
    import requests as _rq3, zoneinfo as _zi3
    _kk3={}
    for _l in open('/home/saengtawan/work/project/cc/stock-analyzer/.env'):
        _l=_l.strip()
        if _l and not _l.startswith('#') and '=' in _l:
            _k,_v=_l.split('=',1); _kk3[_k.strip()]=_v.strip().strip('\"\'')
    _hdr3={'APCA-API-KEY-ID':_kk3.get('ALPACA_API_KEY'),'APCA-API-SECRET-KEY':_kk3.get('ALPACA_SECRET_KEY')}
    _u0c=now.replace(hour=9,minute=30,second=0,microsecond=0).astimezone(_zi3.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
    _u1c=now.astimezone(_zi3.ZoneInfo('UTC')).strftime('%Y-%m-%dT%H:%M:%SZ')
    # 1) sector ETF strength (own-sector)
    try:
        _etfs3=sorted(set(_sec2etf3.get(r.get('sec')) for r in risers if _sec2etf3.get(r.get('sec'))))
        if _etfs3:
            _re3=_rq3.get('https://data.alpaca.markets/v2/stocks/bars',headers=_hdr3,params={'symbols':','.join(_etfs3),'timeframe':'1Min','start':_u0c,'end':_u1c,'feed':'iex','limit':5000},timeout=15)
            _bde=_re3.json().get('bars',{})
            for _e in _etfs3:
                _b=_bde.get(_e,[])
                if len(_b)>=1 and _b[0]['o']>0: _etfg3[_e]=(_b[-1]['c']/_b[0]['o']-1)*100
    except Exception as _e3: print(f"[steady] ETF fetch skip: {_e3}")
    # 2) per-candidate 1-min bars -> giveback + 2nd-half slope (rising signal)
    _rise={}
    try:
        _syms3=[r['sym'] for r in risers]
        for _ci in range(0,len(_syms3),50):
            _ch=_syms3[_ci:_ci+50]
            _rb3=_rq3.get('https://data.alpaca.markets/v2/stocks/bars',headers=_hdr3,params={'symbols':','.join(_ch),'timeframe':'1Min','start':_u0c,'end':_u1c,'feed':'iex','limit':10000},timeout=20)
            _bdb=_rb3.json().get('bars',{})
            for _s in _ch:
                _b=_bdb.get(_s,[])
                if len(_b)<4: continue
                _op=_b[0]['o']
                if _op<=0: continue
                _hi=max(x['h'] for x in _b); _cur=_b[-1]['c']
                _gb=(_hi/_op-1)*100-(_cur/_op-1)*100
                _cl=[(x['c']/_op-1)*100 for x in _b]; _slope=_cl[-1]-_cl[len(_cl)//2]
                _rise[_s]=(_gb,_slope)
    except Exception as _e4: print(f"[steady] bar fetch error: {_e4}")
    # 3) filter to rising + identity, annotate
    # RISER_RISING_GB (2026-07-11, user deploy): giveback threshold for "at the intraday high". Tightened
    # 0.4->0.3 — pick only stocks REALLY glued to their high (<0.3% off) => the ones starting to fade drop
    # out. Validated steady+capture-peak per-year+fold: med +0.67->+0.76, WR 77->79, Sharpe 0.66->0.72,
    # worst -4.0->-2.3, every year >= current, monotonic (0.5 worse / 0.4 mid / 0.3 best). Rollback: =0.4.
    _RISING_GB=float(os.environ.get('RISER_RISING_GB','0.4'))
    _steady=[]
    for r in risers:
        _rv=_rise.get(r['sym'])
        if _rv is None: continue
        _gb,_sl=_rv
        _sid=_ida3(r)
        r['gb']=_gb; r['slope']=_sl; r['own']=_etfg3.get(_sec2etf3.get(r.get('sec')),-99.0); r['sid_s']=_sid
        if _gb<_RISING_GB and _sl>0 and _sid is not None and _sid>0:
            _steady.append(r)
    print(f"[steady] ETF {{{', '.join('%s:%+.2f'%(k,v) for k,v in sorted(_etfg3.items()))}}} | rising+id {len(_steady)}/{len(risers)} pass")
    if _steady:
        _or3={id(r):i+1 for i,r in enumerate(sorted(_steady,key=lambda r:-r['own']))}
        _gbr3={id(r):i+1 for i,r in enumerate(sorted(_steady,key=lambda r:r['gb']))}   # lower giveback=better
        _idr3={id(r):i+1 for i,r in enumerate(sorted(_steady,key=lambda r:-(r['sid_s'] or -9)))}
        _steady.sort(key=lambda r:(_or3[id(r)]+_gbr3[id(r)]+_idr3[id(r)])/3.0)
        risers=_steady; top=risers[0]; _rankdesc='steady(own-sector+rising+id)'
    else:
        print("Status: no_picks — steady: no low-gain riser climbing steadily in a strong sector"); raise SystemExit
elif _rankmode=='gainwinp':
    risers.sort(key=lambda r: -(r['gain']*(r.get('win_p') or 0)))
    top=risers[0]; _rankdesc='gain×win_p'
else:
    risers.sort(key=lambda r: -r['gain'])
    top=risers[0]
    _tw=float(os.environ.get('RISER_TIEBREAK_WIN','0') or 0)
    if _tw>0 and len(risers)>1:
        _tie=[r for r in risers if r['gain']>=risers[0]['gain']-_tw]
        top=max(_tie, key=lambda r:(r.get('min_gain') if r.get('min_gain') is not None else -99))
    _rankdesc='gain'
# TOP-N picks (2026-06-24): #1 + next distinct names by the same rank key. RISER_TOP_N (default 1).
# Diversification: top-2/3 cuts the worst trade (broad pool -13 -> -6) though per-pick edge is flat.
_topn=max(1,int(os.environ.get('RISER_TOP_N','1') or 1))
picks=[top]+[r for r in risers if r['sym']!=top['sym']][:_topn-1]
print(f"Status: active — top-{len(picks)} RISER by {_rankdesc} in band({_MIN_GAIN}-{_MAX_GAIN},gap<={_GAP_CAP}) among {len(risers)} Z1 candidates (09:31:30-09:36:30)")
# ENTRY: chase MARKET immediately (2026-06-24 refit). Limit-dip LOSES once measured realistically
# (pick visible ~09:37 -> the dip is already past): chase -1.18 > static-limit -1.36 / walking -1.25;
# timing 09:33-40 = noise. Set RISER_LIMIT_DISCOUNT>0 to re-show a limit suggestion.
_disc=float(os.environ.get('RISER_LIMIT_DISCOUNT','0') or 0)
_regime=os.environ.get('RISER_REGIME_EXIT','0')=='1'
for _i,_p in enumerate(picks,1):
    _px=_p.get('price',0)
    print()
    print(f"  BUY#{_i}  {_p['sym']}  @ ${_px:.2f}")
    print(f"        gain +{_p['gain']:.1f}%  min-gain {(('%+.1f%%'%_p['min_gain']) if _p.get('min_gain') is not None else 'na')}  win_p {_p.get('win_p',0):.3f}  sec {str(_p.get('sec',''))[:12]}  spy_intra {_p.get('spy_intra',0):+.2f}")
    if _disc>0:
        print(f"        ENTRY: LIMIT @ ${_px*(1-_disc/100):.2f} (display −{_disc:.1f}%) — runner ไม่ fill → market @ ${_px:.2f}")
    else:
        print(f"        ENTRY: chase MARKET ทันที @ ~${_px:.2f} (อย่ารอ limit — ย่อผ่านไปแล้วตอนเห็น pick)")
    if _regime:
        _si=_p.get('spy_intra')
        if _si is None: _ep='hold-EOD (spy_intra n/a)'
        elif _si>0:     _ep=f'hold-EOD (SPY {_si:+.2f}% green, sustain)'
        else:           _ep=f'exit~10:05 (SPY {_si:+.2f}% red, pump-fade)'
        print(f"        EXIT-PLAN: {_ep}  [+ peak-fade reactive]")
print()
_pset={p['sym'] for p in picks}
_runners=[r for r in risers if r['sym'] not in _pset][:5]
print(f"  รองลงมา: " + " ".join(f"{r['sym']}+{r['gain']:.1f}%(wp{r.get('win_p',0):.2f})" for r in _runners))
# journal each pick for forward tracking
if _rpd:
    print("\n  [REPLAY: skip journal]"); raise SystemExit
try:
    import sqlite3
    db=sqlite3.connect('/home/saengtawan/work/project/cc/stock-analyzer/data/scan_journal.db')
    db.execute("""CREATE TABLE IF NOT EXISTS riser_picks(scan_date TEXT, scan_ts TEXT, symbol TEXT, price REAL, gain REAL, win_p REAL, sector TEXT, n_cand INT)""")
    # 2026-06-16: add gap+range_exp; 2026-06-25: add gex (live monitoring of the GEX filter). idempotent.
    for _c in ('gap REAL','range_exp REAL','gex REAL','giveback REAL'):
        try: db.execute(f"ALTER TABLE riser_picks ADD COLUMN {_c}")
        except Exception: pass
    for _p in picks:
        db.execute("INSERT INTO riser_picks(scan_date,scan_ts,symbol,price,gain,win_p,sector,n_cand,gap,range_exp,gex,giveback) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(now.strftime('%Y-%m-%d'),now.strftime('%Y-%m-%d %H:%M:%S'),_p['sym'],_p.get('price',0),_p['gain'],_p.get('win_p',0),_p.get('sec',''),len(risers),_p.get('gap'),_p.get('range_exp'),_p.get('gex'),_p.get('giveback')))
    db.commit(); db.close()
    print(f"\n  [journaled {len(picks)} pick(s) -> riser_picks]")
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
  _DISC="${RISER_LIMIT_DISCOUNT:-0}"
  # launch an exit-tracker (+ entry-fill monitor if a limit is in use) for EACH pick of the latest
  # scan — top-N aware (2026-06-24): reads all rows at the most recent scan_ts.
  while IFS='|' read -r RSYM RPRICE; do
    [[ -z "${RSYM:-}" ]] && continue
    if pgrep -f "exit_loop.sh $RSYM " >/dev/null 2>&1; then
      echo "[riser] $RSYM exit-tracker already running — skip"
    else
      LOG="$LOG_DIR/${RSYM}_${ET_DATE}_riser.log"
      nohup bash scripts/exit_loop.sh "$RSYM" "$RPRICE" 09:37 "$ET_DATE" > "$LOG" 2>&1 < /dev/null &
      disown 2>/dev/null || true
      echo "[riser] launched exit-tracker: $RSYM @ \$$RPRICE (riser dynamic exit) -> $LOG"
    fi
    if [[ "${RISER_FILL_WATCH:-1}" == "1" && -n "$_DISC" && "$_DISC" != "0" ]]; then
      _LIM=$(awk -v p="$RPRICE" -v d="$_DISC" 'BEGIN{printf "%.2f", p*(1-d/100)}')
      ELOG="$LOG_DIR/${RSYM}_${ET_DATE}_entry.log"
      if ! pgrep -f "entry_fill_watch.py $RSYM " >/dev/null 2>&1; then
        nohup "$PY" scripts/entry_fill_watch.py "$RSYM" "$_LIM" "$RPRICE" "$ET_DATE" > "$ELOG" 2>&1 < /dev/null &
        disown 2>/dev/null || true
        echo "[riser] launched entry-fill monitor: $RSYM LIMIT \$$_LIM -> $ELOG"
      fi
    fi
  done < <(sqlite3 data/scan_journal.db \
    "SELECT symbol, price FROM riser_picks WHERE scan_date='$ET_DATE' AND scan_ts=(SELECT MAX(scan_ts) FROM riser_picks WHERE scan_date='$ET_DATE')" 2>/dev/null)
fi
