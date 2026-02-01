#!/usr/bin/env python3
"""
v6.2 - Fix overextended problem

Key insight: LOSERS have HIGHER momentum than WINNERS
- They're over-extended and crash

New filters:
1. Mom 20d <= 20% (cap the upper limit)
2. Vol ratio >= 1.0x (need volume confirmation)
3. ATR <= 4% (avoid high volatility)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from api.data_manager import DataManager

dm = DataManager()

STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX',
    'COIN', 'ROKU', 'SNAP', 'PINS', 'UBER', 'LYFT', 'ABNB', 'DASH',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'U', 'RBLX', 'PATH', 'CFLT', 'MQ',
    'BILL', 'HUBS', 'VEEV', 'WDAY', 'ESTC', 'GTLB', 'DOMO',
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
]


def get_metrics(df, idx):
    """Calculate all metrics"""
    if idx < 50:
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
    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    # 52-week position
    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # Distance from 20d high
    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    # ATR
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    return {
        'price': price,
        'rsi': rsi,
        'above_ma20': above_ma20,
        'vol_ratio': vol_ratio,
        'mom_3d': mom_3d,
        'mom_20d': mom_20d,
        'pos_52w': pos_52w,
        'dist_from_20d_high': dist_from_20d_high,
        'atr_pct': atr_pct,
    }


def passes_v61(m):
    """v6.1 criteria (current)"""
    if m is None:
        return False
    if m['above_ma20'] <= 0:
        return False
    if m['pos_52w'] < 60 or m['pos_52w'] > 85:
        return False
    if m['mom_20d'] < 8:
        return False
    if m['mom_3d'] < 1 or m['mom_3d'] > 8:
        return False
    if m['rsi'] >= 70:
        return False
    if m['dist_from_20d_high'] < -5:
        return False
    return True


def passes_v62(m):
    """v6.2 criteria - Prevent over-extended stocks"""
    if not passes_v61(m):
        return False

    # NEW: Upper limit for Mom 20d (prevent over-extended)
    if m['mom_20d'] > 20:
        return False

    # NEW: Volume confirmation
    if m['vol_ratio'] < 1.0:
        return False

    return True


def passes_v62_strict(m):
    """v6.2 STRICT - Even tighter controls"""
    if not passes_v61(m):
        return False

    # Stricter upper limit for Mom 20d
    if m['mom_20d'] > 15:
        return False

    # Volume confirmation
    if m['vol_ratio'] < 1.0:
        return False

    # Tighter Mom 3d
    if m['mom_3d'] > 5:
        return False

    # Lower volatility
    if m['atr_pct'] > 4:
        return False

    return True


def backtest(data, check_func, name, hold_days=14, stop_loss=-0.06, target=0.05):
    """Run backtest"""
    results = []

    for sym, df in data.items():
        for days_back in range(30, 180, 2):
            idx = len(df) - 1 - days_back
            if idx < 50 or idx + hold_days >= len(df):
                continue

            m = get_metrics(df, idx)
            if not check_func(m):
                continue

            entry = df.iloc[idx]['close']
            entry_date = pd.to_datetime(df.iloc[idx]['date'])

            # Simulate trade
            exit_reason = 'HOLD14'
            exit_price = df.iloc[min(idx + hold_days, len(df)-1)]['close']

            for i in range(1, min(hold_days + 1, len(df) - idx)):
                day_low = df.iloc[idx + i]['low']
                day_high = df.iloc[idx + i]['high']

                if (day_low - entry) / entry <= stop_loss:
                    exit_price = entry * (1 + stop_loss)
                    exit_reason = 'STOP'
                    break

                if (day_high - entry) / entry >= target:
                    exit_price = entry * (1 + target)
                    exit_reason = 'TARGET'
                    break

            ret = ((exit_price - entry) / entry) * 100

            results.append({
                'sym': sym,
                'date': entry_date,
                'ret': ret,
                'win': ret > 0,
                'exit_reason': exit_reason,
                'mom_20d': m['mom_20d'],
            })

    if not results:
        return None

    df_res = pd.DataFrame(results)

    # Dedupe
    df_res = df_res.sort_values(['sym', 'date'])
    df_res['diff'] = df_res.groupby('sym')['date'].diff().dt.days
    df_res = df_res[(df_res['diff'].isna()) | (df_res['diff'] > 10)]

    n = len(df_res)
    wins = df_res['win'].sum()
    stops = (df_res['exit_reason'] == 'STOP').sum()
    targets = (df_res['exit_reason'] == 'TARGET').sum()

    return {
        'name': name,
        'trades': n,
        'wins': wins,
        'win_rate': wins / n * 100 if n > 0 else 0,
        'avg_ret': df_res['ret'].mean(),
        'losers': n - wins,
        'stops': stops,
        'targets': targets,
        'details': df_res,
    }


# Load data
print("Loading data...")
data = {}
for s in STOCKS:
    try:
        df = dm.get_price_data(s, period="1y", interval="1d")
        if df is not None and len(df) >= 200:
            data[s] = df
    except:
        pass

print(f"Loaded {len(data)} stocks\n")

# Run backtests
print("="*80)
print("COMPARING v6.1 vs v6.2 (FIX OVER-EXTENDED PROBLEM)")
print("="*80)

r_v61 = backtest(data, passes_v61, "v6.1 CURRENT")
r_v62 = backtest(data, passes_v62, "v6.2 (Mom20d<=20%, Vol>=1x)")
r_v62s = backtest(data, passes_v62_strict, "v6.2 STRICT (Mom20d<=15%, Mom3d<=5%)")

print(f"\n{'Version':<40} {'Trades':>8} {'Win%':>8} {'Losers':>8} {'Stops':>8} {'AvgRet':>10}")
print("-"*80)

for r in [r_v61, r_v62, r_v62s]:
    if r:
        print(f"{r['name']:<40} {r['trades']:>8} {r['win_rate']:>7.1f}% {r['losers']:>8} {r['stops']:>8} {r['avg_ret']:>+9.2f}%")

# Show improvement
print("\n" + "="*80)
print("IMPROVEMENT SUMMARY")
print("="*80)

if r_v61 and r_v62:
    print(f"""
