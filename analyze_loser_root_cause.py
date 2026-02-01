#!/usr/bin/env python3
"""
LOSER ROOT CAUSE ANALYSIS - หา pattern ของหุ้นที่ขาดทุน

เป้าหมาย:
1. หา root cause ว่าทำไมหุ้นถึง loser
2. ดูว่าตัวไหนโดน SL เร็ว (ภายในวัน) - PDT risk!
3. หา filter เพิ่มเพื่อลด loser

PDT Rule: ซื้อ-ขายหุ้นตัวเดียวกันภายในวันเดียว 4+ ครั้งใน 5 วัน = PDT
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

# Rapid Trader universe
UNIVERSE = [
    'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
    'QCOM', 'AMAT', 'LRCX', 'KLAC',
    'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG',
    'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
    'CRM', 'NOW', 'SHOP',
    'RIVN', 'LCID', 'ENPH', 'FSLR',
]

# v2.0 Parameters
SL_PCT = 1.5  # Stop loss %
TP_PCT = 4.0  # Take profit %
MAX_DAYS = 4  # Max hold days

def get_intraday_data(symbol, date):
    """Get intraday data to check same-day SL hits"""
    try:
        ticker = yf.Ticker(symbol)
        # Get 1-hour data for the day
        start = date.strftime('%Y-%m-%d')
        end = (date + timedelta(days=1)).strftime('%Y-%m-%d')
        data = ticker.history(start=start, end=end, interval='1h')
        return data
    except:
        return None

def analyze_trade(symbol, entry_date, entry_price, data):
    """Analyze a single trade - when did it hit SL or TP?"""
    sl_price = entry_price * (1 - SL_PCT / 100)
    tp_price = entry_price * (1 + TP_PCT / 100)

    result = {
        'symbol': symbol,
        'entry_date': entry_date,
        'entry_price': entry_price,
        'sl_price': sl_price,
        'tp_price': tp_price,
        'outcome': None,
        'exit_date': None,
        'exit_price': None,
        'days_held': 0,
        'pnl_pct': 0,
        'same_day_sl': False,  # PDT risk!
        'hit_sl_first_hour': False,
        'reasons': []
    }

    # Find entry index
    entry_idx = None
    for i, d in enumerate(data.index):
        if d.strftime('%Y-%m-%d') == entry_date.strftime('%Y-%m-%d'):
            entry_idx = i
            break

    if entry_idx is None:
        return None

    # Track from entry
    for i in range(entry_idx, min(entry_idx + MAX_DAYS + 1, len(data))):
        row = data.iloc[i]
        current_date = data.index[i]
        days_held = (current_date - data.index[entry_idx]).days

        low = row['Low']
        high = row['High']
        close = row['Close']

        # Check if hit SL (using low)
        if low <= sl_price:
            result['outcome'] = 'LOSS'
            result['exit_date'] = current_date
            result['exit_price'] = sl_price
            result['days_held'] = days_held
            result['pnl_pct'] = -SL_PCT
            result['same_day_sl'] = (days_held == 0)

            if days_held == 0:
                result['reasons'].append("Same-day SL hit - PDT RISK!")
            break

        # Check if hit TP (using high)
        if high >= tp_price:
            result['outcome'] = 'WIN'
            result['exit_date'] = current_date
            result['exit_price'] = tp_price
            result['days_held'] = days_held
            result['pnl_pct'] = TP_PCT
            break

        # Time stop
        if days_held >= MAX_DAYS:
            result['outcome'] = 'TIME_STOP'
            result['exit_date'] = current_date
            result['exit_price'] = close
            result['days_held'] = days_held
            result['pnl_pct'] = (close - entry_price) / entry_price * 100
            break

    return result

def get_entry_conditions(symbol, entry_date, data):
    """Get conditions at entry to find patterns"""
    entry_idx = None
    for i, d in enumerate(data.index):
        if d.strftime('%Y-%m-%d') == entry_date.strftime('%Y-%m-%d'):
            entry_idx = i
            break

    if entry_idx is None or entry_idx < 20:
        return {}

    close = data['Close']
    high = data['High']
    low = data['Low']
    volume = data['Volume']

    current = close.iloc[entry_idx]

    # Calculate indicators
    sma5 = close.iloc[entry_idx-5:entry_idx].mean()
    sma10 = close.iloc[entry_idx-10:entry_idx].mean()
    sma20 = close.iloc[entry_idx-20:entry_idx].mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).iloc[entry_idx]

    # Momentum
    mom_1d = (current / close.iloc[entry_idx-1] - 1) * 100
    mom_3d = (current / close.iloc[entry_idx-3] - 1) * 100
    mom_5d = (current / close.iloc[entry_idx-5] - 1) * 100

    # ATR
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[entry_idx]
    atr_pct = atr / current * 100

    # Gap
    prev_close = close.iloc[entry_idx-1]
    open_price = data['Open'].iloc[entry_idx]
    gap_pct = (open_price - prev_close) / prev_close * 100

    # Distance from high
    high_10d = high.iloc[entry_idx-10:entry_idx].max()
    dist_from_high = (high_10d - current) / high_10d * 100

    # Volume
    avg_vol = volume.iloc[entry_idx-20:entry_idx].mean()
    vol_ratio = volume.iloc[entry_idx] / avg_vol if avg_vol > 0 else 1

    # Day of week
    dow = entry_date.strftime('%A')

    return {
        'rsi': rsi,
        'mom_1d': mom_1d,
        'mom_3d': mom_3d,
        'mom_5d': mom_5d,
        'atr_pct': atr_pct,
        'gap_pct': gap_pct,
        'dist_from_high': dist_from_high,
        'vol_ratio': vol_ratio,
        'above_sma5': current > sma5,
        'above_sma10': current > sma10,
        'above_sma20': current > sma20,
        'day_of_week': dow,
    }

def simulate_trades(start_date, end_date):
    """Simulate trades and collect loser data"""
    print("=" * 70)
    print("LOSER ROOT CAUSE ANALYSIS")
    print("=" * 70)
    print(f"Period: {start_date} to {end_date}")
    print(f"SL: {SL_PCT}% | TP: {TP_PCT}% | Max Hold: {MAX_DAYS} days")
    print()

    # Load data
    print("Loading data...")
    all_data = {}
    for symbol in UNIVERSE:
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date - timedelta(days=60), end=end_date + timedelta(days=10))
            if len(data) > 30:
                all_data[symbol] = data
        except:
            pass

    print(f"Loaded {len(all_data)} stocks")
    print()

    # Simulate entries
    trades = []
    current = start_date

    while current <= end_date:
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        for symbol in all_data:
            data = all_data[symbol]

            # Check if we have data for this date
            entry_idx = None
            for i, d in enumerate(data.index):
                if d.strftime('%Y-%m-%d') == current.strftime('%Y-%m-%d'):
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx < 20:
                continue

            # Get entry conditions
            conditions = get_entry_conditions(symbol, current, data)
            if not conditions:
                continue

            # Simple entry criteria (similar to screener)
            score = 0

            # Pullback
            if -8 <= conditions.get('mom_5d', 0) <= 0:
                score += 30

            # RSI
            if 30 <= conditions.get('rsi', 50) <= 55:
                score += 25

            # Trend
            if conditions.get('above_sma20', False):
                score += 20

            # Volatility
            if conditions.get('atr_pct', 0) >= 2:
                score += 15

            # Minimum score
            if score < 60:
                continue

            # Simulate trade
            entry_price = data['Close'].iloc[entry_idx]
            result = analyze_trade(symbol, current, entry_price, data)

            if result:
                result['conditions'] = conditions
                result['score'] = score
                trades.append(result)

        current += timedelta(days=1)

    return trades

def analyze_results(trades):
    """Analyze trade results"""

    if not trades:
        print("No trades to analyze")
        return

    # Separate winners and losers
    winners = [t for t in trades if t['outcome'] == 'WIN']
    losers = [t for t in trades if t['outcome'] == 'LOSS']
    time_stops = [t for t in trades if t['outcome'] == 'TIME_STOP']

    print("=" * 70)
    print("OVERALL STATISTICS")
    print("=" * 70)
    print(f"Total Trades: {len(trades)}")
    print(f"Winners: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")
    print(f"Time Stops: {len(time_stops)} ({len(time_stops)/len(trades)*100:.1f}%)")
    print()

    # PDT Risk Analysis
    same_day_sl = [t for t in losers if t.get('same_day_sl', False)]
    print("=" * 70)
    print("⚠️  PDT RISK ANALYSIS - Same-Day Stop Loss Hits")
    print("=" * 70)
    print(f"Same-day SL hits: {len(same_day_sl)} out of {len(losers)} losers ({len(same_day_sl)/len(losers)*100:.1f}%)")
    print()

    if same_day_sl:
        print("Same-day SL trades:")
        for t in same_day_sl[:10]:
            cond = t.get('conditions', {})
            print(f"  {t['symbol']} on {t['entry_date'].strftime('%Y-%m-%d')}")
            print(f"    Entry: ${t['entry_price']:.2f} | RSI: {cond.get('rsi', 0):.0f} | Mom1d: {cond.get('mom_1d', 0):+.1f}%")
            print(f"    Gap: {cond.get('gap_pct', 0):+.1f}% | ATR: {cond.get('atr_pct', 0):.1f}%")
        print()

    # Loser Pattern Analysis
    print("=" * 70)
    print("LOSER PATTERN ANALYSIS")
    print("=" * 70)

    # By days held
    days_held_dist = defaultdict(int)
    for t in losers:
        days_held_dist[t['days_held']] += 1

    print("\nLosers by days held:")
    for days in sorted(days_held_dist.keys()):
        count = days_held_dist[days]
        pct = count / len(losers) * 100
        bar = "█" * int(pct / 2)
        print(f"  Day {days}: {count:3d} ({pct:5.1f}%) {bar}")

    # Analyze conditions that lead to losses
    print("\n" + "=" * 70)
    print("CONDITIONS THAT LEAD TO LOSSES (vs Winners)")
    print("=" * 70)

    def avg_condition(trades_list, key):
        values = [t['conditions'].get(key, 0) for t in trades_list if t.get('conditions')]
        return sum(values) / len(values) if values else 0

    conditions_to_check = [
        ('rsi', 'RSI'),
        ('mom_1d', 'Momentum 1d'),
        ('mom_3d', 'Momentum 3d'),
        ('mom_5d', 'Momentum 5d'),
        ('atr_pct', 'ATR %'),
        ('gap_pct', 'Gap %'),
        ('dist_from_high', 'Dist from High %'),
        ('vol_ratio', 'Volume Ratio'),
    ]

    print(f"\n{'Condition':<20} {'Winners':>12} {'Losers':>12} {'Diff':>12}")
    print("-" * 60)

    for key, label in conditions_to_check:
        win_avg = avg_condition(winners, key)
        lose_avg = avg_condition(losers, key)
        diff = lose_avg - win_avg
        print(f"{label:<20} {win_avg:>12.2f} {lose_avg:>12.2f} {diff:>+12.2f}")

    # SMA analysis
    print("\nSMA Position (% above):")
    for sma in ['above_sma5', 'above_sma10', 'above_sma20']:
        win_pct = sum(1 for t in winners if t['conditions'].get(sma, False)) / len(winners) * 100 if winners else 0
        lose_pct = sum(1 for t in losers if t['conditions'].get(sma, False)) / len(losers) * 100 if losers else 0
        print(f"  {sma}: Winners {win_pct:.1f}% | Losers {lose_pct:.1f}%")

    # Day of week analysis
    print("\nLosers by day of week:")
    dow_dist = defaultdict(int)
    for t in losers:
        dow = t['conditions'].get('day_of_week', 'Unknown')
        dow_dist[dow] += 1

    for dow in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        count = dow_dist.get(dow, 0)
        pct = count / len(losers) * 100 if losers else 0
        bar = "█" * int(pct / 2)
        print(f"  {dow:<12}: {count:3d} ({pct:5.1f}%) {bar}")

    # Key findings
    print("\n" + "=" * 70)
    print("🔑 KEY FINDINGS & RECOMMENDATIONS")
    print("=" * 70)

    # Find patterns
    findings = []

    # Same-day SL
    same_day_pct = len(same_day_sl) / len(losers) * 100 if losers else 0
    if same_day_pct > 30:
        findings.append(f"⚠️  {same_day_pct:.0f}% of losers hit SL on SAME DAY - PDT risk!")

    # Gap up entries
    losers_gap_up = [t for t in losers if t['conditions'].get('gap_pct', 0) > 1]
    if len(losers_gap_up) / len(losers) > 0.3 if losers else False:
        findings.append(f"⚠️  {len(losers_gap_up)/len(losers)*100:.0f}% of losers entered on GAP UP days")

    # Below SMA20
    losers_below_sma20 = [t for t in losers if not t['conditions'].get('above_sma20', True)]
    if len(losers_below_sma20) / len(losers) > 0.4 if losers else False:
        findings.append(f"⚠️  {len(losers_below_sma20)/len(losers)*100:.0f}% of losers were BELOW SMA20")

    # High volatility
    avg_atr_losers = avg_condition(losers, 'atr_pct')
    avg_atr_winners = avg_condition(winners, 'atr_pct')
    if avg_atr_losers > avg_atr_winners * 1.2:
        findings.append(f"⚠️  Losers had {avg_atr_losers/avg_atr_winners:.0%} higher ATR than winners")

    # Monday/Friday
    monday_losers = dow_dist.get('Monday', 0)
    friday_losers = dow_dist.get('Friday', 0)
    if monday_losers / len(losers) > 0.25 if losers else False:
        findings.append(f"⚠️  {monday_losers/len(losers)*100:.0f}% of losers on Monday - avoid Monday entries?")

    for f in findings:
        print(f"  {f}")

    # Recommendations
    print("\n📋 RECOMMENDATIONS TO REDUCE LOSERS & AVOID PDT:")
    print()

    if same_day_pct > 30:
        print("  1. AVOID entering on gap-up days (gap > 1%)")
        print("     - Gap up often reverses, hitting SL same day")
        print()

    print("  2. ADD TIME FILTER:")
    print("     - Don't enter in first 30 min of market open")
    print("     - Wait for price to stabilize")
    print()

    print("  3. STRICTER ENTRY FILTERS:")
    print(f"     - Only enter if above SMA20 (losers: {len(losers_below_sma20)} were below)")
    print("     - Require RSI 35-50 (avoid too oversold)")
    print()

    print("  4. WIDER SL FOR VOLATILE STOCKS:")
    print("     - If ATR > 4%, use 2% SL instead of 1.5%")
    print("     - Prevents getting stopped out by noise")
    print()

    print("  5. AVOID HIGH-RISK DAYS:")
    print("     - Monday: Weekend news gaps")
    print("     - FOMC/CPI days: High volatility")
    print()

    return {
        'total': len(trades),
        'winners': len(winners),
        'losers': len(losers),
        'same_day_sl': len(same_day_sl),
        'same_day_pct': same_day_pct,
    }


if __name__ == "__main__":
    # Analyze last 3 months
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    trades = simulate_trades(start_date, end_date)
    results = analyze_results(trades)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total trades analyzed: {results['total']}")
    print(f"Same-day SL hits (PDT risk): {results['same_day_sl']} ({results['same_day_pct']:.1f}%)")
    print()
    print("Run this analysis regularly to monitor loser patterns!")
