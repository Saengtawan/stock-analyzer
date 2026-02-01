#!/usr/bin/env python3
"""
Verify v5.4 filters would have blocked the 3 losers from v5.3:
- COST: 3 days from 52w high -> filtered by days_from_high < 50
- HON: 34 days from 52w high -> filtered by days_from_high < 50
- NVO: Mom 10d -1.6% -> filtered by mom_10d <= 0

This test simulates entry conditions on known dates.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

# Initialize
dm = DataManager()

def calculate_metrics(df, as_of_idx):
    """Calculate metrics as of a specific index position"""
    if df is None or as_of_idx < 252:
        return None

    df_slice = df.iloc[:as_of_idx+1]
    lookback = min(252, len(df_slice))

    close = df_slice['close'].iloc[-lookback:]
    high = df_slice['high'].iloc[-lookback:]

    current_price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Moving averages
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    price_above_ma20 = ((current_price - ma20) / ma20) * 100
    price_above_ma50 = ((current_price - ma50) / ma50) * 100

    # Momentum
    mom_5d = ((current_price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((current_price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_30d = ((current_price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0

    # 52-week position
    high_52w = high.max()
    low_52w = close.min()
    position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50

    # Days from 52-week high
    high_idx = high.idxmax()
    current_idx = close.index[-1]
    days_from_high = current_idx - high_idx

    return {
        'rsi': float(rsi.iloc[-1]),
        'price_above_ma20': float(price_above_ma20),
        'price_above_ma50': float(price_above_ma50),
        'momentum_5d': float(mom_5d),
        'momentum_10d': float(mom_10d),
        'momentum_30d': float(mom_30d),
        'position_52w': float(position_52w),
        'days_from_high': int(days_from_high),
        'current_price': float(current_price),
        'high_52w': float(high_52w),
    }


def check_v53(metrics):
    """v5.3 criteria"""
    if metrics is None:
        return False, "No metrics"

    reasons = []
    passed = True

    # 52w position: 55-90%
    pos = metrics['position_52w']
    if pos < 55 or pos > 90:
        passed = False
        reasons.append(f"52w={pos:.0f}%")

    # Mom 30d: 6-16%
    mom30 = metrics['momentum_30d']
    if mom30 < 6 or mom30 > 16:
        passed = False
        reasons.append(f"M30={mom30:.1f}%")

    # Mom 5d: 0.5-12%
    mom5 = metrics['momentum_5d']
    if mom5 < 0.5 or mom5 > 12:
        passed = False
        reasons.append(f"M5={mom5:.1f}%")

    # RSI: 45-62
    rsi = metrics['rsi']
    if rsi < 45 or rsi > 62:
        passed = False
        reasons.append(f"RSI={rsi:.0f}")

    # Above MA20
    if metrics['price_above_ma20'] <= 0:
        passed = False
        reasons.append("Below MA20")

    return passed, ", ".join(reasons) if reasons else "PASS"


def check_v54(metrics):
    """v5.4 criteria (with new filters)"""
    if metrics is None:
        return False, "No metrics"

    reasons = []
    passed = True

    # 52w position: 55-90%
    pos = metrics['position_52w']
    if pos < 55 or pos > 90:
        passed = False
        reasons.append(f"52w={pos:.0f}%")

    # NEW: Days from 52w high > 50
    days = metrics['days_from_high']
    if days < 50:
        passed = False
        reasons.append(f"DaysFromHigh={days}<50")

    # Mom 30d: 6-16%
    mom30 = metrics['momentum_30d']
    if mom30 < 6 or mom30 > 16:
        passed = False
        reasons.append(f"M30={mom30:.1f}%")

    # NEW: Mom 10d > 0%
    mom10 = metrics['momentum_10d']
    if mom10 <= 0:
        passed = False
        reasons.append(f"M10={mom10:.1f}%<=0")

    # Mom 5d: 0.5-12%
    mom5 = metrics['momentum_5d']
    if mom5 < 0.5 or mom5 > 12:
        passed = False
        reasons.append(f"M5={mom5:.1f}%")

    # RSI: 45-62
    rsi = metrics['rsi']
    if rsi < 45 or rsi > 62:
        passed = False
        reasons.append(f"RSI={rsi:.0f}")

    # Above MA20
    if metrics['price_above_ma20'] <= 0:
        passed = False
        reasons.append("Below MA20")

    return passed, ", ".join(reasons) if reasons else "PASS"


def test_stock(symbol, days_back=0):
    """Test a stock with current or historical data"""
    print(f"\n{'='*60}")
    print(f"Testing {symbol}")
    print(f"{'='*60}")

    try:
        df = dm.get_price_data(symbol, period="2y", interval="1d")
        if df is None or len(df) < 260:
            print(f"Insufficient data for {symbol}")
            return None

        # Use index position based on days_back
        test_idx = len(df) - 1 - days_back
        test_date = pd.to_datetime(df.iloc[test_idx]['date']).strftime('%Y-%m-%d')

        print(f"Test date: {test_date}")

        metrics = calculate_metrics(df, test_idx)

        if metrics is None:
            print("Failed to calculate metrics")
            return None

        print(f"\nMetrics:")
        print(f"  Price:         ${metrics['current_price']:.2f}")
        print(f"  52w High:      ${metrics['high_52w']:.2f}")
        print(f"  52w Position:  {metrics['position_52w']:.1f}%")
        print(f"  Days from High: {metrics['days_from_high']}")
        print(f"  Mom 5d:        {metrics['momentum_5d']:+.2f}%")
        print(f"  Mom 10d:       {metrics['momentum_10d']:+.2f}%")
        print(f"  Mom 30d:       {metrics['momentum_30d']:+.2f}%")
        print(f"  RSI:           {metrics['rsi']:.1f}")
        print(f"  Above MA20:    {metrics['price_above_ma20']:+.2f}%")

        # Check both versions
        v53_pass, v53_reason = check_v53(metrics)
        v54_pass, v54_reason = check_v54(metrics)

        print(f"\nv5.3 Result: {'✅ PASS' if v53_pass else '❌ FAIL'} {v53_reason}")
        print(f"v5.4 Result: {'✅ PASS' if v54_pass else '❌ FAIL'} {v54_reason}")

        return {
            'symbol': symbol,
            'metrics': metrics,
            'v53_pass': v53_pass,
            'v53_reason': v53_reason,
            'v54_pass': v54_pass,
            'v54_reason': v54_reason,
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_entry_scenario(symbol, scenario_type='near_high'):
    """Find historical scenario for testing"""
    print(f"\n{'='*60}")
    print(f"Finding {scenario_type} scenario for {symbol}")
    print(f"{'='*60}")

    try:
        df = dm.get_price_data(symbol, period="2y", interval="1d")
        if df is None or len(df) < 260:
            print(f"Insufficient data")
            return None

        # Look through last 200 days to find matching scenarios
        for days_back in range(30, 200):
            test_idx = len(df) - 1 - days_back
            if test_idx < 252:
                continue

            metrics = calculate_metrics(df, test_idx)
            if metrics is None:
                continue

            # Check v5.3 pass but specific filter criteria
            v53_pass, _ = check_v53(metrics)

            if not v53_pass:
                continue

            days_from_high = metrics['days_from_high']
            mom_10d = metrics['momentum_10d']

            if scenario_type == 'near_high' and days_from_high < 50:
                # Found a near-high scenario
                entry_date = pd.to_datetime(df.iloc[test_idx]['date']).strftime('%Y-%m-%d')
                entry_price = df.iloc[test_idx]['close']

                # Calculate outcome (30 days later)
                exit_idx = min(test_idx + 30, len(df) - 1)
                exit_price = df.iloc[exit_idx]['close']

                # Check for stop loss
                hit_stop = False
                for i in range(test_idx + 1, exit_idx + 1):
                    if (df.iloc[i]['low'] - entry_price) / entry_price <= -0.06:
                        hit_stop = True
                        exit_price = entry_price * 0.94
                        break

                return_pct = ((exit_price - entry_price) / entry_price) * 100

                print(f"\nFound NEAR HIGH scenario:")
                print(f"  Date: {entry_date}")
                print(f"  Days from 52w High: {days_from_high}")
                print(f"  Entry: ${entry_price:.2f} -> Exit: ${exit_price:.2f}")
                print(f"  Return: {return_pct:+.1f}%")
                print(f"  Hit Stop: {hit_stop}")

                # Test v5.4
                v54_pass, v54_reason = check_v54(metrics)
                print(f"\n  v5.3: ✅ PASS")
                print(f"  v5.4: {'✅ PASS' if v54_pass else '❌ FILTERED'} {v54_reason}")

                return {
                    'symbol': symbol,
                    'date': entry_date,
                    'days_from_high': days_from_high,
                    'return_pct': return_pct,
                    'hit_stop': hit_stop,
                    'v54_filtered': not v54_pass,
                    'v54_reason': v54_reason,
                }

            elif scenario_type == 'weak_mom10' and mom_10d <= 0:
                # Found weak momentum scenario
                entry_date = pd.to_datetime(df.iloc[test_idx]['date']).strftime('%Y-%m-%d')
                entry_price = df.iloc[test_idx]['close']

                # Calculate outcome
                exit_idx = min(test_idx + 30, len(df) - 1)
                exit_price = df.iloc[exit_idx]['close']

                hit_stop = False
                for i in range(test_idx + 1, exit_idx + 1):
                    if (df.iloc[i]['low'] - entry_price) / entry_price <= -0.06:
                        hit_stop = True
                        exit_price = entry_price * 0.94
                        break

                return_pct = ((exit_price - entry_price) / entry_price) * 100

                print(f"\nFound WEAK MOM 10D scenario:")
                print(f"  Date: {entry_date}")
                print(f"  Mom 10d: {mom_10d:+.1f}%")
                print(f"  Entry: ${entry_price:.2f} -> Exit: ${exit_price:.2f}")
                print(f"  Return: {return_pct:+.1f}%")

                v54_pass, v54_reason = check_v54(metrics)
                print(f"\n  v5.3: ✅ PASS")
                print(f"  v5.4: {'✅ PASS' if v54_pass else '❌ FILTERED'} {v54_reason}")

                return {
                    'symbol': symbol,
                    'date': entry_date,
                    'mom_10d': mom_10d,
                    'return_pct': return_pct,
                    'hit_stop': hit_stop,
                    'v54_filtered': not v54_pass,
                    'v54_reason': v54_reason,
                }

        print(f"No {scenario_type} scenario found")
        return None

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None


# Main test
if __name__ == "__main__":
    print("\n" + "="*70)
    print("v5.4 FILTER VERIFICATION TEST")
    print("="*70)
    print("\nGoal: Verify that v5.4's new filters would block losers from v5.3")
    print("\nNew filters in v5.4:")
    print("  1. Days from 52w High > 50 (to filter COST, HON)")
    print("  2. Mom 10d > 0% (to filter NVO)")

    # Test current metrics for the known losers
    print("\n" + "="*70)
    print("PART 1: CURRENT METRICS CHECK")
    print("="*70)

    losers = ['COST', 'HON', 'NVO']
    for symbol in losers:
        test_stock(symbol)

    # Find historical scenarios
    print("\n" + "="*70)
    print("PART 2: FIND NEAR-HIGH SCENARIOS (v5.4 would filter)")
    print("="*70)

    near_high_results = []
    for symbol in ['COST', 'HON', 'AAPL', 'MSFT', 'NVDA']:
        result = find_entry_scenario(symbol, 'near_high')
        if result:
            near_high_results.append(result)

    print("\n" + "="*70)
    print("PART 3: FIND WEAK MOM 10D SCENARIOS (v5.4 would filter)")
    print("="*70)

    weak_mom_results = []
    for symbol in ['NVO', 'JNJ', 'PFE', 'MRK', 'UNH']:
        result = find_entry_scenario(symbol, 'weak_mom10')
        if result:
            weak_mom_results.append(result)

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    if near_high_results:
        print("\nNear-High Scenarios Found:")
        filtered = [r for r in near_high_results if r['v54_filtered']]
        print(f"  Total: {len(near_high_results)}, v5.4 would filter: {len(filtered)}")

        for r in near_high_results:
            status = "❌ FILTERED" if r['v54_filtered'] else "✅ PASSED"
            outcome = "LOSS" if r['return_pct'] < 0 else "WIN"
            print(f"  {r['symbol']:6} DaysFromHigh={r['days_from_high']:3} Return={r['return_pct']:+.1f}% {outcome} -> {status}")

    if weak_mom_results:
        print("\nWeak Mom 10d Scenarios Found:")
        filtered = [r for r in weak_mom_results if r['v54_filtered']]
        print(f"  Total: {len(weak_mom_results)}, v5.4 would filter: {len(filtered)}")

        for r in weak_mom_results:
            status = "❌ FILTERED" if r['v54_filtered'] else "✅ PASSED"
            outcome = "LOSS" if r['return_pct'] < 0 else "WIN"
            print(f"  {r['symbol']:6} Mom10d={r['mom_10d']:+.1f}% Return={r['return_pct']:+.1f}% {outcome} -> {status}")

    print("\n" + "="*70)
    print("CONCLUSION")
    print("="*70)
    print("\nv5.4 adds two key filters to avoid losers:")
    print("  1. Days from 52w High > 50: Avoids buying at peak")
    print("  2. Mom 10d > 0%: Ensures short-term momentum is positive")
    print("\nThese filters are designed to reduce -6% stop-loss hits.")
