#!/usr/bin/env python
"""
Aggressive optimizer targeting 5%+ monthly with:
- Gap momentum strategy
- Breakout strategy
- More positions (up to 7)
- Higher R:R ratios (up to 5:1)
- Shorter hold periods (5-7 days)
"""
import sys
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.api.data_manager import DataManager
import json
import warnings
warnings.filterwarnings('ignore')

# Stock universe - focus on high-volatility stocks
STOCKS = [
    # High Beta Tech
    'TSLA', 'AMD', 'NVDA', 'SHOP', 'SNOW', 'PLTR', 'NET', 'DDOG', 'CRWD', 'MDB',
    'COIN', 'MARA', 'RIOT', 'SQ', 'ROKU', 'UPST', 'AFRM', 'SOFI', 'HOOD',
    # Semis
    'MU', 'MRVL', 'KLAC', 'LRCX', 'AMAT', 'ASML', 'ON', 'NXPI',
    # Growth Tech
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'CRM', 'NFLX',
    # Volatile Healthcare/Biotech
    'MRNA', 'ILMN', 'DXCM', 'ALGN', 'ISRG',
    # Consumer Growth
    'LULU', 'DECK', 'CROX', 'CMG', 'ULTA', 'W',
    # Clean Energy
    'ENPH', 'FSLR', 'RUN',
]


