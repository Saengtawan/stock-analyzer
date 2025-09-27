#!/usr/bin/env python3
"""
Debug SPYI specifically to understand why values are strange
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger

def debug_spyi():
    """Debug SPYI dividend analysis"""
    logger.info("Debugging SPYI dividend analysis...")

    # Initialize analyzer
    analyzer = StockAnalyzer()
    dividend_screener = DividendGrowthScreener(analyzer)

    try:
        # Analyze SPYI directly
        logger.info("=== Step 1: Basic Analysis ===")
        analysis = analyzer.analyze_stock('SPYI', time_horizon='long', account_value=100000)

        if 'error' in analysis:
            logger.error(f"❌ Basic analysis failed: {analysis['error']}")
            return

        logger.info("✅ Basic analysis successful")

        # Check financial data
        logger.info("\n=== Step 2: Raw Financial Data ===")
        financial_data = analyzer.data_manager.get_financial_data('SPYI')

        logger.info(f"Symbol: {financial_data.get('symbol', 'N/A')}")
        logger.info(f"Sector: {financial_data.get('sector', 'N/A')}")
        logger.info(f"Industry: {financial_data.get('industry', 'N/A')}")
        logger.info(f"Dividend yield: {financial_data.get('dividend_yield', 'N/A')}")
        logger.info(f"Payout ratio (raw): {financial_data.get('payout_ratio', 'N/A')}")
        logger.info(f"EPS: {financial_data.get('eps', 'N/A')}")
        logger.info(f"Revenue growth: {financial_data.get('revenue_growth', 'N/A')}")
        logger.info(f"Earnings growth: {financial_data.get('earnings_growth', 'N/A')}")
        logger.info(f"ROE: {financial_data.get('return_on_equity', 'N/A')}")
        logger.info(f"Current ratio: {financial_data.get('current_ratio', 'N/A')}")
        logger.info(f"Debt to equity: {financial_data.get('debt_to_equity', 'N/A')}")

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

        # Test dividend sustainability calculation
        logger.info("\n=== Step 5: Dividend Sustainability ===")
        mock_opportunity = {
            'dividend_analysis': dividend_analysis,
            'fundamental_analysis': fundamental
        }

        sustainability_score = dividend_screener._calculate_dividend_sustainability(mock_opportunity)
        logger.info(f"Dividend sustainability score: {sustainability_score:.1f}/10")

        # Test with very relaxed criteria
        logger.info("\n=== Step 6: Testing with Relaxed Criteria ===")
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
        else:
            logger.success("✅ Passed with relaxed criteria")
            opp = opportunities[0]

            logger.info(f"SPYI opportunity details:")
            logger.info(f"  Symbol: {opp.get('symbol', 'N/A')}")
            logger.info(f"  Dividend yield: {opp.get('dividend_analysis', {}).get('dividend_yield', 'N/A')}%")
            logger.info(f"  Dividend growth: {opp.get('dividend_analysis', {}).get('dividend_growth_rate', 'N/A')}%")
            logger.info(f"  Payout ratio: {opp.get('dividend_analysis', {}).get('payout_ratio', 'N/A')}%")
            logger.info(f"  Dividend safety: {opp.get('dividend_analysis', {}).get('dividend_safety', 'N/A')}")
            logger.info(f"  Sustainability score: {opp.get('dividend_sustainability_score', 'N/A')}/10")
            logger.info(f"  Fundamental score: {opp.get('fundamental_analysis', {}).get('overall_score', 'N/A')}/10")
            logger.info(f"  Long-term attractiveness: {opp.get('long_term_attractiveness', 'N/A')}/10")

    except Exception as e:
        logger.error(f"❌ Debug failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_spyi()