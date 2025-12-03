"""
Liquidity Grab Detector
ตรวจจับการ "กวาด Stop Loss" (Stop Hunt / Liquidity Grab)

Based on Stop Loss Hunting insights:
- สถาบันมักล่า SL ที่ support/resistance เพื่อหา liquidity
- หลังจากกวาดเสร็จมักจะกลับทิศทาง (reversal)
- เป็นจังหวะ entry ที่ดี
"""

from typing import Dict, Any, Optional, List
import pandas as pd
from datetime import datetime


class LiquidityGrabDetector:
    """
    ตรวจจับการกวาด Stop Loss (Liquidity Grab)

    รูปแบบที่ตรวจจับ:
    1. Long Wick (เงาเทียนยาว) - ราคาไปแตะแล้วกลับทันที
    2. Fake Breakout - ทะลุ support/resistance แล้วกลับเข้ามา
    3. Volume Spike - volume สูงขณะกวาด
    4. Quick Rejection - กลับทันทีภายใน 1-2 candles
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def detect(self,
              price_data: pd.DataFrame,
              support_level: Optional[float] = None,
              resistance_level: Optional[float] = None,
              atr: Optional[float] = None) -> Dict[str, Any]:
        """
        ตรวจจับ liquidity grab patterns

        Args:
            price_data: DataFrame with OHLCV data (ต้องมีอย่างน้อย 5 candles)
            support_level: Support level to watch
            resistance_level: Resistance level to watch
            atr: Average True Range (for validation)

        Returns:
            Dictionary with detection results
        """
        if len(price_data) < 5:
            return self._no_detection("Need at least 5 candles")

        latest_candle = price_data.iloc[-1]
        prev_candle = price_data.iloc[-2]

        current_price = latest_candle['close']

        # Default ATR if not provided
        if atr is None:
            atr = self._calculate_simple_atr(price_data)

        detections = []

        # Detection 1: Long Wick Pattern (bullish reversal)
        bullish_wick = self._detect_bullish_long_wick(latest_candle, atr)
        if bullish_wick['detected']:
            detections.append(bullish_wick)

        # Detection 2: Long Wick Pattern (bearish reversal)
        bearish_wick = self._detect_bearish_long_wick(latest_candle, atr)
        if bearish_wick['detected']:
            detections.append(bearish_wick)

        # Detection 3: Fake Breakout Below Support
        if support_level:
            fake_breakdown = self._detect_fake_breakdown(
                price_data, support_level, atr
            )
            if fake_breakdown['detected']:
                detections.append(fake_breakdown)

        # Detection 4: Fake Breakout Above Resistance
        if resistance_level:
            fake_breakout = self._detect_fake_breakout(
                price_data, resistance_level, atr
            )
            if fake_breakout['detected']:
                detections.append(fake_breakout)

        # Build result
        if detections:
            return self._build_detection_result(detections, current_price, atr)
        else:
            return self._no_detection("No liquidity grab detected")

    def _detect_bullish_long_wick(self, candle: pd.Series, atr: float) -> Dict[str, Any]:
        """ตรวจจับ long lower wick (bullish rejection)"""

        open_price = candle['open']
        high_price = candle['high']
        low_price = candle['low']
        close_price = candle['close']

        # คำนวณขนาด body และ wick
        body_size = abs(close_price - open_price)
        lower_wick = min(open_price, close_price) - low_price
        upper_wick = high_price - max(open_price, close_price)

        # เงื่อนไข: Lower wick ยาวกว่า body อย่างน้อย 2 เท่า
        # และ lower wick มากกว่า 50% ของ ATR
        if (lower_wick > body_size * 2 and
            lower_wick > atr * 0.5 and
            close_price > open_price):  # Bullish candle

            return {
                'detected': True,
                'type': 'BULLISH_LONG_WICK',
                'direction': 'UP',
                'strength': self._calculate_wick_strength(lower_wick, body_size),
                'message': f'🎯 Bullish Rejection: ราคาลงไปล่า SL ที่ {low_price:.2f} แล้วกลับขึ้น',
                'suggested_entry': close_price,
                'invalidation': low_price,
                'wick_size': round(lower_wick, 2),
                'body_size': round(body_size, 2)
            }

        return {'detected': False}

    def _detect_bearish_long_wick(self, candle: pd.Series, atr: float) -> Dict[str, Any]:
        """ตรวจจับ long upper wick (bearish rejection)"""

        open_price = candle['open']
        high_price = candle['high']
        low_price = candle['low']
        close_price = candle['close']

        # คำนวณขนาด body และ wick
        body_size = abs(close_price - open_price)
        upper_wick = high_price - max(open_price, close_price)
        lower_wick = min(open_price, close_price) - low_price

        # เงื่อนไข: Upper wick ยาวกว่า body อย่างน้อย 2 เท่า
        if (upper_wick > body_size * 2 and
            upper_wick > atr * 0.5 and
            close_price < open_price):  # Bearish candle

            return {
                'detected': True,
                'type': 'BEARISH_LONG_WICK',
                'direction': 'DOWN',
                'strength': self._calculate_wick_strength(upper_wick, body_size),
                'message': f'🎯 Bearish Rejection: ราคาขึ้นไปล่า SL ที่ {high_price:.2f} แล้วกลับลง',
                'suggested_entry': close_price,
                'invalidation': high_price,
                'wick_size': round(upper_wick, 2),
                'body_size': round(body_size, 2)
            }

        return {'detected': False}

    def _detect_fake_breakdown(self, price_data: pd.DataFrame,
                               support: float, atr: float) -> Dict[str, Any]:
        """
        ตรวจจับ Fake Breakdown ที่ support

        Pattern:
        - ราคาทะลุ support ลงไปนิดหน่อย
        - กลับเข้ามาเหนือ support ภายใน 1-2 candles
        - Volume spike ขณะทะลุ
        """
        latest = price_data.iloc[-1]
        prev = price_data.iloc[-2]

        # เช็คว่ามี candle ที่ทะลุ support ลงไปหรือไม่
        breakdown_distance = support - prev['low']

        # เงื่อนไข:
        # 1. Candle ก่อนหน้าทะลุ support ลงไป (แต่ไม่เกิน 1.5x ATR)
        # 2. Candle ปัจจุบันกลับมาเหนือ support
        # 3. Close เหนือ support
        if (breakdown_distance > 0 and
            breakdown_distance < atr * 1.5 and
            latest['close'] > support and
            latest['low'] < support):  # Touch support

            return {
                'detected': True,
                'type': 'FAKE_BREAKDOWN',
                'direction': 'UP',
                'strength': 'MEDIUM',
                'message': f'🚨 Fake Breakdown: ทะลุ support {support:.2f} แล้วกลับเข้ามา - Stop Hunt!',
                'suggested_entry': latest['close'],
                'support_level': support,
                'lowest_point': prev['low'],
                'distance_broken': round(breakdown_distance, 2)
            }

        return {'detected': False}

    def _detect_fake_breakout(self, price_data: pd.DataFrame,
                             resistance: float, atr: float) -> Dict[str, Any]:
        """
        ตรวจจับ Fake Breakout ที่ resistance

        Pattern:
        - ราคาทะลุ resistance ขึ้นไปนิดหน่อย
        - กลับลงมาใต้ resistance ภายใน 1-2 candles
        """
        latest = price_data.iloc[-1]
        prev = price_data.iloc[-2]

        # เช็คว่ามี candle ที่ทะลุ resistance ขึ้นไปหรือไม่
        breakout_distance = prev['high'] - resistance

        # เงื่อนไข:
        # 1. Candle ก่อนหน้าทะลุ resistance ขึ้นไป (แต่ไม่เกิน 1.5x ATR)
        # 2. Candle ปัจจุบันกลับมาใต้ resistance
        # 3. Close ใต้ resistance
        if (breakout_distance > 0 and
            breakout_distance < atr * 1.5 and
            latest['close'] < resistance and
            latest['high'] > resistance):  # Touch resistance

            return {
                'detected': True,
                'type': 'FAKE_BREAKOUT',
                'direction': 'DOWN',
                'strength': 'MEDIUM',
                'message': f'🚨 Fake Breakout: ทะลุ resistance {resistance:.2f} แล้วกลับลง - Stop Hunt!',
                'suggested_entry': latest['close'],
                'resistance_level': resistance,
                'highest_point': prev['high'],
                'distance_broken': round(breakout_distance, 2)
            }

        return {'detected': False}

    def _calculate_wick_strength(self, wick_size: float, body_size: float) -> str:
        """คำนวณความแข็งแกร่งของ wick"""
        ratio = wick_size / body_size if body_size > 0 else 999

        if ratio > 4:
            return "VERY_STRONG"
        elif ratio > 3:
            return "STRONG"
        elif ratio > 2:
            return "MEDIUM"
        else:
            return "WEAK"

    def _calculate_simple_atr(self, price_data: pd.DataFrame, period: int = 14) -> float:
        """คำนวณ ATR แบบง่าย"""
        if len(price_data) < period:
            period = len(price_data)

        high = price_data['high'].tail(period)
        low = price_data['low'].tail(period)
        close = price_data['close'].tail(period)

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.mean()

        return atr

    def _build_detection_result(self, detections: List[Dict],
                                current_price: float, atr: float) -> Dict[str, Any]:
        """สร้าง result จาก detections"""

        # เลือก detection ที่แข็งแกร่งที่สุด
        primary = max(detections, key=lambda x: self._strength_score(x.get('strength', 'WEAK')))

        return {
            'detected': True,
            'symbol': self.symbol,
            'timestamp': datetime.now().isoformat(),
            'current_price': current_price,
            'primary_signal': primary,
            'all_signals': detections,
            'signal_count': len(detections),
            'confidence': self._calculate_confidence(detections),
            'action_recommendation': self._get_action_recommendation(primary),
            'atr': round(atr, 2)
        }

    def _no_detection(self, reason: str) -> Dict[str, Any]:
        """สร้าง result เมื่อไม่เจอ detection"""
        return {
            'detected': False,
            'symbol': self.symbol,
            'timestamp': datetime.now().isoformat(),
            'reason': reason
        }

    def _strength_score(self, strength: str) -> int:
        """แปลง strength เป็น score"""
        scores = {
            'VERY_STRONG': 4,
            'STRONG': 3,
            'MEDIUM': 2,
            'WEAK': 1
        }
        return scores.get(strength, 0)

    def _calculate_confidence(self, detections: List[Dict]) -> str:
        """คำนวณ confidence จากจำนวนและความแข็งแกร่งของ signals"""
        total_score = sum(self._strength_score(d.get('strength', 'WEAK')) for d in detections)

        if total_score >= 6 or len(detections) >= 3:
            return "HIGH"
        elif total_score >= 4 or len(detections) >= 2:
            return "MEDIUM"
        else:
            return "LOW"

    def _get_action_recommendation(self, primary_signal: Dict) -> str:
        """แนะนำ action จาก primary signal"""
        direction = primary_signal.get('direction', 'UNKNOWN')
        strength = primary_signal.get('strength', 'WEAK')
        signal_type = primary_signal.get('type', '')

        if direction == 'UP':
            if strength in ['VERY_STRONG', 'STRONG']:
                return f"🟢 STRONG BUY SIGNAL - เข้า Buy หลัง {signal_type}"
            else:
                return f"🟡 MODERATE BUY - พิจารณา Buy หลัง {signal_type}"
        elif direction == 'DOWN':
            if strength in ['VERY_STRONG', 'STRONG']:
                return f"🔴 STRONG SELL SIGNAL - เข้า Sell หลัง {signal_type}"
            else:
                return f"🟡 MODERATE SELL - พิจารณา Sell หลัง {signal_type}"
        else:
            return "⚪ NO CLEAR SIGNAL"


def format_liquidity_grab(result: Dict[str, Any]) -> str:
    """Format Liquidity Grab detection result"""

    if not result['detected']:
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 LIQUIDITY GRAB DETECTOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚪ ไม่พบสัญญาณการกวาด Stop Loss
Reason: {result['reason']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    primary = result['primary_signal']

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 LIQUIDITY GRAB DETECTED!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{result['action_recommendation']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Primary Signal: {primary['type']}
├─ Direction: {primary['direction']}
├─ Strength: {primary['strength']}
└─ Message: {primary['message']}

💡 Suggested Entry: ${primary.get('suggested_entry', 'N/A'):.2f}
⛔ Invalidation: ${primary.get('invalidation', 'N/A'):.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 All Signals Detected ({result['signal_count']}):
"""

    for i, signal in enumerate(result['all_signals'], 1):
        output += f"\n{i}. {signal['type']} - {signal.get('strength', 'N/A')}"
        output += f"\n   {signal['message']}\n"

    output += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Confidence: {result['confidence']}
Current Price: ${result['current_price']:.2f}
ATR: ${result['atr']:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Insight: สถาบันเพิ่งกวาด Stop Loss เสร็จ - นี่คือโอกาสดี!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    return output
