#!/usr/bin/env python3
"""
Debug Growth Catalyst Screener - ทดสอบว่าทำไมไม่เจอหุ้น
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from ai_stock_analyzer import AIStockAnalyzer
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

logger.info("=" * 80)
logger.info("🔬 DEBUG GROWTH CATALYST SCREENER")
logger.info("=" * 80)
logger.info("")

# Initialize components
logger.info("Initializing AI Stock Analyzer...")
ai_analyzer = AIStockAnalyzer()

logger.info("Initializing Growth Catalyst Screener...")
screener = GrowthCatalystScreener(stock_analyzer=ai_analyzer)

# Test with same parameters from UI
logger.info("")
logger.info("Testing with UI parameters:")
logger.info("  target_return: 5%")
logger.info("  min_entry_score: 55 (KEY FILTER)")
logger.info("  min_price: 3.0")
logger.info("  universe_multiplier: 2.0")
logger.info("")

# Run screening
logger.info("🔄 Starting screening...")
results = screener.screen(
    target_return=5.0,
    min_composite_score=0,
    min_technical_score=0,
    min_ai_probability=0,
    min_entry_score=55,
    min_catalyst_score=0,
    min_price=3.0,
    max_results=20,
    universe_multiplier=2.0
)

logger.info("")
logger.info("=" * 80)
logger.info("📊 SCREENING RESULTS")
logger.info("=" * 80)
logger.info("")

if 'error' in results:
    logger.error(f"❌ ERROR: {results['error']}")
else:
    logger.info(f"✅ Screening completed")
    metadata = results.get('metadata', {})
    logger.info(f"   Universe size: {metadata.get('universe_size', 'N/A')}")
    logger.info(f"   Stocks analyzed: {metadata.get('stocks_analyzed', 'N/A')}")
    logger.info(f"   Passed gates: {metadata.get('passed_gates', 'N/A')}")
    logger.info(f"   Results found: {len(results.get('stocks', []))}")
    logger.info("")

    if len(results.get('stocks', [])) == 0:
        logger.warning("⚠️ NO STOCKS FOUND!")
        logger.info("")
        logger.info("Analyzing rejection reasons...")
        logger.info("")

        if 'rejection_summary' in metadata:
            logger.info("🚫 TOP 10 REJECTION REASONS:")
            for reason, count in sorted(metadata['rejection_summary'].items(), key=lambda x: x[1], reverse=True)[:10]:
                logger.info(f"   {count:3d}x: {reason}")
        
        logger.info("")
        logger.info("💡 POSSIBLE CAUSES:")
        logger.info("   1. Market conditions today don't meet v4.2 criteria")
        logger.info("   2. Entry Score 55+ is too high for current stocks")
        logger.info("   3. Most stocks are extended (RSI >72 or momentum >38%)")
        logger.info("")
        logger.info("🔧 SUGGESTIONS:")
        logger.info("   • Try lowering Entry Score to 50 or 45")
        logger.info("   • Check if it's a Bear market day")
        logger.info("   • Look at rejection reasons above for patterns")
    else:
        logger.info("🏆 TOP STOCKS FOUND:")
        for i, stock in enumerate(results['stocks'][:5], 1):
            entry_score = stock.get('entry_score', 0)
            logger.info(f"{i}. {stock['symbol']:6s} ${stock['price']:7.2f} - Entry: {entry_score:.1f}/100")

logger.info("")
logger.info("=" * 80)
