#!/usr/bin/env python3
"""
Debug payout ratio values to understand data format
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from loguru import logger

def debug_payout_ratio():
    """Debug payout ratio for various stocks"""
    logger.info("Debugging payout ratio values...")

    analyzer = StockAnalyzer()

    # Test stocks with known dividends
    test_stocks = ['KO', 'PG', 'JNJ', 'AAPL', 'MSFT']

    for symbol in test_stocks:
        try:
            logger.info(f"\n=== {symbol} ===")

            # Get financial data directly
            financial_data = analyzer.data_manager.get_financial_data(symbol)

            # Raw values
            payout_ratio = financial_data.get('payout_ratio')
            dividend_yield = financial_data.get('dividend_yield')
            eps = financial_data.get('eps')

            logger.info(f"Raw payout_ratio: {payout_ratio} (type: {type(payout_ratio)})")
            logger.info(f"Raw dividend_yield: {dividend_yield} (type: {type(dividend_yield)})")
            logger.info(f"Raw EPS: {eps} (type: {type(eps)})")

            # Test payout ratio analysis
            from screeners.dividend_screener import DividendGrowthScreener
            dividend_screener = DividendGrowthScreener(analyzer)

            dividend_analysis = dividend_screener._analyze_dividend_metrics(financial_data)
            if dividend_analysis:
                analyzed_payout = dividend_analysis.get('payout_ratio')
                logger.info(f"Analyzed payout_ratio: {analyzed_payout}")

                # Check if it's likely a percentage vs decimal
                if payout_ratio is not None:
                    if payout_ratio < 1.0:
                        logger.warning(f"⚠️  Payout ratio {payout_ratio} appears to be decimal format (should multiply by 100)")
                        converted = payout_ratio * 100
                        logger.info(f"Converted: {converted}%")
                    else:
                        logger.info(f"✅ Payout ratio {payout_ratio}% appears correct")

        except Exception as e:
            logger.error(f"❌ Failed to analyze {symbol}: {e}")

if __name__ == "__main__":
    debug_payout_ratio()