#!/usr/bin/env python3
"""
Test Sector Regime Detector
Demonstrates usage of the SectorRegimeDetector class
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from loguru import logger
from api.data_manager import DataManager
from sector_regime_detector import SectorRegimeDetector

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def main():
    """Test sector regime detector"""

    logger.info("=" * 80)
    logger.info("SECTOR REGIME DETECTOR TEST")
    logger.info("=" * 80)
    logger.info("")

    # Initialize
    dm = DataManager()
    detector = SectorRegimeDetector(data_manager=dm)

    # Update all sector regimes
    logger.info("Fetching sector regime data...")
    regimes = detector.update_all_sectors()

    # Print formatted report
    logger.info("")
    print(detector.format_sector_report())

    # Test individual sector lookups
    logger.info("=" * 80)
    logger.info("TESTING INDIVIDUAL SECTOR LOOKUPS")
    logger.info("=" * 80)
    logger.info("")

    test_sectors = [
        'Technology',
        'Financials',
        'Energy',
        'Healthcare',
        'Financial Services',  # Alternative name
        'XLK',  # Direct ETF lookup
        'Communication Services'
    ]

    for sector in test_sectors:
        regime = detector.get_sector_regime(sector)
        adjustment = detector.get_regime_adjustment(sector)
        threshold = detector.get_confidence_threshold(sector)
        should_trade = detector.should_trade_sector(sector, min_regime_level='SIDEWAYS')

        logger.info(f"Sector: {sector:25s}")
        logger.info(f"  Regime: {regime:15s} | Score Adj: {adjustment:>+3d} | "
                   f"Confidence Threshold: {threshold} | Tradeable: {should_trade}")
        logger.info("")

    # Get summary DataFrame
    logger.info("=" * 80)
    logger.info("SECTOR SUMMARY DATAFRAME")
    logger.info("=" * 80)
    logger.info("")

    summary = detector.get_sector_summary()
    print(summary.to_string(index=False))

    # Identify bull and bear sectors
    logger.info("")
    logger.info("=" * 80)
    logger.info("SECTOR CLASSIFICATION")
    logger.info("=" * 80)
    logger.info("")

    bull_sectors = detector.get_bull_sectors()
    bear_sectors = detector.get_bear_sectors()

    logger.info(f"BULL SECTORS ({len(bull_sectors)}):")
    for etf in bull_sectors:
        sector_name = detector.SECTOR_ETFS[etf]
        logger.info(f"  {etf} - {sector_name}")

    logger.info("")

    if bear_sectors:
        logger.info(f"BEAR SECTORS ({len(bear_sectors)}):")
        for etf in bear_sectors:
            sector_name = detector.SECTOR_ETFS[etf]
            logger.info(f"  {etf} - {sector_name}")
    else:
        logger.info("BEAR SECTORS: None")

    # Example: How to use in screening
    logger.info("")
    logger.info("=" * 80)
    logger.info("EXAMPLE: APPLYING TO STOCK SCREENING")
    logger.info("=" * 80)
    logger.info("")

    # Simulate screening some stocks
    example_stocks = [
        {'symbol': 'JPM', 'sector': 'Financial Services', 'base_score': 70},
        {'symbol': 'AAPL', 'sector': 'Technology', 'base_score': 70},
        {'symbol': 'XOM', 'sector': 'Energy', 'base_score': 70},
        {'symbol': 'GOOGL', 'sector': 'Communication Services', 'base_score': 70},
        {'symbol': 'UNH', 'sector': 'Healthcare', 'base_score': 70},
    ]

    logger.info("Stock Screening with Sector Regime Adjustments:")
    logger.info("")

    adjusted_stocks = []

    for stock in example_stocks:
        regime = detector.get_sector_regime(stock['sector'])
        adjustment = detector.get_regime_adjustment(stock['sector'])
        threshold = detector.get_confidence_threshold(stock['sector'])

        adjusted_score = stock['base_score'] + adjustment
        passes = adjusted_score >= threshold

        logger.info(f"{stock['symbol']:6s} ({stock['sector']:25s})")
        logger.info(f"  Sector Regime: {regime:15s}")
        logger.info(f"  Base Score: {stock['base_score']:3d} + Sector Adj: {adjustment:>+3d} = {adjusted_score:3d}")
        logger.info(f"  Threshold: {threshold} | PASSES: {'YES' if passes else 'NO'}")
        logger.info("")

        adjusted_stocks.append({
            **stock,
            'regime': regime,
            'adjustment': adjustment,
            'adjusted_score': adjusted_score,
            'threshold': threshold,
            'passes': passes
        })

    # Show which stocks would be selected
    passing_stocks = [s for s in adjusted_stocks if s['passes']]
    logger.info(f"PASSING STOCKS ({len(passing_stocks)}/{len(adjusted_stocks)}):")
    for stock in sorted(passing_stocks, key=lambda x: x['adjusted_score'], reverse=True):
        logger.info(f"  {stock['symbol']:6s} - Score: {stock['adjusted_score']:3d} ({stock['regime']})")

    logger.info("")
    logger.info("=" * 80)
    logger.info("TEST COMPLETE")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
