#!/usr/bin/env python3
"""
Quick test for Dividend Screener with relaxed criteria
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger

def test_quick_dividend_screening():
    """Quick test with relaxed criteria"""
    logger.info("Testing Dividend Screener with relaxed criteria...")

    # Initialize analyzer and screener
    analyzer = StockAnalyzer()
    dividend_screener = DividendGrowthScreener(analyzer)

    # Reduce the stock universe for quick testing
    dividend_screener.dividend_universe = ['KO', 'PG', 'JNJ', 'PEP', 'XOM', 'CVX', 'T', 'VZ', 'ABBV', 'SO']

    try:
        # Test with very relaxed criteria
        opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=1.0,  # Very low threshold
            min_dividend_growth_rate=0,  # No growth requirement
            min_payout_ratio=10.0,  # Very low payout ratio requirement
            max_payout_ratio=90.0,  # High max payout ratio
            min_fundamental_score=1.0,  # Very low fundamental score
            max_stocks=10
        )

        logger.info(f"✅ Found {len(opportunities)} dividend opportunities with relaxed criteria")

        # Show top opportunities
        for i, opp in enumerate(opportunities[:5], 1):
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
        logger.error(f"❌ Quick dividend screening failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_quick_dividend_screening()
    if success:
        logger.success("🎉 Quick dividend screening test passed!")
    else:
        logger.error("❌ Quick dividend screening test failed!")