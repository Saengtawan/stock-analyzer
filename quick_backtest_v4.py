#!/usr/bin/env python3
"""
Quick Backtest v4.0 - Rule-Based Systems Test
Simple test to show rule-based systems working
"""

import sys
sys.path.insert(0, 'src')

from portfolio_manager_v3 import PortfolioManagerV3
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer

print("=" * 80)
print("🚀 Quick System Test v4.0 - RULE-BASED SYSTEMS")
print("=" * 80)

# Initialize
print("\n📦 Initializing systems...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)
pm = PortfolioManagerV3()

print("\n✅ Systems initialized!")

# Check rule-based status
print("\n🔍 Rule-Based Systems Status:")
if screener.screening_rules:
    print(f"   ✅ Screening Rules Engine: Active")
    print(f"      {len(screener.screening_rules.rules)} rules loaded:")
    for rule in screener.screening_rules.rules[:5]:  # Show first 5
        print(f"      - {rule.name} ({rule.priority.name})")
    print(f"      ... and {len(screener.screening_rules.rules) - 5} more")
else:
    print("   ⚠️  Screening Rules Engine: Not available")

if pm.exit_rules:
    print(f"\n   ✅ Exit Rules Engine: Active")
    print(f"      {len(pm.exit_rules.rules)} rules loaded:")
    for rule in pm.exit_rules.rules[:5]:  # Show first 5
        print(f"      - {rule.name} ({rule.priority.name})")
    print(f"      ... and {len(pm.exit_rules.rules) - 5} more")
else:
    print("   ⚠️  Exit Rules Engine: Not available")

# Show example tuning
print("\n🎛️  Example: Tune Screening Rules")
print("   Before:")
rsi_rule = [r for r in screener.screening_rules.rules if r.name == "MOMENTUM_RSI"][0]
print(f"   - RSI sweet spot: {rsi_rule.thresholds['sweet_spot_min']}-{rsi_rule.thresholds['sweet_spot_max']}")

print("\n   Tuning...")
screener.tune_screening_rule("MOMENTUM_RSI", "sweet_spot_min", 40.0)
screener.tune_screening_rule("MOMENTUM_RSI", "sweet_spot_max", 75.0)

print("   After:")
print(f"   - RSI sweet spot: {rsi_rule.thresholds['sweet_spot_min']}-{rsi_rule.thresholds['sweet_spot_max']}")

# Show example exit rule tuning
print("\n🎛️  Example: Tune Exit Rules")
print("   Before:")
target_rule = [r for r in pm.exit_rules.rules if r.name == "TARGET_HIT"][0]
print(f"   - Target: {target_rule.thresholds['target_pct']}%")

print("\n   Tuning...")
pm.tune_exit_rule("TARGET_HIT", "target_pct", 3.5)

print("   After:")
print(f"   - Target: {target_rule.thresholds['target_pct']}%")

# Export/Import example
print("\n💾 Example: Export/Import Configuration")
config = screener.export_screening_rules_config()
print(f"   ✅ Exported {len(config['rules'])} screening rules")

pm_config = pm.export_exit_rules_config()
print(f"   ✅ Exported {len(pm_config['rules'])} exit rules")

# Show rule statistics
print("\n📊 Screening Rules (All Rules):")
stats = screener.get_screening_rules_stats()
print(f"   {'Rule Name':30} {'Priority':10} {'Enabled':8}")
print("   " + "-" * 50)
for stat in stats:
    enabled = "✅" if stat['enabled'] else "❌"
    print(f"   {stat['name']:30} {stat['priority']:10} {enabled:8}")

print("\n📊 Exit Rules (All Rules):")
stats = pm.get_exit_rules_stats()
print(f"   {'Rule Name':30} {'Priority':10} {'Enabled':8}")
print("   " + "-" * 50)
for stat in stats:
    enabled = "✅" if stat['enabled'] else "❌"
    print(f"   {stat['name']:30} {stat['priority']:10} {enabled:8}")

print("\n" + "=" * 80)
print("✅ Rule-Based Systems Test Complete!")
print("=" * 80)

print("\n📚 Next Steps:")
print("   1. Run: python3 backtest_complete_v4.py (for full backtest)")
print("   2. Tune thresholds: screener.tune_screening_rule(...)")
print("   3. A/B test: export/import configs")
print("   4. Track performance: get_screening_rules_stats()")
print("\n🎯 Both systems are ready for optimization!")
