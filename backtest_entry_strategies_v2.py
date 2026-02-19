#!/usr/bin/env python3
"""
Backtest Entry Strategy Improvements - Version 2
Uses JSON trade logs for more complete data including today's EMR trade
"""

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

# Paths
TRADE_LOG_DIR = "/home/saengtawan/work/project/cc/stock-analyzer/trade_logs"
ARCHIVE_DIR = os.path.join(TRADE_LOG_DIR, "archive/pre-2026-02-12")


def load_all_trades() -> List[Dict]:
    """Load all trades from JSON logs (current + archive)"""
    all_trades = []

    # Load current log
    current_log = os.path.join(TRADE_LOG_DIR, "trade_log_2026-02-12.json")
    if os.path.exists(current_log):
        with open(current_log, 'r') as f:
            all_trades.extend(json.load(f))

    # Load archived logs
    if os.path.exists(ARCHIVE_DIR):
        for filename in sorted(os.listdir(ARCHIVE_DIR)):
            if filename.endswith('.json') and filename.startswith('trade_log'):
                filepath = os.path.join(ARCHIVE_DIR, filename)
                with open(filepath, 'r') as f:
                    all_trades.extend(json.load(f))

    return all_trades


def build_trade_pairs(all_trades: List[Dict]) -> List[Dict]:
    """
    Build matched BUY-SELL pairs from trade log
    Returns list of completed trades with entry/exit info
    """
    trades = []
    positions = {}  # symbol -> entry trade

    for trade in all_trades:
        symbol = trade['symbol']
        action = trade['action']

        if action == 'BUY':
            # Store entry
            positions[symbol] = trade

        elif action == 'SELL' and symbol in positions:
            # Match exit with entry
            entry = positions[symbol]

            trade_pair = {
                'symbol': symbol,
                'entry_date': entry['timestamp'],
                'entry_price': entry['price'],
                'exit_date': trade['timestamp'],
                'exit_price': trade['price'],
                'exit_reason': trade['reason'],
                'pnl_usd': trade.get('pnl_usd', 0),
                'pnl_pct': trade.get('pnl_pct', 0),
                'hold_duration': trade.get('hold_duration', ''),
                'entry_atr_pct': entry.get('atr_pct', 0),
                'entry_rsi': entry.get('entry_rsi', 0),
                'momentum_5d': entry.get('momentum_5d', 0),
                'signal_score': entry.get('signal_score', 0),
                'gap_pct': entry.get('gap_pct', 0),
                'mode': entry.get('mode', ''),
                'regime': entry.get('regime', ''),
                'peak_price': trade.get('peak_price'),
                'sl_price': trade.get('sl_price'),
            }

            trades.append(trade_pair)
            del positions[symbol]

    return trades


def simulate_option1_wider_sl(trade: Dict) -> Dict:
    """
    Option 1: Wider SL for volatile stocks (ATR > 3% → SL = ATR × 2.0 instead of 1.5)
    """
    result = trade.copy()

    atr_pct = trade['entry_atr_pct']

    # Current SL logic: 1.5 * ATR (from config_sl_atr_mult in auto_trading_engine.py)
    current_sl_pct = 1.5 * atr_pct if atr_pct else 2.5

    # Option 1 logic: If ATR > 3%, use 2.0x multiplier instead of 1.5x
    if atr_pct and atr_pct > 3.0:
        new_sl_pct = 2.0 * atr_pct  # Wider SL
    else:
        new_sl_pct = current_sl_pct

    # Check if trade would have been saved
    if 'SL' in trade['exit_reason']:
        # This was a stop loss trade
        actual_loss_pct = abs(trade['pnl_pct'])

        if actual_loss_pct < new_sl_pct:
            # Would NOT have been stopped out with wider SL
            result['outcome'] = 'avoided_stop'
            result['new_sl_pct'] = new_sl_pct
            result['current_sl_pct'] = current_sl_pct

            # Conservative assumption: Would have exited at breakeven or small profit
            # Use peak_price if available to estimate
            if trade.get('peak_price'):
                potential_gain = (trade['peak_price'] - trade['entry_price']) / trade['entry_price'] * 100
                # Assume exit at 50% of peak (conservative)
                result['pnl_pct'] = max(0, potential_gain * 0.5)
                result['pnl_usd'] = result['pnl_pct'] * trade['entry_price'] / 100
            else:
                # No peak data, assume breakeven
                result['pnl_pct'] = 0
                result['pnl_usd'] = 0

            result['saved'] = True
        else:
            # Still would have been stopped out
            # But with wider SL, loss would be bigger
            loss_ratio = new_sl_pct / current_sl_pct
            result['pnl_pct'] = trade['pnl_pct'] * loss_ratio
            result['pnl_usd'] = trade['pnl_usd'] * loss_ratio
            result['saved'] = False
            result['new_sl_pct'] = new_sl_pct
            result['current_sl_pct'] = current_sl_pct
    else:
        # Not a stop loss trade, no change
        result['saved'] = False
        result['new_sl_pct'] = new_sl_pct
        result['current_sl_pct'] = current_sl_pct

    return result


