#!/usr/bin/env python3
"""
Test script to verify fundamental analysis fixes for NoneType errors
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from loguru import logger

def test_problematic_stocks():
    """Test stocks that were failing with NoneType errors"""

    # List of stocks that were failing in the error logs
    test_stocks = ['MCD', 'JPM', 'C', 'WFC', 'BAC']

    analyzer = StockAnalyzer()

    logger.info("Testing fundamental analysis fixes...")

    results = {}

    for symbol in test_stocks:
        logger.info(f"Testing {symbol}...")
        try:
            # Analyze stock with medium time horizon
            result = analyzer.analyze_stock(symbol, time_horizon='medium', account_value=100000)

            # Check if fundamental analysis succeeded
            if 'fundamental_analysis' in result:
                fund_analysis = result['fundamental_analysis']
                if 'error' not in fund_analysis:
                    logger.success(f"✅ {symbol}: Fundamental analysis successful")
                    logger.info(f"   Overall Score: {fund_analysis.get('overall_score', 'N/A')}")
                    logger.info(f"   Total Score: {fund_analysis.get('fundamental_score', {}).get('total_score', 'N/A')}")
                else:
                    logger.error(f"❌ {symbol}: Fundamental analysis failed with error: {fund_analysis['error']}")
            else:
                logger.warning(f"⚠️  {symbol}: No fundamental analysis in result")

            results[symbol] = result

        except Exception as e:
            logger.error(f"❌ {symbol}: Exception occurred: {e}")
            results[symbol] = {'error': str(e)}

    # Summary
    logger.info("\n=== SUMMARY ===")
    successful = 0
    failed = 0

    for symbol, result in results.items():
        if 'fundamental_analysis' in result and 'error' not in result['fundamental_analysis']:
            successful += 1
            logger.success(f"✅ {symbol}: OK")
        else:
            failed += 1
            logger.error(f"❌ {symbol}: FAILED")

    logger.info(f"\nResults: {successful} successful, {failed} failed out of {len(test_stocks)} total")

    if failed == 0:
        logger.success("🎉 All tests passed! NoneType errors fixed successfully.")
    else:
        logger.warning(f"⚠️  {failed} stocks still have issues.")

    return results

if __name__ == "__main__":
    test_problematic_stocks()