#!/usr/bin/env python3
"""
Exit Rules Engine - Rule-Based System for Stock Exits
=====================================================

แนวคิด: แทนที่จะเขียน if-else ยาวๆ ให้แปลงเป็น declarative rules
ที่สามารถ configure, tune, และ optimize ได้ง่าย

Benefits:
- ✅ ปรับ threshold ง่าย (แก้ที่เดียว)
- ✅ Test แต่ละ rule ได้
- ✅ Log rule performance
- ✅ A/B test rules
- ✅ ML-based optimization
- ✅ Explainable decisions
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from enum import Enum
import numpy as np
from loguru import logger


class RulePriority(Enum):
    """Priority levels for exit rules"""
    CRITICAL = 1    # Must exit (hard stop, target hit)
    HIGH = 2        # Strong signal (gap down, breaking down)
    MEDIUM = 3      # Medium signal (volume collapse, SMA20 break)
    LOW = 4         # Weak signal (RSI weak, momentum reversal)


class RuleCategory(Enum):
    """Categories of exit rules"""
    PROFIT_TAKING = "profit"
    STOP_LOSS = "stop"
    TECHNICAL = "technical"
    VOLUME = "volume"
    MOMENTUM = "momentum"
    REGIME = "regime"


@dataclass
class RuleConfig:
    """Configuration for a single exit rule"""
    name: str
    category: RuleCategory
    priority: RulePriority
    enabled: bool = True

    # Thresholds (can be tuned)
    thresholds: Dict[str, float] = None

    # Conditions (can be customized)
    conditions: Dict[str, any] = None

    # Performance tracking
    fired_count: int = 0
    win_count: int = 0
    total_pnl: float = 0.0

    def __post_init__(self):
        if self.thresholds is None:
            self.thresholds = {}
        if self.conditions is None:
            self.conditions = {}


@dataclass
class MarketData:
    """Market data for rule evaluation"""
    current_price: float
    entry_price: float
    highest_price: float
    close_prices: List[float]
    open_prices: List[float]
    volume_data: List[float]
    days_held: int

    # Calculated fields
    @property
    def pnl_pct(self) -> float:
        return ((self.current_price - self.entry_price) / self.entry_price) * 100

    @property
    def peak_gain_pct(self) -> float:
        return ((self.highest_price - self.entry_price) / self.entry_price) * 100

    @property
    def drawdown_pct(self) -> float:
        if self.highest_price <= self.entry_price:
            return 0.0
        return ((self.current_price - self.highest_price) / self.highest_price) * 100


class ExitRulesEngine:
    """
    Rule-Based Exit System

    Design Pattern: Strategy + Chain of Responsibility
    - Each rule is a strategy
    - Rules are evaluated in priority order
    - First rule that fires wins
    """

    def __init__(self):
        self.rules: List[RuleConfig] = []
        self._initialize_v5_rules()

    def _initialize_v5_rules(self):
        """Initialize v5 SMART SELECTIVE EXITS as rules"""

        # =====================================================
        # PRIORITY 1: CRITICAL (MUST EXIT)
        # =====================================================

        self.add_rule(RuleConfig(
            name="TARGET_HIT",
            category=RuleCategory.PROFIT_TAKING,
            priority=RulePriority.CRITICAL,
            thresholds={
                'target_pct': 4.0,  # v5: 4.0% target
            },
            conditions={
                'min_days': 0,      # Can exit any day
            }
        ))

        self.add_rule(RuleConfig(
            name="HARD_STOP",
            category=RuleCategory.STOP_LOSS,
            priority=RulePriority.CRITICAL,
            thresholds={
                'stop_pct': -3.5,   # v5: -3.5% stop
            },
            conditions={
                'min_days': 0,
            }
        ))

        self.add_rule(RuleConfig(
            name="TRAILING_STOP",
            category=RuleCategory.STOP_LOSS,
            priority=RulePriority.CRITICAL,
            thresholds={
                'drawdown_pct': -3.5,  # v5: -3.5% trailing
            },
            conditions={
                'min_days': 0,          # Immediate
                'must_be_in_profit': True,  # Only after peak
            }
        ))

        # =====================================================
        # PRIORITY 2: HIGH (STRONG SIGNALS)
        # =====================================================

        self.add_rule(RuleConfig(
            name="SMART_GAP_DOWN",
            category=RuleCategory.TECHNICAL,
            priority=RulePriority.HIGH,
            thresholds={
                'gap_pct': -1.5,        # Gap down > 1.5%
                'overall_loss': -1.0,   # Overall losing > 1.0%
            },
            conditions={
                'min_days': 1,
            }
        ))

        self.add_rule(RuleConfig(
            name="SMART_BREAKING_DOWN",
            category=RuleCategory.TECHNICAL,
            priority=RulePriority.HIGH,
            thresholds={
                'daily_drop': -2.0,     # Daily drop > 2.0%
                'overall_loss': -0.5,   # Overall losing > 0.5%
            },
            conditions={
                'min_days': 2,
            }
        ))

        # =====================================================
        # PRIORITY 3: MEDIUM (MEDIUM SIGNALS)
        # =====================================================

        self.add_rule(RuleConfig(
            name="SMART_VOLUME_COLLAPSE",
            category=RuleCategory.VOLUME,
            priority=RulePriority.MEDIUM,
            thresholds={
                'volume_ratio': 0.5,    # Volume < 50% of avg
                'overall_loss': -1.0,   # Overall losing > 1.0%
            },
            conditions={
                'min_days': 2,
                'lookback_days': 10,    # 10-day avg
            }
        ))

        self.add_rule(RuleConfig(
            name="SMART_FAILED_PUMP",
            category=RuleCategory.MOMENTUM,
            priority=RulePriority.MEDIUM,
            thresholds={
                'peak_gain': 3.0,       # Must have peaked > 3%
                'below_entry': True,    # Now below entry
            },
            conditions={
                'min_days': 2,
            }
        ))

        self.add_rule(RuleConfig(
            name="SMART_SMA20_BREAK",
            category=RuleCategory.TECHNICAL,
            priority=RulePriority.MEDIUM,
            thresholds={
                'distance_pct': -1.0,   # > 1% below SMA20
            },
            conditions={
                'min_days': 2,
                'must_be_losing': True,
                'min_data_points': 20,
            }
        ))

        # =====================================================
        # PRIORITY 4: LOW (WEAK SIGNALS)
        # =====================================================

        self.add_rule(RuleConfig(
            name="SMART_WEAK_RSI",
            category=RuleCategory.MOMENTUM,
            priority=RulePriority.LOW,
            thresholds={
                'rsi_threshold': 35,    # RSI < 35
                'overall_loss': -2.0,   # Losing > 2.0%
            },
            conditions={
                'min_days': 2,
                'min_data_points': 15,
            }
        ))

        self.add_rule(RuleConfig(
            name="SMART_MOMENTUM_REVERSAL",
            category=RuleCategory.MOMENTUM,
            priority=RulePriority.LOW,
            thresholds={
                'day1_gain': 1.0,       # Day 1 up > 1%
                'day2_loss': -1.5,      # Day 2 down > 1.5%
                'overall_max': 1.0,     # Overall < 1%
            },
            conditions={
                'min_days': 2,
            }
        ))

        self.add_rule(RuleConfig(
            name="MAX_HOLD",
            category=RuleCategory.STOP_LOSS,
            priority=RulePriority.LOW,
            thresholds={
                'max_days': 30,
            },
            conditions={}
        ))

    def add_rule(self, rule: RuleConfig):
        """Add a rule to the engine"""
        self.rules.append(rule)

        # Sort by priority (CRITICAL first)
        self.rules.sort(key=lambda r: r.priority.value)

    def remove_rule(self, rule_name: str):
        """Remove a rule by name"""
        self.rules = [r for r in self.rules if r.name != rule_name]

    def enable_rule(self, rule_name: str):
        """Enable a rule"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"✅ Enabled rule: {rule_name}")

    def disable_rule(self, rule_name: str):
        """Disable a rule"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"❌ Disabled rule: {rule_name}")

    def update_threshold(self, rule_name: str, threshold_name: str, value: float):
        """Update a rule's threshold"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.thresholds[threshold_name] = value
                logger.info(f"🔧 Updated {rule_name}.{threshold_name} = {value}")

    def evaluate(self, data: MarketData, symbol: str = "") -> Optional[str]:
        """
        Evaluate all rules and return first matching exit reason

        Returns:
            exit_reason: str or None
        """

        for rule in self.rules:
            if not rule.enabled:
                continue

            # Evaluate rule
            should_exit, details = self._evaluate_rule(rule, data)

            if should_exit:
                # Log the exit
                logger.info(f"{symbol}: {rule.name} fired - {details}")

                # Track performance
                rule.fired_count += 1

                return rule.name

        return None

    def _evaluate_rule(self, rule: RuleConfig, data: MarketData) -> tuple[bool, str]:
        """
        Evaluate a single rule

        Returns:
            (should_exit: bool, details: str)
        """

        # Check minimum days condition
        min_days = rule.conditions.get('min_days', 0)
        if data.days_held < min_days:
            return False, ""

        # =====================================================
        # CRITICAL RULES
        # =====================================================

        if rule.name == "TARGET_HIT":
            target = rule.thresholds['target_pct']
            if data.pnl_pct >= target:
                return True, f"Hit target {data.pnl_pct:.1f}% >= {target}%"

        elif rule.name == "HARD_STOP":
            stop = rule.thresholds['stop_pct']
            if data.pnl_pct <= stop:
                return True, f"Hit stop {data.pnl_pct:.1f}% <= {stop}%"

        elif rule.name == "TRAILING_STOP":
            if rule.conditions.get('must_be_in_profit', True):
                if data.highest_price <= data.entry_price:
                    return False, ""

            threshold = rule.thresholds['drawdown_pct']
            if data.drawdown_pct < threshold:
                return True, f"Trailing stop {data.drawdown_pct:.1f}% < {threshold}%"

        # =====================================================
        # HIGH PRIORITY RULES
        # =====================================================

        elif rule.name == "SMART_GAP_DOWN":
            if len(data.open_prices) < 1 or len(data.close_prices) < 2:
                return False, ""

            today_open = data.open_prices[-1]
            yesterday_close = data.close_prices[-2]
            gap_pct = ((today_open - yesterday_close) / yesterday_close) * 100

            gap_threshold = rule.thresholds['gap_pct']
            loss_threshold = rule.thresholds['overall_loss']

            if gap_pct < gap_threshold and data.pnl_pct < loss_threshold:
                return True, f"Gap down {gap_pct:.1f}%, overall {data.pnl_pct:.1f}%"

        elif rule.name == "SMART_BREAKING_DOWN":
            if len(data.close_prices) < 2:
                return False, ""

            prev_close = data.close_prices[-2]
            daily_change = ((data.current_price - prev_close) / prev_close) * 100

            drop_threshold = rule.thresholds['daily_drop']
            loss_threshold = rule.thresholds['overall_loss']

            if daily_change < drop_threshold and data.pnl_pct < loss_threshold:
                return True, f"Breaking down {daily_change:.1f}%, overall {data.pnl_pct:.1f}%"

        # =====================================================
        # MEDIUM PRIORITY RULES
        # =====================================================

        elif rule.name == "SMART_VOLUME_COLLAPSE":
            lookback = rule.conditions.get('lookback_days', 10)
            if len(data.volume_data) < lookback:
                return False, ""

            avg_volume = np.mean(data.volume_data[-lookback:])
            current_volume = data.volume_data[-1]

            if avg_volume == 0:
                return False, ""

            volume_ratio = current_volume / avg_volume
            ratio_threshold = rule.thresholds['volume_ratio']
            loss_threshold = rule.thresholds['overall_loss']

            if volume_ratio < ratio_threshold and data.pnl_pct < loss_threshold:
                return True, f"Volume collapsed to {volume_ratio*100:.0f}% of avg"

        elif rule.name == "SMART_FAILED_PUMP":
            peak_threshold = rule.thresholds['peak_gain']

            if data.peak_gain_pct >= peak_threshold and data.current_price < data.entry_price:
                return True, f"Failed pump - peaked {data.peak_gain_pct:.1f}%, now below entry"

        elif rule.name == "SMART_SMA20_BREAK":
            if rule.conditions.get('must_be_losing', False) and data.pnl_pct >= 0:
                return False, ""

            min_points = rule.conditions.get('min_data_points', 20)
            if len(data.close_prices) < min_points:
                return False, ""

            sma20 = np.mean(data.close_prices[-20:])
            distance_pct = ((data.current_price - sma20) / sma20) * 100
            threshold = rule.thresholds['distance_pct']

            if distance_pct < threshold:
                return True, f"SMA20 break - {distance_pct:.1f}% below"

        # =====================================================
        # LOW PRIORITY RULES
        # =====================================================

        elif rule.name == "SMART_WEAK_RSI":
            min_points = rule.conditions.get('min_data_points', 15)
            if len(data.close_prices) < min_points:
                return False, ""

            loss_threshold = rule.thresholds['overall_loss']
            if data.pnl_pct >= loss_threshold:
                return False, ""

            # Calculate RSI
            rsi = self._calculate_rsi(data.close_prices, period=14)
            if rsi is None:
                return False, ""

            rsi_threshold = rule.thresholds['rsi_threshold']
            if rsi < rsi_threshold:
                return True, f"Weak RSI {rsi:.1f} when losing {data.pnl_pct:.1f}%"

        elif rule.name == "SMART_MOMENTUM_REVERSAL":
            if len(data.close_prices) < 3:
                return False, ""

            recent = data.close_prices[-3:]
            day1_gain = ((recent[1] - recent[0]) / recent[0]) * 100
            day2_loss = ((recent[2] - recent[1]) / recent[1]) * 100

            gain_threshold = rule.thresholds['day1_gain']
            loss_threshold = rule.thresholds['day2_loss']
            overall_max = rule.thresholds['overall_max']

            if day1_gain > gain_threshold and day2_loss < loss_threshold and data.pnl_pct < overall_max:
                return True, f"Reversal - up {day1_gain:.1f}%, down {day2_loss:.1f}%"

        elif rule.name == "MAX_HOLD":
            max_days = rule.thresholds['max_days']
            if data.days_held >= max_days:
                return True, f"Max hold {data.days_held} days"

        return False, ""

    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        if len(prices) < period + 1:
            return None

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def get_rule_stats(self) -> List[Dict]:
        """Get performance statistics for all rules"""
        stats = []

        for rule in self.rules:
            avg_pnl = rule.total_pnl / rule.fired_count if rule.fired_count > 0 else 0
            win_rate = rule.win_count / rule.fired_count * 100 if rule.fired_count > 0 else 0

            stats.append({
                'name': rule.name,
                'category': rule.category.value,
                'priority': rule.priority.name,
                'enabled': rule.enabled,
                'fired_count': rule.fired_count,
                'win_count': rule.win_count,
                'win_rate': win_rate,
                'avg_pnl': avg_pnl,
                'thresholds': rule.thresholds,
            })

        return stats

    def export_config(self) -> Dict:
        """Export current configuration"""
        return {
            'rules': [
                {
                    'name': r.name,
                    'category': r.category.value,
                    'priority': r.priority.value,
                    'enabled': r.enabled,
                    'thresholds': r.thresholds,
                    'conditions': r.conditions,
                }
                for r in self.rules
            ]
        }

    def import_config(self, config: Dict):
        """Import configuration (for A/B testing different configs)"""
        self.rules = []

        for rule_data in config['rules']:
            rule = RuleConfig(
                name=rule_data['name'],
                category=RuleCategory(rule_data['category']),
                priority=RulePriority(rule_data['priority']),
                enabled=rule_data['enabled'],
                thresholds=rule_data['thresholds'],
                conditions=rule_data['conditions'],
            )
            self.add_rule(rule)


