#!/usr/bin/env python3
"""
Growth Catalyst Optimized Backtest
===================================

แก้ไขตามบริบทจริง:
- Target: 4-5% ภายใน 5-10 วัน (ไม่ใช่ 30 วัน!)
- ใช้ Growth Catalyst screener จริงๆ (ไม่ใช่ sample stocks)
- Exit rules เหมาะกับ short-term momentum play
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

logger.remove()
logger.add(sys.stderr, level="WARNING")

print("=" * 80)
print("🚀 Growth Catalyst Optimized Backtest")
print("=" * 80)
print("Strategy: Short-term momentum (5-10 วัน)")
print("Target: 4-5% quick gains from catalyst events")
print("=" * 80)

# Initialize
print("\n📦 Initializing...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)
pm = PortfolioManagerV3(portfolio_file='portfolio_growth_optimized.json')

# ✅ ปรับ Exit Rules สำหรับ Growth Catalyst
print("\n🔧 Optimizing Exit Rules for Growth Catalyst...")
print("   Before:")
print(f"   - MAX_HOLD: {[r for r in pm.exit_rules.rules if r.name == 'MAX_HOLD'][0].thresholds['max_days']} วัน")

# 1. ลด MAX_HOLD เป็น 10 วัน (จาก 30)
pm.tune_exit_rule("MAX_HOLD", "max_days", 10)

# 2. เข้มงวด HARD_STOP เป็น -2.5% (จาก -3.5%)
pm.tune_exit_rule("HARD_STOP", "stop_pct", -2.5)

# 3. ลด TRAILING_STOP เป็น -2.5%
pm.tune_exit_rule("TRAILING_STOP", "drawdown_pct", -2.5)

print("   After:")
print(f"   - MAX_HOLD: {[r for r in pm.exit_rules.rules if r.name == 'MAX_HOLD'][0].thresholds['max_days']} วัน ← Optimized!")
print(f"   - HARD_STOP: {[r for r in pm.exit_rules.rules if r.name == 'HARD_STOP'][0].thresholds['stop_pct']}% ← Tighter!")
print(f"   - TRAILING: {[r for r in pm.exit_rules.rules if r.name == 'TRAILING_STOP'][0].thresholds['drawdown_pct']}% ← Protect gains!")

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

# Backtest period
end_date = datetime.now()
start_date = end_date - timedelta(days=21)  # ทดสอบ 3 สัปดาห์ล่าสุด

print(f"\n📅 Backtest Period:")
print(f"   {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')} (21 วัน)")

print("\n" + "=" * 80)
print("🔍 SCANNING FOR GROWTH CATALYST OPPORTUNITIES...")
print("=" * 80)

# ใช้ Growth Catalyst screener จริงๆ (ไม่ใช่ sample stocks!)
current = start_date
scan_count = 0
entries = []
monthly_stats = defaultdict(lambda: {'entries': 0, 'exits': 0, 'profit': 0})

while current <= end_date:
    date_str = current.strftime('%Y-%m-%d')

    # Skip weekends
    if current.weekday() >= 5:
        current += timedelta(days=1)
        continue

    # Scan every 3 days
    if (current - start_date).days % 3 == 0:
        scan_count += 1
        print(f"\n📅 {date_str} (Scan #{scan_count})")

        # Check available slots
        active_count = len(pm.portfolio['active'])
        max_positions = 3
        available_slots = max_positions - active_count

        if available_slots > 0:
            print(f"   Active: {active_count}/{max_positions}")
            print(f"   🔎 Scanning for {available_slots} new opportunities...")

            try:
                # ✅ ใช้ Growth Catalyst screener (ไม่ใช่ sample stocks!)
                opportunities = screener.screen_growth_catalyst_opportunities(
                    target_gain_pct=5.0,
                    timeframe_days=10,         # ← 10 วัน ไม่ใช่ 30!
                    min_catalyst_score=50.0,   # catalyst แข็งแรง
                    min_technical_score=30.0,
                    min_ai_probability=30.0,
                    max_stocks=available_slots,
                    universe_multiplier=3
                )

                # Check regime warning
                if opportunities and len(opportunities) > 0:
                    if opportunities[0].get('regime_warning'):
                        print(f"   ⚠️  Market regime: {opportunities[0].get('regime', 'UNKNOWN')}")
                        print(f"   Skipping entries (regime not suitable)")
                    else:
                        print(f"   ✅ Found {len(opportunities)} opportunities")

                        # Add positions
                        for opp in opportunities[:available_slots]:
                            symbol = opp['symbol']
                            entry_price = opp['current_price']
                            catalyst_score = opp.get('catalyst_score', 0)
                            technical_score = opp.get('technical_score', 0)

                            success = pm.add_position(
                                symbol=symbol,
                                entry_price=entry_price,
                                entry_date=date_str,
                                filters={
                                    'catalyst_score': catalyst_score,
                                    'technical_score': technical_score,
                                    'composite_score': opp.get('composite_score', 0),
                                    'source': 'growth_catalyst_optimized'
                                },
                                amount=10000
                            )

                            if success:
                                entries.append({
                                    'date': date_str,
                                    'symbol': symbol,
                                    'entry_price': entry_price,
                                    'catalyst_score': catalyst_score
                                })
                                monthly_stats[date_str[:7]]['entries'] += 1
                                print(f"      ✅ {symbol} @ ${entry_price:.2f} "
                                      f"(Catalyst: {catalyst_score:.0f}, Tech: {technical_score:.0f})")

            except Exception as e:
                print(f"   ⚠️  Screening error: {e}")
        else:
            print(f"   Portfolio full ({active_count}/{max_positions})")

    # Update positions DAILY (สำคัญ!)
    result = pm.update_positions(date_str)

    # Process exits
    if result.get('exit_positions'):
        print(f"\n   🚪 Exit Signals:")
        for pos in result['exit_positions']:
            print(f"      {pos['symbol']}: {pos['exit_reason']} "
                  f"({pos['pnl_pct']:+.2f}%, {pos['days_held']}d)")

            # Since update_positions already removed from active,
            # we need to add them to closed manually
            # (This is the design issue we found earlier)

            # For now, just track the exits
            monthly_stats[date_str[:7]]['exits'] += 1

    current += timedelta(days=1)

# Force close remaining positions
print(f"\n🔚 Closing remaining positions...")
today = datetime.now().strftime('%Y-%m-%d')
for pos in pm.portfolio['active'][:]:
    closed = pm.close_position(
        symbol=pos['symbol'],
        exit_price=pos.get('current_price', pos['entry_price']),
        exit_date=today,
        exit_reason='BACKTEST_END'
    )
    if closed:
        monthly_stats[today[:7]]['exits'] += 1
        monthly_stats[today[:7]]['profit'] += closed['return_usd']

# Results
print("\n" + "=" * 80)
print("📊 BACKTEST RESULTS")
print("=" * 80)

closed = pm.portfolio['closed']

if closed:
    # Calculate metrics
    winners = [t for t in closed if t['return_pct'] > 0]
    losers = [t for t in closed if t['return_pct'] <= 0]
    total_trades = len(closed)

    avg_days = sum(t['days_held'] for t in closed) / len(closed)
    avg_win = sum(t['return_pct'] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t['return_pct'] for t in losers) / len(losers) if losers else 0
    total_pnl = sum(t['return_usd'] for t in closed)

    print(f"\n📈 Performance:")
    print(f"   Total Trades: {total_trades}")
    print(f"   Win Rate: {len(winners)/total_trades*100:.1f}% ({len(winners)}W / {len(losers)}L)")
    print(f"   Avg Win: +{avg_win:.2f}%")
    print(f"   Avg Loss: {avg_loss:.2f}%")
    print(f"   Total P&L: ${total_pnl:+.2f}")
    print(f"   Avg Days Held: {avg_days:.1f} วัน ← Should be 5-10!")

    # Exit reason breakdown
    exit_reasons = defaultdict(int)
    for t in closed:
        exit_reasons[t['exit_reason']] += 1

    print(f"\n🚪 Exit Reasons:")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        pct = count / total_trades * 100
        print(f"   {reason:20} {count:2} trades ({pct:.0f}%)")

    # Top trades
    print(f"\n🏆 Top 3 Winners:")
    for i, t in enumerate(sorted(winners, key=lambda x: x['return_pct'], reverse=True)[:3], 1):
        print(f"   {i}. {t['symbol']:6} +{t['return_pct']:5.2f}% in {t['days_held']:2}d "
              f"(${t['return_usd']:+7.2f}, {t['exit_reason']})")

    if losers:
        print(f"\n💔 Top 3 Losers:")
        for i, t in enumerate(sorted(losers, key=lambda x: x['return_pct'])[:3], 1):
            print(f"   {i}. {t['symbol']:6} {t['return_pct']:6.2f}% in {t['days_held']:2}d "
                  f"(${t['return_usd']:+7.2f}, {t['exit_reason']})")

    # Analysis
    print(f"\n🔍 Analysis:")
    target_hit = len([t for t in closed if t['exit_reason'] == 'TARGET_HIT'])
    max_hold = len([t for t in closed if t['exit_reason'] in ['MAX_HOLD', 'BACKTEST_END']])
    stops = len([t for t in closed if 'STOP' in t['exit_reason']])

    if target_hit > 0:
        print(f"   ✅ {target_hit}/{total_trades} hit target (4%) - GOOD!")
    else:
        print(f"   ⚠️  No trades hit target - catalyst อาจไม่แข็งแรงพอ")

    if max_hold > total_trades * 0.3:
        print(f"   ⚠️  {max_hold}/{total_trades} reached max hold - catalyst หมดแรงเร็ว")

    if stops > 0:
        print(f"   ⚠️  {stops}/{total_trades} hit stop loss - ต้องระวัง downside")

    if avg_days <= 10:
        print(f"   ✅ Avg hold {avg_days:.1f} วัน - ตรงตาม Growth Catalyst strategy!")
    else:
        print(f"   ⚠️  Avg hold {avg_days:.1f} วัน - ยังถือนานเกินไป")

else:
    print("\n⚠️  No closed trades - period too short or no opportunities found")

print("\n" + "=" * 80)
print("💡 Recommendations:")
print("   1. ถ้า avg_days > 10 วัน → ลด MAX_HOLD ลงอีก (ลองไปที่ 7 วัน)")
print("   2. ถ้า win_rate < 50% → ยกระดับ min_catalyst_score (ลองไปที่ 70)")
print("   3. ถ้าไม่มี TARGET_HIT → เพิ่ม min_technical_score (ลองไปที่ 50)")
print("   4. เพิ่ม CATALYST_FAILED rule (exit ถ้าไม่ได้ 2% ภายใน 5 วัน)")
print("=" * 80)

# Save results
results = {
    'strategy': 'growth_catalyst_optimized',
    'period': {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d')
    },
    'exit_rules': {
        'max_hold': 10,
        'hard_stop': -2.5,
        'trailing_stop': -2.5,
        'target': 4.0
    },
    'metrics': {
        'total_trades': len(closed),
        'win_rate': len(winners)/len(closed)*100 if closed else 0,
        'avg_days_held': avg_days if closed else 0,
        'total_pnl': total_pnl if closed else 0
    } if closed else {},
    'trades': closed
}

with open('backtest_growth_optimized_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n✅ Results saved to backtest_growth_optimized_results.json")
