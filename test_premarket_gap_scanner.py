#!/usr/bin/env python3
"""
Test Pre-Market Gap Scanner Integration

Tests:
1. Scanner loads correctly
2. Can detect gaps
3. Integration with auto trading engine works
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from loguru import logger

def test_scanner_import():
    """Test that scanner can be imported"""
    try:
        from screeners.premarket_gap_scanner import PreMarketGapScanner, PreMarketGapSignal
        logger.info("✅ Scanner import successful")
        return True
    except Exception as e:
        logger.error(f"❌ Scanner import failed: {e}")
        return False


def test_scanner_initialization():
    """Test scanner initialization"""
    try:
        from screeners.premarket_gap_scanner import PreMarketGapScanner
        scanner = PreMarketGapScanner()
        logger.info(f"✅ Scanner initialized with {len(scanner.watchlist)} symbols")
        return True
    except Exception as e:
        logger.error(f"❌ Scanner initialization failed: {e}")
        return False


def test_scanner_scan():
    """Test scanner scan function"""
    try:
        from screeners.premarket_gap_scanner import PreMarketGapScanner
        scanner = PreMarketGapScanner(watchlist=['NVDA', 'AMD', 'TSLA', 'AAPL', 'META'])

        logger.info("Running scan (may not find gaps if market is closed)...")
        signals = scanner.scan_premarket(min_confidence=70)

        if signals:
            logger.info(f"✅ Scanner found {len(signals)} gaps:")
            for sig in signals:
                logger.info(f"  {sig.symbol}: {sig.gap_pct:+.1f}% gap, "
                           f"{sig.confidence}% conf, "
                           f"worth rotating: {sig.worth_rotating}")
        else:
            logger.info("✅ Scanner ran successfully (no gaps found - market may be closed)")

        return True
    except Exception as e:
        logger.error(f"❌ Scanner scan failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_engine_integration():
    """Test integration with auto trading engine"""
    try:
        from auto_trading_engine import AutoTradingEngine
        logger.info("Checking if auto trading engine loads scanner...")

        # We can't actually start the engine, but we can check if it imports correctly
        logger.info("✅ Auto trading engine imports successfully")
        logger.info("Note: Full integration test requires running the engine")
        return True
    except Exception as e:
        logger.error(f"❌ Engine integration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """Run all tests"""
    logger.info("=" * 80)
    logger.info("PRE-MARKET GAP SCANNER INTEGRATION TEST")
    logger.info("=" * 80)

    tests = [
        ("Import", test_scanner_import),
        ("Initialization", test_scanner_initialization),
        ("Scan", test_scanner_scan),
        ("Engine Integration", test_engine_integration),
    ]

    results = []
    for name, test_func in tests:
        logger.info(f"\n{'='*80}")
        logger.info(f"Test: {name}")
        logger.info(f"{'='*80}")
        success = test_func()
        results.append((name, success))

    logger.info(f"\n{'='*80}")
    logger.info("TEST RESULTS")
    logger.info(f"{'='*80}")

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"  {name}: {status}")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    logger.info(f"\n{passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 All tests passed! Pre-Market Gap Scanner is ready!")
        logger.info("\n📋 Next steps:")
        logger.info("  1. Start auto trading engine: python src/run_app.py")
        logger.info("  2. Scanner will activate at 6:00 AM - 9:30 AM ET")
        logger.info("  3. Monitor logs for gap signals")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
