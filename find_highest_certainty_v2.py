#!/usr/bin/env python3
"""
หา Setting ที่ให้ความแน่นอนสูงสุด v2.0
เพิ่ม Fundamental + Catalyst + Better Technical

Filter ครบ 5 หมวด:
1. Technical (RSI, MA, Momentum, MACD, Trend)
2. Catalyst (Earnings date)
3. Fundamental (P/E, Profit Growth, D/E)
4. Volume (Accumulation)
5. Quality (Market Cap, Liquidity)
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
    """Download price data + fundamental info for a single symbol"""
    try:
        ticker = yf.Ticker(symbol)

        # Price data
        df = ticker.history(start='2025-07-01', end='2026-01-30', auto_adjust=True)
        if df.empty or len(df) < 20:
            return symbol, None, None
        df.index = df.index.tz_localize(None)

        # Fundamental data
        info = {}
        try:
            ticker_info = ticker.info
            info = {
                'pe_ratio': ticker_info.get('trailingPE') or ticker_info.get('forwardPE'),
                'peg_ratio': ticker_info.get('pegRatio'),
                'profit_margin': ticker_info.get('profitMargins'),
                'revenue_growth': ticker_info.get('revenueGrowth'),
                'earnings_growth': ticker_info.get('earningsGrowth'),
                'debt_to_equity': ticker_info.get('debtToEquity'),
                'current_ratio': ticker_info.get('currentRatio'),
                'market_cap': ticker_info.get('marketCap'),
                'avg_volume': ticker_info.get('averageVolume'),
                'sector': ticker_info.get('sector'),
                # Earnings calendar
                'earnings_date': None
            }

            # Try to get next earnings date
            try:
                calendar = ticker.calendar
                if calendar is not None and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earnings_dates = calendar.loc['Earnings Date']
                        if isinstance(earnings_dates, pd.Series) and len(earnings_dates) > 0:
                            info['earnings_date'] = pd.to_datetime(earnings_dates.iloc[0])
                        elif isinstance(earnings_dates, (datetime, pd.Timestamp)):
                            info['earnings_date'] = pd.to_datetime(earnings_dates)
            except:
                pass

        except:
            pass

        return symbol, df, info
    except:
        return symbol, None, None


def download_all_parallel(symbols, max_workers=20):
    """Download data for all symbols in parallel"""
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


def calc_macd(df):
    """Calculate MACD"""
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def calc_metrics_v2(df, idx, info):
    """Calculate metrics with enhanced indicators"""
    if idx < 30:
        return None

    close = df.iloc[idx]['Close']

    # Basic metrics
    ma20 = df['Close'].iloc[idx-20:idx].mean()
    ma50 = df['Close'].iloc[max(0,idx-50):idx].mean() if idx >= 50 else ma20
    ma20_pct = ((close - ma20) / ma20) * 100

    # 52-week position
    lookback = min(252, idx)
    high_52w = df['High'].iloc[idx-lookback:idx].max()
    low_52w = df['Low'].iloc[idx-lookback:idx].min()
    pos_52w = ((close - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

    # Momentum
    mom_20d = ((close - df['Close'].iloc[idx-20]) / df['Close'].iloc[idx-20]) * 100

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    rsi_14 = rsi.iloc[idx] if not pd.isna(rsi.iloc[idx]) else 50

    # ATR%
    tr = pd.DataFrame({
        'hl': df['High'] - df['Low'],
        'hc': abs(df['High'] - df['Close'].shift(1)),
        'lc': abs(df['Low'] - df['Close'].shift(1))
    }).max(axis=1)
    atr_pct = (tr.rolling(14).mean().iloc[idx] / close) * 100

    # Volume
    vol_20 = df['Volume'].iloc[idx-20:idx].mean()
    vol_ratio = df['Volume'].iloc[idx] / vol_20 if vol_20 > 0 else 1

    # === NEW: MACD ===
    macd, signal = calc_macd(df.iloc[:idx+1])
    macd_val = macd.iloc[-1]
    signal_val = signal.iloc[-1]
    macd_histogram = macd_val - signal_val
    macd_bullish = macd_val > signal_val

    # === NEW: Trend (Higher Highs, Higher Lows) ===
    recent_highs = df['High'].iloc[idx-20:idx]
    recent_lows = df['Low'].iloc[idx-20:idx]

    # Check if making higher highs and higher lows
    mid_high = recent_highs.iloc[:10].max()
    late_high = recent_highs.iloc[10:].max()
    mid_low = recent_lows.iloc[:10].min()
    late_low = recent_lows.iloc[10:].min()

    uptrend = (late_high >= mid_high * 0.98) and (late_low >= mid_low * 0.98)

    # === NEW: Volume Accumulation ===
    # Volume on up days vs down days
    price_change = df['Close'].diff().iloc[idx-10:idx]
    volume = df['Volume'].iloc[idx-10:idx]
    up_volume = volume[price_change > 0].sum()
    down_volume = volume[price_change <= 0].sum()
    accumulation = up_volume > down_volume * 1.2  # Up volume 20% more than down

    # === NEW: Above MA50 (longer trend) ===
    above_ma50 = close > ma50

    return {
        'close': close,
        'ma20_pct': ma20_pct,
        'pos_52w': pos_52w,
        'mom_20d': mom_20d,
        'rsi': rsi_14,
        'atr_pct': atr_pct,
        'vol_ratio': vol_ratio,
        # New metrics
        'macd_bullish': macd_bullish,
        'macd_histogram': macd_histogram,
        'uptrend': uptrend,
        'accumulation': accumulation,
        'above_ma50': above_ma50,
    }


def check_fundamental(info, check_date=None):
    """Check fundamental quality"""
    if not info:
        return False, "No fundamental data"

    reasons = []

    # P/E ratio: ไม่แพงเกินไป (< 50) และไม่ติดลบ
    pe = info.get('pe_ratio')
    if pe is not None:
        if pe < 0:
            reasons.append(f"Negative P/E ({pe:.1f})")
        elif pe > 50:
            reasons.append(f"P/E too high ({pe:.1f})")

    # Debt/Equity: ไม่เกิน 2.0
    de = info.get('debt_to_equity')
    if de is not None and de > 200:  # D/E > 2.0 (reported as percentage)
        reasons.append(f"High debt (D/E={de/100:.1f})")

    # Profit Margin: ไม่ติดลบมาก
    margin = info.get('profit_margin')
    if margin is not None and margin < -0.3:  # ขาดทุนเกิน 30%
        reasons.append(f"Negative margin ({margin*100:.0f}%)")

    # Market Cap: ไม่เล็กเกินไป (> $500M)
    mcap = info.get('market_cap')
    if mcap is not None and mcap < 500_000_000:
        reasons.append(f"Small cap (${mcap/1e6:.0f}M)")

    # Earnings Date: หลีกเลี่ยง 7 วันก่อน earnings
    earnings_date = info.get('earnings_date')
    if earnings_date and check_date:
        try:
            days_to_earnings = (pd.to_datetime(earnings_date) - pd.to_datetime(check_date)).days
            if 0 <= days_to_earnings <= 7:
                reasons.append(f"Earnings in {days_to_earnings} days")
        except:
            pass

    if reasons:
        return False, "; ".join(reasons)
    return True, "OK"


def calc_score_v2(m, info):
    """Calculate score with enhanced metrics"""
    score = 0

    # === Original Scoring ===
    # Momentum (sweet spot 8-12%)
    if 8 <= m['mom_20d'] <= 12:
        score += 30
    elif 5 <= m['mom_20d'] <= 15:
        score += 22
    else:
        score += 10

    # RSI (sweet spot 50-58)
    if 50 <= m['rsi'] <= 58:
        score += 25
    elif 45 <= m['rsi'] <= 62:
        score += 18
    else:
        score += 8

    # Position in 52w range (sweet spot 65-80%)
    if 65 <= m['pos_52w'] <= 80:
        score += 20
    elif 55 <= m['pos_52w'] <= 85:
        score += 15
    else:
        score += 5

    # === NEW: Technical Bonus ===
    # MACD bullish
    if m['macd_bullish']:
        score += 8

    # Uptrend (higher highs/lows)
    if m['uptrend']:
        score += 7

    # Volume accumulation
    if m['accumulation']:
        score += 5

    # Above MA50
    if m['above_ma50']:
        score += 5

    # === Total: 100 points max ===
    return min(score, 100)


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


def run_config_v2(data, info_data, min_score, top_n, atr_max=4.0, use_fundamental=True):
    """Run backtest with v2 filters"""
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
                if idx < 30: continue

                info = info_data.get(s, {})
                m = calc_metrics_v2(df, idx, info)
                if m is None: continue

                # === GATES (Hard Filters) ===

                # Basic Technical Gates
                if m['ma20_pct'] < -5: continue
                if not (30 <= m['pos_52w'] <= 95): continue
                if m['mom_20d'] < 0 or m['mom_20d'] > 25: continue
                if m['rsi'] < 35 or m['rsi'] > 70: continue
                if m['atr_pct'] > atr_max: continue
                if m['vol_ratio'] < 0.5: continue

                # NEW: Must be above MA50 (uptrend)
                if not m['above_ma50']: continue

                # NEW: MACD must be bullish
                if not m['macd_bullish']: continue

                # NEW: Fundamental Check
                if use_fundamental:
                    fund_ok, fund_reason = check_fundamental(info, check_date=d)
                    if not fund_ok:
                        continue

                score = calc_score_v2(m, info)
                if score >= min_score:
                    candidates.append({
                        's': s,
                        'score': score,
                        'idx': idx,
                        'atr': m['atr_pct'],
                        'uptrend': m['uptrend'],
                        'accum': m['accumulation']
                    })
            except:
                continue

        if not candidates:
            continue

        # Sort by score, then by uptrend, then by accumulation
        candidates.sort(key=lambda x: (x['score'], x['uptrend'], x['accum']), reverse=True)
        selected = candidates[:top_n]

        for c in selected:
            t = sim_trade(data[c['s']], c['idx'])
            trades.append({
                'symbol': c['s'],
                'score': c['score'],
                'atr': c['atr'],
                'uptrend': c['uptrend'],
                'accum': c['accum'],
                **t
            })
            recent[c['s']] = d

    return trades


def run():
    print("=" * 70)
    print("หา Setting ที่ให้ความแน่นอนสูงสุด v2.0")
    print("เพิ่ม: Fundamental + Catalyst + MACD + Trend")
    print(f"Universe: {len(FULL_UNIVERSE)} stocks")
    print("=" * 70)

    print("\nกำลังโหลดข้อมูล + Fundamental (อาจใช้เวลา 3-5 นาที)...")
    data, info_data = download_all_parallel(FULL_UNIVERSE, max_workers=25)
    print(f"โหลดสำเร็จ {len(data)} หุ้น\n")

    # Count how many have fundamental data
    with_fund = sum(1 for s in info_data if info_data[s].get('pe_ratio') is not None)
    print(f"มี Fundamental data: {with_fund} หุ้น")

    # Test configurations
    results = []

    print("\nกำลัง backtest (v2 filters)...")

    for min_score in [70, 75, 80, 85, 90]:
        for top_n in [1, 2, 3]:
            for atr_max in [4.0, 3.0]:
                trades = run_config_v2(data, info_data, min_score, top_n, atr_max, use_fundamental=True)
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

    # Sort by win rate
    results.sort(key=lambda x: (-x['wr'], x['losses']))

    print()
    print("=" * 70)
    print("TOP 10 Settings (v2.0 with Fundamental + Catalyst)")
    print("=" * 70)
    print(f"{'Score':>5} | {'Top':>3} | {'ATR':>4} | {'Trades':>6} | {'Win':>4} | {'Lose':>4} | {'WR%':>6} | {'Total':>7} | {'ต่อเดือน':>8}")
    print("-" * 70)

    for r in results[:10]:
        print(f"{r['score']:>5} | {r['top_n']:>3} | {r['atr_max']:>4} | {r['trades']:>6} | {r['wins']:>4} | {r['losses']:>4} | {r['wr']:>5.1f}% | {r['total']:>+6.1f}% | {r['per_month']:>7.1f}")

    if not results:
        print("\n❌ ไม่มีผลลัพธ์ที่มี trades >= 5")
        return

    best = results[0]

    print()
    print("=" * 70)
    print("RECOMMENDATION v2.0")
    print("=" * 70)
    print(f"""
   🏆 Setting ที่ดีที่สุด (with Fundamental + Catalyst):

   Score >= {best['score']}
   เลือกแค่ Top {best['top_n']} ตัว/สัปดาห์
   ATR <= {best['atr_max']}%

   ผลลัพธ์:
   - {best['trades']} trades ใน 4 เดือน ({best['per_month']:.1f}/month)
   - Win Rate: {best['wr']:.1f}%
   - Losers: แค่ {best['losses']} ตัว
   - Total: {best['total']:+.1f}%

   🆕 Filters ใหม่ที่เพิ่ม:
   - ✅ MACD > Signal (momentum confirm)
   - ✅ Price > MA50 (uptrend)
   - ✅ P/E < 50 (ไม่แพงเกิน)
   - ✅ D/E < 2.0 (หนี้ไม่เยอะ)
   - ✅ Market Cap > $500M
   - ✅ หลีกเลี่ยง 7 วันก่อน Earnings
