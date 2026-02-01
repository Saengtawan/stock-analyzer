#!/usr/bin/env python3
"""
RAPID TRADER OPTIMIZER V5
Fixed data format handling - uses correct column names
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


def standardize_df(df):
    """Standardize DataFrame columns and index"""
    df = df.copy()

    # Handle column names - convert to standard capitalized format
    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower == 'close':
            col_map[col] = 'Close'
        elif col_lower == 'open':
            col_map[col] = 'Open'
        elif col_lower == 'high':
            col_map[col] = 'High'
        elif col_lower == 'low':
            col_map[col] = 'Low'
        elif col_lower == 'volume':
            col_map[col] = 'Volume'
        elif col_lower == 'date':
            col_map[col] = 'Date'

    df = df.rename(columns=col_map)

    # Set date as index if it exists as column
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
    elif not isinstance(df.index, pd.DatetimeIndex):
        # Try to find a date-like column
        for col in df.columns:
            if 'date' in str(col).lower():
                df[col] = pd.to_datetime(df[col])
                df = df.set_index(col)
                break

    return df


def load_data(dm, symbols):
    """Load and standardize data"""
    data = {}
    print(f"Loading {len(symbols)} stocks...")

    for sym in symbols:
        try:
            df = dm.get_price_data(sym, period='6mo')
            if df is not None and len(df) > 30:
                df = standardize_df(df)
                # Verify required columns exist
                if all(col in df.columns for col in ['Close', 'High', 'Low', 'Open', 'Volume']):
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
            # Convert to float
            df[col] = pd.to_numeric(df[col], errors='coerce')

    c = df['Close']
    h = df['High']
    l = df['Low']

    # Momentum
    df['mom_1d'] = c.pct_change(1) * 100
    df['mom_3d'] = c.pct_change(3) * 100
    df['mom_5d'] = c.pct_change(5) * 100
    df['mom_10d'] = c.pct_change(10) * 100
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
    df['sma10'] = c.rolling(10).mean()
    df['sma20'] = c.rolling(20).mean()
    df['sma50'] = c.rolling(50).mean()

    # Volume
    df['vol_avg'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_avg']

    # Distance from 20d high
    df['high_20d'] = h.rolling(20).max()
    df['dist_high'] = ((df['high_20d'] - c) / df['high_20d'] * 100).fillna(5)

    # Bollinger Bands
    df['bb_mid'] = c.rolling(20).mean()
    df['bb_std'] = c.rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_pct'] = (c - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

    return df


def simulate_trade(df, entry_idx, sl_pct, tp_pct, max_days, trailing_stop=False):
    """Simulate a trade"""
    try:
        entry_price = float(df.iloc[entry_idx]['Close'])
        sl_price = entry_price * (1 - sl_pct/100)
        tp_price = entry_price * (1 + tp_pct/100)

        highest_price = entry_price

        for i in range(1, max_days + 1):
            if entry_idx + i >= len(df):
                break

            row = df.iloc[entry_idx + i]
            low = float(row['Low'])
            high = float(row['High'])
            close = float(row['Close'])

            # Trailing stop
            if trailing_stop and high > highest_price:
                highest_price = high
                profit_pct = (highest_price - entry_price) / entry_price * 100
                if profit_pct > sl_pct:
                    # Trail at breakeven + small profit once we're up
                    new_sl = entry_price * (1 + (profit_pct - sl_pct) / 2 / 100)
                    sl_price = max(sl_price, new_sl)

            # Check SL
            if low <= sl_price:
                pnl = (sl_price - entry_price) / entry_price * 100
                return {
                    'pnl': pnl,
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


def backtest(data, config, debug=False):
    """Run backtest"""
    all_trades = []
    filter_stats = defaultdict(int)

    for symbol, raw_df in data.items():
        try:
            df = add_indicators(raw_df)

            for i in range(50, len(df) - 10):
                row = df.iloc[i]
                date = df.index[i]

                # Date filtering
                try:
                    ts = pd.Timestamp(date)
                    if ts < pd.Timestamp(START_DATE) or ts > pd.Timestamp(END_DATE):
                        continue
                except:
                    continue

                filter_stats['total_days'] += 1

                # Get values safely
                def safe_float(val, default=0):
                    try:
                        v = float(val)
                        return v if not pd.isna(v) else default
                    except:
                        return default

                mom_1d = safe_float(row.get('mom_1d', 0), 0)
                mom_5d = safe_float(row.get('mom_5d', 0), 0)
                mom_10d = safe_float(row.get('mom_10d', 0), 0)
                rsi = safe_float(row.get('rsi', 50), 50)
                gap = safe_float(row.get('gap', 0), 0)
                atr_pct = safe_float(row.get('atr_pct', 2), 2)
                dist_high = safe_float(row.get('dist_high', 5), 5)
                close = safe_float(row['Close'], 0)
                sma5 = safe_float(row.get('sma5', close), close)
                sma20 = safe_float(row.get('sma20', close), close)
                sma50 = safe_float(row.get('sma50', close), close)
                vol_ratio = safe_float(row.get('vol_ratio', 1), 1)
                bb_pct = safe_float(row.get('bb_pct', 0.5), 0.5)

                if close <= 0:
                    continue

                # Strategy
                strategy = config.get('strategy', 'dip')

                if strategy == 'dip':
                    # 1. Recent move filter
                    if mom_1d > config.get('max_mom_1d', 2):
                        filter_stats['mom_1d_fail'] += 1
                        continue

                    # 2. Gap filter
                    if gap > config.get('max_gap', 2):
                        filter_stats['gap_fail'] += 1
                        continue

                    # 3. RSI filter
                    if rsi > config.get('max_rsi', 60):
                        filter_stats['rsi_fail'] += 1
                        continue

                    # 4. Medium-term filter
                    if config.get('check_mom_5d', True):
                        if mom_5d > config.get('max_mom_5d', 5):
                            filter_stats['mom_5d_fail'] += 1
                            continue

                    # 5. Uptrend filter
                    if config.get('require_uptrend', False):
                        if sma20 < sma50:
                            filter_stats['uptrend_fail'] += 1
                            continue

                elif strategy == 'breakout':
                    # Positive momentum
                    if mom_1d < config.get('min_mom_1d', 1):
                        filter_stats['mom_1d_fail'] += 1
                        continue

                    # RSI strength
                    if rsi < config.get('min_rsi', 50) or rsi > config.get('max_rsi', 75):
                        filter_stats['rsi_fail'] += 1
                        continue

                    # Volume
                    if vol_ratio < config.get('min_vol_ratio', 1.2):
                        filter_stats['vol_fail'] += 1
                        continue

                    # Near highs
                    if dist_high > config.get('max_dist_high', 5):
                        filter_stats['dist_high_fail'] += 1
                        continue

                elif strategy == 'mean_reversion':
                    # Oversold BB
                    if bb_pct > config.get('max_bb_pct', 0.3):
                        filter_stats['bb_fail'] += 1
                        continue

                    # RSI oversold
                    if rsi > config.get('max_rsi', 35):
                        filter_stats['rsi_fail'] += 1
                        continue

                filter_stats['passed'] += 1

                # Calculate SL/TP
                sl_pct = min(max(atr_pct * config.get('atr_mult', 1.0),
                                 config.get('min_sl', 1.5)),
                             config.get('max_sl', 3.0))
                tp_pct = sl_pct * config.get('rr_ratio', 2.0)

                # Simulate
                result = simulate_trade(
                    df, i, sl_pct, tp_pct,
                    config.get('max_hold', 5),
                    trailing_stop=config.get('trailing_stop', False)
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
            continue

    if debug and filter_stats:
        print(f"\n  Filter Stats:")
        for k, v in sorted(filter_stats.items()):
            print(f"    {k}: {v}")

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

    # Win/loss amounts
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0

    # Profit factor
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
    """Run diagnostic test"""
    print("\n" + "=" * 70)
    print("  DIAGNOSTIC: Testing data and filters")
    print("=" * 70)

    # Super relaxed config
    config = {
        'strategy': 'dip',
        'max_mom_1d': 100,   # Accept anything
        'max_gap': 100,
        'max_rsi': 100,
        'check_mom_5d': False,
        'require_uptrend': False,
        'min_sl': 2,
        'max_sl': 4,
        'rr_ratio': 2.0,
        'max_hold': 5,
    }

    trades = backtest(data, config, debug=True)
    result = analyze(trades)

    if result:
        print(f"\n  With NO filters:")
        print(f"    Trades: {result['total']}")
        print(f"    Win Rate: {result['win_rate']:.0f}%")
        print(f"    Monthly P&L: {result['monthly_pnl']:.1f}%")

        # Sample trades
        if len(trades) > 0:
            print(f"\n  Sample trades:")
            for _, t in trades.head(5).iterrows():
                print(f"    {t['symbol']} {t['date']}: {t['pnl']:.1f}% ({t['exit']})")

    return trades, result


def optimize(data):
    """Run full optimization"""
    print("\n" + "=" * 70)
    print("  OPTIMIZING FOR 5-15% MONTHLY PROFIT")
    print("=" * 70)

    best_config = None
    best_score = -999
    best_result = None
    best_trades = None

    iteration = 0

    # Strategy 1: DIP BUYING with various parameters
    print("\n  Testing DIP strategy...")

    for max_mom_1d in [0, 1, 2, 3, 5]:
        for max_mom_5d in [0, 3, 5, 10]:
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
                                'check_mom_5d': True,
                                'require_uptrend': False,
                                'min_sl': 1.5,
                                'max_sl': 3.0,
                                'atr_mult': 1.0,
                                'rr_ratio': rr_ratio,
                                'max_hold': max_hold,
                                'trailing_stop': trailing,
                            }

                            iteration += 1
                            trades = backtest(data, config)

                            if len(trades) < 10:
                                continue

                            result = analyze(trades)
                            if result is None:
                                continue

                            # Score: prioritize monthly profit and low losers
                            loser_ratio = result['losers'] / max(result['winners'], 1)
                            score = (
                                result['monthly_pnl'] * 3 +           # Primary goal
                                result['profit_factor'] * 5 +         # Risk/reward
                                result['win_rate'] * 0.2 -            # Win rate bonus
                                loser_ratio * 15 -                    # Penalize high losers
                                result['same_day_pct'] * 0.3          # PDT penalty
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
                            'trailing_stop': True,
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
                        'trailing_stop': False,
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

    return best_config, best_result, best_trades


def main():
    """Main function"""
    dm = DataManager()
    data = load_data(dm, UNIVERSE)

    if len(data) < 10:
        print("ERROR: Not enough data loaded!")
        return None, None, None

    # Diagnostic first
    run_diagnostic(data)

    # Run optimization
    best_config, best_result, best_trades = optimize(data)

    # Final results
    print("\n" + "=" * 70)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 70)

    if best_result:
        print(f"\nBEST CONFIG:")
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
            print(f"\n❌ Current: {best_result['monthly_pnl']:.1f}%/month - need more tuning")

        # Save config
        import json
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_v5.json', 'w') as f:
            json.dump({
                'strategy': best_config.get('strategy', 'dip'),
                'config': best_config,
                'performance': {k: float(v) if isinstance(v, (np.floating, np.integer)) else v
                               for k, v in best_result.items()}
            }, f, indent=2)

        # Show sample trades
        if best_trades is not None and len(best_trades) > 0:
            print(f"\nSample Winners:")
            winners = best_trades[best_trades['pnl'] > 0].head(5)
            for _, t in winners.iterrows():
                print(f"  {t['symbol']} {str(t['date'])[:10]}: +{t['pnl']:.1f}% ({t['days']}d)")

            print(f"\nSample Losers:")
            losers = best_trades[best_trades['pnl'] <= 0].head(5)
            for _, t in losers.iterrows():
                print(f"  {t['symbol']} {str(t['date'])[:10]}: {t['pnl']:.1f}% ({t['days']}d)")

        return best_config, best_result, best_trades

    print("\nNo profitable configuration found - need different approach")
    return None, None, None


if __name__ == '__main__':
    best_config, best_result, best_trades = main()
