"""
Technical Analysis Engine
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from .indicators import TechnicalIndicators, TrendAnalysis
from .pattern_recognizer import PatternRecognizer

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
        self.pattern_recognizer = PatternRecognizer(self.price_data, self.symbol)

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

            # NEW: Market State Analysis
            market_state = self._detect_market_state(latest_values)
            strategy_recommendation = self._get_strategy_recommendation(market_state, latest_values, filtered_signals)
            confidence_score = self._calculate_confidence_score(market_state, latest_values, filtered_signals)

            # NEW: Overextension & Dip Detection (Anti-Doji Protection)
            # Add price_data to indicators for these detections
            indicators_with_price = {**latest_values, 'price_data': self.price_data}
            overextension_analysis = self._detect_overextension(indicators_with_price)
            dip_analysis = self._detect_pullback_opportunity(indicators_with_price)

            # NEW: Falling Knife Detection (ตกต่อเนื่อง vs ตกชั่วคราว)
            falling_knife_analysis = self._detect_falling_knife(indicators_with_price)

            # ปรับ Dip Quality ตาม Falling Knife Risk
            if dip_analysis['is_dip'] and falling_knife_analysis['is_falling_knife']:
                # ถ้าเป็น Dip แต่ก็เป็น Falling Knife ด้วย -> ลดคะแนน
                original_score = dip_analysis['opportunity_score']
                penalty = falling_knife_analysis['risk_score'] * 0.5  # ลดตาม risk
                adjusted_score = max(0, original_score - penalty)

                dip_analysis['opportunity_score'] = int(adjusted_score)
                dip_analysis['falling_knife_penalty'] = int(penalty)

                # ปรับ Quality และ Suggestion
                if adjusted_score < 40:
                    dip_analysis['is_dip'] = False
                    dip_analysis['dip_quality'] = 'POOR'
                    dip_analysis['entry_suggestion'] = f'⚠️ ระวัง! แม้ดูเหมือนจุดช้อน แต่มี Falling Knife Risk ({falling_knife_analysis["risk_level"]}) - {falling_knife_analysis["recommendation"]}'
                elif adjusted_score < 60:
                    dip_analysis['dip_quality'] = 'FAIR'
                    dip_analysis['entry_suggestion'] = f'⚡ ระวัง! มี Falling Knife Risk - {falling_knife_analysis["recommendation"]}'

            # NEW: Pattern Recognition
            pattern_analysis = self.pattern_recognizer.detect_all_patterns()

            # Extract support/resistance for easy access
            support_resistance = latest_values.get('support_resistance', {})
            support_1 = support_resistance.get('support_1')
            resistance_1 = support_resistance.get('resistance_1')

            return {
                'symbol': self.symbol,
                'analysis_date': datetime.now().isoformat(),
                'last_price': latest_values['current_price'],

                # Add support/resistance at top level for Enhanced Features
                'support_1': support_1,
                'resistance_1': resistance_1,

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
                'support_resistance': support_resistance,
                'target_levels': self._calculate_target_levels(latest_values),

                # Adaptability insights
                'adaptability_insights': self._generate_adaptability_insights(current_regime, advanced_analysis),

                # NEW: Market State Strategy Analysis
                'market_state_analysis': {
                    'current_state': market_state,
                    'strategy': strategy_recommendation,
                    'confidence': confidence_score,
                    'overextension': overextension_analysis,  # NEW: ตรวจจับติดดอย
                    'dip_opportunity': dip_analysis,  # NEW: ตรวจจับจุดช้อน
                    'falling_knife': falling_knife_analysis  # NEW: ตรวจจับตกต่อเนื่อง
                },

                # NEW: Pattern Recognition
                'pattern_recognition': pattern_analysis
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

    def _calculate_position_size_for_sl(self,
                                       account_value: float,
                                       entry_price: float,
                                       stop_loss: float,
                                       risk_per_trade_pct: float = 3.0,
                                       max_position_value_pct: float = 20.0) -> Dict[str, Any]:
        """
        คำนวณ Position Size ตาม Stop Loss Distance

        🆕 ตามแนวคิด Stop Loss Hunting:
        - ถ้า SL ห่าง → ลด shares เพื่อให้ความเสี่ยงต่อรอบคงที่
        - ถ้า SL แคบ → เพิ่ม shares ได้

        Args:
            account_value: มูลค่าพอร์ต (บาท)
            entry_price: ราคา entry
            stop_loss: ราคา stop loss
            risk_per_trade_pct: ความเสี่ยงต่อรอบ (% ของพอร์ต) default = 3%
            max_position_value_pct: มูลค่า position สูงสุด (% ของพอร์ต) default = 20%

        Returns:
            Dictionary with position sizing details
        """
        # คำนวณความเสี่ยงต่อหุ้น
        price_risk_per_share = abs(entry_price - stop_loss)
        price_risk_pct = (price_risk_per_share / entry_price) * 100 if entry_price > 0 else 0

        # คำนวณจำนวนเงินที่เสี่ยงต่อรอบ
        risk_amount = account_value * (risk_per_trade_pct / 100)

        # คำนวณจำนวนหุ้นที่ควรซื้อ
        if price_risk_per_share > 0:
            shares = int(risk_amount / price_risk_per_share)
        else:
            shares = 0

        # คำนวณมูลค่า position
        position_value = shares * entry_price
        position_value_pct = (position_value / account_value) * 100 if account_value > 0 else 0

        # เช็คว่า position value ไม่เกิน max (20% ของพอร์ต)
        if position_value_pct > max_position_value_pct:
            # ลด shares ลง
            max_position_value = account_value * (max_position_value_pct / 100)
            shares = int(max_position_value / entry_price)
            position_value = shares * entry_price
            position_value_pct = (position_value / account_value) * 100

            # คำนวณความเสี่ยงจริง (ลดลง)
            actual_risk_amount = shares * price_risk_per_share
            actual_risk_pct = (actual_risk_amount / account_value) * 100

            warning = f"⚠️ Position ถูกจำกัดที่ {max_position_value_pct}% ของพอร์ต (ความเสี่ยงลดเหลือ {actual_risk_pct:.2f}%)"
        else:
            actual_risk_amount = risk_amount
            actual_risk_pct = risk_per_trade_pct
            warning = None

        # สร้าง summary
        return {
            'shares': shares,
            'position_value': round(position_value, 2),
            'position_value_pct': round(position_value_pct, 2),
            'risk_amount': round(actual_risk_amount, 2),
            'risk_pct': round(actual_risk_pct, 2),
            'risk_per_share': round(price_risk_per_share, 2),
            'price_risk_pct': round(price_risk_pct, 2),
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'warning': warning,
            'calculation_method': 'Fixed Risk per Trade (based on SL distance)',
            'max_loss_if_hit_sl': round(actual_risk_amount, 2)
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

        # Support/Resistance Signals (🆕 v5.0: includes 52W high/low)
        support_resistance = indicators.get('support_resistance', {})
        if support_resistance:
            s1 = support_resistance.get('support_1')
            r1 = support_resistance.get('resistance_1')
            s52w = support_resistance.get('support_52w')  # 🆕 v5.0
            r52w = support_resistance.get('resistance_52w')  # 🆕 v5.0

            # 🆕 v5.0: Check 52W levels first (stronger psychological levels)
            if s52w and current_price <= s52w * 1.02:  # Within 2% of 52W low
                signals['sr_signal'] = {'signal': 'BUY', 'strength': 'Very Strong', 'reason': f'Price near 52-week low at {s52w:.2f} (strong support)'}
            elif r52w and current_price >= r52w * 0.98:  # Within 2% of 52W high
                signals['sr_signal'] = {'signal': 'SELL', 'strength': 'Very Strong', 'reason': f'Price near 52-week high at {r52w:.2f} (strong resistance)'}
            # Recent support/resistance (20-day levels)
            elif s1 and current_price <= s1 * 1.01:  # Within 1% of support
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
        """
        Score support/resistance levels (0-2 points)

        🆕 v5.0: Now includes "Very Strong" scoring for 52W levels
        """
        if not sr_signal:
            return 1.0

        signal = sr_signal.get('signal')
        strength = sr_signal.get('strength')

        if signal == 'BUY':
            if strength == 'Very Strong':  # 🆕 v5.0: 52W low
                return 2.0
            elif strength == 'Strong':
                return 1.8
            else:
                return 1.5
        elif signal == 'SELL':
            if strength == 'Very Strong':  # 🆕 v5.0: 52W high
                return 0.0
            elif strength == 'Strong':
                return 0.2
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

    def _detect_volatility_class(self, atr: float, current_price: float) -> str:
        """
        🆕 v7.3.2: Dynamic volatility classification using adaptive thresholds

        Uses both absolute thresholds AND relative percentile ranking for better accuracy.
        This approach adapts to changing market regimes while maintaining reasonable baselines.

        Args:
            atr: Average True Range
            current_price: Current stock price

        Returns:
            'HIGH', 'MEDIUM', or 'LOW'
        """
        if current_price <= 0 or atr <= 0:
            return 'MEDIUM'  # Default fallback

        atr_pct = (atr / current_price) * 100

        # Calculate historical ATR percentiles if we have enough data
        if len(self.price_data) >= 60:  # Need at least 60 days
            try:
                # Calculate rolling ATR% for last 252 days (1 year) or available data
                lookback = min(252, len(self.price_data))
                historical_atr_pcts = []

                for i in range(lookback):
                    if i >= len(self.price_data):
                        break
                    hist_price = self.price_data['close'].iloc[-(i+1)]
                    # Calculate ATR for each historical point (simplified)
                    if hist_price > 0:
                        hist_atr_pct = (atr / hist_price) * 100
                        historical_atr_pcts.append(hist_atr_pct)

                if len(historical_atr_pcts) >= 30:
                    # Calculate percentile rank of current ATR%
                    percentile = (sum(1 for x in historical_atr_pcts if x < atr_pct) / len(historical_atr_pcts)) * 100

                    # 🆕 v7.3.2: Hybrid approach - use BOTH percentile AND absolute thresholds
                    # This balances adaptation to market regime with realistic volatility assessment

                    # Absolute thresholds (baseline - prevents extreme misclassification)
                    absolute_class = None
                    if atr_pct >= 5.0:  # Very high absolute volatility
                        absolute_class = 'HIGH'
                    elif atr_pct < 0.8:  # Very low absolute volatility
                        absolute_class = 'LOW'

                    # Percentile-based classification (adaptive to market regime)
                    if percentile >= 70:  # Top 30% = HIGH
                        percentile_class = 'HIGH'
                    elif percentile >= 35:  # Middle 35% = MEDIUM
                        percentile_class = 'MEDIUM'
                    else:  # Bottom 35% = LOW
                        percentile_class = 'LOW'

                    # Use absolute class if defined, otherwise use percentile
                    if absolute_class:
                        volatility_class = absolute_class
                    else:
                        volatility_class = percentile_class

                    logger.info(f"📊 Volatility (Adaptive): ATR={atr:.2f}, Price=${current_price:.2f}, ATR%={atr_pct:.2f}%, Percentile={percentile:.1f}% → {volatility_class}")
                    return volatility_class

            except Exception as e:
                logger.warning(f"Percentile calculation failed: {e}, falling back to absolute thresholds")

        # Fallback to absolute thresholds if not enough data or calculation failed
        # 🆕 v7.3.2: Slightly relaxed thresholds (was 4.0/1.5)
        if atr_pct >= 4.5:
            volatility_class = 'HIGH'
        elif atr_pct >= 2.0:
            volatility_class = 'MEDIUM'
        else:
            volatility_class = 'LOW'

        logger.info(f"📊 Volatility (Absolute): ATR={atr:.2f}, Price=${current_price:.2f}, ATR%={atr_pct:.2f}% → {volatility_class}")
        return volatility_class

    def _get_dynamic_atr_multipliers(self, market_state: str, volatility_class: str) -> Dict[str, Any]:
        """
        Get dynamic ATR multipliers based on market state and volatility class

        🆕 v6.0: Volatility-aware multipliers for better TP/SL targeting

        Logic:
        - HIGH volatility: More aggressive TPs (wider targets), tighter SLs (accept volatility)
        - MEDIUM volatility: Standard multipliers (balanced)
        - LOW volatility: More conservative TPs (closer targets), wider SLs (less volatility)

        Args:
            market_state: TRENDING_BULLISH, SIDEWAY, or BEARISH
            volatility_class: HIGH, MEDIUM, or LOW

        Returns:
            Dict with tp1_mult, tp2_mult, tp3_mult, sl_mult
        """

        # Define multipliers by market state and volatility
        multipliers = {
            'TRENDING_BULLISH': {
                'HIGH': {'tp1': 2.5, 'tp2': 3.0, 'tp3': 3.5, 'sl': 1.5},    # Aggressive
                'MEDIUM': {'tp1': 2.0, 'tp2': 2.5, 'tp3': 3.0, 'sl': 2.0},  # Balanced
                'LOW': {'tp1': 1.5, 'tp2': 2.0, 'tp3': 2.5, 'sl': 2.5}      # Conservative
            },
            'SIDEWAY': {
                'HIGH': {'tp1': 2.0, 'tp2': 2.5, 'tp3': 3.0, 'sl': 1.5},    # Moderate
                'MEDIUM': {'tp1': 1.5, 'tp2': 2.0, 'tp3': 2.5, 'sl': 2.0},  # Balanced
                'LOW': {'tp1': 1.2, 'tp2': 1.5, 'tp3': 2.0, 'sl': 2.5}      # Conservative
            },
            'BEARISH': {
                'HIGH': {'tp1': 2.0, 'tp2': 2.5, 'tp3': 3.0, 'sl': 1.5},    # Quick profits
                'MEDIUM': {'tp1': 1.5, 'tp2': 2.0, 'tp3': 2.5, 'sl': 2.0},  # Balanced
                'LOW': {'tp1': 1.2, 'tp2': 1.5, 'tp3': 2.0, 'sl': 2.5}      # Very conservative
            }
        }

        # Get multipliers for this combination
        state_multipliers = multipliers.get(market_state, multipliers['SIDEWAY'])
        vol_multipliers = state_multipliers.get(volatility_class, state_multipliers['MEDIUM'])

        logger.info(f"📊 Dynamic ATR Multipliers ({market_state}, {volatility_class}): "
                   f"TP={vol_multipliers['tp1']:.1f}x/{vol_multipliers['tp2']:.1f}x/{vol_multipliers['tp3']:.1f}x, "
                   f"SL={vol_multipliers['sl']:.1f}x")

        return vol_multipliers

    def _detect_swing_points(self, lookback: int = 20) -> Dict[str, Any]:
        """
        Detect swing highs and lows using lookback window

        Swing High = Highest high in lookback period where price declined after
        Swing Low = Lowest low in lookback period where price rallied after

        Args:
            lookback: Number of bars to look back for swing detection (default: 20)

        Returns:
            Dict with swing_high, swing_low, swing_high_idx, swing_low_idx
        """
        try:
            # Get recent price data
            if len(self.price_data) < lookback + 5:
                # Not enough data, use what we have
                recent_data = self.price_data
            else:
                recent_data = self.price_data.tail(lookback + 5)

            # Ensure we have High and Low columns (case-insensitive)
            high_col = 'High' if 'High' in recent_data.columns else 'high'
            low_col = 'Low' if 'Low' in recent_data.columns else 'low'
            close_col = 'Close' if 'Close' in recent_data.columns else 'close'

            if high_col not in recent_data.columns or low_col not in recent_data.columns:
                # Fallback to Close if High/Low not available
                recent_data[high_col] = recent_data[close_col]
                recent_data[low_col] = recent_data[close_col]

            highs = recent_data[high_col].values
            lows = recent_data[low_col].values

            # Find swing high (highest point with lower highs on both sides)
            swing_high_idx = 0
            swing_high = highs[0]

            for i in range(2, len(highs) - 2):
                # Check if this is a local maximum
                if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                    if highs[i] > swing_high:
                        swing_high = highs[i]
                        swing_high_idx = i

            # If no swing high found, use recent high
            if swing_high_idx == 0:
                swing_high_idx = np.argmax(highs)
                swing_high = highs[swing_high_idx]

            # Find swing low (lowest point with higher lows on both sides)
            swing_low_idx = 0
            swing_low = lows[0]

            for i in range(2, len(lows) - 2):
                # Check if this is a local minimum
                if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                    if swing_low == lows[0] or lows[i] < swing_low:
                        swing_low = lows[i]
                        swing_low_idx = i

            # If no swing low found, use recent low
            if swing_low_idx == 0:
                swing_low_idx = np.argmin(lows)
                swing_low = lows[swing_low_idx]

            return {
                'swing_high': float(swing_high),
                'swing_low': float(swing_low),
                'swing_high_idx': int(swing_high_idx),
                'swing_low_idx': int(swing_low_idx),
                'lookback_bars': len(recent_data)
            }

        except Exception as e:
            logger.warning(f"Error detecting swing points: {e}")
            # Fallback: use simple high/low from recent data
            close_col = 'Close' if 'Close' in self.price_data.columns else 'close'
            current_price = self.price_data[close_col].iloc[-1]
            return {
                'swing_high': float(current_price * 1.05),
                'swing_low': float(current_price * 0.95),
                'swing_high_idx': 0,
                'swing_low_idx': 0,
                'lookback_bars': 0
            }

    def _calculate_fibonacci_levels(self,
                                    swing_high: float,
                                    swing_low: float,
                                    direction: str = 'retracement') -> Dict[str, float]:
        """
        Calculate Fibonacci levels for entries (retracement) or targets (extension)

        Retracement levels (for entry zones in uptrend):
        - 0.236 (23.6%) - Aggressive entry
        - 0.382 (38.2%) - Aggressive-moderate entry
        - 0.500 (50.0%) - Moderate entry (most common)
        - 0.618 (61.8%) - Conservative entry (golden ratio)
        - 0.786 (78.6%) - Very conservative entry

        Extension levels (for take profit targets):
        - 1.000 (100%) - Swing high breakout
        - 1.272 (127.2%) - Moderate target
        - 1.414 (141.4%) - Strong target
        - 1.618 (161.8%) - Aggressive target (golden ratio)
        - 2.000 (200%) - Very aggressive target
        - 2.618 (261.8%) - Extreme target

        Args:
            swing_high: Recent swing high price
            swing_low: Recent swing low price
            direction: 'retracement' for entries, 'extension' for targets

        Returns:
            Dictionary of Fibonacci levels
        """
        swing_range = swing_high - swing_low

        if direction == 'retracement':
            # Retracement from swing_high (for entries in uptrend)
            return {
                'fib_0.236': swing_high - (swing_range * 0.236),
                'fib_0.382': swing_high - (swing_range * 0.382),
                'fib_0.500': swing_high - (swing_range * 0.500),
                'fib_0.618': swing_high - (swing_range * 0.618),
                'fib_0.786': swing_high - (swing_range * 0.786)
            }
        elif direction == 'extension':
            # Extension from swing_low (for targets in uptrend)
            return {
                'fib_1.000': swing_low + swing_range,
                'fib_1.272': swing_low + (swing_range * 1.272),
                'fib_1.414': swing_low + (swing_range * 1.414),
                'fib_1.618': swing_low + (swing_range * 1.618),
                'fib_2.000': swing_low + (swing_range * 2.000),
                'fib_2.618': swing_low + (swing_range * 2.618)
            }
        else:
            return {}

    def _check_immediate_entry_conditions(self,
                                         current_price: float,
                                         recommended_entry: float,
                                         support: float,
                                         resistance: float,
                                         indicators: Dict[str, Any],
                                         market_state: str) -> Dict[str, Any]:
        """
        Check if conditions warrant IMMEDIATE entry at current price
        instead of waiting for pullback to entry zone

        Immediate Entry Conditions:
        1. Already at or very close to entry zone (< 1% distance)
        2. Strong breakout with volume spike (> 150%)
        3. Strong momentum (RSI 50-70, MACD positive)
        4. Gap up opening (> 2% gap)
        5. Near support in sideways (< 1% from support)
        6. Reversal confirmation (MACD cross + RSI bounce)

        Args:
            current_price: Current stock price
            recommended_entry: Calculated entry price from Fibonacci
            support: Support level
            resistance: Resistance level
            indicators: Technical indicators dict
            market_state: Market state (TRENDING_BULLISH, SIDEWAY, BEARISH)

        Returns:
            Dictionary with immediate_entry (bool) and reasons (list)
        """
        immediate_entry = False
        reasons = []
        confidence_score = 0

        # Get indicators
        volume = indicators.get('volume', 0)
        volume_sma = indicators.get('volume_sma_20', 1)
        rsi = indicators.get('rsi', 50)
        macd_line = indicators.get('macd_line', 0)
        macd_signal = indicators.get('macd_signal', 0)
        macd_histogram = indicators.get('macd_histogram', 0)

        # Calculate distance to entry zone
        distance_to_entry_pct = abs((current_price - recommended_entry) / current_price) * 100
        distance_to_support_pct = abs((current_price - support) / support) * 100 if support > 0 else 100
        distance_to_resistance_pct = abs((resistance - current_price) / current_price) * 100 if resistance > 0 else 100

        # Condition 1: Already in Entry Zone (< 1% distance)
        if distance_to_entry_pct < 1.0:
            immediate_entry = True
            confidence_score += 30
            reasons.append(f"✅ Already at entry zone (distance: {distance_to_entry_pct:.2f}% only)")

        # Condition 2: Strong Breakout with Volume
        volume_ratio = volume / volume_sma if volume_sma > 0 else 1
        if market_state == 'TRENDING_BULLISH':
            if current_price > resistance and volume_ratio > 1.5:
                immediate_entry = True
                confidence_score += 25
                reasons.append(f"✅ Breakout above resistance with volume spike ({volume_ratio:.1f}x)")

            # Strong momentum continuation
            if rsi > 55 and rsi < 75 and macd_histogram > 0 and volume_ratio > 1.2:
                immediate_entry = True
                confidence_score += 20
                reasons.append(f"✅ Strong momentum (RSI: {rsi:.0f}, Volume: {volume_ratio:.1f}x)")

        # Condition 3: Near Support in Sideways (< 1.5% from support)
        if market_state == 'SIDEWAY':
            if distance_to_support_pct < 1.5 and rsi < 50:
                immediate_entry = True
                confidence_score += 25
                reasons.append(f"✅ Near support in sideways (distance: {distance_to_support_pct:.2f}%)")

        # Condition 4: Reversal Confirmation (MACD cross + RSI bounce)
        if market_state in ['BEARISH', 'SIDEWAY']:
            # MACD just crossed up (histogram positive and increasing)
            if macd_line > macd_signal and macd_histogram > 0:
                # RSI bounced from oversold
                if rsi >= 35 and rsi <= 50:
                    immediate_entry = True
                    confidence_score += 25
                    reasons.append(f"✅ Reversal confirmed (MACD cross + RSI bounce from {rsi:.0f})")

        # Condition 5: Already very close to recommended entry (< 0.5%)
        if distance_to_entry_pct < 0.5:
            immediate_entry = True
            confidence_score += 20
            reasons.append(f"✅ Too close to wait ({distance_to_entry_pct:.2f}% from entry)")

        # Condition 6: Strong trend continuation (don't wait for pullback)
        if market_state == 'TRENDING_BULLISH':
            # Check if price consistently above entry zone (already pulled back and bounced)
            if current_price > recommended_entry and distance_to_entry_pct < 2.0:
                if volume_ratio > 1.0 and rsi > 50:
                    immediate_entry = True
                    confidence_score += 15
                    reasons.append(f"✅ Already bounced from pullback zone (current > entry by {distance_to_entry_pct:.2f}%)")

        # If no conditions met
        if not reasons:
            reasons.append(f"⏳ Wait for pullback to entry zone (distance: {distance_to_entry_pct:.2f}%)")

        return {
            'immediate_entry': immediate_entry,
            'confidence_score': min(100, confidence_score),
            'reasons': reasons,
            'distance_to_entry_pct': distance_to_entry_pct,
            'volume_ratio': volume_ratio,
            'action': 'ENTER_NOW' if immediate_entry else 'WAIT_FOR_PULLBACK'
        }

    def _calculate_smart_entry_zone(self,
                                    current_price: float,
                                    swing_high: float,
                                    swing_low: float,
                                    ema_50: float,
                                    market_state: str,
                                    support: float,
                                    resistance: float) -> Dict[str, Any]:
        """
        Calculate intelligent entry zone based on market structure

        TRENDING_BULLISH:
        - Use Fibonacci retracement from swing high
        - Entry 1 (Aggressive): 38.2% retracement
        - Entry 2 (Moderate): 50.0% retracement (RECOMMENDED)
        - Entry 3 (Conservative): 61.8% retracement
        - Must be above EMA50 for confirmation

        SIDEWAY:
        - Use support level with buffer
        - Entry zone: Support to Support + 2%

        BEARISH:
        - Wait for reversal confirmation
        - Entry after MACD cross + RSI > 30

        Args:
            current_price: Current stock price
            swing_high: Recent swing high
            swing_low: Recent swing low
            ema_50: 50-period EMA
            market_state: TRENDING_BULLISH, SIDEWAY, or BEARISH
            support: Support level
            resistance: Resistance level

        Returns:
            Dictionary with entry_aggressive, entry_moderate, entry_conservative,
            recommended_entry, entry_range, distance_from_current_pct
        """
        if market_state == 'TRENDING_BULLISH':
            # Calculate Fibonacci retracement levels
            fib_levels = self._calculate_fibonacci_levels(swing_high, swing_low, 'retracement')

            entry_aggressive = fib_levels['fib_0.382']
            entry_moderate = fib_levels['fib_0.500']
            entry_conservative = fib_levels['fib_0.618']

            # Choose recommended entry based on position relative to EMA50
            if current_price > ema_50:
                # Price above EMA50 - prefer aggressive entry (closer to current price)
                recommended = entry_aggressive
                entry_reason = "ราคาเหนือ EMA50 → Entry aggressive ที่ Fib 38.2%"
            elif current_price > entry_moderate:
                # Price between moderate and EMA50 - use moderate entry
                recommended = entry_moderate
                entry_reason = "ราคาใกล้ EMA50 → Entry moderate ที่ Fib 50%"
            else:
                # Price below moderate - wait for better entry
                recommended = entry_conservative
                entry_reason = "ราคาต่ำกว่า Fib 50% → Entry conservative ที่ Fib 61.8%"

            # Entry range: ±1% from recommended
            entry_range = [recommended * 0.99, recommended * 1.01]
            distance_pct = ((recommended - current_price) / current_price) * 100

            return {
                'entry_aggressive': round(entry_aggressive, 2),
                'entry_moderate': round(entry_moderate, 2),
                'entry_conservative': round(entry_conservative, 2),
                'recommended_entry': round(recommended, 2),
                'entry_range': [round(entry_range[0], 2), round(entry_range[1], 2)],
                'distance_from_current_pct': round(distance_pct, 2),
                'entry_reason': entry_reason,
                'calculation_method': 'Fibonacci Retracement'
            }

        elif market_state == 'SIDEWAY':
            # Use support level with small buffer
            entry_aggressive = support * 1.005  # 0.5% above support
            entry_moderate = support * 1.010   # 1.0% above support
            entry_conservative = support * 0.995  # 0.5% below support

            # Recommended entry: slightly above support
            recommended = entry_moderate
            entry_range = [support * 0.99, support * 1.02]
            distance_pct = ((recommended - current_price) / current_price) * 100

            return {
                'entry_aggressive': round(entry_aggressive, 2),
                'entry_moderate': round(entry_moderate, 2),
                'entry_conservative': round(entry_conservative, 2),
                'recommended_entry': round(recommended, 2),
                'entry_range': [round(entry_range[0], 2), round(entry_range[1], 2)],
                'distance_from_current_pct': round(distance_pct, 2),
                'entry_reason': f"Sideway → Entry ที่แนวรับ ${support:.2f} + 1%",
                'calculation_method': 'Support Level'
            }

        else:  # BEARISH
            # Conservative entry after reversal confirmation
            entry_aggressive = current_price * 0.97  # 3% below current
            entry_moderate = current_price * 0.95    # 5% below current
            entry_conservative = current_price * 0.93  # 7% below current

            recommended = entry_moderate
            entry_range = [current_price * 0.94, current_price * 0.96]
            distance_pct = ((recommended - current_price) / current_price) * 100

            return {
                'entry_aggressive': round(entry_aggressive, 2),
                'entry_moderate': round(entry_moderate, 2),
                'entry_conservative': round(entry_conservative, 2),
                'recommended_entry': round(recommended, 2),
                'entry_range': [round(entry_range[0], 2), round(entry_range[1], 2)],
                'distance_from_current_pct': round(distance_pct, 2),
                'entry_reason': "Bearish → รอ reversal + entry 5% ต่ำกว่า current",
                'calculation_method': 'Percentage Below Current'
            }

    def _calculate_intelligent_tp_levels(self,
                                        entry_price: float,
                                        swing_high: float,
                                        swing_low: float,
                                        resistance: float,
                                        market_state: str,
                                        atr: float) -> Dict[str, Any]:
        """
        Calculate intelligent Take Profit levels using Fibonacci extensions

        TRENDING_BULLISH:
        - TP1 (Conservative): Fib 1.0 (100% - swing high breakout)
        - TP2 (Moderate): Fib 1.272 (127.2%)
        - TP3 (Aggressive): Fib 1.618 (161.8% - golden ratio)

        SIDEWAY:
        - TP1: Resistance - 1%
        - TP2: Resistance + 1%

        BEARISH:
        - TP1: Entry + (ATR * 2) - Quick profit target

        Args:
            entry_price: Recommended entry price
            swing_high: Recent swing high
            swing_low: Recent swing low
            resistance: Resistance level
            market_state: Market state
            atr: Average True Range

        Returns:
            Dictionary with tp1, tp2, tp3, recommended_tp, calculation_method
        """
        if market_state == 'TRENDING_BULLISH':
            # Calculate Fibonacci extension levels
            fib_ext = self._calculate_fibonacci_levels(swing_high, swing_low, 'extension')

            tp1 = fib_ext['fib_1.000']  # Swing high breakout
            tp2 = fib_ext['fib_1.272']  # Moderate target
            tp3 = fib_ext['fib_1.618']  # Aggressive target

            # Use resistance as cap if it's below Fib levels
            if resistance < tp2:
                tp2 = resistance * 0.99  # 1% before resistance
                tp3 = resistance * 1.02  # 2% after resistance break

            # Recommended: Fib 1.272 (balance between conservative and aggressive)
            recommended = tp2

            return {
                'tp1': round(tp1, 2),
                'tp2': round(tp2, 2),
                'tp3': round(tp3, 2),
                'recommended_tp': round(recommended, 2),
                'tp1_return_pct': round(((tp1 - entry_price) / entry_price) * 100, 2),
                'tp2_return_pct': round(((tp2 - entry_price) / entry_price) * 100, 2),
                'tp3_return_pct': round(((tp3 - entry_price) / entry_price) * 100, 2),
                'calculation_method': 'Fibonacci Extension'
            }

        elif market_state == 'SIDEWAY':
            tp1 = resistance * 0.99  # 1% before resistance (conservative)
            tp2 = resistance * 1.01  # 1% after resistance break (aggressive)
            tp3 = resistance * 1.03  # 3% after resistance (very aggressive)

            recommended = tp1  # Conservative in sideways

            return {
                'tp1': round(tp1, 2),
                'tp2': round(tp2, 2),
                'tp3': round(tp3, 2),
                'recommended_tp': round(recommended, 2),
                'tp1_return_pct': round(((tp1 - entry_price) / entry_price) * 100, 2),
                'tp2_return_pct': round(((tp2 - entry_price) / entry_price) * 100, 2),
                'tp3_return_pct': round(((tp3 - entry_price) / entry_price) * 100, 2),
                'calculation_method': 'Resistance Level'
            }

        else:  # BEARISH
            tp1 = entry_price + (atr * 2)  # Quick profit (2 ATR)
            tp2 = entry_price + (atr * 3)  # Moderate profit (3 ATR)
            tp3 = entry_price + (atr * 4)  # Aggressive profit (4 ATR)

            recommended = tp1  # Quick profit in bearish

            return {
                'tp1': round(tp1, 2),
                'tp2': round(tp2, 2),
                'tp3': round(tp3, 2),
                'recommended_tp': round(recommended, 2),
                'tp1_return_pct': round(((tp1 - entry_price) / entry_price) * 100, 2),
                'tp2_return_pct': round(((tp2 - entry_price) / entry_price) * 100, 2),
                'tp3_return_pct': round(((tp3 - entry_price) / entry_price) * 100, 2),
                'calculation_method': 'ATR Multiple'
            }

    # ==================== Anti-Stop Hunt Helper Functions ====================

    def _get_adaptive_atr_multiplier(self, current_price: float, atr: float,
                                     historical_volatility: Optional[float] = None) -> float:
        """
        Calculate adaptive ATR multiplier based on current volatility

        ตามแนวคิด Stop Loss Hunting:
        - ตลาดผันผวนมาก → ใช้ buffer มากขึ้น
        - ตลาดสงบ → ใช้ buffer ปกติ

        Args:
            current_price: ราคาปัจจุบัน
            atr: Average True Range
            historical_volatility: ATR เฉลี่ยในอดีต (optional)

        Returns:
            ATR multiplier (1.5 - 3.0)
        """
        # คำนวณ volatility % ของราคา
        volatility_pct = (atr / current_price) * 100 if current_price > 0 else 2.0

        # ถ้ามี historical volatility ให้เปรียบเทียบ
        if historical_volatility and historical_volatility > 0:
            volatility_ratio = volatility_pct / historical_volatility

            if volatility_ratio > 1.5:  # ผันผวนมากกว่าปกติ 50%
                return 2.5
            elif volatility_ratio > 1.2:  # ผันผวนมากกว่าปกติ 20%
                return 2.0
            else:
                return 1.5

        # ถ้าไม่มี historical ให้ดูจาก absolute volatility
        if volatility_pct > 5.0:  # ผันผวนมากกว่า 5%
            return 2.5
        elif volatility_pct > 3.0:  # ผันผวน 3-5%
            return 2.0
        else:
            return 1.5  # ผันผวนต่ำกว่า 3%

    def _avoid_round_numbers(self, price: float, atr: float, direction: str = 'down') -> float:
        """
        ปรับราคาให้ห่างจากเลขกลมที่มี Stop Loss กองอยู่เยอะ

        ตามแนวคิด Stop Loss Hunting:
        - เลขกลม (50.00, 100.00) มี SL เยอะ = เป้าหมายของสถาบัน
        - ควรวาง SL ห่างออกไป (เช่น 48.73 แทน 49.00)

        Args:
            price: ราคาที่คำนวณได้
            atr: Average True Range
            direction: 'down' = ปรับลง, 'up' = ปรับขึ้น

        Returns:
            ราคาที่ปรับแล้ว (ไม่เป็นเลขกลม)
        """
        # ตรวจสอบว่าเป็นเลขกลมหรือไม่
        buffer = atr * 0.3  # เผื่อ 30% ของ ATR

        # เลขกลมที่ต้องหลีก: .00, .50
        decimal_part = price - int(price)

        # ถ้าใกล้ .00 (0.95-1.00 or 0.00-0.05)
        if decimal_part >= 0.95 or decimal_part <= 0.05:
            if direction == 'down':
                # ปรับลงห่าง (เช่น 50.00 → 49.27)
                adjusted = int(price) - (buffer if decimal_part <= 0.05 else 1 - buffer)
            else:
                # ปรับขึ้นห่าง (เช่น 50.00 → 50.73)
                adjusted = int(price) + (1 + buffer if decimal_part <= 0.05 else buffer)
            return round(adjusted, 2)

        # ถ้าใกล้ .50 (0.45-0.55)
        if 0.45 <= decimal_part <= 0.55:
            if direction == 'down':
                # ปรับลงห่าง (เช่น 50.50 → 50.23)
                adjusted = int(price) + 0.50 - buffer
            else:
                # ปรับขึ้นห่าง (เช่น 50.50 → 50.77)
                adjusted = int(price) + 0.50 + buffer
            return round(adjusted, 2)

        # ถ้าไม่ใกล้เลขกลม ใช้ได้เลย
        return round(price, 2)

    def _avoid_ma_levels(self, stop_loss: float, ma_levels: Dict[str, float],
                        atr: float, direction: str = 'down') -> float:
        """
        ปรับ Stop Loss ให้ห่างจาก MA levels ที่สำคัญ

        ตามแนวคิด Stop Loss Hunting:
        - MA ที่นิยม (50, 200) มี SL กองอยู่เยอะ
        - ควรวาง SL ห่างจาก MA อย่างน้อย 0.5 ATR

        Args:
            stop_loss: Stop Loss ที่คำนวณได้
            ma_levels: Dictionary ของ MA levels
            atr: Average True Range
            direction: 'down' = ปรับลง, 'up' = ปรับขึ้น

        Returns:
            Stop Loss ที่ปรับแล้ว
        """
        critical_mas = ['sma_50', 'sma_200', 'ema_50', 'ema_200']
        min_buffer = atr * 0.5  # ระยะห่างขั้นต่ำ

        adjusted_sl = stop_loss

        for ma_name in critical_mas:
            ma_value = ma_levels.get(ma_name)

            if ma_value is None or ma_value == 0:
                continue

            # ตรวจสอบว่า SL ใกล้ MA เกินไปหรือไม่
            distance = abs(stop_loss - ma_value)

            if distance < min_buffer:
                # ปรับ SL ให้ห่างจาก MA
                if direction == 'down':
                    # Stop Loss ควรอยู่ด้านล่าง MA
                    if stop_loss > ma_value:
                        adjusted_sl = min(adjusted_sl, ma_value - min_buffer)
                    else:
                        adjusted_sl = min(adjusted_sl, stop_loss - min_buffer)
                else:
                    # Stop Loss ควรอยู่ด้านบน MA
                    if stop_loss < ma_value:
                        adjusted_sl = max(adjusted_sl, ma_value + min_buffer)
                    else:
                        adjusted_sl = max(adjusted_sl, stop_loss + min_buffer)

        return round(adjusted_sl, 2)

    def _validate_stop_loss(self, stop_loss: float, entry_price: float,
                           support_level: float, ma_levels: Dict[str, float],
                           atr: float, current_price: float) -> Dict[str, Any]:
        """
        Validate Stop Loss ก่อน return - ตาม Checklist จากแนวคิด Stop Loss Hunting

        Checklist:
        ☐ ไม่ได้วางที่เลขกลม
        ☐ ไม่ได้วางใกล้ support/resistance เกินไป
        ☐ ไม่ได้วางบน MA สำคัญ
        ☐ ห่างจาก entry ตาม ATR
        ☐ ความเสี่ยงไม่เกิน 10%

        Returns:
            Dictionary with validation result และ warnings
        """
        warnings = []
        suggestions = []

        # Check 1: เลขกลม
        decimal_part = stop_loss - int(stop_loss)
        if (decimal_part >= 0.95 or decimal_part <= 0.05 or
            (0.45 <= decimal_part <= 0.55)):
            warnings.append("⚠️ SL อยู่ที่เลขกลม - เสี่ยงโดน Stop Hunt")
            suggestions.append(f"แนะนำปรับเป็น {self._avoid_round_numbers(stop_loss, atr, 'down')}")

        # Check 2: ใกล้ support เกินไป
        buffer = atr * 0.5
        if support_level and abs(stop_loss - support_level) < buffer:
            warnings.append(f"⚠️ SL ใกล้ support เกินไป - ควรห่าง {buffer:.2f}")
            suggestions.append(f"แนะนำวางที่ {support_level - buffer:.2f}")

        # Check 3: บน MA สำคัญ
        critical_mas = ['sma_50', 'sma_200', 'ema_50', 'ema_200']
        for ma_name in critical_mas:
            ma_value = ma_levels.get(ma_name, 0)
            if ma_value and abs(stop_loss - ma_value) < atr * 0.3:
                warnings.append(f"⚠️ SL ใกล้ {ma_name.upper()} ({ma_value:.2f}) - อาจโดนล่า")

        # Check 4: ระยะจาก entry
        sl_distance = abs(entry_price - stop_loss)
        min_distance = atr * 1.5
        if sl_distance < min_distance:
            warnings.append(f"⚠️ SL แคบเกินไป - ควรห่างอย่างน้อย {min_distance:.2f}")
            suggestions.append(f"แนะนำวางที่ {entry_price - min_distance:.2f}")

        # Check 5: ความเสี่ยงต่อรอบ
        risk_pct = ((entry_price - stop_loss) / entry_price) * 100
        if risk_pct > 10:
            warnings.append(f"⚠️ ความเสี่ยง {risk_pct:.1f}% สูงเกินไป (>10%)")
            suggestions.append("พิจารณาลด position size แทน")

        return {
            'valid': len(warnings) == 0,
            'warnings': warnings,
            'suggestions': suggestions,
            'stop_loss': stop_loss,
            'risk_pct': risk_pct
        }

    # ==================== End of Anti-Stop Hunt Helpers ====================

    def _calculate_intelligent_stop_loss(self,
                                        entry_price: float,
                                        swing_low: float,
                                        support: float,
                                        market_state: str,
                                        atr: float,
                                        indicators: Optional[Dict[str, Any]] = None,
                                        enable_anti_hunt: bool = True) -> Dict[str, Any]:
        """
        Calculate intelligent Stop Loss based on market structure

        🆕 ENHANCED WITH ANTI-STOP HUNT PROTECTION
        Based on "Stop Loss Hunting" insights from professional traders

        TRENDING_BULLISH:
        - Place SL below swing low with ADAPTIVE ATR buffer (ปรับตาม volatility)
        - Avoid round numbers and MA levels

        SIDEWAY:
        - Place SL below support with ATR-based buffer (ไม่ใช้ 2% แบบตายตัว)
        - Avoid psychological levels

        BEARISH:
        - Adaptive SL based on current volatility
        - Protect against excessive slippage

        Args:
            entry_price: Recommended entry price
            swing_low: Recent swing low
            support: Support level
            market_state: Market state
            atr: Average True Range
            indicators: Optional indicators dict (for MA levels, current_price)
            enable_anti_hunt: Enable anti-stop hunt protection (default: True)

        Returns:
            Dictionary with stop_loss, risk_pct, calculation_method, warnings
        """
        # Extract data from indicators (if available)
        current_price = entry_price
        ma_levels = {}

        if indicators:
            current_price = indicators.get('current_price', entry_price)

            # Extract MA levels for anti-hunt logic
            ma_levels = {
                'sma_50': indicators.get('sma_50'),
                'sma_200': indicators.get('sma_200'),
                'ema_50': indicators.get('ema_50'),
                'ema_200': indicators.get('ema_200')
            }

        # Get adaptive ATR multiplier based on volatility
        if enable_anti_hunt:
            atr_multiplier = self._get_adaptive_atr_multiplier(current_price, atr)
        else:
            atr_multiplier = 1.5  # Default

        # Calculate Stop Loss based on market state
        if market_state == 'TRENDING_BULLISH':
            # Structure-based SL: Below swing low with ADAPTIVE ATR buffer
            stop_loss = swing_low - (atr * atr_multiplier)

            # 🆕 v7.2: TIGHTER risk management - Cap at 7% max risk (was 10%)
            max_risk_pct = 7.0  # Maximum 7% risk (tighter than before)
            min_sl = entry_price * (1 - max_risk_pct / 100)

            # 🆕 v7.2: If SL is too far (swing_low is very far from entry), use ATR-based SL instead
            swing_low_risk_pct = ((entry_price - stop_loss) / entry_price) * 100 if entry_price > 0 else 0

            if swing_low_risk_pct > max_risk_pct:
                # Swing low is too far - use ATR-based SL from entry instead
                stop_loss = entry_price - (atr * atr_multiplier)
                calculation_method = f'ATR-based SL ({atr_multiplier}x) - Swing low too far'
                logger.info(f"⚠️ Swing low SL would be {swing_low_risk_pct:.1f}% risk - using ATR-based SL instead")
            else:
                calculation_method = f'Below Swing Low + Adaptive ATR ({atr_multiplier}x)'

            # Final safety check
            if stop_loss < min_sl:
                stop_loss = min_sl
                calculation_method += ' (capped at 7% max risk)'

            atr_buffer = round(atr * atr_multiplier, 2)

        elif market_state == 'SIDEWAY':
            # 🆕 v7.2: TIGHTER risk management for sideway - Cap at 5% max risk
            max_risk_pct = 5.0  # Maximum 5% risk for sideway (very tight)

            # Below support with ATR buffer (more dynamic than fixed 2%)
            stop_loss = support - (atr * atr_multiplier * 0.75)  # 0.75 = tighter for sideway

            # Calculate risk percentage
            sideway_risk_pct = ((entry_price - stop_loss) / entry_price) * 100 if entry_price > 0 else 0

            # 🆕 v7.2: FORCE cap at max_risk_pct
            if sideway_risk_pct > max_risk_pct:
                # Too much risk - cap SL at max_risk_pct
                stop_loss = entry_price * (1 - max_risk_pct / 100)
                calculation_method = f'ATR-based SL (capped at {max_risk_pct}% max risk)'
                logger.info(f"⚠️ Sideway SL would be {sideway_risk_pct:.1f}% risk - capped at {max_risk_pct}%")
            else:
                calculation_method = f'Below Support + ATR Buffer ({atr_multiplier * 0.75}x)'

            atr_buffer = round(atr * atr_multiplier * 0.75, 2)

        else:  # BEARISH
            # 🆕 v7.2: TIGHTER risk management for bearish - Cap at 7% max risk
            # Adaptive SL in bearish market
            bearish_multiplier = min(atr_multiplier * 1.2, 3.0)  # Slightly wider for bearish
            stop_loss = entry_price - (atr * bearish_multiplier)

            # 🆕 v7.2: Cap max risk for bearish
            max_risk_pct = 7.0  # Maximum 7% risk
            min_sl = entry_price * (1 - max_risk_pct / 100)

            if stop_loss < min_sl:
                stop_loss = min_sl
                calculation_method = f'ATR-based Adaptive ({bearish_multiplier}x, capped at 7% max risk)'
            else:
                calculation_method = f'ATR-based Adaptive ({bearish_multiplier}x)'

            atr_buffer = round(atr * bearish_multiplier, 2)

        # 🆕 ANTI-STOP HUNT PROTECTION
        original_sl = stop_loss
        warnings = []

        if enable_anti_hunt:
            # 1. Avoid round numbers
            stop_loss = self._avoid_round_numbers(stop_loss, atr, direction='down')

            if abs(stop_loss - original_sl) > 0.01:
                warnings.append(f"Adjusted SL to avoid round number: {original_sl:.2f} → {stop_loss:.2f}")

            # 2. Avoid MA levels (if indicators provided)
            if ma_levels and any(ma_levels.values()):
                stop_loss_before_ma = stop_loss
                stop_loss = self._avoid_ma_levels(stop_loss, ma_levels, atr, direction='down')

                if abs(stop_loss - stop_loss_before_ma) > 0.01:
                    warnings.append(f"Adjusted SL to avoid MA levels: {stop_loss_before_ma:.2f} → {stop_loss:.2f}")

        # 🆕 v7.2: FINAL SAFETY CAP - Re-apply max risk after anti-hunt protection
        # Anti-hunt may have moved SL too far, need to re-cap
        if market_state == 'SIDEWAY':
            max_allowed_risk = 5.0  # Sideway max risk
        elif market_state == 'TRENDING_BULLISH':
            max_allowed_risk = 7.0  # Bullish max risk
        else:  # BEARISH
            max_allowed_risk = 7.0  # Bearish max risk

        min_allowed_sl = entry_price * (1 - max_allowed_risk / 100)
        if stop_loss < min_allowed_sl:
            sl_before_final_cap = stop_loss
            stop_loss = min_allowed_sl
            logger.info(f"🛡️ FINAL CAP: SL {sl_before_final_cap:.2f} → {stop_loss:.2f} (max {max_allowed_risk}% risk)")
            calculation_method += f' [final capped at {max_allowed_risk}%]'

        # Calculate final risk percentage
        risk_pct = ((entry_price - stop_loss) / entry_price) * 100 if entry_price > 0 else 0

        # 🆕 VALIDATION
        validation = None
        if enable_anti_hunt and indicators:
            validation = self._validate_stop_loss(
                stop_loss=stop_loss,
                entry_price=entry_price,
                support_level=support,
                ma_levels=ma_levels,
                atr=atr,
                current_price=current_price
            )

            # Add validation warnings
            if validation['warnings']:
                warnings.extend(validation['warnings'])

        # Build result
        result = {
            'stop_loss': round(stop_loss, 2),
            'risk_pct': round(risk_pct, 2),
            'calculation_method': calculation_method,
            'atr_buffer': atr_buffer,
            'atr_multiplier': round(atr_multiplier, 2),
        }

        # Add market-specific info
        if market_state == 'TRENDING_BULLISH':
            result['swing_low_used'] = round(swing_low, 2)
        elif market_state == 'SIDEWAY':
            result['support_used'] = round(support, 2)
        else:
            result['atr_used'] = round(atr, 2)

        # Add anti-hunt info
        if enable_anti_hunt:
            result['anti_hunt_enabled'] = True
            result['original_sl'] = round(original_sl, 2) if abs(stop_loss - original_sl) > 0.01 else None
            result['adjustments'] = warnings if warnings else []

            if validation:
                result['validation'] = {
                    'valid': validation['valid'],
                    'warnings': validation['warnings'],
                    'suggestions': validation['suggestions']
                }

        return result

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
        """
        Calculate basic support and resistance levels

        🆕 v5.0: Now includes 52-week high/low as key S/R levels
        """
        try:
            if len(close) < 20:
                return {'support_1': None, 'resistance_1': None,
                        'support_52w': None, 'resistance_52w': None}

            # Recent lows and highs (20 days)
            recent_data = close.tail(20)
            support_1 = recent_data.min()
            resistance_1 = recent_data.max()

            # 🆕 v5.0: 52-week high/low (important psychological levels)
            # Use 252 trading days ~= 1 year, fallback to available data
            lookback_52w = min(252, len(close))
            data_52w = close.tail(lookback_52w)
            support_52w = data_52w.min()  # 52-week low
            resistance_52w = data_52w.max()  # 52-week high

            return {
                'support_1': support_1,
                'resistance_1': resistance_1,
                'support_52w': support_52w,      # 🆕 v5.0
                'resistance_52w': resistance_52w  # 🆕 v5.0
            }

        except Exception:
            return {'support_1': None, 'resistance_1': None,
                    'support_52w': None, 'resistance_52w': None}

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

    def _detect_overextension(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        ตรวจจับว่าราคาพุ่งขึ้นเกินจนอันตราย (Overextended Rally)
        สำหรับป้องกันการติดดอย

        Criteria (RELAXED for real-world detection):
        1. RSI > 70 (extreme overbought)
        2. ราคาห่าง SMA20 มากกว่า 5%
        3. ราคาขึ้น > 10% ใน 5 วัน (rapid rally)
        4. ราคาเหนือ Upper Bollinger Band

        Returns:
            {
                'is_overextended': True/False,
                'risk_level': 'EXTREME/HIGH/MODERATE/LOW',
                'severity_score': 0-100,
                'warnings': [...],
                'recommendation': 'คำแนะนำ',
                'details': {...}
            }
        """
        try:
            current_price = indicators.get('current_price')
            rsi = indicators.get('rsi', 50)
            sma_20 = indicators.get('sma_20')
            bb_upper = indicators.get('bb_upper')

            # คำนวณ 5-day price change
            price_data = indicators.get('price_data')
            price_5d_change = 0
            if price_data is not None and len(price_data) >= 6:
                price_5d_ago = price_data['close'].iloc[-6]
                price_5d_change = ((current_price - price_5d_ago) / price_5d_ago) * 100

            # เก็บคะแนนความรุนแรง
            severity_score = 0
            warnings = []
            details = {}

            # 1. เช็ค RSI extreme overbought (RELAXED: start at 70)
            if rsi > 80:
                severity_score += 35
                warnings.append(f'RSI {rsi:.1f} (extreme overbought > 80)')
                details['rsi_extreme'] = True
            elif rsi > 75:
                severity_score += 28
                warnings.append(f'RSI {rsi:.1f} (very overbought > 75)')
                details['rsi_very_high'] = True
            elif rsi > 70:
                severity_score += 20
                warnings.append(f'RSI {rsi:.1f} (overbought > 70)')
                details['rsi_high'] = True

            # 2. เช็คระยะห่างจาก SMA20 (RELAXED: start at 5%)
            if sma_20:
                price_vs_sma20_pct = ((current_price - sma_20) / sma_20) * 100
                details['price_vs_sma20_pct'] = round(price_vs_sma20_pct, 2)

                if price_vs_sma20_pct > 10:
                    severity_score += 30
                    warnings.append(f'ราคาห่าง SMA20 ถึง {price_vs_sma20_pct:.1f}% (มากเกิน)')
                    details['far_from_sma20'] = True
                elif price_vs_sma20_pct > 7:
                    severity_score += 22
                    warnings.append(f'ราคาห่าง SMA20 {price_vs_sma20_pct:.1f}% (ค่อนข้างมาก)')
                    details['above_sma20_far'] = True
                elif price_vs_sma20_pct > 5:
                    severity_score += 15
                    warnings.append(f'ราคาห่าง SMA20 {price_vs_sma20_pct:.1f}% (เริ่มห่าง)')
                    details['above_sma20'] = True

            # 3. เช็คการขึ้นเร็วเกินไป (rapid rally - RELAXED: start at 10%)
            details['price_5d_change'] = round(price_5d_change, 2)
            if price_5d_change > 20:
                severity_score += 28
                warnings.append(f'ราคาพุ่งขึ้น {price_5d_change:.1f}% ใน 5 วัน (rapid rally)')
                details['rapid_rally'] = True
            elif price_5d_change > 15:
                severity_score += 20
                warnings.append(f'ราคาขึ้นเร็ว {price_5d_change:.1f}% ใน 5 วัน')
                details['fast_rally'] = True
            elif price_5d_change > 10:
                severity_score += 12
                warnings.append(f'ราคาขึ้น {price_5d_change:.1f}% ใน 5 วัน (เริ่มเร็ว)')
                details['moderate_rally'] = True

            # 4. เช็คราคาเหนือ Upper Bollinger Band
            if bb_upper and current_price > bb_upper:
                price_vs_bb = ((current_price - bb_upper) / bb_upper) * 100
                severity_score += 15
                warnings.append(f'ราคาเหนือ Upper BB {price_vs_bb:.1f}%')
                details['above_bb_upper'] = True

            # กำหนด Risk Level (RELAXED: trigger at 35 instead of 40)
            is_overextended = severity_score >= 35

            if severity_score >= 70:
                risk_level = 'EXTREME'
                recommendation = '🔴 อย่าซื้อตอนนี้! ราคาขึ้นเกินจนอันตราย - เข้าแล้วติดดอยแน่'
            elif severity_score >= 50:
                risk_level = 'HIGH'
                recommendation = '⚠️ ระวังติดดอย! ราคาขึ้นมามาก - รอ pullback ลงมา 5-10% ก่อน'
            elif severity_score >= 35:
                risk_level = 'MODERATE'
                recommendation = '⚡ ระวัง! ราคาเริ่มขึ้นเกิน - ควรรอจังหวะที่ดีกว่า'
            else:
                risk_level = 'LOW'
                recommendation = 'ราคายังไม่ขึ้นเกิน - สามารถพิจารณาเข้าได้'

            return {
                'is_overextended': is_overextended,
                'risk_level': risk_level,
                'severity_score': severity_score,
                'warnings': warnings,
                'recommendation': recommendation,
                'details': details,
                'expected_pullback': 'ราคาอาจปรับฐานลง 5-10% ภายใน 2-5 วัน' if is_overextended else None
            }

        except Exception as e:
            logger.warning(f"Overextension detection failed: {e}")
            return {
                'is_overextended': False,
                'risk_level': 'UNKNOWN',
                'severity_score': 0,
                'warnings': [],
                'recommendation': 'ไม่สามารถตรวจสอบได้'
            }

    def _detect_pullback_opportunity(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        ตรวจจับจุดช้อนที่ดี (Buying the Dip / Pullback)

        Criteria (RELAXED for real-world detection):
        1. ราคาลงมา 5-25% จากจุดสูงสุด 20 วัน (wider range)
        2. RSI ลงมา 30-55 (wider oversold recovery zone)
        3. ราคาใกล้ Support (±2-3%)
        4. แรงขายเริ่มลดลง

        Returns:
            {
                'is_dip': True/False,
                'dip_quality': 'EXCELLENT/GOOD/FAIR/POOR',
                'opportunity_score': 0-100,
                'entry_suggestion': 'คำแนะนำ',
                'details': {...}
            }
        """
        try:
            current_price = indicators.get('current_price')
            rsi = indicators.get('rsi', 50)
            support = indicators.get('support')
            volume = indicators.get('current_volume')
            volume_sma = indicators.get('volume_sma')

            # หาจุดสูงสุด 20 วัน
            price_data = indicators.get('price_data')
            pullback_pct = 0
            recent_high = current_price

            if price_data is not None and len(price_data) >= 20:
                recent_high = price_data['high'].tail(20).max()
                pullback_pct = ((current_price - recent_high) / recent_high) * 100

            opportunity_score = 0
            positives = []
            details = {}

            # 1. เช็คขนาดของ pullback (RELAXED: 5-25% range, better scoring)
            details['pullback_from_high_pct'] = round(pullback_pct, 2)
            if pullback_pct < -25:
                # ลงมากเกินไป อาจมีปัญหา แต่ยังให้คะแนนบ้าง
                opportunity_score += 15
                positives.append(f'ลงมา {abs(pullback_pct):.1f}% (ลงมาก อาจมีปัญหา)')
                details['deep_pullback'] = True
            elif -25 <= pullback_pct < -15:
                opportunity_score += 38
                positives.append(f'ลงมา {abs(pullback_pct):.1f}% จากจุดสูงสุด (จุดช้อนดีมาก)')
                details['excellent_pullback'] = True
            elif -15 <= pullback_pct < -10:
                opportunity_score += 35
                positives.append(f'ลงมา {abs(pullback_pct):.1f}% จากจุดสูงสุด (จุดช้อนดี)')
                details['ideal_pullback'] = True
            elif -10 <= pullback_pct < -5:
                opportunity_score += 28
                positives.append(f'ลงมา {abs(pullback_pct):.1f}% (pullback ปานกลาง)')
                details['moderate_pullback'] = True

            # 2. เช็ค RSI oversold recovery (RELAXED: 30-55 range)
            details['rsi'] = round(rsi, 1)
            if 38 <= rsi <= 48:
                opportunity_score += 32
                positives.append(f'RSI {rsi:.1f} (oversold recovery zone - ดีเด่น)')
                details['rsi_recovery_excellent'] = True
            elif 30 <= rsi <= 55:
                opportunity_score += 25
                positives.append(f'RSI {rsi:.1f} (โซนกลับตัว)')
                details['rsi_recovery'] = True
            elif rsi < 30:
                opportunity_score += 18
                positives.append(f'RSI {rsi:.1f} (oversold มาก)')
                details['rsi_oversold'] = True

            # 3. เช็คระยะห่างจาก Support
            if support:
                distance_to_support = abs((current_price - support) / support) * 100
                details['distance_to_support_pct'] = round(distance_to_support, 2)

                if distance_to_support <= 2:
                    opportunity_score += 25
                    positives.append(f'ใกล้ Support มาก (ห่างเพียง {distance_to_support:.1f}%)')
                    details['near_support'] = True
                elif distance_to_support <= 3:
                    opportunity_score += 15
                    positives.append(f'ค่อนข้างใกล้ Support ({distance_to_support:.1f}%)')
                    details['close_to_support'] = True

            # 4. เช็ค Volume (selling exhaustion)
            if volume and volume_sma and volume_sma > 0:
                volume_ratio = volume / volume_sma
                details['volume_ratio'] = round(volume_ratio, 2)

                if volume_ratio < 0.8:
                    opportunity_score += 10
                    positives.append(f'Volume ลดลง ({volume_ratio:.1f}x - selling exhaustion)')
                    details['volume_decreasing'] = True

            # กำหนด Quality (RELAXED: trigger at 40 instead of 50)
            is_dip = opportunity_score >= 40

            if opportunity_score >= 75:
                dip_quality = 'EXCELLENT'
                entry_suggestion = '💰 เข้าได้เลย! จุดช้อนคุณภาพดีมาก - โอกาสดีดขึ้นสูง'
                expected_bounce = 'คาดว่าราคาอาจดีดขึ้น 5-10% ใน 2-5 วัน'
            elif opportunity_score >= 60:
                dip_quality = 'GOOD'
                entry_suggestion = '✅ จุดช้อนที่ดี - เข้าได้ โอกาสดีดขึ้นปานกลาง'
                expected_bounce = 'คาดว่าราคาอาจดีดขึ้น 3-7% ใน 3-7 วัน'
            elif opportunity_score >= 40:
                dip_quality = 'FAIR'
                entry_suggestion = '⚡ จุดช้อนพอใช้ได้ - เข้าได้แต่ระวัง'
                expected_bounce = 'คาดว่าราคาอาจดีดขึ้น 2-5% ใน 5-10 วัน'
            else:
                dip_quality = 'POOR'
                entry_suggestion = 'ยังไม่ใช่จุดช้อนที่ดี - รอดูต่อ'
                expected_bounce = None

            return {
                'is_dip': is_dip,
                'dip_quality': dip_quality,
                'opportunity_score': opportunity_score,
                'entry_suggestion': entry_suggestion,
                'expected_bounce': expected_bounce,
                'positives': positives,
                'details': details
            }

        except Exception as e:
            logger.warning(f"Pullback detection failed: {e}")
            return {
                'is_dip': False,
                'dip_quality': 'UNKNOWN',
                'opportunity_score': 0,
                'entry_suggestion': 'ไม่สามารถตรวจสอบได้'
            }

    def _detect_falling_knife(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        ตรวจจับ Falling Knife (ตกต่อเนื่อง) vs Healthy Pullback (ตกชั่วคราว)

        เช็ค 5 อย่าง:
        1. Trend Context - Uptrend pullback (ดี) vs Downtrend breakdown (แย่)
        2. Decline Velocity - ตกเร็วมาก (panic) vs ตกช้า (correction)
        3. Volume Pattern - Capitulation (ดี) vs Distribution (แย่)
        4. MA Structure - เหนือ MA200 (แข็งแรง) vs ต่ำกว่าทุก MA (อ่อนแอ)
        5. Price Structure - Higher Lows (uptrend) vs Lower Lows (downtrend)

        Returns:
            {
                'is_falling_knife': True/False,
                'risk_level': 'EXTREME/HIGH/MODERATE/LOW',
                'risk_score': 0-100,
                'warnings': [...],
                'reasons': [...],
                'recommendation': 'คำแนะนำ'
            }
        """
        try:
            price_data = indicators.get('price_data')
            current_price = indicators.get('current_price')

            if price_data is None or len(price_data) < 60:
                return {'is_falling_knife': False, 'risk_level': 'UNKNOWN', 'risk_score': 0}

            risk_score = 0
            warnings = []
            reasons = []
            details = {}

            # 1. TREND CONTEXT - เช็คเทรนด์ระยะยาว
            ma_50 = indicators.get('sma_50')
            ma_100 = price_data['close'].tail(100).mean() if len(price_data) >= 100 else None
            ma_200 = price_data['close'].tail(200).mean() if len(price_data) >= 200 else None

            # เช็คราคาเทียบกับ MA
            below_ma50 = current_price < ma_50 if ma_50 else False
            below_ma100 = current_price < ma_100 if ma_100 else False
            below_ma200 = current_price < ma_200 if ma_200 else False

            if below_ma200 and below_ma100 and below_ma50:
                risk_score += 30
                warnings.append('ราคาต่ำกว่า MA50/100/200 ทั้งหมด (โครงสร้างอ่อนแอมาก)')
                details['weak_ma_structure'] = True
            elif below_ma100 and below_ma50:
                risk_score += 20
                warnings.append('ราคาต่ำกว่า MA50/100 (เทรนด์อ่อนแอ)')
                details['below_major_mas'] = True
            elif below_ma50:
                risk_score += 10
                warnings.append('ราคาต่ำกว่า MA50 (ระวังเทรนด์กลับ)')
                details['below_ma50'] = True
            else:
                reasons.append('ราคายังเหนือ MA50 (โครงสร้างยังแข็งแรง)')
                details['above_ma50'] = True

            # 2. DECLINE VELOCITY - ความเร็วในการตก
            if len(price_data) >= 10:
                last_10_closes = price_data['close'].tail(10)
                daily_changes = last_10_closes.pct_change().dropna() * 100

                # หาจำนวนวันติดลบ
                negative_days = (daily_changes < 0).sum()
                avg_decline = daily_changes[daily_changes < 0].mean() if len(daily_changes[daily_changes < 0]) > 0 else 0

                details['negative_days_last_10'] = int(negative_days)
                details['avg_daily_decline'] = round(avg_decline, 2)

                if negative_days >= 7 and avg_decline < -2.5:
                    risk_score += 35
                    warnings.append(f'ตกหนักติดต่อกัน {negative_days}/10 วัน เฉลี่ย {avg_decline:.1f}%/วัน (Panic Selling)')
                    details['panic_selling'] = True
                elif negative_days >= 6 and avg_decline < -2:
                    risk_score += 25
                    warnings.append(f'ตกติดต่อกัน {negative_days}/10 วัน (Selling Pressure สูง)')
                    details['high_selling_pressure'] = True
                elif negative_days >= 5 and avg_decline < -1.5:
                    risk_score += 15
                    warnings.append(f'ตกติดต่อกัน {negative_days}/10 วัน')
                    details['moderate_selling'] = True
                else:
                    reasons.append(f'การตกไม่รุนแรง ({negative_days}/10 วันลบ)')
                    details['gradual_decline'] = True

            # 3. VOLUME PATTERN - แพทเทิร์น Volume
            volume = indicators.get('current_volume')
            volume_sma = indicators.get('volume_sma')

            if volume and volume_sma and volume_sma > 0:
                volume_ratio = volume / volume_sma
                details['volume_ratio'] = round(volume_ratio, 2)

                # เช็ค Volume Spike ขณะตก
                if len(price_data) >= 5:
                    last_5_closes = price_data['close'].tail(5)
                    price_declining = (last_5_closes.iloc[-1] < last_5_closes.iloc[0])

                    if volume_ratio > 2.5 and price_declining:
                        # Volume spike ขณะตก อาจเป็น Capitulation (ดี)
                        reasons.append(f'Volume Spike {volume_ratio:.1f}x ขณะตก (อาจเป็น Capitulation - แรงขายหมด)')
                        details['possible_capitulation'] = True
                        risk_score -= 10  # ลดความเสี่ยง
                    elif volume_ratio > 1.5 and price_declining:
                        # Volume สูงต่อเนื่องขณะตก = Distribution (แย่)
                        recent_volumes = price_data['volume'].tail(10)
                        high_volume_days = (recent_volumes > volume_sma * 1.3).sum()

                        if high_volume_days >= 5:
                            risk_score += 20
                            warnings.append('Volume สูงต่อเนื่องขณะตก (Distribution - คนเทขาย)')
                            details['distribution_pattern'] = True

            # 4. PRICE STRUCTURE - เช็ค Higher Lows vs Lower Lows
            if len(price_data) >= 60:
                # หา Swing Lows ล่าสุด 3 จุด
                lows = price_data['low'].tail(60)

                # หา Local Lows (ใช้ rolling min)
                swing_lows = []
                for i in range(10, len(lows) - 10, 10):
                    local_min = lows.iloc[i-10:i+10].min()
                    if lows.iloc[i] == local_min:
                        swing_lows.append(local_min)

                if len(swing_lows) >= 2:
                    # เช็คว่า Lows ต่ำลงเรื่อยๆ หรือไม่
                    lower_lows = all(swing_lows[i] > swing_lows[i+1] for i in range(len(swing_lows)-1))
                    higher_lows = all(swing_lows[i] < swing_lows[i+1] for i in range(len(swing_lows)-1))

                    details['swing_lows_count'] = len(swing_lows)

                    if lower_lows:
                        risk_score += 25
                        warnings.append('ทำ Lower Lows ติดต่อกัน (Downtrend ชัดเจน)')
                        details['lower_lows_pattern'] = True
                    elif higher_lows:
                        reasons.append('ทำ Higher Lows (Uptrend Pullback)')
                        details['higher_lows_pattern'] = True
                        risk_score -= 15  # ลดความเสี่ยง

            # 5. RECENT BREAKDOWN - เช็คทะลุ Support สำคัญ
            support = indicators.get('support')
            if support:
                distance_below_support = ((current_price - support) / support) * 100
                details['distance_from_support_pct'] = round(distance_below_support, 2)

                if distance_below_support < -5:
                    risk_score += 15
                    warnings.append(f'ทะลุ Support ไปแล้ว {abs(distance_below_support):.1f}% (Breakdown)')
                    details['support_breakdown'] = True
                elif distance_below_support < -2:
                    risk_score += 8
                    warnings.append('ใกล้ทะลุ Support')
                    details['near_support_break'] = True

            # คำนวณระดับความเสี่ยง
            # RELAXED: 40 เพื่อจับ MODERATE risk ที่มี warnings ชัดเจน (เช่น COIN = 45)
            is_falling_knife = risk_score >= 40

            if risk_score >= 80:
                risk_level = 'EXTREME'
                recommendation = '🔪 FALLING KNIFE! อย่าช้อน - ตกต่อเนื่องแน่ รอให้หยุดตกก่อน'
            elif risk_score >= 60:
                risk_level = 'HIGH'
                recommendation = '⚠️ เสี่ยงสูง! อาจตกต่อ - ถ้าจะเข้ารอให้เห็นสัญญาณกลับตัวก่อน'
            elif risk_score >= 40:
                risk_level = 'MODERATE'
                recommendation = '⚡ เสี่ยงปานกลาง - ระวังอาจตกต่อ ควรรอดูอีก 2-3 วัน'
            else:
                risk_level = 'LOW'
                recommendation = '✅ Healthy Pullback - ไม่ใช่ Falling Knife ช้อนได้ถ้าสัญญาณดี'

            return {
                'is_falling_knife': is_falling_knife,
                'risk_level': risk_level,
                'risk_score': risk_score,
                'warnings': warnings,
                'reasons': reasons,
                'recommendation': recommendation,
                'details': details
            }

        except Exception as e:
            logger.warning(f"Falling knife detection failed: {e}")
            return {
                'is_falling_knife': False,
                'risk_level': 'UNKNOWN',
                'risk_score': 0,
                'warnings': [],
                'reasons': [],
                'recommendation': 'ไม่สามารถตรวจสอบได้'
            }

    def _detect_market_state(self, indicators: Dict[str, Any]) -> str:
        """
        ตรวจสอบสภาวะตลาดปัจจุบัน

        Returns:
            'TRENDING_BULLISH', 'SIDEWAY', หรือ 'BEARISH'
        """
        try:
            current_price = indicators['current_price']
            ema_10 = indicators.get('ema_10') or indicators.get('sma_20')  # Fallback to SMA20
            ema_30 = indicators.get('ema_30') or indicators.get('sma_50')  # Fallback to SMA50
            volume = indicators.get('current_volume')
            volume_sma = indicators.get('volume_sma')
            atr = indicators.get('atr')

            # ตรวจสอบ Trend จาก EMA
            if ema_10 and ema_30:
                # Bullish: EMA10 > EMA30 และราคา > EMA
                if ema_10 > ema_30 and current_price > ema_10:
                    # ตรวจสอบ Volume ยืนยัน
                    if volume and volume_sma and volume > volume_sma:
                        return 'TRENDING_BULLISH'
                    else:
                        # Volume ไม่ยืนยัน อาจเป็น Sideway
                        return 'SIDEWAY'

                # Bearish: EMA10 < EMA30 และราคา < EMA
                elif ema_10 < ema_30 and current_price < ema_10:
                    return 'BEARISH'

                # Sideway: EMA ใกล้กัน หรือราคาอยู่ระหว่าง EMA
                else:
                    return 'SIDEWAY'

            # ถ้าไม่มี EMA ให้ดูจาก ATR และ Price movement
            if atr and current_price:
                volatility_pct = (atr / current_price) * 100
                if volatility_pct < 1.5:
                    return 'SIDEWAY'  # Low volatility = Sideway

            return 'SIDEWAY'  # Default

        except Exception as e:
            logger.warning(f"Market state detection failed: {e}")
            return 'SIDEWAY'

    def _get_strategy_recommendation(self, market_state: str, indicators: Dict[str, Any],
                                    signals: Dict[str, Any]) -> Dict[str, Any]:
        """
        แนะนำ Strategy ตามสภาวะตลาด

        Args:
            market_state: สภาวะตลาด (TRENDING_BULLISH, SIDEWAY, BEARISH)
            indicators: ค่า indicators
            signals: สัญญาณต่างๆ

        Returns:
            Strategy recommendation พร้อมเงื่อนไขเข้า/ออก
        """
        try:
            current_price = indicators['current_price']
            ema_10 = indicators.get('ema_10') or indicators.get('sma_20', current_price)
            ema_30 = indicators.get('ema_30') or indicators.get('sma_50', current_price)
            rsi = indicators.get('rsi', 50)
            volume = indicators.get('current_volume', 0)
            volume_sma = indicators.get('volume_sma', 1)
            support = indicators.get('support_resistance', {}).get('support_1', current_price * 0.98)
            resistance = indicators.get('support_resistance', {}).get('resistance_1', current_price * 1.02)
            macd_line = indicators.get('macd_line', 0)
            macd_signal = indicators.get('macd_signal', 0)
            bb_upper = indicators.get('bb_upper', current_price * 1.02)
            bb_lower = indicators.get('bb_lower', current_price * 0.98)

            if market_state == 'TRENDING_BULLISH':
                # Strategy: EMA Cross + Volume
                entry_conditions = []
                exit_conditions = []
                warnings = []

                # Entry conditions
                if ema_10 > ema_30:
                    entry_conditions.append({
                        'condition': f'EMA10 ({ema_10:.2f}) > EMA30 ({ema_30:.2f})',
                        'status': '✅',
                        'reason': 'แนวโน้มขาขึ้น'
                    })
                else:
                    entry_conditions.append({
                        'condition': f'EMA10 ({ema_10:.2f}) < EMA30 ({ema_30:.2f})',
                        'status': '❌',
                        'reason': 'รอ EMA ตัดขึ้น'
                    })

                volume_ratio = volume / volume_sma if volume_sma > 0 else 1
                if volume > volume_sma:
                    entry_conditions.append({
                        'condition': f'Volume ({volume_ratio:.1f}x) > SMA5',
                        'status': '✅',
                        'reason': 'แรงซื้อจริง'
                    })
                else:
                    entry_conditions.append({
                        'condition': f'Volume ({volume_ratio:.1f}x) < SMA5',
                        'status': '⚠️',
                        'reason': 'Volume อ่อน รอยืนยัน'
                    })

                if current_price > ema_10 and current_price > ema_30:
                    entry_conditions.append({
                        'condition': f'ราคา ({current_price:.2f}) > EMA ทั้งสอง',
                        'status': '✅',
                        'reason': 'ยืนยัน trend'
                    })

                # Exit conditions
                exit_conditions.append({
                    'condition': 'EMA10 ตัดลง EMA30',
                    'status': '❌' if ema_10 < ema_30 else '✗',
                    'reason': 'Trend กลับ'
                })

                if rsi > 70:
                    exit_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) > 70',
                        'status': '⚠️',
                        'reason': 'Overbought'
                    })
                    warnings.append(f'RSI ({rsi:.0f}) ใกล้ overbought → ระวังปรับฐาน')
                else:
                    exit_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) < 70',
                        'status': '✗',
                        'reason': f'ปกติ (ตอนนี้ {rsi:.0f})'
                    })

                exit_conditions.append({
                    'condition': f'ราคาหลุด EMA30 ({ema_30:.2f})',
                    'status': '❌' if current_price < ema_30 else '✗',
                    'reason': 'แนวรับสำคัญหลุด'
                })

                # Trading plan - INTELLIGENT CALCULATION (v5.0)
                atr = indicators.get('atr', current_price * 0.02)

                # Detect volatility class early (before using it)
                volatility_class = self._detect_volatility_class(atr, current_price)

                # Step 1: Detect swing points
                swing_points = self._detect_swing_points(lookback=20)
                swing_high = swing_points['swing_high']
                swing_low = swing_points['swing_low']

                # Step 2: Calculate smart entry zone using Fibonacci
                entry_analysis = self._calculate_smart_entry_zone(
                    current_price=current_price,
                    swing_high=swing_high,
                    swing_low=swing_low,
                    ema_50=ema_30,  # Use EMA30 as proxy for EMA50
                    market_state='TRENDING_BULLISH',
                    support=support,
                    resistance=resistance
                )

                # Step 2.5: Check if immediate entry is warranted
                immediate_entry_check = self._check_immediate_entry_conditions(
                    current_price=current_price,
                    recommended_entry=entry_analysis['recommended_entry'],
                    support=support,
                    resistance=resistance,
                    indicators=indicators,
                    market_state='TRENDING_BULLISH'
                )

                # Use current price if immediate entry, otherwise use recommended entry
                if immediate_entry_check['immediate_entry']:
                    entry_price = current_price
                    entry_range = [current_price * 0.995, current_price * 1.005]
                    entry_analysis['entry_reason'] = f"IMMEDIATE ENTRY: {', '.join(immediate_entry_check['reasons'])}"
                    entry_analysis['calculation_method'] = 'Immediate Entry (Current Price)'
                else:
                    entry_price = entry_analysis['recommended_entry']
                    entry_range = entry_analysis['entry_range']

                # Step 3: Calculate intelligent TP levels
                # For immediate entry, use ATR-based TP from current price
                # For pullback entry, use Fibonacci extension
                if immediate_entry_check['immediate_entry']:
                    # Immediate entry: ATR-based TP from current price
                    logger.info(f"🎯 IMMEDIATE ENTRY detected - Using ATR-based TP from entry ${entry_price:.2f}, ATR=${atr:.2f}")

                    # 🆕 v6.0: Get dynamic multipliers based on volatility
                    multipliers = self._get_dynamic_atr_multipliers('TRENDING_BULLISH', volatility_class)

                    tp1 = entry_price + (atr * multipliers['tp1'])
                    tp2 = entry_price + (atr * multipliers['tp2'])
                    tp3 = entry_price + (atr * multipliers['tp3'])
                    logger.info(f"   Calculated TP1=${tp1:.2f}, TP2=${tp2:.2f}, TP3=${tp3:.2f}")

                    # Cap at resistance if nearby (but only if it doesn't make TP < entry!)
                    if resistance > entry_price and resistance < tp2:
                        tp2_capped = resistance * 0.99
                        # Only apply cap if it doesn't make TP < entry
                        if tp2_capped > entry_price:
                            logger.info(f"   Capping TP2 at resistance: ${tp2:.2f} → ${tp2_capped:.2f}")
                            tp2 = tp2_capped
                            tp3 = resistance * 1.02
                        else:
                            logger.info(f"   ⚠️ Resistance too close! Keeping uncapped ATR-based TP")

                    tp_analysis = {
                        'tp1': round(tp1, 2),
                        'tp2': round(tp2, 2),
                        'tp3': round(tp3, 2),
                        'recommended_tp': round(tp2, 2),
                        'tp1_return_pct': round(((tp1 - entry_price) / entry_price) * 100, 2),
                        'tp2_return_pct': round(((tp2 - entry_price) / entry_price) * 100, 2),
                        'tp3_return_pct': round(((tp3 - entry_price) / entry_price) * 100, 2),
                        'calculation_method': 'ATR Multiple (Immediate Entry)'
                    }
                else:
                    # Pullback entry: Fibonacci extension
                    tp_analysis = self._calculate_intelligent_tp_levels(
                        entry_price=entry_price,
                        swing_high=swing_high,
                        swing_low=swing_low,
                        resistance=resistance,
                        market_state='TRENDING_BULLISH',
                        atr=atr
                    )

                take_profit = tp_analysis['recommended_tp']

                # Step 4: Calculate intelligent SL below swing low (with Anti-Hunt Protection)
                sl_analysis = self._calculate_intelligent_stop_loss(
                    entry_price=entry_price,
                    swing_low=swing_low,
                    support=support,
                    market_state='TRENDING_BULLISH',
                    atr=atr,
                    indicators=indicators,  # 🆕 ส่ง indicators เพื่อใช้ anti-hunt logic
                    enable_anti_hunt=True   # 🆕 เปิดใช้ anti-hunt protection
                )

                stop_loss = sl_analysis['stop_loss']

                # Overall Action Signal สำหรับ TRENDING_BULLISH
                volume_ratio = volume / volume_sma if volume_sma > 0 else 1

                # Entry Readiness Score สำหรับ Trending
                # คำนวณจาก: EMA alignment + Volume + Price position
                ema_score = 100 if ema_10 > ema_30 else 0
                price_score = 100 if current_price > ema_10 else max(0, 50 - abs((current_price - ema_10) / ema_10) * 100)
                volume_score = min(100, volume_ratio * 50)  # 2.0x = 100, 1.0x = 50
                entry_readiness = (ema_score * 0.4 + price_score * 0.3 + volume_score * 0.3)

                # คำนวณระยะห่างจาก EMA (เพื่อให้ข้อมูลเชิงตัวเลข)
                price_above_ema10 = current_price - ema_10
                price_above_ema10_pct = ((current_price - ema_10) / ema_10) * 100 if ema_10 > 0 else 0

                if ema_10 > ema_30 and current_price > ema_10 and volume_ratio > 1.2:
                    # Perfect: Trend + Volume + Price
                    action_signal = 'BUY_NOW'
                    action_reason = f'เข้าได้เลย: Trend ขึ้นชัด + ราคาเหนือ EMA10 (${price_above_ema10:.2f} / {price_above_ema10_pct:.1f}%) + Volume {volume_ratio:.1f}x แรง'
                    action_color = 'green'
                elif ema_10 > ema_30 and current_price > ema_10 and volume_ratio > 0.8:
                    # Trend ดี แต่ Volume ปานกลาง
                    action_signal = 'READY'
                    action_reason = f'เตรียมพร้อม: Trend ขึ้น + ราคาเหนือ EMA10 (${price_above_ema10:.2f}) - Volume {volume_ratio:.1f}x พอใช้'
                    action_color = 'yellow'
                elif ema_10 > ema_30:
                    # Trend ดีแต่ราคาต่ำกว่า EMA หรือ Volume อ่อน
                    price_below_ema10 = abs(current_price - ema_10)
                    action_signal = 'READY'
                    action_reason = f'เตรียมพร้อม: Trend ขึ้น - รอราคากลับมาเหนือ EMA10 (อีก ${price_below_ema10:.2f}) หรือ Volume เพิ่ม'
                    action_color = 'yellow'
                else:
                    # EMA ยังไม่ตัดขึ้น
                    ema_gap = abs(ema_10 - ema_30)
                    action_signal = 'WAIT'
                    action_reason = f'รอ: EMA10-EMA30 ห่าง ${ema_gap:.2f} - รอให้ตัดขึ้นก่อน'
                    action_color = 'red'

                return {
                    'strategy_name': 'EMA Cross + Volume Breakout',
                    'market_state': 'Trending / Bullish Momentum',
                    'action_signal': action_signal,
                    'action_reason': action_reason,
                    'action_color': action_color,
                    'entry_readiness': round(entry_readiness, 1),  # Entry Readiness Score (0-100)
                    'entry_conditions': entry_conditions,
                    'exit_conditions': exit_conditions,
                    'warnings': warnings,
                    'trading_plan': {
                        # Volatility classification
                        'volatility_class': volatility_class,
                        'atr': atr,
                        'atr_pct': round((atr / current_price) * 100, 2) if current_price > 0 else 0,
                        # Entry details
                        'entry_range': entry_range,
                        'entry_price': entry_price,
                        'entry_aggressive': entry_analysis['entry_aggressive'],
                        'entry_moderate': entry_analysis['entry_moderate'],
                        'entry_conservative': entry_analysis['entry_conservative'],
                        'entry_distance_pct': entry_analysis['distance_from_current_pct'],
                        'entry_method': entry_analysis['calculation_method'],
                        'entry_reason': entry_analysis['entry_reason'],
                        # Immediate entry check
                        'immediate_entry': immediate_entry_check['immediate_entry'],
                        'immediate_entry_confidence': immediate_entry_check['confidence_score'],
                        'immediate_entry_reasons': immediate_entry_check['reasons'],
                        'entry_action': immediate_entry_check['action'],
                        # Take profit details
                        'take_profit': take_profit,
                        'tp1': tp_analysis['tp1'],
                        'tp2': tp_analysis['tp2'],
                        'tp3': tp_analysis['tp3'],
                        'tp1_return_pct': tp_analysis['tp1_return_pct'],
                        'tp2_return_pct': tp_analysis['tp2_return_pct'],
                        'tp3_return_pct': tp_analysis['tp3_return_pct'],
                        'tp_method': tp_analysis['calculation_method'],
                        # Stop loss details
                        'stop_loss': stop_loss,
                        'risk_pct': sl_analysis['risk_pct'],
                        'sl_method': sl_analysis['calculation_method'],
                        # Risk/Reward
                        'risk_reward_ratio': round((take_profit - entry_price) / (entry_price - stop_loss), 2) if entry_price > stop_loss else 0,
                        # Swing points used
                        'swing_high': swing_high,
                        'swing_low': swing_low
                    }
                }

            elif market_state == 'SIDEWAY':
                # Strategy: Support/Resistance + RSI
                entry_conditions = []
                exit_conditions = []
                warnings = []

                # Entry conditions (ซื้อใกล้รับ)
                distance_to_support = abs((current_price - support) / support) * 100
                if distance_to_support <= 2:
                    entry_conditions.append({
                        'condition': f'ราคา ({current_price:.2f}) ใกล้รับ ({support:.2f})',
                        'status': '✅',
                        'reason': 'โอกาสดีดขึ้น'
                    })
                else:
                    entry_conditions.append({
                        'condition': f'ราคาห่างรับ {distance_to_support:.1f}%',
                        'status': '⚠️',
                        'reason': 'รอราคาลงใกล้รับก่อน'
                    })

                if rsi < 50:
                    entry_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) < 50',
                        'status': '✅',
                        'reason': 'Oversold เริ่มดีดขึ้น'
                    })
                else:
                    entry_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) > 50',
                        'status': '⚠️',
                        'reason': 'รอ RSI ต่ำกว่า'
                    })

                if current_price <= bb_lower:
                    entry_conditions.append({
                        'condition': f'ราคาชน Lower BB ({bb_lower:.2f})',
                        'status': '✅',
                        'reason': 'โอกาสกลับตัว'
                    })

                # Exit conditions (ขายใกล้ต้าน)
                distance_to_resistance = abs((resistance - current_price) / resistance) * 100
                if distance_to_resistance <= 2:
                    exit_conditions.append({
                        'condition': f'ราคา ({current_price:.2f}) ใกล้ต้าน ({resistance:.2f})',
                        'status': '⚠️',
                        'reason': 'ควรขายทำกำไร'
                    })
                else:
                    exit_conditions.append({
                        'condition': f'ราคาห่างต้าน {distance_to_resistance:.1f}%',
                        'status': '✗',
                        'reason': 'ยังมีที่วิ่ง'
                    })

                if rsi > 70:
                    exit_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) > 70',
                        'status': '⚠️',
                        'reason': 'Overbought'
                    })

                if current_price >= bb_upper:
                    exit_conditions.append({
                        'condition': f'ราคาชน Upper BB ({bb_upper:.2f})',
                        'status': '⚠️',
                        'reason': 'ควรขาย'
                    })

                warnings.append('ตลาดแกว่งในกรอบ → เทรดระยะสั้นที่แนวรับ-ต้าน')

                # Overall Action Signal สำหรับ SIDEWAY (ปรับให้ยืดหยุ่นขึ้น)
                # คำนวณ distance และ entry readiness
                distance_to_support = abs((current_price - support) / support) * 100
                distance_to_resistance = abs((resistance - current_price) / resistance) * 100

                # Entry Readiness Score (0-100)
                # ยิ่งใกล้รับ + RSI ต่ำ = Score สูง
                distance_score = max(0, 100 - (distance_to_support * 10))  # 0% = 100, 5% = 50, 10% = 0
                rsi_score = max(0, 100 - rsi) if rsi < 50 else max(0, 50 - (rsi - 50))  # RSI < 30 = 100, 50 = 50, 70 = 30
                entry_readiness = (distance_score * 0.6 + rsi_score * 0.4)  # Distance สำคัญกว่า

                # ตัดสินใจ Action Signal
                price_distance_dollars = abs(current_price - support)

                if distance_to_support <= 2 and rsi < 50:
                    # Perfect entry: ใกล้รับ + RSI ดี
                    action_signal = 'BUY_NOW'
                    action_reason = f'เข้าได้เลย: ราคาชนรับ ({distance_to_support:.1f}% / ${price_distance_dollars:.2f}) + RSI {rsi:.0f} ต่ำ โอกาสดีดขึ้น'
                    action_color = 'green'
                elif distance_to_support <= 5 and rsi <= 60:
                    # ใกล้รับพอสมควร - เตรียมพร้อม
                    action_signal = 'READY'
                    action_reason = f'เตรียมพร้อม: ราคาห่างรับ {distance_to_support:.1f}% (อีก ${price_distance_dollars:.2f}) RSI {rsi:.0f} - ติดตามใกล้ชิด'
                    action_color = 'yellow'
                elif distance_to_support <= 2 and rsi > 60:
                    # ราคาดีแต่ RSI สูง
                    action_signal = 'READY'
                    action_reason = f'เตรียมพร้อม: ราคาใกล้รับ ({distance_to_support:.1f}% / ${price_distance_dollars:.2f}) แต่ RSI {rsi:.0f} สูง - รอ pullback'
                    action_color = 'yellow'
                else:
                    # ห่างเกินไป
                    action_signal = 'WAIT'
                    if distance_to_support > 10:
                        action_reason = f'รอ: ราคาห่างรับมาก ({distance_to_support:.1f}% / ${price_distance_dollars:.2f}) - ยังไม่ใช่จังหวะ'
                    else:
                        action_reason = f'รอ: ราคาห่างรับ {distance_to_support:.1f}% (อีก ${price_distance_dollars:.2f}) - รอให้ลงใกล้รับก่อน'
                    action_color = 'red'

                # Trading plan for SIDEWAY - INTELLIGENT CALCULATION (v5.0)
                atr = indicators.get('atr', current_price * 0.02)

                # Detect volatility class early (before using it)
                volatility_class = self._detect_volatility_class(atr, current_price)

                # Step 1: Detect swing points
                swing_points = self._detect_swing_points(lookback=20)
                swing_high = swing_points['swing_high']
                swing_low = swing_points['swing_low']

                # Step 2: Calculate smart entry zone at support
                entry_analysis = self._calculate_smart_entry_zone(
                    current_price=current_price,
                    swing_high=swing_high,
                    swing_low=swing_low,
                    ema_50=ema_30,
                    market_state='SIDEWAY',
                    support=support,
                    resistance=resistance
                )

                # Step 2.5: Check if immediate entry is warranted
                immediate_entry_check = self._check_immediate_entry_conditions(
                    current_price=current_price,
                    recommended_entry=entry_analysis['recommended_entry'],
                    support=support,
                    resistance=resistance,
                    indicators=indicators,
                    market_state='SIDEWAY'
                )

                # Use current price if immediate entry, otherwise use recommended entry
                if immediate_entry_check['immediate_entry']:
                    entry_price = current_price
                    entry_range = [current_price * 0.995, current_price * 1.005]
                    entry_analysis['entry_reason'] = f"IMMEDIATE ENTRY: {', '.join(immediate_entry_check['reasons'])}"
                    entry_analysis['calculation_method'] = 'Immediate Entry (Current Price)'
                else:
                    entry_price = entry_analysis['recommended_entry']
                    entry_range = entry_analysis['entry_range']

                # Step 3: Calculate intelligent TP at resistance
                # For immediate entry, use ATR-based TP from current price
                # For pullback entry, use resistance-based TP
                if immediate_entry_check['immediate_entry']:
                    # Immediate entry: ATR-based TP from current price (conservative for sideway)
                    logger.info(f"🎯 IMMEDIATE ENTRY (SIDEWAY) detected - Using ATR-based TP from entry ${entry_price:.2f}, ATR=${atr:.2f}")

                    # 🆕 v6.0: Get dynamic multipliers based on volatility
                    multipliers = self._get_dynamic_atr_multipliers('SIDEWAY', volatility_class)

                    tp1 = entry_price + (atr * multipliers['tp1'])
                    tp2 = entry_price + (atr * multipliers['tp2'])
                    tp3 = entry_price + (atr * multipliers['tp3'])
                    logger.info(f"   Calculated TP1=${tp1:.2f}, TP2=${tp2:.2f}, TP3=${tp3:.2f}")

                    # Cap at resistance (but only if it doesn't make TP < entry!)
                    if resistance > entry_price:
                        logger.info(f"   Resistance ${resistance:.2f} > Entry ${entry_price:.2f}")
                        tp1_capped = min(tp1, resistance * 0.99)
                        tp2_capped = min(tp2, resistance * 0.99)

                        # Only apply cap if it doesn't make TP < entry
                        if tp1_capped > entry_price:
                            logger.info(f"   Applying resistance cap: TP1=${tp1:.2f} → ${tp1_capped:.2f}")
                            tp1 = tp1_capped
                            tp2 = tp2_capped
                            tp3 = resistance * 1.01
                        else:
                            logger.info(f"   ⚠️ Resistance too close! Cap would make TP < Entry. Using uncapped ATR-based TP")
                            # Keep original ATR-based TPs

                    tp_analysis = {
                        'tp1': round(tp1, 2),
                        'tp2': round(tp2, 2),
                        'tp3': round(tp3, 2),
                        'recommended_tp': round(tp1, 2),  # Conservative for sideway
                        'tp1_return_pct': round(((tp1 - entry_price) / entry_price) * 100, 2),
                        'tp2_return_pct': round(((tp2 - entry_price) / entry_price) * 100, 2),
                        'tp3_return_pct': round(((tp3 - entry_price) / entry_price) * 100, 2),
                        'calculation_method': 'ATR Multiple (Immediate Entry - Sideway)'
                    }
                else:
                    # Pullback entry: Resistance-based TP
                    tp_analysis = self._calculate_intelligent_tp_levels(
                        entry_price=entry_price,
                        swing_high=swing_high,
                        swing_low=swing_low,
                        resistance=resistance,
                        market_state='SIDEWAY',
                        atr=atr
                    )

                take_profit = tp_analysis['recommended_tp']

                # Step 4: Calculate intelligent SL below support (with Anti-Hunt Protection)
                sl_analysis = self._calculate_intelligent_stop_loss(
                    entry_price=entry_price,
                    swing_low=swing_low,
                    support=support,
                    market_state='SIDEWAY',
                    atr=atr,
                    indicators=indicators,  # 🆕 ส่ง indicators เพื่อใช้ anti-hunt logic
                    enable_anti_hunt=True   # 🆕 เปิดใช้ anti-hunt protection
                )

                stop_loss = sl_analysis['stop_loss']

                return {
                    'strategy_name': 'Support/Resistance + RSI Swing',
                    'market_state': 'Sideway / Range Bound',
                    'action_signal': action_signal,
                    'action_reason': action_reason,
                    'action_color': action_color,
                    'entry_readiness': round(entry_readiness, 1),  # Entry Readiness Score (0-100)
                    'entry_conditions': entry_conditions,
                    'exit_conditions': exit_conditions,
                    'warnings': warnings,
                    'trading_plan': {
                        # Volatility classification
                        'volatility_class': volatility_class,
                        'atr': atr,
                        'atr_pct': round((atr / current_price) * 100, 2) if current_price > 0 else 0,
                        # Entry details
                        'entry_range': entry_range,
                        'entry_price': entry_price,
                        'entry_aggressive': entry_analysis['entry_aggressive'],
                        'entry_moderate': entry_analysis['entry_moderate'],
                        'entry_conservative': entry_analysis['entry_conservative'],
                        'entry_distance_pct': entry_analysis['distance_from_current_pct'],
                        'entry_method': entry_analysis['calculation_method'],
                        'entry_reason': entry_analysis['entry_reason'],
                        # Immediate entry check
                        'immediate_entry': immediate_entry_check['immediate_entry'],
                        'immediate_entry_confidence': immediate_entry_check['confidence_score'],
                        'immediate_entry_reasons': immediate_entry_check['reasons'],
                        'entry_action': immediate_entry_check['action'],
                        # Take profit details
                        'take_profit': take_profit,
                        'tp1': tp_analysis['tp1'],
                        'tp2': tp_analysis['tp2'],
                        'tp3': tp_analysis['tp3'],
                        'tp1_return_pct': tp_analysis['tp1_return_pct'],
                        'tp2_return_pct': tp_analysis['tp2_return_pct'],
                        'tp3_return_pct': tp_analysis['tp3_return_pct'],
                        'tp_method': tp_analysis['calculation_method'],
                        # Stop loss details
                        'stop_loss': stop_loss,
                        'risk_pct': sl_analysis['risk_pct'],
                        'sl_method': sl_analysis['calculation_method'],
                        # Risk/Reward
                        'risk_reward_ratio': round((take_profit - entry_price) / (entry_price - stop_loss), 2) if entry_price > stop_loss else 0,
                        # Swing points used
                        'swing_high': swing_high,
                        'swing_low': swing_low
                    }
                }

            else:  # BEARISH
                # Strategy: MACD + RSI (รอ reversal)
                entry_conditions = []
                exit_conditions = []
                warnings = []

                # Entry conditions (รอสัญญาณกลับตัว)
                if macd_line > macd_signal:
                    entry_conditions.append({
                        'condition': 'MACD line ขึ้นตัด Signal line',
                        'status': '✅',
                        'reason': 'สัญญาณ reversal'
                    })
                else:
                    entry_conditions.append({
                        'condition': 'MACD line ยังต่ำกว่า Signal line',
                        'status': '⏸️',
                        'reason': 'รอ MACD กลับขึ้น'
                    })

                if rsi >= 30 and rsi <= 40:
                    entry_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) กลับจาก 30-40',
                        'status': '✅',
                        'reason': 'Momentum กลับมา'
                    })
                elif rsi < 30:
                    entry_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) < 30',
                        'status': '⏸️',
                        'reason': 'Oversold มาก รอดีดขึ้น'
                    })
                else:
                    entry_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) ยังสูง',
                        'status': '⏸️',
                        'reason': 'รอ RSI ลงก่อน'
                    })

                # Exit conditions
                if macd_line < macd_signal:
                    exit_conditions.append({
                        'condition': 'MACD line ตัดลง Signal line',
                        'status': '❌',
                        'reason': 'Trend ยังลง'
                    })

                if rsi < 50:
                    exit_conditions.append({
                        'condition': f'RSI ({rsi:.0f}) < 50',
                        'status': '❌',
                        'reason': 'แรงขายยังอยู่'
                    })

                if current_price < support:
                    exit_conditions.append({
                        'condition': f'ราคาหลุดรับ ({support:.2f})',
                        'status': '❌',
                        'reason': 'ควรหยุดซื้อ'
                    })
                    warnings.append('ราคาหลุดแนวรับสำคัญ → ไม่ควรเข้าซื้อ')

                warnings.append('ตลาดอ่อนแรง → รอสัญญาณชัดเจนก่อนเข้า')

                # Overall Action Signal สำหรับ BEARISH
                # Entry Readiness สำหรับ Reversal
                macd_score = 100 if macd_line > macd_signal else max(0, 50 + (macd_line - macd_signal) * 10)
                rsi_score = 100 if (rsi >= 30 and rsi <= 40) else max(0, 50 if rsi < 50 else 0)
                support_score = 100 if current_price <= support * 1.02 else max(0, 100 - ((current_price - support) / support) * 1000)
                entry_readiness = (macd_score * 0.4 + rsi_score * 0.4 + support_score * 0.2)

                if macd_line > macd_signal and rsi >= 30 and rsi <= 45:
                    # สัญญาณกลับตัวชัดเจน
                    action_signal = 'BUY_NOW'
                    action_reason = f'เข้าได้เลย: MACD กลับขึ้น + RSI {rsi:.0f} กลับจาก oversold - สัญญาณ reversal'
                    action_color = 'green'
                elif macd_line > macd_signal or (rsi >= 25 and rsi <= 50):
                    # มีบางสัญญาณกลับตัว
                    action_signal = 'READY'
                    action_reason = f'เตรียมพร้อม: มีสัญญาณกลับตัว (MACD: {macd_line > macd_signal}, RSI: {rsi:.0f}) - รอยืนยันเพิ่ม'
                    action_color = 'yellow'
                else:
                    # ยังไม่มีสัญญาณ
                    action_signal = 'WAIT'
                    action_reason = f'รอ: ยังไม่มีสัญญาณกลับตัวชัดเจน (RSI {rsi:.0f}, MACD ลบ) - ตลาดยังอ่อนแรง'
                    action_color = 'red'

                # Trading plan for BEARISH - INTELLIGENT CALCULATION (v5.0)
                atr = indicators.get('atr', current_price * 0.02)

                # Detect volatility class early (before using it)
                volatility_class = self._detect_volatility_class(atr, current_price)

                # Step 1: Detect swing points
                swing_points = self._detect_swing_points(lookback=20)
                swing_high = swing_points['swing_high']
                swing_low = swing_points['swing_low']

                # Step 2: Calculate conservative entry in bearish market
                entry_analysis = self._calculate_smart_entry_zone(
                    current_price=current_price,
                    swing_high=swing_high,
                    swing_low=swing_low,
                    ema_50=ema_30,
                    market_state='BEARISH',
                    support=support,
                    resistance=resistance
                )

                # Step 2.5: Check if immediate entry is warranted (reversal confirmed)
                immediate_entry_check = self._check_immediate_entry_conditions(
                    current_price=current_price,
                    recommended_entry=entry_analysis['recommended_entry'],
                    support=support,
                    resistance=resistance,
                    indicators=indicators,
                    market_state='BEARISH'
                )

                # Use current price if immediate entry, otherwise use recommended entry
                if immediate_entry_check['immediate_entry']:
                    entry_price = current_price
                    entry_range = [current_price * 0.995, current_price * 1.005]
                    entry_analysis['entry_reason'] = f"IMMEDIATE ENTRY: {', '.join(immediate_entry_check['reasons'])}"
                    entry_analysis['calculation_method'] = 'Immediate Entry (Current Price)'
                else:
                    entry_price = entry_analysis['recommended_entry']
                    entry_range = entry_analysis['entry_range']

                # Step 3: Calculate quick profit targets in bearish
                # For immediate entry, use ATR-based TP from current price
                # For pullback entry, use ATR multiple (quick profit in bearish)
                if immediate_entry_check['immediate_entry']:
                    # Immediate entry: Quick profit ATR-based (very conservative for bearish)
                    # 🆕 v6.0: Get dynamic multipliers based on volatility
                    multipliers = self._get_dynamic_atr_multipliers('BEARISH', volatility_class)

                    tp1 = entry_price + (atr * multipliers['tp1'])
                    tp2 = entry_price + (atr * multipliers['tp2'])
                    tp3 = entry_price + (atr * multipliers['tp3'])

                    tp_analysis = {
                        'tp1': round(tp1, 2),
                        'tp2': round(tp2, 2),
                        'tp3': round(tp3, 2),
                        'recommended_tp': round(tp1, 2),  # Very conservative for bearish
                        'tp1_return_pct': round(((tp1 - entry_price) / entry_price) * 100, 2),
                        'tp2_return_pct': round(((tp2 - entry_price) / entry_price) * 100, 2),
                        'tp3_return_pct': round(((tp3 - entry_price) / entry_price) * 100, 2),
                        'calculation_method': 'ATR Multiple (Immediate Entry - Bearish)'
                    }
                else:
                    # Pullback entry: ATR-based (already conservative for bearish)
                    tp_analysis = self._calculate_intelligent_tp_levels(
                        entry_price=entry_price,
                        swing_high=swing_high,
                        swing_low=swing_low,
                        resistance=resistance,
                        market_state='BEARISH',
                        atr=atr
                    )

                take_profit = tp_analysis['recommended_tp']

                # Step 4: Calculate tight SL in bearish market (with Anti-Hunt Protection)
                sl_analysis = self._calculate_intelligent_stop_loss(
                    entry_price=entry_price,
                    swing_low=swing_low,
                    support=support,
                    market_state='BEARISH',
                    atr=atr,
                    indicators=indicators,  # 🆕 ส่ง indicators เพื่อใช้ anti-hunt logic
                    enable_anti_hunt=True   # 🆕 เปิดใช้ anti-hunt protection
                )

                stop_loss = sl_analysis['stop_loss']

                # คำนวณ R/R ratio ถ้ามีสัญญาณกลับตัว ถ้าไม่มีให้เป็น 0
                if entry_price > stop_loss and (macd_line > macd_signal or (rsi >= 30 and rsi <= 40)):
                    r_r_ratio = round((take_profit - entry_price) / (entry_price - stop_loss), 2)
                else:
                    r_r_ratio = 0  # ไม่แนะนำเข้าในตลาดขาลง

                return {
                    'strategy_name': 'MACD + RSI Reversal',
                    'market_state': 'Bearish / Correction',
                    'action_signal': action_signal,
                    'action_reason': action_reason,
                    'action_color': action_color,
                    'entry_readiness': round(entry_readiness, 1),  # Entry Readiness Score (0-100)
                    'entry_conditions': entry_conditions,
                    'exit_conditions': exit_conditions,
                    'warnings': warnings,
                    'trading_plan': {
                        # Volatility classification
                        'volatility_class': volatility_class,
                        'atr': atr,
                        'atr_pct': round((atr / current_price) * 100, 2) if current_price > 0 else 0,
                        # Entry details
                        'entry_range': entry_range,
                        'entry_price': entry_price,
                        'entry_aggressive': entry_analysis['entry_aggressive'],
                        'entry_moderate': entry_analysis['entry_moderate'],
                        'entry_conservative': entry_analysis['entry_conservative'],
                        'entry_distance_pct': entry_analysis['distance_from_current_pct'],
                        'entry_method': entry_analysis['calculation_method'],
                        'entry_reason': entry_analysis['entry_reason'],
                        # Immediate entry check
                        'immediate_entry': immediate_entry_check['immediate_entry'],
                        'immediate_entry_confidence': immediate_entry_check['confidence_score'],
                        'immediate_entry_reasons': immediate_entry_check['reasons'],
                        'entry_action': immediate_entry_check['action'],
                        # Take profit details
                        'take_profit': take_profit,
                        'tp1': tp_analysis['tp1'],
                        'tp2': tp_analysis['tp2'],
                        'tp3': tp_analysis['tp3'],
                        'tp1_return_pct': tp_analysis['tp1_return_pct'],
                        'tp2_return_pct': tp_analysis['tp2_return_pct'],
                        'tp3_return_pct': tp_analysis['tp3_return_pct'],
                        'tp_method': tp_analysis['calculation_method'],
                        # Stop loss details
                        'stop_loss': stop_loss,
                        'risk_pct': sl_analysis['risk_pct'],
                        'sl_method': sl_analysis['calculation_method'],
                        # Risk/Reward
                        'risk_reward_ratio': r_r_ratio,
                        # Swing points used
                        'swing_high': swing_high,
                        'swing_low': swing_low
                    }
                }

        except Exception as e:
            logger.error(f"Strategy recommendation failed: {e}")
            return {
                'strategy_name': 'Unknown',
                'market_state': 'Unknown',
                'action_signal': 'WAIT',
                'action_reason': 'ไม่สามารถวิเคราะห์ได้ - รอข้อมูลเพิ่มเติม',
                'action_color': 'red',
                'entry_readiness': 0,
                'entry_conditions': [],
                'exit_conditions': [],
                'warnings': ['ไม่สามารถวิเคราะห์ได้'],
                'trading_plan': {}
            }

    def _calculate_confidence_score(self, market_state: str, indicators: Dict[str, Any],
                                    signals: Dict[str, Any]) -> Dict[str, Any]:
        """
        คำนวณ Confidence Score ของสัญญาณ

        Returns:
            Confidence score พร้อมรายละเอียด
        """
        try:
            total_indicators = 0
            aligned_indicators = 0
            conflicting_indicators = 0

            # ตรวจสอบแต่ละ indicator
            # เก็บ list ของทิศทาง เพื่อหาทิศทางหลัก
            directions = []

            for signal_name, signal_data in signals.items():
                if isinstance(signal_data, dict):
                    signal_type = signal_data.get('signal', 'NEUTRAL')
                    total_indicators += 1

                    current_direction = 0
                    if signal_type in ['BUY', 'BULLISH']:
                        current_direction = 1
                    elif signal_type in ['SELL', 'BEARISH']:
                        current_direction = -1

                    directions.append(current_direction)

            # หาทิศทางหลัก (ทิศทางที่มีมากที่สุด)
            if directions:
                # นับจำนวน BUY, SELL, NEUTRAL
                buy_count = directions.count(1)
                sell_count = directions.count(-1)
                neutral_count = directions.count(0)

                # ทิศทางหลักคือทิศทางที่มีมากที่สุด
                if buy_count >= sell_count and buy_count >= neutral_count:
                    signal_direction = 1
                elif sell_count >= buy_count and sell_count >= neutral_count:
                    signal_direction = -1
                else:
                    signal_direction = 0

                # นับ indicator ที่ชี้ทิศทางเดียวกัน
                # ถ้าทิศทางหลักเป็น NEUTRAL (0) ให้นับจำนวน NEUTRAL
                if signal_direction != 0:
                    aligned_indicators = directions.count(signal_direction)
                else:
                    # ตลาด Sideway: นับ NEUTRAL indicators
                    aligned_indicators = neutral_count

                # นับ indicator ที่ขัดแย้ง
                if signal_direction == 1:
                    conflicting_indicators = sell_count
                elif signal_direction == -1:
                    conflicting_indicators = buy_count
                else:
                    conflicting_indicators = 0

            # คำนวณ confidence
            if total_indicators > 0:
                alignment_ratio = aligned_indicators / total_indicators
                conflict_penalty = conflicting_indicators / total_indicators
                confidence = (alignment_ratio - (conflict_penalty * 0.5)) * 100
                confidence = max(0, min(100, confidence))  # 0-100
            else:
                confidence = 50  # Neutral

            # Sideway Confidence Boost
            # เมื่อตลาด Sideway และ NEUTRAL indicators เยอะ → นั่นคือสัญญาณที่ชัดเจน
            if market_state == 'SIDEWAY' and signal_direction == 0:
                neutral_ratio = neutral_count / total_indicators if total_indicators > 0 else 0
                if neutral_ratio >= 0.5:  # ถ้า NEUTRAL >= 50%
                    # Bonus สำหรับการตรวจจับ Sideway ที่แม่นยำ
                    sideway_boost = min(20, neutral_ratio * 30)  # Max +20
                    confidence = min(100, confidence + sideway_boost)

            # Volume confirmation bonus (ปรับตามสภาวะตลาด)
            volume = indicators.get('current_volume', 0)
            volume_sma = indicators.get('volume_sma', 1)
            volume_ratio = volume / volume_sma if volume_sma > 0 else 1

            volume_bonus = 0
            if market_state == 'TRENDING_BULLISH':
                # Trending: Volume สูงดี, Volume ต่ำแย่
                if volume_ratio > 1.2:
                    volume_bonus = 10
                elif volume_ratio < 0.8:
                    volume_bonus = -10
            elif market_state == 'SIDEWAY':
                # Sideway: Volume ต่ำเป็นเรื่องปกติ (ไม่ penalty มาก)
                if volume_ratio > 1.5:
                    volume_bonus = 5  # Breakout potential
                elif volume_ratio < 0.5:
                    volume_bonus = -5  # Very low volume
            elif market_state == 'BEARISH':
                # Bearish: Volume สูงเป็นสัญญาณแย่ (selling pressure)
                if volume_ratio > 1.5:
                    volume_bonus = -10  # High volume in bearish = bad
                elif volume_ratio < 0.8:
                    volume_bonus = 5  # Low volume = less selling pressure

            confidence = max(0, min(100, confidence + volume_bonus))

            # สรุปเหตุผล
            reasons = []
            reasons.append(f'Indicators {aligned_indicators}/{total_indicators} ตัวชี้ทิศทางเดียวกัน')

            if volume_ratio > 1.2:
                reasons.append(f'Volume ยืนยันแนวโน้ม (+{(volume_ratio - 1) * 100:.0f}% vs average)')
            elif volume_ratio < 0.8:
                reasons.append(f'Volume อ่อน ({volume_ratio * 100:.0f}% of average)')

            if conflicting_indicators > 0:
                reasons.append(f'{conflicting_indicators} indicators ขัดแย้ง')
            else:
                reasons.append('ไม่มี indicator ขัดแย้งรุนแรง')

            # ระดับความเชื่อมั่น
            if confidence >= 80:
                level = 'สัญญาณแรงมาก'
            elif confidence >= 65:
                level = 'สัญญาณแรง'
            elif confidence >= 50:
                level = 'สัญญาณปานกลาง'
            elif confidence >= 35:
                level = 'สัญญาณอ่อน'
            else:
                level = 'สัญญาณอ่อนมาก / ควรรอ'

            return {
                'confidence': round(confidence, 0),
                'level': level,
                'aligned_count': aligned_indicators,
                'total_count': total_indicators,
                'conflict_count': conflicting_indicators,
                'volume_confirmation': volume_ratio > 1.0,
                'reasons': reasons
            }

        except Exception as e:
            logger.error(f"Confidence calculation failed: {e}")
            return {
                'confidence': 50,
                'level': 'Unknown',
                'aligned_count': 0,
                'total_count': 0,
                'conflict_count': 0,
                'volume_confirmation': False,
                'reasons': ['ไม่สามารถคำนวณได้']
            }