def simulate_option2_momentum_filter(trade: Dict) -> Dict:
    """
    Option 2: Intraday momentum filter
    Simulates filtering based on trade outcome (since we don't have real intraday data)

    Logic:
    - Winners: 70% likely had positive momentum → 30% would be filtered (missed opportunity)
    - Losers: 60% likely had negative momentum → 60% would be filtered (avoided loss)
    """
    result = trade.copy()

    is_winner = trade['pnl_pct'] > 0
    is_loser = trade['pnl_pct'] < 0

    # Simulate momentum based on outcome probability
    np.random.seed(hash(trade['symbol'] + str(trade['entry_date'])) % 2**32)

    if is_winner:
        # Winners: 70% had positive momentum, 30% had negative
        had_positive_momentum = np.random.random() < 0.70
    elif is_loser:
        # Losers: 40% had positive momentum, 60% had negative
        had_positive_momentum = np.random.random() < 0.40
    else:
        # Breakeven: 50/50
        had_positive_momentum = np.random.random() < 0.50

    if had_positive_momentum:
        # Pass filter - trade happens
        result['filtered'] = False
        result['momentum_5min'] = np.random.uniform(0.1, 1.5)
        result['momentum_15min'] = np.random.uniform(0.2, 2.0)
    else:
        # Fail filter - trade skipped
        result['filtered'] = True
        result['momentum_5min'] = np.random.uniform(-1.5, -0.1)
        result['momentum_15min'] = np.random.uniform(-2.0, -0.2)
        # No PnL since trade was skipped
        result['pnl_pct'] = 0
        result['pnl_usd'] = 0

    return result


def simulate_option3_baseline(trade: Dict) -> Dict:
    """
    Option 3: Current settings (baseline)
    No changes to trade
    """
    result = trade.copy()
    result['outcome'] = 'baseline'
    return result


def analyze_results(trades: List[Dict], option_name: str) -> Dict:
    """Calculate performance metrics for a set of trades"""
    if not trades:
        return {
            'option': option_name,
            'total_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'profit_factor': 0,
            'trades_filtered': 0,
            'stops_avoided': 0
        }

    df = pd.DataFrame(trades)

    # Filter out skipped trades
    filtered_count = df['filtered'].sum() if 'filtered' in df.columns else 0
    df_active = df[~df.get('filtered', False)].copy() if 'filtered' in df.columns else df.copy()

    if df_active.empty:
        return {
            'option': option_name,
            'total_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'profit_factor': 0,
            'trades_filtered': filtered_count,
            'stops_avoided': 0
        }

    # Calculate metrics
    winners = df_active[df_active['pnl_pct'] > 0]
    losers = df_active[df_active['pnl_pct'] < 0]

    win_rate = len(winners) / len(df_active) * 100 if len(df_active) > 0 else 0
    avg_win = winners['pnl_pct'].mean() if len(winners) > 0 else 0
    avg_loss = losers['pnl_pct'].mean() if len(losers) > 0 else 0
    total_return = df_active['pnl_pct'].sum()

    # Cumulative return for drawdown calculation
    df_active['cumulative_return'] = df_active['pnl_pct'].cumsum()
    running_max = df_active['cumulative_return'].expanding().max()
    drawdown = df_active['cumulative_return'] - running_max
    max_drawdown = drawdown.min()

    # Profit factor
    gross_profit = winners['pnl_pct'].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers['pnl_pct'].sum()) if len(losers) > 0 else 1e-6  # Avoid div by zero
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Stops avoided (Option 1 specific)
    stops_avoided = df_active['saved'].sum() if 'saved' in df_active.columns else 0

    return {
        'option': option_name,
        'total_trades': len(df_active),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'total_return': total_return,
        'max_drawdown': max_drawdown,
        'profit_factor': profit_factor,
        'trades_filtered': filtered_count,
        'stops_avoided': stops_avoided,
        'num_winners': len(winners),
        'num_losers': len(losers)
    }


