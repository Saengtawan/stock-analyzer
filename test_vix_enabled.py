#!/usr/bin/env python3
"""
Test VIX Adaptive with Enabled Config

Verifies VIX Adaptive initializes correctly and fetches VIX data.
"""

import sys
import os

# Add src to path
sys.path.insert(0, 'src')
os.chdir(os.path.dirname(__file__))

print('=' * 70)
print('VIX ADAPTIVE - ENABLED TEST')
print('=' * 70)
print()

# Load config
from config.strategy_config import RapidRotationConfig
config = RapidRotationConfig()

print(f'✅ Config: vix_adaptive_enabled = {config.vix_adaptive_enabled}')
print()

# Test VIX Adaptive initialization
print('Step 1: Initializing VIX Adaptive Strategy...')
print('-' * 70)

from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration

try:
    vix = VIXAdaptiveIntegration(
        config_path='config/vix_adaptive.yaml',
        enabled=True  # Enable to fetch VIX data
    )

    print(f'✅ VIX Adaptive initialized')
    print(f'   {vix}')
    print()

    # Get current VIX
    print('Step 2: Fetching current VIX data...')
    print('-' * 70)

    current_vix = vix.get_current_vix()
    current_tier = vix.get_current_tier()

    if current_vix is not None:
        print(f'✅ Current VIX: {current_vix:.2f}')
        print(f'✅ Current Tier: {current_tier.upper() if current_tier else "N/A"}')
    else:
        print('⚠️  Current VIX: Not available (may need to call update first)')
        print('   Checking VIX history instead...')
        vix_history = vix.vix_provider.get_vix_history(days=1)
        if len(vix_history) > 0:
            current_vix = vix_history['vix'].iloc[-1]
            current_tier = vix.strategy.tier_manager.get_tier(current_vix)
            print(f'✅ Latest VIX: {current_vix:.2f}')
            print(f'✅ Tier: {current_tier.upper()}')
    print()

    # Show tier boundaries
    print('Step 3: VIX Tier System')
    print('-' * 70)
    boundaries = vix.config['boundaries']
    print(f'  NORMAL tier:  VIX < {boundaries["normal_max"]}')
    print(f'  SKIP tier:    VIX {boundaries["normal_max"]}-{boundaries["skip_max"]}')
    print(f'  HIGH tier:    VIX {boundaries["skip_max"]}-{boundaries["high_max"]}')
    print(f'  EXTREME tier: VIX > {boundaries["high_max"]}')
    print()

    # Show what strategy would do
    print('Step 4: Current Strategy Action')
    print('-' * 70)

    if current_tier == 'normal':
        print('  ✅ NORMAL tier - Mean Reversion Strategy')
        print('     → Scan for high-score stocks with yesterday dip >= -1%')
        print('     → Max 3 positions, position sizes: [40%, 40%, 20%]')
        print('     → Stop loss: 2-4%, Trailing stop: +2% activation')

        # Get adaptive score threshold
        score_threshold = vix.strategy.score_adapter.get_score_threshold(vix=current_vix)
        print(f'     → Score threshold (adaptive): {score_threshold}')

    elif current_tier == 'skip':
        print('  ⏸️  SKIP tier - No New Trades')
        print('     → VIX in uncertainty zone (20-24)')
        print('     → Manage existing positions only')

    elif current_tier == 'high':
        print('  ⚡ HIGH tier - Bounce Strategy')

        # Check VIX direction
        vix_history = vix.vix_provider.get_vix_history(days=2)
        if len(vix_history) >= 2:
            vix_today = vix_history['vix'].iloc[-1]
            vix_yesterday = vix_history['vix'].iloc[-2]
            vix_falling = vix_today < vix_yesterday

            if vix_falling:
                print('     → ✅ VIX FALLING - Ready to scan for bounce signals')
            else:
                print('     → ❌ VIX NOT FALLING - Wait for VIX to drop')

        print('     → Look for confirmed bounces (gain_2d >= 1%, dip_3d <= -3%)')
        print('     → Max 1 position, 100% sizing')
        print('     → Stop loss: 3-6%, NO trailing stop')

    elif current_tier == 'extreme':
        print('  🚨 EXTREME tier - CLOSE ALL POSITIONS')
        print('     → VIX > 38 - Market panic mode')
        print('     → Close all positions immediately')

    print()

    # Show recent VIX history
    print('Step 5: Recent VIX History')
    print('-' * 70)
    vix_history = vix.vix_provider.get_vix_history(days=5)
    print('  Date         VIX    Tier')
    print('  ' + '-' * 30)
    for date, row in vix_history.tail(5).iterrows():
        vix_val = row['vix']
        tier = vix.strategy.tier_manager.get_tier(vix_val)
        print(f'  {date}  {vix_val:6.2f}  {tier.upper()}')

    print()
    print('=' * 70)
    print('✅ VIX ADAPTIVE READY')
    print('=' * 70)
    print()
    print('Status: Enabled and working correctly')
    print()
    print('Next steps:')
    print('  1. Monitor: Watch logs for VIX tier and signals')
    print('  2. Run app: python src/run_app.py')
    print('  3. Check: VIX signals should appear in scans')

except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
