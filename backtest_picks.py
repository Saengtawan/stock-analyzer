#!/usr/bin/env python3
"""
Backtest Stock Picks - ทดสอบว่า picks จะได้กำไร 10-15% จริงไหม

ทดสอบย้อนหลัง 6 เดือน:
1. จำลองการเลือกหุ้นด้วยเกณฑ์เดียวกับระบบ
2. ซื้อ top 5 picks ทุกสัปดาห์
3. ถือ 5 วัน แล้วขาย
4. ใช้ stop-loss -2%
5. วัดผลว่าได้กี่ % ต่อเดือน
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    print("Please install yfinance: pip install yfinance")
    exit(1)


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


def calculate_atr_pct(closes, highs, lows, period=14):
    if len(closes) < period + 1:
        return 5.0
    tr = []
    for i in range(-period, 0):
        tr.append(max(
            float(highs[i]) - float(lows[i]),
            abs(float(highs[i]) - float(closes[i-1])),
            abs(float(lows[i]) - float(closes[i-1]))
        ))
    atr = np.mean(tr)
    price = float(closes[-1])
    return (atr / price) * 100 if price > 0 else 5.0


def score_stock(symbol, df, spy_trend_up):
    """Score a stock based on our criteria"""
    if len(df) < 55:
        return None, "Insufficient data"

    closes = df['Close'].values.flatten()
    volumes = df['Volume'].values.flatten()
    highs = df['High'].values.flatten()
    lows = df['Low'].values.flatten()

    price = float(closes[-1])
    ma20 = float(np.mean(closes[-20:]))
    ma50 = float(np.mean(closes[-50:]))

    above_ma20 = ((price - ma20) / ma20) * 100
    above_ma50 = ((price - ma50) / ma50) * 100
    rsi = calculate_rsi(closes)
    accum = calculate_accumulation(closes, volumes)
    atr_pct = calculate_atr_pct(closes, highs, lows)

    # Check criteria
    if not spy_trend_up:
        return None, "Market not bullish"
    if accum <= 1.2:
        return None, f"Accum {accum:.2f} <= 1.2"
    if rsi >= 58:
        return None, f"RSI {rsi:.0f} >= 58"
    if rsi <= 30:
        return None, f"RSI {rsi:.0f} <= 30"
    if above_ma20 <= 0:
        return None, "Below MA20"
    if above_ma50 <= 0:
        return None, "Below MA50"
    if atr_pct > 3.0:
        return None, f"ATR {atr_pct:.2f}% > 3%"

    # Calculate score
    score = accum * 20 + (60 - rsi) + above_ma20 * 2

    return {
        'symbol': symbol,
        'price': price,
        'score': score,
        'rsi': rsi,
        'accum': accum,
        'atr_pct': atr_pct,
        'above_ma20': above_ma20,
    }, None


def backtest(months=6, hold_days=5, stop_loss=-2.0, top_n=5):
    """Run backtest"""
    print("=" * 70)
    print("BACKTEST - STOCK PICKER STRATEGY")
    print("=" * 70)
    print(f"Period: {months} months")
    print(f"Hold days: {hold_days}")
    print(f"Stop loss: {stop_loss}%")
    print(f"Top picks per week: {top_n}")

    # Universe
    UNIVERSE = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT',
        'CRM', 'ADBE', 'NFLX', 'PYPL',
        'JPM', 'BAC', 'GS', 'V', 'MA',
        'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY',
        'HD', 'LOW', 'COST', 'WMT', 'MCD', 'SBUX', 'NKE',
        'CAT', 'HON', 'GE', 'BA', 'UNP',
        'XOM', 'CVX',
    ]

    # Download data
    print(f"\n1. Downloading {len(UNIVERSE)} stocks for {months} months...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=months*30 + 60)  # Extra for warmup

    stock_data = {}
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                stock_data[symbol] = df
        except:
            pass

    print(f"   Downloaded: {len(stock_data)} stocks")

    # Download SPY for market trend
    spy = yf.download('SPY', start=start_date, end=end_date, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_ma20 = spy['Close'].rolling(20).mean()

    # Get trading dates
    trading_dates = spy.index[60:]  # Skip warmup
    weekly_dates = trading_dates[::5]  # Every 5 trading days

    print(f"   Trading weeks: {len(weekly_dates)}")

    # Run backtest
    print("\n2. Running backtest...")

    all_trades = []

    for i, entry_date in enumerate(weekly_dates[:-1]):  # Skip last week
        # Check market trend
        try:
            spy_close = spy.loc[entry_date, 'Close']
            spy_ma = spy_ma20.loc[entry_date]
            spy_trend_up = spy_close > spy_ma
        except:
            continue

        # Score all stocks
        picks = []
        for symbol, df in stock_data.items():
            # Get data up to entry date
            mask = df.index <= entry_date
            df_to_date = df[mask]

            if len(df_to_date) < 55:
                continue

            result, reason = score_stock(symbol, df_to_date, spy_trend_up)
            if result:
                picks.append(result)

        # Get top N picks
        picks = sorted(picks, key=lambda x: x['score'], reverse=True)[:top_n]

        if not picks:
            continue

        # Simulate trades
        for pick in picks:
            symbol = pick['symbol']
            df = stock_data[symbol]

            # Find entry and exit dates
            try:
                entry_idx = df.index.get_loc(entry_date)
            except:
                continue

            if entry_idx + hold_days >= len(df):
                continue

            entry_price = float(df.iloc[entry_idx]['Close'])
            stop_price = entry_price * (1 + stop_loss / 100)

            # Check each day for stop loss or exit
            stopped = False
            for j in range(1, hold_days + 1):
                day_low = float(df.iloc[entry_idx + j]['Low'])
                if day_low <= stop_price:
                    pct_return = stop_loss
                    stopped = True
                    break
            else:
                exit_price = float(df.iloc[entry_idx + hold_days]['Close'])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'return': pct_return,
                'stopped': stopped,
                'score': pick['score'],
            })

    # Analyze results
    print("\n3. Analyzing results...")

    if not all_trades:
        print("No trades found!")
        return

    df_trades = pd.DataFrame(all_trades)
    df_trades['month'] = df_trades['entry_date'].dt.to_period('M')

    total_trades = len(df_trades)
    winners = len(df_trades[df_trades['return'] > 0])
    total_return = df_trades['return'].sum()
    n_months = len(df_trades['month'].unique())
    monthly_avg = total_return / n_months if n_months > 0 else 0

    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    print(f"""
