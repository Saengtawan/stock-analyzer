#!/usr/bin/env python3
"""
Rule-Based Screening Engine for Growth Catalyst
Similar to exit_rules_engine.py but for entry screening

Benefits:
- ✅ Easy to tune thresholds
- ✅ A/B test different configs
- ✅ Track rule performance
- ✅ Add/remove rules without code changes
- ✅ Export/import configurations
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import json
from loguru import logger


class RulePriority(Enum):
    """Rule priority levels - higher priority rules evaluated first"""
    CRITICAL = 1   # Must-pass rules (price, volume, market cap)
    HIGH = 2       # Strong filters (technical, momentum)
    MEDIUM = 3     # Quality filters (fundamentals)
    LOW = 4        # Nice-to-have (catalyst, AI probability)


@dataclass
class ScreeningMarketData:
    """Market data for screening evaluation"""
    # Basic info
    symbol: str
    current_price: float
    market_cap: float
    avg_volume: float
    sector: str = "Unknown"

    # Price data
    close_prices: List[float] = field(default_factory=list)
    volume_data: List[float] = field(default_factory=list)

    # Technical indicators
    ma20: float = 0.0
    ma50: float = 0.0
    rsi: float = 50.0
    support: float = 0.0
    resistance: float = 0.0

    # Alternative data
    insider_buying: bool = False
    analyst_upgrades: int = 0
    short_interest: float = 0.0
    social_sentiment: float = 50.0

    # Sector/regime
    sector_regime: str = "SIDEWAYS"
    market_regime: str = "SIDEWAYS"


@dataclass
class ScreeningRuleConfig:
    """Configuration for a single screening rule"""
    name: str
    priority: RulePriority
    enabled: bool = True

    # Thresholds (configurable)
    thresholds: Dict[str, float] = field(default_factory=dict)

    # Conditions (boolean checks)
    conditions: Dict[str, Any] = field(default_factory=dict)

    # Scoring weights (for composite rules)
    weights: Dict[str, float] = field(default_factory=dict)

    # Performance tracking
    evaluated_count: int = 0
    passed_count: int = 0

    # Description
    description: str = ""


class ScreeningRulesEngine:
    """
    Rule-Based Screening Engine

    Architecture:
    - CRITICAL: Hard filters (must pass)
    - HIGH: Technical quality filters
    - MEDIUM: Fundamental quality filters
    - LOW: Enhancement filters (bonus points)
    """

    def __init__(self):
        self.rules: List[ScreeningRuleConfig] = []
        self._initialize_growth_catalyst_rules()
        logger.info("✅ Screening Rules Engine initialized with Growth Catalyst rules")

    def _initialize_growth_catalyst_rules(self):
        """Initialize Growth Catalyst screening rules (v3.3)"""

        # ========== CRITICAL RULES (Must Pass) ==========

        self.rules.append(ScreeningRuleConfig(
            name="PRICE_RANGE",
            priority=RulePriority.CRITICAL,
            thresholds={
                'min_price': 2.0,  # v5.0: Lowered for RECOVERY PLAY (stocks near 52w LOW often have lower prices)
                'max_price': 2000.0
            },
            description="Stock price must be within acceptable range"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="MARKET_CAP",
            priority=RulePriority.CRITICAL,
            thresholds={
                'min_market_cap': 200_000_000,  # $200M minimum
                'max_market_cap': 1_000_000_000_000  # $1T max (no real limit)
            },
            description="Market cap must be sufficient for liquidity"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="VOLUME",
            priority=RulePriority.CRITICAL,
            thresholds={
                'min_avg_volume': 10_000_000  # $10M daily
            },
            description="Daily volume must be sufficient for entry/exit"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="MARKET_REGIME",
            priority=RulePriority.CRITICAL,
            conditions={
                'allowed_regimes': ['BULL', 'STRONG BULL', 'SIDEWAYS'],
                'require_bull_sector': True  # v3.3: Allow if sector is BULL even if market is SIDEWAYS
            },
            description="Market/sector regime must support growth trades"
        ))

        # ========== HIGH PRIORITY RULES (Technical Quality) ==========

        self.rules.append(ScreeningRuleConfig(
            name="TREND_STRENGTH",
            priority=RulePriority.HIGH,
            thresholds={
                'min_score': 10.0,  # At least neutral bullish
                'max_score': 25.0
            },
            weights={
                'strong_bullish': 25.0,   # Price > MA20 > MA50
                'bullish': 15.0,          # Price > MA20
                'neutral_bullish': 10.0,  # Price > MA50
                'bearish': 0.0
            },
            description="Trend must be at least neutral bullish"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="MOMENTUM_RSI",
            priority=RulePriority.HIGH,
            thresholds={
                'sweet_spot_min': 45.0,
                'sweet_spot_max': 70.0,
                'oversold_min': 35.0,
                'oversold_max': 45.0,
                'overbought_min': 70.0,
                'overbought_max': 75.0
            },
            weights={
                'sweet_spot': 25.0,      # 45-70: Strong
                'moderate': 15.0,         # 40-45 or 70-75: Moderate
                'oversold_bounce': 10.0,  # 35-40: Oversold bounce potential
                'weak': 0.0
            },
            description="RSI momentum must be in acceptable range"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="VOLUME_CONFIRMATION",
            priority=RulePriority.HIGH,
            thresholds={
                'surge_ratio': 1.5,
                'increasing_ratio': 1.2,
                'normal_ratio': 0.8
            },
            weights={
                'surge': 20.0,         # 1.5x+ volume
                'increasing': 15.0,    # 1.2x+ volume
                'normal': 10.0,        # 0.8x+ volume
                'low': 0.0
            },
            description="Volume must confirm price movement"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="SHORT_TERM_MOMENTUM",
            priority=RulePriority.HIGH,
            thresholds={
                'accelerating_10d': 10.0,  # 10%+ in 10 days
                'accelerating_5d': 5.0,    # 5%+ in 5 days
                'strong_10d': 5.0,
                'building_5d': 3.0
            },
            weights={
                'accelerating': 15.0,  # Strong sustained momentum
                'strong': 10.0,        # Good momentum
                'building': 5.0,       # Recent pickup
                'weak': 0.0
            },
            description="Short-term momentum trend"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="PATTERN_RECOGNITION",
            priority=RulePriority.HIGH,
            thresholds={
                'near_breakout_dist': 5.0,      # Within 5% of high
                'consolidation_dist': 10.0,     # Within 10% of high
                'pullback_min': 15.0,           # 15-25% from high
                'pullback_max': 25.0
            },
            weights={
                'near_breakout': 15.0,
                'healthy_pullback': 14.0,  # Slightly lower than breakout
                'consolidation': 12.0,
                'ranging': 5.0
            },
            description="Chart pattern quality"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="RISK_REWARD_SETUP",
            priority=RulePriority.HIGH,
            thresholds={
                'excellent_rr': 3.0,
                'good_rr': 2.0,
                'acceptable_rr': 1.5
            },
            weights={
                'excellent': 10.0,
                'good': 8.0,
                'acceptable': 5.0,
                'poor': 0.0
            },
            description="Risk/reward based on support/resistance"
        ))

        # ========== MEDIUM PRIORITY RULES (Quality Filters) ==========

        self.rules.append(ScreeningRuleConfig(
            name="TIERED_QUALITY",
            priority=RulePriority.MEDIUM,
            thresholds={
                # Tiers based on price
                'high_price': 50.0,           # $50+
                'mid_high_price': 20.0,       # $20-50
                'mid_price': 10.0,            # $10-20
                'low_mid_price': 5.0,         # $5-10
                'low_price': 3.0              # $3-5
            },
            weights={
                # Dynamic thresholds per tier
                'HIGH_PRICE': {
                    'min_technical': 30.0,
                    'min_ai_prob': 30.0,
                    'require_insider': False
                },
                'MID_HIGH_PRICE': {
                    'min_technical': 40.0,
                    'min_ai_prob': 40.0,
                    'require_insider': False
                },
                'MID_PRICE': {
                    'min_technical': 50.0,
                    'min_ai_prob': 50.0,
                    'require_insider': False
                },
                'LOW_MID_PRICE': {
                    'min_technical': 60.0,
                    'min_ai_prob': 60.0,
                    'require_insider': True
                },
                'LOW_PRICE': {
                    'min_technical': 70.0,
                    'min_ai_prob': 70.0,
                    'require_insider': True
                }
            },
            description="Tiered quality requirements based on price (v3.2)"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="SECTOR_STRENGTH",
            priority=RulePriority.MEDIUM,
            weights={
                'STRONG BULL': 100.0,
                'BULL': 80.0,
                'SIDEWAYS': 50.0,
                'BEAR': 20.0,
                'STRONG BEAR': 0.0
            },
            description="Sector regime strength score"
        ))

        # ========== LOW PRIORITY RULES (Enhancement) ==========

        self.rules.append(ScreeningRuleConfig(
            name="ALTERNATIVE_DATA",
            priority=RulePriority.LOW,
            thresholds={
                'insider_buying_bonus': 15.0,
                'analyst_upgrade_bonus': 10.0,
                'short_squeeze_bonus': 15.0,
                'social_positive_bonus': 10.0
            },
            description="Alternative data signals (insider, analyst, social)"
        ))

        self.rules.append(ScreeningRuleConfig(
            name="PRICE_ADVANTAGE",
            priority=RulePriority.LOW,
            thresholds={
                'very_low_price': 30.0,  # <$30
                'low_price': 50.0,       # <$50
                'high_price': 300.0      # >$300
            },
            weights={
                'very_low_bonus': 1.10,   # 10% bonus
                'low_bonus': 1.05,        # 5% bonus
                'high_penalty': 0.95      # 5% penalty
            },
            description="Price-based score adjustment (low price = explosive potential)"
        ))

        logger.info(f"   Initialized {len(self.rules)} screening rules")
        for priority in RulePriority:
            count = len([r for r in self.rules if r.priority == priority])
            logger.info(f"   {priority.name}: {count} rules")

    def evaluate_stock(self, data: ScreeningMarketData) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate a stock against all screening rules

        Returns:
            (passed: bool, details: Dict)
        """
        passed = True
        failed_critical = []
        details = {
            'symbol': data.symbol,
            'scores': {},
            'failed_rules': [],
            'passed_rules': [],
            'tier': None,
            'technical_score': 0.0,
            'composite_score': 0.0
        }

        # Evaluate ALL rules first (don't break early)
        for rule in self.rules:
            if not rule.enabled:
                continue

            rule.evaluated_count += 1

            # Evaluate based on rule name
            rule_passed, rule_result = self._evaluate_rule(rule, data)

            if rule_passed:
                rule.passed_count += 1
                details['passed_rules'].append(rule.name)

                # Add score if applicable
                if 'score' in rule_result:
                    details['scores'][rule.name] = rule_result['score']

                # Add details
                if 'details' in rule_result:
                    details[rule.name] = rule_result['details']
            else:
                details['failed_rules'].append(rule.name)
                details[f'{rule.name}_reason'] = rule_result.get('reason', 'Unknown')

                # Track CRITICAL rule failures
                if rule.priority == RulePriority.CRITICAL:
                    failed_critical.append(rule.name)

        # Check if any CRITICAL rules failed
        if failed_critical:
            passed = False
            logger.debug(f"   ❌ {data.symbol} failed CRITICAL rules: {failed_critical}")

        # Always calculate scores (even if failed critical rules)
        details['technical_score'] = self._calculate_technical_score(details['scores'])
        details['composite_score'] = self._calculate_composite_score(data, details['scores'])

        return passed, details

    def _evaluate_rule(self, rule: ScreeningRuleConfig, data: ScreeningMarketData) -> Tuple[bool, Dict]:
        """Evaluate a specific rule"""

        if rule.name == "PRICE_RANGE":
            min_price = rule.thresholds['min_price']
            max_price = rule.thresholds['max_price']
            if min_price <= data.current_price <= max_price:
                return True, {'details': f'${data.current_price:.2f} within range'}
            return False, {'reason': f'Price ${data.current_price:.2f} outside ${min_price}-${max_price}'}

        elif rule.name == "MARKET_CAP":
            min_cap = rule.thresholds['min_market_cap']
            if data.market_cap >= min_cap:
                return True, {'details': f'${data.market_cap/1e9:.2f}B market cap'}
            return False, {'reason': f'Market cap too small: ${data.market_cap/1e6:.0f}M'}

        elif rule.name == "VOLUME":
            min_vol = rule.thresholds['min_avg_volume']
            if data.avg_volume >= min_vol:
                return True, {'details': f'${data.avg_volume/1e6:.1f}M avg volume'}
            return False, {'reason': f'Volume too low: ${data.avg_volume/1e6:.1f}M'}

        elif rule.name == "MARKET_REGIME":
            allowed = rule.conditions['allowed_regimes']
            require_bull_sector = rule.conditions.get('require_bull_sector', False)

            # v3.3: Check sector regime if market is SIDEWAYS
            if data.market_regime not in allowed:
                if require_bull_sector and data.sector_regime in ['BULL', 'STRONG BULL']:
                    return True, {'details': f'Market {data.market_regime} but sector {data.sector_regime}'}
                return False, {'reason': f'Market regime {data.market_regime} not suitable'}
            return True, {'details': f'Regime {data.market_regime} OK'}

        elif rule.name == "TREND_STRENGTH":
            # Calculate trend score
            if data.current_price > data.ma20 > data.ma50:
                score = rule.weights['strong_bullish']
                trend = 'strong_bullish'
            elif data.current_price > data.ma20:
                score = rule.weights['bullish']
                trend = 'bullish'
            elif data.current_price > data.ma50:
                score = rule.weights['neutral_bullish']
                trend = 'neutral_bullish'
            else:
                score = rule.weights['bearish']
                trend = 'bearish'

            if score >= rule.thresholds['min_score']:
                return True, {'score': score, 'details': trend}
            return False, {'reason': f'Trend too weak: {trend}'}

        elif rule.name == "MOMENTUM_RSI":
            rsi = data.rsi
            if rule.thresholds['sweet_spot_min'] <= rsi <= rule.thresholds['sweet_spot_max']:
                return True, {'score': rule.weights['sweet_spot'], 'details': f'RSI {rsi:.0f} (sweet spot)'}
            elif (rule.thresholds['oversold_min'] <= rsi < rule.thresholds['sweet_spot_min'] or
                  rule.thresholds['sweet_spot_max'] < rsi <= rule.thresholds['overbought_max']):
                return True, {'score': rule.weights['moderate'], 'details': f'RSI {rsi:.0f} (moderate)'}
            elif rule.thresholds['oversold_min'] <= rsi:
                return True, {'score': rule.weights['oversold_bounce'], 'details': f'RSI {rsi:.0f} (oversold bounce)'}
            return False, {'reason': f'RSI {rsi:.0f} too extreme'}

        elif rule.name == "VOLUME_CONFIRMATION":
            if len(data.volume_data) >= 20:
                avg_vol = sum(data.volume_data[-20:]) / 20
                recent_vol = sum(data.volume_data[-5:]) / 5
                ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

                if ratio >= rule.thresholds['surge_ratio']:
                    return True, {'score': rule.weights['surge'], 'details': f'{ratio:.1f}x volume surge'}
                elif ratio >= rule.thresholds['increasing_ratio']:
                    return True, {'score': rule.weights['increasing'], 'details': f'{ratio:.1f}x increasing'}
                elif ratio >= rule.thresholds['normal_ratio']:
                    return True, {'score': rule.weights['normal'], 'details': f'{ratio:.1f}x normal'}
                return False, {'reason': f'Volume too low: {ratio:.1f}x'}
            return True, {'score': 10.0, 'details': 'Insufficient data'}

        elif rule.name == "SHORT_TERM_MOMENTUM":
            if len(data.close_prices) >= 10:
                current = data.close_prices[-1]
                price_10d = data.close_prices[-10]
                price_5d = data.close_prices[-5]

                ret_10d = ((current - price_10d) / price_10d) * 100
                ret_5d = ((current - price_5d) / price_5d) * 100

                if ret_10d > rule.thresholds['accelerating_10d'] and ret_5d > rule.thresholds['accelerating_5d']:
                    return True, {'score': rule.weights['accelerating'], 'details': f'{ret_10d:.1f}% (10d) accelerating'}
                elif ret_10d > rule.thresholds['strong_10d']:
                    return True, {'score': rule.weights['strong'], 'details': f'{ret_10d:.1f}% (10d) strong'}
                elif ret_5d > rule.thresholds['building_5d']:
                    return True, {'score': rule.weights['building'], 'details': f'{ret_5d:.1f}% (5d) building'}
                return True, {'score': 0.0, 'details': 'weak momentum'}
            return True, {'score': 0.0, 'details': 'Insufficient data'}

        elif rule.name == "PATTERN_RECOGNITION":
            if len(data.close_prices) >= 30:
                high_30d = max(data.close_prices[-30:])
                dist = ((high_30d - data.current_price) / high_30d) * 100

                if dist < rule.thresholds['near_breakout_dist']:
                    return True, {'score': rule.weights['near_breakout'], 'details': f'{dist:.1f}% from high (breakout)'}
                elif dist < rule.thresholds['consolidation_dist']:
                    return True, {'score': rule.weights['consolidation'], 'details': f'{dist:.1f}% from high (consolidation)'}
                elif rule.thresholds['pullback_min'] < dist < rule.thresholds['pullback_max']:
                    return True, {'score': rule.weights['healthy_pullback'], 'details': f'{dist:.1f}% from high (pullback)'}
                return True, {'score': rule.weights['ranging'], 'details': f'{dist:.1f}% from high (ranging)'}
            return True, {'score': 5.0, 'details': 'Insufficient data'}

        elif rule.name == "RISK_REWARD_SETUP":
            if data.support > 0 and data.resistance > 0:
                potential_gain = data.resistance - data.current_price
                potential_loss = data.current_price - data.support

                if potential_loss > 0:
                    rr = potential_gain / potential_loss

                    if rr >= rule.thresholds['excellent_rr']:
                        return True, {'score': rule.weights['excellent'], 'details': f'R:R {rr:.1f}:1 (excellent)'}
                    elif rr >= rule.thresholds['good_rr']:
                        return True, {'score': rule.weights['good'], 'details': f'R:R {rr:.1f}:1 (good)'}
                    elif rr >= rule.thresholds['acceptable_rr']:
                        return True, {'score': rule.weights['acceptable'], 'details': f'R:R {rr:.1f}:1 (acceptable)'}
                    return False, {'reason': f'R:R {rr:.1f}:1 too poor'}
            return True, {'score': 5.0, 'details': 'No S/R data'}

        elif rule.name == "TIERED_QUALITY":
            # Determine tier
            price = data.current_price
            if price >= rule.thresholds['high_price']:
                tier = 'HIGH_PRICE'
            elif price >= rule.thresholds['mid_high_price']:
                tier = 'MID_HIGH_PRICE'
            elif price >= rule.thresholds['mid_price']:
                tier = 'MID_PRICE'
            elif price >= rule.thresholds['low_mid_price']:
                tier = 'LOW_MID_PRICE'
            else:
                tier = 'LOW_PRICE'

            return True, {'details': tier, 'tier_requirements': rule.weights[tier]}

        elif rule.name == "SECTOR_STRENGTH":
            sector_regime = data.sector_regime
            score = rule.weights.get(sector_regime, 50.0)
            return True, {'score': score, 'details': f'Sector {sector_regime}'}

        elif rule.name == "ALTERNATIVE_DATA":
            score = 50.0  # Base score
            bonuses = []

            if data.insider_buying:
                score += rule.thresholds['insider_buying_bonus']
                bonuses.append('insider')
            if data.analyst_upgrades > 0:
                score += rule.thresholds['analyst_upgrade_bonus']
                bonuses.append('analyst')
            if data.short_interest > 20.0:
                score += rule.thresholds['short_squeeze_bonus']
                bonuses.append('short_squeeze')
            if data.social_sentiment > 70.0:
                score += rule.thresholds['social_positive_bonus']
                bonuses.append('social')

            return True, {'score': min(100, score), 'details': f"{len(bonuses)} signals: {', '.join(bonuses) if bonuses else 'none'}"}

        elif rule.name == "PRICE_ADVANTAGE":
            price = data.current_price
            multiplier = 1.0
            reason = 'normal'

            if price < rule.thresholds['very_low_price']:
                multiplier = rule.weights['very_low_bonus']
                reason = 'very_low_price_bonus'
            elif price < rule.thresholds['low_price']:
                multiplier = rule.weights['low_bonus']
                reason = 'low_price_bonus'
            elif price > rule.thresholds['high_price']:
                multiplier = rule.weights['high_penalty']
                reason = 'high_price_penalty'

            return True, {'multiplier': multiplier, 'details': reason}

        # Default: pass
        return True, {}

    def _calculate_technical_score(self, scores: Dict[str, float]) -> float:
        """Calculate technical score from individual rule scores"""
        technical_rules = [
            'TREND_STRENGTH',
            'MOMENTUM_RSI',
            'VOLUME_CONFIRMATION',
            'SHORT_TERM_MOMENTUM',
            'PATTERN_RECOGNITION',
            'RISK_REWARD_SETUP'
        ]

        total = sum(scores.get(rule, 0.0) for rule in technical_rules)
        return min(100.0, total)

    def _calculate_composite_score(self, data: ScreeningMarketData, scores: Dict[str, float]) -> float:
        """
        Calculate composite score (v3.1 weights)

        Weights:
        - Alternative Data: 25%
        - Technical Setup: 25%
        - Sector Strength: 20%
        - Valuation: 15%
        - Catalyst: 10%
        - AI Probability: 5%
        """
        alt_data_score = scores.get('ALTERNATIVE_DATA', 50.0)
        technical_score = self._calculate_technical_score(scores)
        sector_score = scores.get('SECTOR_STRENGTH', 50.0)
        valuation_score = 50.0  # Neutral default
        catalyst_score = 50.0   # Neutral default
        ai_prob = 50.0          # Neutral default

        composite = (
            alt_data_score * 0.25 +
            technical_score * 0.25 +
            sector_score * 0.20 +
            valuation_score * 0.15 +
            catalyst_score * 0.10 +
            ai_prob * 0.05
        )

        # Apply price advantage multiplier
        if 'PRICE_ADVANTAGE' in scores:
            # Get multiplier from details (stored during evaluation)
            # For now, default to 1.0
            price_multiplier = 1.0
            if data.current_price < 30:
                price_multiplier = 1.10
            elif data.current_price < 50:
                price_multiplier = 1.05
            elif data.current_price > 300:
                price_multiplier = 0.95

            composite *= price_multiplier

        return round(composite, 1)

    # ===== Management Methods =====

    def update_threshold(self, rule_name: str, threshold_name: str, value: float):
        """Update a rule's threshold"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.thresholds[threshold_name] = value
                logger.info(f"✅ Updated {rule_name}.{threshold_name} = {value}")
                return
        logger.warning(f"⚠️ Rule {rule_name} not found")

    def update_weight(self, rule_name: str, weight_name: str, value: float):
        """Update a rule's weight"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.weights[weight_name] = value
                logger.info(f"✅ Updated {rule_name}.{weight_name} = {value}")
                return
        logger.warning(f"⚠️ Rule {rule_name} not found")

    def enable_rule(self, rule_name: str):
        """Enable a rule"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"✅ Enabled rule: {rule_name}")
                return
        logger.warning(f"⚠️ Rule {rule_name} not found")

    def disable_rule(self, rule_name: str):
        """Disable a rule"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"❌ Disabled rule: {rule_name}")
                return
        logger.warning(f"⚠️ Rule {rule_name} not found")

    def get_rule_stats(self) -> List[Dict]:
        """Get performance statistics for all rules"""
        stats = []
        for rule in self.rules:
            pass_rate = (rule.passed_count / rule.evaluated_count * 100) if rule.evaluated_count > 0 else 0
            stats.append({
                'name': rule.name,
                'priority': rule.priority.name,
                'enabled': rule.enabled,
                'evaluated': rule.evaluated_count,
                'passed': rule.passed_count,
                'pass_rate': f'{pass_rate:.1f}%',
                'description': rule.description
            })
        return stats

    def export_config(self) -> Dict:
        """Export current configuration"""
        config = {
            'rules': []
        }

        for rule in self.rules:
            config['rules'].append({
                'name': rule.name,
                'enabled': rule.enabled,
                'thresholds': rule.thresholds,
                'weights': rule.weights,
                'conditions': rule.conditions
            })

        return config

    def import_config(self, config: Dict):
        """Import configuration"""
        for rule_config in config['rules']:
            for rule in self.rules:
                if rule.name == rule_config['name']:
                    rule.enabled = rule_config.get('enabled', True)
                    rule.thresholds = rule_config.get('thresholds', {})
                    rule.weights = rule_config.get('weights', {})
                    rule.conditions = rule_config.get('conditions', {})

        logger.info("✅ Configuration imported successfully")

    def reset_stats(self):
        """Reset performance statistics"""
        for rule in self.rules:
            rule.evaluated_count = 0
            rule.passed_count = 0
        logger.info("✅ Rule statistics reset")


