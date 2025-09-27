#!/usr/bin/env python3
"""
Simple test for Dividend Screener - only test screening functionality
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger

def test_simple_dividend_screening():
    """Simple dividend screening test"""
    logger.info("Testing simple dividend screening...")

    # Initialize analyzer and screener
    analyzer = StockAnalyzer()
    dividend_screener = DividendGrowthScreener(analyzer)

    # Test only with 3 high-quality dividend stocks to reduce analysis time
    dividend_screener.dividend_universe = ['KO', 'JNJ', 'PG']

    try:
        # Test with normal criteria
        opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=2.0,  # Reasonable threshold
            min_dividend_growth_rate=0,  # No growth requirement for test
            min_payout_ratio=10.0,  # Low requirement
            max_payout_ratio=90.0,  # High max
            min_fundamental_score=1.0,  # Low fundamental score requirement
            max_stocks=5
        )

        logger.info(f"✅ Found {len(opportunities)} dividend opportunities")

        # Show results
        for i, opp in enumerate(opportunities, 1):
            symbol = opp['symbol']
            dividend_data = opp.get('dividend_analysis', {})
            fundamental = opp.get('fundamental_analysis', {})

            dividend_yield = dividend_data.get('dividend_yield', 0)
            sustainability = opp.get('dividend_sustainability_score', 0)
            fund_score = fundamental.get('overall_score', 0)

            logger.info(f"{i}. {symbol}: {dividend_yield:.2f}% yield, "
                       f"sustainability {sustainability:.1f}/10, "
                       f"fundamental {fund_score:.1f}/10")

        return len(opportunities) > 0

    except Exception as e:
        logger.error(f"❌ Simple dividend screening failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_simple_dividend_screening()
    if success:
        logger.success("🎉 Simple dividend screening test passed!")
    else:
        logger.error("❌ Simple dividend screening test failed!")