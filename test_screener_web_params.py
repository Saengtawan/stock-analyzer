#!/usr/bin/env python3
"""
Debug Growth Catalyst Screener - ใช้ parameters เดียวกับ web app
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

logger.info("=" * 80)
logger.info("🔬 DEBUG GROWTH CATALYST SCREENER (Web App Parameters)")
logger.info("=" * 80)
logger.info("")

# Initialize exactly like web app
logger.info("Initializing Stock Analyzer...")
analyzer = StockAnalyzer()

logger.info("Initializing Growth Catalyst Screener...")
growth_catalyst_screener = GrowthCatalystScreener(analyzer)

# Use exact parameters from web UI
target_gain_pct = 5.0
timeframe_days = 30
min_market_cap = None
max_market_cap = None
min_price = 3.0
max_price = None
min_daily_volume = 100000
min_catalyst_score = 0
min_technical_score = 0
min_ai_probability = 0
min_entry_score = 55
max_stocks = 20
universe_multiplier = 2

logger.info("")
logger.info("Web UI Parameters:")
logger.info(f"  target_gain_pct: {target_gain_pct}%")
logger.info(f"  timeframe_days: {timeframe_days}")
logger.info(f"  min_price: ${min_price}")
logger.info(f"  min_entry_score: {min_entry_score} (KEY FILTER)")
logger.info(f"  universe_multiplier: {universe_multiplier}x")
logger.info("")

# Run screening
logger.info("🔄 Starting screening (this may take 30-60 seconds)...")
logger.info("")

opportunities = growth_catalyst_screener.screen_growth_catalyst_opportunities(
    target_gain_pct=target_gain_pct,
    timeframe_days=timeframe_days,
    min_market_cap=min_market_cap,
    max_market_cap=max_market_cap,
    min_price=min_price,
    max_price=max_price,
    min_daily_volume=min_daily_volume,
    min_catalyst_score=min_catalyst_score,
    min_technical_score=min_technical_score,
    min_ai_probability=min_ai_probability,
    max_stocks=max_stocks,
    universe_multiplier=universe_multiplier
)

logger.info("")
logger.info("=" * 80)
logger.info("📊 BEFORE Entry Score Filter")
logger.info("=" * 80)
logger.info(f"Found {len(opportunities)} stocks")

if opportunities:
    logger.info("")
    logger.info("Top 10 by Entry Score:")
    sorted_opps = sorted(opportunities, key=lambda x: x.get('entry_score', 0), reverse=True)
    for i, opp in enumerate(sorted_opps[:10], 1):
        entry = opp.get('entry_score', 0)
        symbol = opp.get('symbol', 'N/A')
        price = opp.get('price', 0)
        logger.info(f"{i:2d}. {symbol:6s} ${price:7.2f} - Entry: {entry:.1f}/100")

# Apply Entry Score filter (like web app does)
logger.info("")
logger.info("=" * 80)
logger.info(f"📊 AFTER Entry Score ≥ {min_entry_score} Filter")
logger.info("=" * 80)

if min_entry_score > 0 and opportunities:
    before_count = len(opportunities)
    opportunities = [opp for opp in opportunities if opp.get('entry_score', 0) >= min_entry_score]
    after_count = len(opportunities)
    
    logger.info(f"Filtered: {before_count} → {after_count} stocks")
    logger.info(f"Removed: {before_count - after_count} stocks with Entry Score < {min_entry_score}")

logger.info("")
if len(opportunities) == 0:
    logger.warning("⚠️ NO STOCKS PASSED Entry Score ≥ 55 filter!")
    logger.info("")
    logger.info("💡 This is NOT a bug if:")
    logger.info("   • Market is in correction/bear mode")
    logger.info("   • Most stocks are extended (RSI >72, momentum >38%)")
    logger.info("   • BULL sectors are weak today")
    logger.info("")
    logger.info("🔧 Try these:")
    logger.info("   • Lower Entry Score to 50 or 45")
    logger.info("   • Check market conditions (SPY down?)")
    logger.info("   • Run on different trading day")
else:
    logger.info(f"✅ Found {len(opportunities)} stocks!")
    logger.info("")
    for i, opp in enumerate(opportunities[:5], 1):
        entry = opp.get('entry_score', 0)
        symbol = opp.get('symbol', 'N/A')
        price = opp.get('price', 0)
        sector = opp.get('sector_regime', 'N/A')
        logger.info(f"{i}. {symbol:6s} ${price:7.2f} - Entry: {entry:.1f} - Sector: {sector}")

logger.info("")
logger.info("=" * 80)
