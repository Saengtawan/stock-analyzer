"""
Technical Analysis Engine
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from .indicators import TechnicalIndicators, TrendAnalysis

try:
    from ...data_quality.data_validator import DataQualityValidator
    from ...timeframe.timeframe_manager import TimeFrameManager, TradingStrategy
    from ...analysis.advanced.advanced_models import AdvancedTechnicalAnalyzer
    from ...adaptability.market_regime_detector import MarketRegimeDetector
    from ...risk.enhanced_risk_manager import EnhancedRiskManager
    from ...signal_processing.signal_filter import SignalNoiseFilter
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
    from data_quality.data_validator import DataQualityValidator
    from timeframe.timeframe_manager import TimeFrameManager, TradingStrategy
    from analysis.advanced.advanced_models import AdvancedTechnicalAnalyzer
    from adaptability.market_regime_detector import MarketRegimeDetector
    from risk.enhanced_risk_manager import EnhancedRiskManager
    from signal_processing.signal_filter import SignalNoiseFilter

class TechnicalAnalyzer:
    """Enhanced technical analysis engine with advanced modules"""

    def __init__(self, price_data: pd.DataFrame, trading_strategy: str = "swing_trading"):
        """
        Initialize enhanced technical analyzer

        Args:
            price_data: DataFrame with OHLCV data
            trading_strategy: Trading strategy for timeframe optimization
        """
        # Extract symbol first
        self.symbol = price_data.get('symbol', [None])[0] if 'symbol' in price_data.columns else 'UNKNOWN'

        # Data quality validation
        self.data_validator = DataQualityValidator()
        try:
            validated_data = self.data_validator.validate_price_data(price_data, self.symbol)
            self.price_data = validated_data['cleaned_data']
            self.data_quality_score = validated_data['quality_score']
        except Exception:
            # Fallback if validation fails
            self.price_data = price_data.copy()
            self.data_quality_score = 0.8

        # Initialize core components
        self.indicators = TechnicalIndicators(self.price_data)
        self.trend_analysis = TrendAnalysis(self.price_data)

        # Initialize enhanced modules
        self.timeframe_manager = TimeFrameManager()
        self.advanced_analyzer = AdvancedTechnicalAnalyzer(self.price_data)  # Pass DataFrame correctly
        self.regime_detector = MarketRegimeDetector(self.price_data)
        self.risk_manager = EnhancedRiskManager()
        self.signal_filter = SignalNoiseFilter()

        # Set trading strategy
        try:
            self.trading_strategy = TradingStrategy[trading_strategy.upper()]
        except KeyError:
            self.trading_strategy = TradingStrategy.SWING_TRADING
            logger.warning(f"Unknown trading strategy: {trading_strategy}, defaulting to swing_trading")

    def analyze(self) -> Dict[str, Any]:
        """
        Perform comprehensive enhanced technical analysis

        Returns:
            Dictionary containing all technical analysis results
        """
        logger.info(f"Starting enhanced technical analysis for {self.symbol}")

        try:
            # Data quality assessment
            quality_report = {
                'data_quality_score': self.data_quality_score,
                'data_completeness': len(self.price_data) / len(self.price_data.dropna()) if len(self.price_data) > 0 else 0
            }

            # Optimal timeframe analysis
            optimal_timeframes = self.timeframe_manager.get_optimal_timeframes(self.trading_strategy)

            # Get all indicators
            all_indicators = self.indicators.get_all_indicators()
            latest_values = self.indicators.get_latest_values()

            # Advanced technical analysis
            advanced_analysis = self.advanced_analyzer.analyze(self.price_data)

            # Market regime detection
            current_regime = self.regime_detector.detect_current_regime(self.price_data)
            regime_history = self.regime_detector.get_regime_history()

            # Enhanced signals with filtering
            raw_signals = self._generate_signals(latest_values)
            filtered_signals = self._apply_signal_filtering(raw_signals, advanced_analysis)

            # Enhanced risk assessment
            portfolio_data = self._prepare_portfolio_data(latest_values)
            risk_metrics = self.risk_manager.calculate_risk_metrics(portfolio_data)

            # Trend analysis
            trend_info = self.trend_analysis.identify_trend()
            swing_points = self.trend_analysis.find_swing_points()

            # Calculate enhanced technical score
            technical_score = self._calculate_enhanced_technical_score(
                latest_values, filtered_signals, advanced_analysis, current_regime
            )

            # Entry/Exit points with regime consideration
            entry_exit = self._calculate_adaptive_entry_exit_points(
                latest_values, current_regime, risk_metrics
            )

            return {
                'symbol': self.symbol,
                'analysis_date': datetime.now().isoformat(),
                'last_price': latest_values['current_price'],

                # Data quality
                'data_quality': quality_report,

                # Timeframe optimization
                'optimal_timeframes': optimal_timeframes,
                'current_strategy': self.trading_strategy.value,

                # Core technical data
                'indicators': latest_values,
                'trend_analysis': trend_info,
                'swing_points': swing_points,

                # Advanced analysis
                'advanced_analysis': advanced_analysis,
                'market_regime': {
                    'current': current_regime,
                    'history': regime_history
                },

                # Enhanced signals
                'raw_signals': raw_signals,
                'filtered_signals': filtered_signals,
                'signal_quality': self._assess_signal_quality(filtered_signals),

                # Enhanced scoring and risk
                'technical_score': technical_score,
                'risk_metrics': risk_metrics,
                'entry_exit_points': entry_exit,

                # Recommendations
                'recommendation': self._get_enhanced_recommendation(technical_score, current_regime),
                'key_signals': self._identify_key_signals(filtered_signals),
                'support_resistance': latest_values.get('support_resistance', {}),
                'target_levels': self._calculate_target_levels(latest_values),

                # Adaptability insights
                'adaptability_insights': self._generate_adaptability_insights(current_regime, advanced_analysis)
            }

        except Exception as e:
            logger.error(f"Enhanced technical analysis failed for {self.symbol}: {e}")
            return {
                'symbol': self.symbol,
                'error': str(e),
                'technical_score': {'total_score': 0},
                'data_quality': {'data_quality_score': 0},
                'recommendation': 'HOLD - Analysis Error'
            }

    def _apply_signal_filtering(self, raw_signals: Dict[str, Any], advanced_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Apply signal filtering to reduce noise"""
        try:
            # Convert signals to time series for filtering
            signal_strengths = []
            signal_directions = []

            for signal_name, signal_data in raw_signals.items():
                if isinstance(signal_data, dict):
                    # Convert signal to numerical values
                    direction = 1 if signal_data.get('signal') == 'BUY' else -1 if signal_data.get('signal') == 'SELL' else 0
                    strength_map = {'Strong': 3, 'Moderate': 2, 'Weak': 1}
                    strength = strength_map.get(signal_data.get('strength', 'Weak'), 1)

                    signal_strengths.append(strength)
                    signal_directions.append(direction)

            if signal_strengths and signal_directions:
                # Apply signal filtering
                filtered_strengths = self.signal_filter.apply_ensemble_filtering(
                    np.array(signal_strengths), window_size=min(5, len(signal_strengths))
                )
                filtered_directions = self.signal_filter.apply_ensemble_filtering(
                    np.array(signal_directions), window_size=min(5, len(signal_directions))
                )

                # Convert back to signal format
                filtered_signals = raw_signals.copy()
                signal_names = list(raw_signals.keys())

                for i, (strength, direction) in enumerate(zip(filtered_strengths, filtered_directions)):
                    if i < len(signal_names):
                        signal_name = signal_names[i]
                        if isinstance(filtered_signals[signal_name], dict):
                            # Update with filtered values
                            filtered_signals[signal_name]['filtered_strength'] = float(strength)
                            filtered_signals[signal_name]['filtered_direction'] = float(direction)
                            filtered_signals[signal_name]['noise_ratio'] = abs(strength - signal_strengths[i]) / max(signal_strengths[i], 0.1)

                return filtered_signals
            else:
                return raw_signals

        except Exception as e:
            logger.warning(f"Signal filtering failed: {e}")
            return raw_signals

    def _prepare_portfolio_data(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare portfolio data for risk analysis"""
        return {
            'returns': self.price_data['close'].pct_change().dropna().tolist() if 'close' in self.price_data.columns else [],
            'prices': self.price_data['close'].tolist() if 'close' in self.price_data.columns else [],
            'volumes': self.price_data['volume'].tolist() if 'volume' in self.price_data.columns else [],
            'current_price': indicators.get('current_price', 0),
            'volatility': indicators.get('atr', 0)
        }

    def _calculate_enhanced_technical_score(self, indicators: Dict[str, Any], signals: Dict[str, Any],
                                          advanced_analysis: Dict[str, Any], regime: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate enhanced technical score with regime and advanced analysis"""
        base_score = self._calculate_technical_score(indicators, signals)

        # Regime adjustment
        regime_multiplier = 1.0
        current_regime = regime.get('regime', 'NORMAL')

        if current_regime == 'BULL':
            regime_multiplier = 1.2
        elif current_regime == 'BEAR':
            regime_multiplier = 0.8
        elif current_regime == 'HIGH_VOLATILITY':
            regime_multiplier = 0.9

        # Advanced analysis boost
        pattern_score = advanced_analysis.get('pattern_strength', 0) * 0.5
        sentiment_score = advanced_analysis.get('sentiment_score', 0) * 0.3

        enhanced_score = (base_score['total_score'] * regime_multiplier) + pattern_score + sentiment_score
        enhanced_score = min(enhanced_score, 10.0)  # Cap at 10

        return {
            'total_score': enhanced_score,
            'base_score': base_score['total_score'],
            'regime_adjustment': regime_multiplier,
            'pattern_boost': pattern_score,
            'sentiment_boost': sentiment_score,
            'max_score': 10.0,
            'component_scores': base_score['component_scores'],
            'rating': self._get_score_rating(enhanced_score)
        }

    def _calculate_adaptive_entry_exit_points(self, indicators: Dict[str, Any],
                                            regime: Dict[str, Any], risk_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate entry/exit points adapted to market regime"""
        base_points = self._calculate_entry_exit_points(indicators)

        # Adjust based on regime
        current_regime = regime.get('regime', 'NORMAL')
        volatility = risk_metrics.get('portfolio_volatility', 0.02)

        # Regime-based adjustments
        if current_regime == 'HIGH_VOLATILITY':
            # Wider stops in high volatility
            multiplier = 1.5
        elif current_regime == 'LOW_VOLATILITY':
            # Tighter stops in low volatility
            multiplier = 0.8
        else:
            multiplier = 1.0

        # Apply adjustments
        current_price = indicators['current_price']
        atr = indicators.get('atr', current_price * 0.02)

        return {
            **base_points,
            'regime_adjusted_stop_long': base_points['long_stop_loss'] - (atr * multiplier * 0.5),
            'regime_adjusted_stop_short': base_points['short_stop_loss'] + (atr * multiplier * 0.5),
            'volatility_adjustment': multiplier,
            'current_regime': current_regime,
            'recommended_position_size': self._calculate_position_size(risk_metrics, volatility)
        }

    def _calculate_position_size(self, risk_metrics: Dict[str, Any], volatility: float) -> Dict[str, Any]:
        """Calculate recommended position size based on risk"""
        max_risk_per_trade = 0.02  # 2% max risk
        account_size = 100000  # Default account size

        # Kelly criterion-based sizing
        kelly_fraction = risk_metrics.get('kelly_fraction', 0.1)
        volatility_adjusted_size = min(kelly_fraction, max_risk_per_trade / max(volatility, 0.001))

        return {
            'max_position_percentage': min(volatility_adjusted_size * 100, 10.0),  # Max 10%
            'recommended_units': int(account_size * volatility_adjusted_size),
            'risk_per_trade': max_risk_per_trade * 100,
            'volatility_factor': volatility
        }

    def _assess_signal_quality(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the quality of filtered signals"""
        if not signals:
            return {'overall_quality': 0, 'confidence': 0}

        total_signals = 0
        strong_signals = 0
        noise_ratio_sum = 0

        for signal_data in signals.values():
            if isinstance(signal_data, dict):
                total_signals += 1
                if signal_data.get('strength') == 'Strong':
                    strong_signals += 1
                noise_ratio_sum += signal_data.get('noise_ratio', 0.5)

        if total_signals > 0:
            quality_score = (strong_signals / total_signals) * (1 - (noise_ratio_sum / total_signals))
            confidence = min(quality_score * 100, 100)
        else:
            quality_score = 0
            confidence = 0

        return {
            'overall_quality': round(quality_score, 3),
            'confidence': round(confidence, 1),
            'strong_signals_ratio': round(strong_signals / max(total_signals, 1), 3),
            'average_noise_ratio': round(noise_ratio_sum / max(total_signals, 1), 3)
        }

    def _get_enhanced_recommendation(self, technical_score: Dict[str, Any], regime: Dict[str, Any]) -> str:
        """Get enhanced trading recommendation with regime consideration"""
        score = technical_score['total_score']
        current_regime = regime.get('regime', 'NORMAL')

        # Base recommendation
        if score >= 8.5:
            base_rec = "Strong Buy"
        elif score >= 7.0:
            base_rec = "Buy"
        elif score >= 5.5:
            base_rec = "Hold"
        elif score >= 4.0:
            base_rec = "Sell"
        else:
            base_rec = "Strong Sell"

        # Regime modifier
        if current_regime == 'HIGH_VOLATILITY':
            modifier = " (Caution: High Volatility)"
        elif current_regime == 'BEAR' and 'Buy' in base_rec:
            modifier = " (Bear Market Caution)"
        elif current_regime == 'BULL' and 'Sell' in base_rec:
            modifier = " (Bull Market - Consider Hold)"
        else:
            modifier = ""

        return base_rec + modifier

    def _generate_adaptability_insights(self, regime: Dict[str, Any], advanced_analysis: Dict[str, Any]) -> List[str]:
        """Generate insights about market adaptability"""
        insights = []

        current_regime = regime.get('regime', 'NORMAL')
        regime_confidence = regime.get('confidence', 0)

        # Regime insights
        if regime_confidence > 0.8:
            insights.append(f"High confidence {current_regime.lower()} market regime detected")
        elif regime_confidence < 0.4:
            insights.append("Market regime unclear - use adaptive strategies")

        # Volatility insights
        volatility_trend = regime.get('volatility_trend', 'stable')
        if volatility_trend == 'increasing':
            insights.append("Volatility increasing - consider tighter risk management")
        elif volatility_trend == 'decreasing':
            insights.append("Volatility decreasing - opportunity for larger positions")

        # Pattern insights
        pattern_strength = advanced_analysis.get('pattern_strength', 0)
        if pattern_strength > 0.7:
            insights.append("Strong technical patterns detected - high probability setups")
        elif pattern_strength < 0.3:
            insights.append("Weak patterns - focus on risk management over entries")

        return insights

    def _generate_signals(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate trading signals from indicators"""
        signals = {}

        # RSI Signals
        rsi = indicators.get('rsi')
        if rsi:
            if rsi < 30:
                signals['rsi_signal'] = {'signal': 'BUY', 'strength': 'Strong', 'reason': f'RSI oversold at {rsi:.1f}'}
            elif rsi > 70:
                signals['rsi_signal'] = {'signal': 'SELL', 'strength': 'Strong', 'reason': f'RSI overbought at {rsi:.1f}'}
            elif rsi < 40:
                signals['rsi_signal'] = {'signal': 'BUY', 'strength': 'Moderate', 'reason': f'RSI approaching oversold at {rsi:.1f}'}
            elif rsi > 60:
                signals['rsi_signal'] = {'signal': 'SELL', 'strength': 'Moderate', 'reason': f'RSI approaching overbought at {rsi:.1f}'}
            else:
                signals['rsi_signal'] = {'signal': 'NEUTRAL', 'strength': 'Weak', 'reason': f'RSI neutral at {rsi:.1f}'}

        # MACD Signals
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_histogram = indicators.get('macd_histogram')

        if all(x is not None for x in [macd_line, macd_signal, macd_histogram]):
            if macd_line > macd_signal and macd_line > 0 and macd_histogram > 0:
                signals['macd_signal'] = {'signal': 'BUY', 'strength': 'Strong', 'reason': 'MACD bullish crossover above zero'}
            elif macd_line > macd_signal and macd_histogram > 0:
                signals['macd_signal'] = {'signal': 'BUY', 'strength': 'Moderate', 'reason': 'MACD bullish crossover'}
            elif macd_line > macd_signal:
                signals['macd_signal'] = {'signal': 'BUY', 'strength': 'Weak', 'reason': 'MACD bullish divergence'}
            elif macd_line < macd_signal and macd_line < 0 and macd_histogram < 0:
                signals['macd_signal'] = {'signal': 'SELL', 'strength': 'Strong', 'reason': 'MACD bearish crossover below zero'}
            elif macd_line < macd_signal and macd_histogram < 0:
                signals['macd_signal'] = {'signal': 'SELL', 'strength': 'Moderate', 'reason': 'MACD bearish crossover'}
            elif macd_line < macd_signal:
                signals['macd_signal'] = {'signal': 'SELL', 'strength': 'Weak', 'reason': 'MACD bearish divergence'}
            else:
                signals['macd_signal'] = {'signal': 'NEUTRAL', 'strength': 'Weak', 'reason': 'MACD neutral'}

        # Moving Average Signals
        current_price = indicators['current_price']
        ema_20 = indicators.get('sma_20')  # Using SMA_20 as proxy
        ema_50 = indicators.get('sma_50')

        if all(x is not None for x in [current_price, ema_20, ema_50]):
            if current_price > ema_20 > ema_50:
                signals['ma_signal'] = {'signal': 'BUY', 'strength': 'Strong', 'reason': 'Price above all moving averages'}
            elif current_price > ema_20:
                signals['ma_signal'] = {'signal': 'BUY', 'strength': 'Moderate', 'reason': 'Price above short-term MA'}
            elif current_price < ema_20 < ema_50:
                signals['ma_signal'] = {'signal': 'SELL', 'strength': 'Strong', 'reason': 'Price below all moving averages'}
            elif current_price < ema_20:
                signals['ma_signal'] = {'signal': 'SELL', 'strength': 'Moderate', 'reason': 'Price below short-term MA'}
            else:
                signals['ma_signal'] = {'signal': 'NEUTRAL', 'strength': 'Weak', 'reason': 'Mixed MA signals'}

        # Bollinger Bands Signals
        bb_upper = indicators.get('bb_upper')
        bb_lower = indicators.get('bb_lower')
        bb_middle = indicators.get('bb_middle')

        if all(x is not None for x in [current_price, bb_upper, bb_lower, bb_middle]):
            if current_price <= bb_lower:
                signals['bb_signal'] = {'signal': 'BUY', 'strength': 'Strong', 'reason': 'Price at lower Bollinger Band'}
            elif current_price >= bb_upper:
                signals['bb_signal'] = {'signal': 'SELL', 'strength': 'Strong', 'reason': 'Price at upper Bollinger Band'}
            elif current_price < bb_middle:
                signals['bb_signal'] = {'signal': 'BUY', 'strength': 'Weak', 'reason': 'Price below BB middle'}
            elif current_price > bb_middle:
                signals['bb_signal'] = {'signal': 'SELL', 'strength': 'Weak', 'reason': 'Price above BB middle'}
            else:
                signals['bb_signal'] = {'signal': 'NEUTRAL', 'strength': 'Weak', 'reason': 'Price at BB middle'}

        # Volume Signal
        current_volume = indicators.get('current_volume')
        volume_sma = indicators.get('volume_sma')

        if current_volume and volume_sma:
            volume_ratio = current_volume / volume_sma
            if volume_ratio > 1.5:
                signals['volume_signal'] = {'signal': 'BULLISH', 'strength': 'Strong', 'reason': f'High volume ({volume_ratio:.1f}x average)'}
            elif volume_ratio > 1.2:
                signals['volume_signal'] = {'signal': 'BULLISH', 'strength': 'Moderate', 'reason': f'Above average volume ({volume_ratio:.1f}x)'}
            elif volume_ratio < 0.5:
                signals['volume_signal'] = {'signal': 'BEARISH', 'strength': 'Moderate', 'reason': f'Low volume ({volume_ratio:.1f}x average)'}
            else:
                signals['volume_signal'] = {'signal': 'NEUTRAL', 'strength': 'Weak', 'reason': 'Normal volume'}

        # Support/Resistance Signals
        support_resistance = indicators.get('support_resistance', {})
        if support_resistance:
            s1 = support_resistance.get('support_1')
            r1 = support_resistance.get('resistance_1')

            if s1 and current_price <= s1 * 1.01:  # Within 1% of support
                signals['sr_signal'] = {'signal': 'BUY', 'strength': 'Strong', 'reason': f'Price near support at {s1:.2f}'}
            elif r1 and current_price >= r1 * 0.99:  # Within 1% of resistance
                signals['sr_signal'] = {'signal': 'SELL', 'strength': 'Strong', 'reason': f'Price near resistance at {r1:.2f}'}
            else:
                signals['sr_signal'] = {'signal': 'NEUTRAL', 'strength': 'Weak', 'reason': 'Price between support and resistance'}

        return signals

    def _calculate_technical_score(self, indicators: Dict[str, Any], signals: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate technical score (0-10)"""
        scores = {}
        total_score = 0
        max_score = 10

        # RSI Score (2 points)
        rsi_score = self._score_rsi(indicators.get('rsi'), signals.get('rsi_signal'))
        scores['rsi'] = rsi_score
        total_score += rsi_score

        # MACD Score (2 points)
        macd_score = self._score_macd(signals.get('macd_signal'))
        scores['macd'] = macd_score
        total_score += macd_score

        # Moving Average Score (2 points)
        ma_score = self._score_moving_averages(signals.get('ma_signal'))
        scores['moving_averages'] = ma_score
        total_score += ma_score

        # Support/Resistance Score (2 points)
        sr_score = self._score_support_resistance(signals.get('sr_signal'))
        scores['support_resistance'] = sr_score
        total_score += sr_score

        # Volume Score (2 points)
        volume_score = self._score_volume(signals.get('volume_signal'))
        scores['volume'] = volume_score
        total_score += volume_score

        return {
            'total_score': min(total_score, max_score),
            'max_score': max_score,
            'component_scores': scores,
            'rating': self._get_score_rating(total_score)
        }

    def _score_rsi(self, rsi: Optional[float], rsi_signal: Optional[Dict]) -> float:
        """Score RSI indicator (0-2 points)"""
        if not rsi or not rsi_signal:
            return 1.0  # Neutral score if no data

        signal = rsi_signal.get('signal')
        strength = rsi_signal.get('strength')

        if signal == 'BUY':
            if strength == 'Strong':
                return 2.0
            elif strength == 'Moderate':
                return 1.5
            else:
                return 1.2
        elif signal == 'SELL':
            if strength == 'Strong':
                return 0.0
            elif strength == 'Moderate':
                return 0.5
            else:
                return 0.8
        else:
            return 1.0

    def _score_macd(self, macd_signal: Optional[Dict]) -> float:
        """Score MACD indicator (0-2 points)"""
        if not macd_signal:
            return 1.0

        signal = macd_signal.get('signal')
        strength = macd_signal.get('strength')

        if signal == 'BUY':
            if strength == 'Strong':
                return 2.0
            elif strength == 'Moderate':
                return 1.5
            else:
                return 1.2
        elif signal == 'SELL':
            if strength == 'Strong':
                return 0.0
            elif strength == 'Moderate':
                return 0.5
            else:
                return 0.8
        else:
            return 1.0

    def _score_moving_averages(self, ma_signal: Optional[Dict]) -> float:
        """Score moving averages (0-2 points)"""
        if not ma_signal:
            return 1.0

        signal = ma_signal.get('signal')
        strength = ma_signal.get('strength')

        if signal == 'BUY':
            if strength == 'Strong':
                return 2.0
            elif strength == 'Moderate':
                return 1.5
            else:
                return 1.2
        elif signal == 'SELL':
            if strength == 'Strong':
                return 0.0
            elif strength == 'Moderate':
                return 0.5
            else:
                return 0.8
        else:
            return 1.0

    def _score_support_resistance(self, sr_signal: Optional[Dict]) -> float:
        """Score support/resistance levels (0-2 points)"""
        if not sr_signal:
            return 1.0

        signal = sr_signal.get('signal')
        strength = sr_signal.get('strength')

        if signal == 'BUY':
            if strength == 'Strong':
                return 2.0
            else:
                return 1.5
        elif signal == 'SELL':
            if strength == 'Strong':
                return 0.0
            else:
                return 0.5
        else:
            return 1.0

    def _score_volume(self, volume_signal: Optional[Dict]) -> float:
        """Score volume confirmation (0-2 points)"""
        if not volume_signal:
            return 1.0

        signal = volume_signal.get('signal')
        strength = volume_signal.get('strength')

        if signal == 'BULLISH':
            if strength == 'Strong':
                return 2.0
            elif strength == 'Moderate':
                return 1.5
            else:
                return 1.2
        elif signal == 'BEARISH':
            if strength == 'Strong':
                return 0.0
            elif strength == 'Moderate':
                return 0.5
            else:
                return 0.8
        else:
            return 1.0

    def _get_score_rating(self, score: float) -> str:
        """Convert score to rating"""
        if score >= 8.5:
            return "Very Bullish"
        elif score >= 7.0:
            return "Bullish"
        elif score >= 5.0:
            return "Neutral"
        elif score >= 3.0:
            return "Bearish"
        else:
            return "Very Bearish"

    def _detect_market_regime(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Detect current market regime (legacy method - use regime_detector for enhanced)"""
        atr = indicators.get('atr')
        current_price = indicators['current_price']

        # Volatility regime
        if atr and current_price:
            volatility_pct = (atr / current_price) * 100
            if volatility_pct > 3:
                volatility_regime = "High Volatility"
            elif volatility_pct > 1.5:
                volatility_regime = "Normal Volatility"
            else:
                volatility_regime = "Low Volatility"
        else:
            volatility_regime = "Unknown"

        # Trend regime (from moving averages)
        ema_20 = indicators.get('sma_20')
        ema_50 = indicators.get('sma_50')

        if ema_20 and ema_50:
            if current_price > ema_20 > ema_50:
                trend_regime = "Trending Up"
            elif current_price < ema_20 < ema_50:
                trend_regime = "Trending Down"
            else:
                trend_regime = "Sideways/Choppy"
        else:
            trend_regime = "Unknown"

        return {
            'volatility_regime': volatility_regime,
            'trend_regime': trend_regime,
            'volatility_pct': volatility_pct if atr and current_price else None
        }

    def _calculate_entry_exit_points(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate entry and exit points"""
        current_price = indicators['current_price']
        atr = indicators.get('atr', current_price * 0.02)  # Default 2% if no ATR
        support_resistance = indicators.get('support_resistance', {})

        # Entry points
        entry_long = support_resistance.get('support_1', current_price * 0.98)
        entry_short = support_resistance.get('resistance_1', current_price * 1.02)

        # Stop losses
        stop_loss_long = entry_long - (atr * 2)
        stop_loss_short = entry_short + (atr * 2)

        # Take profit levels
        take_profit_long_1 = support_resistance.get('resistance_1', entry_long + (atr * 2))
        take_profit_long_2 = support_resistance.get('resistance_2', entry_long + (atr * 4))

        take_profit_short_1 = support_resistance.get('support_1', entry_short - (atr * 2))
        take_profit_short_2 = support_resistance.get('support_2', entry_short - (atr * 4))

        return {
            'long_entry': entry_long,
            'long_stop_loss': stop_loss_long,
            'long_take_profit_1': take_profit_long_1,
            'long_take_profit_2': take_profit_long_2,
            'short_entry': entry_short,
            'short_stop_loss': stop_loss_short,
            'short_take_profit_1': take_profit_short_1,
            'short_take_profit_2': take_profit_short_2,
            'atr_used': atr
        }

    def _assess_technical_risk(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Assess technical risk factors"""
        risk_factors = {}

        # Volatility risk
        atr = indicators.get('atr')
        current_price = indicators['current_price']

        if atr and current_price:
            volatility_pct = (atr / current_price) * 100
            if volatility_pct > 5:
                risk_factors['volatility_risk'] = "Very High"
            elif volatility_pct > 3:
                risk_factors['volatility_risk'] = "High"
            elif volatility_pct > 1.5:
                risk_factors['volatility_risk'] = "Moderate"
            else:
                risk_factors['volatility_risk'] = "Low"
        else:
            risk_factors['volatility_risk'] = "Unknown"

        # RSI extremes risk
        rsi = indicators.get('rsi')
        if rsi:
            if rsi > 80 or rsi < 20:
                risk_factors['rsi_extreme_risk'] = "High"
            elif rsi > 70 or rsi < 30:
                risk_factors['rsi_extreme_risk'] = "Moderate"
            else:
                risk_factors['rsi_extreme_risk'] = "Low"

        # Support/resistance proximity risk
        support_resistance = indicators.get('support_resistance', {})
        s1 = support_resistance.get('support_1')
        r1 = support_resistance.get('resistance_1')

        proximity_risk = "Low"
        if s1 and current_price <= s1 * 1.02:
            proximity_risk = "High"  # Near support
        elif r1 and current_price >= r1 * 0.98:
            proximity_risk = "High"  # Near resistance

        risk_factors['support_resistance_risk'] = proximity_risk

        return risk_factors

    def _get_recommendation(self, technical_score: Dict[str, Any]) -> str:
        """Get trading recommendation"""
        score = technical_score['total_score']

        if score >= 8.5:
            return "Strong Buy"
        elif score >= 7.0:
            return "Buy"
        elif score >= 5.5:
            return "Hold"
        elif score >= 4.0:
            return "Sell"
        else:
            return "Strong Sell"

    def _identify_key_signals(self, signals: Dict[str, Any]) -> List[str]:
        """Identify the most important signals"""
        key_signals = []

        # Look for strong signals
        for signal_name, signal_data in signals.items():
            if isinstance(signal_data, dict):
                strength = signal_data.get('strength')
                reason = signal_data.get('reason')

                if strength == 'Strong' and reason:
                    key_signals.append(reason)

        return key_signals

    def _calculate_target_levels(self, indicators: Dict[str, Any]) -> Dict[str, float]:
        """Calculate price target levels"""
        current_price = indicators['current_price']
        support_resistance = indicators.get('support_resistance', {})
        fibonacci = indicators.get('fibonacci', {})

        targets = {}

        # Support/Resistance targets
        if 'resistance_1' in support_resistance:
            targets['resistance_1'] = support_resistance['resistance_1']
        if 'resistance_2' in support_resistance:
            targets['resistance_2'] = support_resistance['resistance_2']
        if 'support_1' in support_resistance:
            targets['support_1'] = support_resistance['support_1']
        if 'support_2' in support_resistance:
            targets['support_2'] = support_resistance['support_2']

        # Fibonacci targets
        if 'fib_61.8' in fibonacci:
            targets['fib_618'] = fibonacci['fib_61.8']
        if 'fib_38.2' in fibonacci:
            targets['fib_382'] = fibonacci['fib_38.2']

        return targets

    def calculate_basic_indicators(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate basic technical indicators for fast screening

        Args:
            price_data: Price data DataFrame

        Returns:
            Basic technical indicators
        """
        try:
            if price_data.empty or len(price_data) < 20:
                logger.warning(f"Insufficient data for basic indicators calculation")
                return {}

            # Get basic OHLCV data
            close = price_data['close']
            volume = price_data['volume'] if 'volume' in price_data.columns else None

            # Basic moving averages
            sma_20 = close.rolling(window=20).mean().iloc[-1] if len(close) >= 20 else None
            sma_50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None

            # RSI calculation
            rsi = self._calculate_basic_rsi(close)

            # Volume trend (simple)
            volume_trend = 0
            if volume is not None and len(volume) >= 10:
                recent_vol = volume.tail(5).mean()
                prev_vol = volume.tail(15).head(10).mean()
                if recent_vol > prev_vol * 1.1:
                    volume_trend = 1
                elif recent_vol < prev_vol * 0.9:
                    volume_trend = -1

            # Support/Resistance (basic)
            support_resistance = self._calculate_basic_support_resistance(close)

            return {
                'rsi': rsi,
                'sma_20': sma_20,
                'sma_50': sma_50,
                'volume_trend': volume_trend,
                'support_1': support_resistance.get('support_1'),
                'resistance_1': support_resistance.get('resistance_1'),
                'last_price': close.iloc[-1] if not close.empty else None
            }

        except Exception as e:
            logger.error(f"Basic indicators calculation failed: {e}")
            return {}

    def _calculate_basic_rsi(self, close: pd.Series, period: int = 14) -> Optional[float]:
        """Calculate basic RSI"""
        try:
            if len(close) < period + 1:
                return None

            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            return rsi.iloc[-1] if not rsi.empty else None

        except Exception:
            return None

    def _calculate_basic_support_resistance(self, close: pd.Series) -> Dict[str, Optional[float]]:
        """Calculate basic support and resistance levels"""
        try:
            if len(close) < 20:
                return {'support_1': None, 'resistance_1': None}

            # Simple method: recent lows and highs
            recent_data = close.tail(20)
            support_1 = recent_data.min()
            resistance_1 = recent_data.max()

            return {
                'support_1': support_1,
                'resistance_1': resistance_1
            }

        except Exception:
            return {'support_1': None, 'resistance_1': None}

    def calculate_obv_divergence(self) -> Dict[str, Any]:
        """
        Calculate OBV (On-Balance Volume) and detect divergence

        OBV tracks cumulative volume flow:
        - Price up + Volume up = Bullish confirmation
        - Price up + Volume down = Bearish divergence (warning)
        - Price down + Volume up = Bullish divergence (reversal signal)

        Returns:
            OBV analysis with divergence detection
        """
        try:
            if len(self.price_data) < 20:
                return {'has_data': False, 'error': 'Insufficient data'}

            close = self.price_data['close']
            volume = self.price_data['volume'] if 'volume' in self.price_data.columns else None

            if volume is None or volume.isna().all():
                return {'has_data': False, 'error': 'No volume data'}

            # Calculate OBV
            obv = []
            obv_value = 0
            for i in range(len(self.price_data)):
                if i == 0:
                    obv.append(volume.iloc[i])
                    obv_value = volume.iloc[i]
                else:
                    if close.iloc[i] > close.iloc[i-1]:
                        obv_value += volume.iloc[i]
                    elif close.iloc[i] < close.iloc[i-1]:
                        obv_value -= volume.iloc[i]
                    obv.append(obv_value)

            obv_series = pd.Series(obv, index=self.price_data.index)

            # Calculate OBV trend (20-period SMA)
            obv_sma = obv_series.rolling(window=20).mean()

            # Detect divergence (last 20 periods)
            lookback = 20
            price_trend = 'up' if close.iloc[-1] > close.iloc[-lookback] else 'down'
            obv_trend = 'up' if obv_series.iloc[-1] > obv_series.iloc[-lookback] else 'down'

            # Calculate trend strength
            price_change_pct = ((close.iloc[-1] - close.iloc[-lookback]) / close.iloc[-lookback]) * 100
            obv_change_pct = ((obv_series.iloc[-1] - obv_series.iloc[-lookback]) / abs(obv_series.iloc[-lookback])) * 100 if obv_series.iloc[-lookback] != 0 else 0

            # Divergence detection
            if price_trend == 'up' and obv_trend == 'down':
                divergence = 'bearish_div'
                signal = 'SELL'
                strength = 8.0
                interpretation = f"⚠️ Bearish Divergence: Price up {price_change_pct:.1f}% but OBV down - weak rally, potential reversal"
            elif price_trend == 'down' and obv_trend == 'up':
                divergence = 'bullish_div'
                signal = 'BUY'
                strength = 8.0
                interpretation = f"✅ Bullish Divergence: Price down {price_change_pct:.1f}% but OBV up - strong buying pressure, potential reversal"
            elif price_trend == obv_trend:
                divergence = 'none'
                if price_trend == 'up':
                    signal = 'BUY'
                    strength = 7.0
                    interpretation = f"📈 Confirmed Uptrend: Price and OBV both up - strong bullish momentum"
                else:
                    signal = 'SELL'
                    strength = 7.0
                    interpretation = f"📉 Confirmed Downtrend: Price and OBV both down - strong bearish momentum"
            else:
                divergence = 'none'
                signal = 'NEUTRAL'
                strength = 5.0
                interpretation = "Neutral - no clear divergence"

            return {
                'has_data': True,
                'obv_current': float(obv_series.iloc[-1]),
                'obv_sma_20': float(obv_sma.iloc[-1]) if not pd.isna(obv_sma.iloc[-1]) else None,
                'obv_trend': obv_trend,
                'price_trend': price_trend,
                'divergence': divergence,
                'signal': signal,
                'strength': strength,
                'interpretation': interpretation,
                'price_change_pct': round(price_change_pct, 2),
                'obv_change_pct': round(obv_change_pct, 2)
            }

        except Exception as e:
            logger.error(f"OBV calculation failed: {e}")
            return {'has_data': False, 'error': str(e)}

    def calculate_volume_profile(self, bins: int = 50) -> Dict[str, Any]:
        """
        Calculate Volume-by-Price histogram (Volume Profile)

        Identifies price levels with highest trading activity:
        - POC (Point of Control): Price level with highest volume
        - HVN (High Volume Nodes): Support/Resistance areas
        - LVN (Low Volume Nodes): Quick price movement areas

        Args:
            bins: Number of price bins (default 50)

        Returns:
            Volume Profile analysis with POC and key levels
        """
        try:
            if len(self.price_data) < 50:
                return {'has_data': False, 'error': 'Insufficient data'}

            close = self.price_data['close']
            volume = self.price_data['volume'] if 'volume' in self.price_data.columns else None

            if volume is None or volume.isna().all():
                return {'has_data': False, 'error': 'No volume data'}

            # Create price bins
            price_min = self.price_data['low'].min()
            price_max = self.price_data['high'].max()
            price_bins = np.linspace(price_min, price_max, bins)

            # Calculate volume for each price bin
            volume_profile = []
            for i in range(len(price_bins) - 1):
                # Find candles that traded in this price range
                mask = (
                    (self.price_data['low'] <= price_bins[i+1]) &
                    (self.price_data['high'] >= price_bins[i])
                )
                total_volume = self.price_data.loc[mask, 'volume'].sum()
                mid_price = (price_bins[i] + price_bins[i+1]) / 2

                volume_profile.append({
                    'price_level': mid_price,
                    'volume': total_volume
                })

            # Sort by volume
            volume_profile_sorted = sorted(volume_profile, key=lambda x: x['volume'], reverse=True)

            # POC (Point of Control) - highest volume price
            poc = volume_profile_sorted[0]

            # High Volume Nodes (top 10%)
            hvn_count = max(1, int(len(volume_profile_sorted) * 0.10))
            high_volume_nodes = volume_profile_sorted[:hvn_count]

            # Low Volume Nodes (bottom 10%)
            lvn_count = max(1, int(len(volume_profile_sorted) * 0.10))
            low_volume_nodes = volume_profile_sorted[-lvn_count:]

            # Current price analysis
            current_price = close.iloc[-1]

            # Find nearest HVN (likely support/resistance)
            hvn_prices = [node['price_level'] for node in high_volume_nodes]
            nearest_hvn_above = min([p for p in hvn_prices if p > current_price], default=None)
            nearest_hvn_below = max([p for p in hvn_prices if p < current_price], default=None)

            # Interpretation
            distance_to_poc = ((current_price - poc['price_level']) / current_price) * 100

            if abs(distance_to_poc) < 1:
                poc_interpretation = f"🎯 Price at POC (${poc['price_level']:.2f}) - high activity area, expect consolidation"
            elif distance_to_poc > 2:
                poc_interpretation = f"⬆️ Price {distance_to_poc:.1f}% above POC - may pull back to ${poc['price_level']:.2f}"
            elif distance_to_poc < -2:
                poc_interpretation = f"⬇️ Price {abs(distance_to_poc):.1f}% below POC - may rally to ${poc['price_level']:.2f}"
            else:
                poc_interpretation = f"Near POC (${poc['price_level']:.2f})"

            return {
                'has_data': True,
                'poc': {
                    'price': float(poc['price_level']),
                    'volume': float(poc['volume']),
                    'interpretation': poc_interpretation
                },
                'high_volume_nodes': [
                    {'price': float(node['price_level']), 'volume': float(node['volume'])}
                    for node in high_volume_nodes[:5]  # Top 5 HVNs
                ],
                'low_volume_nodes': [
                    {'price': float(node['price_level']), 'volume': float(node['volume'])}
                    for node in low_volume_nodes[:3]  # Top 3 LVNs
                ],
                'nearest_resistance_hvn': float(nearest_hvn_above) if nearest_hvn_above else None,
                'nearest_support_hvn': float(nearest_hvn_below) if nearest_hvn_below else None,
                'distance_to_poc_pct': round(distance_to_poc, 2),
                'recommendation': 'Use HVN levels as support/resistance - expect price reactions at these levels'
            }

        except Exception as e:
            logger.error(f"Volume Profile calculation failed: {e}")
            return {'has_data': False, 'error': str(e)}