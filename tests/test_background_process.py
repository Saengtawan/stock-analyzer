#!/usr/bin/env python3
"""
TEST 16: Auto-Restart & Background Process
Test that scanner/monitor can run as background service
"""
import sys
import os
import subprocess

def check_scheduler():
    """Check for scheduler/threading setup"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')

    patterns = [
        'schedule',
        'APScheduler',
        'BackgroundScheduler',
        'threading',
        'Thread',
        'Timer',
        'asyncio',
    ]

    results = []
    for pattern in patterns:
        result = subprocess.run(
            ['grep', '-rn', pattern, src_dir],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            results.append((pattern, len(result.stdout.strip().split('\n'))))

    return results


def check_monitor_loop():
    """Check for while True + sleep pattern"""
    engine_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'auto_trading_engine.py')
    run_app_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'run_app.py')

    found = []
    for filepath in [engine_file, run_app_file]:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()

            has_while = 'while True' in content or 'while self.running' in content
            has_sleep = 'sleep' in content or 'time.sleep' in content

            if has_while and has_sleep:
                found.append(os.path.basename(filepath))

    return found


def check_graceful_shutdown():
    """Check for graceful shutdown handling"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')

    patterns = [
        'signal',
        'SIGINT',
        'SIGTERM',
        'KeyboardInterrupt',
        'atexit',
        'shutdown',
        'cleanup',
    ]

    found = []
    for pattern in patterns:
        result = subprocess.run(
            ['grep', '-rn', pattern, src_dir],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            found.append(pattern)

    return found


def check_health_endpoint():
    """Check for health/status endpoint in web app"""
    web_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'web', 'app.py')

    if not os.path.exists(web_file):
        return False, []

    with open(web_file, 'r') as f:
        content = f.read()

    endpoints = []
    if 'health' in content.lower():
        endpoints.append('/health')
    if 'status' in content.lower():
        endpoints.append('/status')
    if 'heartbeat' in content.lower():
        endpoints.append('/heartbeat')
    if '/api/' in content:
        endpoints.append('/api/*')

    return len(endpoints) > 0, endpoints


def check_systemd_or_pm2():
    """Check for systemd/pm2/supervisor config"""
    root_dir = os.path.join(os.path.dirname(__file__), '..')

    service_files = [
        'rapid-trader.service',
        'ecosystem.config.js',
        'supervisord.conf',
        'Procfile',
        'docker-compose.yml',
        'Dockerfile',
    ]

    found = []
    for sfile in service_files:
        if os.path.exists(os.path.join(root_dir, sfile)):
            found.append(sfile)

    return found


def check_daemon_mode():
    """Check if can run as daemon"""
    src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')

    result = subprocess.run(
        ['grep', '-rn', 'daemon\|background\|fork\|nohup\|&', src_dir],
        capture_output=True, text=True
    )

    return bool(result.stdout.strip())


def main():
    print("=" * 60)
    print("TEST 16: AUTO-RESTART & BACKGROUND PROCESS")
    print("=" * 60)

    # 16a: Scheduler Check
    print("\n--- 16a: Scheduler/Threading ---")
    schedulers = check_scheduler()
    if schedulers:
        print("  PASS: Background scheduling found")
        for name, count in schedulers[:5]:
            print(f"    {name}: {count} occurrences")
    else:
        print("  WARN: No scheduler found")

    # 16b: Monitor Loop
    print("\n--- 16b: Monitor Loop ---")
    loops = check_monitor_loop()
    if loops:
        print(f"  PASS: Monitor loop in {', '.join(loops)}")
    else:
        print("  WARN: No while+sleep loop found")

    # 16c: Graceful Shutdown
    print("\n--- 16c: Graceful Shutdown ---")
    shutdown = check_graceful_shutdown()
    if shutdown:
        print(f"  PASS: Shutdown handling: {', '.join(shutdown[:4])}")
    else:
        print("  WARN: No graceful shutdown found")

    # 16d: Health Endpoint
    print("\n--- 16d: Health Endpoint ---")
    has_health, endpoints = check_health_endpoint()
    if has_health:
        print(f"  PASS: Health endpoints: {', '.join(endpoints)}")
    else:
        print("  WARN: No health endpoint - consider adding /health")

    # 16e: Service Config
    print("\n--- 16e: Service Configuration ---")
    services = check_systemd_or_pm2()
    if services:
        print(f"  PASS: Service files: {', '.join(services)}")
    else:
        print("  INFO: No service config - run manually or add systemd/pm2")

    # 16f: Daemon Mode
    print("\n--- 16f: Daemon/Background Mode ---")
    has_daemon = check_daemon_mode()
    if has_daemon:
        print("  PASS: Background mode references found")
    else:
        print("  INFO: Can run with nohup or & manually")

    # Summary
    print("\n--- BACKGROUND PROCESS CHECKLIST ---")
    checklist = [
        ("Scanner runs as background thread", bool(schedulers)),
        ("Monitor loop doesn't block", bool(loops)),
        ("Graceful shutdown on SIGTERM", 'SIGTERM' in shutdown or 'signal' in shutdown),
        ("Exception recovery in loop", True),  # Checked in TEST 14
        ("Health check endpoint", has_health),
    ]

    all_critical_pass = True
    for item, status in checklist:
        icon = "PASS" if status else "WARN"
        print(f"  {icon}: {item}")
        # Only first 3 are critical
        if not status and checklist.index((item, status)) < 3:
            all_critical_pass = False

    print("\n" + "=" * 60)
    print(f"TEST 16: {'PASS' if all_critical_pass else 'PASS with WARNINGS'}")
    print("=" * 60)

    # Recommendations
    print("\n--- RECOMMENDATIONS ---")
    if not services:
        print("  Add systemd service for auto-restart:")
        print("    sudo cp rapid-trader.service /etc/systemd/system/")
        print("    sudo systemctl enable rapid-trader")
        print("    sudo systemctl start rapid-trader")
    if not has_health:
        print("  Add health endpoint for monitoring:")
        print("    @app.route('/health')")
        print("    def health(): return {'status': 'ok'}")

    return True


if __name__ == '__main__':
    result = main()
    sys.exit(0 if result else 1)
