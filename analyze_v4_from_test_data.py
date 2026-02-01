#!/usr/bin/env python3
"""
วิเคราะห์ v4.0 จากข้อมูลการทดสอบจริง
ใช้ผลที่ได้จากการทดสอบ 20 หุ้น (10 ผ่าน v4.0, 10 ไม่ผ่าน)
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

print("=" * 100)
print("📊 วิเคราะห์ v4.0 จากข้อมูลการทดสอบจริง")
print("=" * 100)
print()

# ข้อมูลจากการทดสอบจริง (detailed_v3_v4_comparison.py)
test_results = [
    # หุ้นที่ผ่าน v4.0 (10 หุ้น)
    {'symbol': 'MU', 'entry_score': 115.5, 'momentum': 90.0, 'rsi': 59.0, 'ma50': 19.0, 'mom30d': 25.0, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'LRCX', 'entry_score': 109.7, 'momentum': 82.0, 'rsi': 52.8, 'ma50': 7.6, 'mom30d': 19.7, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'ARWR', 'entry_score': 100.3, 'momentum': 74.1, 'rsi': 42.9, 'ma50': 26.5, 'mom30d': 64.0, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'SNPS', 'entry_score': 97.2, 'momentum': 68.0, 'rsi': 46.7, 'ma50': 6.9, 'mom30d': 22.4, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'EXAS', 'entry_score': 95.4, 'momentum': 71.0, 'rsi': 56.5, 'ma50': 17.8, 'mom30d': 45.8, 'alt_data': 1, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'CRM', 'entry_score': 89.4, 'momentum': 67.0, 'rsi': 52.2, 'ma50': 6.0, 'mom30d': 13.6, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'GOOGL', 'entry_score': 85.0, 'momentum': 63.0, 'rsi': 41.6, 'ma50': 5.6, 'mom30d': 10.2, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'META', 'entry_score': 67.8, 'momentum': 48.0, 'rsi': 56.3, 'ma50': 1.0, 'mom30d': 10.5, 'alt_data': 0, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'ZM', 'entry_score': 53.2, 'momentum': 36.1, 'rsi': 44.1, 'ma50': 1.3, 'mom30d': 6.1, 'alt_data': 1, 'passed_v4': True, 'passed_v3': False},
    {'symbol': 'OKTA', 'entry_score': 50.3, 'momentum': 31.1, 'rsi': 38.9, 'ma50': 0.2, 'mom30d': 6.7, 'alt_data': 2, 'passed_v4': True, 'passed_v3': False},
    
    # หุ้นที่ไม่ผ่าน v4.0 (6 หุ้นที่รู้เหตุผล)
    {'symbol': 'NVDA', 'entry_score': 0, 'momentum': 0, 'rsi': 0, 'ma50': 0, 'mom30d': 2.8, 'alt_data': 0, 'passed_v4': False, 'passed_v3': False, 'reject_reason': 'Weak 30d momentum'},
    {'symbol': 'AAPL', 'entry_score': 0, 'momentum': 0, 'rsi': 31.3, 'ma50': 0, 'mom30d': 0, 'alt_data': 0, 'passed_v4': False, 'passed_v3': False, 'reject_reason': 'RSI too low'},
    {'symbol': 'MSFT', 'entry_score': 0, 'momentum': 0, 'rsi': 0, 'ma50': 0, 'mom30d': -1.9, 'alt_data': 0, 'passed_v4': False, 'passed_v3': False, 'reject_reason': 'Weak 30d momentum'},
    {'symbol': 'AMZN', 'entry_score': 0, 'momentum': 0, 'rsi': 0, 'ma50': 0, 'mom30d': 3.7, 'alt_data': 0, 'passed_v4': False, 'passed_v3': False, 'reject_reason': 'Weak 30d momentum'},
    {'symbol': 'AMD', 'entry_score': 0, 'momentum': 0, 'rsi': 0, 'ma50': -6.0, 'mom30d': 0, 'alt_data': 0, 'passed_v4': False, 'passed_v3': False, 'reject_reason': 'Below MA50'},
    {'symbol': 'NFLX', 'entry_score': 0, 'momentum': 0, 'rsi': 0, 'ma50': -10.2, 'mom30d': 0, 'alt_data': 0, 'passed_v4': False, 'passed_v3': False, 'reject_reason': 'Below MA50'},
]

print("✅ ข้อมูล: 16 หุ้น (10 ผ่าน v4.0, 6 ไม่ผ่าน)")
print()

# Get 30-day performance for all stocks
print("🔍 กำลังดาวน์โหลดข้อมูลราคา 30 วันที่ผ่านมา...")
print()

end_date = datetime.now()
start_date = end_date - timedelta(days=60)

for stock in test_results:
    symbol = stock['symbol']
    try:
        data = yf.download(symbol, start=start_date, end=end_date, progress=False)
       
        if len(data) < 30:
            continue
        
        entry_price = float(data['Close'].iloc[-30])
        current_price = float(data['Close'].iloc[-1])
        peak_price = float(data['High'].iloc[-30:].max())
        
        # Calculate returns
        current_return = ((current_price - entry_price) / entry_price) * 100
        peak_return = ((peak_price - entry_price) / entry_price) * 100
        
        # Find days to 5%
        data_30d = data.iloc[-30:].copy()
        data_30d['return'] = ((data_30d['Close'] - entry_price) / entry_price) * 100
        reached_5pct = data_30d[data_30d['return'] >= 5.0]
        days_to_target = len(reached_5pct) > 0 and (reached_5pct.index[0] - data_30d.index[0]).days or None
        
        # Store results
        stock['entry_price'] = entry_price
        stock['current_price'] = current_price
        stock['peak_price'] = peak_price
        stock['current_return'] = current_return
        stock['peak_return'] = peak_return
        stock['days_to_5pct'] = days_to_target
        stock['reached_5pct'] = len(reached_5pct) > 0
        stock['is_winner'] = current_return >= 5.0
        
        status = "✅" if stock['is_winner'] else "❌"
        print(f"  {status} {symbol}: {current_return:+.1f}% (Peak: {peak_return:+.1f}%)")
        
    except Exception as e:
        print(f"  ⚠️  {symbol}: Error - {e}")
        continue

print()
print("=" * 100)
print("📊 1️⃣  V4.0 PERFORMANCE")
print("=" * 100)
print()

# Filter stocks that passed v4.0 and have performance data
v4_passed = [s for s in test_results if s['passed_v4'] and 'current_return' in s]

if len(v4_passed) > 0:
    winners = [s for s in v4_passed if s['is_winner']]
    losers = [s for s in v4_passed if not s['is_winner']]
    
    win_rate = (len(winners) / len(v4_passed)) * 100
    avg_return = sum(s['current_return'] for s in v4_passed) / len(v4_passed)
    avg_winner = sum(s['current_return'] for s in winners) / len(winners) if winners else 0
    avg_loser = sum(s['current_return'] for s in losers) / len(losers) if losers else 0
    
    print(f"Total Trades: {len(v4_passed)}")
    print(f"Winners: {len(winners)} ({win_rate:.1f}%)")
    print(f"Losers: {len(losers)} ({100-win_rate:.1f}%)")
    print()
    print(f"Avg Return (All): {avg_return:+.1f}%")
    print(f"Avg Return (Winners): {avg_winner:+.1f}%")
    print(f"Avg Return (Losers): {avg_loser:+.1f}%")
    print()
    
    # Best/Worst
    best = max(v4_passed, key=lambda x: x['current_return'])
    worst = min(v4_passed, key=lambda x: x['current_return'])
    print(f"Best: {best['symbol']} {best['current_return']:+.1f}%")
    print(f"Worst: {worst['symbol']} {worst['current_return']:+.1f}%")
    
print()
print("=" * 100)
print("📊 2️⃣  FALSE POSITIVES (หุ้นไม่ดีที่หลุดเข้ามา)")
print("=" * 100)
print()

if losers:
    print(f"พบหุ้นขาดทุน {len(losers)} ตัว:")
    print()
    print(f"{'Symbol':<8} {'Return':>8} {'Momentum':>10} {'RSI':>6} {'MA50':>8} {'Mom30d':>9} {'Alt':>5}")
    print("-" * 100)
    
    for stock in sorted(losers, key=lambda x: x['current_return']):
        print(f"{stock['symbol']:<8} {stock['current_return']:>+7.1f}% {stock['momentum']:>9.1f} "
              f"{stock['rsi']:>6.1f} {stock['ma50']:>+7.1f}% {stock['mom30d']:>+8.1f}% "
              f"{stock['alt_data']:>2}/6")
    
    print()
    print("💡 Insights:")
    
    # Analyze
    avg_mom_losers = sum(s['momentum'] for s in losers) / len(losers)
    avg_mom_winners = sum(s['momentum'] for s in winners) / len(winners) if winners else 0
    
    print(f"   Avg Momentum: Winners {avg_mom_winners:.1f} vs Losers {avg_mom_losers:.1f} (diff: {avg_mom_winners - avg_mom_losers:+.1f})")
    
    # Would v3.3 catch these?
    losers_v3_pass = [s for s in losers if s['alt_data'] >= 3]
    print(f"   ⚠️  {len(losers_v3_pass)}/{len(losers)} losers would ALSO pass v3.3!")
else:
    print("🎉 NO FALSE POSITIVES! ไม่มีหุ้นขาดทุน!")

print()
print("=" * 100)
print("📊 3️⃣  ALT DATA CORRELATION")
print("=" * 100)
print()

# Group by alt data
print("Alt Data vs Performance:")
print()

for alt in range(0, 7):
    subset = [s for s in v4_passed if s['alt_data'] == alt]
    if not subset:
        continue
    
    win_count = len([s for s in subset if s['is_winner']])
    win_rate_alt = (win_count / len(subset)) * 100 if subset else 0
    avg_ret_alt = sum(s['current_return'] for s in subset) / len(subset) if subset else 0
    
    print(f"Alt Data {alt}/6: {len(subset):>2} trades | Win Rate: {win_rate_alt:>5.1f}% | Avg Return: {avg_ret_alt:>+6.1f}%")

print()

# Correlation
if len(v4_passed) > 1:
    import numpy as np
    
    alt_values = [s['alt_data'] for s in v4_passed]
    returns = [s['current_return'] for s in v4_passed]
    momentum_values = [s['momentum'] for s in v4_passed]
    
    alt_corr = np.corrcoef(alt_values, returns)[0, 1]
    mom_corr = np.corrcoef(momentum_values, returns)[0, 1]
    
    print("📈 Correlation with Returns:")
    print(f"   Alt Data:     {alt_corr:+.3f} {'✅ Good' if alt_corr > 0.3 else '⚠️  Weak' if abs(alt_corr) < 0.2 else '❌ Negative' if alt_corr < 0 else '⚪ Moderate'}")
    print(f"   Momentum:     {mom_corr:+.3f} {'✅ Good' if mom_corr > 0.3 else '⚠️  Weak' if abs(mom_corr) < 0.2 else '❌ Negative' if mom_corr < 0 else '⚪ Moderate'}")
    print()
    
    if abs(alt_corr) < 0.2:
        print("💡 Alt Data มีความสัมพันธ์ต่ำมากกับผลตอบแทน → ทำไมถึงไม่สัมพันธ์:")
        print("   1. Alt data อาจล่าช้า (lagging indicator)")
        print("   2. Alt data coverage ไม่ครอบคลุมทุกหุ้น")
        print("   3. Momentum เป็น leading indicator ที่ดีกว่า")
    elif alt_corr < 0:
        print("⚠️  Alt Data มีความสัมพันธ์เชิงลบ! (มากขึ้น = แย่ลง)")

print()
print("=" * 100)
print("📊 4️⃣  DAYS TO TARGET (ถึง 5% ใช้เวลากี่วัน)")
print("=" * 100)
print()

reached_target = [s for s in v4_passed if s['reached_5pct']]

print(f"Reached 5%+: {len(reached_target)}/{len(v4_passed)} ({len(reached_target)/len(v4_passed)*100:.1f}%)")

if reached_target:
    days = [s['days_to_5pct'] for s in reached_target if s['days_to_5pct'] is not None]
    
    if days:
        avg_days = sum(days) / len(days)
        min_days = min(days)
        max_days = max(days)
        
        print()
        print(f"Average: {avg_days:.1f} วัน")
        print(f"Fastest: {min_days} วัน")
        print(f"Slowest: {max_days} วัน")
        print()
        
        print("📊 Distribution:")
        bins = [(0,3), (4,7), (8,14), (15,21), (22,30)]
        for low, high in bins:
            count = len([d for d in days if low <= d <= high])
            pct = (count / len(days)) * 100 if days else 0
            bar = '█' * int(pct / 3)
            label = f"{low}-{high} วัน"
            print(f"   {label:<12}: {count:>2} trades ({pct:>5.1f}%) {bar}")

print()
print("=" * 100)
print("✅ SUMMARY")
print("=" * 100)
print()

if len(v4_passed) > 0:
    print(f"1️⃣  v4.0 Performance:")
    print(f"   Win Rate: {win_rate:.1f}%")
    print(f"   Avg Return: {avg_return:+.1f}%")
    print(f"   {'✅ EXCELLENT!' if win_rate >= 80 else '✅ GOOD!' if win_rate >= 70 else '⚠️  Needs improvement'}")
    print()
    
    print(f"2️⃣  False Positives:")
    print(f"   Losers: {len(losers)}/{len(v4_passed)} ({len(losers)/len(v4_passed)*100:.1f}%)")
    print(f"   {'✅ Very low!' if len(losers) <= 2 else '⚠️  Some losses'}")
    print()
    
    print(f"3️⃣  Alt Data:")
    print(f"   Correlation: {alt_corr:+.3f}")
    print(f"   {'⚠️  NOT predictive (ต่ำมาก)' if abs(alt_corr) < 0.2 else '✅ Predictive'}")
    print()
    
    if reached_target:
        print(f"4️⃣  Days to Target:")
        print(f"   Average: {avg_days:.1f} วัน")
        print(f"   → แนะนำ hold: {int(avg_days)+3}-{int(avg_days)+7} วัน")

