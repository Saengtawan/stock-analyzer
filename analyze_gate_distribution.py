#!/usr/bin/env python3
"""
Analyze which gates stocks fail and how close they are
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
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
    'DVN', 'FANG', 'MRO',
    'NEE', 'DUK', 'SO', 'D', 'AEP',
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'DLR',
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI',
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT',
    'F', 'GM', 'RIVN',
    'VZ', 'T', 'TMUS',
    'LIN', 'APD', 'SHW', 'ECL', 'NEM', 'FCX',
    'PATH', 'CFLT', 'GTLB', 'ESTC', 'DASH', 'LYFT', 'TTD',
]


def get_metrics(df):
    if len(df) < 60:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 0.0001)))

    ma20 = close.rolling(20).mean().iloc[-1]
    above_ma20 = ((price - ma20) / ma20) * 100

    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg if vol_avg > 0 else 1

    mom_3d = ((price / close.iloc[-4]) - 1) * 100
    mom_20d = ((price / close.iloc[-21]) - 1) * 100

    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100

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

    # Days above MA20
    ma20_series = close.rolling(20).mean()
    days_above_ma20 = int((close.iloc[-10:] > ma20_series.iloc[-10:]).sum())

    return {
        'price': price, 'rsi': rsi, 'above_ma20': above_ma20,
        'vol_ratio': vol_ratio, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
        'pos_52w': pos_52w, 'dist_from_20d_high': dist_from_20d_high,
        'atr_pct': atr_pct, 'days_above_ma20': days_above_ma20,
    }


def check_gates(m):
    """Return which gates pass/fail with values"""
    if m is None:
        return None
    
    gates = {
        '1_above_ma20': {'pass': m['above_ma20'] > 0, 'value': m['above_ma20'], 'req': '>0%'},
        '2_pos_52w_low': {'pass': m['pos_52w'] >= 60, 'value': m['pos_52w'], 'req': '>=60%'},
        '3_pos_52w_high': {'pass': m['pos_52w'] <= 85, 'value': m['pos_52w'], 'req': '<=85%'},
        '4_mom20d_low': {'pass': m['mom_20d'] >= 8, 'value': m['mom_20d'], 'req': '>=8%'},
        '5_mom20d_high': {'pass': m['mom_20d'] <= 20, 'value': m['mom_20d'], 'req': '<=20%'},
        '6_mom3d_low': {'pass': m['mom_3d'] >= 1, 'value': m['mom_3d'], 'req': '>=1%'},
        '7_mom3d_high': {'pass': m['mom_3d'] <= 5, 'value': m['mom_3d'], 'req': '<=5%'},
        '8_rsi': {'pass': m['rsi'] < 68, 'value': m['rsi'], 'req': '<68'},
        '9_dist_20d': {'pass': m['dist_from_20d_high'] >= -5, 'value': m['dist_from_20d_high'], 'req': '>=-5%'},
        '10_volume': {'pass': m['vol_ratio'] >= 0.9, 'value': m['vol_ratio'], 'req': '>=0.9x'},
        '11_atr': {'pass': m['atr_pct'] <= 3, 'value': m['atr_pct'], 'req': '<=3%'},
        '12_days_ma20': {'pass': m['days_above_ma20'] >= 8, 'value': m['days_above_ma20'], 'req': '>=8'},
    }
    return gates


print("="*100)
print("GATE FAILURE ANALYSIS - ทำไมหุ้นไม่ผ่าน?")
print("="*100)

gate_fail_count = {}
all_results = []

for sym in STOCKS:
    try:
        df = dm.get_price_data(sym, period="1y", interval="1d")
        if df is None or len(df) < 60:
            continue

        m = get_metrics(df)
        gates = check_gates(m)
        if gates is None:
            continue
        
        passed_count = sum(1 for g in gates.values() if g['pass'])
        failed_gates = [k for k, v in gates.items() if not v['pass']]
        
        for fg in failed_gates:
            gate_fail_count[fg] = gate_fail_count.get(fg, 0) + 1
        
        all_results.append({
            'sym': sym,
            'passed': passed_count,
            'total': len(gates),
            'failed': failed_gates,
            'metrics': m,
            'gates': gates,
        })
    except Exception as e:
        pass

# Sort by most gates passed
all_results.sort(key=lambda x: x['passed'], reverse=True)

print(f"\nAnalyzed: {len(all_results)} stocks")
print(f"Total gates: 12 (need ALL to pass)")

# Distribution
print("\n" + "="*100)
print("GATE PASS DISTRIBUTION")
print("="*100)
dist = {}
for r in all_results:
    p = r['passed']
    dist[p] = dist.get(p, 0) + 1

for p in sorted(dist.keys(), reverse=True):
    bar = "█" * (dist[p] // 2)
    print(f"  {p:2}/12 gates: {dist[p]:3} stocks {bar}")

# Most failed gates
print("\n" + "="*100)
print("GATES THAT FAIL MOST OFTEN (ปัญหาหลัก)")
print("="*100)
sorted_fails = sorted(gate_fail_count.items(), key=lambda x: x[1], reverse=True)
for gate, count in sorted_fails:
    pct = count / len(all_results) * 100
    bar = "█" * int(pct / 2)
    print(f"  {gate:<20}: {count:3} stocks ({pct:5.1f}%) {bar}")

# Top stocks (closest to passing)
print("\n" + "="*100)
print("TOP 20 STOCKS - CLOSEST TO PASSING")
print("="*100)
print(f"{'Sym':<6} {'Pass':>6} {'Failed Gates':<50} {'Mom20d':>8} {'Mom3d':>7} {'ATR':>6}")
print("-"*100)

for r in all_results[:20]:
    failed_str = ", ".join([f.split('_')[1] for f in r['failed'][:4]])
    if len(r['failed']) > 4:
        failed_str += f" +{len(r['failed'])-4}"
    m = r['metrics']
    print(f"{r['sym']:<6} {r['passed']:>2}/12  {failed_str:<50} {m['mom_20d']:>+7.1f}% {m['mom_3d']:>+6.1f}% {m['atr_pct']:>5.1f}%")

# Analyze the most common failure - mom20d
print("\n" + "="*100)
print("MOM 20D DISTRIBUTION (Gate ที่ fail มากที่สุด)")
print("="*100)

mom20d_values = [r['metrics']['mom_20d'] for r in all_results]
ranges = [
    ('<0%', lambda x: x < 0),
    ('0-4%', lambda x: 0 <= x < 4),
    ('4-8%', lambda x: 4 <= x < 8),
    ('8-12%', lambda x: 8 <= x < 12),
    ('12-16%', lambda x: 12 <= x < 16),
    ('16-20%', lambda x: 16 <= x < 20),
    ('>20%', lambda x: x >= 20),
]

print("\n  Mom 20d Range    Count   Status")
print("  " + "-"*40)
for label, fn in ranges:
    count = sum(1 for v in mom20d_values if fn(v))
    status = "✓ PASS" if label in ['8-12%', '12-16%', '16-20%'] else "✗ FAIL"
    bar = "█" * (count // 3)
    print(f"  {label:<12}  {count:5}   {status}  {bar}")

# Suggestion
print("\n" + "="*100)
print("วิเคราะห์และข้อเสนอ")
print("="*100)

# How many would pass if we relax mom20d to 6%?
relax_mom20d = sum(1 for r in all_results 
                   if r['metrics']['mom_20d'] >= 6 and  # relax from 8
                   all(g['pass'] for k, g in r['gates'].items() if k != '4_mom20d_low'))

# How many would pass if we relax mom3d to 6%?
relax_mom3d = sum(1 for r in all_results 
                  if r['metrics']['mom_3d'] <= 6 and  # relax from 5
                  all(g['pass'] for k, g in r['gates'].items() if k != '7_mom3d_high'))

# How many would pass if we relax ATR to 3.5%?
relax_atr = sum(1 for r in all_results 
                if r['metrics']['atr_pct'] <= 3.5 and  # relax from 3
                all(g['pass'] for k, g in r['gates'].items() if k != '11_atr'))

print(f"""
  ปัญหาหลัก: {sorted_fails[0][0]} - {sorted_fails[0][1]} หุ้น fail

  ถ้า relax เกณฑ์:
  ─────────────────────────────────────────────────
  Mom 20d >= 6% (แทน 8%)  →  {relax_mom20d} หุ้นผ่าน
  Mom 3d <= 6% (แทน 5%)   →  {relax_mom3d} หุ้นผ่าน  
  ATR <= 3.5% (แทน 3%)    →  {relax_atr} หุ้นผ่าน
  ─────────────────────────────────────────────────
