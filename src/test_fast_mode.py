#!/usr/bin/env python3
"""
Test Fast Mode Performance
"""
import time
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.support_level_screener import SupportLevelScreener
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger


def test_fast_mode_performance():
    """Test performance difference between normal and fast mode"""
    logger.info("Testing Fast Mode Performance...")

    analyzer = StockAnalyzer()

    # Small test universe
    test_symbols = ['SPYI', 'SPY', 'AAPL', 'MSFT', 'VYM']

    # Test 1: Support Level Screening
    logger.info("=== Support Level Screening Test ===")
    support_screener = SupportLevelScreener(analyzer)

    # Normal mode
    start_time = time.time()
    normal_results = support_screener.screen_support_opportunities(
        max_stocks=3,
        fast_mode=False
    )
    normal_time = time.time() - start_time

    # Fast mode
    start_time = time.time()
    fast_results = support_screener.screen_support_opportunities(
        max_stocks=3,
        fast_mode=True
    )
    fast_time = time.time() - start_time

    logger.info(f"Normal mode: {normal_time:.2f}s, {len(normal_results)} results")
    logger.info(f"Fast mode: {fast_time:.2f}s, {len(fast_results)} results")
    logger.info(f"Speed improvement: {normal_time/fast_time:.2f}x faster")

    # Test 2: Dividend Screening
    logger.info("\n=== Dividend Screening Test ===")
    dividend_screener = DividendGrowthScreener(analyzer)

    # Normal mode
    start_time = time.time()
    normal_div_results = dividend_screener.screen_dividend_opportunities(
        max_stocks=3,
        fast_mode=False
    )
    normal_div_time = time.time() - start_time

    # Fast mode
    start_time = time.time()
    fast_div_results = dividend_screener.screen_dividend_opportunities(
        max_stocks=3,
        fast_mode=True
    )
    fast_div_time = time.time() - start_time

    logger.info(f"Normal mode: {normal_div_time:.2f}s, {len(normal_div_results)} results")
    logger.info(f"Fast mode: {fast_div_time:.2f}s, {len(fast_div_results)} results")
    logger.info(f"Speed improvement: {normal_div_time/fast_div_time:.2f}x faster")

    # Overall
    total_normal = normal_time + normal_div_time
    total_fast = fast_time + fast_div_time
    logger.info(f"\n✅ Overall speed improvement: {total_normal/total_fast:.2f}x faster")
    logger.info(f"Total time saved: {total_normal - total_fast:.2f} seconds")

    return total_normal > total_fast


if __name__ == "__main__":
    success = test_fast_mode_performance()
    if success:
        logger.success("🎉 Fast mode performance test passed!")
    else:
        logger.error("❌ Fast mode performance test failed!")