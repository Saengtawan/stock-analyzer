#!/usr/bin/env python3
"""
Config Integration Test Suite v1.0

Tests comprehensive config validation, edge cases, and integration scenarios.

Author: Auto Trading System
Version: 1.0
Date: 2026-02-09
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import yaml

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config.strategy_config import RapidRotationConfig


class TestConfigValidation(unittest.TestCase):
    """Test config validation rules"""

    def test_valid_default_config(self):
        """Default config should be valid"""
        config = RapidRotationConfig()
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"Default config has errors: {errors}")

    def test_valid_config_from_yaml(self):
        """Config loaded from YAML should be valid"""
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'config', 'trading.yaml'
        )
        config = RapidRotationConfig.from_yaml(config_path)
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"YAML config has errors: {errors}")

    def test_invalid_sl_range(self):
        """SL min >= max should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(min_sl_pct=3.0, max_sl_pct=2.0)
        self.assertIn('min_sl_pct', str(context.exception))
        self.assertIn('max_sl_pct', str(context.exception))

    def test_invalid_tp_range(self):
        """TP min >= max should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(min_tp_pct=8.0, max_tp_pct=4.0)
        self.assertIn('min_tp_pct', str(context.exception))
        self.assertIn('max_tp_pct', str(context.exception))

    def test_tp_below_sl(self):
        """TP < SL should fail (negative R:R)"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                min_sl_pct=2.0, max_sl_pct=4.0,
                min_tp_pct=1.0, max_tp_pct=3.0,  # TP below SL
                default_tp_pct=2.0  # Also adjust default to match
            )
        self.assertIn('min_tp_pct', str(context.exception))
        self.assertIn('max_sl_pct', str(context.exception))

    def test_atr_tp_below_atr_sl(self):
        """ATR TP < ATR SL should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                atr_sl_multiplier=2.5,
                atr_tp_multiplier=1.5  # TP below SL
            )
        self.assertIn('atr_tp_multiplier', str(context.exception))
        self.assertIn('atr_sl_multiplier', str(context.exception))

    def test_invalid_position_size(self):
        """Position size > 100% should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(position_size_pct=150.0)
        self.assertIn('position_size_pct', str(context.exception))

    def test_base_position_exceeds_max(self):
        """Base position > max position should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                position_size_pct=20.0,
                max_position_pct=15.0
            )
        self.assertIn('position_size_pct', str(context.exception))
        self.assertIn('max_position_pct', str(context.exception))

    def test_pdt_reserve_exceeds_limit(self):
        """PDT reserve > day trade limit should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                pdt_day_trade_limit=3,
                pdt_reserve=5  # Reserve more than limit
            )
        self.assertIn('pdt_reserve', str(context.exception))
        self.assertIn('pdt_day_trade_limit', str(context.exception))

    def test_session_start_after_end(self):
        """Session start >= end should fail"""
        from config.strategy_config import SessionConfig
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                sessions={
                    'test': SessionConfig(start=570, end=390, interval=5, label='Bad Session')
                }
            )
        self.assertIn('start', str(context.exception))
        self.assertIn('end', str(context.exception))