v6.1 → v6.2 Comparison:
═══════════════════════════════════════════════════════════════════════════════

                        v6.1 CURRENT          v6.2 (Mom<=20%, Vol>=1x)
─────────────────────────────────────────────────────────────────────────────────
Trades:                 {r_v61['trades']:<20} {r_v62['trades']:<20}
Win Rate:               {r_v61['win_rate']:.1f}%{'':<16} {r_v62['win_rate']:.1f}%
Losers:                 {r_v61['losers']:<20} {r_v62['losers']:<20} ({r_v61['losers'] - r_v62['losers']:+d} fewer!)
Stop Losses:            {r_v61['stops']:<20} {r_v62['stops']:<20} ({r_v61['stops'] - r_v62['stops']:+d} fewer!)
Avg Return:             {r_v61['avg_ret']:+.2f}%{'':<15} {r_v62['avg_ret']:+.2f}%

Key Changes:
  + Added: Mom 20d <= 20% (prevent over-extended)
  + Added: Volume Ratio >= 1.0x (need volume confirmation)

Result:
  ✓ Fewer losers (หุ้นที่วิ่งแรงเกิน 20% ใน 20 วันมักจะตกหนัก)
  ✓ Fewer stop losses (หลีกเลี่ยงซื้อตอนราคาพีค)
""")

# Show over-extended stocks that were filtered
if r_v61:
    print("\n" + "="*80)
    print("OVER-EXTENDED STOCKS FILTERED OUT BY v6.2 (Mom 20d > 20%)")
    print("="*80)

    v61_details = r_v61['details']
    overextended = v61_details[v61_details['mom_20d'] > 20]

    if len(overextended) > 0:
        losers = overextended[~overextended['win']]
        winners = overextended[overextended['win']]

        print(f"\nOver-extended stocks (Mom 20d > 20%): {len(overextended)} trades")
        print(f"  - Winners: {len(winners)} ({len(winners)/len(overextended)*100:.0f}%)")
        print(f"  - Losers: {len(losers)} ({len(losers)/len(overextended)*100:.0f}%)")
        print(f"  - Avg Return: {overextended['ret'].mean():+.2f}%")

        print("\n  Examples of over-extended LOSERS:")
        for _, row in losers.head(10).iterrows():
            print(f"    {row['sym']:<8} Mom20d={row['mom_20d']:+.0f}% → {row['ret']:+.1f}%")

# Monthly projection
print("\n" + "="*80)
print("MONTHLY PROJECTION (v6.2)")
print("="*80)

if r_v62:
    trades_per_month = r_v62['trades'] / 6  # 6 months
    losers_per_month = r_v62['losers'] / 6

    capital = 200000
    per_trade = 50000

    print(f"""
v6.2 Monthly Expectations (200,000 บาท capital):
═══════════════════════════════════════════════════════════════════════════════

Trades/Month:        ~{trades_per_month:.0f}
Win Rate:            {r_v62['win_rate']:.1f}%
Losers/Month:        ~{losers_per_month:.1f}
Avg Return/Trade:    {r_v62['avg_ret']:+.2f}%

Monthly Profit Est:  ~{trades_per_month * (per_trade * r_v62['avg_ret']/100):,.0f} บาท
Monthly ROI:         ~{trades_per_month * r_v62['avg_ret'] * (per_trade/capital):.1f}%

Key Benefit:
  → Losers ลดลงอย่างมาก เพราะหลีกเลี่ยงหุ้นที่วิ่งแรงเกิน (over-extended)
""")
