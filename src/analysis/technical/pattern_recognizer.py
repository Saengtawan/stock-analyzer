"""
Chart Pattern Recognition Module
Detects technical analysis chart patterns from price data
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
from scipy.signal import find_peaks, argrelextrema


class PatternRecognizer:
    """
    จดจำ Chart Patterns จากข้อมูลราคา

    Patterns ที่รองรับ:
    - Reversal Patterns: Head & Shoulders, Inverse H&S, Double Top/Bottom
    - Continuation Patterns: Triangles, Flags, Pennants, Wedges, Cup & Handle, Rectangle
    - Candlestick Patterns: Doji, Engulfing, Hammer, Shooting Star
    """

    def __init__(self, price_data: pd.DataFrame, symbol: str = "UNKNOWN"):
        """
        Initialize Pattern Recognizer

        Args:
            price_data: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            symbol: Stock symbol for logging
        """
        self.symbol = symbol
        self.price_data = price_data.copy()

        # Ensure lowercase column names
        self.price_data.columns = [col.lower() for col in self.price_data.columns]

        # Validate required columns
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in self.price_data.columns:
                raise ValueError(f"Missing required column: {col}")

        self.patterns_detected = []

    def detect_all_patterns(self) -> Dict[str, Any]:
        """
        ตรวจจับ Pattern ทั้งหมด

        Returns:
            Dictionary containing all detected patterns
        """
        logger.info(f"🔍 Starting pattern recognition for {self.symbol}")

        try:
            self.patterns_detected = []

            # 1. Reversal Patterns
            self._detect_head_and_shoulders()
            self._detect_inverse_head_and_shoulders()
            self._detect_double_top()
            self._detect_double_bottom()

            # 2. Continuation Patterns
            self._detect_ascending_triangle()
            self._detect_descending_triangle()
            self._detect_symmetrical_triangle()
            self._detect_flag()
            self._detect_pennant()
            self._detect_wedge()
            self._detect_cup_and_handle()
            self._detect_rectangle()

            # 3. Candlestick Patterns (last 10 candles only)
            self._detect_doji()
            self._detect_engulfing()
            self._detect_hammer_shooting_star()

            # 4. Filter expired patterns (key levels too far from current price)
            current_price = self.price_data['close'].iloc[-1]
            self.patterns_detected = self._filter_expired_patterns(self.patterns_detected, current_price)

            # Summarize results
            summary = self._generate_summary()

            return {
                'symbol': self.symbol,
                'patterns_detected': self.patterns_detected,
                'total_patterns': len(self.patterns_detected),
                'summary': summary,
                'has_patterns': len(self.patterns_detected) > 0
            }

        except Exception as e:
            logger.error(f"Pattern recognition failed for {self.symbol}: {e}")
            return {
                'symbol': self.symbol,
                'patterns_detected': [],
                'total_patterns': 0,
                'summary': f'Error: {str(e)}',
                'has_patterns': False
            }

    # ==================== REVERSAL PATTERNS ====================

    def _detect_head_and_shoulders(self):
        """
        ตรวจจับ Head & Shoulders (รูปแบบกลับตัวลง)

        โครงสร้าง: ไหล่ซ้าย → หัว (สูงสุด) → ไหล่ขวา → ทะลุ Neckline ลง
        """
        try:
            if len(self.price_data) < 50:
                return

            highs = self.price_data['high'].values
            closes = self.price_data['close'].values

            # Find peaks (local maxima)
            peaks, _ = find_peaks(highs, distance=5, prominence=np.std(highs) * 0.5)

            if len(peaks) < 3:
                return

            # Check last 3 peaks for H&S pattern
            for i in range(len(peaks) - 2):
                left_shoulder_idx = peaks[i]
                head_idx = peaks[i + 1]
                right_shoulder_idx = peaks[i + 2]

                left_shoulder = highs[left_shoulder_idx]
                head = highs[head_idx]
                right_shoulder = highs[right_shoulder_idx]

                # Conditions for H&S:
                # 1. Head is highest
                # 2. Shoulders are roughly equal (±5%)
                # 3. Neckline can be drawn

                if head > left_shoulder and head > right_shoulder:
                    shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder

                    if shoulder_diff < 0.05:  # Shoulders within 5% of each other
                        # Find neckline (lows between peaks)
                        valley1_idx = left_shoulder_idx + np.argmin(highs[left_shoulder_idx:head_idx])
                        valley2_idx = head_idx + np.argmin(highs[head_idx:right_shoulder_idx])

                        neckline = (highs[valley1_idx] + highs[valley2_idx]) / 2
                        current_price = closes[-1]

                        # Calculate confidence
                        symmetry_score = (1 - shoulder_diff) * 100
                        head_prominence = ((head - max(left_shoulder, right_shoulder)) / head) * 100
                        confidence = min(95, (symmetry_score * 0.6 + head_prominence * 0.4))

                        # Check if pattern is recent (within last 30% of data)
                        if right_shoulder_idx >= len(highs) * 0.7:
                            self.patterns_detected.append({
                                'name': 'Head and Shoulders',
                                'type': 'Reversal',
                                'signal': 'BEARISH',
                                'confidence': round(confidence, 1),
                                'description': '📉 รูปแบบ Head & Shoulders - สัญญาณกลับตัวลง',
                                'interpretation': 'แนะนำขาย หรือตั้ง Stop Loss ที่ Neckline',
                                'key_levels': {
                                    'neckline': round(neckline, 2),
                                    'left_shoulder': round(left_shoulder, 2),
                                    'head': round(head, 2),
                                    'right_shoulder': round(right_shoulder, 2)
                                },
                                'entry_strategy': f'รอทะลุ Neckline (${neckline:.2f}) ลงมาก่อนขาย',
                                'target': round(neckline - (head - neckline), 2),  # Measure rule
                                'detected_at': 'Recent'
                            })
                            return  # Found pattern, exit

        except Exception as e:
            logger.warning(f"H&S detection failed: {e}")

    def _detect_inverse_head_and_shoulders(self):
        """
        ตรวจจับ Inverse Head & Shoulders (รูปแบบกลับตัวขึ้น)
        """
        try:
            if len(self.price_data) < 50:
                return

            lows = self.price_data['low'].values
            closes = self.price_data['close'].values

            # Find valleys (local minima)
            valleys, _ = find_peaks(-lows, distance=5, prominence=np.std(lows) * 0.5)

            if len(valleys) < 3:
                return

            for i in range(len(valleys) - 2):
                left_shoulder_idx = valleys[i]
                head_idx = valleys[i + 1]
                right_shoulder_idx = valleys[i + 2]

                left_shoulder = lows[left_shoulder_idx]
                head = lows[head_idx]
                right_shoulder = lows[right_shoulder_idx]

                # Head is lowest
                if head < left_shoulder and head < right_shoulder:
                    shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder

                    if shoulder_diff < 0.05:
                        # Find neckline (highs between valleys)
                        peak1_idx = left_shoulder_idx + np.argmax(lows[left_shoulder_idx:head_idx])
                        peak2_idx = head_idx + np.argmax(lows[head_idx:right_shoulder_idx])

                        neckline = (lows[peak1_idx] + lows[peak2_idx]) / 2
                        current_price = closes[-1]

                        symmetry_score = (1 - shoulder_diff) * 100
                        head_prominence = ((min(left_shoulder, right_shoulder) - head) / head) * 100
                        confidence = min(95, (symmetry_score * 0.6 + head_prominence * 0.4))

                        if right_shoulder_idx >= len(lows) * 0.7:
                            self.patterns_detected.append({
                                'name': 'Inverse Head and Shoulders',
                                'type': 'Reversal',
                                'signal': 'BULLISH',
                                'confidence': round(confidence, 1),
                                'description': '📈 รูปแบบ Inverse H&S - สัญญาณกลับตัวขึ้น',
                                'interpretation': 'แนะนำซื้อเมื่อทะลุ Neckline ขึ้น',
                                'key_levels': {
                                    'neckline': round(neckline, 2),
                                    'left_shoulder': round(left_shoulder, 2),
                                    'head': round(head, 2),
                                    'right_shoulder': round(right_shoulder, 2)
                                },
                                'entry_strategy': f'รอทะลุ Neckline (${neckline:.2f}) ขึ้นไปก่อนซื้อ',
                                'target': round(neckline + (neckline - head), 2),
                                'detected_at': 'Recent'
                            })
                            return

        except Exception as e:
            logger.warning(f"Inverse H&S detection failed: {e}")

    def _detect_double_top(self):
        """
        ตรวจจับ Double Top (ยอดสองยอด - รูปตัว M)
        """
        try:
            if len(self.price_data) < 30:
                return

            highs = self.price_data['high'].values
            closes = self.price_data['close'].values

            peaks, _ = find_peaks(highs, distance=5)

            if len(peaks) < 2:
                return

            # Check last 2 peaks
            for i in range(len(peaks) - 1):
                peak1_idx = peaks[i]
                peak2_idx = peaks[i + 1]

                peak1 = highs[peak1_idx]
                peak2 = highs[peak2_idx]

                # Peaks should be roughly equal (±3%)
                peak_diff = abs(peak1 - peak2) / peak1

                if peak_diff < 0.03:
                    # Find valley between peaks
                    valley_idx = peak1_idx + np.argmin(highs[peak1_idx:peak2_idx])
                    valley = highs[valley_idx]

                    current_price = closes[-1]

                    # Calculate confidence
                    symmetry_score = (1 - peak_diff) * 100
                    peak_prominence = ((min(peak1, peak2) - valley) / valley) * 100
                    confidence = min(95, (symmetry_score * 0.7 + min(peak_prominence, 30)))

                    if peak2_idx >= len(highs) * 0.7:
                        self.patterns_detected.append({
                            'name': 'Double Top',
                            'type': 'Reversal',
                            'signal': 'BEARISH',
                            'confidence': round(confidence, 1),
                            'description': '📉 รูปแบบ Double Top (รูป M) - สัญญาณกลับตัวลง',
                            'interpretation': 'ราคาพยายามขึ้นถึงจุดเดิมแต่ไม่ผ่าน แล้วกลับลง',
                            'key_levels': {
                                'peak_1': round(peak1, 2),
                                'peak_2': round(peak2, 2),
                                'valley': round(valley, 2)
                            },
                            'entry_strategy': f'รอทะลุ Valley (${valley:.2f}) ลงมาก่อนขาย',
                            'target': round(valley - (peak1 - valley), 2),
                            'detected_at': 'Recent'
                        })
                        return

        except Exception as e:
            logger.warning(f"Double Top detection failed: {e}")

    def _detect_double_bottom(self):
        """
        ตรวจจับ Double Bottom (ก้นสองก้น - รูปตัว W)
        """
        try:
            if len(self.price_data) < 30:
                return

            lows = self.price_data['low'].values
            closes = self.price_data['close'].values

            valleys, _ = find_peaks(-lows, distance=5)

            if len(valleys) < 2:
                return

            for i in range(len(valleys) - 1):
                valley1_idx = valleys[i]
                valley2_idx = valleys[i + 1]

                valley1 = lows[valley1_idx]
                valley2 = lows[valley2_idx]

                valley_diff = abs(valley1 - valley2) / valley1

                if valley_diff < 0.03:
                    # Find peak between valleys
                    peak_idx = valley1_idx + np.argmax(lows[valley1_idx:valley2_idx])
                    peak = lows[peak_idx]

                    current_price = closes[-1]

                    symmetry_score = (1 - valley_diff) * 100
                    valley_prominence = ((peak - max(valley1, valley2)) / peak) * 100
                    confidence = min(95, (symmetry_score * 0.7 + min(valley_prominence, 30)))

                    if valley2_idx >= len(lows) * 0.7:
                        self.patterns_detected.append({
                            'name': 'Double Bottom',
                            'type': 'Reversal',
                            'signal': 'BULLISH',
                            'confidence': round(confidence, 1),
                            'description': '📈 รูปแบบ Double Bottom (รูป W) - สัญญาณกลับตัวขึ้น',
                            'interpretation': 'ราคาลงถึงจุดเดิมแล้วกลับขึ้น แนวรับแข็งแรง',
                            'key_levels': {
                                'valley_1': round(valley1, 2),
                                'valley_2': round(valley2, 2),
                                'peak': round(peak, 2)
                            },
                            'entry_strategy': f'รอทะลุ Peak (${peak:.2f}) ขึ้นไปก่อนซื้อ',
                            'target': round(peak + (peak - valley1), 2),
                            'detected_at': 'Recent'
                        })
                        return

        except Exception as e:
            logger.warning(f"Double Bottom detection failed: {e}")

    # ==================== CONTINUATION PATTERNS ====================

    def _detect_ascending_triangle(self):
        """
        ตรวจจับ Ascending Triangle (สามเหลี่ยมขาขึ้น)
        แนวต้านแนวนอน + แนวรับลาดขึ้น
        """
        try:
            if len(self.price_data) < 40:
                return

            # Use last 40 bars
            recent_data = self.price_data.tail(40)
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values

            # Find resistance (flat top)
            resistance = np.max(highs[-20:])  # Last 20 bars
            resistance_touches = np.sum(highs[-20:] >= resistance * 0.99)

            # Find support trendline (rising lows)
            valleys, _ = find_peaks(-lows, distance=3)

            if len(valleys) >= 2 and resistance_touches >= 2:
                # Check if lows are rising
                recent_valleys = valleys[-3:] if len(valleys) >= 3 else valleys
                valley_lows = [lows[v] for v in recent_valleys]

                if len(valley_lows) >= 2:
                    is_rising = all(valley_lows[i] < valley_lows[i+1] for i in range(len(valley_lows)-1))

                    if is_rising:
                        current_price = closes[-1]
                        support_slope = (valley_lows[-1] - valley_lows[0]) / len(valley_lows)

                        # Confidence based on pattern clarity
                        confidence = 70 + (resistance_touches * 5) + (len(recent_valleys) * 3)
                        confidence = min(confidence, 90)

                        self.patterns_detected.append({
                            'name': 'Ascending Triangle',
                            'type': 'Continuation',
                            'signal': 'BULLISH',
                            'confidence': round(confidence, 1),
                            'description': '📈 รูปแบบ Ascending Triangle - มักทะลุขึ้นต่อ',
                            'interpretation': 'แนวต้านแนวนอน + แนวรับลาดขึ้น → แรงซื้อเพิ่มขึ้น',
                            'key_levels': {
                                'resistance': round(resistance, 2),
                                'current_support': round(valley_lows[-1], 2)
                            },
                            'entry_strategy': f'รอทะลุแนวต้าน (${resistance:.2f}) ด้วย Volume สูง',
                            'target': round(resistance + (resistance - valley_lows[0]), 2),
                            'detected_at': 'Recent'
                        })

        except Exception as e:
            logger.warning(f"Ascending Triangle detection failed: {e}")

    def _detect_descending_triangle(self):
        """
        ตรวจจับ Descending Triangle (สามเหลี่ยมขาลง)
        แนวรับแนวนอน + แนวต้านลาดลง
        """
        try:
            if len(self.price_data) < 40:
                return

            recent_data = self.price_data.tail(40)
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values

            # Find support (flat bottom)
            support = np.min(lows[-20:])
            support_touches = np.sum(lows[-20:] <= support * 1.01)

            # Find resistance trendline (falling highs)
            peaks, _ = find_peaks(highs, distance=3)

            if len(peaks) >= 2 and support_touches >= 2:
                recent_peaks = peaks[-3:] if len(peaks) >= 3 else peaks
                peak_highs = [highs[p] for p in recent_peaks]

                if len(peak_highs) >= 2:
                    is_falling = all(peak_highs[i] > peak_highs[i+1] for i in range(len(peak_highs)-1))

                    if is_falling:
                        current_price = closes[-1]

                        confidence = 70 + (support_touches * 5) + (len(recent_peaks) * 3)
                        confidence = min(confidence, 90)

                        self.patterns_detected.append({
                            'name': 'Descending Triangle',
                            'type': 'Continuation',
                            'signal': 'BEARISH',
                            'confidence': round(confidence, 1),
                            'description': '📉 รูปแบบ Descending Triangle - มักทะลุลงต่อ',
                            'interpretation': 'แนวรับแนวนอน + แนวต้านลาดลง → แรงขายเพิ่มขึ้น',
                            'key_levels': {
                                'support': round(support, 2),
                                'current_resistance': round(peak_highs[-1], 2)
                            },
                            'entry_strategy': f'รอทะลุแนวรับ (${support:.2f}) ลงมาก่อนขาย',
                            'target': round(support - (peak_highs[0] - support), 2),
                            'detected_at': 'Recent'
                        })

        except Exception as e:
            logger.warning(f"Descending Triangle detection failed: {e}")

    def _detect_symmetrical_triangle(self):
        """
        ตรวจจับ Symmetrical Triangle (สามเหลี่ยมสมมาตร)
        แนวต้านลาดลง + แนวรับลาดขึ้น → มาบรรจบกัน
        """
        try:
            if len(self.price_data) < 40:
                return

            recent_data = self.price_data.tail(40)
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values

            peaks, _ = find_peaks(highs, distance=3)
            valleys, _ = find_peaks(-lows, distance=3)

            if len(peaks) >= 2 and len(valleys) >= 2:
                # Check if highs are falling
                recent_peaks = peaks[-3:] if len(peaks) >= 3 else peaks
                peak_highs = [highs[p] for p in recent_peaks]
                is_falling_highs = len(peak_highs) >= 2 and all(peak_highs[i] > peak_highs[i+1] for i in range(len(peak_highs)-1))

                # Check if lows are rising
                recent_valleys = valleys[-3:] if len(valleys) >= 3 else valleys
                valley_lows = [lows[v] for v in recent_valleys]
                is_rising_lows = len(valley_lows) >= 2 and all(valley_lows[i] < valley_lows[i+1] for i in range(len(valley_lows)-1))

                if is_falling_highs and is_rising_lows:
                    current_price = closes[-1]

                    # Check if converging
                    high_range = peak_highs[0] - peak_highs[-1]
                    low_range = valley_lows[-1] - valley_lows[0]

                    if high_range > 0 and low_range > 0:
                        convergence_ratio = min(high_range, low_range) / max(high_range, low_range)

                        if convergence_ratio > 0.5:  # Relatively symmetrical
                            confidence = 65 + (convergence_ratio * 20)

                            self.patterns_detected.append({
                                'name': 'Symmetrical Triangle',
                                'type': 'Continuation',
                                'signal': 'NEUTRAL',
                                'confidence': round(confidence, 1),
                                'description': '🔄 รูปแบบ Symmetrical Triangle - รอทิศทางใหม่',
                                'interpretation': 'ตลาดกำลังรวมตัว มักไปต่อทิศทางเดิม',
                                'key_levels': {
                                    'upper_trendline': round(peak_highs[-1], 2),
                                    'lower_trendline': round(valley_lows[-1], 2)
                                },
                                'entry_strategy': 'รอทะลุออกจากสามเหลี่ยม แล้วตามทิศทางที่ทะลุ',
                                'detected_at': 'Recent'
                            })

        except Exception as e:
            logger.warning(f"Symmetrical Triangle detection failed: {e}")

    def _detect_flag(self):
        """
        ตรวจจับ Flag (ธง)
        Flagpole (เทรนด์แรง) + Flag (กรอบเล็กๆ เอียงทวนเทรนด์)
        """
        try:
            if len(self.price_data) < 30:
                return

            closes = self.price_data['close'].values

            # Check for strong move (flagpole) in last 10-20 bars
            for i in range(10, 21):
                if len(closes) < i + 10:
                    continue

                pole_start = closes[-(i+10)]
                pole_end = closes[-i]
                pole_move = (pole_end - pole_start) / pole_start

                # Strong move (>5% in 10 bars)
                if abs(pole_move) > 0.05:
                    # Check for consolidation (flag) in last 10 bars
                    flag_data = closes[-i:]
                    flag_range = (np.max(flag_data) - np.min(flag_data)) / np.mean(flag_data)

                    # Flag should be small consolidation (<3% range)
                    if flag_range < 0.03:
                        is_bullish = pole_move > 0

                        self.patterns_detected.append({
                            'name': 'Flag',
                            'type': 'Continuation',
                            'signal': 'BULLISH' if is_bullish else 'BEARISH',
                            'confidence': 75,
                            'description': f'🚩 รูปแบบ {"Bullish" if is_bullish else "Bearish"} Flag - พักตัวสั้นๆ',
                            'interpretation': f'แรง{"ซื้อ" if is_bullish else "ขาย"}แรง → พักตัว → มักไปต่อทิศทางเดิม',
                            'key_levels': {
                                'flagpole_start': round(pole_start, 2),
                                'flagpole_end': round(pole_end, 2),
                                'flag_high': round(np.max(flag_data), 2),
                                'flag_low': round(np.min(flag_data), 2)
                            },
                            'entry_strategy': f'รอทะลุออกจากธง ไปทิศทาง{"ขึ้น" if is_bullish else "ลง"}',
                            'detected_at': 'Recent'
                        })
                        return

        except Exception as e:
            logger.warning(f"Flag detection failed: {e}")

    def _detect_pennant(self):
        """
        ตรวจจับ Pennant (ธงสามเหลี่ยม)
        คล้าย Flag แต่เป็นสามเหลี่ยมเล็กๆ
        """
        try:
            if len(self.price_data) < 30:
                return

            closes = self.price_data['close'].values
            highs = self.price_data['high'].values
            lows = self.price_data['low'].values

            # Check for strong move (flagpole)
            for i in range(10, 21):
                if len(closes) < i + 10:
                    continue

                pole_start = closes[-(i+10)]
                pole_end = closes[-i]
                pole_move = (pole_end - pole_start) / pole_start

                if abs(pole_move) > 0.05:
                    # Check for converging pennant (small triangle)
                    pennant_highs = highs[-i:]
                    pennant_lows = lows[-i:]

                    high_range_start = np.max(pennant_highs[:5]) - np.min(pennant_highs[:5])
                    high_range_end = np.max(pennant_highs[-5:]) - np.min(pennant_highs[-5:])

                    # Converging pattern (range decreases)
                    if high_range_end < high_range_start * 0.7:
                        is_bullish = pole_move > 0

                        self.patterns_detected.append({
                            'name': 'Pennant',
                            'type': 'Continuation',
                            'signal': 'BULLISH' if is_bullish else 'BEARISH',
                            'confidence': 72,
                            'description': f'🚩 รูปแบบ {"Bullish" if is_bullish else "Bearish"} Pennant - ธงสามเหลี่ยม',
                            'interpretation': f'เทรนด์แรง → พักตัวเล็กน้อย → มักไปต่อ',
                            'key_levels': {
                                'flagpole_move': round(pole_move * 100, 1),
                                'pennant_apex': round(closes[-1], 2)
                            },
                            'entry_strategy': 'รอทะลุออกจากสามเหลี่ยม',
                            'detected_at': 'Recent'
                        })
                        return

        except Exception as e:
            logger.warning(f"Pennant detection failed: {e}")

    def _detect_wedge(self):
        """
        ตรวจจับ Wedge (ลิ่ม)
        Rising Wedge (ลาดขึ้น) = Bearish
        Falling Wedge (ลาดลง) = Bullish
        """
        try:
            if len(self.price_data) < 40:
                return

            recent_data = self.price_data.tail(40)
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values

            peaks, _ = find_peaks(highs, distance=3)
            valleys, _ = find_peaks(-lows, distance=3)

            if len(peaks) >= 3 and len(valleys) >= 3:
                # Check slope direction
                recent_peaks = peaks[-3:]
                recent_valleys = valleys[-3:]

                peak_highs = [highs[p] for p in recent_peaks]
                valley_lows = [lows[v] for v in recent_valleys]

                # Rising Wedge: Both lines rising, but converging
                peak_slope = (peak_highs[-1] - peak_highs[0]) / len(peak_highs)
                valley_slope = (valley_lows[-1] - valley_lows[0]) / len(valley_lows)

                if peak_slope > 0 and valley_slope > 0:
                    # Both rising → Rising Wedge (Bearish)
                    if valley_slope > peak_slope * 0.5:  # Converging
                        self.patterns_detected.append({
                            'name': 'Rising Wedge',
                            'type': 'Continuation',
                            'signal': 'BEARISH',
                            'confidence': 68,
                            'description': '📉 รูปแบบ Rising Wedge - มักกลับลง',
                            'interpretation': 'ราคาขึ้นแต่แรงขึ้นอ่อนลง → สัญญาณกลับตัว',
                            'key_levels': {
                                'upper_trendline': round(peak_highs[-1], 2),
                                'lower_trendline': round(valley_lows[-1], 2)
                            },
                            'entry_strategy': 'รอทะลุเส้นล่างลงมาก่อนขาย',
                            'detected_at': 'Recent'
                        })

                elif peak_slope < 0 and valley_slope < 0:
                    # Both falling → Falling Wedge (Bullish)
                    if abs(valley_slope) < abs(peak_slope) * 2:  # Converging
                        self.patterns_detected.append({
                            'name': 'Falling Wedge',
                            'type': 'Continuation',
                            'signal': 'BULLISH',
                            'confidence': 68,
                            'description': '📈 รูปแบบ Falling Wedge - มักกลับขึ้น',
                            'interpretation': 'ราคาลงแต่แรงลงอ่อนลง → สัญญาณกลับตัว',
                            'key_levels': {
                                'upper_trendline': round(peak_highs[-1], 2),
                                'lower_trendline': round(valley_lows[-1], 2)
                            },
                            'entry_strategy': 'รอทะลุเส้นบนขึ้นไปก่อนซื้อ',
                            'detected_at': 'Recent'
                        })

        except Exception as e:
            logger.warning(f"Wedge detection failed: {e}")

    def _detect_cup_and_handle(self):
        """
        ตรวจจับ Cup & Handle (ถ้วยและหูจับ)
        รูปแบบขาขึ้นระยะยาว: Cup (รูป U) + Handle (พักตัวเล็กน้อย)
        """
        try:
            if len(self.price_data) < 60:
                return

            closes = self.price_data['close'].values

            # Divide into Cup (40-50 bars) and Handle (10-20 bars)
            cup_data = closes[-60:-15]
            handle_data = closes[-15:]

            if len(cup_data) < 30 or len(handle_data) < 10:
                return

            # Cup should be U-shaped (down then up)
            cup_left = cup_data[0]
            cup_bottom = np.min(cup_data)
            cup_right = cup_data[-1]

            # Check if cup is U-shaped
            bottom_idx = np.argmin(cup_data)
            if bottom_idx > 10 and bottom_idx < len(cup_data) - 10:  # Bottom in middle
                # Cup should recover to near starting point
                recovery_ratio = cup_right / cup_left

                if recovery_ratio > 0.95 and recovery_ratio < 1.05:  # Within 5%
                    # Handle should be a small pullback
                    handle_high = np.max(handle_data)
                    handle_low = np.min(handle_data)
                    handle_pullback = (handle_high - handle_low) / handle_high

                    if handle_pullback > 0.03 and handle_pullback < 0.15:  # 3-15% pullback
                        self.patterns_detected.append({
                            'name': 'Cup and Handle',
                            'type': 'Continuation',
                            'signal': 'BULLISH',
                            'confidence': 80,
                            'description': '📈☕ รูปแบบ Cup & Handle - สัญญาณขาขึ้นแรง',
                            'interpretation': 'รูปแบบขาขึ้นระยะยาว → มักทะลุขึ้นแรง',
                            'key_levels': {
                                'cup_left': round(cup_left, 2),
                                'cup_bottom': round(cup_bottom, 2),
                                'cup_right': round(cup_right, 2),
                                'handle_low': round(handle_low, 2)
                            },
                            'entry_strategy': f'รอทะลุ Handle (${handle_high:.2f}) ด้วย Volume สูง',
                            'target': round(handle_high + (cup_right - cup_bottom), 2),
                            'detected_at': 'Recent'
                        })

        except Exception as e:
            logger.warning(f"Cup & Handle detection failed: {e}")

    def _detect_rectangle(self):
        """
        ตรวจจับ Rectangle / Channel (กรอบราคา)
        ราคาวิ่งในกรอบแนวนอน (Sideways)
        """
        try:
            if len(self.price_data) < 30:
                return

            recent_data = self.price_data.tail(30)
            highs = recent_data['high'].values
            lows = recent_data['low'].values
            closes = recent_data['close'].values

            # Calculate resistance and support
            resistance = np.max(highs)
            support = np.min(lows)

            # Count touches
            resistance_touches = np.sum(highs >= resistance * 0.98)
            support_touches = np.sum(lows <= support * 1.02)

            # Check if price is oscillating in range
            price_range = (resistance - support) / support

            # Rectangle if: touches at least 2 times each, range 3-10%
            if resistance_touches >= 2 and support_touches >= 2 and 0.03 < price_range < 0.10:
                current_price = closes[-1]

                self.patterns_detected.append({
                    'name': 'Rectangle',
                    'type': 'Continuation',
                    'signal': 'NEUTRAL',
                    'confidence': 70,
                    'description': '📦 รูปแบบ Rectangle - ตลาด Sideways',
                    'interpretation': 'ราคาวิ่งในกรอบ รอทะลุแนวรับหรือแนวต้าน',
                    'key_levels': {
                        'resistance': round(resistance, 2),
                        'support': round(support, 2),
                        'midpoint': round((resistance + support) / 2, 2)
                    },
                    'entry_strategy': 'เทรดในกรอบ: ซื้อใกล้รับ ขายใกล้ต้าน',
                    'breakout_strategy': 'รอทะลุกรอบแล้วตามทิศทางที่ทะลุ',
                    'detected_at': 'Recent'
                })

        except Exception as e:
            logger.warning(f"Rectangle detection failed: {e}")

    # ==================== CANDLESTICK PATTERNS ====================

    def _detect_doji(self):
        """
        ตรวจจับ Doji (โดจิ)
        แท่งเทียนที่เปิด-ปิดใกล้เคียงกัน → ตลาดลังเล
        """
        try:
            if len(self.price_data) < 5:
                return

            # Check last 3 candles
            for i in range(-3, 0):
                open_price = self.price_data['open'].iloc[i]
                close_price = self.price_data['close'].iloc[i]
                high_price = self.price_data['high'].iloc[i]
                low_price = self.price_data['low'].iloc[i]

                # Body size
                body = abs(close_price - open_price)
                full_range = high_price - low_price

                # Doji if body < 5% of full range
                if full_range > 0 and body / full_range < 0.05:
                    self.patterns_detected.append({
                        'name': 'Doji',
                        'type': 'Candlestick',
                        'signal': 'NEUTRAL',
                        'confidence': 65,
                        'description': '🕯️ รูปแบบ Doji - ตลาดลังเล',
                        'interpretation': 'เปิด-ปิดใกล้กัน ตลาดไม่แน่ใจทิศทาง อาจกลับตัว',
                        'candle_position': 'Recent' if i == -1 else f'{abs(i)} candles ago',
                        'detected_at': 'Recent'
                    })
                    return  # Report only once

        except Exception as e:
            logger.warning(f"Doji detection failed: {e}")

    def _detect_engulfing(self):
        """
        ตรวจจับ Engulfing (กลืน)
        Bullish Engulfing: แท่งเขียวใหญ่กลืนแท่งแดงก่อนหน้า
        Bearish Engulfing: แท่งแดงใหญ่กลืนแท่งเขียวก่อนหน้า
        """
        try:
            if len(self.price_data) < 5:
                return

            # Check last 3 pairs
            for i in range(-3, -1):
                prev_open = self.price_data['open'].iloc[i]
                prev_close = self.price_data['close'].iloc[i]
                curr_open = self.price_data['open'].iloc[i+1]
                curr_close = self.price_data['close'].iloc[i+1]

                prev_body = abs(prev_close - prev_open)
                curr_body = abs(curr_close - curr_open)

                # Bullish Engulfing
                if prev_close < prev_open and curr_close > curr_open:  # Prev red, Curr green
                    if curr_close > prev_open and curr_open < prev_close:  # Engulfs
                        self.patterns_detected.append({
                            'name': 'Bullish Engulfing',
                            'type': 'Candlestick',
                            'signal': 'BULLISH',
                            'confidence': 78,
                            'description': '🕯️📈 Bullish Engulfing - สัญญาณขาขึ้น',
                            'interpretation': 'แท่งเขียวใหญ่กลืนแท่งแดง แรงซื้อเข้ามา',
                            'detected_at': 'Recent'
                        })
                        return

                # Bearish Engulfing
                elif prev_close > prev_open and curr_close < curr_open:  # Prev green, Curr red
                    if curr_close < prev_open and curr_open > prev_close:  # Engulfs
                        self.patterns_detected.append({
                            'name': 'Bearish Engulfing',
                            'type': 'Candlestick',
                            'signal': 'BEARISH',
                            'confidence': 78,
                            'description': '🕯️📉 Bearish Engulfing - สัญญาณขาลง',
                            'interpretation': 'แท่งแดงใหญ่กลืนแท่งเขียว แรงขายเข้ามา',
                            'detected_at': 'Recent'
                        })
                        return

        except Exception as e:
            logger.warning(f"Engulfing detection failed: {e}")

    def _detect_hammer_shooting_star(self):
        """
        ตรวจจับ Hammer / Shooting Star
        Hammer: หางยาวด้านล่าง (ที่ก้น) → กลับขึ้น
        Shooting Star: หางยาวด้านบน (ที่ยอด) → กลับลง
        """
        try:
            if len(self.price_data) < 5:
                return

            # Check last 3 candles
            for i in range(-3, 0):
                open_price = self.price_data['open'].iloc[i]
                close_price = self.price_data['close'].iloc[i]
                high_price = self.price_data['high'].iloc[i]
                low_price = self.price_data['low'].iloc[i]

                body = abs(close_price - open_price)
                full_range = high_price - low_price

                if full_range == 0:
                    continue

                upper_wick = high_price - max(open_price, close_price)
                lower_wick = min(open_price, close_price) - low_price

                # Hammer: Lower wick > 2x body, upper wick < body
                if lower_wick > body * 2 and upper_wick < body:
                    self.patterns_detected.append({
                        'name': 'Hammer',
                        'type': 'Candlestick',
                        'signal': 'BULLISH',
                        'confidence': 72,
                        'description': '🕯️🔨 Hammer - สัญญาณกลับขึ้น',
                        'interpretation': 'หางยาวด้านล่าง แรงซื้อดันราคากลับขึ้น (ควรเกิดที่ก้น)',
                        'detected_at': 'Recent'
                    })
                    return

                # Shooting Star: Upper wick > 2x body, lower wick < body
                elif upper_wick > body * 2 and lower_wick < body:
                    self.patterns_detected.append({
                        'name': 'Shooting Star',
                        'type': 'Candlestick',
                        'signal': 'BEARISH',
                        'confidence': 72,
                        'description': '🕯️⭐ Shooting Star - สัญญาณกลับลง',
                        'interpretation': 'หางยาวด้านบน แรงขายดันราคากลับลง (ควรเกิดที่ยอด)',
                        'detected_at': 'Recent'
                    })
                    return

        except Exception as e:
            logger.warning(f"Hammer/Shooting Star detection failed: {e}")

    # ==================== SUMMARY ====================

    def _filter_expired_patterns(self, patterns: List[Dict[str, Any]], current_price: float,
                                  max_distance_pct: float = 0.10) -> List[Dict[str, Any]]:
        """
        กรอง Pattern ที่หมดอายุออก (key levels ห่างจากราคาปัจจุบันมากเกินไป)

        Args:
            patterns: รายการ patterns ที่ตรวจพบ
            current_price: ราคาปัจจุบัน
            max_distance_pct: ระยะห่างสูงสุดที่ยอมรับได้ (default 10%)

        Returns:
            รายการ patterns ที่ยังไม่หมดอายุ
        """
        if not patterns:
            return patterns

        valid_patterns = []

        for pattern in patterns:
            # Candlestick patterns ไม่มี key_levels → ผ่านเสมอ
            if pattern['type'] == 'Candlestick':
                valid_patterns.append(pattern)
                continue

            # Check key levels
            key_levels = pattern.get('key_levels', {})
            if not key_levels:
                # ถ้าไม่มี key_levels ให้ผ่าน (เผื่อ pattern แปลกๆ)
                valid_patterns.append(pattern)
                continue

            # หาระยะห่างเฉลี่ยของ key levels จากราคาปัจจุบัน
            distances = []
            for level_name, level_value in key_levels.items():
                if isinstance(level_value, (int, float)) and level_value > 0:
                    distance_pct = abs(level_value - current_price) / current_price
                    distances.append(distance_pct)

            if distances:
                avg_distance = sum(distances) / len(distances)

                # ถ้าระยะห่างเฉลี่ย <= max_distance_pct → ยังใช้ได้
                if avg_distance <= max_distance_pct:
                    valid_patterns.append(pattern)
                else:
                    logger.debug(f"🗑️ Filtered expired pattern: {pattern['name']} "
                               f"(avg distance {avg_distance*100:.1f}% > {max_distance_pct*100}%)")
            else:
                # ถ้าคำนวณ distance ไม่ได้ ให้ผ่าน
                valid_patterns.append(pattern)

        filtered_count = len(patterns) - len(valid_patterns)
        if filtered_count > 0:
            logger.info(f"🗑️ Filtered {filtered_count} expired patterns (too far from current price ${current_price:.2f})")

        return valid_patterns

    def _generate_summary(self) -> str:
        """
        สรุปผล Pattern ที่พบทั้งหมด
        """
        if not self.patterns_detected:
            return "ไม่พบ Pattern ที่ชัดเจน"

        total = len(self.patterns_detected)
        bullish_count = sum(1 for p in self.patterns_detected if p['signal'] == 'BULLISH')
        bearish_count = sum(1 for p in self.patterns_detected if p['signal'] == 'BEARISH')
        neutral_count = sum(1 for p in self.patterns_detected if p['signal'] == 'NEUTRAL')

        # Dominant signal
        if bullish_count > bearish_count and bullish_count > neutral_count:
            signal = "สัญญาณ BULLISH เด่น"
        elif bearish_count > bullish_count and bearish_count > neutral_count:
            signal = "สัญญาณ BEARISH เด่น"
        elif neutral_count > 0:
            signal = "สัญญาณ NEUTRAL / Sideway"
        else:
            signal = "สัญญาณผสม"

        pattern_names = [p['name'] for p in self.patterns_detected]

        return f"พบ {total} patterns: {bullish_count} Bullish, {bearish_count} Bearish, {neutral_count} Neutral → {signal}"
