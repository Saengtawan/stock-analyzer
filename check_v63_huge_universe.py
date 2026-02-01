#!/usr/bin/env python3
"""
Test v6.3 with HUGE universe (400+ stocks)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
from api.data_manager import DataManager

dm = DataManager()

# HUGE UNIVERSE - 400+ stocks
STOCKS = [
    # Mega Cap Tech
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'SHOP',
    # Semiconductors
    'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI',
    'ON', 'SWKS', 'MPWR', 'MRVL', 'SNPS', 'CDNS', 'ASML', 'TSM', 'ARM', 'SMCI',
    # Cloud/SaaS
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'PYPL', 'PLTR', 'SQ',
    'ZM', 'DOCU', 'TWLO', 'OKTA', 'TEAM', 'SPLK', 'WDAY', 'VEEV', 'HUBS', 'BILL',
    'CFLT', 'GTLB', 'ESTC', 'PATH', 'DOMO', 'RNG', 'FIVN', 'ZEN', 'PCTY', 'PAYC',
    # Streaming/Media/Gaming
    'NFLX', 'DIS', 'CMCSA', 'WBD', 'PARA', 'ROKU', 'SPOT', 'SNAP', 'PINS', 'RBLX',
    'EA', 'TTWO', 'U', 'MTCH',
    # E-commerce/Fintech
    'EBAY', 'ETSY', 'W', 'CHWY', 'MELI', 'SE', 'COIN', 'HOOD', 'AFRM', 'SOFI', 'UPST',
    'V', 'MA', 'AXP', 'PYPL', 'GPN', 'FIS', 'FISV', 'ADP', 'PAYX',
    # Banks & Finance
    'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC', 'USB', 'PNC', 'TFC', 'SCHW',
    'COF', 'DFS', 'SYF', 'ALLY', 'NDAQ', 'ICE', 'CME', 'SPGI', 'MCO', 'MSCI',
    # Insurance
    'BRK-B', 'AIG', 'MET', 'PRU', 'ALL', 'TRV', 'PGR', 'CB', 'AFL', 'HIG',
    # Healthcare/Pharma
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'CI', 'HUM', 'ELV', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA', 'AMGN',
    'BMY', 'ZTS', 'SYK', 'BSX', 'MDT', 'EW', 'DXCM', 'IDXX', 'IQV', 'A',
    'HOLX', 'ALGN', 'PODD', 'INCY', 'EXAS', 'NBIX', 'SGEN', 'ALNY',
    # Consumer Retail
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'DG', 'DLTR', 'BBY',
    'LULU', 'ULTA', 'NKE', 'GPS', 'ANF', 'AEO', 'URBN', 'FIVE', 'ORLY', 'AZO',
    'AAP', 'TSCO', 'BOOT', 'DECK', 'CROX', 'SKX', 'VFC', 'PVH', 'RL', 'TPR',
    # Food & Beverage
    'SBUX', 'MCD', 'CMG', 'DPZ', 'YUM', 'QSR', 'DNUT', 'SHAK', 'WING', 'CAVA',
    'KO', 'PEP', 'MNST', 'KDP', 'STZ', 'TAP', 'SAM', 'BUD',
    # Consumer Staples
    'PG', 'CL', 'KMB', 'CLX', 'CHD', 'EL', 'KVUE', 'HSY', 'K', 'GIS', 'CAG',
    # Industrial
    'CAT', 'DE', 'HON', 'GE', 'MMM', 'EMR', 'ROK', 'ETN', 'PH', 'ITW',
    'RTX', 'LMT', 'NOC', 'BA', 'GD', 'HII', 'LHX', 'TDG', 'HWM', 'TXT',
    'UPS', 'FDX', 'XPO', 'JBHT', 'CHRW', 'EXPD', 'ODFL', 'SAIA', 'XPO',
    'URI', 'WSC', 'GNRC', 'PWR', 'FAST', 'GWW', 'POOL',
    # Transportation
    'DAL', 'UAL', 'LUV', 'AAL', 'ALK', 'JBLU', 'HA', 'SAVE',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'HAL',
    'DVN', 'FANG', 'PXD', 'MRO', 'APA', 'OVV', 'CTRA', 'EQT', 'AR',
    # Utilities
    'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'WEC', 'ED',
    'ES', 'AWK', 'ATO', 'NI', 'CMS', 'DTE', 'FE', 'PPL', 'AES', 'CEG',
    # REITs
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'WELL', 'DLR', 'SPG', 'AVB',
    'EQR', 'VTR', 'ARE', 'ESS', 'UDR', 'MAA', 'SUI', 'ELS', 'INVH', 'AMH',
    # China/Intl ADR
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'TME', 'BILI', 'BEKE',
    'VIPS', 'TAL', 'EDU', 'IQ', 'FUTU', 'TIGR', 'YMM', 'ZTO', 'QFIN', 'LX',
    # Travel/Leisure
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT', 'H', 'RCL', 'CCL', 'NCLH', 'LVS',
    'MGM', 'WYNN', 'CZR', 'DKNG', 'PENN', 'RSI',
    # Auto
    'F', 'GM', 'RIVN', 'LCID', 'TM', 'HMC', 'RACE', 'STLA',
    # Telecom
    'VZ', 'T', 'TMUS', 'LUMN', 'FYBR',
    # Materials
    'LIN', 'APD', 'SHW', 'ECL', 'DD', 'NEM', 'FCX', 'GOLD', 'NUE', 'STLD',
    'CLF', 'X', 'AA', 'SCCO', 'VALE', 'RIO', 'BHP', 'TECK',
    # Cannabis/Speculative
    'TLRY', 'CGC', 'ACB', 'SNDL',
    # SPACs turned companies
    'LCID', 'RIVN', 'GRAB', 'SOFI', 'DNA', 'IONQ', 'JOBY',
    # Other growth
    'TTD', 'APPS', 'DASH', 'LYFT', 'OPEN', 'RDFN', 'CVNA', 'VRM',
    'CHGG', 'PTON', 'BYND', 'OATLY',
]

# Remove duplicates
STOCKS = list(dict.fromkeys(STOCKS))


def get_metrics(df):
    if len(df) < 60:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
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

    mom_3d = ((price / close.iloc[-4]) - 1) * 100
    mom_20d = ((price / close.iloc[-21]) - 1) * 100

    lookback = min(252, len(close))
    high_52w = high.iloc[-lookback:].max()
    low_52w = close.iloc[-lookback:].min()
    pos_52w = ((price - low_52w) / (high_52w - low_52w)) * 100

    high_20d = high.iloc[-20:].max()
    dist_from_20d_high = ((price - high_20d) / high_20d) * 100

    tr = pd.DataFrame({
        'hl': high - low,
        'hc': abs(high - close.shift(1)),
        'lc': abs(low - close.shift(1))
    }).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    atr_pct = (atr / price) * 100

    ma20_series = close.rolling(20).mean()
    days_above_ma20 = int((close.iloc[-10:] > ma20_series.iloc[-10:]).sum())

    return {
        'price': price, 'rsi': rsi, 'above_ma20': above_ma20,
        'vol_ratio': vol_ratio, 'mom_3d': mom_3d, 'mom_20d': mom_20d,
        'pos_52w': pos_52w, 'dist_from_20d_high': dist_from_20d_high,
        'atr_pct': atr_pct, 'days_above_ma20': days_above_ma20,
    }


def check_v63(m):
    if m is None:
        return False, "No data", {}

    failures = {}

    if m['above_ma20'] <= 0:
        failures['above_ma20'] = f"Below MA20"
    if m['pos_52w'] < 60:
        failures['pos_52w'] = f"52w low ({m['pos_52w']:.0f}%)"
    if m['pos_52w'] > 85:
        failures['pos_52w'] = f"52w high ({m['pos_52w']:.0f}%)"
    if m['mom_20d'] < 8:
        failures['mom_20d'] = f"Mom20d weak ({m['mom_20d']:.1f}%)"
    if m['mom_20d'] > 20:
        failures['mom_20d'] = f"Mom20d extended ({m['mom_20d']:.1f}%)"
    if m['mom_3d'] < 1:
        failures['mom_3d'] = f"Mom3d weak ({m['mom_3d']:.1f}%)"
    if m['mom_3d'] > 5:
        failures['mom_3d'] = f"Mom3d rush ({m['mom_3d']:.1f}%)"
    if m['rsi'] >= 68:
        failures['rsi'] = f"RSI high ({m['rsi']:.0f})"
    if m['dist_from_20d_high'] < -5:
        failures['dist_20d'] = f"Pullback ({m['dist_from_20d_high']:.1f}%)"
    if m['vol_ratio'] < 0.9:
        failures['vol'] = f"Vol low ({m['vol_ratio']:.2f}x)"
    if m['atr_pct'] > 3:
        failures['atr'] = f"ATR high ({m['atr_pct']:.1f}%)"
    if m['days_above_ma20'] < 8:
        failures['days_ma20'] = f"Trend weak ({m['days_above_ma20']}/10)"

    if len(failures) == 0:
        return True, "PASS", failures
    else:
        return False, list(failures.values())[0], failures


print("="*90)
print("v6.3 LOW LOSER - HUGE UNIVERSE TEST")
print("="*90)
print(f"\nTesting {len(STOCKS)} stocks...")

passed = []
almost_1 = []  # Failed 1 gate
almost_2 = []  # Failed 2 gates

loaded = 0
for sym in STOCKS:
    try:
        df = dm.get_price_data(sym, period="1y", interval="1d")
        if df is None or len(df) < 60:
            continue
        loaded += 1

        m = get_metrics(df)
        passes, reason, failures = check_v63(m)

        if passes:
            passed.append({
                'sym': sym, 'price': m['price'], 'mom_20d': m['mom_20d'],
                'mom_3d': m['mom_3d'], 'rsi': m['rsi'], 'pos_52w': m['pos_52w'],
                'atr': m['atr_pct'], 'days_ma20': m['days_above_ma20'],
            })
        elif len(failures) == 1:
            almost_1.append({
                'sym': sym, 'reason': reason, 'mom_20d': m['mom_20d'],
                'atr': m['atr_pct'], 'days_ma20': m['days_above_ma20'],
                'failure_type': list(failures.keys())[0],
            })
        elif len(failures) == 2:
            almost_2.append({
                'sym': sym, 'reasons': list(failures.values()),
                'mom_20d': m['mom_20d'],
            })
    except Exception as e:
        pass

print(f"\nLoaded: {loaded} stocks")

passed.sort(key=lambda x: x['mom_20d'], reverse=True)

print(f"\n{'='*90}")
print(f"PASSED v6.3: {len(passed)} stocks")
print("="*90)

if passed:
    print(f"\n{'Symbol':<8} {'Price':>10} {'Mom20d':>8} {'Mom3d':>8} {'RSI':>6} {'52wPos':>8} {'ATR':>8} {'Days>MA20':>10}")
    print("-"*90)
    for s in passed:
        print(f"{s['sym']:<8} ${s['price']:>9.2f} {s['mom_20d']:>+7.1f}% {s['mom_3d']:>+7.1f}% {s['rsi']:>5.0f} {s['pos_52w']:>7.0f}% {s['atr']:>7.1f}% {s['days_ma20']:>9}/10")
else:
    print("\nNo stocks passed all 9 gates.")

print(f"\n{'='*90}")
print(f"ALMOST PASSED (1 gate failed): {len(almost_1)} stocks")
print("="*90)

# Group by failure type
failure_counts = {}
for s in almost_1:
    ft = s['failure_type']
    failure_counts[ft] = failure_counts.get(ft, 0) + 1

print("\nFailure breakdown:")
for ft, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
    print(f"  {ft}: {count} stocks")

print(f"\n{'Symbol':<8} {'Reason':<30} {'Mom20d':>8} {'ATR':>8} {'Days>MA20':>10}")
print("-"*90)
for s in almost_1[:20]:
    print(f"{s['sym']:<8} {s['reason']:<30} {s['mom_20d']:>+7.1f}% {s['atr']:>7.1f}% {s['days_ma20']:>9}/10")

print(f"\n{'='*90}")
print(f"2 GATES AWAY: {len(almost_2)} stocks")
print("="*90)

print(f"\n{'='*90}")
print("RECOMMENDATION")
print("="*90)

if len(passed) > 0:
    print(f"\n✅ Found {len(passed)} stocks that pass v6.3!")
elif len(almost_1) > 5:
    # Find which gate to relax
    most_common = max(failure_counts.items(), key=lambda x: x[1])
    print(f"""
🔍 No stocks pass but {len(almost_1)} are 1 gate away.

Most common failure: {most_common[0]} ({most_common[1]} stocks)

Options:
1. Wait for market conditions to improve
2. Consider slight relaxation of {most_common[0]} filter
""")
else:
    print(f"\n⏳ Market conditions not favorable. Wait for better setups.")
