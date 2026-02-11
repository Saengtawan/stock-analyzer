#!/usr/bin/env python3
"""
VIX Adaptive Strategy v3.0 - Demo Script

Demonstrates how to use the VIX Adaptive Strategy.

Usage:
    python examples/vix_adaptive_demo.py
"""

import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategies.vix_adaptive import VIXAdaptiveStrategy
from src.data.vix_data_provider import VIXDataProvider


def main():
    print("=" * 80)
    print("VIX ADAPTIVE STRATEGY v3.0 - DEMO")
    print("=" * 80)
    print()

    # 1. Load configuration
    print("📋 Loading configuration...")
    config_path = Path(__file__).parent.parent / 'config' / 'vix_adaptive.yaml'

    with open(config_path) as f:
        config = yaml.safe_load(f)

    print(f"✅ Loaded config: {config_path}")
    print(f"   Boundaries: {config['boundaries']}")
    print()

    # 2. Initialize VIX data provider
    print("📊 Initializing VIX data provider...")
    vix_provider = VIXDataProvider(cache_duration_hours=1)

    # Fetch recent VIX data
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    vix_provider.fetch_vix_data(start_date=start_date, end_date=end_date)

    print(f"✅ {vix_provider}")
    print()

    # 3. Initialize VIX Adaptive Strategy
    print("🚀 Initializing VIX Adaptive Strategy...")
    strategy = VIXAdaptiveStrategy(config, vix_provider)

    print(f"✅ {strategy}")
    print()

    # 4. Get current VIX and tier
    print("🔍 Current Market State:")
    try:
        current_vix = vix_provider.get_current_vix()
        print(f"   VIX: {current_vix:.2f}")

        tier = strategy.tier_manager.get_tier(current_vix)
        print(f"   Tier: {tier.upper()}")

        # Get recent VIX history
        vix_history = vix_provider.get_vix_history(days=5)
        print(f"\n   Recent VIX History:")
        for date, row in vix_history.tail(5).iterrows():
            print(f"      {date}: {row['vix']:.2f}")

        # Determine direction
        if len(vix_history) >= 2:
            vix_today = vix_history['vix'].iloc[-1]
            vix_yesterday = vix_history['vix'].iloc[-2]
            direction = strategy.tier_manager.get_vix_direction(vix_today, vix_yesterday)
            print(f"\n   VIX Direction: {direction.upper()}")

        # Get adaptive score threshold
        score_threshold = strategy.score_adapter.get_score_threshold(vix=current_vix)
        print(f"   Adaptive Score Threshold: {score_threshold}")

        print()

    except Exception as e:
        print(f"❌ Error fetching current VIX: {e}")
        print()

    # 5. Show tier-specific configuration
    print("⚙️  Tier Configurations:")
    print()

    print("NORMAL Tier (VIX < 20):")
    normal_config = config['tiers']['normal']
    print(f"   Strategy: {normal_config['strategy']}")
    print(f"   Max Positions: {normal_config['max_positions']}")
    print(f"   Position Sizes: {normal_config['position_sizes']}")
    print(f"   Stop Loss Range: {normal_config['stop_loss_range']}")
    print(f"   Max Hold Days: {normal_config['max_hold_days']}")
    print()

    print("HIGH Tier (VIX 24-38):")
    high_config = config['tiers']['high']
    print(f"   Strategy: {high_config['strategy']}")
    print(f"   Max Positions: {high_config['max_positions']}")
    print(f"   Bounce Type: {high_config['bounce_type']}")
    print(f"   VIX Condition: {high_config['vix_condition']} ⚠️ CRITICAL")
    print(f"   Stop Loss Range: {high_config['stop_loss_range']}")
    print(f"   Max Hold Days: {high_config['max_hold_days']}")
    print()

    # 6. Show what strategy would do right now
    print("🎯 Current Strategy Action:")
    if tier == 'normal':
        print("   ✅ NORMAL tier - Scan for mean reversion signals")
        print("   → Look for high-score stocks with yesterday dip >= -1%")
        print(f"   → Score threshold: {score_threshold}")
        print("   → Max 3 positions")
    elif tier == 'skip':
        print("   ⏸️  SKIP tier - No new trades")
        print("   → VIX in uncertainty zone (20-24)")
        print("   → Manage existing positions only")
    elif tier == 'high':
        print("   ⚡ HIGH tier - Scan for bounce signals")
        direction_msg = "✅ VIX FALLING" if direction == 'falling' else "❌ VIX NOT FALLING"
        print(f"   → VIX direction: {direction_msg}")
        if direction == 'falling':
            print("   → Look for confirmed bounces (gain_2d >= 1%, dip_3d <= -3%)")
            print("   → Max 1 position")
        else:
            print("   → Wait for VIX to fall before trading")
    elif tier == 'extreme':
        print("   🚨 EXTREME tier - CLOSE ALL POSITIONS")
        print("   → VIX > 38 - Market panic mode")
        print("   → Protect capital, wait for VIX to drop")
    print()

    print("=" * 80)
    print("Demo complete!")
    print()
    print("Next steps:")
    print("  1. Integrate with trading engine")
    print("  2. Add required indicators (return_2d, dip_from_3d_high)")
    print("  3. Run historical backtest validation")
    print("  4. Paper trade for 30+ days")
    print("=" * 80)


if __name__ == '__main__':
    main()
