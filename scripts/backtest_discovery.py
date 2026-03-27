#!/usr/bin/env python3
"""
Discovery Engine Backtest
=========================
Simulates the Discovery Engine scan on each trading day from 2026-02-05 to 2026-03-12
and evaluates 5-day forward outcomes for each picked stock.

Pipeline per day:
  1. Slice pre-downloaded OHLCV data at scan_date
  2. Compute technical features (beta, ATR, RSI, momentum, etc.)
  3. Apply L1 hard filters via DiscoveryScorer.passes_layer1()
  4. Load macro + breadth from DB → compute stress_score / adaptive_min_score
  5. Score with DiscoveryScorer.compute_layer2_score()
  6. Keep picks where score >= adaptive_min_score
  7. Compute outcome_5d, max_gain_5d, max_dd_5d

Run: python3 scripts/backtest_discovery.py [--no-cache] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""

import sys
import os
import math
import pickle
import argparse
import sqlite3
import warnings
from datetime import datetime, timedelta, date
from collections import defaultdict

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

# --- Path setup (run from project root or scripts/) ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..'))
sys.path.insert(0, _PROJECT_ROOT)

from src.discovery.scorer import DiscoveryScorer
from src.database.repositories.universe_repository import UniverseRepository

DB_PATH = os.path.join(_PROJECT_ROOT, 'data', 'trade_history.db')
CACHE_PATH = os.path.join(_PROJECT_ROOT, 'data', 'discovery_backtest_cache.pkl')


# ══════════════════════════════════════════════════════════
# 1. Universe
# ══════════════════════════════════════════════════════════

def load_universe() -> dict:
    """Load stock universe. Returns {symbol: {'sector': ..., ...}}."""
    stocks = UniverseRepository().get_all()
    print(f"[Universe] {len(stocks)} stocks loaded from DB")
    return stocks


def get_universe_betas() -> dict:
    """Load per-stock beta from stock_fundamentals table (pre-collected)."""
    conn = None  # via get_session()
    rows = conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


# ══════════════════════════════════════════════════════════
# 2. OHLCV Download (batch, cached)
# ══════════════════════════════════════════════════════════

def download_all_data(symbols: list, start: str, end: str, use_cache: bool) -> pd.DataFrame:
    """
    Download OHLCV for all symbols at once, cached to pickle.
    Returns MultiLevel DataFrame: columns = (field, symbol).
    """
    if use_cache and os.path.exists(CACHE_PATH):
        print(f"[Cache] Loading from {CACHE_PATH} ...")
        with open(CACHE_PATH, 'rb') as f:
            data = pickle.load(f)
        print(f"[Cache] Loaded {data.shape if hasattr(data, 'shape') else '?'} rows")
        return data

    print(f"[Download] Fetching {len(symbols)} symbols from {start} to {end}")
    print("[Download] This may take 10-20 minutes. Splitting into batches of 100...")

    all_dfs = []
    batch_size = 100
    total_batches = (len(symbols) + batch_size - 1) // batch_size

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        pct = batch_num / total_batches * 100
        print(f"  Batch {batch_num}/{total_batches} ({pct:.0f}%) — {batch[0]}..{batch[-1]}", flush=True)

        try:
            df = yf.download(
                ' '.join(batch),
                start=start,
                end=end,
                interval='1d',
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if not df.empty:
                # Single-symbol download → promote to multi-level for uniformity
                if len(batch) == 1:
                    sym = batch[0]
                    df.columns = pd.MultiIndex.from_tuples(
                        [(col, sym) for col in df.columns]
                    )
                all_dfs.append(df)
        except Exception as e:
            print(f"  [WARN] Batch {batch_num} failed: {e}")
            continue

    if not all_dfs:
        raise RuntimeError("No data downloaded — check network / yfinance version")

    print("[Download] Concatenating all batches ...", flush=True)
    data = pd.concat(all_dfs, axis=1)
    # Deduplicate columns (some symbols may appear in overlapping batches)
    data = data.loc[:, ~data.columns.duplicated()]
    data.index = pd.to_datetime(data.index).tz_localize(None)

    print(f"[Download] Done — {data.shape[0]} rows, {len(data.columns.get_level_values(1).unique())} symbols")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'wb') as f:
        pickle.dump(data, f)
    print(f"[Cache] Saved to {CACHE_PATH}")

    return data


# ══════════════════════════════════════════════════════════
# 3. Technical Feature Computation (per stock, per scan_date)
# ══════════════════════════════════════════════════════════

def _compute_rsi(close_arr: np.ndarray, period: int = 14) -> float:
    """Standard 14-day RSI using simple moving averages."""
    if len(close_arr) < period + 1:
        return 50.0
    deltas = np.diff(close_arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[-period:]))
    avg_loss = float(np.mean(losses[-period:]))
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_atr(high_arr: np.ndarray, low_arr: np.ndarray, close_arr: np.ndarray, period: int = 14) -> float:
    """14-day Average True Range as % of last close."""
    tr_list = []
    for i in range(1, len(close_arr)):
        h = high_arr[i]
        l = low_arr[i]
        pc = close_arr[i - 1]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(tr_list) < period:
        return float(np.mean(tr_list)) / close_arr[-1] * 100 if tr_list else 2.0
    return float(np.mean(tr_list[-period:])) / close_arr[-1] * 100


def _compute_beta(stock_rets: np.ndarray, spy_rets: np.ndarray, period: int = 60) -> float:
    """60-day rolling beta: corr * (std_stock / std_spy)."""
    if len(stock_rets) < period or len(spy_rets) < period:
        return 0.5
    s = stock_rets[-period:]
    m = spy_rets[-period:]
    min_len = min(len(s), len(m))
    s = s[-min_len:]
    m = m[-min_len:]
    if np.std(m) == 0:
        return 0.5
    corr = float(np.corrcoef(s, m)[0, 1])
    if np.isnan(corr):
        return 0.5
    return corr * (float(np.std(s)) / float(np.std(m)))


def compute_features_for_stock(
    sym: str,
    close_hist: np.ndarray,
    high_hist: np.ndarray,
    low_hist: np.ndarray,
    vol_hist: np.ndarray,
    spy_rets: np.ndarray,
    fund_beta: float,
    sector: str,
    market_cap: float,
) -> dict | None:
    """
    Compute all technical features for one stock on one scan_date.
    close_hist etc. are arrays of all available data UP TO (inclusive of) scan_date.
    Returns dict or None if insufficient data.
    """
    if len(close_hist) < 22:  # need at least 22 bars for 20d momentum + volume
        return None

    close = close_hist
    high = high_hist
    low = low_hist
    volume = vol_hist
    current = float(close[-1])

    if current <= 0 or np.isnan(current):
        return None

    # ATR%
    atr_pct = _compute_atr(high, low, close)

    # RSI
    rsi = _compute_rsi(close)

    # Momentum
    momentum_5d = float((close[-1] / close[-6] - 1) * 100) if len(close) >= 6 else 0.0
    momentum_20d = float((close[-1] / close[-21] - 1) * 100) if len(close) >= 21 else 0.0

    # Distance from 52-week high (negative convention: 0=at high, -10=10% below)
    look_back = min(len(high), 252)
    high_52w = float(np.max(high[-look_back:]))
    distance_from_high = (current / high_52w - 1) * 100 if high_52w > 0 else 0.0

    # Volume ratio (today vs 20d avg)
    if len(volume) >= 21:
        avg_vol_20 = float(np.mean(volume[-21:-1]))
        volume_ratio = float(volume[-1]) / avg_vol_20 if avg_vol_20 > 0 else 1.0
    else:
        volume_ratio = 1.0

    # Beta (prefer fundamentals DB; fall back to rolling computation)
    if fund_beta is not None and not np.isnan(fund_beta):
        beta = float(fund_beta)
    else:
        stock_rets = np.diff(close) / close[:-1]
        beta = _compute_beta(stock_rets, spy_rets)

    # Market cap log
    mcap_log = math.log10(market_cap + 1) if market_cap and market_cap > 0 else 9.0

    return {
        'symbol': sym,
        'close': current,
        'atr_pct': atr_pct,
        'rsi': rsi,
        'momentum_5d': momentum_5d,
        'momentum_20d': momentum_20d,
        'distance_from_high': distance_from_high,
        'volume_ratio': volume_ratio,
        'beta': beta,
        'sector': sector,
        'market_cap': market_cap,
        'mcap_log': mcap_log,
    }


# ══════════════════════════════════════════════════════════
# 4. Macro / Breadth Data from DB
# ══════════════════════════════════════════════════════════

def load_all_macro() -> tuple[dict, dict]:
    """
    Load all macro_snapshots and market_breadth rows into dicts keyed by date string.
    Returns (macro_by_date, breadth_by_date).
    """
    conn = None  # via get_session()
    conn.row_factory = dict

    macro_rows = conn.execute("SELECT * FROM macro_snapshots ORDER BY date").fetchall()
    macro_by_date = {r['date']: dict(r) for r in macro_rows}

    breadth_rows = conn.execute("SELECT * FROM market_breadth ORDER BY date").fetchall()
    breadth_by_date = {r['date']: dict(r) for r in breadth_rows}

    conn.close()
    print(f"[Macro] Loaded {len(macro_by_date)} macro rows, {len(breadth_by_date)} breadth rows")
    return macro_by_date, breadth_by_date


def get_macro_for_date(scan_date_str: str, macro_by_date: dict, breadth_by_date: dict,
                        sorted_macro_dates: list, sorted_breadth_dates: list) -> dict:
    """
    Return the macro snapshot for the given scan_date.
    If exact date not in DB, use the most-recent prior date.
    Computes: vix_term_structure, highs_lows_ratio, vix_delta_5d, breadth_delta_5d, dxy_delta_5d, stress_score.
    """
    # Find most-recent macro date <= scan_date
    macro_row = None
    for d in reversed(sorted_macro_dates):
        if d <= scan_date_str:
            macro_row = macro_by_date[d]
            break

    breadth_row = None
    for d in reversed(sorted_breadth_dates):
        if d <= scan_date_str:
            breadth_row = breadth_by_date[d]
            break

    if macro_row is None:
        return {}

    result = dict(macro_row)

    # Merge breadth
    if breadth_row:
        result.update({k: v for k, v in breadth_row.items() if k not in result or result[k] is None})

    # Derived: VIX term structure
    vix = result.get('vix_close') or 20.0
    vix3m = result.get('vix3m_close') or 20.0
    result['vix_term_structure'] = vix3m / vix if vix > 0 else 1.0

    # Highs/Lows ratio
    highs = result.get('new_52w_highs') or 100
    lows = result.get('new_52w_lows') or 100
    result['highs_lows_ratio'] = highs / max(lows, 1)

    # 5-day deltas — find the row ~5 trading days ago
    idx_macro = sorted_macro_dates.index(macro_row['date']) if macro_row['date'] in sorted_macro_dates else -1
    macro_5d = macro_by_date.get(sorted_macro_dates[idx_macro - 5]) if idx_macro >= 5 else None

    idx_breadth = sorted_breadth_dates.index(breadth_row['date']) if (breadth_row and breadth_row['date'] in sorted_breadth_dates) else -1
    breadth_5d = breadth_by_date.get(sorted_breadth_dates[idx_breadth - 5]) if idx_breadth >= 5 else None

    # VIX delta 5d
    if macro_5d and macro_5d.get('vix_close'):
        result['vix_delta_5d'] = round(float(vix) - float(macro_5d['vix_close']), 2)
    else:
        result['vix_delta_5d'] = 0.0

    # DXY delta 5d
    dxy = result.get('dxy_close')
    if macro_5d and macro_5d.get('dxy_close') and dxy:
        result['dxy_delta_5d'] = round(float(dxy) - float(macro_5d['dxy_close']), 2)
    else:
        result['dxy_delta_5d'] = 0.0

    # Breadth delta 5d
    breadth_now = result.get('pct_above_20d_ma')
    if breadth_5d and breadth_5d.get('pct_above_20d_ma') and breadth_now:
        result['breadth_delta_5d'] = round(float(breadth_now) - float(breadth_5d['pct_above_20d_ma']), 2)
    else:
        result['breadth_delta_5d'] = 0.0

    # Stress score (simplified version matching engine._load_macro logic)
    # Uses the spec formula from the backtest brief:
    #   stress += min(25, (vix-20)*1.5) if vix>20
    #   stress += 15 if vix > vix3m (backwardation)
    #   stress += min(25, (40-breadth)*1.0) if breadth<40
    breadth = breadth_now or 50.0
    stress = 0.0
    if vix > 20:
        stress += min(25.0, (vix - 20) * 1.5)
    if vix > vix3m:
        stress += 15.0
    if breadth < 40:
        stress += min(25.0, (40.0 - breadth) * 1.0)
    stress = min(100.0, stress)
    result['stress_score'] = round(stress, 1)

    return result


# ══════════════════════════════════════════════════════════
# 5. Outcome Computation
# ══════════════════════════════════════════════════════════

def compute_outcome(sym: str, scan_date_idx: int, close_data: pd.Series,
                    scan_price: float, window: int = 5) -> dict:
    """
    Compute forward outcomes from scan_date_idx + 1 to scan_date_idx + window.
    All percentages relative to scan_price (close on scan_date).
    """
    future_closes = close_data.iloc[scan_date_idx + 1: scan_date_idx + 1 + window].dropna()
    if future_closes.empty or scan_price <= 0:
        return {'outcome_5d': None, 'max_gain_5d': None, 'max_dd_5d': None}

    outcome_5d = (float(future_closes.iloc[-1]) / scan_price - 1) * 100 if len(future_closes) >= 1 else None

    daily_rets = (future_closes.values / scan_price - 1) * 100
    max_gain_5d = float(np.max(daily_rets)) if len(daily_rets) > 0 else None
    max_dd_5d = float(np.min(daily_rets)) if len(daily_rets) > 0 else None

    return {
        'outcome_5d': round(outcome_5d, 3) if outcome_5d is not None else None,
        'max_gain_5d': round(max_gain_5d, 3) if max_gain_5d is not None else None,
        'max_dd_5d': round(max_dd_5d, 3) if max_dd_5d is not None else None,
    }


# ══════════════════════════════════════════════════════════
# 6. Main Backtest Loop
# ══════════════════════════════════════════════════════════

def run_backtest(start_date: str, end_date: str, use_cache: bool):
    print(f"\n{'='*60}")
    print(f"  Discovery Backtest: {start_date} to {end_date}")
    print(f"{'='*60}\n")

    # --- Load universe ---
    stocks = load_universe()
    all_symbols = list(stocks.keys())
    fund_betas = get_universe_betas()

    # --- Download all OHLCV data once ---
    # We need data 1 year before start (for 52w high / beta) and +10 days after end (for outcomes)
    dl_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=380)).strftime('%Y-%m-%d')
    dl_end = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=15)).strftime('%Y-%m-%d')

    # Also download SPY for beta computation
    all_dl_symbols = list(dict.fromkeys(['SPY'] + all_symbols))  # SPY first, deduplicated

    raw_data = download_all_data(all_dl_symbols, dl_start, dl_end, use_cache)

    # Extract Close/High/Low/Volume for all symbols
    print("\n[Prep] Extracting price arrays ...", flush=True)
    close_df = raw_data['Close'] if 'Close' in raw_data.columns.get_level_values(0) else raw_data.xs('Close', axis=1, level=0)
    high_df  = raw_data['High']  if 'High'  in raw_data.columns.get_level_values(0) else raw_data.xs('High',  axis=1, level=0)
    low_df   = raw_data['Low']   if 'Low'   in raw_data.columns.get_level_values(0) else raw_data.xs('Low',   axis=1, level=0)
    vol_df   = raw_data['Volume'] if 'Volume' in raw_data.columns.get_level_values(0) else raw_data.xs('Volume', axis=1, level=0)

    # SPY returns for beta computation
    spy_close = close_df['SPY'].dropna() if 'SPY' in close_df.columns else pd.Series(dtype=float)
    spy_rets_all = spy_close.pct_change().dropna().values

    # --- Load macro data ---
    macro_by_date, breadth_by_date = load_all_macro()
    sorted_macro_dates = sorted(macro_by_date.keys())
    sorted_breadth_dates = sorted(breadth_by_date.keys())

    # --- Initialize scorer ---
    scorer = DiscoveryScorer()
    print("[Scorer] DiscoveryScorer initialized\n")

    # --- Determine scan dates (trading days in range that have macro data) ---
    # Use macro_snapshots as proxy for "was a trading day with data"
    scan_dates = [d for d in sorted_macro_dates if start_date <= d <= end_date]
    print(f"[Backtest] {len(scan_dates)} scan dates with macro data: {scan_dates[0]} .. {scan_dates[-1]}\n")

    # ══ Per-day loop ══
    all_picks = []  # list of dicts, one per pick
    day_summaries = []

    for scan_date_str in scan_dates:
        scan_dt = datetime.strptime(scan_date_str, '%Y-%m-%d')

        # Slice price data up to scan_date (inclusive)
        mask = close_df.index <= scan_dt
        close_to_date = close_df.loc[mask]
        high_to_date  = high_df.loc[mask]
        low_to_date   = low_df.loc[mask]
        vol_to_date   = vol_df.loc[mask]

        if close_to_date.empty:
            continue

        # SPY returns up to scan_date for rolling beta
        spy_mask = spy_close.index <= scan_dt
        spy_rets_to_date = spy_close.loc[spy_mask].pct_change().dropna().values

        # Load macro features
        macro = get_macro_for_date(scan_date_str, macro_by_date, breadth_by_date,
                                    sorted_macro_dates, sorted_breadth_dates)
        if not macro:
            print(f"  [{scan_date_str}] SKIP — no macro data")
            continue

        vix = macro.get('vix_close', 20.0) or 20.0
        vix3m = macro.get('vix3m_close', 20.0) or 20.0
        breadth = macro.get('pct_above_20d_ma', 50.0) or 50.0
        stress = macro.get('stress_score', 0.0) or 0.0

        # Adaptive min_score (from engine logic)
        base_min_score = 35.0
        stress_penalty = max(0.0, stress - 20.0) * 0.3
        adaptive_min_score = min(80.0, base_min_score + stress_penalty)

        # Find scan_date index in full close_df (for outcome computation)
        scan_date_idx_in_full = None
        full_dates = close_df.index
        for ii, idx_dt in enumerate(full_dates):
            if idx_dt.date() == scan_dt.date():
                scan_date_idx_in_full = ii
                break

        if scan_date_idx_in_full is None:
            print(f"  [{scan_date_str}] SKIP — scan_date not found in price data")
            continue

        # Iterate over all symbols
        candidates_l1 = 0
        day_picks = []

        available_syms = [s for s in all_symbols if s in close_to_date.columns]

        for sym in available_syms:
            try:
                close_arr = close_to_date[sym].dropna().values
                high_arr  = high_to_date[sym].dropna().values
                low_arr   = low_to_date[sym].dropna().values
                vol_arr   = vol_to_date[sym].dropna().values

                # Align lengths (dropna may produce different lengths for OHLCV)
                min_len = min(len(close_arr), len(high_arr), len(low_arr), len(vol_arr))
                if min_len < 22:
                    continue
                close_arr = close_arr[-min_len:]
                high_arr  = high_arr[-min_len:]
                low_arr   = low_arr[-min_len:]
                vol_arr   = vol_arr[-min_len:]

                stock_info = stocks.get(sym, {})
                sector = stock_info.get('sector', '') or ''

                # Get market_cap from fundamentals if available
                fund_beta_val = fund_betas.get(sym)
                market_cap = 0.0  # not in universe_stocks; fundamentals has it but we skip for speed

                features = compute_features_for_stock(
                    sym=sym,
                    close_hist=close_arr,
                    high_hist=high_arr,
                    low_hist=low_arr,
                    vol_hist=vol_arr,
                    spy_rets=spy_rets_to_date,
                    fund_beta=fund_beta_val,
                    sector=sector,
                    market_cap=market_cap,
                )
                if features is None:
                    continue

                # L1 filter
                passed, reject_reason = scorer.passes_layer1(features)
                if not passed:
                    continue

                candidates_l1 += 1

                # Merge macro features
                features.update(macro)

                # L2 score
                score = scorer.compute_layer2_score(features)
                if score < adaptive_min_score:
                    continue

                # Compute forward outcome
                sym_close_full = close_df[sym] if sym in close_df.columns else pd.Series(dtype=float)
                outcome = compute_outcome(sym, scan_date_idx_in_full, sym_close_full,
                                          features['close'], window=5)

                pick = {
                    'scan_date': scan_date_str,
                    'symbol': sym,
                    'score': round(score, 1),
                    'sector': sector,
                    'close': round(features['close'], 2),
                    'beta': round(features['beta'], 2),
                    'atr_pct': round(features['atr_pct'], 2),
                    'distance_from_high': round(features['distance_from_high'], 1),
                    'rsi': round(features['rsi'], 1),
                    'momentum_5d': round(features['momentum_5d'], 1),
                    'momentum_20d': round(features['momentum_20d'], 1),
                    'volume_ratio': round(features['volume_ratio'], 2),
                    'vix': round(vix, 1),
                    'stress_score': round(stress, 1),
                    'adaptive_min_score': round(adaptive_min_score, 1),
                    'breadth': round(breadth, 1),
                    **outcome,
                }
                day_picks.append(pick)

            except Exception as e:
                continue  # skip bad symbols silently

        # Sort day picks by score descending
        day_picks.sort(key=lambda x: x['score'], reverse=True)
        all_picks.extend(day_picks)

        # Day summary
        n = len(day_picks)
        has_outcome = [p for p in day_picks if p['outcome_5d'] is not None]
        wins = [p for p in has_outcome if p['outcome_5d'] > 0]
        wr = len(wins) / len(has_outcome) * 100 if has_outcome else float('nan')
        avg = float(np.mean([p['outcome_5d'] for p in has_outcome])) if has_outcome else float('nan')
        syms_str = ', '.join([p['symbol'] for p in day_picks[:5]])
        if n > 5:
            syms_str += f', +{n-5} more'

        wr_str = f"WR={wr:.0f}%" if has_outcome else "WR=n/a"
        avg_str = f"avg={avg:+.1f}%" if has_outcome else "avg=n/a"
        print(f"  {scan_date_str}: picks={n:2d}  L1={candidates_l1:3d}  {wr_str:8s} {avg_str:10s}  VIX={vix:.1f} stress={stress:.0f} min_score={adaptive_min_score:.0f}  [{syms_str}]")

        day_summaries.append({
            'date': scan_date_str,
            'picks': n,
            'l1_pass': candidates_l1,
            'has_outcome': len(has_outcome),
            'wins': len(wins),
            'wr': wr,
            'avg_outcome': avg,
        })

    # ══════════════════════════════════════════════════════
    # 7. Summary Report
    # ══════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")

    if not all_picks:
        print("  No picks generated in this period.")
        return

    total_picks = len(all_picks)
    has_out = [p for p in all_picks if p['outcome_5d'] is not None]
    wins_total = [p for p in has_out if p['outcome_5d'] > 0]
    avg_picks_per_day = total_picks / len(scan_dates) if scan_dates else 0

    wr_overall = len(wins_total) / len(has_out) * 100 if has_out else 0
    avg_5d = float(np.mean([p['outcome_5d'] for p in has_out])) if has_out else 0
    avg_gain = float(np.mean([p['max_gain_5d'] for p in has_out if p['max_gain_5d'] is not None])) if has_out else 0
    avg_dd   = float(np.mean([p['max_dd_5d']   for p in has_out if p['max_dd_5d']   is not None])) if has_out else 0

    print(f"\n  Total picks: {total_picks} (avg {avg_picks_per_day:.1f}/day)")
    print(f"  With 5d outcome: {len(has_out)}/{total_picks}")
    print(f"  Win Rate: {wr_overall:.1f}% ({len(wins_total)}/{len(has_out)})")
    print(f"  Avg outcome_5d:  {avg_5d:+.2f}%")
    print(f"  Avg max_gain_5d: {avg_gain:+.2f}%")
    print(f"  Avg max_dd_5d:   {avg_dd:+.2f}%")

    # Score buckets
    print("\n  Score Buckets (outcome_5d):")
    buckets = [
        ('[35-50)', 35, 50),
        ('[50-60)', 50, 60),
        ('[60-70)', 60, 70),
        ('[70-80)', 70, 80),
        ('[80+)  ', 80, 101),
    ]
    for label, lo, hi in buckets:
        bucket_picks = [p for p in has_out if lo <= p['score'] < hi]
        if not bucket_picks:
            continue
        bwins = [p for p in bucket_picks if p['outcome_5d'] > 0]
        bwr = len(bwins) / len(bucket_picks) * 100
        bavg = float(np.mean([p['outcome_5d'] for p in bucket_picks]))
        print(f"    {label}: n={len(bucket_picks):3d}  WR={bwr:5.1f}%  avg={bavg:+.2f}%")

    # Sector distribution
    print("\n  Sector Distribution (outcome_5d):")
    sector_groups = defaultdict(list)
    for p in has_out:
        sector_groups[p['sector'] or 'Unknown'].append(p)
    for sec in sorted(sector_groups.keys(), key=lambda s: -len(sector_groups[s])):
        sg = sector_groups[sec]
        sw = [p for p in sg if p['outcome_5d'] > 0]
        swr = len(sw) / len(sg) * 100
        savg = float(np.mean([p['outcome_5d'] for p in sg]))
        print(f"    {sec:<30s}: n={len(sg):3d}  WR={swr:5.1f}%  avg={savg:+.2f}%")

    # Stress analysis
    print("\n  Stress Zone Analysis (outcome_5d):")
    stress_buckets = [
        ('Low stress (<20)',    0,  20),
        ('Mild stress (20-40)', 20, 40),
        ('High stress (40-60)', 40, 60),
        ('Max stress (60+)',    60, 101),
    ]
    for label, lo, hi in stress_buckets:
        sb = [p for p in has_out if lo <= p['stress_score'] < hi]
        if not sb:
            continue
        sw = [p for p in sb if p['outcome_5d'] > 0]
        swr = len(sw) / len(sb) * 100
        savg = float(np.mean([p['outcome_5d'] for p in sb]))
        print(f"    {label:<28s}: n={len(sb):3d}  WR={swr:5.1f}%  avg={savg:+.2f}%")

    # Top 10 picks by score
    print("\n  Top 10 Picks by Score:")
    print(f"  {'Date':<12} {'Symbol':<8} {'Score':>6} {'Sector':<25} {'5d%':>7} {'MaxGn':>7} {'MaxDD':>7} {'Beta':>5} {'ATR%':>5} {'Dist52w':>8}")
    top10 = sorted(has_out, key=lambda p: p['score'], reverse=True)[:10]
    for p in top10:
        print(
            f"  {p['scan_date']:<12} {p['symbol']:<8} {p['score']:>6.1f} "
            f"{(p['sector'] or 'Unknown'):<25} "
            f"{p['outcome_5d']:>+7.2f}% {p['max_gain_5d']:>+7.2f}% {p['max_dd_5d']:>+7.2f}% "
            f"{p['beta']:>5.2f} {p['atr_pct']:>5.2f} {p['distance_from_high']:>+8.1f}%"
        )

    print(f"\n{'='*60}\n")


# ══════════════════════════════════════════════════════════
# CLI Entry Point
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Discovery Engine Backtest')
    parser.add_argument('--start', default='2026-02-05', help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end',   default='2026-03-12', help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--no-cache', action='store_true', help='Re-download data even if cache exists')
    args = parser.parse_args()

    # Change to project root so relative imports & DB paths work
    os.chdir(_PROJECT_ROOT)

    run_backtest(
        start_date=args.start,
        end_date=args.end,
        use_cache=not args.no_cache,
    )


if __name__ == '__main__':
    main()