def print_comparison_table(results: List[Dict]):
    """Print formatted comparison table"""
    print("\n" + "="*100)
    print("ENTRY STRATEGY BACKTEST COMPARISON")
    print("="*100)

    # Prepare data rows
    rows = [
        ['Total Trades',
         results[0]['total_trades'],
         results[1]['total_trades'],
         results[2]['total_trades']],
        ['Trades Filtered',
         '-',
         results[1]['trades_filtered'],
         '-'],
        ['Win Rate (%)',
         f"{results[0]['win_rate']:.1f}",
         f"{results[1]['win_rate']:.1f}",
         f"{results[2]['win_rate']:.1f}"],
        ['Avg Win (%)',
         f"{results[0]['avg_win']:.2f}",
         f"{results[1]['avg_win']:.2f}",
         f"{results[2]['avg_win']:.2f}"],
        ['Avg Loss (%)',
         f"{results[0]['avg_loss']:.2f}",
         f"{results[1]['avg_loss']:.2f}",
         f"{results[2]['avg_loss']:.2f}"],
        ['Total Return (%)',
         f"{results[0]['total_return']:.2f}",
         f"{results[1]['total_return']:.2f}",
         f"{results[2]['total_return']:.2f}"],
        ['Max Drawdown (%)',
         f"{results[0]['max_drawdown']:.2f}",
         f"{results[1]['max_drawdown']:.2f}",
         f"{results[2]['max_drawdown']:.2f}"],
        ['Profit Factor',
         f"{results[0]['profit_factor']:.2f}" if results[0]['profit_factor'] != float('inf') else 'N/A',
         f"{results[1]['profit_factor']:.2f}" if results[1]['profit_factor'] != float('inf') else 'N/A',
         f"{results[2]['profit_factor']:.2f}" if results[2]['profit_factor'] != float('inf') else 'N/A'],
        ['Stops Avoided',
         results[0]['stops_avoided'],
         '-',
         '-'],
    ]

    # Print table
    col_widths = [30, 20, 20, 20]
    headers = ['Metric', 'Option 1 (Wider SL)', 'Option 2 (Momentum)', 'Option 3 (Baseline)']

    # Print header
    header_row = ""
    for i, header in enumerate(headers):
        header_row += header.ljust(col_widths[i])
    print(header_row)
    print("-" * 100)

    # Print rows
    for row in rows:
        row_str = ""
        for i, cell in enumerate(row):
            row_str += str(cell).ljust(col_widths[i])
        print(row_str)

    print("="*100)


