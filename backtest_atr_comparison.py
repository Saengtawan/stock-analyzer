#!/usr/bin/env python3
"""
ATR Threshold Comparison Backtest

เปรียบเทียบ ATR <= 3% (ปัจจุบัน) vs ATR <= 3.5% (relax)
ดูว่า relax จะเพิ่ม loser หรือไม่

Question: เป็นไปได้ไหมที่หาหุ้นไม่เจอเพราะ criteria เข้มเกินไป?
Answer: ทดสอบโดย relax ATR threshold
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

# HUGE UNIVERSE
STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER',
    'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI',
    'ON', 'SWKS', 'MPWR', 'MRVL', 'SNPS', 'CDNS',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'TEAM', 'SPLK', 'WDAY', 'VEEV', 'HUBS', 'BILL',
    'NFLX', 'DIS', 'CMCSA', 'ROKU', 'SPOT',
    'SNAP', 'PINS', 'RBLX', 'EA', 'TTWO',
    'EBAY', 'ETSY', 'MELI',
    'V', 'MA', 'AXP', 'COIN', 'AFRM', 'SOFI',
    'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC', 'USB', 'PNC', 'TFC', 'SCHW',
    'BRK-B', 'MET', 'PRU', 'TRV', 'PGR',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'CI', 'HUM', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA', 'AMGN',
    'BMY', 'ZTS', 'SYK', 'BSX', 'MDT', 'EW', 'DXCM', 'IDXX',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'DG', 'DLTR', 'BBY',
    'LULU', 'ULTA', 'NKE', 'ORLY', 'AZO',
    'SBUX', 'MCD', 'CMG', 'DPZ', 'YUM',
    'KO', 'PEP', 'MNST',
    'PG', 'CL', 'KMB', 'EL',
    'CAT', 'DE', 'HON', 'GE', 'MMM', 'EMR', 'ETN', 'ITW',
    'RTX', 'LMT', 'NOC', 'BA', 'GD',
    'UPS', 'FDX',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX',
    'DVN', 'FANG', 'HES', 'MRO',
    'NEE', 'DUK', 'SO', 'D', 'AEP',
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'DLR',
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT',
    'F', 'GM', 'RIVN',
    'VZ', 'T', 'TMUS',
    'LIN', 'APD', 'SHW', 'ECL', 'NEM', 'FCX',
    'PATH', 'CFLT', 'GTLB', 'ESTC', 'DASH', 'LYFT', 'TTD',
]


def get_metrics(df, idx):
    """คำนวณ metrics ทั้งหมด ณ วันที่ idx"""
    if idx < 60:
        return None

    close = df['close'].iloc[:idx+1]
    high = df['high'].iloc[:idx+1]
    low = df['low'].iloc[:idx+1]
    volume = df['volume'].iloc[:idx+1]
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    # MA
    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    # Volume
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # Momentum
    mom_3d = ((price / close.iloc[-4]) - 1) * 100
    mom_20d = ((price / close.iloc[-21]) - 1) * 100

    # 52w position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100

    # 20d position
    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    # ATR (Average True Range)
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    # Days above MA20
    ma20_series = close.rolling(20).mean()
    days_above_ma20 = (close.iloc[-10:] > ma20_series.iloc[-10:]).sum()

    return {
        'price': price, 'rsi': rsi, 'above_ma20': above_ma20,
        'vol_ratio': vol_ratio, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
        'pos_52w': pos_52w, 'dist_from_20d_high': dist_from_20d_high,
        'atr_pct': atr_pct, 'days_above_ma20': days_above_ma20,
    }


def passes_base_criteria(m):
    """Base criteria (ทุกอย่างยกเว้น ATR)"""
    if m is None: return False
    if m['above_ma20'] <= 0: return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85: return False
    if m['mom_20d'] < 8 or m['mom_20d'] > 20: return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 5: return False
    if m['rsi'] >= 68: return False
    if m['dist_from_20d_high'] < -5: return False
    if m['vol_ratio'] < 0.9: return False
    if m['days_above_ma20'] < 8: return False
    return True


def passes_atr_3pct(m):
    """v6.3 ปัจจุบัน: ATR <= 3%"""
    if not passes_base_criteria(m): return False
    return m['atr_pct'] <= 3.0


def passes_atr_3_5pct(m):
    """RELAXED: ATR <= 3.5%"""
    if not passes_base_criteria(m): return False
    return m['atr_pct'] <= 3.5


def passes_atr_4pct(m):
    """MORE RELAXED: ATR <= 4%"""
    if not passes_base_criteria(m): return False
    return m['atr_pct'] <= 4.0


def passes_no_atr_filter(m):
    """NO ATR FILTER (just base)"""
    return passes_base_criteria(m)


def backtest(data, check_func, name, per_trade=50000):
    """Run backtest with 14-day hold, 5% target, 6% stop"""
    results = []
    extra_trades = []  # เก็บ trades ที่มีเฉพาะใน relaxed version

    for sym, df in data.items():
        for days_back in range(30, 180, 2):
            idx = len(df) - 1 - days_back
            if idx < 60 or idx + 14 >= len(df):
                continue

            m = get_metrics(df, idx)
            if not check_func(m):
                continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            exit_reason = 'HOLD14'
            exit_price = df.iloc[min(idx + 14, len(df)-1)]['close']

            for i in range(1, min(15, len(df) - idx)):
                if (df.iloc[idx + i]['low'] - entry) / entry <= -0.06:
                    exit_price = entry * 0.94
                    exit_reason = 'STOP'
                    break
                if (df.iloc[idx + i]['high'] - entry) / entry >= 0.05:
                    exit_price = entry * 1.05
                    exit_reason = 'TARGET'
                    break

            ret = ((exit_price - entry) / entry) * 100
            profit = per_trade * (ret / 100)

            results.append({
                'sym': sym, 'date': entry_date, 'ret': ret,
                'profit': profit, 'win': ret > 0, 'exit_reason': exit_reason,
                'atr_pct': m['atr_pct'],
            })

    if not results:
        return None

    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(['sym', 'date'])
    df_res['diff'] = df_res.groupby('sym')['date'].diff().dt.days
    df_res = df_res[(df_res['diff'].isna()) | (df_res['diff'] > 10)]

    n = len(df_res)
    wins = df_res['win'].sum()
    losers = n - wins
    total_profit = df_res['profit'].sum()

    # ATR distribution
    atr_bins = {
        '<=2.5%': len(df_res[df_res['atr_pct'] <= 2.5]),
        '2.5-3.0%': len(df_res[(df_res['atr_pct'] > 2.5) & (df_res['atr_pct'] <= 3.0)]),
        '3.0-3.5%': len(df_res[(df_res['atr_pct'] > 3.0) & (df_res['atr_pct'] <= 3.5)]),
        '3.5-4.0%': len(df_res[(df_res['atr_pct'] > 3.5) & (df_res['atr_pct'] <= 4.0)]),
        '>4.0%': len(df_res[df_res['atr_pct'] > 4.0]),
    }

    # Win rate by ATR
    atr_winrates = {}
    for atr_range, lower, upper in [
        ('<=3.0%', 0, 3.0),
        ('3.0-3.5%', 3.0, 3.5),
        ('3.5-4.0%', 3.5, 4.0),
        ('>4.0%', 4.0, 100),
    ]:
        subset = df_res[(df_res['atr_pct'] > lower) & (df_res['atr_pct'] <= upper)]
        if len(subset) > 0:
            atr_winrates[atr_range] = {
                'count': len(subset),
                'win_rate': subset['win'].sum() / len(subset) * 100,
                'avg_ret': subset['ret'].mean(),
                'losers': len(subset) - subset['win'].sum(),
            }

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'losers': losers,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'total_profit': total_profit,
        'monthly_profit': total_profit / 6,
        'avg_ret': df_res['ret'].mean(),
        'atr_bins': atr_bins,
        'atr_winrates': atr_winrates,
        'df': df_res,
    }


# ========================================
# MAIN
# ========================================
print("="*100)
print("ATR THRESHOLD COMPARISON BACKTEST")
print("Question: Relax ATR จาก 3% → 3.5% จะเพิ่ม loser หรือไม่?")
print("="*100)

print("\nLoading data...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="1y", interval="1d")
        if df is not None and len(df) >= 200:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Test all versions
print("Running backtests...")
versions = [
    (passes_atr_3pct, "v6.3 (ATR <= 3.0%) - CURRENT"),
    (passes_atr_3_5pct, "v6.3 (ATR <= 3.5%) - RELAXED"),
    (passes_atr_4pct, "v6.3 (ATR <= 4.0%) - MORE RELAXED"),
    (passes_no_atr_filter, "v6.3 (NO ATR FILTER) - BASELINE"),
]

results = []
for func, name in versions:
    r = backtest(data, func, name)
    if r:
        results.append(r)

# ========================================
# RESULTS
# ========================================
print("\n" + "="*100)
print("MAIN RESULTS")
print("="*100)

print(f"\n{'Version':<40} {'Trades':>8} {'Wins':>8} {'Losers':>8} {'Win%':>8} {'Avg Ret':>10} {'Monthly P/L':>15}")
print("-"*100)

for r in results:
    print(f"{r['name']:<40} {r['trades']:>8} {r['wins']:>8} {r['losers']:>8} {r['win_rate']:>7.1f}% {r['avg_ret']:>+9.2f}% {r['monthly_profit']:>+14,.0f} บาท")

# Compare 3% vs 3.5%
if len(results) >= 2:
    v3, v35 = results[0], results[1]

    extra_trades = v35['trades'] - v3['trades']
    extra_losers = v35['losers'] - v3['losers']
    extra_wins = v35['wins'] - v3['wins']

    print("\n" + "="*100)
    print("ATR 3% vs 3.5% COMPARISON")
    print("="*100)

    print(f"""
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           ATR <= 3% (Current)         ATR <= 3.5% (Relaxed)              │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Total Trades                  {v3['trades']:<25} {v35['trades']:<25} │
│ Winners                       {v3['wins']:<25} {v35['wins']:<25} │
│ Losers                        {v3['losers']:<25} {v35['losers']:<25} │
│ Win Rate                      {v3['win_rate']:.1f}%{'':<21} {v35['win_rate']:.1f}%{'':<21} │
│ Avg Return                    {v3['avg_ret']:+.2f}%{'':<20} {v35['avg_ret']:+.2f}%{'':<20} │
│ Monthly Profit                {v3['monthly_profit']:>+,.0f} บาท{'':<10} {v35['monthly_profit']:>+,.0f} บาท{'':<10} │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ DIFFERENCE (Relax Effect):                                                                │
│   Extra Trades:               {extra_trades:>+d} trades                                              │
│   Extra Winners:              {extra_wins:>+d}                                                       │
│   Extra Losers:               {extra_losers:>+d}                                                       │
└──────────────────────────────────────────────────────────────────────────────────────────┘
""")

# ========================================
# DETAILED ATR ANALYSIS
# ========================================
print("\n" + "="*100)
print("WIN RATE BY ATR RANGE (from NO ATR FILTER version)")
print("="*100)

if len(results) >= 4:
    no_atr_result = results[3]  # NO ATR FILTER version

    print(f"\n{'ATR Range':<15} {'Count':>8} {'Win Rate':>10} {'Avg Ret':>10} {'Losers':>8} {'Assessment':>30}")
    print("-"*85)

    for atr_range, stats in no_atr_result['atr_winrates'].items():
        if stats['count'] > 0:
            assessment = ""
            if stats['win_rate'] >= 70:
                assessment = "✅ GOOD - Keep"
            elif stats['win_rate'] >= 60:
                assessment = "⚠️ RISKY - Monitor"
            else:
                assessment = "❌ BAD - Filter out"

            print(f"{atr_range:<15} {stats['count']:>8} {stats['win_rate']:>9.1f}% {stats['avg_ret']:>+9.2f}% {stats['losers']:>8} {assessment:>30}")

# ========================================
# ANSWER TO THE QUESTION
# ========================================
print("\n" + "="*100)
print("CONCLUSION")
print("="*100)

if len(results) >= 2:
    v3, v35 = results[0], results[1]

    if extra_losers > 0 and v35['win_rate'] < v3['win_rate']:
        print(f"""
