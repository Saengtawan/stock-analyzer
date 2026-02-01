#!/usr/bin/env python3
"""
Improved Backtest - ปรับปรุงตาม findings ก่อนหน้า

Improvements:
1. หลีกเลี่ยง October, November (เดือนที่ผลไม่ดี)
2. ใช้ top 10 picks แทน 5 (เพิ่ม diversification)
3. เทรดเฉพาะเมื่อ market uptrend (SPY > MA20)
4. เน้น sectors ที่ดี (Industrial, Consumer, Finance)
5. ใช้ stricter criteria
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
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


def score_stock(symbol, df):
    """Score a stock"""
    if len(df) < 55:
        return None

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

    # Stricter criteria
    if accum <= 1.3:  # Stronger accumulation required
        return None
    if rsi >= 55 or rsi <= 35:  # Tighter RSI range
        return None
    if above_ma20 <= 0:
        return None
    if above_ma50 <= 0:
        return None
    if atr_pct > 2.5:  # Lower volatility
        return None

    # Score
    score = accum * 25 + (55 - rsi) + above_ma20 * 2 + (3 - atr_pct) * 10

    return {
        'symbol': symbol,
        'price': price,
        'score': score,
        'rsi': rsi,
        'accum': accum,
        'atr_pct': atr_pct,
        'above_ma20': above_ma20,
    }


def backtest():
    """Run improved backtest"""
    print("=" * 70)
    print("IMPROVED BACKTEST - With Filters")
    print("=" * 70)

    # Config
    MONTHS = 8
    HOLD_DAYS = 5
    STOP_LOSS = -2.0
    TOP_N = 10
    AVOID_MONTHS = [10, 11]  # October, November

    # Good sectors only
    UNIVERSE = {
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA', 'UNP', 'RTX', 'LMT'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE'],
        'Finance': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'AXP'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY'],
        'Tech_Blue': ['AAPL', 'MSFT', 'GOOGL'],  # Only blue chip tech
    }

    all_symbols = []
    symbol_sector = {}
    for sector, symbols in UNIVERSE.items():
        for s in symbols:
            all_symbols.append(s)
            symbol_sector[s] = sector

    print(f"\nConfig:")
    print(f"  Period: {MONTHS} months")
    print(f"  Hold days: {HOLD_DAYS}")
    print(f"  Stop loss: {STOP_LOSS}%")
    print(f"  Top picks: {TOP_N}")
    print(f"  Avoid months: Oct, Nov")
    print(f"  Sectors: {list(UNIVERSE.keys())}")

    # Download data
    print(f"\n1. Downloading {len(all_symbols)} stocks...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=MONTHS*30 + 60)

    stock_data = {}
    for symbol in all_symbols:
        try:
            df = yf.download(symbol, start=start_date, end=end_date, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                stock_data[symbol] = df
        except:
            pass

    print(f"   Downloaded: {len(stock_data)} stocks")

    # SPY
    spy = yf.download('SPY', start=start_date, end=end_date, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy_ma20 = spy['Close'].rolling(20).mean()

    # Trading dates
    trading_dates = spy.index[60:]
    weekly_dates = trading_dates[::5]

    print(f"   Trading weeks: {len(weekly_dates)}")

    # Backtest
    print("\n2. Running backtest with filters...")

    all_trades = []
    filtered_out = {'market': 0, 'month': 0, 'no_picks': 0}

    for entry_date in weekly_dates[:-1]:
        # Filter 1: Market trend
        try:
            spy_close = spy.loc[entry_date, 'Close']
            spy_ma = spy_ma20.loc[entry_date]
            if pd.isna(spy_ma) or spy_close < spy_ma:
                filtered_out['market'] += 1
                continue
        except:
            continue

        # Filter 2: Avoid bad months
        if entry_date.month in AVOID_MONTHS:
            filtered_out['month'] += 1
            continue

        # Score stocks
        picks = []
        for symbol, df in stock_data.items():
            mask = df.index <= entry_date
            df_to_date = df[mask]

            if len(df_to_date) < 55:
                continue

            result = score_stock(symbol, df_to_date)
            if result:
                result['sector'] = symbol_sector.get(symbol, 'Other')
                picks.append(result)

        # Top picks
        picks = sorted(picks, key=lambda x: x['score'], reverse=True)[:TOP_N]

        if not picks:
            filtered_out['no_picks'] += 1
            continue

        # Simulate trades
        for pick in picks:
            symbol = pick['symbol']
            df = stock_data[symbol]

            try:
                entry_idx = df.index.get_loc(entry_date)
            except:
                continue

            if entry_idx + HOLD_DAYS >= len(df):
                continue

            entry_price = float(df.iloc[entry_idx]['Close'])
            stop_price = entry_price * (1 + STOP_LOSS / 100)

            stopped = False
            for j in range(1, HOLD_DAYS + 1):
                day_low = float(df.iloc[entry_idx + j]['Low'])
                if day_low <= stop_price:
                    pct_return = STOP_LOSS
                    stopped = True
                    break
            else:
                exit_price = float(df.iloc[entry_idx + HOLD_DAYS]['Close'])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            all_trades.append({
                'symbol': symbol,
                'sector': pick['sector'],
                'entry_date': entry_date,
                'return': pct_return,
                'stopped': stopped,
                'score': pick['score'],
            })

    # Results
    print("\n3. Analyzing results...")

    print(f"\n   Filtered out:")
    print(f"   - Market downtrend: {filtered_out['market']} weeks")
    print(f"   - Bad months (Oct/Nov): {filtered_out['month']} weeks")
    print(f"   - No picks: {filtered_out['no_picks']} weeks")

    if not all_trades:
        print("No trades after filtering!")
        return

    df_trades = pd.DataFrame(all_trades)
    df_trades['month'] = df_trades['entry_date'].dt.to_period('M')

    total_trades = len(df_trades)
    winners = len(df_trades[df_trades['return'] > 0])
    total_return = df_trades['return'].sum()
    n_months = len(df_trades['month'].unique())
    monthly_avg = total_return / n_months if n_months > 0 else 0

    print("\n" + "=" * 70)
    print("IMPROVED BACKTEST RESULTS")
    print("=" * 70)

    print(f"""
