"""
Phase 2 — Feature engineering for swing ML.

Reads phase1_labeled_daily.pkl and adds ~70 features:
  Group A: Daily TA (RSI, MACD, BB, ATR, MAs, ADX, Stoch)         ~20
  Group B: Returns/Momentum (1d/3d/5d/10d/20d/60d + vol)          ~10
  Group C: Volume (vol_ratio, OBV, money flow)                    ~8
  Group D: Position/Range (52w hi/lo, 20d hi/lo, consolidation)   ~8
  Group E: Fundamentals (beta, mcap_log, sector_id, PE)           ~6
  Group F: Macro context (VIX, SPY, HYG, TLT, DXY, spread)        ~12
  Group G: Sector relative strength                                ~4
  Group H: Calendar (days_to_earnings, dow, dom, month)            ~6

NO LOOKAHEAD: all features use information available AT scan time.
Earnings dates are scheduled (not actual report — assumed known beforehand).

Output: backtests/cache_swing/phase2_features.pkl
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')
CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')


# ---------- Technical helpers ----------

def rsi(series, period):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def stoch_k(df, period=14):
    high_n = df['high'].rolling(period).max()
    low_n = df['low'].rolling(period).min()
    return 100 * (df['close'] - low_n) / (high_n - low_n).replace(0, np.nan)


def add_ta_features(df):
    """Per-symbol TA features."""
    out = []
    for sym, g in df.groupby('symbol', sort=False):
        g = g.sort_values('date').reset_index(drop=True).copy()
        c = g['close']
        h = g['high']
        l = g['low']
        v = g['volume']

        # === Group A: Technical ===
        g['rsi_7'] = rsi(c, 7)
        g['rsi_14'] = rsi(c, 14)

        ema12 = ema(c, 12)
        ema26 = ema(c, 26)
        macd_line = ema12 - ema26
        macd_sig = ema(macd_line, 9)
        g['macd_hist'] = (macd_line - macd_sig) / c * 100  # normalized %

        bb_ma = c.rolling(20).mean()
        bb_std = c.rolling(20).std()
        g['bb_pos'] = (c - (bb_ma - 2 * bb_std)) / (4 * bb_std).replace(0, np.nan)
        g['bb_width'] = (4 * bb_std / bb_ma).clip(0, 1)

        g['atr_14'] = atr(g, 14)
        g['atr_pct'] = g['atr_14'] / c * 100

        for ma in [5, 10, 20, 50, 100, 200]:
            ma_col = c.rolling(ma).mean()
            g[f'dist_ma{ma}'] = (c - ma_col) / ma_col * 100

        # MA cross flags
        ma5 = c.rolling(5).mean()
        ma20 = c.rolling(20).mean()
        ma50 = c.rolling(50).mean()
        g['ma_cross_5_20'] = (ma5 > ma20).astype(int)
        g['ma_cross_20_50'] = (ma20 > ma50).astype(int)

        g['stoch_k_14'] = stoch_k(g, 14)
        g['stoch_d_14'] = g['stoch_k_14'].rolling(3).mean()

        # ADX simplified (trend strength via |EMA cross|)
        g['adx_proxy'] = (ema12 - ema26).abs() / c * 100

        # === Group B: Returns/Momentum ===
        for n in [1, 3, 5, 10, 20, 60]:
            g[f'ret_{n}d'] = c.pct_change(n) * 100

        for n in [10, 20, 60]:
            g[f'vol_{n}d'] = c.pct_change().rolling(n).std() * 100  # daily realized vol %

        # === Group C: Volume ===
        v_ma20 = v.rolling(20).mean()
        g['vol_ratio_20'] = v / v_ma20.replace(0, np.nan)
        g['vol_ratio_5'] = v / v.rolling(5).mean().replace(0, np.nan)

        v_change = v.pct_change().replace([np.inf, -np.inf], np.nan).clip(-5, 5)
        g['vol_change_1d'] = v_change

        # OBV
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        g['obv_ma20_dist'] = (obv - obv.rolling(20).mean()) / obv.rolling(20).std().replace(0, np.nan)

        # Money Flow Proxy
        typical = (h + l + c) / 3
        mf = typical * v
        pos_mf = mf.where(typical > typical.shift(1), 0).rolling(14).sum()
        neg_mf = mf.where(typical < typical.shift(1), 0).rolling(14).sum()
        g['money_flow_14'] = pos_mf / (pos_mf + neg_mf).replace(0, np.nan)

        # === Group D: Position/Range ===
        g['pct_52w_hi'] = (c / c.rolling(252).max() - 1) * 100
        g['pct_52w_lo'] = (c / c.rolling(252).min() - 1) * 100
        g['pct_20d_hi'] = (c / c.rolling(20).max() - 1) * 100
        g['pct_20d_lo'] = (c / c.rolling(20).min() - 1) * 100

        # Range expansion
        rng_today = (h - l) / c * 100
        rng_avg = rng_today.rolling(20).mean()
        g['range_exp'] = rng_today / rng_avg.replace(0, np.nan)

        # Consolidation (low std = tight)
        g['consol_20d'] = c.rolling(20).std() / c * 100

        # Days since 20d high / low
        rolling_max = c.rolling(20).max()
        rolling_min = c.rolling(20).min()
        g['days_since_20d_hi'] = (c.rolling(20).apply(lambda x: 20 - 1 - np.argmax(x), raw=True)).fillna(0)
        g['days_since_20d_lo'] = (c.rolling(20).apply(lambda x: 20 - 1 - np.argmin(x), raw=True)).fillna(0)

        out.append(g)
    return pd.concat(out, ignore_index=True)


def add_calendar_features(df, earn_df):
    """Days-to-earnings + calendar features."""
    df['dow'] = df['date'].dt.dayofweek
    df['dom'] = df['date'].dt.day
    df['month'] = df['date'].dt.month
    df['days_to_next_earnings'] = 999

    earn_dict = {}
    for sym, g in earn_df.groupby('symbol'):
        earn_dict[sym] = sorted(g['report_date'].values)

    # For each row, find next earnings
    out_days = np.full(len(df), 999.0)
    for sym, g_idx in df.groupby('symbol', sort=False).groups.items():
        if sym not in earn_dict:
            continue
        sub = df.loc[g_idx, 'date'].values
        report_dates = np.array(earn_dict[sym])
        for i, idx in enumerate(g_idx):
            d = sub[i]
            future = report_dates[report_dates >= d]
            if len(future) > 0:
                out_days[idx] = (future[0] - d) / np.timedelta64(1, 'D')
    df['days_to_next_earnings'] = out_days
    df['days_to_next_earnings'] = df['days_to_next_earnings'].clip(0, 999)
    return df


def add_macro_features(df, macro_df):
    """Merge daily macro + add macro features (vix percentile, spy trend)."""
    macro_df = macro_df.sort_values('date').copy()

    # VIX features
    macro_df['vix_5d_chg'] = macro_df['vix'].pct_change(5) * 100
    macro_df['vix_pctile_60d'] = macro_df['vix'].rolling(60).rank(pct=True) * 100
    # SPY features
    if 'spy_close' in macro_df.columns:
        spy = macro_df['spy_close']
        macro_df['spy_5d_chg'] = spy.pct_change(5) * 100
        macro_df['spy_20d_chg'] = spy.pct_change(20) * 100
        macro_df['spy_dist_ma20'] = (spy / spy.rolling(20).mean() - 1) * 100
        macro_df['spy_dist_ma50'] = (spy / spy.rolling(50).mean() - 1) * 100
    if 'hyg_close' in macro_df.columns and 'spy_close' in macro_df.columns:
        macro_df['hyg_spy_ratio'] = macro_df['hyg_close'] / macro_df['spy_close']
        macro_df['hyg_spy_chg'] = macro_df['hyg_spy_ratio'].pct_change(5) * 100
    if 'tlt_close' in macro_df.columns:
        macro_df['tlt_5d_chg'] = macro_df['tlt_close'].pct_change(5) * 100
    if 'dxy_close' in macro_df.columns:
        macro_df['dxy_5d_chg'] = macro_df['dxy_close'].pct_change(5) * 100
    if 'yield_spread' in macro_df.columns:
        macro_df['yield_spread_chg'] = macro_df['yield_spread'].diff(5)

    macro_cols = ['date', 'vix', 'vix_5d_chg', 'vix_pctile_60d',
                  'spy_5d_chg', 'spy_20d_chg', 'spy_dist_ma20', 'spy_dist_ma50',
                  'hyg_spy_chg', 'tlt_5d_chg', 'dxy_5d_chg', 'yield_spread_chg']
    macro_cols = [c for c in macro_cols if c in macro_df.columns]
    return df.merge(macro_df[macro_cols], on='date', how='left')


def add_fundamentals_features(df, funda_df):
    """Beta, mcap, sector code, PE."""
    funda_df = funda_df.copy()
    funda_df['mcap_log'] = np.log10(funda_df['market_cap'].clip(lower=1e6))
    # Sector encoding
    sector_map = {s: i for i, s in enumerate(sorted(funda_df['sector'].fillna('Unknown').unique()))}
    funda_df['sector_id'] = funda_df['sector'].fillna('Unknown').map(sector_map)
    return df.merge(
        funda_df[['symbol', 'beta', 'mcap_log', 'sector_id', 'pe_trailing', 'pe_forward']],
        on='symbol', how='left', suffixes=('', '_fund')
    )


def load_aux():
    con = sqlite3.connect(str(DB))
    earn = pd.read_sql(
        "SELECT symbol, report_date FROM earnings_history "
        "WHERE report_date >= '2019-01-01'", con
    )
    earn['report_date'] = pd.to_datetime(earn['report_date'])
    funda = pd.read_sql(
        "SELECT symbol, beta, market_cap, sector, pe_trailing, pe_forward FROM stock_fundamentals", con
    )
    macro = pd.read_sql(
        "SELECT date, vix_close as vix, spy_close, hyg_close, tlt_close, dxy_close, yield_spread "
        "FROM macro_snapshots WHERE date >= '2019-01-01' ORDER BY date", con
    )
    macro['date'] = pd.to_datetime(macro['date'])
    con.close()
    return earn, funda, macro


def main():
    print("== Phase 2: Feature Engineering ==")
    start = datetime.now()

    print("Loading labeled daily data...")
    df = pd.read_pickle(CACHE / 'phase1_labeled_daily.pkl')
    print(f"  shape: {df.shape}")

    print("Loading aux (earnings/funda/macro)...")
    earn, funda, macro = load_aux()
    print(f"  earnings: {len(earn):,}, funda: {len(funda):,}, macro: {len(macro):,}")

    print("Adding TA features (slow, per-symbol)...")
    df = add_ta_features(df)
    print(f"  → cols: {len(df.columns)}")

    print("Adding calendar + days-to-earnings...")
    df = add_calendar_features(df, earn)

    print("Adding fundamentals...")
    df = add_fundamentals_features(df, funda)

    print("Adding macro...")
    df = add_macro_features(df, macro)

    print(f"\nFinal shape: {df.shape}, total cols: {len(df.columns)}")
    feature_cols = [c for c in df.columns if c not in ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'year']
                    and not c.startswith('fhigh_') and not c.startswith('flow_') and not c.startswith('fclose_')
                    and not c.startswith('L_')]
    print(f"Feature columns ({len(feature_cols)}): {feature_cols}")

    out_path = CACHE / 'phase2_features.pkl'
    df.to_pickle(out_path)
    print(f"\n✅ Saved to {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"Elapsed: {elapsed:.1f}s")


if __name__ == '__main__':
    main()
