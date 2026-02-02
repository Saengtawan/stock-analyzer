#!/usr/bin/env python3
"""
TEST 11: Full Historical Backtest with Monthly P/L
Rapid Trader v3.10 - 20-month backtest (2024-06 to 2026-02)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# ===== RAPID TRADER v3.10 CONFIGURATION =====
SIMULATED_CAPITAL = 4000
POSITION_SIZE_PCT = 40
MAX_POSITIONS = 2
STOP_LOSS_PCT = 2.5
TAKE_PROFIT_PCT = 6.0
TRAIL_ACTIVATION_PCT = 2.0
TRAIL_LOCK_PCT = 70
MAX_HOLD_DAYS = 5

# v3.10 Overextended Filter
MAX_SINGLE_DAY_MOVE = 8.0
MAX_SMA20_EXTENSION = 10.0
LOOKBACK_DAYS = 10

# Universe - volatile stocks for swing trading
UNIVERSE = [
    'NVDA', 'AMD', 'TSLA', 'META', 'GOOGL', 'AMZN', 'MSFT', 'AAPL',
    'NFLX', 'SHOP', 'ROKU', 'COIN', 'MARA', 'RIOT', 'HOOD',
    'PLTR', 'SNOW', 'DDOG', 'NET', 'CRWD', 'ZS', 'PANW', 'MDB',
    'ARM', 'SMCI', 'AVGO', 'MRVL', 'AMAT', 'LRCX', 'KLAC', 'ASML',
    'DASH', 'UBER', 'LYFT', 'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT',
    'PATH', 'DOCN', 'TWLO', 'OKTA', 'ZM', 'TEAM', 'WDAY', 'NOW',
    'CRM', 'ADBE', 'INTU', 'PYPL', 'V', 'MA', 'AXP', 'COF',
    'JPM', 'GS', 'MS', 'BAC', 'WFC', 'C', 'SCHW', 'BLK',
    'XOM', 'CVX', 'SLB', 'HAL', 'OXY', 'DVN', 'MPC', 'VLO',
    'LLY', 'UNH', 'JNJ', 'PFE', 'MRK', 'ABBV', 'TMO', 'DHR'
]


def get_val(series, idx):
    """Safely get float value from pandas series"""
    try:
        val = series.iloc[idx]
        if hasattr(val, 'iloc'):
            return float(val.iloc[0])
        return float(val)
    except:
        return None


def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return None
    return float(prices.iloc[-period:].mean())


def screen_stock(symbol, close, high, low, volume, open_prices, date_idx):
    """
    Rapid Trader v3.10 Screening Pipeline
    Returns signal dict if passes all gates, None otherwise
    """
    if date_idx < 25:  # Need at least 25 days of data
        return None

    current_price = get_val(close, date_idx)
    prev_close = get_val(close, date_idx - 1)
    prev_prev_close = get_val(close, date_idx - 2)

    if current_price is None or prev_close is None or prev_prev_close is None:
        return None

    # GATE 1: Price Filter ($10-$2000)
    if not (10 <= current_price <= 2000):
        return None

    # GATE 2: Minimum Volume
    avg_volume = float(volume.iloc[date_idx-19:date_idx+1].mean())
    if avg_volume < 500000:
        return None

    # GATE 3: SMA20 Uptrend
    sma20 = calculate_sma(close.iloc[:date_idx+1], 20)
    if sma20 is None or current_price <= sma20:
        return None

    # GATE 4: Yesterday Dip Required (>= -1%)
    yesterday_change = ((prev_close / prev_prev_close) - 1) * 100
    if yesterday_change > -1.0:
        return None

    # GATE 5: Today Not Falling (>= -1%)
    today_change = ((current_price / prev_close) - 1) * 100
    if today_change < -1.0:
        return None

    # GATE 6: Bounce Confirmation (green candle OR +0.5%)
    open_price = get_val(open_prices, date_idx)
    if open_price is None:
        return None
    is_green = current_price > open_price
    is_up_half = today_change >= 0.5
    if not (is_green or is_up_half):
        return None

    # GATE 7: Volume Confirmation
    today_volume = get_val(volume, date_idx)
    if today_volume is None or today_volume < avg_volume * 0.8:
        return None

    # GATE 8: Not in downtrend (SMA20 slope positive)
    if date_idx >= 25:
        sma20_5d_ago = calculate_sma(close.iloc[:date_idx-4], 20)
        if sma20_5d_ago is not None and sma20 < sma20_5d_ago:
            return None

    # ===== v3.10: OVEREXTENDED FILTER =====
    # GATE 9a: Max single-day move in last 10 days < 8%
    max_daily_move = 0
    if date_idx >= 11:
        for i in range(date_idx - LOOKBACK_DAYS, date_idx):
            c1 = get_val(close, i)
            c0 = get_val(close, i - 1)
            if c1 is not None and c0 is not None and c0 > 0:
                daily_return = (c1 / c0 - 1) * 100
                max_daily_move = max(max_daily_move, daily_return)

    if max_daily_move > MAX_SINGLE_DAY_MOVE:
        return None

    # GATE 9b: Price not too far above SMA20 (< 10%)
    sma20_extension = ((current_price / sma20) - 1) * 100
    if sma20_extension > MAX_SMA20_EXTENSION:
        return None

    # GATE 10: Score >= 90
    score = 60  # Base score
    score += min(10, yesterday_change * -3)  # Bigger dip = better
    score += min(10, today_change * 5)  # Bounce strength
    score += min(10, (today_volume / avg_volume - 1) * 20)  # Volume surge
    score += 5 if is_green else 0  # Green candle bonus

    if score < 90:
        return None

    return {
        'symbol': symbol,
        'price': current_price,
        'score': score,
        'yesterday_dip': yesterday_change,
        'today_bounce': today_change,
        'sma20_ext': sma20_extension,
        'max_10d_move': max_daily_move
    }


def run_backtest(start_date, end_date):
    """Run full backtest over the period"""
    print(f"\n{'='*60}")
    print(f"RAPID TRADER v3.10 - FULL HISTORICAL BACKTEST")
    print(f"Period: {start_date} to {end_date}")
    print(f"{'='*60}")

    # Download data for each stock individually
    print(f"\nDownloading data for {len(UNIVERSE)} stocks...")
    stock_data = {}
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if len(df) > 50:
                # Flatten multi-index if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                stock_data[symbol] = df
        except Exception as e:
            pass
    print(f"Loaded {len(stock_data)} stocks with sufficient data")

    if not stock_data:
        print("ERROR: No data loaded!")
        return SIMULATED_CAPITAL, [], {}

    # Get trading dates from first available stock
    sample_df = list(stock_data.values())[0]
    trading_dates = sample_df.index.tolist()

    # Track state
    capital = SIMULATED_CAPITAL
    all_trades = []
    monthly_pnl = defaultdict(float)
    open_positions = []
    day_trades_5day = []  # Rolling 5-day window for PDT

    print(f"\nRunning simulation on {len(trading_dates)} trading days...")

    for date_idx, current_date in enumerate(trading_dates):
        if date_idx < 25:  # Need history
            continue

        # Check for exits on open positions
        for pos in open_positions[:]:
            symbol = pos['symbol']
            if symbol not in stock_data:
                continue

            df = stock_data[symbol]
            if current_date not in df.index:
                continue

            pos_idx = df.index.get_loc(current_date)
            entry_idx = pos['entry_idx']
            days_held = pos_idx - entry_idx

            if days_held <= 0:
                continue

            entry_price = pos['entry_price']
            high = get_val(df['High'], pos_idx)
            low = get_val(df['Low'], pos_idx)
            close = get_val(df['Close'], pos_idx)

            if high is None or low is None or close is None:
                continue

            sl_price = entry_price * (1 - STOP_LOSS_PCT / 100)
            tp_price = entry_price * (1 + TAKE_PROFIT_PCT / 100)

            # Update peak
            if high > pos['peak']:
                pos['peak'] = high

            # Check trailing
            gain_pct = ((pos['peak'] - entry_price) / entry_price) * 100
            if gain_pct >= TRAIL_ACTIVATION_PCT:
                locked = (pos['peak'] - entry_price) * (TRAIL_LOCK_PCT / 100)
                new_trail = entry_price + locked
                if new_trail > pos['trail_stop']:
                    pos['trail_stop'] = new_trail

            exit_price = None
            exit_reason = None

            # Check exits
            if low <= sl_price:
                exit_price = sl_price
                exit_reason = 'SL'
            elif high >= tp_price:
                exit_price = tp_price
                exit_reason = 'TP'
            elif pos['trail_stop'] > 0 and low <= pos['trail_stop']:
                exit_price = pos['trail_stop']
                exit_reason = 'TRAIL'
            elif days_held >= MAX_HOLD_DAYS:
                current_pnl = ((close - entry_price) / entry_price) * 100
                if current_pnl < 1.0:
                    exit_price = close
                    exit_reason = 'TIME'

            if exit_price:
                shares = pos['shares']
                pnl_usd = (exit_price - entry_price) * shares
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': pos['entry_date'],
                    'exit_date': current_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'shares': shares,
                    'pnl_pct': pnl_pct,
                    'pnl_usd': pnl_usd,
                    'exit_reason': exit_reason,
                    'days_held': days_held
                }
                all_trades.append(trade)
                capital += pnl_usd

                # Track monthly P/L
                month_key = current_date.strftime('%Y-%m')
                monthly_pnl[month_key] += pnl_usd

                # Check if day trade
                if days_held == 1:
                    day_trades_5day.append(current_date)

                open_positions.remove(pos)

        # Clean up day trade tracker (rolling 5 days)
        cutoff = current_date - timedelta(days=5)
        day_trades_5day = [d for d in day_trades_5day if d > cutoff]

        # PDT check
        if len(day_trades_5day) >= 3:
            continue  # Can't trade today

        # Look for new entries (if we have room)
        if len(open_positions) >= MAX_POSITIONS:
            continue

        # Screen all stocks
        signals = []
        for symbol, df in stock_data.items():
            if current_date not in df.index:
                continue

            # Skip if already holding
            if any(p['symbol'] == symbol for p in open_positions):
                continue

            idx = df.index.get_loc(current_date)
            signal = screen_stock(
                symbol,
                df['Close'],
                df['High'],
                df['Low'],
                df['Volume'],
                df['Open'],
                idx
            )
            if signal:
                signals.append(signal)

        # Take best signal(s)
        signals.sort(key=lambda x: x['score'], reverse=True)
        slots_available = MAX_POSITIONS - len(open_positions)

        for signal in signals[:slots_available]:
            symbol = signal['symbol']
            df = stock_data[symbol]
            idx = df.index.get_loc(current_date)
            entry_price = signal['price']

            position_value = capital * POSITION_SIZE_PCT / 100
            shares = int(position_value / entry_price)
            if shares == 0:
                shares = 1

            open_positions.append({
                'symbol': symbol,
                'entry_date': current_date,
                'entry_price': entry_price,
                'entry_idx': idx,
                'shares': shares,
                'peak': entry_price,
                'trail_stop': 0
            })

    # Close any remaining positions at end
    for pos in open_positions:
        symbol = pos['symbol']
        if symbol in stock_data:
            df = stock_data[symbol]
            exit_price = get_val(df['Close'], -1)
            if exit_price is None:
                continue
            pnl_usd = (exit_price - pos['entry_price']) * pos['shares']
            pnl_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
            trade = {
                'symbol': symbol,
                'entry_date': pos['entry_date'],
                'exit_date': df.index[-1],
                'entry_price': pos['entry_price'],
                'exit_price': exit_price,
                'shares': pos['shares'],
                'pnl_pct': pnl_pct,
                'pnl_usd': pnl_usd,
                'exit_reason': 'END',
                'days_held': (df.index[-1] - pos['entry_date']).days
            }
            all_trades.append(trade)
            capital += pnl_usd
            month_key = df.index[-1].strftime('%Y-%m')
            monthly_pnl[month_key] += pnl_usd

    return capital, all_trades, monthly_pnl


def main():
    # 20-month backtest
    start_date = '2024-06-01'
    end_date = '2026-02-01'

    final_capital, trades, monthly_pnl = run_backtest(start_date, end_date)

    if not trades:
        print("\nNo trades executed!")
        return

    # Calculate stats
    total_return = ((final_capital - SIMULATED_CAPITAL) / SIMULATED_CAPITAL) * 100
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0

    # Print results
    print(f"\n{'='*60}")
    print(f"BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Starting Capital: ${SIMULATED_CAPITAL:,.2f}")
    print(f"Final Capital:    ${final_capital:,.2f}")
    print(f"Total Return:     {total_return:+.2f}%")
    print(f"\nTotal Trades:     {len(trades)}")
    print(f"Win Rate:         {win_rate:.1f}%")
    print(f"Avg Win:          {avg_win:+.2f}%")
    print(f"Avg Loss:         {avg_loss:.2f}%")

    # Monthly P/L
    print(f"\n{'='*60}")
    print(f"MONTHLY P/L BREAKDOWN")
    print(f"{'='*60}")

    profitable_months = 0
    for month in sorted(monthly_pnl.keys()):
        pnl = monthly_pnl[month]
        pnl_pct = (pnl / SIMULATED_CAPITAL) * 100
        status = "+" if pnl >= 0 else ""
        icon = "+" if pnl >= 0 else "-"
        print(f"{month}: {icon} {status}${pnl:,.2f} ({status}{pnl_pct:.2f}%)")
        if pnl >= 0:
            profitable_months += 1

    print(f"\nProfitable Months: {profitable_months}/{len(monthly_pnl)}")

    # Max drawdown calculation
    running_capital = SIMULATED_CAPITAL
    peak_capital = SIMULATED_CAPITAL
    max_dd = 0

    for trade in sorted(trades, key=lambda x: x['exit_date']):
        running_capital += trade['pnl_usd']
        if running_capital > peak_capital:
            peak_capital = running_capital
        dd = ((peak_capital - running_capital) / peak_capital) * 100
        if dd > max_dd:
            max_dd = dd

    print(f"\nMax Drawdown:     -{max_dd:.2f}%")

    # Trade details
    print(f"\n{'='*60}")
    print(f"ALL TRADES")
    print(f"{'='*60}")
    for t in sorted(trades, key=lambda x: x['entry_date']):
        entry = t['entry_date'].strftime('%Y-%m-%d') if hasattr(t['entry_date'], 'strftime') else str(t['entry_date'])[:10]
        exit_d = t['exit_date'].strftime('%Y-%m-%d') if hasattr(t['exit_date'], 'strftime') else str(t['exit_date'])[:10]
        icon = "+" if t['pnl_pct'] > 0 else "-"
        print(f"{icon} {t['symbol']:6} | {entry} -> {exit_d} | {t['pnl_pct']:+6.2f}% | ${t['pnl_usd']:+8.2f} | {t['exit_reason']}")

    print(f"\n{'='*60}")
    print(f"TEST 11 COMPLETE")
    print(f"{'='*60}")

    return final_capital, trades, monthly_pnl


if __name__ == '__main__':
    main()
