"""
swing_features.py — Live daily feature computation for swing_filter.

Builds today's feature vector for each universe stock by:
  1. Loading recent daily OHLC (200+ days for MA200)
  2. Computing same features as Phase 2 (rsi, macd, ATR, MAs, momentum, etc.)
  3. Merging fundamentals + earnings + macro
  4. Returning DataFrame: (symbol, feature_cols)

Used by SwingFilter strategy at 15:55-16:00 ET market close.
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta


DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')


# Mirror Phase 2 TA helpers
def _rsi(s, period):
    delta = s.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def _atr(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _stoch_k(df, period=14):
    high_n = df['high'].rolling(period).max()
    low_n = df['low'].rolling(period).min()
    return 100 * (df['close'] - low_n) / (high_n - low_n).replace(0, np.nan)


def _compute_ta_one_symbol(g):
    """Compute all TA features for one symbol's history."""
    g = g.sort_values('date').reset_index(drop=True).copy()
    c, h, l, v = g['close'], g['high'], g['low'], g['volume']

    g['rsi_7'] = _rsi(c, 7)
    g['rsi_14'] = _rsi(c, 14)
    ema12, ema26 = _ema(c, 12), _ema(c, 26)
    macd_line = ema12 - ema26
    macd_sig = _ema(macd_line, 9)
    g['macd_hist'] = (macd_line - macd_sig) / c * 100

    bb_ma = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    g['bb_pos'] = (c - (bb_ma - 2 * bb_std)) / (4 * bb_std).replace(0, np.nan)
    g['bb_width'] = (4 * bb_std / bb_ma).clip(0, 1)

    g['atr_14'] = _atr(g, 14)
    g['atr_pct'] = g['atr_14'] / c * 100

    for ma in [5, 10, 20, 50, 100, 200]:
        ma_col = c.rolling(ma).mean()
        g[f'dist_ma{ma}'] = (c - ma_col) / ma_col * 100
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma50 = c.rolling(50).mean()
    g['ma_cross_5_20'] = (ma5 > ma20).astype(int)
    g['ma_cross_20_50'] = (ma20 > ma50).astype(int)

    g['stoch_k_14'] = _stoch_k(g, 14)
    g['stoch_d_14'] = g['stoch_k_14'].rolling(3).mean()
    g['adx_proxy'] = (ema12 - ema26).abs() / c * 100

    for n in [1, 3, 5, 10, 20, 60]:
        g[f'ret_{n}d'] = c.pct_change(n) * 100
    for n in [10, 20, 60]:
        g[f'vol_{n}d'] = c.pct_change().rolling(n).std() * 100

    v_ma20 = v.rolling(20).mean()
    g['vol_ratio_20'] = v / v_ma20.replace(0, np.nan)
    g['vol_ratio_5'] = v / v.rolling(5).mean().replace(0, np.nan)
    v_change = v.pct_change().replace([np.inf, -np.inf], np.nan).clip(-5, 5)
    g['vol_change_1d'] = v_change

    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    g['obv_ma20_dist'] = (obv - obv.rolling(20).mean()) / obv.rolling(20).std().replace(0, np.nan)

    typical = (h + l + c) / 3
    mf = typical * v
    pos_mf = mf.where(typical > typical.shift(1), 0).rolling(14).sum()
    neg_mf = mf.where(typical < typical.shift(1), 0).rolling(14).sum()
    g['money_flow_14'] = pos_mf / (pos_mf + neg_mf).replace(0, np.nan)

    g['pct_52w_hi'] = (c / c.rolling(252).max() - 1) * 100
    g['pct_52w_lo'] = (c / c.rolling(252).min() - 1) * 100
    g['pct_20d_hi'] = (c / c.rolling(20).max() - 1) * 100
    g['pct_20d_lo'] = (c / c.rolling(20).min() - 1) * 100

    rng_today = (h - l) / c * 100
    rng_avg = rng_today.rolling(20).mean()
    g['range_exp'] = rng_today / rng_avg.replace(0, np.nan)
    g['consol_20d'] = c.rolling(20).std() / c * 100

    g['days_since_20d_hi'] = c.rolling(20).apply(lambda x: 20 - 1 - np.argmax(x), raw=True).fillna(0)
    g['days_since_20d_lo'] = c.rolling(20).apply(lambda x: 20 - 1 - np.argmin(x), raw=True).fillna(0)

    return g


