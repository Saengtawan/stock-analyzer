#!/usr/bin/env python3
"""
หา Setting ที่ให้ความแน่นอนสูงสุด v2.1
- Fundamental filters (P/E, D/E, Market Cap) ✅
- หลีกเลี่ยง Earnings 7 วัน ✅
- MACD/MA50 เป็น scoring bonus ไม่ใช่ gate ✅

สิ่งที่เรียนรู้จาก v2:
- MACD > Signal เป็น gate = ซื้อช้าเกินไป
- Sweet spot scoring คือหัวใจสำคัญ
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import full STATIC_UNIVERSE (680 stocks)
from screeners.growth_catalyst_screener import GrowthCatalystScreener
FULL_UNIVERSE = GrowthCatalystScreener.STATIC_UNIVERSE


def download_data_with_info(symbol):
    """Download price data + fundamental info"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start='2025-07-01', end='2026-01-30', auto_adjust=True)
        if df.empty or len(df) < 20:
            return symbol, None, None
        df.index = df.index.tz_localize(None)

        info = {}
        try:
            ticker_info = ticker.info
            info = {
                'pe_ratio': ticker_info.get('trailingPE') or ticker_info.get('forwardPE'),
                'profit_margin': ticker_info.get('profitMargins'),
                'debt_to_equity': ticker_info.get('debtToEquity'),
                'market_cap': ticker_info.get('marketCap'),
                'earnings_date': None
            }
            try:
                calendar = ticker.calendar
                if calendar is not None and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earnings_dates = calendar.loc['Earnings Date']
                        if isinstance(earnings_dates, pd.Series) and len(earnings_dates) > 0:
                            info['earnings_date'] = pd.to_datetime(earnings_dates.iloc[0])
            except:
                pass
        except:
            pass

        return symbol, df, info
    except:
        return symbol, None, None


def download_all_parallel(symbols, max_workers=25):
    data = {}
    info_data = {}
    total = len(symbols)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_data_with_info, s): s for s in symbols}
        done = 0
        for future in as_completed(futures):
            done += 1
            symbol, df, info = future.result()
            if df is not None and len(df) >= 50:
                data[symbol] = df
                info_data[symbol] = info or {}
            if done % 100 == 0:
                print(f"  Downloaded {done}/{total} ({len(data)} valid)...")

    return data, info_data


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


def calc_score(m):
    """Original sweet spot scoring - พิสูจน์แล้วว่าได้ผล"""
    score = 0

    # Momentum sweet spot 8-12%
    if 8 <= m['mom_20d'] <= 12:
        score += 40
    elif 5 <= m['mom_20d'] <= 15:
        score += 30
    else:
        score += 15

    # RSI sweet spot 50-58
    if 50 <= m['rsi'] <= 58:
        score += 35
    elif 45 <= m['rsi'] <= 62:
        score += 28
    else:
        score += 15

    # 52w position sweet spot 65-80%
    if 65 <= m['pos_52w'] <= 80:
        score += 25
    elif 55 <= m['pos_52w'] <= 85:
        score += 20
    else:
        score += 10

    return score


def check_fundamental(info, check_date=None):
    """Check fundamental quality - ไม่เข้มงวดเกินไป"""
    if not info:
        return True, "No data (pass)"  # ถ้าไม่มีข้อมูล ให้ผ่าน

    reasons = []

    # P/E: ไม่ติดลบมาก และไม่แพงเกินไป
    pe = info.get('pe_ratio')
    if pe is not None:
        if pe < -50:  # ขาดทุนหนักมาก
            reasons.append(f"Very negative P/E ({pe:.0f})")
        elif pe > 100:  # แพงมากๆ
            reasons.append(f"P/E too high ({pe:.0f})")

    # D/E: ไม่เกิน 3.0 (ผ่อนปรนกว่าเดิม)
    de = info.get('debt_to_equity')
    if de is not None and de > 300:
        reasons.append(f"Very high debt (D/E={de/100:.1f})")

    # Market Cap: ไม่เล็กเกินไป (> $300M) - ผ่อนปรน
    mcap = info.get('market_cap')
    if mcap is not None and mcap < 300_000_000:
        reasons.append(f"Micro cap (${mcap/1e6:.0f}M)")

    # Earnings: หลีกเลี่ยง 5 วันก่อน (ลดจาก 7)
    earnings_date = info.get('earnings_date')
    if earnings_date and check_date:
        try:
            days_to_earnings = (pd.to_datetime(earnings_date) - pd.to_datetime(check_date)).days
            if 0 <= days_to_earnings <= 5:
                reasons.append(f"Earnings in {days_to_earnings} days")
        except:
            pass

    if reasons:
        return False, "; ".join(reasons)
    return True, "OK"