# ===== Example Usage =====

if __name__ == "__main__":
    # Initialize engine
    engine = ScreeningRulesEngine()

    # Create sample market data
    sample_data = ScreeningMarketData(
        symbol="NVDA",
        current_price=120.50,
        market_cap=3_000_000_000_000,  # $3T
        avg_volume=50_000_000,
        sector="Technology",
        close_prices=[110, 112, 115, 117, 118, 119, 120, 121, 120.5],
        volume_data=[40e6, 42e6, 45e6, 48e6, 50e6, 52e6, 55e6, 58e6, 60e6],
        ma20=115.0,
        ma50=110.0,
        rsi=58.0,
        support=115.0,
        resistance=125.0,
        insider_buying=True,
        analyst_upgrades=3,
        sector_regime="BULL",
        market_regime="BULL"
    )

    # Evaluate
    passed, details = engine.evaluate_stock(sample_data)

    print(f"\n{'='*60}")
    print(f"Symbol: {details['symbol']}")
    print(f"Passed: {passed}")
    print(f"Technical Score: {details['technical_score']:.1f}/100")
    print(f"Composite Score: {details['composite_score']:.1f}/100")
    print(f"\nPassed Rules: {len(details['passed_rules'])}")
    for rule in details['passed_rules']:
        print(f"  ✅ {rule}")

    if details['failed_rules']:
        print(f"\nFailed Rules: {len(details['failed_rules'])}")
        for rule in details['failed_rules']:
            print(f"  ❌ {rule}: {details.get(f'{rule}_reason', 'Unknown')}")

    print(f"\n{'='*60}")

    # Show stats
    print("\n📊 Rule Statistics:")
    stats = engine.get_rule_stats()
    for stat in stats[:5]:  # Show first 5
        print(f"  {stat['name']:25} | Pass Rate: {stat['pass_rate']:6} | Eval: {stat['evaluated']:3}")
