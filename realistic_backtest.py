#!/usr/bin/env python3
"""
REALISTIC PORTFOLIO BACKTEST
Limits trades to realistic daily limits
Target: 5-15% monthly profit
"""

import sys
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

START_DATE = pd.Timestamp('2025-10-01')
END_DATE = pd.Timestamp('2026-01-30')

# Best config from optimizer
CONFIG = {
    'max_mom_1d': 5,
    'max_mom_5d': 10,
    'max_gap': 2,
    'max_rsi': 80,
    'atr_mult': 1.0,
    'min_sl': 1.5,
    'max_sl': 3.0,
    'rr_ratio': 3.0,
    'max_hold': 7,
}

# Realistic trading limits
MAX_POSITIONS = 5      # Max positions at a time
MAX_NEW_TRADES_PER_DAY = 2  # Max new entries per day
POSITION_SIZE = 0.20   # 20% of capital per position

UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'CRM',
    'ADBE', 'NFLX', 'ORCL', 'CSCO', 'QCOM', 'TXN', 'AVGO', 'NOW', 'INTU',
    'SHOP', 'SNOW', 'PLTR', 'NET', 'DDOG', 'ZS', 'CRWD', 'MDB', 'TWLO',
    'MU', 'MRVL', 'KLAC', 'LRCX', 'AMAT', 'ASML', 'ADI', 'NXPI', 'ON',
    'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
    'AMGN', 'GILD', 'ISRG', 'VRTX', 'REGN', 'MRNA', 'ILMN', 'DXCM', 'ALGN',
    'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'COST', 'LOW', 'TJX', 'ROST',
    'CMG', 'LULU', 'ULTA', 'W', 'DECK', 'CROX',
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'BLK',
    'CAT', 'DE', 'BA', 'HON', 'UNP', 'UPS', 'RTX', 'LMT', 'GE',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'VLO', 'OXY', 'DVN',
    'ENPH', 'FSLR', 'RUN',
]


def load_and_prep(dm, symbols):
    """Load and precompute all data"""
    print(f"Loading {len(symbols)} stocks...")
    data = {}

    for sym in symbols:
        try:
            df = dm.get_price_data(sym, period='6mo')
            if df is None or len(df) < 50:
                continue

            df = df.rename(columns={
                'date': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })

            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)

            # Compute indicators
            c = df['Close']
            df['mom_1d'] = c.pct_change(1) * 100
            df['mom_5d'] = c.pct_change(5) * 100

            delta = c.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            df['rsi'] = 100 - 100 / (1 + gain / (loss + 0.0001))

            df['gap'] = (df['Open'] - c.shift(1)) / c.shift(1) * 100

            tr = pd.concat([df['High'] - df['Low'],
                           abs(df['High'] - c.shift()),
                           abs(df['Low'] - c.shift())], axis=1).max(axis=1)
            df['atr_pct'] = (tr.rolling(14).mean() / c * 100).fillna(2)

            # Create date index for lookup
            df = df.set_index('Date')
            data[sym] = df

        except Exception as e:
            pass

    print(f"Loaded {len(data)} stocks")
    return data


def get_entry_signals(data, date, config):
    """Get all entry signals for a specific date"""
    signals = []

    for sym, df in data.items():
        if date not in df.index:
            continue

        row = df.loc[date]

        mom_1d = row['mom_1d'] if pd.notna(row['mom_1d']) else 0
        mom_5d = row['mom_5d'] if pd.notna(row['mom_5d']) else 0
        rsi = row['rsi'] if pd.notna(row['rsi']) else 50
        gap = row['gap'] if pd.notna(row['gap']) else 0
        atr_pct = row['atr_pct'] if pd.notna(row['atr_pct']) else 2

        # Entry filters
        if mom_1d > config['max_mom_1d']:
            continue
        if gap > config['max_gap']:
            continue
        if rsi > config['max_rsi']:
            continue
        if mom_5d > config['max_mom_5d']:
            continue

        # Calculate stop/target
        sl_pct = min(max(atr_pct * config['atr_mult'], config['min_sl']), config['max_sl'])
        tp_pct = sl_pct * config['rr_ratio']

        # Score by RSI (lower = better for dip buying)
        score = 100 - rsi  # Lower RSI = higher score

        signals.append({
            'symbol': sym,
            'date': date,
            'entry_price': row['Close'],
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'rsi': rsi,
            'mom_1d': mom_1d,
            'score': score,
        })

    # Sort by score (best signals first)
    signals.sort(key=lambda x: x['score'], reverse=True)
    return signals


