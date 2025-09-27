#!/usr/bin/env python3
"""
Test Main StockAnalyzer with ETF support
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from loguru import logger

def test_main_etf_support():
    """Test main analyzer ETF detection and analysis"""
    logger.info("Testing Main StockAnalyzer ETF support...")

    analyzer = StockAnalyzer()

    # Test ETF analysis
    logger.info("=== Testing SPYI (ETF) ===")
    spyi_analysis = analyzer.analyze_stock('SPYI', time_horizon='long', account_value=100000)

    if 'error' in spyi_analysis:
        logger.error(f"❌ SPYI analysis failed: {spyi_analysis['error']}")
    else:
        logger.info("✅ SPYI analysis successful")
        logger.info(f"Symbol: {spyi_analysis.get('symbol')}")
        logger.info(f"Is ETF: {spyi_analysis.get('is_etf', False)}")
        logger.info(f"Current Price: ${spyi_analysis.get('current_price', 0):.2f}")
        logger.info(f"Recommendation: {spyi_analysis.get('signal_analysis', {}).get('recommendation', {}).get('recommendation', 'N/A')}")
        logger.info(f"Overall Score: {spyi_analysis.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0):.1f}/100")

        # Check if fundamental data has ETF flag
        fundamental = spyi_analysis.get('fundamental_analysis', {})
        logger.info(f"Fundamental is_etf: {fundamental.get('is_etf', False)}")

    # Test regular stock for comparison
    logger.info("\n=== Testing KO (Regular Stock) ===")
    ko_analysis = analyzer.analyze_stock('KO', time_horizon='long', account_value=100000)

    if 'error' in ko_analysis:
        logger.error(f"❌ KO analysis failed: {ko_analysis['error']}")
    else:
        logger.info("✅ KO analysis successful")
        logger.info(f"Symbol: {ko_analysis.get('symbol')}")
        logger.info(f"Is ETF: {ko_analysis.get('is_etf', False)}")
        logger.info(f"Current Price: ${ko_analysis.get('current_price', 0):.2f}")
        logger.info(f"Recommendation: {ko_analysis.get('signal_analysis', {}).get('recommendation', {}).get('recommendation', 'N/A')}")
        logger.info(f"Overall Score: {ko_analysis.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0):.1f}/100")

        # Check if fundamental data has ETF flag
        fundamental = ko_analysis.get('fundamental_analysis', {})
        logger.info(f"Fundamental is_etf: {fundamental.get('is_etf', False)}")

if __name__ == "__main__":
    test_main_etf_support()