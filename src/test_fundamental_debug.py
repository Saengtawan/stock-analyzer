#!/usr/bin/env python3
"""
Debug script to find the exact source of NoneType comparison errors
"""
import sys
import os
import traceback

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer
from api.yahoo_finance_client import YahooFinanceClient
from loguru import logger

def debug_fundamental_analysis(symbol: str):
    """Debug fundamental analysis for a specific symbol"""
    logger.info(f"Debugging fundamental analysis for {symbol}")

    try:
        # Get financial data
        client = YahooFinanceClient()
        financial_data = client.get_financial_data(symbol)
        current_price = 100.0  # Use dummy price for testing

        logger.info(f"Financial data keys: {list(financial_data.keys())}")

        # Initialize analyzer
        analyzer = FundamentalAnalyzer(financial_data, current_price)

        # Try to analyze step by step
        logger.info("Getting ratios...")
        ratios = analyzer.ratios_calculator.get_all_ratios(current_price)
        logger.info(f"Ratios: {ratios}")

        logger.info("Getting industry comparison...")
        industry_comparison = analyzer.industry_comparison.compare_ratios(ratios)

        logger.info("Getting sector ranking...")
        sector_ranking = analyzer.industry_comparison.get_sector_ranking(ratios)

        logger.info("Getting DCF results...")
        dcf_results = analyzer.dcf_valuation.calculate_dcf_value()

        logger.info("Calculating fundamental score...")
        try:
            fundamental_score = analyzer._calculate_fundamental_score(ratios, dcf_results, sector_ranking)
            logger.success(f"✅ {symbol}: Fundamental score calculated successfully")
        except Exception as e:
            logger.error(f"❌ {symbol}: Error in fundamental score calculation: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")

        logger.success(f"✅ {symbol}: Analysis debug completed")
        return None

    except Exception as e:
        logger.error(f"❌ {symbol}: Error occurred: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return None

if __name__ == "__main__":
    # Test with one problematic stock first
    debug_fundamental_analysis('MCD')