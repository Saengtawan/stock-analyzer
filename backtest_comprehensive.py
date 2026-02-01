#!/usr/bin/env python3
"""
Comprehensive Backtest:
- 6-12 months historical data
- Different market conditions (bull, bear, sideways)
- Target: 50-100 trades minimum
- Statistical analysis
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from exit_rules import ExitRulesEngine
from collections import defaultdict

STOCK_UNIVERSE = [
    # Mega caps
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    # Tech growth
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'TEAM', 'DASH', 'SHOP', 'SQ',
    # Semiconductors
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC', 'LRCX', 'TSM', 'ASML', 'MU', 'MRVL',
    # Cloud/SaaS
    'CRM', 'NOW', 'WDAY', 'PANW', 'ZS', 'OKTA', 'MDB', 'HUBS',
    # Consumer/Fintech
    'UBER', 'ABNB', 'COIN', 'HOOD', 'ROKU', 'LYFT',
    # AI/Data
    'SNPS', 'CDNS', 'ARM', 'ADBE',
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


def apply_entry_filters(symbol, entry_date, hist_data, spy_data):
    """Check if stock passes entry filters"""
    try:
        data = hist_data[hist_data.index <= entry_date].copy()
        if len(data) < 50:
            return False

        close = data['Close']
        entry_price = close.iloc[-1]

        # RSI
        rsi = calculate_rsi(close)
        if rsi.iloc[-1] < FILTERS['rsi_min']:
            return False

        # Momentum 7d
        if len(close) >= 7:
            momentum = ((entry_price - close.iloc[-7]) / close.iloc[-7]) * 100
            if momentum < FILTERS['momentum_7d_min']:
                return False
        else:
            return False

        # RS 14d
        if len(close) >= 14:
            stock_ret = ((entry_price / close.iloc[-14]) - 1) * 100
            spy_at = spy_data[spy_data.index <= entry_date]
            if len(spy_at) >= 14:
                spy_ret = ((spy_at['Close'].iloc[-1] / spy_at['Close'].iloc[-14]) - 1) * 100
                if (stock_ret - spy_ret) < FILTERS['rs_14d_min']:
                    return False
            else:
                return False
        else:
            return False

        # MA20
        if len(close) >= 20:
            ma20 = close.rolling(20).mean().iloc[-1]
            if ((entry_price - ma20) / ma20) * 100 < FILTERS['dist_ma20_min']:
                return False

        return True

    except:
        return False


def identify_market_condition(spy_data, date):
    """Identify market condition at given date"""
    try:
        data = spy_data[spy_data.index <= date].copy()
        if len(data) < 50:
            return 'UNKNOWN'

        close = data['Close']
        current = close.iloc[-1]

        # MA20 and MA50
        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]

        # 20-day return
        ret_20d = ((current / close.iloc[-20]) - 1) * 100

        # Volatility (20-day std)
        volatility = close.pct_change().rolling(20).std().iloc[-1] * 100

        # Classify
        if current > ma20 > ma50 and ret_20d > 2:
            return 'BULL'
        elif current < ma20 < ma50 and ret_20d < -2:
            return 'BEAR'
        else:
            return 'SIDEWAYS'

    except:
        return 'UNKNOWN'


def run_comprehensive_backtest():
    """Run comprehensive backtest across multiple periods"""

    print("=" * 100)
    print("🔬 COMPREHENSIVE BACKTEST (6-12 Months)")
    print("=" * 100)
    print(f"\nUniverse: {len(STOCK_UNIVERSE)} stocks")
    print("Target: 50-100 trades minimum")
    print("Testing: Filter-based Dynamic Exit\n")

    # Download SPY first to identify periods
    print("📥 Downloading SPY data...")
    spy = yf.Ticker('SPY')

    # Try to get 1 year of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    spy_data = spy.history(start=start_date, end=end_date)

    if spy_data.empty:
        print("❌ Failed to download SPY data")
        return

    print(f"✅ SPY data: {spy_data.index[0].strftime('%Y-%m-%d')} to {spy_data.index[-1].strftime('%Y-%m-%d')}")

    # Download stock data
    print(f"\n📥 Downloading {len(STOCK_UNIVERSE)} stocks...")
    stock_data = {}

    for i, symbol in enumerate(STOCK_UNIVERSE):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)
            if not hist.empty and len(hist) > 100:
                stock_data[symbol] = hist
                print(f"  ✅ {i+1}/{len(STOCK_UNIVERSE)}: {symbol} ({len(hist)} days)", end='\r')
        except:
            pass

    print(f"\n✅ Downloaded {len(stock_data)} stocks successfully")

    # Generate entry points (every 3-4 trading days to get more trades)
    all_dates = spy_data.index
    entry_indices = []

    # Start from 100 days before end, test every 3 days
    start_idx = max(100, len(all_dates) - 250)  # Up to 250 days back
    idx = start_idx

    while idx < len(all_dates) - 20:  # Need 20 days for exit
        entry_indices.append(idx)
        idx += 3  # Every 3 trading days

    entry_dates = [all_dates[i] for i in entry_indices]

    print(f"\n📅 Generated {len(entry_dates)} entry points")
    print(f"   From: {entry_dates[0].strftime('%Y-%m-%d')}")
    print(f"   To: {entry_dates[-1].strftime('%Y-%m-%d')}")

    # Identify market conditions for each period
    print("\n🌍 Analyzing market conditions...")
    market_conditions = {}
    for date in entry_dates:
        condition = identify_market_condition(spy_data, date)
        market_conditions[date] = condition

    # Count conditions
    condition_counts = defaultdict(int)
    for cond in market_conditions.values():
        condition_counts[cond] += 1

    print("\n📊 Market Condition Distribution:")
    for cond, count in sorted(condition_counts.items()):
        pct = count / len(entry_dates) * 100
        print(f"   {cond:10s}: {count:3d} periods ({pct:.1f}%)")

    # Run backtest
    print("\n🔬 Running backtest...")
    exit_engine = ExitRulesEngine()
    all_trades = []

    for i, entry_date in enumerate(entry_dates):
        # Show progress
        if (i + 1) % 10 == 0:
            print(f"  Processing entry {i+1}/{len(entry_dates)}...", end='\r')

        market_cond = market_conditions[entry_date]

        # Find stocks that pass filters
        passed_stocks = []
        for symbol, hist in stock_data.items():
            if apply_entry_filters(symbol, entry_date, hist, spy_data):
                passed_stocks.append(symbol)

        if not passed_stocks:
            continue

        # Limit to max 5 positions per entry to avoid over-concentration
        if len(passed_stocks) > 5:
            passed_stocks = passed_stocks[:5]

        # Simulate trades
        for symbol in passed_stocks:
            hist = stock_data[symbol]

            # Find entry index
            entry_idx = None
            for j, date in enumerate(hist.index):
                if date >= entry_date:
                    entry_idx = j
                    break

            if entry_idx is None or entry_idx + 20 >= len(hist):
                continue

            entry_price = hist['Close'].iloc[entry_idx]
            entry_actual_date = hist.index[entry_idx]

            # Simulate holding period
            exit_idx = None
            exit_reason = None

            for day in range(1, 21):
                check_idx = entry_idx + day
                if check_idx >= len(hist):
                    break

                position = {
                    'symbol': symbol,
                    'entry_date': entry_actual_date.strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'days_held': day,
                }

                check_date = hist.index[check_idx]
                should_exit, reason, details = exit_engine.check_exit(
                    position, check_date.strftime('%Y-%m-%d'), hist, spy_data
                )

                if should_exit:
                    exit_idx = check_idx
                    exit_reason = reason
                    break

            if exit_idx is None:
                exit_idx = min(entry_idx + 20, len(hist) - 1)
                exit_reason = 'MAX_HOLD'

            exit_price = hist['Close'].iloc[exit_idx]
            exit_date = hist.index[exit_idx]
            days_held = exit_idx - entry_idx

            actual_return = ((exit_price - entry_price) / entry_price) * 100

            holding_data = hist.iloc[entry_idx+1:exit_idx+1]
            max_high = holding_data['High'].max() if not holding_data.empty else exit_price
            max_return = ((max_high - entry_price) / entry_price) * 100

            trade = {
                'symbol': symbol,
                'entry_date': entry_actual_date,
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'actual_return': actual_return,
                'max_return': max_return,
                'days_held': days_held,
                'exit_reason': exit_reason,
                'market_condition': market_cond,
            }

            all_trades.append(trade)

    print(f"\n✅ Backtest complete: {len(all_trades)} trades\n")

    # Analysis
    return analyze_comprehensive_results(all_trades)


def analyze_comprehensive_results(trades):
    """Comprehensive analysis of backtest results"""

    if not trades:
        print("❌ No trades executed")
        return

    print("=" * 100)
    print("📊 COMPREHENSIVE BACKTEST RESULTS")
    print("=" * 100)

    # Overall stats
    total = len(trades)
    winners = [t for t in trades if t['actual_return'] > 0]
    losers = [t for t in trades if t['actual_return'] <= 0]

    returns = [t['actual_return'] for t in trades]
    win_rate = len(winners) / total * 100

    avg_return = np.mean(returns)
    median_return = np.median(returns)
    std_return = np.std(returns)

    avg_winner = np.mean([t['actual_return'] for t in winners]) if winners else 0
    avg_loser = np.mean([t['actual_return'] for t in losers]) if losers else 0

    expectancy = (len(winners)/total * avg_winner) + (len(losers)/total * avg_loser)

    # P&L
    total_pnl = sum([r * 10 for r in returns])  # $1000 per trade

    print(f"\n📈 OVERALL PERFORMANCE:")
    print(f"   Total Trades: {total}")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total})")
    print(f"   Avg Return: {avg_return:+.2f}%")
    print(f"   Median Return: {median_return:+.2f}%")
    print(f"   Std Dev: {std_return:.2f}%")
    print(f"   Expectancy: {expectancy:+.2f}%")

    print(f"\n💰 RETURNS:")
    print(f"   Winners Avg: {avg_winner:+.2f}%")
    print(f"   Losers Avg: {avg_loser:+.2f}%")
    print(f"   Best: {max(returns):+.2f}%")
    print(f"   Worst: {min(returns):+.2f}%")
    print(f"   Risk-Reward: {abs(avg_winner/avg_loser):.2f}:1")

    print(f"\n💵 P&L ($1000/trade):")
    print(f"   Total: ${total_pnl:+,.2f}")
    print(f"   ROI: {total_pnl/(total*1000)*100:+.1f}%")

    # By market condition
    print(f"\n📊 PERFORMANCE BY MARKET CONDITION:")
    print("=" * 100)

    conditions = {}
    for trade in trades:
        cond = trade['market_condition']
        if cond not in conditions:
            conditions[cond] = []
        conditions[cond].append(trade)

    for cond in sorted(conditions.keys()):
        cond_trades = conditions[cond]
        cond_winners = [t for t in cond_trades if t['actual_return'] > 0]
        cond_returns = [t['actual_return'] for t in cond_trades]

        cond_wr = len(cond_winners) / len(cond_trades) * 100
        cond_avg = np.mean(cond_returns)
        cond_best = max(cond_returns)
        cond_worst = min(cond_returns)

        print(f"\n{cond} Market ({len(cond_trades)} trades):")
        print(f"   Win Rate: {cond_wr:.1f}% ({len(cond_winners)}/{len(cond_trades)})")
        print(f"   Avg Return: {cond_avg:+.2f}%")
        print(f"   Best/Worst: {cond_best:+.2f}% / {cond_worst:+.2f}%")

    # Consecutive wins/losses
    print(f"\n📊 STREAK ANALYSIS:")
    print("=" * 100)

    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for trade in trades:
        if trade['actual_return'] > 0:
            current_win_streak += 1
            current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        else:
            current_loss_streak += 1
            current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)

    print(f"   Max Win Streak: {max_win_streak}")
    print(f"   Max Loss Streak: {max_loss_streak}")

    # Drawdown
    cumulative_returns = []
    cumulative = 0
    for r in returns:
        cumulative += r
        cumulative_returns.append(cumulative)

    max_dd = 0
    peak = cumulative_returns[0]
    for cr in cumulative_returns:
        if cr > peak:
            peak = cr
        dd = peak - cr
        if dd > max_dd:
            max_dd = dd

    print(f"   Max Drawdown: {max_dd:.2f}%")

    # Statistical significance
    print(f"\n📊 STATISTICAL ANALYSIS:")
    print("=" * 100)

    # Standard error
    se = std_return / np.sqrt(total)

    # 95% confidence interval for mean return
    ci_95 = 1.96 * se

    print(f"   Sample Size: {total} trades")
    print(f"   Standard Error: {se:.2f}%")
    print(f"   95% Confidence Interval: {avg_return-ci_95:+.2f}% to {avg_return+ci_95:+.2f}%")

    # Is it statistically significant?
    t_stat = avg_return / se

    print(f"   t-statistic: {t_stat:.2f}")

    if abs(t_stat) > 1.96:
        print(f"   ✅ STATISTICALLY SIGNIFICANT (95% confidence)")
    else:
        print(f"   ⚠️  Not statistically significant")

    # Exit reasons
    print(f"\n🚪 EXIT REASONS:")
    exit_reasons = defaultdict(int)
    for t in trades:
        exit_reasons[t['exit_reason']] += 1

    for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        pct = count / total * 100
        print(f"   {reason:15s}: {count:3d} ({pct:.1f}%)")

    # Monthly breakdown
    print(f"\n📅 MONTHLY BREAKDOWN:")
    print("=" * 100)

    monthly = defaultdict(list)
    for trade in trades:
        month_key = trade['entry_date'].strftime('%Y-%m')
        monthly[month_key].append(trade)

    for month in sorted(monthly.keys()):
        month_trades = monthly[month]
        month_winners = [t for t in month_trades if t['actual_return'] > 0]
        month_returns = [t['actual_return'] for t in month_trades]

        month_wr = len(month_winners) / len(month_trades) * 100
        month_avg = np.mean(month_returns)
        month_total = sum([r * 10 for r in month_returns])

        print(f"\n{month}:")
        print(f"   Trades: {len(month_trades)}")
        print(f"   Win Rate: {month_wr:.1f}%")
        print(f"   Avg Return: {month_avg:+.2f}%")
        print(f"   Total P&L: ${month_total:+,.0f}")

    # Final verdict
    print(f"\n\n{'='*100}")
    print("🎯 FINAL VERDICT")
    print("=" * 100)

    # Criteria for "good" strategy
    criteria_met = 0
    total_criteria = 5

    print(f"\n✅ Quality Criteria:")

    # 1. Sample size
    if total >= 50:
        print(f"   ✅ Sample Size: {total} trades (≥50)")
        criteria_met += 1
    else:
        print(f"   ⚠️  Sample Size: {total} trades (need ≥50)")

    # 2. Win rate
    if win_rate >= 60:
        print(f"   ✅ Win Rate: {win_rate:.1f}% (≥60%)")
        criteria_met += 1
    else:
        print(f"   ⚠️  Win Rate: {win_rate:.1f}% (target ≥60%)")

    # 3. Expectancy
    if expectancy >= 2.0:
        print(f"   ✅ Expectancy: {expectancy:+.2f}% (≥2%)")
        criteria_met += 1
    else:
        print(f"   ⚠️  Expectancy: {expectancy:+.2f}% (target ≥2%)")

    # 4. Risk-reward
    rr = abs(avg_winner/avg_loser) if avg_loser != 0 else 0
    if rr >= 2.0:
        print(f"   ✅ Risk-Reward: {rr:.2f}:1 (≥2:1)")
        criteria_met += 1
    else:
        print(f"   ⚠️  Risk-Reward: {rr:.2f}:1 (target ≥2:1)")

    # 5. Consistency across market conditions
    all_conditions_positive = all(
        np.mean([t['actual_return'] for t in trades_list]) > 0
        for trades_list in conditions.values() if len(trades_list) > 5
    )

    if all_conditions_positive:
        print(f"   ✅ Consistency: Positive in all market conditions")
        criteria_met += 1
    else:
        print(f"   ⚠️  Consistency: Not positive in all conditions")

    print(f"\n📊 Score: {criteria_met}/{total_criteria} criteria met")

    if criteria_met >= 4:
        print(f"\n✅ EXCELLENT! Strategy is robust and ready to use! 🚀")
    elif criteria_met >= 3:
        print(f"\n👍 GOOD! Strategy shows promise, continue monitoring")
    else:
        print(f"\n⚠️  NEEDS IMPROVEMENT: More work needed")

    print("=" * 100)

    return {
        'total_trades': total,
        'win_rate': win_rate,
        'expectancy': expectancy,
        'avg_return': avg_return,
        'total_pnl': total_pnl,
        'criteria_met': criteria_met,
    }


if __name__ == "__main__":
    results = run_comprehensive_backtest()
