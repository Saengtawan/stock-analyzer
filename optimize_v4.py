#!/usr/bin/env python3
"""
RAPID TRADER OPTIMIZER V4
More aggressive parameter search with diagnostic logging
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

# Use existing data manager
from api.data_manager import DataManager

# Config
START_DATE = datetime(2025, 10, 1)
END_DATE = datetime(2026, 1, 30)

# Larger Universe - 100+ stocks across sectors
UNIVERSE = [
    # Tech Giants
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'CRM',
    'ADBE', 'NFLX', 'ORCL', 'CSCO', 'QCOM', 'TXN', 'AVGO', 'NOW', 'INTU',
    # Growth Tech
    'SHOP', 'SNOW', 'PLTR', 'NET', 'DDOG', 'ZS', 'CRWD', 'MDB', 'TWLO',
    # Semiconductors
    'MU', 'MRVL', 'KLAC', 'LRCX', 'AMAT', 'ASML', 'ADI', 'NXPI', 'ON',
    # Healthcare
    'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
    'AMGN', 'GILD', 'ISRG', 'VRTX', 'REGN', 'MRNA', 'ILMN', 'DXCM', 'ALGN',
    # Consumer
    'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'COST', 'LOW', 'TJX', 'ROST',
    'CMG', 'LULU', 'ULTA', 'W', 'DECK', 'CROX',
    # Finance
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'BLK',
    # Industrial
    'CAT', 'DE', 'BA', 'HON', 'UNP', 'UPS', 'RTX', 'LMT', 'GE',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'VLO', 'OXY', 'DVN',
    # Clean Energy
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

    # Distance from high
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
    """Simulate a trade with optional trailing stop"""
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

            # Update trailing stop if enabled
            if trailing_stop and high > highest_price:
                highest_price = high
                # Trail at 50% of profit
                trail_pct = (highest_price - entry_price) / entry_price * 100 * 0.5
                if trail_pct > 0:
                    new_sl = entry_price * (1 + trail_pct/100 - sl_pct/100)
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
    """Run backtest with optional debug output"""
    all_trades = []
    filter_stats = defaultdict(int)

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

                filter_stats['total_days'] += 1

                # Get values
                mom_1d = float(row['mom_1d']) if not pd.isna(row['mom_1d']) else 0
                mom_5d = float(row['mom_5d']) if not pd.isna(row['mom_5d']) else 0
                mom_10d = float(row['mom_10d']) if not pd.isna(row['mom_10d']) else 0
                rsi = float(row['rsi']) if not pd.isna(row['rsi']) else 50
                gap = float(row['gap']) if not pd.isna(row['gap']) else 0
                atr_pct = float(row['atr_pct']) if not pd.isna(row['atr_pct']) else 2
                dist_high = float(row['dist_high']) if not pd.isna(row['dist_high']) else 5
                close = float(row['Close'])
                sma5 = float(row['sma5']) if not pd.isna(row['sma5']) else close
                sma10 = float(row['sma10']) if not pd.isna(row['sma10']) else close
                sma20 = float(row['sma20']) if not pd.isna(row['sma20']) else close
                sma50 = float(row['sma50']) if not pd.isna(row['sma50']) else close
                vol_ratio = float(row['vol_ratio']) if not pd.isna(row['vol_ratio']) else 1
                bb_pct = float(row['bb_pct']) if not pd.isna(row['bb_pct']) else 0.5

                # === ENTRY CONDITIONS ===

                # Strategy selector
                strategy = config.get('strategy', 'dip')

                if strategy == 'dip':
                    # DIP BUYING: Buy weakness in uptrend

                    # 1. Recent dip (configurable)
                    if mom_1d > config['max_mom_1d']:
                        filter_stats['mom_1d_fail'] += 1
                        continue

                    # 2. No excessive gap up
                    if gap > config['max_gap']:
                        filter_stats['gap_fail'] += 1
                        continue

                    # 3. RSI filter
                    if rsi > config['max_rsi'] or rsi < config.get('min_rsi', 0):
                        filter_stats['rsi_fail'] += 1
                        continue

                    # 4. Medium-term pullback
                    if config.get('check_mom_5d', True) and mom_5d > config['max_mom_5d']:
                        filter_stats['mom_5d_fail'] += 1
                        continue

                    # 5. Uptrend check
                    if config.get('require_uptrend', False) and sma20 < sma50:
                        filter_stats['uptrend_fail'] += 1
                        continue

                    # 6. Below short MA
                    if config.get('require_below_sma', False) and close > sma5 * 1.02:
                        filter_stats['sma_fail'] += 1
                        continue

                    # 7. Volatility range
                    if atr_pct < config.get('min_atr', 0) or atr_pct > config.get('max_atr', 20):
                        filter_stats['atr_fail'] += 1
                        continue

                elif strategy == 'breakout':
                    # BREAKOUT: Buy strength with momentum

                    # 1. Positive momentum
                    if mom_1d < config.get('min_mom_1d', 0):
                        filter_stats['mom_1d_fail'] += 1
                        continue

                    # 2. RSI showing strength but not overbought
                    if rsi < config.get('min_rsi', 40) or rsi > config.get('max_rsi', 70):
                        filter_stats['rsi_fail'] += 1
                        continue

                    # 3. Volume confirmation
                    if vol_ratio < config.get('min_vol_ratio', 1.0):
                        filter_stats['vol_fail'] += 1
                        continue

                    # 4. Above SMA
                    if close < sma20:
                        filter_stats['sma_fail'] += 1
                        continue

                    # 5. Near high
                    if dist_high > config.get('max_dist_high', 5):
                        filter_stats['dist_high_fail'] += 1
                        continue

                elif strategy == 'mean_reversion':
                    # MEAN REVERSION: Buy oversold, sell at mean

                    # 1. Oversold BB
                    if bb_pct > config.get('max_bb_pct', 0.3):
                        filter_stats['bb_fail'] += 1
                        continue

                    # 2. RSI oversold
                    if rsi > config.get('max_rsi', 35):
                        filter_stats['rsi_fail'] += 1
                        continue

                    # 3. Not in free fall
                    if mom_5d < config.get('min_mom_5d', -15):
                        filter_stats['mom_5d_fail'] += 1
                        continue

                filter_stats['passed'] += 1

                # Calculate SL/TP
                sl_pct = min(max(atr_pct * config.get('atr_mult', 1.0), config.get('min_sl', 1.5)), config.get('max_sl', 3.0))
                tp_pct = sl_pct * config['rr_ratio']

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
                        'atr_pct': atr_pct,
                        'sl_pct': sl_pct,
                        'tp_pct': tp_pct,
                        **result
                    })

        except Exception as e:
            continue

    if debug:
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

    # By exit type
    tp_exits = len(trades_df[trades_df['exit'] == 'TP'])
    sl_exits = len(trades_df[trades_df['exit'] == 'SL'])
    time_exits = len(trades_df[trades_df['exit'] == 'TIME'])

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
        'tp_exits': tp_exits,
        'sl_exits': sl_exits,
        'time_exits': time_exits,
    }


def run_diagnostic(data):
    """Run diagnostic to understand why no trades"""
    print("\n" + "=" * 70)
    print("  DIAGNOSTIC: Testing relaxed filters")
    print("=" * 70)

    # Super relaxed config
    relaxed_config = {
        'strategy': 'dip',
        'max_mom_1d': 5,      # Allow up to +5% day
        'max_mom_5d': 10,     # Allow up to +10% week
        'max_gap': 5,         # Allow up to 5% gap
        'max_rsi': 80,        # Almost any RSI
        'min_rsi': 20,
        'check_mom_5d': False,
        'require_uptrend': False,
        'require_below_sma': False,
        'min_atr': 0,
        'max_atr': 20,
        'atr_mult': 1.0,
        'min_sl': 2,
        'max_sl': 4,
        'rr_ratio': 2.0,
        'max_hold': 5,
    }

    trades = backtest(data, relaxed_config, debug=True)
    result = analyze(trades)

    if result:
        print(f"\n  With RELAXED filters:")
        print(f"    Trades: {result['total']}")
        print(f"    Win Rate: {result['win_rate']:.0f}%")
        print(f"    Monthly P&L: {result['monthly_pnl']:.1f}%")
    else:
        print("\n  ERROR: Still no trades with relaxed filters!")

    return trades, result


def optimize_dip_strategy(data):
    """Optimize dip buying strategy"""
    print("\n" + "=" * 70)
    print("  OPTIMIZING DIP BUYING STRATEGY")
    print("=" * 70)

    best_config = None
    best_score = -999
    best_result = None
    best_trades = None

    iteration = 0

    # More granular parameter grid
    for max_mom_1d in [0, 1, 2, 3]:  # Allow slight up days
        for max_mom_5d in [0, 3, 5, 8]:  # Wider range
            for max_rsi in [40, 50, 60, 70]:  # Various RSI levels
                for rr_ratio in [1.5, 2.0, 2.5, 3.0]:
                    for max_hold in [3, 5, 7, 10]:
                        for require_uptrend in [True, False]:
                            for trailing in [True, False]:

                                config = {
                                    'strategy': 'dip',
                                    'max_mom_1d': max_mom_1d,
                                    'max_mom_5d': max_mom_5d,
                                    'max_gap': 2,
                                    'max_rsi': max_rsi,
                                    'min_rsi': 15,
                                    'check_mom_5d': True,
                                    'require_uptrend': require_uptrend,
                                    'require_below_sma': False,
                                    'min_atr': 1,
                                    'max_atr': 10,
                                    'atr_mult': 1.0,
                                    'min_sl': 1.5,
                                    'max_sl': 3.0,
                                    'rr_ratio': rr_ratio,
                                    'max_hold': max_hold,
                                    'trailing_stop': trailing,
                                }

                                iteration += 1
                                trades = backtest(data, config)

                                if len(trades) < 10:  # Need minimum trades
                                    continue

                                result = analyze(trades)
                                if result is None:
                                    continue

                                # Score function: prioritize monthly profit AND win rate
                                # Penalize high same-day SL (PDT risk)
                                score = (
                                    result['monthly_pnl'] * 2 +           # Weight monthly profit
                                    result['win_rate'] * 0.3 +            # Want >40% win rate
                                    result['profit_factor'] * 5 -         # Good risk/reward
                                    result['same_day_pct'] * 0.5 -        # Penalize PDT risk
                                    (result['losers'] / max(result['winners'], 1)) * 10  # Low loser ratio
                                )

                                # Must meet minimum criteria
                                if (result['win_rate'] >= 35 and
                                    result['monthly_pnl'] > 0 and
                                    score > best_score):

                                    best_score = score
                                    best_config = config.copy()
                                    best_result = result.copy()
                                    best_trades = trades.copy()

                                    print(f"\n  [{iteration}] NEW BEST (score={score:.1f}):")
                                    print(f"    Monthly: {result['monthly_pnl']:.1f}%")
                                    print(f"    Win Rate: {result['win_rate']:.0f}%")
                                    print(f"    Trades: {result['total']} (W:{result['winners']} L:{result['losers']})")
                                    print(f"    Profit Factor: {result['profit_factor']:.2f}")
                                    print(f"    Same-day SL: {result['same_day_pct']:.0f}%")

                                if iteration % 500 == 0:
                                    print(f"    Progress: {iteration} configs tested...")

    return best_config, best_result, best_trades


def optimize_breakout_strategy(data):
    """Optimize breakout strategy"""
    print("\n" + "=" * 70)
    print("  OPTIMIZING BREAKOUT STRATEGY")
    print("=" * 70)

    best_config = None
    best_score = -999
    best_result = None
    best_trades = None

    iteration = 0

    for min_mom_1d in [0.5, 1, 2, 3]:
        for min_rsi in [40, 50, 55]:
            for max_rsi in [65, 70, 75]:
                for min_vol_ratio in [1.0, 1.2, 1.5]:
                    for max_dist_high in [3, 5, 8]:
                        for rr_ratio in [1.5, 2.0, 2.5]:
                            for max_hold in [3, 5, 7]:

                                config = {
                                    'strategy': 'breakout',
                                    'min_mom_1d': min_mom_1d,
                                    'min_rsi': min_rsi,
                                    'max_rsi': max_rsi,
                                    'min_vol_ratio': min_vol_ratio,
                                    'max_dist_high': max_dist_high,
                                    'min_atr': 1,
                                    'max_atr': 10,
                                    'atr_mult': 1.2,
                                    'min_sl': 1.5,
                                    'max_sl': 3.0,
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

                                score = (
                                    result['monthly_pnl'] * 2 +
                                    result['win_rate'] * 0.3 +
                                    result['profit_factor'] * 5 -
                                    result['same_day_pct'] * 0.5 -
                                    (result['losers'] / max(result['winners'], 1)) * 10
                                )

                                if (result['win_rate'] >= 35 and
                                    result['monthly_pnl'] > 0 and
                                    score > best_score):

                                    best_score = score
                                    best_config = config.copy()
                                    best_result = result.copy()
                                    best_trades = trades.copy()

                                    print(f"\n  [{iteration}] NEW BEST (score={score:.1f}):")
                                    print(f"    Monthly: {result['monthly_pnl']:.1f}%")
                                    print(f"    Win Rate: {result['win_rate']:.0f}%")
                                    print(f"    Trades: {result['total']} (W:{result['winners']} L:{result['losers']})")

                                if iteration % 300 == 0:
                                    print(f"    Progress: {iteration} configs tested...")

    return best_config, best_result, best_trades


def optimize_mean_reversion(data):
    """Optimize mean reversion strategy"""
    print("\n" + "=" * 70)
    print("  OPTIMIZING MEAN REVERSION STRATEGY")
    print("=" * 70)

    best_config = None
    best_score = -999
    best_result = None
    best_trades = None

    iteration = 0

    for max_bb_pct in [0.1, 0.2, 0.3, 0.4]:
        for max_rsi in [25, 30, 35, 40]:
            for min_mom_5d in [-20, -15, -10, -8]:
                for rr_ratio in [1.5, 2.0, 2.5]:
                    for max_hold in [3, 5, 7]:

                        config = {
                            'strategy': 'mean_reversion',
                            'max_bb_pct': max_bb_pct,
                            'max_rsi': max_rsi,
                            'min_mom_5d': min_mom_5d,
                            'min_atr': 1,
                            'max_atr': 10,
                            'atr_mult': 1.0,
                            'min_sl': 2.0,
                            'max_sl': 4.0,
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

                        score = (
                            result['monthly_pnl'] * 2 +
                            result['win_rate'] * 0.3 +
                            result['profit_factor'] * 5 -
                            result['same_day_pct'] * 0.5 -
                            (result['losers'] / max(result['winners'], 1)) * 10
                        )

                        if (result['win_rate'] >= 35 and
                            result['monthly_pnl'] > 0 and
                            score > best_score):

                            best_score = score
                            best_config = config.copy()
                            best_result = result.copy()
                            best_trades = trades.copy()

                            print(f"\n  [{iteration}] NEW BEST (score={score:.1f}):")
                            print(f"    Monthly: {result['monthly_pnl']:.1f}%")
                            print(f"    Win Rate: {result['win_rate']:.0f}%")
                            print(f"    Trades: {result['total']} (W:{result['winners']} L:{result['losers']})")

                        if iteration % 200 == 0:
                            print(f"    Progress: {iteration} configs tested...")

    return best_config, best_result, best_trades


def main():
    """Main optimization"""
    dm = DataManager()
    data = load_data(dm, UNIVERSE)

    if len(data) < 50:
        print("ERROR: Not enough data loaded!")
        return

    # First, run diagnostic
    run_diagnostic(data)

    # Run all strategy optimizations
    results = []

    # 1. Dip buying
    dip_config, dip_result, dip_trades = optimize_dip_strategy(data)
    if dip_result:
        results.append(('DIP', dip_config, dip_result, dip_trades))

    # 2. Breakout
    brk_config, brk_result, brk_trades = optimize_breakout_strategy(data)
    if brk_result:
        results.append(('BREAKOUT', brk_config, brk_result, brk_trades))

    # 3. Mean reversion
    mr_config, mr_result, mr_trades = optimize_mean_reversion(data)
    if mr_result:
        results.append(('MEAN_REVERSION', mr_config, mr_result, mr_trades))

    # Find best overall
    print("\n" + "=" * 70)
    print("  FINAL RESULTS - ALL STRATEGIES")
    print("=" * 70)

    if not results:
        print("\nNo profitable strategy found!")
        return None, None, None

    best_strategy = None
    best_monthly = -999

    for name, config, result, trades in results:
        print(f"\n{name}:")
        print(f"  Monthly P&L: {result['monthly_pnl']:.1f}%")
        print(f"  Win Rate: {result['win_rate']:.0f}%")
        print(f"  Trades: {result['total']} (W:{result['winners']} L:{result['losers']})")
        print(f"  Profit Factor: {result['profit_factor']:.2f}")
        print(f"  Same-day SL: {result['same_day_pct']:.0f}%")

        if result['monthly_pnl'] > best_monthly:
            best_monthly = result['monthly_pnl']
            best_strategy = (name, config, result, trades)

    if best_strategy:
        name, config, result, trades = best_strategy

        print("\n" + "=" * 70)
        print(f"  BEST STRATEGY: {name}")
        print("=" * 70)

        print(f"\nBEST CONFIG:")
        for k, v in config.items():
            print(f"  {k}: {v}")

        print(f"\nPERFORMANCE:")
        print(f"  Trades: {result['total']}")
        print(f"  Winners: {result['winners']} ({result['win_rate']:.0f}%)")
        print(f"  Losers: {result['losers']}")
        print(f"  Total P&L: {result['total_pnl']:.1f}%")
        print(f"  Monthly P&L: {result['monthly_pnl']:.1f}%")
        print(f"  Profit Factor: {result['profit_factor']:.2f}")
        print(f"  Same-day SL: {result['same_day_pct']:.0f}%")

        if result['monthly_pnl'] >= 5:
            print(f"\n✅ TARGET ACHIEVED: {result['monthly_pnl']:.1f}%/month!")
        elif result['monthly_pnl'] >= 3:
            print(f"\n⚠️ CLOSE: {result['monthly_pnl']:.1f}%/month - continuing optimization...")
        else:
            print(f"\n❌ Current: {result['monthly_pnl']:.1f}%/month - need more work")

        # Save best config
        import json
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_v4.json', 'w') as f:
            json.dump({
                'strategy': name,
                'config': config,
                'result': {k: float(v) if isinstance(v, (np.floating, np.integer)) else v
                          for k, v in result.items()}
            }, f, indent=2)

        # Show sample trades
        if len(trades) > 0:
            print(f"\nSample Winning Trades:")
            winners = trades[trades['pnl'] > 0].head(5)
            for _, t in winners.iterrows():
                print(f"  {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: +{t['pnl']:.1f}% ({t['days']}d, {t['exit']})")

            print(f"\nSample Losing Trades:")
            losers = trades[trades['pnl'] <= 0].head(5)
            for _, t in losers.iterrows():
                print(f"  {t['symbol']} {t['date'].strftime('%Y-%m-%d')}: {t['pnl']:.1f}% ({t['days']}d, {t['exit']})")

        return config, result, trades

    return None, None, None


if __name__ == '__main__':
    best_config, best_result, best_trades = main()
