#!/usr/bin/env python3
"""
Debug SPYI sector/industry data
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from loguru import logger

def debug_spyi_sector():
    """Debug SPYI sector and industry data"""
    logger.info("Debugging SPYI sector/industry...")

    analyzer = StockAnalyzer()

    # Get financial data
    financial_data = analyzer.data_manager.get_financial_data('SPYI')

    logger.info(f"SPYI Financial Data:")
    logger.info(f"  Symbol: {financial_data.get('symbol')}")
    logger.info(f"  Sector: {financial_data.get('sector')} (type: {type(financial_data.get('sector'))})")
    logger.info(f"  Industry: {financial_data.get('industry')} (type: {type(financial_data.get('industry'))})")

    # Test ETF detection manually
    is_etf = analyzer._detect_etf('SPYI', financial_data)
    logger.info(f"  ETF Detection Result: {is_etf}")

    # Test known ETFs check
    known_etfs = {
        'SPYI', 'VYM', 'DVY', 'HDV', 'SCHD', 'VIG', 'DGRO', 'FDV', 'RDVY', 'NOBL',
        'SPY', 'QQQ', 'IWM', 'VTI', 'VXUS', 'VEA', 'VWO', 'BND', 'AGG', 'TLT',
        'GLD', 'SLV', 'VNQ', 'XLF', 'XLK', 'XLV', 'XLE', 'XLI', 'XLP', 'XLU',
        'ARKK', 'ARKQ', 'ARKG', 'ARKF', 'ARKW', 'TQQQ', 'SQQQ', 'UPRO', 'TMF'
    }
    logger.info(f"  In known ETFs list: {'SPYI' in known_etfs}")

if __name__ == "__main__":
    debug_spyi_sector()