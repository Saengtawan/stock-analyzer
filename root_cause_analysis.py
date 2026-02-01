#!/usr/bin/env python3
"""
Root Cause Analysis: ทำไมหุ้นถึงตก?
วิเคราะห์หุ้นที่โดน Stop Loss อย่างละเอียด
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# โหลดผลลัพธ์
with open('standard_backtest_20260201_171257.json', 'r') as f:
    data = json.load(f)

trades = data['trades']
sl_trades = [t for t in trades if t['exit_reason'] == 'STOP_LOSS']

print("=" * 80)
print("ROOT CAUSE ANALYSIS: ทำไมหุ้นถึงตก?")
print("=" * 80)

def analyze_stock(symbol, entry_date, entry_price):
    """วิเคราะห์หุ้นอย่างละเอียด"""

    # ดึงข้อมูลย้อนหลัง 30 วันก่อน entry และ 10 วันหลัง
    start = (datetime.strptime(entry_date, '%Y-%m-%d') - timedelta(days=40)).strftime('%Y-%m-%d')
    end = (datetime.strptime(entry_date, '%Y-%m-%d') + timedelta(days=15)).strftime('%Y-%m-%d')

    try:
        df = yf.download(symbol, start=start, end=end, progress=False)
        if df.empty:
            return None

        # Flatten columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        # คำนวณ indicators
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        df['RSI'] = compute_rsi(df['Close'], 14)
        df['ATR'] = compute_atr(df, 14)
        df['Volume_SMA'] = df['Volume'].rolling(20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA']

        # หา entry day
        entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
        entry_idx = None
        for i, idx in enumerate(df.index):
            if idx.strftime('%Y-%m-%d') == entry_date:
                entry_idx = i
                break

        if entry_idx is None:
            return None

        # ข้อมูล ณ วัน entry
        entry_row = df.iloc[entry_idx]

        # ข้อมูล 5 วันก่อน entry
        pre_5d = df.iloc[max(0, entry_idx-5):entry_idx]

        # ข้อมูล 5 วันหลัง entry
        post_5d = df.iloc[entry_idx+1:min(len(df), entry_idx+6)]

        result = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,

            # Technical ณ วัน entry
            'rsi_at_entry': entry_row['RSI'] if 'RSI' in entry_row else None,
            'above_sma20': entry_row['Close'] > entry_row['SMA20'] if pd.notna(entry_row['SMA20']) else None,
            'above_sma50': entry_row['Close'] > entry_row['SMA50'] if pd.notna(entry_row['SMA50']) else None,
            'volume_ratio': entry_row['Volume_Ratio'] if pd.notna(entry_row['Volume_Ratio']) else None,
            'atr_pct': (entry_row['ATR'] / entry_row['Close'] * 100) if pd.notna(entry_row['ATR']) else None,

            # Price action ก่อน entry
            'pre_5d_change': ((entry_row['Close'] - pre_5d.iloc[0]['Close']) / pre_5d.iloc[0]['Close'] * 100) if len(pre_5d) > 0 else None,
            'pre_5d_lowest': ((entry_row['Close'] - pre_5d['Low'].min()) / pre_5d['Low'].min() * 100) if len(pre_5d) > 0 else None,

            # Price action หลัง entry
            'post_max_gain': ((post_5d['High'].max() - entry_price) / entry_price * 100) if len(post_5d) > 0 else None,
            'post_max_loss': ((post_5d['Low'].min() - entry_price) / entry_price * 100) if len(post_5d) > 0 else None,
            'post_day1_change': ((post_5d.iloc[0]['Close'] - entry_price) / entry_price * 100) if len(post_5d) > 0 else None,

            # วัน entry เป็น gap down?
            'entry_gap': ((entry_row['Open'] - df.iloc[entry_idx-1]['Close']) / df.iloc[entry_idx-1]['Close'] * 100) if entry_idx > 0 else None,

            # Candle pattern วัน entry
            'entry_candle_body': ((entry_row['Close'] - entry_row['Open']) / entry_row['Open'] * 100),
            'entry_upper_wick': ((entry_row['High'] - max(entry_row['Open'], entry_row['Close'])) / entry_row['Close'] * 100),
            'entry_lower_wick': ((min(entry_row['Open'], entry_row['Close']) - entry_row['Low']) / entry_row['Close'] * 100),
        }

        return result

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# วิเคราะห์ทุก SL trade
print(f"\nวิเคราะห์ {len(sl_trades)} trades ที่โดน Stop Loss...\n")

results = []
for t in sl_trades:
    print(f"Analyzing {t['symbol']} ({t['entry_date']})...")
    result = analyze_stock(t['symbol'], t['entry_date'], t['entry_price'])
    if result:
        result['pnl'] = t['pnl_pct']
        result['sl_pct'] = t['sl_pct']
        result['score'] = t['score']
        results.append(result)

# แสดงผลวิเคราะห์
print("\n" + "=" * 80)
print("ผลวิเคราะห์ ROOT CAUSE")
print("=" * 80)

for r in results:
    print(f"\n### {r['symbol']} ({r['entry_date']}) - ขาดทุน {r['pnl']:.2f}% ###")
    print(f"    Score: {r['score']}")
    print(f"    Entry: ${r['entry_price']:.2f}")
    print()
    print(f"    Technical ณ วัน Entry:")
    print(f"      RSI: {r['rsi_at_entry']:.1f}" if r['rsi_at_entry'] else "      RSI: N/A")
    print(f"      Above SMA20: {'Yes' if r['above_sma20'] else 'No'}" if r['above_sma20'] is not None else "      Above SMA20: N/A")
    print(f"      Above SMA50: {'Yes' if r['above_sma50'] else 'No'}" if r['above_sma50'] is not None else "      Above SMA50: N/A")
    print(f"      Volume Ratio: {r['volume_ratio']:.2f}x" if r['volume_ratio'] else "      Volume Ratio: N/A")
    print(f"      ATR%: {r['atr_pct']:.2f}%" if r['atr_pct'] else "      ATR%: N/A")
    print()
    print(f"    Price Action ก่อน Entry (5 วัน):")
    print(f"      Change: {r['pre_5d_change']:+.2f}%" if r['pre_5d_change'] else "      Change: N/A")
    print()
    print(f"    Price Action หลัง Entry:")
    print(f"      Max Gain: {r['post_max_gain']:+.2f}%" if r['post_max_gain'] else "      Max Gain: N/A")
    print(f"      Max Loss: {r['post_max_loss']:+.2f}%" if r['post_max_loss'] else "      Max Loss: N/A")
    print(f"      Day 1 Change: {r['post_day1_change']:+.2f}%" if r['post_day1_change'] else "      Day 1: N/A")
    print()
    print(f"    Entry Day Pattern:")
    print(f"      Gap: {r['entry_gap']:+.2f}%" if r['entry_gap'] else "      Gap: N/A")
    print(f"      Candle Body: {r['entry_candle_body']:+.2f}%" if r['entry_candle_body'] else "      Body: N/A")

    # วิเคราะห์สาเหตุ
    causes = []
    if r['rsi_at_entry'] and r['rsi_at_entry'] > 70:
        causes.append("RSI Overbought (>70)")
    if r['rsi_at_entry'] and r['rsi_at_entry'] < 30:
        causes.append("RSI Oversold (<30) - อาจยังลงต่อ")
    if r['above_sma20'] == False:
        causes.append("Below SMA20 - Downtrend")
    if r['above_sma50'] == False:
        causes.append("Below SMA50 - Major Downtrend")
    if r['pre_5d_change'] and r['pre_5d_change'] < -5:
        causes.append(f"ลงมาแรงก่อน entry ({r['pre_5d_change']:.1f}%)")
    if r['entry_gap'] and r['entry_gap'] < -1:
        causes.append(f"Gap Down ที่ entry ({r['entry_gap']:.1f}%)")
    if r['volume_ratio'] and r['volume_ratio'] > 2:
        causes.append(f"Volume Spike ({r['volume_ratio']:.1f}x) - อาจเป็น panic selling")
    if r['post_max_gain'] and r['post_max_gain'] < 2:
        causes.append(f"ไม่เคยขึ้นเลย (max {r['post_max_gain']:.1f}%)")
    if r['post_day1_change'] and r['post_day1_change'] < -2:
        causes.append(f"Day 1 ลงแรง ({r['post_day1_change']:.1f}%)")

    print()
    print(f"    🔍 สาเหตุที่เป็นไปได้:")
    if causes:
        for c in causes:
            print(f"       - {c}")
    else:
        print(f"       - ไม่พบ pattern ชัดเจน")

# สรุป pattern ที่พบ
print("\n" + "=" * 80)
print("สรุป COMMON PATTERNS ของหุ้นที่โดน SL")
print("=" * 80)

# นับ pattern
below_sma20 = sum(1 for r in results if r['above_sma20'] == False)
below_sma50 = sum(1 for r in results if r['above_sma50'] == False)
rsi_low = sum(1 for r in results if r['rsi_at_entry'] and r['rsi_at_entry'] < 40)
rsi_high = sum(1 for r in results if r['rsi_at_entry'] and r['rsi_at_entry'] > 60)
gap_down = sum(1 for r in results if r['entry_gap'] and r['entry_gap'] < -1)
never_up = sum(1 for r in results if r['post_max_gain'] and r['post_max_gain'] < 2)
day1_drop = sum(1 for r in results if r['post_day1_change'] and r['post_day1_change'] < -2)

total = len(results)
print(f"\nจาก {total} trades ที่โดน SL:")
print(f"  - Below SMA20 (Downtrend): {below_sma20}/{total} ({below_sma20/total*100:.0f}%)")
print(f"  - Below SMA50 (Major Downtrend): {below_sma50}/{total} ({below_sma50/total*100:.0f}%)")
print(f"  - RSI < 40 (Weak): {rsi_low}/{total} ({rsi_low/total*100:.0f}%)")
print(f"  - RSI > 60 (Strong): {rsi_high}/{total} ({rsi_high/total*100:.0f}%)")
print(f"  - Gap Down at entry: {gap_down}/{total} ({gap_down/total*100:.0f}%)")
print(f"  - Never went up 2%+: {never_up}/{total} ({never_up/total*100:.0f}%)")
print(f"  - Day 1 dropped > 2%: {day1_drop}/{total} ({day1_drop/total*100:.0f}%)")

# แนะนำ filter
print("\n" + "=" * 80)
print("แนะนำ FILTER เพิ่มเติม")
print("=" * 80)

print("""
จาก Root Cause Analysis พบว่าหุ้นที่โดน SL มักมี pattern:

1. Below SMA20/SMA50 → อยู่ใน downtrend
   แนะนำ: Entry เฉพาะหุ้นที่ > SMA20

2. RSI ต่ำ → momentum อ่อน
   แนะนำ: Entry เฉพาะ RSI > 40

3. Gap Down at entry → sentiment แย่
   แนะนำ: หลีกเลี่ยง gap down > 1%

4. Day 1 ลงแรง → false bounce
   แนะนำ: ถ้า Day 1 ลง > 2% ให้ออกเลย (ไม่รอ SL)

5. ไม่เคยขึ้นเลย → wrong stock selection
   แนะนำ: เพิ่ม momentum filter
""")

# บันทึกผล
with open('root_cause_results.json', 'w') as f:
    json.dump(results, f, indent=2)
print("\nResults saved to: root_cause_results.json")
