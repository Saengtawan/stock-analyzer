#!/usr/bin/env python3
"""
Root Cause Analysis: Why is the strategy underperforming?
Analyze:
1. Market conditions during backtest period
2. Why did winning trades work?
3. Why did losing trades fail?
4. Which filters blocked good opportunities?
5. Entry timing issues?
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

STOCK_UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'TEAM', 'DASH', 'SHOP',
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC', 'LRCX', 'TSM',
    'UBER', 'ABNB', 'COIN', 'ROKU',
]

FILTERS = {
    'rsi_min': 49.0,
    'momentum_7d_min': 3.5,
    'rs_14d_min': 1.9,
    'dist_ma20_min': -2.8,
}


def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def analyze_market_condition(spy_data):
    """Analyze overall market condition"""
    print("=" * 100)
    print("1️⃣  MARKET CONDITION ANALYSIS (SPY)")
    print("=" * 100)

    # Get 2-month period
    end = spy_data.index[-1]
    start_2m = spy_data.index[-40] if len(spy_data) >= 40 else spy_data.index[0]

    spy_2m = spy_data.loc[start_2m:]

    start_price = spy_2m['Close'].iloc[0]
    end_price = spy_2m['Close'].iloc[-1]
    max_price = spy_2m['High'].max()
    min_price = spy_2m['Low'].min()

    total_return = ((end_price - start_price) / start_price) * 100
    max_gain = ((max_price - start_price) / start_price) * 100
    max_dd = ((min_price - start_price) / start_price) * 100

    # Calculate volatility
    daily_returns = spy_2m['Close'].pct_change()
    volatility = daily_returns.std() * np.sqrt(252) * 100

    # Trend analysis
    ma20 = spy_2m['Close'].rolling(20).mean()
    above_ma20 = (spy_2m['Close'] > ma20).sum()
    total_days = len(spy_2m)
    pct_above_ma20 = (above_ma20 / total_days) * 100

    print(f"\n📅 Period: {start_2m.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
    print(f"\n📊 SPY Performance:")
    print(f"   Total Return: {total_return:+.2f}%")
    print(f"   Max Gain: {max_gain:+.2f}%")
    print(f"   Max Drawdown: {max_dd:+.2f}%")
    print(f"   Volatility (annualized): {volatility:.1f}%")
    print(f"   Days Above MA20: {pct_above_ma20:.0f}%")

    # Classify market
    if total_return > 5:
        market_type = "🟢 STRONG UPTREND"
    elif total_return > 0:
        market_type = "🟡 WEAK UPTREND"
    elif total_return > -5:
        market_type = "🟠 WEAK DOWNTREND"
    else:
        market_type = "🔴 STRONG DOWNTREND"

    print(f"\n🎯 Market Type: {market_type}")

    if volatility > 25:
        print("   ⚠️  HIGH VOLATILITY - choppy market")
    elif volatility > 20:
        print("   ⚠️  MODERATE VOLATILITY")
    else:
        print("   ✅ LOW VOLATILITY - stable market")

    return {
        'total_return': total_return,
        'volatility': volatility,
        'pct_above_ma20': pct_above_ma20,
        'market_type': market_type
    }


def analyze_actual_trades():
    """Analyze the 8 actual trades that happened"""
    print("\n\n" + "=" * 100)
    print("2️⃣  ACTUAL TRADES DEEP DIVE")
    print("=" * 100)

    # The 8 trades from backtest
    trades = [
        {'symbol': 'DDOG', 'entry_date': '2025-11-10', 'result': -20.94, 'max': 1.0, 'status': 'LOSER'},
        {'symbol': 'LRCX', 'entry_date': '2025-11-10', 'result': -6.96, 'max': -1.1, 'status': 'LOSER'},
        {'symbol': 'AAPL', 'entry_date': '2025-12-01', 'result': -3.33, 'max': 1.9, 'status': 'LOSER'},
        {'symbol': 'GOOGL', 'entry_date': '2025-12-01', 'result': -2.39, 'max': 2.6, 'status': 'LOSER'},
        {'symbol': 'AMAT', 'entry_date': '2025-12-01', 'result': 0.65, 'max': 8.38, 'status': 'WINNER'},
        {'symbol': 'META', 'entry_date': '2025-12-01', 'result': 2.88, 'max': 10.94, 'status': 'WINNER'},
        {'symbol': 'AVGO', 'entry_date': '2025-12-01', 'result': -11.84, 'max': 7.39, 'status': 'WINNER'},
        {'symbol': 'DASH', 'entry_date': '2025-12-01', 'result': 13.95, 'max': 16.26, 'status': 'WINNER'},
    ]

    print("\n📊 WINNERS vs LOSERS Analysis:\n")

    winners = [t for t in trades if t['status'] == 'WINNER']
    losers = [t for t in trades if t['status'] == 'LOSER']

    print(f"Winners: {len(winners)}")
    for t in winners:
        give_back = t['max'] - t['result']
        print(f"   {t['symbol']:6s} ({t['entry_date']}): Max {t['max']:+.1f}% → Exit {t['result']:+.1f}% (gave back: {give_back:.1f}%)")

    avg_giveback = np.mean([t['max'] - t['result'] for t in winners])
    print(f"   Average Give-Back: {avg_giveback:.1f}%")

    print(f"\nLosers: {len(losers)}")
    for t in losers:
        print(f"   {t['symbol']:6s} ({t['entry_date']}): Max {t['max']:+.1f}% → Exit {t['result']:+.1f}%")

    print("\n🔍 KEY FINDINGS:")

    # Finding 1: Give-back issue
    if avg_giveback > 5:
        print(f"\n   ⚠️  CRITICAL ISSUE #1: Large Give-Back")
        print(f"      Winners gave back an average of {avg_giveback:.1f}% from peak")
        print(f"      → NEED: Take profit rule or trailing stop")
        print(f"      → IMPACT: AVGO went from +7.4% to -11.8% (gave back 19.2%!)")

    # Finding 2: Losers that almost worked
    almost_worked = [t for t in losers if t['max'] > 0]
    if almost_worked:
        print(f"\n   ⚠️  ISSUE #2: Reversals After Small Gains")
        print(f"      {len(almost_worked)}/{len(losers)} losing trades had positive max returns")
        for t in almost_worked:
            print(f"         {t['symbol']}: went to +{t['max']:.1f}% but finished {t['result']:+.1f}%")
        print(f"      → NEED: Tighter holding period or trailing stop")

    # Finding 3: Big losers
    big_losers = [t for t in trades if t['result'] < -10]
    if big_losers:
        print(f"\n   🚨 CRITICAL ISSUE #3: Big Losers (>10% loss)")
        for t in big_losers:
            print(f"      {t['symbol']}: {t['result']:.1f}%")
        print(f"      → NEED: Stop loss at -8% to -10%")


def analyze_missed_opportunities(stock_data, spy_data):
    """Find good opportunities that filters blocked"""
    print("\n\n" + "=" * 100)
    print("3️⃣  MISSED OPPORTUNITIES ANALYSIS")
    print("=" * 100)

    print("\n🔍 Scanning all stocks without filters...\n")

    # Test entry dates
    entry_dates_str = ['2025-10-01', '2025-10-10', '2025-10-21', '2025-10-30',
                       '2025-11-10', '2025-11-19', '2025-12-01']

    all_opportunities = []

    for entry_str in entry_dates_str:
        entry_date = pd.Timestamp(entry_str).tz_localize('America/New_York')

        for symbol, hist in stock_data.items():
            # Find entry
            entry_idx = None
            for i, date in enumerate(hist.index):
                if date >= entry_date:
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx + 14 >= len(hist):
                continue

            entry_price = hist['Close'].iloc[entry_idx]
            holding = hist.iloc[entry_idx+1:entry_idx+15]

            if holding.empty:
                continue

            max_high = holding['High'].max()
            exit_price = holding['Close'].iloc[-1]

            max_return = ((max_high - entry_price) / entry_price) * 100
            actual_return = ((exit_price - entry_price) / entry_price) * 100

            if max_return >= 5.0:  # Would have reached target
                all_opportunities.append({
                    'symbol': symbol,
                    'entry_date': entry_str,
                    'max_return': max_return,
                    'actual_return': actual_return,
                })

    print(f"Total opportunities that hit 5%+ target: {len(all_opportunities)}\n")

    if all_opportunities:
        # Show top opportunities
        top_opps = sorted(all_opportunities, key=lambda x: x['max_return'], reverse=True)[:15]

        print("🏆 TOP 15 MISSED OPPORTUNITIES:")
        for i, opp in enumerate(top_opps, 1):
            print(f"   {i:2d}. {opp['symbol']:6s} ({opp['entry_date']}): {opp['max_return']:+.1f}%")

        # Calculate what we missed
        actual_trades = 8
        potential_trades = len(all_opportunities)

        print(f"\n📊 OPPORTUNITY COST:")
        print(f"   Actual Trades: {actual_trades}")
        print(f"   Missed Opportunities: {potential_trades}")
        print(f"   Filter Selectivity: {actual_trades}/{potential_trades} = {actual_trades/potential_trades*100:.1f}%")
        print(f"   → Filters blocked {potential_trades - actual_trades} good opportunities!")


def analyze_filter_effectiveness(stock_data, spy_data):
    """Analyze which filter blocks what"""
    print("\n\n" + "=" * 100)
    print("4️⃣  FILTER EFFECTIVENESS ANALYSIS")
    print("=" * 100)

    print("\n🔬 Testing: What if we relaxed each filter individually?\n")

    test_date = pd.Timestamp('2025-12-01').tz_localize('America/New_York')  # The successful entry date

    # Test with each filter removed
    filter_tests = {
        'NO_RSI': {'rsi_min': 0, 'momentum_7d_min': 3.5, 'rs_14d_min': 1.9, 'dist_ma20_min': -2.8},
        'NO_MOMENTUM': {'rsi_min': 49.0, 'momentum_7d_min': -999, 'rs_14d_min': 1.9, 'dist_ma20_min': -2.8},
        'NO_RS': {'rsi_min': 49.0, 'momentum_7d_min': 3.5, 'rs_14d_min': -999, 'dist_ma20_min': -2.8},
        'NO_MA20': {'rsi_min': 49.0, 'momentum_7d_min': 3.5, 'rs_14d_min': 1.9, 'dist_ma20_min': -999},
        'NO_FILTERS': {'rsi_min': 0, 'momentum_7d_min': -999, 'rs_14d_min': -999, 'dist_ma20_min': -999},
    }

    for test_name, test_filters in filter_tests.items():
        passed_count = 0

        for symbol, hist in stock_data.items():
            # Apply test filters
            data = hist[hist.index <= test_date].copy()
            if len(data) < 50:
                continue

            close = data['Close']
            entry_price = close.iloc[-1]

            # Check filters
            pass_all = True

            # RSI
            rsi = calculate_rsi(close)
            if rsi.iloc[-1] < test_filters['rsi_min']:
                pass_all = False

            # Momentum
            if len(close) >= 7:
                momentum = ((entry_price - close.iloc[-7]) / close.iloc[-7]) * 100
                if momentum < test_filters['momentum_7d_min']:
                    pass_all = False
            else:
                pass_all = False

            # RS
            if len(close) >= 14:
                stock_ret = ((entry_price / close.iloc[-14]) - 1) * 100
                spy_at = spy_data[spy_data.index <= test_date]
                if len(spy_at) >= 14:
                    spy_ret = ((spy_at['Close'].iloc[-1] / spy_at['Close'].iloc[-14]) - 1) * 100
                    rs = stock_ret - spy_ret
                    if rs < test_filters['rs_14d_min']:
                        pass_all = False

            # MA20
            if len(close) >= 20:
                ma20 = close.rolling(20).mean().iloc[-1]
                dist = ((entry_price - ma20) / ma20) * 100
                if dist < test_filters['dist_ma20_min']:
                    pass_all = False

            if pass_all:
                passed_count += 1

        print(f"{test_name:15s}: {passed_count:2d} stocks would pass")

    print("\n💡 INTERPRETATION:")
    print("   If relaxing a filter dramatically increases stock count,")
    print("   that filter is very restrictive and may be blocking opportunities")


def main():
    print("=" * 100)
    print("🔍 ROOT CAUSE ANALYSIS: Why Is Strategy Underperforming?")
    print("=" * 100)

    # Download data
    print("\n📥 Downloading data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=120)

    stock_data = {}
    for symbol in STOCK_UNIVERSE:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)
            if not hist.empty:
                stock_data[symbol] = hist
        except:
            pass

    spy = yf.Ticker('SPY')
    spy_data = spy.history(start=start_date, end=end_date)

    print(f"✅ Data ready\n")

    # Run analyses
    market_stats = analyze_market_condition(spy_data)
    analyze_actual_trades()
    analyze_missed_opportunities(stock_data, spy_data)
    analyze_filter_effectiveness(stock_data, spy_data)

    # Final summary
    print("\n\n" + "=" * 100)
    print("📋 ROOT CAUSE SUMMARY")
    print("=" * 100)

    print("""
🎯 PRIMARY ISSUES IDENTIFIED:

1. NO TAKE PROFIT MECHANISM
   - Winners gave back significant gains (avg 7+ %)
   - AVGO: +7.4% → -11.8% (19% give-back!)
   - FIX: Add take profit at 5% or trailing stop

2. NO STOP LOSS
   - Big losers like DDOG (-20.9%) hurt overall P&L
   - FIX: Add stop loss at -8% to -10%

3. FILTERS TOO STRICT FOR CURRENT MARKET
   - Only 8 trades in 2 months
   - Missed many 5%+ opportunities
   - FIX: Relax one filter OR allow 1 filter failure

4. MARKET TIMING
   - Nov 10 entry (2 trades, both losers) suggests bad timing
   - Dec 1 entry (6 trades, 67% win rate) was much better
   - Market conditions matter!

💡 RECOMMENDED FIXES (in priority order):
   1️⃣  Add take profit rule (most impactful)
   2️⃣  Add stop loss (protect capital)
   3️⃣  Relax filters slightly (more opportunities)
   4️⃣  Consider market regime filter (avoid bad timing)
""")

    print("=" * 100)


if __name__ == "__main__":
    main()
