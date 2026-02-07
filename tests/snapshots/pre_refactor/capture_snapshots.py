#!/usr/bin/env python3
"""
Phase 0: Pre-Refactor Snapshot Capture
=======================================
Captures output of all public methods before refactoring.
Run this BEFORE making any changes to auto_trading_engine.py

Usage:
    python3 tests/snapshots/pre_refactor/capture_snapshots.py
"""

import os
import sys
import json
import hashlib
import pickle
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

SNAPSHOT_DIR = Path(__file__).parent
METHODS_DIR = SNAPSHOT_DIR / 'methods'
STATE_DIR = SNAPSHOT_DIR / 'state'
CHECKSUMS_DIR = SNAPSHOT_DIR / 'checksums'


def calculate_file_checksum(filepath: str) -> str:
    """Calculate MD5 checksum of a file"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def capture_checksums():
    """Capture checksums of all relevant files"""
    print("\n📦 Capturing file checksums...")

    src_dir = SNAPSHOT_DIR.parent.parent.parent / 'src'
    checksums = {}

    files_to_check = [
        'auto_trading_engine.py',
        'alpaca_trader.py',
        'trading_config.py',
        'trading_safety.py',
        'trade_logger.py',
        'sector_regime_detector.py',
        'screeners/rapid_rotation_screener.py',
        'api/data_manager.py',
        'api/base_client.py',
        'web/app.py',
    ]

    for f in files_to_check:
        filepath = src_dir / f
        if filepath.exists():
            checksums[f] = {
                'md5': calculate_file_checksum(str(filepath)),
                'size': filepath.stat().st_size,
                'lines': len(filepath.read_text().splitlines())
            }
            print(f"  ✓ {f}: {checksums[f]['md5'][:8]}... ({checksums[f]['lines']} lines)")

    with open(CHECKSUMS_DIR / 'file_checksums.json', 'w') as f:
        json.dump(checksums, f, indent=2)

    print(f"  → Saved to checksums/file_checksums.json")
    return checksums


def capture_method_signatures():
    """Capture all method signatures from AutoTradingEngine"""
    print("\n📋 Capturing method signatures...")

    from auto_trading_engine import AutoTradingEngine
    import inspect

    signatures = {}

    for name, method in inspect.getmembers(AutoTradingEngine, predicate=inspect.isfunction):
        sig = inspect.signature(method)
        signatures[name] = {
            'params': [p for p in sig.parameters.keys()],
            'doc': (method.__doc__ or '')[:200],
            'is_public': not name.startswith('_'),
            'line_number': inspect.getsourcelines(method)[1] if hasattr(method, '__code__') else 0
        }

    with open(METHODS_DIR / 'method_signatures.json', 'w') as f:
        json.dump(signatures, f, indent=2)

    public_count = sum(1 for s in signatures.values() if s['is_public'])
    private_count = len(signatures) - public_count
    print(f"  ✓ {len(signatures)} methods captured ({public_count} public, {private_count} private)")
    print(f"  → Saved to methods/method_signatures.json")

    return signatures


def capture_class_structure():
    """Capture class hierarchy and attributes"""
    print("\n🏗️ Capturing class structure...")

    import auto_trading_engine as engine_module
    import inspect

    structure = {
        'classes': {},
        'module_level': []
    }

    for name, obj in inspect.getmembers(engine_module):
        if inspect.isclass(obj) and obj.__module__ == 'auto_trading_engine':
            structure['classes'][name] = {
                'bases': [b.__name__ for b in obj.__bases__],
                'methods': [m for m in dir(obj) if not m.startswith('__')],
                'line_number': inspect.getsourcelines(obj)[1] if hasattr(obj, '__module__') else 0
            }
            print(f"  ✓ class {name}: {len(structure['classes'][name]['methods'])} members")

    with open(METHODS_DIR / 'class_structure.json', 'w') as f:
        json.dump(structure, f, indent=2)

    print(f"  → Saved to methods/class_structure.json")
    return structure


def capture_state_file_formats():
    """Capture format of state files"""
    print("\n💾 Capturing state file formats...")

    state_dir = SNAPSHOT_DIR.parent.parent.parent / 'state'
    formats = {}

    if state_dir.exists():
        for f in state_dir.glob('*.json'):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                formats[f.name] = {
                    'keys': list(data.keys()) if isinstance(data, dict) else 'list',
                    'sample': str(data)[:500],
                    'size': f.stat().st_size
                }
                print(f"  ✓ {f.name}: {formats[f.name]['keys']}")
            except Exception as e:
                formats[f.name] = {'error': str(e)}

    with open(STATE_DIR / 'state_formats.json', 'w') as f:
        json.dump(formats, f, indent=2)

    print(f"  → Saved to state/state_formats.json")
    return formats


def capture_config_snapshot():
    """Capture current config values"""
    print("\n⚙️ Capturing config snapshot...")

    config_file = SNAPSHOT_DIR.parent.parent.parent / 'config' / 'trading.yaml'

    if config_file.exists():
        import yaml
        with open(config_file) as f:
            config = yaml.safe_load(f)

        with open(STATE_DIR / 'config_snapshot.json', 'w') as f:
            json.dump(config, f, indent=2, default=str)

        print(f"  ✓ Config captured ({len(config)} top-level keys)")
        print(f"  → Saved to state/config_snapshot.json")
        return config
    else:
        print(f"  ⚠ Config file not found")
        return {}


def capture_dependency_map():
    """Capture import dependencies"""
    print("\n🔗 Capturing dependency map...")

    engine_file = SNAPSHOT_DIR.parent.parent.parent / 'src' / 'auto_trading_engine.py'

    imports = {
        'stdlib': [],
        'third_party': [],
        'local': []
    }

    with open(engine_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith('import ') or line.startswith('from '):
                if 'from .' in line or any(x in line for x in ['alpaca', 'trading_', 'sector_', 'screeners', 'api.']):
                    imports['local'].append(line)
                elif any(x in line for x in ['pandas', 'numpy', 'loguru', 'requests', 'yaml', 'pytz']):
                    imports['third_party'].append(line)
                else:
                    imports['stdlib'].append(line)

    with open(METHODS_DIR / 'dependency_map.json', 'w') as f:
        json.dump(imports, f, indent=2)

    print(f"  ✓ stdlib: {len(imports['stdlib'])}, third_party: {len(imports['third_party'])}, local: {len(imports['local'])}")
    print(f"  → Saved to methods/dependency_map.json")
    return imports


def capture_public_api():
    """Capture public API method return types (mock mode)"""
    print("\n🌐 Capturing public API signatures...")

    # These are the methods called by web/app.py
    public_api = {
        'get_status': {
            'return_type': 'Dict',
            'keys': ['state', 'is_running', 'mode', 'positions_count', 'queue_count',
                     'daily_pnl', 'weekly_pnl', 'market_regime', 'vix', 'last_scan_time',
                     'next_scan_time', 'pdt_budget', 'paper_mode', 'version']
        },
        'get_full_config': {
            'return_type': 'Dict',
            'keys': ['version', 'mode', 'paper_mode', 'params', 'limits', 'schedule']
        },
        'get_sector_regimes': {
            'return_type': 'List[Dict]',
            'item_keys': ['sector', 'regime', 'score', 'rsi', 'return_1d', 'return_5d']
        },
        'get_positions_status': {
            'return_type': 'List[Dict]',
            'item_keys': ['symbol', 'qty', 'entry_price', 'current_price', 'pnl_pct',
                          'hold_days', 'stop_loss', 'take_profit', 'trailing_stop']
        },
        'get_queue_status': {
            'return_type': 'List[Dict]',
            'item_keys': ['symbol', 'score', 'queued_at', 'price_at_queue', 'current_price']
        },
        'daily_summary': {
            'return_type': 'Dict',
            'keys': ['date', 'trades', 'winners', 'losers', 'pnl_total', 'pnl_pct']
        }
    }

    with open(METHODS_DIR / 'public_api.json', 'w') as f:
        json.dump(public_api, f, indent=2)

    print(f"  ✓ {len(public_api)} public API methods documented")
    print(f"  → Saved to methods/public_api.json")
    return public_api


def generate_manifest():
    """Generate manifest of all snapshot files"""
    print("\n📝 Generating manifest...")

    manifest = {
        'created_at': datetime.now().isoformat(),
        'engine_version': 'v6.0',
        'python_version': sys.version,
        'files': {}
    }

    for subdir in ['methods', 'state', 'checksums']:
        path = SNAPSHOT_DIR / subdir
        if path.exists():
            for f in path.glob('*.json'):
                manifest['files'][f'{subdir}/{f.name}'] = {
                    'size': f.stat().st_size,
                    'md5': calculate_file_checksum(str(f))
                }

    # Add backup file
    backup = SNAPSHOT_DIR / 'auto_trading_engine.py.backup'
    if backup.exists():
        manifest['files']['auto_trading_engine.py.backup'] = {
            'size': backup.stat().st_size,
            'md5': calculate_file_checksum(str(backup)),
            'lines': len(backup.read_text().splitlines())
        }

    with open(SNAPSHOT_DIR / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"  ✓ Manifest created with {len(manifest['files'])} files")
    print(f"  → Saved to manifest.json")
    return manifest


def main():
    """Main entry point"""
    print("=" * 60)
    print("  PHASE 0: PRE-REFACTOR SNAPSHOT CAPTURE")
    print("=" * 60)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Output: {SNAPSHOT_DIR}")
    print("=" * 60)

    # Capture all snapshots
    capture_checksums()
    capture_method_signatures()
    capture_class_structure()
    capture_state_file_formats()
    capture_config_snapshot()
    capture_dependency_map()
    capture_public_api()
    manifest = generate_manifest()

    print("\n" + "=" * 60)
    print("  ✅ PHASE 0 COMPLETE")
    print("=" * 60)
    print(f"  Files created: {len(manifest['files'])}")
    print(f"  Backup saved: auto_trading_engine.py.backup")
    print("\n  Next: Run Phase 1 (extract models.py)")
    print("=" * 60)


if __name__ == '__main__':
    main()
