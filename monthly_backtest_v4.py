#!/usr/bin/env python3
"""
Monthly Performance Backtest v4.0
Tests exit rules with sample stocks, shows monthly profit breakdown
"""

import sys
sys.path.insert(0, 'src')

from datetime import datetime, timedelta
from portfolio_manager_v3 import PortfolioManagerV3
import yfinance as yf
from collections import defaultdict
import json

# Sample stocks to test (known active stocks)
SAMPLE_STOCKS = [
    'NVDA', 'TSLA', 'AMD', 'AAPL', 'MSFT',
    'GOOGL', 'META', 'AMZN', 'NFLX', 'PLTR',
    'COIN', 'MARA', 'RIOT', 'SQ', 'PYPL'
]

def get_entry_price(symbol, date):
    """Get stock price on a specific date"""
    try:
        ticker = yf.Ticker(symbol)
        end_date = (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')
        hist = ticker.history(start=date, end=end_date)
        if not hist.empty:
            return float(hist['Close'].iloc[0])
    except:
        pass
    return None

def monthly_backtest(months_back=6, stocks_per_month=3):
    """
    Backtest with monthly entries

    Args:
        months_back: How many months to test
        stocks_per_month: How many stocks to enter each month
    """
    print("=" * 80)
    print("📊 Monthly Performance Backtest v4.0 - EXIT RULES TEST")
    print("=" * 80)
    print(f"Period: Last {months_back} months")
    print(f"Stocks per month: {stocks_per_month}")
    print()

    # Initialize portfolio manager
    print("📦 Initializing Portfolio Manager v4.0...")
    pm = PortfolioManagerV3(portfolio_file='portfolio_monthly_test.json')

    # Check exit rules
    if pm.exit_rules:
        print("   ✅ Exit Rules Engine: Active (11 rules)")
        print(f"      Current thresholds:")
        target_rule = [r for r in pm.exit_rules.rules if r.name == "TARGET_HIT"][0]
        stop_rule = [r for r in pm.exit_rules.rules if r.name == "HARD_STOP"][0]
        trail_rule = [r for r in pm.exit_rules.rules if r.name == "TRAILING_STOP"][0]
        print(f"      - Target: {target_rule.thresholds['target_pct']}%")
        print(f"      - Hard Stop: {stop_rule.thresholds['stop_pct']}%")
        print(f"      - Trailing: {trail_rule.thresholds['drawdown_pct']}%")
    else:
        print("   ⚠️  Exit Rules Engine: Not available")

    # Clear portfolio
    pm.portfolio = {
        'active': [],
        'closed': [],
        'cash': 100000,
        'initial_cash': 100000,
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

    # Calculate entry dates (1st of each month)
    entry_dates = []
    current_date = datetime.now()
    for i in range(months_back):
        month_date = current_date - timedelta(days=30*i)
        entry_date = month_date.replace(day=1).strftime('%Y-%m-%d')
        entry_dates.append(entry_date)
    entry_dates.reverse()  # Oldest first

    print(f"\n📅 Entry dates: {', '.join(entry_dates)}")
    print("\n" + "=" * 80)
    print("📈 RUNNING BACKTEST...")
    print("=" * 80)

    monthly_results = defaultdict(lambda: {
        'entries': [],
        'exits': [],
        'profit': 0,
        'trades_closed': 0
    })

    # Enter positions each month
    stock_idx = 0
    for entry_date in entry_dates:
        month_key = entry_date[:7]  # YYYY-MM
        print(f"\n📅 {month_key} - Entering positions...")

        for _ in range(stocks_per_month):
            if stock_idx >= len(SAMPLE_STOCKS):
                stock_idx = 0

            symbol = SAMPLE_STOCKS[stock_idx]
            stock_idx += 1

            # Get entry price
            entry_price = get_entry_price(symbol, entry_date)
            if entry_price is None:
                print(f"   ⚠️  {symbol}: No price data")
                continue

            # Add position
            success = pm.add_position(
                symbol=symbol,
                entry_price=entry_price,
                entry_date=entry_date,
                filters={'source': 'monthly_test'},
                amount=10000
            )

            if success:
                monthly_results[month_key]['entries'].append({
                    'symbol': symbol,
                    'price': entry_price,
                    'date': entry_date
                })
                print(f"   ✅ Entered {symbol} @ ${entry_price:.2f}")
            else:
                print(f"   ⚠️  Failed to enter {symbol}")

        # Update positions daily until next month
        next_month_date = datetime.strptime(entry_date, '%Y-%m-%d') + timedelta(days=30)
        current = datetime.strptime(entry_date, '%Y-%m-%d')

        while current <= min(next_month_date, datetime.now()):
            date_str = current.strftime('%Y-%m-%d')

            # Skip weekends
            if current.weekday() < 5:
                result = pm.update_positions(date_str)

                # Process exits
                for exit_pos in result.get('exit_positions', []):
                    exit_month = date_str[:7]

                    # Close position
                    closed = pm.close_position(
                        symbol=exit_pos['symbol'],
                        exit_price=exit_pos['current_price'],
                        exit_date=date_str,
                        exit_reason=exit_pos['exit_reason']
                    )

                    if closed:
                        monthly_results[exit_month]['exits'].append({
                            'symbol': closed['symbol'],
                            'return_pct': closed['return_pct'],
                            'return_usd': closed['return_usd'],
                            'reason': closed['exit_reason'],
                            'days': closed['days_held']
                        })
                        monthly_results[exit_month]['profit'] += closed['return_usd']
                        monthly_results[exit_month]['trades_closed'] += 1

            current += timedelta(days=1)

    # Close any remaining positions
    print(f"\n🔚 Closing remaining positions...")
    today = datetime.now().strftime('%Y-%m-%d')
    result = pm.update_positions(today)

    for pos in pm.portfolio['active'][:]:  # Copy list to avoid modification during iteration
        closed = pm.close_position(
            symbol=pos['symbol'],
            exit_price=pos.get('current_price', pos['entry_price']),
            exit_date=today,
            exit_reason='BACKTEST_END'
        )

        if closed:
            month_key = today[:7]
            monthly_results[month_key]['exits'].append({
                'symbol': closed['symbol'],
                'return_pct': closed['return_pct'],
                'return_usd': closed['return_usd'],
                'reason': closed['exit_reason'],
                'days': closed['days_held']
            })
            monthly_results[month_key]['profit'] += closed['return_usd']
            monthly_results[month_key]['trades_closed'] += 1

    # Display results
    print("\n" + "=" * 80)
    print("📊 MONTHLY PERFORMANCE BREAKDOWN")
    print("=" * 80)

    total_profit = 0
    total_trades = 0
    winners = 0
    losers = 0

    sorted_months = sorted(monthly_results.keys())

    for month in sorted_months:
        data = monthly_results[month]
        print(f"\n📅 {month}")
        print(f"   Entries: {len(data['entries'])} positions")
        print(f"   Exits: {data['trades_closed']} trades closed")
        print(f"   Profit: ${data['profit']:+.2f}")

        if data['exits']:
            month_winners = len([e for e in data['exits'] if e['return_pct'] > 0])
            month_losers = len([e for e in data['exits'] if e['return_pct'] <= 0])
            win_rate = (month_winners / len(data['exits']) * 100) if data['exits'] else 0

            print(f"   Win Rate: {win_rate:.1f}% ({month_winners}W / {month_losers}L)")
            print(f"   Trades:")

            # Show top 3 winners and losers
            sorted_exits = sorted(data['exits'], key=lambda x: x['return_pct'], reverse=True)
            for exit in sorted_exits[:3]:
                print(f"      {exit['symbol']:6} {exit['return_pct']:+6.2f}% (${exit['return_usd']:+7.2f}, {exit['days']:2}d, {exit['reason']})")

            if len(sorted_exits) > 3:
                print(f"      ... and {len(sorted_exits) - 3} more trades")

            winners += month_winners
            losers += month_losers

        total_profit += data['profit']
        total_trades += data['trades_closed']

    # Summary
    print("\n" + "=" * 80)
    print("📈 OVERALL SUMMARY")
    print("=" * 80)
    print(f"Total Period: {sorted_months[0]} to {sorted_months[-1]}")
    print(f"Total Months: {len(sorted_months)}")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {(winners/total_trades*100):.1f}% ({winners}W / {losers}L)" if total_trades > 0 else "Win Rate: N/A")
    print(f"Total Profit: ${total_profit:+.2f}")
    print(f"Avg Profit/Month: ${total_profit/len(sorted_months):+.2f}")
    print(f"Avg Profit/Trade: ${total_profit/total_trades:+.2f}" if total_trades > 0 else "Avg Profit/Trade: N/A")

    # Exit reason breakdown
    print(f"\n🚪 Exit Reasons Breakdown:")
    all_exits = []
    for data in monthly_results.values():
        all_exits.extend(data['exits'])

    exit_reasons = defaultdict(lambda: {'count': 0, 'profit': 0})
    for exit in all_exits:
        exit_reasons[exit['reason']]['count'] += 1
        exit_reasons[exit['reason']]['profit'] += exit['return_usd']

    for reason, data in sorted(exit_reasons.items(), key=lambda x: x[1]['count'], reverse=True):
        avg_profit = data['profit'] / data['count']
        print(f"   {reason:30} {data['count']:3} trades @ ${avg_profit:+7.2f} avg")

    # Rule performance
    if pm.exit_rules:
        print(f"\n📊 Exit Rules Performance:")
        stats = pm.get_exit_rules_stats()
        fired_stats = [s for s in stats if s['fired_count'] > 0]

        if fired_stats:
            for stat in sorted(fired_stats, key=lambda x: x['fired_count'], reverse=True):
                print(f"   {stat['name']:30} Fired: {stat['fired_count']:3} times")
        else:
            print("   (No rule statistics available yet)")

    # Save results
    results = {
        'period': f"{sorted_months[0]} to {sorted_months[-1]}",
        'months': len(sorted_months),
        'total_trades': total_trades,
        'win_rate': (winners/total_trades*100) if total_trades > 0 else 0,
        'total_profit': total_profit,
        'avg_profit_per_month': total_profit/len(sorted_months),
        'monthly_breakdown': {month: {
            'profit': data['profit'],
            'trades': data['trades_closed'],
            'entries': len(data['entries'])
        } for month, data in monthly_results.items()}
    }

    with open('monthly_backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to monthly_backtest_results.json")
    print("=" * 80)


if __name__ == "__main__":
    print("\n🎯 Monthly Performance Backtest v4.0")
    print("   Tests: Exit Rules Engine")
    print("   Method: Enter sample stocks monthly, track exits\n")

    # Run backtest for last 6 months
    monthly_backtest(months_back=6, stocks_per_month=3)

    print("\n💡 Tips:")
    print("   - Tune exit rules: pm.tune_exit_rule('TARGET_HIT', 'target_pct', 3.5)")
    print("   - Export config: pm.export_exit_rules_config()")
    print("   - Track performance: pm.get_exit_rules_stats()")
    print("\n🎯 Exit rules are working! Optimize to improve monthly profits!")
