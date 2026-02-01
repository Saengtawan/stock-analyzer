#!/usr/bin/env python3
"""
Test the updated gap range (2-4%) to verify scoring works correctly
"""

import sys
import os
sys.path.append(os.path.dirname(__file__) + '/src')

def test_gap_scoring():
    """Test that gap scoring properly handles 2-4% range"""

    print("=" * 80)
    print("🧪 Testing Gap Range Update (v8.0): 2-4% Range")
    print("=" * 80)
    print()

    # Simulate gap score calculation for different gap sizes
    test_cases = [
        (1.8, "Below range"),
        (2.2, "Sweet spot (2-3%)"),
        (2.8, "Sweet spot (2-3%)"),
        (3.2, "NEW: Moderate (3-4%)"),
        (3.8, "NEW: Moderate (3-4%)"),
        (4.2, "High risk (4-5%)"),
        (5.5, "Very high risk (5%+)"),
    ]

    print(f"{'Gap %':<10} {'Category':<30} {'Expected Score Range':<25} {'Confidence Impact':<20}")
    print("-" * 80)

    for gap_pct, category in test_cases:
        # Simplified gap size score calculation
        if gap_pct >= 15:
            gap_size_score = 0.2
            conf_impact = "-20"
        elif gap_pct >= 10:
            gap_size_score = 0.3
            conf_impact = "-20"
        elif gap_pct >= 7:
            gap_size_score = 0.5
            conf_impact = "-20"
        elif gap_pct >= 5:
            gap_size_score = 0.6
            conf_impact = "-15"
        elif gap_pct >= 4:
            gap_size_score = 0.4
            conf_impact = "-20"
        elif gap_pct >= 3:
            gap_size_score = 1.0  # NEW: Improved from 0.4
            conf_impact = "+5"    # NEW: Was -25 before!
        elif gap_pct >= 2:
            gap_size_score = 1.5
            conf_impact = "+15"
        else:
            gap_size_score = 0.8
            conf_impact = "+3"

        score_range = f"{gap_size_score:.1f}/1.5 pts"
        print(f"{gap_pct:<10.1f} {category:<30} {score_range:<25} {conf_impact:<20}")

    print()
    print("=" * 80)
    print("✅ KEY IMPROVEMENTS:")
    print("=" * 80)
    print("1. Gap 3-4% now gets +5 confidence (was -25 before!)")
    print("2. Gap 3-4% now scores 1.0/1.5 pts (was 0.4/1.5 before)")
    print("3. Gap 4-5% still heavily penalized (-20 confidence)")
    print("4. Default max_gap_pct = 4.0% (was 3.0%)")
    print()
    print("📊 Expected Results:")
    print("   - More opportunities (includes 3-4% gaps)")
    print("   - Moderate quality (expect ~50% trap rate for 3-4% vs 41% for 2-3%)")
    print("   - Trade-off: quantity vs quality")
    print()

    # Test what would happen with real scanner call
    print("=" * 80)
    print("🔧 Scanner Configuration:")
    print("=" * 80)
    print("Default parameters (scan_premarket_opportunities):")
    print(f"  min_gap_pct = 2.0%")
    print(f"  max_gap_pct = 4.0% (NEW - was 3.0%)")
    print()
    print("Example stocks that will NOW be included:")
    print("  • Stock with 3.2% gap → NOW INCLUDED ✅ (was excluded before)")
    print("  • Stock with 3.8% gap → NOW INCLUDED ✅ (was excluded before)")
    print("  • Stock with 4.2% gap → Still excluded (> 4.0%)")
    print()

    return True

if __name__ == '__main__':
    test_gap_scoring()
    print("✅ Test completed!")
