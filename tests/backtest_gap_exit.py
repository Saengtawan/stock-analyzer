#!/usr/bin/env python3
"""
TEST 18: Rapid Trader v3.10 — Pre-market Gap Exit Research
⚠️ RESEARCH ONLY — ไม่ implement เข้า production ทันที

เปรียบเทียบ 3 modes:
  A) NORMAL: SL -2.5% เท่านั้น
  B) GAP_EXIT_1.5: gap down > -1.5% → ขายที่ Open
  C) GAP_EXIT_1.0: gap down > -1.0% → ขายที่ Open

ข้อมูล: gap_pct = (Open / Prev_Close - 1) * 100 ← มีอยู่แล้วใน daily data
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

# CONFIG เหมือน production v3.11
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

# Gap exit thresholds to test
GAP_MODES = {
    'NORMAL':       None,   # ไม่มี gap exit
    'GAP_EXIT_1.5': -1.5,   # gap down > -1.5% → ขาย Open
    'GAP_EXIT_1.0': -1.0,   # gap down > -1.0% → ขาย Open
}


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
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['prev_close'] = df['Close'].shift(1)
    df['gap_pct'] = (df['Open'] / df['prev_close'] - 1) * 100
    df['avg_volume'] = df['Volume'].rolling(20).mean()
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


def run_backtest(stock_data, gap_threshold):
    """Run backtest with specific gap threshold"""

    sample_df = list(stock_data.values())[0]
    trading_dates = sample_df.index.tolist()

    capital = SIMULATED_CAPITAL
    all_trades = []
    open_positions = []
    monthly_pnl = defaultdict(float)

    # Gap exit tracking
    gap_exits = 0
    gap_exit_correct = 0  # หุ้นตกต่อหลังขาย
    gap_exit_false = 0    # หุ้นกลับขึ้นหลังขาย
    gap_saved = 0         # เงินที่ประหยัดได้

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
            open_price = get_val(df['Open'], pos_idx)
            high = get_val(df['High'], pos_idx)
            low = get_val(df['Low'], pos_idx)
            close = get_val(df['Close'], pos_idx)
            prev_close = get_val(df['Close'], pos_idx - 1)

            if open_price is None or high is None or low is None or close is None:
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

            # ═══ GAP EXIT CHECK (เห็นตอน Open ก่อน SL) ═══
            if gap_threshold is not None and days_held >= 1:
                gap = (open_price / prev_close - 1) * 100 if prev_close else 0
                gap_loss = (open_price / entry_price - 1) * 100

                # ขาย Open เมื่อ: gap down เกิน threshold + กำลังขาดทุน + ยังไม่ถึง SL
                if gap <= gap_threshold and gap_loss < 0 and gap_loss > -STOP_LOSS_PCT:
                    exit_price = open_price
                    exit_reason = 'GAP_EXIT'
                    gap_exits += 1

                    # วิเคราะห์: ถ้าไม่ขาย วันนี้จะเป็นยังไง?
                    if low <= entry_price * (1 - STOP_LOSS_PCT / 100):
                        # SL จะโดน hit วันนี้ → ขาย Open ดีกว่า
                        actual_sl = entry_price * (1 - STOP_LOSS_PCT / 100)
                        saved = (open_price - actual_sl) * pos['shares']
                        gap_saved += saved
                        gap_exit_correct += 1
                    elif close > open_price:
                        # วันนี้กลับขึ้น → ไม่ควรขาย
                        gap_exit_false += 1
                    else:
                        # วันนี้ยังตกต่อแต่ไม่ถึง SL → ถือว่าถูก
                        gap_exit_correct += 1

            # ═══ SL HARD LIMIT ═══
            if exit_price is None and low <= sl_price:
                exit_price = sl_price
                exit_reason = 'TRAIL' if pos['trail_active'] else 'SL'

            # ═══ TP ═══
            elif exit_price is None and high >= tp_price:
                exit_price = tp_price
                exit_reason = 'TP'

            # ═══ MAX HOLD ═══
            elif exit_price is None and days_held >= MAX_HOLD_DAYS:
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

                open_positions.remove(pos)

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

    # Calculate stats
    wins = [t for t in all_trades if t['pnl_pct'] > 0]
    losses = [t for t in all_trades if t['pnl_pct'] <= 0]

    return {
        'capital': capital,
        'return_pct': (capital - SIMULATED_CAPITAL) / SIMULATED_CAPITAL * 100,
        'trades': len(all_trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(all_trades) * 100 if all_trades else 0,
        'avg_win': np.mean([t['pnl_pct'] for t in wins]) if wins else 0,
        'avg_loss': np.mean([t['pnl_pct'] for t in losses]) if losses else 0,
        'gap_exits': gap_exits,
        'gap_correct': gap_exit_correct,
        'gap_false': gap_exit_false,
        'gap_saved': gap_saved,
        'monthly': monthly_pnl,
        'all_trades': all_trades,
    }


def main():
    print("=" * 70)
    print("  TEST 18: PRE-MARKET GAP EXIT RESEARCH")
    print("  ⚠️ RESEARCH ONLY — ไม่ implement production ทันที")
    print("=" * 70)

    # Download and prepare data
    stock_data = download_all_data()

    print("Calculating indicators...")
    for symbol in list(stock_data.keys()):
        try:
            stock_data[symbol] = calc_indicators(stock_data[symbol])
        except:
            del stock_data[symbol]
    print(f"Ready: {len(stock_data)} stocks")

    # Run all modes
    results = {}
    for mode_name, gap_threshold in GAP_MODES.items():
        print(f"\n--- Running {mode_name} ---")
        results[mode_name] = run_backtest(stock_data, gap_threshold)

    # === COMPARISON REPORT ===
    print("\n" + "=" * 70)
    print("  GAP EXIT RESEARCH — 3-WAY COMPARISON")
    print("=" * 70)

    print(f"\n  {'Metric':<22} {'NORMAL':>12} {'GAP -1.5%':>12} {'GAP -1.0%':>12}")
    print(f"  {'-'*60}")

    n = results['NORMAL']
    g15 = results['GAP_EXIT_1.5']
    g10 = results['GAP_EXIT_1.0']

    print(f"  {'Final Capital':<22} ${n['capital']:>10,.2f} ${g15['capital']:>10,.2f} ${g10['capital']:>10,.2f}")
    print(f"  {'Return':<22} {n['return_pct']:>+11.2f}% {g15['return_pct']:>+11.2f}% {g10['return_pct']:>+11.2f}%")
    print(f"  {'Trades':<22} {n['trades']:>12} {g15['trades']:>12} {g10['trades']:>12}")
    print(f"  {'Win Rate':<22} {n['win_rate']:>11.1f}% {g15['win_rate']:>11.1f}% {g10['win_rate']:>11.1f}%")
    print(f"  {'Avg Win':<22} {n['avg_win']:>+11.2f}% {g15['avg_win']:>+11.2f}% {g10['avg_win']:>+11.2f}%")
    print(f"  {'Avg Loss':<22} {n['avg_loss']:>+11.2f}% {g15['avg_loss']:>+11.2f}% {g10['avg_loss']:>+11.2f}%")
    print(f"  {'Gap Exits':<22} {n['gap_exits']:>12} {g15['gap_exits']:>12} {g10['gap_exits']:>12}")
    print(f"  {'Correct Exits':<22} {n['gap_correct']:>12} {g15['gap_correct']:>12} {g10['gap_correct']:>12}")
    print(f"  {'False Exits':<22} {n['gap_false']:>12} {g15['gap_false']:>12} {g10['gap_false']:>12}")
    print(f"  {'$ Saved by Gap':<22} ${n['gap_saved']:>10,.2f} ${g15['gap_saved']:>10,.2f} ${g10['gap_saved']:>10,.2f}")

    # Gap exit analysis
    for mode_name in ['GAP_EXIT_1.5', 'GAP_EXIT_1.0']:
        r = results[mode_name]
        if r['gap_exits'] > 0:
            correct_pct = r['gap_correct'] / r['gap_exits'] * 100
            false_pct = r['gap_false'] / r['gap_exits'] * 100
            print(f"\n  {mode_name} Analysis:")
            print(f"    Gap exits: {r['gap_exits']}")
            print(f"    Correct (หุ้นตกต่อ/SL hit): {r['gap_correct']} ({correct_pct:.0f}%)")
            print(f"    False (หุ้นกลับขึ้น): {r['gap_false']} ({false_pct:.0f}%)")
            print(f"    $ saved vs SL: ${r['gap_saved']:.2f}")

    # Monthly comparison
    print(f"\n  {'Month':<10} {'NORMAL':>10} {'GAP-1.5%':>10} {'GAP-1.0%':>10}")
    print(f"  {'-'*42}")
    all_months = sorted(set(list(n['monthly'].keys()) + list(g15['monthly'].keys())))
    for mo in all_months:
        nv = n['monthly'].get(mo, 0)
        g15v = g15['monthly'].get(mo, 0)
        g10v = g10['monthly'].get(mo, 0)
        best = max(nv, g15v, g10v)
        icon = '=' if nv == g15v == g10v else ('+' if g15v == best or g10v == best else '-')
        print(f"  {icon} {mo:<8} ${nv:>+9.2f} ${g15v:>+9.2f} ${g10v:>+9.2f}")

    # === VERDICT ===
    print(f"\n{'='*70}")

    best_mode = max(results.items(), key=lambda x: x[1]['return_pct'])
    print(f"  Best Mode: {best_mode[0]} ({best_mode[1]['return_pct']:+.2f}%)")

    for mode_name in ['GAP_EXIT_1.5', 'GAP_EXIT_1.0']:
        r = results[mode_name]
        diff = r['return_pct'] - n['return_pct']

        if r['gap_exits'] == 0:
            verdict = "N/A"
            reason = "ไม่มี gap exit เลย"
        elif diff > 0.5:
            verdict = "CONSIDER"
            reason = f"ดีกว่า NORMAL {diff:+.2f}%"
        elif diff > -0.5:
            false_pct = r['gap_false'] / r['gap_exits'] * 100 if r['gap_exits'] else 0
            if false_pct < 30:
                verdict = "MAYBE"
                reason = f"ใกล้เคียง + false exit {false_pct:.0f}%"
            else:
                verdict = "NO"
                reason = f"false exit สูง {false_pct:.0f}%"
        else:
            verdict = "NO"
            reason = f"แย่กว่า {diff:+.2f}%"

        print(f"  {mode_name}: {verdict} — {reason}")

    print(f"\n  ⚠️ REMINDER: นี่คือ RESEARCH เท่านั้น")
    print(f"     วันจันทร์ใช้ NORMAL mode (SL -2.5%)")
    print("=" * 70)

    # Summary box
    print(f"""
╔══════════════════════════════════════════════════════════╗
║ TEST 18: Pre-market Gap Exit Research                    ║
╠══════════════════════════════════════════════════════════╣
║   NORMAL return:      {n['return_pct']:>+6.2f}%                           ║
║   GAP -1.5% return:   {g15['return_pct']:>+6.2f}%                           ║
║   GAP -1.0% return:   {g10['return_pct']:>+6.2f}%                           ║
║                                                          ║
║   GAP -1.5% exits:    {g15['gap_exits']:>3} (correct: {g15['gap_correct']}, false: {g15['gap_false']})       ║
║   GAP -1.0% exits:    {g10['gap_exits']:>3} (correct: {g10['gap_correct']}, false: {g10['gap_false']})       ║
║                                                          ║
║   Best Mode:          {best_mode[0]:<20}             ║
║   Status:             RESEARCH COMPLETE                  ║
╚══════════════════════════════════════════════════════════╝
    """)

    return results


if __name__ == '__main__':
    main()
