#!/usr/bin/env python3
"""
Backtest v10 STRICT - Reduced Loser Version

Changes from v9:
1. Min entry score: 80 (was 55)
2. RSI max: 65 (was 80)
3. Momentum 20d cap: 25% (was unlimited)
4. Wider stop loss: -10% (was -7%) to avoid quick shakeouts
5. No repeat trades within 14 days
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# Known working stocks
WORKING_UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'QCOM',
    'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI', 'INTC', 'ON',
    'MRVL', 'SNPS', 'CDNS', 'ASML', 'TSM', 'ARM', 'SMCI',
    'PANW', 'CRWD', 'ZS', 'NET', 'DDOG', 'SNOW', 'MDB', 'PLTR', 'SHOP', 'WDAY',
    'VEEV', 'HUBS', 'TTD', 'ZM', 'DOCU', 'TEAM', 'OKTA', 'FTNT',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'USB', 'PNC', 'SCHW', 'COIN', 'AFRM', 'SOFI', 'HOOD', 'PYPL',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'GILD', 'REGN', 'VRTX', 'MRNA', 'AMGN', 'BMY', 'DXCM',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CMG', 'LULU', 'DECK', 'CROX', 'RH', 'ULTA',
    'CAT', 'DE', 'HON', 'GE', 'BA', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX',
    'WM', 'URI', 'PWR', 'EMR', 'ETN',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN',
    'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS',
    'RIVN', 'LCID', 'F', 'GM', 'APTV',
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT', 'RCL', 'CCL', 'UAL', 'DAL', 'LUV',
    'DKNG', 'MGM', 'LVS', 'WYNN',
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'DLR', 'SPG', 'O',
    'ENPH', 'SEDG', 'FSLR', 'PLUG', 'BE',
    'AXON', 'CAVA', 'DUOL', 'TOST', 'HIMS', 'IONQ', 'APP', 'RKLB',
    'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'AA',
]


def download_stock_data(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Download historical data"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None
        df.index = df.index.tz_localize(None)
        return df
    except:
        return None


def calculate_metrics(df: pd.DataFrame, idx: int) -> Dict:
    """Calculate technical metrics"""
    if idx < 25:
        return None

    close = df.iloc[idx]['Close']

    # MA20
    ma20 = df['Close'].iloc[idx-20:idx].mean()
    ma20_pct = ((close - ma20) / ma20) * 100

    # 52-week position
    lookback = min(252, idx)
    high_52w = df['High'].iloc[idx-lookback:idx].max()
    low_52w = df['Low'].iloc[idx-lookback:idx].min()
    position_52w = ((close - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # Momentum 20d
    close_20d_ago = df['Close'].iloc[idx - 20]
    momentum_20d = ((close - close_20d_ago) / close_20d_ago) * 100

    # Momentum 3d
    close_3d_ago = df['Close'].iloc[idx - 3]
    momentum_3d = ((close - close_3d_ago) / close_3d_ago) * 100

    # RSI 14
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_14 = rsi.iloc[idx] if not pd.isna(rsi.iloc[idx]) else 50

    # ATR %
    tr = pd.DataFrame({
        'hl': df['High'] - df['Low'],
        'hc': abs(df['High'] - df['Close'].shift(1)),
        'lc': abs(df['Low'] - df['Close'].shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean()
    atr_pct = (atr.iloc[idx] / close) * 100 if close > 0 else 10

    # Volume ratio
    vol_20 = df['Volume'].iloc[idx-20:idx].mean()
    vol_today = df['Volume'].iloc[idx]
    volume_ratio = vol_today / vol_20 if vol_20 > 0 else 1

    # Distance from 20d high
    high_20d = df['High'].iloc[idx-20:idx].max()
    dist_from_high = ((close - high_20d) / high_20d) * 100

    return {
        'close': close,
        'ma20_pct': ma20_pct,
        'position_52w': position_52w,
        'momentum_20d': momentum_20d,
        'momentum_3d': momentum_3d,
        'rsi_14': rsi_14,
        'atr_pct': atr_pct,
        'volume_ratio': volume_ratio,
        'dist_from_high': dist_from_high
    }


def passes_strict_gates(metrics: Dict) -> tuple:
    """v10 STRICT momentum gates - designed to reduce losers"""
    reasons = []

    # Gate 1: MA20 > -5%
    if metrics['ma20_pct'] < -5:
        reasons.append(f"MA20: {metrics['ma20_pct']:.1f}%")

    # Gate 2: 52-week position 40-85% (tighter than v9)
    if not (40 <= metrics['position_52w'] <= 85):
        reasons.append(f"52w: {metrics['position_52w']:.1f}%")

    # Gate 3: Momentum 20d 0-25% (must be positive, capped at 25%)
    if metrics['momentum_20d'] < 0:
        reasons.append(f"Mom20d neg: {metrics['momentum_20d']:.1f}%")
    if metrics['momentum_20d'] > 25:
        reasons.append(f"Mom20d too high: {metrics['momentum_20d']:.1f}%")

    # Gate 4: Momentum 3d > -3%
    if metrics['momentum_3d'] < -3:
        reasons.append(f"Mom3d: {metrics['momentum_3d']:.1f}%")

    # Gate 5: RSI 40-65 (tighter - avoid overbought)
    if not (40 <= metrics['rsi_14'] <= 65):
        reasons.append(f"RSI: {metrics['rsi_14']:.1f}")

    # Gate 6: ATR <= 3.5%
    if metrics['atr_pct'] > 3.5:
        reasons.append(f"ATR: {metrics['atr_pct']:.1f}%")

    # Gate 7: Volume >= 0.6x
    if metrics['volume_ratio'] < 0.6:
        reasons.append(f"Vol: {metrics['volume_ratio']:.2f}x")

    # Gate 8: Near 20d high (within -5%)
    if metrics['dist_from_high'] < -5:
        reasons.append(f"Dist from high: {metrics['dist_from_high']:.1f}%")

    return len(reasons) == 0, reasons


def calculate_entry_score(metrics: Dict) -> float:
    """Calculate entry score with focus on quality"""
    # Momentum component (30%) - optimal 10-15%
    if 10 <= metrics['momentum_20d'] <= 15:
        mom_score = 100
    elif 5 <= metrics['momentum_20d'] <= 20:
        mom_score = 80
    else:
        mom_score = max(0, 60 - abs(metrics['momentum_20d'] - 12.5) * 2)

    # RSI component (30%) - optimal 50-55
    rsi_score = 100 - abs(metrics['rsi_14'] - 52.5) * 2

    # Position component (20%) - optimal 60-70%
    pos_score = 100 - abs(metrics['position_52w'] - 65) * 1.5

    # Near high bonus (20%) - closer to 20d high is better
    high_score = 100 + metrics['dist_from_high'] * 10  # -5% dist = 50 score

    return mom_score * 0.30 + rsi_score * 0.30 + pos_score * 0.20 + high_score * 0.20


def simulate_trade(df: pd.DataFrame, entry_idx: int, max_hold_days: int = 30,
                   target_pct: float = 10.0, stop_loss_pct: float = 10.0) -> Dict:
    """Simulate trade with wider stop loss"""
    entry_price = df.iloc[entry_idx]['Close']
    target_price = entry_price * (1 + target_pct / 100)
    stop_price = entry_price * (1 - stop_loss_pct / 100)

    for i in range(1, min(max_hold_days + 1, len(df) - entry_idx)):
        current_idx = entry_idx + i
        if current_idx >= len(df):
            break

        high = df.iloc[current_idx]['High']
        low = df.iloc[current_idx]['Low']
        exit_date = df.index[current_idx]

        # Check stop loss
        if low <= stop_price:
            return {
                'entry_date': df.index[entry_idx],
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': stop_price,
                'return_pct': -stop_loss_pct,
                'hold_days': i,
                'exit_reason': 'STOP_LOSS'
            }

        # Check target
        if high >= target_price:
            return {
                'entry_date': df.index[entry_idx],
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': target_price,
                'return_pct': target_pct,
                'hold_days': i,
                'exit_reason': 'TARGET_HIT'
            }

    # Max hold
    final_idx = min(entry_idx + max_hold_days, len(df) - 1)
    final_close = df.iloc[final_idx]['Close']
    return_pct = ((final_close - entry_price) / entry_price) * 100

    return {
        'entry_date': df.index[entry_idx],
        'exit_date': df.index[final_idx],
        'entry_price': entry_price,
        'exit_price': final_close,
        'return_pct': return_pct,
        'hold_days': final_idx - entry_idx,
        'exit_reason': 'MAX_HOLD'
    }


def run_backtest():
    """Run strict backtest"""
    print("=" * 70)
    print("BACKTEST v10 STRICT - Reduced Loser Version")
    print("=" * 70)

    # Parameters
    start_date = '2025-10-01'
    end_date = '2026-01-25'
    max_stocks_per_day = 5
    min_entry_score = 80  # Raised from 55

    print(f"Period: {start_date} to {end_date}")
    print(f"Max stocks per screening: {max_stocks_per_day}")
    print(f"Min entry score: {min_entry_score}")
    print(f"Target: +10%, Stop Loss: -10% (wider), Max Hold: 30 days")
    print("=" * 70)

    # Download data
    print("\n📥 Downloading price data...")
    stock_data = {}
    for i, symbol in enumerate(WORKING_UNIVERSE):
        df = download_stock_data(symbol, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            stock_data[symbol] = df
        if (i + 1) % 50 == 0:
            print(f"   Downloaded {i + 1}/{len(WORKING_UNIVERSE)}...")

    print(f"✅ Got data for {len(stock_data)} stocks")

    screening_dates = pd.date_range(start=start_date, end=end_date, freq='W-MON')
    print(f"Screening dates: {len(screening_dates)} Mondays")

    all_trades = []
    recent_trades = {}  # Track recent trades to avoid repeats

    for screen_date in screening_dates:
        screen_str = screen_date.strftime('%Y-%m-%d')
        print(f"\n📅 Screening {screen_str}...")

        # Clean up old entries from recent_trades (older than 14 days)
        cutoff = screen_date - timedelta(days=14)
        recent_trades = {k: v for k, v in recent_trades.items() if v > cutoff}

        candidates = []

        for symbol, df in stock_data.items():
            # Skip if recently traded
            if symbol in recent_trades:
                continue

            try:
                if screen_date not in df.index:
                    valid_dates = df.index[df.index <= screen_date]
                    if len(valid_dates) == 0:
                        continue
                    actual_date = valid_dates[-1]
                    idx = df.index.get_loc(actual_date)
                else:
                    idx = df.index.get_loc(screen_date)

                if idx < 25:
                    continue

                metrics = calculate_metrics(df, idx)
                if metrics is None:
                    continue

                passed, reasons = passes_strict_gates(metrics)

                if passed:
                    entry_score = calculate_entry_score(metrics)
                    if entry_score >= min_entry_score:
                        candidates.append({
                            'symbol': symbol,
                            'entry_score': entry_score,
                            'idx': idx,
                            **metrics
                        })

            except Exception as e:
                continue

        print(f"   Passed gates: {len(candidates)}")

        if not candidates:
            continue

        candidates.sort(key=lambda x: x['entry_score'], reverse=True)
        selected = candidates[:max_stocks_per_day]

        selected_str = [f"{c['symbol']}({c['entry_score']:.0f})" for c in selected]
        print(f"   Selected: {selected_str}")

        for stock in selected:
            df = stock_data[stock['symbol']]
            trade = simulate_trade(df, stock['idx'])
            if trade:
                trade['symbol'] = stock['symbol']
                trade['entry_score'] = stock['entry_score']
                trade['momentum_20d'] = stock['momentum_20d']
                trade['rsi'] = stock['rsi_14']
                trade['atr_pct'] = stock['atr_pct']
                all_trades.append(trade)

                # Mark as recently traded
                recent_trades[stock['symbol']] = screen_date

    # Results
    print("\n" + "=" * 70)
    print("📊 BACKTEST v10 STRICT RESULTS")
    print("=" * 70)

    if not all_trades:
        print("No trades executed!")
        return

    df_trades = pd.DataFrame(all_trades)

    total = len(df_trades)
    winners = df_trades[df_trades['return_pct'] > 0]
    losers = df_trades[df_trades['return_pct'] <= 0]
    win_rate = len(winners) / total * 100

    print(f"\n🎯 TRADE STATISTICS:")
    print(f"   Total trades: {total}")
    print(f"   Winners: {len(winners)} ({win_rate:.1f}%)")
    print(f"   Losers: {len(losers)} ({100-win_rate:.1f}%)")

    print(f"\n💰 RETURNS:")
    print(f"   Average return: {df_trades['return_pct'].mean():.2f}%")
    if len(winners) > 0:
        print(f"   Average winner: +{winners['return_pct'].mean():.2f}%")
    if len(losers) > 0:
        print(f"   Average loser: {losers['return_pct'].mean():.2f}%")
    print(f"   Best trade: +{df_trades['return_pct'].max():.2f}%")
    print(f"   Worst trade: {df_trades['return_pct'].min():.2f}%")

    print(f"\n⏱️ HOLDING PERIOD:")
    print(f"   Average hold: {df_trades['hold_days'].mean():.1f} days")

    print(f"\n🚪 EXIT REASONS:")
    for reason in df_trades['exit_reason'].unique():
        subset = df_trades[df_trades['exit_reason'] == reason]
        pct = len(subset) / total * 100
        avg = subset['return_pct'].mean()
        print(f"   {reason}: {len(subset)} ({pct:.1f}%) avg: {avg:+.1f}%")

    print(f"\n❌ LOSER ANALYSIS:")
    if len(losers) > 0:
        big = len(losers[losers['return_pct'] <= -10])
        med = len(losers[(losers['return_pct'] > -10) & (losers['return_pct'] <= -5)])
        small = len(losers[losers['return_pct'] > -5])
        print(f"   Big (≤-10%): {big} ({big/total*100:.1f}%)")
        print(f"   Medium (-10% to -5%): {med} ({med/total*100:.1f}%)")
        print(f"   Small (>-5%): {small} ({small/total*100:.1f}%)")

    # Monthly
    print(f"\n📅 MONTHLY BREAKDOWN:")
    df_trades['month'] = pd.to_datetime(df_trades['entry_date']).dt.to_period('M')
    monthly = df_trades.groupby('month').agg({
        'return_pct': ['count', 'mean', lambda x: (x > 0).sum() / len(x) * 100]
    }).round(1)
    monthly.columns = ['Trades', 'Avg Ret%', 'WinRate%']
    print(monthly.to_string())

    # Performance
    total_return = df_trades['return_pct'].sum()
    gross_profit = winners['return_pct'].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers['return_pct'].sum()) if len(losers) > 0 else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else 0

    print(f"\n📈 PERFORMANCE:")
    print(f"   Total Return: {total_return:+.1f}%")
    print(f"   Profit Factor: {pf:.2f}")

    # Compare with v9
    print(f"\n📊 vs v9 COMPARISON:")
    print(f"   v9: 80 trades, 62.5% WR, 30% losers")
    print(f"   v10: {total} trades, {win_rate:.1f}% WR, {100-win_rate:.1f}% losers")

    df_trades.to_csv('backtest_v10_results.csv', index=False)
    print(f"\n💾 Results saved to backtest_v10_results.csv")

    return df_trades


if __name__ == "__main__":
    run_backtest()
