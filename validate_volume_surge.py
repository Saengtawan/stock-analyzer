#!/usr/bin/env python3
"""
VALIDATION: Volume Surge Filter - The Key to Zero Losers?
==========================================================
Testing the volume surge > 1.2 filter that showed 100% win rate
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import json
warnings.filterwarnings('ignore')

TEST_MONTHS = 6


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
    print("VALIDATION: VOLUME SURGE FILTER - THE KEY TO ZERO LOSERS")
    print("=" * 80)

    # Expanded universe for better validation
    symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'QCOM',
        'TXN', 'AVGO', 'MU', 'AMAT', 'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG',
        'NET', 'ZS', 'PANW', 'CRWD', 'PLTR', 'COIN',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'WFC', 'V', 'MA', 'AXP',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD',
        # Retail
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'LULU',
        # Industrial
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB',
        # Telecom/Media
        'T', 'VZ', 'TMUS', 'NFLX', 'DIS', 'CMCSA',
        # Growth
        'UBER', 'ABNB', 'PYPL', 'SHOP', 'SQ', 'RBLX', 'ROKU'
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 100)

    print(f"\nDownloading {len(symbols)} stocks...")
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    stock_data = {}
    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 80:
                return None, sym
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df, sym
        except:
            return None, sym

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df

    print(f"Downloaded: {len(stock_data)} stocks\n")

    # Test configurations with volume surge
    CONFIGS = [
        # Original v9.1 (baseline)
        {
            'name': 'v9.1 Baseline',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 0,  # No volume filter
            'mom_3d_min': -999,
            'hold_days': 5,
            'stop_pct': None  # No stop-loss
        },
        # v9.1 + Volume Surge
        {
            'name': 'v9.1 + Vol Surge > 1.2',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': -999,
            'hold_days': 5,
            'stop_pct': None
        },
        # v9.1 + Volume Surge + Mom 3d
        {
            'name': 'v9.1 + Vol>1.2 + Mom3d>1%',
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': 1,
            'hold_days': 5,
            'stop_pct': None
        },
        # Relaxed base + Vol Surge (more signals)
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
        # Volume Surge only (test its standalone power)
        {
            'name': 'Vol Surge Only (>1.3)',
            'accum_min': 1.0,
            'rsi_max': 70,
            'ma20_min': -5,
            'ma50_min': -5,
            'vol_surge_min': 1.3,
            'mom_3d_min': 0,
            'hold_days': 5,
            'stop_pct': None
        },
        # With stop-loss for comparison
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
        # Different hold periods
        {
            'name': 'Vol>1.2 + 7-day hold',
            'accum_min': 1.2,
            'rsi_max': 57,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': 0,
            'hold_days': 7,
            'stop_pct': None
        },
        {
            'name': 'Vol>1.2 + 10-day hold',
            'accum_min': 1.2,
            'rsi_max': 57,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.2,
            'mom_3d_min': 0,
            'hold_days': 10,
            'stop_pct': None
        },
    ]

    results = []

    for config in CONFIGS:
        print(f"\n{'='*70}")
        print(f"Testing: {config['name']}")
        print(f"{'='*70}")

        trades = []

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

                # MA calculations
                ma20 = float(np.mean(closes[i-19:i+1]))
                ma50 = float(np.mean(closes[i-49:i+1]))
                above_ma20 = ((price - ma20) / ma20) * 100
                above_ma50 = ((price - ma50) / ma50) * 100

                # RSI & Accumulation
                rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
                accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

                # Volume surge (today vs 20-day avg)
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

                # Calculate return
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

                trades.append({
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

        if not trades:
            print("  No trades generated")
            continue

        df_trades = pd.DataFrame(trades)

        # Deduplicate by symbol + week
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
        print(f"     Trades:    {n_trades}")
        print(f"     Winners:   {n_winners} ({n_winners/n_trades*100:.1f}%)")
        print(f"     Losers:    {n_losers}")
        print(f"     Avg Return: {avg_return:+.2f}%")
        print(f"     Max Loss:  {max_loss:+.2f}%")
        print(f"     Max Gain:  {max_gain:+.2f}%")

        if n_losers > 0 and n_losers <= 10:
            print(f"\n  💡 Losers:")
            losers = df_trades[df_trades['return'] <= 0].nsmallest(10, 'return')
            for _, r in losers.iterrows():
                date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
                print(f"     {r['symbol']:<6} {date_str} {r['return']:+.2f}% RSI:{r['rsi']:.0f} Vol:{r['vol_surge']:.2f}")

        if n_winners > 0:
            print(f"\n  🏆 Top Winners:")
            winners = df_trades.nlargest(5, 'return')
            for _, r in winners.iterrows():
                date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
                print(f"     {r['symbol']:<6} {date_str} {r['return']:+.2f}% Vol:{r['vol_surge']:.2f}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: COMPARING ALL CONFIGURATIONS")
    print("=" * 80)

    print(f"\n{'Config':<35} {'Trades':>7} {'Win%':>7} {'Losers':>7} {'AvgRet':>8} {'MaxLoss':>8}")
    print("-" * 80)

    for r in sorted(results, key=lambda x: (x['losers'], -x['win_rate'])):
        print(f"{r['config']:<35} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['losers']:>7} {r['avg_return']:>+7.2f}% {r['max_loss']:>+7.2f}%")

    # Find zero/low loser configs
    zero_loser = [r for r in results if r['losers'] == 0]
    low_loser = [r for r in results if r['losers'] <= 3 and r['losers'] > 0]

    if zero_loser:
        print(f"\n✅ ZERO LOSER CONFIGURATIONS:")
        for r in zero_loser:
            print(f"   {r['config']}: {r['trades']} trades, {r['avg_return']:+.2f}% avg return")

    if low_loser:
        print(f"\n⭐ LOW LOSER CONFIGURATIONS (1-3 losers):")
        for r in sorted(low_loser, key=lambda x: x['losers']):
            print(f"   {r['config']}: {r['losers']} losers, {r['trades']} trades, {r['avg_return']:+.2f}%")

    # Best overall
    if results:
        best = min(results, key=lambda x: (x['losers'], -x['avg_return']))
        print(f"\n🏆 BEST CONFIG: {best['config']}")
        print(f"   Trades: {best['trades']}")
        print(f"   Win Rate: {best['win_rate']:.1f}%")
        print(f"   Losers: {best['losers']}")
        print(f"   Avg Return: {best['avg_return']:.2f}%")
        print(f"   Max Loss: {best['max_loss']:.2f}%")

    # Save results
    with open('volume_surge_validation.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\n💾 Saved to: volume_surge_validation.json")


if __name__ == '__main__':
    main()
