#!/usr/bin/env python3
"""
RAPID TRADER OPTIMIZER V3
Simplified approach using existing infrastructure
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Use existing data manager
from api.data_manager import DataManager

# Config
START_DATE = datetime(2025, 10, 1)
END_DATE = datetime(2026, 1, 30)

# Universe
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


def load_data(dm, symbols):
    """Load data using existing data manager"""
    data = {}
    print(f"Loading {len(symbols)} stocks...")

    for sym in symbols:
        try:
            df = dm.get_price_data(sym, period='6mo')
            if df is not None and len(df) > 30:
                data[sym] = df
        except Exception as e:
            pass

    print(f"Loaded {len(data)} stocks")
    return data


def add_indicators(df):
    """Add technical indicators"""
    df = df.copy()

    # Ensure single column series
    for col in ['Close', 'High', 'Low', 'Open', 'Volume']:
        if col in df.columns:
            if isinstance(df[col], pd.DataFrame):
                df[col] = df[col].iloc[:, 0]

    c = df['Close']
    h = df['High']
    l = df['Low']

    # Momentum
    df['mom_1d'] = c.pct_change(1) * 100
    df['mom_3d'] = c.pct_change(3) * 100
    df['mom_5d'] = c.pct_change(5) * 100
    df['mom_20d'] = c.pct_change(20) * 100

    # Gap
    df['gap'] = (df['Open'] - c.shift(1)) / c.shift(1) * 100

    # RSI
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - 100 / (1 + rs)

    # ATR
    hl = h - l
    hc = abs(h - c.shift())
    lc = abs(l - c.shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = (df['atr'] / c * 100).fillna(2)

    # SMAs
    df['sma5'] = c.rolling(5).mean()
    df['sma20'] = c.rolling(20).mean()
    df['sma50'] = c.rolling(50).mean()

    # Volume
    df['vol_avg'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_avg']

    # Distance from high
    df['high_20d'] = h.rolling(20).max()
    df['dist_high'] = ((df['high_20d'] - c) / df['high_20d'] * 100).fillna(5)

    return df


def simulate_trade(df, entry_idx, sl_pct, tp_pct, max_days):
    """Simulate a trade"""
    try:
        entry_price = float(df.iloc[entry_idx]['Close'])
        sl_price = entry_price * (1 - sl_pct/100)
        tp_price = entry_price * (1 + tp_pct/100)

        for i in range(1, max_days + 1):
            if entry_idx + i >= len(df):
                break

            row = df.iloc[entry_idx + i]
            low = float(row['Low'])
            high = float(row['High'])
            close = float(row['Close'])

            # Check SL
            if low <= sl_price:
                return {
                    'pnl': -sl_pct,
                    'days': i,
                    'exit': 'SL',
                    'same_day': i == 1
                }

            # Check TP
            if high >= tp_price:
                return {
                    'pnl': tp_pct,
                    'days': i,
                    'exit': 'TP',
                    'same_day': False
                }

        # Time exit
        if entry_idx + max_days < len(df):
            exit_price = float(df.iloc[entry_idx + max_days]['Close'])
            pnl = (exit_price - entry_price) / entry_price * 100
            return {
                'pnl': pnl,
                'days': max_days,
                'exit': 'TIME',
                'same_day': False
            }
    except:
        pass

    return None


def backtest(data, config):
    """Run backtest"""
    all_trades = []

    for symbol, raw_df in data.items():
        try:
            df = add_indicators(raw_df)

            for i in range(50, len(df) - 10):
                row = df.iloc[i]
                date = df.index[i]

                if pd.Timestamp(date) < pd.Timestamp(START_DATE):
                    continue
                if pd.Timestamp(date) > pd.Timestamp(END_DATE):
                    continue

                # === ENTRY CONDITIONS ===
                mom_1d = float(row['mom_1d']) if not pd.isna(row['mom_1d']) else 0
                mom_5d = float(row['mom_5d']) if not pd.isna(row['mom_5d']) else 0
                rsi = float(row['rsi']) if not pd.isna(row['rsi']) else 50
                gap = float(row['gap']) if not pd.isna(row['gap']) else 0
                atr_pct = float(row['atr_pct']) if not pd.isna(row['atr_pct']) else 2
                dist_high = float(row['dist_high']) if not pd.isna(row['dist_high']) else 5
                close = float(row['Close'])
                sma5 = float(row['sma5']) if not pd.isna(row['sma5']) else close
                sma20 = float(row['sma20']) if not pd.isna(row['sma20']) else close
                sma50 = float(row['sma50']) if not pd.isna(row['sma50']) else close

                # 1. True dip
                if mom_1d > config['max_mom_1d']:
                    continue

                # 2. No gap up
                if gap > config['max_gap']:
                    continue

                # 3. RSI not overbought
                if rsi > config['max_rsi']:
                    continue

                # 4. Pullback
                if mom_5d > config['max_mom_5d']:
                    continue

                # 5. Uptrend
                if config['require_uptrend'] and sma20 < sma50:
                    continue

                # 6. Below SMA5
                if config['require_below_sma'] and close > sma5 * 1.01:
                    continue

                # 7. Volatility
                if atr_pct < config['min_atr'] or atr_pct > config['max_atr']:
                    continue

                # 8. Oversold required
                if config['require_oversold'] and rsi > 45:
                    continue

                # Calculate SL/TP
                sl_pct = min(max(atr_pct * config['atr_mult'], config['min_sl']), config['max_sl'])
                tp_pct = sl_pct * config['rr_ratio']

                # Simulate
                result = simulate_trade(df, i, sl_pct, tp_pct, config['max_hold'])

                if result:
                    all_trades.append({
                        'symbol': symbol,
                        'date': date,
                        'rsi': rsi,
                        'mom_1d': mom_1d,
                        'mom_5d': mom_5d,
                        **result
                    })

        except Exception as e:
            continue

    return pd.DataFrame(all_trades) if all_trades else pd.DataFrame()


def analyze(trades_df):
    """Analyze results"""
    if len(trades_df) == 0:
        return None

    total = len(trades_df)
    winners = len(trades_df[trades_df['pnl'] > 0])
    losers = total - winners

    total_pnl = trades_df['pnl'].sum()
    months = (END_DATE - START_DATE).days / 30
    monthly_pnl = total_pnl / months

    same_day_sl = len(trades_df[trades_df['same_day'] == True])

    return {
        'total': total,
        'winners': winners,
        'losers': losers,
        'win_rate': winners / total * 100 if total > 0 else 0,
        'total_pnl': total_pnl,
        'monthly_pnl': monthly_pnl,
        'avg_win': trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0,
        'avg_loss': trades_df[trades_df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0,
        'same_day_sl': same_day_sl,
        'same_day_pct': same_day_sl / total * 100 if total > 0 else 0,
    }


def main():
    """Main optimization"""
    dm = DataManager()
    data = load_data(dm, UNIVERSE)

    print("\n" + "=" * 70)
    print("  OPTIMIZING FOR 5-15% MONTHLY PROFIT")
    print("=" * 70)

    best_config = None
    best_monthly = -999
    best_result = None
    best_trades = None

    iteration = 0

    # Parameter grid - FOCUS ON STRICT FILTERING
    for max_mom_1d in [-3, -2, -1, 0]:
        for max_mom_5d in [-5, -3, -1, 0]:
            for max_rsi in [35, 40, 45, 50, 55]:
                for require_oversold in [True, False]:
                    for rr_ratio in [2.5, 3.0, 3.5, 4.0]:
                        for max_hold in [3, 5, 7]:

                            config = {
                                'max_mom_1d': max_mom_1d,
                                'max_mom_5d': max_mom_5d,
                                'max_gap': 1.5,
                                'max_rsi': max_rsi,
                                'require_uptrend': True,
                                'require_below_sma': True,
                                'require_oversold': require_oversold,
                                'min_atr': 1.5,
                                'max_atr': 8,
                                'atr_mult': 1.0,
                                'min_sl': 1.5,
                                'max_sl': 2.5,
                                'rr_ratio': rr_ratio,
                                'max_hold': max_hold,
                            }

                            iteration += 1
                            trades = backtest(data, config)

                            if len(trades) < 5:
                                continue

                            result = analyze(trades)
                            if result is None:
                                continue

                            # Target: high monthly, good win rate, low PDT
                            if (result['monthly_pnl'] > best_monthly and
                                result['win_rate'] >= 40 and
                                result['same_day_pct'] < 25):

                                best_monthly = result['monthly_pnl']
                                best_config = config.copy()
                                best_result = result.copy()
                                best_trades = trades.copy()

                                print(f"\n[{iteration}] NEW BEST!")
                                print(f"  Monthly: {result['monthly_pnl']:.1f}%")
                                print(f"  Win Rate: {result['win_rate']:.0f}%")
                                print(f"  Trades: {result['total']} (W:{result['winners']} L:{result['losers']})")
                                print(f"  Same-day SL: {result['same_day_pct']:.0f}%")
                                print(f"  Avg Win/Loss: +{result['avg_win']:.1f}% / {result['avg_loss']:.1f}%")

                            if iteration % 200 == 0:
                                print(f"  Progress: {iteration} configs tested...")

    # Final results
    print("\n" + "=" * 70)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 70)

    if best_result:
        print(f"\nBEST CONFIG:")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nBEST RESULTS:")
        print(f"  Trades: {best_result['total']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.0f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Total P&L: {best_result['total_pnl']:.1f}%")
        print(f"  Monthly P&L: {best_result['monthly_pnl']:.1f}%")
        print(f"  Same-day SL: {best_result['same_day_pct']:.0f}%")

        if best_result['monthly_pnl'] >= 5:
            print(f"\n✅ TARGET ACHIEVED: {best_result['monthly_pnl']:.1f}%/month!")
        else:
            print(f"\n⚠️ Current: {best_result['monthly_pnl']:.1f}%/month - need more optimization")

        # Save config
        import json
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_v3.json', 'w') as f:
            json.dump(best_config, f, indent=2)

        return best_config, best_result, best_trades

    return None, None, None


if __name__ == '__main__':
    best_config, best_result, best_trades = main()
