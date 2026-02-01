#!/usr/bin/env python3
"""
ลองเพิ่มจำนวนหุ้น + หาแนวทางใหม่

แนวคิด:
1. ใช้หุ้นมากขึ้น = มีโอกาสมากขึ้น
2. ลอง momentum ที่แตกต่าง
3. ดู time of entry (ช่วงเวลาที่ดีที่สุด)
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
    print("TRY MORE STOCKS - หาทาง 10%+")
    print("=" * 80)

    # ขยายจำนวนหุ้น
    symbols = [
        # Tech - Mega
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # Tech - Semis
        'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC',
        # Tech - Software
        'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG', 'NET', 'ZS', 'PANW', 'CRWD',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'V', 'MA', 'AXP', 'COF',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'CVS',
        # Consumer
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'LULU', 'DG',
        # Industrial
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT', 'MMM',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY',
        # Telecom/Media
        'T', 'VZ', 'TMUS', 'NFLX', 'DIS', 'CMCSA',
        # Growth
        'UBER', 'ABNB', 'PYPL', 'SHOP', 'COIN', 'PLTR', 'RBLX', 'ROKU'
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

    # Best config + stop-loss
    CONFIG = {
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    # Collect all trades
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
                if day_low <= stop_price:
                    pct_return = CONFIG['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': sym,
                'date': dates[i],
                'return': pct_return,
                'stopped': stopped,
                'rsi': rsi,
                'accum': accum,
                'atr_pct': atr_pct
            })

    df_trades = pd.DataFrame(all_trades)

    # Deduplicate
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    # Monthly analysis
    df_trades['month'] = df_trades['date'].dt.to_period('M')

    print("\n" + "=" * 80)
    print("MONTHLY BREAKDOWN")
    print("=" * 80)

    monthly_stats = []
    for month, group in df_trades.groupby('month'):
        n_trades = len(group)
        n_winners = len(group[group['return'] > 0])
        total_ret = group['return'].sum()

        status = "✅" if total_ret > 10 else ("⭐" if total_ret > 0 else "❌")
        print(f"{status} {month}: {n_trades:>3} trades, {n_winners:>3}W, Total: {total_ret:>+7.2f}%")

        monthly_stats.append({
            'month': str(month),
            'trades': n_trades,
            'total_return': total_ret
        })

    df_monthly = pd.DataFrame(monthly_stats)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_trades = len(df_trades)
    total_winners = len(df_trades[df_trades['return'] > 0])
    total_return = df_trades['return'].sum()
    n_months = len(df_monthly)
    monthly_avg = total_return / n_months
    trades_per_month = total_trades / n_months

    good_months = len(df_monthly[df_monthly['total_return'] > 10])
    profitable_months = len(df_monthly[df_monthly['total_return'] > 0])

    print(f"""
📊 ผลรวม:
   หุ้นที่ใช้: {len(stock_data)}
   เทรดทั้งหมด: {total_trades}
   ชนะ: {total_winners} ({total_winners/total_trades*100:.1f}%)
   กำไรรวม: {total_return:+.2f}%

📅 รายเดือน:
   จำนวนเดือน: {n_months}
   เดือนที่ได้ 10%+: {good_months}/{n_months} ({good_months/n_months*100:.0f}%)
   เดือนกำไร: {profitable_months}/{n_months} ({profitable_months/n_months*100:.0f}%)

📈 ค่าเฉลี่ย:
   กำไร/เดือน: {monthly_avg:+.2f}%
   เทรด/เดือน: {trades_per_month:.1f}
""")

    # Target check
    print("=" * 80)
    print("TARGET CHECK")
    print("=" * 80)

    if monthly_avg >= 10:
        print(f"\n✅ TARGET MET! {monthly_avg:.2f}%/month >= 10%")
    elif monthly_avg >= 8:
        print(f"\n⭐ CLOSE! {monthly_avg:.2f}%/month (target: 10%)")
        print(f"   ขาดอีก {10 - monthly_avg:.2f}%")

        # หาทางเพิ่ม
        print(f"\n💡 วิธีเพิ่ม:")
        print(f"   1. ใช้หุ้นมากขึ้น (+20-30 หุ้น)")
        print(f"   2. ปรับ stop-loss เป็น -1.5% (aggressive)")
        print(f"   3. เพิ่ม quality filter (trade น้อยลงแต่ดีขึ้น)")
    else:
        print(f"\n❌ {monthly_avg:.2f}%/month < 10%")

    # Analyze what makes big winners
    print("\n" + "=" * 80)
    print("BIG WINNERS ANALYSIS")
    print("=" * 80)

    big_winners = df_trades[df_trades['return'] > 5]
    if len(big_winners) > 0:
        print(f"\nBig Winners (>5%): {len(big_winners)}")
        print(f"  Average RSI: {big_winners['rsi'].mean():.1f}")
        print(f"  Average Accum: {big_winners['accum'].mean():.2f}")
        print(f"  Average ATR: {big_winners['atr_pct'].mean():.2f}%")

    losers = df_trades[df_trades['return'] <= 0]
    if len(losers) > 0:
        print(f"\nLosers: {len(losers)}")
        print(f"  Average RSI: {losers['rsi'].mean():.1f}")
        print(f"  Average Accum: {losers['accum'].mean():.2f}")
        print(f"  Average ATR: {losers['atr_pct'].mean():.2f}%")


if __name__ == '__main__':
    main()
