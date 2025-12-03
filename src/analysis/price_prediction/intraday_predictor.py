"""
Intraday Price Range Prediction & Bull Trap Detection
ทำนายช่วงราคาภายในวัน และเตือน Bull Trap (กับดักซื้อ)
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
import numpy as np


class IntradayPricePredictor:
    """
    ทำนายช่วงราคาภายในวันและเตือน Bull Trap

    Features:
    1. Intraday High/Low Prediction - ทำนาย high/low ของวัน
    2. Bull Trap Detection - ตรวจจับกับดักซื้อ
    3. Multi-Day Trend Warning - เตือนแนวโน้ม 1-3 วันข้างหน้า
    4. Dead Cat Bounce - ตรวจจับการกระดอนในเทรนด์ขาลง
    """

    def __init__(self):
        pass

    def predict_intraday_range(
        self,
        current_price: float,
        support: float,
        resistance: float,
        atr: float,
        volatility: float,
        trend: str,
        volume_ratio: float = 1.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        ทำนายช่วงราคาภายในวัน (high/low)

        Args:
            current_price: ราคาปัจจุบัน
            support: Support level
            resistance: Resistance level
            atr: Average True Range (วัดความผันผวน)
            volatility: Daily volatility %
            trend: แนวโน้ม ('uptrend', 'downtrend', 'sideways')
            volume_ratio: Volume วันนี้ vs average

        Returns:
            {
                'predicted_high': ราคาสูงสุดที่คาดหวัง,
                'predicted_low': ราคาต่ำสุดที่คาดหวัง,
                'expected_gain': % ที่อาจขึ้นได้สูงสุด,
                'expected_loss': % ที่อาจลงได้สูงสุด,
                'confidence': ความมั่นใจในการทำนาย
            }
        """
        try:
            # 1. คำนวณ Intraday Range จาก ATR
            # ปกติ intraday range ≈ 0.7 * ATR (ไม่ถึง full day range)
            intraday_range = atr * 0.7

            # ปรับตาม volume (volume สูง → range กว้างขึ้น)
            if volume_ratio > 1.5:
                intraday_range *= 1.2  # เพิ่ม 20%
            elif volume_ratio < 0.7:
                intraday_range *= 0.8  # ลด 20%

            # 2. ทำนาย High/Low ตาม Trend
            if trend == 'uptrend':
                # Uptrend: มักจะทดสอบ resistance
                predicted_high = min(resistance, current_price + intraday_range)
                predicted_low = max(support, current_price - (intraday_range * 0.3))
                bias = 'bullish'

            elif trend == 'downtrend':
                # Downtrend: มักจะทดสอบ support
                predicted_high = min(resistance, current_price + (intraday_range * 0.3))
                predicted_low = max(support, current_price - intraday_range)
                bias = 'bearish'

            else:  # sideways
                # Sideways: range กว้าง
                predicted_high = min(resistance, current_price + (intraday_range * 0.5))
                predicted_low = max(support, current_price - (intraday_range * 0.5))
                bias = 'neutral'

            # 3. คำนวณ % ที่อาจเกิดขึ้น
            expected_gain = ((predicted_high - current_price) / current_price) * 100
            expected_loss = ((current_price - predicted_low) / current_price) * 100

            # 4. คำนวณ Confidence
            # ยิ่ง volatility สูง → confidence ต่ำ (ทำนายยาก)
            if volatility < 2.0:
                confidence = 85
            elif volatility < 3.0:
                confidence = 75
            elif volatility < 5.0:
                confidence = 65
            else:
                confidence = 50

            # ปรับตาม volume confirmation
            if volume_ratio > 1.2:
                confidence += 5  # Volume สูง → เชื่อถือได้มากขึ้น
            elif volume_ratio < 0.8:
                confidence -= 10  # Volume ต่ำ → ไม่แน่ใจ

            confidence = max(30, min(95, confidence))

            # 5. Generate explanation
            explanation = self._generate_range_explanation(
                expected_gain, expected_loss, bias, confidence, volume_ratio
            )

            return {
                'predicted_high': round(predicted_high, 2),
                'predicted_low': round(predicted_low, 2),
                'expected_gain_pct': round(expected_gain, 2),
                'expected_loss_pct': round(expected_loss, 2),
                'intraday_range': round(intraday_range, 2),
                'bias': bias,
                'confidence': confidence,
                'explanation': explanation,
                'key_levels': {
                    'resistance': resistance,
                    'support': support,
                    'pivot': round((predicted_high + predicted_low) / 2, 2)
                }
            }

        except Exception as e:
            logger.error(f"Intraday prediction failed: {e}")
            return {
                'predicted_high': current_price * 1.02,
                'predicted_low': current_price * 0.98,
                'expected_gain_pct': 2.0,
                'expected_loss_pct': 2.0,
                'confidence': 50,
                'explanation': 'Unable to predict accurately'
            }

    def detect_bull_trap(
        self,
        current_price: float,
        trend: str,
        falling_knife_data: Dict[str, Any],
        momentum_indicators: Dict[str, Any],
        price_change_pct: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        ตรวจจับ Bull Trap (กับดักซื้อ)

        Bull Trap = ราคาขึ้นชั่วคราวในเทรนด์ขาลง → หลอกให้คิดว่ากลับตัว → แล้วลงต่อ

        Signals:
        - เทรนด์หลักยังลง (downtrend)
        - ราคาขึ้น 1-3% (ดึงดูดผู้ซื้อ)
        - RSI ยังไม่ถึง overbought (45-60)
        - Volume ต่ำ (ไม่มีแรงซื้อจริง)
        - Falling knife risk ยังสูง

        Returns:
            {
                'is_bull_trap': True/False,
                'trap_probability': 0-100%,
                'warning_message': ข้อความเตือน,
                'expected_reversal': ช่วงราคาที่จะกลับลง
            }
        """
        try:
            trap_signals = []
            trap_score = 0

            # 1. เช็ค Trend (ต้องเป็น downtrend)
            if trend in ['downtrend', 'bearish']:
                trap_signals.append('แนวโน้มหลักยังลง')
                trap_score += 20
            else:
                # ไม่ใช่ downtrend → ไม่ใช่ bull trap
                return {
                    'is_bull_trap': False,
                    'trap_probability': 0,
                    'warning_message': None
                }

            # 2. เช็คการขึ้นชั่วคราว (0-5%)
            if 0 < price_change_pct <= 5:
                trap_signals.append(f'ราคาขึ้นชั่วคราว +{price_change_pct:.1f}%')
                trap_score += 25
            elif price_change_pct > 5:
                # ขึ้นมากเกินไป → อาจเป็นการกลับตัวจริง
                trap_score -= 10

            # 3. เช็ค Falling Knife (ยังตกต่อเนื่องหรือไม่)
            is_falling_knife = falling_knife_data.get('is_falling_knife', False)
            risk_level = falling_knife_data.get('risk_level', 'NONE')

            if is_falling_knife and risk_level in ['HIGH', 'MODERATE']:
                trap_signals.append(f'ยังอยู่ใน Falling Knife ({risk_level})')
                trap_score += 30

            # 4. เช็ค RSI (ต้องไม่ overbought แต่ยังไม่ถึง oversold)
            rsi = momentum_indicators.get('rsi')
            if rsi and 40 <= rsi <= 60:
                trap_signals.append(f'RSI {rsi:.0f} (ขึ้นแต่ยังไม่แรง)')
                trap_score += 15
            elif rsi and rsi > 70:
                # Overbought → อาจกลับลงได้
                trap_score += 10

            # 5. เช็ค Volume (ต้องต่ำ - ไม่มีแรงซื้อจริง)
            volume_ratio = kwargs.get('volume_ratio', 1.0)
            if volume_ratio < 0.8:
                trap_signals.append(f'Volume ต่ำ ({volume_ratio*100:.0f}% of avg)')
                trap_score += 20
            elif volume_ratio > 1.5:
                # Volume สูง → อาจเป็นการกลับตัวจริง
                trap_score -= 15

            # 6. เช็ค MACD (ถ้ายัง bearish → trap แน่นอน)
            macd_line = momentum_indicators.get('macd_line')
            macd_signal = momentum_indicators.get('macd_signal')

            if macd_line is not None and macd_signal is not None:
                if macd_line < macd_signal:
                    trap_signals.append('MACD ยัง bearish')
                    trap_score += 15

            # คำนวณ probability
            trap_probability = min(100, max(0, trap_score))

            # ตัดสินว่าเป็น Bull Trap หรือไม่
            is_bull_trap = trap_probability >= 60

            # สร้างข้อความเตือน
            if is_bull_trap:
                if trap_probability >= 80:
                    severity = '🚨 HIGH'
                    color = '🔴'
                elif trap_probability >= 70:
                    severity = '⚠️ MODERATE'
                    color = '🟠'
                else:
                    severity = '⚠️ LOW'
                    color = '🟡'

                warning_message = (
                    f"{color} {severity} BULL TRAP DETECTED ({trap_probability}%)\n"
                    f"→ ราคาอาจขึ้น +{price_change_pct:.1f}% วันนี้ แต่แนวโน้มยังลงต่อ!\n"
                    f"→ สัญญาณ: {', '.join(trap_signals[:3])}\n"
                    f"→ คำแนะนำ: อย่าหลงซื้อ - รอจนเทรนด์กลับจริง"
                )
            else:
                warning_message = None

            # ทำนายว่าจะกลับลงที่ไหน
            expected_reversal = None
            if is_bull_trap:
                # คาดว่าจะกลับลงต่ำกว่าราคาปัจจุบัน 2-5%
                reversal_low = current_price * 0.95
                reversal_high = current_price * 0.98
                expected_reversal = {
                    'range': f"${reversal_low:.2f} - ${reversal_high:.2f}",
                    'percent': '-2% to -5% from current'
                }

            return {
                'is_bull_trap': is_bull_trap,
                'trap_probability': trap_probability,
                'trap_score': trap_score,
                'signals': trap_signals,
                'warning_message': warning_message,
                'expected_reversal': expected_reversal,
                'severity': severity if is_bull_trap else 'NONE'
            }

        except Exception as e:
            logger.error(f"Bull trap detection failed: {e}")
            return {
                'is_bull_trap': False,
                'trap_probability': 0,
                'warning_message': None
            }

    def predict_multi_day_trend(
        self,
        current_price: float,
        trend_strength: float,
        momentum_indicators: Dict[str, Any],
        falling_knife_data: Dict[str, Any],
        days_ahead: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        ทำนายแนวโน้มหลายวัน (1-3 วันข้างหน้า)

        Args:
            days_ahead: จำนวนวันที่ต้องการทำนาย (1-3)

        Returns:
            {
                'day_1': {'trend': 'down', 'expected_change': -2.5},
                'day_2': {'trend': 'down', 'expected_change': -1.5},
                'day_3': {'trend': 'sideways', 'expected_change': 0.5},
                'summary': 'แนวโน้มยังลงต่อเนื่อง 2 วัน แล้วจะซื้อขาย sideways'
            }
        """
        try:
            predictions = {}

            # ดึงข้อมูล momentum
            rsi = momentum_indicators.get('rsi', 50)
            macd_histogram = momentum_indicators.get('macd_histogram', 0)

            # ดึงข้อมูล falling knife
            is_falling_knife = falling_knife_data.get('is_falling_knife', False)
            fall_days = falling_knife_data.get('fall_days', 0)

            # คำนวณแนวโน้มแต่ละวัน
            for day in range(1, min(days_ahead + 1, 4)):
                if is_falling_knife:
                    # ถ้ายังเป็น Falling Knife → มักจะยังลงต่อ 1-2 วัน
                    if day <= 2:
                        trend_direction = 'down'
                        # วันแรกลงแรงสุด, วันที่ 2 ลงน้อยลง
                        expected_change = -2.5 + (day * 0.5)
                    else:
                        # วันที่ 3 เริ่ม stabilize
                        trend_direction = 'sideways'
                        expected_change = -0.5
                else:
                    # ไม่ใช่ Falling Knife → ดูจาก momentum
                    if rsi < 30:
                        # Oversold → อาจกลับตัว
                        if day == 1:
                            trend_direction = 'sideways'
                            expected_change = 0.5
                        else:
                            trend_direction = 'up'
                            expected_change = 1.5
                    elif rsi > 70:
                        # Overbought → อาจปรับฐาน
                        trend_direction = 'down'
                        expected_change = -1.5
                    else:
                        # Neutral
                        trend_direction = 'sideways'
                        expected_change = 0.0

                # ปรับตาม trend strength
                if abs(trend_strength) > 70:
                    # Trend แรง → มักจะยังไปทิศทางเดิมต่อ
                    expected_change *= 1.2

                predictions[f'day_{day}'] = {
                    'trend': trend_direction,
                    'expected_change_pct': round(expected_change, 1),
                    'confidence': 70 - (day * 10)  # วันไกล → confidence ลดลง
                }

            # สรุปแนวโน้ม
            down_days = sum(1 for p in predictions.values() if p['trend'] == 'down')
            up_days = sum(1 for p in predictions.values() if p['trend'] == 'up')

            if down_days >= 2:
                summary = f'⚠️ แนวโน้มยังลงต่อเนื่อง {down_days} วัน - ระวังกับดัก!'
                overall_bias = 'bearish'
            elif up_days >= 2:
                summary = f'✅ แนวโน้มกลับตัวขึ้น {up_days} วัน - พิจารณาเข้าซื้อ'
                overall_bias = 'bullish'
            else:
                summary = '⏸️ แนวโน้มไม่ชัดเจน - รอสัญญาณที่ดีกว่า'
                overall_bias = 'neutral'

            return {
                'predictions': predictions,
                'summary': summary,
                'overall_bias': overall_bias,
                'down_days_count': down_days,
                'up_days_count': up_days
            }

        except Exception as e:
            logger.error(f"Multi-day prediction failed: {e}")
            return {
                'predictions': {},
                'summary': 'Unable to predict',
                'overall_bias': 'neutral'
            }

    def _generate_range_explanation(
        self,
        expected_gain: float,
        expected_loss: float,
        bias: str,
        confidence: int,
        volume_ratio: float
    ) -> str:
        """สร้างคำอธิบายสำหรับ intraday range"""

        if bias == 'bullish':
            direction = '↗️ มีโอกาสขึ้น'
        elif bias == 'bearish':
            direction = '↘️ มีโอกาสลง'
        else:
            direction = '↔️ แกว่งตัว'

        volume_msg = ''
        if volume_ratio > 1.5:
            volume_msg = ' (Volume สูง - เชื่อถือได้)'
        elif volume_ratio < 0.7:
            volume_msg = ' (Volume ต่ำ - ระวัง)'

        explanation = (
            f"{direction} สูงสุด +{expected_gain:.1f}%, "
            f"ต่ำสุด -{expected_loss:.1f}%{volume_msg}"
        )

        return explanation


def generate_trading_alert(
    intraday_prediction: Dict[str, Any],
    bull_trap_detection: Dict[str, Any],
    multi_day_trend: Dict[str, Any]
) -> Dict[str, Any]:
    """
    รวมข้อมูลทั้งหมดเป็น Trading Alert ที่ชัดเจน

    Returns:
        {
            'alert_type': 'BULL_TRAP' / 'SAFE_TO_BUY' / 'WAIT',
            'message': ข้อความเตือนหลัก,
            'intraday_forecast': ทำนายวันนี้,
            'next_days_forecast': ทำนาย 1-3 วันข้างหน้า,
            'recommendation': คำแนะนำ
        }
    """
    try:
        is_bull_trap = bull_trap_detection.get('is_bull_trap', False)
        trap_probability = bull_trap_detection.get('trap_probability', 0)

        # ดึงข้อมูล intraday
        expected_gain = intraday_prediction.get('expected_gain_pct', 0)
        expected_loss = intraday_prediction.get('expected_loss_pct', 0)

        # ดึงข้อมูล multi-day
        overall_bias = multi_day_trend.get('overall_bias', 'neutral')
        down_days = multi_day_trend.get('down_days_count', 0)

        # ตัดสินใจ Alert Type
        if is_bull_trap:
            alert_type = 'BULL_TRAP'
            alert_icon = '🚨'
            main_message = (
                f"{alert_icon} BULL TRAP WARNING!\n\n"
                f"📈 วันนี้: อาจขึ้น +{expected_gain:.1f}% (ดูดี)\n"
                f"📉 แนวโน้ม: ยังลงต่อเนื่อง {down_days} วัน (อันตราย!)\n"
                f"🎯 Trap Probability: {trap_probability}%\n\n"
                f"⚠️ อย่าหลงกับดัก! ราคาอาจขึ้นชั่วคราวแล้วกลับลงต่อ"
            )
            recommendation = "❌ DON'T BUY - รอจนเทรนด์กลับตัวจริง"

        elif overall_bias == 'bearish':
            alert_type = 'DOWNTREND_WARNING'
            alert_icon = '⚠️'
            main_message = (
                f"{alert_icon} แนวโน้มยังลงต่อเนื่อง\n\n"
                f"📉 แนวโน้ม {down_days} วัน: ยังลงต่อ\n"
                f"📈 วันนี้: อาจขึ้น +{expected_gain:.1f}% แต่ไม่ยั่งยืน\n\n"
                f"💡 รอจนมีสัญญาณกลับตัวชัดเจนก่อนเข้า"
            )
            recommendation = "⏸️ WAIT - รอสัญญาณที่ดีกว่า"

        elif overall_bias == 'bullish':
            alert_type = 'SAFE_TO_BUY'
            alert_icon = '✅'
            main_message = (
                f"{alert_icon} แนวโน้มดี - พิจารณาเข้าได้\n\n"
                f"📈 วันนี้: อาจขึ้น +{expected_gain:.1f}%\n"
                f"🎯 แนวโน้ม: กลับตัวขึ้นแล้ว\n\n"
                f"💡 เป็นจังหวะที่ดีสำหรับเข้าซื้อ"
            )
            recommendation = "✅ CONSIDER BUYING - จังหวะดี"

        else:
            alert_type = 'WAIT'
            alert_icon = '⏸️'
            main_message = (
                f"{alert_icon} สัญญาณไม่ชัดเจน\n\n"
                f"↔️ วันนี้: แกว่งตัว +{expected_gain:.1f}% / -{expected_loss:.1f}%\n"
                f"❓ แนวโน้ม: ยังไม่ชัดเจน\n\n"
                f"💡 รอจนมีสัญญาณที่ชัดเจนกว่า"
            )
            recommendation = "⏸️ WAIT - รอสัญญาณ"

        return {
            'alert_type': alert_type,
            'alert_icon': alert_icon,
            'main_message': main_message,
            'intraday_forecast': {
                'expected_high': intraday_prediction.get('predicted_high'),
                'expected_low': intraday_prediction.get('predicted_low'),
                'gain_potential': f"+{expected_gain:.1f}%",
                'loss_risk': f"-{expected_loss:.1f}%"
            },
            'next_days_forecast': multi_day_trend.get('summary'),
            'recommendation': recommendation,
            'bull_trap_warning': bull_trap_detection.get('warning_message') if is_bull_trap else None
        }

    except Exception as e:
        logger.error(f"Alert generation failed: {e}")
        return {
            'alert_type': 'ERROR',
            'main_message': 'Unable to generate alert',
            'recommendation': 'Manual review required'
        }
