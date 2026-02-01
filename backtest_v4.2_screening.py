#!/usr/bin/env python3
"""
Backtest v4.2 Screening - ทดสอบว่า screener ค้นหาหุ้นได้ดีแค่ไหน
ใช้ v4.2 Anti-Extended criteria + NEW Trailing Stop
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from api.data_manager import DataManager

logger.info("=" * 80)
logger.info("🔬 BACKTEST v4.2 SCREENING + NEW TRAILING STOP")
logger.info("=" * 80)
logger.info("")

# v4.2 Anti-Extended Criteria
V4_2_CRITERIA = {
    'momentum_max': 38,      # Reject extended (>38%)
    'rsi_min': 45,
    'rsi_max': 72,          # Anti-extended (was 65 in v5.1)
    'volume_min': 0.8,
    'volume_max': 1.8,
    'ma20_vs_ma50_min': 0,  # Uptrend
    'momentum_5d_min': -8,  # Not in freefall
}

logger.info("🎯 v4.2 Anti-Extended Criteria:")
logger.info(f"   Momentum: ANY positive, but <{V4_2_CRITERIA['momentum_max']}%")
logger.info(f"   RSI: {V4_2_CRITERIA['rsi_min']}-{V4_2_CRITERIA['rsi_max']}")
logger.info(f"   Volume: {V4_2_CRITERIA['volume_min']}-{V4_2_CRITERIA['volume_max']}x")
logger.info(f"   MA20 > MA50: Yes")
logger.info(f"   5d momentum > {V4_2_CRITERIA['momentum_5d_min']}%")
logger.info("")

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def passes_v4_2_screening(data, symbol, check_date):
    """
    Check if stock passes v4.2 Anti-Extended screening

    Returns: (passes, reason, metrics)
    """
    try:
        df = data[data.index <= check_date].copy()
        if len(df) < 50:
            return False, "Insufficient data", {}

        close = df['Close']
        volume = df['Volume']
        current_price = float(close.iloc[-1])

        metrics = {}

        # 1. RSI
        rsi = calculate_rsi(close, 14)
        current_rsi = float(rsi.iloc[-1])
        metrics['rsi'] = current_rsi

        if current_rsi < V4_2_CRITERIA['rsi_min']:
            return False, f"RSI too low ({current_rsi:.1f} < {V4_2_CRITERIA['rsi_min']})", metrics
        if current_rsi > V4_2_CRITERIA['rsi_max']:
            return False, f"RSI extended ({current_rsi:.1f} > {V4_2_CRITERIA['rsi_max']})", metrics

        # 2. Momentum 30d
        if len(close) >= 30:
            price_30d_ago = float(close.iloc[-30])
            momentum_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100
            metrics['momentum_30d'] = momentum_30d

            if momentum_30d > V4_2_CRITERIA['momentum_max']:
                return False, f"Momentum extended ({momentum_30d:.1f}% > {V4_2_CRITERIA['momentum_max']}%)", metrics
        else:
            return False, "Insufficient data for momentum", metrics

        # 3. Momentum 5d
        if len(close) >= 5:
            price_5d_ago = float(close.iloc[-5])
            momentum_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100
            metrics['momentum_5d'] = momentum_5d

            if momentum_5d < V4_2_CRITERIA['momentum_5d_min']:
                return False, f"Freefall ({momentum_5d:.1f}% < {V4_2_CRITERIA['momentum_5d_min']}%)", metrics

        # 4. Volume ratio
        if len(volume) >= 20:
            avg_volume = float(volume.iloc[-20:].mean())
            current_volume = float(volume.iloc[-1])
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            metrics['volume_ratio'] = volume_ratio

            if volume_ratio < V4_2_CRITERIA['volume_min']:
                return False, f"Volume too low ({volume_ratio:.2f}x < {V4_2_CRITERIA['volume_min']}x)", metrics
            if volume_ratio > V4_2_CRITERIA['volume_max']:
                return False, f"Volume too high ({volume_ratio:.2f}x > {V4_2_CRITERIA['volume_max']}x)", metrics

        # 5. MA20 vs MA50
        if len(close) >= 50:
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma20_vs_ma50 = ((ma20 - ma50) / ma50) * 100
            metrics['ma20_vs_ma50'] = ma20_vs_ma50

            if ma20_vs_ma50 < V4_2_CRITERIA['ma20_vs_ma50_min']:
                return False, f"Downtrend (MA20 < MA50)", metrics

        # All checks passed
        return True, "PASS", metrics

    except Exception as e:
        logger.error(f"Error checking {symbol}: {e}")
        return False, f"Error: {e}", {}

def simulate_trailing_stop(entry_price, highest_price, min_return):
    """
    Simulate NEW trailing stop (Breakeven Protection)
    """
    profit_pct = ((highest_price - entry_price) / entry_price) * 100

    if profit_pct > 0:
        # Calculate trailing threshold
        if profit_pct >= 5.0:
            trailing_pct = -3.0
        elif profit_pct >= 2.0:
            trailing_pct = -4.0
        else:
            trailing_pct = max(-1.0, -(profit_pct - 0.5))

        # Estimate if trailing would trigger
        exit_price_at_min = entry_price * (1 + min_return/100)
        drawdown_from_peak = ((exit_price_at_min - highest_price) / highest_price) * 100

        if drawdown_from_peak <= trailing_pct:
            exit_price = highest_price * (1 + trailing_pct/100)
            exit_return = ((exit_price - entry_price) / entry_price) * 100
            return True, exit_price, exit_return, 'TRAILING_STOP'

    return False, None, None, None

# Test stocks (same as before)
test_stocks = [
    'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'NVDA', 'TSLA', 'META',
    'AVGO', 'ASML', 'AMD', 'QCOM', 'MU', 'INTC', 'TSM',
    'AMAT', 'LRCX', 'KLAC', 'SNPS', 'CDNS', 'MRVL',
    'SNOW', 'CRWD', 'DDOG', 'NET', 'ZS', 'OKTA',
    'SHOP', 'SQ', 'COIN', 'HOOD', 'RBLX', 'U',
    'ARWR', 'VRTX', 'MRNA', 'ILMN', 'REGN', 'BIIB',
    'SCCO', 'FCX', 'NEM', 'GOLD', 'PATH', 'PLTR',
    'DKNG', 'PENN', 'RIVN', 'LCID'
]

# Test dates
test_dates = [
    '2025-10-15', '2025-10-20', '2025-10-25',
    '2025-11-05', '2025-11-10', '2025-11-15', '2025-11-20', '2025-11-25',
    '2025-12-01', '2025-12-05', '2025-12-10', '2025-12-15', '2025-12-20'
]

dm = DataManager()

logger.info(f"Testing {len(test_stocks)} stocks across {len(test_dates)} dates")
logger.info(f"Total scenarios: {len(test_stocks) * len(test_dates)}")
logger.info("")

passed_stocks = []
failed_stocks = []
total_tested = 0

logger.info("🔄 Running screening tests...")
logger.info("")

for date_str in test_dates:
    entry_date = datetime.strptime(date_str, '%Y-%m-%d')
    exit_date = entry_date + timedelta(days=30)

    date_passed = 0
    date_failed = 0

    for symbol in test_stocks:
        total_tested += 1

        try:
            # Get data
            data = dm.get_price_data(symbol, period='1y')
            if data is None or data.empty:
                failed_stocks.append({
                    'symbol': symbol,
                    'entry_date': date_str,
                    'reason': 'No data'
                })
                date_failed += 1
                continue

            # Fix data structure: set 'date' column as index
            if 'date' in data.columns:
                data['date'] = pd.to_datetime(data['date'])
                data = data.set_index('date')

            # Standardize column names to uppercase
            data.columns = data.columns.str.capitalize()

            # Make sure index is datetime
            if not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)

            # Remove timezone if present
            if hasattr(data.index, 'tz') and data.index.tz is not None:
                data.index = data.index.tz_localize(None)

            # Check screening
            passes, reason, metrics = passes_v4_2_screening(data, symbol, entry_date)

            if passes:
                # Get entry price
                entry_data = data[data.index <= entry_date]
                if entry_data.empty:
                    continue

                entry_price = float(entry_data['Close'].iloc[-1])

                # Get exit data (30 days)
                future_data = data[(data.index > entry_date) & (data.index <= exit_date)]
                if future_data.empty:
                    continue

                # Calculate returns
                max_price = float(future_data['High'].max())
                min_price = float(future_data['Low'].min())
                exit_price = float(future_data['Close'].iloc[-1])

                max_return = ((max_price - entry_price) / entry_price) * 100
                min_return = ((min_price - entry_price) / entry_price) * 100
                actual_return = ((exit_price - entry_price) / entry_price) * 100

                # Apply NEW trailing stop
                highest_price = max_price
                trailing_triggered, new_exit_price, new_return, _ = simulate_trailing_stop(
                    entry_price, highest_price, min_return
                )

                final_return = new_return if trailing_triggered else actual_return
                final_exit = new_exit_price if trailing_triggered else exit_price

                passed_stocks.append({
                    'symbol': symbol,
                    'entry_date': date_str,
                    'entry_price': entry_price,
                    'exit_price': final_exit,
                    'actual_return': final_return,
                    'max_return': max_return,
                    'min_return': min_return,
                    'trailing_triggered': trailing_triggered,
                    'rsi': metrics.get('rsi', 0),
                    'momentum_30d': metrics.get('momentum_30d', 0),
                    'volume_ratio': metrics.get('volume_ratio', 0),
                })
                date_passed += 1
            else:
                failed_stocks.append({
                    'symbol': symbol,
                    'entry_date': date_str,
                    'reason': reason
                })
                date_failed += 1

        except Exception as e:
            logger.error(f"Error processing {symbol} on {date_str}: {e}")
            failed_stocks.append({
                'symbol': symbol,
                'entry_date': date_str,
                'reason': f'Error: {e}'
            })
            date_failed += 1

    pass_rate = (date_passed / len(test_stocks) * 100) if len(test_stocks) > 0 else 0
    logger.info(f"{date_str}: {date_passed}/{len(test_stocks)} passed ({pass_rate:.1f}%)")

# Save results
df_passed = pd.DataFrame(passed_stocks)
df_failed = pd.DataFrame(failed_stocks)

df_passed.to_csv('backtest_v4.2_screening_passed.csv', index=False)
df_failed.to_csv('backtest_v4.2_screening_failed.csv', index=False)

logger.info("")
logger.info("=" * 80)
logger.info("📊 SCREENING RESULTS")
logger.info("=" * 80)
logger.info("")

total_passed = len(passed_stocks)
total_failed = len(failed_stocks)
pass_rate = (total_passed / total_tested * 100) if total_tested > 0 else 0

logger.info(f"Total tested: {total_tested} scenarios")
logger.info(f"Passed screening: {total_passed} ({pass_rate:.1f}%)")
logger.info(f"Failed screening: {total_failed}")
logger.info("")

if len(df_passed) > 0:
    # Calculate performance
    winners = len(df_passed[df_passed['actual_return'] > 0])
    losers = len(df_passed[df_passed['actual_return'] <= 0])
    win_rate = (winners / len(df_passed) * 100)
    avg_return = df_passed['actual_return'].mean()
    median_return = df_passed['actual_return'].median()

    # Big losers
    big_losers = df_passed[df_passed['actual_return'] < -10]

    logger.info("=" * 80)
    logger.info("📈 PERFORMANCE OF STOCKS THAT PASSED SCREENING")
    logger.info("=" * 80)
    logger.info("")

    logger.info(f"Trades: {len(df_passed)}")
    logger.info(f"Winners: {winners} ({win_rate:.1f}%)")
    logger.info(f"Losers: {losers}")
    logger.info(f"Avg Return: {avg_return:+.2f}%")
    logger.info(f"Median Return: {median_return:+.2f}%")
    logger.info(f"Big Losers (<-10%): {len(big_losers)}")
    logger.info("")

    # Trailing stop impact
    trailing_count = len(df_passed[df_passed['trailing_triggered'] == True])
    logger.info(f"Trailing stop triggered: {trailing_count}/{len(df_passed)} trades ({trailing_count/len(df_passed)*100:.1f}%)")
    logger.info("")

    # Top performers
    top_winners = df_passed.nlargest(10, 'actual_return')
    logger.info("🏆 Top 10 Winners:")
    logger.info(f"{'Symbol':<8} {'Date':<12} {'Return':<10} {'Max Gain'}")
    logger.info("-" * 50)
    for _, row in top_winners.iterrows():
        logger.info(f"{row['symbol']:<8} {row['entry_date']:<12} {row['actual_return']:>7.2f}%   {row['max_return']:>7.2f}%")

    logger.info("")

    # Worst performers
    worst_losers = df_passed.nsmallest(10, 'actual_return')
    logger.info("💀 Bottom 10 (Worst):")
    logger.info(f"{'Symbol':<8} {'Date':<12} {'Return':<10} {'Max Gain'}")
    logger.info("-" * 50)
    for _, row in worst_losers.iterrows():
        logger.info(f"{row['symbol']:<8} {row['entry_date']:<12} {row['actual_return']:>7.2f}%   {row['max_return']:>7.2f}%")

    logger.info("")

# Common rejection reasons
logger.info("=" * 80)
logger.info("🚫 TOP REJECTION REASONS")
logger.info("=" * 80)
logger.info("")

from collections import Counter
rejection_reasons = Counter([f['reason'] for f in failed_stocks])

for reason, count in rejection_reasons.most_common(10):
    pct = (count / len(failed_stocks) * 100) if len(failed_stocks) > 0 else 0
    logger.info(f"  {count:3d} ({pct:5.1f}%): {reason}")

logger.info("")
logger.info("=" * 80)
logger.info("🎯 SUMMARY")
logger.info("=" * 80)
logger.info("")

logger.info(f"✅ Screening Pass Rate: {pass_rate:.1f}%")
if len(df_passed) > 0:
    logger.info(f"✅ Win Rate: {win_rate:.1f}%")
    logger.info(f"✅ Median Return: {median_return:+.2f}%")
    logger.info(f"✅ Avg Return: {avg_return:+.2f}%")
    logger.info(f"✅ Big Losers: {len(big_losers)}")

logger.info("")
logger.info("📁 Results saved:")
logger.info("   backtest_v4.2_screening_passed.csv")
logger.info("   backtest_v4.2_screening_failed.csv")
logger.info("=" * 80)
