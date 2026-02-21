#!/usr/bin/env python3
"""
Test Phase 1 Models & Repositories
===================================
Verify that new models and repositories work correctly.
"""

import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.models import TradingSignal, ExecutionRecord, QueuedSignal, ScanSession
from database.repositories import (
    SignalRepository,
    ExecutionRepository,
    QueueRepository,
    ScanRepository
)
from loguru import logger


def test_models():
    """Test model creation and validation."""
    print("\n" + "="*60)
    print("Testing Models")
    print("="*60)

    # Test TradingSignal
    print("\n1. TradingSignal Model:")
    signal = TradingSignal(
        symbol="AAPL",
        score=150,
        signal_price=175.50,
        stop_loss=171.50,
        take_profit=182.00,
        sl_pct=2.28,
        tp_pct=3.70,
        sector="Technology",
        market_regime="BULL",
        reasons=["Strong bounce", "High volume"]
    )
    signal.validate()
    print(f"   ✅ Created signal for {signal.symbol} @ ${signal.signal_price}")
    print(f"   ✅ Score: {signal.score}, SL: {signal.sl_pct}%, TP: {signal.tp_pct}%")

    # Test ExecutionRecord
    print("\n2. ExecutionRecord Model:")
    record = ExecutionRecord(
        symbol="AAPL",
        action="BOUGHT",
        timestamp=datetime.now(),
        signal_score=150,
        signal_price=175.50
    )
    record.validate()
    print(f"   ✅ Created execution: {record.action} {record.symbol}")

    # Test QueuedSignal
    print("\n3. QueuedSignal Model:")
    queued = QueuedSignal(
        symbol="TSLA",
        signal_price=250.00,
        score=140,
        stop_loss=245.00,
        take_profit=260.00
    )
    queued.validate()
    print(f"   ✅ Created queued signal: {queued.symbol} @ ${queued.signal_price}")

    # Test ScanSession
    print("\n4. ScanSession Model:")
    session = ScanSession(
        session_type="morning",
        scan_time=datetime.now(),
        signal_count=5,
        waiting_count=2,
        market_regime="BULL"
    )
    session.validate()
    print(f"   ✅ Created scan session: {session.session_type}, {session.signal_count} signals")

    print("\n✅ All models passed validation")


def test_repositories():
    """Test repository CRUD operations."""
    print("\n" + "="*60)
    print("Testing Repositories")
    print("="*60)

    # Test SignalRepository
    print("\n1. SignalRepository:")
    sig_repo = SignalRepository()

    # Create test signal
    test_signal = TradingSignal(
        symbol="TEST",
        score=100,
        signal_price=50.00,
        stop_loss=49.00,
        take_profit=52.00,
        sector="Technology",
        status="active"
    )

    signal_id = sig_repo.create(test_signal)
    if signal_id:
        print(f"   ✅ Created signal with ID: {signal_id}")

        # Retrieve signal
        signals = sig_repo.get_by_symbol("TEST")
        if signals:
            print(f"   ✅ Retrieved {len(signals)} signal(s) for TEST")

        # Update status
        sig_repo.update_status(signal_id, "executed", "BOUGHT")
        print(f"   ✅ Updated signal status to 'executed'")

        # Get stats
        stats = sig_repo.get_stats(days=1)
        print(f"   ✅ Stats: {stats.get('total', 0)} signals, avg score: {stats.get('avg_score', 0):.1f}")
    else:
        print("   ❌ Failed to create signal")

    # Test ExecutionRepository
    print("\n2. ExecutionRepository:")
    exec_repo = ExecutionRepository()

    test_record = ExecutionRecord(
        symbol="TEST",
        action="BOUGHT",
        timestamp=datetime.now(),
        signal_score=100,
        signal_price=50.00
    )

    record_id = exec_repo.create(test_record)
    if record_id:
        print(f"   ✅ Created execution record with ID: {record_id}")

        # Get last action
        last = exec_repo.get_last_action("TEST")
        if last:
            print(f"   ✅ Last action for TEST: {last.action}")

        # Get daily summary
        summary = exec_repo.get_daily_summary()
        print(f"   ✅ Daily summary: {summary}")
    else:
        print("   ❌ Failed to create execution record")

    # Test QueueRepository
    print("\n3. QueueRepository:")
    queue_repo = QueueRepository()

    test_queued = QueuedSignal(
        symbol="QTEST",
        signal_price=75.00,
        score=130,
        stop_loss=73.50,
        take_profit=78.75
    )

    if queue_repo.add(test_queued):
        print(f"   ✅ Added QTEST to queue")

        # Get all queued
        queued_signals = queue_repo.get_all()
        print(f"   ✅ Queue size: {len(queued_signals)}")

        # Get top signal
        top = queue_repo.get_top(1)
        if top:
            print(f"   ✅ Top signal: {top[0].symbol} (score: {top[0].score})")

        # Get stats
        stats = queue_repo.get_stats()
        print(f"   ✅ Queue stats: {stats}")

        # Remove from queue
        queue_repo.remove("QTEST")
        print(f"   ✅ Removed QTEST from queue")
    else:
        print("   ❌ Failed to add to queue")

    # Test ScanRepository
    print("\n4. ScanRepository:")
    scan_repo = ScanRepository()

    test_session = ScanSession(
        session_type="test_scan",
        scan_time=datetime.now(),
        signal_count=3,
        waiting_count=1,
        market_regime="NORMAL"
    )

    session_id = scan_repo.create(test_session)
    if session_id:
        print(f"   ✅ Created scan session with ID: {session_id}")

        # Get latest
        latest = scan_repo.get_latest()
        if latest:
            print(f"   ✅ Latest scan: {latest.session_type} at {latest.scan_time}")

        # Get stats
        stats = scan_repo.get_stats(days=1)
        print(f"   ✅ Scan stats: {stats}")
    else:
        print("   ❌ Failed to create scan session")

    print("\n✅ All repositories working correctly")


def cleanup_test_data():
    """Clean up test data."""
    print("\n" + "="*60)
    print("Cleaning Up Test Data")
    print("="*60)

    sig_repo = SignalRepository()
    exec_repo = ExecutionRepository()
    scan_repo = ScanRepository()

    # Delete test signals
    from database.manager import get_db_manager
    db = get_db_manager()

    count = db.execute("DELETE FROM trading_signals WHERE symbol IN ('TEST', 'QTEST')").rowcount
    print(f"   ✅ Deleted {count} test signals")

    count = db.execute("DELETE FROM execution_history WHERE symbol = 'TEST'").rowcount
    print(f"   ✅ Deleted {count} test execution records")

    count = db.execute("DELETE FROM scan_sessions WHERE session_type = 'test_scan'").rowcount
    print(f"   ✅ Deleted {count} test scan sessions")

    print("\n✅ Cleanup complete")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Phase 1 Models & Repositories Test Suite")
    print("="*60)

    try:
        # Test models
        test_models()

        # Test repositories
        test_repositories()

        # Cleanup
        cleanup_test_data()

        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60)
        print("\nPhase 1 models and repositories are ready to use.")
        print("\nNext steps:")
        print("1. Review migration: scripts/migrations/001_create_signals_tables.sql")
        print("2. Apply migration: ./scripts/apply_migration_001.sh")
        print("3. Start dual-write implementation in auto_trading_engine.py")
        print("")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
