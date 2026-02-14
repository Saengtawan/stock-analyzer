"""
4-Layer Entry Protection Filter (v6.23: Adaptive Timing)

Prevents buying at daily highs during opening volatility spike.

Layers:
1. Time Filter: Adaptive timing based on gap % (v6.23)
   - Gap Down <-1.5%: Block 5 min (buy early for bottom fishing)
   - Mild Gap Down: Block 10 min (wait for stabilization)
   - Flat: Block 15 min (standard protection)
   - Gap Up >+0.5%: Block 20 min (wait for pullback)
2. VWAP Filter: Block if extended > 1.5% from VWAP
3. Limit Order: Max 0.2% chase from signal price
4. Intraday Position Filter: Block if buying near day's high (v6.22)

Author: Claude Sonnet 4.5
Date: 2026-02-14
"""

from typing import Dict, Tuple, Optional
from datetime import datetime, time
from dataclasses import dataclass
from loguru import logger
import pandas as pd
import pytz


@dataclass
class EntryProtectionStats:
    """Track rejection statistics"""
    total_signals: int = 0
    layer1_blocks: int = 0  # Time filter
    layer2_blocks: int = 0  # VWAP filter
    layer3_blocks: int = 0  # Limit order timeout
    layer4_blocks: int = 0  # Intraday position filter (v6.22)
    passed: int = 0
    discount_exceptions: int = 0  # Allowed despite being early


