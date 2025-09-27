"""
Market Regime Detection and Adaptability Module
Dynamically adapts analysis parameters based on market conditions
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
from enum import Enum, IntEnum
import warnings
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import talib


class MarketRegime(IntEnum):
    """Market regime types with ordering support"""
    CRISIS = 0
    BEAR_TRENDING = 1
    BEAR_VOLATILE = 2
    SIDEWAYS_LOW_VOL = 3
    SIDEWAYS_HIGH_VOL = 4
    RECOVERY = 5
    BULL_VOLATILE = 6
    BULL_TRENDING = 7
    UNKNOWN = 99

    @property
    def regime_name(self) -> str:
        """Return string representation of regime"""
        name_mapping = {
            0: "crisis",
            1: "bear_trending",
            2: "bear_volatile",
            3: "sideways_low_vol",
            4: "sideways_high_vol",
            5: "recovery",
            6: "bull_volatile",
            7: "bull_trending",
            99: "unknown"
        }
        return name_mapping.get(self.value, "unknown")


class VolatilityRegime(IntEnum):
    """Volatility regime types with ordering support"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    EXTREME = 3


class TrendRegime(IntEnum):
    """Trend regime types with ordering support"""
    STRONG_DOWNTREND = 0
    WEAK_DOWNTREND = 1
    SIDEWAYS = 2
    WEAK_UPTREND = 3
    STRONG_UPTREND = 4


