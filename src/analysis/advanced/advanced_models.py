"""
Advanced Analytical Models Module
Enhanced technical and fundamental analysis with machine learning readiness
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from loguru import logger
import warnings
from scipy import stats
from scipy.signal import find_peaks, savgol_filter
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
import talib


class AdvancedTechnicalAnalyzer:
    """Advanced technical analysis with machine learning capabilities"""

    def __init__(self, price_data: pd.DataFrame = None, config: Dict[str, Any] = None):
        self.config = config if config is not None else {}
        self.price_data = price_data
        self.ml_models = {}
        self.feature_importance = {}

    @staticmethod
    def _ensure_float64(arr) -> np.ndarray:
        """Ensure array is float64 for TA-Lib compatibility"""
        return np.asarray(arr, dtype=np.float64)

    def calculate_advanced_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate advanced technical indicators beyond basic ones

        Args:
            data: OHLCV data

        Returns:
            DataFrame with advanced indicators
        """
        logger.info("Calculating advanced technical indicators")

        if data.empty:
            return data

        df = data.copy()

        # 1. Advanced Momentum Indicators
        df = self._calculate_advanced_momentum(df)

        # 2. Volatility-based Indicators
        df = self._calculate_volatility_indicators(df)

        # 3. Volume-price Analysis
        df = self._calculate_volume_price_indicators(df)

        # 4. Market Structure Indicators
        df = self._calculate_market_structure_indicators(df)

        # 5. Fibonacci-based Indicators
        df = self._calculate_fibonacci_indicators(df)

        # 6. Statistical Indicators
        df = self._calculate_statistical_indicators(df)

        # 7. Cycle Analysis
        df = self._calculate_cycle_indicators(df)

        return df

    def perform_pattern_recognition(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Advanced pattern recognition using multiple methods

        Args:
            data: OHLCV data

        Returns:
            Dictionary of detected patterns
        """
        logger.info("Performing advanced pattern recognition")

        patterns = {
            'candlestick_patterns': {},
            'chart_patterns': {},
            'wave_patterns': {},
            'statistical_patterns': {}
        }

        if data.empty:
            return patterns

        # 1. Candlestick Patterns (using TA-Lib)
        patterns['candlestick_patterns'] = self._detect_candlestick_patterns(data)

        # 2. Chart Patterns
        patterns['chart_patterns'] = self._detect_chart_patterns(data)

        # 3. Elliott Wave Patterns
        patterns['wave_patterns'] = self._detect_wave_patterns(data)

        # 4. Statistical Patterns
        patterns['statistical_patterns'] = self._detect_statistical_patterns(data)

        return patterns

    def calculate_sentiment_indicators(self, data: pd.DataFrame,
                                     volume_profile: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Calculate market sentiment indicators

        Args:
            data: OHLCV data
            volume_profile: Optional volume profile data

        Returns:
            Dictionary of sentiment indicators
        """
        logger.info("Calculating sentiment indicators")

        sentiment = {
            'fear_greed_index': 0.0,
            'momentum_sentiment': 0.0,
            'volume_sentiment': 0.0,
            'volatility_sentiment': 0.0,
            'overall_sentiment': 'neutral'
        }

        if data.empty:
            return sentiment

        # 1. Fear & Greed components
        sentiment['fear_greed_index'] = self._calculate_fear_greed_index(data)

        # 2. Momentum-based sentiment
        sentiment['momentum_sentiment'] = self._calculate_momentum_sentiment(data)

        # 3. Volume-based sentiment
        sentiment['volume_sentiment'] = self._calculate_volume_sentiment(data)

        # 4. Volatility-based sentiment
        sentiment['volatility_sentiment'] = self._calculate_volatility_sentiment(data)

        # 5. Overall sentiment synthesis
        sentiment['overall_sentiment'] = self._synthesize_sentiment(sentiment)

        return sentiment

    def perform_regime_detection(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect market regime (trending vs ranging, bull vs bear)

        Args:
            data: OHLCV data

        Returns:
            Dictionary with regime information
        """
        logger.info("Performing market regime detection")

        regime = {
            'trend_regime': 'unknown',
            'volatility_regime': 'unknown',
            'volume_regime': 'unknown',
            'overall_regime': 'unknown',
            'regime_strength': 0.0,
            'regime_duration': 0,
            'next_regime_probability': {}
        }

        if len(data) < 50:
            return regime

        # Convert DataFrame to dict format expected by regime detection methods
        data_dict = {'df': data}

        # 1. Trend Regime Detection
        regime['trend_regime'] = self._detect_trend_regime(data_dict)

        # 2. Volatility Regime Detection
        regime['volatility_regime'] = self._detect_volatility_regime(data_dict)

        # 3. Volume Regime Detection
        regime['volume_regime'] = self._detect_volume_regime(data_dict)

        # 4. Overall Regime Synthesis
        regime['overall_regime'] = self._synthesize_regime(regime)

        # 5. Regime Strength and Duration
        regime['regime_strength'] = self._calculate_regime_strength(data_dict, regime)
        regime['regime_duration'] = self._calculate_regime_duration(data_dict, regime)

        # 6. Regime Transition Probabilities
        regime['next_regime_probability'] = self._calculate_regime_transition_probabilities(data_dict, regime)

        return regime

    def calculate_multi_timeframe_signals(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Calculate signals across multiple time frames

        Args:
            data_dict: Dictionary of timeframe -> DataFrame

        Returns:
            Multi-timeframe signal analysis
        """
        logger.info("Calculating multi-timeframe signals")

        mtf_analysis = {
            'timeframe_signals': {},
            'signal_alignment': {},
            'dominant_trend': 'unknown',
            'confidence_level': 0.0,
            'conflicting_signals': []
        }

        if not data_dict:
            return mtf_analysis

        # 1. Calculate signals for each timeframe
        for timeframe, data in data_dict.items():
            if not data.empty:
                mtf_analysis['timeframe_signals'][timeframe] = self._calculate_timeframe_signals(data)

        # 2. Analyze signal alignment
        mtf_analysis['signal_alignment'] = self._analyze_signal_alignment(
            mtf_analysis['timeframe_signals']
        )

        # 3. Determine dominant trend
        mtf_analysis['dominant_trend'] = self._determine_dominant_trend(
            mtf_analysis['timeframe_signals']
        )

        # 4. Calculate confidence level
        mtf_analysis['confidence_level'] = self._calculate_mtf_confidence(
            mtf_analysis['signal_alignment']
        )

        # 5. Identify conflicting signals
        mtf_analysis['conflicting_signals'] = self._identify_conflicting_signals(
            mtf_analysis['timeframe_signals']
        )

        return mtf_analysis

    def _calculate_advanced_momentum(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate advanced momentum indicators"""
        if 'close' not in df.columns:
            return df

        # 1. Rate of Change (ROC) with multiple periods
        for period in [5, 10, 20]:
            df[f'roc_{period}'] = ((df['close'] / df['close'].shift(period)) - 1) * 100

        # 2. Price Rate of Change (PROC)
        df['proc'] = df['close'].pct_change(periods=12) * 100

        # 3. Momentum Oscillator
        df['momentum_14'] = df['close'] / df['close'].shift(14) * 100

        # 4. Stochastic Momentum Index (SMI)
        if all(col in df.columns for col in ['high', 'low', 'close']):
            df['smi'] = self._calculate_smi(df)

        # 5. True Strength Index (TSI)
        df['tsi'] = self._calculate_tsi(df)

        # 6. Relative Vigor Index (RVI)
        if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
            df['rvi'] = self._calculate_rvi(df)

        return df

    def _calculate_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volatility-based indicators"""
        if 'close' not in df.columns:
            return df

        # 1. Historical Volatility
        returns = df['close'].pct_change()
        df['hist_vol_20'] = returns.rolling(20).std() * np.sqrt(252)

        # 2. Garman-Klass Volatility
        if all(col in df.columns for col in ['high', 'low', 'open', 'close']):
            df['gk_volatility'] = self._calculate_garman_klass_volatility(df)

        # 3. Average True Range Percent
        if all(col in df.columns for col in ['high', 'low', 'close']):
            df['atr_14'] = talib.ATR(
                self._ensure_float64(df['high'].values),
                self._ensure_float64(df['low'].values),
                self._ensure_float64(df['close'].values),
                timeperiod=14
            )
            df['atr_percent'] = (df['atr_14'] / df['close']) * 100

        # 4. Volatility Ratio
        df['vol_ratio'] = df['hist_vol_20'] / df['hist_vol_20'].rolling(60).mean()

        # 5. Keltner Channels
        if all(col in df.columns for col in ['high', 'low', 'close']):
            ema_20 = df['close'].ewm(span=20).mean()
            atr_10 = talib.ATR(
                self._ensure_float64(df['high'].values),
                self._ensure_float64(df['low'].values),
                self._ensure_float64(df['close'].values),
                timeperiod=10
            )
            df['keltner_upper'] = ema_20 + (2 * atr_10)
            df['keltner_lower'] = ema_20 - (2 * atr_10)
            df['keltner_position'] = (df['close'] - df['keltner_lower']) / (df['keltner_upper'] - df['keltner_lower'])

        return df

    def _calculate_volume_price_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume-price relationship indicators"""
        if not all(col in df.columns for col in ['close', 'volume']):
            return df

        # 1. Volume Weighted Average Price (VWAP)
        if 'high' in df.columns and 'low' in df.columns:
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()

        # 2. On Balance Volume (OBV)
        df['obv'] = talib.OBV(
            self._ensure_float64(df['close'].values),
            self._ensure_float64(df['volume'].values)
        )

        # 3. Accumulation/Distribution Line
        if all(col in df.columns for col in ['high', 'low', 'close', 'volume']):
            df['ad_line'] = talib.AD(
                self._ensure_float64(df['high'].values),
                self._ensure_float64(df['low'].values),
                self._ensure_float64(df['close'].values),
                self._ensure_float64(df['volume'].values)
            )

        # 4. Chaikin Money Flow
        if all(col in df.columns for col in ['high', 'low', 'close', 'volume']):
            df['cmf'] = self._calculate_chaikin_money_flow(df)

        # 5. Volume Price Trend (VPT)
        price_change_pct = df['close'].pct_change()
        df['vpt'] = (price_change_pct * df['volume']).cumsum()

        # 6. Price Volume Divergence
        df['pv_divergence'] = self._calculate_price_volume_divergence(df)

        return df

    def _calculate_market_structure_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate market structure indicators"""
        if 'close' not in df.columns:
            return df

        # 1. Market Structure (Higher Highs, Lower Lows)
        df['market_structure'] = self._calculate_market_structure(df)

        # 2. Support and Resistance Levels
        support_resistance = self._calculate_support_resistance_levels(df)
        df['nearest_support'] = support_resistance['nearest_support']
        df['nearest_resistance'] = support_resistance['nearest_resistance']

        # 3. Pivot Points
        if all(col in df.columns for col in ['high', 'low', 'close']):
            pivot_points = self._calculate_pivot_points(df)
            for key, value in pivot_points.items():
                df[key] = value

        # 4. Fractal Dimension
        df['fractal_dimension'] = self._calculate_fractal_dimension(df['close'])

        return df

    def _calculate_fibonacci_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Fibonacci-based indicators"""
        if len(df) < 50:
            return df

        # 1. Fibonacci Retracement Levels
        fib_levels = self._calculate_fibonacci_retracements(df)
        for level, value in fib_levels.items():
            df[f'fib_{level}'] = value

        # 2. Fibonacci Extensions
        fib_extensions = self._calculate_fibonacci_extensions(df)
        for level, value in fib_extensions.items():
            df[f'fib_ext_{level}'] = value

        # 3. Fibonacci Time Zones
        df['fib_time_zone'] = self._calculate_fibonacci_time_zones(df)

        return df

    def _calculate_statistical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate statistical indicators"""
        if 'close' not in df.columns:
            return df

        # 1. Z-Score
        rolling_mean = df['close'].rolling(20).mean()
        rolling_std = df['close'].rolling(20).std()
        df['zscore'] = (df['close'] - rolling_mean) / rolling_std

        # 2. Percentile Rank
        df['percentile_rank'] = df['close'].rolling(252).rank(pct=True)

        # 3. Linear Regression
        df['linear_reg'] = self._calculate_linear_regression(df['close'])
        df['linear_reg_slope'] = self._calculate_linear_regression_slope(df['close'])

        # 4. Correlation with Market (if available)
        # This would require market index data
        # df['market_correlation'] = self._calculate_market_correlation(df)

        # 5. Beta Coefficient
        # df['beta'] = self._calculate_beta(df)

        return df

    def _calculate_cycle_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate cycle analysis indicators"""
        if len(df) < 100:
            return df

        # 1. Dominant Cycle Period
        df['dominant_cycle'] = self._calculate_dominant_cycle(df['close'])

        # 2. Cycle Phase
        df['cycle_phase'] = self._calculate_cycle_phase(df['close'])

        # 3. Cycle Strength
        df['cycle_strength'] = self._calculate_cycle_strength(df['close'])

        # 4. Hilbert Transform - SineWave
        if len(df) > 50:
            sine, leadsine = talib.HT_SINE(self._ensure_float64(df['close'].values))
            df['ht_sine'] = sine
            df['ht_leadsine'] = leadsine

        return df

    def _calculate_smi(self, df: pd.DataFrame, k_period: int = 10, d_period: int = 3) -> pd.Series:
        """Calculate Stochastic Momentum Index"""
        ll = df['low'].rolling(k_period).min()
        hh = df['high'].rolling(k_period).max()
        diff = hh - ll
        rdiff = df['close'] - (hh + ll) / 2

        avgrel = rdiff.ewm(span=d_period).mean().ewm(span=d_period).mean()
        avgdiff = diff.ewm(span=d_period).mean().ewm(span=d_period).mean()

        smi = np.where(avgdiff != 0, (avgrel / avgdiff) * 100, 0)
        return pd.Series(smi, index=df.index)

    def _calculate_tsi(self, df: pd.DataFrame, r: int = 25, s: int = 13) -> pd.Series:
        """Calculate True Strength Index"""
        price_changes = df['close'].diff()
        double_smoothed_pc = price_changes.ewm(span=r).mean().ewm(span=s).mean()
        double_smoothed_abs_pc = price_changes.abs().ewm(span=r).mean().ewm(span=s).mean()

        tsi = 100 * (double_smoothed_pc / double_smoothed_abs_pc)
        return tsi.fillna(0)

    def _calculate_rvi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Relative Vigor Index"""
        numerator = (df['close'] - df['open']) + 2 * (df['close'].shift(1) - df['open'].shift(1)) + \
                   2 * (df['close'].shift(2) - df['open'].shift(2)) + (df['close'].shift(3) - df['open'].shift(3))

        denominator = (df['high'] - df['low']) + 2 * (df['high'].shift(1) - df['low'].shift(1)) + \
                     2 * (df['high'].shift(2) - df['low'].shift(2)) + (df['high'].shift(3) - df['low'].shift(3))

        rvi = numerator.rolling(period).mean() / denominator.rolling(period).mean()
        return rvi.fillna(0)

    def _calculate_garman_klass_volatility(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """Calculate Garman-Klass volatility estimator"""
        rs = np.log(df['high'] / df['close']) * np.log(df['high'] / df['open']) + \
             np.log(df['low'] / df['close']) * np.log(df['low'] / df['open'])

        gk_vol = np.sqrt(rs.rolling(window).mean() * 252)
        return gk_vol

    def _calculate_chaikin_money_flow(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Chaikin Money Flow"""
        mf_multiplier = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        mf_volume = mf_multiplier * df['volume']
        cmf = mf_volume.rolling(period).sum() / df['volume'].rolling(period).sum()
        return cmf.fillna(0)

    def _calculate_price_volume_divergence(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """Calculate price-volume divergence"""
        price_trend = df['close'].rolling(window).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0])
        volume_trend = df['volume'].rolling(window).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0])

        # Normalize trends
        price_trend_norm = (price_trend - price_trend.mean()) / price_trend.std()
        volume_trend_norm = (volume_trend - volume_trend.mean()) / volume_trend.std()

        # Calculate divergence (when trends move in opposite directions)
        divergence = price_trend_norm * volume_trend_norm
        return divergence.fillna(0)

    def _detect_candlestick_patterns(self, data: pd.DataFrame) -> Dict[str, bool]:
        """Detect candlestick patterns using TA-Lib"""
        patterns = {}

        if not all(col in data.columns for col in ['open', 'high', 'low', 'close']):
            return patterns

        o = self._ensure_float64(data['open'].values)
        h = self._ensure_float64(data['high'].values)
        l = self._ensure_float64(data['low'].values)
        c = self._ensure_float64(data['close'].values)

        # Major reversal patterns
        patterns['hammer'] = bool(talib.CDLHAMMER(o, h, l, c)[-1])
        patterns['hanging_man'] = bool(talib.CDLHANGINGMAN(o, h, l, c)[-1])
        patterns['doji'] = bool(talib.CDLDOJI(o, h, l, c)[-1])
        patterns['shooting_star'] = bool(talib.CDLSHOOTINGSTAR(o, h, l, c)[-1])
        patterns['engulfing_bullish'] = bool(talib.CDLENGULFING(o, h, l, c)[-1] > 0)
        patterns['engulfing_bearish'] = bool(talib.CDLENGULFING(o, h, l, c)[-1] < 0)

        # Continuation patterns
        patterns['spinning_top'] = bool(talib.CDLSPINNINGTOP(o, h, l, c)[-1])
        patterns['marubozu'] = bool(talib.CDLMARUBOZU(o, h, l, c)[-1])

        # Complex patterns
        patterns['morning_star'] = bool(talib.CDLMORNINGSTAR(o, h, l, c)[-1])
        patterns['evening_star'] = bool(talib.CDLEVENINGSTAR(o, h, l, c)[-1])
        patterns['three_white_soldiers'] = bool(talib.CDL3WHITESOLDIERS(o, h, l, c)[-1])
        patterns['three_black_crows'] = bool(talib.CDL3BLACKCROWS(o, h, l, c)[-1])

        return patterns

    def _detect_chart_patterns(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Detect chart patterns"""
        patterns = {
            'head_and_shoulders': False,
            'double_top': False,
            'double_bottom': False,
            'triangle': 'none',  # ascending, descending, symmetrical
            'flag': 'none',      # bullish, bearish
            'cup_and_handle': False
        }

        if len(data) < 50:
            return patterns

        # Simplified pattern detection
        # In practice, this would use more sophisticated algorithms
        close_prices = data['close'].values

        # Find peaks and valleys
        peaks, _ = find_peaks(close_prices, distance=20)
        valleys, _ = find_peaks(-close_prices, distance=20)

        # Double top/bottom detection
        if len(peaks) >= 2:
            patterns['double_top'] = self._is_double_top(close_prices, peaks)

        if len(valleys) >= 2:
            patterns['double_bottom'] = self._is_double_bottom(close_prices, valleys)

        # Triangle pattern detection
        patterns['triangle'] = self._detect_triangle_pattern(data)

        return patterns

    def _detect_wave_patterns(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Detect Elliott Wave patterns (simplified)"""
        wave_patterns = {
            'wave_count': 0,
            'current_wave': 'unknown',
            'wave_degree': 'minor',
            'fibonacci_relationships': {}
        }

        if len(data) < 100:
            return wave_patterns

        # Simplified Elliott Wave detection
        # This is a complex topic that would require extensive implementation
        close_prices = data['close'].values

        # Find significant swing points
        swing_points = self._find_significant_swings(close_prices)

        if len(swing_points) >= 5:
            wave_patterns['wave_count'] = len(swing_points)
            wave_patterns['current_wave'] = self._identify_current_wave(swing_points)

        return wave_patterns

    def _detect_statistical_patterns(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Detect statistical patterns"""
        patterns = {
            'mean_reversion_signal': 0.0,
            'momentum_signal': 0.0,
            'volatility_clustering': False,
            'serial_correlation': 0.0
        }

        if len(data) < 50:
            return patterns

        returns = data['close'].pct_change().dropna()

        # Mean reversion signal (based on z-score)
        z_score = (data['close'].iloc[-1] - data['close'].rolling(20).mean().iloc[-1]) / data['close'].rolling(20).std().iloc[-1]
        patterns['mean_reversion_signal'] = float(z_score) if not np.isnan(z_score) else 0.0

        # Momentum signal
        momentum = data['close'].iloc[-1] / data['close'].iloc[-20] - 1
        patterns['momentum_signal'] = float(momentum) if not np.isnan(momentum) else 0.0

        # Volatility clustering (ARCH effects)
        patterns['volatility_clustering'] = self._test_volatility_clustering(returns)

        # Serial correlation
        if len(returns) > 1:
            patterns['serial_correlation'] = float(returns.autocorr(lag=1)) if not np.isnan(returns.autocorr(lag=1)) else 0.0

        return patterns

    # Additional helper methods would continue here...
    # Due to length constraints, I'm including the key structure
    # The full implementation would include all the helper methods

    def _calculate_fear_greed_index(self, data: pd.DataFrame) -> float:
        """Calculate Fear & Greed Index components"""
        # Simplified implementation
        # Real Fear & Greed index uses multiple market indicators
        components = []

        # Volatility component (VIX-like)
        if len(data) > 20:
            returns = data['close'].pct_change()
            volatility = returns.rolling(20).std() * np.sqrt(252)
            vol_score = min(100, max(0, 100 - (volatility.iloc[-1] * 1000)))
            components.append(vol_score)

        # Momentum component
        if len(data) > 125:
            momentum = (data['close'].iloc[-1] / data['close'].iloc[-125] - 1) * 100
            momentum_score = min(100, max(0, 50 + momentum))
            components.append(momentum_score)

        return np.mean(components) if components else 50.0

    def _synthesize_sentiment(self, sentiment: Dict[str, Any]) -> str:
        """Synthesize overall sentiment from components"""
        numeric_scores = [v for k, v in sentiment.items() if isinstance(v, (int, float)) and k != 'fear_greed_index']

        if not numeric_scores:
            return 'neutral'

        avg_score = np.mean(numeric_scores)

        if avg_score > 0.6:
            return 'bullish'
        elif avg_score < -0.6:
            return 'bearish'
        elif avg_score > 0.2:
            return 'slightly_bullish'
        elif avg_score < -0.2:
            return 'slightly_bearish'
        else:
            return 'neutral'

    # Placeholder methods for complex calculations
    def _calculate_momentum_sentiment(self, data: pd.DataFrame) -> float:
        """Calculate momentum-based sentiment"""
        return 0.0  # Placeholder

    def _calculate_volume_sentiment(self, data: pd.DataFrame) -> float:
        """Calculate volume-based sentiment"""
        return 0.0  # Placeholder

    def _calculate_volatility_sentiment(self, data: pd.DataFrame) -> float:
        """Calculate volatility-based sentiment"""
        return 0.0  # Placeholder

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Main analysis method that combines all advanced technical analysis features

        Args:
            data: OHLCV price data

        Returns:
            Dictionary containing comprehensive analysis results
        """
        logger.info("Performing advanced technical analysis")

        if data.empty:
            return {
                'pattern_strength': 0.0,
                'sentiment_score': 0.0,
                'patterns': {},
                'indicators': {},
                'regime': {},
                'signals': {}
            }

        try:
            # 1. Calculate advanced indicators
            enhanced_data = self.calculate_advanced_indicators(data)

            # 2. Perform pattern recognition
            patterns = self.perform_pattern_recognition(data)

            # 3. Calculate sentiment indicators
            sentiment = self.calculate_sentiment_indicators(data)

            # 4. Perform regime detection
            regime = self.perform_regime_detection(data)

            # 5. Calculate pattern strength score
            pattern_strength = self._calculate_overall_pattern_strength(patterns)

            # 6. Calculate sentiment score
            sentiment_score = self._calculate_overall_sentiment_score(sentiment)

            # 7. Generate trading signals
            signals = self._generate_trading_signals(enhanced_data, patterns, sentiment, regime)

            return {
                'pattern_strength': pattern_strength,
                'sentiment_score': sentiment_score,
                'patterns': patterns,
                'indicators': self._extract_key_indicators(enhanced_data),
                'regime': regime,
                'sentiment': sentiment,
                'signals': signals,
                'confidence': self._calculate_analysis_confidence(patterns, sentiment, regime)
            }

        except Exception as e:
            logger.error(f"Error in advanced technical analysis: {e}")
            return {
                'pattern_strength': 0.0,
                'sentiment_score': 0.0,
                'patterns': {},
                'indicators': {},
                'regime': {'overall_regime': 'unknown'},
                'signals': {},
                'error': str(e)
            }

    def _calculate_overall_pattern_strength(self, patterns: Dict[str, Any]) -> float:
        """Calculate overall pattern strength from detected patterns"""
        strength_scores = []

        # Candlestick patterns
        if 'candlestick_patterns' in patterns:
            candlestick_count = sum(1 for v in patterns['candlestick_patterns'].values() if v)
            strength_scores.append(min(1.0, candlestick_count * 0.1))

        # Chart patterns
        if 'chart_patterns' in patterns:
            chart_patterns = patterns['chart_patterns']
            chart_score = 0.0
            if chart_patterns.get('double_top') or chart_patterns.get('double_bottom'):
                chart_score += 0.3
            if chart_patterns.get('head_and_shoulders'):
                chart_score += 0.4
            if chart_patterns.get('triangle') != 'none':
                chart_score += 0.2
            strength_scores.append(min(1.0, chart_score))

        # Statistical patterns
        if 'statistical_patterns' in patterns:
            stat_patterns = patterns['statistical_patterns']
            momentum_strength = abs(stat_patterns.get('momentum_signal', 0.0))
            mean_reversion_strength = abs(stat_patterns.get('mean_reversion_signal', 0.0))
            strength_scores.append(min(1.0, (momentum_strength + mean_reversion_strength) / 2))

        return np.mean(strength_scores) if strength_scores else 0.0

    def _calculate_overall_sentiment_score(self, sentiment: Dict[str, Any]) -> float:
        """Calculate overall sentiment score"""
        sentiment_mapping = {
            'bearish': -1.0,
            'slightly_bearish': -0.5,
            'neutral': 0.0,
            'slightly_bullish': 0.5,
            'bullish': 1.0
        }

        overall_sentiment = sentiment.get('overall_sentiment', 'neutral')
        base_score = sentiment_mapping.get(overall_sentiment, 0.0)

        # Adjust based on fear/greed index
        fear_greed = sentiment.get('fear_greed_index', 50.0)
        fear_greed_adjustment = (fear_greed - 50.0) / 100.0  # Convert to -0.5 to 0.5 range

        final_score = (base_score + fear_greed_adjustment) / 2
        return max(-1.0, min(1.0, final_score))

    def _extract_key_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Extract key indicators from enhanced data"""
        indicators = {}

        if data.empty:
            return indicators

        # Get latest values of key indicators
        latest = data.iloc[-1] if len(data) > 0 else {}

        key_indicators = [
            'rsi_14', 'macd', 'bb_position', 'sma_20', 'ema_20',
            'atr_14', 'obv', 'vwap', 'zscore', 'momentum_14'
        ]

        for indicator in key_indicators:
            if indicator in latest:
                value = latest[indicator]
                if pd.notna(value):
                    indicators[indicator] = float(value)

        return indicators

    def _generate_trading_signals(self, data: pd.DataFrame, patterns: Dict[str, Any],
                                sentiment: Dict[str, Any], regime: Dict[str, Any]) -> Dict[str, Any]:
        """Generate trading signals based on analysis"""
        signals = {
            'signal': 'HOLD',
            'strength': 0.0,
            'confidence': 0.0,
            'entry_price': None,
            'stop_loss': None,
            'take_profit': None
        }

        if data.empty:
            return signals

        current_price = data['close'].iloc[-1]

        # Combine multiple signal sources
        signal_scores = []

        # Pattern-based signals
        pattern_score = self._get_pattern_signal_score(patterns)
        signal_scores.append(pattern_score)

        # Sentiment-based signals
        sentiment_score = self._get_sentiment_signal_score(sentiment)
        signal_scores.append(sentiment_score)

        # Regime-based signals
        regime_score = self._get_regime_signal_score(regime)
        signal_scores.append(regime_score)

        # Technical indicator signals
        if not data.empty and len(data) > 20:
            tech_score = self._get_technical_signal_score(data)
            signal_scores.append(tech_score)

        # Calculate overall signal
        overall_score = np.mean(signal_scores)

        if overall_score > 0.3:
            signals['signal'] = 'BUY'
        elif overall_score < -0.3:
            signals['signal'] = 'SELL'
        else:
            signals['signal'] = 'HOLD'

        signals['strength'] = abs(overall_score)
        signals['confidence'] = min(1.0, len(signal_scores) * 0.2)  # More sources = higher confidence

        # Calculate price levels
        if signals['signal'] != 'HOLD':
            atr = data.get('atr_14', pd.Series()).iloc[-1] if 'atr_14' in data.columns else current_price * 0.02
            if pd.isna(atr):
                atr = current_price * 0.02

            signals['entry_price'] = float(current_price)
            signals['stop_loss'] = float(current_price - (2 * atr) if signals['signal'] == 'BUY' else current_price + (2 * atr))
            signals['take_profit'] = float(current_price + (3 * atr) if signals['signal'] == 'BUY' else current_price - (3 * atr))

        return signals

    def _get_pattern_signal_score(self, patterns: Dict[str, Any]) -> float:
        """Get signal score from patterns"""
        score = 0.0

        # Candlestick patterns
        if 'candlestick_patterns' in patterns:
            cp = patterns['candlestick_patterns']
            if cp.get('engulfing_bullish') or cp.get('hammer') or cp.get('morning_star'):
                score += 0.3
            if cp.get('engulfing_bearish') or cp.get('hanging_man') or cp.get('evening_star'):
                score -= 0.3

        # Chart patterns
        if 'chart_patterns' in patterns:
            chart_p = patterns['chart_patterns']
            if chart_p.get('double_bottom'):
                score += 0.4
            if chart_p.get('double_top'):
                score -= 0.4

        return max(-1.0, min(1.0, score))

    def _get_sentiment_signal_score(self, sentiment: Dict[str, Any]) -> float:
        """Get signal score from sentiment"""
        sentiment_mapping = {
            'bearish': -0.8,
            'slightly_bearish': -0.3,
            'neutral': 0.0,
            'slightly_bullish': 0.3,
            'bullish': 0.8
        }

        return sentiment_mapping.get(sentiment.get('overall_sentiment', 'neutral'), 0.0)

    def _get_regime_signal_score(self, regime: Dict[str, Any]) -> float:
        """Get signal score from market regime"""
        overall_regime = regime.get('overall_regime', {})

        # Handle case where overall_regime is a dictionary
        if isinstance(overall_regime, dict):
            regime_type = overall_regime.get('regime', 'unknown')
        else:
            regime_type = overall_regime

        regime_scores = {
            'bullish': 0.6,
            'bearish': -0.6,
            'neutral': 0.2,
            'uncertain': 0.0,
            'unknown': 0.0
        }

        return regime_scores.get(regime_type, 0.0)

    def _get_technical_signal_score(self, data: pd.DataFrame) -> float:
        """Get signal score from technical indicators"""
        score = 0.0
        count = 0

        # RSI
        if 'rsi_14' in data.columns:
            rsi = data['rsi_14'].iloc[-1]
            if pd.notna(rsi):
                if rsi < 30:
                    score += 0.5  # Oversold
                elif rsi > 70:
                    score -= 0.5  # Overbought
                count += 1

        # MACD
        if 'macd' in data.columns and 'macd_signal' in data.columns:
            macd = data['macd'].iloc[-1]
            macd_signal = data['macd_signal'].iloc[-1]
            if pd.notna(macd) and pd.notna(macd_signal):
                if macd > macd_signal:
                    score += 0.3
                else:
                    score -= 0.3
                count += 1

        # Moving averages
        if 'sma_20' in data.columns and 'sma_50' in data.columns:
            sma_20 = data['sma_20'].iloc[-1]
            sma_50 = data['sma_50'].iloc[-1]
            if pd.notna(sma_20) and pd.notna(sma_50):
                if sma_20 > sma_50:
                    score += 0.2
                else:
                    score -= 0.2
                count += 1

        return score / count if count > 0 else 0.0

    def _calculate_analysis_confidence(self, patterns: Dict[str, Any],
                                     sentiment: Dict[str, Any],
                                     regime: Dict[str, Any]) -> float:
        """Calculate overall confidence in the analysis"""
        confidence_factors = []

        # Pattern confidence
        pattern_count = 0
        if 'candlestick_patterns' in patterns:
            pattern_count += sum(1 for v in patterns['candlestick_patterns'].values() if v)
        if 'chart_patterns' in patterns:
            pattern_count += sum(1 for k, v in patterns['chart_patterns'].items()
                               if (isinstance(v, bool) and v) or (isinstance(v, str) and v != 'none'))

        confidence_factors.append(min(1.0, pattern_count * 0.1))

        # Sentiment confidence
        sentiment_strength = abs(sentiment.get('fear_greed_index', 50.0) - 50.0) / 50.0
        confidence_factors.append(sentiment_strength)

        # Regime confidence
        regime_strength_data = regime.get('regime_strength', 0.0)
        if isinstance(regime_strength_data, dict):
            regime_strength = regime_strength_data.get('strength', 0.0)
        else:
            regime_strength = regime_strength_data
        confidence_factors.append(regime_strength)

        return np.mean(confidence_factors) if confidence_factors else 0.0

    def _calculate_market_structure(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate market structure (Higher Highs, Lower Lows pattern)

        Args:
            df: Price data DataFrame

        Returns:
            Series with market structure values
        """
        if 'close' not in df.columns or len(df) < 20:
            return pd.Series(0, index=df.index)

        close = df['close']
        structure = []

        for i in range(len(close)):
            if i < 10:  # Need enough history
                structure.append(0)
                continue

            # Look at last 10 periods for trend determination
            recent_high = close.iloc[max(0, i-9):i+1].max()
            recent_low = close.iloc[max(0, i-9):i+1].min()
            current_price = close.iloc[i]

            # Look at previous 10 periods for comparison
            prev_high = close.iloc[max(0, i-19):max(1, i-9)].max()
            prev_low = close.iloc[max(0, i-19):max(1, i-9)].min()

            # Determine structure
            if recent_high > prev_high and recent_low > prev_low:
                structure.append(1)  # Higher Highs, Higher Lows (Uptrend)
            elif recent_high < prev_high and recent_low < prev_low:
                structure.append(-1)  # Lower Highs, Lower Lows (Downtrend)
            elif recent_high > prev_high and recent_low < prev_low:
                structure.append(0.5)  # Expanding range
            elif recent_high < prev_high and recent_low > prev_low:
                structure.append(-0.5)  # Contracting range
            else:
                structure.append(0)  # Sideways

        return pd.Series(structure, index=df.index)

    def _calculate_support_resistance_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate support and resistance levels

        Args:
            df: Price data DataFrame

        Returns:
            Dictionary with support and resistance levels
        """
        try:
            if 'close' not in df.columns:
                empty_series = pd.Series(0.0, index=df.index if not df.empty else [])
                return {
                    'support_levels': [],
                    'resistance_levels': [],
                    'current_support': 0.0,
                    'current_resistance': 0.0,
                    'nearest_support': empty_series,
                    'nearest_resistance': empty_series,
                    'strength_scores': {}
                }

            close_prices = df['close'].dropna()
            if len(close_prices) < 20:
                empty_series = pd.Series(0.0, index=df.index if not df.empty else [])
                return {
                    'support_levels': [],
                    'resistance_levels': [],
                    'current_support': 0.0,
                    'current_resistance': 0.0,
                    'nearest_support': empty_series,
                    'nearest_resistance': empty_series,
                    'strength_scores': {}
                }

            # Find local minima and maxima
            from scipy.signal import find_peaks

            # Find peaks (resistance) and valleys (support)
            peaks, _ = find_peaks(close_prices.values, distance=5, prominence=close_prices.std() * 0.5)
            valleys, _ = find_peaks(-close_prices.values, distance=5, prominence=close_prices.std() * 0.5)

            # Get resistance levels from peaks
            resistance_levels = []
            if len(peaks) > 0:
                resistance_prices = close_prices.iloc[peaks].values
                resistance_levels = list(resistance_prices)

            # Get support levels from valleys
            support_levels = []
            if len(valleys) > 0:
                support_prices = close_prices.iloc[valleys].values
                support_levels = list(support_prices)

            # Find current support and resistance
            current_price = close_prices.iloc[-1]

            # Current support: highest support level below current price
            current_support = 0.0
            if support_levels:
                valid_supports = [s for s in support_levels if s < current_price]
                if valid_supports:
                    current_support = max(valid_supports)

            # Current resistance: lowest resistance level above current price
            current_resistance = 0.0
            if resistance_levels:
                valid_resistances = [r for r in resistance_levels if r > current_price]
                if valid_resistances:
                    current_resistance = min(valid_resistances)

            # Calculate strength scores (simplified)
            strength_scores = {
                'support_strength': len(support_levels) / max(1, len(close_prices) // 10),
                'resistance_strength': len(resistance_levels) / max(1, len(close_prices) // 10)
            }

            # Create series for nearest support/resistance for each data point
            nearest_support_series = pd.Series(current_support, index=close_prices.index)
            nearest_resistance_series = pd.Series(current_resistance, index=close_prices.index)

            return {
                'support_levels': sorted(support_levels, reverse=True)[:5],  # Top 5
                'resistance_levels': sorted(resistance_levels)[:5],  # Top 5
                'current_support': float(current_support),
                'current_resistance': float(current_resistance),
                'nearest_support': nearest_support_series,
                'nearest_resistance': nearest_resistance_series,
                'strength_scores': strength_scores
            }

        except Exception as e:
            logger.warning(f"Support/resistance calculation failed: {e}")
            # Create empty series for fallback
            empty_series = pd.Series(0.0, index=df.index if not df.empty else [])
            return {
                'support_levels': [],
                'resistance_levels': [],
                'current_support': 0.0,
                'current_resistance': 0.0,
                'nearest_support': empty_series,
                'nearest_resistance': empty_series,
                'strength_scores': {}
            }

    def _calculate_pivot_points(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calculate pivot points and related levels

        Args:
            df: Price data DataFrame with high, low, close columns

        Returns:
            Dictionary with pivot point series
        """
        try:
            if not all(col in df.columns for col in ['high', 'low', 'close']):
                empty_series = pd.Series(0.0, index=df.index)
                return {
                    'pivot_point': empty_series,
                    'resistance_1': empty_series,
                    'resistance_2': empty_series,
                    'support_1': empty_series,
                    'support_2': empty_series
                }

            high = df['high']
            low = df['low']
            close = df['close']

            # Standard Pivot Point formula
            pivot_point = (high + low + close) / 3

            # Calculate resistance and support levels
            resistance_1 = 2 * pivot_point - low
            resistance_2 = pivot_point + (high - low)
            support_1 = 2 * pivot_point - high
            support_2 = pivot_point - (high - low)

            return {
                'pivot_point': pivot_point,
                'resistance_1': resistance_1,
                'resistance_2': resistance_2,
                'support_1': support_1,
                'support_2': support_2
            }

        except Exception as e:
            logger.warning(f"Pivot point calculation failed: {e}")
            empty_series = pd.Series(0.0, index=df.index if not df.empty else [])
            return {
                'pivot_point': empty_series,
                'resistance_1': empty_series,
                'resistance_2': empty_series,
                'support_1': empty_series,
                'support_2': empty_series
            }

    def _calculate_fractal_dimension(self, price_series: pd.Series) -> pd.Series:
        """
        Calculate fractal dimension using Higuchi's method

        Args:
            price_series: Price series data

        Returns:
            Series with fractal dimension values
        """
        try:
            if len(price_series) < 50:
                return pd.Series(1.5, index=price_series.index)  # Default fractal dimension

            prices = price_series.dropna()
            if len(prices) < 50:
                return pd.Series(1.5, index=price_series.index)

            # Simplified fractal dimension calculation
            # Using a rolling window approach
            window_size = min(50, len(prices) // 2)
            fractal_dims = []

            for i in range(len(prices)):
                start_idx = max(0, i - window_size + 1)
                end_idx = i + 1
                window_data = prices.iloc[start_idx:end_idx]

                if len(window_data) < 10:
                    fractal_dims.append(1.5)
                    continue

                # Simplified Higuchi's method calculation
                try:
                    k_max = min(10, len(window_data) // 2)
                    lk_values = []

                    for k in range(1, k_max + 1):
                        lk = 0
                        for m in range(k):
                            lm = 0
                            n_max = int((len(window_data) - m - 1) / k)
                            if n_max < 1:
                                continue

                            for n in range(1, n_max + 1):
                                if m + n * k < len(window_data):
                                    lm += abs(window_data.iloc[m + n * k] - window_data.iloc[m + (n - 1) * k])

                            if n_max > 0:
                                lm = (lm * (len(window_data) - 1)) / (n_max * k * k)
                                lk += lm

                        if k > 0:
                            lk_values.append(lk / k)

                    if len(lk_values) >= 2:
                        # Calculate fractal dimension using regression
                        k_values = list(range(1, len(lk_values) + 1))
                        log_k = [np.log(k) for k in k_values]
                        log_lk = [np.log(lk) if lk > 0 else 0 for lk in lk_values]

                        # Simple linear regression
                        n = len(log_k)
                        sum_x = sum(log_k)
                        sum_y = sum(log_lk)
                        sum_xy = sum(x * y for x, y in zip(log_k, log_lk))
                        sum_x2 = sum(x * x for x in log_k)

                        if n * sum_x2 - sum_x * sum_x != 0:
                            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                            fractal_dim = -slope
                            # Clamp between reasonable bounds
                            fractal_dim = max(1.0, min(2.0, fractal_dim))
                        else:
                            fractal_dim = 1.5
                    else:
                        fractal_dim = 1.5

                except Exception:
                    fractal_dim = 1.5

                fractal_dims.append(fractal_dim)

            return pd.Series(fractal_dims, index=prices.index)

        except Exception as e:
            logger.warning(f"Fractal dimension calculation failed: {e}")
            return pd.Series(1.5, index=price_series.index)

    def _calculate_fibonacci_retracements(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calculate Fibonacci retracement levels

        Args:
            df: Price data DataFrame with high, low, close columns

        Returns:
            Dictionary with Fibonacci retracement series
        """
        try:
            if not all(col in df.columns for col in ['high', 'low', 'close']):
                empty_series = pd.Series(0.0, index=df.index)
                return {
                    'fib_23_6': empty_series,
                    'fib_38_2': empty_series,
                    'fib_50_0': empty_series,
                    'fib_61_8': empty_series,
                    'fib_78_6': empty_series
                }

            high = df['high']
            low = df['low']
            close = df['close']

            # Calculate rolling max and min over a lookback period
            lookback = min(50, len(df) // 2)
            rolling_high = high.rolling(window=lookback, min_periods=1).max()
            rolling_low = low.rolling(window=lookback, min_periods=1).min()

            # Calculate the range
            price_range = rolling_high - rolling_low

            # Fibonacci retracement levels (from high to low)
            fib_levels = {
                'fib_23_6': rolling_high - 0.236 * price_range,
                'fib_38_2': rolling_high - 0.382 * price_range,
                'fib_50_0': rolling_high - 0.500 * price_range,
                'fib_61_8': rolling_high - 0.618 * price_range,
                'fib_78_6': rolling_high - 0.786 * price_range
            }

            return fib_levels

        except Exception as e:
            logger.warning(f"Fibonacci retracement calculation failed: {e}")
            empty_series = pd.Series(0.0, index=df.index if not df.empty else [])
            return {
                'fib_23_6': empty_series,
                'fib_38_2': empty_series,
                'fib_50_0': empty_series,
                'fib_61_8': empty_series,
                'fib_78_6': empty_series
            }

    def _calculate_fibonacci_extensions(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calculate Fibonacci extension levels

        Args:
            df: Price data DataFrame with high, low, close columns

        Returns:
            Dictionary with Fibonacci extension series
        """
        try:
            if not all(col in df.columns for col in ['high', 'low', 'close']):
                empty_series = pd.Series(0.0, index=df.index)
                return {
                    'fib_ext_127_2': empty_series,
                    'fib_ext_161_8': empty_series,
                    'fib_ext_200_0': empty_series,
                    'fib_ext_261_8': empty_series,
                    'fib_ext_423_6': empty_series
                }

            high = df['high']
            low = df['low']
            close = df['close']

            # Calculate rolling max and min over a lookback period
            lookback = min(50, len(df) // 2)
            rolling_high = high.rolling(window=lookback, min_periods=1).max()
            rolling_low = low.rolling(window=lookback, min_periods=1).min()

            # Calculate the range
            price_range = rolling_high - rolling_low

            # Fibonacci extension levels (beyond 100%)
            fib_extensions = {
                'fib_ext_127_2': rolling_high + 0.272 * price_range,
                'fib_ext_161_8': rolling_high + 0.618 * price_range,
                'fib_ext_200_0': rolling_high + 1.000 * price_range,
                'fib_ext_261_8': rolling_high + 1.618 * price_range,
                'fib_ext_423_6': rolling_high + 3.236 * price_range
            }

            return fib_extensions

        except Exception as e:
            logger.warning(f"Fibonacci extension calculation failed: {e}")
            empty_series = pd.Series(0.0, index=df.index if not df.empty else [])
            return {
                'fib_ext_127_2': empty_series,
                'fib_ext_161_8': empty_series,
                'fib_ext_200_0': empty_series,
                'fib_ext_261_8': empty_series,
                'fib_ext_423_6': empty_series
            }

    def _calculate_fibonacci_time_zones(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate Fibonacci time zones

        Args:
            df: Price data DataFrame

        Returns:
            Series with Fibonacci time zone values
        """
        try:
            if len(df) < 20:
                return pd.Series(0, index=df.index)

            # Fibonacci sequence for time zones: 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144...
            fib_sequence = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]

            # Initialize time zone series
            time_zones = pd.Series(0, index=df.index)

            # Find significant price points (local highs and lows)
            if 'close' in df.columns:
                close_prices = df['close']

                # Simple peak detection for demonstration
                from scipy.signal import find_peaks
                peaks, _ = find_peaks(close_prices.values, distance=10)
                valleys, _ = find_peaks(-close_prices.values, distance=10)

                # Combine and sort significant points
                significant_points = sorted(list(peaks) + list(valleys))

                # Apply Fibonacci time zones from significant points
                for start_point in significant_points:
                    for fib_num in fib_sequence:
                        target_index = start_point + fib_num
                        if target_index < len(df):
                            # Mark Fibonacci time zone with the sequence number
                            time_zones.iloc[target_index] = fib_num
                        else:
                            break  # Stop if we exceed the data range

            return time_zones

        except Exception as e:
            logger.warning(f"Fibonacci time zone calculation failed: {e}")
            return pd.Series(0, index=df.index)

    def _calculate_linear_regression(self, price_series: pd.Series, window: int = 20) -> pd.Series:
        """
        Calculate linear regression values for price series

        Args:
            price_series: Price series data
            window: Rolling window size

        Returns:
            Series with linear regression values
        """
        try:
            if len(price_series) < window:
                return pd.Series(price_series.iloc[0], index=price_series.index)

            linear_reg_values = []

            for i in range(len(price_series)):
                start_idx = max(0, i - window + 1)
                end_idx = i + 1
                window_data = price_series.iloc[start_idx:end_idx]

                if len(window_data) < 2:
                    linear_reg_values.append(price_series.iloc[i])
                    continue

                # Simple linear regression calculation
                x_values = np.arange(len(window_data))
                y_values = window_data.values

                # Calculate regression line: y = mx + b
                n = len(x_values)
                sum_x = np.sum(x_values)
                sum_y = np.sum(y_values)
                sum_xy = np.sum(x_values * y_values)
                sum_x2 = np.sum(x_values * x_values)

                if n * sum_x2 - sum_x * sum_x != 0:
                    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                    intercept = (sum_y - slope * sum_x) / n

                    # Get predicted value for current point (last x value)
                    predicted_value = slope * (len(x_values) - 1) + intercept
                    linear_reg_values.append(predicted_value)
                else:
                    linear_reg_values.append(price_series.iloc[i])

            return pd.Series(linear_reg_values, index=price_series.index)

        except Exception as e:
            logger.warning(f"Linear regression calculation failed: {e}")
            return pd.Series(price_series.iloc[0], index=price_series.index)

    def _calculate_linear_regression_slope(self, price_series: pd.Series, window: int = 20) -> pd.Series:
        """
        Calculate linear regression slope for price series

        Args:
            price_series: Price series data
            window: Rolling window size

        Returns:
            Series with linear regression slope values
        """
        try:
            if len(price_series) < window:
                return pd.Series(0.0, index=price_series.index)

            slope_values = []

            for i in range(len(price_series)):
                start_idx = max(0, i - window + 1)
                end_idx = i + 1
                window_data = price_series.iloc[start_idx:end_idx]

                if len(window_data) < 2:
                    slope_values.append(0.0)
                    continue

                # Calculate slope of regression line
                x_values = np.arange(len(window_data))
                y_values = window_data.values

                n = len(x_values)
                sum_x = np.sum(x_values)
                sum_y = np.sum(y_values)
                sum_xy = np.sum(x_values * y_values)
                sum_x2 = np.sum(x_values * x_values)

                if n * sum_x2 - sum_x * sum_x != 0:
                    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                    slope_values.append(slope)
                else:
                    slope_values.append(0.0)

            return pd.Series(slope_values, index=price_series.index)

        except Exception as e:
            logger.warning(f"Linear regression slope calculation failed: {e}")
            return pd.Series(0.0, index=price_series.index)

    def _calculate_dominant_cycle(self, price_series: pd.Series) -> pd.Series:
        """
        Calculate dominant cycle using spectral analysis

        Args:
            price_series: Price series data

        Returns:
            Series with dominant cycle values
        """
        try:
            if len(price_series) < 50:
                return pd.Series(20.0, index=price_series.index)  # Default cycle period

            # Simple approach using rolling correlation with different periods
            cycle_values = []
            test_periods = [5, 8, 13, 21, 34, 55]  # Fibonacci-based periods

            for i in range(len(price_series)):
                if i < 50:
                    cycle_values.append(20.0)  # Default for insufficient data
                    continue

                # Look at recent data window
                window_size = min(100, i + 1)
                window_data = price_series.iloc[max(0, i - window_size + 1):i + 1]

                best_period = 20.0
                best_correlation = 0.0

                # Test different cycle periods
                for period in test_periods:
                    if len(window_data) < period * 3:  # Need at least 3 cycles
                        continue

                    try:
                        # Create synthetic cycle for this period
                        cycle_indices = np.arange(len(window_data))
                        synthetic_cycle = np.sin(2 * np.pi * cycle_indices / period)

                        # Calculate correlation with price changes
                        price_changes = window_data.pct_change().dropna()
                        if len(price_changes) >= len(synthetic_cycle):
                            correlation = np.corrcoef(
                                price_changes.iloc[-len(synthetic_cycle):].values,
                                synthetic_cycle
                            )[0, 1]

                            if not np.isnan(correlation) and abs(correlation) > abs(best_correlation):
                                best_correlation = correlation
                                best_period = period

                    except Exception:
                        continue

                cycle_values.append(best_period)

            return pd.Series(cycle_values, index=price_series.index)

        except Exception as e:
            logger.warning(f"Dominant cycle calculation failed: {e}")
            return pd.Series(20.0, index=price_series.index)

    def _calculate_cycle_phase(self, price_series: pd.Series) -> pd.Series:
        """
        Calculate cycle phase (position within the dominant cycle)

        Args:
            price_series: Price series data

        Returns:
            Series with cycle phase values (0-1, where 0 is trough, 0.5 is peak)
        """
        try:
            if len(price_series) < 20:
                return pd.Series(0.0, index=price_series.index)

            phase_values = []
            window = 20  # Analysis window

            for i in range(len(price_series)):
                if i < window:
                    phase_values.append(0.0)
                    continue

                # Get window data
                window_data = price_series.iloc[max(0, i - window + 1):i + 1]

                try:
                    # Simple phase calculation using price position relative to range
                    window_min = window_data.min()
                    window_max = window_data.max()
                    current_price = price_series.iloc[i]

                    if window_max - window_min > 0:
                        # Normalize price position (0 = min, 1 = max)
                        normalized_position = (current_price - window_min) / (window_max - window_min)

                        # Convert to phase (0 = trough, 0.5 = peak, 1.0 = trough again)
                        # This is a simplified phase calculation
                        if normalized_position <= 0.5:
                            phase = normalized_position  # Rising phase (0 to 0.5)
                        else:
                            phase = 1.0 - normalized_position  # Falling phase (0.5 to 0)

                        phase_values.append(phase)
                    else:
                        phase_values.append(0.0)

                except Exception:
                    phase_values.append(0.0)

            return pd.Series(phase_values, index=price_series.index)

        except Exception as e:
            logger.warning(f"Cycle phase calculation failed: {e}")
            return pd.Series(0.0, index=price_series.index)

    def _calculate_cycle_strength(self, price_series: pd.Series) -> pd.Series:
        """
        Calculate cycle strength (how pronounced the cyclical behavior is)

        Args:
            price_series: Price series data

        Returns:
            Series with cycle strength values (0-1, where 1 is strong cyclical behavior)
        """
        try:
            if len(price_series) < 30:
                return pd.Series(0.5, index=price_series.index)

            strength_values = []
            window = 30  # Analysis window

            for i in range(len(price_series)):
                if i < window:
                    strength_values.append(0.5)
                    continue

                # Get window data
                window_data = price_series.iloc[max(0, i - window + 1):i + 1]

                try:
                    # Calculate cycle strength using volatility and trend consistency
                    returns = window_data.pct_change().dropna()

                    if len(returns) < 5:
                        strength_values.append(0.5)
                        continue

                    # Measure 1: Volatility (higher volatility = stronger cycles)
                    volatility = returns.std()

                    # Measure 2: Autocorrelation (higher autocorr = stronger patterns)
                    if len(returns) > 10:
                        autocorr = returns.autocorr(lag=5)  # 5-period autocorrelation
                        if np.isnan(autocorr):
                            autocorr = 0.0
                    else:
                        autocorr = 0.0

                    # Measure 3: Range vs mean (normalized range indicates cycle strength)
                    price_range = window_data.max() - window_data.min()
                    mean_price = window_data.mean()
                    normalized_range = price_range / mean_price if mean_price > 0 else 0

                    # Combine measures (weighted average)
                    volatility_score = min(1.0, volatility * 50)  # Scale volatility
                    autocorr_score = abs(autocorr)  # Absolute autocorrelation
                    range_score = min(1.0, normalized_range * 5)  # Scale range

                    # Weighted combination
                    strength = (volatility_score * 0.4 + autocorr_score * 0.3 + range_score * 0.3)
                    strength = max(0.0, min(1.0, strength))  # Clamp to [0,1]

                    strength_values.append(strength)

                except Exception:
                    strength_values.append(0.5)

            return pd.Series(strength_values, index=price_series.index)

        except Exception as e:
            logger.warning(f"Cycle strength calculation failed: {e}")
            return pd.Series(0.5, index=price_series.index)

    def _is_double_top(self, price_series: pd.Series, peaks: np.ndarray) -> bool:
        """
        Detect double top pattern

        Args:
            price_series: Price series data
            peaks: Array of peak indices

        Returns:
            Boolean indicating if double top pattern exists
        """
        try:
            if len(peaks) < 2:
                return False

            # Look at the last few peaks
            recent_peaks = peaks[-3:] if len(peaks) >= 3 else peaks

            for i in range(len(recent_peaks) - 1):
                peak1_idx = recent_peaks[i]
                peak2_idx = recent_peaks[i + 1]

                peak1_price = price_series.iloc[peak1_idx]
                peak2_price = price_series.iloc[peak2_idx]

                # Check if peaks are roughly equal (within 3% tolerance)
                price_diff_pct = abs(peak1_price - peak2_price) / max(peak1_price, peak2_price)

                if price_diff_pct < 0.03:  # 3% tolerance
                    # Check if there's a valley between peaks
                    valley_start = min(peak1_idx, peak2_idx)
                    valley_end = max(peak1_idx, peak2_idx)

                    if valley_end - valley_start > 5:  # Minimum distance between peaks
                        valley_section = price_series.iloc[valley_start:valley_end + 1]
                        valley_low = valley_section.min()

                        # Valley should be at least 5% below peaks
                        valley_depth = (min(peak1_price, peak2_price) - valley_low) / min(peak1_price, peak2_price)

                        if valley_depth > 0.05:  # 5% minimum valley depth
                            return True

            return False

        except Exception as e:
            logger.warning(f"Double top detection failed: {e}")
            return False

    def _is_double_bottom(self, price_series: pd.Series, valleys: np.ndarray) -> bool:
        """
        Detect double bottom pattern

        Args:
            price_series: Price series data
            valleys: Array of valley indices

        Returns:
            Boolean indicating if double bottom pattern exists
        """
        try:
            if len(valleys) < 2:
                return False

            # Look at the last few valleys
            recent_valleys = valleys[-3:] if len(valleys) >= 3 else valleys

            for i in range(len(recent_valleys) - 1):
                valley1_idx = recent_valleys[i]
                valley2_idx = recent_valleys[i + 1]

                valley1_price = price_series.iloc[valley1_idx]
                valley2_price = price_series.iloc[valley2_idx]

                # Check if valleys are roughly equal (within 3% tolerance)
                price_diff_pct = abs(valley1_price - valley2_price) / max(valley1_price, valley2_price)

                if price_diff_pct < 0.03:  # 3% tolerance
                    # Check if there's a peak between valleys
                    peak_start = min(valley1_idx, valley2_idx)
                    peak_end = max(valley1_idx, valley2_idx)

                    if peak_end - peak_start > 5:  # Minimum distance between valleys
                        peak_section = price_series.iloc[peak_start:peak_end + 1]
                        peak_high = peak_section.max()

                        # Peak should be at least 5% above valleys
                        peak_height = (peak_high - max(valley1_price, valley2_price)) / max(valley1_price, valley2_price)

                        if peak_height > 0.05:  # 5% minimum peak height
                            return True

            return False

        except Exception as e:
            logger.warning(f"Double bottom detection failed: {e}")
            return False

    def _detect_triangle_pattern(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect triangle patterns in price data.

        Args:
            data: Dictionary containing price data and analysis results

        Returns:
            Dictionary with triangle pattern information
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {'detected': False, 'type': None, 'confidence': 0.0}

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 20:  # Need minimum data points
                return {'detected': False, 'type': None, 'confidence': 0.0}

            # Get recent price data (last 50 periods)
            recent_data = close_prices.tail(50)

            # Find peaks and valleys for triangle detection
            from scipy.signal import find_peaks

            # Find peaks (resistance levels)
            peaks, _ = find_peaks(recent_data.values, distance=5, prominence=recent_data.std() * 0.5)

            # Find valleys (support levels)
            valleys, _ = find_peaks(-recent_data.values, distance=5, prominence=recent_data.std() * 0.5)

            if len(peaks) < 2 or len(valleys) < 2:
                return {'detected': False, 'type': None, 'confidence': 0.0}

            # Get peak and valley prices
            peak_prices = recent_data.iloc[peaks].values
            valley_prices = recent_data.iloc[valleys].values
            peak_indices = peaks
            valley_indices = valleys

            # Sort by time
            peak_times = recent_data.iloc[peaks].index
            valley_times = recent_data.iloc[valleys].index

            triangle_type = None
            confidence = 0.0

            # Check for ascending triangle (horizontal resistance, rising support)
            if len(peaks) >= 2 and len(valleys) >= 2:
                # Check resistance trend (should be relatively flat)
                resistance_slope = np.polyfit(range(len(peak_prices)), peak_prices, 1)[0]
                resistance_flatness = abs(resistance_slope) / peak_prices.mean()

                # Check support trend (should be rising)
                support_slope = np.polyfit(range(len(valley_prices)), valley_prices, 1)[0]
                support_trend = support_slope / valley_prices.mean()

                if resistance_flatness < 0.02 and support_trend > 0.01:  # Flat resistance, rising support
                    triangle_type = 'ascending'
                    confidence = min(0.8, max(0.3, 1.0 - resistance_flatness + support_trend))

            # Check for descending triangle (declining resistance, horizontal support)
            if triangle_type is None and len(peaks) >= 2 and len(valleys) >= 2:
                # Check support trend (should be relatively flat)
                support_slope = np.polyfit(range(len(valley_prices)), valley_prices, 1)[0]
                support_flatness = abs(support_slope) / valley_prices.mean()

                # Check resistance trend (should be declining)
                resistance_slope = np.polyfit(range(len(peak_prices)), peak_prices, 1)[0]
                resistance_trend = resistance_slope / peak_prices.mean()

                if support_flatness < 0.02 and resistance_trend < -0.01:  # Flat support, declining resistance
                    triangle_type = 'descending'
                    confidence = min(0.8, max(0.3, 1.0 - support_flatness - resistance_trend))

            # Check for symmetrical triangle (converging trend lines)
            if triangle_type is None and len(peaks) >= 2 and len(valleys) >= 2:
                # Check if resistance is declining and support is rising
                resistance_slope = np.polyfit(range(len(peak_prices)), peak_prices, 1)[0]
                support_slope = np.polyfit(range(len(valley_prices)), valley_prices, 1)[0]

                resistance_trend = resistance_slope / peak_prices.mean()
                support_trend = support_slope / valley_prices.mean()

                # Converging: resistance declining, support rising
                if resistance_trend < -0.005 and support_trend > 0.005:
                    # Check convergence strength
                    convergence_strength = abs(resistance_trend) + support_trend
                    if convergence_strength > 0.02:
                        triangle_type = 'symmetrical'
                        confidence = min(0.7, max(0.3, convergence_strength * 10))

            # Additional validation: check price range compression
            if triangle_type is not None:
                # Price range should be compressing over time
                early_range = recent_data[:len(recent_data)//2].max() - recent_data[:len(recent_data)//2].min()
                late_range = recent_data[len(recent_data)//2:].max() - recent_data[len(recent_data)//2:].min()

                if late_range > early_range * 0.8:  # Range should compress by at least 20%
                    confidence *= 0.7  # Reduce confidence if not compressing

            return {
                'detected': triangle_type is not None,
                'type': triangle_type,
                'confidence': float(confidence),
                'peak_count': len(peaks),
                'valley_count': len(valleys),
                'price_compression': late_range / early_range if triangle_type is not None else 1.0
            }

        except Exception as e:
            logger.warning(f"Triangle pattern detection failed: {e}")
            return {'detected': False, 'type': None, 'confidence': 0.0}

    def _find_significant_swings(self, price_series: pd.Series, min_swing_pct: float = 0.02) -> Dict[str, List[int]]:
        """
        Find significant swing highs and lows in price data.

        Args:
            price_series: Price series data
            min_swing_pct: Minimum percentage move to qualify as a swing (default 2%)

        Returns:
            Dictionary with 'highs' and 'lows' lists containing indices of swing points
        """
        try:
            if len(price_series) < 10:
                return {'highs': [], 'lows': []}

            from scipy.signal import find_peaks

            # Calculate minimum prominence based on price volatility
            price_std = price_series.std()
            min_prominence = max(price_std * 0.5, price_series.mean() * min_swing_pct)

            # Find swing highs (peaks)
            swing_highs, _ = find_peaks(
                price_series.values,
                distance=5,  # Minimum 5 periods between swings
                prominence=min_prominence
            )

            # Find swing lows (valleys)
            swing_lows, _ = find_peaks(
                -price_series.values,
                distance=5,  # Minimum 5 periods between swings
                prominence=min_prominence
            )

            # Filter swings by minimum percentage move
            filtered_highs = []
            filtered_lows = []

            # Filter swing highs
            for high_idx in swing_highs:
                if high_idx < 5 or high_idx >= len(price_series) - 5:
                    continue

                # Check if it's a significant swing from nearby lows
                left_section = price_series.iloc[max(0, high_idx-10):high_idx]
                right_section = price_series.iloc[high_idx+1:min(len(price_series), high_idx+11)]

                if len(left_section) > 0 and len(right_section) > 0:
                    nearby_low = min(left_section.min(), right_section.min())
                    swing_move = (price_series.iloc[high_idx] - nearby_low) / nearby_low

                    if swing_move >= min_swing_pct:
                        filtered_highs.append(high_idx)

            # Filter swing lows
            for low_idx in swing_lows:
                if low_idx < 5 or low_idx >= len(price_series) - 5:
                    continue

                # Check if it's a significant swing from nearby highs
                left_section = price_series.iloc[max(0, low_idx-10):low_idx]
                right_section = price_series.iloc[low_idx+1:min(len(price_series), low_idx+11)]

                if len(left_section) > 0 and len(right_section) > 0:
                    nearby_high = max(left_section.max(), right_section.max())
                    swing_move = (nearby_high - price_series.iloc[low_idx]) / price_series.iloc[low_idx]

                    if swing_move >= min_swing_pct:
                        filtered_lows.append(low_idx)

            # Sort by time (index)
            filtered_highs.sort()
            filtered_lows.sort()

            # Limit to most recent significant swings
            max_swings = 20
            if len(filtered_highs) > max_swings:
                filtered_highs = filtered_highs[-max_swings:]
            if len(filtered_lows) > max_swings:
                filtered_lows = filtered_lows[-max_swings:]

            return {
                'highs': filtered_highs,
                'lows': filtered_lows
            }

        except Exception as e:
            logger.warning(f"Significant swings detection failed: {e}")
            return {'highs': [], 'lows': []}

    def _test_volatility_clustering(self, returns: pd.Series) -> Dict[str, Any]:
        """
        Test for volatility clustering in returns data.

        Args:
            returns: Price returns series

        Returns:
            Dictionary with volatility clustering test results
        """
        try:
            if len(returns) < 20:
                return {'detected': False, 'arch_statistic': 0.0, 'p_value': 1.0, 'clustering_strength': 0.0}

            # Calculate absolute returns for volatility proxy
            abs_returns = abs(returns).dropna()

            if len(abs_returns) < 10:
                return {'detected': False, 'arch_statistic': 0.0, 'p_value': 1.0, 'clustering_strength': 0.0}

            # Test for serial correlation in squared returns (ARCH test)
            squared_returns = returns.dropna() ** 2

            # Simple ARCH(1) test - correlation between consecutive squared returns
            if len(squared_returns) > 1:
                # Calculate autocorrelation of squared returns at lag 1
                lag1_corr = squared_returns.autocorr(lag=1)
                if pd.isna(lag1_corr):
                    lag1_corr = 0.0

                # Calculate Ljung-Box type statistic for autocorrelation
                n = len(squared_returns)
                lb_statistic = n * (n + 2) * (lag1_corr ** 2) / (n - 1)

                # Approximate p-value (chi-square with 1 df)
                from scipy.stats import chi2
                p_value = 1 - chi2.cdf(lb_statistic, df=1)

                # Calculate clustering strength based on rolling volatility
                rolling_vol = abs_returns.rolling(window=5, min_periods=3).std()
                if len(rolling_vol.dropna()) > 5:
                    vol_variance = rolling_vol.var()
                    vol_mean = rolling_vol.mean()
                    clustering_strength = vol_variance / (vol_mean ** 2) if vol_mean > 0 else 0.0
                else:
                    clustering_strength = 0.0

                # Additional volatility clustering indicators
                # High volatility periods tend to cluster
                high_vol_threshold = abs_returns.quantile(0.75)
                high_vol_periods = (abs_returns > high_vol_threshold).astype(int)

                # Calculate runs of high volatility
                runs = []
                current_run = 0
                for val in high_vol_periods:
                    if val == 1:
                        current_run += 1
                    else:
                        if current_run > 0:
                            runs.append(current_run)
                        current_run = 0
                if current_run > 0:
                    runs.append(current_run)

                # Average run length (clustering indicator)
                avg_run_length = np.mean(runs) if runs else 0.0

                # Combine indicators for final assessment
                volatility_detected = (
                    p_value < 0.1 or  # Significant autocorrelation
                    clustering_strength > 1.5 or  # High volatility variance
                    avg_run_length > 2.0  # Long volatility runs
                )

                return {
                    'detected': bool(volatility_detected),
                    'arch_statistic': float(lb_statistic),
                    'p_value': float(p_value),
                    'clustering_strength': float(clustering_strength),
                    'autocorr_lag1': float(lag1_corr),
                    'avg_run_length': float(avg_run_length),
                    'high_vol_ratio': float(high_vol_periods.mean())
                }

            else:
                return {'detected': False, 'arch_statistic': 0.0, 'p_value': 1.0, 'clustering_strength': 0.0}

        except Exception as e:
            logger.warning(f"Volatility clustering test failed: {e}")
            return {'detected': False, 'arch_statistic': 0.0, 'p_value': 1.0, 'clustering_strength': 0.0}

    def _detect_trend_regime(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect current trend regime in price data.

        Args:
            data: Dictionary containing price data and analysis results

        Returns:
            Dictionary with trend regime information
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {'regime': 'uncertain', 'strength': 0.0, 'duration': 0, 'confidence': 0.0}

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 20:
                return {'regime': 'uncertain', 'strength': 0.0, 'duration': 0, 'confidence': 0.0}

            # Calculate multiple moving averages for trend detection
            ma_short = close_prices.rolling(window=10, min_periods=5).mean()
            ma_medium = close_prices.rolling(window=20, min_periods=10).mean()
            ma_long = close_prices.rolling(window=50, min_periods=25).mean()

            # Current values (last available)
            current_price = close_prices.iloc[-1]
            current_ma_short = ma_short.iloc[-1] if not pd.isna(ma_short.iloc[-1]) else current_price
            current_ma_medium = ma_medium.iloc[-1] if not pd.isna(ma_medium.iloc[-1]) else current_price
            current_ma_long = ma_long.iloc[-1] if not pd.isna(ma_long.iloc[-1]) else current_price

            # Trend strength indicators
            trend_indicators = []

            # 1. Price vs Moving Averages
            if current_price > current_ma_short > current_ma_medium > current_ma_long:
                trend_indicators.append(('bullish', 1.0))
            elif current_price < current_ma_short < current_ma_medium < current_ma_long:
                trend_indicators.append(('bearish', 1.0))
            elif current_price > current_ma_short > current_ma_medium:
                trend_indicators.append(('bullish', 0.7))
            elif current_price < current_ma_short < current_ma_medium:
                trend_indicators.append(('bearish', 0.7))
            elif current_price > current_ma_short:
                trend_indicators.append(('bullish', 0.4))
            elif current_price < current_ma_short:
                trend_indicators.append(('bearish', 0.4))
            else:
                trend_indicators.append(('sideways', 0.5))

            # 2. Moving Average Slopes
            if len(ma_short) >= 5:
                ma_short_slope = (ma_short.iloc[-1] - ma_short.iloc[-5]) / ma_short.iloc[-5]
                ma_medium_slope = (ma_medium.iloc[-1] - ma_medium.iloc[-10]) / ma_medium.iloc[-10] if len(ma_medium) >= 10 else 0
                ma_long_slope = (ma_long.iloc[-1] - ma_long.iloc[-20]) / ma_long.iloc[-20] if len(ma_long) >= 20 else 0

                # Slope-based trend detection
                if ma_short_slope > 0.02 and ma_medium_slope > 0.01:
                    trend_indicators.append(('bullish', 0.8))
                elif ma_short_slope < -0.02 and ma_medium_slope < -0.01:
                    trend_indicators.append(('bearish', 0.8))
                elif abs(ma_short_slope) < 0.01:
                    trend_indicators.append(('sideways', 0.6))

            # 3. Price momentum (rate of change)
            if len(close_prices) >= 10:
                roc_short = (close_prices.iloc[-1] - close_prices.iloc[-5]) / close_prices.iloc[-5]
                roc_medium = (close_prices.iloc[-1] - close_prices.iloc[-10]) / close_prices.iloc[-10]

                if roc_short > 0.03 and roc_medium > 0.02:
                    trend_indicators.append(('bullish', 0.7))
                elif roc_short < -0.03 and roc_medium < -0.02:
                    trend_indicators.append(('bearish', 0.7))
                elif abs(roc_short) < 0.01:
                    trend_indicators.append(('sideways', 0.4))

            # 4. Higher highs / Lower lows analysis
            recent_highs = close_prices.tail(20).rolling(window=5).max()
            recent_lows = close_prices.tail(20).rolling(window=5).min()

            if len(recent_highs.dropna()) >= 3:
                highs_trend = recent_highs.dropna().diff().mean()
                lows_trend = recent_lows.dropna().diff().mean()

                if highs_trend > 0 and lows_trend > 0:
                    trend_indicators.append(('bullish', 0.6))
                elif highs_trend < 0 and lows_trend < 0:
                    trend_indicators.append(('bearish', 0.6))
                else:
                    trend_indicators.append(('sideways', 0.3))

            # Aggregate trend signals
            bullish_score = sum([strength for regime, strength in trend_indicators if regime == 'bullish'])
            bearish_score = sum([strength for regime, strength in trend_indicators if regime == 'bearish'])
            sideways_score = sum([strength for regime, strength in trend_indicators if regime == 'sideways'])

            # Determine dominant regime
            max_score = max(bullish_score, bearish_score, sideways_score)
            total_score = bullish_score + bearish_score + sideways_score

            if max_score == bullish_score and bullish_score > bearish_score * 1.2:
                regime = 'bullish'
                strength = bullish_score / max(1, total_score)
            elif max_score == bearish_score and bearish_score > bullish_score * 1.2:
                regime = 'bearish'
                strength = bearish_score / max(1, total_score)
            else:
                regime = 'sideways'
                strength = sideways_score / max(1, total_score)

            # Calculate trend duration (consecutive periods in same regime)
            duration = 1
            if regime != 'sideways':
                # Look back to see how long this trend has been in place
                lookback_prices = close_prices.tail(50)
                lookback_ma = lookback_prices.rolling(window=10).mean()

                if regime == 'bullish':
                    for i in range(len(lookback_prices) - 2, -1, -1):
                        if (lookback_prices.iloc[i] > lookback_ma.iloc[i] and
                            lookback_prices.iloc[i] > lookback_prices.iloc[i-1] if i > 0 else True):
                            duration += 1
                        else:
                            break
                elif regime == 'bearish':
                    for i in range(len(lookback_prices) - 2, -1, -1):
                        if (lookback_prices.iloc[i] < lookback_ma.iloc[i] and
                            lookback_prices.iloc[i] < lookback_prices.iloc[i-1] if i > 0 else True):
                            duration += 1
                        else:
                            break

            # Calculate confidence based on signal agreement
            confidence = min(0.95, strength * len(trend_indicators) / 4.0)

            return {
                'regime': regime,
                'strength': float(strength),
                'duration': int(duration),
                'confidence': float(confidence),
                'bullish_score': float(bullish_score),
                'bearish_score': float(bearish_score),
                'sideways_score': float(sideways_score),
                'indicators_count': len(trend_indicators)
            }

        except Exception as e:
            logger.warning(f"Trend regime detection failed: {e}")
            return {'regime': 'uncertain', 'strength': 0.0, 'duration': 0, 'confidence': 0.0}

    def _detect_volatility_regime(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect current volatility regime in price data.

        Args:
            data: Dictionary containing price data and analysis results

        Returns:
            Dictionary with volatility regime information
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 20:
                return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

            # Calculate returns for volatility analysis
            returns = close_prices.pct_change().dropna()

            if len(returns) < 10:
                return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

            # Calculate multiple volatility measures
            # 1. Rolling standard deviation of returns
            vol_window = min(20, len(returns) // 2)
            rolling_vol = returns.rolling(window=vol_window, min_periods=vol_window//2).std()

            # 2. Current volatility vs historical
            current_vol = rolling_vol.iloc[-1] if not pd.isna(rolling_vol.iloc[-1]) else returns.std()
            historical_vol = rolling_vol.dropna()

            if len(historical_vol) < 5:
                historical_vol = pd.Series([returns.std()] * 5)

            # Calculate percentile of current volatility
            vol_percentile = (historical_vol < current_vol).mean() * 100

            # 3. GARCH-like volatility clustering detection
            abs_returns = abs(returns)
            recent_abs_returns = abs_returns.tail(10)
            long_term_abs_returns = abs_returns

            recent_vol_avg = recent_abs_returns.mean()
            long_term_vol_avg = long_term_abs_returns.mean()

            vol_ratio = recent_vol_avg / long_term_vol_avg if long_term_vol_avg > 0 else 1.0

            # 4. Volatility regime classification
            # Calculate thresholds based on historical distribution
            vol_25th = historical_vol.quantile(0.25)
            vol_75th = historical_vol.quantile(0.75)
            vol_90th = historical_vol.quantile(0.90)
            vol_10th = historical_vol.quantile(0.10)

            # Regime determination
            if current_vol > vol_90th:
                regime = 'high'
                regime_strength = min(1.0, (current_vol - vol_90th) / (vol_90th - vol_75th + 1e-8))
            elif current_vol < vol_10th:
                regime = 'low'
                regime_strength = min(1.0, (vol_10th - current_vol) / (vol_25th - vol_10th + 1e-8))
            elif current_vol > vol_75th:
                regime = 'elevated'
                regime_strength = (current_vol - vol_75th) / (vol_90th - vol_75th + 1e-8)
            elif current_vol < vol_25th:
                regime = 'subdued'
                regime_strength = (vol_25th - current_vol) / (vol_25th - vol_10th + 1e-8)
            else:
                regime = 'normal'
                regime_strength = 0.5

            # 5. Additional volatility indicators
            # Volatility of volatility (vol clustering strength)
            if len(rolling_vol.dropna()) > 5:
                vol_of_vol = rolling_vol.dropna().std()
                vol_of_vol_normalized = vol_of_vol / rolling_vol.dropna().mean() if rolling_vol.dropna().mean() > 0 else 0
            else:
                vol_of_vol_normalized = 0

            # Recent volatility trend
            if len(rolling_vol.dropna()) >= 5:
                recent_vol_trend = (rolling_vol.iloc[-1] - rolling_vol.iloc[-5]) / rolling_vol.iloc[-5]
            else:
                recent_vol_trend = 0

            # 6. Market stress indicators
            # Large price moves (> 2 standard deviations)
            stress_threshold = returns.std() * 2
            recent_stress_events = (abs(returns.tail(10)) > stress_threshold).sum()
            stress_ratio = recent_stress_events / 10

            # 7. Volatility persistence
            # How long has current regime been in place
            persistence = 1
            if len(rolling_vol.dropna()) > 5:
                for i in range(len(rolling_vol) - 2, max(0, len(rolling_vol) - 21), -1):
                    if not pd.isna(rolling_vol.iloc[i]):
                        past_vol = rolling_vol.iloc[i]
                        past_percentile = (historical_vol < past_vol).mean() * 100

                        # Check if same regime
                        if regime == 'high' and past_percentile > 90:
                            persistence += 1
                        elif regime == 'low' and past_percentile < 10:
                            persistence += 1
                        elif regime == 'elevated' and 75 < past_percentile <= 90:
                            persistence += 1
                        elif regime == 'subdued' and 10 <= past_percentile < 25:
                            persistence += 1
                        elif regime == 'normal' and 25 <= past_percentile <= 75:
                            persistence += 1
                        else:
                            break

            # Calculate confidence based on multiple factors
            confidence_factors = [
                min(1.0, abs(vol_percentile - 50) / 40),  # Distance from median
                min(1.0, abs(vol_ratio - 1.0) * 2),  # Deviation from normal
                min(1.0, vol_of_vol_normalized),  # Volatility clustering
                min(1.0, stress_ratio * 2),  # Market stress
                min(1.0, persistence / 10)  # Regime persistence
            ]

            confidence = np.mean(confidence_factors)

            return {
                'regime': regime,
                'level': float(current_vol),
                'percentile': float(vol_percentile),
                'confidence': float(confidence),
                'strength': float(regime_strength),
                'volatility_ratio': float(vol_ratio),
                'vol_of_vol': float(vol_of_vol_normalized),
                'trend': float(recent_vol_trend),
                'stress_ratio': float(stress_ratio),
                'persistence': int(persistence),
                'thresholds': {
                    'low': float(vol_10th),
                    'normal_low': float(vol_25th),
                    'normal_high': float(vol_75th),
                    'high': float(vol_90th)
                }
            }

        except Exception as e:
            logger.warning(f"Volatility regime detection failed: {e}")
            return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

    def _detect_volume_regime(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect current volume regime in trading data.

        Args:
            data: Dictionary containing price and volume data

        Returns:
            Dictionary with volume regime information
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

            # Check if volume data is available
            if 'volume' not in df.columns:
                # Generate synthetic volume data if not available
                close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]
                returns = close_prices.pct_change().abs()
                synthetic_volume = returns * 1000000  # Scale factor for realistic volume
                volume = synthetic_volume.fillna(synthetic_volume.mean())
            else:
                volume = df['volume']

            if len(volume) < 20:
                return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

            # Remove zero and negative volumes
            volume = volume[volume > 0]
            if len(volume) < 10:
                return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

            # Calculate volume statistics
            # 1. Rolling average volume
            vol_window = min(20, len(volume) // 2)
            rolling_avg_vol = volume.rolling(window=vol_window, min_periods=vol_window//2).mean()

            # 2. Current volume vs historical
            current_vol = volume.iloc[-1]
            recent_avg_vol = rolling_avg_vol.iloc[-5:].mean() if len(rolling_avg_vol) >= 5 else current_vol
            historical_vol = rolling_avg_vol.dropna()

            if len(historical_vol) < 5:
                historical_vol = pd.Series([volume.mean()] * 5)

            # Calculate percentile of current volume
            vol_percentile = (historical_vol < recent_avg_vol).mean() * 100

            # 3. Volume trend analysis
            # Short-term vs long-term average
            if len(volume) >= 10:
                short_term_avg = volume.tail(5).mean()
                long_term_avg = volume.tail(20).mean() if len(volume) >= 20 else volume.mean()
                volume_ratio = short_term_avg / long_term_avg if long_term_avg > 0 else 1.0
            else:
                volume_ratio = 1.0

            # 4. Volume regime classification
            # Calculate thresholds based on historical distribution
            vol_25th = historical_vol.quantile(0.25)
            vol_75th = historical_vol.quantile(0.75)
            vol_90th = historical_vol.quantile(0.90)
            vol_10th = historical_vol.quantile(0.10)

            # Regime determination
            if recent_avg_vol > vol_90th:
                regime = 'high'
                regime_strength = min(1.0, (recent_avg_vol - vol_90th) / (vol_90th - vol_75th + 1e-8))
            elif recent_avg_vol < vol_10th:
                regime = 'low'
                regime_strength = min(1.0, (vol_10th - recent_avg_vol) / (vol_25th - vol_10th + 1e-8))
            elif recent_avg_vol > vol_75th:
                regime = 'elevated'
                regime_strength = (recent_avg_vol - vol_75th) / (vol_90th - vol_75th + 1e-8)
            elif recent_avg_vol < vol_25th:
                regime = 'subdued'
                regime_strength = (vol_25th - recent_avg_vol) / (vol_25th - vol_10th + 1e-8)
            else:
                regime = 'normal'
                regime_strength = 0.5

            # 5. Volume-price relationship analysis
            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]
            if len(close_prices) == len(volume):
                price_changes = close_prices.pct_change().dropna()
                volume_aligned = volume.iloc[1:] if len(volume) > len(price_changes) else volume

                if len(price_changes) == len(volume_aligned):
                    # Calculate correlation between volume and absolute price changes
                    abs_price_changes = abs(price_changes)
                    vol_price_corr = abs_price_changes.corr(volume_aligned)
                    if pd.isna(vol_price_corr):
                        vol_price_corr = 0.0
                else:
                    vol_price_corr = 0.0
            else:
                vol_price_corr = 0.0

            # 6. Volume clustering analysis
            # Check if high volume periods cluster together
            high_vol_threshold = volume.quantile(0.75)
            high_vol_periods = (volume > high_vol_threshold).astype(int)

            # Calculate runs of high volume
            volume_runs = []
            current_run = 0
            for val in high_vol_periods:
                if val == 1:
                    current_run += 1
                else:
                    if current_run > 0:
                        volume_runs.append(current_run)
                    current_run = 0
            if current_run > 0:
                volume_runs.append(current_run)

            avg_volume_run = np.mean(volume_runs) if volume_runs else 0.0

            # 7. Volume volatility
            volume_returns = volume.pct_change().dropna()
            volume_volatility = volume_returns.std() if len(volume_returns) > 1 else 0.0

            # 8. Recent volume activity
            recent_volume_activity = volume.tail(5).std() / volume.tail(5).mean() if volume.tail(5).mean() > 0 else 0.0

            # 9. Volume persistence
            persistence = 1
            if len(rolling_avg_vol.dropna()) > 5:
                for i in range(len(rolling_avg_vol) - 2, max(0, len(rolling_avg_vol) - 21), -1):
                    if not pd.isna(rolling_avg_vol.iloc[i]):
                        past_vol = rolling_avg_vol.iloc[i]
                        past_percentile = (historical_vol < past_vol).mean() * 100

                        # Check if same regime
                        if regime == 'high' and past_percentile > 90:
                            persistence += 1
                        elif regime == 'low' and past_percentile < 10:
                            persistence += 1
                        elif regime == 'elevated' and 75 < past_percentile <= 90:
                            persistence += 1
                        elif regime == 'subdued' and 10 <= past_percentile < 25:
                            persistence += 1
                        elif regime == 'normal' and 25 <= past_percentile <= 75:
                            persistence += 1
                        else:
                            break

            # Calculate confidence based on multiple factors
            confidence_factors = [
                min(1.0, abs(vol_percentile - 50) / 40),  # Distance from median
                min(1.0, abs(volume_ratio - 1.0) * 2),  # Deviation from normal
                min(1.0, abs(vol_price_corr)),  # Volume-price relationship
                min(1.0, avg_volume_run / 5),  # Volume clustering
                min(1.0, persistence / 10)  # Regime persistence
            ]

            confidence = np.mean([f for f in confidence_factors if not pd.isna(f)])

            return {
                'regime': regime,
                'level': float(current_vol),
                'percentile': float(vol_percentile),
                'confidence': float(confidence),
                'strength': float(regime_strength),
                'volume_ratio': float(volume_ratio),
                'vol_price_correlation': float(vol_price_corr),
                'volume_volatility': float(volume_volatility),
                'activity_level': float(recent_volume_activity),
                'avg_run_length': float(avg_volume_run),
                'persistence': int(persistence),
                'thresholds': {
                    'low': float(vol_10th),
                    'normal_low': float(vol_25th),
                    'normal_high': float(vol_75th),
                    'high': float(vol_90th)
                }
            }

        except Exception as e:
            logger.warning(f"Volume regime detection failed: {e}")
            return {'regime': 'normal', 'level': 0.5, 'percentile': 50, 'confidence': 0.0}

    def _synthesize_regime(self, regime_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize overall market regime from individual regime components.

        Args:
            regime_data: Dictionary containing individual regime analyses

        Returns:
            Dictionary with synthesized overall market regime
        """
        try:
            # Extract individual regimes
            trend_regime = regime_data.get('trend_regime', {})
            volatility_regime = regime_data.get('volatility_regime', {})
            volume_regime = regime_data.get('volume_regime', {})

            # Initialize synthesis components
            regime_scores = {
                'bullish': 0.0,
                'bearish': 0.0,
                'neutral': 0.0,
                'uncertain': 0.0
            }

            confidence_factors = []
            strength_factors = []

            # 1. Trend regime analysis
            trend_type = trend_regime.get('regime', 'uncertain')
            trend_confidence = trend_regime.get('confidence', 0.0)
            trend_strength = trend_regime.get('strength', 0.0)

            if trend_type == 'bullish':
                regime_scores['bullish'] += 0.4 * trend_confidence
            elif trend_type == 'bearish':
                regime_scores['bearish'] += 0.4 * trend_confidence
            elif trend_type == 'sideways':
                regime_scores['neutral'] += 0.4 * trend_confidence
            else:
                regime_scores['uncertain'] += 0.4

            confidence_factors.append(trend_confidence)
            strength_factors.append(trend_strength)

            # 2. Volatility regime analysis
            vol_type = volatility_regime.get('regime', 'normal')
            vol_confidence = volatility_regime.get('confidence', 0.0)
            vol_strength = volatility_regime.get('strength', 0.0)

            # High volatility can indicate uncertainty or strong trends
            if vol_type in ['high', 'elevated']:
                # High volatility can amplify existing trends or create uncertainty
                if trend_type in ['bullish', 'bearish']:
                    # Amplify trend signal
                    if trend_type == 'bullish':
                        regime_scores['bullish'] += 0.2 * vol_confidence
                    else:
                        regime_scores['bearish'] += 0.2 * vol_confidence
                else:
                    # High volatility without clear trend = uncertainty
                    regime_scores['uncertain'] += 0.2 * vol_confidence
            elif vol_type == 'low':
                # Low volatility suggests stability
                regime_scores['neutral'] += 0.2 * vol_confidence
            else:
                # Normal volatility is neutral
                regime_scores['neutral'] += 0.1 * vol_confidence

            confidence_factors.append(vol_confidence)
            strength_factors.append(vol_strength)

            # 3. Volume regime analysis
            volume_type = volume_regime.get('regime', 'normal')
            volume_confidence = volume_regime.get('confidence', 0.0)
            volume_strength = volume_regime.get('strength', 0.0)

            # Volume confirms or questions trend strength
            if volume_type in ['high', 'elevated']:
                # High volume can confirm trends
                if trend_type == 'bullish':
                    regime_scores['bullish'] += 0.2 * volume_confidence
                elif trend_type == 'bearish':
                    regime_scores['bearish'] += 0.2 * volume_confidence
                else:
                    # High volume without trend could signal incoming change
                    regime_scores['uncertain'] += 0.1 * volume_confidence
            elif volume_type == 'low':
                # Low volume suggests weak conviction
                regime_scores['uncertain'] += 0.1 * volume_confidence
                # Reduce confidence in existing trend signals
                if trend_type in ['bullish', 'bearish']:
                    regime_scores[trend_type] *= 0.8

            confidence_factors.append(volume_confidence)
            strength_factors.append(volume_strength)

            # 4. Cross-regime validation
            # Check for regime alignment
            alignment_score = 0.0

            # Trend-Volume alignment
            if trend_type == 'bullish' and volume_type in ['high', 'elevated']:
                alignment_score += 0.3  # Strong bullish confirmation
            elif trend_type == 'bearish' and volume_type in ['high', 'elevated']:
                alignment_score += 0.3  # Strong bearish confirmation
            elif trend_type in ['bullish', 'bearish'] and volume_type == 'low':
                alignment_score -= 0.2  # Trend without volume support

            # Trend-Volatility alignment
            if trend_type in ['bullish', 'bearish'] and vol_type in ['normal', 'subdued']:
                alignment_score += 0.2  # Healthy trend with normal volatility
            elif trend_type == 'sideways' and vol_type == 'low':
                alignment_score += 0.2  # Stable sideways market

            # Apply alignment adjustment
            for regime in regime_scores:
                if regime_scores[regime] > 0:
                    regime_scores[regime] *= (1.0 + alignment_score)

            # 5. Determine dominant regime
            max_score = max(regime_scores.values())
            total_score = sum(regime_scores.values())

            if total_score == 0:
                overall_regime = 'uncertain'
                regime_confidence = 0.0
                regime_strength = 0.0
            else:
                # Find dominant regime
                dominant_regime = max(regime_scores.keys(), key=lambda k: regime_scores[k])

                # Require clear dominance (at least 20% higher than others)
                other_scores = [score for regime, score in regime_scores.items() if regime != dominant_regime]
                max_other = max(other_scores) if other_scores else 0

                if regime_scores[dominant_regime] > max_other * 1.2 and regime_scores[dominant_regime] > 0.3:
                    overall_regime = dominant_regime
                    regime_confidence = regime_scores[dominant_regime] / max(total_score, 0.1)
                else:
                    overall_regime = 'uncertain'
                    regime_confidence = 0.5

                # Calculate overall strength
                regime_strength = np.mean([f for f in strength_factors if not pd.isna(f) and f > 0])
                if pd.isna(regime_strength):
                    regime_strength = 0.0

            # 6. Risk assessment
            # High volatility + uncertainty = high risk
            risk_level = 'medium'
            if vol_type in ['high', 'elevated'] and overall_regime == 'uncertain':
                risk_level = 'high'
            elif vol_type == 'low' and overall_regime != 'uncertain':
                risk_level = 'low'
            elif vol_type in ['high', 'elevated'] and overall_regime in ['bullish', 'bearish']:
                risk_level = 'medium-high'

            # 7. Market phase identification
            if overall_regime == 'bullish' and vol_type in ['normal', 'subdued']:
                market_phase = 'uptrend'
            elif overall_regime == 'bearish' and vol_type in ['normal', 'subdued']:
                market_phase = 'downtrend'
            elif overall_regime == 'neutral' and vol_type == 'low':
                market_phase = 'consolidation'
            elif vol_type in ['high', 'elevated']:
                market_phase = 'volatile'
            else:
                market_phase = 'transitional'

            # Final confidence calculation
            base_confidence = np.mean([f for f in confidence_factors if not pd.isna(f)])
            if pd.isna(base_confidence):
                base_confidence = 0.0

            final_confidence = min(0.95, base_confidence * (1.0 + alignment_score))

            return {
                'regime': overall_regime,
                'confidence': float(final_confidence),
                'strength': float(regime_strength),
                'risk_level': risk_level,
                'market_phase': market_phase,
                'alignment_score': float(alignment_score),
                'regime_scores': {k: float(v) for k, v in regime_scores.items()},
                'component_summary': {
                    'trend': trend_type,
                    'volatility': vol_type,
                    'volume': volume_type
                }
            }

        except Exception as e:
            logger.warning(f"Regime synthesis failed: {e}")
            return {
                'regime': 'uncertain',
                'confidence': 0.0,
                'strength': 0.0,
                'risk_level': 'high',
                'market_phase': 'unknown'
            }

    def _calculate_regime_strength(self, data: Dict[str, Any], regime_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate the strength and persistence of the identified market regime.

        Args:
            data: Dictionary containing price and market data
            regime_data: Dictionary containing regime analysis results

        Returns:
            Dictionary with regime strength metrics
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {'strength': 0.0, 'persistence': 0, 'consistency': 0.0, 'momentum': 0.0}

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 10:
                return {'strength': 0.0, 'persistence': 0, 'consistency': 0.0, 'momentum': 0.0}

            # Extract overall regime information
            overall_regime = regime_data.get('overall_regime', {})
            current_regime = overall_regime.get('regime', 'uncertain')
            regime_confidence = overall_regime.get('confidence', 0.0)

            # 1. Calculate regime persistence (how long has it been in place)
            persistence = self._calculate_regime_persistence(close_prices, current_regime)

            # 2. Calculate regime consistency (how stable the signals are)
            consistency = self._calculate_regime_consistency(data, regime_data)

            # 3. Calculate regime momentum (how strong the current movement is)
            momentum = self._calculate_regime_momentum(close_prices, current_regime)

            # 4. Calculate regime strength based on multiple factors
            strength_factors = []

            # Base strength from regime confidence
            strength_factors.append(regime_confidence)

            # Persistence factor (longer persistence = higher strength up to a point)
            persistence_factor = min(1.0, persistence / 20.0)  # Normalize to 20 periods max
            strength_factors.append(persistence_factor)

            # Consistency factor
            strength_factors.append(consistency)

            # Momentum factor
            strength_factors.append(momentum)

            # Volume confirmation (if available)
            volume_regime = regime_data.get('volume_regime', {})
            if volume_regime:
                volume_confirmation = self._get_volume_confirmation(current_regime, volume_regime)
                strength_factors.append(volume_confirmation)

            # Volatility confirmation
            volatility_regime = regime_data.get('volatility_regime', {})
            if volatility_regime:
                volatility_confirmation = self._get_volatility_confirmation(current_regime, volatility_regime)
                strength_factors.append(volatility_confirmation)

            # Calculate weighted average strength
            weights = [0.25, 0.20, 0.20, 0.15, 0.10, 0.10]  # Adjust based on available factors
            weights = weights[:len(strength_factors)]
            if sum(weights) > 0:
                overall_strength = sum(f * w for f, w in zip(strength_factors, weights)) / sum(weights)
            else:
                overall_strength = 0.0

            # 5. Calculate regime quality score
            quality_score = self._calculate_regime_quality(current_regime, regime_confidence, persistence, consistency)

            # 6. Calculate trend exhaustion risk
            exhaustion_risk = self._calculate_exhaustion_risk(close_prices, current_regime, persistence)

            return {
                'strength': float(overall_strength),
                'persistence': int(persistence),
                'consistency': float(consistency),
                'momentum': float(momentum),
                'quality_score': float(quality_score),
                'exhaustion_risk': float(exhaustion_risk),
                'strength_factors': {
                    'confidence': float(regime_confidence),
                    'persistence_factor': float(persistence_factor),
                    'consistency': float(consistency),
                    'momentum': float(momentum)
                }
            }

        except Exception as e:
            logger.warning(f"Regime strength calculation failed: {e}")
            return {'strength': 0.0, 'persistence': 0, 'consistency': 0.0, 'momentum': 0.0}

    def _calculate_regime_persistence(self, price_series: pd.Series, regime: str) -> int:
        """Calculate how long the current regime has been in place."""
        try:
            if len(price_series) < 5:
                return 1

            # Use moving averages to determine regime persistence
            ma_short = price_series.rolling(window=5, min_periods=3).mean()
            ma_long = price_series.rolling(window=20, min_periods=10).mean()

            persistence = 1
            for i in range(len(price_series) - 2, max(0, len(price_series) - 51), -1):
                if i < len(ma_short) and i < len(ma_long):
                    if regime == 'bullish' and ma_short.iloc[i] > ma_long.iloc[i]:
                        persistence += 1
                    elif regime == 'bearish' and ma_short.iloc[i] < ma_long.iloc[i]:
                        persistence += 1
                    elif regime == 'neutral' and abs(ma_short.iloc[i] - ma_long.iloc[i]) / ma_long.iloc[i] < 0.02:
                        persistence += 1
                    else:
                        break

            return min(persistence, 50)  # Cap at 50 periods

        except Exception:
            return 1

    def _calculate_regime_consistency(self, data: Dict[str, Any], regime_data: Dict[str, Any]) -> float:
        """Calculate how consistent the regime signals are."""
        try:
            # Check alignment between different regime components
            trend_regime = regime_data.get('trend_regime', {})
            volatility_regime = regime_data.get('volatility_regime', {})
            volume_regime = regime_data.get('volume_regime', {})

            consistency_scores = []

            # Trend consistency
            trend_confidence = trend_regime.get('confidence', 0.0)
            consistency_scores.append(trend_confidence)

            # Volatility consistency
            vol_confidence = volatility_regime.get('confidence', 0.0)
            consistency_scores.append(vol_confidence)

            # Volume consistency
            volume_confidence = volume_regime.get('confidence', 0.0)
            consistency_scores.append(volume_confidence)

            return np.mean([s for s in consistency_scores if s > 0]) if consistency_scores else 0.0

        except Exception:
            return 0.0

    def _calculate_regime_momentum(self, price_series: pd.Series, regime: str) -> float:
        """Calculate the momentum strength of the current regime."""
        try:
            if len(price_series) < 10:
                return 0.0

            # Calculate recent price momentum
            recent_prices = price_series.tail(10)
            price_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]

            # Adjust momentum based on regime type
            if regime == 'bullish':
                momentum = max(0.0, price_change * 10)  # Positive momentum for bullish
            elif regime == 'bearish':
                momentum = max(0.0, -price_change * 10)  # Negative price change = positive momentum for bearish
            else:
                momentum = max(0.0, 1.0 - abs(price_change) * 10)  # Low volatility = good for neutral

            return min(1.0, momentum)

        except Exception:
            return 0.0

    def _get_volume_confirmation(self, regime: str, volume_regime: Dict[str, Any]) -> float:
        """Get volume confirmation for the current regime."""
        try:
            volume_type = volume_regime.get('regime', 'normal')
            volume_confidence = volume_regime.get('confidence', 0.0)

            if regime in ['bullish', 'bearish'] and volume_type in ['high', 'elevated']:
                return volume_confidence  # High volume confirms trends
            elif regime == 'neutral' and volume_type in ['low', 'subdued']:
                return volume_confidence  # Low volume confirms sideways
            else:
                return volume_confidence * 0.5  # Partial confirmation

        except Exception:
            return 0.0

    def _get_volatility_confirmation(self, regime: str, volatility_regime: Dict[str, Any]) -> float:
        """Get volatility confirmation for the current regime."""
        try:
            vol_type = volatility_regime.get('regime', 'normal')
            vol_confidence = volatility_regime.get('confidence', 0.0)

            if regime in ['bullish', 'bearish'] and vol_type in ['normal', 'subdued']:
                return vol_confidence  # Normal volatility confirms trends
            elif regime == 'neutral' and vol_type in ['low', 'subdued']:
                return vol_confidence  # Low volatility confirms sideways
            else:
                return vol_confidence * 0.5  # Partial confirmation

        except Exception:
            return 0.0

    def _calculate_regime_quality(self, regime: str, confidence: float, persistence: int, consistency: float) -> float:
        """Calculate overall quality score for the regime."""
        try:
            quality_factors = [
                confidence,
                min(1.0, persistence / 10.0),  # Normalize persistence
                consistency
            ]

            # Penalty for uncertain regime
            if regime == 'uncertain':
                quality_score = np.mean(quality_factors) * 0.5
            else:
                quality_score = np.mean(quality_factors)

            return max(0.0, min(1.0, quality_score))

        except Exception:
            return 0.0

    def _calculate_exhaustion_risk(self, price_series: pd.Series, regime: str, persistence: int) -> float:
        """Calculate risk of regime exhaustion/reversal."""
        try:
            if len(price_series) < 20:
                return 0.0

            exhaustion_risk = 0.0

            # High persistence increases exhaustion risk
            if persistence > 30:
                exhaustion_risk += 0.3
            elif persistence > 20:
                exhaustion_risk += 0.1

            # Check for divergence in momentum
            recent_momentum = price_series.pct_change().tail(5).mean()
            older_momentum = price_series.pct_change().tail(20).head(10).mean()

            if regime == 'bullish' and recent_momentum < older_momentum:
                exhaustion_risk += 0.2  # Momentum divergence in uptrend
            elif regime == 'bearish' and recent_momentum > older_momentum:
                exhaustion_risk += 0.2  # Momentum divergence in downtrend

            return min(1.0, exhaustion_risk)

        except Exception:
            return 0.0

    def _calculate_regime_duration(self, data: Dict[str, Any], regime_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate duration-related metrics for the current market regime.

        Args:
            data: Dictionary containing price and market data
            regime_data: Dictionary containing regime analysis results

        Returns:
            Dictionary with regime duration metrics
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {
                    'current_duration': 0,
                    'expected_duration': 0,
                    'duration_percentile': 50,
                    'regime_age': 'new'
                }

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 10:
                return {
                    'current_duration': 1,
                    'expected_duration': 10,
                    'duration_percentile': 10,
                    'regime_age': 'new'
                }

            # Extract overall regime information
            overall_regime = regime_data.get('overall_regime', {})
            current_regime = overall_regime.get('regime', 'uncertain')

            # 1. Calculate current regime duration
            current_duration = self._get_current_regime_duration(close_prices, current_regime)

            # 2. Calculate expected duration based on historical patterns
            expected_duration = self._get_expected_regime_duration(close_prices, current_regime)

            # 3. Calculate historical regime durations for comparison
            historical_durations = self._get_historical_regime_durations(close_prices, current_regime)

            # 4. Calculate duration percentile (where current duration ranks historically)
            if historical_durations:
                duration_percentile = (sum(1 for d in historical_durations if d < current_duration) /
                                     len(historical_durations)) * 100
            else:
                duration_percentile = 50  # Default to median

            # 5. Determine regime age category
            regime_age = self._categorize_regime_age(current_duration, expected_duration)

            # 6. Calculate duration stability
            duration_stability = self._calculate_duration_stability(historical_durations)

            # 7. Estimate remaining duration
            remaining_duration = max(0, expected_duration - current_duration)

            # 8. Calculate duration risk (probability of regime change)
            duration_risk = self._calculate_duration_risk(current_duration, expected_duration,
                                                        duration_percentile)

            return {
                'current_duration': int(current_duration),
                'expected_duration': int(expected_duration),
                'remaining_duration': int(remaining_duration),
                'duration_percentile': float(duration_percentile),
                'regime_age': regime_age,
                'duration_stability': float(duration_stability),
                'duration_risk': float(duration_risk),
                'historical_stats': {
                    'avg_duration': float(np.mean(historical_durations)) if historical_durations else 0.0,
                    'median_duration': float(np.median(historical_durations)) if historical_durations else 0.0,
                    'std_duration': float(np.std(historical_durations)) if historical_durations else 0.0,
                    'count': len(historical_durations)
                }
            }

        except Exception as e:
            logger.warning(f"Regime duration calculation failed: {e}")
            return {
                'current_duration': 1,
                'expected_duration': 10,
                'duration_percentile': 50,
                'regime_age': 'new'
            }

    def _get_current_regime_duration(self, price_series: pd.Series, regime: str) -> int:
        """Calculate how long the current regime has been active."""
        try:
            if len(price_series) < 5:
                return 1

            # Use multiple timeframe moving averages for regime identification
            ma_5 = price_series.rolling(window=5, min_periods=3).mean()
            ma_20 = price_series.rolling(window=20, min_periods=10).mean()
            ma_50 = price_series.rolling(window=50, min_periods=25).mean()

            duration = 1
            current_price = price_series.iloc[-1]

            # Look backwards to find regime start
            for i in range(len(price_series) - 2, max(0, len(price_series) - 101), -1):
                if i < len(ma_5) and i < len(ma_20):
                    price_i = price_series.iloc[i]
                    ma5_i = ma_5.iloc[i] if not pd.isna(ma_5.iloc[i]) else price_i
                    ma20_i = ma_20.iloc[i] if not pd.isna(ma_20.iloc[i]) else price_i

                    # Check if regime conditions are still met
                    regime_continues = False

                    if regime == 'bullish':
                        regime_continues = (price_i > ma5_i > ma20_i) or (price_i > ma5_i and ma5_i > ma20_i * 0.98)
                    elif regime == 'bearish':
                        regime_continues = (price_i < ma5_i < ma20_i) or (price_i < ma5_i and ma5_i < ma20_i * 1.02)
                    elif regime == 'neutral':
                        regime_continues = abs(ma5_i - ma20_i) / ma20_i < 0.03
                    else:  # uncertain
                        regime_continues = True  # Continue counting for uncertain regime

                    if regime_continues:
                        duration += 1
                    else:
                        break

            return min(duration, 100)  # Cap at 100 periods

        except Exception:
            return 1

    def _get_expected_regime_duration(self, price_series: pd.Series, regime: str) -> int:
        """Estimate expected duration for the regime type based on volatility and historical patterns."""
        try:
            # Base expected durations by regime type
            base_durations = {
                'bullish': 25,
                'bearish': 20,
                'neutral': 15,
                'uncertain': 10
            }

            base_duration = base_durations.get(regime, 15)

            # Adjust based on market volatility
            if len(price_series) >= 20:
                volatility = price_series.pct_change().rolling(window=20).std().iloc[-1]
                avg_volatility = price_series.pct_change().std()

                if not pd.isna(volatility) and not pd.isna(avg_volatility) and avg_volatility > 0:
                    vol_ratio = volatility / avg_volatility

                    # High volatility = shorter expected duration
                    if vol_ratio > 1.5:
                        base_duration = int(base_duration * 0.7)
                    elif vol_ratio > 1.2:
                        base_duration = int(base_duration * 0.85)
                    elif vol_ratio < 0.8:
                        base_duration = int(base_duration * 1.2)

            return max(5, base_duration)

        except Exception:
            return 15

    def _get_historical_regime_durations(self, price_series: pd.Series, regime: str) -> List[int]:
        """Find historical durations of similar regimes."""
        try:
            if len(price_series) < 50:
                return []

            durations = []
            ma_5 = price_series.rolling(window=5, min_periods=3).mean()
            ma_20 = price_series.rolling(window=20, min_periods=10).mean()

            current_regime_type = None
            current_duration = 0

            for i in range(20, len(price_series)):
                if i < len(ma_5) and i < len(ma_20):
                    price_i = price_series.iloc[i]
                    ma5_i = ma_5.iloc[i] if not pd.isna(ma_5.iloc[i]) else price_i
                    ma20_i = ma_20.iloc[i] if not pd.isna(ma_20.iloc[i]) else price_i

                    # Determine regime at this point
                    if price_i > ma5_i > ma20_i:
                        regime_type = 'bullish'
                    elif price_i < ma5_i < ma20_i:
                        regime_type = 'bearish'
                    elif abs(ma5_i - ma20_i) / ma20_i < 0.03:
                        regime_type = 'neutral'
                    else:
                        regime_type = 'uncertain'

                    # Track regime changes
                    if regime_type == current_regime_type:
                        current_duration += 1
                    else:
                        # Regime changed - record previous duration if it matches our target
                        if current_regime_type == regime and current_duration >= 3:
                            durations.append(current_duration)

                        current_regime_type = regime_type
                        current_duration = 1

            # Don't include the current ongoing regime in historical data
            return durations[-20:] if len(durations) > 20 else durations  # Keep last 20 instances

        except Exception:
            return []

    def _categorize_regime_age(self, current_duration: int, expected_duration: int) -> str:
        """Categorize the age of the current regime."""
        try:
            if current_duration <= expected_duration * 0.25:
                return 'new'
            elif current_duration <= expected_duration * 0.75:
                return 'developing'
            elif current_duration <= expected_duration * 1.25:
                return 'mature'
            elif current_duration <= expected_duration * 2.0:
                return 'extended'
            else:
                return 'exhausted'

        except Exception:
            return 'unknown'

    def _calculate_duration_stability(self, historical_durations: List[int]) -> float:
        """Calculate how stable regime durations are historically."""
        try:
            if len(historical_durations) < 3:
                return 0.5  # Default moderate stability

            # Calculate coefficient of variation (lower = more stable)
            mean_duration = np.mean(historical_durations)
            std_duration = np.std(historical_durations)

            if mean_duration > 0:
                cv = std_duration / mean_duration
                # Convert to stability score (0-1, higher = more stable)
                stability = max(0.0, min(1.0, 1.0 - cv))
            else:
                stability = 0.5

            return stability

        except Exception:
            return 0.5

    def _calculate_duration_risk(self, current_duration: int, expected_duration: int,
                               duration_percentile: float) -> float:
        """Calculate the risk of regime change based on duration."""
        try:
            risk_factors = []

            # Risk based on expected duration
            if expected_duration > 0:
                duration_ratio = current_duration / expected_duration
                if duration_ratio > 2.0:
                    risk_factors.append(0.8)  # Very high risk
                elif duration_ratio > 1.5:
                    risk_factors.append(0.6)  # High risk
                elif duration_ratio > 1.0:
                    risk_factors.append(0.4)  # Moderate risk
                else:
                    risk_factors.append(0.2)  # Low risk

            # Risk based on percentile
            if duration_percentile > 90:
                risk_factors.append(0.8)  # Very high risk
            elif duration_percentile > 75:
                risk_factors.append(0.6)  # High risk
            elif duration_percentile > 50:
                risk_factors.append(0.4)  # Moderate risk
            else:
                risk_factors.append(0.2)  # Low risk

            # Base risk for very long regimes
            if current_duration > 50:
                risk_factors.append(0.7)

            return min(1.0, np.mean(risk_factors)) if risk_factors else 0.3

        except Exception:
            return 0.3

    def _calculate_regime_transition_probabilities(self, data: Dict[str, Any], regime_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate probabilities of transitioning to different market regimes.

        Args:
            data: Dictionary containing price and market data
            regime_data: Dictionary containing regime analysis results

        Returns:
            Dictionary with regime transition probabilities
        """
        try:
            df = data.get('df')
            if df is None or df.empty:
                return {
                    'bullish': 0.25,
                    'bearish': 0.25,
                    'neutral': 0.25,
                    'uncertain': 0.25
                }

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 20:
                return {
                    'bullish': 0.25,
                    'bearish': 0.25,
                    'neutral': 0.25,
                    'uncertain': 0.25
                }

            # Extract current regime information
            overall_regime = regime_data.get('overall_regime', {})
            current_regime = overall_regime.get('regime', 'uncertain')

            # 1. Build historical transition matrix
            transition_matrix = self._build_transition_matrix(close_prices)

            # 2. Get base transition probabilities from historical data
            base_probabilities = self._get_base_transition_probabilities(current_regime, transition_matrix)

            # 3. Adjust probabilities based on current market conditions
            adjusted_probabilities = self._adjust_transition_probabilities(
                base_probabilities, data, regime_data
            )

            # 4. Apply regime duration effects
            duration_adjusted = self._apply_duration_effects(
                adjusted_probabilities, regime_data
            )

            # 5. Apply momentum and trend strength effects
            final_probabilities = self._apply_momentum_effects(
                duration_adjusted, data, regime_data
            )

            # 6. Normalize probabilities to sum to 1
            total_prob = sum(final_probabilities.values())
            if total_prob > 0:
                normalized_probabilities = {k: v / total_prob for k, v in final_probabilities.items()}
            else:
                normalized_probabilities = {
                    'bullish': 0.25,
                    'bearish': 0.25,
                    'neutral': 0.25,
                    'uncertain': 0.25
                }

            # 7. Calculate additional metrics
            most_likely_regime = max(normalized_probabilities.keys(),
                                   key=lambda k: normalized_probabilities[k])

            transition_confidence = max(normalized_probabilities.values())

            regime_stability = normalized_probabilities.get(current_regime, 0.0)

            return {
                'probabilities': normalized_probabilities,
                'most_likely_next': most_likely_regime,
                'transition_confidence': float(transition_confidence),
                'regime_stability': float(regime_stability),
                'transition_matrix': transition_matrix
            }

        except Exception as e:
            logger.warning(f"Regime transition probability calculation failed: {e}")
            return {
                'bullish': 0.25,
                'bearish': 0.25,
                'neutral': 0.25,
                'uncertain': 0.25
            }

    def _build_transition_matrix(self, price_series: pd.Series) -> Dict[str, Dict[str, float]]:
        """Build historical regime transition matrix."""
        try:
            if len(price_series) < 50:
                # Default transition matrix if insufficient data
                return {
                    'bullish': {'bullish': 0.6, 'bearish': 0.15, 'neutral': 0.2, 'uncertain': 0.05},
                    'bearish': {'bullish': 0.15, 'bearish': 0.6, 'neutral': 0.2, 'uncertain': 0.05},
                    'neutral': {'bullish': 0.3, 'bearish': 0.3, 'neutral': 0.35, 'uncertain': 0.05},
                    'uncertain': {'bullish': 0.25, 'bearish': 0.25, 'neutral': 0.25, 'uncertain': 0.25}
                }

            # Identify historical regimes
            regime_sequence = self._identify_regime_sequence(price_series)

            # Count transitions
            transitions = {}
            for i in range(len(regime_sequence) - 1):
                current = regime_sequence[i]
                next_regime = regime_sequence[i + 1]

                if current not in transitions:
                    transitions[current] = {}
                if next_regime not in transitions[current]:
                    transitions[current][next_regime] = 0

                transitions[current][next_regime] += 1

            # Convert counts to probabilities
            transition_matrix = {}
            regimes = ['bullish', 'bearish', 'neutral', 'uncertain']

            for from_regime in regimes:
                transition_matrix[from_regime] = {}
                total_transitions = sum(transitions.get(from_regime, {}).values())

                if total_transitions > 0:
                    for to_regime in regimes:
                        count = transitions.get(from_regime, {}).get(to_regime, 0)
                        transition_matrix[from_regime][to_regime] = count / total_transitions
                else:
                    # Equal probability if no historical data
                    for to_regime in regimes:
                        transition_matrix[from_regime][to_regime] = 0.25

            return transition_matrix

        except Exception:
            # Default transition matrix
            return {
                'bullish': {'bullish': 0.6, 'bearish': 0.15, 'neutral': 0.2, 'uncertain': 0.05},
                'bearish': {'bullish': 0.15, 'bearish': 0.6, 'neutral': 0.2, 'uncertain': 0.05},
                'neutral': {'bullish': 0.3, 'bearish': 0.3, 'neutral': 0.35, 'uncertain': 0.05},
                'uncertain': {'bullish': 0.25, 'bearish': 0.25, 'neutral': 0.25, 'uncertain': 0.25}
            }

    def _identify_regime_sequence(self, price_series: pd.Series) -> List[str]:
        """Identify sequence of historical regimes."""
        try:
            regime_sequence = []
            ma_5 = price_series.rolling(window=5, min_periods=3).mean()
            ma_20 = price_series.rolling(window=20, min_periods=10).mean()

            for i in range(20, len(price_series)):
                if i < len(ma_5) and i < len(ma_20):
                    price_i = price_series.iloc[i]
                    ma5_i = ma_5.iloc[i] if not pd.isna(ma_5.iloc[i]) else price_i
                    ma20_i = ma_20.iloc[i] if not pd.isna(ma_20.iloc[i]) else price_i

                    # Determine regime
                    if price_i > ma5_i > ma20_i:
                        regime = 'bullish'
                    elif price_i < ma5_i < ma20_i:
                        regime = 'bearish'
                    elif abs(ma5_i - ma20_i) / ma20_i < 0.03:
                        regime = 'neutral'
                    else:
                        regime = 'uncertain'

                    regime_sequence.append(regime)

            return regime_sequence

        except Exception:
            return []

    def _get_base_transition_probabilities(self, current_regime: str,
                                         transition_matrix: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Get base transition probabilities from historical data."""
        try:
            if current_regime in transition_matrix:
                return transition_matrix[current_regime].copy()
            else:
                # Default equal probabilities
                return {'bullish': 0.25, 'bearish': 0.25, 'neutral': 0.25, 'uncertain': 0.25}

        except Exception:
            return {'bullish': 0.25, 'bearish': 0.25, 'neutral': 0.25, 'uncertain': 0.25}

    def _adjust_transition_probabilities(self, base_probs: Dict[str, float],
                                       data: Dict[str, Any],
                                       regime_data: Dict[str, Any]) -> Dict[str, float]:
        """Adjust probabilities based on current market conditions."""
        try:
            adjusted_probs = base_probs.copy()

            # Get current market condition indicators
            volatility_regime = regime_data.get('volatility_regime', {})
            volume_regime = regime_data.get('volume_regime', {})

            vol_type = volatility_regime.get('regime', 'normal')
            volume_type = volume_regime.get('regime', 'normal')

            # High volatility increases uncertainty
            if vol_type in ['high', 'elevated']:
                adjusted_probs['uncertain'] *= 1.5
                adjusted_probs['bullish'] *= 0.8
                adjusted_probs['bearish'] *= 0.8
                adjusted_probs['neutral'] *= 0.7

            # Low volatility favors continuation
            elif vol_type in ['low', 'subdued']:
                current_regime = regime_data.get('overall_regime', {}).get('regime', 'uncertain')
                if current_regime in adjusted_probs:
                    adjusted_probs[current_regime] *= 1.3

            # High volume can amplify trend changes
            if volume_type in ['high', 'elevated']:
                adjusted_probs['bullish'] *= 1.2
                adjusted_probs['bearish'] *= 1.2
                adjusted_probs['neutral'] *= 0.8

            # Low volume favors sideways action
            elif volume_type in ['low', 'subdued']:
                adjusted_probs['neutral'] *= 1.3
                adjusted_probs['bullish'] *= 0.9
                adjusted_probs['bearish'] *= 0.9

            return adjusted_probs

        except Exception:
            return base_probs

    def _apply_duration_effects(self, probs: Dict[str, float],
                              regime_data: Dict[str, Any]) -> Dict[str, float]:
        """Apply regime duration effects to transition probabilities."""
        try:
            adjusted_probs = probs.copy()

            # Get duration information
            regime_duration = regime_data.get('regime_duration', {})
            current_regime = regime_data.get('overall_regime', {}).get('regime', 'uncertain')

            duration_percentile = regime_duration.get('duration_percentile', 50)
            regime_age = regime_duration.get('regime_age', 'new')

            # Long-duration regimes are more likely to change
            if regime_age in ['extended', 'exhausted']:
                # Reduce probability of staying in current regime
                if current_regime in adjusted_probs:
                    adjusted_probs[current_regime] *= 0.7

                # Increase probability of transitioning to other regimes
                for regime in adjusted_probs:
                    if regime != current_regime:
                        adjusted_probs[regime] *= 1.1

            # Very new regimes are likely to continue
            elif regime_age == 'new':
                if current_regime in adjusted_probs:
                    adjusted_probs[current_regime] *= 1.2

            return adjusted_probs

        except Exception:
            return probs

    def _apply_momentum_effects(self, probs: Dict[str, float],
                              data: Dict[str, Any],
                              regime_data: Dict[str, Any]) -> Dict[str, float]:
        """Apply momentum and trend strength effects."""
        try:
            adjusted_probs = probs.copy()

            df = data.get('df')
            if df is None or df.empty:
                return probs

            close_prices = df['close'] if 'close' in df.columns else df.iloc[:, -1]

            if len(close_prices) < 10:
                return probs

            # Calculate recent momentum
            recent_momentum = close_prices.pct_change().tail(5).mean()
            momentum_strength = abs(recent_momentum)

            # Get trend regime strength
            trend_regime = regime_data.get('trend_regime', {})
            trend_strength = trend_regime.get('strength', 0.0)

            # Strong positive momentum favors bullish
            if recent_momentum > 0.01 and momentum_strength > 0.02:
                adjusted_probs['bullish'] *= 1.3
                adjusted_probs['bearish'] *= 0.7

            # Strong negative momentum favors bearish
            elif recent_momentum < -0.01 and momentum_strength > 0.02:
                adjusted_probs['bearish'] *= 1.3
                adjusted_probs['bullish'] *= 0.7

            # Weak momentum favors neutral
            elif momentum_strength < 0.005:
                adjusted_probs['neutral'] *= 1.2
                adjusted_probs['bullish'] *= 0.9
                adjusted_probs['bearish'] *= 0.9

            # Strong trend strength increases continuation probability
            if trend_strength > 0.7:
                current_regime = regime_data.get('overall_regime', {}).get('regime', 'uncertain')
                if current_regime in adjusted_probs:
                    adjusted_probs[current_regime] *= 1.2

            return adjusted_probs

        except Exception:
            return probs