#!/usr/bin/env python3
"""
RAPID TRADER OPTIMIZER V6
Properly handles DataManager output format
Target: 5-15% monthly profit with very low losers
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

from api.data_manager import DataManager

# Config
START_DATE = pd.Timestamp('2025-10-01')
END_DATE = pd.Timestamp('2026-01-30')

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
    """Load and prepare data"""
    data = {}
    print(f"Loading {len(symbols)} stocks...")

    for sym in symbols:
        try:
            df = dm.get_price_data(sym, period='6mo')
            if df is None or len(df) < 50:
                continue

            # Standardize column names (lowercase to Title case)
            df = df.rename(columns={
                'date': 'Date',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })

            # Ensure Date column exists
            if 'Date' not in df.columns:
                continue

            # Convert to numeric
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Make Date timezone naive for comparison
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)

            data[sym] = df

        except Exception as e:
            pass

    print(f"Loaded {len(data)} stocks successfully")
    return data


def add_indicators(df):
    """Add technical indicators"""
    df = df.copy()

    c = df['Close']
    h = df['High']
    l = df['Low']
    v = df['Volume']

    # Momentum
    df['mom_1d'] = c.pct_change(1) * 100
    df['mom_3d'] = c.pct_change(3) * 100
    df['mom_5d'] = c.pct_change(5) * 100
    df['mom_10d'] = c.pct_change(10) * 100
    df['mom_20d'] = c.pct_change(20) * 100

    # Gap
    prev_close = c.shift(1)
    df['gap'] = (df['Open'] - prev_close) / prev_close * 100

    # RSI
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 0.0001)
    df['rsi'] = 100 - 100 / (1 + rs)

    # ATR
    hl = h - l
    hc = abs(h - prev_close)
    lc = abs(l - prev_close)
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = (df['atr'] / c * 100)

    # SMAs
    df['sma5'] = c.rolling(5).mean()
    df['sma10'] = c.rolling(10).mean()
    df['sma20'] = c.rolling(20).mean()
    df['sma50'] = c.rolling(50).mean()

    # Volume
    df['vol_avg'] = v.rolling(20).mean()
    df['vol_ratio'] = v / (df['vol_avg'] + 1)

    # Distance from 20d high
    df['high_20d'] = h.rolling(20).max()
    df['dist_high'] = ((df['high_20d'] - c) / df['high_20d'] * 100)

    # Bollinger
    df['bb_mid'] = c.rolling(20).mean()
    std = c.rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - 2 * std
    df['bb_upper'] = df['bb_mid'] + 2 * std
    df['bb_pct'] = (c - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 0.0001)

    return df


def simulate_trade(df, entry_idx, sl_pct, tp_pct, max_days, trailing=False):
    """Simulate a single trade"""
    entry_price = df.iloc[entry_idx]['Close']
    sl_price = entry_price * (1 - sl_pct/100)
    tp_price = entry_price * (1 + tp_pct/100)

    highest = entry_price

    for i in range(1, max_days + 1):
        if entry_idx + i >= len(df):
            break

        row = df.iloc[entry_idx + i]
        low = row['Low']
        high = row['High']
        close = row['Close']

        # Trailing stop
        if trailing and high > highest:
            highest = high
            profit = (highest - entry_price) / entry_price * 100
            if profit > sl_pct:
                new_sl = entry_price * (1 + (profit - sl_pct) / 2 / 100)
                sl_price = max(sl_price, new_sl)

        # Check SL hit
        if low <= sl_price:
            pnl = (sl_price - entry_price) / entry_price * 100
            return {'pnl': pnl, 'days': i, 'exit': 'SL', 'same_day': i == 1}

        # Check TP hit
        if high >= tp_price:
            return {'pnl': tp_pct, 'days': i, 'exit': 'TP', 'same_day': False}

    # Time exit
    if entry_idx + max_days < len(df):
        exit_price = df.iloc[entry_idx + max_days]['Close']
        pnl = (exit_price - entry_price) / entry_price * 100
        return {'pnl': pnl, 'days': max_days, 'exit': 'TIME', 'same_day': False}

    return None


def backtest(data, config, debug=False):
    """Run backtest with given config"""
    all_trades = []
    filter_stats = defaultdict(int)

    for symbol, raw_df in data.items():
        try:
            df = add_indicators(raw_df)

            for i in range(50, len(df) - 10):
                row = df.iloc[i]
                date = row['Date']

                # Date filter
                if date < START_DATE or date > END_DATE:
                    continue

                filter_stats['total_days'] += 1

                # Extract values
                mom_1d = row['mom_1d'] if pd.notna(row['mom_1d']) else 0
                mom_5d = row['mom_5d'] if pd.notna(row['mom_5d']) else 0
                rsi = row['rsi'] if pd.notna(row['rsi']) else 50
                gap = row['gap'] if pd.notna(row['gap']) else 0
                atr_pct = row['atr_pct'] if pd.notna(row['atr_pct']) else 2
                dist_high = row['dist_high'] if pd.notna(row['dist_high']) else 5
                close = row['Close']
                sma5 = row['sma5'] if pd.notna(row['sma5']) else close
                sma20 = row['sma20'] if pd.notna(row['sma20']) else close
                sma50 = row['sma50'] if pd.notna(row['sma50']) else close
                vol_ratio = row['vol_ratio'] if pd.notna(row['vol_ratio']) else 1
                bb_pct = row['bb_pct'] if pd.notna(row['bb_pct']) else 0.5

                strategy = config.get('strategy', 'dip')

                # === DIP BUYING STRATEGY ===
                if strategy == 'dip':
                    if mom_1d > config.get('max_mom_1d', 2):
                        filter_stats['mom_1d_fail'] += 1
                        continue

                    if gap > config.get('max_gap', 2):
                        filter_stats['gap_fail'] += 1
                        continue

                    if rsi > config.get('max_rsi', 60):
                        filter_stats['rsi_fail'] += 1
                        continue

                    if mom_5d > config.get('max_mom_5d', 5):
                        filter_stats['mom_5d_fail'] += 1
                        continue

                    if config.get('require_uptrend', False) and sma20 < sma50:
                        filter_stats['uptrend_fail'] += 1
                        continue

                # === BREAKOUT STRATEGY ===
                elif strategy == 'breakout':
                    if mom_1d < config.get('min_mom_1d', 1):
                        filter_stats['mom_1d_fail'] += 1
                        continue

                    if rsi < config.get('min_rsi', 50) or rsi > config.get('max_rsi', 75):
                        filter_stats['rsi_fail'] += 1
                        continue

                    if vol_ratio < config.get('min_vol_ratio', 1.2):
                        filter_stats['vol_fail'] += 1
                        continue

                    if dist_high > config.get('max_dist_high', 5):
                        filter_stats['dist_high_fail'] += 1
                        continue

                # === MEAN REVERSION STRATEGY ===
                elif strategy == 'mean_reversion':
                    if bb_pct > config.get('max_bb_pct', 0.3):
                        filter_stats['bb_fail'] += 1
                        continue

                    if rsi > config.get('max_rsi', 35):
                        filter_stats['rsi_fail'] += 1
                        continue

                filter_stats['passed'] += 1

                # Calculate position sizing
                sl_pct = min(max(atr_pct * config.get('atr_mult', 1.0),
                                 config.get('min_sl', 1.5)),
                             config.get('max_sl', 3.0))
                tp_pct = sl_pct * config.get('rr_ratio', 2.0)

                # Simulate trade
                result = simulate_trade(
                    df, i, sl_pct, tp_pct,
                    config.get('max_hold', 5),
                    trailing=config.get('trailing', False)
                )

                if result:
                    all_trades.append({
                        'symbol': symbol,
                        'date': date,
                        'rsi': rsi,
                        'mom_1d': mom_1d,
                        'mom_5d': mom_5d,
                        'sl_pct': sl_pct,
                        'tp_pct': tp_pct,
                        **result
                    })

        except Exception as e:
            if debug:
                print(f"  Error {symbol}: {e}")

    if debug:
        print(f"\n  Filter Stats:")
        for k, v in sorted(filter_stats.items()):
            print(f"    {k}: {v}")

    return pd.DataFrame(all_trades) if all_trades else pd.DataFrame()


def analyze(trades_df):
    """Analyze backtest results"""
    if len(trades_df) == 0:
        return None

    total = len(trades_df)
    winners = len(trades_df[trades_df['pnl'] > 0])
    losers = total - winners

    total_pnl = trades_df['pnl'].sum()
    months = (END_DATE - START_DATE).days / 30
    monthly_pnl = total_pnl / months

    same_day_sl = len(trades_df[trades_df['same_day'] == True])

    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0

    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] <= 0]['pnl'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999

    return {
        'total': total,
        'winners': winners,
        'losers': losers,
        'win_rate': winners / total * 100 if total > 0 else 0,
        'total_pnl': total_pnl,
        'monthly_pnl': monthly_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'same_day_sl': same_day_sl,
        'same_day_pct': same_day_sl / total * 100 if total > 0 else 0,
    }


def run_diagnostic(data):
    """Diagnostic test"""
    print("\n" + "=" * 70)
    print("  DIAGNOSTIC: Testing data and no filters")
    print("=" * 70)

    # No filters
    config = {
        'strategy': 'dip',
        'max_mom_1d': 100,
        'max_gap': 100,
        'max_rsi': 100,
        'max_mom_5d': 100,
        'require_uptrend': False,
        'min_sl': 2,
        'max_sl': 4,
        'rr_ratio': 2.0,
        'max_hold': 5,
    }

    trades = backtest(data, config, debug=True)
    result = analyze(trades)

    if result:
        print(f"\n  With NO FILTERS:")
        print(f"    Trades: {result['total']}")
        print(f"    Win Rate: {result['win_rate']:.0f}%")
        print(f"    Monthly P&L: {result['monthly_pnl']:.1f}%")
        print(f"    Avg Win: +{result['avg_win']:.1f}%")
        print(f"    Avg Loss: {result['avg_loss']:.1f}%")

        print(f"\n  Sample trades:")
        for _, t in trades.head(5).iterrows():
            print(f"    {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: {t['pnl']:.1f}% ({t['exit']})")
    else:
        print("\n  ERROR: No trades generated!")

    return trades, result


def optimize(data):
    """Main optimization loop"""
    print("\n" + "=" * 70)
    print("  OPTIMIZING FOR 5-15% MONTHLY WITH LOW LOSERS")
    print("=" * 70)

    best_config = None
    best_score = -999
    best_result = None
    best_trades = None

    iteration = 0

    # Strategy 1: DIP BUYING
    print("\n  Testing DIP strategy...")
    for max_mom_1d in [0, 1, 2, 3, 5]:
        for max_mom_5d in [0, 3, 5, 10, 15]:
            for max_rsi in [40, 50, 60, 70]:
                for rr_ratio in [1.5, 2.0, 2.5, 3.0]:
                    for max_hold in [3, 5, 7, 10]:
                        for trailing in [True, False]:

                            config = {
                                'strategy': 'dip',
                                'max_mom_1d': max_mom_1d,
                                'max_mom_5d': max_mom_5d,
                                'max_gap': 2,
                                'max_rsi': max_rsi,
                                'require_uptrend': False,
                                'min_sl': 1.5,
                                'max_sl': 3.0,
                                'atr_mult': 1.0,
                                'rr_ratio': rr_ratio,
                                'max_hold': max_hold,
                                'trailing': trailing,
                            }

                            iteration += 1
                            trades = backtest(data, config)

                            if len(trades) < 10:
                                continue

                            result = analyze(trades)
                            if result is None:
                                continue

                            # Scoring: prioritize monthly profit and low loser ratio
                            loser_ratio = result['losers'] / max(result['winners'], 1)
                            score = (
                                result['monthly_pnl'] * 3 +
                                result['profit_factor'] * 5 +
                                result['win_rate'] * 0.2 -
                                loser_ratio * 15 -
                                result['same_day_pct'] * 0.3
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
                                print(f"    PF: {result['profit_factor']:.2f}")

                            if iteration % 500 == 0:
                                print(f"    Progress: {iteration} configs...")

    # Strategy 2: BREAKOUT
    print("\n  Testing BREAKOUT strategy...")
    for min_mom_1d in [0.5, 1, 2, 3]:
        for min_rsi in [45, 50, 55]:
            for max_rsi in [65, 70, 75, 80]:
                for rr_ratio in [1.5, 2.0, 2.5]:
                    for max_hold in [3, 5, 7]:

                        config = {
                            'strategy': 'breakout',
                            'min_mom_1d': min_mom_1d,
                            'min_rsi': min_rsi,
                            'max_rsi': max_rsi,
                            'min_vol_ratio': 1.2,
                            'max_dist_high': 5,
                            'min_sl': 1.5,
                            'max_sl': 3.0,
                            'atr_mult': 1.0,
                            'rr_ratio': rr_ratio,
                            'max_hold': max_hold,
                            'trailing': True,
                        }

                        iteration += 1
                        trades = backtest(data, config)

                        if len(trades) < 10:
                            continue

                        result = analyze(trades)
                        if result is None:
                            continue

                        loser_ratio = result['losers'] / max(result['winners'], 1)
                        score = (
                            result['monthly_pnl'] * 3 +
                            result['profit_factor'] * 5 +
                            result['win_rate'] * 0.2 -
                            loser_ratio * 15 -
                            result['same_day_pct'] * 0.3
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

                        if iteration % 300 == 0:
                            print(f"    Progress: {iteration} configs...")

    # Strategy 3: MEAN REVERSION
    print("\n  Testing MEAN REVERSION strategy...")
    for max_bb_pct in [0.1, 0.2, 0.3, 0.4]:
        for max_rsi in [25, 30, 35, 40, 45]:
            for rr_ratio in [1.5, 2.0, 2.5, 3.0]:
                for max_hold in [3, 5, 7]:

                    config = {
                        'strategy': 'mean_reversion',
                        'max_bb_pct': max_bb_pct,
                        'max_rsi': max_rsi,
                        'min_sl': 2.0,
                        'max_sl': 4.0,
                        'atr_mult': 1.0,
                        'rr_ratio': rr_ratio,
                        'max_hold': max_hold,
                        'trailing': False,
                    }

                    iteration += 1
                    trades = backtest(data, config)

                    if len(trades) < 10:
                        continue

                    result = analyze(trades)
                    if result is None:
                        continue

                    loser_ratio = result['losers'] / max(result['winners'], 1)
                    score = (
                        result['monthly_pnl'] * 3 +
                        result['profit_factor'] * 5 +
                        result['win_rate'] * 0.2 -
                        loser_ratio * 15 -
                        result['same_day_pct'] * 0.3
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

                    if iteration % 200 == 0:
                        print(f"    Progress: {iteration} configs...")

    print(f"\n  Total configs tested: {iteration}")
    return best_config, best_result, best_trades


def main():
    """Main function"""
    print("=" * 70)
    print("  RAPID TRADER OPTIMIZER V6")
    print("  Target: 5-15% monthly profit with very low losers")
    print("=" * 70)

    dm = DataManager()
    data = load_data(dm, UNIVERSE)

    if len(data) < 10:
        print("ERROR: Not enough data!")
        return None, None, None

    # Run diagnostic
    run_diagnostic(data)

    # Run optimization
    best_config, best_result, best_trades = optimize(data)

    # Show final results
    print("\n" + "=" * 70)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 70)

    if best_result:
        print(f"\nBEST CONFIG ({best_config.get('strategy', 'unknown')}):")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nPERFORMANCE:")
        print(f"  Total Trades: {best_result['total']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.0f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Total P&L: {best_result['total_pnl']:.1f}%")
        print(f"  Monthly P&L: {best_result['monthly_pnl']:.1f}%")
        print(f"  Profit Factor: {best_result['profit_factor']:.2f}")
        print(f"  Avg Win: +{best_result['avg_win']:.1f}%")
        print(f"  Avg Loss: {best_result['avg_loss']:.1f}%")
        print(f"  Same-day SL: {best_result['same_day_pct']:.0f}%")

        if best_result['monthly_pnl'] >= 5:
            print(f"\n✅ TARGET ACHIEVED: {best_result['monthly_pnl']:.1f}%/month!")
        elif best_result['monthly_pnl'] >= 3:
            print(f"\n⚠️ Getting closer: {best_result['monthly_pnl']:.1f}%/month")
        else:
            print(f"\n❌ Current: {best_result['monthly_pnl']:.1f}%/month - continuing...")

        # Save config
        import json
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_v6.json', 'w') as f:
            json.dump({
                'config': best_config,
                'performance': {k: float(v) if isinstance(v, (np.floating, np.integer)) else v
                               for k, v in best_result.items()}
            }, f, indent=2)

        # Show trades
        if best_trades is not None and len(best_trades) > 0:
            print(f"\nSample Winners:")
            for _, t in best_trades[best_trades['pnl'] > 0].head(5).iterrows():
                print(f"  {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: +{t['pnl']:.1f}% ({t['days']}d)")

            print(f"\nSample Losers:")
            for _, t in best_trades[best_trades['pnl'] <= 0].head(5).iterrows():
                print(f"  {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: {t['pnl']:.1f}% ({t['days']}d)")

        return best_config, best_result, best_trades

    print("\nNo profitable config found!")
    return None, None, None


if __name__ == '__main__':
    best_config, best_result, best_trades = main()