def add_indicators(df):
    """Add technical indicators"""
    c = df['Close']
    h = df['High']
    l = df['Low']
    o = df['Open']
    v = df['Volume']

    # Multiple momentum periods
    df['mom_1d'] = c.pct_change(1) * 100
    df['mom_2d'] = c.pct_change(2) * 100
    df['mom_3d'] = c.pct_change(3) * 100
    df['mom_5d'] = c.pct_change(5) * 100
    df['mom_10d'] = c.pct_change(10) * 100

    # Gap
    df['gap'] = ((o - c.shift(1)) / c.shift(1)) * 100

    # RSI
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = (df['atr'] / c) * 100

    # Volume
    df['vol_sma'] = v.rolling(20).mean()
    df['vol_ratio'] = v / df['vol_sma']

    # Moving averages
    df['sma5'] = c.rolling(5).mean()
    df['sma10'] = c.rolling(10).mean()
    df['sma20'] = c.rolling(20).mean()
    df['sma50'] = c.rolling(50).mean()

    # Bollinger Bands
    df['bb_mid'] = c.rolling(20).mean()
    df['bb_std'] = c.rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    df['bb_pct'] = (c - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

    # Distance from highs/lows
    df['high_5d'] = h.rolling(5).max()
    df['low_5d'] = l.rolling(5).min()
    df['dist_from_high'] = ((df['high_5d'] - c) / c) * 100
    df['dist_from_low'] = ((c - df['low_5d']) / df['low_5d']) * 100

    # Breakout indicator
    df['high_20d'] = h.rolling(20).max()
    df['breakout'] = c >= df['high_20d'].shift(1)

    return df


def load_data():
    """Load and prepare data"""
    dm = DataManager()
    data = {}

    for sym in STOCKS:
        try:
            df = dm.get_price_data(sym, period='6mo')
            if df is None or len(df) < 50:
                continue

            df = df.rename(columns={
                'date': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
            df = df.set_index('Date')
            df = add_indicators(df)
            data[sym] = df
        except Exception as e:
            continue

    return data


def run_backtest(data, config):
    """Run portfolio backtest with given config"""
    MAX_POSITIONS = config.get('max_positions', 5)
    MAX_NEW_TRADES = config.get('max_new_trades', 2)
    POSITION_SIZE = config.get('position_size', 0.20)

    strategy = config.get('strategy', 'gap_momentum')

    # Get all dates
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)

    # Skip warmup period
    dates = dates[60:]

    capital = 100000
    open_positions = []
    trades = []

    for date in dates:
        # Check existing positions
        for pos in open_positions[:]:
            sym = pos['symbol']
            if sym not in data or date not in data[sym].index:
                continue

            row = data[sym].loc[date]
            current_price = row['Close']
            days_held = (date - pos['entry_date']).days

            # Update highest price for trailing stop
            if current_price > pos.get('highest', pos['entry_price']):
                pos['highest'] = current_price

            # Exit conditions
            exit_reason = None
            exit_price = current_price

            # Stop loss
            if current_price <= pos['sl_price']:
                exit_reason = 'stop_loss'
                exit_price = pos['sl_price']

            # Take profit
            elif current_price >= pos['tp_price']:
                exit_reason = 'take_profit'
                exit_price = pos['tp_price']

            # Trailing stop (if enabled and in profit)
            elif config.get('trailing_stop', False):
                profit_pct = (pos['highest'] - pos['entry_price']) / pos['entry_price'] * 100
                if profit_pct > config.get('trail_activation', 3):
                    trail_pct = profit_pct * config.get('trail_pct', 0.5)
                    trail_price = pos['entry_price'] * (1 + trail_pct / 100)
                    if current_price < trail_price:
                        exit_reason = 'trailing_stop'
                        exit_price = current_price

            # Time exit
            if days_held >= config.get('max_hold', 7):
                exit_reason = 'time_exit'
                exit_price = current_price

            if exit_reason:
                pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price'] * 100
                pnl_dollar = pos['size'] * pnl_pct / 100
                capital += pos['size'] + pnl_dollar

                trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'pnl_pct': pnl_pct,
                    'exit_reason': exit_reason,
                })
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
            close = row['Close']

            # Get indicators
            gap = row['gap'] if pd.notna(row['gap']) else 0
            mom_1d = row['mom_1d'] if pd.notna(row['mom_1d']) else 0
            mom_3d = row['mom_3d'] if pd.notna(row['mom_3d']) else 0
            mom_5d = row['mom_5d'] if pd.notna(row['mom_5d']) else 0
            rsi = row['rsi'] if pd.notna(row['rsi']) else 50
            vol_ratio = row['vol_ratio'] if pd.notna(row['vol_ratio']) else 1
            atr_pct = row['atr_pct'] if pd.notna(row['atr_pct']) else 2
            bb_pct = row['bb_pct'] if pd.notna(row['bb_pct']) else 0.5
            sma20 = row['sma20'] if pd.notna(row['sma20']) else close
            sma50 = row['sma50'] if pd.notna(row['sma50']) else close
            breakout = row['breakout'] if pd.notna(row['breakout']) else False

            # Strategy filters
            if strategy == 'gap_momentum':
                # Gap up with momentum continuation
                if gap < config.get('min_gap', 1):
                    continue
                if gap > config.get('max_gap', 8):
                    continue
                if vol_ratio < config.get('min_vol_ratio', 1.5):
                    continue
                if rsi > config.get('max_rsi', 70):
                    continue
                if mom_5d < config.get('min_mom_5d', -5):
                    continue

                score = gap * vol_ratio

            elif strategy == 'breakout':
                # Breakout above 20-day high
                if not breakout:
                    continue
                if vol_ratio < config.get('min_vol_ratio', 1.3):
                    continue
                if rsi > config.get('max_rsi', 75):
                    continue
                if sma20 < sma50:  # Only in uptrend
                    continue

                score = vol_ratio * 10

            elif strategy == 'oversold_bounce':
                # Deep oversold bounce
                if rsi > config.get('max_rsi', 30):
                    continue
                if bb_pct > config.get('max_bb_pct', 0.2):
                    continue
                if mom_3d > config.get('max_mom_3d', -3):
                    continue
                if sma20 < sma50 and not config.get('allow_downtrend', False):
                    continue

                score = (100 - rsi) + (1 - bb_pct) * 50

            elif strategy == 'mean_reversion':
                # Mean reversion at BB lower
                if bb_pct > config.get('max_bb_pct', 0.25):
                    continue
                if rsi > config.get('max_rsi', 30):
                    continue
                if mom_5d < config.get('min_mom_5d', -15):
                    continue

                score = (100 - rsi) + (1 - bb_pct) * 50

            else:
                continue

            # Calculate SL/TP
            sl_pct = min(max(atr_pct * config.get('atr_mult', 1.5),
                            config.get('min_sl', 2)),
                        config.get('max_sl', 5))
            tp_pct = sl_pct * config.get('rr_ratio', 3)

            signals.append({
                'symbol': sym,
                'entry_price': close,
                'sl_pct': sl_pct,
                'tp_pct': tp_pct,
                'score': score,
            })

        # Sort and take best signals
        signals.sort(key=lambda x: x['score'], reverse=True)

        new_entries = 0
        for sig in signals:
            if len(open_positions) >= MAX_POSITIONS:
                break
            if new_entries >= MAX_NEW_TRADES:
                break

            pos_size = capital * POSITION_SIZE
            if pos_size < 1000:
                continue

            capital -= pos_size

            open_positions.append({
                'symbol': sig['symbol'],
                'entry_date': date,
                'entry_price': sig['entry_price'],
                'sl_price': sig['entry_price'] * (1 - sig['sl_pct'] / 100),
                'tp_price': sig['entry_price'] * (1 + sig['tp_pct'] / 100),
                'size': pos_size,
                'highest': sig['entry_price'],
            })
            new_entries += 1

    # Calculate results
    if not trades:
        return None

    winners = [t for t in trades if t['pnl_pct'] > 0]
    losers = [t for t in trades if t['pnl_pct'] <= 0]

    total_return = sum(t['pnl_pct'] for t in trades)

    # Calculate monthly return
    if trades:
        first_date = min(t['entry_date'] for t in trades)
        last_date = max(t['exit_date'] for t in trades)
        months = max(1, (last_date - first_date).days / 30)
        monthly_return = total_return / months
    else:
        monthly_return = 0

    return {
        'total': len(trades),
        'winners': len(winners),
        'losers': len(losers),
        'win_rate': len(winners) / len(trades) * 100 if trades else 0,
        'total_return': total_return,
        'monthly_return': monthly_return,
    }


