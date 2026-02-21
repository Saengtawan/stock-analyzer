#!/usr/bin/env python3
"""Import existing pre-filter JSON data to database"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
from datetime import datetime
from database import PreFilterSession, FilteredStock, PreFilterRepository

def import_prefilter_data():
    """Import pre-filter data from JSON files"""

    print("=" * 60)
    print("Importing Pre-filter Data to Database")
    print("=" * 60)

    repo = PreFilterRepository()

    # Read pre_filter_status.json
    status_file = 'data/pre_filter_status.json'
    filtered_file = 'data/pre_filtered.json'

    if not os.path.exists(status_file):
        print(f"❌ Status file not found: {status_file}")
        return False

    if not os.path.exists(filtered_file):
        print(f"❌ Filtered file not found: {filtered_file}")
        return False

    print(f"\n📂 Reading {status_file}...")
    with open(status_file, 'r') as f:
        status_data = json.load(f)

    print(f"✅ Status data loaded")
    print(f"   Pool size: {status_data.get('pool_size', 0)}")
    print(f"   Last updated: {status_data.get('last_updated', 'unknown')}")

    # Create session from status
    print(f"\n📝 Creating database session...")
    session = PreFilterSession.from_json_status(status_data, scan_type='evening')
    session_id = repo.create_session(session)

    if not session_id:
        print("❌ Failed to create session")
        return False

    print(f"✅ Session created with ID: {session_id}")

    # Read filtered stocks
    print(f"\n📂 Reading {filtered_file}...")
    with open(filtered_file, 'r') as f:
        filtered_data = json.load(f)

    # Extract stocks from "stocks" key
    if isinstance(filtered_data, dict) and 'stocks' in filtered_data:
        stocks_data = filtered_data['stocks']
        print(f"✅ Found stocks dictionary with {len(stocks_data)} entries")
    elif isinstance(filtered_data, dict):
        stocks_data = filtered_data
    else:
        print(f"❌ Unknown format: {type(filtered_data)}")
        return False

    stocks = []
    for symbol, data in stocks_data.items():
        if isinstance(data, dict):
            stock = FilteredStock(
                session_id=session_id,
                symbol=symbol,
                sector=data.get('sector'),
                score=data.get('score'),
                close_price=data.get('close') or data.get('close_price'),
                volume_avg_20d=data.get('volume_avg_20d'),
                atr_pct=data.get('atr_pct'),
                rsi=data.get('rsi')
            )
            stocks.append(stock)

    print(f"✅ Found {len(stocks)} stocks")

    # Bulk insert
    print(f"\n💾 Inserting stocks into database...")
    added = repo.add_stocks_bulk(stocks)

    if added == len(stocks):
        print(f"✅ Inserted {added} stocks")
    else:
        print(f"⚠️ Inserted {added}/{len(stocks)} stocks")

    # Update session pool size
    repo.update_session_status(session_id, status='completed', pool_size=added)

    # Verify
    print(f"\n🔍 Verifying...")
    latest = repo.get_latest_session()
    if latest:
        print(f"✅ Latest session: {latest.scan_type}, pool_size={latest.pool_size}")

    pool = repo.get_filtered_pool(session_id)
    if pool:
        print(f"✅ Filtered pool: {len(pool)} stocks")
        print(f"   First 5: {', '.join([s.symbol for s in pool[:5]])}")

    print("\n" + "=" * 60)
    print("✅ Import Complete!")
    print("=" * 60)

    return True

if __name__ == '__main__':
    try:
        success = import_prefilter_data()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Import failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
