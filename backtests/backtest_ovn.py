#!/usr/bin/env python3
"""
OVN (Overnight Gap) Backtest 2023-2025
=======================================
Replicates overnight_gap_scanner.py logic on historical data.

Strategy:
  Entry:  Day T close (buy at ~3:45 PM ET)
  Exit:   Day T+1 open (sell at market open next morning)
  P&L:    (T+1 open - T close) / T close

Filters (from OVN screener):
  1. Close ≥ 96% of daily high (close near HOD)
  2. Green day: close > open
  3. Intraday selling pressure < 3% (open→low drop)
  4. Volume ≥ 1.2× 20d average
  5. RSI 40-65
  6. ATR 1.5–6%
  7. Score ≥ 70

Exit scenarios tested:
  A. Exit at T+1 open (pure overnight gap — production behavior)
  B. Exit at T+1 close (hold full day)
  C. Exit at T+1 open with SL=1.5% (current production SL)

Usage:
  python3 backtests/backtest_ovn.py
  python3 backtests/backtest_ovn.py --universe sp400  # larger universe
  python3 backtests/backtest_ovn.py --top-n 3        # take top 3 per day
"""

import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# ─── Universe ──────────────────────────────────────────────────────────────────

# ~300 liquid non-Financial stocks across sectors
# Mix of large/mid cap to match OVN screener target
BASE_UNIVERSE = [
    # Tech
    'AAPL','MSFT','NVDA','AMD','GOOGL','META','AMZN','TSLA','AVGO','QCOM',
    'TXN','AMAT','LRCX','KLAC','MU','INTC','CRM','NOW','ADBE','ORCL',
    'SNPS','CDNS','FTNT','PANW','CRWD','NET','DDOG','ZS','OKTA','TEAM',
    'SNOW','PLTR','PATH','MDB','HUBS','TTD','BILL','AFRM','SHOP','UBER',
    # Healthcare
    'UNH','LLY','JNJ','ABBV','MRK','PFE','AMGN','GILD','REGN','VRTX',
    'ISRG','BSX','MDT','SYK','ZBH','BAX','BDX','EW','ALGN','HOLX',
    # Industrials
    'GE','HON','CAT','DE','EMR','ITW','ETN','PH','ROK','AME',
    'XYL','ROP','VRSK','IEX','IDEX','TDY','HWM','WWD','AOS','GNRC',
    'FTV','PWR','ACM','J','FLR','XPO','SAIA','ODFL','JBHT','CHRW',
    # Consumer Discretionary
    'MCD','SBUX','NKE','TGT','HD','LOW','BBY','ROST','TJX','ULTA',
    'YUM','CMG','DRI','DKNG','LYFT','BKNG','EXPE','MAR','HLT','H',
    'NFLX','DIS','PARA','WBD','FOXA','LYV','CHDN','PENN','WYNN',
    # Consumer Staples
    'PG','KO','PEP','MDLZ','GIS','K','CPB','MKC','CAG','SJM',
    # Energy (non-Financial)
    'XOM','CVX','COP','EOG','PXD','DVN','MPC','PSX','VLO','OXY',
    'HAL','SLB','BKR','NOV','HP','RIG','PTEN',
    # Materials
    'LIN','APD','ECL','SHW','PPG','NEM','FCX','STLD','NUE','RS',
    # Utilities (OVN-friendly: low volatility consistent gaps)
    'NEE','DUK','AEE','WEC','PPL','CMS','ATO','NI','OGE','PNW',
    'AES','ETR','EXC','PCG','XEL','EVRG','ES','AWK','SRE','D',
    # REITs (non-Financial)
    'PLD','AMT','EQIX','CCI','DLR','PSA','EXR','INVH','MAA','UDR',
    'SUI','ELS','NNN','O','VICI','GLPI','MPW','DOC','WELL','VTR',
    # Mid-cap growth
    'ENPH','RUN','FSLR','PLUG','HASI','BEP','AES','CEG','VST',
    'GNRC','PODD','DXCM','TFX','NVST','HOLX','IRTC','LIVN','NVCR',
    'ITGR','AMED','ACAD','RXRX','PCVX','ARWR','EXAS','GH','FATE',
    'LNTH','FOLD','ALKS','PRGO','LGND','ITCI','INVA','SUPN',
    # Additional mid-cap
    'MTCH','HOOD','COIN','MSTR','RIOT','MARA','DKL','AIT','FAST',
    'GPI','ROCK','POWI','JCI','SWK','MTN','NOV','PRGO','AKR','GBCI',
    'WAL','COLB','RPD','WEX','RARE','GPK','SSP','BWXT','KHC','XPO',
]