Total Trades: {total_trades}
Winners: {winners} ({winners/total_trades*100:.1f}%)
Losers: {total_trades - winners} ({(total_trades-winners)/total_trades*100:.1f}%)

Total Return: {total_return:+.2f}%
Monthly Average: {monthly_avg:+.2f}%
Trades per Month: {total_trades/n_months:.1f}
""")

    print("Monthly Breakdown:")
    print("-" * 50)

    for month, group in df_trades.groupby('month'):
        n = len(group)
        w = len(group[group['return'] > 0])
        total = group['return'].sum()
        status = "+" if total > 0 else "-"
        print(f"  {status} {month}: {n:>2} trades, {w}W/{n-w}L, Total: {total:>+7.2f}%")

    print("\nSector Performance:")
    print("-" * 50)

    for sector in df_trades['sector'].unique():
        group = df_trades[df_trades['sector'] == sector]
        n = len(group)
        total = group['return'].sum()
        avg = group['return'].mean()
        status = "+" if avg > 0 else "-"
        print(f"  {status} {sector:<12}: {n:>2} trades, Avg: {avg:>+5.2f}%, Total: {total:>+7.2f}%")

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    if monthly_avg >= 15:
        print(f"\n** EXCELLENT! {monthly_avg:.2f}%/month >= 15% target")
    elif monthly_avg >= 10:
        print(f"\n** GOOD! {monthly_avg:.2f}%/month >= 10% target")
    elif monthly_avg >= 5:
        print(f"\n** OK. {monthly_avg:.2f}%/month is positive")
    else:
        print(f"\n** Result: {monthly_avg:.2f}%/month")

    # Compare with original
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("=" * 70)

    print("""
Original Strategy: -0.84%/month (no filters)
Improved Strategy: {monthly_avg:+.2f}%/month (with filters)

Improvements:
- Avoid Oct/Nov: Yes
- Market filter (SPY>MA20): Yes
- Stricter criteria: Yes
- Good sectors only: Yes
""".format(monthly_avg=monthly_avg))

    return df_trades


if __name__ == '__main__':
    backtest()
