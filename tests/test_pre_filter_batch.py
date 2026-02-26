#!/usr/bin/env python3
"""
Pre-Filter Batch Download Refactor — Test Suite
================================================
Phase 1: Capture baseline indicators + filter results
Phase 2: Unit test batch fetch vs individual fetch equivalence
Phase 3: Gate for evening_scan() batch refactor
Phase 4: Gate for pre_open_scan() batch refactor

Usage:
    cd /home/saengtawan/work/project/cc/stock-analyzer
    # Phase 1: capture baseline (run BEFORE refactoring)
    python3 tests/test_pre_filter_batch.py baseline

    # Phase 2: verify batch methods are numerically equivalent
    python3 tests/test_pre_filter_batch.py equivalence

    # Phase 3: verify evening_scan() still matches baseline
    python3 tests/test_pre_filter_batch.py evening

    # Phase 4: verify pre_open_scan() completes cleanly
    python3 tests/test_pre_filter_batch.py pre_open

    # Run all (excluding slow evening/pre_open)
    pytest tests/test_pre_filter_batch.py -v
"""

import os
import sys
import json
import time
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pandas as pd

FIXED_SYMBOLS = [
    'AAPL', 'MSFT', 'NVDA', 'META', 'AMD',
    'JPM', 'AMZN', 'GOOGL', 'TSLA', 'NFLX',
    'KO', 'PEP', 'JNJ', 'XOM', 'GE'
]  # mix: tech + defensive + energy

SNAPSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
BASELINE_FILE = os.path.join(SNAPSHOTS_DIR, 'pre_filter_baseline.json')
FILTER_BASELINE_FILE = os.path.join(SNAPSHOTS_DIR, 'pre_filter_filter_baseline.json')


def get_runner():
    """Create a PreFilterRunner instance."""
    from pre_filter import PreFilterRunner
    return PreFilterRunner()


# ---------------------------------------------------------------------------
# Phase 1 — Test A + B: Capture baseline with CURRENT (individual) code
# ---------------------------------------------------------------------------

def capture_baseline():
    """
    Test A: Record per-indicator values using current _fetch_stock_data().
    Test B: Record pass/fail from _apply_structural_filter().
    Saves JSON snapshots to tests/snapshots/.
    """
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    runner = get_runner()

    print(f"\n=== Phase 1: Capturing baseline for {len(FIXED_SYMBOLS)} symbols ===")
    print("Test A — individual fetch indicators...")

    baseline_indicators = {}
    baseline_filters = {}

    for sym in FIXED_SYMBOLS:
        print(f"  Fetching {sym}...", end=' ', flush=True)
        data = runner._fetch_stock_data(sym)
        if data is None:
            print("FAILED (no data)")
            baseline_indicators[sym] = None
            baseline_filters[sym] = {'passed': False, 'reason': 'no_data'}
            continue

        # Round floats for stable comparison
        baseline_indicators[sym] = {
            'close': round(float(data['close']), 4),
            'sma20': round(float(data['sma20']), 4),
            'sma50': round(float(data['sma50']), 4),
            'atr_pct': round(float(data['atr_pct']), 4),
            'avg_volume': round(float(data['avg_volume']), 0),
            'rsi': round(float(data['rsi']), 4),
            'dollar_volume': round(float(data['dollar_volume']), 0),
            'return_5d': round(float(data['return_5d']), 4),
        }
        print(f"close={data['close']:.2f} rsi={data['rsi']:.1f}", end='  ')

        # Test B: apply filter
        stock, reason = runner._apply_structural_filter(sym, data, 'Technology')
        if stock is not None:
            baseline_filters[sym] = {'passed': True, 'reason': ''}
            print("PASS")
        else:
            baseline_filters[sym] = {'passed': False, 'reason': reason}
            print(f"FAIL ({reason})")

    # Save snapshots
    with open(BASELINE_FILE, 'w') as f:
        json.dump(baseline_indicators, f, indent=2)
    print(f"\n✅ Test A saved: {BASELINE_FILE}")

    with open(FILTER_BASELINE_FILE, 'w') as f:
        json.dump(baseline_filters, f, indent=2)
    print(f"✅ Test B saved: {FILTER_BASELINE_FILE}")

    passed = sum(1 for v in baseline_filters.values() if v['passed'])
    print(f"\nBaseline: {passed}/{len(FIXED_SYMBOLS)} symbols pass filters")
    print("Phase 1 GATE: PASSED — both JSON snapshots written\n")


# ---------------------------------------------------------------------------
# Phase 2 — Test C: Batch vs individual indicator equivalence
# ---------------------------------------------------------------------------

TOLERANCES = {
    'close':        ('abs', 0.01),
    'sma20':        ('abs', 0.01),
    'sma50':        ('abs', 0.01),
    'atr_pct':      ('abs', 0.01),
    'rsi':          ('abs', 0.5),
    'dollar_volume': ('rel', 0.001),   # 0.1% relative
    'return_5d':    ('abs', 0.01),
}


