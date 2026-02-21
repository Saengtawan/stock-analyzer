#!/usr/bin/env python3
"""
Phase 3 Validation Monitor
Tracks performance metrics after fixes to validate improvements
"""
import sys
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer/src')

import sqlite3
from datetime import datetime, timedelta
import yfinance as yf

# Config
DB_PATH = 'data/trade_history.db'
VALIDATION_START_DATE = '2026-02-19'  # Date when fixes went live
TARGET_WIN_RATE = 40.0
TARGET_AVG_PNL = 0.5

def get_spy_status():
    """Get current SPY regime status."""
    spy = yf.Ticker("SPY")
    hist = spy.history(period="60d")

    current = hist['Close'].iloc[-1]
    sma20 = hist['Close'].rolling(20).mean().iloc[-1]

    regime = "BULL" if current > sma20 else "BEAR"
    distance = ((current - sma20) / sma20) * 100

    return {
        'price': current,
        'sma20': sma20,
        'regime': regime,
        'distance_pct': distance
    }

def get_validation_trades():
    """Get all trades since validation start."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            symbol, date, action, price, qty, pnl_pct, reason
        FROM trades
        WHERE date >= ? AND action = 'SELL'
        ORDER BY date DESC
    """, (VALIDATION_START_DATE,))

    trades = cursor.fetchall()
    conn.close()

    return trades

def get_validation_metrics():
    """Calculate validation metrics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get metrics
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
            AVG(pnl_pct) as avg_pnl,
            SUM(pnl_usd) as total_pnl,
            MAX(pnl_pct) as max_win,
            MIN(pnl_pct) as max_loss
        FROM trades
        WHERE date >= ? AND action = 'SELL'
    """, (VALIDATION_START_DATE,))

    result = cursor.fetchone()
    conn.close()

    if result[0] == 0:
        return None

    total, wins, avg_pnl, total_pnl, max_win, max_loss = result
    win_rate = (wins / total) * 100 if total > 0 else 0

    return {
        'total': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'max_win': max_win,
        'max_loss': max_loss
    }

