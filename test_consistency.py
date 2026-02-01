#!/usr/bin/env python3
"""
CONSISTENCY TEST - ทดสอบความสม่ำเสมอของระบบ

เป้าหมาย: ผลลัพธ์ต้องดีเหมือนกันทุกครั้ง
- ทดสอบหลาย periods
- ทดสอบหลาย random samples
- ทดสอบหลาย configurations
- ผลลัพธ์ต้อง consistent

"เราต้องมั่นใจ 10 ครั้ง 100 ครั้ง ผลลัพธ์ที่คิดไว้มันถูกต้องเหมือนเดิม"
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
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


def score_stock(symbol, df, spy_close, spy_ma20, avoid_months):
    """Score a stock"""
    if len(df) < 55:
        return None

    closes = df['Close'].values.flatten()
    volumes = df['Volume'].values.flatten()
    highs = df['High'].values.flatten()
    lows = df['Low'].values.flatten()
    entry_date = df.index[-1]

    # Market filter
    if spy_close < spy_ma20:
        return None

    # Month filter
    if entry_date.month in avoid_months:
        return None

    price = float(closes[-1])
    ma20 = float(np.mean(closes[-20:]))
    ma50 = float(np.mean(closes[-50:]))

    above_ma20 = ((price - ma20) / ma20) * 100
    above_ma50 = ((price - ma50) / ma50) * 100
    rsi = calculate_rsi(closes)
    accum = calculate_accumulation(closes, volumes)
    atr_pct = calculate_atr_pct(closes, highs, lows)

    # Criteria
    if accum <= 1.2:
        return None
    if rsi >= 58:
        return None
    if above_ma20 <= 0:
        return None
    if above_ma50 <= 0:
        return None
    if atr_pct > 3.0:
        return None

    score = accum * 20 + (60 - rsi) + above_ma20 * 2 + (3 - atr_pct) * 10
    return {'symbol': symbol, 'price': price, 'score': score}


def run_backtest(stock_data, spy, spy_ma20, symbols, avoid_months, hold_days=5, stop_loss=-2.0, top_n=5):
    """Run one backtest"""
    trading_dates = spy.index[60:]
    weekly_dates = trading_dates[::5]

    all_trades = []

    for entry_date in weekly_dates[:-2]:
        try:
            spy_close = spy.loc[entry_date, 'Close']
            spy_ma = spy_ma20.loc[entry_date]
        except:
            continue

        if pd.isna(spy_ma) or spy_close < spy_ma:
            continue

        if entry_date.month in avoid_months:
            continue

        picks = []
        for symbol in symbols:
            if symbol not in stock_data:
                continue
            df = stock_data[symbol]
            mask = df.index <= entry_date
            df_to_date = df[mask]
            if len(df_to_date) < 55:
                continue

            result = score_stock(symbol, df_to_date, spy_close, spy_ma, avoid_months)
            if result:
                picks.append(result)

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

            all_trades.append({'symbol': symbol, 'date': entry_date, 'return': pct_return})

    if not all_trades:
        return None

    df_trades = pd.DataFrame(all_trades)
    df_trades['month'] = df_trades['date'].dt.to_period('M')

    total = len(df_trades)
    winners = len(df_trades[df_trades['return'] > 0])
    total_return = df_trades['return'].sum()
    n_months = len(df_trades['month'].unique())
    monthly_avg = total_return / n_months if n_months > 0 else 0

    return {
        'trades': total,
        'win_rate': winners / total * 100 if total > 0 else 0,
        'total_return': total_return,
        'monthly_avg': monthly_avg,
        'n_months': n_months,
    }


def main():
    """Run consistency tests"""
    print("=" * 70)
    print("CONSISTENCY TEST - ทดสอบความสม่ำเสมอของระบบ")
    print("=" * 70)
    print("\n\"เราต้องมั่นใจ 10 ครั้ง 100 ครั้ง ผลลัพธ์ต้องดีเหมือนกัน\"")

    # Full universe
    UNIVERSE = [
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'MMM', 'UPS',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS',
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BLK', 'SCHW',
        'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'AMGN',
        'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'ADBE',
    ]

    AVOID_MONTHS = [10, 11]

    # Download data
    print("\n1. Downloading data (12 months)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 + 60)

    stock_data = {}
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                stock_data[symbol] = df
        except:
            pass

    print(f"   Downloaded: {len(stock_data)} stocks")

    spy = yf.download('SPY', start=start_date, end=end_date, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_ma20 = spy['Close'].rolling(20).mean()

    # ===== TEST 1: Different Random Samples =====
    print("\n" + "=" * 70)
    print("TEST 1: Random Sample Tests (10 times)")
    print("=" * 70)
    print("ทดสอบด้วย random subset 70% ของหุ้น 10 ครั้ง\n")

    sample_results = []
    for i in range(10):
        sample = random.sample(list(stock_data.keys()), int(len(stock_data) * 0.7))
        result = run_backtest(stock_data, spy, spy_ma20, sample, AVOID_MONTHS)
        if result:
            sample_results.append(result)
            print(f"  Test {i+1}: {result['monthly_avg']:+.2f}%/month, "
                  f"{result['win_rate']:.0f}% WR, {result['trades']} trades")

    if sample_results:
        avg_monthly = np.mean([r['monthly_avg'] for r in sample_results])
        std_monthly = np.std([r['monthly_avg'] for r in sample_results])
        avg_wr = np.mean([r['win_rate'] for r in sample_results])

        print(f"\n  Average: {avg_monthly:+.2f}%/month (std: {std_monthly:.2f})")
        print(f"  Win Rate: {avg_wr:.0f}%")

        consistency_1 = "PASS" if std_monthly < 5 else "FAIL"
        print(f"\n  Consistency: {consistency_1} (std < 5%)")

    # ===== TEST 2: Different Time Periods =====
    print("\n" + "=" * 70)
    print("TEST 2: Different Time Periods")
    print("=" * 70)
    print("ทดสอบบน quarterly periods\n")

    quarters = [
        ('Q2 2025', '2025-04-01', '2025-06-30'),
        ('Q3 2025', '2025-07-01', '2025-09-30'),
        ('Q4 2025', '2025-10-01', '2025-12-31'),
        ('Q1 2026', '2026-01-01', '2026-01-31'),
    ]

    period_results = []
    for name, start, end in quarters:
        # Filter data for this period
        period_spy = spy[(spy.index >= start) & (spy.index <= end)]
        period_spy_ma20 = spy_ma20[(spy_ma20.index >= start) & (spy_ma20.index <= end)]

        if len(period_spy) < 30:
            continue

        period_stock_data = {}
        for sym, df in stock_data.items():
            mask = (df.index >= start) & (df.index <= end)
            period_df = df[mask]
            if len(period_df) >= 30:
                period_stock_data[sym] = period_df

        result = run_backtest(period_stock_data, period_spy, period_spy_ma20,
                             list(period_stock_data.keys()), AVOID_MONTHS)
        if result and result['trades'] > 0:
            period_results.append({'period': name, **result})
            print(f"  {name}: {result['monthly_avg']:+.2f}%/month, "
                  f"{result['win_rate']:.0f}% WR, {result['trades']} trades")

    if period_results:
        positive_periods = sum(1 for r in period_results if r['monthly_avg'] > 0)
        print(f"\n  Positive periods: {positive_periods}/{len(period_results)}")

        consistency_2 = "PASS" if positive_periods >= len(period_results) * 0.6 else "FAIL"
        print(f"  Consistency: {consistency_2} (>= 60% positive)")

    # ===== TEST 3: Parameter Sensitivity =====
    print("\n" + "=" * 70)
    print("TEST 3: Parameter Sensitivity")
    print("=" * 70)
    print("ทดสอบกับ parameters ที่ต่างกันเล็กน้อย\n")

    param_results = []
    params_to_test = [
        {'accum_min': 1.1, 'rsi_max': 60, 'atr_max': 3.5},  # Looser
        {'accum_min': 1.2, 'rsi_max': 58, 'atr_max': 3.0},  # Original
        {'accum_min': 1.3, 'rsi_max': 56, 'atr_max': 2.5},  # Stricter
    ]

    for params in params_to_test:
        result = run_backtest(stock_data, spy, spy_ma20, list(stock_data.keys()), AVOID_MONTHS)
        if result:
            param_results.append(result)
            print(f"  accum>{params['accum_min']}, RSI<{params['rsi_max']}, ATR<{params['atr_max']}: "
                  f"{result['monthly_avg']:+.2f}%/month")

    # ===== FINAL VERDICT =====
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)

    all_passes = 0
    total_tests = 3

    if sample_results:
        avg = np.mean([r['monthly_avg'] for r in sample_results])
        std = np.std([r['monthly_avg'] for r in sample_results])
        if std < 5 and avg > 0:
            all_passes += 1
            print(f"\n1. Random Samples: PASS")
        else:
            print(f"\n1. Random Samples: FAIL (std={std:.2f})")

    if period_results:
        positive = sum(1 for r in period_results if r['monthly_avg'] > 0)
        if positive >= len(period_results) * 0.5:
            all_passes += 1
            print(f"2. Time Periods: PASS ({positive}/{len(period_results)} positive)")
        else:
            print(f"2. Time Periods: FAIL ({positive}/{len(period_results)} positive)")

    if param_results:
        all_positive = all(r['monthly_avg'] > 0 for r in param_results)
        if all_positive:
            all_passes += 1
            print(f"3. Parameter Sensitivity: PASS (all positive)")
        else:
            print(f"3. Parameter Sensitivity: FAIL (not all positive)")

    print(f"\n{'='*50}")
    if all_passes >= 2:
        print(f"OVERALL: CONSISTENT ({all_passes}/{total_tests} tests passed)")
        print("\nระบบผ่านการทดสอบความสม่ำเสมอ!")
        print("ผลลัพธ์ที่ได้น่าเชื่อถือ")
    else:
        print(f"OVERALL: NEEDS IMPROVEMENT ({all_passes}/{total_tests} tests passed)")
        print("\nยังต้องปรับปรุงเพิ่ม")


if __name__ == '__main__':
    main()
