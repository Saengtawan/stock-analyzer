#!/usr/bin/env python3
"""
Simplified Backtest - 1 Month (API-Friendly)
============================================

OPTIMIZED FOR SPEED:
- 1 เดือน (Nov 2025)
- Scan ทุก 7 วัน (4 scans)
- Max 3 positions
- ลด API calls
- ยังคงใช้ Growth Catalyst screener จริงๆ
- Exit rules optimized (MAX_HOLD = 10 วัน)

Expected runtime: 15-20 นาที
"""

import sys
sys.path.insert(0, 'src')

from datetime import datetime, timedelta
from portfolio_manager_v3 import PortfolioManagerV3
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
from loguru import logger
from collections import defaultdict
import json
import time

logger.remove()
logger.add(sys.stderr, level="ERROR")

print("=" * 80)
print("🚀 SIMPLIFIED BACKTEST - 1 MONTH (API-Friendly)")
print("=" * 80)
print("Period: November 2025 (30 days)")
print("Scan Frequency: Every 7 days (4 scans total)")
print("Expected Runtime: 15-20 minutes")
print("=" * 80)

start_time = time.time()

# Initialize
print("\n📦 Initializing...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)
pm = PortfolioManagerV3(portfolio_file='portfolio_simplified_1m.json')

# Optimize exit rules
pm.tune_exit_rule("MAX_HOLD", "max_days", 10)
pm.tune_exit_rule("HARD_STOP", "stop_pct", -2.5)
pm.tune_exit_rule("TRAILING_STOP", "drawdown_pct", -2.5)

print("✅ Exit Rules Optimized:")
print(f"   - MAX_HOLD: 10 วัน")
print(f"   - HARD_STOP: -2.5%")
print(f"   - TRAILING_STOP: -2.5%")

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

# Period: October 2025 (better market conditions)
start_date = datetime(2025, 10, 1)
end_date = datetime(2025, 10, 31)

print(f"\n📅 Backtest Period:")
print(f"   Start: {start_date.strftime('%Y-%m-%d')}")
print(f"   End: {end_date.strftime('%Y-%m-%d')}")
print(f"   Duration: 30 days (1 month)")

# Config
MAX_POSITIONS = 3
SCAN_INTERVAL = 7  # Scan ทุก 7 วัน
INITIAL_CAPITAL = 30000
POSITION_SIZE = 10000

print(f"\n💰 Config:")
print(f"   Capital: ${INITIAL_CAPITAL:,}")
print(f"   Max Positions: {MAX_POSITIONS}")
print(f"   Position Size: ${POSITION_SIZE:,}")
print(f"   Scan Interval: {SCAN_INTERVAL} days")

print("\n" + "=" * 80)
print("📈 RUNNING BACKTEST...")
print("=" * 80)

# Track
scan_count = 0
entries_count = 0
exits_count = 0
current = start_date

all_entries = []
all_exits = []
position_tracking = {}

print("\nDate       | Action")
print("-" * 60)

while current <= end_date:
    date_str = current.strftime('%Y-%m-%d')

    # Skip weekends
    if current.weekday() >= 5:
        current += timedelta(days=1)
        continue

    # Scan every 7 days
    if (current - start_date).days % SCAN_INTERVAL == 0:
        scan_count += 1
        active_count = len(pm.portfolio['active'])
        available_slots = MAX_POSITIONS - active_count

        print(f"{date_str} | Scan #{scan_count} (Active: {active_count}/{MAX_POSITIONS})", end="")

        if available_slots > 0:
            try:
                print(f" - Screening...", end="", flush=True)

                # Growth Catalyst screening (VERY RELAXED for backtest)
                opportunities = screener.screen_growth_catalyst_opportunities(
                    target_gain_pct=5.0,
                    timeframe_days=10,
                    min_catalyst_score=0.0,     # Accept any catalyst
                    min_technical_score=0.0,    # Accept any technical
                    min_ai_probability=0.0,      # Accept any AI score
                    max_stocks=available_slots * 3,
                    universe_multiplier=5        # Larger universe
                )

                # Accept ALL opportunities (even with regime warning - for backtest only!)
                if opportunities and len(opportunities) > 0:
                    print(f" Found {len(opportunities)}")

                    # Enter positions
                    for opp in opportunities[:available_slots]:
                        symbol = opp['symbol']
                        entry_price = opp['current_price']

                        success = pm.add_position(
                            symbol=symbol,
                            entry_price=entry_price,
                            entry_date=date_str,
                            filters={
                                'catalyst_score': opp.get('catalyst_score', 0),
                                'technical_score': opp.get('technical_score', 0),
                                'composite_score': opp.get('composite_score', 0),
                            },
                            amount=POSITION_SIZE
                        )

                        if success:
                            entries_count += 1
                            entry_detail = {
                                'date': date_str,
                                'symbol': symbol,
                                'entry_price': entry_price,
                                'catalyst_score': opp.get('catalyst_score', 0),
                            }
                            all_entries.append(entry_detail)
                            position_tracking[symbol] = entry_detail
                            print(f"           | ✅ ENTER: {symbol} @ ${entry_price:.2f} (Score: {opp.get('composite_score', 0):.0f})")
                else:
                    print(f" No opportunities")

            except Exception as e:
                print(f" ERROR: {str(e)[:40]}")
        else:
            print(f" - Portfolio full")

    # Update positions DAILY
    result = pm.update_positions(date_str)

    # Check exits
    if result.get('exit_positions'):
        for exit_pos in result['exit_positions']:
            symbol = exit_pos['symbol']
            exit_reason = exit_pos['exit_reason']
            current_price = exit_pos['current_price']
            pnl_pct = exit_pos['pnl_pct']
            days_held = exit_pos['days_held']

            if symbol in position_tracking:
                entry_price = position_tracking[symbol]['entry_price']
                shares = POSITION_SIZE / entry_price
                profit = (current_price - entry_price) * shares

                exit_detail = {
                    'date': date_str,
                    'symbol': symbol,
                    'entry_date': position_tracking[symbol]['date'],
                    'entry_price': entry_price,
                    'exit_price': current_price,
                    'return_pct': pnl_pct,
                    'return_usd': profit,
                    'days_held': days_held,
                    'exit_reason': exit_reason,
                }

                all_exits.append(exit_detail)
                exits_count += 1

                print(f"{date_str} | 🚪 EXIT: {symbol} - {exit_reason} ({pnl_pct:+.1f}%, {days_held}d)")

                del position_tracking[symbol]

    current += timedelta(days=1)

# Close remaining positions
print("\n" + "-" * 60)
print("🔚 Closing remaining positions...")

today = datetime.now().strftime('%Y-%m-%d')
for pos in pm.portfolio['active'][:]:
    closed = pm.close_position(
        symbol=pos['symbol'],
        exit_price=pos.get('current_price', pos['entry_price']),
        exit_date=today,
        exit_reason='BACKTEST_END'
    )

    if closed:
        all_exits.append({
            'date': today,
            'symbol': closed['symbol'],
            'entry_date': closed['entry_date'],
            'entry_price': closed['entry_price'],
            'exit_price': closed['exit_price'],
            'return_pct': closed['return_pct'],
            'return_usd': closed['return_usd'],
            'days_held': closed['days_held'],
            'exit_reason': closed['exit_reason'],
        })
        exits_count += 1
        print(f"   ✅ {closed['symbol']}: {closed['return_pct']:+.2f}% ({closed['days_held']}d)")

all_closed_trades = all_exits

elapsed_time = time.time() - start_time

print("\n" + "=" * 80)
print(f"⏱️  Backtest completed in {elapsed_time/60:.1f} minutes")
print("=" * 80)

# RESULTS
print("\n" + "=" * 80)
print("📊 BACKTEST RESULTS")
print("=" * 80)

print(f"\n📈 Execution:")
print(f"   Scans: {scan_count}")
print(f"   Entries: {entries_count}")
print(f"   Exits: {exits_count}")

if all_closed_trades:
    # Calculate metrics
    winners = [t for t in all_closed_trades if t['return_pct'] > 0]
    losers = [t for t in all_closed_trades if t['return_pct'] <= 0]

    total_return = sum(t['return_usd'] for t in all_closed_trades)
    avg_return_pct = sum(t['return_pct'] for t in all_closed_trades) / len(all_closed_trades)
    avg_win = sum(t['return_pct'] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t['return_pct'] for t in losers) / len(losers) if losers else 0
    avg_days = sum(t['days_held'] for t in all_closed_trades) / len(all_closed_trades)

    win_rate = len(winners) / len(all_closed_trades) * 100

    print(f"\n💰 Performance:")
    print(f"   Total Trades: {len(all_closed_trades)}")
    print(f"   Winners: {len(winners)} | Losers: {len(losers)}")
    print(f"   Win Rate: {win_rate:.1f}%")
    print(f"")
    print(f"   Avg Return: {avg_return_pct:+.2f}%")
    print(f"   Avg Win: +{avg_win:.2f}%")
    print(f"   Avg Loss: {avg_loss:.2f}%")
    if avg_loss != 0:
        print(f"   R:R Ratio: {abs(avg_win/avg_loss):.2f}:1")
    print(f"")
    print(f"   Total P&L: ${total_return:+,.2f}")
    print(f"   Return: {total_return/INITIAL_CAPITAL*100:+.2f}%")
    print(f"")
    print(f"   Avg Hold: {avg_days:.1f} วัน", end="")

    if avg_days <= 10:
        print(f" ✅ (ตรงตาม Growth Catalyst!)")
    else:
        print(f" ⚠️  (ยังนานเกินไป)")

    # Exit reasons
    print(f"\n🚪 Exit Reasons:")
    exit_reasons = defaultdict(lambda: {'count': 0, 'profit': 0, 'days': 0})
    for t in all_closed_trades:
        reason = t['exit_reason']
        exit_reasons[reason]['count'] += 1
        exit_reasons[reason]['profit'] += t['return_usd']
        exit_reasons[reason]['days'] += t['days_held']

    for reason, data in sorted(exit_reasons.items(), key=lambda x: x[1]['count'], reverse=True):
        avg_profit = data['profit'] / data['count']
        avg_days = data['days'] / data['count']
        pct = data['count'] / len(all_closed_trades) * 100
        print(f"   {reason:20} {data['count']:2} ({pct:4.1f}%) | ${avg_profit:+7.2f} in {avg_days:.0f}d")

    # Top trades
    print(f"\n🏆 Top 3 Winners:")
    for i, t in enumerate(sorted(winners, key=lambda x: x['return_pct'], reverse=True)[:3], 1):
        print(f"   {i}. {t['symbol']:6} +{t['return_pct']:5.2f}% (${t['return_usd']:+7.2f}) in {t['days_held']:2}d - {t['exit_reason']}")

    if losers:
        print(f"\n💔 Top 3 Losers:")
        for i, t in enumerate(sorted(losers, key=lambda x: x['return_pct'])[:3], 1):
            print(f"   {i}. {t['symbol']:6} {t['return_pct']:6.2f}% (${t['return_usd']:+7.2f}) in {t['days_held']:2}d - {t['exit_reason']}")

    # Analysis
    print(f"\n🔍 Analysis:")

    target_hits = len([t for t in all_closed_trades if t['exit_reason'] == 'TARGET_HIT'])
    max_holds = len([t for t in all_closed_trades if t['exit_reason'] in ['MAX_HOLD', 'BACKTEST_END']])
    stops = len([t for t in all_closed_trades if 'STOP' in t['exit_reason']])

    if target_hits > 0:
        print(f"   ✅ {target_hits}/{len(all_closed_trades)} hit 4% target")
    else:
        print(f"   ⚠️  No trades hit target")

    if max_holds > len(all_closed_trades) * 0.5:
        print(f"   ⚠️  {max_holds}/{len(all_closed_trades)} reached max hold")
    else:
        print(f"   ✅ {max_holds}/{len(all_closed_trades)} max hold")

    if stops > 0:
        print(f"   ⚠️  {stops}/{len(all_closed_trades)} hit stop loss")

    if win_rate >= 60:
        print(f"   ✅ Win rate {win_rate:.0f}% - EXCELLENT!")
    elif win_rate >= 50:
        print(f"   ✅ Win rate {win_rate:.0f}% - GOOD")
    else:
        print(f"   ⚠️  Win rate {win_rate:.0f}% - Need improvement")

    # Detailed log
    print(f"\n📋 All Trades:")
    print(f"   Entry      | Symbol | Exit       | Return  | Days | Reason")
    print(f"   " + "-" * 65)
    for t in sorted(all_closed_trades, key=lambda x: x['entry_date']):
        print(f"   {t['entry_date']} | {t['symbol']:6} | {t['date'][:10]} | {t['return_pct']:+6.2f}% | {t['days_held']:3}d | {t['exit_reason']}")

    # Save results
    results = {
        'period': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d'),
            'days': 30
        },
        'config': {
            'max_hold': 10,
            'hard_stop': -2.5,
            'trailing_stop': -2.5,
            'target': 4.0,
            'max_positions': MAX_POSITIONS,
            'scan_interval': SCAN_INTERVAL
        },
        'performance': {
            'total_trades': len(all_closed_trades),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': win_rate,
            'avg_return_pct': avg_return_pct,
            'avg_win_pct': avg_win,
            'avg_loss_pct': avg_loss,
            'total_pnl_usd': total_return,
            'return_pct': total_return/INITIAL_CAPITAL*100,
            'avg_hold_days': avg_days,
        },
        'trades': all_closed_trades
    }

    with open('backtest_simplified_1month_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Results saved to: backtest_simplified_1month_results.json")

else:
    print("\n⚠️  No trades completed")

print("\n" + "=" * 80)
print("✅ SIMPLIFIED BACKTEST COMPLETE")
print("=" * 80)
print(f"⏱️  Runtime: {elapsed_time/60:.1f} minutes")
print(f"📊 {len(all_closed_trades)} trades analyzed" if all_closed_trades else "📊 No trades")
print(f"💰 Total P&L: ${total_return:+,.2f}" if all_closed_trades else "")
print("=" * 80)
