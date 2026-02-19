#!/usr/bin/env python3
"""
Backtest Entry Strategy Improvements
Tests 3 options for improving entry timing and stop loss placement
"""

import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import yfinance as yf
from collections import defaultdict

# Database path
DB_PATH = "/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db"


def load_trades() -> pd.DataFrame:
    """Load all trades from database"""
    conn = sqlite3.connect(DB_PATH)

    # Get all buy and sell trades
    query = """
        SELECT
            id, timestamp, date, action, symbol, qty, price, reason,
            entry_price, pnl_usd, pnl_pct, hold_duration, day_held,
            mode, regime, signal_score, gap_pct, atr_pct, full_data
        FROM trades
        WHERE action IN ('BUY', 'SELL')
        ORDER BY timestamp
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # Parse timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Parse full_data JSON
    def safe_parse_json(x):
        if pd.isna(x) or x == '':
            return {}
        try:
            return json.loads(x)
        except:
            return {}

    df['full_data_dict'] = df['full_data'].apply(safe_parse_json)

    # Extract additional fields from full_data
    df['entry_rsi'] = df['full_data_dict'].apply(lambda x: x.get('entry_rsi', None))
    df['momentum_5d'] = df['full_data_dict'].apply(lambda x: x.get('momentum_5d', None))
    df['peak_price'] = df['full_data_dict'].apply(lambda x: x.get('peak_price', None))
    df['sl_price'] = df['full_data_dict'].apply(lambda x: x.get('sl_price', None))

    return df


def build_trade_pairs(df: pd.DataFrame) -> List[Dict]:
    """
    Build matched BUY-SELL pairs from trade log
    Returns list of completed trades with entry/exit info
    """
    trades = []
    positions = {}  # symbol -> entry trade

    for idx, row in df.iterrows():
        symbol = row['symbol']

        if row['action'] == 'BUY':
            # Store entry
            positions[symbol] = {
                'entry_date': row['timestamp'],
                'entry_price': row['price'],
                'entry_atr_pct': row['atr_pct'],
                'entry_rsi': row['entry_rsi'],
                'momentum_5d': row['momentum_5d'],
                'signal_score': row['signal_score'],
                'gap_pct': row['gap_pct'],
                'mode': row['mode'],
                'regime': row['regime'],
                'qty': row['qty'],
                'full_data': row['full_data_dict']
            }

        elif row['action'] == 'SELL' and symbol in positions:
            # Match exit with entry
            entry = positions[symbol]

            trade = {
                'symbol': symbol,
                'entry_date': entry['entry_date'],
                'entry_price': entry['entry_price'],
                'exit_date': row['timestamp'],
                'exit_price': row['price'],
                'exit_reason': row['reason'],
                'pnl_usd': row['pnl_usd'],
                'pnl_pct': row['pnl_pct'],
                'hold_duration': row['hold_duration'],
                'day_held': row['day_held'],
                'entry_atr_pct': entry['entry_atr_pct'],
                'entry_rsi': entry['entry_rsi'],
                'momentum_5d': entry['momentum_5d'],
                'signal_score': entry['signal_score'],
                'gap_pct': entry['gap_pct'],
                'mode': entry['mode'],
                'regime': entry['regime'],
                'qty': entry['qty'],
                'full_data': entry['full_data']
            }

            trades.append(trade)
            del positions[symbol]

    return trades


def get_intraday_data(symbol: str, date: datetime, minutes_before: int = 60) -> pd.DataFrame:
    """
    Fetch intraday price data for momentum analysis
    Returns 1-min bars for the specified period
    """
    try:
        ticker = yf.Ticker(symbol)

        # Get intraday data (1 minute bars)
        start = date - timedelta(days=1)
        end = date + timedelta(hours=2)

        df = ticker.history(start=start, end=end, interval='1m')

        if df.empty:
            return None

        return df

    except Exception as e:
        print(f"  ⚠️  Failed to fetch intraday data for {symbol}: {e}")
        return None


def calculate_intraday_momentum(price_data: pd.DataFrame, entry_time: datetime) -> Dict:
    """
    Calculate 5-min and 15-min momentum at entry time
    Returns dict with momentum values (None if data unavailable)
    """
    if price_data is None or price_data.empty:
        return {'momentum_5min': None, 'momentum_15min': None}

    try:
        # Find closest timestamp to entry
        entry_idx = price_data.index.get_indexer([entry_time], method='nearest')[0]

        if entry_idx < 15:
            return {'momentum_5min': None, 'momentum_15min': None}

        current_price = price_data['Close'].iloc[entry_idx]
        price_5min_ago = price_data['Close'].iloc[max(0, entry_idx - 5)]
        price_15min_ago = price_data['Close'].iloc[max(0, entry_idx - 15)]

        momentum_5min = (current_price - price_5min_ago) / price_5min_ago * 100
        momentum_15min = (current_price - price_15min_ago) / price_15min_ago * 100

        return {
            'momentum_5min': momentum_5min,
            'momentum_15min': momentum_15min
        }

    except Exception as e:
        return {'momentum_5min': None, 'momentum_15min': None}


def simulate_option1_wider_sl(trade: Dict) -> Dict:
    """
    Option 1: Wider SL for volatile stocks (ATR > 3% → SL = ATR * 1.5)
    Returns modified trade outcome
    """
    result = trade.copy()

    atr_pct = trade['entry_atr_pct']

    # Current SL logic: 1.5 * ATR (from config_sl_atr_mult)
    current_sl_pct = 1.5 * atr_pct if atr_pct else 2.5

    # Option 1 logic: If ATR > 3%, use wider SL (2.0 * ATR instead of 1.5)
    if atr_pct and atr_pct > 3.0:
        new_sl_pct = 2.0 * atr_pct  # Wider SL
    else:
        new_sl_pct = current_sl_pct

    # Check if trade would have been saved
    if trade['exit_reason'] == 'SL_FILLED_AT_ALPACA':
        # Calculate if wider SL would have avoided stop out
        actual_drawdown = abs(trade['pnl_pct'])

        if actual_drawdown < new_sl_pct:
            # Would NOT have been stopped out
            result['outcome'] = 'avoided_stop'
            result['new_sl_pct'] = new_sl_pct
            result['pnl_pct'] = 0  # Assume breakeven or small profit (conservative)
            result['pnl_usd'] = 0
            result['saved'] = True
        else:
            # Still would have been stopped out
            # But with wider SL, loss would be bigger
            loss_ratio = new_sl_pct / current_sl_pct
            result['pnl_pct'] = trade['pnl_pct'] * loss_ratio
            result['pnl_usd'] = trade['pnl_usd'] * loss_ratio
            result['saved'] = False
    else:
        # Not a stop loss trade, no change
        result['saved'] = False
        result['new_sl_pct'] = new_sl_pct

    return result


def simulate_option2_momentum_filter(trade: Dict, use_simulated: bool = False) -> Dict:
    """
    Option 2: Intraday momentum filter (skip if price not rising on 5/15min)
    Returns modified trade outcome

    Args:
        trade: Trade dict
        use_simulated: If True, simulate momentum based on outcome (for testing without API calls)
    """
    result = trade.copy()

    if use_simulated:
        # Simulate momentum based on outcome
        # Winners: 70% likely had positive momentum
        # Losers: 50% likely had negative momentum
        is_winner = trade['pnl_pct'] > 0

        if is_winner:
            momentum_5min = np.random.choice([0.5, -0.3], p=[0.7, 0.3])
            momentum_15min = np.random.choice([0.8, -0.4], p=[0.7, 0.3])
        else:
            momentum_5min = np.random.choice([0.5, -0.3], p=[0.3, 0.7])
            momentum_15min = np.random.choice([0.8, -0.4], p=[0.3, 0.7])
    else:
        # TODO: Fetch real intraday data (requires API)
        # For now, use conservative simulation
        momentum_5min = None
        momentum_15min = None

    # Apply filter: Require both 5min and 15min momentum > 0
    if momentum_5min is not None and momentum_15min is not None:
        if momentum_5min > 0 and momentum_15min > 0:
            # Pass filter - trade happens
            result['filtered'] = False
            result['momentum_5min'] = momentum_5min
            result['momentum_15min'] = momentum_15min
        else:
            # Fail filter - trade skipped
            result['filtered'] = True
            result['momentum_5min'] = momentum_5min
            result['momentum_15min'] = momentum_15min
            result['pnl_pct'] = 0
            result['pnl_usd'] = 0
    else:
        # No momentum data, assume trade happens
        result['filtered'] = False
        result['momentum_5min'] = None
        result['momentum_15min'] = None

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
    df = pd.DataFrame(trades)

    if df.empty:
        return {
            'option': option_name,
            'total_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'profit_factor': 0,
            'trades_filtered': 0
        }

    # Filter out skipped trades
    filtered_count = df['filtered'].sum() if 'filtered' in df.columns else 0
    df_active = df[~df.get('filtered', False)] if 'filtered' in df.columns else df

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
            'trades_filtered': filtered_count
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
    gross_loss = abs(losers['pnl_pct'].sum()) if len(losers) > 0 else 0
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

    headers = ['Metric', 'Option 1 (Wider SL)', 'Option 2 (Momentum)', 'Option 3 (Baseline)']

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
         f"{results[0]['profit_factor']:.2f}",
         f"{results[1]['profit_factor']:.2f}",
         f"{results[2]['profit_factor']:.2f}"],
        ['Stops Avoided',
         results[0]['stops_avoided'],
         '-',
         '-'],
    ]

    # Print table
    col_widths = [30, 20, 20, 20]

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
        for trade in saved_trades[:3]:  # Show top 3
            print(f"Symbol: {trade['symbol']}")
            print(f"  Entry: ${trade['entry_price']:.2f} | ATR: {trade['entry_atr_pct']:.1f}%")
            print(f"  Old SL: -{1.5 * trade['entry_atr_pct']:.1f}% | New SL: -{trade.get('new_sl_pct', 0):.1f}%")
            print(f"  Actual DD: {abs(trade['pnl_pct']):.1f}% → Would have avoided stop loss")
            print()
    else:
        print("  No trades saved by wider SL in dataset")

    # Option 1: Trades where wider SL hurt
    print("\n🔴 OPTION 1 - Trades Where Wider SL Hurt (Bigger Loss):")
    print("-" * 100)
    bigger_losses = [t for t in trades_opt1
                     if t['exit_reason'] == 'SL_FILLED_AT_ALPACA'
                     and not t.get('saved', False)
                     and t['entry_atr_pct'] and t['entry_atr_pct'] > 3.0]

    if bigger_losses:
        for trade in bigger_losses[:3]:
            baseline_loss = next((t['pnl_pct'] for t in trades_baseline if t['symbol'] == trade['symbol']), 0)
            print(f"Symbol: {trade['symbol']}")
            print(f"  Baseline Loss: {baseline_loss:.2f}% → Option 1 Loss: {trade['pnl_pct']:.2f}%")
            print(f"  Difference: {trade['pnl_pct'] - baseline_loss:.2f}% (worse)")
            print()
    else:
        print("  No trades with bigger losses in dataset")

    # Option 2: Trades that would have been filtered
    print("\n🟡 OPTION 2 - Trades Filtered by Momentum (Winners Missed):")
    print("-" * 100)
    filtered_winners = [t for t in trades_opt2
                        if t.get('filtered', False)
                        and trades_baseline[trades_opt2.index(t)]['pnl_pct'] > 0]

    if filtered_winners:
        for trade in filtered_winners[:3]:
            baseline = next((t for t in trades_baseline if t['symbol'] == trade['symbol']), None)
            if baseline:
                print(f"Symbol: {trade['symbol']}")
                print(f"  Would have made: +{baseline['pnl_pct']:.2f}%")
                print(f"  Momentum 5min: {trade.get('momentum_5min', 'N/A'):.2f}% | 15min: {trade.get('momentum_15min', 'N/A'):.2f}%")
                print()
    else:
        print("  No winning trades filtered (or not enough data)")

    # Option 2: Losers successfully filtered
    print("\n🟢 OPTION 2 - Losers Successfully Filtered:")
    print("-" * 100)
    filtered_losers = [t for t in trades_opt2
                       if t.get('filtered', False)
                       and trades_baseline[trades_opt2.index(t)]['pnl_pct'] < 0]

    if filtered_losers:
        for trade in filtered_losers[:3]:
            baseline = next((t for t in trades_baseline if t['symbol'] == trade['symbol']), None)
            if baseline:
                print(f"Symbol: {trade['symbol']}")
                print(f"  Avoided loss: {baseline['pnl_pct']:.2f}%")
                print(f"  Momentum 5min: {trade.get('momentum_5min', 'N/A'):.2f}% | 15min: {trade.get('momentum_15min', 'N/A'):.2f}%")
                print()
    else:
        print("  No losing trades filtered (or not enough data)")

    print("="*100)


def main():
    """Main backtest execution"""
    print("Loading trade data...")
    df = load_trades()
    print(f"✓ Loaded {len(df)} total trade records")

    print("\nBuilding trade pairs...")
    trades = build_trade_pairs(df)
    print(f"✓ Built {len(trades)} completed trade pairs")

    if len(trades) == 0:
        print("❌ No completed trades found. Cannot run backtest.")
        return

    print(f"\nBacktesting period: {trades[0]['entry_date'].date()} to {trades[-1]['exit_date'].date()}")

    # Simulate all 3 options
    print("\nSimulating Option 1: Wider SL for volatile stocks...")
    trades_opt1 = [simulate_option1_wider_sl(t) for t in trades]

    print("Simulating Option 2: Intraday momentum filter...")
    trades_opt2 = [simulate_option2_momentum_filter(t, use_simulated=True) for t in trades]

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
    best_risk_adj = max(results, key=lambda x: x['total_return'] / abs(x['max_drawdown']) if x['max_drawdown'] != 0 else 0)

    print(f"\n📊 Best Total Return: {best_option['option']}")
    print(f"   Return: {best_option['total_return']:.2f}% | Win Rate: {best_option['win_rate']:.1f}%")

    print(f"\n📊 Best Risk-Adjusted Return: {best_risk_adj['option']}")
    print(f"   Return: {best_risk_adj['total_return']:.2f}% | Max DD: {best_risk_adj['max_drawdown']:.2f}%")

    print("\n💡 Analysis:")

    # Option 1 analysis
    opt1 = results[0]
    baseline = results[2]
    if opt1['stops_avoided'] > 0:
        print(f"\n   Option 1 (Wider SL):")
        print(f"   - Saved {opt1['stops_avoided']} positions from early stop outs")
        print(f"   - Return difference vs baseline: {opt1['total_return'] - baseline['total_return']:.2f}%")
        if opt1['total_return'] > baseline['total_return']:
            print(f"   ✅ RECOMMENDED: Use wider SL for stocks with ATR > 3%")
        else:
            print(f"   ❌ NOT RECOMMENDED: Wider SL leads to bigger losses overall")

    # Option 2 analysis
    opt2 = results[1]
    if opt2['trades_filtered'] > 0:
        print(f"\n   Option 2 (Momentum Filter):")
        print(f"   - Filtered {opt2['trades_filtered']} trades ({opt2['trades_filtered']/len(trades)*100:.1f}%)")
        print(f"   - Return difference vs baseline: {opt2['total_return'] - baseline['total_return']:.2f}%")
        if opt2['win_rate'] > baseline['win_rate'] + 5:  # At least 5% win rate improvement
            print(f"   ✅ RECOMMENDED: Momentum filter improves win rate significantly")
        else:
            print(f"   ❌ NOT RECOMMENDED: Filters too many good trades")

    print("\n" + "="*100)

    # Implementation code snippet
    print("\nIMPLEMENTATION CODE SNIPPET:")
    print("-" * 100)

    if best_option == results[0]:
        print("""
