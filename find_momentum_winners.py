#!/usr/bin/env python3
"""
Find the OUTLIERS - stocks that gained 10% and CONTINUED to gain another 10%+
What made them different? Can we identify these cases?
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def find_momentum_winners():
    """
    Find cases where momentum CONTINUED - stocks that gained 10% then gained ANOTHER 10%+
    """

    print("\n" + "="*80)
    print("🔍 หาหุ้นที่พุ่งแล้วพุ่งอีก - มีจริงไหม? มี Pattern อะไร?")
    print("="*80)

    symbols = [
        # Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
        # Semiconductors
        'MU', 'AVGO', 'QCOM', 'LRCX', 'AMAT', 'KLAC', 'MRVL',
        # Growth
        'NFLX', 'SHOP', 'SNOW', 'CRWD', 'DDOG', 'NET', 'ZS',
        # AI/Cloud
        'PLTR', 'SMCI', 'IONQ',
        # Consumer
        'NKE', 'SBUX', 'DIS', 'TGT',
    ]

    print(f"\n📋 Analyzing {len(symbols)} stocks over 6 months...")

    all_cases = []
    winners = []
    losers = []

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
                    # Check what happens next
                    price_7d_later = hist['Close'].iloc[i+7] if i+7 < len(hist) else None
                    price_14d_later = hist['Close'].iloc[i+14] if i+14 < len(hist) else None

                    if price_7d_later is None or price_14d_later is None:
                        continue

                    gain_next_7d = ((price_7d_later - price_today) / price_today) * 100
                    gain_next_14d = ((price_14d_later - price_today) / price_today) * 100

                    # Calculate volume ratio
                    avg_volume_before = hist['Volume'].iloc[i-20:i].mean()
                    volume_today = hist['Volume'].iloc[i]
                    volume_ratio = volume_today / avg_volume_before if avg_volume_before > 0 else 1.0

                    # Calculate sector proxy (simplified - use SPY)
                    try:
                        spy = yf.Ticker('SPY')
                        spy_hist = spy.history(period='6mo')
                        # Find matching date
                        date = hist.index[i]
                        spy_price_7d_ago = None
                        spy_price_today = None

                        for j in range(len(spy_hist)):
                            if spy_hist.index[j].date() >= date.date():
                                if j >= 7:
                                    spy_price_7d_ago = spy_hist['Close'].iloc[j-7]
                                    spy_price_today = spy_hist['Close'].iloc[j]
                                break

                        if spy_price_7d_ago and spy_price_today:
                            spy_gain = ((spy_price_today - spy_price_7d_ago) / spy_price_7d_ago) * 100
                            relative_strength = gain_7d - spy_gain
                        else:
                            relative_strength = 0
                    except:
                        relative_strength = 0

                    case = {
                        'symbol': symbol,
                        'date': hist.index[i],
                        'gain_prior_7d': gain_7d,
                        'gain_next_7d': gain_next_7d,
                        'gain_next_14d': gain_next_14d,
                        'volume_ratio': volume_ratio,
                        'relative_strength': relative_strength
                    }

                    all_cases.append(case)

                    # Classify as winner or loser
                    if gain_next_7d >= 5.0:  # Continued to gain 5%+
                        winners.append(case)
                    else:
                        losers.append(case)

        except Exception as e:
            continue

    if not all_cases:
        print("\n❌ No data found")
        return

    print(f"\n✅ Found {len(all_cases)} total cases")
    print(f"   ✅ Winners (gained 5%+ more): {len(winners)} ({len(winners)/len(all_cases)*100:.1f}%)")
    print(f"   ❌ Losers (didn't gain 5%+):  {len(losers)} ({len(losers)/len(all_cases)*100:.1f}%)")

    # Analyze winners vs losers
    print("\n" + "="*80)
    print("📊 WINNERS vs LOSERS - มีความต่างอะไร?")
    print("="*80)

    df_winners = pd.DataFrame(winners)
    df_losers = pd.DataFrame(losers)

    print("\n1️⃣  Volume Characteristics:")
    print("-" * 70)
    avg_vol_winners = df_winners['volume_ratio'].mean()
    avg_vol_losers = df_losers['volume_ratio'].mean()

    print(f"   Winners avg volume ratio: {avg_vol_winners:.2f}x")
    print(f"   Losers avg volume ratio:  {avg_vol_losers:.2f}x")

    vol_high_winners = (df_winners['volume_ratio'] > 1.5).sum()
    vol_high_losers = (df_losers['volume_ratio'] > 1.5).sum()

    print(f"\n   Winners with volume >1.5x: {vol_high_winners}/{len(winners)} ({vol_high_winners/len(winners)*100:.1f}%)")
    print(f"   Losers with volume >1.5x:  {vol_high_losers}/{len(losers)} ({vol_high_losers/len(losers)*100:.1f}%)")

    print("\n2️⃣  Relative Strength (vs Market):")
    print("-" * 70)
    avg_rs_winners = df_winners['relative_strength'].mean()
    avg_rs_losers = df_losers['relative_strength'].mean()

    print(f"   Winners avg RS: {avg_rs_winners:+.2f}%")
    print(f"   Losers avg RS:  {avg_rs_losers:+.2f}%")

    rs_high_winners = (df_winners['relative_strength'] > 5.0).sum()
    rs_high_losers = (df_losers['relative_strength'] > 5.0).sum()

    print(f"\n   Winners with RS >5%: {rs_high_winners}/{len(winners)} ({rs_high_winners/len(winners)*100:.1f}%)")
    print(f"   Losers with RS >5%:  {rs_high_losers}/{len(losers)} ({rs_high_losers/len(losers)*100:.1f}%)")

    print("\n3️⃣  Initial Momentum Strength:")
    print("-" * 70)
    avg_momentum_winners = df_winners['gain_prior_7d'].mean()
    avg_momentum_losers = df_losers['gain_prior_7d'].mean()

    print(f"   Winners avg initial gain: {avg_momentum_winners:+.2f}%")
    print(f"   Losers avg initial gain:  {avg_momentum_losers:+.2f}%")

    strong_momentum_winners = (df_winners['gain_prior_7d'] > 15.0).sum()
    strong_momentum_losers = (df_losers['gain_prior_7d'] > 15.0).sum()

    print(f"\n   Winners with >15% initial: {strong_momentum_winners}/{len(winners)} ({strong_momentum_winners/len(winners)*100:.1f}%)")
    print(f"   Losers with >15% initial:  {strong_momentum_losers}/{len(losers)} ({strong_momentum_losers/len(losers)*100:.1f}%)")

    # Find the pattern
    print("\n" + "="*80)
    print("🎯 PATTERN RECOGNITION - หุ้นที่พุ่งต่อมี Pattern อะไร?")
    print("="*80)

    # Strong winners - those that gained 10%+ more
    strong_winners = [w for w in winners if w['gain_next_7d'] >= 10.0]

    print(f"\n💎 Super Winners (gained 10%+ MORE): {len(strong_winners)} cases")

    if strong_winners:
        df_strong = pd.DataFrame(strong_winners)

        print(f"\n   Characteristics:")
        print(f"   • Avg volume ratio:     {df_strong['volume_ratio'].mean():.2f}x")
        print(f"   • Avg relative strength: {df_strong['relative_strength'].mean():+.2f}%")
        print(f"   • Avg initial momentum:  {df_strong['gain_prior_7d'].mean():+.2f}%")

        # Find patterns
        high_vol_strong = (df_strong['volume_ratio'] > 2.0).sum()
        high_rs_strong = (df_strong['relative_strength'] > 8.0).sum()

        print(f"\n   Patterns:")
        print(f"   • Volume >2.0x:  {high_vol_strong}/{len(strong_winners)} ({high_vol_strong/len(strong_winners)*100:.1f}%)")
        print(f"   • RS >8%:        {high_rs_strong}/{len(strong_winners)} ({high_rs_strong/len(strong_winners)*100:.1f}%)")

        # Show examples
        print(f"\n   📋 Examples (Top 5):")
        print(f"   {'Symbol':<8} {'Date':<12} {'Init':<8} {'Next 7d':<10} {'Vol':<8} {'RS':<8}")
        print("   " + "-" * 70)

        sorted_strong = sorted(strong_winners, key=lambda x: x['gain_next_7d'], reverse=True)
        for case in sorted_strong[:5]:
            print(f"   {case['symbol']:<8} {str(case['date'])[:10]:<12} {case['gain_prior_7d']:>6.1f}%  {case['gain_next_7d']:>7.1f}%  {case['volume_ratio']:>6.2f}x  {case['relative_strength']:>+6.1f}%")

    # Test criteria
    print("\n" + "="*80)
    print("🧪 TESTING CRITERIA - ถ้ามีเงื่อนไข จะจับ winners ได้ไหม?")
    print("="*80)

    # Criteria 1: High volume + High RS
    print("\n1️⃣  Criteria: Volume >1.5x AND RS >5%")
    print("-" * 70)

    winners_match = sum(1 for w in winners if w['volume_ratio'] > 1.5 and w['relative_strength'] > 5.0)
    losers_match = sum(1 for l in losers if l['volume_ratio'] > 1.5 and l['relative_strength'] > 5.0)

    if winners_match + losers_match > 0:
        precision = winners_match / (winners_match + losers_match)
        recall = winners_match / len(winners)

        print(f"   Matched: {winners_match + losers_match} cases")
        print(f"   • Winners matched: {winners_match}/{len(winners)} (recall: {recall*100:.1f}%)")
        print(f"   • Losers matched:  {losers_match}/{len(losers)}")
        print(f"   • Precision: {precision*100:.1f}% (ถ้าผ่านเกณฑ์นี้ จะเป็น winner)")
        print(f"   • Win rate if applied: {precision*100:.1f}%")

    # Criteria 2: Very high volume
    print("\n2️⃣  Criteria: Volume >2.0x (Strong volume surge)")
    print("-" * 70)

    winners_match = sum(1 for w in winners if w['volume_ratio'] > 2.0)
    losers_match = sum(1 for l in losers if l['volume_ratio'] > 2.0)

    if winners_match + losers_match > 0:
        precision = winners_match / (winners_match + losers_match)
        recall = winners_match / len(winners)

        print(f"   Matched: {winners_match + losers_match} cases")
        print(f"   • Winners matched: {winners_match}/{len(winners)} (recall: {recall*100:.1f}%)")
        print(f"   • Losers matched:  {losers_match}/{len(losers)}")
        print(f"   • Precision: {precision*100:.1f}%")
        print(f"   • Win rate if applied: {precision*100:.1f}%")

    # Criteria 3: Very strong RS
    print("\n3️⃣  Criteria: RS >8% (Massive outperformance)")
    print("-" * 70)

    winners_match = sum(1 for w in winners if w['relative_strength'] > 8.0)
    losers_match = sum(1 for l in losers if l['relative_strength'] > 8.0)

    if winners_match + losers_match > 0:
        precision = winners_match / (winners_match + losers_match)
        recall = winners_match / len(winners)

        print(f"   Matched: {winners_match + losers_match} cases")
        print(f"   • Winners matched: {winners_match}/{len(winners)} (recall: {recall*100:.1f}%)")
        print(f"   • Losers matched:  {losers_match}/{len(losers)}")
        print(f"   • Precision: {precision*100:.1f}%")
        print(f"   • Win rate if applied: {precision*100:.1f}%")

    # Final recommendation
    print("\n" + "="*80)
    print("💡 RECOMMENDATION - ควรทำไง?")
    print("="*80)

    print("\n✅ มีหุ้นที่พุ่งแล้วพุ่งอีกจริง!")
    print(f"   พบ {len(winners)} cases ({len(winners)/len(all_cases)*100:.1f}%)")
    print(f"   Super winners (>10% more): {len(strong_winners)} cases")

    print("\n📌 แต่ต้องมีเงื่อนไขพิเศษ:")

    # Find best criteria
    criteria_tested = [
        ("Volume >1.5x AND RS >5%", 1.5, 5.0),
        ("Volume >2.0x", 2.0, None),
        ("RS >8%", None, 8.0),
    ]

    best_precision = 0
    best_criteria = None

    for name, vol_threshold, rs_threshold in criteria_tested:
        winners_match = 0
        losers_match = 0

        for w in winners:
            if vol_threshold and rs_threshold:
                if w['volume_ratio'] > vol_threshold and w['relative_strength'] > rs_threshold:
                    winners_match += 1
            elif vol_threshold:
                if w['volume_ratio'] > vol_threshold:
                    winners_match += 1
            elif rs_threshold:
                if w['relative_strength'] > rs_threshold:
                    winners_match += 1

        for l in losers:
            if vol_threshold and rs_threshold:
                if l['volume_ratio'] > vol_threshold and l['relative_strength'] > rs_threshold:
                    losers_match += 1
            elif vol_threshold:
                if l['volume_ratio'] > vol_threshold:
                    losers_match += 1
            elif rs_threshold:
                if l['relative_strength'] > rs_threshold:
                    losers_match += 1

        if winners_match + losers_match > 0:
            precision = winners_match / (winners_match + losers_match)
            if precision > best_precision:
                best_precision = precision
                best_criteria = (name, precision, winners_match, losers_match)

    if best_criteria:
        name, precision, w_match, l_match = best_criteria
        print(f"\n   🏆 Best criteria: {name}")
        print(f"      → Win rate: {precision*100:.1f}%")
        print(f"      → Catches {w_match}/{len(winners)} winners")

        if precision > 0.50:
            print(f"\n   ✅ Win rate >50% - ใช้ได้!")
            print(f"      → อนุญาตหุ้นที่ขึ้น >10% แล้ว ถ้าผ่านเกณฑ์นี้")
        else:
            print(f"\n   ⚠️  Win rate <50% - ยังไม่ดีพอ")
            print(f"      → ไม่ควรใช้")

    print("\n🎯 Final Strategy:")
    if best_precision > 0.50:
        print("   ✅ HYBRID APPROACH")
        print("      1. Default: กรองหุ้นที่ขึ้น >8% ออก")
        print(f"      2. Exception: อนุญาตถ้า {best_criteria[0]}")
        print(f"      3. Win rate จะเป็น: ~{best_precision*100:.0f}%")
    else:
        print("   ✅ STRICT EARLY ENTRY")
        print("      1. กรองหุ้นที่ขึ้น >8% ออกทั้งหมด")
        print("      2. ไม่มี exception (เพราะไม่มี criteria ที่ win rate >50%)")
        print("      3. Win rate จะเป็น: ~55%")

if __name__ == "__main__":
    find_momentum_winners()
