#!/usr/bin/env python3
"""
VIX Adaptive Integration Verification Script

Tests all components to ensure integration is working correctly.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test 1: Verify all imports work"""
    print("=" * 60)
    print("Test 1: Imports")
    print("=" * 60)

    try:
        from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration
        print("✅ VIXAdaptiveIntegration imported")

        from strategies.vix_adaptive.data_enricher import add_vix_indicators_to_cache
        print("✅ data_enricher imported")

        from config.strategy_config import RapidRotationConfig
        print("✅ RapidRotationConfig imported")

        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_config():
    """Test 2: Verify config parameter exists"""
    print("\n" + "=" * 60)
    print("Test 2: Configuration")
    print("=" * 60)

    try:
        from config.strategy_config import RapidRotationConfig
        config = RapidRotationConfig()

        has_param = hasattr(config, 'vix_adaptive_enabled')
        if has_param:
            print(f"✅ vix_adaptive_enabled parameter exists")
            print(f"   Current value: {config.vix_adaptive_enabled}")
            return True
        else:
            print("❌ vix_adaptive_enabled parameter not found")
            return False

    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False


def test_vix_adaptive():
    """Test 3: Verify VIX Adaptive initialization"""
    print("\n" + "=" * 60)
    print("Test 3: VIX Adaptive Strategy")
    print("=" * 60)

    try:
        from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration

        # Initialize with enabled=False to skip VIX data fetch
        vix = VIXAdaptiveIntegration(
            config_path='config/vix_adaptive.yaml',
            enabled=False
        )

        print(f"✅ VIX Adaptive initialized (disabled mode)")
        print(f"   {vix}")
        return True

    except Exception as e:
        print(f"❌ VIX Adaptive init failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_enricher():
    """Test 4: Verify data enricher works"""
    print("\n" + "=" * 60)
    print("Test 4: Data Enricher")
    print("=" * 60)

    try:
        from strategies.vix_adaptive.data_enricher import add_vix_indicators_to_cache
        import pandas as pd
        import numpy as np

        # Create sample data
        np.random.seed(42)
        df = pd.DataFrame({
            'open': np.random.rand(100) * 100 + 50,
            'high': np.random.rand(100) * 100 + 60,
            'low': np.random.rand(100) * 100 + 40,
            'close': np.random.rand(100) * 100 + 50,
            'volume': np.random.randint(1000000, 10000000, 100),
        })

        cache = {'TEST': df}

        print("   Sample data created (100 rows, 5 columns)")

        # Enrich
        count = add_vix_indicators_to_cache(cache)

        print(f"✅ Enriched {count} stocks")

        # Check columns
        enriched_df = cache['TEST']
        print(f"   Columns after enrichment: {len(enriched_df.columns)}")

        # Check required indicators
        required = ['atr', 'atr_pct', 'yesterday_dip', 'return_2d', 'dip_from_3d_high', 'score']
        missing = [col for col in required if col not in enriched_df.columns]

        if missing:
            print(f"❌ Missing indicators: {missing}")
            return False
        else:
            print(f"✅ All required indicators present:")
            for col in required:
                non_null = enriched_df[col].notna().sum()
                print(f"      {col}: {non_null} non-null values")
            return True

    except Exception as e:
        print(f"❌ Data enricher test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_engine_integration():
    """Test 5: Check if engine has VIX Adaptive integration"""
    print("\n" + "=" * 60)
    print("Test 5: Engine Integration")
    print("=" * 60)

    try:
        # Check if auto_trading_engine imports VIX Adaptive
        with open('src/auto_trading_engine.py', 'r') as f:
            content = f.read()

        checks = [
            ('VIXAdaptiveIntegration import', 'from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration'),
            ('data_enricher import', 'from strategies.vix_adaptive.data_enricher import add_vix_indicators_to_cache'),
            ('VIX_ADAPTIVE_ENABLED config', 'self.VIX_ADAPTIVE_ENABLED'),
            ('vix_adaptive initialization', 'self.vix_adaptive = VIXAdaptiveIntegration'),
            ('add_vix_indicators_to_cache call', 'add_vix_indicators_to_cache(self.screener.data_cache)'),
        ]

        all_ok = True
        for name, pattern in checks:
            if pattern in content:
                print(f"✅ {name}")
            else:
                print(f"❌ {name} not found")
                all_ok = False

        return all_ok

    except Exception as e:
        print(f"❌ Engine integration check failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "🔍" * 30)
    print("VIX ADAPTIVE INTEGRATION VERIFICATION")
    print("🔍" * 30 + "\n")

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_config()))
    results.append(("VIX Adaptive", test_vix_adaptive()))
    results.append(("Data Enricher", test_data_enricher()))
    results.append(("Engine Integration", test_engine_integration()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print("\n" + "=" * 60)
    if passed == total:
        print(f"✅ ALL TESTS PASSED ({passed}/{total})")
        print("=" * 60)
        print("\nVIX Adaptive integration is working correctly!")
        print("\nNext steps:")
        print("1. Test engine startup: python src/run_app.py")
        print("2. Enable VIX Adaptive: vix_adaptive_enabled = True")
        print("3. Monitor for 1-2 days (dry run)")
        print("4. Paper trade for 30+ days")
        return 0
    else:
        print(f"❌ TESTS FAILED ({passed}/{total} passed)")
        print("=" * 60)
        print("\nPlease fix the failing tests before proceeding.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