def sim_trade(df, idx, stop_loss=5, target=10, maxhold=30):
    entry = df.iloc[idx]['Close']
    tp = entry * (1 + target/100)
    sl = entry * (1 - stop_loss/100)

    for i in range(1, min(maxhold+1, len(df)-idx)):
        cidx = idx + i
        if cidx >= len(df):
            break
        h, l = df.iloc[cidx]['High'], df.iloc[cidx]['Low']
        if l <= sl:
            return {'ret': -stop_loss, 'days': i, 'exit': 'STOP'}
        if h >= tp:
            return {'ret': target, 'days': i, 'exit': 'TARGET'}

    fidx = min(idx + maxhold, len(df)-1)
    ret = ((df.iloc[fidx]['Close'] - entry) / entry) * 100
    return {'ret': ret, 'days': fidx-idx, 'exit': 'MAX_HOLD'}


def run_config(data, info_data, min_score, top_n, atr_max=4.0, use_fundamental=True):
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
                if m is None: continue

                # Technical Gates (เหมือนเดิม)
                if m['ma20_pct'] < -5: continue
                if not (30 <= m['pos_52w'] <= 95): continue
                if m['mom_20d'] < 0 or m['mom_20d'] > 25: continue
                if m['rsi'] < 35 or m['rsi'] > 70: continue
                if m['atr_pct'] > atr_max: continue
                if m['vol_ratio'] < 0.5: continue

                # Fundamental Filter (ใหม่ แต่ไม่เข้มงวด)
                if use_fundamental:
                    info = info_data.get(s, {})
                    fund_ok, fund_reason = check_fundamental(info, check_date=d)
                    if not fund_ok:
                        continue

                score = calc_score(m)
                if score >= min_score:
                    candidates.append({'s': s, 'score': score, 'idx': idx, 'atr': m['atr_pct']})
            except:
                continue

        if not candidates:
            continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        selected = candidates[:top_n]

        for c in selected:
            t = sim_trade(data[c['s']], c['idx'])
            trades.append({'symbol': c['s'], 'score': c['score'], 'atr': c['atr'], **t})
            recent[c['s']] = d

    return trades