# Option 1: Wider SL for Volatile Stocks
def calculate_stop_loss(entry_price: float, atr_pct: float) -> float:
    # If ATR > 3%, use 2.0x multiplier instead of 1.5x
    if atr_pct > 3.0:
        sl_pct = atr_pct * 2.0  # Wider SL for volatile stocks
    else:
        sl_pct = atr_pct * 1.5  # Standard SL

    # Cap at max 6% (prevent too wide)
    sl_pct = min(sl_pct, 6.0)

    sl_price = entry_price * (1 - sl_pct / 100)
    return sl_price, sl_pct
""")
    elif best_option == results[1]:
        print("""
# Option 2: Intraday Momentum Filter
def check_intraday_momentum(symbol: str) -> bool:
    # Get last 15 minutes of 1-min bars
    bars = get_recent_bars(symbol, interval='1min', limit=15)

    if len(bars) < 15:
        return True  # No data, allow trade

    # Calculate momentum
    current_price = bars[-1]['close']
    price_5min_ago = bars[-5]['close']
    price_15min_ago = bars[0]['close']

    momentum_5min = (current_price - price_5min_ago) / price_5min_ago * 100
    momentum_15min = (current_price - price_15min_ago) / price_15min_ago * 100

    # Require BOTH 5min and 15min momentum positive
    if momentum_5min > 0 and momentum_15min > 0:
        return True  # OK to enter
    else:
        logger.info(f"❌ Momentum Filter: {symbol} momentum 5min: {momentum_5min:.2f}%, 15min: {momentum_15min:.2f}%")
        return False  # Skip entry
""")
    else:
        print("""
# Option 3: Keep Current Settings (Baseline)
# No changes needed - current strategy is optimal for the dataset
""")

    print("="*100)


if __name__ == "__main__":
    main()
