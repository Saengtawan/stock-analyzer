#!/usr/bin/env python3
"""
Backtest Latest Implementation (v9) - Fixed Version
Uses cached price data and better error handling
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# Known working stocks (verified tradeable)
WORKING_UNIVERSE = [
    # Tech Mega Caps
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'QCOM',
    # Semiconductors
    'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI', 'INTC', 'ON',
    'MRVL', 'SNPS', 'CDNS', 'ASML', 'TSM', 'ARM', 'SMCI',
    # Software/Cloud
    'PANW', 'CRWD', 'ZS', 'NET', 'DDOG', 'SNOW', 'MDB', 'PLTR', 'SHOP', 'WDAY',
    'VEEV', 'HUBS', 'TTD', 'ZM', 'DOCU', 'TEAM', 'OKTA', 'FTNT',
    # Financial
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'USB', 'PNC', 'SCHW', 'COIN', 'AFRM', 'SOFI', 'HOOD', 'PYPL',
    # Healthcare
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'GILD', 'REGN', 'VRTX', 'MRNA', 'AMGN', 'BMY', 'DXCM',
    # Consumer
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CMG', 'LULU', 'DECK', 'CROX', 'RH', 'ULTA',
    # Industrial
    'CAT', 'DE', 'HON', 'GE', 'BA', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX',
    'WM', 'URI', 'PWR', 'EMR', 'ETN',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN',
    # Communication
    'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS',
    # EV/Auto
    'RIVN', 'LCID', 'F', 'GM', 'APTV',
    # Travel/Leisure
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT', 'RCL', 'CCL', 'UAL', 'DAL', 'LUV',
    'DKNG', 'MGM', 'LVS', 'WYNN',
    # REITs
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'DLR', 'SPG', 'O',
    # Clean Energy
    'ENPH', 'SEDG', 'FSLR', 'PLUG', 'BE',
    # Hot Growth
    'AXON', 'CAVA', 'DUOL', 'TOST', 'HIMS', 'IONQ', 'APP', 'RKLB',
    # Materials
    'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'AA',
]


def download_stock_data(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Download historical data using yfinance directly"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None
        # Remove timezone to make comparison easier
        df.index = df.index.tz_localize(None)
        return df
    except Exception as e:
        return None


def calculate_metrics(df: pd.DataFrame, idx: int) -> Dict:
    """Calculate all technical metrics for a given index"""
    if idx < 20:
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
    if idx >= 3:
        close_3d_ago = df['Close'].iloc[idx - 3]
        momentum_3d = ((close - close_3d_ago) / close_3d_ago) * 100
    else:
        momentum_3d = 0

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

    return {
        'close': close,
        'ma20_pct': ma20_pct,
        'position_52w': position_52w,
        'momentum_20d': momentum_20d,
        'momentum_3d': momentum_3d,
        'rsi_14': rsi_14,
        'atr_pct': atr_pct,
        'volume_ratio': volume_ratio
    }


def passes_momentum_gates(metrics: Dict) -> tuple:
    """Check if stock passes v6.5 RELAXED momentum gates for volatile market"""
    reasons = []

    # Gate 1: Price > MA20 (within -5%) - relaxed from -3%
    if metrics['ma20_pct'] < -5:
        reasons.append(f"MA20: {metrics['ma20_pct']:.1f}%")

    # Gate 2: 52-week position 30-95% - relaxed from 50-90%
    if not (30 <= metrics['position_52w'] <= 95):
        reasons.append(f"52w: {metrics['position_52w']:.1f}%")

    # Gate 3: Momentum 20d > -10% - relaxed from -5%
    if metrics['momentum_20d'] < -10:
        reasons.append(f"Mom20d: {metrics['momentum_20d']:.1f}%")

    # Gate 4: Momentum 3d > -5% - relaxed from -3%
    if metrics['momentum_3d'] < -5:
        reasons.append(f"Mom3d: {metrics['momentum_3d']:.1f}%")

    # Gate 5: RSI 35-80 - relaxed from 40-75
    if not (35 <= metrics['rsi_14'] <= 80):
        reasons.append(f"RSI: {metrics['rsi_14']:.1f}")

    # Gate 6: ATR <= 4% - relaxed from 3%
    if metrics['atr_pct'] > 4:
        reasons.append(f"ATR: {metrics['atr_pct']:.1f}%")

    # Gate 7: Volume ratio >= 0.5 - relaxed from 0.7
    if metrics['volume_ratio'] < 0.5:
        reasons.append(f"Vol: {metrics['volume_ratio']:.2f}x")

    return len(reasons) == 0, reasons


def calculate_entry_score(metrics: Dict) -> float:
    """Calculate entry score (0-100)"""
    # Momentum component (40%)
    mom_score = min(100, max(0, 50 + metrics['momentum_20d'] * 2))

    # RSI component (30%) - optimal around 55
    rsi_score = 100 - abs(metrics['rsi_14'] - 55) * 2

    # Position component (30%) - optimal around 70%
    pos_score = 100 - abs(metrics['position_52w'] - 70) * 2

    return mom_score * 0.4 + rsi_score * 0.3 + pos_score * 0.3


def simulate_trade(df: pd.DataFrame, entry_idx: int, max_hold_days: int = 30,
                   target_pct: float = 10.0, stop_loss_pct: float = 7.0) -> Dict:
    """Simulate a single trade"""
    entry_price = df.iloc[entry_idx]['Close']
    target_price = entry_price * (1 + target_pct / 100)
    stop_price = entry_price * (1 - stop_loss_pct / 100)

    for i in range(1, min(max_hold_days + 1, len(df) - entry_idx)):
        current_idx = entry_idx + i
        if current_idx >= len(df):
            break

        high = df.iloc[current_idx]['High']
        low = df.iloc[current_idx]['Low']
        close = df.iloc[current_idx]['Close']
        exit_date = df.index[current_idx]

        # Check stop loss first
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

        # Check target hit
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

    # Max hold period
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
    """Run comprehensive backtest"""
    print("=" * 70)
    print("BACKTEST: Latest Implementation v9 (Fixed)")
    print("=" * 70)

    # Parameters
    start_date = '2025-10-01'
    end_date = '2026-01-25'
    max_stocks_per_day = 5

    print(f"Period: {start_date} to {end_date}")
    print(f"Max stocks per screening: {max_stocks_per_day}")
    print(f"Target: +10%, Stop Loss: -7%, Max Hold: 30 days")
    print(f"Universe: {len(WORKING_UNIVERSE)} verified stocks")
    print("=" * 70)

    # Download all data first
    print("\n📥 Downloading price data...")
    stock_data = {}
    failed = []

    for i, symbol in enumerate(WORKING_UNIVERSE):
        df = download_stock_data(symbol, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            stock_data[symbol] = df
        else:
            failed.append(symbol)
        if (i + 1) % 50 == 0:
            print(f"   Downloaded {i + 1}/{len(WORKING_UNIVERSE)}...")

    print(f"✅ Got data for {len(stock_data)} stocks, {len(failed)} failed")

    # Generate screening dates (every Monday)
    screening_dates = pd.date_range(start=start_date, end=end_date, freq='W-MON')
    print(f"Screening dates: {len(screening_dates)} Mondays")

    # Track all trades
    all_trades = []

    # Run screening for each date
    for screen_date in screening_dates:
        screen_str = screen_date.strftime('%Y-%m-%d')
        print(f"\n📅 Screening {screen_str}...")

        candidates = []

        for symbol, df in stock_data.items():
            try:
                # Find the date in data
                if screen_date not in df.index:
                    # Find nearest previous trading day
                    valid_dates = df.index[df.index <= screen_date]
                    if len(valid_dates) == 0:
                        continue
                    actual_date = valid_dates[-1]
                    idx = df.index.get_loc(actual_date)
                else:
                    idx = df.index.get_loc(screen_date)

                if idx < 25:
                    continue

                # Calculate metrics
                metrics = calculate_metrics(df, idx)
                if metrics is None:
                    continue

                # Check momentum gates
                passed, reasons = passes_momentum_gates(metrics)

                if passed:
                    entry_score = calculate_entry_score(metrics)
                    if entry_score >= 55:  # Min entry score
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

        # Sort by entry score and take top N
        candidates.sort(key=lambda x: x['entry_score'], reverse=True)
        selected = candidates[:max_stocks_per_day]

        selected_str = [f"{c['symbol']}({c['entry_score']:.0f})" for c in selected]
        print(f"   Selected: {selected_str}")

        # Simulate trades
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

    # Analyze results
    print("\n" + "=" * 70)
    print("📊 BACKTEST RESULTS")
    print("=" * 70)

    if not all_trades:
        print("No trades executed!")
        return

    df_trades = pd.DataFrame(all_trades)

    # Basic stats
    total_trades = len(df_trades)
    winners = df_trades[df_trades['return_pct'] > 0]
    losers = df_trades[df_trades['return_pct'] <= 0]
    win_rate = len(winners) / total_trades * 100

    print(f"\n🎯 TRADE STATISTICS:")
    print(f"   Total trades: {total_trades}")
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
    print(f"   Winners avg: {winners['hold_days'].mean():.1f} days" if len(winners) > 0 else "")
    print(f"   Losers avg: {losers['hold_days'].mean():.1f} days" if len(losers) > 0 else "")

    print(f"\n🚪 EXIT REASONS:")
    exit_counts = df_trades['exit_reason'].value_counts()
    for reason, count in exit_counts.items():
        pct = count / total_trades * 100
        avg_ret = df_trades[df_trades['exit_reason'] == reason]['return_pct'].mean()
        print(f"   {reason}: {count} ({pct:.1f}%) avg: {avg_ret:+.1f}%")

    # Analyze losers in detail
    print(f"\n❌ LOSER ANALYSIS:")
    if len(losers) > 0:
        big_losers = losers[losers['return_pct'] <= -7]
        medium_losers = losers[(losers['return_pct'] > -7) & (losers['return_pct'] <= -3)]
        small_losers = losers[losers['return_pct'] > -3]

        print(f"   Big losers (≤-7%): {len(big_losers)} ({len(big_losers)/total_trades*100:.1f}%)")
        print(f"   Medium losers (-7% to -3%): {len(medium_losers)} ({len(medium_losers)/total_trades*100:.1f}%)")
        print(f"   Small losers (>-3%): {len(small_losers)} ({len(small_losers)/total_trades*100:.1f}%)")

        if len(losers) > 0:
            print(f"\n   Top 5 worst trades:")
            worst = df_trades.nsmallest(5, 'return_pct')
            for _, row in worst.iterrows():
                print(f"      {row['symbol']}: {row['return_pct']:.1f}% ({row['exit_reason']}, {row['hold_days']}d, score={row['entry_score']:.0f})")

    # Show winners
    print(f"\n✅ WINNER ANALYSIS:")
    if len(winners) > 0:
        print(f"   Top 5 best trades:")
        best = df_trades.nlargest(5, 'return_pct')
        for _, row in best.iterrows():
            print(f"      {row['symbol']}: +{row['return_pct']:.1f}% ({row['exit_reason']}, {row['hold_days']}d, score={row['entry_score']:.0f})")

    # Monthly breakdown
    print(f"\n📅 MONTHLY BREAKDOWN:")
    df_trades['month'] = pd.to_datetime(df_trades['entry_date']).dt.to_period('M')
    monthly = df_trades.groupby('month').agg({
        'return_pct': ['count', 'mean', lambda x: (x > 0).sum() / len(x) * 100],
        'hold_days': 'mean'
    }).round(1)
    monthly.columns = ['Trades', 'Avg Ret%', 'WinRate%', 'AvgDays']
    print(monthly.to_string())

    # Performance metrics
    total_return = df_trades['return_pct'].sum()
    gross_profit = winners['return_pct'].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers['return_pct'].sum()) if len(losers) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    print(f"\n📈 PERFORMANCE SUMMARY:")
    print(f"   Total Return (sum): {total_return:+.1f}%")
    print(f"   Profit Factor: {profit_factor:.2f}")
    print(f"   Trades per month: {total_trades / len(screening_dates) * 4:.1f}")

    # Risk metrics
    if len(losers) > 0:
        max_drawdown = losers['return_pct'].min()
        avg_loss = losers['return_pct'].mean()
        print(f"   Max single loss: {max_drawdown:.1f}%")
        print(f"   Average loss: {avg_loss:.1f}%")

    # Save results
    df_trades.to_csv('backtest_v9_results.csv', index=False)
    print(f"\n💾 Results saved to backtest_v9_results.csv")

    return df_trades


if __name__ == "__main__":
    results = run_backtest()
