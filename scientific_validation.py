#!/usr/bin/env python3
"""
SCIENTIFIC VALIDATION - ทดสอบซ้ำๆ หลายรอบ
นักวิทยาศาสตร์ต้องทดลองซ้ำ ผลลัพธ์ต้องดีทุกรอบ!

การทดสอบ:
1. แบ่งช่วงเวลาเป็นหลายช่วง (time periods)
2. ทดสอบกับหุ้นชุดต่างๆ (different stock sets)
3. ทดสอบหลายครั้ง (multiple runs)
4. วิเคราะห์ความคงที่ของผลลัพธ์ (consistency)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
import random
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


def backtest_config(stock_data, config, start_idx=55, end_idx=None):
    """Backtest a config on given data and index range"""
    trades = []

    for sym, df in stock_data.items():
        closes = df['Close'].values.flatten()
        volumes = df['Volume'].values.flatten()
        highs = df['High'].values.flatten()
        lows = df['Low'].values.flatten()
        dates = df.index

        n = min(len(closes), len(volumes), len(highs), len(lows), len(dates))
        hold_days = config['hold_days']
        actual_end = end_idx if end_idx else n - hold_days - 1

        for i in range(start_idx, min(actual_end, n - hold_days - 1)):
            price = float(closes[i])

            ma20 = float(np.mean(closes[i-19:i+1]))
            ma50 = float(np.mean(closes[i-49:i+1]))
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100

            rsi = calculate_rsi(closes[max(0,i-29):i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            atr_pct = calculate_atr_pct(closes, highs, lows, i, period=14)

            vol_avg = float(np.mean(volumes[i-19:i]))
            vol_surge = volumes[i] / vol_avg if vol_avg > 0 else 1.0

            # Apply gates
            if accum <= config['accum_min']:
                continue
            if rsi >= config['rsi_max']:
                continue
            if above_ma20 <= config['ma20_min']:
                continue
            if above_ma50 <= config['ma50_min']:
                continue
            if atr_pct > config['atr_max']:
                continue

            # Trade with stop-loss
            entry_price = price
            stop_price = entry_price * (1 + config['stop_pct'] / 100)
            stopped = False

            for j in range(1, hold_days + 1):
                if i + j >= n:
                    break
                day_price = float(closes[i + j])
                if day_price <= stop_price:
                    pct_return = config['stop_pct']
                    stopped = True
                    break
            else:
                exit_price = float(closes[i + hold_days])
                pct_return = ((exit_price - entry_price) / entry_price) * 100

            trades.append({
                'symbol': sym,
                'date': dates[i],
                'return': pct_return,
                'stopped': stopped
            })

    if not trades:
        return None

    df_trades = pd.DataFrame(trades)
    df_trades['week'] = df_trades['date'].dt.isocalendar().week
    df_trades['year'] = df_trades['date'].dt.year
    df_trades = df_trades.drop_duplicates(subset=['symbol', 'year', 'week'])

    return df_trades


def main():
    print("=" * 80)
    print("SCIENTIFIC VALIDATION - ทดสอบซ้ำๆ แบบนักวิทยาศาสตร์")
    print("=" * 80)

    # v11.0 Config
    CONFIG = {
        'name': 'v11.0 HIGH PROFIT',
        'accum_min': 1.2,
        'rsi_max': 58,
        'ma20_min': 0,
        'ma50_min': 0,
        'atr_max': 3.0,
        'hold_days': 5,
        'stop_pct': -2.0
    }

    print(f"\nConfig ที่ทดสอบ: {CONFIG['name']}")

    # ชุดหุ้นทั้งหมด
    ALL_SYMBOLS = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT', 'LRCX',
        'CRM', 'ADBE', 'ORCL', 'NOW', 'SNOW', 'DDOG', 'NET',
        # Finance
        'JPM', 'BAC', 'GS', 'MS', 'WFC', 'V', 'MA', 'AXP',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN',
        # Consumer
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE',
        # Industrial
        'CAT', 'DE', 'HON', 'GE', 'BA', 'UNP',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB',
        # Other
        'NFLX', 'DIS', 'T', 'VZ', 'UBER', 'ABNB'
    ]

    print(f"ดาวน์โหลด {len(ALL_SYMBOLS)} หุ้น...")

    # Download all data
    all_data = {}
    for sym in ALL_SYMBOLS:
        try:
            df = yf.download(sym, period='1y', progress=False)
            if df.empty or len(df) < 150:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            all_data[sym] = df
        except:
            pass

    print(f"ดาวน์โหลดได้: {len(all_data)} หุ้น")

    # ========== TEST 1: Full Year Test ==========
    print("\n" + "=" * 80)
    print("TEST 1: ทดสอบทั้งปี (Full Year)")
    print("=" * 80)

    df_full = backtest_config(all_data, CONFIG)
    if df_full is not None:
        n = len(df_full)
        winners = len(df_full[df_full['return'] > 0])
        total_ret = df_full['return'].sum()
        print(f"   Trades: {n}")
        print(f"   Win Rate: {winners/n*100:.1f}%")
        print(f"   Total Return: {total_ret:+.2f}%")
        print(f"   Monthly Avg: {total_ret/12:+.2f}%")

    # ========== TEST 2: Quarter by Quarter ==========
    print("\n" + "=" * 80)
    print("TEST 2: ทดสอบรายไตรมาส (Quarter by Quarter)")
    print("=" * 80)

    # Get date range from data
    sample_df = list(all_data.values())[0]
    data_length = len(sample_df)

    quarters = [
        ('Q1', 55, data_length // 4),
        ('Q2', data_length // 4, data_length // 2),
        ('Q3', data_length // 2, 3 * data_length // 4),
        ('Q4', 3 * data_length // 4, data_length - 6)
    ]

    quarter_results = []
    for q_name, start, end in quarters:
        df_q = backtest_config(all_data, CONFIG, start_idx=start, end_idx=end)
        if df_q is not None and len(df_q) > 0:
            n = len(df_q)
            winners = len(df_q[df_q['return'] > 0])
            total_ret = df_q['return'].sum()
            monthly = total_ret / 3  # 3 months per quarter

            status = "✅" if monthly > 0 else "❌"
            print(f"   {status} {q_name}: {n} trades, {winners/n*100:.0f}% WR, {monthly:+.2f}%/month")

            quarter_results.append({
                'quarter': q_name,
                'trades': n,
                'win_rate': winners/n*100,
                'monthly_return': monthly,
                'profitable': monthly > 0
            })

    profitable_quarters = sum(1 for q in quarter_results if q['profitable'])
    print(f"\n   Profitable Quarters: {profitable_quarters}/{len(quarter_results)}")

    # ========== TEST 3: Random Stock Subsets ==========
    print("\n" + "=" * 80)
    print("TEST 3: ทดสอบกับหุ้นชุดสุ่ม (Random Subsets)")
    print("=" * 80)

    symbols_list = list(all_data.keys())
    subset_results = []

    for i in range(5):
        # Random 30 stocks
        subset = random.sample(symbols_list, min(30, len(symbols_list)))
        subset_data = {s: all_data[s] for s in subset}

        df_subset = backtest_config(subset_data, CONFIG)
        if df_subset is not None and len(df_subset) > 0:
            n = len(df_subset)
            winners = len(df_subset[df_subset['return'] > 0])
            total_ret = df_subset['return'].sum()

            status = "✅" if total_ret > 0 else "❌"
            print(f"   {status} Run {i+1}: {n} trades, {winners/n*100:.0f}% WR, Total: {total_ret:+.2f}%")

            subset_results.append({
                'run': i+1,
                'trades': n,
                'total_return': total_ret,
                'profitable': total_ret > 0
            })

    profitable_runs = sum(1 for r in subset_results if r['profitable'])
    print(f"\n   Profitable Runs: {profitable_runs}/{len(subset_results)}")

    # ========== TEST 4: Sector Analysis ==========
    print("\n" + "=" * 80)
    print("TEST 4: ทดสอบรายเซกเตอร์ (Sector Analysis)")
    print("=" * 80)

    sectors = {
        'Tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD'],
        'Finance': ['JPM', 'BAC', 'GS', 'MS', 'V', 'MA'],
        'Healthcare': ['JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY'],
        'Consumer': ['HD', 'LOW', 'COST', 'WMT', 'MCD', 'NKE'],
        'Industrial': ['CAT', 'DE', 'HON', 'GE', 'BA'],
    }

    sector_results = []
    for sector_name, sector_symbols in sectors.items():
        sector_data = {s: all_data[s] for s in sector_symbols if s in all_data}
        if not sector_data:
            continue

        df_sector = backtest_config(sector_data, CONFIG)
        if df_sector is not None and len(df_sector) > 0:
            n = len(df_sector)
            winners = len(df_sector[df_sector['return'] > 0])
            total_ret = df_sector['return'].sum()

            status = "✅" if total_ret > 0 else "❌"
            print(f"   {status} {sector_name}: {n} trades, {winners/n*100:.0f}% WR, {total_ret:+.2f}%")

            sector_results.append({
                'sector': sector_name,
                'total_return': total_ret,
                'profitable': total_ret > 0
            })

    profitable_sectors = sum(1 for s in sector_results if s['profitable'])
    print(f"\n   Profitable Sectors: {profitable_sectors}/{len(sector_results)}")

    # ========== FINAL VERDICT ==========
    print("\n" + "=" * 80)
    print("🔬 SCIENTIFIC VERDICT")
    print("=" * 80)

    all_tests = [
        ('Full Year', df_full['return'].sum() > 0 if df_full is not None else False),
        ('Quarters', profitable_quarters >= 3),
        ('Random Subsets', profitable_runs >= 4),
        ('Sectors', profitable_sectors >= 4)
    ]

    passed = sum(1 for _, result in all_tests if result)

    print(f"\n{'Test':<20} {'Result':<10}")
    print("-" * 30)
    for test_name, result in all_tests:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<20} {status}")

    print(f"\nPassed: {passed}/{len(all_tests)}")

    if passed >= 3:
        print("""
✅ FORMULA VALIDATED!
   สูตร v11.0 ผ่านการทดสอบ {}/{}
   - ทำกำไรในเกือบทุกช่วงเวลา
   - ทำกำไรในเกือบทุกเซกเตอร์
   - ทำกำไรเมื่อทดสอบกับหุ้นชุดต่างๆ

⚠️ ข้อควรจำ:
   - MUST use -2% stop-loss
   - Hold 5 days
   - Trade ALL signals (don't cherry-pick)
""".format(passed, len(all_tests)))
    else:
        print("""
❌ FORMULA NEEDS MORE WORK
   ผ่านเพียง {}/{} tests
   ต้องปรับปรุงต่อไป...
""".format(passed, len(all_tests)))


if __name__ == '__main__':
    main()