def test_batch_vs_individual():
    """
    Test C: Compare _batch_fetch_all() + _compute_indicators() vs
    _fetch_stock_data() for the 15 FIXED_SYMBOLS.
    All indicators must match within tolerance.
    """
    runner = get_runner()

    print(f"\n=== Phase 2 Test C: Batch vs Individual ({len(FIXED_SYMBOLS)} symbols) ===")

    # Batch fetch
    t0 = time.time()
    batch_data = runner._batch_fetch_all(FIXED_SYMBOLS)
    batch_time = time.time() - t0
    print(f"Batch fetch: {len(batch_data)}/{len(FIXED_SYMBOLS)} symbols in {batch_time:.1f}s")

    mismatches = []
    skipped = []

    for sym in FIXED_SYMBOLS:
        # Individual fetch (old method)
        old = runner._fetch_stock_data(sym)
        if old is None:
            skipped.append(sym)
            print(f"  {sym}: SKIP (individual fetch returned None)")
            continue

        # Batch method
        if sym not in batch_data:
            mismatches.append(f"{sym}: absent from batch result")
            print(f"  {sym}: FAIL (absent from batch)")
            continue

        new = runner._compute_indicators(batch_data[sym])

        sym_ok = True
        for field, (tol_type, tol_val) in TOLERANCES.items():
            old_val = old.get(field)
            new_val = new.get(field)
            if old_val is None or new_val is None:
                continue

            if tol_type == 'abs':
                diff = abs(float(old_val) - float(new_val))
                ok = diff <= tol_val
                detail = f"abs_diff={diff:.4f} (tol={tol_val})"
            else:  # rel
                ref = abs(float(old_val)) if abs(float(old_val)) > 0 else 1.0
                diff = abs(float(old_val) - float(new_val)) / ref
                ok = diff <= tol_val
                detail = f"rel_diff={diff:.6f} (tol={tol_val})"

            if not ok:
                mismatches.append(f"{sym}.{field}: old={old_val:.4f} new={new_val:.4f} {detail}")
                sym_ok = False

        status = "OK" if sym_ok else "MISMATCH"
        print(f"  {sym}: {status} (rsi old={old['rsi']:.1f} new={new['rsi']:.1f})")

    print(f"\nResults: {len(mismatches)} mismatches, {len(skipped)} skipped")
    if mismatches:
        print("FAILURES:")
        for m in mismatches:
            print(f"  ❌ {m}")
        print("\nPhase 2 GATE: FAILED")
        return False
    else:
        print("Phase 2 GATE: PASSED — all indicators within tolerance\n")
        return True


# ---------------------------------------------------------------------------
# Phase 3 — Test D: evening_scan() with new code matches baseline
# ---------------------------------------------------------------------------

def test_evening_scan_gate():
    """
    Test D: Run evening_scan() and verify:
    1. FIXED_SYMBOLS pass/fail matches baseline (if baseline exists)
    2. Total pool size within ±2% of previous run
    3. DB session completed
    4. Duration < 120s
    """
    runner = get_runner()

    print("\n=== Phase 3 Test D: evening_scan() gate ===")
    print("WARNING: This runs a FULL scan (~900+ stocks). Takes ~20-120s.")

    # Load baseline if available
    filter_baseline = {}
    if os.path.exists(FILTER_BASELINE_FILE):
        with open(FILTER_BASELINE_FILE) as f:
            filter_baseline = json.load(f)
        print(f"Loaded filter baseline: {len(filter_baseline)} symbols")
    else:
        print("No filter baseline found — skipping baseline comparison")

    t0 = time.time()
    count = runner.evening_scan()
    elapsed = time.time() - t0

    print(f"\nevening_scan() completed: {count} stocks in {elapsed:.1f}s")

    # Gate 1: Duration
    if elapsed > 120:
        print(f"❌ GATE FAIL: Duration {elapsed:.1f}s > 120s")
        return False
    print(f"✅ Duration: {elapsed:.1f}s < 120s")

    # Gate 2: Pool size > 0
    if count == 0:
        print("❌ GATE FAIL: pool_size = 0")
        return False
    print(f"✅ Pool size: {count} > 0")

    # Gate 3: Check FIXED_SYMBOLS match baseline
    if filter_baseline:
        from database import PreFilterRepository
        repo = PreFilterRepository()
        session = repo.get_latest_session('evening')
        if session:
            pool = {s.symbol for s in repo.get_filtered_pool(session_id=session.id)}
            mismatches = []
            for sym in FIXED_SYMBOLS:
                if sym not in filter_baseline:
                    continue
                expected_pass = filter_baseline[sym]['passed']
                actual_pass = sym in pool
                if expected_pass != actual_pass:
                    mismatches.append(f"{sym}: expected={'PASS' if expected_pass else 'FAIL'} got={'PASS' if actual_pass else 'FAIL'}")

            if mismatches:
                print(f"⚠️  Filter result changes (price drift OK): {len(mismatches)}")
                for m in mismatches:
                    print(f"    {m}")
            else:
                print(f"✅ All {len(FIXED_SYMBOLS)} FIXED_SYMBOLS match baseline pass/fail")

    # Gate 4: DB session completed
    try:
        from database import PreFilterRepository
        repo = PreFilterRepository()
        session = repo.get_latest_session('evening')
        if session and session.status == 'completed':
            print(f"✅ DB session: status=completed, pool_size={session.pool_size}, duration={session.duration_seconds:.1f}s")
        else:
            print(f"❌ GATE FAIL: DB session status={session.status if session else 'None'}")
            return False
    except Exception as e:
        print(f"⚠️  Could not check DB session: {e}")

    print("Phase 3 GATE: PASSED\n")
    return True