def build_today_features(target_date=None, universe=None,
                          apply_liquidity_filter=True,
                          min_price=5.0, min_mcap=1e9, min_dollar_vol=10e6):
    """Build feature vector for each symbol on target_date (or latest).

    Args:
        target_date: date string YYYY-MM-DD or None (= latest)
        universe: list of symbols to limit to, or None (= all)
        apply_liquidity_filter: if True (default), apply v2.0 universe filter
        min_price, min_mcap, min_dollar_vol: filter thresholds

    Returns: DataFrame indexed by symbol with all feature cols.
    """
    con = sqlite3.connect(str(DB))

    # Load recent OHLC (need 252 days lookback for 52w features)
    if target_date is None:
        target_date = pd.read_sql("SELECT MAX(date) FROM stock_daily_ohlc", con).iloc[0, 0]
    target_dt = pd.to_datetime(target_date)
    lookback_start = (target_dt - pd.Timedelta(days=400)).strftime('%Y-%m-%d')

    where_uni = ""
    if universe:
        syms_str = ",".join([f"'{s}'" for s in universe])
        where_uni = f" AND symbol IN ({syms_str})"

    daily = pd.read_sql(
        f"SELECT symbol, date, open, high, low, close, volume "
        f"FROM stock_daily_ohlc WHERE date >= '{lookback_start}' AND date <= '{target_date}'{where_uni} "
        "ORDER BY symbol, date", con
    )
    daily['date'] = pd.to_datetime(daily['date'])

    funda = pd.read_sql(
        "SELECT symbol, beta, market_cap, sector, pe_trailing, pe_forward FROM stock_fundamentals", con
    )
    funda['mcap_log'] = np.log10(funda['market_cap'].clip(lower=1e6))
    sector_map = {s: i for i, s in enumerate(sorted(funda['sector'].fillna('Unknown').unique()))}
    funda['sector_id'] = funda['sector'].fillna('Unknown').map(sector_map)

    earn = pd.read_sql(
        f"SELECT symbol, report_date FROM earnings_history WHERE report_date >= '{lookback_start}'", con
    )
    earn['report_date'] = pd.to_datetime(earn['report_date'])

    macro = pd.read_sql(
        f"SELECT date, vix_close as vix, spy_close, hyg_close, tlt_close, dxy_close, yield_spread "
        f"FROM macro_snapshots WHERE date >= '{lookback_start}' ORDER BY date", con
    )
    macro['date'] = pd.to_datetime(macro['date'])
    con.close()

    # Compute TA per symbol
    enriched = []
    for sym, g in daily.groupby('symbol', sort=False):
        if len(g) < 200:
            continue
        gf = _compute_ta_one_symbol(g)
        # Take only target date row
        latest = gf[gf['date'] == target_dt]
        if len(latest) == 0:
            continue
        enriched.append(latest.iloc[-1:])

    if not enriched:
        return pd.DataFrame()
    df = pd.concat(enriched, ignore_index=True)

    # Add calendar
    df['dow'] = df['date'].dt.dayofweek
    df['dom'] = df['date'].dt.day
    df['month'] = df['date'].dt.month

    # Days to next earnings
    earn_dict = {}
    for sym, g in earn.groupby('symbol'):
        earn_dict[sym] = sorted(g['report_date'].values)
    dtn = np.full(len(df), 999.0)
    for i, row in df.iterrows():
        sym = row['symbol']
        if sym in earn_dict:
            future = [r for r in earn_dict[sym] if r >= row['date']]
            if future:
                dtn[i] = (future[0] - row['date']) / np.timedelta64(1, 'D')
    df['days_to_next_earnings'] = np.clip(dtn, 0, 999)

    # Earnings nearby flag (±2 days)
    earn_set = set()
    for sym, dts in earn_dict.items():
        for d in dts:
            for off in range(-2, 3):
                earn_set.add((sym, pd.Timestamp(d) + pd.Timedelta(days=off)))
    df['has_earnings_nearby'] = df.apply(lambda r: int((r['symbol'], r['date']) in earn_set), axis=1)

    # Merge fundamentals
    df = df.merge(funda[['symbol', 'beta', 'mcap_log', 'sector_id', 'pe_trailing', 'pe_forward']],
                  on='symbol', how='left')

    # Compute macro features for target date
    macro_sorted = macro.sort_values('date').copy()
    macro_sorted['vix_5d_chg'] = macro_sorted['vix'].pct_change(5) * 100
    macro_sorted['vix_pctile_60d'] = macro_sorted['vix'].rolling(60).rank(pct=True) * 100
    if 'spy_close' in macro_sorted.columns:
        spy = macro_sorted['spy_close']
        macro_sorted['spy_5d_chg'] = spy.pct_change(5) * 100
        macro_sorted['spy_20d_chg'] = spy.pct_change(20) * 100
        macro_sorted['spy_dist_ma20'] = (spy / spy.rolling(20).mean() - 1) * 100
        macro_sorted['spy_dist_ma50'] = (spy / spy.rolling(50).mean() - 1) * 100
    if 'hyg_close' in macro_sorted.columns and 'spy_close' in macro_sorted.columns:
        macro_sorted['hyg_spy_ratio'] = macro_sorted['hyg_close'] / macro_sorted['spy_close']
        macro_sorted['hyg_spy_chg'] = macro_sorted['hyg_spy_ratio'].pct_change(5) * 100
    if 'tlt_close' in macro_sorted.columns:
        macro_sorted['tlt_5d_chg'] = macro_sorted['tlt_close'].pct_change(5) * 100
    if 'dxy_close' in macro_sorted.columns:
        macro_sorted['dxy_5d_chg'] = macro_sorted['dxy_close'].pct_change(5) * 100
    if 'yield_spread' in macro_sorted.columns:
        macro_sorted['yield_spread_chg'] = macro_sorted['yield_spread'].diff(5)

    macro_today = macro_sorted[macro_sorted['date'] == target_dt]
    if len(macro_today) > 0:
        m = macro_today.iloc[0]
    else:
        m = macro_sorted.iloc[-1]
    # Training pkl used 'vix_x' (from pandas suffix conflict), so live must match
    for col_live, col_train in [('vix', 'vix_x'),
                                  ('vix_5d_chg', 'vix_5d_chg'),
                                  ('vix_pctile_60d', 'vix_pctile_60d'),
                                  ('spy_5d_chg', 'spy_5d_chg'),
                                  ('spy_20d_chg', 'spy_20d_chg'),
                                  ('spy_dist_ma20', 'spy_dist_ma20'),
                                  ('spy_dist_ma50', 'spy_dist_ma50'),
                                  ('hyg_spy_chg', 'hyg_spy_chg'),
                                  ('tlt_5d_chg', 'tlt_5d_chg'),
                                  ('dxy_5d_chg', 'dxy_5d_chg'),
                                  ('yield_spread_chg', 'yield_spread_chg')]:
        if col_live in macro_sorted.columns:
            df[col_train] = m[col_live]

    # Apply v2.0 universe filter (price, mcap, ADV)
    if apply_liquidity_filter:
        funda_full = pd.read_sql(
            f"SELECT symbol, market_cap, avg_volume FROM stock_fundamentals",
            sqlite3.connect(str(DB))
        )
        df = df.merge(funda_full, on='symbol', how='left', suffixes=('', '_f2'))
        if 'avg_volume_f2' in df.columns:
            df['avg_volume'] = df['avg_volume_f2']
            df = df.drop(columns=['avg_volume_f2'])
        if 'market_cap_f2' in df.columns:
            df['market_cap'] = df['market_cap_f2']
            df = df.drop(columns=['market_cap_f2'])
        df['avg_dollar_vol'] = df['avg_volume'] * df['close']
        n_before = len(df)
        df = df[
            (df['close'] >= min_price) &
            (df['market_cap'].fillna(0) >= min_mcap) &
            (df['avg_dollar_vol'].fillna(0) >= min_dollar_vol)
        ].copy()
        n_after = len(df)
        # Drop intermediate columns (don't pollute features)
        df = df.drop(columns=[c for c in ['market_cap', 'avg_volume', 'avg_dollar_vol'] if c in df.columns])

    return df


if __name__ == '__main__':
    df = build_today_features()
    print(f"Built features for {len(df)} symbols")
    print(df.head())
