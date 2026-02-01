#!/usr/bin/env python3
"""
วิเคราะห์: Stop Loss เร็วแค่ไหนดีที่สุด สำหรับคนทุนจำกัด

สถานการณ์:
- มีเงินจำกัด (เดือนต่อเดือน)
- ติดลบนาน = ชะงัก ซื้อตัวใหม่ไม่ได้
- ต้องการ loser น้อยที่สุด
- ยอมขาดทุนน้อยๆ ดีกว่าติดลบนาน

เปรียบเทียบ:
- SL -7% (ปกติ)
- SL -5%
- SL -3%
- SL -2%
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
    return {
        'close': close, 'ma20_pct': ma20_pct, 'pos_52w': pos_52w,
        'mom_20d': mom_20d, 'rsi': rsi_14, 'atr_pct': atr_pct, 'vol_ratio': vol_ratio
    }


def passes_gates(m):
    if m['ma20_pct'] < -5: return False
    if not (30 <= m['pos_52w'] <= 95): return False
    if m['mom_20d'] < 0 or m['mom_20d'] > 25: return False
    if m['rsi'] < 35 or m['rsi'] > 70: return False
    if m['atr_pct'] > 4: return False
    if m['vol_ratio'] < 0.5: return False
    return True


def calc_score(m):
    if 8 <= m['mom_20d'] <= 12:
        mom_score = 100
    elif 5 <= m['mom_20d'] <= 15:
        mom_score = 85
    else:
        mom_score = 60
    if 50 <= m['rsi'] <= 58:
        rsi_score = 100
    elif 45 <= m['rsi'] <= 62:
        rsi_score = 85
    else:
        rsi_score = 60
    if 65 <= m['pos_52w'] <= 80:
        pos_score = 100
    elif 55 <= m['pos_52w'] <= 85:
        pos_score = 85
    else:
        pos_score = 60
    return mom_score * 0.4 + rsi_score * 0.35 + pos_score * 0.25


def sim_trade_with_sl(df, idx, stop_loss, target=10, maxhold=30):
    """Simulate trade with configurable stop loss"""
    entry = df.iloc[idx]['Close']
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop_loss/100)

    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break
        h, l = df.iloc[cidx]['High'], df.iloc[cidx]['Low']

        if l <= sl:
            return {'ret': -stop_loss, 'days': i, 'exit': 'STOP_LOSS', 'hit_sl': True}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET_HIT', 'hit_sl': False}

    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD', 'hit_sl': False}


def run_with_sl(data, stop_loss, min_score=88):
    """Run backtest with specific stop loss"""
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
                if m and passes_gates(m):
                    score = calc_score(m)
                    if score >= min_score:
                        candidates.append({'s': s, 'score': score, 'idx': idx, **m})
            except: continue

        if not candidates: continue
        candidates.sort(key=lambda x: x['score'], reverse=True)
        for c in candidates[:5]:
            t = sim_trade_with_sl(data[c['s']], c['idx'], stop_loss)
            trades.append({
                'symbol': c['s'],
                'score': c['score'],
                **t
            })
            recent[c['s']] = d

    return trades


def run():
    print("=" * 75)
    print("วิเคราะห์: Stop Loss เร็วแค่ไหนดีที่สุด (สำหรับคนทุนจำกัด)")
    print("=" * 75)
    print()
    print("สถานการณ์:")
    print("  - มีเงินจำกัด (เดือนต่อเดือน)")
    print("  - ติดลบนาน = ชะงัก ซื้อตัวใหม่ไม่ได้")
    print("  - ต้องการ loser น้อยที่สุด + ขาดทุนน้อยที่สุด")
    print()

    print("กำลังโหลดข้อมูล...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"โหลดแล้ว {len(data)} หุ้น\n")

    # Test different stop loss levels with high score threshold
    stop_losses = [7, 5, 4, 3, 2]
    score_thresholds = [88, 90, 92, 95]

    print("=" * 75)
    print("ผลการทดสอบ: Score >= 88 (ค่า default)")
    print("=" * 75)
    print(f"{'SL%':>5} | {'Trades':>6} | {'Win':>4} | {'Lose':>4} | {'WR%':>6} | {'AvgLoss':>8} | {'TotalRet':>9} | {'MaxDD':>7}")
    print("-" * 75)

    results_88 = []
    for sl in stop_losses:
        trades = run_with_sl(data, sl, min_score=88)
        if not trades:
            continue

        df = pd.DataFrame(trades)
        total = len(df)
        winners = df[df['ret'] > 0]
        losers = df[df['ret'] <= 0]
        wr = len(winners) / total * 100

        # Calculate max drawdown (consecutive losses)
        max_dd = 0
        current_dd = 0
        for ret in df['ret']:
            if ret < 0:
                current_dd += ret
                max_dd = min(max_dd, current_dd)
            else:
                current_dd = 0

        avg_loss = losers['ret'].mean() if len(losers) > 0 else 0
        total_ret = df['ret'].sum()

        results_88.append({
            'sl': sl,
            'trades': total,
            'winners': len(winners),
            'losers': len(losers),
            'wr': wr,
            'avg_loss': avg_loss,
            'total_ret': total_ret,
            'max_dd': max_dd
        })

        print(f"{sl:>4}% | {total:>6} | {len(winners):>4} | {len(losers):>4} | {wr:>5.1f}% | {avg_loss:>7.1f}% | {total_ret:>+8.1f}% | {max_dd:>6.1f}%")

    # Higher score threshold for fewer losers
    print()
    print("=" * 75)
    print("ผลการทดสอบ: Score >= 92 (เข้มงวดกว่า = loser น้อยกว่า)")
    print("=" * 75)
    print(f"{'SL%':>5} | {'Trades':>6} | {'Win':>4} | {'Lose':>4} | {'WR%':>6} | {'AvgLoss':>8} | {'TotalRet':>9} | {'MaxDD':>7}")
    print("-" * 75)

    results_92 = []
    for sl in stop_losses:
        trades = run_with_sl(data, sl, min_score=92)
        if not trades:
            continue

        df = pd.DataFrame(trades)
        total = len(df)
        winners = df[df['ret'] > 0]
        losers = df[df['ret'] <= 0]
        wr = len(winners) / total * 100

        max_dd = 0
        current_dd = 0
        for ret in df['ret']:
            if ret < 0:
                current_dd += ret
                max_dd = min(max_dd, current_dd)
            else:
                current_dd = 0

        avg_loss = losers['ret'].mean() if len(losers) > 0 else 0
        total_ret = df['ret'].sum()

        results_92.append({
            'sl': sl,
            'trades': total,
            'winners': len(winners),
            'losers': len(losers),
            'wr': wr,
            'avg_loss': avg_loss,
            'total_ret': total_ret,
            'max_dd': max_dd
        })

        print(f"{sl:>4}% | {total:>6} | {len(winners):>4} | {len(losers):>4} | {wr:>5.1f}% | {avg_loss:>7.1f}% | {total_ret:>+8.1f}% | {max_dd:>6.1f}%")

    # Ultra conservative: Score >= 95
    print()
    print("=" * 75)
    print("ผลการทดสอบ: Score >= 95 (เข้มงวดมาก = loser น้อยมาก)")
    print("=" * 75)
    print(f"{'SL%':>5} | {'Trades':>6} | {'Win':>4} | {'Lose':>4} | {'WR%':>6} | {'AvgLoss':>8} | {'TotalRet':>9} | {'MaxDD':>7}")
    print("-" * 75)

    results_95 = []
    for sl in stop_losses:
        trades = run_with_sl(data, sl, min_score=95)
        if not trades:
            continue

        df = pd.DataFrame(trades)
        total = len(df)
        winners = df[df['ret'] > 0]
        losers = df[df['ret'] <= 0]
        wr = len(winners) / total * 100

        max_dd = 0
        current_dd = 0
        for ret in df['ret']:
            if ret < 0:
                current_dd += ret
                max_dd = min(max_dd, current_dd)
            else:
                current_dd = 0

        avg_loss = losers['ret'].mean() if len(losers) > 0 else 0
        total_ret = df['ret'].sum()

        results_95.append({
            'sl': sl,
            'trades': total,
            'winners': len(winners),
            'losers': len(losers),
            'wr': wr,
            'avg_loss': avg_loss,
            'total_ret': total_ret,
            'max_dd': max_dd
        })

        print(f"{sl:>4}% | {total:>6} | {len(winners):>4} | {len(losers):>4} | {wr:>5.1f}% | {avg_loss:>7.1f}% | {total_ret:>+8.1f}% | {max_dd:>6.1f}%")

    # Recommendation
    print()
    print("=" * 75)
    print("💡 คำแนะนำสำหรับคนทุนจำกัด:")
    print("=" * 75)

    # Find best combo for limited capital
    all_results = []
    for r in results_88:
        r['score'] = 88
        all_results.append(r)
    for r in results_92:
        r['score'] = 92
        all_results.append(r)
    for r in results_95:
        r['score'] = 95
        all_results.append(r)

    # Sort by fewest losers, then by total return
    all_results.sort(key=lambda x: (x['losers'], -x['total_ret']))

    print()
    print("🏆 TOP 5 ตัวเลือกที่ Loser น้อยที่สุด:")
    print("-" * 75)
    for i, r in enumerate(all_results[:5], 1):
        print(f"   {i}. Score >= {r['score']}, SL -{r['sl']}%")
        print(f"      → {r['trades']} trades, {r['losers']} losers, {r['wr']:.0f}% WR")
        print(f"      → AvgLoss: {r['avg_loss']:.1f}%, Total: {r['total_ret']:+.1f}%, MaxDD: {r['max_dd']:.1f}%")
        print()

    # Best for capital preservation
    best_preservation = min(all_results, key=lambda x: abs(x['max_dd']))
    best_wr = max(all_results, key=lambda x: x['wr'])

    print("=" * 75)
    print("📊 สรุป:")
    print("=" * 75)
    print(f"""
   สำหรับคนทุนจำกัด ที่ต้องการ:
   ✅ Loser น้อยที่สุด
   ✅ ขาดทุนต่อครั้งน้อยที่สุด
   ✅ ไม่อยากติดลบนาน

   แนะนำ: Score >= {all_results[0]['score']}, SL -{all_results[0]['sl']}%

   เหตุผล:
   - มีแค่ {all_results[0]['losers']} losers ใน 4 เดือน
   - ขาดทุนเฉลี่ย {all_results[0]['avg_loss']:.1f}% ต่อครั้ง (ยอมรับได้)
   - Win Rate {all_results[0]['wr']:.0f}%
   - Max Drawdown {all_results[0]['max_dd']:.1f}% (เงินไม่จมนาน)
""")


if __name__ == "__main__":
    run()
