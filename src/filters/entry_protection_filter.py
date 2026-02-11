"""
3-Layer Entry Protection Filter (v6.17)

Prevents buying at daily highs during opening volatility spike.

Layers:
1. Time Filter: Block first 15 min after market open
2. VWAP Filter: Block if extended > 1.5% from VWAP
3. Limit Order: Max 0.2% chase from signal price

Author: Claude Sonnet 4.5
Date: 2026-02-11
"""

from typing import Dict, Tuple, Optional
from datetime import datetime, time
from dataclasses import dataclass
from loguru import logger
import pandas as pd


@dataclass
class EntryProtectionStats:
    """Track rejection statistics"""
    total_signals: int = 0
    layer1_blocks: int = 0  # Time filter
    layer2_blocks: int = 0  # VWAP filter
    layer3_blocks: int = 0  # Limit order timeout
    passed: int = 0
    discount_exceptions: int = 0  # Allowed despite being early


class EntryProtectionFilter:
    """
    3-Layer Entry Protection System

    Prevents buying at opening spike highs by using layered filters:
    - Layer 1: Time-based (opening volatility window)
    - Layer 2: Price-based (VWAP distance)
    - Layer 3: Execution-based (limit orders only)
    """

    def __init__(self, config):
        """
        Initialize Entry Protection Filter

        Args:
            config: RapidRotationConfig or dict with settings
        """
        self.enabled = getattr(config, 'entry_protection_enabled', True)

        # Layer 1: Time Filter
        self.block_minutes = getattr(config, 'entry_block_minutes_after_open', 15)
        self.allow_discount = getattr(config, 'entry_allow_discount_exception', True)
        self.discount_threshold = getattr(config, 'entry_discount_exception_pct', -0.5)

        # Layer 2: VWAP Filter
        self.vwap_max_distance = getattr(config, 'entry_vwap_max_distance_pct', 1.5)
        self.vwap_allow_below = getattr(config, 'entry_vwap_allow_below', True)

        # Layer 3: Limit Order
        self.limit_only = getattr(config, 'entry_limit_order_only', True)
        self.max_chase = getattr(config, 'entry_max_chase_pct', 0.2)
        self.limit_timeout = getattr(config, 'entry_limit_timeout_minutes', 5)

        # Market hours
        self.market_open_hour = getattr(config, 'market_open_hour', 9)
        self.market_open_minute = getattr(config, 'market_open_minute', 30)

        # Statistics
        self.track_rejections = getattr(config, 'entry_track_rejections', True)
        self.stats = EntryProtectionStats()

        logger.info(f"🛡️ Entry Protection Filter initialized (enabled={self.enabled})")
        if self.enabled:
            logger.info(f"   Layer 1: Block first {self.block_minutes} min")
            logger.info(f"   Layer 2: Max VWAP distance {self.vwap_max_distance}%")
            logger.info(f"   Layer 3: Max chase {self.max_chase}%")

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

        current_time = current_time or datetime.now()

        # ========== Layer 1: Time Filter ==========
        allowed, reason = self._check_time_filter(
            symbol, signal_price, current_price, current_time
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

        return True, f"✅ Passed all 3 layers (limit ${limit_price:.2f})", limit_price

    def _check_time_filter(
        self,
        symbol: str,
        signal_price: float,
        current_price: float,
        current_time: datetime
    ) -> Tuple[bool, str]:
        """
        Layer 1: Check if within opening volatility window

        Returns:
            (allowed, reason)
        """
        # Calculate minutes since market open
        market_open = current_time.replace(
            hour=self.market_open_hour,
            minute=self.market_open_minute,
            second=0,
            microsecond=0
        )

        minutes_since_open = (current_time - market_open).total_seconds() / 60

        # After block window - always allow
        if minutes_since_open >= self.block_minutes:
            return True, f"Time OK ({minutes_since_open:.0f} min after open)"

        # Within block window - check exceptions
        if self.allow_discount:
            price_change_pct = ((current_price - signal_price) / signal_price) * 100

            # Allow if price dropped (discount from signal)
            if price_change_pct <= self.discount_threshold:
                return True, f"Discount exception: {price_change_pct:.2f}% < {self.discount_threshold}%"

        # Block by default
        return False, f"Only {minutes_since_open:.0f} min after open (need {self.block_minutes} min)"

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