class EntryProtectionFilter:
    """
    4-Layer Entry Protection System (v6.22)

    Prevents buying at opening spike highs by using layered filters:
    - Layer 1: Time-based (opening volatility window)
    - Layer 2: Price-based (VWAP distance)
    - Layer 3: Execution-based (limit orders only)
    - Layer 4: Intraday position (prevent buying near day's high)
    """

    def __init__(self, config):
        """
        Initialize Entry Protection Filter

        Args:
            config: RapidRotationConfig or dict with settings
        """
        self.enabled = getattr(config, 'entry_protection_enabled', True)

        # Layer 1: Time Filter (v6.23: Adaptive timing based on gap)
        self.block_minutes = getattr(config, 'entry_block_minutes_after_open', 15)
        self.allow_discount = getattr(config, 'entry_allow_discount_exception', True)
        self.discount_threshold = getattr(config, 'entry_discount_exception_pct', -0.5)

        # Adaptive timing (v6.23): Different block times based on gap %
        self.adaptive_timing_enabled = getattr(config, 'entry_adaptive_timing_enabled', True)
        self.adaptive_gap_down_strong_minutes = getattr(config, 'entry_adaptive_gap_down_strong_minutes', 5)  # <-1.5%
        self.adaptive_gap_down_mild_minutes = getattr(config, 'entry_adaptive_gap_down_mild_minutes', 10)    # -1.5% to -0.5%
        self.adaptive_flat_minutes = getattr(config, 'entry_adaptive_flat_minutes', 15)                       # -0.5% to +0.5%
        self.adaptive_gap_up_minutes = getattr(config, 'entry_adaptive_gap_up_minutes', 20)                   # >+0.5%

        # Layer 2: VWAP Filter
        self.vwap_max_distance = getattr(config, 'entry_vwap_max_distance_pct', 1.5)
        self.vwap_allow_below = getattr(config, 'entry_vwap_allow_below', True)

        # Layer 3: Limit Order
        self.limit_only = getattr(config, 'entry_limit_order_only', True)
        self.max_chase = getattr(config, 'entry_max_chase_pct', 0.2)
        self.limit_timeout = getattr(config, 'entry_limit_timeout_minutes', 5)

        # Layer 4: Intraday Position Filter (v6.22)
        self.intraday_max_range_pct = getattr(config, 'entry_intraday_max_range_pct', 80.0)  # Block if in top 20%
        self.intraday_max_move_from_low = getattr(config, 'entry_intraday_max_move_from_low', 2.5)  # Block if > 2.5% from low
        self.intraday_strict_after_minutes = getattr(config, 'entry_intraday_strict_after_minutes', 120)  # Stricter after 2hr

        # Market hours
        self.market_open_hour = getattr(config, 'market_open_hour', 9)
        self.market_open_minute = getattr(config, 'market_open_minute', 30)

        # Statistics
        self.track_rejections = getattr(config, 'entry_track_rejections', True)
        self.stats = EntryProtectionStats()

        logger.info(f"🛡️ Entry Protection Filter initialized (enabled={self.enabled})")
        if self.enabled:
            if self.adaptive_timing_enabled:
                logger.info(f"   Layer 1: Adaptive timing (Gap Down <-1.5%: {self.adaptive_gap_down_strong_minutes}min, Mild: {self.adaptive_gap_down_mild_minutes}min, Flat: {self.adaptive_flat_minutes}min, Gap Up: {self.adaptive_gap_up_minutes}min)")
            else:
                logger.info(f"   Layer 1: Block first {self.block_minutes} min (US Eastern Time)")
            logger.info(f"   Layer 2: Max VWAP distance {self.vwap_max_distance}%")
            logger.info(f"   Layer 3: Max chase {self.max_chase}%")
            logger.info(f"   Layer 4: Block if in top {100-self.intraday_max_range_pct:.0f}% of range or >{self.intraday_max_move_from_low}% from low")

    def check_entry(
        self,
        symbol: str,
        signal_price: float,
        current_price: float,
        market_data: Optional[Dict] = None,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Check if entry should be allowed through all 3 layers

        Args:
            symbol: Stock symbol
            signal_price: Original signal price
            current_price: Current market price
            market_data: Dict with OHLCV data and VWAP
            current_time: Current time (default: now)

        Returns:
            (allowed, reason, limit_price)
            - allowed: True if passed all layers
            - reason: Explanation
            - limit_price: Recommended limit price (None if blocked)
        """
        if not self.enabled:
            return True, "Entry protection disabled", current_price

        if self.track_rejections:
            self.stats.total_signals += 1

        # v6.21: Use Eastern time directly to avoid timezone conversion issues
        if current_time is None:
            import pytz
            eastern = pytz.timezone('US/Eastern')
            current_time = datetime.now(eastern)

        # Extract gap % for adaptive timing (v6.23)
        gap_pct = None
        if market_data:
            gap_pct = market_data.get('gap_pct')

        # ========== Layer 1: Time Filter (Adaptive) ==========
        allowed, reason = self._check_time_filter(
            symbol, signal_price, current_price, current_time, gap_pct
        )

        if not allowed:
            if self.track_rejections:
                self.stats.layer1_blocks += 1
            return False, f"🕒 Layer 1 BLOCK: {reason}", None

        # Check discount exception
        if "discount" in reason.lower() and self.track_rejections:
            self.stats.discount_exceptions += 1

        # ========== Layer 2: VWAP Filter ==========
        if market_data:
            allowed, reason = self._check_vwap_filter(
                symbol, current_price, market_data
            )

            if not allowed:
                if self.track_rejections:
                    self.stats.layer2_blocks += 1
                return False, f"📊 Layer 2 BLOCK: {reason}", None

        # ========== Layer 4: Intraday Position Filter (v6.22) ==========
        if market_data:
            allowed, reason = self._check_intraday_position_filter(
                symbol, current_price, market_data, current_time
            )

            if not allowed:
                if self.track_rejections:
                    self.stats.layer4_blocks += 1
                return False, f"📍 Layer 4 BLOCK: {reason}", None

        # ========== Layer 3: Limit Order ==========
        limit_price = self._calculate_limit_price(signal_price, current_price)

        if current_price > limit_price:
            if self.track_rejections:
                self.stats.layer3_blocks += 1
            chase_pct = ((current_price - signal_price) / signal_price) * 100
            return False, f"💸 Layer 3 BLOCK: Chasing {chase_pct:.2f}% (max {self.max_chase}%)", None

        # ========== All Layers Passed ==========
        if self.track_rejections:
            self.stats.passed += 1

        return True, f"✅ Passed all 4 layers (limit ${limit_price:.2f})", limit_price

    def _check_time_filter(
        self,
        symbol: str,
        signal_price: float,
        current_price: float,
        current_time: datetime,
        gap_pct: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Layer 1: Check if within opening volatility window (v6.23: Adaptive timing)

        Args:
            gap_pct: Opening gap % (for adaptive timing)

        Returns:
            (allowed, reason)
        """
        # FIX: Convert to US Eastern Time (market timezone)
        eastern = pytz.timezone('US/Eastern')

        # If current_time is naive (no timezone), assume it's already in Eastern
        if current_time.tzinfo is None:
            current_time_et = eastern.localize(current_time)
        else:
            # Convert from whatever timezone to Eastern
            current_time_et = current_time.astimezone(eastern)

        # Calculate minutes since market open (in Eastern Time)
        market_open = current_time_et.replace(
            hour=self.market_open_hour,
            minute=self.market_open_minute,
            second=0,
            microsecond=0
        )

        minutes_since_open = (current_time_et - market_open).total_seconds() / 60

        # v6.23: Adaptive timing based on gap %
        if self.adaptive_timing_enabled and gap_pct is not None:
            # Determine block time based on gap category
            if gap_pct < -1.5:
                # Strong Gap Down: Bottom fishing, buy early
                block_time = self.adaptive_gap_down_strong_minutes
                gap_category = f"Gap Down {gap_pct:.1f}%"
            elif gap_pct < -0.5:
                # Mild Gap Down: Wait a bit
                block_time = self.adaptive_gap_down_mild_minutes
                gap_category = f"Mild Gap Down {gap_pct:.1f}%"
            elif gap_pct <= 0.5:
                # Flat: Standard protection
                block_time = self.adaptive_flat_minutes
                gap_category = f"Flat {gap_pct:.1f}%"
            else:
                # Gap Up: Wait for pullback
                block_time = self.adaptive_gap_up_minutes
                gap_category = f"Gap Up {gap_pct:.1f}%"

            # Check if past adaptive block time
            if minutes_since_open >= block_time:
                return True, f"Time OK ({minutes_since_open:.0f}min, {gap_category}, block={block_time}min)"
            else:
                # Check discount exception
                if self.allow_discount:
                    price_change_pct = ((current_price - signal_price) / signal_price) * 100
                    if price_change_pct <= self.discount_threshold:
                        return True, f"Discount exception: {price_change_pct:.2f}% < {self.discount_threshold}%"

                return False, f"Only {minutes_since_open:.0f}min after open ({gap_category}, need {block_time}min)"
        else:
            # Standard fixed block time (fallback if no gap data or adaptive disabled)
            if minutes_since_open >= self.block_minutes:
                return True, f"Time OK ({minutes_since_open:.0f} min after open ET)"

            # Within block window - check discount exception
            if self.allow_discount:
                price_change_pct = ((current_price - signal_price) / signal_price) * 100
                if price_change_pct <= self.discount_threshold:
                    return True, f"Discount exception: {price_change_pct:.2f}% < {self.discount_threshold}%"

            # Block by default
            return False, f"Only {minutes_since_open:.0f} min after open ET (need {self.block_minutes} min)"

    def _check_vwap_filter(
        self,
        symbol: str,
        current_price: float,
        market_data: Dict
    ) -> Tuple[bool, str]:
        """
        Layer 2: Check if price extended from VWAP

        Returns:
            (allowed, reason)
        """
        vwap = market_data.get('vwap')

        if vwap is None or vwap <= 0:
            # No VWAP data - allow (can't check)
            return True, "No VWAP data - skip filter"

        # Always allow if below VWAP
        if self.vwap_allow_below and current_price <= vwap:
            distance_pct = ((current_price - vwap) / vwap) * 100
            return True, f"Below VWAP ({distance_pct:+.2f}%)"

        # Check distance from VWAP
        distance_pct = ((current_price - vwap) / vwap) * 100

        if distance_pct > self.vwap_max_distance:
            return False, f"Extended {distance_pct:.2f}% from VWAP (max {self.vwap_max_distance}%)"

        return True, f"Near VWAP ({distance_pct:+.2f}%)"

    def _check_intraday_position_filter(
        self,
        symbol: str,
        current_price: float,
        market_data: Dict,
        current_time: datetime
    ) -> Tuple[bool, str]:
        """
        Layer 4: Check intraday position to prevent buying near day's high (v6.22)

        Blocks entry if:
        1. Price is in top X% of day's range (near high)
        2. Stock moved too much from day's low
        3. After 2 hours + price near high (stricter)

        Returns:
            (allowed, reason)
        """
        # Get OHLC data
        day_high = market_data.get('high')
        day_low = market_data.get('low')
        day_open = market_data.get('open')

        # Skip if no data
        if not all([day_high, day_low, day_open]) or day_high <= 0 or day_low <= 0:
            return True, "No OHLC data - skip filter"

        # Skip if invalid range (high = low)
        day_range = day_high - day_low
        if day_range <= 0.01:  # Less than 1 cent range
            return True, "Insufficient price range"

        # ========== Check 1: Position in day's range ==========
        # Calculate where current price is in the range (0-100%)
        position_in_range = (current_price - day_low) / day_range * 100

        if position_in_range > self.intraday_max_range_pct:
            return False, f"Price at {position_in_range:.1f}% of range (near high ${day_high:.2f}, buying too late)"

        # ========== Check 2: Movement from day's low ==========
        move_from_low_pct = (current_price - day_low) / day_low * 100

        if move_from_low_pct > self.intraday_max_move_from_low:
            return False, f"Moved {move_from_low_pct:.1f}% from low ${day_low:.2f} (max {self.intraday_max_move_from_low}%)"

        # ========== Check 3: Time + Position combination (stricter after 2hr) ==========
        # Calculate minutes since open
        eastern = pytz.timezone('US/Eastern')
        if current_time.tzinfo is None:
            current_time_et = eastern.localize(current_time)
        else:
            current_time_et = current_time.astimezone(eastern)

        market_open = current_time_et.replace(
            hour=self.market_open_hour,
            minute=self.market_open_minute,
            second=0,
            microsecond=0
        )
        minutes_since_open = (current_time_et - market_open).total_seconds() / 60

        # After 2 hours, be stricter (block if in top 30% instead of top 20%)
        if minutes_since_open > self.intraday_strict_after_minutes:
            strict_threshold = 70.0  # Block if above 70% (in top 30%)
            if position_in_range > strict_threshold:
                return False, f"After {minutes_since_open:.0f}min + price at {position_in_range:.1f}% of range (too late)"

        # All checks passed
        return True, f"Position OK: {position_in_range:.1f}% of range, +{move_from_low_pct:.1f}% from low"

    def _calculate_limit_price(
        self,
        signal_price: float,
        current_price: float
    ) -> float:
        """
        Layer 3: Calculate limit order price

        Args:
            signal_price: Original signal price
            current_price: Current market price

        Returns:
            Limit price (signal + max_chase)
        """
        # Limit = signal price + max chase %
        limit_price = signal_price * (1 + self.max_chase / 100)

        return round(limit_price, 2)

    def get_stats(self) -> Dict:
        """Get rejection statistics"""
        if not self.track_rejections:
            return {}

        total = self.stats.total_signals
        if total == 0:
            return {
                'total_signals': 0,
                'passed': 0,
                'pass_rate': 0.0
            }

        return {
            'total_signals': total,
            'layer1_blocks': self.stats.layer1_blocks,
            'layer2_blocks': self.stats.layer2_blocks,
            'layer3_blocks': self.stats.layer3_blocks,
            'layer4_blocks': self.stats.layer4_blocks,
            'discount_exceptions': self.stats.discount_exceptions,
            'passed': self.stats.passed,
            'pass_rate': (self.stats.passed / total) * 100,
            'rejection_rate': ((total - self.stats.passed) / total) * 100
        }

    def reset_stats(self):
        """Reset statistics"""
        self.stats = EntryProtectionStats()

    def log_stats(self):
        """Log current statistics"""
        stats = self.get_stats()

        if stats.get('total_signals', 0) == 0:
            logger.info("🛡️ Entry Protection: No signals processed yet")
            return

        logger.info("🛡️ Entry Protection Statistics:")
        logger.info(f"   Total Signals: {stats['total_signals']}")
        logger.info(f"   ✅ Passed: {stats['passed']} ({stats['pass_rate']:.1f}%)")
        logger.info(f"   ❌ Layer 1 Blocks: {stats['layer1_blocks']} (time)")
        logger.info(f"   ❌ Layer 2 Blocks: {stats['layer2_blocks']} (VWAP)")
        logger.info(f"   ❌ Layer 3 Blocks: {stats['layer3_blocks']} (chase)")
        logger.info(f"   💰 Discount Exceptions: {stats['discount_exceptions']}")
