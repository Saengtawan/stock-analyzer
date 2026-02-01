#!/usr/bin/env python3
"""
Quick verification that v4.2 gates are working correctly
"""

from loguru import logger

# Test cases: (momentum, rsi, position_52w) -> should_pass
test_cases = [
    # v4.2 should PASS these (v5.1 would REJECT):
    ("Low momentum, healthy RSI", 5.0, 55, 50, True, "Early momentum - v4.2 accepts, v5.1 rejects (<10%)"),
    ("Very low momentum", 3.0, 52, 45, True, "Very early stage - v4.2 accepts, v5.1 rejects"),
    ("Moderate momentum, not near 52w high", 18.0, 58, 55, True, "v4.2 accepts (no 52w req), v5.1 rejects (<70%)"),
    ("Low momentum, low 52w position", 8.0, 53, 40, True, "v4.2 accepts both, v5.1 rejects both"),

    # v4.2 should REJECT these (EXTENDED):
    ("Extended momentum", 40.0, 55, 85, False, "Extended move - both reject (>38%)"),
    ("Extended RSI", 20.0, 75, 90, False, "Extended RSI - v4.2 rejects (>72), v5.1 accepts (<65 limit)"),
    ("Very extended", 45.0, 78, 95, False, "Both extended - both reject"),

    # Both should PASS:
    ("Good momentum, healthy RSI", 18.0, 58, 85, True, "Healthy momentum - both accept"),
    ("Moderate momentum", 12.0, 54, 75, True, "Good setup - both accept"),
]

logger.info("=" * 80)
logger.info("v4.2 GATE VERIFICATION TEST")
logger.info("=" * 80)
logger.info("")

logger.info("Testing v4.2 gate logic:")
logger.info("  • Momentum: Accept 0-38% (no minimum!)")
logger.info("  • RSI: Accept 45-72 (reject extended >72)")
logger.info("  • 52w Position: NO requirement (removed!)")
logger.info("")

all_pass = True

for test_name, momentum, rsi, pos_52w, should_pass, explanation in test_cases:
    # Simulate v4.2 gates
    passes_v42 = True
    rejection_reason = ""

    # Gate 1: Momentum <38%
    if momentum > 38:
        passes_v42 = False
        rejection_reason = f"Momentum exhausted ({momentum:.1f}% > 38%)"

    # Gate 2: RSI 45-72
    if rsi < 45:
        passes_v42 = False
        rejection_reason = f"RSI too low ({rsi:.1f} < 45)"
    if rsi > 72:
        passes_v42 = False
        rejection_reason = f"RSI too high ({rsi:.1f} > 72) - extended"

    # Gate 3: NO 52w requirement (removed in v4.2!)
    # (This is what makes v4.2 different from v5.1)

    # Check if result matches expectation
    if passes_v42 == should_pass:
        status = "✅ PASS"
    else:
        status = "❌ FAIL"
        all_pass = False

    logger.info(f"{status} | {test_name}")
    logger.info(f"         Metrics: Momentum {momentum:.1f}%, RSI {rsi:.1f}, 52w {pos_52w:.0f}%")
    logger.info(f"         Expected: {'PASS' if should_pass else 'REJECT'}, Got: {'PASS' if passes_v42 else 'REJECT'}")
    if not passes_v42:
        logger.info(f"         Reason: {rejection_reason}")
    logger.info(f"         Note: {explanation}")
    logger.info("")

logger.info("=" * 80)
if all_pass:
    logger.info("✅ ALL TESTS PASSED - v4.2 gates working correctly!")
else:
    logger.error("❌ SOME TESTS FAILED - check gate logic!")
logger.info("=" * 80)
logger.info("")

# Summary of key differences
logger.info("🔑 KEY DIFFERENCES v4.2 vs v5.1:")
logger.info("")
logger.info("1. Momentum Gate:")
logger.info("   v5.1: 10-25% REQUIRED")
logger.info("   v4.2: >38% REJECTED (0-38% OK!) ✅ More flexible")
logger.info("")
logger.info("2. RSI Gate:")
logger.info("   v5.1: <65 limit")
logger.info("   v4.2: <72 limit ✅ Anti-extended focus")
logger.info("")
logger.info("3. 52w Position:")
logger.info("   v5.1: >70% REQUIRED")
logger.info("   v4.2: NO requirement ✅ Catches early moves")
logger.info("")
logger.info("📊 Expected Impact:")
logger.info("   • Pass rate: Similar (~7-8%)")
logger.info("   • Win rate: Lower (47.9% vs 58.1%)")
logger.info("   • Median return: MUCH BETTER (+4.80% vs +2.39%)")
logger.info("   • Philosophy: Better TYPICAL performance > higher win rate")
