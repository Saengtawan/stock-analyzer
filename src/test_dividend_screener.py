#!/usr/bin/env python3
"""
Test script for Dividend Growth Screener
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger

def test_dividend_screener():
    """Test dividend screener functionality"""
    logger.info("Testing Dividend Growth Screener...")

    # Initialize analyzer and screener
    analyzer = StockAnalyzer()
    dividend_screener = DividendGrowthScreener(analyzer)

    # Test 1: Basic dividend screening
    logger.info("=== Test 1: Basic Dividend Screening ===")
    try:
        opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=3.0,
            min_dividend_growth_rate=5.0,
            min_fundamental_score=4.0,
            max_stocks=5  # Limit to 5 for testing
        )

        logger.info(f"Found {len(opportunities)} dividend opportunities")

        for i, opp in enumerate(opportunities[:3], 1):  # Show top 3
            symbol = opp['symbol']
            dividend_data = opp.get('dividend_analysis', {})
            dividend_yield = dividend_data.get('dividend_yield', 0)
            sustainability = opp.get('dividend_sustainability_score', 0)
            attractiveness = opp.get('long_term_attractiveness', 0)

            logger.info(f"{i}. {symbol}: {dividend_yield:.1f}% yield, "
                       f"sustainability {sustainability:.1f}/10, "
                       f"attractiveness {attractiveness:.1f}/10")

    except Exception as e:
        logger.error(f"❌ Dividend screening failed: {e}")

    # Test 2: Portfolio generation
    logger.info("\n=== Test 2: Dividend Portfolio Generation ===")
    try:
        portfolio = dividend_screener.get_dividend_portfolio_suggestion(
            total_investment=100000,
            max_single_position=0.15,
            sector_diversification=True
        )

        if 'error' in portfolio:
            logger.error(f"❌ Portfolio generation failed: {portfolio['error']}")
        else:
            metrics = portfolio.get('portfolio_metrics', {})
            positions = portfolio.get('positions', [])

            logger.info(f"Portfolio created with {len(positions)} positions")
            logger.info(f"Portfolio dividend yield: {metrics.get('portfolio_dividend_yield', 0):.2f}%")
            logger.info(f"Annual dividend income: ${metrics.get('estimated_annual_dividend_income', 0):,.0f}")

            logger.info("Top 3 positions:")
            for i, pos in enumerate(positions[:3], 1):
                logger.info(f"{i}. {pos['symbol']}: ${pos['allocation_amount']:,.0f} "
                           f"({pos['allocation_percentage']:.1f}%) - "
                           f"{pos['dividend_yield']:.1f}% yield")

    except Exception as e:
        logger.error(f"❌ Portfolio generation failed: {e}")

    # Test 3: Sector-focused screening
    logger.info("\n=== Test 3: Sector-focused Screening ===")
    try:
        utilities_opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=3.0,
            min_fundamental_score=4.0,
            focus_sectors=['Utilities', 'Consumer Staples'],
            max_stocks=5
        )

        logger.info(f"Found {len(utilities_opportunities)} utilities/consumer staples opportunities")

        for i, opp in enumerate(utilities_opportunities[:3], 1):
            symbol = opp['symbol']
            sector = opp.get('fundamental_analysis', {}).get('sector', 'N/A')
            dividend_yield = opp.get('dividend_analysis', {}).get('dividend_yield', 0)

            logger.info(f"{i}. {symbol} ({sector}): {dividend_yield:.1f}% yield")

    except Exception as e:
        logger.error(f"❌ Sector-focused screening failed: {e}")

    logger.info("\n🎉 Dividend screener testing completed!")

if __name__ == "__main__":
    test_dividend_screener()