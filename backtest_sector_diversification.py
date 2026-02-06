#!/usr/bin/env python3
"""
Backtest: Sector Diversification (P4-19)

Hypothesis:
  H0: MAX_PER_SECTOR=2 helps by reducing sector concentration risk
  H1: MAX_PER_SECTOR=2 limits winners (blocks good trades in hot sectors)

Current Setting:
  MAX_PER_SECTOR = 2

Test Cases:
  1. NO_LIMIT: No sector restriction
  2. MAX_1: Only 1 position per sector
  3. MAX_2: Current setting (2 per sector)
  4. MAX_3: Allow 3 per sector
  5. MAX_4: Allow 4 per sector

Metrics:
  - Total return
  - Win rate
  - Expectancy
  - Max drawdown
  - Blocked trades (would have been winners)
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("yfinance not available")

# Sector limits to test
SECTOR_LIMITS = {
    'NO_LIMIT': 999,
    'MAX_1': 1,
    'MAX_2': 2,  # Current
    'MAX_3': 3,
    'MAX_4': 4,
}

# Stocks by sector (representative sample)
STOCKS_BY_SECTOR = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AMD', 'INTC', 'AVGO', 'QCOM', 'CRM', 'ADBE', 'NOW', 'ORCL', 'IBM'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN', 'VRTX', 'TMO'],
    'Financial': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'V', 'MA', 'COF'],
    'Consumer': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'WMT', 'COST', 'LOW', 'TJX', 'ROST'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN', 'HAL', 'BKR'],
    'Industrial': ['CAT', 'DE', 'UNP', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX', 'WM', 'EMR'],
    'Communication': ['GOOGL', 'META', 'NFLX', 'DIS', 'VZ', 'T', 'TMUS', 'CMCSA', 'CHTR', 'EA', 'TTWO', 'WBD'],
}

# Flatten for easy lookup
SYMBOL_TO_SECTOR = {}
ALL_SYMBOLS = []
for sector, symbols in STOCKS_BY_SECTOR.items():
    for symbol in symbols:
        SYMBOL_TO_SECTOR[symbol] = sector
        ALL_SYMBOLS.append(symbol)


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_score(yesterday_return: float, today_return: float, rsi: float,
                   sma20_above: bool, sma50_above: bool, atr_pct: float) -> int:
    """Calculate signal score (simplified v5.3.1)"""
    score = 50

    # Dip-bounce
    if yesterday_return <= -3:
        score += 30
    elif yesterday_return <= -2:
        score += 20
    elif yesterday_return <= -1:
        score += 10

    # Bounce strength
    if today_return >= 3:
        score += 20
    elif today_return >= 2:
        score += 15
    elif today_return >= 1:
        score += 10

    # RSI (v5.3.1 - no penalty for high RSI)
    if 25 <= rsi <= 40:
        score += 35
    elif 40 < rsi <= 50:
        score += 20

    # Trend
    if sma50_above and sma20_above:
        score += 25
    elif sma20_above:
        score += 15

    # Volatility
    if atr_pct > 5:
        score += 20
    elif atr_pct > 4:
        score += 15
    elif atr_pct > 3:
        score += 10

    return score


def get_all_signals(start_date: str, end_date: str) -> List[Dict]:
    """
    Get all dip-bounce signals across all stocks.
    Returns signals with scores and outcomes.
    """
    all_signals = []

    for symbol in ALL_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist is None or len(hist) < 50:
                continue

            # Calculate indicators
            hist['prev_close'] = hist['Close'].shift(1)
            hist['daily_return'] = (hist['Close'] - hist['prev_close']) / hist['prev_close'] * 100
            hist['yesterday_return'] = hist['daily_return'].shift(1)
            hist['rsi'] = calculate_rsi(hist['Close'])
            hist['sma20'] = hist['Close'].rolling(window=20).mean()
            hist['sma50'] = hist['Close'].rolling(window=50).mean()

            # ATR
            hist['tr'] = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - hist['Close'].shift(1)).abs(),
                (hist['Low'] - hist['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            hist['atr'] = hist['tr'].rolling(window=14).mean()
            hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

            for i in range(50, len(hist) - 5):
                row = hist.iloc[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                    continue

                # Dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Calculate score
                sma20_above = row['Close'] > row['sma20'] if not pd.isna(row['sma20']) else False
                sma50_above = row['Close'] > row['sma50'] if not pd.isna(row['sma50']) else False
                atr_pct = row['atr_pct'] if not pd.isna(row['atr_pct']) else 3.0

                score = calculate_score(yesterday_ret, today_ret, rsi, sma20_above, sma50_above, atr_pct)

                if score < 80:  # MIN_SCORE filter
                    continue

                # Calculate outcome (TP +4%, SL -2%, max 4 days)
                entry_price = row['Close']
                future_prices = hist.iloc[i+1:i+6]['Close'].values

                if len(future_prices) < 3:
                    continue

                exit_return = 0
                for j, future_price in enumerate(future_prices[:4], 1):
                    pct_change = (future_price - entry_price) / entry_price * 100
                    if pct_change >= 4.0:
                        exit_return = 4.0
                        break
                    elif pct_change <= -2.0:
                        exit_return = -2.0
                        break
                    exit_return = pct_change

                all_signals.append({
                    'symbol': symbol,
                    'sector': SYMBOL_TO_SECTOR[symbol],
                    'date': hist.index[i],
                    'score': score,
                    'exit_return': exit_return,
                    'is_winner': exit_return > 0,
                })

        except Exception as e:
            continue

    # Sort by date then score
    all_signals.sort(key=lambda x: (x['date'], -x['score']))
    return all_signals


def simulate_with_sector_limit(signals: List[Dict], max_per_sector: int, max_positions: int = 3) -> Dict:
    """
    Simulate trading with sector limit.
    Returns performance metrics and blocked trade analysis.
    """
    trades_taken = []
    trades_blocked = []

    current_date = None
    current_positions = []  # List of (symbol, sector)
    sector_counts = defaultdict(int)

    for signal in signals:
        signal_date = signal['date']

        # New day - close all positions (simplified)
        if current_date is None or signal_date.date() != current_date.date():
            current_positions = []
            sector_counts = defaultdict(int)
            current_date = signal_date

        sector = signal['sector']

        # Check if we can take this trade
        can_take = True
        block_reason = None

        if len(current_positions) >= max_positions:
            can_take = False
            block_reason = 'MAX_POSITIONS'
        elif sector_counts[sector] >= max_per_sector:
            can_take = False
            block_reason = 'SECTOR_LIMIT'

        if can_take:
            trades_taken.append(signal)
            current_positions.append((signal['symbol'], sector))
            sector_counts[sector] += 1
        else:
            signal['block_reason'] = block_reason
            trades_blocked.append(signal)

    # Calculate metrics
    if not trades_taken:
        return {
            'trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'expectancy': 0,
            'blocked_count': len(trades_blocked),
            'blocked_winners': 0,
            'blocked_winner_return': 0,
        }

    wins = [t for t in trades_taken if t['is_winner']]
    losses = [t for t in trades_taken if not t['is_winner']]

    win_rate = len(wins) / len(trades_taken) * 100
    total_return = sum(t['exit_return'] for t in trades_taken)
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

    # Analyze blocked trades
    blocked_by_sector = [t for t in trades_blocked if t.get('block_reason') == 'SECTOR_LIMIT']
    blocked_winners = [t for t in blocked_by_sector if t['is_winner']]
    blocked_winner_return = sum(t['exit_return'] for t in blocked_winners)

    return {
        'trades': len(trades_taken),
        'win_rate': win_rate,
        'total_return': total_return,
        'expectancy': expectancy,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'blocked_count': len(blocked_by_sector),
        'blocked_winners': len(blocked_winners),
        'blocked_winner_return': blocked_winner_return,
        'blocked_losers': len([t for t in blocked_by_sector if not t['is_winner']]),
    }


def analyze_sector_concentration(signals: List[Dict]) -> Dict:
    """Analyze which sectors generate most signals"""
    sector_signals = defaultdict(list)
    for s in signals:
        sector_signals[s['sector']].append(s)

    results = {}
    for sector, sigs in sector_signals.items():
        wins = [s for s in sigs if s['is_winner']]
        win_rate = len(wins) / len(sigs) * 100 if sigs else 0
        total_return = sum(s['exit_return'] for s in sigs)
        results[sector] = {
            'count': len(sigs),
            'win_rate': win_rate,
            'total_return': total_return,
        }

    return results


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 70)
    print("BACKTEST: Sector Diversification (P4-19)")
    print("=" * 70)
    print("Testing MAX_PER_SECTOR limits")
    print(f"Current setting: MAX_PER_SECTOR = 2")
    print()

    # Date range: last 2 years
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(ALL_SYMBOLS)} across {len(STOCKS_BY_SECTOR)} sectors")
    print()

    # Get all signals
    print("Collecting signals...")
    all_signals = get_all_signals(start_date, end_date)
    print(f"Total signals found: {len(all_signals)}")
    print()

    if not all_signals:
        print("No signals found!")
        return

    # Test each sector limit
    print("=" * 70)
    print("SECTOR LIMIT COMPARISON")
    print("=" * 70)
    print()
    print(f"{'Limit':<12} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10} {'Blocked':<10} {'BlkWin':<8} {'BlkRet':<10}")
    print("-" * 80)

    results = {}
    for name, limit in SECTOR_LIMITS.items():
        result = simulate_with_sector_limit(all_signals, limit)
        results[name] = result

        marker = " ← CURRENT" if name == 'MAX_2' else ""
        print(f"{name:<12} {result['trades']:<8} {result['win_rate']:.1f}%{'':<3} "
              f"{result['expectancy']:+.3f}%{'':<3} {result['total_return']:+.1f}%{'':<5} "
              f"{result['blocked_count']:<10} {result['blocked_winners']:<8} "
              f"{result['blocked_winner_return']:+.1f}%{marker}")

    print()

    # Sector analysis
    print("=" * 70)
    print("SECTOR SIGNAL DISTRIBUTION")
    print("=" * 70)
    print()

    sector_stats = analyze_sector_concentration(all_signals)
    print(f"{'Sector':<15} {'Signals':<10} {'Win%':<10} {'Total%':<10}")
    print("-" * 50)

    for sector, stats in sorted(sector_stats.items(), key=lambda x: -x[1]['count']):
        print(f"{sector:<15} {stats['count']:<10} {stats['win_rate']:.1f}%{'':<5} {stats['total_return']:+.1f}%")

    print()

    # Analysis
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print()

    current = results['MAX_2']
    no_limit = results['NO_LIMIT']

    blocked_cost = current['blocked_winner_return']
    blocked_benefit = abs(sum(t['exit_return'] for t in all_signals
                              if not t['is_winner']) * (current['blocked_count'] - current['blocked_winners']) / max(1, len(all_signals)))

    print(f"Current (MAX_2) vs NO_LIMIT:")
    print(f"  - Trades: {current['trades']} vs {no_limit['trades']} ({current['trades'] - no_limit['trades']:+d})")
    print(f"  - Win Rate: {current['win_rate']:.1f}% vs {no_limit['win_rate']:.1f}% ({current['win_rate'] - no_limit['win_rate']:+.1f}%)")
    print(f"  - Total Return: {current['total_return']:+.1f}% vs {no_limit['total_return']:+.1f}% ({current['total_return'] - no_limit['total_return']:+.1f}%)")
    print()
    print(f"Blocked by sector limit:")
    print(f"  - Total blocked: {current['blocked_count']}")
    print(f"  - Blocked winners: {current['blocked_winners']} (lost return: {current['blocked_winner_return']:+.1f}%)")
    print(f"  - Blocked losers: {current['blocked_losers']}")
    print()

    # Recommendation
    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print()

    # Find best limit
    best_name = max(results.keys(), key=lambda k: results[k]['total_return'])
    best = results[best_name]

    if best_name == 'MAX_2':
        print(f"✅ KEEP current MAX_PER_SECTOR = 2")
        print(f"   Current setting is optimal")
    elif best['total_return'] > current['total_return']:
        diff = best['total_return'] - current['total_return']
        print(f"⚠️ CONSIDER changing to {best_name}")
        print(f"   Would improve total return by {diff:+.1f}%")
        if best_name == 'NO_LIMIT':
            print(f"   But increases concentration risk")
    else:
        print(f"✅ KEEP current MAX_PER_SECTOR = 2")


if __name__ == '__main__':
    main()
