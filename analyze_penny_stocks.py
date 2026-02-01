#!/usr/bin/env python3
"""
Analyze the list of stocks that user mentioned - check what type they are
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def analyze_stocks():
    """Analyze the mystery stocks"""

    symbols = [
        'SOPA', 'PCLA', 'AFJK', 'ASPC', 'EKSO', 'OMER',
        'EUDA', 'DLXY', 'TROO', 'LPCN', 'IZM', 'OPTX',
        'INAB', 'GRDX', 'ASBP', 'CHHN'
    ]

    print("\n" + "="*80)
    print("🔍 วิเคราะห์หุ้นลึกลับที่คุณเจอ")
    print("="*80)

    results = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period='1mo')

            if hist.empty:
                print(f"⚠️  {symbol}: No data")
                continue

            current_price = hist['Close'].iloc[-1]

            # Calculate returns
            returns = {}
            for days, label in [(1, '1d'), (5, '5d'), (7, '7d'), (20, '1m')]:
                if len(hist) > days:
                    old_price = hist['Close'].iloc[-days-1]
                    returns[label] = ((current_price - old_price) / old_price) * 100
                else:
                    returns[label] = 0

            # Get basic info
            market_cap = info.get('marketCap', 0)
            sector = info.get('sector', 'Unknown')
            industry = info.get('industry', 'Unknown')
            volume = hist['Volume'].iloc[-1]
            avg_volume = hist['Volume'].mean()

            # Calculate volatility
            price_returns = hist['Close'].pct_change().dropna()
            volatility = price_returns.std() * (252 ** 0.5) * 100 if len(price_returns) > 10 else 0

            results.append({
                'symbol': symbol,
                'price': current_price,
                'market_cap': market_cap,
                'sector': sector,
                'industry': industry,
                'return_1d': returns.get('1d', 0),
                'return_5d': returns.get('5d', 0),
                'return_7d': returns.get('7d', 0),
                'return_1m': returns.get('1m', 0),
                'volume': volume,
                'avg_volume': avg_volume,
                'volatility': volatility
            })

        except Exception as e:
            print(f"⚠️  {symbol}: Error - {e}")
            continue

    # Analysis
    if not results:
        print("\n❌ ไม่สามารถดึงข้อมูลได้")
        return

    # Sort by 7-day return
    results.sort(key=lambda x: x['return_7d'], reverse=True)

    # Display results
    print(f"\n📊 พบข้อมูล {len(results)}/{len(symbols)} ตัว")
    print("\n" + "="*80)

    # Check characteristics
    avg_price = sum(r['price'] for r in results) / len(results)
    avg_market_cap = sum(r['market_cap'] for r in results if r['market_cap'] > 0) / max(1, sum(1 for r in results if r['market_cap'] > 0))
    avg_volatility = sum(r['volatility'] for r in results) / len(results)

    penny_stocks = sum(1 for r in results if r['price'] < 5)
    micro_caps = sum(1 for r in results if 0 < r['market_cap'] < 300_000_000)

    print("\n🎯 ประเภทหุ้น:")
    print(f"   • ราคาเฉลี่ย: ${avg_price:.2f}")
    print(f"   • Market Cap เฉลี่ย: ${avg_market_cap/1e6:.1f}M")
    print(f"   • Volatility เฉลี่ย: {avg_volatility:.1f}%")
    print(f"   • Penny Stocks (< $5): {penny_stocks}/{len(results)} ตัว ({penny_stocks/len(results)*100:.0f}%)")
    print(f"   • Micro-cap (< $300M): {micro_caps}/{len(results)} ตัว ({micro_caps/len(results)*100:.0f}%)")

    # Sectors
    sectors = {}
    for r in results:
        sector = r['sector']
        if sector not in sectors:
            sectors[sector] = 0
        sectors[sector] += 1

    print(f"\n📈 Sectors:")
    for sector, count in sorted(sectors.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {sector}: {count} ตัว")

    # Show top performers
    print("\n" + "="*80)
    print("🚀 TOP PERFORMERS (7 วัน)")
    print("="*80)
    print(f"\n{'Rank':<6} {'Symbol':<8} {'Price':<10} {'1d':<10} {'7d':<10} {'1m':<10} {'Cap':<12} {'Sector':<20}")
    print("-" * 95)

    for i, r in enumerate(results[:10], 1):
        cap_str = f"${r['market_cap']/1e6:.1f}M" if r['market_cap'] > 0 else "N/A"
        print(f"{i:<6} {r['symbol']:<8} ${r['price']:<9.2f} {r['return_1d']:>7.1f}%  {r['return_7d']:>7.1f}%  {r['return_1m']:>7.1f}%  {cap_str:<12} {r['sector']:<20}")

    # Identify type
    print("\n" + "="*80)
    print("🏷️  หุ้นพวกนี้คือ...")
    print("="*80)

    if penny_stocks / len(results) > 0.7:
        print("\n✅ **PENNY STOCKS** (หุ้นราคาต่ำ < $5)")
        print("   - ลักษณะ: ราคาต่ำ, ความเสี่ยงสูง, volatile มาก")
        print("   - ใช้เงินลงทุนน้อย แต่อาจเสียหมด!")

    if micro_caps / len(results) > 0.6:
        print("\n✅ **MICRO-CAP STOCKS** (Market Cap < $300M)")
        print("   - ลักษณะ: บริษัทเล็ก, สภาพคล่องต่ำ")
        print("   - ง่ายต่อการ pump & dump")

    if avg_volatility > 100:
        print("\n✅ **HIGH VOLATILITY STOCKS** (Volatility > 100%)")
        print("   - ลักษณะ: ขึ้น-ลงรุนแรงมาก")
        print("   - ไม่เหมาะสำหรับคนรับความเสี่ยงต่ำ")

    # Check if biotech heavy
    biotech_count = sectors.get('Healthcare', 0)
    if biotech_count / len(results) > 0.5:
        print("\n✅ **BIOTECH/PHARMA STOCKS**")
        print("   - ลักษณะ: บริษัทยา/เทคโนโลยีชีวภาพ")
        print("   - ขึ้น-ลงตาม clinical trials, FDA approvals")
        print("   - เสี่ยงสูงมาก!")

    # Warning
    print("\n" + "="*80)
    print("⚠️  คำเตือน!")
    print("="*80)

    avg_return_7d = sum(r['return_7d'] for r in results) / len(results)

    if avg_return_7d > 20:
        print(f"\n🔥 หุ้นพวกนี้ขึ้นเฉลี่ย {avg_return_7d:.1f}% ใน 7 วัน!")
        print("   → อาจเป็น PUMP & DUMP scheme")
        print("   → อย่าไล่ซื้อ! อาจจะลงมาแรงเท่าๆ กับที่ขึ้น")

    print("\n💡 Penny Stocks มีความเสี่ยงสูงมาก:")
    print("   • ขาดสภาพคล่อง (ยากขาย)")
    print("   • ง่ายต่อการ manipulate ราคา")
    print("   • บริษัทมักขาดทุนหรือใกล้ล้มละลาย")
    print("   • 95% ของ penny stocks จะสูญเสียเงิน")
    print("   • ใช้เฉพาะเงินที่เสียหมดก็ได้!")

    print("\n🎯 ถ้าจะเล่น Penny Stocks:")
    print("   1. ลงทุนแค่ 1-2% ของพอร์ต")
    print("   2. ตั้ง stop loss เข้มงวด (-10% ขายทันที)")
    print("   3. ถ้ากำไร 20-30% ขายทันที (อย่าโลภ)")
    print("   4. อย่าหวังรวยข้ามคืน")
    print("   5. ระวัง pump & dump groups")

if __name__ == "__main__":
    analyze_stocks()
