#!/usr/bin/env python3
"""
FINAL OPTIMIZER - Stricter filters for low losers
Target: 5-15% monthly profit with very low losers
"""

import sys
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from api.data_manager import DataManager

START_DATE = pd.Timestamp('2025-10-01')
END_DATE = pd.Timestamp('2026-01-30')

MAX_POSITIONS = 5
MAX_NEW_TRADES_PER_DAY = 2
POSITION_SIZE = 0.20

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

            c = df['Close']
            df['mom_1d'] = c.pct_change(1) * 100
            df['mom_5d'] = c.pct_change(5) * 100
            df['mom_10d'] = c.pct_change(10) * 100

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

            # Bollinger
            df['bb_mid'] = c.rolling(20).mean()
            std = c.rolling(20).std()
            df['bb_lower'] = df['bb_mid'] - 2 * std
            df['bb_pct'] = (c - df['bb_lower']) / (4 * std + 0.0001)

            df = df.set_index('Date')
            data[sym] = df

        except:
            pass

    return data


def run_portfolio_backtest(data, config):
    """Run realistic portfolio backtest"""
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    trading_dates = sorted([d for d in all_dates if START_DATE <= d <= END_DATE])

    open_positions = []
    closed_trades = []
    capital = 100000
    current_capital = capital

    for date in trading_dates:
        # Close positions
        positions_to_remove = []
        for pos in open_positions:
            sym = pos['symbol']
            if sym not in data or date not in data[sym].index:
                continue

            row = data[sym].loc[date]
            entry_price = pos['entry_price']
            sl_price = pos['sl_price']
            tp_price = pos['tp_price']

            if row['Low'] <= sl_price:
                pnl_pct = (sl_price - entry_price) / entry_price * 100
                closed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'pnl_pct': pnl_pct,
                    'exit': 'SL'
                })
                current_capital *= (1 + pnl_pct * POSITION_SIZE / 100)
                positions_to_remove.append(pos)
                continue

            if row['High'] >= tp_price:
                pnl_pct = (tp_price - entry_price) / entry_price * 100
                closed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'pnl_pct': pnl_pct,
                    'exit': 'TP'
                })
                current_capital *= (1 + pnl_pct * POSITION_SIZE / 100)
                positions_to_remove.append(pos)
                continue

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
                current_capital *= (1 + pnl_pct * POSITION_SIZE / 100)
                positions_to_remove.append(pos)

        for pos in positions_to_remove:
            open_positions.remove(pos)

        # Find new entries
        current_symbols = [p['symbol'] for p in open_positions]
        signals = []

        for sym, df in data.items():
            if sym in current_symbols:
                continue
            if date not in df.index:
                continue

            row = df.loc[date]

            mom_1d = row['mom_1d'] if pd.notna(row['mom_1d']) else 0
            mom_5d = row['mom_5d'] if pd.notna(row['mom_5d']) else 0
            mom_10d = row['mom_10d'] if pd.notna(row['mom_10d']) else 0
            rsi = row['rsi'] if pd.notna(row['rsi']) else 50
            gap = row['gap'] if pd.notna(row['gap']) else 0
            atr_pct = row['atr_pct'] if pd.notna(row['atr_pct']) else 2
            sma20 = row['sma20'] if pd.notna(row['sma20']) else row['Close']
            sma50 = row['sma50'] if pd.notna(row['sma50']) else row['Close']
            vol_ratio = row['vol_ratio'] if pd.notna(row['vol_ratio']) else 1
            bb_pct = row['bb_pct'] if pd.notna(row['bb_pct']) else 0.5
            close = row['Close']

            strategy = config.get('strategy', 'dip')

            if strategy == 'dip':
                # Dip buying - strict filters
                if mom_1d > config.get('max_mom_1d', 1):
                    continue
                if gap > config.get('max_gap', 1):
                    continue
                if rsi > config.get('max_rsi', 50):
                    continue
                if mom_5d > config.get('max_mom_5d', 3):
                    continue
                if config.get('require_uptrend', True) and sma20 < sma50:
                    continue

            elif strategy == 'breakout':
                # Breakout
                if mom_1d < config.get('min_mom_1d', 2):
                    continue
                if rsi < config.get('min_rsi', 55) or rsi > config.get('max_rsi', 75):
                    continue
                if vol_ratio < config.get('min_vol_ratio', 1.5):
                    continue

            elif strategy == 'mean_reversion':
                # Mean reversion - very oversold
                if bb_pct > config.get('max_bb_pct', 0.2):
                    continue
                if rsi > config.get('max_rsi', 35):
                    continue
                if mom_5d < config.get('min_mom_5d', -12):
                    continue

            sl_pct = min(max(atr_pct * config.get('atr_mult', 1.0), config.get('min_sl', 1.5)), config.get('max_sl', 2.5))
            tp_pct = sl_pct * config.get('rr_ratio', 2.5)

            score = 100 - rsi if strategy == 'dip' else rsi

            signals.append({
                'symbol': sym,
                'entry_price': close,
                'sl_pct': sl_pct,
                'tp_pct': tp_pct,
                'score': score,
            })

        signals.sort(key=lambda x: x['score'], reverse=True)

        new_entries = 0
        for sig in signals:
            if len(open_positions) >= MAX_POSITIONS:
                break
            if new_entries >= MAX_NEW_TRADES_PER_DAY:
                break

            open_positions.append({
                'symbol': sig['symbol'],
                'entry_date': date,
                'entry_price': sig['entry_price'],
                'sl_price': sig['entry_price'] * (1 - sig['sl_pct'] / 100),
                'tp_price': sig['entry_price'] * (1 + sig['tp_pct'] / 100),
            })
            new_entries += 1

    return closed_trades, current_capital


