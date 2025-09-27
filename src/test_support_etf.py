#!/usr/bin/env python3
"""
Test Support Level Screener with ETF support
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.support_level_screener import SupportLevelScreener
from loguru import logger

def test_support_etf():
    """Test support level screener with ETF support"""
    logger.info("Testing Support Level Screener with ETF support...")

    analyzer = StockAnalyzer()
    support_screener = SupportLevelScreener(analyzer)

    # AI-powered screener will automatically generate universe with stocks and ETFs

    try:
        opportunities = support_screener.screen_support_opportunities(
            max_distance_from_support=0.10,  # 10% below support
            min_fundamental_score=3.0,  # Lower requirement
            min_technical_score=3.0,   # Lower requirement
            max_stocks=5,
            time_horizon='medium'
        )

        logger.info(f"✅ Found {len(opportunities)} support opportunities")

        # Show results with ETF indicators
        for i, opp in enumerate(opportunities, 1):
            symbol = opp['symbol']
            is_etf = opp.get('is_etf', False)
            etf_tag = " [ETF]" if is_etf else " [STOCK]"
            current_price = opp['current_price']
            support_1 = opp['support_1']
            attractiveness = opp['attractiveness_score']

            logger.info(f"{i}. {symbol}{etf_tag}: ${current_price:.2f} "
                       f"(Support: ${support_1:.2f}) - Score: {attractiveness:.1f}/10")

        return len(opportunities) > 0

    except Exception as e:
        logger.error(f"❌ Support screening failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_support_etf()
    if success:
        logger.success("🎉 Support Level Screener ETF test passed!")
    else:
        logger.error("❌ Support Level Screener ETF test failed!")