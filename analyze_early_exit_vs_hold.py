#!/usr/bin/env python3
"""
วิเคราะห์: ขายเร็วตอนติดลบน้อยๆ vs รอ recovery

คำถาม:
A) ขายทันทีเมื่อติดลบ 2-3% → ไปซื้อหุ้นตัวใหม่
B) ถือรอ recovery จนถึง stop loss (-7%) หรือ target (+10%)

อะไรให้ win rate และกำไรเยอะกว่า?
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


def sim_trade_detailed(df, idx, maxhold=30):
    """
    Simulate trade and track daily P&L
    Returns detailed daily data for analysis
    """
    entry = df.iloc[idx]['Close']
    daily_returns = []

    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break

        close = df.iloc[cidx]['Close']
        high = df.iloc[cidx]['High']
        low = df.iloc[cidx]['Low']

        # Calculate daily metrics
        pnl_close = ((close - entry) / entry) * 100
        pnl_low = ((low - entry) / entry) * 100
        pnl_high = ((high - entry) / entry) * 100

        daily_returns.append({
            'day': i,
            'pnl_close': pnl_close,
            'pnl_low': pnl_low,
            'pnl_high': pnl_high
        })

        # Check exit conditions
        if pnl_low <= -7:
            return {
                'final_ret': -7,
                'days': i,
                'exit': 'STOP_LOSS',
                'daily': daily_returns
            }
        if pnl_high >= 10:
            return {
                'final_ret': 10,
                'days': i,
                'exit': 'TARGET_HIT',
                'daily': daily_returns
            }

    # Max hold
    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {
        'final_ret': ret,
        'days': len(daily_returns),
        'exit': 'MAX_HOLD',
        'daily': daily_returns
    }


def run():
    print("=" * 70)
    print("การวิเคราะห์: ขายเร็ว vs รอ Recovery")
    print("=" * 70)

    print("\nกำลังโหลดข้อมูล...")
    data = {}
    for s in WORKING_UNIVERSE:
        df = download_data(s, '2025-07-01', '2026-01-30')
        if df is not None and len(df) >= 50:
            data[s] = df
    print(f"โหลดแล้ว {len(data)} หุ้น\n")

    # Collect all trades with detailed daily data
    dates = pd.date_range('2025-10-01', '2026-01-25', freq='W-MON')
    all_trades = []
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
                    if score >= 88:  # High score threshold
                        candidates.append({'s': s, 'score': score, 'idx': idx, **m})
            except: continue

        if not candidates: continue
        candidates.sort(key=lambda x: x['score'], reverse=True)

        for c in candidates[:5]:
            t = sim_trade_detailed(data[c['s']], c['idx'])
            all_trades.append({
                'symbol': c['s'],
                'entry_date': d,
                'score': c['score'],
                **t
            })
            recent[c['s']] = d

    # Analyze: what happens to trades that dip early?
    print("=" * 70)
    print("การวิเคราะห์ว่าถ้าขายเร็วตอนติดลบ จะดีกว่าไหม")
    print("=" * 70)

    early_dip_trades = []
    no_dip_trades = []

    for trade in all_trades:
        # Check if trade dipped in first 3 days
        early_days = trade['daily'][:3] if len(trade['daily']) >= 3 else trade['daily']
        min_early_pnl = min([d['pnl_low'] for d in early_days]) if early_days else 0

        if min_early_pnl <= -3:  # Dipped 3%+ in first 3 days
            early_dip_trades.append({
                **trade,
                'early_dip': min_early_pnl
            })
        else:
            no_dip_trades.append(trade)

    print(f"\n📊 สถิติการ Dip ใน 3 วันแรก:")
    print(f"   หุ้นที่ dip >= 3%: {len(early_dip_trades)} ตัว")
    print(f"   หุ้นที่ไม่ dip: {len(no_dip_trades)} ตัว")

    # What happened to stocks that dipped early?
    print(f"\n" + "=" * 70)
    print("กลุ่ม A: หุ้นที่ dip >=3% ใน 3 วันแรก (ถ้าขายตอนนั้นจะได้อะไร?)")
    print("=" * 70)

    recovered = []
    stayed_bad = []

    for t in early_dip_trades:
        if t['final_ret'] > 0:
            recovered.append(t)
        else:
            stayed_bad.append(t)

    print(f"\n   ✅ RECOVER แล้วกำไร: {len(recovered)} ตัว ({len(recovered)/len(early_dip_trades)*100:.0f}%)")
    for t in recovered[:10]:
        print(f"      {t['symbol']}: dip {t['early_dip']:.1f}% → สุดท้าย {t['final_ret']:+.1f}% ({t['exit']})")

    print(f"\n   ❌ ยังคงขาดทุน: {len(stayed_bad)} ตัว ({len(stayed_bad)/len(early_dip_trades)*100:.0f}%)")
    for t in stayed_bad[:10]:
        print(f"      {t['symbol']}: dip {t['early_dip']:.1f}% → สุดท้าย {t['final_ret']:+.1f}% ({t['exit']})")

    # Calculate scenarios
    print(f"\n" + "=" * 70)
    print("เปรียบเทียบ 2 กลยุทธ์:")
    print("=" * 70)

    # Strategy A: Hold to completion (current)
    total_trades = len(all_trades)
    all_returns = [t['final_ret'] for t in all_trades]
    winners_a = sum(1 for r in all_returns if r > 0)
    total_ret_a = sum(all_returns)

    print(f"\n📈 กลยุทธ์ A: ถือจนจบ (stop loss -7%, target +10%)")
    print(f"   Total Trades: {total_trades}")
    print(f"   Winners: {winners_a} ({winners_a/total_trades*100:.1f}%)")
    print(f"   Total Return: {total_ret_a:+.1f}%")
    print(f"   Avg Return: {np.mean(all_returns):+.2f}%")

    # Strategy B: Early exit at -3%
    # If dipped >= 3% in first 3 days, exit at -3%
    # Otherwise, hold to completion
    returns_b = []
    wins_b = 0

    for trade in all_trades:
        early_days = trade['daily'][:3] if len(trade['daily']) >= 3 else trade['daily']
        min_early_pnl = min([d['pnl_low'] for d in early_days]) if early_days else 0

        if min_early_pnl <= -3:
            # Exit early at -3%
            returns_b.append(-3)
        else:
            returns_b.append(trade['final_ret'])
            if trade['final_ret'] > 0:
                wins_b += 1

    # Count wins for early exits (none, they all exit at -3%)
    total_ret_b = sum(returns_b)
    winners_b = sum(1 for r in returns_b if r > 0)

    print(f"\n📉 กลยุทธ์ B: ขายทันทีถ้า dip >=3% ใน 3 วันแรก")
    print(f"   Total Trades: {total_trades}")
    print(f"   Winners: {winners_b} ({winners_b/total_trades*100:.1f}%)")
    print(f"   Total Return: {total_ret_b:+.1f}%")
    print(f"   Avg Return: {np.mean(returns_b):+.2f}%")

    # Strategy C: Reinvest after early exit
    # If we exit early, we can take another trade
    # Assume the next trade has average return
    avg_return = np.mean([t['final_ret'] for t in no_dip_trades]) if no_dip_trades else 0

    returns_c = []
    for trade in all_trades:
        early_days = trade['daily'][:3] if len(trade['daily']) >= 3 else trade['daily']
        min_early_pnl = min([d['pnl_low'] for d in early_days]) if early_days else 0

        if min_early_pnl <= -3:
            # Exit early at -3%, then reinvest
            returns_c.append(-3 + avg_return * 0.7)  # 70% of avg (conservative)
        else:
            returns_c.append(trade['final_ret'])

    total_ret_c = sum(returns_c)
    winners_c = sum(1 for r in returns_c if r > 0)

    print(f"\n🔄 กลยุทธ์ C: ขายเร็ว + ซื้อตัวใหม่ (สมมติได้ 70% ของ avg return)")
    print(f"   Total Trades: {total_trades} + {len(early_dip_trades)} reinvest")
    print(f"   Winners: {winners_c} ({winners_c/total_trades*100:.1f}%)")
    print(f"   Total Return: {total_ret_c:+.1f}%")
    print(f"   Avg Return: {np.mean(returns_c):+.2f}%")

    # Key insight
    print(f"\n" + "=" * 70)
    print("💡 สรุปผลวิเคราะห์:")
    print("=" * 70)

    recovery_rate = len(recovered) / len(early_dip_trades) * 100 if early_dip_trades else 0

    print(f"""
   หุ้นที่ dip >=3% ใน 3 วันแรก:
   - {recovery_rate:.0f}% RECOVER และกำไร (ถ้าถือต่อ)
   - {100-recovery_rate:.0f}% ยังคงขาดทุน

   ผลลัพธ์:
   - กลยุทธ์ A (ถือจนจบ):     {total_ret_a:+.1f}% total, {winners_a/total_trades*100:.1f}% WR
   - กลยุทธ์ B (ขายเร็ว):      {total_ret_b:+.1f}% total, {winners_b/total_trades*100:.1f}% WR
   - กลยุทธ์ C (ขาย+ซื้อใหม่): {total_ret_c:+.1f}% total, {winners_c/total_trades*100:.1f}% WR
""")

    if total_ret_a > total_ret_b and total_ret_a > total_ret_c:
        print("   🏆 ผู้ชนะ: กลยุทธ์ A (ถือจนจบ) - ให้กำไรมากที่สุด!")
        print(f"      เหตุผล: {recovery_rate:.0f}% ของหุ้นที่ dip ก็ยัง recover กลับมากำไร")
    elif total_ret_c > total_ret_a:
        print("   🏆 ผู้ชนะ: กลยุทธ์ C (ขาย+ซื้อใหม่) - ถ้าหาหุ้นใหม่ได้เร็ว")
    else:
        print("   🏆 ผู้ชนะ: กลยุทธ์ B (ขายเร็ว) - ลด drawdown")


if __name__ == "__main__":
    run()
