#!/usr/bin/env python3
"""
Debug QQQI to find why it doesn't pass dividend criteria
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger

def debug_qqqi():
    """Debug QQQI dividend analysis"""
    logger.info("Debugging QQQI dividend analysis...")

    # Initialize analyzer
    analyzer = StockAnalyzer()
    dividend_screener = DividendGrowthScreener(analyzer)

    try:
        # Analyze QQQI directly
        logger.info("=== Step 1: Basic Analysis ===")
        analysis = analyzer.analyze_stock('QQQI', time_horizon='long', account_value=100000)

        if 'error' in analysis:
            logger.error(f"❌ Basic analysis failed: {analysis['error']}")
            return

        logger.info("✅ Basic analysis successful")

        # Check financial data
        logger.info("\n=== Step 2: Financial Data ===")
        financial_data = analyzer.data_manager.get_financial_data('QQQI')

        logger.info(f"Financial data keys: {list(financial_data.keys())}")
        logger.info(f"Dividend yield: {financial_data.get('dividend_yield', 'N/A')}")
        logger.info(f"Payout ratio: {financial_data.get('payout_ratio', 'N/A')}")
        logger.info(f"EPS: {financial_data.get('eps', 'N/A')}")
        logger.info(f"Revenue growth: {financial_data.get('revenue_growth', 'N/A')}")
        logger.info(f"Earnings growth: {financial_data.get('earnings_growth', 'N/A')}")

        # Check dividend-specific analysis
        logger.info("\n=== Step 3: Dividend Analysis ===")
        dividend_analysis = dividend_screener._analyze_dividend_metrics(financial_data)

        if dividend_analysis is None:
            logger.error("❌ Dividend analysis returned None")
            logger.info("This usually means dividend_yield <= 0")
            return
        else:
            logger.info("✅ Dividend analysis successful")
            for key, value in dividend_analysis.items():
                logger.info(f"  {key}: {value}")

        # Check fundamental analysis
        logger.info("\n=== Step 4: Fundamental Analysis ===")
        fundamental = analysis.get('fundamental_analysis', {})
        logger.info(f"Overall score: {fundamental.get('overall_score', 'N/A')}")
        logger.info(f"Sector: {fundamental.get('sector', 'N/A')}")

        # Test with very relaxed criteria
        logger.info("\n=== Step 5: Testing with Relaxed Criteria ===")

        # Set dividend_universe to only QQQI for focused testing
        dividend_screener.dividend_universe = ['QQQI']

        opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=0.1,  # Very low - 0.1%
            min_dividend_growth_rate=0,  # No growth requirement
            min_payout_ratio=0,  # No minimum payout ratio
            max_payout_ratio=200,  # Very high max payout ratio
            min_fundamental_score=0,  # No fundamental score requirement
            max_stocks=1
        )

        logger.info(f"Result with relaxed criteria: {len(opportunities)} opportunities")

        if len(opportunities) == 0:
            logger.error("❌ Still failed with relaxed criteria")
            logger.info("This suggests QQQI has no dividend at all")
        else:
            logger.success("✅ Passed with relaxed criteria")
            opp = opportunities[0]
            dividend_data = opp.get('dividend_analysis', {})
            logger.info(f"QQQI dividend details:")
            for key, value in dividend_data.items():
                logger.info(f"  {key}: {value}")

    except Exception as e:
        logger.error(f"❌ Debug failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_qqqi()