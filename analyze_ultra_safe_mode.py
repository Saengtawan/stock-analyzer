#!/usr/bin/env python3
"""
Ultra Safe Mode - หาหุ้นที่แน่นอนที่สุด

เป้าหมาย:
- Win Rate สูงสุด (>80%)
- ไม่ต้องการเยอะ แค่ 2-5 ตัวที่แน่นอน
- ไม่อยากตื่นมาเจอขาดทุน
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

WORKING_UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
    'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'QCOM',
    'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI', 'INTC', 'ON',
    'MRVL', 'SNPS', 'CDNS', 'ASML', 'TSM', 'ARM', 'SMCI',
    'PANW', 'CRWD', 'ZS', 'NET', 'DDOG', 'SNOW', 'MDB', 'PLTR', 'SHOP', 'WDAY',
    'VEEV', 'HUBS', 'TTD', 'ZM', 'DOCU', 'TEAM', 'OKTA', 'FTNT',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'USB', 'PNC', 'SCHW', 'COIN', 'AFRM', 'SOFI', 'HOOD', 'PYPL',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'CVS', 'GILD', 'REGN', 'VRTX', 'MRNA', 'AMGN', 'BMY', 'DXCM',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CMG', 'LULU', 'DECK', 'CROX', 'RH', 'ULTA',
    'CAT', 'DE', 'HON', 'GE', 'BA', 'RTX', 'LMT', 'NOC', 'UPS', 'FDX',
    'WM', 'URI', 'PWR', 'EMR', 'ETN',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN',
    'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS',
    'RIVN', 'LCID', 'F', 'GM', 'APTV',
    'ABNB', 'BKNG', 'EXPE', 'MAR', 'HLT', 'RCL', 'CCL', 'UAL', 'DAL', 'LUV',
    'DKNG', 'MGM', 'LVS', 'WYNN',
    'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'DLR', 'SPG', 'O',
    'ENPH', 'SEDG', 'FSLR', 'PLUG', 'BE',
    'AXON', 'CAVA', 'DUOL', 'TOST', 'HIMS', 'IONQ', 'APP', 'RKLB',
    'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'AA',
]


def download_data(symbol, start, end):
    try:
        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None
        df.index = df.index.tz_localize(None)
        return df
    except:
        return None


def calc_metrics(df, idx):
    if idx < 25:
        return None
    close = df.iloc[idx]['Close']
    ma20 = df['Close'].iloc[idx-20:idx].mean()
    ma20_pct = ((close - ma20) / ma20) * 100
    lookback = min(252, idx)
    high_52w = df['High'].iloc[idx-lookback:idx].max()
    low_52w = df['Low'].iloc[idx-lookback:idx].min()
    pos_52w = ((close - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50
    mom_20d = ((close - df['Close'].iloc[idx-20]) / df['Close'].iloc[idx-20]) * 100
    mom_5d = ((close - df['Close'].iloc[idx-5]) / df['Close'].iloc[idx-5]) * 100
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    rsi_14 = rsi.iloc[idx] if not pd.isna(rsi.iloc[idx]) else 50
    tr = pd.DataFrame({
        'hl': df['High'] - df['Low'],
        'hc': abs(df['High'] - df['Close'].shift(1)),
        'lc': abs(df['Low'] - df['Close'].shift(1))
    }).max(axis=1)
    atr_pct = (tr.rolling(14).mean().iloc[idx] / close) * 100
    vol_20 = df['Volume'].iloc[idx-20:idx].mean()
    vol_ratio = df['Volume'].iloc[idx] / vol_20 if vol_20 > 0 else 1

    # Consistency check - how many of last 5 days were up?
    up_days = sum(df['Close'].iloc[idx-5:idx].diff().dropna() > 0)

    return {
        'close': close, 'ma20_pct': ma20_pct, 'pos_52w': pos_52w,
        'mom_20d': mom_20d, 'mom_5d': mom_5d, 'rsi': rsi_14,
        'atr_pct': atr_pct, 'vol_ratio': vol_ratio, 'up_days': up_days
    }


def passes_ultra_safe_gates(m):
    """Ultra safe gates - เน้นความแน่นอน"""
    # Basic gates
    if m['ma20_pct'] < 0:  # Must be above MA20
        return False
    if not (50 <= m['pos_52w'] <= 90):  # Not too low, not at peak
        return False
    if m['mom_20d'] < 5 or m['mom_20d'] > 15:  # Sweet spot only
        return False
    if m['rsi'] < 45 or m['rsi'] > 60:  # Neutral zone only
        return False
    if m['atr_pct'] > 2.5:  # Low volatility only!
        return False
    if m['vol_ratio'] < 0.8:  # Good volume
        return False
    if m['up_days'] < 3:  # At least 3/5 days up (consistent)
        return False
    return True


def calc_ultra_safe_score(m):
    """Score สำหรับ Ultra Safe Mode"""
    score = 0

    # Momentum sweet spot (35 pts)
    if 8 <= m['mom_20d'] <= 12:
        score += 35
    elif 6 <= m['mom_20d'] <= 14:
        score += 28
    else:
        score += 15

    # RSI neutral zone (30 pts)
    if 50 <= m['rsi'] <= 56:
        score += 30
    elif 48 <= m['rsi'] <= 58:
        score += 25
    else:
        score += 15

    # Position (20 pts)
    if 60 <= m['pos_52w'] <= 80:
        score += 20
    elif 55 <= m['pos_52w'] <= 85:
        score += 15
    else:
        score += 8

    # Low volatility bonus (15 pts)
    if m['atr_pct'] < 1.5:
        score += 15
    elif m['atr_pct'] < 2.0:
        score += 12
    else:
        score += 5

    return score


def sim_trade(df, idx, stop_loss=5, target=10, maxhold=30):
    entry = df.iloc[idx]['Close']
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop_loss/100)

    # Track if it dipped day 1
    dipped_day1 = False

    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break
        h, l, o = df.iloc[cidx]['High'], df.iloc[cidx]['Low'], df.iloc[cidx]['Open']

        # Check if opened lower (gap down)
        if i == 1 and o < entry * 0.98:  # Gap down > 2%
            dipped_day1 = True

        if l <= sl:
            return {'ret': -stop_loss, 'days': i, 'exit': 'STOP', 'dipped_day1': dipped_day1}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET', 'dipped_day1': dipped_day1}

    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD', 'dipped_day1': dipped_day1}


def run():
    print("=" * 70)
    print("ULTRA SAFE MODE - หาหุ้นที่แน่นอนที่สุด")
    print("=" * 70)
    print()
    print("เป้าหมาย:")
    print("  - Win Rate > 80%")
    print("  - ไม่ต้องเยอะ แค่ 2-5 ตัวที่แน่ๆ")
    print("  - ไม่อยากตื่นมาเจอขาดทุน (no gap down)")
    print()

    print("กำลังโหลดข้อมูล...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"โหลดแล้ว {len(data)} หุ้น\n")

    # Test different configurations
    configs = [
        {'name': 'Normal (Score>=88, Top 5)', 'min_score': 88, 'top_n': 5, 'ultra_safe': False},
        {'name': 'Safe (Score>=92, Top 3)', 'min_score': 92, 'top_n': 3, 'ultra_safe': False},
        {'name': 'Ultra Safe (Score>=92, Top 2, Low Vol)', 'min_score': 92, 'top_n': 2, 'ultra_safe': True},
        {'name': 'Ultra Safe (Score>=95, Top 2, Low Vol)', 'min_score': 95, 'top_n': 2, 'ultra_safe': True},
    ]

    all_results = []

    for config in configs:
        dates = pd.date_range('2025-10-01', '2026-01-25', freq='W-MON')
        trades = []
        recent = {}

        for d in dates:
            cutoff = d - timedelta(days=14)
            recent = {k: v for k, v in recent.items() if v > cutoff}
            candidates = []

            for s, df in data.items():
                if s in recent:
                    continue
                try:
                    if d not in df.index:
                        vd = df.index[df.index <= d]
                        if len(vd) == 0: continue
                        idx = df.index.get_loc(vd[-1])
                    else:
                        idx = df.index.get_loc(d)
                    if idx < 25: continue
                    m = calc_metrics(df, idx)
                    if m is None:
                        continue

                    # Use ultra safe gates or normal
                    if config['ultra_safe']:
                        if not passes_ultra_safe_gates(m):
                            continue
                        score = calc_ultra_safe_score(m)
                    else:
                        # Normal gates
                        if m['ma20_pct'] < -5: continue
                        if not (30 <= m['pos_52w'] <= 95): continue
                        if m['mom_20d'] < 0 or m['mom_20d'] > 25: continue
                        if m['rsi'] < 35 or m['rsi'] > 70: continue
                        if m['atr_pct'] > 4: continue

                        # Normal score
                        score = 0
                        if 8 <= m['mom_20d'] <= 12: score += 40
                        elif 5 <= m['mom_20d'] <= 15: score += 30
                        else: score += 15
                        if 50 <= m['rsi'] <= 58: score += 35
                        elif 45 <= m['rsi'] <= 62: score += 28
                        else: score += 15
                        if 65 <= m['pos_52w'] <= 80: score += 25
                        elif 55 <= m['pos_52w'] <= 85: score += 20
                        else: score += 10

                    if score >= config['min_score']:
                        candidates.append({'s': s, 'score': score, 'idx': idx, **m})
                except:
                    continue

            if not candidates:
                continue

            candidates.sort(key=lambda x: x['score'], reverse=True)
            selected = candidates[:config['top_n']]

            for c in selected:
                t = sim_trade(data[c['s']], c['idx'])
                trades.append({
                    'symbol': c['s'],
                    'score': c['score'],
                    'atr': c['atr_pct'],
                    **t
                })
                recent[c['s']] = d

        if not trades:
            continue

        df_trades = pd.DataFrame(trades)
        total = len(df_trades)
        winners = df_trades[df_trades['ret'] > 0]
        losers = df_trades[df_trades['ret'] <= 0]
        wr = len(winners) / total * 100

        # Gap down analysis
        gap_downs = df_trades[df_trades['dipped_day1'] == True]

        result = {
            'config': config['name'],
            'trades': total,
            'winners': len(winners),
            'losers': len(losers),
            'wr': wr,
            'total_ret': df_trades['ret'].sum(),
            'gap_downs': len(gap_downs),
            'trades_per_month': total / 4,
            'avg_loss': losers['ret'].mean() if len(losers) > 0 else 0
        }
        all_results.append(result)

        print(f"\n{config['name']}:")
        print(f"  Trades: {total} ({total/4:.1f}/month)")
        print(f"  Win Rate: {wr:.1f}%")
        print(f"  Losers: {len(losers)}")
        print(f"  Gap Downs (Day 1 dip): {len(gap_downs)}")
        print(f"  Total Return: {df_trades['ret'].sum():+.1f}%")

    # Recommendation
    print()
    print("=" * 70)
    print("RECOMMENDATION สำหรับสไตล์ของคุณ (2-5 ตัว, ต้องการความแน่นอน)")
    print("=" * 70)

    # Find best for user's style
    best = max(all_results, key=lambda x: x['wr'] if x['trades'] >= 10 else 0)

    print(f"""
   🏆 แนะนำ: {best['config']}

   ผลลัพธ์:
   - Trades: {best['trades']} ใน 4 เดือน ({best['trades_per_month']:.1f}/month)
   - Win Rate: {best['wr']:.1f}%
   - Losers: {best['losers']} ตัว
   - Gap Downs: {best['gap_downs']} ครั้ง
   - Total Return: {best['total_ret']:+.1f}%

   เหมาะกับคุณเพราะ:
   ✅ ซื้อแค่ 2-3 ตัวต่อสัปดาห์ (ไม่เยอะ)
   ✅ Win Rate สูง ({best['wr']:.0f}%)
   ✅ Loser น้อย
   ✅ Gap down น้อย (ไม่ตื่นมาช็อค)
""")

    # Compare strategies
    print("=" * 70)
    print("เปรียบเทียบ:")
    print("=" * 70)
    print(f"{'Config':<40} | {'Trades':>6} | {'WR%':>6} | {'Losers':>6} | {'GapDown':>7}")
    print("-" * 70)
    for r in all_results:
        print(f"{r['config']:<40} | {r['trades']:>6} | {r['wr']:>5.1f}% | {r['losers']:>6} | {r['gap_downs']:>7}")


if __name__ == "__main__":
    run()
