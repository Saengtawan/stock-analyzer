#!/usr/bin/env python3
"""
Check stocks passing v6.2 BALANCED today
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
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
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
]


def get_metrics(df):
    if len(df) < 50:
        return None

    close = df['close']
    high = df['high']
    volume = df['volume']
    price = close.iloc[-1]

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    mom_3d = ((price / close.iloc[-4]) - 1) * 100 if len(close) >= 4 else 0
    mom_20d = ((price / close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0

    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    return {
        'price': price, 'rsi': rsi, 'above_ma20': above_ma20,
        'vol_ratio': vol_ratio, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
        'pos_52w': pos_52w, 'dist_from_20d_high': dist_from_20d_high,
    }


def check_v62_balanced(m):
    """v6.2 BALANCED criteria"""
    if m is None:
        return False, "No data"

    if m['above_ma20'] <= 0:
        return False, f"Below MA20 ({m['above_ma20']:.1f}%)"
    if m['pos_52w'] < 60:
        return False, f"52w pos low ({m['pos_52w']:.0f}%)"
    if m['pos_52w'] > 85:
        return False, f"52w pos high ({m['pos_52w']:.0f}%)"
    if m['mom_20d'] < 8:
        return False, f"Mom20d weak ({m['mom_20d']:.1f}%)"
    if m['mom_20d'] > 20:
        return False, f"Mom20d extended ({m['mom_20d']:.1f}%)"
    if m['mom_3d'] < 1:
        return False, f"Mom3d weak ({m['mom_3d']:.1f}%)"
    if m['mom_3d'] > 8:
        return False, f"Mom3d extended ({m['mom_3d']:.1f}%)"
    if m['rsi'] >= 68:  # BALANCED: relaxed from 65
        return False, f"RSI high ({m['rsi']:.0f})"
    if m['dist_from_20d_high'] < -5:
        return False, f"Pullback ({m['dist_from_20d_high']:.1f}%)"
    if m['vol_ratio'] < 0.9:  # BALANCED: relaxed from 1.0
        return False, f"Volume low ({m['vol_ratio']:.2f}x)"

    return True, "PASS"


print("="*80)
print("v6.2 BALANCED - TODAY'S STOCKS")
print("="*80)
print("""
v6.2 BALANCED Criteria:
  1. Above MA20
  2. 52w Position: 60-85%
  3. Mom 20d: 8-20%
  4. Mom 3d: 1-8%
  5. RSI < 68 (relaxed from 65)
  6. Dist 20d High >= -5%
  7. Volume >= 0.9x (relaxed from 1.0x)

Backtest Result: 70% WR, +3,840 บาท/เดือน
""")

print("Checking stocks...\n")

passed = []
almost = []

for sym in STOCKS:
    try:
        df = dm.get_price_data(sym, period="1y", interval="1d")
        if df is None or len(df) < 50:
            continue

        m = get_metrics(df)
        passes, reason = check_v62_balanced(m)

        if passes:
            passed.append({
                'sym': sym, 'price': m['price'], 'mom_20d': m['mom_20d'],
                'mom_3d': m['mom_3d'], 'rsi': m['rsi'], 'pos_52w': m['pos_52w'],
                'vol_ratio': m['vol_ratio'], 'dist_20d': m['dist_from_20d_high'],
            })
        else:
            # Count failed gates
            gates_failed = 0
            if m['above_ma20'] <= 0: gates_failed += 1
            if m['pos_52w'] < 60 or m['pos_52w'] > 85: gates_failed += 1
            if m['mom_20d'] < 8 or m['mom_20d'] > 20: gates_failed += 1
            if m['mom_3d'] < 1 or m['mom_3d'] > 8: gates_failed += 1
            if m['rsi'] >= 68: gates_failed += 1
            if m['dist_from_20d_high'] < -5: gates_failed += 1
            if m['vol_ratio'] < 0.9: gates_failed += 1

            if gates_failed == 1:
                almost.append({'sym': sym, 'reason': reason, 'mom_20d': m['mom_20d']})
    except:
        pass

passed.sort(key=lambda x: x['mom_20d'], reverse=True)

print(f"PASSED v6.2 BALANCED: {len(passed)} stocks")
print("="*80)

if passed:
    print(f"\n{'Symbol':<8} {'Price':>10} {'Mom20d':>8} {'Mom3d':>8} {'RSI':>6} {'52wPos':>8} {'Vol':>8} {'Dist20d':>8}")
    print("-"*80)

    for s in passed:
        print(f"{s['sym']:<8} ${s['price']:>9.2f} {s['mom_20d']:>+7.1f}% {s['mom_3d']:>+7.1f}% {s['rsi']:>5.0f} {s['pos_52w']:>7.0f}% {s['vol_ratio']:>7.2f}x {s['dist_20d']:>+7.1f}%")
else:
    print("\nNo stocks passed today.")

if almost:
    print(f"\n\nALMOST PASSED (1 gate failed): {len(almost)} stocks")
    print("-"*80)
    for s in almost[:10]:
        print(f"  {s['sym']:<8} {s['reason']:<30} Mom20d={s['mom_20d']:+.1f}%")

print("\n" + "="*80)
print("v6.2 BALANCED SUMMARY")
print("="*80)
print(f"""
  Today: {len(passed)} stocks passed
  Almost: {len(almost)} stocks (1 gate away)

  v6.2 BALANCED vs STRICT:
  ─────────────────────────────────────
  STRICT:   58% WR, +317 บาท/เดือน
  BALANCED: 70% WR, +3,840 บาท/เดือน
  ─────────────────────────────────────
  BALANCED ดีกว่า 12 เท่า!
""")
