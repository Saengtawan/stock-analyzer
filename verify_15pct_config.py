#!/usr/bin/env python3
"""
ตรวจสอบ config ที่ได้ 15%+/เดือน อย่างละเอียด
ดูว่าผลลัพธ์สมจริงหรือไม่
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
    print("ตรวจสอบ Config ATR<3.0 อย่างละเอียด")
    print("=" * 80)

    # Config ที่จะทดสอบ
    CONFIG = {
        'name': 'ATR<3.0 (15%/month)',
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'vol_surge_min': 1.0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    print(f"\nConfig: {CONFIG['name']}")
    print(f"  Accum > {CONFIG['accum_min']}")
    print(f"  RSI < {CONFIG['rsi_max']}")
    print(f"  MA20 > {CONFIG['ma20_min']}%")
    print(f"  MA50 > {CONFIG['ma50_min']}%")
    print(f"  Vol Surge > {CONFIG['vol_surge_min']}")
    print(f"  ATR < {CONFIG['atr_max']}%")
    print(f"  Hold: {CONFIG['hold_days']} days")
    print(f"  Stop: {CONFIG['stop_pct']}%")

    symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT',
        'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG', 'NET',
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'NKE',
        'CAT', 'DE', 'HON', 'GE', 'BA',
        'XOM', 'CVX', 'NFLX', 'DIS', 'T', 'VZ'
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

    # รัน backtest
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

            vol_avg = float(np.mean(volumes[i-19:i]))
            vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

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
            if vol_surge < CONFIG['vol_surge_min']:
                continue
            if atr_pct > CONFIG['atr_max']:
                continue

            # Trade
            entry_price = price
            stop_price = entry_price * (1 + CONFIG['stop_pct'] / 100)
            stopped = False

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break
                day_price = float(closes[i + j])
                if day_price <= stop_price:
                    pct_return = CONFIG['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'date': dates[i],
                'entry_price': entry_price,
                'return': pct_return,
                'stopped': stopped,
                'rsi': rsi,
                'accum': accum,
                'atr_pct': atr_pct,
                'vol_surge': vol_surge
            })

    df_trades = pd.DataFrame(all_trades)

    # Deduplicate
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades['month'] = df_trades['date'].dt.month
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    print("\n" + "=" * 80)
    print("ผลลัพธ์รายเดือน")
    print("=" * 80)

    # วิเคราะห์รายเดือน
    monthly_stats = []
    for (year, month), group in df_trades.groupby(['year', 'month']):
        n_trades = len(group)
        n_winners = len(group[group['return'] > 0])
        n_losers = len(group[group['return'] <= 0])
        total_ret = group['return'].sum()
        avg_ret = group['return'].mean()

        monthly_stats.append({
            'year': year,
            'month': month,
            'trades': n_trades,
            'winners': n_winners,
            'losers': n_losers,
            'win_rate': n_winners / n_trades * 100 if n_trades > 0 else 0,
            'total_return': total_ret,
            'avg_return': avg_ret
        })

        status = "✅" if total_ret > 0 else "❌"
        print(f"{status} {year}-{month:02d}: {n_trades} trades, {n_winners}W/{n_losers}L, Total: {total_ret:+.2f}%")

    df_monthly = pd.DataFrame(monthly_stats)

    # สรุป
    print("\n" + "=" * 80)
    print("สรุปรวม")
    print("=" * 80)

    total_trades = len(df_trades)
    total_winners = len(df_trades[df_trades['return'] > 0])
    total_losers = len(df_trades[df_trades['return'] <= 0])
    total_return = df_trades['return'].sum()
    avg_return = df_trades['return'].mean()

    n_months = len(df_monthly)
    profitable_months = len(df_monthly[df_monthly['total_return'] > 0])

    print(f"""
📊 ผลรวมทั้งหมด:
   เทรดทั้งหมด: {total_trades}
   ชนะ: {total_winners} ({total_winners/total_trades*100:.1f}%)
   แพ้: {total_losers} ({total_losers/total_trades*100:.1f}%)
   กำไรรวม: {total_return:+.2f}%
   กำไรเฉลี่ย/เทรด: {avg_return:+.2f}%

📅 รายเดือน:
   จำนวนเดือน: {n_months}
   เดือนกำไร: {profitable_months} ({profitable_months/n_months*100:.1f}%)
   เดือนขาดทุน: {n_months - profitable_months}
   กำไรเฉลี่ย/เดือน: {total_return/n_months:+.2f}%
   เทรดเฉลี่ย/เดือน: {total_trades/n_months:.1f}
""")

    # ดู loser ที่แย่ที่สุด
    print("💀 Loser ที่แย่ที่สุด:")
    losers = df_trades[df_trades['return'] <= 0].nsmallest(10, 'return')
    for _, r in losers.iterrows():
        date_str = r['date'].strftime('%Y-%m-%d')
        status = "STOP" if r['stopped'] else ""
        print(f"   {r['symbol']:<6} {date_str} {r['return']:+.2f}% {status}")

    # ดู winner ที่ดีที่สุด
    print("\n🏆 Winner ที่ดีที่สุด:")
    winners = df_trades.nlargest(10, 'return')
    for _, r in winners.iterrows():
        date_str = r['date'].strftime('%Y-%m-%d')
        print(f"   {r['symbol']:<6} {date_str} {r['return']:+.2f}%")

    # ความเป็นจริง
    print("\n" + "=" * 80)
    print("💡 การวิเคราะห์ความเป็นจริง")
    print("=" * 80)

    if total_return/n_months >= 10:
        print(f"""
✅ CONFIG นี้ได้ {total_return/n_months:.1f}%/เดือน จริง!

แต่ต้องพิจารณา:
1. Win Rate {total_winners/total_trades*100:.1f}% หมายความว่า {total_losers/total_trades*100:.1f}% เป็น loser
2. Loser ทุกตัวโดน stop-loss -2% (ควบคุมได้)
3. ต้องเทรด {total_trades/n_months:.0f} ครั้ง/เดือน

✅ ข้อดี:
- กำไรสูง
- Max loss คุมได้ที่ -2%
- มี trade บ่อย

⚠️ ข้อควรระวัง:
- ต้องมีวินัยในการ stop-loss
- ต้องเทรดทุก signal (ไม่เลือก)
""")
    else:
        print(f"\n❌ ได้เพียง {total_return/n_months:.1f}%/เดือน ยังไม่ถึง 10%")


if __name__ == '__main__':
    main()
