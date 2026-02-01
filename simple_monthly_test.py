#!/usr/bin/env python3
"""
Simple Monthly Performance Test
Shows how exit rules work over a few test trades
"""

import sys
sys.path.insert(0, 'src')

from datetime import datetime, timedelta
from portfolio_manager_v3 import PortfolioManagerV3
import yfinance as yf

print("=" * 80)
print("📊 Simple Monthly Performance Test")
print("=" * 80)

# Test stocks with their historical entry dates
test_trades = [
    {'symbol': 'NVDA', 'entry_date': '2025-10-01', 'amount': 10000},
    {'symbol': 'TSLA', 'entry_date': '2025-10-15', 'amount': 10000},
    {'symbol': 'AMD',  'entry_date': '2025-11-01', 'amount': 10000},
    {'symbol': 'AAPL', 'entry_date': '2025-11-15', 'amount': 10000},
    {'symbol': 'MSFT', 'entry_date': '2025-12-01', 'amount': 10000},
]

# Initialize PM
pm = PortfolioManagerV3(portfolio_file='portfolio_simple_test.json')

print(f"\n✅ Exit Rules Engine Active")
print(f"   - Target: {pm.exit_rules.rules[0].thresholds['target_pct']}%")
print(f"   - Hard Stop: {pm.exit_rules.rules[1].thresholds['stop_pct']}%")
print(f"   - Trailing: {pm.exit_rules.rules[2].thresholds['drawdown_pct']}%")

# Clear portfolio
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

print(f"\n📈 Entering {len(test_trades)} test positions...")
print("=" * 80)

# Enter each position and immediately simulate holding to today
for trade in test_trades:
    symbol = trade['symbol']
    entry_date = trade['entry_date']
    amount = trade['amount']

    # Get historical entry price
    try:
        ticker = yf.Ticker(symbol)
        end_date = (datetime.strptime(entry_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')
        hist = ticker.history(start=entry_date, end=end_date)

        if hist.empty:
            print(f"⚠️  {symbol}: No price data for {entry_date}")
            continue

        entry_price = float(hist['Close'].iloc[0])

        # Add position
        success = pm.add_position(
            symbol=symbol,
            entry_price=entry_price,
            entry_date=entry_date,
            filters={'source': 'test'},
            amount=amount
        )

        if success:
            # Get current price
            current_hist = ticker.history(period='1d')
            if not current_hist.empty:
                current_price = float(current_hist['Close'].iloc[-1])
                entry_date_dt = datetime.strptime(entry_date, '%Y-%m-%d')
                days_held = (datetime.now() - entry_date_dt).days
                return_pct = ((current_price - entry_price) / entry_price) * 100

                print(f"\n✅ {symbol}")
                print(f"   Entry: {entry_date} @ ${entry_price:.2f}")
                print(f"   Now: {datetime.now().strftime('%Y-%m-%d')} @ ${current_price:.2f}")
                print(f"   Return: {return_pct:+.2f}% over {days_held} days")

                # Check what exit rule would fire
                from exit_rules_engine import MarketData

                market_data = MarketData(
                    current_price=current_price,
                    entry_price=entry_price,
                    highest_price=max(entry_price, current_price),
                    close_prices=[entry_price, current_price],
                    open_prices=[entry_price, current_price],
                    volume_data=[100000, 100000],
                    days_held=days_held
                )

                exit_reason = pm.exit_rules.evaluate(market_data, symbol)
                if exit_reason:
                    print(f"   🚪 Exit Rule: {exit_reason}")
                else:
                    print(f"   ✋ No exit signal (would hold)")

    except Exception as e:
        print(f"⚠️  {symbol}: Error - {e}")

print("\n" + "=" * 80)
print("📊 Current Portfolio State")
print("=" * 80)

# Show current holdings
if pm.portfolio['active']:
    print(f"\n💼 Active Positions: {len(pm.portfolio['active'])}")
    for pos in pm.portfolio['active']:
        print(f"   {pos['symbol']:6} Entry: ${pos['entry_price']:.2f} | "
              f"Current: ${pos.get('current_price', 0):.2f} | "
              f"P&L: {pos.get('pnl_pct', 0):+.2f}%")
else:
    print(f"\n💼 No active positions")

if pm.portfolio['closed']:
    print(f"\n✅ Closed Positions: {len(pm.portfolio['closed'])}")
    total_pnl = 0
    for pos in pm.portfolio['closed']:
        total_pnl += pos['return_usd']
        print(f"   {pos['symbol']:6} {pos['entry_date'][:7]} → {pos['exit_date'][:7]} | "
              f"{pos['return_pct']:+6.2f}% | ${pos['return_usd']:+7.2f} | {pos['exit_reason']}")
    print(f"\n   Total P&L: ${total_pnl:+.2f}")
else:
    print(f"\n✅ No closed positions yet")

print("\n" + "=" * 80)
print("💡 This demonstrates exit rules working on historical entries")
print("   Each position shows what exit rule (if any) would fire today")
print("=" * 80)