def check_ghost_positions():
    """Check for ghost positions (BUY without SELL)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all BUY symbols
    cursor.execute("""
        SELECT DISTINCT symbol
        FROM trades
        WHERE date >= ? AND action = 'BUY'
    """, (VALIDATION_START_DATE,))
    buy_symbols = {row[0] for row in cursor.fetchall()}

    # Get all SELL symbols
    cursor.execute("""
        SELECT DISTINCT symbol
        FROM trades
        WHERE date >= ? AND action = 'SELL'
    """, (VALIDATION_START_DATE,))
    sell_symbols = {row[0] for row in cursor.fetchall()}

    # Get active positions
    cursor.execute("SELECT symbol FROM active_positions")
    active_symbols = {row[0] for row in cursor.fetchall()}

    conn.close()

    # Ghost = (BUY - SELL) - Active
    ghosts = buy_symbols - sell_symbols - active_symbols

    return list(ghosts)

def get_entry_rejections():
    """Get entry rejections (SKIP actions)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT symbol, date, price, reason
        FROM trades
        WHERE date >= ? AND action = 'SKIP'
        ORDER BY date DESC
        LIMIT 20
    """, (VALIDATION_START_DATE,))

    skips = cursor.fetchall()
    conn.close()

    return skips

def print_validation_report():
    """Print comprehensive validation report."""
    print("=" * 80)
    print("📊 PHASE 3 VALIDATION MONITOR")
    print("=" * 80)
    print(f"Validation Start: {VALIDATION_START_DATE}")
    print(f"Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # SPY Status
    print("🎯 MARKET STATUS")
    print("-" * 80)
    spy = get_spy_status()
    print(f"SPY Price:    ${spy['price']:.2f}")
    print(f"SPY SMA20:    ${spy['sma20']:.2f}")
    print(f"Regime:       {spy['regime']}")
    print(f"Distance:     {spy['distance_pct']:+.2f}%")

    if spy['regime'] == 'BEAR':
        print("⚠️  Status:     NO NEW TRADES (waiting for BULL mode)")
    else:
        print("✅ Status:     TRADING ACTIVE")
    print()

    # Validation Metrics
    print("📈 VALIDATION METRICS (Since Fixes)")
    print("-" * 80)

    metrics = get_validation_metrics()

    if metrics is None or metrics['total'] == 0:
        print("⏸️  No validation trades yet (waiting for market recovery)")
        print()
    else:
        # Performance Table
        data = [
            ["Total Trades", metrics['total']],
            ["Wins", f"{metrics['wins']} ({metrics['win_rate']:.1f}%)"],
            ["Losses", f"{metrics['losses']} ({100-metrics['win_rate']:.1f}%)"],
            ["", ""],
            ["Win Rate", f"{metrics['win_rate']:.1f}%"],
            ["Target Win Rate", f"{TARGET_WIN_RATE:.1f}%"],
            ["Status", "✅ ON TRACK" if metrics['win_rate'] >= TARGET_WIN_RATE else "⚠️ BELOW TARGET"],
            ["", ""],
            ["Avg P&L", f"{metrics['avg_pnl']:.2f}%"],
            ["Target Avg P&L", f"{TARGET_AVG_PNL:.2f}%"],
            ["Status", "✅ ON TRACK" if metrics['avg_pnl'] >= TARGET_AVG_PNL else "⚠️ BELOW TARGET"],
            ["", ""],
            ["Total P&L", f"${metrics['total_pnl']:.2f}"],
            ["Best Win", f"{metrics['max_win']:.2f}%"],
            ["Worst Loss", f"{metrics['max_loss']:.2f}%"],
        ]

        for row in data:
            if len(row) == 2:
                print(f"{row[0]:<20} {row[1]}")
            else:
                print()
        print()

        # Progress Assessment
        print("🎯 VALIDATION PROGRESS")
        print("-" * 80)

        if metrics['total'] < 10:
            print(f"Trades: {metrics['total']}/10 (need 10 for initial assessment)")
            print("Status: 📊 COLLECTING DATA")
        elif metrics['total'] < 20:
            print(f"Trades: {metrics['total']}/20 (need 20 for full validation)")
            if metrics['win_rate'] >= TARGET_WIN_RATE:
                print("Status: ✅ ON TRACK - Continue monitoring")
            elif metrics['win_rate'] >= 30:
                print("Status: ⚠️ MIXED - Monitor closely")
            else:
                print("Status: ❌ BELOW TARGET - Investigation needed")
        else:
            print(f"Trades: {metrics['total']}/20 ✅ VALIDATION COMPLETE")
            if metrics['win_rate'] >= TARGET_WIN_RATE:
                print("Status: ✅ SUCCESS - Proceed to Phase 4!")
            elif metrics['win_rate'] >= 30:
                print("Status: ⚠️ MIXED - Extend validation to 30 trades")
            else:
                print("Status: ❌ FAILED - Deep investigation needed")
        print()

        # Recent Trades
        print("📋 RECENT TRADES")
        print("-" * 80)
        trades = get_validation_trades()

        if trades:
            trade_data = []
            for symbol, date, action, price, qty, pnl, reason in trades[:10]:
                result = "✅" if pnl > 0 else "❌"
                trade_data.append([
                    date[:10],
                    symbol,
                    f"${price:.2f}",
                    f"{pnl:+.2f}%",
                    result,
                    reason[:30]
                ])

            print(f"{'Date':<12} {'Symbol':<8} {'Price':<10} {'P&L':<10} {'✓':<3} {'Reason':<30}")
            print("-" * 80)
            for row in trade_data:
                print(f"{row[0]:<12} {row[1]:<8} {row[2]:<10} {row[3]:<10} {row[4]:<3} {row[5]:<30}")
        else:
            print("No trades yet")
        print()

    # Ghost Positions Check
    print("👻 GHOST POSITION CHECK")
    print("-" * 80)
    ghosts = check_ghost_positions()

    if ghosts:
        print(f"❌ FOUND {len(ghosts)} GHOST POSITIONS:")
        for symbol in ghosts:
            print(f"   - {symbol}")
        print("\n⚠️  Ghost fix may not be working! Investigate immediately.")
    else:
        print("✅ No ghost positions detected")
    print()

    # Entry Rejections
    print("⛔ RECENT ENTRY REJECTIONS (SKIP)")
    print("-" * 80)
    skips = get_entry_rejections()

    if skips:
        print(f"Recent SKIP actions: {len(skips)}")
        print("\nNote: Some SKIPs are expected (BEAR mode, position limits)")
        print("⚠️  Red flag: High-score stocks (>140) being SKIPped when in BULL mode")
    else:
        print("No entry rejections since validation start")
    print()

    # Action Items
    print("📝 ACTION ITEMS")
    print("-" * 80)

    if spy['regime'] == 'BEAR':
        print("⏸️  Wait for SPY to cross SMA20 (BEAR → BULL)")
        print(f"   Currently {abs(spy['distance_pct']):.2f}% below SMA20")

    if metrics and metrics['total'] > 0:
        if metrics['total'] < 10:
            print("📊 Continue collecting trades (need 10 for assessment)")
        elif metrics['total'] < 20:
            print("📊 Continue collecting trades (need 20 for validation)")
        else:
            if metrics['win_rate'] >= TARGET_WIN_RATE:
                print("🎉 Validation successful! Ready for Phase 4 (scale up)")
            else:
                print("🔍 Investigate why win rate below target")

    if ghosts:
        print("❌ Fix ghost position bug immediately!")

    print()
    print("=" * 80)

if __name__ == "__main__":
    print_validation_report()
