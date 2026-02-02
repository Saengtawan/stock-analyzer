#!/usr/bin/env python3
"""
TEST 17: Rapid Trader v3.10 — Smart Early Exit T+1 Backtest
เปรียบเทียบ: ระบบปกติ vs ระบบ + Signal Degradation Exit

กฎสำคัญ: ห้ามขายวันเดียวกับที่ซื้อ (PDT protection)
Smart Exit ทำงานเฉพาะ T+1 ขึ้นไปเท่านั้น
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

# === CONFIG (เหมือน production) ===
SIMULATED_CAPITAL = 4000
MAX_POSITIONS = 2
POSITION_SIZE_PCT = 40
STOP_LOSS_PCT = 2.5
TAKE_PROFIT_PCT = 6.0
MAX_HOLD_DAYS = 5
TRAIL_ACTIVATION_PCT = 2.0
TRAIL_LOCK_PCT = 70
MIN_SCORE = 90

# v3.10 Overextended Filter
MAX_SINGLE_DAY_MOVE = 8.0
MAX_SMA20_EXTENSION = 10.0
LOOKBACK_DAYS = 10

START_DATE = "2024-06-01"
END_DATE = "2026-02-01"

# === SMART EXIT CONFIG ===
SMART_EXIT_MIN_DEGRADED = 2  # ต้องมีอย่างน้อย 2 conditions ถึงจะ exit

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


def download_all_data():
    """Download data for all symbols"""
    print(f"Downloading data for {len(UNIVERSE)} stocks...")
    stock_data = {}
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
            if len(df) > 50:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                stock_data[symbol] = df
        except:
            pass
    print(f"Loaded {len(stock_data)} stocks")
    return stock_data


def calc_indicators(df):
    """Calculate technical indicators"""
    df = df.copy()

    # SMA20
    df['SMA20'] = df['Close'].rolling(20).mean()

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Volume ratio
    df['avg_volume'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume'] / df['avg_volume']

    # Gap percent (from prev close to today open)
    df['prev_close'] = df['Close'].shift(1)
    df['gap_pct'] = (df['Open'] / df['prev_close'] - 1) * 100

    # Today's move
    df['today_move'] = (df['Close'] / df['Open'] - 1) * 100

    # Yesterday change
    df['yesterday_change'] = (df['Close'].shift(1) / df['Close'].shift(2) - 1) * 100

    # Today change
    df['today_change'] = (df['Close'] / df['Close'].shift(1) - 1) * 100

    return df


def screen_stock(symbol, df, idx):
    """Screen stock for entry signal"""
    if idx < 25:
        return None

    close = df['Close']
    volume = df['Volume']

    current_price = get_val(close, idx)
    prev_close = get_val(close, idx - 1)
    prev_prev_close = get_val(close, idx - 2)

    if current_price is None or prev_close is None or prev_prev_close is None:
        return None

    # GATE 1: Price Filter
    if not (10 <= current_price <= 2000):
        return None

    # GATE 2: Volume
    avg_volume = float(volume.iloc[idx-19:idx+1].mean())
    if avg_volume < 500000:
        return None

    # GATE 3: SMA20 Uptrend
    sma20 = get_val(df['SMA20'], idx)
    if sma20 is None or current_price <= sma20:
        return None

    # GATE 4: Yesterday Dip
    yesterday_change = ((prev_close / prev_prev_close) - 1) * 100
    if yesterday_change > -1.0:
        return None

    # GATE 5: Today Not Falling
    today_change = ((current_price / prev_close) - 1) * 100
    if today_change < -1.0:
        return None

    # GATE 6: Bounce Confirmation
    open_price = get_val(df['Open'], idx)
    if open_price is None:
        return None
    is_green = current_price > open_price
    is_up_half = today_change >= 0.5
    if not (is_green or is_up_half):
        return None

    # GATE 7: Volume Confirmation
    today_volume = get_val(volume, idx)
    if today_volume is None or today_volume < avg_volume * 0.8:
        return None

    # GATE 8: Not in downtrend
    if idx >= 25:
        sma20_prev = get_val(df['SMA20'], idx - 5)
        if sma20_prev is not None and sma20 < sma20_prev:
            return None

    # GATE 9: Overextended Filter
    max_daily_move = 0
    if idx >= 11:
        for i in range(idx - LOOKBACK_DAYS, idx):
            c1 = get_val(close, i)
            c0 = get_val(close, i - 1)
            if c1 and c0 and c0 > 0:
                daily_return = (c1 / c0 - 1) * 100
                max_daily_move = max(max_daily_move, daily_return)

    if max_daily_move > MAX_SINGLE_DAY_MOVE:
        return None

    sma20_extension = ((current_price / sma20) - 1) * 100
    if sma20_extension > MAX_SMA20_EXTENSION:
        return None

    # GATE 10: Score
    score = 60
    score += min(10, yesterday_change * -3)
    score += min(10, today_change * 5)
    score += min(10, (today_volume / avg_volume - 1) * 20)
    score += 5 if is_green else 0

    if score < MIN_SCORE:
        return None

    return {
        'symbol': symbol,
        'price': current_price,
        'score': score
    }


def check_signal_degradation(pos, df, idx, entry_idx):
    """
    Check if Entry Thesis is broken
    Only for T+1+ (never same day = PDT safe)

    Returns: (should_exit, degraded_count, reasons)
    """
    days_held = idx - entry_idx

    # PDT GUARD: Never exit same day
    if days_held < 1:
        return False, 0, ["Same day - PDT blocked"]

    current_price = get_val(df['Close'], idx)
    entry_price = pos['entry_price']

    if current_price is None:
        return False, 0, ["No data"]

    unrealized_pnl = (current_price / entry_price - 1) * 100

    # Don't cut winners - let trail/TP handle
    if unrealized_pnl >= 0:
        return False, 0, ["In profit - let trail handle"]

    degraded = 0
    reasons = []

    # Condition 1: Below SMA20 (uptrend broken)
    sma20 = get_val(df['SMA20'], idx)
    if sma20 and current_price < sma20:
        degraded += 1
        reasons.append(f"Below SMA20")

    # Condition 2: Gap down > 2%
    gap = get_val(df['gap_pct'], idx) if 'gap_pct' in df.columns else 0
    if gap and gap < -2.0:
        degraded += 1
        reasons.append(f"Gap down {gap:.1f}%")

    # Condition 3: Low volume (< 50% avg)
    vol_ratio = get_val(df['vol_ratio'], idx) if 'vol_ratio' in df.columns else 1
    if vol_ratio and vol_ratio < 0.5:
        degraded += 1
        reasons.append(f"Low volume")

    # Condition 4: RSI crushed < 30 while losing
    rsi = get_val(df['RSI'], idx) if 'RSI' in df.columns else 50
    if rsi and rsi < 30 and unrealized_pnl < -1.0:
        degraded += 1
        reasons.append(f"RSI crushed ({rsi:.0f})")

    # Condition 5: Today crash > -3%
    today_move = get_val(df['today_move'], idx) if 'today_move' in df.columns else 0
    if today_move and today_move < -3.0:
        degraded += 1
        reasons.append(f"Today crash {today_move:.1f}%")

    should_exit = degraded >= SMART_EXIT_MIN_DEGRADED
    return should_exit, degraded, reasons


def run_backtest(stock_data, smart_exit_enabled):
    """Run backtest with or without smart exit"""

    # Get trading dates
    sample_df = list(stock_data.values())[0]
    trading_dates = sample_df.index.tolist()

    capital = SIMULATED_CAPITAL
    all_trades = []
    open_positions = []
    day_trades_5day = []
    monthly_pnl = defaultdict(float)

    # Smart exit tracking
    smart_exits = 0
    false_exits = 0
    saved_loss_total = 0

    for date_idx, current_date in enumerate(trading_dates):
        if date_idx < 25:
            continue

        # === CHECK EXITS ===
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

            if days_held < 1:
                continue

            entry_price = pos['entry_price']
            high = get_val(df['High'], pos_idx)
            low = get_val(df['Low'], pos_idx)
            close = get_val(df['Close'], pos_idx)

            if high is None or low is None or close is None:
                continue

            sl_price = pos['sl_price']
            tp_price = entry_price * (1 + TAKE_PROFIT_PCT / 100)

            # Update peak
            if high > pos['peak']:
                pos['peak'] = high

            # Check trailing
            gain_pct = ((pos['peak'] - entry_price) / entry_price) * 100
            if gain_pct >= TRAIL_ACTIVATION_PCT:
                pos['trail_active'] = True
                locked = (pos['peak'] - entry_price) * (TRAIL_LOCK_PCT / 100)
                new_trail = entry_price + locked
                if new_trail > pos['sl_price']:
                    pos['sl_price'] = new_trail
                    sl_price = new_trail

            exit_price = None
            exit_reason = None

            # === SMART EXIT CHECK (before SL/TP) ===
            if smart_exit_enabled and days_held >= 1:
                should_exit, deg_count, reasons = check_signal_degradation(
                    pos, df, pos_idx, entry_idx
                )
                if should_exit:
                    exit_price = close
                    exit_reason = 'SMART_EXIT'
                    smart_exits += 1

                    # Check false exit: would price recover in next 3 days?
                    future_high = 0
                    for f in range(1, 4):
                        if pos_idx + f < len(df):
                            fh = get_val(df['High'], pos_idx + f)
                            if fh:
                                future_high = max(future_high, fh)
                    if future_high > entry_price:
                        false_exits += 1

                    # Calculate saved loss vs waiting for SL
                    actual_loss_pct = (close / entry_price - 1) * 100
                    sl_loss_pct = -STOP_LOSS_PCT
                    if actual_loss_pct > sl_loss_pct:  # Less negative = saved
                        saved_loss_total += abs(actual_loss_pct - sl_loss_pct)

            # === NORMAL EXIT LOGIC ===
            if exit_price is None:
                if low <= sl_price:
                    exit_price = sl_price
                    exit_reason = 'TRAIL' if pos['trail_active'] else 'SL'
                elif high >= tp_price:
                    exit_price = tp_price
                    exit_reason = 'TP'
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

                month_key = current_date.strftime('%Y-%m')
                monthly_pnl[month_key] += pnl_usd

                if days_held == 0:  # Same day = day trade
                    day_trades_5day.append(current_date)

                open_positions.remove(pos)

        # Clean up day trade tracker
        cutoff = current_date - timedelta(days=5)
        day_trades_5day = [d for d in day_trades_5day if d > cutoff]

        # PDT check
        if len(day_trades_5day) >= 3:
            continue

        # Look for new entries
        if len(open_positions) >= MAX_POSITIONS:
            continue

        signals = []
        for symbol, df in stock_data.items():
            if current_date not in df.index:
                continue
            if any(p['symbol'] == symbol for p in open_positions):
                continue

            idx = df.index.get_loc(current_date)
            signal = screen_stock(symbol, df, idx)
            if signal:
                signals.append(signal)

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
                'sl_price': entry_price * (1 - STOP_LOSS_PCT / 100),
                'trail_active': False,
                'score': signal['score']
            })

    # Close remaining positions
    for pos in open_positions:
        symbol = pos['symbol']
        if symbol in stock_data:
            df = stock_data[symbol]
            exit_price = get_val(df['Close'], -1)
            if exit_price:
                pnl_usd = (exit_price - pos['entry_price']) * pos['shares']
                pnl_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                all_trades.append({
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
                })
                capital += pnl_usd

    # Calculate stats
    wins = [t for t in all_trades if t['pnl_pct'] > 0]
    losses = [t for t in all_trades if t['pnl_pct'] <= 0]
    day_trades_count = len([t for t in all_trades if t['days_held'] == 0])

    return {
        'capital': capital,
        'return_pct': (capital - SIMULATED_CAPITAL) / SIMULATED_CAPITAL * 100,
        'trades': len(all_trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(all_trades) * 100 if all_trades else 0,
        'avg_win': np.mean([t['pnl_pct'] for t in wins]) if wins else 0,
        'avg_loss': np.mean([t['pnl_pct'] for t in losses]) if losses else 0,
        'monthly': monthly_pnl,
        'day_trades': day_trades_count,
        'smart_exits': smart_exits,
        'false_exits': false_exits,
        'saved_loss': saved_loss_total,
        'all_trades': all_trades,
    }


def main():
    print("=" * 70)
    print("  TEST 17: SMART EARLY EXIT T+1 BACKTEST")
    print("=" * 70)

    # Download and prepare data
    stock_data = download_all_data()

    print("Calculating indicators...")
    for symbol in list(stock_data.keys()):
        try:
            stock_data[symbol] = calc_indicators(stock_data[symbol])
        except Exception as e:
            del stock_data[symbol]
    print(f"Ready: {len(stock_data)} stocks with indicators")

    # Run both backtests
    print("\n--- Running NORMAL backtest ---")
    normal = run_backtest(stock_data, smart_exit_enabled=False)

    print("\n--- Running SMART EXIT backtest ---")
    smart = run_backtest(stock_data, smart_exit_enabled=True)

    # === COMPARISON REPORT ===
    print("\n" + "=" * 70)
    print("  COMPARISON: NORMAL vs SMART EARLY EXIT T+1")
    print("=" * 70)

    diff_return = smart['return_pct'] - normal['return_pct']
    diff_capital = smart['capital'] - normal['capital']

    print(f"""
  {'Metric':<25} {'NORMAL':>12} {'SMART EXIT':>12} {'Diff':>10}
  {'-'*60}
  Final Capital           ${normal['capital']:>10,.2f} ${smart['capital']:>10,.2f} ${diff_capital:>+9,.2f}
  Total Return            {normal['return_pct']:>+11.2f}% {smart['return_pct']:>+11.2f}% {diff_return:>+9.2f}%
  Trades                  {normal['trades']:>12} {smart['trades']:>12}
  Win Rate                {normal['win_rate']:>11.1f}% {smart['win_rate']:>11.1f}% {smart['win_rate']-normal['win_rate']:>+9.1f}%
  Avg Win                 {normal['avg_win']:>+11.2f}% {smart['avg_win']:>+11.2f}%
  Avg Loss                {normal['avg_loss']:>+11.2f}% {smart['avg_loss']:>+11.2f}%
  Day Trades              {normal['day_trades']:>12} {smart['day_trades']:>12}
    """)

    if smart['smart_exits'] > 0:
        false_rate = smart['false_exits'] / smart['smart_exits'] * 100
        correct_rate = 100 - false_rate
        avg_saved = smart['saved_loss'] / smart['smart_exits']

        print(f"  SMART EXIT STATS:")
        print(f"  Smart Exits triggered:  {smart['smart_exits']}")
        print(f"  False Exits (mistake):  {smart['false_exits']} ({false_rate:.0f}%)")
        print(f"  Correct Exits:          {smart['smart_exits'] - smart['false_exits']} ({correct_rate:.0f}%)")
        print(f"  Avg Loss saved vs SL:   {avg_saved:.2f}% per exit")
    else:
        print("  No smart exits triggered")
        false_rate = 0

    # Monthly comparison
    print(f"\n  {'Month':<10} {'NORMAL':>10} {'SMART':>10} {'Diff':>10}")
    print(f"  {'-'*42}")
    all_months = sorted(set(list(normal['monthly'].keys()) + list(smart['monthly'].keys())))
    for mo in all_months:
        np_val = normal['monthly'].get(mo, 0)
        sp_val = smart['monthly'].get(mo, 0)
        diff = sp_val - np_val
        icon = '+' if diff > 0 else '-' if diff < 0 else '='
        print(f"  {icon} {mo:<8} ${np_val:>+9.2f} ${sp_val:>+9.2f} ${diff:>+9.2f}")

    # === VERDICT ===
    print(f"\n{'='*70}")

    pdt_safe = normal['day_trades'] == 0 and smart['day_trades'] == 0

    if diff_return > 1.0:
        verdict = "ENABLE"
        print(f"  VERDICT: SMART EXIT ดีกว่า {diff_return:+.2f}% --> ควรเปิดใช้")
    elif diff_return > -0.5 and smart['avg_loss'] > normal['avg_loss']:
        verdict = "ENABLE"
        print(f"  VERDICT: ใกล้เคียง ({diff_return:+.2f}%) แต่ avg loss ดีขึ้น --> เปิดใช้ได้")
    elif false_rate > 40:
        verdict = "KEEP NORMAL"
        print(f"  VERDICT: False exits สูง ({false_rate:.0f}%) --> ยังไม่ควรเปิด")
    else:
        verdict = "KEEP NORMAL"
        print(f"  VERDICT: SMART EXIT แย่กว่า {diff_return:+.2f}% --> ยังไม่ควรเปิด")

    if pdt_safe:
        print(f"  PDT STATUS: SAFE (0 day trades ทั้ง 2 modes)")
    else:
        print(f"  PDT WARNING: มี day trades! Normal={normal['day_trades']}, Smart={smart['day_trades']}")

    print("=" * 70)

    # Summary for test report
    print(f"""
╔══════════════════════════════════════════════════════════╗
║ TEST 17: Smart Early Exit T+1                            ║
╠══════════════════════════════════════════════════════════╣
║   NORMAL return:    {normal['return_pct']:>+6.2f}%                              ║
║   SMART return:     {smart['return_pct']:>+6.2f}%                              ║
║   Difference:       {diff_return:>+6.2f}%                              ║
║   Avg loss saved:   {smart['saved_loss']/max(1,smart['smart_exits']):>6.2f}% per exit                     ║
║   False exit rate:  {false_rate:>5.0f}%                               ║
║   Day trades:       {smart['day_trades']} (PDT {'SAFE' if pdt_safe else 'WARNING'})                        ║
║   Verdict:          {verdict:<20}                   ║
╚══════════════════════════════════════════════════════════╝
    """)

    return {
        'normal': normal,
        'smart': smart,
        'verdict': verdict,
        'pdt_safe': pdt_safe
    }


if __name__ == '__main__':
    main()