คำตอบ: ❌ ไม่ควร relax ATR จาก 3% → 3.5%

เหตุผล:
1. เพิ่ม Losers: {v3['losers']} → {v35['losers']} (+{extra_losers} losers)
2. Win Rate ลดลง: {v3['win_rate']:.1f}% → {v35['win_rate']:.1f}%
3. หุ้นที่มี ATR 3-3.5% มีแนวโน้มเป็น loser มากกว่า

สรุป: ATR <= 3% เป็น filter ที่ดี ช่วยกรอง "หุ้นที่ผันผวนสูง = เสี่ยง crash"
""")
    elif extra_losers == 0 or extra_losers <= extra_wins:
        print(f"""
คำตอบ: ✅ อาจ relax ATR จาก 3% → 3.5% ได้

เหตุผล:
1. Extra trades: +{extra_trades} (เพิ่มโอกาส)
2. Extra losers: +{extra_losers} (ยอมรับได้)
3. Extra winners: +{extra_wins}
4. Win Rate ยังคงดี: {v35['win_rate']:.1f}%

แต่ต้องระวัง: หุ้น ATR 3-3.5% อาจผันผวนกว่า
""")
    else:
        print(f"""
คำตอบ: ⚠️ ไม่แนะนำ - Risk/Reward ไม่คุ้ม

