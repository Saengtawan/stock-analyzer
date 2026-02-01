#!/usr/bin/env python3
"""
BACKTEST v2.1 ANTI-PDT vs v2.0

Compare:
- v2.0: Tight SL 1.5%, no entry filters
- v2.1: ATR-based SL 1.5-2.5%, anti-PDT filters

Focus on:
1. Same-day SL hits (PDT risk)
2. Win rate
3. Total return
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

# Universe
UNIVERSE = [
    'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
    'QCOM', 'AMAT', 'LRCX', 'KLAC',
    'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG',
    'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
    'CRM', 'NOW', 'SHOP',
    'RIVN', 'LCID', 'ENPH', 'FSLR',
]

MAX_DAYS = 4
TP_PCT = 4.0

def calculate_indicators(data, idx):
    """Calculate all indicators at index"""
    close = data['Close']
    high = data['High']
    low = data['Low']
    volume = data['Volume']

    current = close.iloc[idx]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).iloc[idx]

    # Momentum
    mom_1d = (current / close.iloc[idx-1] - 1) * 100 if idx >= 1 else 0
    mom_5d = (current / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
    mom_20d = (current / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0

    # ATR
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[idx]
    atr_pct = atr / current * 100

    # SMAs
    sma5 = close.iloc[idx-5:idx].mean() if idx >= 5 else current
    sma20 = close.iloc[idx-20:idx].mean() if idx >= 20 else current
    sma50 = close.iloc[idx-50:idx].mean() if idx >= 50 else current

    # Gap
    prev_close = close.iloc[idx-1] if idx >= 1 else current
    open_price = data['Open'].iloc[idx] if 'Open' in data.columns else current
    gap_pct = (open_price - prev_close) / prev_close * 100

    # Distance from high
    high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
    dist_from_high = (high_20d - current) / high_20d * 100

    return {
        'price': current,
        'rsi': rsi,
        'mom_1d': mom_1d,
        'mom_5d': mom_5d,
        'mom_20d': mom_20d,
        'atr_pct': atr_pct,
        'sma5': sma5,
        'sma20': sma20,
        'sma50': sma50,
        'gap_pct': gap_pct,
        'dist_from_high': dist_from_high,
    }

def check_entry_v20(ind):
    """v2.0 entry criteria (original tight SL)"""
    score = 0

    # Volatility
    if ind['atr_pct'] < 2.0:
        return False, 0

    # Pullback
    if -8 <= ind['mom_5d'] <= 0:
        score += 30
    elif 0 < ind['mom_5d'] <= 2:
        score += 15

    # RSI
    if 30 <= ind['rsi'] <= 55:
        score += 25
    elif ind['rsi'] < 30:
        score += 15

    # Trend
    if ind['price'] > ind['sma50'] and ind['mom_20d'] > 0:
        score += 20
    elif ind['price'] > ind['sma20']:
        score += 15

    # Volatility bonus
    if ind['atr_pct'] > 3:
        score += 10

    return score >= 60, score

def check_entry_v21(ind):
    """v2.1 entry criteria (anti-PDT)"""
    # ANTI-PDT FILTERS

    # Filter 1: Must be TRUE DIP (negative 1-day momentum)
    if ind['mom_1d'] > 0.5:
        return False, 0

    # Filter 2: Skip gap-up entries
    if ind['gap_pct'] > 1.5:
        return False, 0

    # Filter 3: Must be below SMA5
    if ind['price'] > ind['sma5'] * 1.01:
        return False, 0

    # Now score
    score = 0

    # Volatility
    if ind['atr_pct'] < 2.0:
        return False, 0

    # Pullback
    if -8 <= ind['mom_5d'] <= -3:
        score += 35
    elif -3 < ind['mom_5d'] <= 0:
        score += 25

    # 1-day dip bonus
    if ind['mom_1d'] <= -1.5:
        score += 15

    # RSI
    if 30 <= ind['rsi'] <= 55:
        score += 25
    elif ind['rsi'] < 30:
        score += 15

    # Trend
    if ind['price'] > ind['sma50'] and ind['mom_20d'] > 0:
        score += 20
    elif ind['price'] > ind['sma20']:
        score += 15

    # Volatility bonus
    if ind['atr_pct'] > 3:
        score += 10

    return score >= 60, score

def get_sl_v20(ind):
    """v2.0 SL: fixed 1.5%"""
    return 1.5

def get_sl_v21(ind):
    """v2.1 SL: ATR-based"""
    atr_pct = ind['atr_pct']
    if atr_pct > 5:
        return 2.5
    elif atr_pct > 4:
        return 2.0
    elif atr_pct > 3:
        return 1.75
    else:
        return 1.5

def simulate_trade(data, entry_idx, entry_price, sl_pct, tp_pct=TP_PCT, max_days=MAX_DAYS):
    """Simulate a single trade"""
    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    result = {
        'entry_price': entry_price,
        'sl_pct': sl_pct,
        'outcome': None,
        'exit_price': None,
        'days_held': 0,
        'pnl_pct': 0,
        'same_day_sl': False,
    }

    for i in range(entry_idx, min(entry_idx + max_days + 1, len(data))):
        row = data.iloc[i]
        days_held = i - entry_idx

        low = row['Low']
        high = row['High']
        close = row['Close']

        # Check SL
        if low <= sl_price:
            result['outcome'] = 'LOSS'
            result['exit_price'] = sl_price
            result['days_held'] = days_held
            result['pnl_pct'] = -sl_pct
            result['same_day_sl'] = (days_held == 0)
            return result

        # Check TP
        if high >= tp_price:
            result['outcome'] = 'WIN'
            result['exit_price'] = tp_price
            result['days_held'] = days_held
            result['pnl_pct'] = tp_pct
            return result

        # Time stop
        if days_held >= max_days:
            result['outcome'] = 'TIME_STOP'
            result['exit_price'] = close
            result['days_held'] = days_held
            result['pnl_pct'] = (close - entry_price) / entry_price * 100
            return result

    return result

def run_backtest(start_date, end_date):
    """Run backtest comparing v2.0 vs v2.1"""
    print("=" * 70)
    print("BACKTEST: v2.0 vs v2.1 ANTI-PDT")
    print("=" * 70)
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print()

    # Load data
    print("Loading data...")
    all_data = {}
    for symbol in UNIVERSE:
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date - timedelta(days=60), end=end_date + timedelta(days=10))
            if len(data) > 50:
                all_data[symbol] = data
        except:
            pass
    print(f"Loaded {len(all_data)} stocks")
    print()

    # Results
    v20_trades = []
    v21_trades = []

    # Simulate
    current = start_date
    while current <= end_date:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        for symbol, data in all_data.items():
            # Find entry index
            entry_idx = None
            for i, d in enumerate(data.index):
                if d.strftime('%Y-%m-%d') == current.strftime('%Y-%m-%d'):
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx < 50:
                continue

            # Calculate indicators
            ind = calculate_indicators(data, entry_idx)

            # v2.0 check
            v20_ok, v20_score = check_entry_v20(ind)
            if v20_ok:
                sl_pct = get_sl_v20(ind)
                result = simulate_trade(data, entry_idx, ind['price'], sl_pct)
                if result['outcome']:
                    result['symbol'] = symbol
                    result['date'] = current
                    result['version'] = 'v2.0'
                    v20_trades.append(result)

            # v2.1 check
            v21_ok, v21_score = check_entry_v21(ind)
            if v21_ok:
                sl_pct = get_sl_v21(ind)
                result = simulate_trade(data, entry_idx, ind['price'], sl_pct)
                if result['outcome']:
                    result['symbol'] = symbol
                    result['date'] = current
                    result['version'] = 'v2.1'
                    v21_trades.append(result)

        current += timedelta(days=1)

    return v20_trades, v21_trades

def analyze_results(v20_trades, v21_trades):
    """Analyze and compare results"""

    def calc_stats(trades, label):
        if not trades:
            return None

        wins = [t for t in trades if t['outcome'] == 'WIN']
        losses = [t for t in trades if t['outcome'] == 'LOSS']
        time_stops = [t for t in trades if t['outcome'] == 'TIME_STOP']
        same_day_sl = [t for t in losses if t.get('same_day_sl', False)]

        total_pnl = sum(t['pnl_pct'] for t in trades)
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        return {
            'label': label,
            'total': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'time_stops': len(time_stops),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / len(trades) if trades else 0,
            'same_day_sl': len(same_day_sl),
            'same_day_pct': len(same_day_sl) / len(losses) * 100 if losses else 0,
            'avg_sl_pct': sum(t['sl_pct'] for t in trades) / len(trades) if trades else 0,
        }

    v20_stats = calc_stats(v20_trades, 'v2.0 (Tight SL)')
    v21_stats = calc_stats(v21_trades, 'v2.1 (Anti-PDT)')

    # Print comparison
    print("=" * 70)
    print("COMPARISON: v2.0 vs v2.1")
    print("=" * 70)
    print()

    print(f"{'Metric':<25} {'v2.0 (Tight SL)':>18} {'v2.1 (Anti-PDT)':>18} {'Change':>12}")
    print("-" * 75)

    metrics = [
        ('Total Trades', 'total', ''),
        ('Winners', 'wins', ''),
        ('Losers', 'losses', ''),
        ('Win Rate', 'win_rate', '%'),
        ('Total P&L', 'total_pnl', '%'),
        ('Avg P&L/Trade', 'avg_pnl', '%'),
        ('Avg SL %', 'avg_sl_pct', '%'),
        ('Same-Day SL Hits', 'same_day_sl', ''),
        ('Same-Day SL %', 'same_day_pct', '%'),
    ]

    for label, key, suffix in metrics:
        v20_val = v20_stats[key] if v20_stats else 0
        v21_val = v21_stats[key] if v21_stats else 0

        if key in ['total', 'wins', 'losses', 'same_day_sl']:
            change = v21_val - v20_val
            change_str = f"{change:+d}"
        else:
            change = v21_val - v20_val
            change_str = f"{change:+.1f}{suffix}"

        print(f"{label:<25} {v20_val:>17.1f}{suffix} {v21_val:>17.1f}{suffix} {change_str:>12}")

    # PDT Risk Analysis
    print()
    print("=" * 70)
    print("⚠️  PDT RISK ANALYSIS")
    print("=" * 70)

    v20_pdt = v20_stats['same_day_sl'] if v20_stats else 0
    v21_pdt = v21_stats['same_day_sl'] if v21_stats else 0
    reduction = ((v20_pdt - v21_pdt) / v20_pdt * 100) if v20_pdt > 0 else 0

    print(f"v2.0 Same-Day SL Hits: {v20_pdt}")
    print(f"v2.1 Same-Day SL Hits: {v21_pdt}")
    print(f"Reduction: {reduction:.0f}%")
    print()

    if v21_pdt < v20_pdt:
        print(f"✅ v2.1 reduced same-day SL hits by {v20_pdt - v21_pdt} trades ({reduction:.0f}%)")
    else:
        print("⚠️  v2.1 did not reduce same-day SL hits")

    # Profitability check
    print()
    print("=" * 70)
    print("💰 PROFITABILITY CHECK")
    print("=" * 70)

    v20_profit = v20_stats['total_pnl'] if v20_stats else 0
    v21_profit = v21_stats['total_pnl'] if v21_stats else 0

    print(f"v2.0 Total P&L: {v20_profit:+.1f}%")
    print(f"v2.1 Total P&L: {v21_profit:+.1f}%")
    print()

    if v21_profit > v20_profit:
        print(f"✅ v2.1 is MORE profitable (+{v21_profit - v20_profit:.1f}%)")
    elif v21_profit > 0:
        print(f"✅ v2.1 is still profitable (slightly less: {v21_profit - v20_profit:.1f}%)")
    else:
        print(f"⚠️  v2.1 is less profitable ({v21_profit - v20_profit:.1f}%)")

    # Recommendation
    print()
    print("=" * 70)
    print("📋 RECOMMENDATION")
    print("=" * 70)

    if v21_pdt < v20_pdt and v21_profit > 0:
        print("✅ USE v2.1 - Lower PDT risk AND profitable")
    elif v21_pdt < v20_pdt:
        print("⚠️  v2.1 reduces PDT risk but may need tuning for profitability")
    else:
        print("⚠️  Need further analysis")

    # Days held distribution
    print()
    print("=" * 70)
    print("📊 DAYS HELD DISTRIBUTION (Losers)")
    print("=" * 70)

    def days_dist(trades):
        losses = [t for t in trades if t['outcome'] == 'LOSS']
        dist = defaultdict(int)
        for t in losses:
            dist[t['days_held']] += 1
        return dist

    v20_dist = days_dist(v20_trades)
    v21_dist = days_dist(v21_trades)

    print(f"{'Day':<6} {'v2.0':>12} {'v2.1':>12}")
    print("-" * 32)
    for day in range(5):
        v20_count = v20_dist.get(day, 0)
        v21_count = v21_dist.get(day, 0)
        print(f"Day {day:<3} {v20_count:>12} {v21_count:>12}")

    return v20_stats, v21_stats


if __name__ == "__main__":
    # 3 months backtest
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    v20_trades, v21_trades = run_backtest(start_date, end_date)

    print()
    analyze_results(v20_trades, v21_trades)
