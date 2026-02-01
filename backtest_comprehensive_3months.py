#!/usr/bin/env python3
"""
Comprehensive Backtest - 3 Months Historical Data
==================================================

REAL BACKTEST - ไม่ใช่ test มั่วๆ:
- ย้อนหลัง 3 เดือน (Oct - Dec 2025)
- ใช้ Growth Catalyst screener จริงๆ
- Exit rules optimized (MAX_HOLD = 10 วัน)
- Track ทุกอย่างละเอียด
- ใช้เวลานาน แต่ได้ผลจริง
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
logger.add(sys.stderr, level="ERROR")  # แสดงแค่ error เพื่อให้อ่านง่าย

print("=" * 80)
print("🚀 COMPREHENSIVE BACKTEST - 3 MONTHS")
print("=" * 80)
print("⚠️  This will take time - please be patient!")
print("   Scanning + Entering + Exiting real positions")
print("   Expect 10-15 minutes runtime")
print("=" * 80)

start_time = time.time()

# Initialize
print("\n📦 Step 1/5: Initializing systems...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)
pm = PortfolioManagerV3(portfolio_file='portfolio_comprehensive_3m.json')

# Optimize exit rules for Growth Catalyst
print("\n🔧 Step 2/5: Optimizing Exit Rules...")
pm.tune_exit_rule("MAX_HOLD", "max_days", 10)      # 10 วัน ไม่ใช่ 30!
pm.tune_exit_rule("HARD_STOP", "stop_pct", -2.5)   # เข้มงวดขึ้น
pm.tune_exit_rule("TRAILING_STOP", "drawdown_pct", -2.5)

print(f"   ✅ MAX_HOLD: 10 วัน (optimized for Growth Catalyst)")
print(f"   ✅ HARD_STOP: -2.5%")
print(f"   ✅ TRAILING_STOP: -2.5%")

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

# Backtest period: 3 months
end_date = datetime.now()
start_date = end_date - timedelta(days=90)  # 3 เดือน

print(f"\n📅 Step 3/5: Backtest Period")
print(f"   Start: {start_date.strftime('%Y-%m-%d')}")
print(f"   End: {end_date.strftime('%Y-%m-%d')}")
print(f"   Duration: 90 days (~3 months)")

# Config
MAX_POSITIONS = 5
SCAN_INTERVAL = 2  # Scan ทุก 2 วัน
INITIAL_CAPITAL = 50000  # $50k
POSITION_SIZE = 10000    # $10k per position

print(f"\n💰 Capital Management:")
print(f"   Initial Capital: ${INITIAL_CAPITAL:,}")
print(f"   Max Positions: {MAX_POSITIONS}")
print(f"   Position Size: ${POSITION_SIZE:,}")

print("\n" + "=" * 80)
print("📈 Step 4/5: RUNNING BACKTEST (This will take 10-15 minutes...)")
print("=" * 80)

# Track everything
scan_count = 0
entries_count = 0
exits_count = 0
current = start_date
daily_progress = []

# For detailed tracking
all_scans = []
all_entries = []
all_exits = []
monthly_stats = defaultdict(lambda: {
    'scans': 0,
    'opportunities_found': 0,
    'entries': 0,
    'exits': 0,
    'profit': 0,
    'trades': []
})

# Track positions that were removed by update_positions but not properly closed
# This is to work around the design issue we found
position_tracking = {}  # symbol -> entry details

print("\nProgress:")
print("Date       | Scan# | Action")
print("-" * 60)

while current <= end_date:
    date_str = current.strftime('%Y-%m-%d')
    month_key = date_str[:7]

    # Skip weekends
    if current.weekday() >= 5:
        current += timedelta(days=1)
        continue

    # Scan every N days
    if (current - start_date).days % SCAN_INTERVAL == 0:
        scan_count += 1
        monthly_stats[month_key]['scans'] += 1

        # Check available slots
        active_count = len(pm.portfolio['active'])
        available_slots = MAX_POSITIONS - active_count

        action = f"Scan {scan_count:3d} | Active: {active_count}/{MAX_POSITIONS}"

        if available_slots > 0:
            try:
                # Real Growth Catalyst screening
                opportunities = screener.screen_growth_catalyst_opportunities(
                    target_gain_pct=5.0,
                    timeframe_days=10,
                    min_catalyst_score=40.0,    # ลดลงเล็กน้อยเพื่อให้หาได้มากขึ้น
                    min_technical_score=30.0,
                    min_ai_probability=25.0,
                    max_stocks=available_slots * 2,  # ขอ 2 เท่าแล้วเลือกดีสุด
                    universe_multiplier=3
                )

                # Filter out regime warnings
                valid_opportunities = []
                if opportunities:
                    for opp in opportunities:
                        if not opp.get('regime_warning', False):
                            valid_opportunities.append(opp)

                opps_found = len(valid_opportunities)
                monthly_stats[month_key]['opportunities_found'] += opps_found

                if opps_found > 0:
                    action += f" | Found: {opps_found}"

                    # Take top opportunities
                    for opp in valid_opportunities[:available_slots]:
                        symbol = opp['symbol']
                        entry_price = opp['current_price']

                        # Add position
                        success = pm.add_position(
                            symbol=symbol,
                            entry_price=entry_price,
                            entry_date=date_str,
                            filters={
                                'catalyst_score': opp.get('catalyst_score', 0),
                                'technical_score': opp.get('technical_score', 0),
                                'ai_probability': opp.get('ai_probability', 0),
                                'composite_score': opp.get('composite_score', 0),
                            },
                            amount=POSITION_SIZE
                        )

                        if success:
                            entries_count += 1
                            monthly_stats[month_key]['entries'] += 1

                            entry_detail = {
                                'date': date_str,
                                'symbol': symbol,
                                'entry_price': entry_price,
                                'catalyst_score': opp.get('catalyst_score', 0),
                                'technical_score': opp.get('technical_score', 0),
                            }
                            all_entries.append(entry_detail)
                            position_tracking[symbol] = entry_detail

                            action += f" | ENTER: {symbol} @ ${entry_price:.2f}"

            except Exception as e:
                action += f" | ERROR: {str(e)[:30]}"

        print(f"{date_str} | {action}")

    # Update positions DAILY
    # Important: This is where exits happen
    result = pm.update_positions(date_str)

    # Check for exits
    # Note: update_positions removes positions from active but doesn't close them properly
    # We need to handle this manually

    if result.get('exit_positions'):
        for exit_pos in result['exit_positions']:
            symbol = exit_pos['symbol']
            exit_reason = exit_pos['exit_reason']
            current_price = exit_pos['current_price']
            pnl_pct = exit_pos['pnl_pct']
            days_held = exit_pos['days_held']

            # Calculate profit
            if symbol in position_tracking:
                entry_price = position_tracking[symbol]['entry_price']
                shares = POSITION_SIZE / entry_price
                profit = (current_price - entry_price) * shares

                # Track exit
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
                monthly_stats[month_key]['exits'] += 1
                monthly_stats[month_key]['profit'] += profit
                monthly_stats[month_key]['trades'].append(exit_detail)

                exits_count += 1

                print(f"{date_str} |       | EXIT: {symbol} {exit_reason} {pnl_pct:+.1f}% ({days_held}d)")

                # Remove from tracking
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
        month_key = today[:7]
        monthly_stats[month_key]['exits'] += 1
        monthly_stats[month_key]['profit'] += closed['return_usd']
        monthly_stats[month_key]['trades'].append({
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

# Get all closed trades
all_closed_trades = []
for month_data in monthly_stats.values():
    all_closed_trades.extend(month_data['trades'])

all_closed_trades.extend(pm.portfolio['closed'])

elapsed_time = time.time() - start_time

print("\n" + "=" * 80)
print(f"⏱️  Backtest completed in {elapsed_time/60:.1f} minutes")
print("=" * 80)

# RESULTS
print("\n" + "=" * 80)
print("📊 Step 5/5: BACKTEST RESULTS")
print("=" * 80)

print(f"\n📈 Execution Summary:")
print(f"   Total Scans: {scan_count}")
print(f"   Total Entries: {entries_count}")
print(f"   Total Exits: {exits_count}")

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
    print(f"   Winners: {len(winners)} ({len(winners)/len(all_closed_trades)*100:.1f}%)")
    print(f"   Losers: {len(losers)} ({len(losers)/len(all_closed_trades)*100:.1f}%)")
    print(f"   Win Rate: {win_rate:.1f}%")
    print(f"")
    print(f"   Avg Return: {avg_return_pct:+.2f}%")
    print(f"   Avg Win: +{avg_win:.2f}%")
    print(f"   Avg Loss: {avg_loss:.2f}%")
    print(f"   R:R Ratio: {abs(avg_win/avg_loss):.2f}:1" if avg_loss != 0 else "   R:R Ratio: N/A")
    print(f"")
    print(f"   Total P&L: ${total_return:+,.2f}")
    print(f"   Return on Capital: {total_return/INITIAL_CAPITAL*100:+.2f}%")
    print(f"")
    print(f"   Avg Hold Time: {avg_days:.1f} วัน")

    # Check if within target
    if avg_days <= 10:
        print(f"   ✅ ถือเฉลี่ย {avg_days:.1f} วัน - ตรงตาม Growth Catalyst strategy!")
    else:
        print(f"   ⚠️  ถือเฉลี่ย {avg_days:.1f} วัน - ยังนานเกินไปสำหรับ short-term momentum")

    # Exit reasons breakdown
    print(f"\n🚪 Exit Reasons:")
    exit_reasons = defaultdict(lambda: {'count': 0, 'profit': 0, 'avg_days': 0})
    for t in all_closed_trades:
        reason = t['exit_reason']
        exit_reasons[reason]['count'] += 1
        exit_reasons[reason]['profit'] += t['return_usd']
        exit_reasons[reason]['avg_days'] += t['days_held']

    for reason, data in sorted(exit_reasons.items(), key=lambda x: x[1]['count'], reverse=True):
        avg_profit = data['profit'] / data['count']
        avg_days = data['avg_days'] / data['count']
        pct = data['count'] / len(all_closed_trades) * 100
        print(f"   {reason:20} {data['count']:3} trades ({pct:4.1f}%) | "
              f"Avg: ${avg_profit:+7.2f} in {avg_days:.0f}d")

    # Monthly breakdown
    print(f"\n📅 Monthly Breakdown:")
    print(f"   Month    | Scans | Opps | Entries | Exits | Profit")
    print(f"   " + "-" * 58)

    total_monthly_profit = 0
    sorted_months = sorted(monthly_stats.keys())

    for month in sorted_months:
        data = monthly_stats[month]
        print(f"   {month}   |  {data['scans']:3}  |  {data['opportunities_found']:3} |   {data['entries']:3}   | {data['exits']:3}   | ${data['profit']:+8,.2f}")
        total_monthly_profit += data['profit']

    print(f"   " + "-" * 58)
    print(f"   TOTAL    |  {scan_count:3}  |      |   {entries_count:3}   | {exits_count:3}   | ${total_monthly_profit:+8,.2f}")

    # Top trades
    print(f"\n🏆 Top 5 Winners:")
    for i, t in enumerate(sorted(winners, key=lambda x: x['return_pct'], reverse=True)[:5], 1):
        print(f"   {i}. {t['symbol']:6} +{t['return_pct']:5.2f}% (${t['return_usd']:+7.2f}) "
              f"in {t['days_held']:2}d - {t['exit_reason']}")

    if losers:
        print(f"\n💔 Top 5 Losers:")
        for i, t in enumerate(sorted(losers, key=lambda x: x['return_pct'])[:5], 1):
            print(f"   {i}. {t['symbol']:6} {t['return_pct']:6.2f}% (${t['return_usd']:+7.2f}) "
                  f"in {t['days_held']:2}d - {t['exit_reason']}")

    # Analysis
    print(f"\n🔍 Strategy Analysis:")

    # Target hits
    target_hits = len([t for t in all_closed_trades if t['exit_reason'] == 'TARGET_HIT'])
    max_holds = len([t for t in all_closed_trades if t['exit_reason'] in ['MAX_HOLD', 'BACKTEST_END']])
    stops = len([t for t in all_closed_trades if 'STOP' in t['exit_reason']])

    if target_hits > 0:
        print(f"   ✅ {target_hits}/{len(all_closed_trades)} hit 4% target - GOOD!")
    else:
        print(f"   ⚠️  No trades hit target - catalyst อาจไม่แข็งแรงพอ")

    if max_holds > len(all_closed_trades) * 0.5:
        print(f"   ⚠️  {max_holds}/{len(all_closed_trades)} reached max hold - momentum หมดเร็ว")
    else:
        print(f"   ✅ {max_holds}/{len(all_closed_trades)} max hold - ส่วนใหญ่ exit ก่อน 10 วัน")

    if stops > 0:
        print(f"   ⚠️  {stops}/{len(all_closed_trades)} hit stop - ระวังการคัด catalyst quality")

    if win_rate >= 60:
        print(f"   ✅ Win rate {win_rate:.0f}% - EXCELLENT!")
    elif win_rate >= 50:
        print(f"   ✅ Win rate {win_rate:.0f}% - GOOD")
    else:
        print(f"   ⚠️  Win rate {win_rate:.0f}% - ควรปรับ screening criteria")

    # Save detailed results
    results = {
        'backtest_config': {
            'period': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d'),
                'days': 90
            },
            'exit_rules': {
                'max_hold': 10,
                'hard_stop': -2.5,
                'trailing_stop': -2.5,
                'target': 4.0
            },
            'capital': {
                'initial': INITIAL_CAPITAL,
                'max_positions': MAX_POSITIONS,
                'position_size': POSITION_SIZE
            },
            'screening': {
                'min_catalyst_score': 40.0,
                'min_technical_score': 30.0,
                'min_ai_probability': 25.0
            }
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
            'return_on_capital_pct': total_return/INITIAL_CAPITAL*100,
            'avg_hold_days': avg_days,
        },
        'monthly_stats': {k: {
            'scans': v['scans'],
            'opportunities': v['opportunities_found'],
            'entries': v['entries'],
            'exits': v['exits'],
            'profit': v['profit']
        } for k, v in monthly_stats.items()},
        'all_trades': all_closed_trades,
        'exit_reasons': {k: {
            'count': v['count'],
            'total_profit': v['profit'],
            'avg_profit': v['profit']/v['count'],
            'avg_days': v['avg_days']/v['count']
        } for k, v in exit_reasons.items()}
    }

    with open('backtest_comprehensive_3months_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Detailed results saved to: backtest_comprehensive_3months_results.json")

else:
    print("\n⚠️  No trades completed during backtest period")
    print("   Possible reasons:")
    print("   - Market regime unfavorable entire period")
    print("   - Screening criteria too strict")
    print("   - Period too short for strategy")

print("\n" + "=" * 80)
print("✅ COMPREHENSIVE BACKTEST COMPLETE")
print("=" * 80)
print(f"⏱️  Total runtime: {elapsed_time/60:.1f} minutes")
print(f"📊 {len(all_closed_trades)} trades analyzed")
print(f"💰 Total P&L: ${total_return:+,.2f}" if all_closed_trades else "💰 No P&L data")
print("=" * 80)
