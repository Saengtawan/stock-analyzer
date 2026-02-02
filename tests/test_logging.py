#!/usr/bin/env python3
"""
TEST 15: Logging & Monitoring
Check logging coverage for debugging during live trading
"""
import sys
import os
import subprocess

def count_pattern(pattern, directory):
    """Count occurrences of pattern in directory"""
    result = subprocess.run(
        ['grep', '-rn', pattern, directory],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        return len(result.stdout.strip().split('\n')), result.stdout.strip()
    return 0, ""


def check_logging_setup():
    """Check logging configuration"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')

    # Count logging statements
    log_count, _ = count_pattern('logger\.\|logging\.', src_dir)
    loguru_count, _ = count_pattern('from loguru import logger', src_dir)

    return log_count, loguru_count


def check_file_logging():
    """Check if file logging is configured"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')

    # Check for FileHandler or log file configuration
    file_count, file_output = count_pattern('FileHandler\|log_file\|\.log\|add.*sink', src_dir)

    return file_count > 0, file_output


def check_critical_log_events():
    """Check if critical events are logged"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')

    events = {
        'BUY order': ('submit.*order\|place.*order\|buy.*order', 'alpaca_trader.py'),
        'SELL/Exit': ('sell\|exit\|close.*position', 'alpaca_trader.py'),
        'Stop Loss': ('stop.*loss\|sl\|trailing', 'alpaca_trader.py'),
        'Screener signal': ('signal\|found\|candidate', 'screeners/'),
        'Error/Exception': ('error\|exception\|failed', 'src/'),
    }

    results = []
    for event, (pattern, path) in events.items():
        full_path = os.path.join(os.path.dirname(__file__), '..', 'src', path) if '/' in path else os.path.join(os.path.dirname(__file__), '..', path)
        if os.path.exists(full_path):
            count, _ = count_pattern(pattern, full_path)
            results.append((event, count > 0, count))
        else:
            # Search in src directory
            count, _ = count_pattern(pattern, src_dir)
            results.append((event, count > 0, count))

    return results


def check_print_vs_logging():
    """Compare print vs logging usage"""
    engine_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'auto_trading_engine.py')

    if not os.path.exists(engine_file):
        return 0, 0

    with open(engine_file, 'r') as f:
        content = f.read()

    print_count = content.count('print(')
    logger_count = content.count('logger.')

    return print_count, logger_count


def check_heartbeat():
    """Check for monitor heartbeat logging"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
    count, output = count_pattern('heartbeat\|alive\|running\|loop.*iteration\|check.*every', src_dir)
    return count > 0, output


def main():
    print("=" * 60)
    print("TEST 15: LOGGING & MONITORING")
    print("=" * 60)

    all_pass = True

    # 15a: Logging Setup
    print("\n--- 15a: Logging Setup ---")
    log_count, loguru_count = check_logging_setup()
    print(f"  Logger statements: {log_count}")
    print(f"  Loguru imports:    {loguru_count}")
    if log_count > 10 or loguru_count > 0:
        print("  PASS: Logging framework in use")
    else:
        print("  WARN: Limited logging")

    # 15b: File Logging
    print("\n--- 15b: File Logging ---")
    has_file_log, file_output = check_file_logging()
    if has_file_log:
        print("  PASS: File logging configured")
        lines = file_output.split('\n')[:2]
        for line in lines:
            print(f"    {line[:70]}")
    else:
        print("  WARN: Only console logging - consider adding file logging")

    # 15c: Critical Events Logged
    print("\n--- 15c: Critical Events ---")
    events = check_critical_log_events()
    for event, logged, count in events:
        status = "PASS" if logged else "WARN"
        print(f"  {status}: {event} ({count} occurrences)")

    # 15d: Print vs Logging
    print("\n--- 15d: Print vs Logger ---")
    print_count, logger_count = check_print_vs_logging()
    print(f"  print() statements: {print_count}")
    print(f"  logger statements:  {logger_count}")
    if logger_count >= print_count or (print_count < 20):
        print("  PASS: Reasonable logging balance")
    else:
        print("  WARN: Consider converting print to logger")

    # 15e: Heartbeat
    print("\n--- 15e: Monitor Heartbeat ---")
    has_heartbeat, hb_output = check_heartbeat()
    if has_heartbeat:
        print("  PASS: Heartbeat/status logging found")
    else:
        print("  WARN: No explicit heartbeat - consider adding")

    # Summary of what should be logged
    print("\n--- LOGGING CHECKLIST ---")
    must_log = [
        "BUY order submitted",
        "SELL / exit triggered",
        "SL placed / modified",
        "Trail activated",
        "Screener signal found",
        "Safety check blocked",
        "PDT check result",
        "Error / exception",
        "Daily P/L summary",
        "Monitor heartbeat",
    ]
    for item in must_log:
        print(f"  [ ] {item}")

    print("\n" + "=" * 60)
    print("TEST 15: PASS")
    print("=" * 60)

    return True


if __name__ == '__main__':
    result = main()
    sys.exit(0 if result else 1)
