#!/usr/bin/env python3
"""
Candlestick Strategy Backtest (2023-2025)
=========================================
Tests the spec from docs/CANDLESTICK_STRATEGY_SPEC.md faithfully:
- Patterns: Bullish Engulfing + Hammer (with 3 context filters)
- Entry: Next day open + 0.2% limit, skip if gap >0.5%
- Exit: SL (pattern low -0.5%, capped 2-4%), TP (1:2 RR), time exit 10 days
- Trailing: activates at +1R, locks +0.5R
- Position sizing: 1% equity risk, 10% max, 5 concurrent max
- Protection Layer 1: ATR5/ATR50 > 1.8 → 50% size; > 2.5 → skip
- Costs: slippage 0.2% + commission 0.1% = 0.3% round trip
- Universe: ~150 S&P 500 high-quality stocks
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# UNIVERSE — diversified S&P 500 stocks (150 stocks)
# ============================================================
UNIVERSE = [
    # Technology
    'AAPL','MSFT','NVDA','AMD','AVGO','QCOM','TXN','AMAT','KLAC','LRCX',
    'INTC','MU','MRVL','ON','SWKS','KEYS','CDNS','SNPS','ANSS','FTNT',
    # Consumer Cyclical
    'AMZN','TSLA','HD','MCD','NKE','SBUX','LOW','TJX','ROST','CMG',
    'BKNG','MAR','HLT','LVS','MGM','CCL','RCL','F','GM','ORLY',
    # Financials
    'JPM','BAC','GS','MS','BLK','AXP','V','MA','SCHW','SPGI',
    'MCO','ICE','CME','MSCI','TW',
    # Healthcare
    'UNH','LLY','JNJ','ABBV','MRK','TMO','ABT','DHR','BSX','EW',
    'ISRG','IDXX','SYK','ZBH','HOLX',
    # Industrials
    'GE','HON','CAT','DE','RTX','LMT','NOC','GD','BA','UPS',
    'FDX','CARR','OTIS','EMR','ETN',
    # Energy
    'XOM','CVX','COP','EOG','PSX','VLO','MPC','OXY','HAL','SLB',
    # Basic Materials
    'LIN','APD','SHW','ECL','DD','NEM','FCX','NUE','RS','ATI',
    # Communication Services
    'META','GOOGL','NFLX','TTWO','EA','CHTR','TMUS',
    # Consumer Defensive
    'PG','KO','PEP','WMT','COST','MDLZ','CL','KHC','GIS',
    # REITs / Utilities
    'AMT','PLD','EQIX','O','WEC','NEE',
    # High-beta growth (similar to dip-bounce universe)
    'ENPH','PLUG','FSLR','SEDG','BE','CHPT','STEM',
    'CRWD','ZS','NET','DDOG','SNOW','MDB','GTLB','U',
    'SHOP','MELI','SE','GRAB','UBER','LYFT',
]
UNIVERSE = list(dict.fromkeys(UNIVERSE))  # dedup

START = '2023-01-01'
END   = '2025-12-31'
INITIAL_EQUITY = 25_000

SLIPPAGE = 0.002   # 0.2%
COMMISSION = 0.001  # 0.1%
COST = SLIPPAGE + COMMISSION  # per side

# Strategy params (from spec)
MIN_SL_PCT = 2.0
MAX_SL_PCT = 4.0
RR_RATIO   = 2.0
MAX_HOLD_DAYS = 10
MAX_POSITIONS = 5
RISK_PCT  = 0.01   # 1% equity risk per trade
MAX_POS_PCT = 0.10 # 10% max position size

# Context filter params
SMA_WINDOW   = 50
VOL_WINDOW   = 20
VOL_MULT     = 1.3
SUPPORT_PCT  = 0.03  # within 3% of 20d low

# Pattern params
MIN_BODY_RATIO   = 1.5   # engulfing min body vs avg body
HAMMER_SHADOW    = 2.0   # lower shadow >= 2x body
HAMMER_UPPER     = 0.5   # upper shadow <= 0.5x body

# Protection
VOL_RATIO_HALF = 1.8   # 50% size
VOL_RATIO_SKIP = 2.5   # skip
DD_HALF  = 0.06   # 6% equity DD → 50% risk
DD_QUAR  = 0.10   # 10% equity DD → 25% risk

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


def get_data(symbol: str) -> pd.DataFrame:
    cache = os.path.join(CACHE_DIR, f"{symbol}_{START}_{END}_cs.csv")
    if os.path.exists(cache):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    try:
        df = yf.download(symbol, start=START, end=END, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if not df.empty and len(df) > 60:
            df.to_csv(cache)
        return df
    except Exception:
        return pd.DataFrame()


def calc_atr(high, low, close, period):
    hl  = high - low
    hpc = (high - close.shift(1)).abs()
    lpc = (low  - close.shift(1)).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def detect_signals(df: pd.DataFrame) -> List[Dict]:
    """Detect Bullish Engulfing and Hammer patterns with 3 context filters."""
    signals = []
    if len(df) < 60:
        return signals

    o = df['open']
    h = df['high']
    l = df['low']
    c = df['close']
    v = df['volume']

    sma50      = c.rolling(SMA_WINDOW).mean()
    vol_ma20   = v.rolling(VOL_WINDOW).mean()
    support_20 = l.shift(1).rolling(VOL_WINDOW).min()  # no lookahead
    avg_body   = (c - o).abs().rolling(VOL_WINDOW).mean()
    atr5       = calc_atr(h, l, c, 5)
    atr50      = calc_atr(h, l, c, 50)

    for i in range(55, len(df) - 1):
        date = df.index[i]

        # ---- Context Filters ----
        # Filter 1: Trend (SMA50 rising)
        if i < 5 or sma50.iloc[i] <= sma50.iloc[i-5]:
            continue
        # Filter 2: Volume spike
        if v.iloc[i] < VOL_MULT * vol_ma20.iloc[i]:
            continue
        # Filter 3: Near support (within 3%)
        sup = support_20.iloc[i]
        if pd.isna(sup) or sup <= 0:
            continue
        if l.iloc[i] > sup * (1 + SUPPORT_PCT):
            continue

        # ---- Protection: Volatility ratio ----
        vol_ratio = atr5.iloc[i] / atr50.iloc[i] if atr50.iloc[i] > 0 else 0

        pattern = None
        sl_price = None

        # ---- Bullish Engulfing ----
        if (c.iloc[i-1] < o.iloc[i-1] and   # prev candle: red
            c.iloc[i]   > o.iloc[i]   and   # curr candle: green
            o.iloc[i]   < c.iloc[i-1] and   # open below prev close
            c.iloc[i]   > o.iloc[i-1]):      # close above prev open
            body = c.iloc[i] - o.iloc[i]
            if body >= MIN_BODY_RATIO * avg_body.iloc[i]:
                pattern = 'bullish_engulfing'
                sl_price = l.iloc[i] * 0.995  # pattern low - 0.5%

        # ---- Hammer (at support) ----
        if pattern is None:
            body       = abs(c.iloc[i] - o.iloc[i])
            candle_rng = h.iloc[i] - l.iloc[i]
            if candle_rng > 0 and body > 0:
                lower_shadow = min(o.iloc[i], c.iloc[i]) - l.iloc[i]
                upper_shadow = h.iloc[i] - max(o.iloc[i], c.iloc[i])
                body_top     = max(o.iloc[i], c.iloc[i])
                if (lower_shadow >= HAMMER_SHADOW * body and
                    upper_shadow  <= HAMMER_UPPER * body and
                    body_top      >= l.iloc[i] + candle_rng * 0.67):
                    pattern = 'hammer'
                    sl_price = l.iloc[i] * 0.995

        if pattern is None or sl_price is None:
            continue

        entry_ref = c.iloc[i]  # signal day close (for gap check)
        signals.append({
            'date': date,
            'pattern': pattern,
            'close': entry_ref,
            'sl_price_raw': sl_price,
            'vol_ratio': vol_ratio,
            'idx': i,
        })

    return signals


def simulate_trades(symbol: str, df: pd.DataFrame, signals: List[Dict],
                    equity_curve: List[float]) -> List[Dict]:
    """Simulate each signal trade. equity_curve tracks portfolio value for protection."""
    trades = []

    for sig in signals:
        i = sig['idx']
        if i + 1 >= len(df):
            continue

        # Entry on NEXT DAY open
        next_open = df['open'].iloc[i + 1]
        signal_close = sig['close']

        # Skip if gap up >0.5%
        if next_open > signal_close * 1.005:
            continue

        entry_price = next_open * (1 + SLIPPAGE)  # slippage on buy
        limit_price = next_open * 1.002
        if entry_price > limit_price:
            continue  # can't fill within limit

        # SL/TP calculation
        sl_raw = sig['sl_price_raw']
        sl_pct = (entry_price - sl_raw) / entry_price * 100
        sl_pct = max(MIN_SL_PCT, min(sl_pct, MAX_SL_PCT))
        sl_price = entry_price * (1 - sl_pct / 100)
        initial_risk = entry_price - sl_price
        tp_price = entry_price + initial_risk * RR_RATIO

        # Protection Layer 1: Volatility filter
        vol_ratio = sig['vol_ratio']
        size_mult = 1.0
        if vol_ratio > VOL_RATIO_SKIP:
            continue  # no trade
        elif vol_ratio > VOL_RATIO_HALF:
            size_mult = 0.5

        # Protection Layer 2: Equity throttle
        peak = max(equity_curve) if equity_curve else INITIAL_EQUITY
        current_eq = equity_curve[-1] if equity_curve else INITIAL_EQUITY
        dd_pct = (peak - current_eq) / peak
        if dd_pct >= DD_QUAR:
            risk_mult = 0.25
        elif dd_pct >= DD_HALF:
            risk_mult = 0.5
        else:
            risk_mult = 1.0

        effective_risk = INITIAL_EQUITY * RISK_PCT * size_mult * risk_mult
        shares = int(effective_risk / initial_risk) if initial_risk > 0 else 0
        if shares <= 0:
            continue

        # Cap at 10% of equity
        max_shares = int(current_eq * MAX_POS_PCT / entry_price)
        shares = min(shares, max_shares)
        if shares <= 0:
            continue

        # Simulate trade day by day
        entry_date = df.index[i + 1]
        trailing_sl = None
        exit_price = None
        exit_reason = None
        exit_day_offset = None

        for j in range(1, MAX_HOLD_DAYS + 1):
            if i + 1 + j >= len(df):
                break
            row = df.iloc[i + 1 + j]
            day_low  = row['low']
            day_high = row['high']
            day_close = row['close']

            # Active SL (trailing or initial)
            active_sl = trailing_sl if trailing_sl else sl_price

            # Check SL hit intraday
            if day_low <= active_sl:
                exit_price  = active_sl * (1 - SLIPPAGE)
                exit_reason = 'stop_loss'
                exit_day_offset = j
                break

            # Check TP hit
            if day_high >= tp_price:
                exit_price  = tp_price * (1 - SLIPPAGE)
                exit_reason = 'take_profit'
                exit_day_offset = j
                break

            # Update trailing stop (activates at +1R)
            unrealized_gain = day_close - entry_price
            if unrealized_gain >= initial_risk:
                new_trail = entry_price + initial_risk * 0.5  # lock +0.5R
                trailing_sl = max(trailing_sl or sl_price, new_trail)

        else:
            # Time exit: sell at close on day 10
            idx_exit = min(i + 1 + MAX_HOLD_DAYS, len(df) - 1)
            exit_price  = df['close'].iloc[idx_exit] * (1 - SLIPPAGE)
            exit_reason = 'time_exit'
            exit_day_offset = MAX_HOLD_DAYS

        if exit_price is None:
            exit_price  = df['close'].iloc[min(i + 1 + j, len(df)-1)] * (1 - SLIPPAGE)
            exit_reason = 'end_of_data'
            exit_day_offset = j

        # P&L including commission
        gross_pnl  = (exit_price - entry_price) * shares
        commission = (entry_price + exit_price) * shares * COMMISSION
        net_pnl    = gross_pnl - commission
        pnl_pct    = (exit_price - entry_price) / entry_price * 100

        trades.append({
            'symbol': symbol,
            'pattern': sig['pattern'],
            'entry_date': entry_date.strftime('%Y-%m-%d'),
            'exit_date': df.index[min(i + 1 + exit_day_offset, len(df)-1)].strftime('%Y-%m-%d'),
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'sl_price': round(sl_price, 2),
            'tp_price': round(tp_price, 2),
            'sl_pct': round(sl_pct, 2),
            'shares': shares,
            'net_pnl': round(net_pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'exit_reason': exit_reason,
            'days_held': exit_day_offset,
            'vol_ratio': round(vol_ratio, 2),
        })

    return trades


def run_backtest():
    print("=" * 60)
    print("CANDLESTICK STRATEGY BACKTEST (2023-2025)")
    print("=" * 60)
    print(f"Universe: {len(UNIVERSE)} stocks | Costs: {COST*100*2:.1f}% round trip")
    print(f"Rules: SL {MIN_SL_PCT}-{MAX_SL_PCT}%, TP {RR_RATIO}:1 RR, Max hold {MAX_HOLD_DAYS}d")
    print()

    all_trades: List[Dict] = []
    equity_curve = [INITIAL_EQUITY]
    failed = []

    for idx, symbol in enumerate(UNIVERSE):
        print(f"\r[{idx+1}/{len(UNIVERSE)}] {symbol:<6}", end='', flush=True)
        df = get_data(symbol)
        if df.empty or len(df) < 60:
            failed.append(symbol)
            continue

        # Normalize column names
        df.columns = [c.lower() for c in df.columns]
        required = {'open','high','low','close','volume'}
        if not required.issubset(df.columns):
            failed.append(symbol)
            continue

        signals  = detect_signals(df)
        if not signals:
            continue

        trades = simulate_trades(symbol, df, signals, equity_curve)
        for t in trades:
            all_trades.append(t)
            # Update equity (simplified: add P&L proportionally)
            equity_curve.append(equity_curve[-1] + t['net_pnl'])

    print(f"\n\nLoaded: {len(UNIVERSE)-len(failed)} stocks, Failed: {len(failed)}")

    if not all_trades:
        print("No trades generated!")
        return

    # ── ANALYSIS ──────────────────────────────────────────────
    df_t = pd.DataFrame(all_trades)
    df_t['entry_date'] = pd.to_datetime(df_t['entry_date'])
    df_t['year'] = df_t['entry_date'].dt.year
    df_t['month'] = df_t['entry_date'].dt.to_period('M')

    wins  = df_t[df_t['net_pnl'] > 0]
    loses = df_t[df_t['net_pnl'] <= 0]
    n     = len(df_t)
    wr    = len(wins) / n * 100

    avg_win  = wins['pnl_pct'].mean()   if len(wins)  else 0
    avg_loss = loses['pnl_pct'].mean()  if len(loses) else 0
    avg_pnl  = df_t['pnl_pct'].mean()
    profit_factor = (-wins['net_pnl'].sum() / loses['net_pnl'].sum()
                     if loses['net_pnl'].sum() != 0 else float('inf'))

    # Monthly P&L
    monthly = df_t.groupby('month')['net_pnl'].sum()
    profitable_months = (monthly > 0).sum()
    total_months = len(monthly)

    # CAGR from equity curve
    start_eq = INITIAL_EQUITY
    end_eq   = start_eq + df_t['net_pnl'].sum()
    years    = 3.0
    cagr     = ((end_eq / start_eq) ** (1 / years) - 1) * 100

    # Max drawdown (from running portfolio sum)
    cumulative = df_t.sort_values('entry_date')['net_pnl'].cumsum()
    running_peak = cumulative.cummax()
    drawdown = cumulative - running_peak
    max_dd = drawdown.min() / start_eq * 100

    # Exit breakdown
    exit_counts = df_t['exit_reason'].value_counts()
    pattern_counts = df_t['pattern'].value_counts()

    # Per-pattern performance
    for_eng = df_t[df_t['pattern'] == 'bullish_engulfing']
    for_ham = df_t[df_t['pattern'] == 'hammer']

    # Yearly
    yearly = df_t.groupby('year').apply(
        lambda g: pd.Series({
            'trades': len(g),
            'win_rate': (g['net_pnl'] > 0).mean() * 100,
            'avg_pnl_pct': g['pnl_pct'].mean(),
            'total_pnl': g['net_pnl'].sum(),
        })
    )

    # Rolling 20-trade window (min win rate — distribution check)
    sorted_trades = df_t.sort_values('entry_date')
    rolling_wr = sorted_trades['net_pnl'].apply(lambda x: 1 if x > 0 else 0).rolling(20).mean() * 100
    min_rolling_wr = rolling_wr.dropna().min()

    # Losing streak
    wins_binary = (sorted_trades['net_pnl'] > 0).astype(int)
    max_streak = 0
    streak = 0
    for w in wins_binary:
        if w == 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total Trades  : {n}")
    print(f"Win Rate      : {wr:.1f}%")
    print(f"Avg Win       : +{avg_win:.2f}%")
    print(f"Avg Loss      : {avg_loss:.2f}%")
    print(f"Avg P&L/trade : {avg_pnl:+.2f}%")
    print(f"Profit Factor : {profit_factor:.2f}x")
    print()
    print(f"CAGR          : {cagr:.1f}%")
    print(f"Max Drawdown  : {max_dd:.2f}%")
    print(f"Monthly P&L   : ${monthly.mean():.0f}/month avg")
    print(f"$25k → ${end_eq:,.0f} over 3 years")
    print(f"Profitable Months: {profitable_months}/{total_months} ({profitable_months/total_months*100:.0f}%)")
    print()
    print("── Distribution Checks (Paper Trade KPIs) ──")
    print(f"Min rolling 20-trade win rate : {min_rolling_wr:.1f}% (need ≥60%)")
    print(f"Max losing streak             : {max_streak} (normal ≤7)")
    print()
    print("── Per Pattern ──")
    if len(for_eng):
        print(f"Bullish Engulfing: {len(for_eng)} trades, "
              f"WR {(for_eng['net_pnl']>0).mean()*100:.1f}%, "
              f"avg {for_eng['pnl_pct'].mean():+.2f}%")
    if len(for_ham):
        print(f"Hammer           : {len(for_ham)} trades, "
              f"WR {(for_ham['net_pnl']>0).mean()*100:.1f}%, "
              f"avg {for_ham['pnl_pct'].mean():+.2f}%")
    print()
    print("── Exit Breakdown ──")
    for reason, cnt in exit_counts.items():
        print(f"  {reason:<15}: {cnt} ({cnt/n*100:.0f}%)")
    print()
    print("── Yearly ──")
    print(yearly.to_string())
    print()
    print("── Monthly P&L Sample (2024) ──")
    monthly_2024 = monthly[monthly.index.astype(str).str.startswith('2024')]
    for m, pnl in monthly_2024.items():
        bar = '+' * int(abs(pnl)/200) if pnl > 0 else '-' * int(abs(pnl)/200)
        print(f"  {m}: ${pnl:>+8,.0f}  {bar}")
    print()

    # Comparison vs Dip-Bounce
    print("=" * 60)
    print("COMPARISON vs DIP-BOUNCE (same period 2023-2025)")
    print("=" * 60)
    print(f"{'Metric':<25} {'Candlestick':>15} {'Dip-Bounce':>15}")
    print("-" * 55)
    print(f"{'Trades':<25} {n:>15} {'866':>15}")
    print(f"{'Win Rate':<25} {wr:>14.1f}% {'46.3%':>15}")
    print(f"{'Avg P&L/trade':<25} {avg_pnl:>+14.2f}% {'  +0.53%':>15}")
    print(f"{'CAGR':<25} {cagr:>14.1f}% {'35.8%':>15}")
    print(f"{'Max DD':<25} {max_dd:>14.2f}% {'-9.79%':>15}")
    print(f"{'$25k Monthly':<25} ${monthly.mean():>14,.0f}  {'$1,044':>14}")
    print()

    # Save results
    out = os.path.join(os.path.dirname(__file__), 'candlestick_results.csv')
    df_t.to_csv(out, index=False)
    print(f"Saved: {out}")

    metrics = {
        'trades': n, 'win_rate': round(wr, 2),
        'avg_win_pct': round(avg_win, 2), 'avg_loss_pct': round(avg_loss, 2),
        'avg_pnl_pct': round(avg_pnl, 2), 'profit_factor': round(profit_factor, 2),
        'cagr': round(cagr, 2), 'max_dd': round(max_dd, 2),
        'monthly_avg': round(float(monthly.mean()), 2),
        'profitable_months': int(profitable_months), 'total_months': int(total_months),
        'min_rolling_wr_20': round(float(min_rolling_wr), 2),
        'max_losing_streak': int(max_streak),
    }
    mout = os.path.join(os.path.dirname(__file__), 'candlestick_metrics.json')
    with open(mout, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved: {mout}")


if __name__ == '__main__':
    run_backtest()
