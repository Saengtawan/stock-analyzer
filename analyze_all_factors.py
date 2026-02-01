#!/usr/bin/env python3
"""
วิเคราะห์ทุกปัจจัยที่กระทบผลลัพธ์

ปัจจัยที่ต้องดู:
1. Market Regime (ตลาดขาขึ้น/ขาลง)
2. Sector Performance (กลุ่มอุตสาหกรรม)
3. Seasonality (ฤดูกาล, วันในสัปดาห์)
4. VIX (ความผันผวนของตลาด)
5. วิเคราะห์ว่าเดือนไหนขาดทุน ทำไม?
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_accumulation(closes, volumes, period=20):
    if len(closes) < period:
        return 1.0
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


def calculate_atr_pct(closes, highs, lows, i, period=14):
    if i < period:
        return 5.0
    tr = []
    for j in range(i - period + 1, i + 1):
        if j > 0:
            tr.append(max(
                float(highs[j]) - float(lows[j]),
                abs(float(highs[j]) - float(closes[j-1])),
                abs(float(lows[j]) - float(closes[j-1]))
            ))
    atr = np.mean(tr) if tr else 0
    price = float(closes[i])
    return (atr / price) * 100 if price > 0 else 5.0


def main():
    print("=" * 80)
    print("วิเคราะห์ทุกปัจจัย")
    print("=" * 80)

    # Download market data
    print("\n1. ดาวน์โหลดข้อมูลตลาด...")
    spy = yf.download('SPY', period='1y', progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)

    # VIX
    vix = yf.download('^VIX', period='1y', progress=False)
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)

    # Define sectors
    SECTORS = {
        'Tech': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META'],
        'Finance': ['JPM', 'BAC', 'V', 'GS'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'LLY'],
        'Consumer': ['HD', 'COST', 'MCD', 'NKE'],
        'Industrial': ['CAT', 'HON', 'GE'],
        'Energy': ['XOM', 'CVX']
    }

    all_symbols = []
    for stocks in SECTORS.values():
        all_symbols.extend(stocks)

    print(f"\n2. ดาวน์โหลด {len(all_symbols)} หุ้น...")

    stock_data = {}
    for sym in all_symbols:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 100:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"   ดาวน์โหลดได้: {len(stock_data)} หุ้น")

    # Config
    CONFIG = {
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    # Collect trades with context
    all_trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        # Find sector
        sector = 'Other'
        for sec_name, sec_stocks in SECTORS.items():
            if sym in sec_stocks:
                sector = sec_name
                break

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))
        hold_days = CONFIG['hold_days']

        for i in range(55, n - hold_days - 1):
            price = float(closes[i])
            entry_date = dates[i]

            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

            # Gates
            if accum <= CONFIG['accum_min']:
                continue
            if rsi >= CONFIG['rsi_max']:
                continue
            if above_ma20 <= CONFIG['ma20_min']:
                continue
            if above_ma50 <= CONFIG['ma50_min']:
                continue
            if atr_pct > CONFIG['atr_max']:
                continue

            # Trade with stop-loss
            entry_price = price
            stop_price = entry_price * (1 + CONFIG['stop_pct'] / 100)
            stopped = False

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break
                day_low = float(lows[i + j])
                if day_low <= stop_price:
                    pct_return = CONFIG['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            # Get market context at entry
            try:
                spy_close = spy.loc[entry_date, 'Close']
                spy_ma20 = spy['Close'].rolling(20).mean().loc[entry_date]
                market_trend = 'UP' if spy_close > spy_ma20 else 'DOWN'
            except:
                market_trend = 'UNKNOWN'

            try:
                vix_val = vix.loc[entry_date, 'Close']
            except:
                vix_val = 20

            all_trades.append({
                'symbol': sym,
                'sector': sector,
                'date': entry_date,
                'day_of_week': entry_date.dayofweek,
                'month': entry_date.month,
                'return': pct_return,
                'stopped': stopped,
                'market_trend': market_trend,
                'vix': float(vix_val) if not pd.isna(vix_val) else 20,
                'rsi': rsi,
                'accum': accum,
                'atr_pct': atr_pct
            })

    df_trades = pd.DataFrame(all_trades)
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    print(f"\n3. รวม {len(df_trades)} trades")

    # ========== ANALYSIS ==========

    # Factor 1: Market Trend
    print("\n" + "=" * 80)
    print("Factor 1: MARKET TREND (SPY > MA20)")
    print("=" * 80)

    for trend in ['UP', 'DOWN']:
        group = df_trades[df_trades['market_trend'] == trend]
        if len(group) > 0:
            n = len(group)
            winners = len(group[group['return'] > 0])
            avg_ret = group['return'].mean()
            total = group['return'].sum()
            print(f"   {trend}: {n} trades, {winners/n*100:.0f}% WR, Avg: {avg_ret:+.2f}%, Total: {total:+.2f}%")

    # Factor 2: Sector
    print("\n" + "=" * 80)
    print("Factor 2: SECTOR PERFORMANCE")
    print("=" * 80)

    sector_stats = []
    for sector in df_trades['sector'].unique():
        group = df_trades[df_trades['sector'] == sector]
        n = len(group)
        winners = len(group[group['return'] > 0])
        avg_ret = group['return'].mean()
        total = group['return'].sum()

        sector_stats.append({
            'sector': sector,
            'trades': n,
            'win_rate': winners/n*100,
            'avg_return': avg_ret,
            'total_return': total
        })

        status = "✅" if avg_ret > 0 else "❌"
        print(f"   {status} {sector:<12}: {n:>2} trades, {winners/n*100:>5.1f}% WR, Avg: {avg_ret:+.2f}%")

    # Factor 3: Day of Week
    print("\n" + "=" * 80)
    print("Factor 3: DAY OF WEEK")
    print("=" * 80)

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    for dow, day_name in enumerate(days):
        group = df_trades[df_trades['day_of_week'] == dow]
        if len(group) > 0:
            n = len(group)
            winners = len(group[group['return'] > 0])
            avg_ret = group['return'].mean()
            status = "✅" if avg_ret > 0 else "❌"
            print(f"   {status} {day_name}: {n:>3} trades, {winners/n*100:>5.1f}% WR, Avg: {avg_ret:+.2f}%")

    # Factor 4: Month
    print("\n" + "=" * 80)
    print("Factor 4: MONTH")
    print("=" * 80)

    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    for m in sorted(df_trades['month'].unique()):
        group = df_trades[df_trades['month'] == m]
        n = len(group)
        winners = len(group[group['return'] > 0])
        avg_ret = group['return'].mean()
        total = group['return'].sum()
        status = "✅" if total > 0 else "❌"
        print(f"   {status} {months[m-1]}: {n:>3} trades, Total: {total:>+7.2f}%")

    # Factor 5: VIX Level
    print("\n" + "=" * 80)
    print("Factor 5: VIX LEVEL (Market Fear)")
    print("=" * 80)

    vix_bins = [(0, 15, 'Low (<15)'), (15, 20, 'Normal (15-20)'), (20, 30, 'High (20-30)'), (30, 100, 'Extreme (>30)')]
    for low, high, label in vix_bins:
        group = df_trades[(df_trades['vix'] >= low) & (df_trades['vix'] < high)]
        if len(group) > 0:
            n = len(group)
            winners = len(group[group['return'] > 0])
            avg_ret = group['return'].mean()
            status = "✅" if avg_ret > 0 else "❌"
            print(f"   {status} VIX {label}: {n:>3} trades, {winners/n*100:>5.1f}% WR, Avg: {avg_ret:+.2f}%")

    # ========== KEY INSIGHTS ==========
    print("\n" + "=" * 80)
    print("🔑 KEY INSIGHTS")
    print("=" * 80)

    # Best sectors
    best_sectors = sorted(sector_stats, key=lambda x: x['avg_return'], reverse=True)[:2]
    worst_sectors = sorted(sector_stats, key=lambda x: x['avg_return'])[:2]

    print(f"""
💡 ค้นพบ:

1. SECTOR ที่ดีที่สุด:
   - {best_sectors[0]['sector']}: {best_sectors[0]['avg_return']:+.2f}% avg
   - {best_sectors[1]['sector']}: {best_sectors[1]['avg_return']:+.2f}% avg

2. SECTOR ที่แย่:
   - {worst_sectors[0]['sector']}: {worst_sectors[0]['avg_return']:+.2f}% avg

3. MARKET TREND:
   - เทรดเฉพาะตอน SPY > MA20 จะดีกว่า

4. VIX:
   - ระวังเมื่อ VIX สูง (> 20)
""")

    # Suggestion
    print("=" * 80)
    print("💡 SUGGESTION")
    print("=" * 80)

    print("""
เพื่อให้ได้ 10%/เดือน ลองปรับ:

1. เทรดเฉพาะ sectors ที่ดี (Finance, Industrial)
2. เทรดเฉพาะตอนตลาดขาขึ้น (SPY > MA20)
3. หลีกเลี่ยงเดือนที่ผลงานไม่ดี (Aug, Oct, Nov)
4. หลีกเลี่ยง VIX สูง (> 25)
""")


if __name__ == '__main__':
    main()
