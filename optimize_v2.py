#!/usr/bin/env python3
"""
RAPID TRADER OPTIMIZER V2
Focus: Find the WINNING criteria from 680+ stocks
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# Config
START_DATE = datetime(2025, 10, 1)
END_DATE = datetime(2026, 1, 30)

# Large universe
UNIVERSE = [
    # Tech Giants
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'CRM',
    'ADBE', 'NFLX', 'ORCL', 'CSCO', 'IBM', 'QCOM', 'TXN', 'AVGO', 'NOW', 'INTU',
    # Growth Tech
    'SHOP', 'SNOW', 'PLTR', 'NET', 'DDOG', 'ZS', 'CRWD', 'OKTA', 'MDB', 'TWLO',
    'ROKU', 'TTD', 'PINS', 'SNAP', 'U', 'RBLX', 'COIN', 'HOOD', 'AFRM', 'UPST',
    # Semiconductors
    'MU', 'MRVL', 'KLAC', 'LRCX', 'AMAT', 'ASML', 'ADI', 'NXPI', 'ON', 'SWKS',
    # Healthcare
    'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
    'AMGN', 'GILD', 'ISRG', 'VRTX', 'REGN', 'MRNA', 'BIIB', 'ILMN', 'DXCM', 'ALGN',
    'ZBH', 'SYK', 'BSX', 'MDT', 'EW', 'HOLX', 'IDXX', 'IQV', 'A', 'BIO',
    # Consumer
    'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'COST', 'LOW', 'TJX', 'ROST',
    'CMG', 'DG', 'DLTR', 'LULU', 'ULTA', 'ETSY', 'W', 'CHWY', 'DECK', 'CROX',
    'YUM', 'DPZ', 'WING', 'CAVA', 'SHAK', 'EL', 'CPNG', 'PDD', 'BABA', 'JD',
    # Financial
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'V', 'MA', 'BLK',
    'SCHW', 'CME', 'ICE', 'SPGI', 'MCO', 'MSCI', 'FIS', 'FISV', 'GPN', 'SQ',
    # Industrial
    'CAT', 'DE', 'BA', 'HON', 'UNP', 'UPS', 'RTX', 'LMT', 'GE', 'MMM',
    'EMR', 'ROK', 'PH', 'ITW', 'ETN', 'PCAR', 'CMI', 'ODFL', 'JBHT', 'CHRW',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'VLO', 'PSX', 'OXY', 'DVN',
    'HAL', 'BKR', 'FANG', 'PXD', 'HES', 'MRO', 'APA', 'OVV', 'AR', 'RRC',
    # Clean Energy
    'ENPH', 'SEDG', 'FSLR', 'RUN', 'NOVA', 'SPWR', 'PLUG', 'BE', 'CHPT', 'LCID',
    # REITs
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'DLR', 'O', 'WELL', 'AVB', 'EQR',
    # Materials
    'LIN', 'APD', 'SHW', 'ECL', 'DD', 'NEM', 'FCX', 'SCCO', 'NUE', 'CLF',
    # Telecom/Media
    'VZ', 'T', 'TMUS', 'CMCSA', 'DIS', 'PARA', 'WBD', 'FOX', 'NWSA', 'LYV',
]


def load_all_data():
    """Load data for all stocks"""
    print(f"Loading {len(UNIVERSE)} stocks...")
    data = {}

    def fetch(symbol):
        try:
            df = yf.download(symbol, start=START_DATE - timedelta(days=60),
                           end=END_DATE + timedelta(days=5), progress=False)
            # Flatten multi-index columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if len(df) > 30:
                return symbol, df
        except:
            pass
        return symbol, None

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(fetch, s) for s in UNIVERSE]
        for f in as_completed(futures):
            sym, df = f.result()
            if df is not None:
                data[sym] = df

    print(f"Loaded {len(data)} stocks")
    return data


def add_indicators(df):
    """Add technical indicators"""
    df = df.copy()

    # Handle multi-index columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Ensure we have Series not DataFrame
    close = df['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    high = df['High']
    if isinstance(high, pd.DataFrame):
        high = high.iloc[:, 0]

    low = df['Low']
    if isinstance(low, pd.DataFrame):
        low = low.iloc[:, 0]

    volume = df['Volume']
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    open_p = df['Open']
    if isinstance(open_p, pd.DataFrame):
        open_p = open_p.iloc[:, 0]

    # Store back
    df['Close'] = close
    df['High'] = high
    df['Low'] = low
    df['Volume'] = volume
    df['Open'] = open_p

    # Momentum
    df['mom_1d'] = df['Close'].pct_change(1) * 100
    df['mom_3d'] = df['Close'].pct_change(3) * 100
    df['mom_5d'] = df['Close'].pct_change(5) * 100
    df['mom_10d'] = df['Close'].pct_change(10) * 100
    df['mom_20d'] = df['Close'].pct_change(20) * 100

    # Gap
    df['gap'] = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1) * 100

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - 100 / (1 + gain/loss)

    # ATR
    hl = df['High'] - df['Low']
    hc = abs(df['High'] - df['Close'].shift())
    lc = abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = df['atr'] / df['Close'] * 100

    # SMAs
    df['sma5'] = df['Close'].rolling(5).mean()
    df['sma10'] = df['Close'].rolling(10).mean()
    df['sma20'] = df['Close'].rolling(20).mean()
    df['sma50'] = df['Close'].rolling(50).mean()

    # Volume
    df['vol_avg'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume'] / df['vol_avg']

    # Distance from high
    df['high_20d'] = df['High'].rolling(20).max()
    df['dist_high'] = (df['high_20d'] - df['Close']) / df['high_20d'] * 100

    return df


def simulate_trade(df, entry_idx, sl_pct, tp_pct, max_days):
    """Simulate a trade and return result"""
    entry_price = df.iloc[entry_idx]['Close']
    sl_price = entry_price * (1 - sl_pct/100)
    tp_price = entry_price * (1 + tp_pct/100)

    for i in range(1, max_days + 1):
        if entry_idx + i >= len(df):
            break

        row = df.iloc[entry_idx + i]

        # Check SL
        if row['Low'] <= sl_price:
            return {
                'pnl': -sl_pct,
                'days': i,
                'exit': 'SL',
                'same_day': i == 1
            }

        # Check TP
        if row['High'] >= tp_price:
            return {
                'pnl': tp_pct,
                'days': i,
                'exit': 'TP',
                'same_day': False
            }

    # Time exit
    if entry_idx + max_days < len(df):
        exit_price = df.iloc[entry_idx + max_days]['Close']
        pnl = (exit_price - entry_price) / entry_price * 100
        return {
            'pnl': pnl,
            'days': max_days,
            'exit': 'TIME',
            'same_day': False
        }

    return None


def backtest_strategy(data, config):
    """Run backtest with given config"""
    all_trades = []

    for symbol, df in data.items():
        df = add_indicators(df)

        # Iterate through dates
        for i in range(50, len(df) - 10):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            date = df.index[i]

            if date < pd.Timestamp(START_DATE) or date > pd.Timestamp(END_DATE):
                continue

            # === ENTRY CONDITIONS ===

            # 1. True dip (down today)
            if row['mom_1d'] > config['max_mom_1d']:
                continue

            # 2. No big gap up
            if row['gap'] > config['max_gap']:
                continue

            # 3. RSI not overbought
            if row['rsi'] > config['max_rsi']:
                continue

            # 4. Some pullback
            if row['mom_5d'] > config['max_mom_5d']:
                continue

            # 5. In uptrend (sma20 > sma50)
            if config['require_uptrend'] and row['sma20'] < row['sma50']:
                continue

            # 6. Below short-term MA
            if config['require_below_sma'] and row['Close'] > row['sma5'] * 1.01:
                continue

            # 7. Volatility range
            if row['atr_pct'] < config['min_atr'] or row['atr_pct'] > config['max_atr']:
                continue

            # 8. Volume
            if row['vol_ratio'] < config['min_vol_ratio']:
                continue

            # 9. Distance from high
            if row['dist_high'] < config['min_dist_high']:
                continue

            # 10. RSI oversold bonus - STRICT filter
            if config['require_oversold'] and row['rsi'] > 45:
                continue

            # Calculate SL/TP
            sl_pct = min(max(row['atr_pct'] * config['atr_mult'], config['min_sl']), config['max_sl'])
            tp_pct = sl_pct * config['rr_ratio']

            # Simulate trade
            result = simulate_trade(df, i, sl_pct, tp_pct, config['max_hold'])

            if result:
                all_trades.append({
                    'symbol': symbol,
                    'date': date,
                    'entry': row['Close'],
                    'rsi': row['rsi'],
                    'mom_1d': row['mom_1d'],
                    'mom_5d': row['mom_5d'],
                    'gap': row['gap'],
                    'atr_pct': row['atr_pct'],
                    'dist_high': row['dist_high'],
                    **result
                })

    return pd.DataFrame(all_trades) if all_trades else pd.DataFrame()


def analyze_results(trades_df):
    """Analyze results"""
    if len(trades_df) == 0:
        return {'error': True}

    total = len(trades_df)
    winners = len(trades_df[trades_df['pnl'] > 0])
    losers = total - winners
    win_rate = winners / total * 100

    total_pnl = trades_df['pnl'].sum()
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] <= 0]['pnl'].mean() if losers > 0 else 0

    same_day_sl = len(trades_df[trades_df['same_day'] == True])

    months = (END_DATE - START_DATE).days / 30
    monthly_pnl = total_pnl / months

    return {
        'total': total,
        'winners': winners,
        'losers': losers,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'monthly_pnl': monthly_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'same_day_sl': same_day_sl,
        'same_day_pct': same_day_sl / total * 100 if total > 0 else 0,
    }


def run_optimization():
    """Main optimization loop"""

    # Load data once
    data = load_all_data()

    print("\n" + "=" * 70)
    print("  OPTIMIZING FOR 5-15% MONTHLY PROFIT")
    print("=" * 70)

    # Best so far
    best_config = None
    best_monthly = -999
    best_result = None

    iteration = 0

    # Parameter ranges
    configs_to_test = []

    # Generate configs - focus on STRICT filtering
    for max_mom_1d in [-2, -1, -0.5, 0]:
        for max_mom_5d in [-3, -1, 0, 2]:
            for max_rsi in [40, 45, 50, 55, 60]:
                for require_oversold in [True, False]:
                    for rr_ratio in [2.0, 2.5, 3.0, 3.5]:
                        for max_hold in [3, 5, 7]:
                            for min_dist_high in [3, 5, 8, 10]:
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
                                    'min_vol_ratio': 0.5,
                                    'min_dist_high': min_dist_high,
                                    'atr_mult': 1.0,
                                    'min_sl': 1.5,
                                    'max_sl': 2.5,
                                    'rr_ratio': rr_ratio,
                                    'max_hold': max_hold,
                                }
                                configs_to_test.append(config)

    print(f"Testing {len(configs_to_test)} configurations...")

    for config in configs_to_test:
        iteration += 1

        trades = backtest_strategy(data, config)
        if len(trades) < 10:  # Need minimum trades
            continue

        result = analyze_results(trades)
        if 'error' in result:
            continue

        # Target: 5%+ monthly, 50%+ win rate, <15% same-day SL
        if (result['monthly_pnl'] > best_monthly and
            result['win_rate'] >= 45 and
            result['same_day_pct'] < 20):

            best_monthly = result['monthly_pnl']
            best_config = config.copy()
            best_result = result.copy()
            best_trades = trades.copy()

            print(f"\n[{iteration}] NEW BEST!")
            print(f"  Monthly: {result['monthly_pnl']:.1f}%")
            print(f"  Win Rate: {result['win_rate']:.0f}%")
            print(f"  Trades: {result['total']}")
            print(f"  Same-day SL: {result['same_day_pct']:.0f}%")
            print(f"  Config: mom1d={config['max_mom_1d']}, rsi={config['max_rsi']}, "
                  f"oversold={config['require_oversold']}, rr={config['rr_ratio']}")

        if iteration % 500 == 0:
            print(f"  Progress: {iteration}/{len(configs_to_test)}")

    # Final results
    print("\n" + "=" * 70)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 70)

    if best_result:
        print(f"\nBEST CONFIGURATION:")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nBEST RESULTS:")
        print(f"  Total Trades: {best_result['total']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.0f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Total P&L: {best_result['total_pnl']:.1f}%")
        print(f"  Monthly P&L: {best_result['monthly_pnl']:.1f}%")
        print(f"  Avg Win: +{best_result['avg_win']:.1f}%")
        print(f"  Avg Loss: {best_result['avg_loss']:.1f}%")
        print(f"  Same-day SL: {best_result['same_day_sl']} ({best_result['same_day_pct']:.0f}%)")

        # Check if we hit target
        if best_result['monthly_pnl'] >= 5:
            print(f"\n✅ TARGET ACHIEVED: {best_result['monthly_pnl']:.1f}%/month!")
        else:
            print(f"\n⚠️ Not yet at target. Current: {best_result['monthly_pnl']:.1f}%/month")
            print("  Continuing optimization...")

        return best_config, best_result, best_trades
    else:
        print("No valid configuration found")
        return None, None, None


if __name__ == '__main__':
    best_config, best_result, best_trades = run_optimization()

    if best_result and best_result['monthly_pnl'] < 5:
        print("\n" + "=" * 70)
        print("  STARTING PHASE 2 - STRICTER FILTERS")
        print("=" * 70)

        # Phase 2: Even stricter
        # ... continue optimizing