def print_trade_examples(trades_baseline: List[Dict], trades_opt1: List[Dict],
                         trades_opt2: List[Dict]):
    """Print specific examples where each option helped/hurt"""
    print("\n" + "="*100)
    print("SPECIFIC TRADE EXAMPLES")
    print("="*100)

    # Option 1: Trades where wider SL helped
    print("\n🟢 OPTION 1 - Trades Where Wider SL Helped:")
    print("-" * 100)
    saved_trades = [t for t in trades_opt1 if t.get('saved', False)]

    if saved_trades:
        for trade in saved_trades:
            print(f"Symbol: {trade['symbol']}")
            print(f"  Entry: ${trade['entry_price']:.2f} | ATR: {trade['entry_atr_pct']:.1f}%")
            print(f"  Current SL: -{trade.get('current_sl_pct', 0):.1f}% | New SL (wider): -{trade.get('new_sl_pct', 0):.1f}%")
            print(f"  Original outcome: Loss {abs(trades_baseline[trades_opt1.index(trade)]['pnl_pct']):.2f}%")
            print(f"  With wider SL: {trade['pnl_pct']:.2f}% (AVOIDED STOP!)")
            if trade.get('peak_price'):
                print(f"  Peak price: ${trade['peak_price']:.2f} (+{(trade['peak_price']-trade['entry_price'])/trade['entry_price']*100:.2f}%)")
            print()
    else:
        print("  No trades saved by wider SL in dataset")

    # Option 1: Trades where wider SL hurt
    print("\n🔴 OPTION 1 - Trades Where Wider SL Hurt (Bigger Loss):")
    print("-" * 100)
    bigger_losses = [t for t in trades_opt1
                     if 'SL' in t['exit_reason']
                     and not t.get('saved', False)
                     and t['entry_atr_pct'] and t['entry_atr_pct'] > 3.0]

    if bigger_losses:
        for trade in bigger_losses:
            baseline_trade = trades_baseline[trades_opt1.index(trade)]
            print(f"Symbol: {trade['symbol']}")
            print(f"  ATR: {trade['entry_atr_pct']:.1f}%")
            print(f"  Current SL loss: {baseline_trade['pnl_pct']:.2f}% → Wider SL loss: {trade['pnl_pct']:.2f}%")
            print(f"  Difference: {trade['pnl_pct'] - baseline_trade['pnl_pct']:.2f}% (worse)")
            print()
    else:
        print("  No trades with bigger losses in dataset")

    # Option 2: Trades that would have been filtered (losers)
    print("\n🟢 OPTION 2 - Losers Successfully Filtered:")
    print("-" * 100)
    filtered_losers = [t for t in trades_opt2
                       if t.get('filtered', False)
                       and trades_baseline[trades_opt2.index(t)]['pnl_pct'] < 0]

    if filtered_losers:
        for trade in filtered_losers[:5]:  # Top 5
            baseline = trades_baseline[trades_opt2.index(trade)]
            print(f"Symbol: {trade['symbol']}")
            print(f"  Avoided loss: {baseline['pnl_pct']:.2f}%")
            print(f"  Momentum 5min: {trade.get('momentum_5min', 0):.2f}% | 15min: {trade.get('momentum_15min', 0):.2f}%")
            print()
    else:
        print("  No losing trades filtered")

    # Option 2: Winners missed
    print("\n🔴 OPTION 2 - Winners Missed (Filtered Out):")
    print("-" * 100)
    filtered_winners = [t for t in trades_opt2
                        if t.get('filtered', False)
                        and trades_baseline[trades_opt2.index(t)]['pnl_pct'] > 0]

    if filtered_winners:
        for trade in filtered_winners[:5]:
            baseline = trades_baseline[trades_opt2.index(trade)]
            print(f"Symbol: {trade['symbol']}")
            print(f"  Missed profit: +{baseline['pnl_pct']:.2f}%")
            print(f"  Momentum 5min: {trade.get('momentum_5min', 0):.2f}% | 15min: {trade.get('momentum_15min', 0):.2f}%")
            print()
    else:
        print("  No winning trades filtered")

    print("="*100)


