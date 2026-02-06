#!/usr/bin/env python3
"""
Backtest: Sector Cooldown Impact on Mean-Reversion Edge

Hypothesis:
  H0: Sector Cooldown helps avoid bad sectors (positive impact)
  H1: Sector Cooldown destroys mean-reversion edge (negative impact)
      - Similar to DD Control destroying BEAR edge
      - Mean-reversion needs "room to work"
      - Cooldown may prevent good recovery entries

Current Settings:
  - MAX_SECTOR_CONSECUTIVE_LOSS = 2 (trigger after 2 losses)
  - SECTOR_COOLDOWN_DAYS = 2 (cooldown duration)

Approach:
  Since we don't have enough real trade data, we simulate trades using
  historical price data with the same entry/exit logic as the engine.
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("yfinance not available - install with: pip install yfinance")

# Cooldown parameters (match engine settings)
MAX_SECTOR_CONSECUTIVE_LOSS = 2
SECTOR_COOLDOWN_DAYS = 2

# Sector ETF mapping
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financial Services': 'XLF',
    'Consumer Cyclical': 'XLY',
    'Consumer Defensive': 'XLP',
    'Energy': 'XLE',
    'Industrials': 'XLI',
    'Basic Materials': 'XLB',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Communication Services': 'XLC',
}

# Sample stocks per sector for simulation
SECTOR_STOCKS = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AMD', 'INTC'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'MRK', 'ABBV'],
    'Financial Services': ['JPM', 'BAC', 'WFC', 'GS', 'MS'],
    'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD'],
    'Consumer Defensive': ['PG', 'KO', 'PEP', 'WMT', 'COST'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG'],
    'Industrials': ['CAT', 'DE', 'UNP', 'HON', 'GE'],
    'Basic Materials': ['LIN', 'APD', 'ECL', 'DD', 'NEM'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP'],
    'Real Estate': ['AMT', 'PLD', 'CCI', 'EQIX', 'PSA'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'VZ'],
}


def get_dip_bounce_signals(symbol: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Find dip-bounce signals in historical data.

    Entry: Yesterday dip >= 2%, Today bounce >= 1%
    Exit: TP +4% or SL -2.5% or Max 5 days
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)

        if hist is None or len(hist) < 20:
            return []

        signals = []
        hist['prev_close'] = hist['Close'].shift(1)
        hist['prev_prev_close'] = hist['Close'].shift(2)
        hist['daily_return'] = (hist['Close'] - hist['prev_close']) / hist['prev_close'] * 100
        hist['yesterday_return'] = hist['daily_return'].shift(1)

        for i in range(5, len(hist) - 5):
            row = hist.iloc[i]

            # Check dip-bounce pattern
            yesterday_ret = row.get('yesterday_return', 0)
            today_ret = row.get('daily_return', 0)

            if pd.isna(yesterday_ret) or pd.isna(today_ret):
                continue

            is_dip = yesterday_ret <= -2.0
            is_bounce = today_ret >= 1.0

            if not (is_dip and is_bounce):
                continue

            # Entry at close
            entry_price = row['Close']
            entry_date = hist.index[i]

            # Simulate exit over next 5 days
            tp_price = entry_price * 1.04  # +4% TP
            sl_price = entry_price * 0.975  # -2.5% SL

            exit_price = None
            exit_date = None
            exit_reason = None

            for j in range(i + 1, min(i + 6, len(hist))):
                day = hist.iloc[j]
                high = day['High']
                low = day['Low']
                close = day['Close']

                # Check SL hit (use low)
                if low <= sl_price:
                    exit_price = sl_price
                    exit_date = hist.index[j]
                    exit_reason = 'SL'
                    break

                # Check TP hit (use high)
                if high >= tp_price:
                    exit_price = tp_price
                    exit_date = hist.index[j]
                    exit_reason = 'TP'
                    break

                # Max hold 5 days
                if j == i + 5:
                    exit_price = close
                    exit_date = hist.index[j]
                    exit_reason = 'MAX_HOLD'
                    break

            if exit_price is None:
                continue

            pnl_pct = (exit_price - entry_price) / entry_price * 100

            signals.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'pnl_pct': round(pnl_pct, 2),
                'yesterday_dip': round(yesterday_ret, 2),
                'today_bounce': round(today_ret, 2),
            })

        return signals

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []


def simulate_trades_for_sector(sector: str, start_date: str, end_date: str) -> List[Dict]:
    """Generate simulated trades for a sector"""
    stocks = SECTOR_STOCKS.get(sector, [])
    all_signals = []

    for symbol in stocks:
        signals = get_dip_bounce_signals(symbol, start_date, end_date)
        for sig in signals:
            sig['sector'] = sector
        all_signals.extend(signals)

    # Sort by entry date
    all_signals.sort(key=lambda x: x['entry_date'])
    return all_signals


def simulate_sector_cooldown(trades: List[Dict], max_loss: int = 2, cd_days: int = 2) -> Tuple[List[Dict], List[Dict]]:
    """
    Simulate sector cooldown and return allowed/blocked trades.
    """
    sector_tracker: Dict[str, Dict] = defaultdict(lambda: {'losses': 0, 'cooldown_until': None})
    allowed_trades = []
    blocked_trades = []

    for trade in trades:
        sector = trade.get('sector', 'unknown').lower()
        entry_date = trade.get('entry_date')

        if hasattr(entry_date, 'date'):
            trade_date = entry_date.date()
        else:
            trade_date = datetime.now().date()

        tracker = sector_tracker[sector]

        # Check if trade would be blocked by cooldown
        is_blocked = False
        if tracker['cooldown_until'] and trade_date <= tracker['cooldown_until']:
            is_blocked = True
            blocked_trades.append({**trade, 'block_reason': f"Sector {sector} cooldown until {tracker['cooldown_until']}"})
        else:
            # Cooldown expired, reset
            if tracker['cooldown_until'] and trade_date > tracker['cooldown_until']:
                tracker['losses'] = 0
                tracker['cooldown_until'] = None
            allowed_trades.append(trade)

        # Update tracker based on trade result
        pnl_pct = trade.get('pnl_pct', 0)

        if pnl_pct >= 0:
            tracker['losses'] = 0
        else:
            tracker['losses'] += 1
            if tracker['losses'] >= max_loss:
                tracker['cooldown_until'] = trade_date + timedelta(days=cd_days)

    return allowed_trades, blocked_trades


def calculate_metrics(trades: List[Dict], label: str) -> Dict:
    """Calculate trading metrics"""
    if not trades:
        return {
            'label': label,
            'count': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'expectancy': 0,
            'total_pnl': 0,
            'max_dd': 0,
        }

    wins = [t for t in trades if t.get('pnl_pct', 0) > 0]
    losses = [t for t in trades if t.get('pnl_pct', 0) <= 0]

    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = statistics.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([abs(t['pnl_pct']) for t in losses]) if losses else 0

    expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
    total_pnl = sum(t.get('pnl_pct', 0) for t in trades)

    # Max drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cumulative += t.get('pnl_pct', 0)
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    return {
        'label': label,
        'count': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(win_rate, 1),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'expectancy': round(expectancy, 3),
        'total_pnl': round(total_pnl, 2),
        'max_dd': round(max_dd, 2),
    }


def analyze_blocked_trades(blocked_trades: List[Dict]) -> Dict:
    """Analyze what we're missing by blocking trades"""
    if not blocked_trades:
        return {'count': 0, 'would_have_won': 0, 'would_have_lost': 0, 'net_impact': 0}

    would_have_won = [t for t in blocked_trades if t.get('pnl_pct', 0) > 0]
    would_have_lost = [t for t in blocked_trades if t.get('pnl_pct', 0) <= 0]

    return {
        'count': len(blocked_trades),
        'would_have_won': len(would_have_won),
        'would_have_lost': len(would_have_lost),
        'missed_profit': sum(t.get('pnl_pct', 0) for t in would_have_won),
        'avoided_loss': sum(abs(t.get('pnl_pct', 0)) for t in would_have_lost),
        'net_impact': sum(t.get('pnl_pct', 0) for t in blocked_trades),
    }


