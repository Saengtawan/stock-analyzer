#!/usr/bin/env python3
"""
Test Trailing Stop Fix - ทดสอบว่า Breakeven Protection ทำงานถูกต้อง
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from advanced_exit_rules import AdvancedExitRules
import pandas as pd
from datetime import datetime
from loguru import logger

logger.info("=" * 80)
logger.info("🧪 TESTING TRAILING STOP FIX - Breakeven Protection")
logger.info("=" * 80)
logger.info("")

exit_rules = AdvancedExitRules()

# Test cases จาก v4.2 big losers
test_cases = [
    {
        'name': 'NVDA - Small Gain (0.45%)',
        'symbol': 'NVDA',
        'entry_price': 199.04,
        'highest_price': 199.04 * 1.0045,  # +0.45%
        'current_price': 199.04 * 0.99,    # -1.0% from entry (should trigger)
        'days_held': 5,
        'expected_exit': True,
        'expected_reason': 'TRAILING_STOP',
        'note': 'Profit 0.45% → Trailing breakeven + 0.5% = จะ trigger ถ้าลงใกล้ entry'
    },
    {
        'name': 'SNOW - Medium Gain (2.74%)',
        'symbol': 'SNOW',
        'entry_price': 268.51,
        'highest_price': 268.51 * 1.0274,  # +2.74%
        'current_price': 268.51 * 0.996,   # -0.4% from entry (ลงจาก peak ~3%)
        'days_held': 5,
        'expected_exit': True,
        'expected_reason': 'TRAILING_STOP',
        'note': 'Profit 2.74% → Trailing -4% = จะ trigger ถ้าลง >4% จาก peak'
    },
    {
        'name': 'AVGO - Large Gain (6.24%)',
        'symbol': 'AVGO',
        'entry_price': 389.49,
        'highest_price': 389.49 * 1.0624,  # +6.24%
        'current_price': 389.49 * 1.03,    # +3% from entry (ลงจาก peak ~3%)
        'days_held': 5,
        'expected_exit': True,
        'expected_reason': 'TRAILING_STOP',
        'note': 'Profit 6.24% → Trailing -3% = จะ trigger ถ้าลง >3% จาก peak'
    },
    {
        'name': 'Winner - Still Rising',
        'symbol': 'MU',
        'entry_price': 276.48,
        'highest_price': 276.48 * 1.10,   # +10%
        'current_price': 276.48 * 1.08,   # +8% (ลงจาก peak แค่ 2%)
        'days_held': 5,
        'expected_exit': False,
        'expected_reason': None,
        'note': 'Profit 10% → Trailing -3% = ลงแค่ 2% ยังไม่ trigger'
    },
    {
        'name': 'No Profit Yet',
        'symbol': 'AAPL',
        'entry_price': 262.57,
        'highest_price': 262.57,           # ยังไม่เคยกำไร
        'current_price': 262.57 * 0.98,   # -2%
        'days_held': 3,
        'expected_exit': False,
        'expected_reason': None,
        'note': 'ยังไม่เคยกำไร → Trailing stop ยังไม่ทำงาน (ใช้ hard stop -6%)'
    }
]

logger.info("🔍 Running Test Cases:")
logger.info("")

passed = 0
failed = 0

for i, test in enumerate(test_cases, 1):
    logger.info(f"Test {i}: {test['name']}")
    logger.info(f"  Entry: ${test['entry_price']:.2f}")
    logger.info(f"  Peak:  ${test['highest_price']:.2f} ({((test['highest_price']/test['entry_price'])-1)*100:+.2f}%)")
    logger.info(f"  Now:   ${test['current_price']:.2f} ({((test['current_price']/test['entry_price'])-1)*100:+.2f}%)")
    logger.info(f"  Note:  {test['note']}")

    # Create mock position
    position = {
        'symbol': test['symbol'],
        'entry_price': test['entry_price'],
        'entry_date': '2025-11-10',
        'highest_price': test['highest_price'],
        'days_held': test['days_held']
    }

    # Create mock price history
    dates = pd.date_range(start='2025-11-10', periods=test['days_held']+1, freq='D')
    hist_data = pd.DataFrame({
        'Close': [test['current_price']] * (test['days_held']+1)
    }, index=dates)

    # Test exit rule
    current_date = dates[-1]
    should_exit, reason, exit_price = exit_rules.should_exit(
        position, current_date, hist_data, spy_data=None
    )

    # Check result
    if should_exit == test['expected_exit']:
        if not test['expected_exit'] or reason == test['expected_reason']:
            logger.info(f"  ✅ PASS: Exit={should_exit}, Reason={reason}")
            passed += 1
        else:
            logger.error(f"  ❌ FAIL: Expected reason {test['expected_reason']}, got {reason}")
            failed += 1
    else:
        logger.error(f"  ❌ FAIL: Expected exit={test['expected_exit']}, got {should_exit}")
        failed += 1

    logger.info("")

# Summary
logger.info("=" * 80)
logger.info("📊 TEST RESULTS")
logger.info("=" * 80)
logger.info(f"✅ Passed: {passed}/{len(test_cases)}")
logger.info(f"❌ Failed: {failed}/{len(test_cases)}")
logger.info("")

if failed == 0:
    logger.info("🎉 ALL TESTS PASSED! Trailing Stop Fix working correctly!")
    logger.info("")
    logger.info("🔑 Key Improvements:")
    logger.info("  • NVDA (+0.45%) → Now protected with breakeven stop")
    logger.info("  • SNOW (+2.74%) → Now protected with -4% trailing")
    logger.info("  • AVGO (+6.24%) → Now protected with -3% trailing")
    logger.info("  • Expected: 3 big losers → 0 big losers!")
else:
    logger.error("⚠️ SOME TESTS FAILED - Please review the logic!")

logger.info("")
logger.info("=" * 80)
logger.info("📌 Next Steps:")
logger.info("=" * 80)
logger.info("1. ✅ Code updated: advanced_exit_rules.py")
logger.info("2. ⏳ Run backtest: python backtest_v4.2_with_trailing_fix.py")
logger.info("3. 📊 Compare results: Before vs After")
logger.info("4. 🚀 Deploy to production if results good!")
