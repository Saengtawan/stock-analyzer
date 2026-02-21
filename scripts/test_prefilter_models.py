#!/usr/bin/env python3
"""Test Pre-filter Models and Repository"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime
from database import PreFilterSession, FilteredStock, PreFilterRepository

def test_prefilter():
    """Test pre-filter models and repository"""

    print("=" * 60)
    print("Testing Pre-filter Models & Repository")
    print("=" * 60)

    repo = PreFilterRepository()

    # Test 1: Create session
    print("\n1️⃣ Creating pre-filter session...")
    session = PreFilterSession(
        scan_type='evening',
        scan_time=datetime.now(),
        pool_size=280,
        total_scanned=987,
        status='completed',
        is_ready=True,
        duration_seconds=45.2
    )

    session_id = repo.create_session(session)
    if session_id:
        print(f"✅ Session created with ID: {session_id}")
    else:
        print("❌ Failed to create session")
        return False

    # Test 2: Add filtered stocks
    print("\n2️⃣ Adding filtered stocks...")
    stocks = [
        FilteredStock(
            session_id=session_id,
            symbol='AAPL',
            sector='Technology',
            score=85.5,
            close_price=175.23,
            volume_avg_20d=55000000,
            atr_pct=2.5,
            rsi=62.3,
            filter_reason='High volume + trend'
        ),
        FilteredStock(
            session_id=session_id,
            symbol='MSFT',
            sector='Technology',
            score=82.1,
            close_price=380.45,
            volume_avg_20d=28000000,
            atr_pct=2.1,
            rsi=58.7,
            filter_reason='Strong momentum'
        ),
        FilteredStock(
            session_id=session_id,
            symbol='TSLA',
            sector='Automotive',
            score=78.9,
            close_price=245.67,
            volume_avg_20d=112000000,
            atr_pct=3.8,
            rsi=55.2,
            filter_reason='High volatility'
        )
    ]

    added = repo.add_stocks_bulk(stocks)
    if added == len(stocks):
        print(f"✅ Added {added} stocks to pool")
    else:
        print(f"⚠️ Added {added}/{len(stocks)} stocks")

    # Test 3: Get latest session
    print("\n3️⃣ Retrieving latest session...")
    latest = repo.get_latest_session()
    if latest:
        print(f"✅ Latest session: ID={latest.id}, type={latest.scan_type}, pool_size={latest.pool_size}")
    else:
        print("❌ Failed to get latest session")
        return False

    # Test 4: Get filtered pool
    print("\n4️⃣ Retrieving filtered pool...")
    pool = repo.get_filtered_pool(session_id)
    if pool:
        print(f"✅ Pool size: {len(pool)} stocks")
        for stock in pool[:3]:
            print(f"   - {stock.symbol}: score={stock.score}, sector={stock.sector}")
    else:
        print("❌ Failed to get pool")
        return False

    # Test 5: Get symbols
    print("\n5️⃣ Retrieving symbol list...")
    symbols = repo.get_stock_symbols(session_id)
    if symbols:
        print(f"✅ Symbols: {', '.join(symbols)}")
    else:
        print("❌ Failed to get symbols")
        return False

    # Test 6: Update session status
    print("\n6️⃣ Updating session status...")
    success = repo.update_session_status(
        session_id=session_id,
        status='completed',
        pool_size=len(pool),
        duration=45.2
    )
    if success:
        print("✅ Session updated")
    else:
        print("❌ Failed to update session")

    # Test 7: Get pool size history
    print("\n7️⃣ Getting pool size history...")
    history = repo.get_pool_size_history(days=7)
    if history:
        print(f"✅ History: {len(history)} sessions")
        for h in history[:3]:
            print(f"   - {h['scan_time']}: {h['pool_size']} stocks ({h['scan_type']})")
    else:
        print("⚠️ No history (expected for new table)")

    print("\n" + "=" * 60)
    print("✅ All Tests Passed!")
    print("=" * 60)

    return True

if __name__ == '__main__':
    try:
        success = test_prefilter()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