def simulate_position(data, signal, config):
    """Simulate a position and return result"""
    sym = signal['symbol']
    df = data[sym]
    entry_date = signal['date']
    entry_price = signal['entry_price']
    sl_pct = signal['sl_pct']
    tp_pct = signal['tp_pct']

    sl_price = entry_price * (1 - sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100)

    # Get dates after entry
    dates = df.index.tolist()
    try:
        entry_idx = dates.index(entry_date)
    except ValueError:
        return None

    for i in range(1, config['max_hold'] + 1):
        if entry_idx + i >= len(dates):
            break

        check_date = dates[entry_idx + i]
        row = df.loc[check_date]

        # Check SL
        if row['Low'] <= sl_price:
            pnl_pct = -sl_pct
            return {
                'symbol': sym,
                'entry_date': entry_date,
                'exit_date': check_date,
                'entry_price': entry_price,
                'exit_price': sl_price,
                'pnl_pct': pnl_pct,
                'days': i,
                'exit': 'SL'
            }

        # Check TP
        if row['High'] >= tp_price:
            pnl_pct = tp_pct
            return {
                'symbol': sym,
                'entry_date': entry_date,
                'exit_date': check_date,
                'entry_price': entry_price,
                'exit_price': tp_price,
                'pnl_pct': pnl_pct,
                'days': i,
                'exit': 'TP'
            }

    # Time exit
    if entry_idx + config['max_hold'] < len(dates):
        exit_date = dates[entry_idx + config['max_hold']]
        exit_price = df.loc[exit_date]['Close']
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        return {
            'symbol': sym,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'days': config['max_hold'],
            'exit': 'TIME'
        }

    return None


def run_realistic_backtest(data, config):
    """Run backtest with realistic position limits"""
    # Get all trading dates
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    trading_dates = sorted([d for d in all_dates if START_DATE <= d <= END_DATE])

    print(f"Trading dates: {len(trading_dates)}")

    # Track portfolio
    open_positions = []  # {symbol, entry_date, sl_price, tp_price, entry_price}
    closed_trades = []
    daily_pnl = []

    capital = 100000  # Starting capital
    current_capital = capital

    for date in trading_dates:
        # First, check and close any positions that hit SL/TP
        positions_to_remove = []
        for pos in open_positions:
            sym = pos['symbol']
            if sym not in data or date not in data[sym].index:
                continue

            row = data[sym].loc[date]
            entry_price = pos['entry_price']
            sl_price = pos['sl_price']
            tp_price = pos['tp_price']

            # Check SL
            if row['Low'] <= sl_price:
                pnl_pct = (sl_price - entry_price) / entry_price * 100
                closed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'pnl_pct': pnl_pct,
                    'exit': 'SL'
                })
                positions_to_remove.append(pos)
                continue

            # Check TP
            if row['High'] >= tp_price:
                pnl_pct = (tp_price - entry_price) / entry_price * 100
                closed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'pnl_pct': pnl_pct,
                    'exit': 'TP'
                })
                positions_to_remove.append(pos)
                continue

            # Check max hold
            days_held = (date - pos['entry_date']).days
            if days_held >= config['max_hold']:
                exit_price = row['Close']
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                closed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'pnl_pct': pnl_pct,
                    'exit': 'TIME'
                })
                positions_to_remove.append(pos)

        for pos in positions_to_remove:
            open_positions.remove(pos)

        # Calculate daily P&L
        day_pnl = sum(t['pnl_pct'] * POSITION_SIZE for t in closed_trades if t['exit_date'] == date)
        current_capital *= (1 + day_pnl / 100)
        daily_pnl.append({'date': date, 'pnl': day_pnl, 'capital': current_capital})

        # Get new entry signals
        current_symbols = [p['symbol'] for p in open_positions]
        signals = get_entry_signals(data, date, config)

        # Filter out symbols we already hold
        signals = [s for s in signals if s['symbol'] not in current_symbols]

        # Limit new entries
        new_entries = 0
        for signal in signals:
            if len(open_positions) >= MAX_POSITIONS:
                break
            if new_entries >= MAX_NEW_TRADES_PER_DAY:
                break

            open_positions.append({
                'symbol': signal['symbol'],
                'entry_date': date,
                'entry_price': signal['entry_price'],
                'sl_price': signal['entry_price'] * (1 - signal['sl_pct'] / 100),
                'tp_price': signal['entry_price'] * (1 + signal['tp_pct'] / 100),
            })
            new_entries += 1

    return closed_trades, daily_pnl, current_capital