# Remove duplicates
BASE_UNIVERSE = list(dict.fromkeys(BASE_UNIVERSE))

CACHE_DIR = Path('backtests/cache/ovn')
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─── Data Loading ──────────────────────────────────────────────────────────────

def load_data(universe: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """
    Batch download OHLCV data with per-symbol cache.
    Returns {symbol: DataFrame} with columns Open/High/Low/Close/Volume.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    cache_key = f"{start}_{end}"
    data = {}
    to_fetch = []

    for sym in universe:
        cache_file = CACHE_DIR / f"{sym}_{cache_key}.csv"
        if cache_file.exists():
            try:
                df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                if len(df) > 50:
                    data[sym] = df
                    continue
            except Exception:
                pass
        to_fetch.append(sym)

    if to_fetch:
        print(f"Downloading {len(to_fetch)} symbols from yfinance...", flush=True)
        BATCH = 100
        for i in range(0, len(to_fetch), BATCH):
            batch = to_fetch[i:i+BATCH]
            print(f"  Batch {i//BATCH+1}/{(len(to_fetch)-1)//BATCH+1}: {len(batch)} symbols", flush=True)
            try:
                raw = yf.download(
                    batch, start=start, end=end,
                    auto_adjust=True, progress=False, threads=True
                )
                if raw.empty:
                    continue

                # Handle multi-ticker format (MultiIndex columns)
                if isinstance(raw.columns, pd.MultiIndex):
                    for sym in batch:
                        try:
                            df = raw.xs(sym, level=1, axis=1).copy()
                            df.dropna(how='all', inplace=True)
                            if len(df) > 50:
                                df.to_csv(CACHE_DIR / f"{sym}_{cache_key}.csv")
                                data[sym] = df
                        except Exception:
                            pass
                else:
                    # Single ticker
                    sym = batch[0]
                    raw.dropna(how='all', inplace=True)
                    if len(raw) > 50:
                        raw.to_csv(CACHE_DIR / f"{sym}_{cache_key}.csv")
                        data[sym] = raw
            except Exception as e:
                print(f"  Batch download error: {e}")

    print(f"Loaded {len(data)} symbols with data\n", flush=True)
    return data


# ─── OVN Filter Logic ──────────────────────────────────────────────────────────

# Parameters (from overnight_gap_scanner.py)
MIN_CLOSE_TO_HIGH_PCT = 96.0
MIN_VOLUME_RATIO = 1.2
RSI_MIN, RSI_MAX = 40, 65
MIN_ATR_PCT, MAX_ATR_PCT = 1.5, 6.0
MAX_INTRADAY_SELLING_PCT = 3.0
MIN_SCORE = 70
BLOCKED_SECTORS = {'Financial Services'}


def calc_rsi(close: np.ndarray, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    deltas = np.diff(close[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_atr_pct(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        trs.append(max(float(high[i]) - float(low[i]),
                       abs(float(high[i]) - float(close[i-1])),
                       abs(float(low[i]) - float(close[i-1]))))
    atr = np.mean(trs)
    price = float(close[-1])
    return (atr / price * 100) if price > 0 else None


def score_candidate(symbol: str, df: pd.DataFrame, idx: int) -> Optional[dict]:
    """
    Apply OVN filters for day at position `idx` in DataFrame.
    Returns candidate dict or None.
    """
    if idx < 25:
        return None

    close = df['Close'].values[:idx+1]
    high  = df['High'].values[:idx+1]
    low   = df['Low'].values[:idx+1]
    open_ = df['Open'].values[:idx+1]
    vol   = df['Volume'].values[:idx+1]

    cur_close  = float(close[-1])
    cur_high   = float(high[-1])
    cur_low    = float(low[-1])
    cur_open   = float(open_[-1])
    cur_vol    = float(vol[-1])

    if cur_close <= 0 or cur_high <= 0 or cur_open <= 0:
        return None

    score = 0

    # 1. Close near HOD (≥96%)
    close_to_high = (cur_close / cur_high) * 100
    if close_to_high < MIN_CLOSE_TO_HIGH_PCT:
        return None
    score += 30

    # 2. Green day
    if cur_close <= cur_open:
        return None
    day_gain = (cur_close - cur_open) / cur_open * 100
    score += min(int(day_gain * 5), 20)

    # 3. Intraday selling pressure < 3%
    open_to_low = (cur_open - cur_low) / cur_open * 100
    if open_to_low >= MAX_INTRADAY_SELLING_PCT:
        return None

    # 4. Volume ≥ 1.2× 20d avg
    avg_vol = float(np.mean(vol[-21:-1])) if len(vol) >= 21 else float(np.mean(vol[:-1]))
    if avg_vol <= 0:
        return None
    vol_ratio = cur_vol / avg_vol
    if vol_ratio < MIN_VOLUME_RATIO:
        return None
    score += min(int(vol_ratio * 10), 20)

    # 5. RSI 40-65
    rsi = calc_rsi(close)
    if rsi is not None:
        if rsi < RSI_MIN or rsi > RSI_MAX:
            return None
        score += 15

    # 6. ATR 1.5-6%
    atr_pct = calc_atr_pct(high, low, close)
    if atr_pct is None:
        atr_pct = 3.0
    elif atr_pct > MAX_ATR_PCT or atr_pct < MIN_ATR_PCT:
        return None
    score += 10

    # 7. Above SMA20 bonus
    sma20 = float(np.mean(close[-20:]))
    if cur_close > sma20:
        score += 10

    if score < MIN_SCORE:
        return None

    return {
        'symbol': symbol,
        'score': score,
        'entry': cur_close,
        'rsi': round(rsi, 1) if rsi else 50.0,
        'atr_pct': round(atr_pct, 2),
        'vol_ratio': round(vol_ratio, 2),
        'day_gain': round(day_gain, 2),
        'close_to_high': round(close_to_high, 2),
        'open_to_low': round(open_to_low, 2),
    }


# ─── Backtest Engine ───────────────────────────────────────────────────────────

def run_backtest(data: Dict[str, pd.DataFrame], top_n: int = 1, sl_pct: float = 1.5) -> pd.DataFrame:
    """
    For each trading day T, find OVN candidates and simulate overnight P&L.
    P&L = T+1 open vs T close.

    Returns DataFrame of all trades.
    """
    # Build date index across all symbols
    all_dates = sorted(set(
        date for df in data.values() for date in df.index
    ))

    trades = []

    for i, date_t in enumerate(all_dates[25:-1]):  # need history + next day
        date_t1 = all_dates[i + 25 + 1]  # next trading day

        # Scan all symbols for this day
        candidates = []
        for sym, df in data.items():
            if date_t not in df.index:
                continue
            idx = df.index.get_loc(date_t)
            if idx < 25:
                continue
            c = score_candidate(sym, df, idx)
            if c:
                # Get next day open for P&L
                if date_t1 not in df.index:
                    continue
                idx_t1 = df.index.get_loc(date_t1)
                next_open  = float(df['Open'].iloc[idx_t1])
                next_close = float(df['Close'].iloc[idx_t1])
                if next_open <= 0:
                    continue

                overnight_ret = (next_open - c['entry']) / c['entry'] * 100
                hold_day_ret  = (next_close - c['entry']) / c['entry'] * 100

                c['date']          = date_t.strftime('%Y-%m-%d')
                c['next_open']     = next_open
                c['next_close']    = next_close
                c['overnight_ret'] = round(overnight_ret, 3)
                c['hold_day_ret']  = round(hold_day_ret, 3)

                # With SL applied at open
                if overnight_ret <= -sl_pct:
                    c['sl_ret'] = -sl_pct
                    c['sl_hit'] = True
                else:
                    c['sl_ret'] = overnight_ret
                    c['sl_hit'] = False

                candidates.append(c)

        # Sort by score desc, take top N
        candidates.sort(key=lambda x: x['score'], reverse=True)
        for c in candidates[:top_n]:
            trades.append(c)

    return pd.DataFrame(trades)


# ─── Analysis ──────────────────────────────────────────────────────────────────

def print_metrics(df: pd.DataFrame, label: str, col: str):
    if df.empty:
        print(f"  {label}: no data")
        return
    vals = df[col].values
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    n = len(vals)
    wr = len(wins) / n * 100
    avg = vals.mean()
    avg_win = wins.mean() if len(wins) else 0
    avg_loss = losses.mean() if len(losses) else 0
    expectancy = wr/100 * avg_win + (1-wr/100) * avg_loss
    total_usd = sum(v / 100 * 1500 for v in vals)  # $1,500 per OVN trade
    print(f"  {label:<35} n={n:>4}  WR={wr:>5.1f}%  avg={avg:>+6.2f}%  E={expectancy:>+5.2f}%  total=${total_usd:>7.0f}")


def analyze(df: pd.DataFrame, sl_pct: float):
    n = len(df)
    if n == 0:
        print("No trades found.")
        return

    print(f"\n{'='*70}")
    print(f"OVN BACKTEST RESULTS  (n={n} trade-days, $1,500/trade)")
    print(f"{'='*70}")

    print_metrics(df, "A) Exit at T+1 open (pure overnight)", 'overnight_ret')
    print_metrics(df, f"B) Exit at open with SL={sl_pct}%", 'sl_ret')
    print_metrics(df, "C) Exit at T+1 close (hold full day)", 'hold_day_ret')

    # Year breakdown
    df['year'] = df['date'].str[:4]
    print(f"\n--- By Year (overnight exit) ---")
    print(f"  {'Year':>6}  {'n':>4}  {'WR':>6}  {'avg':>7}  {'total$':>8}")
    for yr in sorted(df['year'].unique()):
        sub = df[df['year'] == yr]
        vals = sub['overnight_ret'].values
        wr = (vals > 0).mean() * 100
        print(f"  {yr:>6}  {len(vals):>4}  {wr:>5.1f}%  {vals.mean():>+6.2f}%  ${vals.sum()/100*1500:>7.0f}")

    # Month breakdown
    df['month'] = df['date'].str[:7]
    print(f"\n--- By Month (overnight exit, last 12) ---")
    print(f"  {'Month':>8}  {'n':>4}  {'WR':>6}  {'avg':>7}  {'SL hits':>8}")
    for mo in sorted(df['month'].unique())[-12:]:
        sub = df[df['month'] == mo]
        vals = sub['overnight_ret'].values
        wr = (vals > 0).mean() * 100
        sl_hits = sub['sl_hit'].sum()
        print(f"  {mo:>8}  {len(vals):>4}  {wr:>5.1f}%  {vals.mean():>+6.2f}%  {sl_hits:>8}")

    # RSI analysis
    df['rsi_bucket'] = pd.cut(df['rsi'], bins=[0,45,50,55,60,65,100],
                               labels=['<45','45-50','50-55','55-60','60-65','≥65'])
    print(f"\n--- RSI Buckets (overnight exit) ---")
    print(f"  {'RSI':>7}  {'n':>4}  {'WR':>6}  {'avg':>7}")
    for b in ['<45','45-50','50-55','55-60','60-65']:
        sub = df[df['rsi_bucket'] == b]
        if len(sub) == 0:
            continue
        vals = sub['overnight_ret'].values
        print(f"  {b:>7}  {len(vals):>4}  {(vals>0).mean()*100:>5.1f}%  {vals.mean():>+6.2f}%")

    # ATR analysis
    df['atr_bucket'] = pd.cut(df['atr_pct'], bins=[0,2,3,4,5,6,100],
                               labels=['<2','2-3','3-4','4-5','5-6','>6'])
    print(f"\n--- ATR Buckets (overnight exit) ---")
    print(f"  {'ATR':>5}  {'n':>4}  {'WR':>6}  {'avg':>7}")
    for b in ['<2','2-3','3-4','4-5','5-6']:
        sub = df[df['atr_bucket'] == b]
        if len(sub) == 0:
            continue
        vals = sub['overnight_ret'].values
        print(f"  {b:>5}  {len(vals):>4}  {(vals>0).mean()*100:>5.1f}%  {vals.mean():>+6.2f}%")

    # Vol ratio analysis
    df['vol_bucket'] = pd.cut(df['vol_ratio'], bins=[0,1.5,2,3,5,100],
                               labels=['1.2-1.5','1.5-2','2-3','3-5','>5'])
    print(f"\n--- Volume Ratio Buckets ---")
    print(f"  {'Vol':>8}  {'n':>4}  {'WR':>6}  {'avg':>7}")
    for b in ['1.2-1.5','1.5-2','2-3','3-5','>5']:
        sub = df[df['vol_bucket'] == b]
        if len(sub) == 0:
            continue
        vals = sub['overnight_ret'].values
        print(f"  {b:>8}  {len(vals):>4}  {(vals>0).mean()*100:>5.1f}%  {vals.mean():>+6.2f}%")

    # Top 10 best and worst trades
    print(f"\n--- Top 10 Best Trades ---")
    top = df.nlargest(10, 'overnight_ret')[['date','symbol','overnight_ret','rsi','atr_pct','vol_ratio','score']]
    for _, r in top.iterrows():
        print(f"  {r['date']}  {r['symbol']:<7} {r['overnight_ret']:>+6.2f}%  RSI={r['rsi']:.0f}  ATR={r['atr_pct']:.1f}%  Vol={r['vol_ratio']:.1f}x  score={r['score']}")

    print(f"\n--- Top 10 Worst Trades ---")
    bot = df.nsmallest(10, 'overnight_ret')[['date','symbol','overnight_ret','rsi','atr_pct','vol_ratio','score']]
    for _, r in bot.iterrows():
        print(f"  {r['date']}  {r['symbol']:<7} {r['overnight_ret']:>+6.2f}%  RSI={r['rsi']:.0f}  ATR={r['atr_pct']:.1f}%  Vol={r['vol_ratio']:.1f}x  score={r['score']}")

    # Save results
    out = Path('backtests/cache/ovn') / 'results.csv'
    df.to_csv(out, index=False)
    print(f"\nFull results saved: {out}")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='OVN Backtest')
    parser.add_argument('--start', default='2023-01-01')
    parser.add_argument('--end',   default='2026-01-01')
    parser.add_argument('--sl',    type=float, default=1.5, help='Stop loss %')
    parser.add_argument('--top-n', type=int,   default=1,   help='Top N candidates per day')
    parser.add_argument('--universe', default='base', choices=['base'],
                        help='Universe to use')
    args = parser.parse_args()

    universe = BASE_UNIVERSE
    print(f"OVN Backtest: {args.start} → {args.end}")
    print(f"Universe: {len(universe)} stocks | SL={args.sl}% | Top-N={args.top_n}")
    print()

    data = load_data(universe, args.start, args.end)

    print("Running backtest...", flush=True)
    trades_df = run_backtest(data, top_n=args.top_n, sl_pct=args.sl)

    analyze(trades_df, sl_pct=args.sl)


if __name__ == '__main__':
    main()
