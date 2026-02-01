"""
Test v4.0 with DEBUG logging to see why stocks are being rejected
"""
import sys
import os
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener

# Set DEBUG level
logger.remove()
logger.add(sys.stdout, level="DEBUG", format="<level>{message}</level>")

def test_v4_debug():
    """Test v4.0 with DEBUG logging"""
    print("=" * 80)
    print("🔍 Testing v4.0 with DEBUG Logging")
    print("=" * 80)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Test with minimal parameters
    results = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        min_price=3.0,
        min_catalyst_score=0.0,
        min_technical_score=0.0,
        min_ai_probability=0.0,
        max_stocks=30,
        universe_multiplier=2
    )

    print(f"\n" + "=" * 80)
    print(f"RESULTS: Found {len(results)} stocks")
    print("=" * 80)

    return results

if __name__ == "__main__":
    test_v4_debug()
