#!/usr/bin/env python3
"""
Comprehensive Backtest for v5.0 Momentum Continuation Screener
Compare directly with v4.2 results
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from api.data_manager import DataManager

# v5.2 criteria (FURTHER RELAXED: momentum 8-30%, 52w >60%)
V5_CRITERIA = {
    'momentum_min': 8,   # CHANGED from 10 (v5.1 still too strict!)
    'momentum_max': 30,  # CHANGED from 25
    'rsi_min': 45,
    'rsi_max': 65,
    'volume_min': 0.8,
    'volume_max_high_mom': 2.0,  # For momentum >= 20%
    'volume_max_mod_mom': 1.8,   # For momentum 8-20%
    'position_52w_min': 60,  # CHANGED from 70 (major bottleneck!)
    'ma20_vs_ma50_min': 0,  # Just uptrend
    'momentum_5d_min': -8,  # Not in freefall
}

def calculate_52w_position(close_series):
    """Calculate 52-week position (0-100%)"""
    if len(close_series) >= 252:
        high_52w = close_series.iloc[-252:].max()
        low_52w = close_series.iloc[-252:].min()
    else:
        high_52w = close_series.max()
        low_52w = close_series.min()

    if high_52w > low_52w:
        current = close_series.iloc[-1]
        return ((current - low_52w) / (high_52w - low_52w)) * 100
    return 50.0

def passes_v5_criteria(stock_data, symbol, entry_date):
    """Check if stock passes v5.0 momentum continuation criteria"""
    try:
        # Prepare DataFrame - set date as index
        df_prep = stock_data.copy()
        if 'date' in df_prep.columns:
            df_prep['date'] = pd.to_datetime(df_prep['date'])
            df_prep = df_prep.set_index('date')

        # Remove timezone from index for comparison
        if hasattr(df_prep.index, 'tz') and df_prep.index.tz is not None:
            df_prep.index = df_prep.index.tz_localize(None)

        # Get data up to entry date
        df = df_prep[df_prep.index <= entry_date].copy()
        if len(df) < 60:  # Need at least 60 days
            return False, "Insufficient data"

        # Use lowercase column names
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        current_price = close.iloc[-1]

        # Calculate metrics
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_current = rsi.iloc[-1]

        # Momentum
        if len(close) >= 30:
            momentum_30d = ((close.iloc[-1] / close.iloc[-30]) - 1) * 100
        else:
            return False, "Need 30 days for momentum"

        if len(close) >= 5:
            momentum_5d = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100
        else:
            momentum_5d = 0

        # Volume ratio
        avg_volume = volume.iloc[-20:].mean()
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        # 52-week position (NEW in v5.0!)
        position_52w = calculate_52w_position(close)

        # MA20 vs MA50
        ma20 = close.rolling(window=20).mean().iloc[-1]
        ma50 = close.rolling(window=50).mean().iloc[-1]
        ma20_vs_ma50 = ((ma20 / ma50) - 1) * 100 if ma50 > 0 else 0

        # Gate 1: Momentum 8-30% (v5.2: further relaxed from 10-25%)
        if momentum_30d < V5_CRITERIA['momentum_min']:
            return False, f"Momentum too weak ({momentum_30d:.1f}% < 8%)"
        if momentum_30d > V5_CRITERIA['momentum_max']:
            return False, f"Momentum exhausted ({momentum_30d:.1f}% > 30%)"

        # Gate 2: Context-dependent volume
        if momentum_30d >= 20:
            # Very high momentum - can handle higher volume
            if volume_ratio < V5_CRITERIA['volume_min']:
                return False, f"Volume too low ({volume_ratio:.2f} < 0.8)"
            if volume_ratio > V5_CRITERIA['volume_max_high_mom']:
                return False, f"Volume too high ({volume_ratio:.2f} > 2.0)"
        else:
            # Good momentum - golden combo zone
            if volume_ratio < V5_CRITERIA['volume_min']:
                return False, f"Volume too low ({volume_ratio:.2f} < 0.8)"
            if volume_ratio > V5_CRITERIA['volume_max_mod_mom']:
                return False, f"Volume too high ({volume_ratio:.2f} > 1.8)"

        # Gate 3: RSI 45-65
        if rsi_current < V5_CRITERIA['rsi_min']:
            return False, f"RSI too low ({rsi_current:.1f} < 45)"
        if rsi_current > V5_CRITERIA['rsi_max']:
            return False, f"RSI too high ({rsi_current:.1f} > 65)"

        # Gate 4: 52-week position > 60% (v5.2: relaxed from 70%)
        if position_52w < V5_CRITERIA['position_52w_min']:
            return False, f"Not near 52w high ({position_52w:.1f}% < 60%)"

        # Gate 5: MA20 > MA50 (uptrend)
        if ma20_vs_ma50 < V5_CRITERIA['ma20_vs_ma50_min']:
            return False, f"Downtrend (MA20 < MA50)"

        # Gate 6: Not in freefall
        if momentum_5d < V5_CRITERIA['momentum_5d_min']:
            return False, f"Freefall ({momentum_5d:.1f}% < -8%)"

        # All gates passed!
        metrics = {
            'rsi': rsi_current,
            'momentum_30d': momentum_30d,
            'momentum_5d': momentum_5d,
            'volume_ratio': volume_ratio,
            'position_52w': position_52w,
            'ma20_vs_ma50': ma20_vs_ma50,
            'entry_price': current_price
        }

        return True, metrics

    except Exception as e:
        return False, f"Error: {str(e)}"

def backtest_v5():
    """Run comprehensive backtest on v5.2 criteria"""

    logger.info("🔬 COMPREHENSIVE BACKTEST - v5.2 MOMENTUM CONTINUATION (FURTHER RELAXED)")
    logger.info("=" * 80)
    logger.info("v5.2 Changes:")
    logger.info("  • Momentum: 8-30% (relaxed from v5.1's 10-25%)")
    logger.info("  • 52w Position: >60% (relaxed from v5.1's >70%)")
    logger.info("")

    # Use same stocks and dates as v4.2 comprehensive test
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

    # Test dates (same as v4.2 comprehensive test)
    test_dates = [
        '2025-10-15', '2025-10-20', '2025-10-25',
        '2025-11-05', '2025-11-10', '2025-11-15', '2025-11-20', '2025-11-25',
        '2025-12-01', '2025-12-05', '2025-12-10', '2025-12-15', '2025-12-20'
    ]

    dm = DataManager()

    all_results = []
    stocks_tested = 0
    stocks_passed = 0

    logger.info(f"Testing {len(test_stocks)} stocks across {len(test_dates)} dates")
    logger.info(f"Total scenarios: {len(test_stocks) * len(test_dates)}")
    logger.info("")

    for entry_date_str in test_dates:
        entry_date = pd.Timestamp(entry_date_str)
        exit_date = entry_date + timedelta(days=30)

        logger.info(f"📅 Testing entry date: {entry_date_str}")

        passed_this_date = 0

        for symbol in test_stocks:
            stocks_tested += 1

            try:
                # Get data (use 2y to ensure enough historical data)
                df = dm.get_price_data(symbol, period="2y", interval="1d")
                if df is None or len(df) < 60:
                    continue

                # Check v5.0 criteria
                passes, result = passes_v5_criteria(df, symbol, entry_date)

                if not passes:
                    continue

                stocks_passed += 1
                passed_this_date += 1

                # Get metrics
                metrics = result
                entry_price = metrics['entry_price']

                # Prepare full DataFrame for future data
                df_full = df.copy()
                if 'date' in df_full.columns:
                    df_full['date'] = pd.to_datetime(df_full['date'])
                    df_full = df_full.set_index('date')

                # Remove timezone from index
                if hasattr(df_full.index, 'tz') and df_full.index.tz is not None:
                    df_full.index = df_full.index.tz_localize(None)

                # Calculate returns (30-day hold)
                future_data = df_full[(df_full.index > entry_date) & (df_full.index <= exit_date)]
                if len(future_data) == 0:
                    continue

                exit_price = future_data['close'].iloc[-1]

                # Calculate metrics during hold
                max_price = future_data['high'].max()
                min_price = future_data['low'].min()

                actual_return = ((exit_price / entry_price) - 1) * 100
                max_return = ((max_price / entry_price) - 1) * 100
                min_return = ((min_price / entry_price) - 1) * 100

                hit_12pct = max_return >= 12
                hit_15pct = max_return >= 15

                all_results.append({
                    'symbol': symbol,
                    'entry_date': entry_date_str,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'actual_return': actual_return,
                    'max_return': max_return,
                    'min_return': min_return,
                    'hit_12pct': hit_12pct,
                    'hit_15pct': hit_15pct,
                    'rsi': metrics['rsi'],
                    'momentum_30d': metrics['momentum_30d'],
                    'volume_ratio': metrics['volume_ratio'],
                    'position_52w': metrics['position_52w'],
                })

            except Exception as e:
                logger.error(f"Error testing {symbol}: {e}")
                continue

        logger.info(f"   Passed v5.0 filters: {passed_this_date} stocks")

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 BACKTEST RESULTS - v5.2 MOMENTUM CONTINUATION (FURTHER RELAXED)")
    logger.info("=" * 80)

    if len(all_results) == 0:
        logger.error("❌ No stocks passed v5.2 filters!")
        return

    # Convert to DataFrame
    results_df = pd.DataFrame(all_results)

    # Calculate statistics
    total_trades = len(results_df)
    winners = results_df[results_df['actual_return'] > 0]
    losers = results_df[results_df['actual_return'] <= 0]

    win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0
    avg_return = results_df['actual_return'].mean()
    median_return = results_df['actual_return'].median()

    hit_12_rate = (results_df['hit_12pct'].sum() / total_trades * 100) if total_trades > 0 else 0
    hit_15_rate = (results_df['hit_15pct'].sum() / total_trades * 100) if total_trades > 0 else 0

    logger.info(f"Total scenarios tested: {stocks_tested}")
    logger.info(f"Passed v5.2 filters: {stocks_passed} ({stocks_passed/stocks_tested*100:.1f}%)")
    logger.info(f"Total trades: {total_trades}")
    logger.info("")

    logger.info("🎯 OVERALL PERFORMANCE:")
    logger.info(f"   Win Rate: {win_rate:.1f}%")
    logger.info(f"   Avg Return: {avg_return:+.2f}%")
    logger.info(f"   Median Return: {median_return:+.2f}%")
    logger.info(f"   Hit 12% Target: {hit_12_rate:.1f}%")
    logger.info(f"   Hit 15% Target: {hit_15_rate:.1f}%")
    logger.info("")

    logger.info("📈 WINNERS:")
    logger.info(f"   Count: {len(winners)}")
    logger.info(f"   Avg Return: {winners['actual_return'].mean():+.2f}%")
    logger.info(f"   Best: {results_df['actual_return'].max():+.2f}%")
    logger.info("")

    logger.info("📉 LOSERS:")
    logger.info(f"   Count: {len(losers)}")
    logger.info(f"   Avg Return: {losers['actual_return'].mean():+.2f}%")
    logger.info(f"   Worst: {results_df['actual_return'].min():+.2f}%")
    logger.info("")

    # Top performers
    logger.info("🏆 TOP 10 PERFORMERS:")
    top10 = results_df.nlargest(10, 'actual_return')
    for idx, row in top10.iterrows():
        logger.info(f"   {row['symbol']:6s} {row['entry_date']:10s} → {row['actual_return']:+7.2f}% (Max: {row['max_return']:+.1f}%)")
    logger.info("")

    # Bottom performers
    logger.info("💔 BOTTOM 10 PERFORMERS:")
    bottom10 = results_df.nsmallest(10, 'actual_return')
    for idx, row in bottom10.iterrows():
        logger.info(f"   {row['symbol']:6s} {row['entry_date']:10s} → {row['actual_return']:+7.2f}% (Min: {row['min_return']:+.1f}%)")
    logger.info("")

    # Compare with v4.2, v5.0, v5.1
    logger.info("=" * 80)
    logger.info("📊 COMPARISON: v5.2 vs v5.1 vs v4.2")
    logger.info("=" * 80)
    logger.info("")
    logger.info("v4.2 Comprehensive Test:")
    logger.info("   Win Rate: 47.9%")
    logger.info("   Avg Return: +2.67%")
    logger.info("   Median Return: +4.80%")
    logger.info("   Trades: 47")
    logger.info("")
    logger.info("v5.1 Results:")
    logger.info("   Win Rate: 58.1%")
    logger.info("   Avg Return: +5.59% (WITH outliers)")
    logger.info("   Avg Return: +1.19% (WITHOUT ARWR)")
    logger.info("   Median Return: +2.39%")
    logger.info("   Pass Rate: 5.0%")
    logger.info("   Trades: 31")
    logger.info("")
    logger.info("v5.2 Actual Results (THIS TEST):")
    logger.info(f"   Win Rate: {win_rate:.1f}% ({win_rate - 47.9:+.1f}% vs v4.2)")
    logger.info(f"   Avg Return: {avg_return:+.2f}% ({avg_return - 2.67:+.2f}% vs v4.2)")
    logger.info(f"   Median Return: {median_return:+.2f}% ({median_return - 4.80:+.2f}% vs v4.2)")
    logger.info(f"   Pass Rate: {stocks_passed/stocks_tested*100:.1f}%")
    logger.info(f"   Trades: {total_trades}")
    logger.info(f"   Criteria: Momentum 8-30%, 52w >60%")
    logger.info("")

    # Decision logic
    logger.info("=" * 80)
    logger.info("🎯 FINAL DECISION")
    logger.info("=" * 80)
    logger.info("")

    # Calculate which is better
    v42_better_count = 0
    v52_better_count = 0

    if win_rate > 47.9:
        logger.info(f"✅ v5.2 WIN RATE BETTER: {win_rate:.1f}% vs 47.9% (+{win_rate - 47.9:.1f}%)")
        v52_better_count += 1
    else:
        logger.info(f"❌ v4.2 WIN RATE BETTER: 47.9% vs {win_rate:.1f}% (+{47.9 - win_rate:.1f}%)")
        v42_better_count += 1

    if avg_return > 2.67:
        logger.info(f"✅ v5.2 AVG RETURN BETTER: {avg_return:+.2f}% vs +2.67% ({avg_return - 2.67:+.2f}%)")
        v52_better_count += 1
    else:
        logger.info(f"❌ v4.2 AVG RETURN BETTER: +2.67% vs {avg_return:+.2f}% (+{2.67 - avg_return:.2f}%)")
        v42_better_count += 1

    if median_return > 4.80:
        logger.info(f"✅ v5.2 MEDIAN RETURN BETTER: {median_return:+.2f}% vs +4.80% ({median_return - 4.80:+.2f}%)")
        v52_better_count += 1
    else:
        logger.info(f"❌ v4.2 MEDIAN RETURN BETTER: +4.80% vs {median_return:+.2f}% (+{4.80 - median_return:.2f}%)")
        v42_better_count += 1

    logger.info("")
    logger.info(f"Score: v5.2 = {v52_better_count}, v4.2 = {v42_better_count}")
    logger.info("")

    if v52_better_count > v42_better_count:
        logger.info("🏆 WINNER: v5.2 (Momentum Continuation)")
        logger.info("   ✅ Use v5.2 in production")
        recommendation = "v5.2"
    else:
        logger.info("🏆 WINNER: v4.2 (Original Criteria)")
        logger.info("   ✅ Revert to v4.2 in production")
        recommendation = "v4.2"

    # Save results
    results_df.to_csv('backtest_v5.2_results.csv', index=False)
    logger.info("")
    logger.info("💾 Results saved to: backtest_v5.2_results.csv")
    logger.info("")
    logger.info(f"📌 RECOMMENDATION: Use **{recommendation}**")

    return results_df

if __name__ == "__main__":
    backtest_v5()