class TestConfigScenarios(unittest.TestCase):
    """Test real-world config scenarios"""

    def test_conservative_profile(self):
        """Conservative trading profile should be valid"""
        config = RapidRotationConfig(
            min_sl_pct=1.5,
            max_sl_pct=2.0,
            default_sl_pct=1.75,  # Must be within [1.5, 2.0]
            min_tp_pct=4.0,
            max_tp_pct=6.0,
            default_tp_pct=5.0,   # Must be within [4.0, 6.0]
            position_size_pct=5.0,
            max_position_pct=8.0,
            max_positions=3,
            risk_budget_pct=0.5,
            daily_loss_limit_pct=2.0
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"Conservative profile invalid: {errors}")

    def test_aggressive_profile(self):
        """Aggressive trading profile should be valid"""
        config = RapidRotationConfig(
            min_sl_pct=2.5,
            max_sl_pct=4.0,
            default_sl_pct=3.0,   # Must be within [2.5, 4.0]
            min_tp_pct=8.0,
            max_tp_pct=15.0,
            default_tp_pct=10.0,  # Must be within [8.0, 15.0]
            position_size_pct=15.0,
            max_position_pct=20.0,
            max_positions=8,
            risk_budget_pct=2.0,
            daily_loss_limit_pct=8.0
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"Aggressive profile invalid: {errors}")

    def test_pdt_safe_profile(self):
        """PDT-safe profile (under $25k) should be valid"""
        config = RapidRotationConfig(
            pdt_account_threshold=25000.0,
            pdt_day_trade_limit=3,
            pdt_reserve=1,
            pdt_tp_threshold=3.0,
            pdt_enforce_always=True
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"PDT-safe profile invalid: {errors}")

    def test_no_trailing_stop(self):
        """Disabled trailing stop should be valid (use default values)"""
        config = RapidRotationConfig(
            trail_enabled=False
            # Keep default trail_activation_pct and trail_lock_pct
            # (validation still checks them even if disabled)
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"No trailing stop invalid: {errors}")

    def test_regime_filter_disabled(self):
        """Disabled regime filter should be valid"""
        config = RapidRotationConfig(
            regime_filter_enabled=False
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"Disabled regime filter invalid: {errors}")


class TestConfigEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions"""

    def test_minimum_valid_sl(self):
        """SL at 1% (minimum) should be valid"""
        config = RapidRotationConfig(
            min_sl_pct=1.0,
            max_sl_pct=1.5,
            default_sl_pct=1.25,  # Must be within [1.0, 1.5]
            min_tp_pct=3.0,
            max_tp_pct=5.0,
            default_tp_pct=4.0    # Must be within [3.0, 5.0]
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"Min SL invalid: {errors}")

    def test_maximum_valid_sl(self):
        """SL at 10% (maximum) should be valid"""
        config = RapidRotationConfig(
            min_sl_pct=8.0,
            max_sl_pct=10.0,
            default_sl_pct=9.0,   # Must be within [8.0, 10.0]
            min_tp_pct=15.0,
            max_tp_pct=20.0,
            default_tp_pct=17.0   # Must be within [15.0, 20.0]
        )
        errors = config.validate()
        self.assertEqual(len(errors), 0, f"Max SL invalid: {errors}")

    def test_sl_below_minimum(self):
        """SL < 1% should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                min_sl_pct=0.5,  # Below minimum
                max_sl_pct=1.0,
                default_sl_pct=0.8
            )
        self.assertIn('min_sl_pct', str(context.exception))

    def test_sl_above_maximum(self):
        """SL > 10% should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(
                min_sl_pct=8.0,
                max_sl_pct=12.0,  # Above maximum
                default_sl_pct=10.0,
                min_tp_pct=18.0,
                max_tp_pct=20.0,
                default_tp_pct=19.0
            )
        self.assertIn('max_sl_pct', str(context.exception))

    def test_single_position(self):
        """Max 1 position should be valid"""
        config = RapidRotationConfig(max_positions=1)
        errors = config.validate()
        self.assertEqual(len(errors), 0)

    def test_zero_positions(self):
        """Max 0 positions should fail"""
        with self.assertRaises(ValueError) as context:
            config = RapidRotationConfig(max_positions=0)
        self.assertIn('max_positions', str(context.exception))

    def test_many_positions(self):
        """Max 20 positions should be valid (with warning)"""
        config = RapidRotationConfig(max_positions=20)
        errors = config.validate()
        # Should have warning but no error
        self.assertTrue(
            len(errors) == 0 or
            all('WARNING' in err.upper() for err in errors)
        )


class TestConfigYAMLIntegration(unittest.TestCase):
    """Test YAML loading and saving"""

    def test_load_from_yaml(self):
        """Load config from YAML file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'min_sl_pct': 2.0,
                'max_sl_pct': 2.5,
                'min_tp_pct': 4.0,
                'max_tp_pct': 8.0,
                'max_positions': 5
            }, f)
            temp_path = f.name

        try:
            config = RapidRotationConfig.from_yaml(temp_path)
            self.assertEqual(config.min_sl_pct, 2.0)
            self.assertEqual(config.max_sl_pct, 2.5)
            self.assertEqual(config.min_tp_pct, 4.0)
            self.assertEqual(config.max_tp_pct, 8.0)
            self.assertEqual(config.max_positions, 5)
        finally:
            os.unlink(temp_path)

    def test_partial_yaml_uses_defaults(self):
        """Partial YAML should use defaults for missing values"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'min_sl_pct': 2.2,  # Use value compatible with defaults
                'max_positions': 5,
                # Other fields missing - should use defaults
            }, f)
            temp_path = f.name

        try:
            config = RapidRotationConfig.from_yaml(temp_path)
            self.assertEqual(config.min_sl_pct, 2.2)
            self.assertEqual(config.max_positions, 5)
            # Should have default values
            self.assertIsNotNone(config.max_sl_pct)
            self.assertIsNotNone(config.min_tp_pct)
        finally:
            os.unlink(temp_path)

    def test_invalid_yaml_field(self):
        """Unknown YAML fields should be ignored or handled gracefully"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                'min_sl_pct': 2.0,
                'unknown_field_xyz': 999,  # Unknown field
            }, f)
            temp_path = f.name

        try:
            config = RapidRotationConfig.from_yaml(temp_path)
            self.assertEqual(config.min_sl_pct, 2.0)
            # Should load successfully, ignoring unknown field
        finally:
            os.unlink(temp_path)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with PDTConfig"""

    def test_pdt_config_deprecated_warning(self):
        """PDTConfig should emit deprecation warning"""
        import warnings
        from pdt_smart_guard import PDTConfig

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = PDTConfig(max_day_trades=3)

            # Should have at least one deprecation warning
            deprecation_warnings = [
                warning for warning in w
                if issubclass(warning.category, DeprecationWarning)
            ]
            self.assertGreater(
                len(deprecation_warnings), 0,
                "PDTConfig should emit DeprecationWarning"
            )

    def test_pdt_smart_guard_accepts_rapid_rotation_config(self):
        """PDTSmartGuard should accept RapidRotationConfig directly"""
        from pdt_smart_guard import init_pdt_guard

        config = RapidRotationConfig(
            pdt_day_trade_limit=3,
            pdt_tp_threshold=3.0
        )

        # Should not raise error
        pdt_guard = init_pdt_guard(config=config)
        self.assertIsNotNone(pdt_guard)

    def test_pdt_smart_guard_still_accepts_pdt_config(self):
        """PDTSmartGuard should still accept PDTConfig (deprecated)"""
        from pdt_smart_guard import init_pdt_guard, PDTConfig
        import warnings

        pdt_config = PDTConfig(max_day_trades=3, sl_threshold=-2.5)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            # Should not raise error (backward compatible)
            pdt_guard = init_pdt_guard(config=pdt_config)
            self.assertIsNotNone(pdt_guard)


class TestConfigTools(unittest.TestCase):
    """Test config management CLI tools"""

    def test_config_tools_validate(self):
        """Config tools validate command should work"""
        import subprocess

        result = subprocess.run(
            ['python', 'scripts/config_tools.py', 'validate'],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..')
        )

        self.assertEqual(result.returncode, 0, f"Validate failed: {result.stderr}")
        self.assertIn('VALID', result.stdout)

    def test_config_tools_dump_text(self):
        """Config tools dump (text) should work"""
        import subprocess

        result = subprocess.run(
            ['python', 'scripts/config_tools.py', 'dump'],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..')
        )

        self.assertEqual(result.returncode, 0, f"Dump failed: {result.stderr}")
        self.assertIn('Stop Loss', result.stdout)

    def test_config_tools_dump_json(self):
        """Config tools dump (JSON) should work"""
        import subprocess
        import json

        result = subprocess.run(
            ['python', 'scripts/config_tools.py', 'dump', '--format', 'json'],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..')
        )

        self.assertEqual(result.returncode, 0, f"Dump JSON failed: {result.stderr}")

        # Should be valid JSON
        try:
            config_dict = json.loads(result.stdout)
            self.assertIn('min_sl_pct', config_dict)
            self.assertIn('max_tp_pct', config_dict)
        except json.JSONDecodeError as e:
            self.fail(f"Invalid JSON output: {e}")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
