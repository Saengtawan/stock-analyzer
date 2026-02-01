#!/usr/bin/env python3
"""
Check stocks passing v6.3 LOW LOSER today
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

    # v6.3: ATR
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    # v6.3: Days above MA20
    ma20_series = close.rolling(20).mean()
    days_above_ma20 = int((close.iloc[-10:] > ma20_series.iloc[-10:]).sum())

    return {
        'price': price, 'rsi': rsi, 'above_ma20': above_ma20,
        'vol_ratio': vol_ratio, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
        'pos_52w': pos_52w, 'dist_from_20d_high': dist_from_20d_high,
        'atr_pct': atr_pct, 'days_above_ma20': days_above_ma20,
    }


def check_v63(m):
    """v6.3 LOW LOSER criteria"""
    if m is None:
        return False, "No data"

    if m['above_ma20'] <= 0:
        return False, f"Below MA20"
    if m['pos_52w'] < 60:
        return False, f"52w low ({m['pos_52w']:.0f}%)"
    if m['pos_52w'] > 85:
        return False, f"52w high ({m['pos_52w']:.0f}%)"
    if m['mom_20d'] < 8:
        return False, f"Mom20d weak ({m['mom_20d']:.1f}%)"
    if m['mom_20d'] > 20:
        return False, f"Mom20d extended ({m['mom_20d']:.1f}%)"
    if m['mom_3d'] < 1:
        return False, f"Mom3d weak ({m['mom_3d']:.1f}%)"
    if m['mom_3d'] > 5:  # v6.3: tighter
        return False, f"Mom3d rush ({m['mom_3d']:.1f}%)"
    if m['rsi'] >= 68:
        return False, f"RSI high ({m['rsi']:.0f})"
    if m['dist_from_20d_high'] < -5:
        return False, f"Pullback ({m['dist_from_20d_high']:.1f}%)"
    if m['vol_ratio'] < 0.9:
        return False, f"Vol low ({m['vol_ratio']:.2f}x)"
    if m['atr_pct'] > 3:  # v6.3 NEW
        return False, f"ATR high ({m['atr_pct']:.1f}%)"
    if m['days_above_ma20'] < 8:  # v6.3 NEW
        return False, f"Trend weak ({m['days_above_ma20']}/10 days)"

    return True, "PASS"


print("="*90)
print("v6.3 LOW LOSER - TODAY'S STOCKS")
print("="*90)
print("""
v6.3 LOW LOSER Criteria (9 gates):
  1. Above MA20           - Uptrend
  2. 52w Position 60-85%  - Not extreme
  3. Mom 20d: 8-20%       - Strong but not over-extended
  4. Mom 3d: 1-5%         - Recent push but not rushing
  5. RSI < 68             - Not overbought
  6. Dist 20d High >= -5% - Not in pullback
  7. Volume >= 0.9x       - Volume confirmation
  8. ATR <= 3%            - Low volatility (NEW!)
  9. Days above MA20 >= 8 - Trend consistency (NEW!)

Backtest: 28 trades, 75% WR, 7 losers, +4,069 บาท/เดือน
""")

print(f"Checking {len(STOCKS)} stocks...\n")

passed = []
almost = []

for sym in STOCKS:
    try:
        df = dm.get_price_data(sym, period="1y", interval="1d")
        if df is None or len(df) < 60:
            continue

        m = get_metrics(df)
        passes, reason = check_v63(m)

        if passes:
            passed.append({
                'sym': sym, 'price': m['price'], 'mom_20d': m['mom_20d'],
                'mom_3d': m['mom_3d'], 'rsi': m['rsi'], 'pos_52w': m['pos_52w'],
                'atr': m['atr_pct'], 'days_ma20': m['days_above_ma20'],
            })
        else:
            # Count gates failed
            gates = 0
            if m['above_ma20'] <= 0: gates += 1
            if m['pos_52w'] < 60 or m['pos_52w'] > 85: gates += 1
            if m['mom_20d'] < 8 or m['mom_20d'] > 20: gates += 1
            if m['mom_3d'] < 1 or m['mom_3d'] > 5: gates += 1
            if m['rsi'] >= 68: gates += 1
            if m['dist_from_20d_high'] < -5: gates += 1
            if m['vol_ratio'] < 0.9: gates += 1
            if m['atr_pct'] > 3: gates += 1
            if m['days_above_ma20'] < 8: gates += 1

            if gates == 1:
                almost.append({
                    'sym': sym, 'reason': reason, 'mom_20d': m['mom_20d'],
                    'atr': m['atr_pct'], 'days_ma20': m['days_above_ma20'],
                })
    except:
        pass

passed.sort(key=lambda x: x['mom_20d'], reverse=True)

print(f"PASSED v6.3 LOW LOSER: {len(passed)} stocks")
print("="*90)

if passed:
    print(f"\n{'Symbol':<8} {'Price':>10} {'Mom20d':>8} {'Mom3d':>8} {'RSI':>6} {'52wPos':>8} {'ATR':>8} {'Days>MA20':>10}")
    print("-"*90)

    for s in passed:
        print(f"{s['sym']:<8} ${s['price']:>9.2f} {s['mom_20d']:>+7.1f}% {s['mom_3d']:>+7.1f}% {s['rsi']:>5.0f} {s['pos_52w']:>7.0f}% {s['atr']:>7.1f}% {s['days_ma20']:>9}/10")
else:
    print("\nNo stocks passed all 9 gates today.")

if almost:
    print(f"\n\nALMOST PASSED (1 gate failed): {len(almost)} stocks")
    print("-"*90)
    print(f"{'Symbol':<8} {'Reason':<25} {'Mom20d':>8} {'ATR':>8} {'Days>MA20':>10}")
    print("-"*90)
    for s in almost[:15]:
        print(f"{s['sym']:<8} {s['reason']:<25} {s['mom_20d']:>+7.1f}% {s['atr']:>7.1f}% {s['days_ma20']:>9}/10")

print("\n" + "="*90)
print("v6.3 LOW LOSER SUMMARY")
print("="*90)
print(f"""
  Today:  {len(passed)} passed, {len(almost)} almost passed

  v6.3 ต่างจาก v6.2:
  ─────────────────────────────────────────────────────
  + ATR <= 3% (Low volatility = fewer crashes)
  + Days above MA20 >= 8 (Trend consistency)
  + Mom 3d <= 5% (Not rushing - was 8%)
  ─────────────────────────────────────────────────────

  Result: Losers ลด 11 ตัว (18→7), Win Rate เพิ่ม 9% (66%→75%)
""")
