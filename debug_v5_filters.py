#!/usr/bin/env python3
"""
Debug v5.0 filters - see why stocks are failing
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
import sys
import os
from collections import Counter

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from api.data_manager import DataManager

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

def check_v5_filters(stock_data, symbol, entry_date):
    """Check each v5.0 filter and report failures"""
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
        if len(df) < 60:
            return {'failed_at': 'insufficient_data', 'metrics': {}}

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
            return {'failed_at': 'momentum_calc', 'metrics': {}}

        if len(close) >= 5:
            momentum_5d = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100
        else:
            momentum_5d = 0

        # Volume ratio
        avg_volume = volume.iloc[-20:].mean()
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        # 52-week position
        position_52w = calculate_52w_position(close)

        # MA20 vs MA50
        ma20 = close.rolling(window=20).mean().iloc[-1]
        ma50 = close.rolling(window=50).mean().iloc[-1]
        ma20_vs_ma50 = ((ma20 / ma50) - 1) * 100 if ma50 > 0 else 0

        metrics = {
            'rsi': rsi_current,
            'momentum_30d': momentum_30d,
            'momentum_5d': momentum_5d,
            'volume_ratio': volume_ratio,
            'position_52w': position_52w,
            'ma20_vs_ma50': ma20_vs_ma50,
        }

        # Check each gate
        # Gate 1: Momentum 15-25%
        if momentum_30d < 15:
            return {'failed_at': 'momentum_too_weak', 'metrics': metrics}
        if momentum_30d > 25:
            return {'failed_at': 'momentum_exhausted', 'metrics': metrics}

        # Gate 2: Volume
        if momentum_30d >= 20:
            if volume_ratio < 0.8:
                return {'failed_at': 'volume_too_low', 'metrics': metrics}
            if volume_ratio > 2.0:
                return {'failed_at': 'volume_too_high', 'metrics': metrics}
        else:
            if volume_ratio < 0.8:
                return {'failed_at': 'volume_too_low', 'metrics': metrics}
            if volume_ratio > 1.8:
                return {'failed_at': 'volume_too_high', 'metrics': metrics}

        # Gate 3: RSI
        if rsi_current < 45:
            return {'failed_at': 'rsi_too_low', 'metrics': metrics}
        if rsi_current > 65:
            return {'failed_at': 'rsi_too_high', 'metrics': metrics}

        # Gate 4: 52w position
        if position_52w < 70:
            return {'failed_at': '52w_position_weak', 'metrics': metrics}

        # Gate 5: MA trend
        if ma20_vs_ma50 < 0:
            return {'failed_at': 'downtrend', 'metrics': metrics}

        # Gate 6: Freefall
        if momentum_5d < -8:
            return {'failed_at': 'freefall', 'metrics': metrics}

        # Passed!
        return {'failed_at': 'PASSED', 'metrics': metrics}

    except Exception as e:
        return {'failed_at': f'error: {str(e)}', 'metrics': {}}

def debug_v5():
    """Debug why v5.0 filters are too strict"""

    logger.info("🔍 DEBUGGING v5.0 FILTERS")
    logger.info("=" * 80)

    # Test with stocks from v4.2 that passed
    test_stocks = [
        'SCCO', 'PATH', 'ILMN', 'TSLA', 'MU', 'LRCX', 'SNPS', 'ADI', 'TXN',
        'GOOGL', 'AAPL', 'AVGO', 'AMAT', 'AMZN',
        'ARWR', 'NVDA', 'INTC', 'KLAC', 'MRVL', 'SNOW', 'TSM', 'DDOG', 'ASML'
    ]

    # Test one date for now
    test_date = pd.Timestamp('2025-12-20')

    dm = DataManager()

    failure_reasons = Counter()
    all_results = []

    logger.info(f"Testing {len(test_stocks)} stocks on {test_date.date()}")
    logger.info("")

    for symbol in test_stocks:
        try:
            df = dm.get_price_data(symbol, period="2y", interval="1d")
            if df is None or len(df) < 60:
                failure_reasons['insufficient_data'] += 1
                continue

            result = check_v5_filters(df, symbol, test_date)
            failed_at = result['failed_at']
            metrics = result['metrics']

            failure_reasons[failed_at] += 1

            all_results.append({
                'symbol': symbol,
                'failed_at': failed_at,
                **metrics
            })

            # Log detail
            if failed_at == 'PASSED':
                logger.info(f"✅ {symbol:6s} PASSED!")
            else:
                mom = metrics.get('momentum_30d', 0)
                rsi_val = metrics.get('rsi', 0)
                vol = metrics.get('volume_ratio', 0)
                pos52 = metrics.get('position_52w', 0)

                logger.info(f"❌ {symbol:6s} Failed: {failed_at:25s} | Mom:{mom:6.1f}% RSI:{rsi_val:5.1f} Vol:{vol:4.2f}x 52w:{pos52:5.1f}%")

        except Exception as e:
            logger.error(f"Error testing {symbol}: {e}")
            failure_reasons['error'] += 1

    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 FAILURE BREAKDOWN")
    logger.info("=" * 80)

    for reason, count in failure_reasons.most_common():
        logger.info(f"{count:3d} stocks: {reason}")

    logger.info("")

    # Analyze metrics distribution
    if all_results:
        df_results = pd.DataFrame(all_results)

        logger.info("=" * 80)
        logger.info("📈 METRICS DISTRIBUTION")
        logger.info("=" * 80)

        for col in ['momentum_30d', 'rsi', 'volume_ratio', 'position_52w']:
            if col in df_results.columns and len(df_results[col]) > 0:
                vals = df_results[col].dropna()
                if len(vals) > 0:
                    logger.info(f"\n{col}:")
                    logger.info(f"  Min:    {vals.min():.2f}")
                    logger.info(f"  25th:   {vals.quantile(0.25):.2f}")
                    logger.info(f"  Median: {vals.median():.2f}")
                    logger.info(f"  75th:   {vals.quantile(0.75):.2f}")
                    logger.info(f"  Max:    {vals.max():.2f}")

                    # Show v5.0 requirements
                    if col == 'momentum_30d':
                        logger.info(f"  v5.0 requires: 15-25%")
                        in_range = vals[(vals >= 15) & (vals <= 25)]
                        logger.info(f"  In range: {len(in_range)}/{len(vals)} ({len(in_range)/len(vals)*100:.1f}%)")
                    elif col == 'rsi':
                        logger.info(f"  v5.0 requires: 45-65")
                        in_range = vals[(vals >= 45) & (vals <= 65)]
                        logger.info(f"  In range: {len(in_range)}/{len(vals)} ({len(in_range)/len(vals)*100:.1f}%)")
                    elif col == 'volume_ratio':
                        logger.info(f"  v5.0 requires: 0.8-1.8x")
                        in_range = vals[(vals >= 0.8) & (vals <= 1.8)]
                        logger.info(f"  In range: {len(in_range)}/{len(vals)} ({len(in_range)/len(vals)*100:.1f}%)")
                    elif col == 'position_52w':
                        logger.info(f"  v5.0 requires: >70%")
                        in_range = vals[vals >= 70]
                        logger.info(f"  In range: {len(in_range)}/{len(vals)} ({len(in_range)/len(vals)*100:.1f}%)")

if __name__ == "__main__":
    debug_v5()
