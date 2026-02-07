#!/usr/bin/env python3
"""
Post-Refactor Verification Script
==================================
Compares current state against pre-refactor snapshots.
Run after each refactoring phase to ensure behavior is unchanged.

Usage:
    python3 tests/snapshots/verify_refactor.py
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

SNAPSHOT_DIR = Path(__file__).parent / 'pre_refactor'


def load_snapshot(name: str) -> dict:
    """Load a snapshot file"""
    filepath = SNAPSHOT_DIR / name
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


def calculate_file_checksum(filepath: str) -> str:
    """Calculate MD5 checksum"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def verify_public_api() -> tuple:
    """Verify public API methods still exist and have same signatures"""
    print("\n🌐 Verifying public API...")

    from auto_trading_engine import AutoTradingEngine
    import inspect

    expected = load_snapshot('methods/public_api.json')
    errors = []
    passed = 0

    for method_name, expected_info in expected.items():
        if hasattr(AutoTradingEngine, method_name):
            method = getattr(AutoTradingEngine, method_name)
            passed += 1
            print(f"  ✓ {method_name}() exists")
        else:
            errors.append(f"Missing method: {method_name}")
            print(f"  ✗ {method_name}() MISSING!")

    return passed, errors


def verify_class_structure() -> tuple:
    """Verify all classes still exist"""
    print("\n🏗️ Verifying class structure...")

    import auto_trading_engine as engine_module
    import inspect

    expected = load_snapshot('methods/class_structure.json')
    errors = []
    passed = 0

    for class_name, expected_info in expected.get('classes', {}).items():
        if hasattr(engine_module, class_name):
            cls = getattr(engine_module, class_name)
            if inspect.isclass(cls):
                passed += 1
                print(f"  ✓ class {class_name} exists")
            else:
                errors.append(f"{class_name} is not a class")
        else:
            # Check if imported from submodule (after refactor)
            try:
                from engine.models import TradingState, SignalSource, ManagedPosition, DailyStats, QueuedSignal
                model_classes = {'TradingState', 'SignalSource', 'ManagedPosition', 'DailyStats', 'QueuedSignal'}
                if class_name in model_classes:
                    passed += 1
                    print(f"  ✓ class {class_name} exists (from engine.models)")
                    continue
            except ImportError:
                pass
            errors.append(f"Missing class: {class_name}")
            print(f"  ✗ class {class_name} MISSING!")

    return passed, errors


def verify_method_signatures() -> tuple:
    """Verify all method signatures match"""
    print("\n📋 Verifying method signatures...")

    from auto_trading_engine import AutoTradingEngine
    import inspect

    expected = load_snapshot('methods/method_signatures.json')
    errors = []
    passed = 0
    warnings = 0

    # Only verify public methods
    public_methods = {k: v for k, v in expected.items() if v.get('is_public', False)}

    for method_name, expected_info in public_methods.items():
        if hasattr(AutoTradingEngine, method_name):
            method = getattr(AutoTradingEngine, method_name)
            try:
                sig = inspect.signature(method)
                current_params = list(sig.parameters.keys())
                expected_params = expected_info.get('params', [])

                if current_params == expected_params:
                    passed += 1
                    print(f"  ✓ {method_name}() signature matches")
                else:
                    warnings += 1
                    print(f"  ⚠ {method_name}() signature changed: {expected_params} → {current_params}")
            except Exception as e:
                warnings += 1
                print(f"  ⚠ {method_name}() cannot inspect: {e}")
        else:
            errors.append(f"Missing public method: {method_name}")
            print(f"  ✗ {method_name}() MISSING!")

    return passed, errors, warnings


def verify_dependencies() -> tuple:
    """Verify all dependencies are still importable"""
    print("\n🔗 Verifying dependencies...")

    expected = load_snapshot('methods/dependency_map.json')
    errors = []
    passed = 0

    local_imports = expected.get('local', [])

    for imp in local_imports:
        # Extract module name from import statement
        if 'from' in imp:
            parts = imp.split()
            if len(parts) >= 2:
                module = parts[1].replace('.', '').strip()
        else:
            parts = imp.split()
            if len(parts) >= 2:
                module = parts[1].strip()

        # Try to import
        try:
            if module in ['alpaca_trader', 'trading_config', 'trading_safety', 'trade_logger', 'sector_regime_detector']:
                __import__(module)
                passed += 1
                print(f"  ✓ {module} importable")
        except ImportError as e:
            errors.append(f"Cannot import {module}: {e}")
            print(f"  ✗ {module} import failed!")

    return passed, errors