class MarketRegimeDetector:
    """Detects and adapts to different market regimes"""

    def __init__(self, price_data: pd.DataFrame = None, config: Dict[str, Any] = None):
        self.config = config if config is not None else {}
        self.price_data = price_data
        self.regime_history = []
        self.regime_model = None
        self.scaler = StandardScaler()

        # Regime detection parameters
        self.detection_params = {
            'lookback_period': 60,  # Days to look back for regime detection
            'volatility_window': 20,
            'trend_window': 50,
            'volume_window': 20,
            'regime_stability_threshold': 0.7,
            'min_regime_duration': 5  # Minimum days in a regime
        }

        # Adaptive parameters for different regimes
        self.regime_parameters = {
            MarketRegime.BULL_TRENDING: {
                'rsi_overbought': 80,
                'rsi_oversold': 40,
                'ma_periods': [10, 20, 50],
                'volatility_multiplier': 1.0,
                'position_size_multiplier': 1.2,
                'stop_loss_multiplier': 0.8,
                'take_profit_multiplier': 1.5
            },
            MarketRegime.BEAR_TRENDING: {
                'rsi_overbought': 60,
                'rsi_oversold': 20,
                'ma_periods': [20, 50, 100],
                'volatility_multiplier': 1.5,
                'position_size_multiplier': 0.6,
                'stop_loss_multiplier': 1.2,
                'take_profit_multiplier': 1.0
            },
            MarketRegime.SIDEWAYS_LOW_VOL: {
                'rsi_overbought': 75,
                'rsi_oversold': 25,
                'ma_periods': [5, 10, 20],
                'volatility_multiplier': 0.8,
                'position_size_multiplier': 1.0,
                'stop_loss_multiplier': 1.0,
                'take_profit_multiplier': 1.2
            },
            MarketRegime.SIDEWAYS_HIGH_VOL: {
                'rsi_overbought': 85,
                'rsi_oversold': 15,
                'ma_periods': [20, 50, 100],
                'volatility_multiplier': 2.0,
                'position_size_multiplier': 0.8,
                'stop_loss_multiplier': 1.5,
                'take_profit_multiplier': 0.8
            },
            MarketRegime.CRISIS: {
                'rsi_overbought': 50,
                'rsi_oversold': 10,
                'ma_periods': [50, 100, 200],
                'volatility_multiplier': 3.0,
                'position_size_multiplier': 0.3,
                'stop_loss_multiplier': 2.0,
                'take_profit_multiplier': 0.5
            }
        }

    def detect_current_regime(self, data: pd.DataFrame,
                            market_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Detect current market regime

        Args:
            data: Price data for the symbol
            market_data: Optional market index data for correlation

        Returns:
            Dictionary with regime information
        """
        logger.info("Detecting current market regime")

        regime_info = {
            'current_regime': MarketRegime.UNKNOWN,
            'regime_probability': 0.0,
            'regime_strength': 0.0,
            'regime_duration': 0,
            'next_regime_probabilities': {},
            'regime_features': {},
            'adaptation_required': False
        }

        if len(data) < self.detection_params['lookback_period']:
            logger.warning("Insufficient data for regime detection")
            return regime_info

        # 1. Calculate regime features
        features = self._calculate_regime_features(data, market_data)
        regime_info['regime_features'] = features

        # 2. Detect regime using multiple methods
        trend_regime = self._detect_trend_regime(features)
        volatility_regime = self._detect_volatility_regime(features)
        volume_regime = self._detect_volume_regime(features)

        # 3. Combine regimes to determine overall market regime
        overall_regime = self._combine_regimes(trend_regime, volatility_regime, volume_regime, features)
        regime_info['current_regime'] = overall_regime

        # 4. Calculate regime probability and strength
        regime_info['regime_probability'] = self._calculate_regime_probability(features, overall_regime)
        regime_info['regime_strength'] = self._calculate_regime_strength(features, overall_regime)

        # 5. Estimate regime duration
        regime_info['regime_duration'] = self._estimate_regime_duration(data, overall_regime)

        # 6. Predict next regime probabilities
        regime_info['next_regime_probabilities'] = self._predict_regime_transitions(features, overall_regime)

        # 7. Determine if adaptation is required
        regime_info['adaptation_required'] = self._should_adapt_parameters(overall_regime)

        # Update regime history
        self._update_regime_history(overall_regime, regime_info['regime_strength'])

        return regime_info

    def adapt_parameters(self, current_regime: MarketRegime,
                        base_parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adapt analysis parameters based on current market regime

        Args:
            current_regime: Current market regime
            base_parameters: Base analysis parameters

        Returns:
            Adapted parameters
        """
        logger.info(f"Adapting parameters for regime: {current_regime.value}")

        adapted_params = base_parameters.copy()

        # Get regime-specific parameter adjustments
        regime_adjustments = self.regime_parameters.get(current_regime, {})

        if not regime_adjustments:
            logger.warning(f"No parameter adjustments defined for regime: {current_regime.value}")
            return adapted_params

        # Apply regime-specific adjustments
        for param, adjustment in regime_adjustments.items():
            if param in adapted_params:
                if isinstance(adjustment, (int, float)):
                    # Multiply numeric parameters
                    if isinstance(adapted_params[param], (int, float)):
                        adapted_params[param] *= adjustment
                    elif isinstance(adapted_params[param], list):
                        adapted_params[param] = [x * adjustment for x in adapted_params[param]]
                else:
                    # Replace non-numeric parameters
                    adapted_params[param] = adjustment
            else:
                # Add new regime-specific parameter
                adapted_params[param] = adjustment

        logger.info(f"Parameters adapted for {current_regime.value}")
        return adapted_params

    def get_regime_specific_indicators(self, regime: MarketRegime) -> List[str]:
        """
        Get the most effective indicators for a specific regime

        Args:
            regime: Market regime

        Returns:
            List of recommended indicators
        """
        regime_indicators = {
            MarketRegime.BULL_TRENDING: [
                'moving_averages', 'macd', 'momentum', 'adx', 'parabolic_sar'
            ],
            MarketRegime.BEAR_TRENDING: [
                'moving_averages', 'rsi', 'macd', 'adx', 'williams_r'
            ],
            MarketRegime.SIDEWAYS_LOW_VOL: [
                'rsi', 'stochastic', 'bollinger_bands', 'cci', 'mfi'
            ],
            MarketRegime.SIDEWAYS_HIGH_VOL: [
                'bollinger_bands', 'atr', 'keltner_channels', 'rsi', 'vwap'
            ],
            MarketRegime.BULL_VOLATILE: [
                'atr', 'bollinger_bands', 'rsi', 'momentum', 'volume_indicators'
            ],
            MarketRegime.BEAR_VOLATILE: [
                'atr', 'rsi', 'moving_averages', 'vix', 'volume_indicators'
            ],
            MarketRegime.CRISIS: [
                'moving_averages', 'support_resistance', 'volume_indicators', 'vix'
            ],
            MarketRegime.RECOVERY: [
                'momentum', 'macd', 'moving_averages', 'volume_indicators', 'rsi'
            ]
        }

        return regime_indicators.get(regime, ['moving_averages', 'rsi', 'macd'])

    def calculate_sector_rotation(self, sector_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Analyze sector rotation patterns

        Args:
            sector_data: Dictionary of sector -> price data

        Returns:
            Sector rotation analysis
        """
        logger.info("Analyzing sector rotation patterns")

        rotation_analysis = {
            'leading_sectors': [],
            'lagging_sectors': [],
            'rotation_phase': 'unknown',
            'sector_momentum': {},
            'relative_strength': {}
        }

        if not sector_data:
            return rotation_analysis

        # Calculate relative performance for each sector
        for sector, data in sector_data.items():
            if len(data) > 20:
                # 20-day momentum
                momentum = (data['close'].iloc[-1] / data['close'].iloc[-20] - 1) * 100
                rotation_analysis['sector_momentum'][sector] = momentum

                # Relative strength vs market (simplified)
                rs = self._calculate_relative_strength(data)
                rotation_analysis['relative_strength'][sector] = rs

        # Identify leading and lagging sectors
        if rotation_analysis['sector_momentum']:
            sorted_sectors = sorted(
                rotation_analysis['sector_momentum'].items(),
                key=lambda x: x[1],
                reverse=True
            )

            n_sectors = len(sorted_sectors)
            n_leading = max(1, n_sectors // 3)
            n_lagging = max(1, n_sectors // 3)

            rotation_analysis['leading_sectors'] = [s[0] for s in sorted_sectors[:n_leading]]
            rotation_analysis['lagging_sectors'] = [s[0] for s in sorted_sectors[-n_lagging:]]

        # Determine rotation phase
        rotation_analysis['rotation_phase'] = self._determine_rotation_phase(rotation_analysis)

        return rotation_analysis

    def _calculate_regime_features(self, data: pd.DataFrame,
                                 market_data: Optional[pd.DataFrame] = None) -> Dict[str, float]:
        """Calculate features for regime detection"""
        features = {}

        if data.empty:
            return features

        # Price-based features
        returns = data['close'].pct_change().dropna()

        # 1. Trend features
        if len(data) >= 50:
            sma_20 = data['close'].rolling(20).mean()
            sma_50 = data['close'].rolling(50).mean()
            features['trend_20_50'] = (sma_20.iloc[-1] - sma_50.iloc[-1]) / sma_50.iloc[-1]

        # 2. Volatility features
        features['volatility_20d'] = returns.rolling(20).std() * np.sqrt(252)
        features['volatility_percentile'] = self._calculate_volatility_percentile(returns)

        # 3. Momentum features
        if len(data) >= 20:
            features['momentum_20d'] = (data['close'].iloc[-1] / data['close'].iloc[-20] - 1) * 100

        # 4. Volume features
        if 'volume' in data.columns:
            volume_ma = data['volume'].rolling(20).mean()
            features['volume_ratio'] = data['volume'].iloc[-1] / volume_ma.iloc[-1]

        # 5. Market correlation (if market data available)
        if market_data is not None and len(market_data) >= len(data):
            market_returns = market_data['close'].pct_change().dropna()
            if len(returns) == len(market_returns):
                correlation = returns.corr(market_returns)
                features['market_correlation'] = correlation if not np.isnan(correlation) else 0.0

        # 6. Technical indicators
        if len(data) >= 14:
            features['rsi'] = talib.RSI(data['close'].values, timeperiod=14)[-1]

        if len(data) >= 26:
            macd, signal, _ = talib.MACD(data['close'].values)
            features['macd_signal'] = macd[-1] - signal[-1] if not np.isnan(macd[-1]) else 0.0

        return features

    def _detect_trend_regime(self, features: Dict[str, float]) -> TrendRegime:
        """Detect trend regime based on features"""
        trend_score = 0.0

        # Moving average trend
        if 'trend_20_50' in features:
            trend_score += features['trend_20_50'] * 100

        # Momentum contribution
        if 'momentum_20d' in features:
            trend_score += features['momentum_20d'] * 0.5

        # MACD contribution
        if 'macd_signal' in features:
            trend_score += features['macd_signal'] * 10

        # Classify trend
        if trend_score > 5:
            return TrendRegime.STRONG_UPTREND
        elif trend_score > 2:
            return TrendRegime.WEAK_UPTREND
        elif trend_score > -2:
            return TrendRegime.SIDEWAYS
        elif trend_score > -5:
            return TrendRegime.WEAK_DOWNTREND
        else:
            return TrendRegime.STRONG_DOWNTREND

    def _detect_volatility_regime(self, features: Dict[str, float]) -> VolatilityRegime:
        """Detect volatility regime based on features"""
        if 'volatility_percentile' not in features:
            return VolatilityRegime.NORMAL

        vol_percentile = features['volatility_percentile']

        if vol_percentile > 0.9:
            return VolatilityRegime.EXTREME
        elif vol_percentile > 0.7:
            return VolatilityRegime.HIGH
        elif vol_percentile < 0.3:
            return VolatilityRegime.LOW
        else:
            return VolatilityRegime.NORMAL

    def _detect_volume_regime(self, features: Dict[str, float]) -> str:
        """Detect volume regime based on features"""
        if 'volume_ratio' not in features:
            return 'normal'

        volume_ratio = features['volume_ratio']

        if volume_ratio > 2.0:
            return 'high'
        elif volume_ratio < 0.5:
            return 'low'
        else:
            return 'normal'

    def _combine_regimes(self, trend_regime: TrendRegime,
                        volatility_regime: VolatilityRegime,
                        volume_regime: str,
                        features: Dict[str, float]) -> MarketRegime:
        """Combine individual regimes into overall market regime"""

        # Crisis detection (extreme volatility + strong downtrend)
        if (volatility_regime == VolatilityRegime.EXTREME and
            trend_regime in [TrendRegime.STRONG_DOWNTREND, TrendRegime.WEAK_DOWNTREND]):
            return MarketRegime.CRISIS

        # Recovery detection (high volume + uptrend after crisis)
        if (trend_regime in [TrendRegime.STRONG_UPTREND, TrendRegime.WEAK_UPTREND] and
            volume_regime == 'high' and
            volatility_regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]):
            return MarketRegime.RECOVERY

        # Bull markets
        if trend_regime in [TrendRegime.STRONG_UPTREND, TrendRegime.WEAK_UPTREND]:
            if volatility_regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]:
                return MarketRegime.BULL_VOLATILE
            else:
                return MarketRegime.BULL_TRENDING

        # Bear markets
        if trend_regime in [TrendRegime.STRONG_DOWNTREND, TrendRegime.WEAK_DOWNTREND]:
            if volatility_regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]:
                return MarketRegime.BEAR_VOLATILE
            else:
                return MarketRegime.BEAR_TRENDING

        # Sideways markets
        if trend_regime == TrendRegime.SIDEWAYS:
            if volatility_regime in [VolatilityRegime.LOW]:
                return MarketRegime.SIDEWAYS_LOW_VOL
            else:
                return MarketRegime.SIDEWAYS_HIGH_VOL

        return MarketRegime.UNKNOWN

    def _calculate_regime_probability(self, features: Dict[str, float],
                                    regime: MarketRegime) -> float:
        """Calculate probability of current regime classification"""
        # Simplified probability calculation
        # In practice, this would use a trained ML model

        confidence_factors = []

        # Trend confidence
        if 'trend_20_50' in features:
            trend_strength = abs(features['trend_20_50'])
            confidence_factors.append(min(1.0, trend_strength * 10))

        # Volatility confidence
        if 'volatility_percentile' in features:
            vol_confidence = abs(features['volatility_percentile'] - 0.5) * 2
            confidence_factors.append(vol_confidence)

        # Volume confidence
        if 'volume_ratio' in features:
            vol_deviation = abs(features['volume_ratio'] - 1.0)
            vol_confidence = min(1.0, vol_deviation)
            confidence_factors.append(vol_confidence)

        return np.mean(confidence_factors) if confidence_factors else 0.5

    def _calculate_regime_strength(self, features: Dict[str, float],
                                 regime: MarketRegime) -> float:
        """Calculate strength of current regime"""
        # Regime strength based on how pronounced the characteristics are
        strength_factors = []

        if regime in [MarketRegime.BULL_TRENDING, MarketRegime.BEAR_TRENDING]:
            # Trend strength
            if 'momentum_20d' in features:
                strength_factors.append(abs(features['momentum_20d']) / 20)

        if regime in [MarketRegime.BULL_VOLATILE, MarketRegime.BEAR_VOLATILE, MarketRegime.CRISIS]:
            # Volatility strength
            if 'volatility_percentile' in features:
                strength_factors.append(features['volatility_percentile'])

        return min(1.0, np.mean(strength_factors)) if strength_factors else 0.5

    def _estimate_regime_duration(self, data: pd.DataFrame, regime: MarketRegime) -> int:
        """Estimate how long the current regime has been in place"""
        # Simplified duration estimation
        # In practice, this would track regime changes over time
        return len(self.regime_history) if self.regime_history else 0

    def _predict_regime_transitions(self, features: Dict[str, float],
                                  current_regime: MarketRegime) -> Dict[str, float]:
        """Predict probabilities of transitioning to other regimes"""
        # Simplified transition prediction
        # In practice, this would use a Markov model or ML approach

        transition_probs = {}

        # Define likely transitions based on market behavior
        transition_matrix = {
            MarketRegime.BULL_TRENDING: {
                MarketRegime.BULL_VOLATILE: 0.3,
                MarketRegime.SIDEWAYS_LOW_VOL: 0.4,
                MarketRegime.BEAR_TRENDING: 0.2,
                MarketRegime.BULL_TRENDING: 0.1
            },
            MarketRegime.BEAR_TRENDING: {
                MarketRegime.BEAR_VOLATILE: 0.3,
                MarketRegime.CRISIS: 0.2,
                MarketRegime.SIDEWAYS_LOW_VOL: 0.3,
                MarketRegime.RECOVERY: 0.2
            },
            MarketRegime.SIDEWAYS_LOW_VOL: {
                MarketRegime.BULL_TRENDING: 0.4,
                MarketRegime.BEAR_TRENDING: 0.3,
                MarketRegime.SIDEWAYS_HIGH_VOL: 0.2,
                MarketRegime.SIDEWAYS_LOW_VOL: 0.1
            }
        }

        return transition_matrix.get(current_regime, {})

    def _should_adapt_parameters(self, regime: MarketRegime) -> bool:
        """Determine if parameters should be adapted for current regime"""
        # Check if current regime is different from recent history
        if not self.regime_history:
            return True

        recent_regimes = self.regime_history[-5:]  # Last 5 periods
        regime_stability = sum(1 for r in recent_regimes if r == regime) / len(recent_regimes)

        return regime_stability < self.detection_params['regime_stability_threshold']

    def _update_regime_history(self, regime: MarketRegime, strength: float):
        """Update regime history for tracking changes"""
        self.regime_history.append({
            'regime': regime,
            'timestamp': datetime.now(),
            'strength': strength
        })

        # Keep only recent history
        max_history = 100
        if len(self.regime_history) > max_history:
            self.regime_history = self.regime_history[-max_history:]

    def _calculate_volatility_percentile(self, returns: pd.Series, window: int = 252) -> float:
        """Calculate current volatility percentile over rolling window"""
        if len(returns) < window:
            return 0.5

        current_vol = returns.rolling(20).std().iloc[-1] * np.sqrt(252)
        historical_vols = returns.rolling(20).std().rolling(window).apply(
            lambda x: x.iloc[-1] if len(x) > 0 else 0
        ) * np.sqrt(252)

        percentile = stats.percentileofscore(historical_vols.dropna(), current_vol) / 100
        return percentile

    def _calculate_relative_strength(self, data: pd.DataFrame, benchmark_return: float = 0.1) -> float:
        """Calculate relative strength vs benchmark"""
        if len(data) < 20:
            return 0.0

        symbol_return = (data['close'].iloc[-1] / data['close'].iloc[-20] - 1) * 100
        relative_strength = symbol_return - benchmark_return
        return relative_strength

    def _determine_rotation_phase(self, rotation_analysis: Dict[str, Any]) -> str:
        """Determine current sector rotation phase"""
        # Simplified rotation phase detection
        leading_momentum = np.mean([
            rotation_analysis['sector_momentum'].get(sector, 0)
            for sector in rotation_analysis['leading_sectors']
        ]) if rotation_analysis['leading_sectors'] else 0

        if leading_momentum > 5:
            return 'expansion'
        elif leading_momentum > 0:
            return 'peak'
        elif leading_momentum > -5:
            return 'contraction'
        else:
            return 'trough'

    def get_regime_history(self) -> List[Dict[str, Any]]:
        """
        Get historical regime information

        Returns:
            List of historical regime data
        """
        return self.regime_history

    def detect_regime_transitions(self) -> Dict[str, Any]:
        """
        Detect regime transitions and transition patterns

        Returns:
            Dictionary with transition information
        """
        transitions = {
            'recent_transitions': [],
            'transition_frequency': 0.0,
            'average_regime_duration': 0.0,
            'regime_stability': 0.0
        }

        if len(self.regime_history) < 2:
            return transitions

        # Calculate transition frequency
        transition_count = 0
        for i in range(1, len(self.regime_history)):
            if self.regime_history[i]['regime'] != self.regime_history[i-1]['regime']:
                transition_count += 1
                transitions['recent_transitions'].append({
                    'from': self.regime_history[i-1]['regime'],
                    'to': self.regime_history[i]['regime'],
                    'date': self.regime_history[i].get('date', 'unknown')
                })

        transitions['transition_frequency'] = transition_count / len(self.regime_history)

        # Calculate average regime duration (simplified)
        if transition_count > 0:
            transitions['average_regime_duration'] = len(self.regime_history) / (transition_count + 1)
        else:
            transitions['average_regime_duration'] = len(self.regime_history)

        # Calculate regime stability (inverse of transition frequency)
        transitions['regime_stability'] = 1.0 - transitions['transition_frequency']

        return transitions