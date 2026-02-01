#!/usr/bin/env python3
"""
MULTI-DIMENSIONAL TEST - ทดสอบทุกมิติ

"เทสหลายๆแบบหลายๆมิติ เราก็จะรู้เองว่าแบบไหนคือแบบที่ถูกต้องเแม่นยำ"

มิติที่ทดสอบ:
1. Time periods (different months/years)
2. Market conditions (bull/bear/neutral)
3. Sectors (which ones perform best)
4. Hold periods (1, 3, 5, 10, 20 days)
5. Stop-loss levels (-1%, -2%, -3%, -5%)
6. Number of picks (top 3, 5, 10)
7. Criteria strictness (loose/normal/strict)
8. Entry timing (any day vs Monday only)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    exit(1)


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_accumulation(closes, volumes, period=20):
    if len(closes) < period:
        return 1.0
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


def calculate_atr_pct(closes, highs, lows, period=14):
    if len(closes) < period + 1:
        return 5.0
    tr = []
    for i in range(-period, 0):
        tr.append(max(
            float(highs[i]) - float(lows[i]),
            abs(float(highs[i]) - float(closes[i-1])),
            abs(float(lows[i]) - float(closes[i-1]))
        ))
    atr = np.mean(tr)
    price = float(closes[-1])
    return (atr / price) * 100 if price > 0 else 5.0


def run_test(stock_data, spy, spy_ma20, symbols, config):
    """Run one backtest with given config"""
    avoid_months = config.get('avoid_months', [10, 11])
    hold_days = config.get('hold_days', 5)
    stop_loss = config.get('stop_loss', -2.0)
    top_n = config.get('top_n', 5)
    accum_min = config.get('accum_min', 1.2)
    rsi_max = config.get('rsi_max', 58)
    atr_max = config.get('atr_max', 3.0)
    market_filter = config.get('market_filter', True)

    trading_dates = spy.index[60:]
    weekly_dates = trading_dates[::5]

    all_trades = []

    for entry_date in weekly_dates[:-5]:
        # Market filter
        if market_filter:
            try:
                spy_close = spy.loc[entry_date, 'Close']
                spy_ma = spy_ma20.loc[entry_date]
                if pd.isna(spy_ma) or spy_close < spy_ma:
                    continue
            except:
                continue

        # Month filter
        if entry_date.month in avoid_months:
            continue

        # Score stocks
        picks = []
        for symbol in symbols:
            if symbol not in stock_data:
                continue
            df = stock_data[symbol]
            mask = df.index <= entry_date
            df_to_date = df[mask]
            if len(df_to_date) < 55:
                continue

            closes = df_to_date['Close'].values.flatten()
            volumes = df_to_date['Volume'].values.flatten()
            highs = df_to_date['High'].values.flatten()
            lows = df_to_date['Low'].values.flatten()

            price = float(closes[-1])
            ma20 = float(np.mean(closes[-20:]))
            ma50 = float(np.mean(closes[-50:]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100
            rsi = calculate_rsi(closes)
            accum = calculate_accumulation(closes, volumes)
            atr_pct = calculate_atr_pct(closes, highs, lows)

            if accum <= accum_min:
                continue
            if rsi >= rsi_max:
                continue
            if above_ma20 <= 0 or above_ma50 <= 0:
                continue
            if atr_pct > atr_max:
                continue

            score = accum * 20 + (60 - rsi) + above_ma20 * 2
            picks.append({'symbol': symbol, 'score': score, 'price': price})

        picks = sorted(picks, key=lambda x: x['score'], reverse=True)[:top_n]

        for pick in picks:
            symbol = pick['symbol']
            df = stock_data[symbol]

            try:
                entry_idx = df.index.get_loc(entry_date)
            except:
                continue

            if entry_idx + hold_days >= len(df):
                continue

            entry_price = float(df.iloc[entry_idx]['Close'])
            stop_price = entry_price * (1 + stop_loss / 100)

            for j in range(1, hold_days + 1):
                day_low = float(df.iloc[entry_idx + j]['Low'])
                if day_low <= stop_price:
                    pct_return = stop_loss
                    break
            else:
                exit_price = float(df.iloc[entry_idx + hold_days]['Close'])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({'return': pct_return})

    if not all_trades:
        return None

    df_trades = pd.DataFrame(all_trades)
    total = len(df_trades)
    winners = len(df_trades[df_trades['return'] > 0])
    total_return = df_trades['return'].sum()

    return {
        'trades': total,
        'win_rate': winners / total * 100 if total > 0 else 0,
        'total_return': total_return,
        'avg_return': df_trades['return'].mean(),
    }


def main():
    """Run multi-dimensional tests"""
    print("=" * 70)
    print("MULTI-DIMENSIONAL TEST")
    print("=" * 70)
    print("\n\"เทสหลายๆแบบหลายๆมิติ เราจะรู้ว่าแบบไหนถูกต้อง\"")

    # Download data
    print("\n1. Downloading data (12 months)...")
    UNIVERSE = [
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE',
        'JPM', 'BAC', 'GS', 'V', 'MA', 'AXP', 'BLK', 'SCHW',
        'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY',
        'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD',
    ]

    end = datetime.now()
    start = end - timedelta(days=365 + 60)

    stock_data = {}
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=start, end=end, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                stock_data[symbol] = df
        except:
            pass

    spy = yf.download('SPY', start=start, end=end, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_ma20 = spy['Close'].rolling(20).mean()

    print(f"   Downloaded: {len(stock_data)} stocks")

    # ===== DIMENSION 1: HOLD PERIODS =====
    print("\n" + "=" * 70)
    print("DIMENSION 1: HOLD PERIODS")
    print("=" * 70)

    hold_results = []
    for hold in [3, 5, 10, 20]:
        result = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()),
                         {'hold_days': hold})
        if result:
            hold_results.append((hold, result))
            print(f"  {hold} days: {result['avg_return']:+.2f}% avg, "
                  f"{result['win_rate']:.0f}% WR, {result['trades']} trades")

    best_hold = max(hold_results, key=lambda x: x[1]['avg_return'])
    print(f"\n  BEST: {best_hold[0]} days ({best_hold[1]['avg_return']:+.2f}% avg)")

    # ===== DIMENSION 2: STOP-LOSS LEVELS =====
    print("\n" + "=" * 70)
    print("DIMENSION 2: STOP-LOSS LEVELS")
    print("=" * 70)

    stop_results = []
    for stop in [-1.0, -2.0, -3.0, -5.0]:
        result = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()),
                         {'stop_loss': stop})
        if result:
            stop_results.append((stop, result))
            print(f"  {stop}%: {result['avg_return']:+.2f}% avg, "
                  f"{result['win_rate']:.0f}% WR")

    best_stop = max(stop_results, key=lambda x: x[1]['avg_return'])
    print(f"\n  BEST: {best_stop[0]}% ({best_stop[1]['avg_return']:+.2f}% avg)")

    # ===== DIMENSION 3: TOP N PICKS =====
    print("\n" + "=" * 70)
    print("DIMENSION 3: NUMBER OF PICKS")
    print("=" * 70)

    topn_results = []
    for n in [3, 5, 10, 15]:
        result = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()),
                         {'top_n': n})
        if result:
            topn_results.append((n, result))
            print(f"  Top {n}: {result['avg_return']:+.2f}% avg, "
                  f"{result['win_rate']:.0f}% WR, {result['trades']} trades")

    best_n = max(topn_results, key=lambda x: x[1]['avg_return'])
    print(f"\n  BEST: Top {best_n[0]} ({best_n[1]['avg_return']:+.2f}% avg)")

    # ===== DIMENSION 4: CRITERIA STRICTNESS =====
    print("\n" + "=" * 70)
    print("DIMENSION 4: CRITERIA STRICTNESS")
    print("=" * 70)

    criteria = [
        ('Loose', {'accum_min': 1.1, 'rsi_max': 60, 'atr_max': 3.5}),
        ('Normal', {'accum_min': 1.2, 'rsi_max': 58, 'atr_max': 3.0}),
        ('Strict', {'accum_min': 1.3, 'rsi_max': 55, 'atr_max': 2.5}),
        ('Very Strict', {'accum_min': 1.5, 'rsi_max': 52, 'atr_max': 2.0}),
    ]

    criteria_results = []
    for name, config in criteria:
        result = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()), config)
        if result:
            criteria_results.append((name, result))
            print(f"  {name}: {result['avg_return']:+.2f}% avg, "
                  f"{result['win_rate']:.0f}% WR, {result['trades']} trades")

    best_criteria = max(criteria_results, key=lambda x: x[1]['avg_return'])
    print(f"\n  BEST: {best_criteria[0]} ({best_criteria[1]['avg_return']:+.2f}% avg)")

    # ===== DIMENSION 5: SECTORS =====
    print("\n" + "=" * 70)
    print("DIMENSION 5: SECTOR PERFORMANCE")
    print("=" * 70)

    sectors = {
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE'],
        'Finance': ['JPM', 'BAC', 'GS', 'V', 'MA', 'AXP', 'BLK', 'SCHW'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY'],
        'Tech': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD'],
    }

    sector_results = []
    for sector, symbols in sectors.items():
        available = [s for s in symbols if s in stock_data]
        if len(available) < 3:
            continue
        result = run_test(stock_data, spy, spy_ma20, available, {})
        if result:
            sector_results.append((sector, result))
            print(f"  {sector}: {result['avg_return']:+.2f}% avg, "
                  f"{result['win_rate']:.0f}% WR")

    best_sector = max(sector_results, key=lambda x: x[1]['avg_return'])
    print(f"\n  BEST: {best_sector[0]} ({best_sector[1]['avg_return']:+.2f}% avg)")

    # ===== DIMENSION 6: MARKET FILTER =====
    print("\n" + "=" * 70)
    print("DIMENSION 6: MARKET FILTER")
    print("=" * 70)

    result_with = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()),
                          {'market_filter': True})
    result_without = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()),
                             {'market_filter': False})

    if result_with and result_without:
        print(f"  With market filter: {result_with['avg_return']:+.2f}% avg")
        print(f"  Without filter: {result_without['avg_return']:+.2f}% avg")
        print(f"\n  BEST: {'With filter' if result_with['avg_return'] > result_without['avg_return'] else 'Without'}")

    # ===== OPTIMAL CONFIGURATION =====
    print("\n" + "=" * 70)
    print("OPTIMAL CONFIGURATION")
    print("=" * 70)

    optimal = {
        'hold_days': best_hold[0],
        'stop_loss': best_stop[0],
        'top_n': best_n[0],
        'accum_min': dict(criteria)[best_criteria[0]]['accum_min'] if best_criteria else 1.2,
        'rsi_max': dict(criteria)[best_criteria[0]]['rsi_max'] if best_criteria else 58,
        'atr_max': dict(criteria)[best_criteria[0]]['atr_max'] if best_criteria else 3.0,
        'market_filter': True,
        'avoid_months': [10, 11],
    }

    print(f"""
Based on multi-dimensional testing:

Hold Period: {optimal['hold_days']} days
Stop-Loss: {optimal['stop_loss']}%
Top Picks: {optimal['top_n']}
Accum Min: {optimal['accum_min']}
RSI Max: {optimal['rsi_max']}
ATR Max: {optimal['atr_max']}%
Market Filter: {optimal['market_filter']}
Avoid Months: Oct, Nov
Best Sector: {best_sector[0]}
""")

    # Run with optimal config
    print("Testing optimal configuration...")
    result = run_test(stock_data, spy, spy_ma20, list(stock_data.keys()), optimal)
    if result:
        print(f"\nRESULT: {result['avg_return']:+.2f}% avg per trade")
        print(f"Win Rate: {result['win_rate']:.0f}%")
        print(f"Total Trades: {result['trades']}")


if __name__ == '__main__':
    main()