def main():
    print("=" * 60)
    print("  AGGRESSIVE OPTIMIZER - TARGET 5%+ MONTHLY")
    print("=" * 60)

    print("\nLoading data...")
    data = load_data()
    print(f"Loaded {len(data)} stocks")

    best_result = None
    best_config = None
    best_monthly = 0
    iteration = 0

    strategies = ['gap_momentum', 'breakout', 'oversold_bounce', 'mean_reversion']

    for strategy in strategies:
        print(f"\n{'='*40}")
        print(f"Testing: {strategy.upper()}")
        print(f"{'='*40}")

        # Strategy-specific parameter ranges
        if strategy == 'gap_momentum':
            param_grid = {
                'min_gap': [0.5, 1, 2, 3],
                'max_gap': [5, 8, 12],
                'min_vol_ratio': [1.2, 1.5, 2.0],
                'max_rsi': [65, 70, 75],
                'min_mom_5d': [-10, -5, 0],
            }
        elif strategy == 'breakout':
            param_grid = {
                'min_vol_ratio': [1.2, 1.5, 2.0],
                'max_rsi': [70, 75, 80],
            }
        elif strategy == 'oversold_bounce':
            param_grid = {
                'max_rsi': [25, 30, 35],
                'max_bb_pct': [0.15, 0.2, 0.25],
                'max_mom_3d': [-5, -3, -1],
                'allow_downtrend': [True, False],
            }
        else:  # mean_reversion
            param_grid = {
                'max_bb_pct': [0.2, 0.25, 0.3],
                'max_rsi': [25, 30, 35],
                'min_mom_5d': [-15, -10, -5],
            }

        # Common parameters
        common_params = {
            'max_positions': [5, 6, 7],
            'max_new_trades': [2, 3],
            'position_size': [0.15, 0.20, 0.25],
            'atr_mult': [1.0, 1.5, 2.0],
            'min_sl': [1.5, 2.0, 2.5],
            'max_sl': [4, 5, 6],
            'rr_ratio': [2.5, 3.0, 4.0, 5.0],
            'max_hold': [5, 7, 10],
            'trailing_stop': [True, False],
            'trail_activation': [2, 3, 5],
            'trail_pct': [0.4, 0.5, 0.6],
        }

        # Merge params
        all_params = {**param_grid, **common_params}

        # Generate configs
        from itertools import product
        keys = list(all_params.keys())
        values = list(all_params.values())

        configs = []
        for combo in product(*values):
            config = dict(zip(keys, combo))
            config['strategy'] = strategy
            configs.append(config)

        print(f"Testing {len(configs)} configurations...")

        for i, config in enumerate(configs):
            iteration += 1

            try:
                result = run_backtest(data, config)
                if result is None:
                    continue

                # Need at least 30 trades for statistical significance
                if result['total'] < 30:
                    continue

                monthly = result['monthly_return']

                if monthly > best_monthly:
                    best_monthly = monthly
                    best_result = result
                    best_config = config.copy()

                    print(f"\n  [{iteration}] NEW BEST: {monthly:.2f}%")
                    print(f"    W/L: {result['winners']}/{result['losers']} ({result['win_rate']:.0f}%)")
                    print(f"    Config: pos={config['max_positions']}, rr={config['rr_ratio']}, hold={config['max_hold']}")

                    # If we hit 5%, we can continue to optimize further
                    if monthly >= 5.0:
                        print(f"\n  *** TARGET ACHIEVED: {monthly:.2f}% ***")

            except Exception as e:
                continue

            if (i + 1) % 500 == 0:
                print(f"    Progress: {i+1}/{len(configs)}...")

    # Print final results
    print("\n" + "=" * 60)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 60)

    if best_result:
        print(f"\nBest Monthly Return: {best_monthly:.2f}%")
        print(f"Win Rate: {best_result['win_rate']:.1f}%")
        print(f"Winners/Losers: {best_result['winners']}/{best_result['losers']}")
        print(f"Total Trades: {best_result['total']}")
        print(f"\nBest Configuration:")
        print(json.dumps(best_config, indent=2))

        # Save best config
        with open('data/best_aggressive_config.json', 'w') as f:
            json.dump({
                'config': best_config,
                'result': best_result,
            }, f, indent=2)
        print("\nSaved to data/best_aggressive_config.json")

        if best_monthly >= 5.0:
            print(f"\n*** SUCCESS: Achieved {best_monthly:.2f}% monthly return! ***")
        else:
            print(f"\n*** Current best: {best_monthly:.2f}% - need more optimization ***")
    else:
        print("\nNo valid configurations found.")


if __name__ == '__main__':
    main()
