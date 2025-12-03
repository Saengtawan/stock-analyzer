"""
🎯 Demo: Anti-Stop Hunt Features
แสดงการใช้งาน features ใหม่ที่เพิ่มเข้ามาเพื่อป้องกันการถูกล่า Stop Loss

Features ที่จะ demo:
1. Adaptive ATR Multiplier - ปรับ SL ตาม volatility
2. Anti-Hunt SL Placement - หลีกเลขกลมและ MA levels
3. Liquidity Grab Detector - ตรวจจับการกวาด SL
4. Stop Loss Heatmap - แสดงจุดอันตราย
5. Position Sizing based on SL - คำนวณ shares ตาม SL distance
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import features
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer
from src.analysis.enhanced_features import (
    LiquidityGrabDetector,
    format_liquidity_grab,
    StopLossHeatmap,
    format_sl_heatmap
)


def create_sample_price_data(base_price: float = 150.0, days: int = 60) -> pd.DataFrame:
    """สร้างข้อมูลราคาตัวอย่าง"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

    # สร้างราคาแบบ trending + noise
    trend = np.linspace(0, 20, days)  # Uptrend 20 points
    noise = np.random.randn(days) * 2  # Random noise
    close = base_price + trend + noise

    # สร้าง OHLC
    high = close + np.random.rand(days) * 2
    low = close - np.random.rand(days) * 2
    open_price = close + (np.random.rand(days) - 0.5) * 1.5

    # Volume
    volume = np.random.randint(1000000, 5000000, days)

    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })

    df.set_index('date', inplace=True)
    return df


def create_liquidity_grab_scenario(base_price: float = 150.0) -> pd.DataFrame:
    """
    สร้าง scenario ที่มีการ liquidity grab

    Pattern: ราคาลงไปแตะ support แล้วกลับขึ้นทันที (Long Wick)
    """
    dates = pd.date_range(end=datetime.now(), periods=10, freq='H')

    # ปกติ: ราคาอยู่ที่ 150-152
    closes = [150, 151, 152, 151, 150.5, 151, 150, 148, 150.5, 151.5]

    # แต่ candle ที่ 8 (index=7) มี long lower wick (liquidity grab!)
    opens = [150, 150.5, 151.5, 151.5, 151, 150.5, 150.5, 148.5, 149, 151]
    highs = [151, 152, 152.5, 152, 151.5, 151.5, 151, 149, 151, 152]
    lows = [149.5, 150, 151, 150.5, 150, 150, 149, 145, 148.5, 150.5]  # Candle 8: low ที่ 145!

    # Note: Candle 8 มี:
    # - Open: 148.5
    # - High: 149
    # - Low: 145 (ลงไปล่า SL!)
    # - Close: 150.5 (กลับขึ้นเหนือ open)
    # = Long lower wick!

    volume = np.random.randint(500000, 2000000, 10)

    df = pd.DataFrame({
        'date': dates,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volume
    })

    df.set_index('date', inplace=True)
    return df


def demo_1_adaptive_stop_loss():
    """
    Demo 1: Adaptive Stop Loss
    แสดงการคำนวณ SL ที่ปรับตาม volatility และหลีกเลขกลม
    """
    print("\n" + "="*80)
    print("🎯 DEMO 1: Adaptive Stop Loss with Anti-Hunt Protection")
    print("="*80)

    # สร้างข้อมูล
    price_data = create_sample_price_data(base_price=150.0, days=60)

    # สร้าง TechnicalAnalyzer
    analyzer = TechnicalAnalyzer(price_data)

    # คำนวณ indicators
    indicators = analyzer.calculate_basic_indicators(price_data)

    current_price = indicators['current_price']
    atr = indicators.get('atr', current_price * 0.02)

    print(f"\n📊 Current Price: ${current_price:.2f}")
    print(f"📊 ATR: ${atr:.2f} ({(atr/current_price)*100:.2f}%)")

    # เปรียบเทียบ: SL แบบเดิม vs แบบใหม่

    # แบบเดิม: ATR * 1.5 แบบตายตัว
    old_sl = current_price - (atr * 1.5)
    print(f"\n❌ OLD METHOD: SL = ${old_sl:.2f} (ATR * 1.5 แบบตายตัว)")

    # แบบใหม่: Adaptive + Anti-Hunt
    adaptive_multiplier = analyzer._get_adaptive_atr_multiplier(current_price, atr)
    new_sl = current_price - (atr * adaptive_multiplier)
    print(f"✅ NEW METHOD: SL = ${new_sl:.2f} (Adaptive ATR * {adaptive_multiplier})")

    # Apply anti-hunt logic
    anti_hunt_sl = analyzer._avoid_round_numbers(new_sl, atr, direction='down')
    print(f"🆕 ANTI-HUNT SL: ${anti_hunt_sl:.2f} (หลีกเลขกลม)")

    # Validate
    ma_levels = {
        'sma_50': indicators.get('sma_50'),
        'sma_200': indicators.get('sma_200'),
        'ema_50': indicators.get('ema_50'),
        'ema_200': indicators.get('ema_200')
    }

    validation = analyzer._validate_stop_loss(
        stop_loss=anti_hunt_sl,
        entry_price=current_price,
        support_level=current_price * 0.95,
        ma_levels=ma_levels,
        atr=atr,
        current_price=current_price
    )

    if validation['warnings']:
        print(f"\n⚠️ WARNINGS:")
        for warning in validation['warnings']:
            print(f"   {warning}")
    else:
        print(f"\n✅ SL Validation: PASSED")

    # Position Sizing
    print(f"\n💰 Position Sizing (ตาม SL distance):")
    account_value = 100000  # 100k บาท
    position_info = analyzer._calculate_position_size_for_sl(
        account_value=account_value,
        entry_price=current_price,
        stop_loss=anti_hunt_sl,
        risk_per_trade_pct=3.0
    )

    print(f"   Account: ${account_value:,.0f}")
    print(f"   Shares: {position_info['shares']} หุ้น")
    print(f"   Position Value: ${position_info['position_value']:,.2f} ({position_info['position_value_pct']:.1f}%)")
    print(f"   Risk Amount: ${position_info['risk_amount']:,.2f} ({position_info['risk_pct']:.1f}%)")
    print(f"   Max Loss if SL hit: ${position_info['max_loss_if_hit_sl']:,.2f}")


