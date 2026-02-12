#!/usr/bin/env python3
"""
Test Database Access Layer
===========================
Quick test to verify DatabaseManager, Models, and Repositories.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import (
    DatabaseManager,
    TradeRepository,
    PositionRepository,
    StockDataRepository
)
from database.manager import get_db_manager

def test_database_manager():
    """Test DatabaseManager connection and queries."""
    print("=" * 70)
    print("TEST 1: DatabaseManager")
    print("=" * 70)
    
    try:
        # Get manager
        db = get_db_manager('trade_history')
        print("✓ DatabaseManager initialized")
        
        # Test fetch_one
        row = db.fetch_one("SELECT COUNT(*) as count FROM trades")
        print(f"✓ Total trades in database: {row['count']}")
        
        # Test fetch_all
        rows = db.fetch_all("SELECT * FROM trades LIMIT 5")
        print(f"✓ Fetched {len(rows)} sample trades")
        
        print("✓ DatabaseManager: PASS\n")
        return True
        
    except Exception as e:
        print(f"✗ DatabaseManager: FAIL - {e}\n")
        return False


def test_trade_repository():
    """Test TradeRepository."""
    print("=" * 70)
    print("TEST 2: TradeRepository")
    print("=" * 70)
    
    try:
        repo = TradeRepository()
        print("✓ TradeRepository initialized")
        
        # Get all trades
        all_trades = repo.get_all(limit=10)
        print(f"✓ get_all(): {len(all_trades)} trades")
        
        # Get open trades
        open_trades = repo.get_open_trades()
        print(f"✓ get_open_trades(): {len(open_trades)} open trades")
        
        # Get closed trades
        closed_trades = repo.get_closed_trades(limit=10)
        print(f"✓ get_closed_trades(): {len(closed_trades)} closed trades")
        
        # Get recent trades
        recent_trades = repo.get_recent_trades(days=7)
        print(f"✓ get_recent_trades(7 days): {len(recent_trades)} trades")
        
        # Get statistics
        stats = repo.get_statistics()
        if stats:
            print(f"✓ get_statistics():")
            print(f"    Total trades: {stats.get('total_trades', 0)}")
            print(f"    Win rate: {stats.get('win_rate', 0):.1f}%")
            print(f"    Total P&L: ${stats.get('total_pnl', 0):,.2f}")
        
        # Test with a specific trade
        if all_trades:
            first_trade = all_trades[0]
            print(f"✓ Sample trade: {first_trade.symbol} {first_trade.action} {first_trade.qty}@${first_trade.price:.2f}")
        
        print("✓ TradeRepository: PASS\n")
        return True
        
    except Exception as e:
        print(f"✗ TradeRepository: FAIL - {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_position_repository():
    """Test PositionRepository."""
    print("=" * 70)
    print("TEST 3: PositionRepository")
    print("=" * 70)
    
    try:
        repo = PositionRepository()
        print("✓ PositionRepository initialized")
        
        # Get all positions
        positions = repo.get_all()
        print(f"✓ get_all(): {len(positions)} active positions")
        
        # Get total exposure
        exposure = repo.get_total_exposure()
        print(f"✓ get_total_exposure(): ${exposure:,.2f}")
        
        # Get symbols
        symbols = repo.get_symbols()
        print(f"✓ get_symbols(): {symbols}")
        
        # Test position count
        count = repo.count()
        print(f"✓ count(): {count} positions")
        
        # Show sample position
        if positions:
            pos = positions[0]
            print(f"✓ Sample position: {pos.symbol} {pos.qty}@${pos.entry_price:.2f}")
            print(f"    Strategy: {pos.strategy}, SL: ${pos.stop_loss:.2f}, TP: ${pos.take_profit:.2f}")
        
        print("✓ PositionRepository: PASS\n")
        return True
        
    except Exception as e:
        print(f"✗ PositionRepository: FAIL - {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_stock_data_repository():
    """Test StockDataRepository."""
    print("=" * 70)
    print("TEST 4: StockDataRepository")
    print("=" * 70)
    
    try:
        repo = StockDataRepository()
        print("✓ StockDataRepository initialized")
        
        # Get symbol count
        symbol_count = repo.get_symbols_count()
        print(f"✓ get_symbols_count(): {symbol_count} symbols")
        
        # Get total prices
        price_count = repo.get_price_count()
        print(f"✓ get_price_count(): {price_count:,} price records")
        
        # Get sample symbols
        symbols = repo.get_symbols_list()[:5]
        print(f"✓ get_symbols_list() sample: {symbols}")
        
        # Test with specific symbol
        if symbols:
            test_symbol = symbols[0]
            
            # Get latest price
            latest = repo.get_latest_price(test_symbol)
            if latest:
                print(f"✓ get_latest_price({test_symbol}): ${latest.close:.2f} on {latest.date}")
            
            # Get price history
            prices = repo.get_prices(test_symbol, days=30)
            print(f"✓ get_prices({test_symbol}, 30 days): {len(prices)} records")
            
            # Get date range
            date_range = repo.get_date_range(test_symbol)
            if date_range:
                print(f"✓ get_date_range({test_symbol}): {date_range[0]} to {date_range[1]}")
        
        print("✓ StockDataRepository: PASS\n")
        return True
        
    except Exception as e:
        print(f"✗ StockDataRepository: FAIL - {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("DATABASE ACCESS LAYER - TEST SUITE")
    print("=" * 70)
    print()
    
    results = []
    
    # Run tests
    results.append(("DatabaseManager", test_database_manager()))
    results.append(("TradeRepository", test_trade_repository()))
    results.append(("PositionRepository", test_position_repository()))
    results.append(("StockDataRepository", test_stock_data_repository()))
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} - {name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print(f"✗ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