# =====================================================
# USAGE EXAMPLES
# =====================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Exit Rules Engine - Demo")
    print("=" * 60)
    print()

    # 1. Initialize engine
    engine = ExitRulesEngine()

    print(f"✅ Initialized with {len(engine.rules)} rules")
    print()

    # 2. Show all rules
    print("📋 Rules (by priority):")
    print("-" * 60)
    for rule in engine.rules:
        status = "✅" if rule.enabled else "❌"
        print(f"{status} {rule.priority.name:8} | {rule.category.value:10} | {rule.name}")
    print()

    # 3. Test rule evaluation
    print("🧪 Testing rule evaluation:")
    print("-" * 60)

    # Example 1: Target hit
    data = MarketData(
        current_price=104.5,
        entry_price=100.0,
        highest_price=104.5,
        close_prices=[100, 101, 102, 103, 104.5],
        open_prices=[100, 101, 102, 103, 104],
        volume_data=[1000] * 5,
        days_held=4
    )

    exit_reason = engine.evaluate(data, "NVDA")
    print(f"Example 1: Price at +4.5% → {exit_reason}")

    # Example 2: Gap down
    data2 = MarketData(
        current_price=97.0,
        entry_price=100.0,
        highest_price=101.0,
        close_prices=[100, 101, 99.5, 97.0],
        open_prices=[100, 100.5, 97.0],  # Gap down at open!
        volume_data=[1000] * 4,
        days_held=3
    )

    exit_reason2 = engine.evaluate(data2, "AMD")
    print(f"Example 2: Gap down to -3% → {exit_reason2}")

    print()

    # 4. Tune a rule
    print("🔧 Tuning rules:")
    print("-" * 60)
    print("Original: TARGET_HIT at 4.0%")
    engine.update_threshold("TARGET_HIT", "target_pct", 3.5)
    print("Updated:  TARGET_HIT at 3.5%")
    print()

    # 5. Disable a rule
    print("❌ Disabling SMART_MOMENTUM_REVERSAL")
    engine.disable_rule("SMART_MOMENTUM_REVERSAL")
    print()

    # 6. Export config
    print("💾 Exporting configuration...")
    config = engine.export_config()
    print(f"   Exported {len(config['rules'])} rules")
    print()

    print("=" * 60)
    print("✅ Demo complete! Rule-based system is ready.")
    print("=" * 60)
