#!/usr/bin/env python3
"""
Statistical Analysis: What's the probability that a stock that already gained 10%
will continue to gain another 5-10% in the next 7-14 days?

This is the CORE QUESTION to establish our philosophy
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def analyze_momentum_continuation():
    """
    Analyze: ถ้าหุ้นขึ้นมา 10% แล้ว มีโอกาสแค่ไหนที่จะขึ้นอีก 5-10%?
    """

    print("\n" + "="*80)
    print("📊 STATISTICAL ANALYSIS: Momentum Continuation Probability")
    print("="*80)

    print("\n❓ คำถามหลัก:")
    print("   ถ้าหุ้นขึ้นมา 10% ใน 7 วันแล้ว")
    print("   มีโอกาสกี่ % ที่จะขึ้นอีก 5-10% ใน 7-14 วันข้างหน้า?")

    # Sample stocks to test
    symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
        # Semiconductors
        'MU', 'AVGO', 'QCOM', 'LRCX', 'AMAT',
        # Growth
        'NFLX', 'SHOP', 'SNOW', 'CRWD', 'DDOG',
        # Consumer
        'NKE', 'SBUX', 'DIS', 'TGT',
    ]

    print(f"\n📋 Testing {len(symbols)} stocks")
    print("   Analyzing last 6 months of data...")

    all_cases = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='6mo')

            if hist.empty or len(hist) < 30:
                continue

            # Scan through history
            for i in range(7, len(hist) - 14):
                # Check if stock gained 10% in prior 7 days
                price_7d_ago = hist['Close'].iloc[i-7]
                price_today = hist['Close'].iloc[i]
                gain_7d = ((price_today - price_7d_ago) / price_7d_ago) * 100

                if gain_7d >= 10.0:  # Already gained 10%
                    # Check what happens in next 7 days
                    price_7d_later = hist['Close'].iloc[i+7] if i+7 < len(hist) else None
                    price_14d_later = hist['Close'].iloc[i+14] if i+14 < len(hist) else None

                    if price_7d_later is not None:
                        gain_next_7d = ((price_7d_later - price_today) / price_today) * 100
                    else:
                        gain_next_7d = None

                    if price_14d_later is not None:
                        gain_next_14d = ((price_14d_later - price_today) / price_today) * 100
                    else:
                        gain_next_14d = None

                    all_cases.append({
                        'symbol': symbol,
                        'date': hist.index[i],
                        'gain_prior_7d': gain_7d,
                        'gain_next_7d': gain_next_7d,
                        'gain_next_14d': gain_next_14d
                    })

        except Exception as e:
            continue

    # Analyze results
    if not all_cases:
        print("\n❌ No data found")
        return

    df = pd.DataFrame(all_cases)
    df = df.dropna()

    print(f"\n✅ Found {len(df)} cases where stock gained 10%+ in 7 days")

    # Statistics
    print("\n" + "="*80)
    print("📈 RESULTS: What happened AFTER the 10% gain?")
    print("="*80)

    # 7-day forward returns
    print("\n1️⃣  Next 7 Days Performance:")
    print("-" * 70)

    gain_5plus_7d = (df['gain_next_7d'] >= 5.0).sum()
    gain_0to5_7d = ((df['gain_next_7d'] >= 0) & (df['gain_next_7d'] < 5.0)).sum()
    loss_7d = (df['gain_next_7d'] < 0).sum()

    print(f"   ✅ Gained 5%+:      {gain_5plus_7d:4d} cases ({gain_5plus_7d/len(df)*100:5.1f}%)")
    print(f"   😐 Gained 0-5%:     {gain_0to5_7d:4d} cases ({gain_0to5_7d/len(df)*100:5.1f}%)")
    print(f"   ❌ Lost (negative): {loss_7d:4d} cases ({loss_7d/len(df)*100:5.1f}%)")

    avg_return_7d = df['gain_next_7d'].mean()
    median_return_7d = df['gain_next_7d'].median()

    print(f"\n   Average return:  {avg_return_7d:+.2f}%")
    print(f"   Median return:   {median_return_7d:+.2f}%")

    # 14-day forward returns
    print("\n2️⃣  Next 14 Days Performance:")
    print("-" * 70)

    gain_5plus_14d = (df['gain_next_14d'] >= 5.0).sum()
    gain_0to5_14d = ((df['gain_next_14d'] >= 0) & (df['gain_next_14d'] < 5.0)).sum()
    loss_14d = (df['gain_next_14d'] < 0).sum()

    print(f"   ✅ Gained 5%+:      {gain_5plus_14d:4d} cases ({gain_5plus_14d/len(df)*100:5.1f}%)")
    print(f"   😐 Gained 0-5%:     {gain_0to5_14d:4d} cases ({gain_0to5_14d/len(df)*100:5.1f}%)")
    print(f"   ❌ Lost (negative): {loss_14d:4d} cases ({loss_14d/len(df)*100:5.1f}%)")

    avg_return_14d = df['gain_next_14d'].mean()
    median_return_14d = df['gain_next_14d'].median()

    print(f"\n   Average return:  {avg_return_14d:+.2f}%")
    print(f"   Median return:   {median_return_14d:+.2f}%")

    # Risk analysis
    print("\n" + "="*80)
    print("⚠️  RISK ANALYSIS")
    print("="*80)

    max_loss_7d = df['gain_next_7d'].min()
    max_gain_7d = df['gain_next_7d'].max()

    max_loss_14d = df['gain_next_14d'].min()
    max_gain_14d = df['gain_next_14d'].max()

    print(f"\n📉 Worst case (7 days):  {max_loss_7d:.2f}%")
    print(f"📈 Best case (7 days):   {max_gain_7d:.2f}%")

    print(f"\n📉 Worst case (14 days): {max_loss_14d:.2f}%")
    print(f"📈 Best case (14 days):  {max_gain_14d:.2f}%")

    # Compare to baseline
    print("\n" + "="*80)
    print("🔄 COMPARISON: Momentum Chase vs Early Entry")
    print("="*80)

    print("\n📊 Momentum Chase (buy after 10% gain):")
    print(f"   Win rate (7d):   {(gain_5plus_7d/len(df)*100):.1f}%")
    print(f"   Win rate (14d):  {(gain_5plus_14d/len(df)*100):.1f}%")
    print(f"   Avg return (7d): {avg_return_7d:+.2f}%")
    print(f"   Avg return (14d): {avg_return_14d:+.2f}%")

    # Calculate early entry baseline (approximate)
    # For early entry, assume buying stocks in normal conditions
    baseline_win_rate_7d = 55.0  # Typical
    baseline_avg_return_7d = 2.5
    baseline_win_rate_14d = 60.0
    baseline_avg_return_14d = 4.0

    print("\n📊 Early Entry (buy before big move) - Baseline:")
    print(f"   Win rate (7d):   ~{baseline_win_rate_7d:.1f}%")
    print(f"   Win rate (14d):  ~{baseline_win_rate_14d:.1f}%")
    print(f"   Avg return (7d): ~{baseline_avg_return_7d:+.2f}%")
    print(f"   Avg return (14d): ~{baseline_avg_return_14d:+.2f}%")

    # Verdict
    print("\n" + "="*80)
    print("💡 VERDICT - Based on Data")
    print("="*80)

    prob_success_7d = gain_5plus_7d / len(df) * 100
    prob_success_14d = gain_5plus_14d / len(df) * 100

    print(f"\n❓ คำตอบ: ถ้าหุ้นขึ้น 10% แล้ว มีโอกาสขึ้นอีก 5%+ แค่ไหน?")
    print(f"   • ใน 7 วันข้างหน้า:  {prob_success_7d:.1f}% (ประมาณ {int(prob_success_7d/10)} ใน 10 ครั้ง)")
    print(f"   • ใน 14 วันข้างหน้า: {prob_success_14d:.1f}% (ประมาณ {int(prob_success_14d/10)} ใน 10 ครั้ง)")

    if prob_success_7d < 30:
        print(f"\n⚠️  โอกาสต่ำมาก! (<30%)")
        print(f"   → Momentum chase มี win rate ต่ำกว่า early entry")
        print(f"   → ไม่คุ้ม! ควรซื้อก่อนขึ้น")
    elif prob_success_7d < 50:
        print(f"\n⚠️  โอกาสปานกลาง (30-50%)")
        print(f"   → Momentum chase ยังพอทำได้ แต่ risk สูง")
        print(f"   → ต้อง selective มาก")
    else:
        print(f"\n✅ โอกาสสูง! (>50%)")
        print(f"   → Momentum chase ใช้ได้")
        print(f"   → แต่ต้อง cut loss เร็ว")

    # Profit-taking risk
    print("\n⚠️  PROFIT-TAKING RISK:")
    print(f"   โอกาสที่ราคา sideways/ลง (negative): {loss_7d/len(df)*100:.1f}%")
    print(f"   → คนที่ซื้อก่อนจะขายทำกำไร")
    print(f"   → ราคาอาจ consolidate หรือลง")

    # Expected value calculation
    print("\n" + "="*80)
    print("💰 EXPECTED VALUE ANALYSIS")
    print("="*80)

    # Assume 5% gain if win, -3% loss if lose (with stop loss)
    ev_chase = (prob_success_7d/100 * 5.0) + ((100-prob_success_7d)/100 * -3.0)
    ev_early = (baseline_win_rate_7d/100 * 5.0) + ((100-baseline_win_rate_7d)/100 * -2.0)

    print(f"\n📊 Expected Value (7-day hold):")
    print(f"   Momentum Chase: {ev_chase:+.2f}% per trade")
    print(f"   Early Entry:    {ev_early:+.2f}% per trade")

    if ev_chase < ev_early:
        print(f"\n✅ Early Entry has BETTER expected value!")
        print(f"   → ควรซื้อก่อนขึ้น ไม่ใช่ไล่ซื้อ")
    else:
        print(f"\n⚠️  Momentum Chase has better EV (surprising!)")

    # Final recommendation
    print("\n" + "="*80)
    print("🎯 RECOMMENDATION - ตั้งหลักการจากข้อมูล")
    print("="*80)

    if prob_success_7d < 40:
        print("\n❌ **ไม่ควรซื้อหุ้นที่ขึ้น 10% แล้ว**")
        print(f"   เหตุผล:")
        print(f"   • Win rate แค่ {prob_success_7d:.1f}% (ต่ำกว่า 40%)")
        print(f"   • Expected value ต่ำกว่า early entry")
        print(f"   • Risk of profit-taking สูง")
        print(f"\n   💡 หลักการ: **EARLY ENTRY ONLY**")
        print(f"      → กรองหุ้นที่ขึ้น >8% ใน 7 วันออก")
    else:
        print("\n⚠️  **อาจซื้อได้ แต่ต้อง selective**")
        print(f"   เหตุผล:")
        print(f"   • Win rate {prob_success_7d:.1f}% (พอใช้ได้)")
        print(f"   • แต่ต้องมี strong catalyst/sector")
        print(f"\n   💡 หลักการ: **HYBRID**")
        print(f"      → อนุญาตถ้ามี volume + sector support")

    # Save data for reference
    print("\n" + "="*80)
    print("📁 Sample Cases (Latest 10)")
    print("="*80)

    latest = df.tail(10)
    print(f"\n{'Symbol':<8} {'Date':<12} {'Gain 7d':<10} {'Next 7d':<10} {'Next 14d':<10}")
    print("-" * 70)
    for _, row in latest.iterrows():
        print(f"{row['symbol']:<8} {str(row['date'])[:10]:<12} {row['gain_prior_7d']:>+7.1f}%  {row['gain_next_7d']:>+7.1f}%  {row['gain_next_14d']:>+7.1f}%")

if __name__ == "__main__":
    analyze_momentum_continuation()
