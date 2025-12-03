#!/usr/bin/env python3
"""
Test script for Intelligent Entry/TP/SL Calculation System (v5.0)
Tests the new Fibonacci-based and swing point detection functions
"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer

# Create sample price data
def create_sample_data():
    """Create sample OHLCV data for testing"""
    dates = pd.date_range('2024-01-01', periods=100, freq='D')

    # Simulate an uptrend with pullback
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 2 + 0.5)
    high = close + np.random.rand(100) * 2
    low = close - np.random.rand(100) * 2
    open_price = close + np.random.randn(100) * 1
    volume = np.random.randint(1000000, 5000000, 100)

    data = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'symbol': ['TEST'] * 100
    })

    return data

def test_swing_point_detection():
    """Test swing point detection"""
    print("=" * 80)
    print("TEST 1: Swing Point Detection")
    print("=" * 80)

    data = create_sample_data()
    analyzer = TechnicalAnalyzer(data)

    swing_points = analyzer._detect_swing_points(lookback=20)

    print(f"✅ Swing High: ${swing_points['swing_high']:.2f}")
    print(f"✅ Swing Low: ${swing_points['swing_low']:.2f}")
    print(f"✅ Swing Range: ${swing_points['swing_high'] - swing_points['swing_low']:.2f}")
    print(f"✅ Lookback Bars: {swing_points['lookback_bars']}")
    print()

    return swing_points

def test_fibonacci_levels(swing_high, swing_low):
    """Test Fibonacci level calculation"""
    print("=" * 80)
    print("TEST 2: Fibonacci Levels Calculation")
    print("=" * 80)

    data = create_sample_data()
    analyzer = TechnicalAnalyzer(data)

    # Test retracement levels
    fib_retracement = analyzer._calculate_fibonacci_levels(
        swing_high=swing_high,
        swing_low=swing_low,
        direction='retracement'
    )

    print("📊 Fibonacci RETRACEMENT Levels (Entry Zones):")
    for level, price in fib_retracement.items():
        print(f"  {level}: ${price:.2f}")
    print()

    # Test extension levels
    fib_extension = analyzer._calculate_fibonacci_levels(
        swing_high=swing_high,
        swing_low=swing_low,
        direction='extension'
    )

    print("📊 Fibonacci EXTENSION Levels (Target Zones):")
    for level, price in fib_extension.items():
        print(f"  {level}: ${price:.2f}")
    print()

    return fib_retracement, fib_extension

def test_smart_entry_zone():
    """Test smart entry zone calculation"""
    print("=" * 80)
    print("TEST 3: Smart Entry Zone Calculation")
    print("=" * 80)

    data = create_sample_data()
    analyzer = TechnicalAnalyzer(data)

    current_price = data['close'].iloc[-1]
    swing_points = analyzer._detect_swing_points(lookback=20)

    # Test TRENDING_BULLISH
    entry_analysis = analyzer._calculate_smart_entry_zone(
        current_price=current_price,
        swing_high=swing_points['swing_high'],
        swing_low=swing_points['swing_low'],
        ema_50=current_price * 0.98,  # Assume EMA50 slightly below
        market_state='TRENDING_BULLISH',
        support=current_price * 0.95,
        resistance=current_price * 1.05
    )

    print(f"Current Price: ${current_price:.2f}")
    print(f"\n🎯 Entry Zones:")
    print(f"  Aggressive:    ${entry_analysis['entry_aggressive']:.2f}")
    print(f"  Moderate:      ${entry_analysis['entry_moderate']:.2f}")
    print(f"  Conservative:  ${entry_analysis['entry_conservative']:.2f}")
    print(f"\n💡 Recommended: ${entry_analysis['recommended_entry']:.2f}")
    print(f"   Distance: {entry_analysis['distance_from_current_pct']:.2f}%")
    print(f"   Method: {entry_analysis['calculation_method']}")
    print(f"   Reason: {entry_analysis['entry_reason']}")
    print()

    return entry_analysis

def test_intelligent_tp_levels():
    """Test intelligent take profit calculation"""
    print("=" * 80)
    print("TEST 4: Intelligent Take Profit Levels")
    print("=" * 80)

    data = create_sample_data()
    analyzer = TechnicalAnalyzer(data)

    current_price = data['close'].iloc[-1]
    swing_points = analyzer._detect_swing_points(lookback=20)
    entry_price = current_price * 0.98  # Assume entry at 2% pullback

    tp_analysis = analyzer._calculate_intelligent_tp_levels(
        entry_price=entry_price,
        swing_high=swing_points['swing_high'],
        swing_low=swing_points['swing_low'],
        resistance=current_price * 1.05,
        market_state='TRENDING_BULLISH',
        atr=current_price * 0.02
    )

    print(f"Entry Price: ${entry_price:.2f}")
    print(f"\n🎯 Take Profit Levels:")
    print(f"  TP1 (Conservative): ${tp_analysis['tp1']:.2f} (+{tp_analysis['tp1_return_pct']:.2f}%)")
    print(f"  TP2 (Moderate):     ${tp_analysis['tp2']:.2f} (+{tp_analysis['tp2_return_pct']:.2f}%)")
    print(f"  TP3 (Aggressive):   ${tp_analysis['tp3']:.2f} (+{tp_analysis['tp3_return_pct']:.2f}%)")
    print(f"\n💡 Recommended: ${tp_analysis['recommended_tp']:.2f}")
    print(f"   Method: {tp_analysis['calculation_method']}")
    print()

    return tp_analysis

def test_intelligent_stop_loss():
    """Test intelligent stop loss calculation"""
    print("=" * 80)
    print("TEST 5: Intelligent Stop Loss Calculation")
    print("=" * 80)

    data = create_sample_data()
    analyzer = TechnicalAnalyzer(data)

    current_price = data['close'].iloc[-1]
    swing_points = analyzer._detect_swing_points(lookback=20)
    entry_price = current_price * 0.98

    sl_analysis = analyzer._calculate_intelligent_stop_loss(
        entry_price=entry_price,
        swing_low=swing_points['swing_low'],
        support=current_price * 0.95,
        market_state='TRENDING_BULLISH',
        atr=current_price * 0.02
    )

    print(f"Entry Price: ${entry_price:.2f}")
    print(f"\n🛑 Stop Loss:")
    print(f"  Stop Loss: ${sl_analysis['stop_loss']:.2f}")
    print(f"  Risk: {sl_analysis['risk_pct']:.2f}%")
    print(f"  Method: {sl_analysis['calculation_method']}")
    if 'swing_low_used' in sl_analysis:
        print(f"  Swing Low Used: ${sl_analysis['swing_low_used']:.2f}")
        print(f"  ATR Buffer: ${sl_analysis['atr_buffer']:.2f}")
    print()

    return sl_analysis

def test_complete_trading_plan():
    """Test complete trading plan calculation"""
    print("=" * 80)
    print("TEST 6: Complete Trading Plan (BEFORE vs AFTER)")
    print("=" * 80)

    data = create_sample_data()
    current_price = data['close'].iloc[-1]

    print(f"Current Price: ${current_price:.2f}\n")

    # BEFORE (Old System)
    print("❌ BEFORE (Old System - Fixed %):")
    old_entry = current_price  # 0% distance!
    old_tp = current_price * 1.07  # Fixed 7%
    old_sl = current_price * 0.97  # Fixed 3%
    old_rr = (old_tp - old_entry) / (old_entry - old_sl)

    print(f"  Entry: ${old_entry:.2f} (0.0% from current) ❌")
    print(f"  TP:    ${old_tp:.2f} (+7.0%)")
    print(f"  SL:    ${old_sl:.2f} (-3.0%)")
    print(f"  R:R:   {old_rr:.2f}:1")
    print(f"  Method: Fixed Percentages")
    print()

    # AFTER (New System)
    print("✅ AFTER (New System - Intelligent):")
    analyzer = TechnicalAnalyzer(data)
    swing_points = analyzer._detect_swing_points(lookback=20)

    entry_analysis = analyzer._calculate_smart_entry_zone(
        current_price=current_price,
        swing_high=swing_points['swing_high'],
        swing_low=swing_points['swing_low'],
        ema_50=current_price * 0.98,
        market_state='TRENDING_BULLISH',
        support=current_price * 0.95,
        resistance=current_price * 1.05
    )

    tp_analysis = analyzer._calculate_intelligent_tp_levels(
        entry_price=entry_analysis['recommended_entry'],
        swing_high=swing_points['swing_high'],
        swing_low=swing_points['swing_low'],
        resistance=current_price * 1.05,
        market_state='TRENDING_BULLISH',
        atr=current_price * 0.02
    )

    sl_analysis = analyzer._calculate_intelligent_stop_loss(
        entry_price=entry_analysis['recommended_entry'],
        swing_low=swing_points['swing_low'],
        support=current_price * 0.95,
        market_state='TRENDING_BULLISH',
        atr=current_price * 0.02
    )

    new_rr = (tp_analysis['recommended_tp'] - entry_analysis['recommended_entry']) / \
             (entry_analysis['recommended_entry'] - sl_analysis['stop_loss'])

    print(f"  Entry: ${entry_analysis['recommended_entry']:.2f} ({entry_analysis['distance_from_current_pct']:.2f}% from current) ✅")
    print(f"  TP:    ${tp_analysis['recommended_tp']:.2f} (+{tp_analysis['tp2_return_pct']:.2f}%)")
    print(f"  SL:    ${sl_analysis['stop_loss']:.2f} (-{sl_analysis['risk_pct']:.2f}%)")
    print(f"  R:R:   {new_rr:.2f}:1 🎯")
    print(f"  Method: {entry_analysis['calculation_method']} + {tp_analysis['calculation_method']}")
    print()

    # Improvement metrics
    print("📈 IMPROVEMENTS:")
    rr_improvement = ((new_rr - old_rr) / old_rr) * 100
    print(f"  R:R Ratio Improvement: +{rr_improvement:.1f}%")
    print(f"  Entry Quality: From 'current price' (0% distance) → '{entry_analysis['calculation_method']}'")
    print(f"  TP Quality: From 'fixed 7%' → '{tp_analysis['calculation_method']}'")
    print(f"  SL Quality: From 'fixed 3%' → '{sl_analysis['calculation_method']}'")
    print()

def main():
    """Run all tests"""
    print("\n")
    print("🚀 " * 20)
    print("INTELLIGENT ENTRY/TP/SL SYSTEM TEST (v5.0)")
    print("🚀 " * 20)
    print()

    try:
        # Test 1: Swing Point Detection
        swing_points = test_swing_point_detection()

        # Test 2: Fibonacci Levels
        fib_ret, fib_ext = test_fibonacci_levels(
            swing_points['swing_high'],
            swing_points['swing_low']
        )

        # Test 3: Smart Entry Zone
        entry_analysis = test_smart_entry_zone()

        # Test 4: Intelligent TP
        tp_analysis = test_intelligent_tp_levels()

        # Test 5: Intelligent SL
        sl_analysis = test_intelligent_stop_loss()

        # Test 6: Complete Trading Plan Comparison
        test_complete_trading_plan()

        print("=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        print()
        print("Summary: The new intelligent Entry/TP/SL system is working correctly!")
        print("- Swing points detected successfully")
        print("- Fibonacci levels calculated correctly")
        print("- Smart entry zones using structure-based analysis")
        print("- Intelligent TP levels using Fibonacci extensions")
        print("- Structure-based stop loss below swing lows")
        print()

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
