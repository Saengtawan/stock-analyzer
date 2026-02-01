#!/usr/bin/env python3
"""
RAPID TRADER - FAST OPTIMIZER
Target: 5-15% monthly profit with very low losers
"""

import sys
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime
from api.data_manager import DataManager

START_DATE = pd.Timestamp('2025-10-01')
END_DATE = pd.Timestamp('2026-01-30')
MONTHS = (END_DATE - START_DATE).days / 30

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

            df['sma20'] = c.rolling(20).mean()
            df['sma50'] = c.rolling(50).mean()
            df['vol_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()

            data[sym] = df

        except Exception as e:
            pass

    print(f"Loaded {len(data)} stocks")
    return data


def run_backtest(data, config):
    """Run backtest with given config"""
    trades = []

    for sym, df in data.items():
        for i in range(50, len(df) - 10):
            row = df.iloc[i]
            date = row['Date']

            if date < START_DATE or date > END_DATE:
                continue

            # Get values
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

            # Entry
            entry_price = row['Close']
            sl_pct = min(max(atr_pct * config['atr_mult'], config['min_sl']), config['max_sl'])
            tp_pct = sl_pct * config['rr_ratio']
            sl_price = entry_price * (1 - sl_pct/100)
            tp_price = entry_price * (1 + tp_pct/100)

            # Simulate
            for j in range(1, config['max_hold'] + 1):
                if i + j >= len(df):
                    break

                next_row = df.iloc[i + j]

                if next_row['Low'] <= sl_price:
                    trades.append({
                        'symbol': sym,
                        'date': date,
                        'pnl': -sl_pct,
                        'days': j,
                        'exit': 'SL',
                        'same_day': j == 1
                    })
                    break

                if next_row['High'] >= tp_price:
                    trades.append({
                        'symbol': sym,
                        'date': date,
                        'pnl': tp_pct,
                        'days': j,
                        'exit': 'TP',
                        'same_day': False
                    })
                    break
            else:
                # Time exit
                if i + config['max_hold'] < len(df):
                    exit_price = df.iloc[i + config['max_hold']]['Close']
                    pnl = (exit_price - entry_price) / entry_price * 100
                    trades.append({
                        'symbol': sym,
                        'date': date,
                        'pnl': pnl,
                        'days': config['max_hold'],
                        'exit': 'TIME',
                        'same_day': False
                    })

    return pd.DataFrame(trades) if trades else pd.DataFrame()


def analyze(trades_df):
    """Analyze results"""
    if len(trades_df) == 0:
        return None

    total = len(trades_df)
    winners = len(trades_df[trades_df['pnl'] > 0])
    losers = total - winners

    total_pnl = trades_df['pnl'].sum()
    monthly_pnl = total_pnl / MONTHS

    same_day = len(trades_df[trades_df['same_day'] == True])

    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0

    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] <= 0]['pnl'].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else 999

    return {
        'total': total,
        'winners': winners,
        'losers': losers,
        'win_rate': winners / total * 100,
        'total_pnl': total_pnl,
        'monthly_pnl': monthly_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'pf': pf,
        'same_day_pct': same_day / total * 100,
    }


def main():
    print("=" * 60)
    print("  RAPID TRADER - FAST OPTIMIZER")
    print("  Target: 5-15% monthly, low losers")
    print("=" * 60)

    dm = DataManager()
    data = load_and_prep(dm, UNIVERSE)

    # Test baseline (no filters)
    print("\n--- BASELINE (no filters) ---")
    baseline_config = {
        'max_mom_1d': 100, 'max_mom_5d': 100, 'max_gap': 100, 'max_rsi': 100,
        'atr_mult': 1.0, 'min_sl': 2, 'max_sl': 3, 'rr_ratio': 2.0, 'max_hold': 5
    }
    trades = run_backtest(data, baseline_config)
    result = analyze(trades)
    if result:
        print(f"  Trades: {result['total']}, WR: {result['win_rate']:.0f}%, Monthly: {result['monthly_pnl']:.1f}%")

    # Optimize
    print("\n" + "=" * 60)
    print("  OPTIMIZING...")
    print("=" * 60)

    best_config = None
    best_score = -999
    best_result = None
    best_trades = None

    iteration = 0

    for max_mom_1d in [0, 1, 2, 3, 5]:
        for max_mom_5d in [0, 3, 5, 10, 15]:
            for max_rsi in [40, 50, 60, 70, 80]:
                for rr_ratio in [1.5, 2.0, 2.5, 3.0]:
                    for max_hold in [3, 5, 7]:

                        config = {
                            'max_mom_1d': max_mom_1d,
                            'max_mom_5d': max_mom_5d,
                            'max_gap': 2,
                            'max_rsi': max_rsi,
                            'atr_mult': 1.0,
                            'min_sl': 1.5,
                            'max_sl': 3.0,
                            'rr_ratio': rr_ratio,
                            'max_hold': max_hold,
                        }

                        iteration += 1
                        trades = run_backtest(data, config)

                        if len(trades) < 20:
                            continue

                        result = analyze(trades)
                        if result is None:
                            continue

                        # Score: maximize monthly profit, minimize loser ratio
                        loser_ratio = result['losers'] / max(result['winners'], 1)
                        score = (
                            result['monthly_pnl'] * 3 +
                            result['pf'] * 5 +
                            result['win_rate'] * 0.2 -
                            loser_ratio * 10 -
                            result['same_day_pct'] * 0.2
                        )

                        if result['monthly_pnl'] > 0 and score > best_score:
                            best_score = score
                            best_config = config.copy()
                            best_result = result.copy()
                            best_trades = trades.copy()

                            print(f"\n  [{iteration}] NEW BEST (score={score:.1f}):")
                            print(f"    Monthly: {result['monthly_pnl']:.1f}%")
                            print(f"    Win Rate: {result['win_rate']:.0f}%")
                            print(f"    W/L: {result['winners']}/{result['losers']}")
                            print(f"    PF: {result['pf']:.2f}")

                        if iteration % 300 == 0:
                            print(f"    Progress: {iteration}...")

    # Results
    print("\n" + "=" * 60)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 60)
    print(f"  Tested: {iteration} configurations")

    if best_result:
        print(f"\nBEST CONFIG:")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nPERFORMANCE:")
        print(f"  Trades: {best_result['total']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.0f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Monthly P&L: {best_result['monthly_pnl']:.1f}%")
        print(f"  Profit Factor: {best_result['pf']:.2f}")
        print(f"  Avg Win: +{best_result['avg_win']:.1f}%")
        print(f"  Avg Loss: {best_result['avg_loss']:.1f}%")

        if best_result['monthly_pnl'] >= 5:
            print(f"\n✅ TARGET ACHIEVED: {best_result['monthly_pnl']:.1f}%/month!")
        else:
            print(f"\n⚠️ Current: {best_result['monthly_pnl']:.1f}%/month")

        # Show trades
        print(f"\nSample Winners:")
        for _, t in best_trades[best_trades['pnl'] > 0].head(5).iterrows():
            print(f"  {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: +{t['pnl']:.1f}%")

        print(f"\nSample Losers:")
        for _, t in best_trades[best_trades['pnl'] <= 0].head(5).iterrows():
            print(f"  {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: {t['pnl']:.1f}%")

        # Save
        import json
        import os
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_fast.json', 'w') as f:
            json.dump({'config': best_config, 'result': {k: float(v) for k, v in best_result.items()}}, f, indent=2)

        return best_config, best_result, best_trades

    return None, None, None


if __name__ == '__main__':
    main()
