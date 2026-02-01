#!/usr/bin/env python3
"""
OPTIMIZER TO 5%+ MONTHLY
Enhance Mean Reversion + Add Trailing Stop + Sector Filter
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

# Sector mapping for rotation
SECTORS = {
    'tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'AMD', 'INTC', 'CRM', 'ADBE', 'NFLX', 'ORCL', 'CSCO', 'QCOM', 'TXN', 'AVGO', 'NOW', 'INTU'],
    'growth_tech': ['SHOP', 'SNOW', 'PLTR', 'NET', 'DDOG', 'ZS', 'CRWD', 'MDB', 'TWLO'],
    'semis': ['MU', 'MRVL', 'KLAC', 'LRCX', 'AMAT', 'ASML', 'ADI', 'NXPI', 'ON'],
    'healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN', 'GILD', 'ISRG', 'VRTX', 'REGN', 'MRNA', 'ILMN', 'DXCM', 'ALGN'],
    'consumer': ['WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'COST', 'LOW', 'TJX', 'ROST', 'CMG', 'LULU', 'ULTA', 'W', 'DECK', 'CROX'],
    'finance': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'BLK'],
    'industrial': ['CAT', 'DE', 'BA', 'HON', 'UNP', 'UPS', 'RTX', 'LMT', 'GE'],
    'energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'VLO', 'OXY', 'DVN', 'ENPH', 'FSLR', 'RUN'],
}


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
            df['mom_3d'] = c.pct_change(3) * 100
            df['mom_5d'] = c.pct_change(5) * 100
            df['mom_10d'] = c.pct_change(10) * 100
            df['mom_20d'] = c.pct_change(20) * 100

            delta = c.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            df['rsi'] = 100 - 100 / (1 + gain / (loss + 0.0001))

            df['gap'] = (df['Open'] - c.shift(1)) / c.shift(1) * 100

            tr = pd.concat([df['High'] - df['Low'],
                           abs(df['High'] - c.shift()),
                           abs(df['Low'] - c.shift())], axis=1).max(axis=1)
            df['atr'] = tr.rolling(14).mean()
            df['atr_pct'] = (df['atr'] / c * 100).fillna(2)

            df['sma10'] = c.rolling(10).mean()
            df['sma20'] = c.rolling(20).mean()
            df['sma50'] = c.rolling(50).mean()
            df['vol_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()

            # Bollinger Bands
            df['bb_mid'] = c.rolling(20).mean()
            std = c.rolling(20).std()
            df['bb_lower'] = df['bb_mid'] - 2 * std
            df['bb_upper'] = df['bb_mid'] + 2 * std
            df['bb_pct'] = (c - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 0.0001)

            # Distance from 20d low (for bounce plays)
            df['low_20d'] = df['Low'].rolling(20).min()
            df['dist_from_low'] = (c - df['low_20d']) / df['low_20d'] * 100

            df = df.set_index('Date')
            data[sym] = df

        except:
            pass

    return data


def get_sector_momentum(data, date, lookback=10):
    """Calculate sector momentum for rotation"""
    sector_mom = {}
    for sector, symbols in SECTORS.items():
        moms = []
        for sym in symbols:
            if sym in data and date in data[sym].index:
                mom = data[sym].loc[date].get('mom_10d', 0)
                if pd.notna(mom):
                    moms.append(mom)
        if moms:
            sector_mom[sector] = np.mean(moms)
    return sector_mom


def run_portfolio_backtest(data, config):
    """Run realistic portfolio backtest with enhancements"""
    all_dates = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    trading_dates = sorted([d for d in all_dates if START_DATE <= d <= END_DATE])

    open_positions = []
    closed_trades = []
    capital = 100000
    current_capital = capital

    for date in trading_dates:
        # Update and close positions
        positions_to_remove = []
        for pos in open_positions:
            sym = pos['symbol']
            if sym not in data or date not in data[sym].index:
                continue

            row = data[sym].loc[date]
            entry_price = pos['entry_price']
            sl_price = pos['sl_price']
            tp_price = pos['tp_price']
            highest_since_entry = pos.get('highest', entry_price)

            # Update highest price for trailing stop
            if row['High'] > highest_since_entry:
                highest_since_entry = row['High']
                pos['highest'] = highest_since_entry

                # Trailing stop: if up > 3%, trail at 50% of profit
                if config.get('trailing_stop', False):
                    profit_pct = (highest_since_entry - entry_price) / entry_price * 100
                    if profit_pct > 3:
                        trail_pct = profit_pct * 0.5
                        new_sl = entry_price * (1 + trail_pct / 100)
                        if new_sl > sl_price:
                            pos['sl_price'] = new_sl
                            sl_price = new_sl

            # Check SL
            if row['Low'] <= sl_price:
                pnl_pct = (sl_price - entry_price) / entry_price * 100
                closed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'pnl_pct': pnl_pct,
                    'exit': 'SL' if pnl_pct < 0 else 'TRAIL'
                })
                current_capital *= (1 + pnl_pct * POSITION_SIZE / 100)
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
                current_capital *= (1 + pnl_pct * POSITION_SIZE / 100)
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
                current_capital *= (1 + pnl_pct * POSITION_SIZE / 100)
                positions_to_remove.append(pos)

        for pos in positions_to_remove:
            open_positions.remove(pos)

        # Get sector momentum for rotation
        sector_mom = get_sector_momentum(data, date) if config.get('sector_rotation', False) else {}
        hot_sectors = [s for s, m in sorted(sector_mom.items(), key=lambda x: x[1], reverse=True)[:3]] if sector_mom else list(SECTORS.keys())

        # Find new entries
        current_symbols = [p['symbol'] for p in open_positions]
        signals = []

        for sym, df in data.items():
            if sym in current_symbols:
                continue
            if date not in df.index:
                continue

            # Sector filter
            if config.get('sector_rotation', False):
                sym_sector = None
                for sector, syms in SECTORS.items():
                    if sym in syms:
                        sym_sector = sector
                        break
                if sym_sector and sym_sector not in hot_sectors:
                    continue

            row = df.loc[date]

            mom_1d = row['mom_1d'] if pd.notna(row['mom_1d']) else 0
            mom_3d = row['mom_3d'] if pd.notna(row['mom_3d']) else 0
            mom_5d = row['mom_5d'] if pd.notna(row['mom_5d']) else 0
            mom_10d = row['mom_10d'] if pd.notna(row['mom_10d']) else 0
            mom_20d = row['mom_20d'] if pd.notna(row['mom_20d']) else 0
            rsi = row['rsi'] if pd.notna(row['rsi']) else 50
            gap = row['gap'] if pd.notna(row['gap']) else 0
            atr_pct = row['atr_pct'] if pd.notna(row['atr_pct']) else 2
            sma20 = row['sma20'] if pd.notna(row['sma20']) else row['Close']
            sma50 = row['sma50'] if pd.notna(row['sma50']) else row['Close']
            vol_ratio = row['vol_ratio'] if pd.notna(row['vol_ratio']) else 1
            bb_pct = row['bb_pct'] if pd.notna(row['bb_pct']) else 0.5
            dist_from_low = row['dist_from_low'] if pd.notna(row['dist_from_low']) else 5
            close = row['Close']

            strategy = config.get('strategy', 'mean_reversion')

            if strategy == 'mean_reversion':
                # Enhanced mean reversion
                if bb_pct > config.get('max_bb_pct', 0.25):
                    continue
                if rsi > config.get('max_rsi', 30):
                    continue
                if mom_5d < config.get('min_mom_5d', -15):
                    continue
                # Bounce confirmation: slightly up from 20d low
                if config.get('bounce_confirm', False):
                    if dist_from_low < 1 or dist_from_low > 5:
                        continue

            elif strategy == 'oversold_bounce':
                # Deep oversold bounce
                if rsi > config.get('max_rsi', 25):
                    continue
                if bb_pct > config.get('max_bb_pct', 0.15):
                    continue
                if mom_3d > config.get('max_mom_3d', -2):
                    continue
                # Must be in uptrend
                if config.get('require_uptrend', True) and sma20 < sma50:
                    continue

            elif strategy == 'dip_in_uptrend':
                # Dip buying in strong uptrend
                if sma20 < sma50:
                    continue
                if mom_20d < config.get('min_mom_20d', 5):
                    continue
                if rsi > config.get('max_rsi', 40):
                    continue
                if mom_1d > config.get('max_mom_1d', 0):
                    continue

            sl_pct = min(max(atr_pct * config.get('atr_mult', 1.0), config.get('min_sl', 1.5)), config.get('max_sl', 3.0))
            tp_pct = sl_pct * config.get('rr_ratio', 3.0)

            # Score by oversold level
            score = (100 - rsi) + (1 - bb_pct) * 50

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
                'highest': sig['entry_price'],
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

    avg_win = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].mean() if winners > 0 else 0
    avg_loss = trades_df[trades_df['pnl_pct'] <= 0]['pnl_pct'].mean() if losers > 0 else 0

    return {
        'total': total,
        'winners': winners,
        'losers': losers,
        'win_rate': winners / total * 100 if total > 0 else 0,
        'total_return': total_return,
        'monthly_return': monthly_return,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'loser_ratio': losers / max(winners, 1),
    }


def main():
    print("=" * 60)
    print("  OPTIMIZER TO 5%+ MONTHLY")
    print("=" * 60)

    dm = DataManager()
    print("Loading data...")
    data = load_and_prep(dm, UNIVERSE)
    print(f"Loaded {len(data)} stocks")

    best_config = None
    best_monthly = 4.5  # Start from current best
    best_result = None
    iteration = 0

    # Enhanced Mean Reversion with more parameters
    print("\nTesting ENHANCED MEAN REVERSION...")
    for max_bb_pct in [0.15, 0.2, 0.25, 0.3]:
        for max_rsi in [20, 25, 30, 35]:
            for min_mom_5d in [-15, -12, -10, -8]:
                for rr_ratio in [2.5, 3.0, 3.5, 4.0]:
                    for max_hold in [7, 10, 14]:
                        for trailing in [True, False]:
                            for sector_rot in [True, False]:

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
                                    'trailing_stop': trailing,
                                    'sector_rotation': sector_rot,
                                }

                                iteration += 1
                                trades, final_cap = run_portfolio_backtest(data, config)
                                result = analyze(trades, final_cap)

                                if result and result['total'] >= 15 and result['monthly_return'] > best_monthly:
                                    best_monthly = result['monthly_return']
                                    best_config = config.copy()
                                    best_result = result.copy()

                                    print(f"\n  [{iteration}] NEW BEST: {result['monthly_return']:.2f}%")
                                    print(f"    W/L: {result['winners']}/{result['losers']} ({result['win_rate']:.0f}%)")
                                    print(f"    Trailing: {trailing}, Sector: {sector_rot}")

                                if iteration % 500 == 0:
                                    print(f"    Progress: {iteration}...")

    # Oversold Bounce Strategy
    print("\nTesting OVERSOLD BOUNCE...")
    for max_rsi in [20, 25, 30]:
        for max_bb_pct in [0.1, 0.15, 0.2]:
            for max_mom_3d in [-3, -2, -1, 0]:
                for rr_ratio in [2.5, 3.0, 3.5]:
                    for max_hold in [5, 7, 10]:
                        for require_uptrend in [True, False]:

                            config = {
                                'strategy': 'oversold_bounce',
                                'max_rsi': max_rsi,
                                'max_bb_pct': max_bb_pct,
                                'max_mom_3d': max_mom_3d,
                                'require_uptrend': require_uptrend,
                                'min_sl': 2.0,
                                'max_sl': 3.0,
                                'atr_mult': 1.0,
                                'rr_ratio': rr_ratio,
                                'max_hold': max_hold,
                                'trailing_stop': True,
                                'sector_rotation': False,
                            }

                            iteration += 1
                            trades, final_cap = run_portfolio_backtest(data, config)
                            result = analyze(trades, final_cap)

                            if result and result['total'] >= 15 and result['monthly_return'] > best_monthly:
                                best_monthly = result['monthly_return']
                                best_config = config.copy()
                                best_result = result.copy()

                                print(f"\n  [{iteration}] NEW BEST: {result['monthly_return']:.2f}%")
                                print(f"    W/L: {result['winners']}/{result['losers']} ({result['win_rate']:.0f}%)")

                            if iteration % 300 == 0:
                                print(f"    Progress: {iteration}...")

    # Dip in Uptrend
    print("\nTesting DIP IN UPTREND...")
    for min_mom_20d in [3, 5, 8, 10]:
        for max_rsi in [35, 40, 45]:
            for max_mom_1d in [-2, -1, 0]:
                for rr_ratio in [2.0, 2.5, 3.0]:
                    for max_hold in [5, 7, 10]:

                        config = {
                            'strategy': 'dip_in_uptrend',
                            'min_mom_20d': min_mom_20d,
                            'max_rsi': max_rsi,
                            'max_mom_1d': max_mom_1d,
                            'min_sl': 1.5,
                            'max_sl': 2.5,
                            'atr_mult': 1.0,
                            'rr_ratio': rr_ratio,
                            'max_hold': max_hold,
                            'trailing_stop': True,
                            'sector_rotation': False,
                        }

                        iteration += 1
                        trades, final_cap = run_portfolio_backtest(data, config)
                        result = analyze(trades, final_cap)

                        if result and result['total'] >= 15 and result['monthly_return'] > best_monthly:
                            best_monthly = result['monthly_return']
                            best_config = config.copy()
                            best_result = result.copy()

                            print(f"\n  [{iteration}] NEW BEST: {result['monthly_return']:.2f}%")
                            print(f"    W/L: {result['winners']}/{result['losers']} ({result['win_rate']:.0f}%)")

                        if iteration % 200 == 0:
                            print(f"    Progress: {iteration}...")

    # Final results
    print("\n" + "=" * 60)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 60)
    print(f"  Tested: {iteration} configurations")

    if best_result and best_monthly >= 5.0:
        print(f"\n✅ TARGET ACHIEVED!")
        print(f"\nBEST CONFIG ({best_config.get('strategy', 'unknown')}):")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nPERFORMANCE:")
        print(f"  Trades: {best_result['total']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.0f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Monthly Return: {best_result['monthly_return']:.2f}%")
        print(f"  Total Return: {best_result['total_return']:.1f}%")
        print(f"  Avg Win: +{best_result['avg_win']:.1f}%")
        print(f"  Avg Loss: {best_result['avg_loss']:.1f}%")

        # Save
        import json
        import os
        os.makedirs('data', exist_ok=True)
        with open('data/best_config_5pct.json', 'w') as f:
            json.dump({
                'config': best_config,
                'result': {k: float(v) for k, v in best_result.items()}
            }, f, indent=2)

    elif best_result:
        print(f"\n⚠️ Best found: {best_monthly:.2f}% (still working...)")
        print(f"  Strategy: {best_config.get('strategy')}")
        print(f"  W/L: {best_result['winners']}/{best_result['losers']}")

    return best_config, best_result


if __name__ == '__main__':
    main()
