#!/usr/bin/env python3
"""
Config Management Tools v1.0

Tools for managing and validating trading configurations.

Usage:
    # Validate config
    python scripts/config_tools.py validate

    # Dump current config
    python scripts/config_tools.py dump

    # Dump as JSON
    python scripts/config_tools.py dump --format json > config.json

    # Compare two configs
    python scripts/config_tools.py diff --file1 config/trading.yaml --file2 config/backup.yaml

Author: Auto Trading System
Version: 1.0
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config.strategy_config import RapidRotationConfig
import json
from typing import Optional


def validate_config(file_path: Optional[str] = None):
    """Validate configuration file"""
    if file_path is None:
        file_path = os.path.join(
            os.path.dirname(__file__), '..', 'config', 'trading.yaml'
        )

    print("=" * 70)
    print(f"Validating Configuration: {file_path}")
    print("=" * 70)
    print()

    try:
        config = RapidRotationConfig.from_yaml(file_path)
        print("✅ Configuration is VALID!")
        print()
        print("Key Parameters:")
        print(f"  SL Range: {config.min_sl_pct}% - {config.max_sl_pct}%")
        print(f"  TP Range: {config.min_tp_pct}% - {config.max_tp_pct}%")
        print(f"  Max Positions: {config.max_positions}")
        print(f"  Risk Budget: {config.risk_budget_pct}% per trade")
        print(f"  Daily Loss Limit: {config.daily_loss_limit_pct}%")
        print()
        return 0
    except ValueError as e:
        print(f"❌ Configuration is INVALID!")
        print()
        print(f"Error: {e}")
        print()
        print("Fix the errors above and try again.")
        print("See docs/CONFIG_SCHEMA.md for parameter reference.")
        print()
        return 1
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return 1


def dump_config(file_path: Optional[str] = None, output_format: str = 'text'):
    """Dump configuration to stdout"""
    if file_path is None:
        file_path = os.path.join(
            os.path.dirname(__file__), '..', 'config', 'trading.yaml'
        )

    try:
        config = RapidRotationConfig.from_yaml(file_path)

        if output_format == 'json':
            # Convert to dict and dump as JSON
            import dataclasses
            config_dict = dataclasses.asdict(config)
            print(json.dumps(config_dict, indent=2, default=str))
        else:
            # Pretty print
            print("=" * 70)
            print(f"Configuration Dump: {file_path}")
            print("=" * 70)
            print()

            # Group by category
            categories = {
                'Stop Loss / Take Profit': [
                    'atr_sl_multiplier', 'atr_tp_multiplier',
                    'min_sl_pct', 'max_sl_pct', 'min_tp_pct', 'max_tp_pct',
                    'default_sl_pct', 'default_tp_pct', 'pdt_tp_threshold'
                ],
                'Trailing Stop': [
                    'trail_enabled', 'trail_activation_pct', 'trail_lock_pct'
                ],
                'Position Management': [
                    'max_positions', 'max_hold_days', 'position_size_pct',
                    'max_position_pct', 'simulated_capital'
                ],
                'Risk Management': [
                    'risk_parity_enabled', 'risk_budget_pct',
                    'daily_loss_limit_pct', 'weekly_loss_limit_pct',
                    'max_consecutive_losses'
                ],
                'Scoring & Filtering': [
                    'min_score', 'min_atr_pct', 'max_rsi_entry'
                ],
                'PDT Settings': [
                    'pdt_account_threshold', 'pdt_day_trade_limit',
                    'pdt_reserve', 'pdt_enforce_always'
                ],
                'Regime Detection': [
                    'regime_filter_enabled', 'regime_sma_period',
                    'regime_rsi_min', 'regime_vix_max'
                ]
            }

            for category, fields in categories.items():
                print(f"{category}:")
                print("-" * 70)
                for field in fields:
                    if hasattr(config, field):
                        value = getattr(config, field)
                        print(f"  {field:30s} = {value}")
                print()

        return 0
    except Exception as e:
        print(f"❌ Failed to dump config: {e}")
        return 1


def compare_configs(file1: str, file2: str):
    """Compare two configuration files"""
    print("=" * 70)
    print(f"Comparing Configurations")
    print("=" * 70)
    print(f"File 1: {file1}")
    print(f"File 2: {file2}")
    print()

    try:
        config1 = RapidRotationConfig.from_yaml(file1)
        config2 = RapidRotationConfig.from_yaml(file2)

        import dataclasses
        dict1 = dataclasses.asdict(config1)
        dict2 = dataclasses.asdict(config2)

        # Find differences
        differences = []
        for key in dict1:
            val1 = dict1[key]
            val2 = dict2.get(key)
            if val1 != val2:
                differences.append((key, val1, val2))

        if not differences:
            print("✅ No differences found - configs are identical")
            return 0
        else:
            print(f"❌ Found {len(differences)} difference(s):\n")
            for key, val1, val2 in differences:
                print(f"{key:30s}:")
                print(f"  File 1: {val1}")
                print(f"  File 2: {val2}")
                print()
            return 1

    except Exception as e:
        print(f"❌ Failed to compare configs: {e}")
        return 1


def show_help():
    """Show usage help"""
    print(__doc__)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Config Management Tools',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate config file')
    validate_parser.add_argument('--file', help='Config file to validate (default: config/trading.yaml)')

    # Dump command
    dump_parser = subparsers.add_parser('dump', help='Dump config to stdout')
    dump_parser.add_argument('--file', help='Config file to dump (default: config/trading.yaml)')
    dump_parser.add_argument('--format', choices=['text', 'json'], default='text',
                            help='Output format (default: text)')

    # Diff command
    diff_parser = subparsers.add_parser('diff', help='Compare two config files')
    diff_parser.add_argument('--file1', required=True, help='First config file')
    diff_parser.add_argument('--file2', required=True, help='Second config file')

    args = parser.parse_args()

    if not args.command:
        show_help()
        return 1

    # Run command
    if args.command == 'validate':
        return validate_config(args.file)
    elif args.command == 'dump':
        return dump_config(args.file, args.format)
    elif args.command == 'diff':
        return compare_configs(args.file1, args.file2)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
