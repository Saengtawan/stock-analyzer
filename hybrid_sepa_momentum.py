#!/usr/bin/env python3
"""
HYBRID APPROACH: SEPA (Minervini) + Momentum Gates + Tight Stop-Loss
=====================================================================
Combining the best from:
1. Mark Minervini's SEPA - Trend Template (price structure)
2. Our momentum gates - Accumulation, RSI
3. Tight stop-loss (-2%) to cap losses

Goal: Minimize losers while maintaining good trade frequency
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


def check_sepa_template(closes, highs, lows, i):
    """
    Minervini's SEPA Trend Template (simplified)
    - Price > MA50 > MA150 > MA200 (trend alignment)
    - Price at least 25% above 52w low
    - Price within 25% of 52w high
    - MA200 trending up for at least 1 month
    """
    if i < 200:
        return False, 0

    price = float(closes[i])
    ma50 = float(np.mean(closes[i-49:i+1]))
    ma150 = float(np.mean(closes[i-149:i+1]))
    ma200 = float(np.mean(closes[i-199:i+1]))
    ma200_1m_ago = float(np.mean(closes[i-219:i-19])) if i >= 220 else ma200

    low_52w = float(np.min(lows[max(0,i-252):i+1]))
    high_52w = float(np.max(highs[max(0,i-252):i+1]))

    score = 0

    # Price above all MAs
    if price > ma50:
        score += 1
    if price > ma150:
        score += 1
    if price > ma200:
        score += 1

    # MA alignment: MA50 > MA150 > MA200
    if ma50 > ma150 > ma200:
        score += 2
    elif ma50 > ma150 or ma150 > ma200:
        score += 1

    # At least 25% above 52w low
    pct_above_low = ((price - low_52w) / low_52w) * 100
    if pct_above_low >= 25:
        score += 1

    # Within 25% of 52w high
    pct_from_high = ((high_52w - price) / high_52w) * 100
    if pct_from_high <= 25:
        score += 1

    # MA200 trending up
    if ma200 > ma200_1m_ago:
        score += 1

    return score >= 6, score


def check_momentum_gates(closes, volumes, i, config):
    """Our momentum quality gates"""
    if i < 50:
        return False, {}

    price = float(closes[i])
    ma20 = float(np.mean(closes[i-19:i+1]))
    ma50 = float(np.mean(closes[i-49:i+1]))

    above_ma20 = ((price - ma20) / ma20) * 100
    above_ma50 = ((price - ma50) / ma50) * 100

    rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
    accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

    # Volume surge check (today's volume vs 20-day average)
    vol_avg = float(np.mean(volumes[i-19:i]))
    vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

    metrics = {
        'rsi': rsi,
        'accum': accum,
        'above_ma20': above_ma20,
        'above_ma50': above_ma50,
        'vol_surge': vol_surge
    }

    # Apply gates
    if accum <= config['accum_min']:
        return False, metrics
    if rsi >= config['rsi_max']:
        return False, metrics
    if above_ma20 <= config['ma20_min']:
        return False, metrics
    if above_ma50 <= config['ma50_min']:
        return False, metrics
    if vol_surge < config.get('vol_surge_min', 0):
        return False, metrics

    return True, metrics


def simulate_trade_with_stoploss(closes, i, hold_days, stop_pct):
    """Simulate trade with stop-loss"""
    n = len(closes)
    if i + hold_days >= n:
        return None

    entry_price = float(closes[i])
    stop_price = entry_price * (1 + stop_pct / 100)

    for j in range(1, hold_days + 1):
        if i + j >= n:
            break
        day_price = float(closes[i + j])

        if day_price <= stop_price:
            return {
                'return': stop_pct,
                'exit_day': j,
                'stopped': True
            }

    exit_price = float(closes[i + hold_days])
    actual_return = ((exit_price - entry_price) / entry_price) * 100

    return {
        'return': actual_return,
        'exit_day': hold_days,
        'stopped': False
    }


def main():
    print("=" * 80)
    print("HYBRID APPROACH: SEPA + MOMENTUM GATES + TIGHT STOP-LOSS")
    print("=" * 80)

    # Test configurations
    CONFIGS = [
        # Base: Our v9.1 momentum gates
        {
            'name': 'Momentum Only (v9.1)',
            'use_sepa': False,
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 0,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # SEPA + Momentum
        {
            'name': 'SEPA + Momentum',
            'use_sepa': True,
            'sepa_min_score': 6,
            'accum_min': 1.2,
            'rsi_max': 60,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 0,
            'hold_days': 10,
            'stop_pct': -2.0
        },
        # SEPA + Strict Momentum
        {
            'name': 'SEPA + Strict Momentum',
            'use_sepa': True,
            'sepa_min_score': 6,
            'accum_min': 1.3,
            'rsi_max': 55,
            'ma20_min': 1,
            'ma50_min': 0,
            'vol_surge_min': 0,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # SEPA + Volume Surge
        {
            'name': 'SEPA + Volume Surge',
            'use_sepa': True,
            'sepa_min_score': 5,
            'accum_min': 1.2,
            'rsi_max': 60,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.2,  # Volume 20% above average
            'hold_days': 7,
            'stop_pct': -2.0
        },
        # Ultra-strict: SEPA + Strict Momentum + Volume
        {
            'name': 'Ultra-Strict (SEPA+Mom+Vol)',
            'use_sepa': True,
            'sepa_min_score': 6,
            'accum_min': 1.4,
            'rsi_max': 52,
            'ma20_min': 2,
            'ma50_min': 3,
            'vol_surge_min': 1.3,
            'hold_days': 5,
            'stop_pct': -2.0
        },
        # Relaxed with tighter stop
        {
            'name': 'Relaxed + Tight Stop (-1.5%)',
            'use_sepa': True,
            'sepa_min_score': 5,
            'accum_min': 1.1,
            'rsi_max': 58,
            'ma20_min': 0,
            'ma50_min': 0,
            'vol_surge_min': 1.1,
            'hold_days': 5,
            'stop_pct': -1.5
        },
    ]

    # Large universe
    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'QCOM',
        'TXN', 'AVGO', 'MU', 'AMAT', 'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG',
        'NET', 'ZS', 'PANW', 'CRWD', 'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE',
        'CAT', 'DE', 'HON', 'GE', 'BA', 'XOM', 'CVX',
        'T', 'VZ', 'TMUS', 'NFLX', 'UBER', 'ABNB', 'PYPL', 'SHOP'
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 260)

    print(f"\nDownloading {len(symbols)} stocks...")

    stock_data = {}
    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 250:
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

            for i in range(220, n - hold_days - 1):
                # Check SEPA if required
                if config.get('use_sepa', False):
                    sepa_pass, sepa_score = check_sepa_template(closes, highs, lows, i)
                    if not sepa_pass or sepa_score < config.get('sepa_min_score', 6):
                        continue

                # Check momentum gates
                mom_pass, metrics = check_momentum_gates(closes, volumes, i, config)
                if not mom_pass:
                    continue

                # Simulate trade with stop-loss
                result = simulate_trade_with_stoploss(closes, i, hold_days, config['stop_pct'])

                if result:
                    trades.append({
                        'symbol': sym,
                        'date': dates[i],
                        'return': result['return'],
                        'stopped': result['stopped'],
                        'exit_day': result['exit_day'],
                        **metrics
                    })

        if not trades:
            print("  No trades generated")
            continue

        df_trades = pd.DataFrame(trades)

        # Deduplicate
        df_trades['week'] = df_trades['date'].dt.isocalendar().week
        df_trades['year'] = df_trades['date'].dt.year
        df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

        n_trades = len(df_trades)
        n_stopped = len(df_trades[df_trades['stopped'] == True])
        n_winners = len(df_trades[df_trades['return'] > 0])
        n_losers = len(df_trades[df_trades['return'] <= 0])
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
            'max_gain': max_gain,
            'stop_pct': config['stop_pct']
        }
        results.append(result)

        print(f"\n  📊 Results:")
        print(f"     Trades:    {n_trades}")
        print(f"     Winners:   {n_winners} ({n_winners/n_trades*100:.1f}%)")
        print(f"     Losers:    {n_losers} (stopped: {n_stopped})")
        print(f"     Avg Return: {avg_return:+.2f}%")
        print(f"     Max Loss:  {max_loss:+.2f}%")
        print(f"     Max Gain:  {max_gain:+.2f}%")

        if n_losers > 0 and n_losers <= 5:
            print(f"\n  💡 Losers:")
            losers = df_trades[df_trades['return'] <= 0].nsmallest(5, 'return')
            for _, r in losers.iterrows():
                status = "STOPPED" if r['stopped'] else f"held {r['exit_day']}d"
                print(f"     {r['symbol']:<6} {r['return']:+.2f}% ({status}) RSI:{r['rsi']:.0f} Accum:{r['accum']:.2f}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: COMPARING ALL CONFIGURATIONS")
    print("=" * 80)

    print(f"\n{'Config':<30} {'Trades':>7} {'Win%':>7} {'AvgRet':>8} {'MaxLoss':>8} {'Losers':>7}")
    print("-" * 75)

    for r in sorted(results, key=lambda x: (-x['win_rate'], x['losers'])):
        print(f"{r['config']:<30} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['avg_return']:>+7.2f}% {r['max_loss']:>+7.2f}% {r['losers']:>7}")

    # Best configuration
    if results:
        # Prioritize: min losers, then high win rate, then avg return
        best = min(results, key=lambda x: (x['losers'], -x['win_rate'], -x['avg_return']))
        print(f"\n🏆 BEST CONFIG: {best['config']}")
        print(f"   Trades: {best['trades']}, Win Rate: {best['win_rate']:.1f}%")
        print(f"   Losers: {best['losers']}, Max Loss: {best['max_loss']:.2f}%")
        print(f"   Avg Return: {best['avg_return']:.2f}%")

        # Find zero/low loser configs
        low_loser = [r for r in results if r['losers'] <= 3]
        if low_loser:
            print(f"\n✅ LOW LOSER CONFIGS (<= 3 losers):")
            for r in sorted(low_loser, key=lambda x: x['losers']):
                print(f"   {r['config']}: {r['losers']} losers, {r['trades']} trades, {r['avg_return']:+.2f}%")

    # Save results
    with open('hybrid_sepa_momentum_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\n💾 Saved to: hybrid_sepa_momentum_results.json")


if __name__ == '__main__':
    main()