def analyze(trades, final_capital):
    """Analyze results"""
    if not trades:
        return None

    trades_df = pd.DataFrame(trades)
    total = len(trades_df)
    winners = len(trades_df[trades_df['pnl_pct'] > 0])
    losers = total - winners

    total_return = (final_capital - 100000) / 100000 * 100
    months = (END_DATE - START_DATE).days / 30
    monthly_return = total_return / months

    return {
        'total': total,
        'winners': winners,
        'losers': losers,
        'win_rate': winners / total * 100 if total > 0 else 0,
        'total_return': total_return,
        'monthly_return': monthly_return,
        'loser_ratio': losers / max(winners, 1),
    }


def main():
    print("=" * 60)
    print("  FINAL OPTIMIZER - Strict Filters")
    print("=" * 60)

    dm = DataManager()
    print("Loading data...")
    data = load_and_prep(dm, UNIVERSE)
    print(f"Loaded {len(data)} stocks")

    best_config = None
    best_monthly = -999
    best_result = None
    iteration = 0

    # Strategy 1: STRICT DIP BUYING
    print("\nTesting STRICT DIP strategy...")
    for max_mom_1d in [-1, 0, 1]:  # Very strict - only down days or flat
        for max_mom_5d in [-3, 0, 3]:  # Recent pullback
            for max_rsi in [35, 40, 45, 50]:  # Oversold
                for rr_ratio in [2.0, 2.5, 3.0]:
                    for max_hold in [5, 7, 10]:
                        for require_uptrend in [True, False]:

                            config = {
                                'strategy': 'dip',
                                'max_mom_1d': max_mom_1d,
                                'max_mom_5d': max_mom_5d,
                                'max_gap': 1,
                                'max_rsi': max_rsi,
                                'require_uptrend': require_uptrend,
                                'min_sl': 1.5,
                                'max_sl': 2.5,
                                'atr_mult': 1.0,
                                'rr_ratio': rr_ratio,
                                'max_hold': max_hold,
                            }

                            iteration += 1
                            trades, final_cap = run_portfolio_backtest(data, config)
                            result = analyze(trades, final_cap)

                            if result and result['total'] >= 20:
                                # Score: monthly return, penalize losers
                                score = result['monthly_return'] - result['loser_ratio'] * 2

                                if result['monthly_return'] > best_monthly:
                                    best_monthly = result['monthly_return']
                                    best_config = config.copy()
                                    best_result = result.copy()

                                    print(f"\n  [{iteration}] NEW BEST:")
                                    print(f"    Monthly: {result['monthly_return']:.1f}%")
                                    print(f"    Win Rate: {result['win_rate']:.0f}%")
                                    print(f"    W/L: {result['winners']}/{result['losers']}")

                            if iteration % 200 == 0:
                                print(f"    Progress: {iteration}...")

    # Strategy 2: BREAKOUT
    print("\nTesting BREAKOUT strategy...")
    for min_mom_1d in [1, 2, 3]:
        for min_rsi in [50, 55, 60]:
            for max_rsi in [70, 75]:
                for min_vol_ratio in [1.3, 1.5, 2.0]:
                    for rr_ratio in [2.0, 2.5]:
                        for max_hold in [5, 7]:

                            config = {
                                'strategy': 'breakout',
                                'min_mom_1d': min_mom_1d,
                                'min_rsi': min_rsi,
                                'max_rsi': max_rsi,
                                'min_vol_ratio': min_vol_ratio,
                                'min_sl': 1.5,
                                'max_sl': 2.5,
                                'atr_mult': 1.0,
                                'rr_ratio': rr_ratio,
                                'max_hold': max_hold,
                            }

                            iteration += 1
                            trades, final_cap = run_portfolio_backtest(data, config)
                            result = analyze(trades, final_cap)

                            if result and result['total'] >= 20:
                                if result['monthly_return'] > best_monthly:
                                    best_monthly = result['monthly_return']
                                    best_config = config.copy()
                                    best_result = result.copy()

                                    print(f"\n  [{iteration}] NEW BEST:")
                                    print(f"    Monthly: {result['monthly_return']:.1f}%")
                                    print(f"    Win Rate: {result['win_rate']:.0f}%")
                                    print(f"    W/L: {result['winners']}/{result['losers']}")

                            if iteration % 200 == 0:
                                print(f"    Progress: {iteration}...")

    # Strategy 3: MEAN REVERSION
    print("\nTesting MEAN REVERSION strategy...")
    for max_bb_pct in [0.1, 0.15, 0.2, 0.25]:
        for max_rsi in [25, 30, 35, 40]:
            for min_mom_5d in [-15, -12, -10]:
                for rr_ratio in [2.0, 2.5, 3.0]:
                    for max_hold in [5, 7, 10]:

                        config = {
                            'strategy': 'mean_reversion',
                            'max_bb_pct': max_bb_pct,
                            'max_rsi': max_rsi,
                            'min_mom_5d': min_mom_5d,
                            'min_sl': 2.0,
                            'max_sl': 3.0,
                            'atr_mult': 1.0,
                            'rr_ratio': rr_ratio,
                            'max_hold': max_hold,
                        }

                        iteration += 1
                        trades, final_cap = run_portfolio_backtest(data, config)
                        result = analyze(trades, final_cap)

                        if result and result['total'] >= 10:
                            if result['monthly_return'] > best_monthly:
                                best_monthly = result['monthly_return']
                                best_config = config.copy()
                                best_result = result.copy()

                                print(f"\n  [{iteration}] NEW BEST:")
                                print(f"    Monthly: {result['monthly_return']:.1f}%")
                                print(f"    Win Rate: {result['win_rate']:.0f}%")
                                print(f"    W/L: {result['winners']}/{result['losers']}")

                        if iteration % 200 == 0:
                            print(f"    Progress: {iteration}...")

    # Final results
    print("\n" + "=" * 60)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 60)
    print(f"  Tested: {iteration} configurations")

    if best_result:
        print(f"\nBEST CONFIG ({best_config.get('strategy', 'unknown')}):")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nPERFORMANCE:")
        print(f"  Trades: {best_result['total']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.0f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Monthly Return: {best_result['monthly_return']:.1f}%")
        print(f"  Total Return: {best_result['total_return']:.1f}%")

        if best_result['monthly_return'] >= 5:
            print(f"\n✅ TARGET ACHIEVED: {best_result['monthly_return']:.1f}%/month!")
        elif best_result['monthly_return'] >= 3:
            print(f"\n⚠️ Getting closer: {best_result['monthly_return']:.1f}%/month")
        else:
            print(f"\n❌ Current: {best_result['monthly_return']:.1f}%/month - need different approach")

        # Save
        import json
        import os
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_final.json', 'w') as f:
            json.dump({
                'config': best_config,
                'result': {k: float(v) for k, v in best_result.items()}
            }, f, indent=2)

    return best_config, best_result


if __name__ == '__main__':
    main()
