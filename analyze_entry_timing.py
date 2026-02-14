#!/usr/bin/env python3
"""
Quick Analysis: Entry Timing vs Results
Analyzes existing trade history to find optimal entry times
"""

import sqlite3
import pandas as pd
from datetime import datetime, time
import pytz

# Connect to database
db_path = '/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db'
conn = sqlite3.connect(db_path)

# Load BUY trades
buy_trades = pd.read_sql_query("""
    SELECT
        symbol,
        timestamp,
        date,
        price as entry_price,
        gap_pct,
        atr_pct,
        signal_score,
        mode,
        regime
    FROM trades
    WHERE action='BUY'
    ORDER BY timestamp
""", conn)

print("=" * 80)
print("PHASE A: QUICK ANALYSIS - EXISTING TRADE HISTORY")
print("=" * 80)
print(f"\n📊 Total BUY trades: {len(buy_trades)}")
print(f"📅 Date range: {buy_trades['date'].min()} to {buy_trades['date'].max()}")

# Parse timestamps and extract entry time
buy_trades['timestamp_dt'] = pd.to_datetime(buy_trades['timestamp'])
buy_trades['entry_time'] = buy_trades['timestamp_dt'].dt.time

# Calculate minutes after market open (9:30 ET)
def minutes_after_open(entry_time):
    """Calculate minutes after 9:30 ET open"""
    if isinstance(entry_time, time):
        open_time = time(9, 30)
        entry_minutes = entry_time.hour * 60 + entry_time.minute
        open_minutes = open_time.hour * 60 + open_time.minute
        return entry_minutes - open_minutes
    return None

buy_trades['minutes_after_open'] = buy_trades['entry_time'].apply(minutes_after_open)

# Categorize entry timing
def categorize_entry_time(minutes):
    """Categorize entry time into buckets"""
    if minutes is None:
        return 'Unknown'
    elif minutes < 0:
        return 'Pre-market'
    elif minutes <= 5:
        return '9:30-9:35 (First 5min)'
    elif minutes <= 10:
        return '9:35-9:40 (5-10min)'
    elif minutes <= 15:
        return '9:40-9:45 (10-15min)'
    elif minutes <= 30:
        return '9:45-10:00 (15-30min)'
    elif minutes <= 60:
        return '10:00-10:30 (30-60min)'
    elif minutes <= 180:
        return 'Midday (1-3hr)'
    elif minutes <= 360:
        return 'Afternoon (3-6hr)'
    else:
        return 'Pre-close (>6hr)'

buy_trades['entry_bucket'] = buy_trades['minutes_after_open'].apply(categorize_entry_time)

# Categorize gap
def categorize_gap(gap_pct):
    """Categorize opening gap"""
    if gap_pct is None or pd.isna(gap_pct):
        return 'Unknown'
    elif gap_pct < -1.5:
        return 'Gap Down (<-1.5%)'
    elif gap_pct < -0.5:
        return 'Mild Gap Down (-1.5% to -0.5%)'
    elif gap_pct <= 0.5:
        return 'Flat (-0.5% to +0.5%)'
    elif gap_pct <= 1.5:
        return 'Mild Gap Up (+0.5% to +1.5%)'
    else:
        return 'Gap Up (>+1.5%)'

buy_trades['gap_category'] = buy_trades['gap_pct'].apply(categorize_gap)

print("\n" + "=" * 80)
print("⏰ ENTRY TIMING BREAKDOWN")
print("=" * 80)
print(buy_trades[['symbol', 'entry_time', 'minutes_after_open', 'entry_bucket', 'gap_pct', 'gap_category']].to_string(index=False))

print("\n" + "=" * 80)
print("📊 ENTRY TIME BUCKETS")
print("=" * 80)
timing_summary = buy_trades.groupby('entry_bucket').agg({
    'symbol': 'count',
    'gap_pct': 'mean',
    'atr_pct': 'mean'
}).rename(columns={'symbol': 'count'})
print(timing_summary)

print("\n" + "=" * 80)
print("📈 GAP CATEGORIES")
print("=" * 80)
gap_summary = buy_trades.groupby('gap_category').agg({
    'symbol': 'count',
    'minutes_after_open': 'mean',
    'atr_pct': 'mean'
}).rename(columns={'symbol': 'count'})
print(gap_summary)

# Now load SELL trades to calculate P&L
sell_trades = pd.read_sql_query("""
    SELECT
        symbol,
        timestamp,
        price as exit_price,
        pnl_pct,
        hold_duration
    FROM trades
    WHERE action='SELL'
    ORDER BY timestamp
""", conn)

print(f"\n📊 Total SELL trades: {len(sell_trades)}")

# Match BUY with SELL to calculate returns
if len(sell_trades) > 0:
    print("\n" + "=" * 80)
    print("💰 COMPLETED TRADES (BUY → SELL)")
    print("=" * 80)

    for _, sell in sell_trades.iterrows():
        symbol = sell['symbol']
        # Find corresponding BUY
        buy = buy_trades[buy_trades['symbol'] == symbol]
        if len(buy) > 0:
            buy = buy.iloc[0]
            print(f"\n{symbol}:")
            print(f"  Entry: {buy['entry_time']} ({buy['entry_bucket']})")
            print(f"  Gap: {buy['gap_pct']:.2f}% ({buy['gap_category']})")
            print(f"  P&L: {sell['pnl_pct']:.2f}%")
            print(f"  Hold: {sell['hold_duration']}")

# Load SKIP trades to see what got filtered
skip_trades = pd.read_sql_query("""
    SELECT
        timestamp,
        symbol,
        reason,
        gap_pct,
        atr_pct
    FROM trades
    WHERE action='SKIP'
    AND reason LIKE '%Layer%'
    ORDER BY timestamp
    LIMIT 50
""", conn)

print(f"\n📊 Entry Protection SKIP trades: {len(skip_trades)}")

if len(skip_trades) > 0:
    print("\n" + "=" * 80)
    print("🛡️ ENTRY PROTECTION BLOCKS (Sample)")
    print("=" * 80)

    skip_trades['timestamp_dt'] = pd.to_datetime(skip_trades['timestamp'])
    skip_trades['skip_time'] = skip_trades['timestamp_dt'].dt.time
    skip_trades['minutes_after_open'] = skip_trades['skip_time'].apply(minutes_after_open)

    print(skip_trades[['symbol', 'skip_time', 'minutes_after_open', 'reason', 'gap_pct']].head(20).to_string(index=False))

    # Count skip reasons
    print("\n" + "=" * 80)
    print("🛡️ ENTRY PROTECTION SKIP REASONS")
    print("=" * 80)
    skip_reasons = skip_trades['reason'].value_counts()
    print(skip_reasons)

conn.close()

print("\n" + "=" * 80)
print("✅ PHASE A COMPLETE - QUICK ANALYSIS DONE")
print("=" * 80)
print("\nKEY INSIGHTS:")
print("1. Check entry time distribution (most trades 9:36-9:45)")
print("2. Check gap categories (flat vs gap down vs gap up)")
print("3. Check which Layer blocks most signals")
print("\nNEXT: Build full backtest engine for 6-month analysis")