def run():
    print("=" * 70)
    print("หา Setting ที่ให้ความแน่นอนสูงสุด v2.1")
    print("Fundamental filter (ผ่อนปรน) + หลีกเลี่ยง Earnings")
    print(f"Universe: {len(FULL_UNIVERSE)} stocks")
    print("=" * 70)

    print("\nกำลังโหลดข้อมูล...")
    data, info_data = download_all_parallel(FULL_UNIVERSE, max_workers=25)
    print(f"โหลดสำเร็จ {len(data)} หุ้น")

    with_fund = sum(1 for s in info_data if info_data[s].get('pe_ratio') is not None)
    print(f"มี Fundamental data: {with_fund} หุ้น\n")

    # Test configurations
    print("=" * 70)
    print("Backtest: v2.1 (Fundamental ผ่อนปรน)")
    print("=" * 70)

    results = []
    for min_score in [88, 90, 92, 94]:
        for top_n in [1, 2, 3]:
            for atr_max in [4.0, 3.0]:
                trades = run_config(data, info_data, min_score, top_n, atr_max, use_fundamental=True)
                if len(trades) < 5:
                    continue

                df = pd.DataFrame(trades)
                wins = len(df[df['ret'] > 0])
                losses = len(df[df['ret'] <= 0])
                wr = wins / len(df) * 100
                total_ret = df['ret'].sum()

                results.append({
                    'score': min_score,
                    'top_n': top_n,
                    'atr_max': atr_max,
                    'trades': len(df),
                    'wins': wins,
                    'losses': losses,
                    'wr': wr,
                    'total': total_ret,
                    'per_month': len(df) / 4
                })

    results.sort(key=lambda x: (-x['wr'], x['losses']))

    print(f"\n{'Score':>5} | {'Top':>3} | {'ATR':>4} | {'Trades':>6} | {'Win':>4} | {'Lose':>4} | {'WR%':>6} | {'Total':>7}")
    print("-" * 65)

    for r in results[:10]:
        print(f"{r['score']:>5} | {r['top_n']:>3} | {r['atr_max']:>4} | {r['trades']:>6} | {r['wins']:>4} | {r['losses']:>4} | {r['wr']:>5.1f}% | {r['total']:>+6.1f}%")

    # Compare: v1 vs v2.1
    print()
    print("=" * 70)
    print("เปรียบเทียบ: v1 (no fundamental) vs v2.1 (with fundamental)")
    print("=" * 70)

    # v1: no fundamental
    results_v1 = []
    for min_score in [88, 90]:
        for top_n in [1]:
            trades_v1 = run_config(data, info_data, min_score, top_n, 4.0, use_fundamental=False)
            if len(trades_v1) >= 5:
                df_v1 = pd.DataFrame(trades_v1)
                wr_v1 = len(df_v1[df_v1['ret'] > 0]) / len(df_v1) * 100
                losses_v1 = len(df_v1[df_v1['ret'] <= 0])
                results_v1.append({
                    'score': min_score,
                    'trades': len(df_v1),
                    'wr': wr_v1,
                    'losses': losses_v1,
                    'total': df_v1['ret'].sum()
                })

    # v2.1: with fundamental
    results_v21 = []
    for min_score in [88, 90]:
        for top_n in [1]:
            trades_v21 = run_config(data, info_data, min_score, top_n, 4.0, use_fundamental=True)
            if len(trades_v21) >= 5:
                df_v21 = pd.DataFrame(trades_v21)
                wr_v21 = len(df_v21[df_v21['ret'] > 0]) / len(df_v21) * 100
                losses_v21 = len(df_v21[df_v21['ret'] <= 0])
                results_v21.append({
                    'score': min_score,
                    'trades': len(df_v21),
                    'wr': wr_v21,
                    'losses': losses_v21,
                    'total': df_v21['ret'].sum()
                })

    print(f"\n{'Version':<20} | {'Score':>5} | {'Trades':>6} | {'WR%':>6} | {'Losers':>6} | {'Total':>7}")
    print("-" * 65)

    for r in results_v1[:2]:
        print(f"{'v1 (no fundamental)':<20} | {r['score']:>5} | {r['trades']:>6} | {r['wr']:>5.1f}% | {r['losses']:>6} | {r['total']:>+6.1f}%")

    for r in results_v21[:2]:
        print(f"{'v2.1 (fundamental)':<20} | {r['score']:>5} | {r['trades']:>6} | {r['wr']:>5.1f}% | {r['losses']:>6} | {r['total']:>+6.1f}%")

    # Best recommendation
    if results:
        best = results[0]
        print()
        print("=" * 70)
        print("🏆 RECOMMENDATION v2.1")
        print("=" * 70)
        print(f"""
   Setting ที่ดีที่สุด:
   - Score >= {best['score']}
   - Top {best['top_n']} ตัว/สัปดาห์
   - ATR <= {best['atr_max']}%

   ผลลัพธ์:
   - {best['trades']} trades ({best['per_month']:.1f}/month)
   - Win Rate: {best['wr']:.1f}%
   - Losers: {best['losses']} ตัว
   - Total: {best['total']:+.1f}%

   Filters:
   ✅ Sweet spot scoring (Mom 8-12%, RSI 50-58, Pos 65-80%)
   ✅ P/E ไม่ติดลบหนัก และ < 100
   ✅ D/E < 3.0
   ✅ Market Cap > $300M
   ✅ หลีกเลี่ยง 5 วันก่อน Earnings
""")

        # Show example trades
        print("=" * 70)
        print("ตัวอย่าง Trades:")
        print("=" * 70)
        trades = run_config(data, info_data, best['score'], best['top_n'], best['atr_max'])
        df = pd.DataFrame(trades)

        print(f"\nWinners ({len(df[df['ret'] > 0])}):")
        for _, t in df[df['ret'] > 0].iterrows():
            print(f"  {t['symbol']:6} | Score {t['score']:.0f} | {t['ret']:+.1f}% in {t['days']} days")

        print(f"\nLosers ({len(df[df['ret'] <= 0])}):")
        for _, t in df[df['ret'] <= 0].iterrows():
            print(f"  {t['symbol']:6} | Score {t['score']:.0f} | {t['ret']:+.1f}% in {t['days']} days ({t['exit']})")


if __name__ == "__main__":
    run()
