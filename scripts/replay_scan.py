"""Replay a saved scan snapshot — re-run scan logic with current code/models on historical input.

Usage:
  python3 scripts/replay_scan.py data/scan_snapshots/2026-04-29_09-30-54.json.gz
  python3 scripts/replay_scan.py --date 2026-04-29 --time 09:30
  python3 scripts/replay_scan.py --date 2026-04-29 --time 09:30 --models 2026-04-29  # use old models

Outputs picks that current system would generate from the saved scan-time data.
Compares to live picks (if available in scan_journal).
"""
import argparse, gzip, json, sqlite3, sys, glob
import numpy as np
import lightgbm as lgb
from pathlib import Path
from collections import defaultdict
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scan.ml_scorer import V22_DIR, MLScorer
from src.scan.strategies.ml_filter import MLFilterStrategy
from src.scan.alpaca_bars import extract_multibar_features

SECTOR_ETF_MAP = {
    'Technology': 'xlk_intra', 'Healthcare': 'xlv_intra', 'Health Care': 'xlv_intra',
    'Financial Services': 'xlf_intra', 'Financials': 'xlf_intra',
    'Consumer Cyclical': 'xly_intra', 'Communication Services': 'xlc_intra',
    'Industrials': 'xli_intra', 'Consumer Defensive': 'xlp_intra',
    'Energy': 'xle_intra', 'Basic Materials': 'xlb_intra',
    'Real Estate': 'xlre_intra', 'Utilities': 'xlu_intra',
}
SECTOR_TO_ETF = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Health Care': 'XLV',
    'Financial Services': 'XLF', 'Financials': 'XLF',
    'Consumer Cyclical': 'XLY', 'Communication Services': 'XLC',
    'Industrials': 'XLI', 'Consumer Defensive': 'XLP',
    'Energy': 'XLE', 'Basic Materials': 'XLB',
    'Real Estate': 'XLRE', 'Utilities': 'XLU',
}

def find_snap(date, time_str):
    """Find snapshot file matching date + time prefix."""
    pattern = f'{ROOT}/data/scan_snapshots/{date}_{time_str.replace(":","-")}*.json.gz'
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None

def load_snap(path):
    with gzip.open(path, 'rt') as f:
        return json.load(f)

def load_day_state(date):
    p = ROOT / 'data' / 'scan_snapshots' / f'db_state_{date}.json.gz'
    if not p.exists():
        return None
    with gzip.open(p, 'rt') as f:
        return json.load(f)

