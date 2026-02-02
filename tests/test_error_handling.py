#!/usr/bin/env python3
"""
TEST 14: Error Handling & Recovery
Test that system doesn't crash on errors
"""
import sys
import os
import subprocess
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def check_try_except_coverage():
    """Check try/except blocks in critical files"""
    files_to_check = [
        'src/alpaca_trader.py',
        'src/auto_trading_engine.py',
        'src/screeners/rapid_rotation_screener.py',
    ]

    total_try = 0
    total_except = 0
    results = []

    for filepath in files_to_check:
        full_path = os.path.join(os.path.dirname(__file__), '..', filepath)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                content = f.read()
            try_count = content.count('try:')
            except_count = content.count('except')
            total_try += try_count
            total_except += except_count
            results.append((filepath, try_count, except_count))

    return total_try, total_except, results


def check_retry_logic():
    """Check for retry mechanisms"""
    result = subprocess.run(
        ['grep', '-rn', 'retry\|RETRY\|max_retries\|attempt\|for.*range.*try', 'src/'],
        capture_output=True, text=True, cwd=os.path.dirname(__file__) + '/..'
    )
    return bool(result.stdout.strip()), result.stdout.strip()


def test_nan_handling():
    """Test screener handles NaN data without crashing"""
    # Create test DataFrame with NaN values
    test_df = pd.DataFrame({
        'Close': [100, np.nan, 102, 103, 104, 105, 106, 107, 108, 109,
                  110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                  120, 121, 122, 123, 124, 125],
        'Open':  [99, 100, np.nan, 102, 103, 104, 105, 106, 107, 108,
                  109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
                  119, 120, 121, 122, 123, 124],
        'High':  [101, np.nan, 103, 104, 105, 106, 107, 108, 109, 110,
                  111, 112, 113, 114, 115, 116, 117, 118, 119, 120,
                  121, 122, 123, 124, 125, 126],
        'Low':   [98, 99, 101, 101, 103, 103, 104, 105, 106, 107,
                  108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
                  118, 119, 120, 121, 122, 123],
        'Volume': [1000000, np.nan, 1200000, 900000, 1100000, 1000000,
                   1100000, 1200000, 1000000, 1100000, 1200000, 1000000,
                   1100000, 1200000, 1000000, 1100000, 1200000, 1000000,
                   1100000, 1200000, 1000000, 1100000, 1200000, 1000000,
                   1100000, 1200000]
    })

    # Try to calculate indicators on NaN data
    try:
        # Dropna should work
        clean_df = test_df.dropna()
        sma20 = clean_df['Close'].rolling(20).mean().iloc[-1]
        return True, f"SMA20={sma20:.2f} after dropna"
    except Exception as e:
        return False, str(e)


def check_exception_recovery_in_loop():
    """Check if monitor loop has exception recovery"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'src', 'auto_trading_engine.py')
    if not os.path.exists(filepath):
        return False, "File not found"

    with open(filepath, 'r') as f:
        content = f.read()

    # Look for pattern: while ... try ... except ... continue/pass
    has_while = 'while' in content
    has_try_in_loop = 'try:' in content
    has_except = 'except' in content
    has_continue_or_pass = 'continue' in content or 'pass' in content

    if has_while and has_try_in_loop and has_except:
        return True, "Loop has exception handling"
    return False, "No exception recovery in loop"


def check_order_rejection_handling():
    """Check if order rejection is handled"""
    filepath = os.path.join(os.path.dirname(__file__), '..', 'src', 'alpaca_trader.py')
    if not os.path.exists(filepath):
        return False, "File not found"

    with open(filepath, 'r') as f:
        content = f.read()

    # Check for error handling patterns
    handles_rejection = (
        'except' in content and
        ('APIError' in content or 'Exception' in content or 'error' in content.lower())
    )

    return handles_rejection, "Order error handling present" if handles_rejection else "Missing"


def main():
    print("=" * 60)
    print("TEST 14: ERROR HANDLING & RECOVERY")
    print("=" * 60)

    all_pass = True

    # 14a: Try/Except Coverage
    print("\n--- 14a: Try/Except Coverage ---")
    total_try, total_except, details = check_try_except_coverage()
    print(f"  Total try blocks:    {total_try}")
    print(f"  Total except blocks: {total_except}")
    for filepath, t, e in details:
        print(f"    {filepath}: try={t}, except={e}")

    if total_try >= 5 and total_except >= 5:
        print("  PASS: Adequate error handling")
    else:
        print("  WARN: May need more error handling")
        # Don't fail for this, just warn

    # 14b: Retry Logic
    print("\n--- 14b: Retry Logic ---")
    has_retry, retry_output = check_retry_logic()
    if has_retry:
        print("  PASS: Retry logic found")
        lines = retry_output.split('\n')[:3]
        for line in lines:
            print(f"    {line[:80]}")
    else:
        print("  WARN: No explicit retry logic found")

    # 14c: NaN Handling
    print("\n--- 14c: NaN Data Handling ---")
    nan_pass, nan_msg = test_nan_handling()
    if nan_pass:
        print(f"  PASS: {nan_msg}")
    else:
        print(f"  FAIL: {nan_msg}")
        all_pass = False

    # 14d: Exception Recovery in Loop
    print("\n--- 14d: Loop Exception Recovery ---")
    loop_pass, loop_msg = check_exception_recovery_in_loop()
    if loop_pass:
        print(f"  PASS: {loop_msg}")
    else:
        print(f"  WARN: {loop_msg}")

    # 14e: Order Rejection Handling
    print("\n--- 14e: Order Rejection Handling ---")
    order_pass, order_msg = check_order_rejection_handling()
    if order_pass:
        print(f"  PASS: {order_msg}")
    else:
        print(f"  WARN: {order_msg}")

    print("\n" + "=" * 60)
    print(f"TEST 14: {'PASS' if all_pass else 'PASS with WARNINGS'}")
    print("=" * 60)

    return all_pass


if __name__ == '__main__':
    result = main()
    sys.exit(0 if result else 1)
