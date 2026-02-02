#!/usr/bin/env python3
"""
AUTO TRADING INTEGRATION TEST - Phase 5
Rapid Trader v3.9 Full System Test

Tests all components working together:
1. Alpaca Module - Connection, orders, positions
2. Trading Engine - Scan, execute, monitor
3. Safety System - All 6 layers
4. Web API - All endpoints

Run this before deploying to production!
"""

import sys
import os
import time
import requests

sys.path.insert(0, 'src')

# Credentials
API_KEY = "PK45CDQEE2WO7I7N4BH762VSMK"
SECRET_KEY = "DFDhSeYmnsxS2YpyAZLX1MLm9ndfmYr9XaUEiyn78SH1"

# Web API base URL
WEB_BASE = "http://localhost:5000"


class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, test_name):
        self.passed += 1
        print(f"  ✅ {test_name}")

    def fail(self, test_name, error=""):
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  ❌ {test_name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        status = "PASSED" if self.failed == 0 else "FAILED"
        return f"{self.name}: {self.passed}/{total} {status}"


def test_alpaca_module():
    """Test Alpaca Module (Phase 1)"""
    print("\n" + "=" * 60)
    print("TEST 1: ALPACA MODULE")
    print("=" * 60)

    result = TestResult("Alpaca Module")

    try:
        from alpaca_trader import AlpacaTrader

        trader = AlpacaTrader(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            paper=True
        )

        # Test 1.1: Connection
        try:
            account = trader.get_account()
            if account['status'] == 'ACTIVE':
                result.ok("API Connection")
            else:
                result.fail("API Connection", f"Status: {account['status']}")
        except Exception as e:
            result.fail("API Connection", str(e))

        # Test 1.2: Account info
        try:
            account = trader.get_account()
            if account['cash'] > 0:
                result.ok(f"Account Info (Cash: ${account['cash']:,.0f})")
            else:
                result.fail("Account Info", "No cash")
        except Exception as e:
            result.fail("Account Info", str(e))

        # Test 1.3: Market clock
        try:
            clock = trader.get_clock()
            result.ok(f"Market Clock (Open: {clock['is_open']})")
        except Exception as e:
            result.fail("Market Clock", str(e))

        # Test 1.4: Get positions
        try:
            positions = trader.get_positions()
            result.ok(f"Get Positions ({len(positions)} found)")
        except Exception as e:
            result.fail("Get Positions", str(e))

        # Test 1.5: Get orders
        try:
            orders = trader.get_orders(status='open')
            result.ok(f"Get Orders ({len(orders)} open)")
        except Exception as e:
            result.fail("Get Orders", str(e))

        # Test 1.6: Trailing calculation
        try:
            sl, active = trader.calculate_trailing_stop(100, 102, 2.0, 70)
            expected_sl = 101.40  # 100 + (2 * 0.70)
            if abs(sl - expected_sl) < 0.01 and active:
                result.ok(f"Trailing Calculation (SL=${sl:.2f})")
            else:
                result.fail("Trailing Calculation", f"Expected ${expected_sl}, got ${sl}")
        except Exception as e:
            result.fail("Trailing Calculation", str(e))

    except Exception as e:
        result.fail("Module Import", str(e))

    return result


def test_trading_engine():
    """Test Trading Engine (Phase 2)"""
    print("\n" + "=" * 60)
    print("TEST 2: TRADING ENGINE")
    print("=" * 60)

    result = TestResult("Trading Engine")

    try:
        from auto_trading_engine import AutoTradingEngine

        engine = AutoTradingEngine(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            paper=True,
            auto_start=False
        )

        # Test 2.1: Engine initialization
        try:
            status = engine.get_status()
            if status['state'] == 'sleeping':
                result.ok("Engine Initialization")
            else:
                result.fail("Engine Initialization", f"State: {status['state']}")
        except Exception as e:
            result.fail("Engine Initialization", str(e))

        # Test 2.2: Screener integration
        try:
            if engine.screener:
                result.ok("Screener Integration")
            else:
                result.fail("Screener Integration", "Screener not loaded")
        except Exception as e:
            result.fail("Screener Integration", str(e))

        # Test 2.3: Safety system integration
        try:
            if engine.safety:
                result.ok("Safety System Integration")
            else:
                result.fail("Safety System Integration", "Safety not loaded")
        except Exception as e:
            result.fail("Safety System Integration", str(e))

        # Test 2.4: Position sync
        try:
            positions = engine.get_positions_status()
            result.ok(f"Position Sync ({len(positions)} positions)")
        except Exception as e:
            result.fail("Position Sync", str(e))

        # Test 2.5: Scan (may take time)
        print("  ⏳ Testing scan (this may take 30-60 seconds)...")
        try:
            signals = engine.scan_for_signals()
            result.ok(f"Signal Scan ({len(signals)} signals)")
        except Exception as e:
            result.fail("Signal Scan", str(e))

        # Test 2.6: Start/Stop
        try:
            engine.start()
            time.sleep(1)
            if engine.running:
                result.ok("Engine Start")
            else:
                result.fail("Engine Start", "Not running after start")
            engine.stop()
            time.sleep(1)
            if not engine.running:
                result.ok("Engine Stop")
            else:
                result.fail("Engine Stop", "Still running after stop")
        except Exception as e:
            result.fail("Engine Start/Stop", str(e))

    except Exception as e:
        result.fail("Module Import", str(e))

    return result


def test_safety_system():
    """Test Safety System (Phase 3)"""
    print("\n" + "=" * 60)
    print("TEST 3: SAFETY SYSTEM")
    print("=" * 60)

    result = TestResult("Safety System")

    try:
        from alpaca_trader import AlpacaTrader
        from trading_safety import TradingSafetySystem, SafetyStatus

        trader = AlpacaTrader(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            paper=True
        )
        safety = TradingSafetySystem(trader)

        # Test 3.1: Health check
        try:
            report = safety.run_health_check()
            result.ok(f"Health Check ({report.overall_status.value})")
        except Exception as e:
            result.fail("Health Check", str(e))

        # Test 3.2: SL protection check
        try:
            check = safety.check_sl_protection()
            result.ok(f"SL Protection Check ({check.status.value})")
        except Exception as e:
            result.fail("SL Protection Check", str(e))

        # Test 3.3: Daily loss check
        try:
            check = safety.check_daily_loss()
            result.ok(f"Daily Loss Check ({check.message})")
        except Exception as e:
            result.fail("Daily Loss Check", str(e))

        # Test 3.4: Position count check
        try:
            check = safety.check_position_count()
            result.ok(f"Position Count Check ({check.message})")
        except Exception as e:
            result.fail("Position Count Check", str(e))

        # Test 3.5: Can open position
        try:
            can_trade, reason = safety.can_open_new_position()
            if can_trade:
                result.ok("Can Open Position (YES)")
            else:
                result.ok(f"Can Open Position (NO: {reason})")
        except Exception as e:
            result.fail("Can Open Position", str(e))

        # Test 3.6: Emergency stop toggle
        try:
            safety.activate_emergency_stop("Test")
            if safety.emergency_stop:
                result.ok("Emergency Stop Activate")
            else:
                result.fail("Emergency Stop Activate", "Not activated")

            safety.deactivate_emergency_stop()
            if not safety.emergency_stop:
                result.ok("Emergency Stop Deactivate")
            else:
                result.fail("Emergency Stop Deactivate", "Not deactivated")
        except Exception as e:
            result.fail("Emergency Stop Toggle", str(e))

    except Exception as e:
        result.fail("Module Import", str(e))

    return result


def test_web_api():
    """Test Web API (Phase 4)"""
    print("\n" + "=" * 60)
    print("TEST 4: WEB API")
    print("=" * 60)

    result = TestResult("Web API")

    # Test 4.1: Server running
    try:
        r = requests.get(f"{WEB_BASE}/rapid", timeout=5)
        if r.status_code == 200:
            result.ok("Web Server Running")
        else:
            result.fail("Web Server Running", f"Status: {r.status_code}")
    except Exception as e:
        result.fail("Web Server Running", str(e))
        return result  # Can't continue without server

    # Test 4.2: Auto status API
    try:
        r = requests.get(f"{WEB_BASE}/api/auto/status", timeout=10)
        data = r.json()
        if 'state' in data and 'safety' in data:
            result.ok(f"GET /api/auto/status ({data['state']})")
        else:
            result.fail("GET /api/auto/status", "Invalid response")
    except Exception as e:
        result.fail("GET /api/auto/status", str(e))

    # Test 4.3: Auto positions API
    try:
        r = requests.get(f"{WEB_BASE}/api/auto/positions", timeout=10)
        data = r.json()
        if 'positions' in data and 'account' in data:
            result.ok(f"GET /api/auto/positions ({len(data['positions'])} positions)")
        else:
            result.fail("GET /api/auto/positions", "Invalid response")
    except Exception as e:
        result.fail("GET /api/auto/positions", str(e))

    # Test 4.4: Auto start API
    try:
        r = requests.post(f"{WEB_BASE}/api/auto/start", timeout=10)
        data = r.json()
        if 'running' in data:
            result.ok(f"POST /api/auto/start (running={data['running']})")
        else:
            result.fail("POST /api/auto/start", "Invalid response")
    except Exception as e:
        result.fail("POST /api/auto/start", str(e))

    # Test 4.5: Auto stop API
    try:
        r = requests.post(f"{WEB_BASE}/api/auto/stop", timeout=10)
        data = r.json()
        if 'running' in data:
            result.ok(f"POST /api/auto/stop (running={data['running']})")
        else:
            result.fail("POST /api/auto/stop", "Invalid response")
    except Exception as e:
        result.fail("POST /api/auto/stop", str(e))

    # Test 4.6: Rapid signals API (existing)
    try:
        r = requests.get(f"{WEB_BASE}/api/rapid/signals", timeout=60)
        data = r.json()
        if 'signals' in data:
            result.ok(f"GET /api/rapid/signals ({len(data['signals'])} signals)")
        else:
            result.fail("GET /api/rapid/signals", data.get('error', 'Invalid response'))
    except Exception as e:
        result.fail("GET /api/rapid/signals", str(e))

    return result


def test_full_flow():
    """Test full trading flow (simulation)"""
    print("\n" + "=" * 60)
    print("TEST 5: FULL FLOW SIMULATION")
    print("=" * 60)

    result = TestResult("Full Flow")

    try:
        from auto_trading_engine import AutoTradingEngine

        engine = AutoTradingEngine(
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            paper=True,
            auto_start=False
        )

        # Test 5.1: Check market status
        try:
            is_open = engine.trader.is_market_open()
            result.ok(f"Market Status Check (Open: {is_open})")
        except Exception as e:
            result.fail("Market Status Check", str(e))

        # Test 5.2: Safety pre-check
        try:
            can_trade, reason = engine.safety.can_open_new_position()
            result.ok(f"Safety Pre-check (Can trade: {can_trade})")
        except Exception as e:
            result.fail("Safety Pre-check", str(e))

        # Test 5.3: Scan for signals
        print("  ⏳ Scanning for signals...")
        try:
            signals = engine.scan_for_signals()
            if len(signals) > 0:
                result.ok(f"Found {len(signals)} signals")
                # Show top signal
                top = signals[0]
                print(f"      Top: {top.symbol} (Score: {getattr(top, 'score', 'N/A')})")
            else:
                result.ok("No signals found (normal on weekends)")
        except Exception as e:
            result.fail("Signal Scan", str(e))

        # Test 5.4: Monitor loop (dry run)
        try:
            engine.monitor_positions()
            result.ok("Monitor Loop (dry run)")
        except Exception as e:
            result.fail("Monitor Loop", str(e))

        # Test 5.5: Daily summary
        try:
            summary = engine.daily_summary()
            result.ok(f"Daily Summary Generated")
        except Exception as e:
            result.fail("Daily Summary", str(e))

        # Note: Not testing actual order execution to avoid real trades
        print("\n  ℹ️  Order execution tests skipped (requires market open)")
        print("      Run test_alpaca_orders.py during market hours")

    except Exception as e:
        result.fail("Flow Setup", str(e))

    return result


def main():
    """Run all integration tests"""
    print("=" * 60)
    print("RAPID TRADER v3.9 - INTEGRATION TEST")
    print("=" * 60)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: Paper Trading")

    results = []

    # Run all test suites
    results.append(test_alpaca_module())
    results.append(test_trading_engine())
    results.append(test_safety_system())
    results.append(test_web_api())
    results.append(test_full_flow())

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    total_passed = 0
    total_failed = 0

    for r in results:
        print(f"  {r.summary()}")
        total_passed += r.passed
        total_failed += r.failed

    print("-" * 60)
    print(f"  TOTAL: {total_passed}/{total_passed + total_failed}")

    if total_failed == 0:
        print("\n✅ ALL TESTS PASSED - Ready for production!")
    else:
        print(f"\n❌ {total_failed} TESTS FAILED")
        print("\nFailed tests:")
        for r in results:
            for err in r.errors:
                print(f"  - {r.name}: {err}")

    print("=" * 60)

    return total_failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