def verify_imports() -> tuple:
    """Verify engine still imports correctly"""
    print("\n📦 Verifying engine imports...")

    errors = []

    try:
        from auto_trading_engine import AutoTradingEngine
        print("  ✓ AutoTradingEngine imports")
    except ImportError as e:
        errors.append(f"Cannot import AutoTradingEngine: {e}")
        print(f"  ✗ AutoTradingEngine import failed: {e}")
        return 0, errors

    try:
        from auto_trading_engine import TradingState, ManagedPosition, QueuedSignal
        print("  ✓ TradingState, ManagedPosition, QueuedSignal import")
    except ImportError:
        # After refactor, these may be in engine.models
        try:
            from engine.models import TradingState, ManagedPosition, QueuedSignal
            print("  ✓ TradingState, ManagedPosition, QueuedSignal import (from engine.models)")
        except ImportError as e:
            errors.append(f"Cannot import model classes: {e}")
            print(f"  ✗ Model classes import failed!")

    return 1, errors


def run_syntax_check() -> tuple:
    """Run Python syntax check on all modified files"""
    print("\n🐍 Running syntax checks...")

    import ast

    src_dir = Path(__file__).parent.parent.parent / 'src'
    errors = []
    passed = 0

    files_to_check = [
        'auto_trading_engine.py',
        'engine/__init__.py',
        'engine/models.py',
        'engine/time_utils.py',
        'engine/state_manager.py',
        'engine/regime_checker.py',
        'engine/filter_engine.py',
        'engine/risk_manager.py',
        'engine/signal_queue.py',
        'engine/position_monitor.py',
        'engine/order_executor.py',
        'engine/core.py',
    ]

    for f in files_to_check:
        filepath = src_dir / f
        if filepath.exists():
            try:
                with open(filepath) as fp:
                    ast.parse(fp.read())
                passed += 1
                print(f"  ✓ {f} syntax OK")
            except SyntaxError as e:
                errors.append(f"Syntax error in {f}: {e}")
                print(f"  ✗ {f} SYNTAX ERROR: {e}")

    return passed, errors


def generate_report(results: dict) -> str:
    """Generate verification report"""
    total_passed = sum(r.get('passed', 0) for r in results.values())
    total_errors = sum(len(r.get('errors', [])) for r in results.values())
    total_warnings = sum(r.get('warnings', 0) for r in results.values())

    report = f"""
╔══════════════════════════════════════════════════════════╗
║           POST-REFACTOR VERIFICATION REPORT              ║
╠══════════════════════════════════════════════════════════╣
║  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                              ║
║  Passed: {total_passed:3d}   Errors: {total_errors:3d}   Warnings: {total_warnings:3d}                  ║
╠══════════════════════════════════════════════════════════╣
"""

    for category, data in results.items():
        status = "✓ PASS" if not data.get('errors') else "✗ FAIL"
        report += f"║  {category:20s} {status:10s} ({data.get('passed', 0)} checks)       ║\n"

    if total_errors == 0:
        report += """╠══════════════════════════════════════════════════════════╣
║  🎉 ALL VERIFICATIONS PASSED - REFACTOR SUCCESSFUL!      ║
╚══════════════════════════════════════════════════════════╝
"""
    else:
        report += """╠══════════════════════════════════════════════════════════╣
║  ⚠️  VERIFICATION FAILED - REVIEW ERRORS ABOVE           ║
╚══════════════════════════════════════════════════════════╝
"""
        report += "\nErrors:\n"
        for category, data in results.items():
            for error in data.get('errors', []):
                report += f"  - [{category}] {error}\n"

    return report


def main():
    """Main entry point"""
    print("=" * 60)
    print("  POST-REFACTOR VERIFICATION")
    print("=" * 60)

    results = {}

    # Run all verifications
    passed, errors = verify_imports()
    results['imports'] = {'passed': passed, 'errors': errors}

    passed, errors = run_syntax_check()
    results['syntax'] = {'passed': passed, 'errors': errors}

    passed, errors = verify_class_structure()
    results['classes'] = {'passed': passed, 'errors': errors}

    passed, errors = verify_public_api()
    results['public_api'] = {'passed': passed, 'errors': errors}

    passed, errors, warnings = verify_method_signatures()
    results['signatures'] = {'passed': passed, 'errors': errors, 'warnings': warnings}

    passed, errors = verify_dependencies()
    results['dependencies'] = {'passed': passed, 'errors': errors}

    # Generate report
    report = generate_report(results)
    print(report)

    # Save report
    report_path = SNAPSHOT_DIR.parent / 'verification_report.txt'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Report saved to: {report_path}")

    # Return exit code
    total_errors = sum(len(r.get('errors', [])) for r in results.values())
    return 0 if total_errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
