"""
Technical Analysis Indicators Calculator
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import talib
from loguru import logger


class TechnicalIndicators:
    """Calculate technical analysis indicators"""

    def __init__(self, price_data: pd.DataFrame):
        """
        Initialize with price data

        Args:
            price_data: DataFrame with OHLCV data
        """
        self.data = price_data.copy()
        self._prepare_data()

    def _prepare_data(self):
        """Prepare data for technical analysis"""
        # Ensure required columns exist
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in self.data.columns:
                logger.warning(f"Missing column: {col}")

        # Convert to numpy arrays for TA-Lib (must be float64)
        self.open = self.data['open'].astype(np.float64).values
        self.high = self.data['high'].astype(np.float64).values
        self.low = self.data['low'].astype(np.float64).values
        self.close = self.data['close'].astype(np.float64).values
        self.volume = self.data['volume'].astype(np.float64).values if 'volume' in self.data.columns else None

    def calculate_moving_averages(self) -> Dict[str, np.ndarray]:
        """Calculate various moving averages"""
        indicators = {}

        # Simple Moving Averages
        indicators['sma_20'] = talib.SMA(self.close, timeperiod=20)
        indicators['sma_50'] = talib.SMA(self.close, timeperiod=50)
        indicators['sma_200'] = talib.SMA(self.close, timeperiod=200)

        # Exponential Moving Averages
        indicators['ema_9'] = talib.EMA(self.close, timeperiod=9)
        indicators['ema_12'] = talib.EMA(self.close, timeperiod=12)
        indicators['ema_21'] = talib.EMA(self.close, timeperiod=21)
        indicators['ema_26'] = talib.EMA(self.close, timeperiod=26)
        indicators['ema_50'] = talib.EMA(self.close, timeperiod=50)

        return indicators

    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, np.ndarray]:
        """Calculate MACD indicator"""
        macd_line, macd_signal, macd_histogram = talib.MACD(
            self.close, fastperiod=fast, slowperiod=slow, signalperiod=signal
        )

        return {
            'macd_line': macd_line,
            'macd_signal': macd_signal,
            'macd_histogram': macd_histogram
        }

    def calculate_rsi(self, period: int = 14) -> np.ndarray:
        """Calculate RSI indicator"""
        return talib.RSI(self.close, timeperiod=period)

    def calculate_bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> Dict[str, np.ndarray]:
        """Calculate Bollinger Bands"""
        upper, middle, lower = talib.BBANDS(
            self.close, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev
        )

        return {
            'bb_upper': upper,
            'bb_middle': middle,
            'bb_lower': lower
        }

    def calculate_stochastic(self, k_period: int = 14, d_period: int = 3) -> Dict[str, np.ndarray]:
        """Calculate Stochastic Oscillator"""
        slowk, slowd = talib.STOCH(
            self.high, self.low, self.close,
            fastk_period=k_period, slowk_period=3,
            slowk_matype=0, slowd_period=d_period, slowd_matype=0
        )

        return {
            'stoch_k': slowk,
            'stoch_d': slowd
        }

    def calculate_atr(self, period: int = 14) -> np.ndarray:
        """Calculate Average True Range"""
        return talib.ATR(self.high, self.low, self.close, timeperiod=period)

    def calculate_adx(self, period: int = 14) -> Dict[str, np.ndarray]:
        """Calculate ADX (Average Directional Index)"""
        adx = talib.ADX(self.high, self.low, self.close, timeperiod=period)
        plus_di = talib.PLUS_DI(self.high, self.low, self.close, timeperiod=period)
        minus_di = talib.MINUS_DI(self.high, self.low, self.close, timeperiod=period)

        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }

    def calculate_williams_r(self, period: int = 14) -> np.ndarray:
        """Calculate Williams %R"""
        return talib.WILLR(self.high, self.low, self.close, timeperiod=period)

    def calculate_cci(self, period: int = 20) -> np.ndarray:
        """Calculate Commodity Channel Index"""
        return talib.CCI(self.high, self.low, self.close, timeperiod=period)

    def calculate_momentum_indicators(self) -> Dict[str, np.ndarray]:
        """Calculate momentum indicators"""
        indicators = {}

        # Momentum
        indicators['momentum'] = talib.MOM(self.close, timeperiod=10)

        # Rate of Change
        indicators['roc'] = talib.ROC(self.close, timeperiod=10)

        # Price Rate of Change
        indicators['rocp'] = talib.ROCP(self.close, timeperiod=10)

        return indicators

    def calculate_volume_indicators(self) -> Dict[str, np.ndarray]:
        """Calculate volume-based indicators"""
        if self.volume is None:
            return {}

        indicators = {}

        # On Balance Volume
        indicators['obv'] = talib.OBV(self.close, self.volume)

        # Volume SMA
        indicators['volume_sma'] = talib.SMA(self.volume, timeperiod=20)

        # Ad Line (Accumulation/Distribution Line)
        indicators['ad_line'] = talib.AD(self.high, self.low, self.close, self.volume)

        # Chaikin A/D Oscillator
        indicators['chaikin_ad'] = talib.ADOSC(self.high, self.low, self.close, self.volume)

        return indicators

    def calculate_support_resistance(self) -> Dict[str, Any]:
        """Calculate support and resistance levels using pivot points"""
        # Get latest OHLC
        latest_high = self.high[-1]
        latest_low = self.low[-1]
        latest_close = self.close[-1]

        # Standard Pivot Points
        pivot_point = (latest_high + latest_low + latest_close) / 3

        # Resistance levels
        r1 = (2 * pivot_point) - latest_low
        r2 = pivot_point + (latest_high - latest_low)
        r3 = latest_high + 2 * (pivot_point - latest_low)

        # Support levels
        s1 = (2 * pivot_point) - latest_high
        s2 = pivot_point - (latest_high - latest_low)
        s3 = latest_low - 2 * (latest_high - pivot_point)

        return {
            'pivot_point': pivot_point,
            'resistance_1': r1,
            'resistance_2': r2,
            'resistance_3': r3,
            'support_1': s1,
            'support_2': s2,
            'support_3': s3
        }

    def calculate_fibonacci_retracement(self, swing_high: float = None, swing_low: float = None) -> Dict[str, float]:
        """Calculate Fibonacci retracement levels"""
        if swing_high is None:
            swing_high = np.max(self.high[-100:])  # Last 100 periods
        if swing_low is None:
            swing_low = np.min(self.low[-100:])  # Last 100 periods

        diff = swing_high - swing_low

        fib_levels = {
            'swing_high': swing_high,
            'swing_low': swing_low,
            'fib_0': swing_high,
            'fib_23.6': swing_high - 0.236 * diff,
            'fib_38.2': swing_high - 0.382 * diff,
            'fib_50.0': swing_high - 0.500 * diff,
            'fib_61.8': swing_high - 0.618 * diff,
            'fib_78.6': swing_high - 0.786 * diff,
            'fib_100': swing_low,
            'fib_123.6': swing_low - 0.236 * diff,
            'fib_161.8': swing_low - 0.618 * diff
        }

        return fib_levels

    def calculate_vwap(self) -> np.ndarray:
        """Calculate Volume Weighted Average Price"""
        if self.volume is None:
            return np.full(len(self.close), np.nan)

        typical_price = (self.high + self.low + self.close) / 3
        vwap = np.zeros(len(self.close))

        for i in range(len(self.close)):
            if i == 0:
                vwap[i] = typical_price[i]
            else:
                cumulative_tpv = np.sum(typical_price[:i+1] * self.volume[:i+1])
                cumulative_volume = np.sum(self.volume[:i+1])
                vwap[i] = cumulative_tpv / cumulative_volume if cumulative_volume > 0 else vwap[i-1]

        return vwap

    def calculate_pattern_recognition(self) -> Dict[str, np.ndarray]:
        """Calculate candlestick pattern recognition"""
        patterns = {}

        # Doji patterns
        patterns['doji'] = talib.CDLDOJI(self.open, self.high, self.low, self.close)
        patterns['dragonfly_doji'] = talib.CDLDRAGONFLYDOJI(self.open, self.high, self.low, self.close)
        patterns['gravestone_doji'] = talib.CDLGRAVESTONEDOJI(self.open, self.high, self.low, self.close)

        # Hammer patterns
        patterns['hammer'] = talib.CDLHAMMER(self.open, self.high, self.low, self.close)
        patterns['hanging_man'] = talib.CDLHANGINGMAN(self.open, self.high, self.low, self.close)
        patterns['inverted_hammer'] = talib.CDLINVERTEDHAMMER(self.open, self.high, self.low, self.close)

        # Engulfing patterns
        patterns['bullish_engulfing'] = talib.CDLENGULFING(self.open, self.high, self.low, self.close)
        patterns['bearish_engulfing'] = talib.CDLENGULFING(self.open, self.high, self.low, self.close) * -1

        # Star patterns
        patterns['morning_star'] = talib.CDLMORNINGSTAR(self.open, self.high, self.low, self.close)
        patterns['evening_star'] = talib.CDLEVENINGSTAR(self.open, self.high, self.low, self.close)

        # Other patterns
        patterns['shooting_star'] = talib.CDLSHOOTINGSTAR(self.open, self.high, self.low, self.close)
        patterns['spinning_top'] = talib.CDLSPINNINGTOP(self.open, self.high, self.low, self.close)

        return patterns

    def get_all_indicators(self) -> Dict[str, Any]:
        """Calculate all technical indicators"""
        indicators = {}

        # Moving averages
        indicators.update(self.calculate_moving_averages())

        # MACD
        indicators.update(self.calculate_macd())

        # RSI
        indicators['rsi'] = self.calculate_rsi()

        # Bollinger Bands
        indicators.update(self.calculate_bollinger_bands())

        # Stochastic
        indicators.update(self.calculate_stochastic())

        # ATR
        indicators['atr'] = self.calculate_atr()

        # ADX
        indicators.update(self.calculate_adx())

        # Williams %R
        indicators['williams_r'] = self.calculate_williams_r()

        # CCI
        indicators['cci'] = self.calculate_cci()

        # Momentum indicators
        indicators.update(self.calculate_momentum_indicators())

        # Volume indicators
        indicators.update(self.calculate_volume_indicators())

        # VWAP
        indicators['vwap'] = self.calculate_vwap()

        # Support/Resistance
        indicators['support_resistance'] = self.calculate_support_resistance()

        # Fibonacci retracement
        indicators['fibonacci'] = self.calculate_fibonacci_retracement()

        # Pattern recognition
        indicators['patterns'] = self.calculate_pattern_recognition()

        return indicators

    def get_latest_values(self) -> Dict[str, Any]:
        """Get latest values of all indicators"""
        all_indicators = self.get_all_indicators()
        latest_values = {}

        for key, value in all_indicators.items():
            if isinstance(value, np.ndarray):
                # Get the last non-NaN value
                valid_values = value[~np.isnan(value)]
                latest_values[key] = valid_values[-1] if len(valid_values) > 0 else None
            elif isinstance(value, dict):
                latest_values[key] = value
            else:
                latest_values[key] = value

        # Add current price info
        latest_values['current_price'] = self.close[-1]
        latest_values['current_volume'] = self.volume[-1] if self.volume is not None else None
        latest_values['price_change'] = self.close[-1] - self.close[-2] if len(self.close) > 1 else 0
        latest_values['price_change_percent'] = (latest_values['price_change'] / self.close[-2] * 100) if len(self.close) > 1 and self.close[-2] != 0 else 0

        return latest_values


class TrendAnalysis:
    """Analyze price trends"""

    def __init__(self, price_data: pd.DataFrame):
        self.data = price_data
        self.close = price_data['close'].values

    def identify_trend(self, short_period: int = 20, long_period: int = 50) -> Dict[str, Any]:
        """Identify overall trend direction"""
        short_ma = talib.SMA(self.close, timeperiod=short_period)
        long_ma = talib.SMA(self.close, timeperiod=long_period)

        current_price = self.close[-1]
        short_ma_current = short_ma[-1]
        long_ma_current = long_ma[-1]

        # Determine trend
        if current_price > short_ma_current > long_ma_current:
            trend = "Strong Uptrend"
            strength = "Strong"
        elif current_price > short_ma_current and short_ma_current > long_ma_current:
            trend = "Uptrend"
            strength = "Moderate"
        elif current_price < short_ma_current < long_ma_current:
            trend = "Strong Downtrend"
            strength = "Strong"
        elif current_price < short_ma_current and short_ma_current < long_ma_current:
            trend = "Downtrend"
            strength = "Moderate"
        else:
            trend = "Sideways"
            strength = "Weak"

        # Calculate trend angle
        if len(short_ma) >= 10:
            recent_slope = (short_ma[-1] - short_ma[-10]) / 9
            trend_angle = np.arctan(recent_slope) * 180 / np.pi
        else:
            trend_angle = 0

        return {
            'trend_direction': trend,
            'trend_strength': strength,
            'trend_angle': trend_angle,
            'short_ma': short_ma_current,
            'long_ma': long_ma_current,
            'current_price': current_price
        }

    def find_swing_points(self, window: int = 5) -> Dict[str, List]:
        """Find swing highs and lows"""
        highs = []
        lows = []

        for i in range(window, len(self.close) - window):
            # Check for swing high
            if all(self.close[i] >= self.close[j] for j in range(i-window, i+window+1) if j != i):
                highs.append({'index': i, 'price': self.close[i], 'date': self.data.index[i] if hasattr(self.data, 'index') else i})

            # Check for swing low
            if all(self.close[i] <= self.close[j] for j in range(i-window, i+window+1) if j != i):
                lows.append({'index': i, 'price': self.close[i], 'date': self.data.index[i] if hasattr(self.data, 'index') else i})

        return {
            'swing_highs': highs,
            'swing_lows': lows
        }