""")

# Show stocks that would pass with relaxed criteria
print("หุ้นที่จะผ่านถ้า relax Mom 20d >= 6%:")
for r in all_results:
    m = r['metrics']
    # Check if only mom20d_low fails and value is 6-8%
    if (6 <= m['mom_20d'] < 8 and 
        r['failed'] == ['4_mom20d_low']):
        print(f"  {r['sym']:<6} Mom20d={m['mom_20d']:+.1f}%, Mom3d={m['mom_3d']:+.1f}%, ATR={m['atr_pct']:.1f}%")

print("\nหุ้นที่จะผ่านถ้า relax Mom 3d <= 6%:")
for r in all_results:
    m = r['metrics']
    if (5 < m['mom_3d'] <= 6 and 
        r['failed'] == ['7_mom3d_high']):
        print(f"  {r['sym']:<6} Mom20d={m['mom_20d']:+.1f}%, Mom3d={m['mom_3d']:+.1f}%, ATR={m['atr_pct']:.1f}%")

print("\nหุ้นที่จะผ่านถ้า relax ATR <= 3.5%:")
for r in all_results:
    m = r['metrics']
    if (3 < m['atr_pct'] <= 3.5 and 
        r['failed'] == ['11_atr']):
        print(f"  {r['sym']:<6} Mom20d={m['mom_20d']:+.1f}%, Mom3d={m['mom_3d']:+.1f}%, ATR={m['atr_pct']:.1f}%")