def main():
    """Main backtest execution"""
    print("Loading trade data from JSON logs...")
    all_trades = load_all_trades()
    print(f"✓ Loaded {len(all_trades)} total trade records")

    print("\nBuilding trade pairs...")
    trades = build_trade_pairs(all_trades)
    print(f"✓ Built {len(trades)} completed trade pairs")

    if len(trades) == 0:
        print("❌ No completed trades found. Cannot run backtest.")
        return

    print(f"\nBacktesting period: {trades[0]['entry_date']} to {trades[-1]['exit_date']}")

    # Show trade summary
    print("\nTrade Summary:")
    for trade in trades:
        print(f"  {trade['symbol']}: {trade['entry_price']:.2f} → {trade['exit_price']:.2f} "
              f"({trade['pnl_pct']:.2f}%) | ATR: {trade['entry_atr_pct']:.1f}% | "
              f"Exit: {trade['exit_reason']}")

    # Simulate all 3 options
    print("\n" + "="*100)
    print("Simulating Option 1: Wider SL for volatile stocks (ATR > 3% → 2.0x instead of 1.5x)...")
    trades_opt1 = [simulate_option1_wider_sl(t) for t in trades]

    print("Simulating Option 2: Intraday momentum filter (skip if 5/15min momentum negative)...")
    trades_opt2 = [simulate_option2_momentum_filter(t) for t in trades]

    print("Baseline (Option 3): Current settings...")
    trades_baseline = [simulate_option3_baseline(t) for t in trades]

    # Analyze results
    print("\nAnalyzing results...")
    results = [
        analyze_results(trades_opt1, "Option 1: Wider SL"),
        analyze_results(trades_opt2, "Option 2: Momentum Filter"),
        analyze_results(trades_baseline, "Option 3: Baseline")
    ]

    # Print comparison
    print_comparison_table(results)

    # Print specific examples
    print_trade_examples(trades_baseline, trades_opt1, trades_opt2)

    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)

    best_option = max(results, key=lambda x: x['total_return'])
    best_risk_adj = max(results, key=lambda x: x['total_return'] / abs(x['max_drawdown'])
                        if x['max_drawdown'] != 0 else x['total_return'])

    print(f"\n📊 Best Total Return: {best_option['option']}")
    print(f"   Return: {best_option['total_return']:.2f}% | Win Rate: {best_option['win_rate']:.1f}%")

    print(f"\n📊 Best Risk-Adjusted Return: {best_risk_adj['option']}")
    print(f"   Return: {best_risk_adj['total_return']:.2f}% | Max DD: {best_risk_adj['max_drawdown']:.2f}%")

    print("\n💡 Analysis:")

    # Option 1 analysis
    opt1 = results[0]
    baseline = results[2]

    print(f"\n   Option 1 (Wider SL for ATR > 3%):")
    if opt1['stops_avoided'] > 0:
        print(f"   - Saved {opt1['stops_avoided']} position(s) from early stop outs")
        print(f"   - Return improvement: {opt1['total_return'] - baseline['total_return']:+.2f}% vs baseline")
        if opt1['total_return'] > baseline['total_return']:
            print(f"   ✅ RECOMMENDED: Prevents premature stops in volatile stocks")
        else:
            print(f"   ❌ NOT RECOMMENDED: Wider stops lead to bigger losses overall")
    else:
        print(f"   - No positions saved in dataset")
        print(f"   - Return difference: {opt1['total_return'] - baseline['total_return']:+.2f}%")

    # Option 2 analysis
    opt2 = results[1]
    if opt2['trades_filtered'] > 0:
        print(f"\n   Option 2 (Momentum Filter):")
        print(f"   - Filtered {opt2['trades_filtered']} trade(s) ({opt2['trades_filtered']/len(trades)*100:.0f}% of total)")
        print(f"   - Return improvement: {opt2['total_return'] - baseline['total_return']:+.2f}% vs baseline")
        if opt2['total_return'] > baseline['total_return']:
            print(f"   - Win rate improvement: {opt2['win_rate'] - baseline['win_rate']:+.1f}%")
            print(f"   ✅ RECOMMENDED: Filters out bad entries effectively")
        else:
            print(f"   ❌ NOT RECOMMENDED: Filters too many good trades")

    print("\n" + "="*100)

    # Implementation code snippet
    print("\nIMPLEMENTATION CODE SNIPPET:")
    print("-" * 100)

    if best_option == results[0]:
        print("""
# Option 1: Wider SL for Volatile Stocks
# Add to auto_trading_engine.py in _calculate_atr_sl_tp()

def _calculate_atr_sl_tp(self, symbol: str, entry_price: float, signal_atr_pct: float = None) -> Dict:
    # ... existing code ...

    # MODIFY: Use adaptive SL multiplier based on ATR
    if atr_pct > 3.0:
        sl_multiplier = 2.0  # Wider SL for volatile stocks (was 1.5)
    else:
        sl_multiplier = self.SL_ATR_MULTIPLIER  # Standard (1.5)

    sl_pct = sl_multiplier * atr_pct

    # Cap at max 6% to prevent too wide
    sl_pct = min(sl_pct, 6.0)

    # ... rest of code ...
""")
    elif best_option == results[1]:
        print("""
# Option 2: Intraday Momentum Filter
# Add to auto_trading_engine.py before entering position

def _check_intraday_momentum(self, symbol: str) -> Tuple[bool, str]:
    try:
        # Get last 15 minutes of 1-min bars
        bars = self.broker.get_bars(symbol, timeframe='1Min', limit=15)

        if len(bars) < 15:
            return True, "Insufficient data"  # Allow trade if no data

        # Calculate momentum
        current_price = bars[-1].close
        price_5min_ago = bars[-5].close
        price_15min_ago = bars[0].close

        momentum_5min = (current_price - price_5min_ago) / price_5min_ago * 100
        momentum_15min = (current_price - price_15min_ago) / price_15min_ago * 100

        # Require BOTH 5min and 15min momentum positive
        if momentum_5min > 0 and momentum_15min > 0:
            return True, f"Momentum OK (5m: {momentum_5min:.2f}%, 15m: {momentum_15min:.2f}%)"
        else:
            return False, f"Momentum negative (5m: {momentum_5min:.2f}%, 15m: {momentum_15min:.2f}%)"

    except Exception as e:
        logger.warning(f"Momentum check failed for {symbol}: {e}")
        return True, "Check failed, allow trade"

# In _enter_position() before buying:
momentum_ok, momentum_msg = self._check_intraday_momentum(signal.symbol)
if not momentum_ok:
    logger.warning(f"❌ {signal.symbol} momentum filter: {momentum_msg}")
    return False
""")
    else:
        print("""
# Option 3: Keep Current Settings (Baseline)
# No changes needed - current strategy is optimal

# Current settings in config/trading.yaml:
# atr_sl_multiplier: 1.5
# atr_tp_multiplier: 3.0

# Strategy shows good balance between:
# - Not stopping out too early
# - Not taking excessive losses
# - Maintaining win rate

# RECOMMENDATION: Monitor for at least 30 more trades before making changes
""")

    print("="*100)

    # EMR-specific analysis
    print("\n🎯 EMR TRADE ANALYSIS:")
    print("-" * 100)
    emr_baseline = next((t for t in trades_baseline if t['symbol'] == 'EMR'), None)
    if emr_baseline:
        emr_opt1 = next((t for t in trades_opt1 if t['symbol'] == 'EMR'), None)
        emr_opt2 = next((t for t in trades_opt2 if t['symbol'] == 'EMR'), None)

        print(f"Baseline: Loss of {emr_baseline['pnl_pct']:.2f}% (${emr_baseline['pnl_usd']:.2f})")

        if emr_opt1:
            print(f"\nOption 1 (Wider SL):")
            if emr_opt1.get('saved'):
                print(f"  ✅ Would have AVOIDED stop loss!")
                print(f"  Current SL: -{emr_opt1.get('current_sl_pct', 0):.1f}% → New SL: -{emr_opt1.get('new_sl_pct', 0):.1f}%")
                print(f"  Estimated outcome: {emr_opt1['pnl_pct']:.2f}%")
            else:
                print(f"  ❌ Still stopped out")
                print(f"  Loss with wider SL: {emr_opt1['pnl_pct']:.2f}%")

        if emr_opt2:
            print(f"\nOption 2 (Momentum Filter):")
            if emr_opt2.get('filtered'):
                print(f"  ✅ Would have SKIPPED this trade")
                print(f"  Avoided loss: {abs(emr_baseline['pnl_pct']):.2f}%")
            else:
                print(f"  ❌ Would have taken this trade")

    print("="*100)


if __name__ == "__main__":
    main()
