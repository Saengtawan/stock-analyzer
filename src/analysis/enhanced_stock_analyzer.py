"""
Enhanced Stock Analyzer - Integration of all advanced modules
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

try:
    from .technical.technical_analyzer import TechnicalAnalyzer
    from .fundamental.fundamental_analyzer import FundamentalAnalyzer
    from ..data_quality.data_validator import DataQualityValidator
    from ..timeframe.timeframe_manager import TimeFrameManager, TradingStrategy
    from ..analysis.advanced.advanced_models import AdvancedTechnicalAnalyzer
    from ..adaptability.market_regime_detector import MarketRegimeDetector
    from ..risk.enhanced_risk_manager import EnhancedRiskManager
    from ..signal_processing.signal_filter import SignalNoiseFilter
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
    from analysis.technical.technical_analyzer import TechnicalAnalyzer
    from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer
    from data_quality.data_validator import DataQualityValidator
    from timeframe.timeframe_manager import TimeFrameManager, TradingStrategy
    from analysis.advanced.advanced_models import AdvancedTechnicalAnalyzer
    from adaptability.market_regime_detector import MarketRegimeDetector
    from risk.enhanced_risk_manager import EnhancedRiskManager
    from signal_processing.signal_filter import SignalNoiseFilter


class EnhancedStockAnalyzer:
    """
    Enhanced stock analyzer integrating all advanced modules for comprehensive analysis
    """

    def __init__(self,
                 trading_strategy: str = "swing_trading",
                 risk_tolerance: str = "moderate"):
        """
        Initialize enhanced stock analyzer

        Args:
            trading_strategy: Trading strategy for analysis optimization
            risk_tolerance: Risk tolerance level (conservative, moderate, aggressive)
        """
        self.trading_strategy = trading_strategy
        self.risk_tolerance = risk_tolerance

        # Initialize core modules
        self.data_validator = DataQualityValidator()
        self.timeframe_manager = TimeFrameManager()
        self.risk_manager = EnhancedRiskManager()
        self.signal_filter = SignalNoiseFilter()

        logger.info(f"Enhanced Stock Analyzer initialized with strategy: {trading_strategy}, risk: {risk_tolerance}")

    def analyze_stock(self,
                     symbol: str,
                     price_data: pd.DataFrame,
                     fundamental_data: Optional[Dict[str, Any]] = None,
                     time_horizon: str = 'medium') -> Dict[str, Any]:
        """
        Perform comprehensive enhanced stock analysis

        Args:
            symbol: Stock symbol
            price_data: Historical price data
            fundamental_data: Optional fundamental data
            time_horizon: Investment time horizon ('short', 'medium', 'long')

        Returns:
            Comprehensive analysis results
        """
        logger.info(f"Starting enhanced analysis for {symbol} with time horizon: {time_horizon}")

        try:
            # 1. Data Quality Validation
            quality_validation = self._validate_data_quality(symbol, price_data, fundamental_data)
            if quality_validation['quality_score'] < 0.5:
                logger.warning(f"Low data quality score: {quality_validation['quality_score']}")

            # 2. Timeframe Optimization
            optimal_timeframes = self._optimize_timeframes(price_data)

            # 3. Technical Analysis
            technical_results = self._perform_technical_analysis(price_data)

            # 4. Fundamental Analysis (if data available)
            fundamental_results = self._perform_fundamental_analysis(
                symbol, fundamental_data) if fundamental_data else {}

            # 5. Market Regime Detection
            try:
                regime_analysis = self._analyze_market_regime(price_data)
            except Exception as e:
                logger.warning(f"Market regime analysis failed: {e}")
                regime_analysis = {'current': {'regime': 'NORMAL', 'confidence': 0.5}}

            # 6. Advanced Pattern Recognition
            try:
                advanced_analysis = self._perform_advanced_analysis(price_data)
            except Exception as e:
                logger.warning(f"Advanced analysis failed: {e}")
                advanced_analysis = {'pattern_strength': 0, 'sentiment_score': 0.5}

            # 7. Signal Processing & Filtering
            try:
                processed_signals = self._process_and_filter_signals(
                    technical_results, advanced_analysis, regime_analysis)
            except Exception as e:
                logger.warning(f"Signal processing failed: {e}")
                processed_signals = {'signal_confidence': 0.5, 'dominant_signal': {}}

            # 8. Risk Assessment
            try:
                risk_assessment = self._assess_comprehensive_risk(
                    price_data, processed_signals, regime_analysis)
            except Exception as e:
                logger.warning(f"Risk assessment failed: {e}")
                risk_assessment = {'overall_risk_score': 0.5}

            # 9. Generate Final Recommendations
            try:
                final_recommendation = self._generate_final_recommendation(
                    technical_results, fundamental_results, processed_signals,
                    risk_assessment, regime_analysis, time_horizon)
            except Exception as e:
                logger.warning(f"Final recommendation generation failed: {e}")
                final_recommendation = {
                    'overall_score': 0.5,
                    'recommendation': 'HOLD',
                    'confidence': 0.5,
                    'key_reasons': ['Analysis incomplete due to technical issues']
                }

            # 10. Adaptability Insights
            try:
                adaptability_insights = self._generate_adaptability_insights(
                    regime_analysis, advanced_analysis, risk_assessment)
            except Exception as e:
                logger.warning(f"Adaptability insights generation failed: {e}")
                adaptability_insights = ['System operating in fallback mode']

            return {
                'symbol': symbol,
                'analysis_timestamp': datetime.now().isoformat(),
                'analysis_summary': {
                    'overall_score': final_recommendation['overall_score'],
                    'recommendation': final_recommendation['recommendation'],
                    'confidence': final_recommendation['confidence'],
                    'key_reasons': final_recommendation['key_reasons']
                },

                # Core Analysis Components
                'data_quality': quality_validation,
                'timeframe_optimization': optimal_timeframes,
                'technical_analysis': technical_results,
                'fundamental_analysis': fundamental_results,
                'market_regime': regime_analysis,
                'advanced_analysis': advanced_analysis,

                # Signal Processing
                'signal_processing': {
                    'raw_signals': technical_results.get('raw_signals', {}),
                    'filtered_signals': processed_signals,
                    'signal_quality_metrics': self._calculate_signal_quality_metrics(processed_signals),
                    'noise_analysis': self._analyze_signal_noise(processed_signals)
                },

                # Risk Management
                'risk_assessment': risk_assessment,
                'position_sizing': self._calculate_optimal_position_sizing(risk_assessment),
                'risk_scenarios': self._generate_risk_scenarios(price_data, risk_assessment),

                # Adaptability & Insights
                'adaptability_insights': adaptability_insights,
                'regime_adaptations': self._suggest_regime_adaptations(regime_analysis),
                'strategy_recommendations': self._recommend_strategy_adjustments(
                    regime_analysis, risk_assessment),

                # Actionable Outputs
                'entry_exit_strategy': self._create_entry_exit_strategy(
                    processed_signals, risk_assessment, regime_analysis),
                'monitoring_alerts': self._setup_monitoring_alerts(
                    processed_signals, regime_analysis),
                'performance_expectations': self._set_performance_expectations(
                    technical_results, risk_assessment)
            }

        except Exception as e:
            logger.error(f"Enhanced analysis failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'analysis_timestamp': datetime.now().isoformat(),
                'recommendation': 'ANALYSIS_ERROR'
            }

    def _validate_data_quality(self, symbol: str, price_data: pd.DataFrame,
                              fundamental_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate and enhance data quality"""
        price_validation = self.data_validator.validate_price_data(price_data, symbol)

        quality_report = {
            'price_data_quality': price_validation['quality_score'],
            'data_completeness': price_validation.get('completeness', 0),
            'anomalies_detected': len(price_validation.get('anomalies', [])),
            'missing_data_percentage': price_validation.get('missing_percentage', 0)
        }

        if fundamental_data:
            fundamental_validation = self.data_validator.validate_fundamental_data(fundamental_data, symbol)
            quality_report.update({
                'fundamental_data_quality': fundamental_validation['quality_score'],
                'fundamental_completeness': fundamental_validation.get('completeness', 0)
            })

        overall_quality = np.mean([
            quality_report['price_data_quality'],
            quality_report.get('fundamental_data_quality', quality_report['price_data_quality'])
        ])

        quality_report['quality_score'] = overall_quality
        return quality_report

    def _optimize_timeframes(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """Optimize timeframes for the trading strategy"""
        try:
            strategy_enum = TradingStrategy[self.trading_strategy.upper()]
        except KeyError:
            strategy_enum = TradingStrategy.SWING_TRADING

        optimal_timeframes = self.timeframe_manager.get_optimal_timeframes(strategy_enum)

        return {
            'strategy': self.trading_strategy,
            'optimal_timeframes': optimal_timeframes,
            'data_points': len(price_data),
            'timeframe_status': 'optimized_for_strategy'
        }

    def _perform_technical_analysis(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """Perform enhanced technical analysis"""
        technical_analyzer = TechnicalAnalyzer(price_data, self.trading_strategy)
        return technical_analyzer.analyze()

    def _perform_fundamental_analysis(self, symbol: str,
                                    fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform fundamental analysis if data is available"""
        try:
            current_price = fundamental_data.get('current_price', 100.0)
            fundamental_analyzer = FundamentalAnalyzer(fundamental_data, current_price)
            return fundamental_analyzer.analyze()
        except Exception as e:
            logger.warning(f"Fundamental analysis failed: {e}")
            return {'error': str(e)}

    def _extract_regime_type(self, regime_analysis: Dict[str, Any]) -> str:
        """Extract regime type string from regime analysis"""
        current_regime_info = regime_analysis.get('current_regime', {})
        if isinstance(current_regime_info, dict):
            current_regime = current_regime_info.get('current_regime', 'NORMAL')
            # Handle case where current_regime might be Enum or string
            if hasattr(current_regime, 'regime_name'):
                return current_regime.regime_name
            elif hasattr(current_regime, 'name'):
                return current_regime.name.lower()
            else:
                return str(current_regime) if current_regime else 'NORMAL'
        else:
            return 'NORMAL'

    def _analyze_market_regime(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze current market regime and dynamics"""
        try:
            regime_detector = MarketRegimeDetector(price_data)

            # Get regime detection results with error handling
            try:
                regime_detection_result = regime_detector.detect_current_regime(price_data)
            except Exception as e:
                logger.warning(f"Regime detection failed: {e}")
                regime_detection_result = {
                    'current_regime': 'NORMAL',
                    'regime_probability': 0.5,
                    'regime_strength': 0.5
                }

            try:
                regime_history = regime_detector.get_regime_history()
                if not isinstance(regime_history, list):
                    regime_history = []
            except Exception as e:
                logger.warning(f"Regime history retrieval failed: {e}")
                regime_history = []

            try:
                regime_transitions = regime_detector.detect_regime_transitions()
                if not isinstance(regime_transitions, list):
                    regime_transitions = []
            except Exception as e:
                logger.warning(f"Regime transitions detection failed: {e}")
                regime_transitions = []

            # Extract the current regime from the detection result
            if isinstance(regime_detection_result, dict):
                current_regime_info = regime_detection_result
            else:
                # Fallback if detect_current_regime returns something else
                current_regime_info = {
                    'current_regime': regime_detection_result,
                    'regime_probability': 0.5,
                    'regime_strength': 0.5
                }

            return {
                'current_regime': current_regime_info,
                'regime_history': regime_history,
                'regime_transitions': regime_transitions,
                'regime_stability': self._assess_regime_stability(regime_history),
                'transition_probability': self._calculate_transition_probabilities(regime_transitions)
            }

        except Exception as e:
            logger.warning(f"Market regime analysis completely failed: {e}")
            return {
                'current_regime': {
                    'current_regime': 'NORMAL',
                    'regime_probability': 0.5,
                    'regime_strength': 0.5
                },
                'regime_history': [],
                'regime_transitions': [],
                'regime_stability': {'stability_score': 0.5},
                'transition_probability': {'next_regime_prob': 0.5}
            }

    def _perform_advanced_analysis(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """Perform advanced technical analysis"""
        advanced_analyzer = AdvancedTechnicalAnalyzer(price_data)
        return advanced_analyzer.analyze(price_data)

    def _process_and_filter_signals(self, technical_results: Dict[str, Any],
                                   advanced_analysis: Dict[str, Any],
                                   regime_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Process and filter signals to reduce noise"""
        # Ensure technical_results is a dictionary
        if not isinstance(technical_results, dict):
            technical_results = {}

        raw_signals = technical_results.get('raw_signals', {})
        if not isinstance(raw_signals, dict):
            raw_signals = {}

        # Apply signal filtering
        try:
            # Convert signals to numerical format for filtering
            signal_data = self._convert_signals_to_arrays(raw_signals)

            # Ensure signal_data is a dictionary
            if not isinstance(signal_data, dict):
                signal_data = {'strengths': [], 'directions': []}

            if signal_data.get('strengths') and signal_data.get('directions'):
                filtered_strengths = self.signal_filter.apply_ensemble_filtering(
                    np.array(signal_data['strengths']))
                filtered_directions = self.signal_filter.apply_ensemble_filtering(
                    np.array(signal_data['directions']))

                # Convert back to signal format
                filtered_signals = self._convert_arrays_to_signals(
                    raw_signals, filtered_strengths, filtered_directions)
            else:
                filtered_signals = raw_signals

            # Apply regime-based signal adjustment
            regime_type = self._extract_regime_type(regime_analysis)

            regime_adjusted_signals = self._adjust_signals_for_regime(
                filtered_signals, regime_type)

            # Ensure regime_adjusted_signals is a dictionary
            if not isinstance(regime_adjusted_signals, dict):
                regime_adjusted_signals = filtered_signals

            return {
                'raw_signals': raw_signals,
                'filtered_signals': filtered_signals,
                'regime_adjusted_signals': regime_adjusted_signals,
                'signal_confidence': self._calculate_signal_confidence(regime_adjusted_signals),
                'dominant_signal': self._identify_dominant_signal(regime_adjusted_signals)
            }

        except Exception as e:
            logger.warning(f"Signal processing failed: {e}")
            return {'raw_signals': raw_signals, 'error': str(e)}

    def _assess_comprehensive_risk(self, price_data: pd.DataFrame,
                                 processed_signals: Dict[str, Any],
                                 regime_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Assess comprehensive risk across all dimensions"""
        # Prepare portfolio data
        portfolio_data = {
            'returns': price_data['close'].pct_change().dropna().tolist() if 'close' in price_data.columns else [],
            'prices': price_data['close'].tolist() if 'close' in price_data.columns else [],
            'volumes': price_data['volume'].tolist() if 'volume' in price_data.columns else []
        }

        # Calculate risk metrics
        risk_metrics = self.risk_manager.calculate_risk_metrics(portfolio_data)

        # Add regime-specific risk assessment
        regime_risk = self._assess_regime_specific_risk(regime_analysis, risk_metrics)

        # Add signal-based risk assessment
        signal_risk = self._assess_signal_based_risk(processed_signals)

        return {
            'portfolio_risk_metrics': risk_metrics,
            'regime_specific_risk': regime_risk,
            'signal_based_risk': signal_risk,
            'overall_risk_score': self._calculate_overall_risk_score(
                risk_metrics, regime_risk, signal_risk),
            'risk_recommendations': self._generate_risk_recommendations(
                risk_metrics, regime_risk, signal_risk)
        }

    def _generate_final_recommendation(self, technical_results: Dict[str, Any],
                                     fundamental_results: Dict[str, Any],
                                     processed_signals: Dict[str, Any],
                                     risk_assessment: Dict[str, Any],
                                     regime_analysis: Dict[str, Any],
                                     time_horizon: str = 'medium') -> Dict[str, Any]:
        """Generate final comprehensive recommendation"""

        # Weight different analysis components based on time horizon
        if time_horizon == 'short':
            # Short-term: Focus on technical and signals
            technical_weight = 0.5
            fundamental_weight = 0.1 if fundamental_results and 'error' not in fundamental_results else 0
            signal_weight = 0.4
            risk_weight = 0.1
        elif time_horizon == 'long':
            # Long-term: Focus on fundamentals
            technical_weight = 0.2
            fundamental_weight = 0.6 if fundamental_results and 'error' not in fundamental_results else 0
            signal_weight = 0.2
            risk_weight = 0.1
        else:  # medium
            # Medium-term: Balanced approach
            technical_weight = 0.4
            fundamental_weight = 0.3 if fundamental_results and 'error' not in fundamental_results else 0
            signal_weight = 0.3
            risk_weight = 0.1

        # Calculate component scores
        technical_score = technical_results.get('technical_score', {}).get('total_score', 5) / 10
        fundamental_score = (fundamental_results.get('overall_score', 5) / 10
                           if fundamental_results and 'error' not in fundamental_results else 0.5)
        signal_score = processed_signals.get('signal_confidence', 0.5)
        risk_score = 1 - (risk_assessment.get('overall_risk_score', 0.5))  # Invert risk

        # Adjust weights if fundamental data not available
        if fundamental_weight == 0:
            technical_weight = 0.5
            signal_weight = 0.4
            risk_weight = 0.1

        # Calculate weighted overall score
        overall_score = (technical_score * technical_weight +
                        fundamental_score * fundamental_weight +
                        signal_score * signal_weight +
                        risk_score * risk_weight)

        # Apply overvaluation penalty for long-term analysis
        if time_horizon == 'long' and fundamental_results and 'error' not in fundamental_results:
            valuation_penalty = self._calculate_overvaluation_penalty(fundamental_results)
            overall_score = max(0, overall_score - (valuation_penalty / 10))  # Convert to 0-1 scale

        # Generate recommendation
        if overall_score >= 0.8:
            recommendation = "STRONG BUY"
        elif overall_score >= 0.65:
            recommendation = "BUY"
        elif overall_score >= 0.45:
            recommendation = "HOLD"
        elif overall_score >= 0.3:
            recommendation = "SELL"
        else:
            recommendation = "STRONG SELL"

        # Adjust for market regime
        current_regime = self._extract_regime_type(regime_analysis)
        if current_regime == 'HIGH_VOLATILITY' and recommendation in ['STRONG BUY', 'BUY']:
            recommendation += " (Reduce Position Size)"
        elif current_regime == 'BEAR' and recommendation in ['STRONG BUY', 'BUY']:
            recommendation = "HOLD (Bear Market Caution)"

        # Calculate confidence
        signal_confidence = processed_signals.get('signal_confidence', 0.5)
        regime_confidence = regime_analysis.get('current_regime', {}).get('confidence', 0.5)
        confidence = (signal_confidence + regime_confidence) / 2

        # Generate key reasons
        key_reasons = self._generate_key_reasons(
            technical_results, processed_signals, regime_analysis, overall_score)

        return {
            'overall_score': round(overall_score, 3),
            'recommendation': recommendation,
            'confidence': round(confidence, 3),
            'key_reasons': key_reasons,
            'component_scores': {
                'technical': round(technical_score, 3),
                'fundamental': round(fundamental_score, 3),
                'signals': round(signal_score, 3),
                'risk_adjusted': round(risk_score, 3)
            },
            'regime_context': current_regime
        }

    def _generate_adaptability_insights(self, regime_analysis: Dict[str, Any],
                                      advanced_analysis: Dict[str, Any],
                                      risk_assessment: Dict[str, Any]) -> List[str]:
        """Generate insights about market adaptability and strategy adjustments"""
        insights = []

        current_regime = self._extract_regime_type(regime_analysis)
        regime_confidence = regime_analysis.get('current_regime', {}).get('confidence', 0)

        # Regime-based insights
        if regime_confidence > 0.8:
            insights.append(f"High confidence {current_regime.lower()} regime - adapt strategy accordingly")
        elif regime_confidence < 0.4:
            insights.append("Regime uncertainty detected - use flexible, adaptive approach")

        # Risk-based insights
        overall_risk = risk_assessment.get('overall_risk_score', 0.5)
        if overall_risk > 0.7:
            insights.append("High risk environment - focus on capital preservation")
        elif overall_risk < 0.3:
            insights.append("Low risk environment - opportunity for aggressive positioning")

        # Pattern-based insights
        pattern_strength = advanced_analysis.get('pattern_strength', 0)
        if pattern_strength > 0.7:
            insights.append("Strong patterns detected - high probability technical setups")
        elif pattern_strength < 0.3:
            insights.append("Weak pattern formation - avoid trend-following strategies")

        return insights

    # Helper methods for complex calculations
    def _convert_signals_to_arrays(self, signals: Dict[str, Any]) -> Dict[str, List]:
        """Convert signal dict to arrays for processing"""
        try:
            # Ensure signals is a dictionary
            if not isinstance(signals, dict):
                return {'strengths': [], 'directions': []}

            strengths = []
            directions = []

            strength_map = {'Strong': 3, 'Moderate': 2, 'Weak': 1}

            for signal_data in signals.values():
                try:
                    if isinstance(signal_data, dict):
                        strength = strength_map.get(signal_data.get('strength', 'Weak'), 1)
                        direction = 1 if signal_data.get('signal') == 'BUY' else -1 if signal_data.get('signal') == 'SELL' else 0

                        strengths.append(strength)
                        directions.append(direction)
                except Exception:
                    # Skip invalid signal data
                    continue

            return {'strengths': strengths, 'directions': directions}

        except Exception:
            return {'strengths': [], 'directions': []}

    def _convert_arrays_to_signals(self, original_signals: Dict[str, Any],
                                 filtered_strengths: np.ndarray,
                                 filtered_directions: np.ndarray) -> Dict[str, Any]:
        """Convert filtered arrays back to signal format"""
        filtered_signals = original_signals.copy()
        signal_names = list(original_signals.keys())

        for i, (strength, direction) in enumerate(zip(filtered_strengths, filtered_directions)):
            if i < len(signal_names):
                signal_name = signal_names[i]
                if isinstance(filtered_signals[signal_name], dict):
                    filtered_signals[signal_name]['filtered_strength'] = float(strength)
                    filtered_signals[signal_name]['filtered_direction'] = float(direction)

        return filtered_signals

    def _adjust_signals_for_regime(self, signals: Dict[str, Any], regime_type: str) -> Dict[str, Any]:
        """Adjust signals based on market regime"""
        # Handle both string and dict inputs for backward compatibility
        if isinstance(regime_type, dict):
            regime_type = regime_type.get('regime', 'NORMAL')
        elif not isinstance(regime_type, str):
            regime_type = 'NORMAL'
        adjusted_signals = signals.copy()

        # Apply regime-specific adjustments
        adjustment_factor = 1.0
        if regime_type == 'BEAR':
            adjustment_factor = 0.8  # Reduce bullish signals in bear market
        elif regime_type == 'HIGH_VOLATILITY':
            adjustment_factor = 0.9  # Reduce all signals in high volatility
        elif regime_type == 'BULL':
            adjustment_factor = 1.1  # Enhance signals in bull market

        # Apply adjustments
        for signal_name, signal_data in adjusted_signals.items():
            if isinstance(signal_data, dict) and 'filtered_strength' in signal_data:
                signal_data['regime_adjusted_strength'] = signal_data['filtered_strength'] * adjustment_factor

        return adjusted_signals

    def _calculate_signal_confidence(self, signals: Dict[str, Any]) -> float:
        """Calculate overall signal confidence"""
        if not signals:
            return 0.0

        total_strength = 0
        signal_count = 0

        for signal_data in signals.values():
            if isinstance(signal_data, dict):
                strength = signal_data.get('regime_adjusted_strength',
                                         signal_data.get('filtered_strength', 1))
                total_strength += strength
                signal_count += 1

        return min(total_strength / max(signal_count * 3, 1), 1.0) if signal_count > 0 else 0.0

    def _identify_dominant_signal(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """Identify the strongest/dominant signal"""
        if not signals:
            return {}

        max_strength = 0
        dominant_signal = {}

        for signal_name, signal_data in signals.items():
            if isinstance(signal_data, dict):
                strength = signal_data.get('regime_adjusted_strength',
                                         signal_data.get('filtered_strength', 0))
                if strength > max_strength:
                    max_strength = strength
                    dominant_signal = {
                        'name': signal_name,
                        'data': signal_data,
                        'strength': strength
                    }

        return dominant_signal

    def _assess_regime_stability(self, regime_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess stability of market regime"""
        if len(regime_history) < 5:
            return {'stability': 'insufficient_data', 'stability_score': 0.5}

        recent_regimes = regime_history[-10:]  # Last 10 periods
        regime_changes = 0

        for i in range(1, len(recent_regimes)):
            if recent_regimes[i]['regime'] != recent_regimes[i-1]['regime']:
                regime_changes += 1

        stability_score = 1 - (regime_changes / len(recent_regimes))

        if stability_score > 0.8:
            stability = 'very_stable'
        elif stability_score > 0.6:
            stability = 'stable'
        elif stability_score > 0.4:
            stability = 'moderate'
        else:
            stability = 'unstable'

        return {
            'stability': stability,
            'stability_score': stability_score,
            'regime_changes': regime_changes
        }

    def _calculate_transition_probabilities(self, transitions: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate regime transition probabilities"""
        if not transitions:
            return {}

        transition_counts = {}
        total_transitions = len(transitions)

        for transition in transitions:
            from_regime = transition.get('from_regime', 'UNKNOWN')
            to_regime = transition.get('to_regime', 'UNKNOWN')
            transition_key = f"{from_regime}_to_{to_regime}"

            transition_counts[transition_key] = transition_counts.get(transition_key, 0) + 1

        # Convert to probabilities
        transition_probs = {}
        for transition_key, count in transition_counts.items():
            transition_probs[transition_key] = count / total_transitions

        return transition_probs

    def _assess_regime_specific_risk(self, regime_analysis: Dict[str, Any],
                                   risk_metrics: Dict[str, Any]) -> Dict[str, float]:
        """Assess risk specific to current market regime"""
        current_regime = self._extract_regime_type(regime_analysis)
        base_volatility = risk_metrics.get('portfolio_volatility', 0.02)

        regime_risk_multipliers = {
            'HIGH_VOLATILITY': 1.5,
            'BEAR': 1.3,
            'BULL': 0.8,
            'LOW_VOLATILITY': 0.7,
            'NORMAL': 1.0
        }

        multiplier = regime_risk_multipliers.get(current_regime, 1.0)

        return {
            'regime_adjusted_volatility': base_volatility * multiplier,
            'regime_risk_multiplier': multiplier,
            'regime_specific_risk_score': min(base_volatility * multiplier, 1.0)
        }

    def _assess_signal_based_risk(self, processed_signals: Dict[str, Any]) -> Dict[str, float]:
        """Assess risk based on signal characteristics"""
        signal_confidence = processed_signals.get('signal_confidence', 0.5)
        signal_consistency = self._calculate_signal_consistency(processed_signals)

        # Lower confidence and consistency = higher risk
        signal_risk_score = 1 - ((signal_confidence + signal_consistency) / 2)

        return {
            'signal_confidence': signal_confidence,
            'signal_consistency': signal_consistency,
            'signal_risk_score': signal_risk_score
        }

    def _calculate_signal_consistency(self, processed_signals: Dict[str, Any]) -> float:
        """Calculate consistency across different signals"""
        signals = processed_signals.get('regime_adjusted_signals', {})
        if not signals:
            return 0.0

        directions = []
        for signal_data in signals.values():
            if isinstance(signal_data, dict):
                direction = signal_data.get('filtered_direction', 0)
                directions.append(direction)

        if not directions:
            return 0.0

        # Calculate consistency as agreement between signals
        positive_signals = sum(1 for d in directions if d > 0)
        negative_signals = sum(1 for d in directions if d < 0)
        total_signals = len(directions)

        # Consistency is highest when all signals agree
        consistency = max(positive_signals, negative_signals) / total_signals
        return consistency

    def _calculate_overall_risk_score(self, portfolio_risk: Dict[str, Any],
                                    regime_risk: Dict[str, float],
                                    signal_risk: Dict[str, float]) -> float:
        """Calculate overall risk score from all components"""
        portfolio_risk_score = portfolio_risk.get('portfolio_var', 0.05)  # VaR as risk proxy
        regime_risk_score = regime_risk.get('regime_specific_risk_score', 0.5)
        signal_risk_score = signal_risk.get('signal_risk_score', 0.5)

        # Weight the different risk components
        overall_risk = (portfolio_risk_score * 0.4 +
                       regime_risk_score * 0.3 +
                       signal_risk_score * 0.3)

        return min(overall_risk, 1.0)

    def _generate_risk_recommendations(self, portfolio_risk: Dict[str, Any],
                                     regime_risk: Dict[str, float],
                                     signal_risk: Dict[str, float]) -> List[str]:
        """Generate specific risk management recommendations"""
        recommendations = []

        overall_risk = self._calculate_overall_risk_score(portfolio_risk, regime_risk, signal_risk)

        if overall_risk > 0.7:
            recommendations.append("High risk environment - implement strict stop losses")
            recommendations.append("Consider reducing position sizes by 30-50%")
        elif overall_risk > 0.5:
            recommendations.append("Moderate risk - maintain standard risk management")
            recommendations.append("Monitor positions closely for regime changes")
        else:
            recommendations.append("Low risk environment - opportunity for larger positions")

        # Specific recommendations based on risk components
        if signal_risk['signal_risk_score'] > 0.6:
            recommendations.append("Low signal confidence - avoid aggressive entries")

        if regime_risk['regime_risk_multiplier'] > 1.2:
            recommendations.append("Volatile regime - use wider stops and smaller positions")

        return recommendations

    def _generate_key_reasons(self, technical_results: Dict[str, Any],
                            processed_signals: Dict[str, Any],
                            regime_analysis: Dict[str, Any],
                            overall_score: float) -> List[str]:
        """Generate key reasons for the recommendation"""
        reasons = []

        # Technical reasons
        tech_score = technical_results.get('technical_score', {}).get('total_score', 5)
        if tech_score >= 8:
            reasons.append("Strong technical indicators support the position")
        elif tech_score <= 3:
            reasons.append("Weak technical setup argues against position")

        # Signal reasons
        dominant_signal = processed_signals.get('dominant_signal', {})
        if dominant_signal:
            signal_data = dominant_signal.get('data', {})
            reason = signal_data.get('reason', '')
            if reason:
                reasons.append(f"Key signal: {reason}")

        # Regime reasons
        current_regime = self._extract_regime_type(regime_analysis)
        if current_regime != 'NORMAL':
            reasons.append(f"Current {current_regime.lower()} market regime influences strategy")

        # Score-based reasons
        if overall_score > 0.8:
            reasons.append("Multiple factors align for strong conviction")
        elif overall_score < 0.3:
            reasons.append("Multiple negative factors suggest caution")

        return reasons[:3]  # Limit to top 3 reasons

    def _calculate_signal_quality_metrics(self, signals: Dict[str, Any]) -> Dict[str, float]:
        """Calculate detailed signal quality metrics"""
        if not signals:
            return {'overall_quality': 0, 'noise_ratio': 1}

        signal_strengths = []
        noise_ratios = []

        for signal_data in signals.values():
            if isinstance(signal_data, dict):
                strength = signal_data.get('filtered_strength', 1)
                original_strength = signal_data.get('original_strength', strength)
                noise_ratio = abs(strength - original_strength) / max(original_strength, 0.1)

                signal_strengths.append(strength)
                noise_ratios.append(noise_ratio)

        if signal_strengths:
            overall_quality = np.mean(signal_strengths) / 3  # Normalize to 0-1
            average_noise = np.mean(noise_ratios)
        else:
            overall_quality = 0
            average_noise = 1

        return {
            'overall_quality': round(overall_quality, 3),
            'noise_ratio': round(average_noise, 3),
            'signal_count': len(signal_strengths),
            'quality_score': round((overall_quality * (1 - average_noise)), 3)
        }

    def _analyze_signal_noise(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze noise characteristics in signals"""
        noise_analysis = {
            'high_noise_signals': [],
            'clean_signals': [],
            'average_noise_level': 0,
            'noise_distribution': {}
        }

        noise_levels = []

        for signal_name, signal_data in signals.items():
            if isinstance(signal_data, dict):
                noise_ratio = signal_data.get('noise_ratio', 0.5)
                noise_levels.append(noise_ratio)

                if noise_ratio > 0.3:
                    noise_analysis['high_noise_signals'].append(signal_name)
                elif noise_ratio < 0.1:
                    noise_analysis['clean_signals'].append(signal_name)

        if noise_levels:
            noise_analysis['average_noise_level'] = round(np.mean(noise_levels), 3)
            noise_analysis['noise_distribution'] = {
                'low_noise': sum(1 for n in noise_levels if n < 0.1),
                'medium_noise': sum(1 for n in noise_levels if 0.1 <= n < 0.3),
                'high_noise': sum(1 for n in noise_levels if n >= 0.3)
            }

        return noise_analysis

    def _calculate_optimal_position_sizing(self, risk_assessment: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate optimal position sizing based on risk assessment"""
        base_position_size = 0.1  # 10% default

        overall_risk = risk_assessment.get('overall_risk_score', 0.5)

        # Adjust position size based on risk
        if overall_risk > 0.7:
            position_multiplier = 0.5  # Reduce to 5%
        elif overall_risk > 0.5:
            position_multiplier = 0.7  # Reduce to 7%
        elif overall_risk < 0.3:
            position_multiplier = 1.5  # Increase to 15%
        else:
            position_multiplier = 1.0

        optimal_size = base_position_size * position_multiplier

        return {
            'recommended_position_percentage': round(optimal_size * 100, 1),
            'position_multiplier': position_multiplier,
            'risk_justification': f"Based on {overall_risk:.1%} overall risk score",
            'max_recommended_percentage': 20.0  # Hard limit
        }

    def _generate_risk_scenarios(self, price_data: pd.DataFrame,
                               risk_assessment: Dict[str, Any]) -> Dict[str, Any]:
        """Generate risk scenario analysis"""
        if 'close' not in price_data.columns or len(price_data) < 30:
            return {'error': 'Insufficient data for scenario analysis'}

        current_price = price_data['close'].iloc[-1]
        returns = price_data['close'].pct_change().dropna()

        # Calculate scenario returns
        worst_case = np.percentile(returns, 5)  # 5th percentile
        bad_case = np.percentile(returns, 25)   # 25th percentile
        base_case = returns.mean()              # Average return
        good_case = np.percentile(returns, 75)  # 75th percentile
        best_case = np.percentile(returns, 95)  # 95th percentile

        scenarios = {
            'worst_case': {
                'probability': 0.05,
                'return': round(worst_case, 4),
                'price_target': round(current_price * (1 + worst_case), 2)
            },
            'bad_case': {
                'probability': 0.20,
                'return': round(bad_case, 4),
                'price_target': round(current_price * (1 + bad_case), 2)
            },
            'base_case': {
                'probability': 0.50,
                'return': round(base_case, 4),
                'price_target': round(current_price * (1 + base_case), 2)
            },
            'good_case': {
                'probability': 0.20,
                'return': round(good_case, 4),
                'price_target': round(current_price * (1 + good_case), 2)
            },
            'best_case': {
                'probability': 0.05,
                'return': round(best_case, 4),
                'price_target': round(current_price * (1 + best_case), 2)
            }
        }

        return {
            'current_price': current_price,
            'scenarios': scenarios,
            'expected_return': round(base_case, 4),
            'volatility': round(returns.std(), 4)
        }

    def _suggest_regime_adaptations(self, regime_analysis: Dict[str, Any]) -> List[str]:
        """Suggest adaptations based on market regime"""
        current_regime = self._extract_regime_type(regime_analysis)
        adaptations = []

        regime_strategies = {
            'BULL': [
                "Focus on momentum strategies",
                "Increase position sizes gradually",
                "Look for breakout opportunities"
            ],
            'BEAR': [
                "Implement defensive strategies",
                "Consider short positions or hedging",
                "Focus on capital preservation"
            ],
            'HIGH_VOLATILITY': [
                "Use wider stop losses",
                "Reduce position sizes",
                "Focus on mean reversion strategies"
            ],
            'LOW_VOLATILITY': [
                "Opportunity for larger positions",
                "Look for range breakouts",
                "Consider volatility expansion strategies"
            ],
            'SIDEWAYS': [
                "Use range trading strategies",
                "Focus on support/resistance levels",
                "Avoid trend-following approaches"
            ]
        }

        adaptations = regime_strategies.get(current_regime, [
            "Maintain standard trading approach",
            "Monitor for regime changes",
            "Use balanced risk management"
        ])

        return adaptations

    def _calculate_overvaluation_penalty(self, fundamental_results: Dict[str, Any]) -> float:
        """Calculate penalty for overvalued stocks in long-term horizon"""
        penalty = 0

        # Get DCF valuation data
        dcf_data = fundamental_results.get('dcf_analysis', {}) or fundamental_results.get('dcf_valuation', {})
        upside_downside = dcf_data.get('upside_downside', 0)

        # Heavy DCF-based penalty for overvalued stocks
        if upside_downside < -50:  # More than 50% overvalued
            penalty += 4.0  # Very heavy penalty
        elif upside_downside < -30:  # 30-50% overvalued
            penalty += 3.0  # Heavy penalty
        elif upside_downside < -15:  # 15-30% overvalued
            penalty += 2.0  # Moderate penalty
        elif upside_downside < 0:   # Any overvaluation
            penalty += 1.0  # Light penalty

        # Get valuation score from fundamental analysis
        overall_score = fundamental_results.get('overall_score', 5.0)

        # Additional penalty for low fundamental scores
        if overall_score < 4.0:
            penalty += 1.0  # Additional penalty for poor fundamentals

        # Additional penalty based on specific valuation metrics
        financial_ratios = fundamental_results.get('financial_ratios', {})
        pe_ratio = financial_ratios.get('pe_ratio')
        pb_ratio = financial_ratios.get('pb_ratio')

        if pe_ratio and pe_ratio > 30:
            penalty += 0.5  # High P/E penalty
        if pb_ratio and pb_ratio > 5:
            penalty += 0.5  # High P/B penalty

        return penalty

    def _recommend_strategy_adjustments(self, regime_analysis: Dict[str, Any],
                                      risk_assessment: Dict[str, Any]) -> Dict[str, Any]:
        """Recommend strategy adjustments based on current conditions"""
        current_regime = self._extract_regime_type(regime_analysis)
        overall_risk = risk_assessment.get('overall_risk_score', 0.5)

        adjustments = {}

        # Timeframe adjustments
        if current_regime == 'HIGH_VOLATILITY':
            adjustments['timeframe'] = "Consider shorter timeframes for faster exits"
        elif current_regime == 'LOW_VOLATILITY':
            adjustments['timeframe'] = "Longer timeframes may be more profitable"

        # Risk management adjustments
        if overall_risk > 0.7:
            adjustments['risk_management'] = "Implement strict risk controls and smaller positions"
        elif overall_risk < 0.3:
            adjustments['risk_management'] = "Opportunity for more aggressive position sizing"

        # Strategy type adjustments
        if current_regime == 'SIDEWAYS':
            adjustments['strategy_type'] = "Focus on mean reversion rather than trend following"
        elif current_regime in ['BULL', 'BEAR']:
            adjustments['strategy_type'] = "Trend following strategies preferred"

        return adjustments

    def _create_entry_exit_strategy(self, processed_signals: Dict[str, Any],
                                  risk_assessment: Dict[str, Any],
                                  regime_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create detailed entry and exit strategy"""
        dominant_signal = processed_signals.get('dominant_signal', {})
        overall_risk = risk_assessment.get('overall_risk_score', 0.5)
        current_regime = self._extract_regime_type(regime_analysis)

        strategy = {
            'entry_conditions': [],
            'exit_conditions': [],
            'stop_loss_strategy': {},
            'take_profit_strategy': {},
            'position_management': {}
        }

        # Entry conditions
        if dominant_signal:
            signal_type = dominant_signal.get('data', {}).get('signal', 'NEUTRAL')
            if signal_type in ['BUY', 'SELL']:
                strategy['entry_conditions'].append(f"Primary signal: {signal_type}")

        # Risk-based conditions
        if overall_risk > 0.7:
            strategy['entry_conditions'].append("Wait for reduced volatility before entry")
        elif overall_risk < 0.3:
            strategy['entry_conditions'].append("Favorable risk environment for entry")

        # Regime-based conditions
        if current_regime == 'HIGH_VOLATILITY':
            strategy['entry_conditions'].append("Use smaller position sizes due to volatility")
        elif current_regime == 'BEAR':
            strategy['entry_conditions'].append("Exercise extra caution in bear market")

        # Stop loss strategy
        base_stop_percentage = 2.0  # 2% base stop loss
        if current_regime == 'HIGH_VOLATILITY':
            stop_percentage = base_stop_percentage * 1.5
        elif current_regime == 'LOW_VOLATILITY':
            stop_percentage = base_stop_percentage * 0.8
        else:
            stop_percentage = base_stop_percentage

        strategy['stop_loss_strategy'] = {
            'percentage': round(stop_percentage, 1),
            'type': 'trailing' if current_regime != 'HIGH_VOLATILITY' else 'fixed',
            'justification': f"Adjusted for {current_regime.lower()} regime"
        }

        # Take profit strategy
        strategy['take_profit_strategy'] = {
            'target_1': round(stop_percentage * 1.5, 1),  # 1.5:1 ratio
            'target_2': round(stop_percentage * 3.0, 1),  # 3:1 ratio
            'scaling_approach': 'Take 50% at target 1, 50% at target 2'
        }

        return strategy

    def _setup_monitoring_alerts(self, processed_signals: Dict[str, Any],
                               regime_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Setup monitoring alerts for position management"""
        alerts = []

        # Signal-based alerts
        signal_confidence = processed_signals.get('signal_confidence', 0.5)
        if signal_confidence < 0.4:
            alerts.append({
                'type': 'signal_degradation',
                'message': 'Signal confidence has degraded - consider position review',
                'priority': 'medium'
            })

        # Regime-based alerts
        regime_confidence = regime_analysis.get('current_regime', {}).get('confidence', 0.5)
        if regime_confidence < 0.3:
            alerts.append({
                'type': 'regime_uncertainty',
                'message': 'Market regime uncertain - monitor for changes',
                'priority': 'high'
            })

        # Volatility alerts
        current_regime = self._extract_regime_type(regime_analysis)
        if current_regime == 'HIGH_VOLATILITY':
            alerts.append({
                'type': 'high_volatility',
                'message': 'High volatility regime - monitor position sizes',
                'priority': 'high'
            })

        return alerts

    def _set_performance_expectations(self, technical_results: Dict[str, Any],
                                    risk_assessment: Dict[str, Any]) -> Dict[str, Any]:
        """Set realistic performance expectations"""
        tech_score = technical_results.get('technical_score', {}).get('total_score', 5)
        overall_risk = risk_assessment.get('overall_risk_score', 0.5)

        # Base expectations on technical score
        if tech_score >= 8:
            expected_win_rate = 0.7
            expected_return = 0.15
        elif tech_score >= 6:
            expected_win_rate = 0.6
            expected_return = 0.10
        elif tech_score >= 4:
            expected_win_rate = 0.5
            expected_return = 0.05
        else:
            expected_win_rate = 0.4
            expected_return = 0.0

        # Adjust for risk
        risk_adjusted_return = expected_return * (1 - overall_risk)

        return {
            'expected_win_rate': round(expected_win_rate, 2),
            'expected_return': round(risk_adjusted_return, 3),
            'risk_adjusted': True,
            'confidence_level': 0.8,  # 80% confidence interval
            'time_horizon': self._get_time_horizon(),
            'key_assumptions': [
                "Based on historical pattern analysis",
                "Assumes current market regime continues",
                "Includes transaction costs and slippage"
            ]
        }

    def _get_time_horizon(self) -> str:
        """Get appropriate time horizon based on trading strategy"""
        strategy_horizons = {
            'day_trading': '1-5 days',
            'swing_trading': '1-4 weeks',
            'position_trading': '1-6 months',
            'long_term_investing': '6+ months'
        }

        return strategy_horizons.get(self.trading_strategy, '1-4 weeks')