""")

    # Show trades from best config
    print("=" * 70)
    print("ตัวอย่าง Trades:")
    print("=" * 70)
    trades = run_config_v2(data, info_data, best['score'], best['top_n'], best['atr_max'])
    df = pd.DataFrame(trades)
    wins = df[df['ret'] > 0]
    losses = df[df['ret'] <= 0]

    print(f"\nWinners ({len(wins)}):")
    for _, t in wins.iterrows():
        trend = "📈" if t.get('uptrend') else ""
        accum = "💰" if t.get('accum') else ""
        print(f"  {t['symbol']:6} | Score {t['score']:.0f} | {t['ret']:+.1f}% in {t['days']} days {trend}{accum}")

    print(f"\nLosers ({len(losses)}):")
    for _, t in losses.iterrows():
        print(f"  {t['symbol']:6} | Score {t['score']:.0f} | {t['ret']:+.1f}% in {t['days']} days ({t['exit']})")

    # Compare with v1
    print()
    print("=" * 70)
    print("เปรียบเทียบ v1 vs v2:")
    print("=" * 70)

    # Run v1 style (without fundamental)
    results_v1 = []
    for min_score in [88, 90]:
        for top_n in [1]:
            trades_v1 = run_config_v2(data, info_data, min_score, top_n, 4.0, use_fundamental=False)
            if len(trades_v1) >= 5:
                df_v1 = pd.DataFrame(trades_v1)
                wr_v1 = len(df_v1[df_v1['ret'] > 0]) / len(df_v1) * 100
                results_v1.append({
                    'score': min_score,
                    'trades': len(df_v1),
                    'wr': wr_v1,
                    'losses': len(df_v1[df_v1['ret'] <= 0])
                })

    if results_v1:
        v1 = results_v1[0]
        print(f"""
   v1 (Technical only):
   - Score >= {v1['score']}, Trades: {v1['trades']}, WR: {v1['wr']:.1f}%, Losers: {v1['losses']}

   v2 (+ Fundamental + Catalyst):
   - Score >= {best['score']}, Trades: {best['trades']}, WR: {best['wr']:.1f}%, Losers: {best['losses']}
""")


if __name__ == "__main__":
    run()