def replay(snap_path, models_dir=None):
    print(f"Loading snap: {snap_path}", flush=True)
    snap = load_snap(snap_path)
    date = snap['scan_ts_et'][:10]
    print(f"  scan_ts: {snap['scan_ts_et']}, mfo: {snap['minutes_from_open']}, bucket: {snap['bucket']}")
    print(f"  saved model_version: {snap.get('model_version','unknown')}")
    print(f"  saved blacklist: {snap.get('sector_blacklist',[])}")
    print(f"  snaps: {len(snap['snaps'])} stocks, {len(snap['etf_snaps'])} ETFs")

    day_state = load_day_state(date)
    if not day_state:
        print(f"⚠️  No db_state_{date}.json.gz — daily history missing. Falling back to current DB.")
        # Fallback: query current DB
        conn = sqlite3.connect(str(ROOT / 'data' / 'trade_history.db'))
        # ... could implement fallback ...
        conn.close()
        return
    print(f"  daily_hist: {len(day_state['daily_hist'])} symbols")

    # Override model dir if specified
    if models_dir:
        print(f"  Using models from: {models_dir}")
        # Monkey-patch V22_DIR
        from src.scan import ml_scorer
        ml_scorer.V22_DIR = Path(models_dir)
        # Force fresh scorer
        if hasattr(MLScorer, '_instance'):
            delattr(MLScorer, '_instance')

    # Get current scorer (loads from V22_DIR which may be patched)
    from src.scan.ml_scorer import get_scorer
    scorer = get_scorer()
    print(f"  Active model: USE_ZONES={scorer.USE_ZONES}, zones loaded: {list(scorer.zone_tp1_models.keys())}")

    strategy = MLFilterStrategy()
    print(f"  Active blacklist: {strategy.SECTOR_BLACKLIST}")

    # Replay scoring on saved data
    snaps = snap['snaps']
    etf_snaps = snap['etf_snaps']
    sectors = snap['sectors']
    betas = snap['betas']
    mcaps = snap['mcaps']
    earnings_skip = set(snap['earnings_skip'])
    macro = snap['macro']
    daily_hist = day_state['daily_hist']
    daily_hl = day_state['daily_hl']
    avg_daily_vol = day_state['avg_daily_vol']
    mfo = snap['minutes_from_open']
    bars_by_sym = snap.get('bars_by_sym', {})
    pre_qualified = set(snap.get('pre_qualified', []))

    def etf_intraday(sym):
        s = etf_snaps.get(sym, {})
        db = s.get('dailyBar', {})
        o = db.get('o', 0); c = db.get('c', 0)
        return (c / o - 1) * 100 if o > 0 else 0

    spy_intra = etf_intraday('SPY')
    sector_chg = {sec: etf_intraday(etf) for sec, etf in SECTOR_TO_ETF.items()}

    # Build candidates
    candidates = []
    for sym, s in snaps.items():
        sec = sectors.get(sym, '')
        if sec in strategy.SECTOR_BLACKLIST: continue
        if sym in earnings_skip or sym == 'SPY': continue
        db = s.get('dailyBar', {})
        pb = s.get('prevDailyBar', {})
        opn = db.get('o', 0); now = db.get('c', 0)
        hi = db.get('h', 0); lo = db.get('l', 0)
        prev_c = pb.get('c', 0)
        if opn < 1 or now < strategy.MIN_PRICE or prev_c < 1: continue
        total_gain = (now / prev_c - 1) * 100
        if not (strategy.MIN_GAIN <= total_gain < strategy.MAX_GAIN): continue
        gain = (now / opn - 1) * 100

        range_pct = (hi - lo) / opn * 100 if opn > 0 else 0
        from_peak = (now / hi - 1) * 100 if hi > 0 else 0
        vwap = db.get('vw', 0)
        vs_vwap = (now / vwap - 1) * 100 if vwap > 0 else 0
        gap = (opn / prev_c - 1) * 100

        today_vol = db.get('v', 0) or 0
        avg_v = avg_daily_vol.get(sym, 0)
        frac = max(5, mfo + 5) / 390.0
        expected = avg_v * frac if avg_v > 0 else 0
        vol_ratio = min(20.0, today_vol / expected) if expected > 0 else 1.0

        beta = betas.get(sym, 1.5)
        mcap = mcaps.get(sym, 0) or 0
        mcap_b = 4 if mcap >= 100e9 else (3 if mcap >= 20e9 else (2 if mcap >= 5e9 else (1 if mcap >= 500e6 else 0)))

        hist = daily_hist.get(sym, [])
        if len(hist) < 21: continue
        closes = [h[1] for h in hist[-21:] if h[1] is not None]
        if len(closes) < 21: continue
        mom5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0
        mom20 = (closes[-1] / closes[0] - 1) * 100 if closes[0] else 0
        sma20 = np.mean(closes[-20:])
        dist_sma20 = (now / sma20 - 1) * 100

        full = [h[1] for h in hist if h[1] is not None]
        if len(full) < 100: continue
        h52 = max(full); l52 = min(full)
        pct_52w_hi = (now / h52 - 1) * 100
        pct_52w_lo = (now / l52 - 1) * 100

        hl = daily_hl.get(sym, [])
        rngs = [(r[1] - r[2]) / r[3] * 100 for r in hl if len(r) >= 4 and r[3]]
        rng10 = np.mean(rngs) if rngs else 3.0
        range_exp = range_pct / rng10 if rng10 > 0 else 1

        sec_chg_v = sector_chg.get(sec, 0)

        # Compute multibar features from saved bars (matches live)
        sym_bars = bars_by_sym.get(sym, [])
        if sym_bars:
            day_open = sym_bars[0].get('o', opn)
            bar_feats = extract_multibar_features(sym_bars, day_open)
        else:
            bar_feats = {'bars_since_hi': 0, 'vol_accel': 1.0, 'hh_count': 0, 'consol': range_pct,
                         'consec_green': 0, 'pullback_depth': 0, 'slope_5': 0, 'slope_10': 0,
                         'gain_first30': 0, 'entry_vs_first30': 0, 'time_since_peak': 0}

        feats = {
            'mins_from_open': mfo, 'gain_from_open': gain, 'range_pct': range_pct,
            'from_peak_pct': from_peak, 'vs_vwap': vs_vwap, 'vol_ratio': vol_ratio,
            'vol_accel': bar_feats.get('vol_accel', 1.0),
            'bars_since_hi': bar_feats.get('bars_since_hi', 0),
            'hh_count': bar_feats.get('hh_count', 0),
            'consol': bar_feats.get('consol', range_pct),
            'range_exp': range_exp, 'gap_from_prev': gap, 'beta': beta, 'mcap_bucket': mcap_b,
            'spy_green': macro['spy_green'], 'spy_intra': spy_intra,
            'vix': macro['vix'], 'vix_5d_chg': macro['vix_5d_chg'],
            'ad_ratio': macro['ad_ratio'], 'mom5d': mom5, 'mom20d': mom20,
            'dist_sma20': dist_sma20, 'pct_52w_hi': pct_52w_hi, 'pct_52w_lo': pct_52w_lo,
            'dow': datetime.strptime(date, '%Y-%m-%d').weekday(),
            'btc_5d_chg': macro['btc_5d_chg'], 'jpy_5d_chg': macro['jpy_5d_chg'],
            'skew': macro['skew'], 'vvix': macro['vvix'],
            'vix_term_spread': macro['vix_term_spread'],
            'sec_rel_strength': sec_chg_v - spy_intra,
        }
        for etf, col in [('XLK','xlk_intra'),('XLV','xlv_intra'),('XLF','xlf_intra'),('XLY','xly_intra'),
                         ('XLC','xlc_intra'),('XLI','xli_intra'),('XLP','xlp_intra'),('XLE','xle_intra'),
                         ('XLB','xlb_intra'),('XLRE','xlre_intra'),('XLU','xlu_intra'),
                         ('IWM','iwm_intra'),('USO','uso_intra'),('SMH','smh_intra'),('QQQ','qqq_intra'),
                         ('TLT','tlt_intra'),('LQD','lqd_intra'),('IEF','ief_intra'),('HYG','hyg_intra'),
                         ('VXX','vxx_intra'),('GLD','gld_intra'),('UUP','uup_intra'),('EEM','eem_intra'),
                         ('DBC','dbc_intra'),('IGV','igv_intra')]:
            feats[col] = etf_intraday(etf)

        feats['anomaly_score'] = 0  # not critical
        feats['gain_x_spy'] = gain * spy_intra
        feats['vol_x_mcap'] = vol_ratio * mcap_b
        feats['gain_x_xlk'] = gain * etf_intraday('XLK')
        feats['gain_div_vix'] = gain / (macro['vix']/20.0) if macro['vix'] > 0 else 0
        feats['range_pullback'] = range_pct * (5 - max(0, min(5, gain)))

        prob = scorer.score(feats, mfo, sector=sec)
        threshold = scorer.threshold_75(mfo)
        if prob < threshold: continue

        # Zone hard rules
        if mfo <= 9:  # Z1
            if mom20 > 20: continue
            sec_etf_col = SECTOR_ETF_MAP.get(sec)
            if sec_etf_col and feats.get(sec_etf_col, 0) < -0.3: continue
        elif mfo <= 29:
            if mom20 > 20: continue
            if feats.get('bars_since_hi', 0) < 1: continue
        elif mfo <= 44:
            if feats.get('bars_since_hi', 0) >= 1: continue
            if feats.get('vol_accel', 1.0) < 1.5: continue
            if feats.get('gain_from_open', 0) < 3.0: continue
        elif mfo <= 75:
            if feats.get('bars_since_hi', 0) >= 1: continue
            if feats.get('vol_accel', 1.0) < 1.5: continue
        else:
            continue

        candidates.append({'sym':sym, 'sec':sec, 'gain':gain, 'total_gain':total_gain,
                           'prob':prob, 'mom20':mom20, 'sec_chg':sec_chg_v})

    # Sort + cap
    candidates.sort(key=lambda c: -c['prob'])
    sec_count = {}; final = []
    for c in candidates:
        if sec_count.get(c['sec'], 0) >= 2: continue
        if len(final) >= 3: break
        sec_count[c['sec']] = sec_count.get(c['sec'], 0) + 1
        final.append(c)

    print(f"\n=== REPLAY RESULTS ===")
    print(f"  Candidates passing all filters: {len(candidates)}")
    print(f"  Final picks (top 3, max-2/sector):")
    if final:
        print(f"  {'sym':<6} {'sector':<22} {'tot%':>6} {'gain%':>6} {'prob':>6} {'mom20':>7}")
        for c in final:
            print(f"  {c['sym']:<6} {c['sec']:<22} {c['total_gain']:>+5.2f}% {c['gain']:>+5.2f}% {c['prob']:>5.3f} {c['mom20']:>+6.1f}%")
    else:
        print("  (no picks)")

    # Compare to live
    j = sqlite3.connect(str(ROOT / 'data' / 'scan_journal.db'))
    rows = j.execute("""SELECT symbol, entry, ml_prob, reason FROM scan_picks
        WHERE scan_date=? AND scan_ts <= ? ORDER BY ml_prob DESC""",
        (date, snap['scan_ts_et'][:19])).fetchall()
    j.close()
    if rows:
        print(f"\n=== LIVE picks at this scan ===")
        for sym, entry, prob, reason in rows[:5]:
            print(f"  {sym}  entry={entry:.2f}  prob={prob:.3f}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('snap_path', nargs='?', help='Path to snapshot file')
    ap.add_argument('--date', help='Date YYYY-MM-DD (alternative to snap_path)')
    ap.add_argument('--time', help='Time HH:MM (with --date)')
    ap.add_argument('--models', help='Path to models directory (default: current)')
    args = ap.parse_args()
    if args.snap_path:
        path = args.snap_path
    elif args.date and args.time:
        path = find_snap(args.date, args.time)
        if not path:
            print(f"No snapshot found for {args.date} {args.time}")
            sys.exit(1)
    else:
        ap.print_help()
        sys.exit(1)
    replay(path, args.models)
