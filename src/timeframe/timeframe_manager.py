"""
Time Frame and Frequency Optimization Module
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
from enum import Enum
import warnings


class TimeFrame(Enum):
    """Time frame enumeration"""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"
    QUARTER_1 = "1Q"
    YEAR_1 = "1Y"


class TradingStrategy(Enum):
    """Trading strategy types"""
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING_TRADING = "swing_trading"
    POSITION_TRADING = "position_trading"
    LONG_TERM_INVESTING = "long_term_investing"


class TimeFrameManager:
    """Manages time frame selection and optimization for different strategies"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

        # Strategy-specific time frame configurations
        self.strategy_timeframes = {
            TradingStrategy.SCALPING: {
                'primary': [TimeFrame.MINUTE_1, TimeFrame.MINUTE_5],
                'secondary': [TimeFrame.MINUTE_15, TimeFrame.MINUTE_30],
                'confirmation': [TimeFrame.HOUR_1],
                'max_holding_period': timedelta(hours=1),
                'data_lookback_days': 5
            },
            TradingStrategy.DAY_TRADING: {
                'primary': [TimeFrame.MINUTE_15, TimeFrame.MINUTE_30],
                'secondary': [TimeFrame.HOUR_1, TimeFrame.HOUR_4],
                'confirmation': [TimeFrame.DAY_1],
                'max_holding_period': timedelta(days=1),
                'data_lookback_days': 30
            },
            TradingStrategy.SWING_TRADING: {
                'primary': [TimeFrame.HOUR_1, TimeFrame.HOUR_4],
                'secondary': [TimeFrame.DAY_1],
                'confirmation': [TimeFrame.WEEK_1],
                'max_holding_period': timedelta(weeks=2),
                'data_lookback_days': 90
            },
            TradingStrategy.POSITION_TRADING: {
                'primary': [TimeFrame.DAY_1],
                'secondary': [TimeFrame.WEEK_1],
                'confirmation': [TimeFrame.MONTH_1],
                'max_holding_period': timedelta(days=180),
                'data_lookback_days': 365
            },
            TradingStrategy.LONG_TERM_INVESTING: {
                'primary': [TimeFrame.WEEK_1, TimeFrame.MONTH_1],
                'secondary': [TimeFrame.QUARTER_1],
                'confirmation': [TimeFrame.YEAR_1],
                'max_holding_period': timedelta(days=1095),  # 3 years
                'data_lookback_days': 1825  # 5 years
            }
        }

        # Technical indicator optimal time frames
        self.indicator_timeframes = {
            'rsi': {
                TimeFrame.MINUTE_5: {'period': 14, 'overbought': 80, 'oversold': 20},
                TimeFrame.HOUR_1: {'period': 14, 'overbought': 75, 'oversold': 25},
                TimeFrame.DAY_1: {'period': 14, 'overbought': 70, 'oversold': 30}
            },
            'macd': {
                TimeFrame.MINUTE_15: {'fast': 8, 'slow': 21, 'signal': 5},
                TimeFrame.HOUR_1: {'fast': 12, 'slow': 26, 'signal': 9},
                TimeFrame.DAY_1: {'fast': 12, 'slow': 26, 'signal': 9}
            },
            'moving_averages': {
                TimeFrame.MINUTE_5: {'short': 20, 'medium': 50, 'long': 100},
                TimeFrame.HOUR_1: {'short': 20, 'medium': 50, 'long': 200},
                TimeFrame.DAY_1: {'short': 20, 'medium': 50, 'long': 200}
            }
        }

    def get_optimal_timeframes(self, strategy: TradingStrategy,
                             market_volatility: float = None,
                             symbol_characteristics: Dict[str, Any] = None) -> Dict[str, List[TimeFrame]]:
        """
        Get optimal time frames for a given strategy

        Args:
            strategy: Trading strategy
            market_volatility: Current market volatility (0-1)
            symbol_characteristics: Symbol-specific characteristics

        Returns:
            Dictionary of time frames by category
        """
        base_timeframes = self.strategy_timeframes.get(strategy, {})

        if not base_timeframes:
            logger.warning(f"No time frames defined for strategy: {strategy}")
            return self._get_default_timeframes()

        optimal_timeframes = base_timeframes.copy()

        # Adjust for market volatility
        if market_volatility is not None:
            optimal_timeframes = self._adjust_for_volatility(optimal_timeframes, market_volatility)

        # Adjust for symbol characteristics
        if symbol_characteristics:
            optimal_timeframes = self._adjust_for_symbol(optimal_timeframes, symbol_characteristics)

        return optimal_timeframes

    def get_multi_timeframe_analysis_plan(self, strategy: TradingStrategy) -> Dict[str, Any]:
        """
        Create a comprehensive multi-timeframe analysis plan

        Args:
            strategy: Trading strategy

        Returns:
            Analysis plan with time frames and their purposes
        """
        timeframes = self.get_optimal_timeframes(strategy)

        analysis_plan = {
            'strategy': strategy.value,
            'timeframes': {},
            'analysis_sequence': [],
            'confirmation_rules': {},
            'risk_parameters': {}
        }

        # Primary time frames - for entry signals
        for tf in timeframes.get('primary', []):
            analysis_plan['timeframes'][tf.value] = {
                'purpose': 'entry_signal',
                'weight': 0.5,
                'indicators': self._get_timeframe_indicators(tf, 'entry'),
                'data_points_needed': self._calculate_data_points(tf, strategy)
            }

        # Secondary time frames - for trend confirmation
        for tf in timeframes.get('secondary', []):
            analysis_plan['timeframes'][tf.value] = {
                'purpose': 'trend_confirmation',
                'weight': 0.3,
                'indicators': self._get_timeframe_indicators(tf, 'trend'),
                'data_points_needed': self._calculate_data_points(tf, strategy)
            }

        # Confirmation time frames - for overall market direction
        for tf in timeframes.get('confirmation', []):
            analysis_plan['timeframes'][tf.value] = {
                'purpose': 'market_direction',
                'weight': 0.2,
                'indicators': self._get_timeframe_indicators(tf, 'direction'),
                'data_points_needed': self._calculate_data_points(tf, strategy)
            }

        # Define analysis sequence (bottom-up approach)
        all_timeframes = []
        all_timeframes.extend(timeframes.get('confirmation', []))
        all_timeframes.extend(timeframes.get('secondary', []))
        all_timeframes.extend(timeframes.get('primary', []))

        analysis_plan['analysis_sequence'] = [tf.value for tf in all_timeframes]

        # Confirmation rules
        analysis_plan['confirmation_rules'] = self._get_confirmation_rules(strategy)

        # Risk parameters by time frame
        analysis_plan['risk_parameters'] = self._get_timeframe_risk_parameters(strategy)

        return analysis_plan

    def optimize_timeframe_for_symbol(self, symbol: str,
                                    historical_data: pd.DataFrame,
                                    strategy: TradingStrategy) -> Dict[str, Any]:
        """
        Optimize time frame selection for a specific symbol

        Args:
            symbol: Stock symbol
            historical_data: Historical price data
            strategy: Trading strategy

        Returns:
            Optimized time frame recommendations
        """
        logger.info(f"Optimizing time frames for {symbol} with {strategy.value} strategy")

        if historical_data.empty:
            return self._get_default_optimization_result(symbol, strategy)

        analysis_result = {
            'symbol': symbol,
            'strategy': strategy.value,
            'optimal_timeframes': {},
            'performance_metrics': {},
            'recommendations': []
        }

        # Analyze symbol characteristics
        symbol_characteristics = self._analyze_symbol_characteristics(historical_data)

        # Test different time frame combinations
        timeframe_performance = self._test_timeframe_combinations(
            historical_data, strategy, symbol_characteristics
        )

        # Select optimal time frames based on performance
        optimal_timeframes = self._select_optimal_timeframes(timeframe_performance)

        analysis_result['optimal_timeframes'] = optimal_timeframes
        analysis_result['performance_metrics'] = timeframe_performance
        analysis_result['symbol_characteristics'] = symbol_characteristics

        # Generate recommendations
        recommendations = self._generate_timeframe_recommendations(
            symbol_characteristics, optimal_timeframes, strategy
        )
        analysis_result['recommendations'] = recommendations

        return analysis_result

    def resample_data_to_timeframe(self, data: pd.DataFrame,
                                 target_timeframe: TimeFrame) -> pd.DataFrame:
        """
        Resample data to target time frame

        Args:
            data: Original data
            target_timeframe: Target time frame

        Returns:
            Resampled data
        """
        if data.empty or 'date' not in data.columns:
            return data

        # Set date as index for resampling
        data_copy = data.copy()
        data_copy.set_index('date', inplace=True)

        # Define resampling rules
        resample_rules = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }

        # Map TimeFrame to pandas resample frequency
        freq_mapping = {
            TimeFrame.MINUTE_1: '1T',
            TimeFrame.MINUTE_5: '5T',
            TimeFrame.MINUTE_15: '15T',
            TimeFrame.MINUTE_30: '30T',
            TimeFrame.HOUR_1: '1H',
            TimeFrame.HOUR_4: '4H',
            TimeFrame.DAY_1: '1D',
            TimeFrame.WEEK_1: 'W',
            TimeFrame.MONTH_1: 'M',
            TimeFrame.QUARTER_1: 'Q',
            TimeFrame.YEAR_1: 'Y'
        }

        freq = freq_mapping.get(target_timeframe, '1D')

        try:
            # Resample the data
            resampled = data_copy.resample(freq).agg(resample_rules)

            # Remove rows with NaN (no data for that period)
            resampled = resampled.dropna()

            # Reset index to get date back as column
            resampled.reset_index(inplace=True)

            # Add symbol if it exists in original data
            if 'symbol' in data.columns:
                resampled['symbol'] = data['symbol'].iloc[0]

            logger.info(f"Resampled data from {len(data)} to {len(resampled)} records for {target_timeframe.value}")
            return resampled

        except Exception as e:
            logger.error(f"Error resampling data to {target_timeframe.value}: {e}")
            return pd.DataFrame()

    def get_data_requirements(self, strategy: TradingStrategy,
                            timeframes: List[TimeFrame]) -> Dict[str, Any]:
        """
        Calculate data requirements for given strategy and time frames

        Args:
            strategy: Trading strategy
            timeframes: List of time frames

        Returns:
            Data requirements specification
        """
        requirements = {
            'strategy': strategy.value,
            'total_lookback_days': 0,
            'minimum_data_points': {},
            'preferred_data_points': {},
            'update_frequency': {},
            'storage_requirements': {}
        }

        strategy_config = self.strategy_timeframes.get(strategy, {})
        base_lookback = strategy_config.get('data_lookback_days', 365)

        for timeframe in timeframes:
            # Calculate minimum and preferred data points
            min_points = self._calculate_minimum_data_points(timeframe)
            preferred_points = self._calculate_preferred_data_points(timeframe, strategy)

            requirements['minimum_data_points'][timeframe.value] = min_points
            requirements['preferred_data_points'][timeframe.value] = preferred_points

            # Update frequency requirements
            requirements['update_frequency'][timeframe.value] = self._get_update_frequency(timeframe)

            # Storage requirements (MB per symbol)
            requirements['storage_requirements'][timeframe.value] = self._estimate_storage_size(
                timeframe, preferred_points
            )

        # Calculate total lookback needed
        requirements['total_lookback_days'] = max(base_lookback,
                                                 self._calculate_total_lookback(timeframes))

        return requirements

    def _adjust_for_volatility(self, timeframes: Dict[str, List[TimeFrame]],
                              volatility: float) -> Dict[str, List[TimeFrame]]:
        """Adjust time frames based on market volatility"""
        adjusted = timeframes.copy()

        if volatility > 0.3:  # High volatility
            # Use longer time frames to filter noise
            for category in ['primary', 'secondary']:
                if category in adjusted:
                    # Shift to next higher time frame
                    adjusted[category] = self._shift_timeframes_higher(adjusted[category])

        elif volatility < 0.1:  # Low volatility
            # Use shorter time frames for more sensitivity
            for category in ['primary', 'secondary']:
                if category in adjusted:
                    # Shift to next lower time frame
                    adjusted[category] = self._shift_timeframes_lower(adjusted[category])

        return adjusted

    def _adjust_for_symbol(self, timeframes: Dict[str, List[TimeFrame]],
                          characteristics: Dict[str, Any]) -> Dict[str, List[TimeFrame]]:
        """Adjust time frames based on symbol characteristics"""
        adjusted = timeframes.copy()

        avg_volume = characteristics.get('average_volume', 0)
        price_volatility = characteristics.get('price_volatility', 0)

        # Low volume stocks need longer time frames
        if avg_volume < 100000:  # Low volume
            for category in ['primary']:
                if category in adjusted:
                    adjusted[category] = self._shift_timeframes_higher(adjusted[category])

        # High volatility stocks may need longer time frames for confirmation
        if price_volatility > 0.05:  # 5% daily volatility
            for category in ['confirmation']:
                if category in adjusted:
                    adjusted[category] = self._shift_timeframes_higher(adjusted[category])

        return adjusted

    def _get_default_timeframes(self) -> Dict[str, List[TimeFrame]]:
        """Get default time frames"""
        return {
            'primary': [TimeFrame.DAY_1],
            'secondary': [TimeFrame.WEEK_1],
            'confirmation': [TimeFrame.MONTH_1]
        }

    def _get_timeframe_indicators(self, timeframe: TimeFrame, purpose: str) -> List[str]:
        """Get appropriate indicators for time frame and purpose"""
        indicator_map = {
            'entry': ['rsi', 'macd', 'bollinger_bands', 'volume'],
            'trend': ['moving_averages', 'adx', 'parabolic_sar'],
            'direction': ['moving_averages', 'trend_lines', 'support_resistance']
        }

        return indicator_map.get(purpose, ['moving_averages'])

    def _calculate_data_points(self, timeframe: TimeFrame, strategy: TradingStrategy) -> int:
        """Calculate required data points for time frame"""
        base_points = {
            TimeFrame.MINUTE_1: 1440,  # 1 day
            TimeFrame.MINUTE_5: 288,   # 1 day
            TimeFrame.MINUTE_15: 96,   # 1 day
            TimeFrame.MINUTE_30: 48,   # 1 day
            TimeFrame.HOUR_1: 24,      # 1 day
            TimeFrame.HOUR_4: 168,     # 1 week
            TimeFrame.DAY_1: 252,      # 1 year
            TimeFrame.WEEK_1: 52,      # 1 year
            TimeFrame.MONTH_1: 24,     # 2 years
            TimeFrame.QUARTER_1: 20,   # 5 years
            TimeFrame.YEAR_1: 10       # 10 years
        }

        return base_points.get(timeframe, 252)

    def _get_confirmation_rules(self, strategy: TradingStrategy) -> Dict[str, Any]:
        """Get confirmation rules for strategy"""
        return {
            'trend_alignment_required': True,
            'minimum_timeframes_agreeing': 2,
            'confirmation_timeframe_weight': 0.4,
            'divergence_tolerance': 0.1
        }

    def _get_timeframe_risk_parameters(self, strategy: TradingStrategy) -> Dict[str, Any]:
        """Get risk parameters by time frame"""
        base_config = self.strategy_timeframes.get(strategy, {})

        return {
            'stop_loss_multiplier': {
                'primary': 1.0,
                'secondary': 1.5,
                'confirmation': 2.0
            },
            'position_size_adjustment': {
                'high_frequency': 0.5,
                'medium_frequency': 1.0,
                'low_frequency': 1.5
            },
            'max_holding_period': base_config.get('max_holding_period', timedelta(days=30))
        }

    def _analyze_symbol_characteristics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze symbol-specific characteristics"""
        if data.empty:
            return {}

        characteristics = {}

        # Average daily volume
        if 'volume' in data.columns:
            characteristics['average_volume'] = data['volume'].mean()
            characteristics['volume_volatility'] = data['volume'].std() / data['volume'].mean()

        # Price volatility
        if 'close' in data.columns:
            returns = data['close'].pct_change().dropna()
            characteristics['price_volatility'] = returns.std()
            characteristics['average_price'] = data['close'].mean()

        # Liquidity indicators
        characteristics['trading_days'] = len(data)

        # Trend characteristics
        if len(data) > 50 and 'close' in data.columns:
            short_ma = data['close'].rolling(20).mean()
            long_ma = data['close'].rolling(50).mean()
            characteristics['trend_strength'] = (short_ma.iloc[-1] - long_ma.iloc[-1]) / long_ma.iloc[-1]

        return characteristics

    def _test_timeframe_combinations(self, data: pd.DataFrame,
                                   strategy: TradingStrategy,
                                   characteristics: Dict[str, Any]) -> Dict[str, Any]:
        """Test different time frame combinations"""
        # Simplified performance testing
        # In a real implementation, this would involve backtesting

        performance = {}
        available_timeframes = [TimeFrame.MINUTE_15, TimeFrame.HOUR_1, TimeFrame.DAY_1, TimeFrame.WEEK_1]

        for tf in available_timeframes:
            # Simulate performance metrics
            volatility_score = characteristics.get('price_volatility', 0.02)
            volume_score = min(characteristics.get('average_volume', 1000000) / 1000000, 1.0)

            # Higher time frames generally more stable but less responsive
            stability_bonus = self._get_timeframe_stability_bonus(tf)
            responsiveness_penalty = self._get_timeframe_responsiveness_penalty(tf)

            performance[tf.value] = {
                'score': (volume_score + stability_bonus - responsiveness_penalty - volatility_score),
                'stability': stability_bonus,
                'responsiveness': 1.0 - responsiveness_penalty,
                'suitable_for_strategy': self._is_suitable_for_strategy(tf, strategy)
            }

        return performance

    def _select_optimal_timeframes(self, performance: Dict[str, Any]) -> Dict[str, List[str]]:
        """Select optimal time frames based on performance"""
        # Sort by performance score
        sorted_timeframes = sorted(performance.items(),
                                 key=lambda x: x[1]['score'],
                                 reverse=True)

        optimal = {
            'primary': [sorted_timeframes[0][0]] if sorted_timeframes else [],
            'secondary': [sorted_timeframes[1][0]] if len(sorted_timeframes) > 1 else [],
            'confirmation': [sorted_timeframes[-1][0]] if len(sorted_timeframes) > 2 else []
        }

        return optimal

    def _generate_timeframe_recommendations(self, characteristics: Dict[str, Any],
                                          optimal_timeframes: Dict[str, List[str]],
                                          strategy: TradingStrategy) -> List[str]:
        """Generate time frame recommendations"""
        recommendations = []

        volume = characteristics.get('average_volume', 0)
        volatility = characteristics.get('price_volatility', 0)

        if volume < 100000:
            recommendations.append("Consider longer time frames due to low volume")

        if volatility > 0.05:
            recommendations.append("Use longer time frames for confirmation due to high volatility")

        if strategy in [TradingStrategy.SCALPING, TradingStrategy.DAY_TRADING]:
            recommendations.append("Ensure sufficient intraday data availability")

        if not optimal_timeframes.get('primary'):
            recommendations.append("Unable to determine optimal primary time frame")

        return recommendations

    def _shift_timeframes_higher(self, timeframes: List[TimeFrame]) -> List[TimeFrame]:
        """Shift time frames to higher (longer) periods"""
        timeframe_hierarchy = [
            TimeFrame.MINUTE_1, TimeFrame.MINUTE_5, TimeFrame.MINUTE_15,
            TimeFrame.MINUTE_30, TimeFrame.HOUR_1, TimeFrame.HOUR_4,
            TimeFrame.DAY_1, TimeFrame.WEEK_1, TimeFrame.MONTH_1, TimeFrame.YEAR_1
        ]

        shifted = []
        for tf in timeframes:
            current_index = timeframe_hierarchy.index(tf) if tf in timeframe_hierarchy else 0
            new_index = min(current_index + 1, len(timeframe_hierarchy) - 1)
            shifted.append(timeframe_hierarchy[new_index])

        return shifted

    def _shift_timeframes_lower(self, timeframes: List[TimeFrame]) -> List[TimeFrame]:
        """Shift time frames to lower (shorter) periods"""
        timeframe_hierarchy = [
            TimeFrame.MINUTE_1, TimeFrame.MINUTE_5, TimeFrame.MINUTE_15,
            TimeFrame.MINUTE_30, TimeFrame.HOUR_1, TimeFrame.HOUR_4,
            TimeFrame.DAY_1, TimeFrame.WEEK_1, TimeFrame.MONTH_1, TimeFrame.YEAR_1
        ]

        shifted = []
        for tf in timeframes:
            current_index = timeframe_hierarchy.index(tf) if tf in timeframe_hierarchy else 0
            new_index = max(current_index - 1, 0)
            shifted.append(timeframe_hierarchy[new_index])

        return shifted

    def _calculate_minimum_data_points(self, timeframe: TimeFrame) -> int:
        """Calculate minimum data points needed"""
        # Minimum for technical indicators to work
        return 50

    def _calculate_preferred_data_points(self, timeframe: TimeFrame, strategy: TradingStrategy) -> int:
        """Calculate preferred data points"""
        base_map = {
            TimeFrame.MINUTE_1: 1440,
            TimeFrame.MINUTE_5: 2016,
            TimeFrame.DAY_1: 252,
            TimeFrame.WEEK_1: 104,
            TimeFrame.MONTH_1: 36
        }

        return base_map.get(timeframe, 252)

    def _get_update_frequency(self, timeframe: TimeFrame) -> str:
        """Get required update frequency"""
        frequency_map = {
            TimeFrame.MINUTE_1: "real_time",
            TimeFrame.MINUTE_5: "real_time",
            TimeFrame.HOUR_1: "hourly",
            TimeFrame.DAY_1: "daily",
            TimeFrame.WEEK_1: "weekly"
        }

        return frequency_map.get(timeframe, "daily")

    def _estimate_storage_size(self, timeframe: TimeFrame, data_points: int) -> float:
        """Estimate storage size in MB"""
        # Rough estimate: 100 bytes per OHLCV record
        bytes_per_record = 100
        total_bytes = data_points * bytes_per_record
        return total_bytes / (1024 * 1024)  # Convert to MB

    def _calculate_total_lookback(self, timeframes: List[TimeFrame]) -> int:
        """Calculate total lookback period needed"""
        lookback_map = {
            TimeFrame.MINUTE_1: 7,
            TimeFrame.MINUTE_5: 30,
            TimeFrame.HOUR_1: 90,
            TimeFrame.DAY_1: 365,
            TimeFrame.WEEK_1: 730,
            TimeFrame.MONTH_1: 1825
        }

        max_lookback = 0
        for tf in timeframes:
            tf_lookback = lookback_map.get(tf, 365)
            max_lookback = max(max_lookback, tf_lookback)

        return max_lookback

    def _get_default_optimization_result(self, symbol: str, strategy: TradingStrategy) -> Dict[str, Any]:
        """Get default optimization result when insufficient data"""
        return {
            'symbol': symbol,
            'strategy': strategy.value,
            'optimal_timeframes': self._get_default_timeframes(),
            'performance_metrics': {},
            'recommendations': ["Insufficient data for optimization"]
        }

    def _get_timeframe_stability_bonus(self, timeframe: TimeFrame) -> float:
        """Get stability bonus for time frame"""
        stability_map = {
            TimeFrame.MINUTE_1: 0.1,
            TimeFrame.MINUTE_5: 0.2,
            TimeFrame.HOUR_1: 0.5,
            TimeFrame.DAY_1: 0.8,
            TimeFrame.WEEK_1: 0.9
        }
        return stability_map.get(timeframe, 0.5)

    def _get_timeframe_responsiveness_penalty(self, timeframe: TimeFrame) -> float:
        """Get responsiveness penalty for time frame"""
        penalty_map = {
            TimeFrame.MINUTE_1: 0.1,
            TimeFrame.MINUTE_5: 0.2,
            TimeFrame.HOUR_1: 0.4,
            TimeFrame.DAY_1: 0.6,
            TimeFrame.WEEK_1: 0.8
        }
        return penalty_map.get(timeframe, 0.3)

    def _is_suitable_for_strategy(self, timeframe: TimeFrame, strategy: TradingStrategy) -> bool:
        """Check if time frame is suitable for strategy"""
        strategy_timeframes = self.strategy_timeframes.get(strategy, {})
        all_suitable_timeframes = []

        for category in ['primary', 'secondary', 'confirmation']:
            all_suitable_timeframes.extend(strategy_timeframes.get(category, []))

        return timeframe in all_suitable_timeframes