def main():
    print("=" * 60)
    print("  REALISTIC PORTFOLIO BACKTEST")
    print("=" * 60)
    print(f"  Period: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"  Max Positions: {MAX_POSITIONS}")
    print(f"  Max New Trades/Day: {MAX_NEW_TRADES_PER_DAY}")
    print(f"  Position Size: {POSITION_SIZE*100:.0f}%")
    print("=" * 60)

    dm = DataManager()
    data = load_and_prep(dm, UNIVERSE)

    print("\nRunning backtest...")
    trades, daily_pnl, final_capital = run_realistic_backtest(data, CONFIG)

    # Analyze results
    if not trades:
        print("No trades executed!")
        return

    trades_df = pd.DataFrame(trades)
    total = len(trades_df)
    winners = len(trades_df[trades_df['pnl_pct'] > 0])
    losers = total - winners

    total_return = (final_capital - 100000) / 100000 * 100
    months = (END_DATE - START_DATE).days / 30
    monthly_return = total_return / months

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"\n  Trades: {total}")
    print(f"  Winners: {winners} ({winners/total*100:.0f}%)")
    print(f"  Losers: {losers} ({losers/total*100:.0f}%)")

    print(f"\n  Avg Win: +{trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].mean():.1f}%")
    print(f"  Avg Loss: {trades_df[trades_df['pnl_pct'] <= 0]['pnl_pct'].mean():.1f}%")

    print(f"\n  Starting Capital: $100,000")
    print(f"  Final Capital: ${final_capital:,.0f}")
    print(f"  Total Return: {total_return:.1f}%")
    print(f"  Monthly Return: {monthly_return:.1f}%")

    if monthly_return >= 5:
        print(f"\n  ✅ TARGET ACHIEVED: {monthly_return:.1f}%/month!")
    else:
        print(f"\n  ⚠️ Current: {monthly_return:.1f}%/month")

    # Monthly breakdown
    print("\n" + "-" * 60)
    print("  MONTHLY BREAKDOWN")
    print("-" * 60)

    pnl_df = pd.DataFrame(daily_pnl)
    pnl_df['month'] = pd.to_datetime(pnl_df['date']).dt.to_period('M')

    monthly_trades = trades_df.copy()
    monthly_trades['month'] = pd.to_datetime(monthly_trades['entry_date']).dt.to_period('M')

    for month in pnl_df['month'].unique():
        month_pnl = pnl_df[pnl_df['month'] == month]['pnl'].sum()
        month_trades = monthly_trades[monthly_trades['month'] == month]
        month_winners = len(month_trades[month_trades['pnl_pct'] > 0])
        month_losers = len(month_trades[month_trades['pnl_pct'] <= 0])

        print(f"  {month}: {len(month_trades)} trades, "
              f"W:{month_winners}/L:{month_losers}, "
              f"P&L: {month_pnl:.1f}%")

    # Exit type breakdown
    print("\n" + "-" * 60)
    print("  EXIT TYPES")
    print("-" * 60)
    for exit_type in ['TP', 'SL', 'TIME']:
        count = len(trades_df[trades_df['exit'] == exit_type])
        avg_pnl = trades_df[trades_df['exit'] == exit_type]['pnl_pct'].mean() if count > 0 else 0
        print(f"  {exit_type}: {count} trades ({count/total*100:.0f}%), Avg P&L: {avg_pnl:+.1f}%")

    # Sample trades
    print("\n" + "-" * 60)
    print("  SAMPLE TRADES")
    print("-" * 60)

    print("\n  Winners:")
    for _, t in trades_df[trades_df['pnl_pct'] > 0].head(5).iterrows():
        print(f"    {t['symbol']} {t['entry_date'].strftime('%Y-%m-%d')}: +{t['pnl_pct']:.1f}% ({t['exit']})")

    print("\n  Losers:")
    for _, t in trades_df[trades_df['pnl_pct'] <= 0].head(5).iterrows():
        print(f"    {t['symbol']} {t['entry_date'].strftime('%Y-%m-%d')}: {t['pnl_pct']:.1f}% ({t['exit']})")

    # Save results
    import json
    import os
    os.makedirs('data', exist_ok=True)
    with open('data/realistic_backtest_results.json', 'w') as f:
        json.dump({
            'config': CONFIG,
            'total_trades': total,
            'winners': winners,
            'losers': losers,
            'win_rate': winners / total * 100,
            'total_return': total_return,
            'monthly_return': monthly_return,
            'final_capital': final_capital,
        }, f, indent=2)

    return trades_df, daily_pnl


if __name__ == '__main__':
    main()
