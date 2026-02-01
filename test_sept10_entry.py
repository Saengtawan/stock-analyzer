#!/usr/bin/env python3
"""
Direct Test - Does screening work on Sept 10?
"""

from datetime import datetime
from src.complete_growth_system import CompleteGrowthSystem

if __name__ == "__main__":
    print("=" * 80)
    print("Testing Sept 10, 2025 - Should find AVGO")
    print("=" * 80)
    print()

    system = CompleteGrowthSystem()
    date = datetime(2025, 9, 10)

    # Run screening (with verbose output)
    candidates = system.screen_for_entries(date, quiet=False)

    print()
    print("=" * 80)
    print(f"Result: {len(candidates)} candidates found")
    print("=" * 80)

    if candidates:
        for i, stock in enumerate(candidates, 1):
            print(f"{i}. {stock['symbol']}: Score {stock['total_score']}/200")
            print(f"   Fundamental: {stock['fundamental']['quality_score']}/100")
            print(f"   Catalyst: {stock['catalyst']['catalyst_score']}/100")
            print(f"   Entry Price: ${stock['technical']['entry_price']:.2f}")
            print()
    else:
        print("\n❌ No candidates - system is broken!")
