#!/usr/bin/env python3
"""
FIXED BACKTEST: Volume Surge + Momentum Gates
Using proper historical data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import json
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


def main():
    print("=" * 80)
    print("FIXED BACKTEST: Volume Surge + Momentum Gates")
    print("=" * 80)

    # Use period='1y' to get actual available data
    symbols = [
        # Mega caps (most liquid, best data)
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'AVGO', 'CRM', 'ADBE', 'ORCL',
        'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
        'HD', 'LOW', 'COST', 'WMT', 'MCD', 'NKE',
        'CAT', 'DE', 'HON', 'GE', 'BA',
        'XOM', 'CVX', 'NFLX', 'DIS', 'T', 'VZ'
    ]

    print(f"\nDownloading {len(symbols)} stocks (1 year data)...")

    stock_data = {}
    for sym in symbols:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 100:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
            print(f"  {sym}: {len(df)} days, {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"  {sym}: Error - {e}")

    print(f"\nDownloaded: {len(stock_data)} stocks")

    if len(stock_data) == 0:
        print("No data available. Exiting.")
        return

    # Get actual date range from data
    first_sym = list(stock_data.keys())[0]
    actual_start = stock_data[first_sym].index[0]
    actual_end = stock_data[first_sym].index[-1]
    print(f"Data range: {actual_start.strftime('%Y-%m-%d')} to {actual_end.strftime('%Y-%m-%d')}")

    # Test configurations
    CONFIGS = [
        # v9.1 Baseline
        {
            'name': 'v9.1 Baseline (no stop)',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 0,
            'mom_3d_min': -999,
            'hold_days': 5,
            'stop_pct': None
        },
        # v9.1 + Stop-loss
        {
            'name': 'v9.1 + Stop -2%',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 0,
            'mom_3d_min': -999,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # v9.1 + Volume surge
        {
            'name': 'v9.1 + Vol>1.2',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': -999,
            'hold_days': 5,
            'stop_pct': None
        },
        # v9.1 + Volume + Stop
        {
            'name': 'v9.1 + Vol>1.2 + Stop -2%',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': -999,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # v9.1 + Vol + Mom3d
        {
            'name': 'v9.1 + Vol>1.2 + Mom3d>0',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': 0,
            'hold_days': 5,
            'stop_pct': None
        },
        # v9.1 + Vol + Mom3d + Stop
        {
            'name': 'v9.1 + Vol + Mom3d + Stop',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': 0,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # Relaxed + Vol (more signals)
        {
            'name': 'Relaxed + Vol>1.2',
            'accum_min': 1.1,
            'rsi_max': 60,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': 0,
            'hold_days': 5,
            'stop_pct': None
        },
        # Strict vol + mom3d
        {
            'name': 'Strict: Vol>1.5 + Mom3d>1',
            'accum_min': 1.2,
            'rsi_max': 57,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.5,
            'mom_3d_min': 1,
            'hold_days': 5,
            'stop_pct': None
        },
    ]

    results = []

    for config in CONFIGS:
        print(f"\n{'='*70}")
        print(f"Testing: {config['name']}")
        print(f"{'='*70}")

        all_trades = []

        for sym, df in stock_data.items():
            closes = df['Close'].values.flatten()
            volumes = df['Volume'].values.flatten()
            dates = df.index

            n = min(len(closes), len(volumes), len(dates))
            hold_days = config['hold_days']

            for i in range(55, n - hold_days - 1):
                price = float(closes[i])

                # MA calculations
                ma20 = float(np.mean(closes[i-19:i+1]))
                ma50 = float(np.mean(closes[i-49:i+1]))
                above_ma20 = ((price - ma20) / ma20) * 100
                above_ma50 = ((price - ma50) / ma50) * 100

                # RSI & Accumulation
                rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
                accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

                # Volume surge
                vol_avg = float(np.mean(volumes[i-19:i]))
                vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

                # 3-day momentum
                mom_3d = ((price - float(closes[i-3])) / float(closes[i-3])) * 100 if i >= 3 else 0

                # Apply gates
                if accum <= config['accum_min']:
                    continue
                if rsi >= config['rsi_max']:
                    continue
                if above_ma20 <= config['ma20_min']:
                    continue
                if above_ma50 <= config['ma50_min']:
                    continue
                if vol_surge < config['vol_surge_min']:
                    continue
                if mom_3d <= config['mom_3d_min']:
                    continue

                # Calculate return with optional stop-loss
                entry_price = price
                stop_pct = config.get('stop_pct')
                stopped = False
                exit_day = hold_days

                if stop_pct is not None:
                    stop_price = entry_price * (1 + stop_pct / 100)
                    for j in range(1, hold_days + 1):
                        if i + j >= n:
                            break
                        day_price = float(closes[i + j])
                        if day_price <= stop_price:
                            pct_return = stop_pct
                            stopped = True
                            exit_day = j
                            break
                    else:
                        exit_price = float(closes[i + hold_days])
                        pct_return = ((exit_price - entry_price) / entry_price) * 100
                else:
                    exit_price = float(closes[i + hold_days])
                    pct_return = ((exit_price - entry_price) / entry_price) * 100

                all_trades.append({
                    'symbol': sym,
                    'date': dates[i],
                    'return': pct_return,
                    'stopped': stopped,
                    'exit_day': exit_day,
                    'rsi': rsi,
                    'accum': accum,
                    'vol_surge': vol_surge,
                    'mom_3d': mom_3d
                })

        if not all_trades:
            print("  No trades generated")
            continue

        df_trades = pd.DataFrame(all_trades)

        # Deduplicate
        df_trades['week'] = df_trades['date'].dt.isocalendar().week
        df_trades['year'] = df_trades['date'].dt.year
        df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

        n_trades = len(df_trades)
        n_winners = len(df_trades[df_trades['return'] > 0])
        n_losers = len(df_trades[df_trades['return'] <= 0])
        n_stopped = len(df_trades[df_trades['stopped'] == True])
        avg_return = df_trades['return'].mean()
        max_loss = df_trades['return'].min()
        max_gain = df_trades['return'].max()

        result = {
            'config': config['name'],
            'trades': n_trades,
            'winners': n_winners,
            'losers': n_losers,
            'stopped': n_stopped,
            'win_rate': n_winners / n_trades * 100 if n_trades > 0 else 0,
            'avg_return': avg_return,
            'max_loss': max_loss,
            'max_gain': max_gain
        }
        results.append(result)

        print(f"\n  📊 Results:")
        print(f"     Trades:     {n_trades}")
        print(f"     Winners:    {n_winners} ({n_winners/n_trades*100:.1f}%)")
        print(f"     Losers:     {n_losers}")
        if n_stopped > 0:
            print(f"     Stopped:    {n_stopped}")
        print(f"     Avg Return: {avg_return:+.2f}%")
        print(f"     Max Loss:   {max_loss:+.2f}%")
        print(f"     Max Gain:   {max_gain:+.2f}%")

        if n_losers > 0 and n_losers <= 10:
            print(f"\n  💡 Losers:")
            losers = df_trades[df_trades['return'] <= 0].nsmallest(min(10, n_losers), 'return')
            for _, r in losers.iterrows():
                date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
                status = " STOP" if r['stopped'] else ""
                print(f"     {r['symbol']:<6} {date_str} {r['return']:+.2f}%{status} RSI:{r['rsi']:.0f} Vol:{r['vol_surge']:.2f}")

        if n_winners > 0 and n_losers == 0:
            print(f"\n  🏆 ALL WINNERS ({n_trades} trades):")
            for _, r in df_trades.nlargest(5, 'return').iterrows():
                date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
                print(f"     {r['symbol']:<6} {date_str} {r['return']:+.2f}% Vol:{r['vol_surge']:.2f}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: ALL CONFIGURATIONS")
    print("=" * 80)

    print(f"\n{'Config':<35} {'Trades':>7} {'Win%':>7} {'Losers':>7} {'AvgRet':>8} {'MaxLoss':>8}")
    print("-" * 80)

    for r in sorted(results, key=lambda x: (x['losers'], -x['avg_return'])):
        print(f"{r['config']:<35} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['losers']:>7} {r['avg_return']:>+7.2f}% {r['max_loss']:>+7.2f}%")

    # Find zero loser configs
    zero_loser = [r for r in results if r['losers'] == 0 and r['trades'] > 0]
    if zero_loser:
        print(f"\n✅ ZERO LOSER CONFIGURATIONS:")
        for r in zero_loser:
            print(f"   {r['config']}: {r['trades']} trades, {r['avg_return']:+.2f}% avg")

    # Best overall (prioritize: min losers, then max avg return)
    if results:
        best = min(results, key=lambda x: (x['losers'], -x['avg_return']))
        print(f"\n🏆 BEST CONFIG: {best['config']}")
        print(f"   Trades: {best['trades']}, Win Rate: {best['win_rate']:.1f}%")
        print(f"   Losers: {best['losers']}, Max Loss: {best['max_loss']:.2f}%")
        print(f"   Avg Return: {best['avg_return']:.2f}%")

    # Save
    with open('backtest_volume_surge_fixed.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\n💾 Saved to: backtest_volume_surge_fixed.json")


if __name__ == '__main__':
    main()