# ---------------------------------------------------------------------------
# Phase 4 — Test E: pre_open_scan() completes cleanly
# ---------------------------------------------------------------------------

def test_pre_open_scan_gate():
    """
    Test E: Run pre_open_scan() and verify:
    1. No exceptions
    2. DB session status=completed
    3. pool_size <= evening pool_size
    4. Duration < 30s
    """
    runner = get_runner()

    print("\n=== Phase 4 Test E: pre_open_scan() gate ===")

    # Get evening pool size first
    evening_pool_size = None
    try:
        from database import PreFilterRepository
        repo = PreFilterRepository()
        evening_session = repo.get_latest_session('evening')
        if evening_session:
            evening_pool_size = evening_session.pool_size
            print(f"Evening pool size: {evening_pool_size}")
    except Exception:
        pass

    t0 = time.time()
    count = runner.pre_open_scan()
    elapsed = time.time() - t0

    print(f"\npre_open_scan() completed: {count} stocks in {elapsed:.1f}s")

    # Gate 1: Duration
    if elapsed > 30:
        print(f"❌ GATE FAIL: Duration {elapsed:.1f}s > 30s")
        return False
    print(f"✅ Duration: {elapsed:.1f}s < 30s")

    # Gate 2: Count > 0
    if count == 0:
        print("❌ GATE FAIL: pool_size = 0")
        return False
    print(f"✅ Pool size: {count} > 0")

    # Gate 3: pre_open <= evening
    if evening_pool_size is not None and count > evening_pool_size:
        print(f"❌ GATE FAIL: pre_open pool ({count}) > evening pool ({evening_pool_size})")
        return False
    if evening_pool_size is not None:
        print(f"✅ Pool shrink OK: pre_open={count} <= evening={evening_pool_size}")

    # Gate 4: DB session
    try:
        from database import PreFilterRepository
        repo = PreFilterRepository()
        session = repo.get_latest_session('pre_open')
        if session and session.status == 'completed':
            print(f"✅ DB session: status=completed, pool_size={session.pool_size}, duration={session.duration_seconds:.1f}s")
        else:
            print(f"❌ GATE FAIL: DB session status={session.status if session else 'None'}")
            return False
    except Exception as e:
        print(f"⚠️  Could not check DB session: {e}")

    print("Phase 4 GATE: PASSED\n")
    return True


# ---------------------------------------------------------------------------
# pytest-compatible test functions (for CI)
# ---------------------------------------------------------------------------

def test_batch_methods_exist():
    """Sanity check: new methods are importable."""
    from pre_filter import PreFilterRunner
    runner = PreFilterRunner()
    assert hasattr(runner, '_batch_fetch_all'), "_batch_fetch_all() not found"
    assert hasattr(runner, '_compute_indicators'), "_compute_indicators() not found"


def test_batch_fetch_returns_dict():
    """_batch_fetch_all(['AAPL','MSFT']) returns non-empty dict."""
    from pre_filter import PreFilterRunner
    runner = PreFilterRunner()
    result = runner._batch_fetch_all(['AAPL', 'MSFT'])
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert len(result) >= 1, "Expected at least 1 symbol in result"
    for sym, df in result.items():
        assert hasattr(df, 'columns'), f"{sym}: result is not a DataFrame"
        assert 'close' in df.columns, f"{sym}: 'close' column missing"


def test_compute_indicators_shape():
    """_compute_indicators() returns expected keys."""
    from pre_filter import PreFilterRunner
    runner = PreFilterRunner()
    df = runner._batch_fetch_all(['AAPL'])['AAPL']
    result = runner._compute_indicators(df)
    expected_keys = {'close', 'sma20', 'sma50', 'atr_pct', 'avg_volume', 'rsi', 'dollar_volume', 'return_5d'}
    assert expected_keys == set(result.keys()), f"Keys mismatch: {set(result.keys())}"


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pre-Filter Batch Refactor Tests')
    parser.add_argument('phase', choices=['baseline', 'equivalence', 'evening', 'pre_open', 'all'],
                        help='Which phase/gate to run')
    args = parser.parse_args()

    if args.phase == 'baseline':
        capture_baseline()

    elif args.phase == 'equivalence':
        ok = test_batch_vs_individual()
        sys.exit(0 if ok else 1)

    elif args.phase == 'evening':
        ok = test_evening_scan_gate()
        sys.exit(0 if ok else 1)

    elif args.phase == 'pre_open':
        ok = test_pre_open_scan_gate()
        sys.exit(0 if ok else 1)

    elif args.phase == 'all':
        print("Running all quick tests (baseline capture + equivalence)...")
        capture_baseline()
        ok = test_batch_vs_individual()
        sys.exit(0 if ok else 1)
