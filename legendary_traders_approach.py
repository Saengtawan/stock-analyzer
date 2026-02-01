#!/usr/bin/env python3
"""
LEGENDARY TRADERS APPROACH
==========================
ศึกษาและทดลองแนวคิดของนักลงทุนระดับโลก

Famous Swing/Momentum Traders:
1. William O'Neil (CANSLIM) - CAN SLIM methodology
2. Mark Minervini - SEPA (Specific Entry Point Analysis)
3. Jesse Livermore - Trend following, pyramiding
4. Nicolas Darvas - Box Theory
5. Stan Weinstein - Stage Analysis

Plus: Tight Stop-Loss Strategy (-2% to -3%)
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


# ===== LEGENDARY STRATEGIES =====

def oneil_canslim(df, i):
    """
    William O'Neil - CANSLIM
    - C: Current earnings (we use momentum as proxy)
    - A: Annual earnings growth (momentum 20d)
    - N: New highs (price near 52w high)
    - S: Supply/demand (volume surge)
    - L: Leader (strong RS)
    - I: Institutional sponsorship (high volume)
    - M: Market direction (above MA50)
    """
    closes = df['Close'].values.flatten()
    volumes = df['Volume'].values.flatten()
    highs = df['High'].values.flatten()

    price = float(closes[i])
    high_52w = float(np.max(highs[max(0,i-252):i+1]))
    ma50 = float(np.mean(closes[i-49:i+1]))
    vol_avg = float(np.mean(volumes[i-49:i+1]))

    # Score each component
    score = 0

    # N: Near new high (within 5% of 52w high)
    pct_from_high = ((high_52w - price) / high_52w) * 100
    if pct_from_high < 5:
        score += 2
    elif pct_from_high < 10:
        score += 1

    # S: Volume surge (current > 1.5x average)
    if volumes[i] > vol_avg * 1.5:
        score += 2
    elif volumes[i] > vol_avg * 1.2:
        score += 1

    # M: Market direction (above MA50)
    if price > ma50:
        score += 2

    # L: Leader (momentum > 5%)
    mom_20d = ((price - float(closes[i-20])) / float(closes[i-20])) * 100 if i >= 20 else 0
    if mom_20d > 10:
        score += 2
    elif mom_20d > 5:
        score += 1

    return score >= 5, score, "CANSLIM"


def minervini_sepa(df, i):
    """
    Mark Minervini - SEPA (Specific Entry Point Analysis)
    - Price above 150 MA and 200 MA
    - 150 MA above 200 MA
    - Price at least 30% above 52w low
    - Price within 25% of 52w high
    - RS > 70 (relative strength)
    - Price above 50 MA
    """
    closes = df['Close'].values.flatten()
    lows = df['Low'].values.flatten()
    highs = df['High'].values.flatten()

    if i < 200:
        return False, 0, "SEPA"

    price = float(closes[i])
    ma50 = float(np.mean(closes[i-49:i+1]))
    ma150 = float(np.mean(closes[i-149:i+1]))
    ma200 = float(np.mean(closes[i-199:i+1]))

    low_52w = float(np.min(lows[max(0,i-252):i+1]))
    high_52w = float(np.max(highs[max(0,i-252):i+1]))

    score = 0

    # Price > MA50
    if price > ma50:
        score += 1

    # Price > MA150 and MA200
    if price > ma150 and price > ma200:
        score += 2

    # MA150 > MA200 (trend confirmation)
    if ma150 > ma200:
        score += 1

    # 30% above 52w low
    pct_above_low = ((price - low_52w) / low_52w) * 100
    if pct_above_low > 30:
        score += 1

    # Within 25% of 52w high
    pct_from_high = ((high_52w - price) / high_52w) * 100
    if pct_from_high < 25:
        score += 1

    return score >= 5, score, "SEPA"


def darvas_box(df, i):
    """
    Nicolas Darvas - Box Theory
    - Price breaks out of consolidation "box"
    - Box = high and low of last N days where price stayed in range
    - Entry on breakout above box top with volume
    """
    closes = df['Close'].values.flatten()
    highs = df['High'].values.flatten()
    lows = df['Low'].values.flatten()
    volumes = df['Volume'].values.flatten()

    if i < 20:
        return False, 0, "Darvas Box"

    price = float(closes[i])

    # Define box (last 10 days)
    box_high = float(np.max(highs[i-10:i]))
    box_low = float(np.min(lows[i-10:i]))
    box_range = box_high - box_low

    # Volume check
    vol_avg = float(np.mean(volumes[i-20:i]))
    vol_surge = volumes[i] > vol_avg * 1.3

    # Breakout above box with volume
    if price > box_high and vol_surge:
        # Check that box was tight (< 10% range)
        if (box_range / box_low * 100) < 10:
            return True, 3, "Darvas Box"

    return False, 0, "Darvas Box"


def weinstein_stage(df, i):
    """
    Stan Weinstein - Stage Analysis
    Stage 1: Basing (accumulation) - avoid
    Stage 2: Advancing (markup) - BUY
    Stage 3: Topping (distribution) - avoid
    Stage 4: Declining (markdown) - avoid

    Stage 2 criteria:
    - Price above 30-week MA
    - 30-week MA trending up
    - Volume increasing on up days
    """
    closes = df['Close'].values.flatten()
    volumes = df['Volume'].values.flatten()

    if i < 150:  # Need ~30 weeks
        return False, 0, "Stage 2"

    price = float(closes[i])
    ma30w = float(np.mean(closes[i-149:i+1]))  # ~30 weeks = 150 days
    ma30w_prev = float(np.mean(closes[i-159:i-9]))

    # Stage 2 check
    score = 0

    # Price above 30w MA
    if price > ma30w:
        score += 2

    # 30w MA trending up
    if ma30w > ma30w_prev:
        score += 2

    # Volume pattern (accumulation)
    accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=30)
    if accum > 1.2:
        score += 1

    return score >= 4, score, "Stage 2"


def tight_stoploss_test(df, i, hold_days, stop_pct=-2.5):
    """
    Test with TIGHT stop-loss
    - Exit immediately if drops below stop
    - Track actual return with stop-loss applied
    """
    closes = df['Close'].values.flatten()
    n = len(closes)

    if i + hold_days >= n:
        return None

    entry_price = float(closes[i])
    stop_price = entry_price * (1 + stop_pct / 100)

    # Check each day for stop-loss trigger
    for j in range(1, hold_days + 1):
        if i + j >= n:
            break
        day_price = float(closes[i + j])

        # Stop-loss hit
        if day_price <= stop_price:
            return {
                'return': stop_pct,
                'exit_day': j,
                'stopped': True
            }

    # Held full period
    exit_price = float(closes[i + hold_days])
    actual_return = ((exit_price - entry_price) / entry_price) * 100

    return {
        'return': actual_return,
        'exit_day': hold_days,
        'stopped': False
    }


def main():
    print("=" * 80)
    print("LEGENDARY TRADERS APPROACH + TIGHT STOP-LOSS")
    print("=" * 80)

    print("""