def run_backtest():
    """Run the sector cooldown backtest with simulated trades"""
    if not YFINANCE_AVAILABLE:
        print("yfinance required for this backtest")
        return

    print("=" * 70)
    print("BACKTEST: Sector Cooldown Impact Analysis")
    print("=" * 70)
    print(f"\nSettings: MAX_CONSECUTIVE_LOSS={MAX_SECTOR_CONSECUTIVE_LOSS}, COOLDOWN_DAYS={SECTOR_COOLDOWN_DAYS}")

    # Use 6 months of data
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    print(f"Period: {start_date} to {end_date}")

    # Generate simulated trades for all sectors
    print("\nGenerating dip-bounce signals from historical data...")
    all_trades = []

    for sector in SECTOR_STOCKS.keys():
        print(f"  Scanning {sector}...", end=" ", flush=True)
        sector_trades = simulate_trades_for_sector(sector, start_date, end_date)
        print(f"{len(sector_trades)} signals")
        all_trades.extend(sector_trades)

    # Sort all trades by entry date
    all_trades.sort(key=lambda x: x['entry_date'])

    print(f"\nTotal simulated trades: {len(all_trades)}")

    if not all_trades:
        print("No trades generated. Check date range or stock data.")
        return

    # Simulate cooldown
    allowed_trades, blocked_trades = simulate_sector_cooldown(all_trades)

    print("\n" + "=" * 70)
    print("HYPOTHESIS TEST: Does Sector Cooldown Help or Hurt?")
    print("=" * 70)

    # Test 1: All trades vs With Cooldown
    print("\n--- TEST 1: Overall Impact ---")
    base_metrics = calculate_metrics(all_trades, "BASE (All Trades)")
    cooldown_metrics = calculate_metrics(allowed_trades, "WITH COOLDOWN")

    print(f"\n{'Metric':<20} {'BASE':<15} {'COOLDOWN':<15} {'Delta':<15}")
    print("-" * 65)
    for key in ['count', 'win_rate', 'avg_win', 'avg_loss', 'expectancy', 'total_pnl', 'max_dd']:
        base_val = base_metrics[key]
        cooldown_val = cooldown_metrics[key]
        if isinstance(base_val, float):
            delta = cooldown_val - base_val
            delta_str = f"{delta:+.3f}" if key == 'expectancy' else f"{delta:+.2f}"
            print(f"{key:<20} {base_val:<15.2f} {cooldown_val:<15.2f} {delta_str:<15}")
        else:
            delta = cooldown_val - base_val
            print(f"{key:<20} {base_val:<15} {cooldown_val:<15} {delta:+d}")

    # Analyze blocked trades
    blocked_analysis = analyze_blocked_trades(blocked_trades)
    print(f"\n--- Blocked Trades Analysis ---")
    print(f"Total blocked: {blocked_analysis['count']}")
    print(f"Would have WON:  {blocked_analysis['would_have_won']} (missed profit: +{blocked_analysis.get('missed_profit', 0):.2f}%)")
    print(f"Would have LOST: {blocked_analysis['would_have_lost']} (avoided loss: -{blocked_analysis.get('avoided_loss', 0):.2f}%)")
    print(f"NET IMPACT of blocking: {blocked_analysis.get('net_impact', 0):+.2f}%")

    # Test 2: Per-Sector Analysis
    print("\n" + "=" * 70)
    print("--- TEST 2: Per-Sector Analysis ---")
    print("=" * 70)

    sector_breakdown = defaultdict(list)
    for t in all_trades:
        sector_breakdown[t['sector']].append(t)

    print(f"\n{'Sector':<25} {'Count':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10}")
    print("-" * 65)
    for sector, trades in sorted(sector_breakdown.items(), key=lambda x: len(x[1]), reverse=True):
        metrics = calculate_metrics(trades, sector)
        print(f"{sector:<25} {metrics['count']:<8} {metrics['win_rate']:<8.1f} {metrics['expectancy']:<10.3f} {metrics['total_pnl']:<10.2f}")

    # Test 3: Cooldown Sensitivity Analysis
    print("\n" + "=" * 70)
    print("--- TEST 3: Cooldown Sensitivity Analysis ---")
    print("=" * 70)

    print(f"\n{'Config':<30} {'Trades':<10} {'Blocked':<10} {'E[R]':<10} {'vs BASE':<10}")
    print("-" * 70)

    print(f"{'No Cooldown':<30} {len(all_trades):<10} {0:<10} {base_metrics['expectancy']:<10.3f} {'---':<10}")

    configs = [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),  # Current
        (2, 3),
        (3, 2),
        (3, 3),
    ]

    for max_loss, cd_days in configs:
        allowed, blocked = simulate_sector_cooldown(all_trades, max_loss, cd_days)
        metrics = calculate_metrics(allowed, f"CD({max_loss}L,{cd_days}D)")
        delta = metrics['expectancy'] - base_metrics['expectancy']

        label = f"CD(loss≥{max_loss}, days={cd_days})"
        if max_loss == 2 and cd_days == 2:
            label += " [CURRENT]"

        print(f"{label:<30} {len(allowed):<10} {len(blocked):<10} {metrics['expectancy']:<10.3f} {delta:+.3f}")

    # Conclusion
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)

    expectancy_delta = cooldown_metrics['expectancy'] - base_metrics['expectancy']

    if expectancy_delta < -0.1:
        print(f"\n🔴 SECTOR COOLDOWN HURTS EXPECTANCY: {expectancy_delta:+.3f}%")
        print("   Recommendation: DISABLE sector cooldown in BEAR mode")
        print("   (Similar to DD Control destroying BEAR edge)")
    elif expectancy_delta > 0.1:
        print(f"\n🟢 SECTOR COOLDOWN HELPS: {expectancy_delta:+.3f}%")
        print("   Recommendation: KEEP current settings")
    else:
        print(f"\n🟡 SECTOR COOLDOWN NEUTRAL: {expectancy_delta:+.3f}%")
        print("   Recommendation: Consider simplifying (remove cooldown)")

    # Show blocked trade examples
    if blocked_trades:
        print("\n--- Sample Blocked Trades ---")
        winners = [t for t in blocked_trades if t.get('pnl_pct', 0) > 0][:3]
        losers = [t for t in blocked_trades if t.get('pnl_pct', 0) <= 0][:3]

        print("Missed Winners:")
        for t in winners:
            print(f"  {t['symbol']}: {t['pnl_pct']:+.2f}% ({t['sector']})")

        print("Avoided Losers:")
        for t in losers:
            print(f"  {t['symbol']}: {t['pnl_pct']:+.2f}% ({t['sector']})")


if __name__ == '__main__':
    run_backtest()
