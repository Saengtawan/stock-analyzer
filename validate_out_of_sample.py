#!/usr/bin/env python3
"""
Out-of-Sample Validation - ทดสอบกลยุทธ์ v12.0 บนข้อมูลที่ไม่เคยเห็น

เป้าหมาย: ยืนยันว่าผลลัพธ์ 20%/month ไม่ใช่ overfitting
วิธีการ: ทดสอบบน 2 ปีย้อนหลังแทน 1 ปี
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')


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
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
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


def calculate_atr_pct(closes, highs, lows, i, period=14):
    if i < period:
        return 5.0
    tr = []
    for j in range(i - period + 1, i + 1):
        if j > 0:
            tr.append(max(
                float(highs[j]) - float(lows[j]),
                abs(float(highs[j]) - float(closes[j-1])),
                abs(float(lows[j]) - float(closes[j-1]))
            ))
    atr = np.mean(tr) if tr else 0
    price = float(closes[i])
    return (atr / price) * 100 if price > 0 else 5.0


def run_backtest(stock_data, spy, spy_ma20, config, avoid_months, period_name):
    """Run backtest on given data"""
    all_trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))
        hold_days = config['hold_days']

        for i in range(55, n - hold_days - 1):
            price = float(closes[i])
            entry_date = dates[i]

            # Filter 1: Market trend (SPY > MA20)
            try:
                spy_close = spy.loc[entry_date, 'Close']
                spy_ma = spy_ma20.loc[entry_date]
                if pd.isna(spy_ma) or spy_close < spy_ma:
                    continue
            except:
                continue

            # Filter 2: Avoid bad months
            if entry_date.month in avoid_months:
                continue

            # Technical gates (v12.0)
            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

            # v12.0 gates
            if accum <= config['accum_min']:
                continue
            if rsi >= config['rsi_max']:
                continue
            if above_ma20 <= config['ma20_min']:
                continue
            if above_ma50 <= config['ma50_min']:
                continue
            if atr_pct > config['atr_max']:
                continue

            # Trade with stop-loss
            entry_price = price
            stop_price = entry_price * (1 + config['stop_pct'] / 100)

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break
                day_low = float(lows[i + j])
                if day_low <= stop_price:
                    pct_return = config['stop_pct']
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'date': entry_date,
                'return': pct_return
            })

    if not all_trades:
        return None

    df_trades = pd.DataFrame(all_trades)
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    return df_trades


def main():
    print("=" * 80)
    print("OUT-OF-SAMPLE VALIDATION - v12.0 Factor-Based Strategy")
    print("=" * 80)

    # v12.0 config
    CONFIG = {
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    AVOID_MONTHS = [10, 11]  # Oct, Nov

    # Good sectors only
    SECTORS = {
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE'],
        'Finance': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP'],
    }

    all_symbols = []
    for stocks in SECTORS.values():
        all_symbols.extend(stocks)

    print(f"\n1. Download 2-year data for {len(all_symbols)} stocks...")

    # Download 2 years of data
    stock_data = {}
    for sym in all_symbols:
        try:
            df = yf.download(sym, period='2y', progress=False)
            if df.empty or len(df) < 200:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"   Downloaded: {len(stock_data)} stocks")

    # Download SPY 2 years
    print("\n2. Download SPY (market trend)...")
    spy = yf.download('SPY', period='2y', progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_ma20 = spy['Close'].rolling(20).mean()

    # Split data into periods
    all_dates = spy.index
    mid_point = len(all_dates) // 2

    # Period 1: First year (out-of-sample - we never tested on this)
    # Period 2: Second year (in-sample - this is what we trained on)

    print("\n3. Split data into 2 periods...")

    results = []

    for period_idx, (start_idx, end_idx, period_name) in enumerate([
        (0, mid_point, "Year 1 (Out-of-Sample)"),
        (mid_point, len(all_dates), "Year 2 (In-Sample)")
    ]):
        period_start = all_dates[start_idx]
        period_end = all_dates[end_idx - 1]

        # Filter stock data for this period
        period_stock_data = {}
        for sym, df in stock_data.items():
            mask = (df.index >= period_start) & (df.index <= period_end)
            period_df = df[mask].copy()
            if len(period_df) >= 100:
                period_stock_data[sym] = period_df

        # Filter SPY for this period
        period_spy = spy[(spy.index >= period_start) & (spy.index <= period_end)]
        period_spy_ma20 = spy_ma20[(spy_ma20.index >= period_start) & (spy_ma20.index <= period_end)]

        # Run backtest
        df_trades = run_backtest(
            period_stock_data, period_spy, period_spy_ma20,
            CONFIG, AVOID_MONTHS, period_name
        )

        if df_trades is not None and len(df_trades) > 0:
            total = len(df_trades)
            winners = len(df_trades[df_trades['return'] > 0])
            total_return = df_trades['return'].sum()

            df_trades['month'] = df_trades['date'].dt.to_period('M')
            n_months = len(df_trades['month'].unique())
            monthly_avg = total_return / n_months if n_months > 0 else 0

            results.append({
                'period': period_name,
                'start': period_start.strftime('%Y-%m-%d'),
                'end': period_end.strftime('%Y-%m-%d'),
                'trades': total,
                'win_rate': winners/total*100,
                'total_return': total_return,
                'monthly_avg': monthly_avg,
                'months': n_months
            })

            print(f"\n   {period_name}:")
            print(f"   Period: {period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}")
            print(f"   Trades: {total}")
            print(f"   Win Rate: {winners/total*100:.1f}%")
            print(f"   Monthly Return: {monthly_avg:+.2f}%")
        else:
            print(f"\n   {period_name}: No trades found")

    # Summary comparison
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)

    if len(results) >= 2:
        oos = results[0]  # Out-of-sample
        ins = results[1]  # In-sample

        print(f"""
Comparison:
                        Out-of-Sample    In-Sample
                        (Year 1)         (Year 2)
Period:                 {oos['start'][:7]} to {oos['end'][:7]}    {ins['start'][:7]} to {ins['end'][:7]}
Trades:                 {oos['trades']:>8}         {ins['trades']:>8}
Win Rate:               {oos['win_rate']:>7.1f}%        {ins['win_rate']:>7.1f}%
Monthly Return:         {oos['monthly_avg']:>+7.2f}%       {ins['monthly_avg']:>+7.2f}%
""")

        # Verdict
        print("=" * 80)
        print("VERDICT")
        print("=" * 80)

        # Check consistency
        oos_good = oos['monthly_avg'] > 5
        ins_good = ins['monthly_avg'] > 5
        consistency = abs(oos['monthly_avg'] - ins['monthly_avg']) < 10

        if oos_good and ins_good and consistency:
            print("""
VALIDATED - Strategy is consistent across different time periods

The out-of-sample results confirm the strategy works on unseen data.
This suggests the parameters are NOT overfitted to recent data.
""")
        elif oos_good:
            print(f"""
PARTIALLY VALIDATED - Out-of-sample is good

Out-of-sample: {oos['monthly_avg']:+.2f}%/month
In-sample: {ins['monthly_avg']:+.2f}%/month

Some variance between periods, but still profitable overall.
""")
        else:
            print(f"""
CAUTION - Possible overfitting detected

Out-of-sample: {oos['monthly_avg']:+.2f}%/month
In-sample: {ins['monthly_avg']:+.2f}%/month

The strategy may be overfitted to recent data.
Consider adjusting parameters.
""")

    print("\nNext steps:")
    print("1. If validated: Proceed with collecting additional data factors")
    print("2. If not validated: Revisit parameters and test more conservatively")


if __name__ == '__main__':
    main()