Total Trades: {total_trades}
Winners: {winners} ({winners/total_trades*100:.1f}%)
Losers: {total_trades - winners} ({(total_trades-winners)/total_trades*100:.1f}%)

Total Return: {total_return:+.2f}%
Monthly Average: {monthly_avg:+.2f}%
Trades per Month: {total_trades/n_months:.1f}
""")

    # Monthly breakdown
    print("Monthly Breakdown:")
    print("-" * 50)

    monthly_results = []
    for month, group in df_trades.groupby('month'):
        n = len(group)
        w = len(group[group['return'] > 0])
        total = group['return'].sum()
        monthly_results.append({
            'month': month,
            'trades': n,
            'winners': w,
            'total': total,
        })

        status = "+" if total > 0 else "-"
        print(f"  {status} {month}: {n:>2} trades, {w}W/{n-w}L, Total: {total:>+7.2f}%")

    # Summary
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    if monthly_avg >= 15:
        print(f"\n** EXCELLENT! {monthly_avg:.2f}%/month >= 15% target")
    elif monthly_avg >= 10:
        print(f"\n** GOOD! {monthly_avg:.2f}%/month >= 10% target")
    elif monthly_avg >= 5:
        print(f"\n** OK. {monthly_avg:.2f}%/month is positive but below 10%")
    else:
        print(f"\n** NEEDS IMPROVEMENT. {monthly_avg:.2f}%/month")

    # Best and worst months
    if monthly_results:
        best = max(monthly_results, key=lambda x: x['total'])
        worst = min(monthly_results, key=lambda x: x['total'])
        print(f"\nBest month: {best['month']} ({best['total']:+.2f}%)")
        print(f"Worst month: {worst['month']} ({worst['total']:+.2f}%)")

    # Top performing stocks
    print("\nTop Performing Stocks:")
    stock_perf = df_trades.groupby('symbol')['return'].agg(['sum', 'count', 'mean'])
    stock_perf = stock_perf.sort_values('sum', ascending=False)
    for symbol, row in stock_perf.head(5).iterrows():
        print(f"  {symbol}: {row['sum']:+.2f}% ({row['count']:.0f} trades, avg {row['mean']:+.2f}%)")

    return df_trades


if __name__ == '__main__':
    backtest(months=6)
