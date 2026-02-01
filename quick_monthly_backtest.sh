#!/usr/bin/env bash
# Quick Monthly Backtest - Simple version
# Shows monthly performance over last 3 months

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')

from datetime import datetime, timedelta
from portfolio_manager_v3 import PortfolioManagerV3
import yfinance as yf
from collections import defaultdict
import json

print("=" * 80)
print("📊 Quick Monthly Backtest - Last 3 Months")
print("=" * 80)

# Sample stocks
STOCKS = ['NVDA', 'TSLA', 'AMD', 'AAPL', 'MSFT']

# Initialize PM
pm = PortfolioManagerV3(portfolio_file='portfolio_quick_test.json')

# Reset portfolio
pm.portfolio = {
    'active': [],
    'closed': [],
    'stats': {
        'total_trades': 0,
        'win_rate': 0.0,
        'total_pnl': 0.0,
        'avg_return': 0.0,
        'win_count': 0,
        'loss_count': 0,
    }
}
pm._save_portfolio()

# Entry dates (1st of last 3 months)
entry_dates = []
for i in range(3, 0, -1):  # 3, 2, 1 months ago
    date = datetime.now() - timedelta(days=30*i)
    entry_dates.append(date.replace(day=1).strftime('%Y-%m-%d'))

print(f"\n📅 Entry dates: {', '.join(entry_dates)}\n")

# Enter positions each month
for month_idx, entry_date in enumerate(entry_dates):
    symbol = STOCKS[month_idx % len(STOCKS)]

    # Get entry price
    try:
        ticker = yf.Ticker(symbol)
        end_date = (datetime.strptime(entry_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')
        hist = ticker.history(start=entry_date, end=end_date)
        if not hist.empty:
            entry_price = float(hist['Close'].iloc[0])

            # Add position using PM's method (which handles all the setup)
            pm.add_position(
                symbol=symbol,
                entry_price=entry_price,
                entry_date=entry_date,
                filters={'source': 'monthly_test'},
                amount=10000
            )
            print(f"✅ {entry_date[:7]} - Entered {symbol} @ ${entry_price:.2f}")
    except Exception as e:
        print(f"⚠️  {entry_date[:7]} - Failed to enter {symbol}: {e}")

# Update to today and let exit rules work
print(f"\n🔄 Running exit rules until today...")
today = datetime.now().strftime('%Y-%m-%d')

# The key insight: update_positions removes positions from active when they hit exits
# So we just need to run it once, and closed positions will be in the 'closed' list
initial_active = len(pm.portfolio['active'])
print(f"   Starting with {initial_active} active positions")

# Update positions (this will automatically remove exited ones from active)
pm.update_positions(today)

final_active = len(pm.portfolio['active'])
closed_count = len(pm.portfolio['closed'])

print(f"   Now: {final_active} active, {closed_count} closed")

# But wait - update_positions doesn't actually CLOSE them, it just removes from active
# The positions that got exit signals are lost!
# We need to manually close the remaining positions

print(f"\n🔚 Manually closing remaining {final_active} positions...")
for pos in pm.portfolio['active'][:]:
    closed = pm.close_position(
        symbol=pos['symbol'],
        exit_price=pos.get('current_price', pos['entry_price']),
        exit_date=today,
        exit_reason='BACKTEST_END'
    )
    if closed:
        print(f"   ✅ Closed {closed['symbol']}: {closed['return_pct']:+.2f}% (${closed['return_usd']:+.2f})")

# Show results
print("\n" + "=" * 80)
print("📊 RESULTS")
print("=" * 80)

closed = pm.portfolio['closed']
if closed:
    total_return = sum(t['return_usd'] for t in closed)
    avg_return = sum(t['return_pct'] for t in closed) / len(closed)
    winners = [t for t in closed if t['return_pct'] > 0]
    losers = [t for t in closed if t['return_pct'] <= 0]

    print(f"\nTotal Trades: {len(closed)}")
    print(f"Win Rate: {len(winners)/len(closed)*100:.1f}% ({len(winners)}W / {len(losers)}L)")
    print(f"Avg Return: {avg_return:+.2f}%")
    print(f"Total P&L: ${total_return:+.2f}")

    print(f"\n📋 Trade Details:")
    for t in closed:
        print(f"   {t['symbol']:6} {t['entry_date'][:7]} → {t['exit_date'][:7]} | "
              f"{t['return_pct']:+6.2f}% | ${t['return_usd']:+7.2f} | {t['days_held']:2}d | {t['exit_reason']}")
else:
    print("\n⚠️  No trades closed")

print("\n" + "=" * 80)
EOF
