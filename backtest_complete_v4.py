#!/usr/bin/env python3
"""
Complete System Backtest v4.0 - Rule-Based Edition
Tests both screening (Growth Catalyst v4.0) + portfolio management (v3 with exit rules)

v4.0: Both systems now use rule-based engines
- Screening: 14 configurable rules
- Exit: 11 configurable rules
"""

import sys
sys.path.insert(0, 'src')

from datetime import datetime, timedelta
from portfolio_manager_v3 import PortfolioManagerV3
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
from loguru import logger
import json

logger.remove()
logger.add(sys.stderr, level="WARNING")  # Only warnings and errors


def backtest_complete_system(start_date: str, end_date: str, max_positions: int = 5):
    """
    Backtest complete system: Screening → Portfolio Management → Exit

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_positions: Max concurrent positions
    """
    print("=" * 80)
    print("🚀 Complete System Backtest v4.0 - RULE-BASED EDITION")
    print("=" * 80)
    print(f"Period: {start_date} to {end_date}")
    print(f"Max Positions: {max_positions}")
    print()

    # Initialize
    print("📦 Initializing systems...")
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)
    pm = PortfolioManagerV3(portfolio_file='portfolio_backtest_v4.json')

    # Check rule-based systems
    print("\n🔍 Rule-Based Systems Status:")
    if screener.screening_rules:
        print("   ✅ Screening Rules Engine: Active (14 rules)")
    else:
        print("   ⚠️  Screening Rules Engine: Not available (using legacy)")

    if pm.exit_rules:
        print("   ✅ Exit Rules Engine: Active (11 rules)")
    else:
        print("   ⚠️  Exit Rules Engine: Not available (using legacy)")

    # Clear portfolio
    pm.portfolio = {
        'active': [],
        'closed': [],
        'cash': 100000,
        'initial_cash': 100000
    }
    pm._save_portfolio()

    # Parse dates
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    current = start

    scan_count = 0
    entries = []

    print("\n" + "=" * 80)
    print("📅 Running Backtest...")
    print("=" * 80)

    # Run screening every 3 days
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')

        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        scan_count += 1
        print(f"\n📅 {date_str} (Scan #{scan_count})")

        # Check if we can add more positions
        active_count = len(pm.portfolio['active'])
        available_slots = max_positions - active_count

        if available_slots > 0:
            print(f"   Active positions: {active_count}/{max_positions}")
            print(f"   Scanning for {available_slots} new entries...")

            try:
                # Run Growth Catalyst screening
                opportunities = screener.screen_growth_catalyst_opportunities(
                    target_gain_pct=5.0,
                    timeframe_days=30,
                    min_catalyst_score=0.0,
                    min_technical_score=30.0,
                    min_ai_probability=30.0,
                    max_stocks=available_slots,
                    universe_multiplier=3  # Faster for backtest
                )

                # Handle regime warning
                if opportunities and len(opportunities) > 0 and opportunities[0].get('regime_warning'):
                    print(f"   ⚠️  Market regime not suitable: {opportunities[0]['regime']}")
                    print(f"   Skipping entries for safety")
                else:
                    print(f"   Found {len(opportunities)} opportunities")

                    # Add top opportunities to portfolio
                    for opp in opportunities[:available_slots]:
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
                                'composite_score': opp.get('composite_score', 0)
                            },
                            amount=10000  # $10k per position
                        )

                        if success:
                            entries.append({
                                'date': date_str,
                                'symbol': symbol,
                                'entry_price': entry_price,
                                'composite_score': opp.get('composite_score', 0)
                            })
                            print(f"   ✅ Entered {symbol} @ ${entry_price:.2f} "
                                  f"(Score: {opp.get('composite_score', 0):.1f}/100)")

            except Exception as e:
                print(f"   ⚠️  Screening error: {e}")
        else:
            print(f"   Portfolio full ({active_count}/{max_positions})")

        # Update positions daily
        result = pm.update_positions(date_str)

        # Check for exits
        if result['exit_positions']:
            print(f"\n   🚪 Exit Signals:")
            for pos in result['exit_positions']:
                print(f"      {pos['symbol']}: {pos['exit_reason']} "
                      f"(PnL: {pos['pnl_pct']:+.2f}%, Days: {pos['days_held']})")

                # Close position
                pm.close_position(
                    symbol=pos['symbol'],
                    exit_price=pos['current_price'],
                    exit_date=date_str,
                    exit_reason=pos['exit_reason']
                )

        # Next day
        current += timedelta(days=1)

    # Final results
    print("\n" + "=" * 80)
    print("📊 BACKTEST RESULTS")
    print("=" * 80)

    summary = pm.get_summary()
    closed = pm.portfolio['closed']

    if not closed:
        print("\n⚠️  No closed trades - period may be too short or no opportunities found")
        return

    # Calculate metrics
    winners = [t for t in closed if t['return_pct'] > 0]
    losers = [t for t in closed if t['return_pct'] <= 0]

    total_trades = len(closed)
    win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0

    avg_win = sum(t['return_pct'] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t['return_pct'] for t in losers) / len(losers) if losers else 0

    total_return = sum(t['return_usd'] for t in closed)
    total_win = sum(t['return_usd'] for t in winners)
    total_loss = sum(t['return_usd'] for t in losers)

    # Exit reason breakdown
    exit_reasons = {}
    for t in closed:
        reason = t['exit_reason']
        if reason not in exit_reasons:
            exit_reasons[reason] = {'count': 0, 'pnl': 0}
        exit_reasons[reason]['count'] += 1
        exit_reasons[reason]['pnl'] += t['return_pct']

    print(f"\n📈 Performance Summary:")
    print(f"   Total Trades: {total_trades}")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}W / {len(losers)}L)")
    print(f"   Avg Win: +{avg_win:.2f}%")
    print(f"   Avg Loss: {avg_loss:.2f}%")
    print(f"   R:R Ratio: {abs(avg_win/avg_loss):.2f}:1" if avg_loss != 0 else "   R:R Ratio: N/A")
    print()
    print(f"   Total P&L: ${total_return:.2f}")
    print(f"   Total Wins: ${total_win:.2f}")
    print(f"   Total Losses: ${total_loss:.2f}")
    print(f"   Loss Impact: {abs(total_loss/total_win*100):.1f}%" if total_win > 0 else "   Loss Impact: N/A")
    print()
    print(f"   Avg Hold Time: {sum(t['days_held'] for t in closed)/len(closed):.1f} days")

    # Exit reasons
    print(f"\n🚪 Exit Reasons:")
    for reason, data in sorted(exit_reasons.items(), key=lambda x: x[1]['count'], reverse=True):
        avg_pnl = data['pnl'] / data['count']
        print(f"   {reason:25} {data['count']:3} trades @ {avg_pnl:+6.2f}% avg")

    # Top wins/losses
    print(f"\n🏆 Top 5 Winners:")
    for i, trade in enumerate(sorted(winners, key=lambda x: x['return_pct'], reverse=True)[:5], 1):
        print(f"   {i}. {trade['symbol']:6} +{trade['return_pct']:5.2f}% "
              f"(${trade['return_usd']:6.2f}, {trade['days_held']:2}d, {trade['exit_reason']})")

    print(f"\n💔 Top 5 Losers:")
    for i, trade in enumerate(sorted(losers, key=lambda x: x['return_pct'])[:5], 1):
        print(f"   {i}. {trade['symbol']:6} {trade['return_pct']:6.2f}% "
              f"(${trade['return_usd']:6.2f}, {trade['days_held']:2}d, {trade['exit_reason']})")

    # Rule performance (if available)
    if screener.screening_rules:
        print(f"\n📊 Screening Rules Performance (Top 10):")
        stats = screener.get_screening_rules_stats()
        for i, stat in enumerate(stats[:10], 1):
            print(f"   {i:2}. {stat['name']:25} Pass Rate: {stat['pass_rate']:6} | Eval: {stat['evaluated']:4}")

    if pm.exit_rules:
        print(f"\n📊 Exit Rules Performance:")
        stats = pm.get_exit_rules_stats()
        # Show rules that actually fired
        fired_stats = [s for s in stats if s['fired_count'] > 0]
        for stat in sorted(fired_stats, key=lambda x: x['fired_count'], reverse=True):
            print(f"   {stat['name']:25} Fired: {stat['fired_count']:3} times")

    print("\n" + "=" * 80)

    # Detailed trade log
    print(f"\n📋 Detailed Trade Log:")
    print(f"{'Date':12} {'Symbol':8} {'Entry':8} {'Exit':8} {'Return':8} {'Days':5} {'Reason':20}")
    print("-" * 90)
    for trade in closed:
        print(f"{trade['entry_date']:12} {trade['symbol']:8} "
              f"${trade['entry_price']:7.2f} ${trade['exit_price']:7.2f} "
              f"{trade['return_pct']:+7.2f}% {trade['days_held']:4}d {trade['exit_reason']:20}")

    # Save results
    results = {
        'period': {'start': start_date, 'end': end_date},
        'metrics': {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_return': total_return,
            'loss_impact': abs(total_loss/total_win*100) if total_win > 0 else 0
        },
        'trades': closed
    }

    with open('backtest_v4_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to backtest_v4_results.json")


if __name__ == "__main__":
    # Backtest last 30 days (faster)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    print(f"\n🎯 Starting Complete System Backtest v4.0")
    print(f"   Screening: Growth Catalyst v4.0 (Rule-Based)")
    print(f"   Portfolio: Portfolio Manager v3 (Rule-Based Exits)")
    print(f"   Period: Last 30 days")
    print()

    backtest_complete_system(start_date, end_date, max_positions=5)
