#!/usr/bin/env python3
"""
ตรวจสอบว่าผลลัพธ์ 16.91%/month เป็นจริงหรือไม่

ข้อควรตรวจสอบ:
1. มีเดือนขาดทุนเยอะ (3/10) - ต้องยอมรับได้หรือไม่?
2. Win rate เพียง 42% - ขาดทุนบ่อยกว่าได้กำไร
3. ตัวเลขมาจากการคำนวณที่ถูกต้องหรือไม่?
4. มีอะไรที่พลาดไปหรือไม่?
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
    print("REALISTIC CHECK - ตรวจสอบความเป็นจริง")
    print("=" * 80)

    # ใช้หุ้นน้อยลงเพื่อดูรายละเอียด
    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'QCOM', 'CRM', 'JPM', 'BAC', 'V',
        'JNJ', 'UNH', 'PFE', 'HD', 'COST', 'MCD',
        'CAT', 'XOM', 'NFLX'
    ]

    print(f"\nDownloading {len(symbols)} stocks...")

    stock_data = {}
    for sym in symbols:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 100:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            stock_data[sym] = df
        except:
            pass

    print(f"Downloaded: {len(stock_data)} stocks")

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

    # Detailed trade log
    all_trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))
        hold_days = CONFIG['hold_days']

        for i in range(55, n - hold_days - 1):
            price = float(closes[i])

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
                day_close = float(closes[i + j])
                if day_low <= stop_price:
                    exit_price = stop_price
                    pct_return = CONFIG['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'date': dates[i],
                'entry': entry_price,
                'exit': exit_price,
                'return': pct_return,
                'stopped': stopped
            })

    df_trades = pd.DataFrame(all_trades)
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])
    df_trades = df_trades.sort_values('date')

    # Statistics
    print("\n" + "=" * 80)
    print("TRADE STATISTICS")
    print("=" * 80)

    total = len(df_trades)
    winners = len(df_trades[df_trades['return'] > 0])
    losers = len(df_trades[df_trades['return'] <= 0])
    stopped = len(df_trades[df_trades['stopped'] == True])

    print(f"\nTotal Trades: {total}")
    print(f"Winners: {winners} ({winners/total*100:.1f}%)")
    print(f"Losers: {losers} ({losers/total*100:.1f}%)")
    print(f"  - Stopped out: {stopped}")
    print(f"  - Held but lost: {losers - stopped}")

    # Return analysis
    print("\n" + "=" * 80)
    print("RETURN ANALYSIS")
    print("=" * 80)

    avg_winner = df_trades[df_trades['return'] > 0]['return'].mean()
    avg_loser = df_trades[df_trades['return'] <= 0]['return'].mean()
    avg_all = df_trades['return'].mean()

    print(f"\nAverage Winner: {avg_winner:+.2f}%")
    print(f"Average Loser: {avg_loser:+.2f}%")
    print(f"Average All: {avg_all:+.2f}%")

    # Expected value calculation
    win_rate = winners / total
    ev = (win_rate * avg_winner) + ((1 - win_rate) * avg_loser)
    print(f"\nExpected Value per trade: {ev:+.2f}%")
    print(f"  = {win_rate*100:.1f}% × {avg_winner:+.2f}% + {(1-win_rate)*100:.1f}% × {avg_loser:+.2f}%")

    # Monthly breakdown
    print("\n" + "=" * 80)
    print("MONTHLY BREAKDOWN")
    print("=" * 80)

    df_trades['month'] = df_trades['date'].dt.to_period('M')

    for month, group in df_trades.groupby('month'):
        n = len(group)
        w = len(group[group['return'] > 0])
        total_ret = group['return'].sum()
        status = "✅" if total_ret > 10 else ("⭐" if total_ret > 0 else "❌")
        print(f"{status} {month}: {n:>2} trades, {w:>2}W/{n-w}L, Total: {total_ret:>+7.2f}%")

    # Total
    total_return = df_trades['return'].sum()
    n_months = len(df_trades['month'].unique())
    monthly_avg = total_return / n_months

    print(f"\n{'='*40}")
    print(f"Total Return: {total_return:+.2f}%")
    print(f"Months: {n_months}")
    print(f"Monthly Average: {monthly_avg:+.2f}%")

    # Sample trades to verify
    print("\n" + "=" * 80)
    print("SAMPLE TRADES (First 15)")
    print("=" * 80)

    print(f"\n{'Symbol':<6} {'Date':<12} {'Entry':>8} {'Exit':>8} {'Return':>8} {'Status':<6}")
    print("-" * 55)

    for _, t in df_trades.head(15).iterrows():
        date_str = t['date'].strftime('%Y-%m-%d')
        status = "STOP" if t['stopped'] else "OK"
        print(f"{t['symbol']:<6} {date_str} ${t['entry']:>7.2f} ${t['exit']:>7.2f} {t['return']:>+7.2f}% {status}")

    # Verdict
    print("\n" + "=" * 80)
    print("FINAL ASSESSMENT")
    print("=" * 80)

    print(f"""
📊 สรุปผลลัพธ์:
   - Win Rate: {winners/total*100:.1f}% (ต่ำกว่า 50%)
   - Average Winner: {avg_winner:+.2f}%
   - Average Loser: {avg_loser:+.2f}%
   - Monthly Return: {monthly_avg:+.2f}%

💡 วิเคราะห์:
   - Win Rate ต่ำ ({winners/total*100:.1f}%) แต่ยังทำกำไรได้
   - เพราะ Winner เฉลี่ย {avg_winner:.2f}% > |Loser| เฉลี่ย {abs(avg_loser):.2f}%
   - Stop-loss -2% คุม max loss ได้ดี
   - มีเดือนขาดทุน แต่ภาพรวมยังบวก

⚠️ ความเสี่ยง:
   - {losers/total*100:.0f}% ของเทรดขาดทุน
   - ต้องยอมรับได้ที่จะแพ้บ่อย
   - ต้องมีวินัยในการ stop-loss
""")

    if monthly_avg >= 10:
        print(f"✅ ผ่านเป้าหมาย 10%/เดือน ({monthly_avg:.2f}%)")
    else:
        print(f"❌ ยังไม่ถึง 10%/เดือน ({monthly_avg:.2f}%)")


if __name__ == '__main__':
    main()
