"""
Price Change Analyzer - วิเคราะห์ว่าทำไมราคาขึ้น/ลงจากก่อนหน้า
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from loguru import logger


class PriceChangeAnalyzer:
    """
    วิเคราะห์การเปลี่ยนแปลงราคาและหาสาเหตุที่ราคาขึ้น/ลง
    """

    def __init__(self):
        """Initialize price change analyzer"""
        pass

    def analyze_price_change(self,
                           price_data: pd.DataFrame,
                           technical_indicators: Dict[str, Any] = None,
                           fundamental_data: Dict[str, Any] = None,
                           market_state_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        วิเคราะห์การเปลี่ยนแปลงราคาและหาสาเหตุ

        Args:
            price_data: ข้อมูลราคาหุ้น
            technical_indicators: ตัวชี้วัดทางเทคนิค
            fundamental_data: ข้อมูลพื้นฐาน
            market_state_analysis: ข้อมูล Dip/Falling Knife/Overextension (NEW)

        Returns:
            Dict ที่มีข้อมูลการวิเคราะห์การเปลี่ยนแปลงราคา
        """
        try:
            if len(price_data) < 2:
                return {
                    'error': 'Insufficient data for price change analysis',
                    'change_percent': 0,
                    'direction': 'NEUTRAL'
                }

            # คำนวณการเปลี่ยนแปลงราคา
            current_price = price_data['close'].iloc[-1]
            previous_price = price_data['close'].iloc[-2]
            change_percent = ((current_price - previous_price) / previous_price) * 100

            # กำหนดทิศทางการเปลี่ยนแปลง
            if change_percent > 0.5:
                direction = 'UP'
            elif change_percent < -0.5:
                direction = 'DOWN'
            else:
                direction = 'NEUTRAL'

            # วิเคราะห์สาเหตุการเปลี่ยนแปลงราคา
            reasons = self._analyze_change_reasons(
                price_data,
                change_percent,
                direction,
                technical_indicators,
                fundamental_data
            )

            # วิเคราะห์การเปลี่ยนแปลงในช่วงเวลาต่างๆ
            period_changes = self._analyze_period_changes(price_data)

            # วิเคราะห์แรงซื้อ/แรงขาย
            buying_selling_pressure = self._analyze_buying_selling_pressure(price_data)

            # ประเมินความแข็งแกร่งของเทรนด์
            trend_strength = self._analyze_trend_strength(price_data, technical_indicators)

            # หาจุดสำคัญที่ส่งผลต่อราคา (ส่ง technical_indicators เพื่อใช้ S/R ที่สอดคล้องกัน)
            key_levels = self._identify_key_price_levels(price_data, current_price, technical_indicators)

            # วิเคราะห์ปริมาณการซื้อขาย (volume)
            volume_analysis = self._analyze_volume_impact(price_data)

            # สรุปการวิเคราะห์
            summary = self._create_change_summary(
                direction, change_percent, reasons,
                trend_strength, buying_selling_pressure
            )

            # ประเมินว่าควรขายกำไรหรือยัง (สำหรับหุ้นที่ขึ้น)
            profit_taking_analysis = self._analyze_profit_taking_opportunity(
                price_data, direction, change_percent,
                technical_indicators, trend_strength,
                buying_selling_pressure, key_levels,
                market_state_analysis  # NEW: ส่ง Dip/Falling Knife data
            )

            return {
                'current_price': round(current_price, 2),
                'previous_price': round(previous_price, 2),
                'change_amount': round(current_price - previous_price, 2),
                'change_percent': round(change_percent, 2),
                'direction': direction,
                'reasons': reasons,
                'period_changes': period_changes,
                'buying_selling_pressure': buying_selling_pressure,
                'trend_strength': trend_strength,
                'key_levels': key_levels,
                'volume_analysis': volume_analysis,
                'summary': summary,
                'profit_taking_analysis': profit_taking_analysis,  # NEW
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Price change analysis failed: {e}")
            return {
                'error': str(e),
                'change_percent': 0,
                'direction': 'NEUTRAL'
            }

    def _analyze_change_reasons(self,
                               price_data: pd.DataFrame,
                               change_percent: float,
                               direction: str,
                               technical_indicators: Dict[str, Any],
                               fundamental_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """วิเคราะห์สาเหตุของการเปลี่ยนแปลงราคา"""
        reasons = []

        try:
            # 1. วิเคราะห์จากปริมาณการซื้อขาย (Volume)
            volume_reason = self._check_volume_reason(price_data, direction)
            if volume_reason:
                reasons.append(volume_reason)

            # 2. วิเคราะห์จาก Technical Indicators
            if technical_indicators:
                tech_reasons = self._check_technical_reasons(
                    price_data, technical_indicators, direction
                )
                reasons.extend(tech_reasons)

            # 3. วิเคราะห์จาก Price Action
            price_action_reasons = self._check_price_action_reasons(price_data, direction)
            reasons.extend(price_action_reasons)

            # 4. วิเคราะห์จาก Support/Resistance
            sr_reasons = self._check_support_resistance_reasons(price_data, direction)
            reasons.extend(sr_reasons)

            # 5. วิเคราะห์จาก Momentum
            momentum_reasons = self._check_momentum_reasons(price_data, direction)
            reasons.extend(momentum_reasons)

            # จัดเรียงตามความสำคัญ
            reasons.sort(key=lambda x: x.get('importance', 0), reverse=True)

            # จำกัดจำนวนเหตุผลไม่เกิน 5 อันดับแรก
            return reasons[:5]

        except Exception as e:
            logger.warning(f"Error analyzing change reasons: {e}")
            return [{
                'reason': 'การเปลี่ยนแปลงราคาตามภาวะตลาดโดยรวม',
                'type': 'general',
                'importance': 50,
                'detail': 'ไม่สามารถระบุสาเหตุเฉพาะได้'
            }]

    def _check_volume_reason(self, price_data: pd.DataFrame, direction: str) -> Dict[str, Any]:
        """ตรวจสอบสาเหตุจากปริมาณการซื้อขาย"""
        try:
            if 'volume' not in price_data.columns:
                return None

            current_volume = price_data['volume'].iloc[-1]
            avg_volume = price_data['volume'].rolling(20).mean().iloc[-1]

            if pd.isna(current_volume) or pd.isna(avg_volume):
                return None

            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            if volume_ratio > 1.5:  # Volume สูงกว่าปกติมาก
                if direction == 'UP':
                    return {
                        'reason': 'แรงซื้อเพิ่มขึ้นอย่างมาก',
                        'type': 'volume',
                        'importance': 85,
                        'detail': f'ปริมาณการซื้อขายเพิ่มขึ้น {(volume_ratio-1)*100:.1f}% จากค่าเฉลี่ย พบแรงซื้อที่แข็งแกร่ง'
                    }
                elif direction == 'DOWN':
                    return {
                        'reason': 'แรงขายเพิ่มขึ้นอย่างมาก',
                        'type': 'volume',
                        'importance': 85,
                        'detail': f'ปริมาณการซื้อขายเพิ่มขึ้น {(volume_ratio-1)*100:.1f}% จากค่าเฉลี่ย พบแรงขายที่แข็งแกร่ง'
                    }
            elif volume_ratio > 1.2:  # Volume สูงกว่าปกติ
                if direction == 'UP':
                    return {
                        'reason': 'มีแรงซื้อเข้ามาสนับสนุน',
                        'type': 'volume',
                        'importance': 70,
                        'detail': f'ปริมาณการซื้อขายสูงกว่าปกติ {(volume_ratio-1)*100:.1f}%'
                    }
                elif direction == 'DOWN':
                    return {
                        'reason': 'มีแรงขายเข้ามากดดัน',
                        'type': 'volume',
                        'importance': 70,
                        'detail': f'ปริมาณการซื้อขายสูงกว่าปกติ {(volume_ratio-1)*100:.1f}%'
                    }
            elif volume_ratio < 0.7:  # Volume ต่ำกว่าปกติ
                return {
                    'reason': 'การเปลี่ยนแปลงราคาด้วยปริมาณซื้อขายที่ต่ำ',
                    'type': 'volume',
                    'importance': 40,
                    'detail': f'ปริมาณการซื้อขายต่ำกว่าปกติ {(1-volume_ratio)*100:.1f}% อาจไม่ยั่งยืน'
                }

            return None

        except Exception:
            return None

    def _check_technical_reasons(self,
                                price_data: pd.DataFrame,
                                technical_indicators: Dict[str, Any],
                                direction: str) -> List[Dict[str, Any]]:
        """ตรวจสอบสาเหตุจาก Technical Indicators"""
        reasons = []

        try:
            indicators = technical_indicators.get('indicators', {})

            # RSI
            rsi = indicators.get('rsi')
            if rsi is not None:
                if direction == 'UP' and rsi < 40:
                    reasons.append({
                        'reason': 'ฟื้นตัวจากภาวะ Oversold',
                        'type': 'technical',
                        'importance': 75,
                        'detail': f'RSI อยู่ที่ {rsi:.1f} แสดงว่าราคาถูกเกินไปและเริ่มฟื้นตัว'
                    })
                elif direction == 'DOWN' and rsi > 60:
                    reasons.append({
                        'reason': 'ปรับฐานจากภาวะ Overbought',
                        'type': 'technical',
                        'importance': 75,
                        'detail': f'RSI อยู่ที่ {rsi:.1f} แสดงว่าราคาสูงเกินไปและเริ่มปรับฐาน'
                    })

            # MACD
            macd_line = indicators.get('macd_line')
            macd_signal = indicators.get('macd_signal')
            if macd_line is not None and macd_signal is not None:
                if direction == 'UP' and macd_line > macd_signal:
                    reasons.append({
                        'reason': 'สัญญาณซื้อจาก MACD',
                        'type': 'technical',
                        'importance': 80,
                        'detail': 'MACD เส้น Signal แสดงแนวโน้มขาขึ้น'
                    })
                elif direction == 'DOWN' and macd_line < macd_signal:
                    reasons.append({
                        'reason': 'สัญญาณขายจาก MACD',
                        'type': 'technical',
                        'importance': 80,
                        'detail': 'MACD ตัดเส้น Signal ลงมา แสดงแนวโน้มขาลง'
                    })

            # Moving Averages
            sma_20 = indicators.get('sma_20')
            sma_50 = indicators.get('sma_50')
            current_price = price_data['close'].iloc[-1]

            if sma_20 is not None:
                if direction == 'UP' and current_price > sma_20:
                    reasons.append({
                        'reason': 'ราคาเหนือค่าเฉลี่ย SMA 20',
                        'type': 'technical',
                        'importance': 65,
                        'detail': f'ราคาอยู่เหนือ SMA 20 วัน ({sma_20:.2f}) แสดงแนวโน้มขาขึ้นในระยะสั้น'
                    })
                elif direction == 'DOWN' and current_price < sma_20:
                    reasons.append({
                        'reason': 'ราคาต่ำกว่าค่าเฉลี่ย SMA 20',
                        'type': 'technical',
                        'importance': 65,
                        'detail': f'ราคาอยู่ต่ำกว่า SMA 20 วัน ({sma_20:.2f}) แสดงแนวโน้มขาลงในระยะสั้น'
                    })

            # Bollinger Bands
            bb_upper = indicators.get('bb_upper')
            bb_lower = indicators.get('bb_lower')
            if bb_upper is not None and bb_lower is not None:
                if direction == 'UP' and current_price > bb_upper:
                    reasons.append({
                        'reason': 'Breakout เหนือ Bollinger Band บน',
                        'type': 'technical',
                        'importance': 85,
                        'detail': 'ราคา Breakout เหนือ BB Upper แสดงแรงซื้อที่แข็งแกร่ง'
                    })
                elif direction == 'DOWN' and current_price < bb_lower:
                    reasons.append({
                        'reason': 'Breakdown ต่ำกว่า Bollinger Band ล่าง',
                        'type': 'technical',
                        'importance': 85,
                        'detail': 'ราคา Breakdown ต่ำกว่า BB Lower แสดงแรงขายที่แข็งแกร่ง'
                    })

        except Exception as e:
            logger.warning(f"Error checking technical reasons: {e}")

        return reasons

    def _check_price_action_reasons(self,
                                   price_data: pd.DataFrame,
                                   direction: str) -> List[Dict[str, Any]]:
        """ตรวจสอบสาเหตุจาก Price Action"""
        reasons = []

        try:
            if len(price_data) < 3:
                return reasons

            # ดึงข้อมูลแท่งเทียนล่าสุด
            latest_candles = price_data.tail(3)
            current = latest_candles.iloc[-1]
            previous = latest_candles.iloc[-2]

            # คำนวณขนาดของแท่งเทียน
            current_body = abs(current['close'] - current['open'])
            current_range = current['high'] - current['low']

            if current_range > 0:
                body_ratio = current_body / current_range

                # แท่งเทียนตัวใหญ่ (Strong candle)
                if body_ratio > 0.7:
                    if direction == 'UP':
                        reasons.append({
                            'reason': 'แท่งเทียนขาขึ้นที่แข็งแกร่ง',
                            'type': 'price_action',
                            'importance': 75,
                            'detail': f'แท่งเทียนมีตัวยาว {body_ratio*100:.0f}% ของ range แสดงแรงซื้อที่แข็งแกร่ง'
                        })
                    elif direction == 'DOWN':
                        reasons.append({
                            'reason': 'แท่งเทียนขาลงที่แข็งแกร่ง',
                            'type': 'price_action',
                            'importance': 75,
                            'detail': f'แท่งเทียนมีตัวยาว {body_ratio*100:.0f}% ของ range แสดงแรงขายที่แข็งแกร่ง'
                        })

            # ตรวจสอบ Gap (ช่องว่างราคา)
            if current['open'] > previous['high']:
                reasons.append({
                    'reason': 'Gap Up - เปิดสูงกว่าราคาปิดวันก่อน',
                    'type': 'price_action',
                    'importance': 80,
                    'detail': f'เปิดช่องว่างขึ้น {((current["open"]/previous["high"])-1)*100:.1f}% แสดงแรงซื้อในตอนเช้า'
                })
            elif current['open'] < previous['low']:
                reasons.append({
                    'reason': 'Gap Down - เปิดต่ำกว่าราคาปิดวันก่อน',
                    'type': 'price_action',
                    'importance': 80,
                    'detail': f'เปิดช่องว่างลง {(1-(current["open"]/previous["low"]))*100:.1f}% แสดงแรงขายในตอนเช้า'
                })

            # ตรวจสอบ Engulfing Pattern
            if direction == 'UP':
                if (current['close'] > current['open'] and
                    previous['close'] < previous['open'] and
                    current['open'] <= previous['close'] and
                    current['close'] >= previous['open']):
                    reasons.append({
                        'reason': 'Bullish Engulfing Pattern',
                        'type': 'price_action',
                        'importance': 85,
                        'detail': 'พบแท่งเทียนกลืนขาขึ้น สัญญาณกลับตัวขึ้นที่แข็งแกร่ง'
                    })
            elif direction == 'DOWN':
                if (current['close'] < current['open'] and
                    previous['close'] > previous['open'] and
                    current['open'] >= previous['close'] and
                    current['close'] <= previous['open']):
                    reasons.append({
                        'reason': 'Bearish Engulfing Pattern',
                        'type': 'price_action',
                        'importance': 85,
                        'detail': 'พบแท่งเทียนกลืนขาลง สัญญาณกลับตัวลงที่แข็งแกร่ง'
                    })

        except Exception as e:
            logger.warning(f"Error checking price action reasons: {e}")

        return reasons

    def _check_support_resistance_reasons(self,
                                         price_data: pd.DataFrame,
                                         direction: str) -> List[Dict[str, Any]]:
        """ตรวจสอบสาเหตุจาก Support/Resistance"""
        reasons = []

        try:
            current_price = price_data['close'].iloc[-1]

            # หา Support/Resistance จากราคาย้อนหลัง
            recent_highs = price_data['high'].rolling(20).max().iloc[-20:]
            recent_lows = price_data['low'].rolling(20).min().iloc[-20:]

            resistance = recent_highs.max()
            support = recent_lows.min()

            # ตรวจสอบ Breakout/Breakdown
            if direction == 'UP':
                distance_to_resistance = ((resistance - current_price) / current_price) * 100
                if distance_to_resistance < 1:  # ใกล้ resistance มาก
                    reasons.append({
                        'reason': 'Breakout เหนือแนวต้าน (Resistance)',
                        'type': 'support_resistance',
                        'importance': 90,
                        'detail': f'ทะลุแนวต้านที่ {resistance:.2f} แสดงความแข็งแกร่งของแนวโน้มขาขึ้น'
                    })
                elif distance_to_resistance < 3:
                    reasons.append({
                        'reason': 'เคลื่อนตัวเข้าใกล้แนวต้าน',
                        'type': 'support_resistance',
                        'importance': 70,
                        'detail': f'ใกล้แนวต้านที่ {resistance:.2f} ({distance_to_resistance:.1f}% จากราคาปัจจุบัน)'
                    })

            elif direction == 'DOWN':
                distance_to_support = ((current_price - support) / current_price) * 100
                if distance_to_support < 1:  # ใกล้ support มาก
                    reasons.append({
                        'reason': 'Breakdown ทะลุแนวรับ (Support)',
                        'type': 'support_resistance',
                        'importance': 90,
                        'detail': f'ทะลุแนวรับที่ {support:.2f} แสดงความอ่อนแอของแนวโน้ม'
                    })
                elif distance_to_support < 3:
                    reasons.append({
                        'reason': 'เคลื่อนตัวเข้าใกล้แนวรับ',
                        'type': 'support_resistance',
                        'importance': 70,
                        'detail': f'ใกล้แนวรับที่ {support:.2f} ({distance_to_support:.1f}% จากราคาปัจจุบัน)'
                    })

        except Exception as e:
            logger.warning(f"Error checking support/resistance reasons: {e}")

        return reasons

    def _check_momentum_reasons(self,
                               price_data: pd.DataFrame,
                               direction: str) -> List[Dict[str, Any]]:
        """ตรวจสอบสาเหตุจาก Momentum"""
        reasons = []

        try:
            if len(price_data) < 10:
                return reasons

            # คำนวณ Rate of Change (ROC)
            current_price = price_data['close'].iloc[-1]
            price_5d_ago = price_data['close'].iloc[-5]
            roc_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100

            if direction == 'UP':
                if roc_5d > 3:  # ขึ้นมากกว่า 3% ใน 5 วัน
                    reasons.append({
                        'reason': 'Momentum ขาขึ้นที่แข็งแกร่ง',
                        'type': 'momentum',
                        'importance': 75,
                        'detail': f'ราคาขึ้น {roc_5d:.1f}% ในรอบ 5 วันที่ผ่านมา แสดง momentum ที่แข็งแกร่ง'
                    })
                elif roc_5d > 1:
                    reasons.append({
                        'reason': 'Momentum ขาขึ้นปานกลาง',
                        'type': 'momentum',
                        'importance': 60,
                        'detail': f'ราคาขึ้น {roc_5d:.1f}% ในรอบ 5 วันที่ผ่านมา'
                    })

            elif direction == 'DOWN':
                if roc_5d < -3:  # ลงมากกว่า 3% ใน 5 วัน
                    reasons.append({
                        'reason': 'Momentum ขาลงที่แข็งแกร่ง',
                        'type': 'momentum',
                        'importance': 75,
                        'detail': f'ราคาลง {abs(roc_5d):.1f}% ในรอบ 5 วันที่ผ่านมา แสดง momentum ขาลงที่แข็งแกร่ง'
                    })
                elif roc_5d < -1:
                    reasons.append({
                        'reason': 'Momentum ขาลงปานกลาง',
                        'type': 'momentum',
                        'importance': 60,
                        'detail': f'ราคาลง {abs(roc_5d):.1f}% ในรอบ 5 วันที่ผ่านมา'
                    })

        except Exception as e:
            logger.warning(f"Error checking momentum reasons: {e}")

        return reasons

    def _analyze_period_changes(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """วิเคราะห์การเปลี่ยนแปลงราคาในช่วงเวลาต่างๆ"""
        try:
            current_price = price_data['close'].iloc[-1]

            changes = {}

            # 1 วันที่แล้ว
            if len(price_data) >= 2:
                price_1d = price_data['close'].iloc[-2]
                changes['1_day'] = {
                    'change_percent': round(((current_price - price_1d) / price_1d) * 100, 2),
                    'direction': 'UP' if current_price > price_1d else 'DOWN' if current_price < price_1d else 'FLAT'
                }

            # 5 วันที่แล้ว (1 สัปดาห์)
            if len(price_data) >= 6:
                price_5d = price_data['close'].iloc[-6]
                changes['5_days'] = {
                    'change_percent': round(((current_price - price_5d) / price_5d) * 100, 2),
                    'direction': 'UP' if current_price > price_5d else 'DOWN' if current_price < price_5d else 'FLAT'
                }

            # 20 วันที่แล้ว (1 เดือน)
            if len(price_data) >= 21:
                price_20d = price_data['close'].iloc[-21]
                changes['20_days'] = {
                    'change_percent': round(((current_price - price_20d) / price_20d) * 100, 2),
                    'direction': 'UP' if current_price > price_20d else 'DOWN' if current_price < price_20d else 'FLAT'
                }

            # 60 วันที่แล้ว (3 เดือน)
            if len(price_data) >= 61:
                price_60d = price_data['close'].iloc[-61]
                changes['60_days'] = {
                    'change_percent': round(((current_price - price_60d) / price_60d) * 100, 2),
                    'direction': 'UP' if current_price > price_60d else 'DOWN' if current_price < price_60d else 'FLAT'
                }

            # 252 วันที่แล้ว (1 ปี)
            if len(price_data) >= 253:
                price_252d = price_data['close'].iloc[-253]
                changes['252_days'] = {
                    'change_percent': round(((current_price - price_252d) / price_252d) * 100, 2),
                    'direction': 'UP' if current_price > price_252d else 'DOWN' if current_price < price_252d else 'FLAT'
                }

            return changes

        except Exception as e:
            logger.warning(f"Error analyzing period changes: {e}")
            return {}

    def _analyze_buying_selling_pressure(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """วิเคราะห์แรงซื้อ/แรงขาย"""
        try:
            if len(price_data) < 5:
                return {'pressure': 'NEUTRAL', 'strength': 50}

            recent_data = price_data.tail(5)

            # คำนวณแรงซื้อ/แรงขาย จาก Close vs Open
            buying_days = 0
            selling_days = 0

            for _, row in recent_data.iterrows():
                if row['close'] > row['open']:
                    buying_days += 1
                elif row['close'] < row['open']:
                    selling_days += 1

            # คำนวณ buying/selling pressure
            if buying_days > selling_days:
                pressure = 'BUYING'
                strength = (buying_days / len(recent_data)) * 100
            elif selling_days > buying_days:
                pressure = 'SELLING'
                strength = (selling_days / len(recent_data)) * 100
            else:
                pressure = 'NEUTRAL'
                strength = 50

            # วิเคราะห์จาก Volume
            volume_trend = 'STABLE'
            if 'volume' in price_data.columns:
                recent_volume = price_data['volume'].tail(5).mean()
                avg_volume = price_data['volume'].mean()

                if recent_volume > avg_volume * 1.2:
                    volume_trend = 'INCREASING'
                elif recent_volume < avg_volume * 0.8:
                    volume_trend = 'DECREASING'

            return {
                'pressure': pressure,
                'strength': round(strength, 1),
                'buying_days': buying_days,
                'selling_days': selling_days,
                'volume_trend': volume_trend,
                'interpretation': self._interpret_pressure(pressure, strength, volume_trend)
            }

        except Exception as e:
            logger.warning(f"Error analyzing buying/selling pressure: {e}")
            return {'pressure': 'NEUTRAL', 'strength': 50}

    def _interpret_pressure(self, pressure: str, strength: float, volume_trend: str) -> str:
        """แปลความหมายของแรงซื้อ/แรงขาย"""
        if pressure == 'BUYING':
            if strength > 80 and volume_trend == 'INCREASING':
                return 'แรงซื้อแข็งแกร่งมากพร้อม Volume สูง - สัญญาณบวกที่ดี'
            elif strength > 70:
                return 'แรงซื้อแข็งแกร่ง - แนวโน้มขาขึ้นชัดเจน'
            elif strength > 60:
                return 'มีแรงซื้อมากกว่าแรงขาย - แนวโน้มขาขึ้นปานกลาง'
            else:
                return 'แรงซื้อเล็กน้อย - แนวโน้มขาขึ้นอ่อน'

        elif pressure == 'SELLING':
            if strength > 80 and volume_trend == 'INCREASING':
                return 'แรงขายแข็งแกร่งมากพร้อม Volume สูง - สัญญาณลบที่รุนแรง'
            elif strength > 70:
                return 'แรงขายแข็งแกร่ง - แนวโน้มขาลงชัดเจน'
            elif strength > 60:
                return 'มีแรงขายมากกว่าแรงซื้อ - แนวโน้มขาลงปานกลาง'
            else:
                return 'แรงขายเล็กน้อย - แนวโน้มขาลงอ่อน'

        else:
            return 'แรงซื้อและแรงขายสมดุล - ตลาดไม่มีทิศทางชัดเจน'

    def _analyze_trend_strength(self,
                               price_data: pd.DataFrame,
                               technical_indicators: Dict[str, Any]) -> Dict[str, Any]:
        """ประเมินความแข็งแกร่งของเทรนด์"""
        try:
            if len(price_data) < 50:
                return {'strength': 50, 'trend': 'NEUTRAL'}

            current_price = price_data['close'].iloc[-1]

            # ใช้ Moving Averages เป็นตัววัดเทรนด์
            sma_20 = price_data['close'].rolling(20).mean().iloc[-1]
            sma_50 = price_data['close'].rolling(50).mean().iloc[-1]

            strength_score = 0

            # เช็คตำแหน่งราคา vs MA
            if current_price > sma_20 > sma_50:
                trend = 'UPTREND'
                strength_score += 40
            elif current_price < sma_20 < sma_50:
                trend = 'DOWNTREND'
                strength_score += 40
            else:
                trend = 'SIDEWAYS'
                strength_score += 20

            # เช็คมุมของ MA
            if len(price_data) >= 55:
                sma_20_prev = price_data['close'].rolling(20).mean().iloc[-5]
                sma_20_change = ((sma_20 - sma_20_prev) / sma_20_prev) * 100

                if abs(sma_20_change) > 2:
                    strength_score += 30
                elif abs(sma_20_change) > 1:
                    strength_score += 20
                else:
                    strength_score += 10

            # เช็คความสม่ำเสมอของเทรนด์
            recent_closes = price_data['close'].tail(10)
            if trend == 'UPTREND':
                higher_closes = sum(recent_closes.diff() > 0)
                strength_score += min((higher_closes / 10) * 30, 30)
            elif trend == 'DOWNTREND':
                lower_closes = sum(recent_closes.diff() < 0)
                strength_score += min((lower_closes / 10) * 30, 30)

            return {
                'trend': trend,
                'strength': round(min(strength_score, 100), 1),
                'interpretation': self._interpret_trend_strength(trend, strength_score)
            }

        except Exception as e:
            logger.warning(f"Error analyzing trend strength: {e}")
            return {'strength': 50, 'trend': 'NEUTRAL'}

    def _interpret_trend_strength(self, trend: str, strength: float) -> str:
        """แปลความหมายความแข็งแกร่งของเทรนด์"""
        if trend == 'UPTREND':
            if strength > 80:
                return 'เทรนด์ขาขึ้นที่แข็งแกร่งมาก - โอกาสสูงที่จะขึ้นต่อ'
            elif strength > 60:
                return 'เทรนด์ขาขึ้นที่ดี - แนวโน้มบวก'
            else:
                return 'เทรนด์ขาขึ้นอ่อนแอ - อาจมีการปรับฐาน'
        elif trend == 'DOWNTREND':
            if strength > 80:
                return 'เทรนด์ขาลงที่แข็งแกร่งมาก - ควรระวัง'
            elif strength > 60:
                return 'เทรนด์ขาลงชัดเจน - แนวโน้มลบ'
            else:
                return 'เทรนด์ขาลงอ่อนแอ - อาจมีการกลับตัว'
        else:
            return 'ไม่มีเทรนด์ชัดเจน - ตลาด Sideways'

    def _identify_key_price_levels(self,
                                   price_data: pd.DataFrame,
                                   current_price: float,
                                   technical_indicators: Dict[str, Any] = None) -> Dict[str, Any]:
        """หาจุดสำคัญที่ส่งผลต่อราคา"""
        try:
            # ลองใช้ Support/Resistance จาก TechnicalAnalyzer ก่อน (เพื่อความสอดคล้อง)
            if technical_indicators and 'support_resistance' in technical_indicators:
                sr_data = technical_indicators['support_resistance']
                resistance_1 = sr_data.get('resistance_1')
                support_1 = sr_data.get('support_1')
            else:
                # Fallback: คำนวณเอง
                recent_highs = price_data['high'].tail(20)
                recent_lows = price_data['low'].tail(20)
                resistance_1 = recent_highs.max()
                support_1 = recent_lows.min()

            # หา Pivot Points
            high = price_data['high'].iloc[-1]
            low = price_data['low'].iloc[-1]
            close = price_data['close'].iloc[-2]  # ปิดวันก่อน

            pivot = (high + low + close) / 3
            r1 = (2 * pivot) - low
            s1 = (2 * pivot) - high

            return {
                'current_price': round(current_price, 2),
                'resistance_1': round(resistance_1, 2),
                'support_1': round(support_1, 2),
                'pivot_point': round(pivot, 2),
                'resistance_pivot': round(r1, 2),
                'support_pivot': round(s1, 2),
                'distance_to_resistance': round(((resistance_1 - current_price) / current_price) * 100, 2),
                'distance_to_support': round(((current_price - support_1) / current_price) * 100, 2)
            }

        except Exception as e:
            logger.warning(f"Error identifying key price levels: {e}")
            return {}

    def _analyze_volume_impact(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """วิเคราะห์ผลกระทบของปริมาณการซื้อขาย"""
        try:
            if 'volume' not in price_data.columns:
                return {'volume_status': 'N/A'}

            current_volume = price_data['volume'].iloc[-1]
            avg_volume_20 = price_data['volume'].rolling(20).mean().iloc[-1]

            if pd.isna(current_volume) or pd.isna(avg_volume_20) or avg_volume_20 == 0:
                return {'volume_status': 'N/A'}

            volume_ratio = current_volume / avg_volume_20

            # จำแนกระดับ Volume
            if volume_ratio > 2.0:
                volume_status = 'VERY_HIGH'
                interpretation = 'ปริมาณการซื้อขายสูงมาก - มีความสนใจอย่างมาก'
            elif volume_ratio > 1.5:
                volume_status = 'HIGH'
                interpretation = 'ปริมาณการซื้อขายสูง - มีความเคลื่อนไหวที่น่าสนใจ'
            elif volume_ratio > 0.8:
                volume_status = 'NORMAL'
                interpretation = 'ปริมาณการซื้อขายปกติ'
            elif volume_ratio > 0.5:
                volume_status = 'LOW'
                interpretation = 'ปริมาณการซื้อขายต่ำ - ความเคลื่อนไหวน้อย'
            else:
                volume_status = 'VERY_LOW'
                interpretation = 'ปริมาณการซื้อขายต่ำมาก - ตลาดเงียบ'

            # ตรวจสอบ Volume Trend
            volume_5d = price_data['volume'].tail(5).mean()
            volume_trend = 'INCREASING' if volume_5d > avg_volume_20 else 'DECREASING'

            return {
                'current_volume': int(current_volume),
                'avg_volume_20': int(avg_volume_20),
                'volume_ratio': round(volume_ratio, 2),
                'volume_status': volume_status,
                'volume_trend': volume_trend,
                'interpretation': interpretation
            }

        except Exception as e:
            logger.warning(f"Error analyzing volume impact: {e}")
            return {'volume_status': 'N/A'}

    def _create_change_summary(self,
                              direction: str,
                              change_percent: float,
                              reasons: List[Dict[str, Any]],
                              trend_strength: Dict[str, Any],
                              buying_selling_pressure: Dict[str, Any]) -> str:
        """สร้างสรุปการวิเคราะห์การเปลี่ยนแปลงราคา"""
        try:
            # เริ่มต้นสรุป
            if direction == 'UP':
                summary = f"📈 ราคาขึ้น {abs(change_percent):.2f}% "
            elif direction == 'DOWN':
                summary = f"📉 ราคาลง {abs(change_percent):.2f}% "
            else:
                summary = f"↔️ ราคาไม่เปลี่ยนแปลงมาก ({abs(change_percent):.2f}%) "

            # เพิ่มสาเหตุหลัก
            if reasons:
                top_reason = reasons[0]
                summary += f"เนื่องจาก{top_reason['reason']}"

            # เพิ่มข้อมูลเทรนด์
            trend = trend_strength.get('trend', 'NEUTRAL')
            if trend != 'NEUTRAL':
                summary += f" ซึ่งสอดคล้องกับเทรนด์{trend.lower()}"

            # เพิ่มข้อมูลแรงซื้อ/แรงขาย
            pressure = buying_selling_pressure.get('pressure', 'NEUTRAL')
            if pressure != 'NEUTRAL':
                pressure_thai = 'ซื้อ' if pressure == 'BUYING' else 'ขาย'
                summary += f" พบแรง{pressure_thai}ที่เด่นชัด"

            return summary

        except Exception as e:
            logger.warning(f"Error creating summary: {e}")
            return "ไม่สามารถสรุปการเปลี่ยนแปลงราคาได้"

    def _analyze_profit_taking_opportunity(self,
                                          price_data: pd.DataFrame,
                                          direction: str,
                                          change_percent: float,
                                          technical_indicators: Dict[str, Any],
                                          trend_strength: Dict[str, Any],
                                          buying_selling_pressure: Dict[str, Any],
                                          key_levels: Dict[str, Any],
                                          market_state_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        วิเคราะห์ว่าควรขายกำไรหรือยัง หรือมีโอกาสขึ้นต่ออีก

        Args:
            market_state_analysis: ข้อมูล Dip/Falling Knife/Overextension (NEW)

        Returns:
            Dict ที่มีคำแนะนำว่าควรขายกำไรหรือยัง พร้อมเหตุผล
        """
        try:
            current_price = price_data['close'].iloc[-1]

            # คะแนนรวมในการตัดสินใจ (0-100)
            hold_score = 0  # คะแนนที่บอกว่าควร HOLD (ยังมีโอกาสขึ้นต่อ)
            sell_score = 0  # คะแนนที่บอกว่าควร SELL (ขายกำไร)

            reasons_to_hold = []  # เหตุผลที่ควรถือต่อ
            reasons_to_sell = []  # เหตุผลที่ควรขายกำไร

            # ========== PRIORITY CHECK: Dip/Falling Knife Analysis ==========
            # ตรวจสอบก่อนว่าเป็น Dip หรือ Falling Knife หรือไม่
            if market_state_analysis:
                dip = market_state_analysis.get('dip_opportunity', {})
                falling_knife = market_state_analysis.get('falling_knife', {})
                overext = market_state_analysis.get('overextension', {})

                # กรณี 1: ถ้าเป็น DIP (จุดช้อน) → ไม่ควรขาย ควรถือ/เข้าซื้อ
                if dip.get('is_dip'):
                    dip_quality = dip.get('dip_quality', 'NONE')
                    dip_score = dip.get('opportunity_score', 0)

                    if dip_quality == 'EXCELLENT':
                        hold_score += 60  # Bonus สูงมาก
                        reasons_to_hold.append({
                            'reason': '💎 จุดช้อนคุณภาพยอดเยี่ยม',
                            'detail': f'Dip Quality: {dip_quality} (Score: {dip_score}/100) - โอกาสเข้าทองครับ!',
                            'weight': 60
                        })
                    elif dip_quality == 'GOOD':
                        hold_score += 50
                        reasons_to_hold.append({
                            'reason': '💰 จุดช้อนที่ดี',
                            'detail': f'Dip Quality: {dip_quality} (Score: {dip_score}/100) - ควรถือ/เข้าซื้อ',
                            'weight': 50
                        })
                    elif dip_quality == 'FAIR':
                        hold_score += 30
                        reasons_to_hold.append({
                            'reason': '📉 จุดช้อนปานกลาง',
                            'detail': f'Dip Quality: {dip_quality} (Score: {dip_score}/100) - พิจารณาถือต่อ',
                            'weight': 30
                        })

                # กรณี 2: ถ้าเป็น FALLING KNIFE → ควรออก/อย่าเข้า
                if falling_knife.get('is_falling_knife'):
                    risk_level = falling_knife.get('risk_level', 'UNKNOWN')
                    risk_score = falling_knife.get('risk_score', 0)

                    if risk_level == 'EXTREME':
                        sell_score += 70
                        reasons_to_sell.append({
                            'reason': '🔪 Falling Knife ระดับอันตราย!',
                            'detail': f'Risk: {risk_level} (Score: {risk_score}/100) - ตกต่อเนื่อง ออกก่อน!',
                            'weight': 70
                        })
                    elif risk_level == 'HIGH':
                        sell_score += 50
                        reasons_to_sell.append({
                            'reason': '⚠️ Falling Knife เสี่ยงสูง',
                            'detail': f'Risk: {risk_level} (Score: {risk_score}/100) - อาจตกต่อ ควรออก',
                            'weight': 50
                        })
                    elif risk_level == 'MODERATE':
                        sell_score += 30
                        reasons_to_sell.append({
                            'reason': '⚡ Falling Knife เสี่ยงปานกลาง',
                            'detail': f'Risk: {risk_level} (Score: {risk_score}/100) - ระวัง รอดูอีก 2-3 วัน',
                            'weight': 30
                        })

                # กรณี 3: ถ้าเป็น OVEREXTENDED → ควรขาย
                if overext.get('is_overextended'):
                    severity = overext.get('severity_score', 0)
                    if severity >= 70:
                        sell_score += 50
                        reasons_to_sell.append({
                            'reason': '🔴 ราคาขึ้นเกินจนอันตราย',
                            'detail': f'Severity: {severity}/100 - ติดดอยแน่ ขายเลย!',
                            'weight': 50
                        })
                    elif severity >= 50:
                        sell_score += 35
                        reasons_to_sell.append({
                            'reason': '⚠️ ราคาขึ้นเกินไปแล้ว',
                            'detail': f'Severity: {severity}/100 - ควรขายบางส่วน',
                            'weight': 35
                        })

            # ========== ต่อด้วย Logic เดิม (ถ้ายังไม่มี Dip/Falling Knife ชัดเจน) ==========

            # 1. ตรวจสอบตำแหน่งราคาเทียบกับ Resistance
            if key_levels:
                distance_to_resistance = key_levels.get('distance_to_resistance', 100)

                if distance_to_resistance < 1:  # ใกล้ resistance มาก (<1%)
                    sell_score += 25
                    reasons_to_sell.append({
                        'reason': 'ราคาเข้าใกล้แนวต้าน (Resistance)',
                        'detail': f'ใกล้แนวต้านเพียง {distance_to_resistance:.2f}% อาจมีแรงขายเข้ามา',
                        'weight': 25
                    })
                elif distance_to_resistance < 3:  # ค่อนข้างใกล้ (1-3%)
                    sell_score += 15
                    reasons_to_sell.append({
                        'reason': 'กำลังเข้าใกล้แนวต้าน',
                        'detail': f'ห่างจากแนวต้าน {distance_to_resistance:.2f}% ควรระวัง',
                        'weight': 15
                    })
                elif distance_to_resistance > 5:  # ยังไกลจาก resistance
                    hold_score += 20
                    reasons_to_hold.append({
                        'reason': 'ยังมีพื้นที่ขึ้นได้อีก',
                        'detail': f'ห่างจากแนวต้าน {distance_to_resistance:.2f}% ยังมีโอกาสขึ้นต่อ',
                        'weight': 20
                    })

            # 2. ตรวจสอบ RSI (Overbought/Oversold)
            if technical_indicators:
                rsi = technical_indicators.get('rsi')
                if rsi is not None:
                    if rsi > 75:  # Overbought มาก
                        sell_score += 30
                        reasons_to_sell.append({
                            'reason': 'RSI อยู่ในโซน Overbought มาก',
                            'detail': f'RSI = {rsi:.1f} (>75) ราคาสูงเกินไป มีโอกาสปรับฐาน',
                            'weight': 30
                        })
                    elif rsi > 65:  # Overbought ปานกลาง
                        sell_score += 15
                        reasons_to_sell.append({
                            'reason': 'RSI เริ่มเข้าโซน Overbought',
                            'detail': f'RSI = {rsi:.1f} (>65) ควรระวังการปรับฐาน',
                            'weight': 15
                        })
                    elif 40 <= rsi <= 60:  # Neutral
                        hold_score += 15
                        reasons_to_hold.append({
                            'reason': 'RSI อยู่ในโซนปกติ',
                            'detail': f'RSI = {rsi:.1f} ยังไม่มีสัญญาณ overbought',
                            'weight': 15
                        })

            # 3. ตรวจสอบเทรนด์
            trend_type = trend_strength.get('trend', 'NEUTRAL')
            strength = trend_strength.get('strength', 0)

            if trend_type == 'UPTREND':
                if strength > 70:  # เทรนด์แข็งแกร่ง
                    hold_score += 25
                    reasons_to_hold.append({
                        'reason': 'เทรนด์ขาขึ้นแข็งแกร่ง',
                        'detail': f'เทรนด์มีความแข็งแกร่ง {strength:.1f}/100 น่าจะขึ้นต่อ',
                        'weight': 25
                    })
                elif strength > 50:
                    hold_score += 15
                    reasons_to_hold.append({
                        'reason': 'เทรนด์ขาขึ้นยังดี',
                        'detail': f'เทรนด์มีความแข็งแกร่งปานกลาง ({strength:.1f}/100)',
                        'weight': 15
                    })
                else:  # เทรนด์อ่อนแอ
                    sell_score += 15
                    reasons_to_sell.append({
                        'reason': 'เทรนด์ขาขึ้นอ่อนแอ',
                        'detail': f'เทรนด์ไม่แข็งแกร่ง ({strength:.1f}/100) อาจกลับตัว',
                        'weight': 15
                    })
            elif trend_type == 'DOWNTREND':
                sell_score += 20
                reasons_to_sell.append({
                    'reason': 'เทรนด์กลับเป็นขาลง',
                    'detail': 'เทรนด์เปลี่ยนเป็นขาลงแล้ว ควรขายกำไรก่อน',
                    'weight': 20
                })

            # 4. ตรวจสอบแรงซื้อ/แรงขาย
            pressure_type = buying_selling_pressure.get('pressure', 'NEUTRAL')
            pressure_strength = buying_selling_pressure.get('strength', 0)

            if pressure_type == 'BUYING':
                if pressure_strength > 70:
                    hold_score += 20
                    reasons_to_hold.append({
                        'reason': 'แรงซื้อยังแข็งแกร่ง',
                        'detail': f'แรงซื้อ {pressure_strength:.1f}% ยังมีแรงหนุน',
                        'weight': 20
                    })
                else:
                    hold_score += 10
                    reasons_to_hold.append({
                        'reason': 'มีแรงซื้อสนับสนุน',
                        'detail': f'แรงซื้อ {pressure_strength:.1f}%',
                        'weight': 10
                    })
            elif pressure_type == 'SELLING':
                if pressure_strength > 70:
                    sell_score += 25
                    reasons_to_sell.append({
                        'reason': 'เริ่มมีแรงขายเข้ามา',
                        'detail': f'แรงขาย {pressure_strength:.1f}% อาจกดดันราคา',
                        'weight': 25
                    })
                else:
                    sell_score += 15
                    reasons_to_sell.append({
                        'reason': 'มีแรงขายเล็กน้อย',
                        'detail': f'แรงขาย {pressure_strength:.1f}% ควรระวัง',
                        'weight': 15
                    })

            # 5. ตรวจสอบการขึ้นของราคา (ขึ้นมากแล้วหรือยัง)
            if direction == 'UP':
                # เช็คว่าขึ้นมากแค่ไหนในช่วงที่ผ่านมา
                if len(price_data) >= 21:
                    price_20d_ago = price_data['close'].iloc[-21]
                    gain_20d = ((current_price - price_20d_ago) / price_20d_ago) * 100

                    if gain_20d > 20:  # ขึ้นมาก > 20% ใน 20 วัน
                        sell_score += 20
                        reasons_to_sell.append({
                            'reason': 'ราคาขึ้นมามากแล้ว',
                            'detail': f'ขึ้นไป {gain_20d:.1f}% ใน 20 วัน ควรขายกำไรบางส่วน',
                            'weight': 20
                        })
                    elif gain_20d > 10:  # ขึ้นปานกลาง 10-20%
                        sell_score += 10
                        reasons_to_sell.append({
                            'reason': 'ราคาขึ้นมาพอสมควร',
                            'detail': f'ขึ้นไป {gain_20d:.1f}% ใน 20 วัน ควรระวัง',
                            'weight': 10
                        })
                    elif gain_20d < 5:  # ขึ้นน้อย < 5%
                        hold_score += 15
                        reasons_to_hold.append({
                            'reason': 'ราคายังขึ้นไม่มาก',
                            'detail': f'ขึ้นเพียง {gain_20d:.1f}% ใน 20 วัน ยังมีพื้นที่ขึ้นอีก',
                            'weight': 15
                        })

            # 6. ตรวจสอบ Volume (ถ้ามี)
            if 'volume' in price_data.columns:
                current_volume = price_data['volume'].iloc[-1]
                avg_volume = price_data['volume'].rolling(20).mean().iloc[-1]

                if not pd.isna(current_volume) and not pd.isna(avg_volume) and avg_volume > 0:
                    volume_ratio = current_volume / avg_volume

                    if direction == 'UP' and volume_ratio > 1.5:  # ขึ้นด้วย volume สูง
                        hold_score += 15
                        reasons_to_hold.append({
                            'reason': 'มี Volume หนุน',
                            'detail': f'Volume สูงกว่าปกติ {(volume_ratio-1)*100:.1f}% แสดงแรงซื้อแท้',
                            'weight': 15
                        })
                    elif direction == 'UP' and volume_ratio < 0.8:  # ขึ้นด้วย volume ต่ำ
                        sell_score += 15
                        reasons_to_sell.append({
                            'reason': 'ขึ้นด้วย Volume ต่ำ',
                            'detail': f'Volume ต่ำกว่าปกติ ไม่มีแรงซื้อหนุน อาจไม่ยั่งยืน',
                            'weight': 15
                        })

            # 7. คำนวณคะแนนรวมและสรุป
            # เพิ่ม baseline เพื่อป้องกันค่า 100%/0% ที่ไม่สมจริง
            hold_score = max(hold_score, 10)  # ขั้นต่ำ 10
            sell_score = max(sell_score, 10)  # ขั้นต่ำ 10

            total_score = hold_score + sell_score
            hold_probability = (hold_score / total_score * 100) if total_score > 0 else 50
            sell_probability = (sell_score / total_score * 100) if total_score > 0 else 50

            # เรียงเหตุผลตามน้ำหนัก
            reasons_to_hold.sort(key=lambda x: x.get('weight', 0), reverse=True)
            reasons_to_sell.sort(key=lambda x: x.get('weight', 0), reverse=True)

            # ตัดสินใจ
            if hold_probability > 65:
                recommendation = 'HOLD'
                action = '💎 ถือต่อ - มีโอกาสขึ้นต่อ'
                confidence = 'HIGH'
            elif sell_probability > 65:
                recommendation = 'SELL'
                action = '💰 ควรขายกำไร'
                confidence = 'HIGH'
            elif hold_probability > 55:
                recommendation = 'HOLD'
                action = '⏳ ถือต่อได้ แต่ควรระวัง'
                confidence = 'MEDIUM'
            elif sell_probability > 55:
                recommendation = 'PARTIAL_SELL'
                action = '📊 ควรขายบางส่วนเพื่อลดความเสี่ยง'
                confidence = 'MEDIUM'
            else:
                recommendation = 'WATCH'
                action = '👀 สังเกตการณ์ - ยังไม่ชัดเจน'
                confidence = 'LOW'

            # สร้างคำอธิบายแบบละเอียด
            detailed_explanation = self._create_profit_taking_explanation(
                recommendation, hold_probability, sell_probability,
                reasons_to_hold, reasons_to_sell
            )

            return {
                'recommendation': recommendation,
                'action': action,
                'confidence': confidence,
                'hold_probability': round(hold_probability, 1),
                'sell_probability': round(sell_probability, 1),
                'hold_score': hold_score,
                'sell_score': sell_score,
                'reasons_to_hold': reasons_to_hold[:3],  # Top 3
                'reasons_to_sell': reasons_to_sell[:3],  # Top 3
                'explanation': detailed_explanation,
                'applicable': direction == 'UP' or change_percent > 0  # ใช้ได้เมื่อราคาขึ้น
            }

        except Exception as e:
            logger.warning(f"Error analyzing profit taking opportunity: {e}")
            return {
                'recommendation': 'WATCH',
                'action': '👀 ไม่สามารถวิเคราะห์ได้',
                'confidence': 'LOW',
                'applicable': False
            }

    def _create_profit_taking_explanation(self,
                                         recommendation: str,
                                         hold_prob: float,
                                         sell_prob: float,
                                         reasons_hold: List[Dict],
                                         reasons_sell: List[Dict]) -> str:
        """สร้างคำอธิบายแบบละเอียด"""

        explanation = ""

        if recommendation == 'HOLD':
            explanation = f"📈 **แนะนำให้ถือต่อ** (โอกาสขึ้นต่อ {hold_prob:.1f}%)\n\n"
            if reasons_hold:
                explanation += "เหตุผลที่ควรถือต่อ:\n"
                for reason in reasons_hold[:3]:
                    explanation += f"• {reason['reason']}: {reason['detail']}\n"

        elif recommendation == 'SELL':
            explanation = f"💰 **แนะนำให้ขายกำไร** (โอกาสควรขาย {sell_prob:.1f}%)\n\n"
            if reasons_sell:
                explanation += "เหตุผลที่ควรขาย:\n"
                for reason in reasons_sell[:3]:
                    explanation += f"• {reason['reason']}: {reason['detail']}\n"

        elif recommendation == 'PARTIAL_SELL':
            explanation = f"📊 **แนะนำให้ขายบางส่วน** (ลดความเสี่ยง)\n\n"
            explanation += "สถานการณ์:\n"
            if reasons_sell:
                explanation += "สัญญาณที่ควรขาย:\n"
                for reason in reasons_sell[:2]:
                    explanation += f"• {reason['reason']}: {reason['detail']}\n"
            if reasons_hold:
                explanation += "\nสัญญาณที่ยังดี:\n"
                for reason in reasons_hold[:2]:
                    explanation += f"• {reason['reason']}: {reason['detail']}\n"

        else:  # WATCH
            explanation = f"👀 **สังเกตการณ์** (สัญญาณยังไม่ชัดเจน)\n\n"
            explanation += f"โอกาสถือต่อ: {hold_prob:.1f}% | โอกาสควรขาย: {sell_prob:.1f}%"

        return explanation