def demo_2_liquidity_grab_detection():
    """
    Demo 2: Liquidity Grab Detection
    ตรวจจับการกวาด Stop Loss
    """
    print("\n" + "="*80)
    print("🎯 DEMO 2: Liquidity Grab Detection")
    print("="*80)

    # สร้าง scenario ที่มี liquidity grab
    price_data = create_liquidity_grab_scenario(base_price=150.0)

    print(f"\n📊 Recent Candles (Last 5):")
    print(price_data[['open', 'high', 'low', 'close']].tail(5).to_string())

    # ใช้ LiquidityGrabDetector
    detector = LiquidityGrabDetector(symbol='TEST')

    result = detector.detect(
        price_data=price_data,
        support_level=149.0,
        resistance_level=153.0,
        atr=2.5
    )

    # แสดงผล
    print(format_liquidity_grab(result))

    if result['detected']:
        print(f"\n🎯 Action: {result['action_recommendation']}")
        print(f"📍 Suggested Entry: ${result['primary_signal']['suggested_entry']:.2f}")
        print(f"⛔ Invalidation: ${result['primary_signal']['invalidation']:.2f}")


def demo_3_stop_loss_heatmap():
    """
    Demo 3: Stop Loss Heatmap
    แสดงจุดที่มี Stop Loss กองอยู่เยอะ
    """
    print("\n" + "="*80)
    print("🎯 DEMO 3: Stop Loss Heatmap")
    print("="*80)

    current_price = 150.5

    # กำหนด Support/Resistance
    support_resistance = {
        'support': [145.0, 148.0],
        'resistance': [152.0, 155.0]
    }

    # MA levels
    ma_levels = {
        'sma_50': 149.5,
        'sma_200': 140.0,
        'ema_50': 150.0,
        'ema_200': 145.0
    }

    # Fibonacci levels
    fib_levels = {
        'fib_0.382': 147.5,
        'fib_0.500': 150.0,
        'fib_0.618': 152.5
    }

    atr = 2.5

    # สร้าง Heatmap
    heatmap = StopLossHeatmap(symbol='TEST')

    result = heatmap.generate_heatmap(
        current_price=current_price,
        support_resistance=support_resistance,
        ma_levels=ma_levels,
        atr=atr,
        fib_levels=fib_levels
    )

    # แสดงผล
    print(format_sl_heatmap(result))


def main():
    """Run all demos"""
    print("\n" + "🎯"*40)
    print("ANTI-STOP HUNT FEATURES DEMONSTRATION")
    print("Based on 'Stop Loss Hunting' insights from professional traders")
    print("🎯"*40)

    try:
        # Demo 1: Adaptive Stop Loss
        demo_1_adaptive_stop_loss()

        # Demo 2: Liquidity Grab Detection
        demo_2_liquidity_grab_detection()

        # Demo 3: Stop Loss Heatmap
        demo_3_stop_loss_heatmap()

        print("\n" + "="*80)
        print("✅ All demos completed successfully!")
        print("="*80)
        print("\n💡 Key Takeaways:")
        print("   1. ใช้ Adaptive ATR แทน fixed multiplier")
        print("   2. หลีกเลขกลมและ MA levels เมื่อวาง SL")
        print("   3. ตรวจจับ liquidity grab เพื่อหา entry opportunity")
        print("   4. ใช้ heatmap เพื่อหลีกเลี่ยง high-risk zones")
        print("   5. ปรับ position size ตาม SL distance")
        print("\n🎯 ไม่อยากโดนล่า Stop Loss? ใช้ features เหล่านี้!")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
