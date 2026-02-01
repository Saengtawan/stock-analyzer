#!/usr/bin/env python3
"""
Test improved sector matching for semiconductor stocks
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from sector_rotation import SectorRotationDetector
import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def main():
    print("\n" + "="*80)
    print("🧪 TEST: Improved Sector Matching for Semiconductors")
    print("="*80)

    detector = SectorRotationDetector()

    # Test semiconductor stocks
    semiconductor_stocks = [
        'LRCX',   # Lam Research - Semiconductor Equipment
        'NVDA',   # NVIDIA - Semiconductors
        'AMD',    # AMD - Semiconductors
        'AVGO',   # Broadcom - Semiconductors
        'QCOM',   # Qualcomm - Semiconductors
        'MRVL',   # Marvell - Semiconductors
    ]

    print(f"\n{'Symbol':<8} {'Industry':<40} {'Matched Sector':<20} {'Momentum':<12} {'Boost':<8}")
    print("-" * 100)

    for symbol in semiconductor_stocks:
        # Get status (which will do smart matching)
        status = detector.get_stock_sector_status(symbol)

        # Get boost using matched sector
        boost = detector.get_sector_boost(status['sector'])

        # Get industry for display
        import yfinance as yf
        try:
            ticker = yf.Ticker(symbol)
            industry = ticker.info.get('industry', 'Unknown')[:38]
        except:
            industry = 'Unknown'

        print(f"{symbol:<8} {industry:<40} {status['sector']:<20} "
              f"{status['momentum_score']:>+6.1f}%{'':<4} "
              f"{boost:.2f}x")

    print("\n" + "="*80)
    print("🔍 VERIFICATION")
    print("="*80)
    print("\n✅ Expected: All semiconductor stocks should match to 'Semiconductors' (+7.7%)")
    print("✅ Expected: Boost should be 1.1x or 1.2x (hot sector)")
    print("\n❌ OLD behavior: Would match to 'Technology' (+2.7%, neutral)")
    print("❌ OLD boost: 1.0x (no boost)")

    print("\n" + "="*80)
    print("💡 IMPACT")
    print("="*80)
    print("\nFor LRCX with composite score of 48.7:")
    print("- OLD: 48.7 × 1.0x = 48.7 (no boost)")
    print("- NEW: 48.7 × 1.1x = 53.6 (+10% boost!) 🚀")
    print("\nThis properly rewards stocks in hot sectors!")


if __name__ == "__main__":
    main()
