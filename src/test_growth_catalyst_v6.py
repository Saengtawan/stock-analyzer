#!/usr/bin/env python3
"""
Test Growth Catalyst Screener with Improved Catalyst Discovery (v6)

This script tests the improvements made to:
1. News Sentiment Analyzer (proxy indicators)
2. Alternative earnings date source (estimation from history)
3. Improved insider data handling (better transaction detection)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_catalyst_screener():
    """Test the growth catalyst screener with improved catalyst discovery"""

    logger.info("=" * 80)
    logger.info("GROWTH CATALYST SCREENER TEST - v6.0 with Improved Catalysts")
    logger.info("=" * 80)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test with default parameters
    logger.info("\n📊 Test 1: Default Parameters")
    logger.info("-" * 80)
    logger.info("Target Gain: 10%")
    logger.info("Timeframe: 30 days")
    logger.info("Min Catalyst Score: 30")
    logger.info("Min Technical Score: 50")
    logger.info("Min AI Probability: 50%")
    logger.info("Max Stocks: 20")
    logger.info("")

    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=10.0,
        timeframe_days=30,
        min_catalyst_score=30.0,
        min_technical_score=50.0,
        min_ai_probability=50.0,
        max_stocks=20
    )

    logger.info(f"\n✅ Found {len(results)} opportunities with default parameters")

    if len(results) > 0:
        logger.info("\n🏆 Top 5 Opportunities:")
        for i, opp in enumerate(results[:5], 1):
            logger.info(f"\n{i}. {opp['symbol']}")
            logger.info(f"   Composite Score: {opp['composite_score']:.1f}")
            logger.info(f"   Catalyst Score: {opp['catalyst_score']:.1f}")
            logger.info(f"   Technical Score: {opp['technical_score']:.1f}")
            logger.info(f"   AI Probability: {opp['ai_probability']:.1f}%")
            logger.info(f"   Current Price: ${opp['current_price']:.2f}")
            logger.info(f"   Expected Return: {opp['expected_return_pct']:.1f}%")

            # Show catalyst breakdown
            if 'catalysts' in opp and opp['catalysts']:
                logger.info(f"   Catalysts:")
                for cat in opp['catalysts'][:3]:  # Top 3 catalysts
                    logger.info(f"      • {cat.get('description', 'N/A')} ({cat.get('score', 0)} pts)")
    else:
        logger.warning("\n⚠️ No opportunities found with default parameters")
        logger.info("\nLet's try with relaxed parameters...")

        # Test 2: Relaxed parameters
        logger.info("\n📊 Test 2: Relaxed Parameters")
        logger.info("-" * 80)

        results = screener.screen_growth_catalyst_opportunities(
            target_gain_pct=10.0,
            timeframe_days=30,
            min_catalyst_score=20.0,  # Lowered from 30
            min_technical_score=40.0,  # Lowered from 50
            min_ai_probability=40.0,   # Lowered from 50
            max_stocks=20
        )

        logger.info(f"\n✅ Found {len(results)} opportunities with relaxed parameters")

        if len(results) > 0:
            logger.info("\n🏆 Top 3 Opportunities:")
            for i, opp in enumerate(results[:3], 1):
                logger.info(f"\n{i}. {opp['symbol']}")
                logger.info(f"   Composite Score: {opp['composite_score']:.1f}")
                logger.info(f"   Catalyst Score: {opp['catalyst_score']:.1f}")
                logger.info(f"   Technical Score: {opp['technical_score']:.1f}")
                logger.info(f"   AI Probability: {opp['ai_probability']:.1f}%")

                if 'catalysts' in opp and opp['catalysts']:
                    logger.info(f"   Top Catalysts:")
                    for cat in opp['catalysts'][:2]:
                        logger.info(f"      • {cat.get('description', 'N/A')}")

    # Test 3: Single stock deep analysis
    logger.info("\n" + "=" * 80)
    logger.info("📊 Test 3: Single Stock Catalyst Analysis")
    logger.info("=" * 80)

    test_symbols = ['TSLA', 'NVDA', 'AAPL']

    for symbol in test_symbols:
        logger.info(f"\n🔍 Analyzing {symbol}...")
        try:
            # Find in results
            stock_result = next((r for r in results if r['symbol'] == symbol), None)

            if stock_result:
                logger.info(f"   ✅ Found in screening results")
                logger.info(f"   Catalyst Score: {stock_result['catalyst_score']:.1f}/100")
                logger.info(f"   Technical Score: {stock_result['technical_score']:.1f}/100")
                logger.info(f"   AI Probability: {stock_result['ai_probability']:.1f}%")

                if 'catalysts' in stock_result:
                    logger.info(f"   Detected Catalysts ({len(stock_result['catalysts'])}):")
                    for cat in stock_result['catalysts']:
                        logger.info(f"      • [{cat.get('type', 'unknown')}] {cat.get('description', 'N/A')} ({cat.get('score', 0)} pts)")
            else:
                logger.info(f"   ❌ Not found in results (likely filtered out)")

        except Exception as e:
            logger.error(f"   ❌ Error analyzing {symbol}: {e}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📈 SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total opportunities found: {len(results)}")

    if len(results) > 0:
        avg_catalyst = sum(r['catalyst_score'] for r in results) / len(results)
        avg_technical = sum(r['technical_score'] for r in results) / len(results)
        avg_ai_prob = sum(r['ai_probability'] for r in results) / len(results)

        logger.info(f"Average Catalyst Score: {avg_catalyst:.1f}")
        logger.info(f"Average Technical Score: {avg_technical:.1f}")
        logger.info(f"Average AI Probability: {avg_ai_prob:.1f}%")

        # Catalyst type breakdown
        catalyst_types = {}
        for result in results:
            if 'catalysts' in result:
                for cat in result['catalysts']:
                    cat_type = cat.get('type', 'unknown')
                    catalyst_types[cat_type] = catalyst_types.get(cat_type, 0) + 1

        logger.info(f"\nCatalyst Type Distribution:")
        for cat_type, count in sorted(catalyst_types.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"   {cat_type}: {count}")

    logger.info("\n✅ Test completed!")

if __name__ == "__main__":
    test_catalyst_screener()
