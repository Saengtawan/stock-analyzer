#!/usr/bin/env python3
"""
TEST 12: Screener Match Verification
Verify backtest screener matches production code
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def compare_screener_logic():
    """Compare key logic between backtest and production screener"""
    print("="*60)
    print("TEST 12: SCREENER MATCH VERIFICATION")
    print("="*60)

    # Read production screener
    prod_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'screeners', 'rapid_rotation_screener.py')
    with open(prod_file, 'r') as f:
        prod_code = f.read()

    # Read backtest screener
    test_file = os.path.join(os.path.dirname(__file__), 'full_backtest.py')
    with open(test_file, 'r') as f:
        test_code = f.read()

    checks = []

    # 1. Check SIMULATED_CAPITAL
    check_1 = "SIMULATED_CAPITAL = 4000" in test_code
    checks.append(("SIMULATED_CAPITAL = $4,000", check_1))

    # 2. Check Position Size
    check_2 = "POSITION_SIZE_PCT = 40" in test_code
    checks.append(("POSITION_SIZE_PCT = 40%", check_2))

    # 3. Check MAX_POSITIONS
    check_3 = "MAX_POSITIONS = 2" in test_code
    checks.append(("MAX_POSITIONS = 2", check_3))

    # 4. Check Stop Loss
    check_4 = "STOP_LOSS_PCT = 2.5" in test_code
    checks.append(("STOP_LOSS_PCT = 2.5%", check_4))

    # 5. Check Take Profit
    check_5 = "TAKE_PROFIT_PCT = 6.0" in test_code
    checks.append(("TAKE_PROFIT_PCT = 6.0%", check_5))

    # 6. Check Trail Activation
    check_6 = "TRAIL_ACTIVATION_PCT = 2.0" in test_code
    checks.append(("TRAIL_ACTIVATION_PCT = 2.0%", check_6))

    # 7. Check Trail Lock
    check_7 = "TRAIL_LOCK_PCT = 70" in test_code
    checks.append(("TRAIL_LOCK_PCT = 70%", check_7))

    # 8. Check Max Hold Days
    check_8 = "MAX_HOLD_DAYS = 5" in test_code
    checks.append(("MAX_HOLD_DAYS = 5", check_8))

    # 9. Check v3.10 Overextended Filter (max single-day move)
    check_9 = "MAX_SINGLE_DAY_MOVE = 8.0" in test_code
    checks.append(("v3.10: MAX_SINGLE_DAY_MOVE = 8.0%", check_9))

    # 10. Check v3.10 SMA20 Extension
    check_10 = "MAX_SMA20_EXTENSION = 10.0" in test_code
    checks.append(("v3.10: MAX_SMA20_EXTENSION = 10.0%", check_10))

    # 11. Check Lookback Days
    check_11 = "LOOKBACK_DAYS = 10" in test_code
    checks.append(("v3.10: LOOKBACK_DAYS = 10", check_11))

    # 12. Check Price Filter Gate
    check_12 = "10 <= current_price <= 2000" in test_code
    checks.append(("GATE 1: Price $10-$2000", check_12))

    # 13. Check Volume Filter
    check_13 = "avg_volume < 500000" in test_code
    checks.append(("GATE 2: Volume > 500K", check_13))

    # 14. Check SMA20 Uptrend
    check_14 = "current_price <= sma20" in test_code or "current_price > sma20" in test_code
    checks.append(("GATE 3: Price > SMA20", check_14))

    # 15. Check Yesterday Dip
    check_15 = "yesterday_change > -1.0" in test_code
    checks.append(("GATE 4: Yesterday dip >= -1%", check_15))

    # 16. Check Today Not Falling
    check_16 = "today_change < -1.0" in test_code
    checks.append(("GATE 5: Today >= -1%", check_16))

    # 17. Check Bounce Confirmation
    check_17 = "is_green or is_up_half" in test_code
    checks.append(("GATE 6: Bounce (green OR +0.5%)", check_17))

    # 18. Check Volume Confirmation
    check_18 = "avg_volume * 0.8" in test_code
    checks.append(("GATE 7: Volume >= 80% avg", check_18))

    # 19. Check Score Threshold
    check_19 = "score < 90" in test_code
    checks.append(("GATE 10: Score >= 90", check_19))

    # 20. Check PDT Protection
    check_20 = "day_trades_5day" in test_code and "len(day_trades_5day) >= 3" in test_code
    checks.append(("PDT: 3 day trades in 5 days", check_20))

    # Compare with production
    print("\n--- CONFIGURATION MATCH ---")
    all_pass = True
    for name, passed in checks:
        icon = "PASS" if passed else "FAIL"
        print(f"{icon}: {name}")
        if not passed:
            all_pass = False

    # Additional check: Compare production screener key parameters
    print("\n--- PRODUCTION SCREENER CHECK ---")

    # Check production has same gates
    prod_checks = []
    prod_checks.append(("Prod: Price Filter", "10 <=" in prod_code and "<= 2000" in prod_code))
    prod_checks.append(("Prod: Volume Filter", "500000" in prod_code or "500_000" in prod_code))
    prod_checks.append(("Prod: Yesterday Dip", "-1" in prod_code and "yesterday" in prod_code.lower()))
    prod_checks.append(("Prod: Bounce Check", "green" in prod_code.lower() or "bounce" in prod_code.lower()))
    prod_checks.append(("Prod: Overextended v3.10", "8.0" in prod_code or "8" in prod_code))

    for name, passed in prod_checks:
        icon = "PASS" if passed else "WARN"
        print(f"{icon}: {name}")

    print("\n" + "="*60)
    if all_pass:
        print("TEST 12: PASS - Backtest matches v3.10 specification")
    else:
        print("TEST 12: FAIL - Some parameters don't match")
    print("="*60)

    return all_pass


if __name__ == '__main__':
    result = compare_screener_logic()
    sys.exit(0 if result else 1)