Extra trades: +{extra_trades}
Extra losers: +{extra_losers} (เพิ่มมากเกินไป)
Extra winners: +{extra_wins}

Loser เพิ่มมากกว่า Winner = ไม่คุ้มที่จะ relax
""")

# ========================================
# ADDITIONAL: หุ้นไม่เจอ = criteria เข้มไป?
# ========================================
print("\n" + "="*100)
print("ADDITIONAL ANALYSIS: หุ้นไม่เจอเพราะ criteria เข้มเกินไป?")
print("="*100)

if len(results) >= 4:
    current = results[0]
    no_filter = results[3]

    missed = no_filter['trades'] - current['trades']
    missed_losers = no_filter['losers'] - current['losers']
    missed_winners = no_filter['wins'] - current['wins']

    print(f"""
การวิเคราะห์:
- ATR Filter ปัจจุบัน (<=3%): {current['trades']} trades
- ถ้าไม่มี ATR Filter:       {no_filter['trades']} trades
- หุ้นที่ถูก filter ออก:     {missed} ตัว

ใน {missed} ตัวที่ถูก filter ออก:
- Winners ที่พลาด:  {missed_winners}
- Losers ที่หลีกเลี่ยง: {missed_losers}

สรุป: ATR filter ช่วยหลีกเลี่ยง {missed_losers} losers
      แต่ก็ทำให้พลาด {missed_winners} winners ด้วย

Trade-off: {"✅ คุ้มค่า (หลีกเลี่ยง loser > พลาด winner)" if missed_losers >= missed_winners else "⚠️ อาจพิจารณา relax"}
""")

print("\n" + "="*100)
print("BACKTEST COMPLETE")
print("="*100)
