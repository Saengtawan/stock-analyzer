"""
Test time_horizon fix - verify weights change correctly for short/medium/long
"""
import requests
import json
from loguru import logger

BASE_URL = "http://localhost:5002"

def test_time_horizon(symbol: str, time_horizon: str):
    """Test analysis with specific time horizon"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing {symbol} with time_horizon={time_horizon}")
    logger.info(f"{'='*60}")

    payload = {
        "symbol": symbol,
        "time_horizon": time_horizon,
        "include_ai": False  # Faster test
    }

    response = requests.post(f"{BASE_URL}/api/analyze", json=payload, timeout=120)

    if response.status_code == 200:
        result = response.json()

        # Extract unified recommendation
        unified_rec = result.get('unified_recommendation', {})
        weights = unified_rec.get('weights_applied', {})

        logger.info(f"✅ SUCCESS - Analysis completed")
        logger.info(f"  Time Horizon: {time_horizon}")
        logger.info(f"  Weights Applied: {weights}")
        logger.info(f"  Recommendation: {unified_rec.get('recommendation')}")
        logger.info(f"  Score: {unified_rec.get('score')}")

        return weights
    else:
        logger.error(f"❌ FAILED - Status {response.status_code}")
        logger.error(f"  Response: {response.text[:500]}")
        return None

if __name__ == "__main__":
    symbol = "AAPL"

    # Test all three time horizons
    logger.info("Testing time_horizon fix for dynamic weighting...")

    short_weights = test_time_horizon(symbol, "short")
    medium_weights = test_time_horizon(symbol, "medium")
    long_weights = test_time_horizon(symbol, "long")

    # Verify weights are different
    logger.info(f"\n{'='*60}")
    logger.info("RESULTS SUMMARY:")
    logger.info(f"{'='*60}")

    if short_weights and medium_weights and long_weights:
        logger.info(f"✅ SHORT  (1-14 days):   Technical={short_weights.get('technical', 0):.0%}, Momentum={short_weights.get('momentum', 0):.0%}")
        logger.info(f"✅ MEDIUM (1-6 months):  Fundamental={medium_weights.get('fundamental', 0):.0%}, Technical={medium_weights.get('technical', 0):.0%}")
        logger.info(f"✅ LONG   (6+ months):   Fundamental={long_weights.get('fundamental', 0):.0%}, Insider={long_weights.get('insider', 0):.0%}")

        # Verify they are actually different
        if short_weights != medium_weights and medium_weights != long_weights:
            logger.success("\n🎉 BUG FIXED! Weights change correctly for different time horizons!")
        else:
            logger.error("\n❌ BUG NOT FIXED - Weights are still the same!")
    else:
        logger.error("\n❌ Test failed - could not get all weights")