STRATEGIES TESTED:
1. William O'Neil - CANSLIM (momentum + volume + trend)
2. Mark Minervini - SEPA (strict trend template)
3. Nicolas Darvas - Box Breakout (consolidation breakout)
4. Stan Weinstein - Stage 2 (trend following)

STOP-LOSS: -2.5% (tight, exit fast on wrong trades)
""")

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
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 250)  # Extra for 200 MA

    print(f"Downloading {len(symbols)} stocks...")

    stock_data = {}
    for sym in symbols:
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 250:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"Downloaded: {len(stock_data)} stocks\n")

    # Test each strategy
    strategies = [
        ('CANSLIM', oneil_canslim),
        ('SEPA', minervini_sepa),
        ('Darvas Box', darvas_box),
        ('Stage 2', weinstein_stage)
    ]

    hold_days = 10  # Swing trade timeframe
    stop_pct = -2.5  # Tight stop-loss

    results = {}

    for strategy_name, strategy_func in strategies:
        print(f"\n{'='*60}")
        print(f"Testing: {strategy_name}")
        print(f"{'='*60}")

        trades = []

        for sym, df in stock_data.items():
            closes = df['Close'].values.flatten()
            n = len(closes)

            for i in range(200, n - hold_days - 1):
                # Check strategy signal
                passes, score, _ = strategy_func(df, i)

                if passes:
                    # Test with stop-loss
                    result = tight_stoploss_test(df, i, hold_days, stop_pct)

                    if result:
                        trades.append({
                            'symbol': sym,
                            'date': df.index[i],
                            'score': score,
                            'return': result['return'],
                            'stopped': result['stopped'],
                            'exit_day': result['exit_day']
                        })

        if not trades:
            print("  No signals generated")
            continue

        df_trades = pd.DataFrame(trades)

        # Deduplicate
        df_trades['week'] = df_trades['date'].dt.isocalendar().week
        df_trades['year'] = df_trades['date'].dt.year
        df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

        n_trades = len(df_trades)
        n_stopped = len(df_trades[df_trades['stopped'] == True])
        n_winners = len(df_trades[df_trades['return'] > 0])
        n_losers = len(df_trades[df_trades['return'] < 0])
        avg_return = df_trades['return'].mean()
        total_return = df_trades['return'].sum()

        # Calculate max loss
        max_loss = df_trades['return'].min()

        results[strategy_name] = {
            'trades': n_trades,
            'winners': n_winners,
            'losers': n_losers,
            'stopped': n_stopped,
            'win_rate': n_winners / n_trades * 100 if n_trades > 0 else 0,
            'avg_return': avg_return,
            'total_return': total_return,
            'max_loss': max_loss
        }

        print(f"\n  📊 RESULTS:")
        print(f"     Trades:      {n_trades}")
        print(f"     Winners:     {n_winners} ({n_winners/n_trades*100:.1f}%)")
        print(f"     Losers:      {n_losers} (including {n_stopped} stopped out)")
        print(f"     Avg Return:  {avg_return:.2f}%")
        print(f"     Max Loss:    {max_loss:.2f}% (stop was {stop_pct}%)")

        if n_losers > 0:
            print(f"\n  💡 LOSER ANALYSIS:")
            losers = df_trades[df_trades['return'] < 0].nsmallest(5, 'return')
            for _, r in losers.iterrows():
                status = "STOPPED" if r['stopped'] else f"held {r['exit_day']}d"
                print(f"     {r['symbol']:<6} {r['return']:+.2f}% ({status})")

        if n_winners > 0:
            print(f"\n  🏆 TOP WINNERS:")
            winners = df_trades.nlargest(5, 'return')
            for _, r in winners.iterrows():
                print(f"     {r['symbol']:<6} {r['return']:+.2f}%")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: WHICH STRATEGY IS BEST?")
    print("=" * 80)

    print(f"\n{'Strategy':<15} {'Trades':>7} {'WinRate':>8} {'AvgRet':>8} {'MaxLoss':>8} {'Stopped':>8}")
    print("-" * 60)

    for name, r in results.items():
        print(f"{name:<15} {r['trades']:>7} {r['win_rate']:>7.1f}% {r['avg_return']:>+7.2f}% {r['max_loss']:>+7.2f}% {r['stopped']:>8}")

    # Best strategy
    if results:
        best = max(results.items(), key=lambda x: x[1]['avg_return'])
        print(f"\n🏆 BEST STRATEGY: {best[0]}")
        print(f"   Win Rate: {best[1]['win_rate']:.1f}%")
        print(f"   Avg Return: {best[1]['avg_return']:.2f}%")
        print(f"   Max Loss: {best[1]['max_loss']:.2f}%")

    # Save results
    with open('legendary_traders_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\n💾 Saved to: legendary_traders_results.json")


if __name__ == '__main__':
    main()
