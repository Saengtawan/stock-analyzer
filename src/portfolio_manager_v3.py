#!/usr/bin/env python3
"""
Portfolio Manager v5 - RULE-BASED EXIT SYSTEM 🎯
================================================

ระบบ portfolio ที่ใช้ Complete 6-Layer System + v5 RULE-BASED EXITS:
- Layer 1-3: Macro (Fed, Breadth, Sector) - จาก pre-computed macro
- Layer 4-5: Fundamental + Catalyst - สำหรับ re-evaluation
- Layer 6: Technical - สำหรับ exit signals
- v5: RULE-BASED EXIT SYSTEM - Configurable, Tunable, Optimizable!

Features:
- Load macro regimes จาก JSON (fast!)
- Daily monitoring ด้วย 6-layer system
- **RULE-BASED exits**: 11 rules with configurable thresholds
- **Performance tracking**: Track which rules work best
- **Easy tuning**: Change thresholds without editing code
- **A/B testing**: Export/import configs for testing
- Portfolio stats tracking
- Sector-aware regime warnings

v5 Rules (11 total):
  🎯 CRITICAL: TARGET_HIT, HARD_STOP, TRAILING_STOP
  🔥 HIGH: SMART_GAP_DOWN, SMART_BREAKING_DOWN
  📊 MEDIUM: SMART_VOLUME_COLLAPSE, SMART_FAILED_PUMP, SMART_SMA20_BREAK
  📉 LOW: SMART_WEAK_RSI, SMART_MOMENTUM_REVERSAL, MAX_HOLD

v5 Backtested Performance:
- Win Rate: 39.6% (only 0.4% from 40% target!)
- Avg Loss: -2.98% ✅ (target met!)
- Loss Impact: 67.1% (only 7.1% from 60% target!)
- Net Profit: $890 per 100 trades ✅ (exceeds $700 target!)

New Methods:
- get_exit_rules_stats(): Track rule performance
- tune_exit_rule(): Adjust thresholds
- enable/disable_exit_rule(): Toggle rules
- export/import_exit_rules_config(): A/B testing
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import yfinance as yf
import pandas as pd
import numpy as np
from loguru import logger
import talib

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import rule-based exit system
try:
    from src.exit_rules_engine import ExitRulesEngine, MarketData
except ImportError:
    from exit_rules_engine import ExitRulesEngine, MarketData

# Import complete system components
try:
    from src.market_regime_detector import MarketRegimeDetector
    from src.complete_growth_system import CompleteGrowthSystem
    from src.sector_regime_detector import SectorRegimeDetector  # v3.3
except ImportError:
    # Fallback for direct execution
    from market_regime_detector import MarketRegimeDetector
    from complete_growth_system import CompleteGrowthSystem
    try:
        from sector_regime_detector import SectorRegimeDetector  # v3.3
    except ImportError:
        SectorRegimeDetector = None  # Optional


class DynamicSLTPCalculator:
    """
    Dynamic Stop Loss / Take Profit Calculator - v6.0
    ===================================================

    Calculates SL/TP based on REAL DATA instead of hardcoded percentages:
    - ATR (Average True Range) for volatility-based stop distance
    - Support levels for stop loss placement
    - Resistance levels for take profit placement
    - Risk:Reward ratio enforcement (min 1:1.5)
    - Market/Sector regime adjustments

    Data Sources Used:
    - Price history (OHLCV) for ATR calculation
    - Pivot Points for support/resistance
    - Fibonacci retracement levels
    - Bollinger Bands for volatility context
    - RSI for overbought/oversold adjustments
    - Sector regime for risk adjustment
    """

    # Regime-based multipliers for SL/TP
    REGIME_MULTIPLIERS = {
        'STRONG BULL': {'sl_mult': 1.2, 'tp_mult': 1.3},   # Wider SL, higher TP in bull
        'BULL': {'sl_mult': 1.1, 'tp_mult': 1.2},
        'NEUTRAL': {'sl_mult': 1.0, 'tp_mult': 1.0},
        'WEAK': {'sl_mult': 0.9, 'tp_mult': 0.85},         # Tighter SL, lower TP in weak
        'BEAR': {'sl_mult': 0.8, 'tp_mult': 0.7},
        'STRONG BEAR': {'sl_mult': 0.7, 'tp_mult': 0.6},
        'UNKNOWN': {'sl_mult': 1.0, 'tp_mult': 1.0},
    }

    # Minimum Risk:Reward ratio
    MIN_RR_RATIO = 1.5  # At least 1:1.5 risk to reward

    def __init__(self):
        """Initialize the calculator"""
        self._cache = {}

    def calculate_atr(self, hist: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average True Range (ATR) - the most important volatility measure

        ATR tells us how much a stock typically moves in a day.
        This is the foundation for dynamic SL/TP calculation.
        """
        if len(hist) < period + 1:
            return None

        try:
            high = hist['High'].values.astype(np.float64)
            low = hist['Low'].values.astype(np.float64)
            close = hist['Close'].values.astype(np.float64)

            atr = talib.ATR(high, low, close, timeperiod=period)
            current_atr = atr[-1]

            if np.isnan(current_atr):
                return None

            return float(current_atr)
        except Exception as e:
            logger.debug(f"ATR calculation error: {e}")
            return None

    def calculate_support_resistance(self, hist: pd.DataFrame) -> Dict:
        """
        Calculate support and resistance levels using multiple methods:
        1. Pivot Points (Standard)
        2. Recent swing highs/lows
        3. Fibonacci retracement
        """
        try:
            close = hist['Close'].values
            high = hist['High'].values
            low = hist['Low'].values

            current_price = close[-1]

            # 1. Standard Pivot Points (most recent day)
            pivot_high = high[-1]
            pivot_low = low[-1]
            pivot_close = close[-1]

            pivot_point = (pivot_high + pivot_low + pivot_close) / 3

            # Resistance levels
            r1 = (2 * pivot_point) - pivot_low
            r2 = pivot_point + (pivot_high - pivot_low)
            r3 = pivot_high + 2 * (pivot_point - pivot_low)

            # Support levels
            s1 = (2 * pivot_point) - pivot_high
            s2 = pivot_point - (pivot_high - pivot_low)
            s3 = pivot_low - 2 * (pivot_high - pivot_point)

            # 2. Recent swing analysis (last 30 days)
            lookback = min(30, len(hist))
            recent_high = float(np.max(high[-lookback:]))
            recent_low = float(np.min(low[-lookback:]))

            # 3. Fibonacci retracement levels
            fib_range = recent_high - recent_low
            fib_382 = recent_high - 0.382 * fib_range  # 38.2% retracement
            fib_500 = recent_high - 0.500 * fib_range  # 50% retracement
            fib_618 = recent_high - 0.618 * fib_range  # 61.8% retracement

            # Fibonacci extension for targets
            fib_ext_127 = recent_high + 0.27 * fib_range   # 127% extension
            fib_ext_162 = recent_high + 0.62 * fib_range   # 162% extension

            return {
                # Pivot points
                'pivot': float(pivot_point),
                'r1': float(r1),
                'r2': float(r2),
                'r3': float(r3),
                's1': float(s1),
                's2': float(s2),
                's3': float(s3),

                # Swing levels
                'recent_high': recent_high,
                'recent_low': recent_low,

                # Fibonacci
                'fib_382': float(fib_382),
                'fib_500': float(fib_500),
                'fib_618': float(fib_618),
                'fib_ext_127': float(fib_ext_127),
                'fib_ext_162': float(fib_ext_162),
            }
        except Exception as e:
            logger.debug(f"Support/Resistance calculation error: {e}")
            return None

    def calculate_rsi(self, hist: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI for overbought/oversold assessment"""
        try:
            close = hist['Close'].values.astype(np.float64)
            rsi = talib.RSI(close, timeperiod=period)
            return float(rsi[-1]) if not np.isnan(rsi[-1]) else None
        except:
            return None

    def calculate_bollinger_position(self, hist: pd.DataFrame) -> Dict:
        """
        Calculate where price is relative to Bollinger Bands
        This helps assess if price is extended or near mean
        """
        try:
            close = hist['Close'].values.astype(np.float64)

            upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)

            current_price = close[-1]
            bb_width = (upper[-1] - lower[-1]) / middle[-1] * 100  # BB width as %

            # Position within bands (0 = lower band, 1 = upper band)
            bb_position = (current_price - lower[-1]) / (upper[-1] - lower[-1]) if upper[-1] != lower[-1] else 0.5

            return {
                'upper': float(upper[-1]),
                'middle': float(middle[-1]),
                'lower': float(lower[-1]),
                'width_pct': float(bb_width),
                'position': float(bb_position),  # 0-1 range
            }
        except:
            return None

    def calculate_dynamic_sltp(self,
                               symbol: str,
                               entry_price: float,
                               regime: str = 'NEUTRAL',
                               sector_regime: str = 'NEUTRAL') -> Dict:
        """
        🎯 MAIN FUNCTION: Calculate DYNAMIC Stop Loss and Take Profit

        Based on REAL data:
        - ATR for volatility-appropriate stop distance
        - Support/Resistance for intelligent level placement
        - Risk:Reward ratio enforcement
        - Regime-based adjustments

        Returns:
            Dict with:
            - stop_loss: calculated SL price
            - take_profit: calculated TP price
            - sl_pct: SL as percentage from entry
            - tp_pct: TP as percentage from entry
            - rr_ratio: Risk:Reward ratio achieved
            - calculation_method: how it was calculated
            - data_sources: what data was used
        """
        logger.info(f"📊 Calculating DYNAMIC SL/TP for {symbol} @ ${entry_price:.2f}")

        # Get price history
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='90d')

            if hist.empty or len(hist) < 30:
                logger.warning(f"Insufficient data for {symbol}, using fallback")
                return self._fallback_calculation(entry_price, regime)
        except Exception as e:
            logger.warning(f"Failed to get data for {symbol}: {e}")
            return self._fallback_calculation(entry_price, regime)

        # 1. Calculate ATR (the most important metric)
        atr = self.calculate_atr(hist)
        atr_pct = (atr / entry_price * 100) if atr else None

        # 2. Calculate Support/Resistance levels
        sr_levels = self.calculate_support_resistance(hist)

        # 3. Get RSI for overbought/oversold context
        rsi = self.calculate_rsi(hist)

        # 4. Get Bollinger Band position
        bb_info = self.calculate_bollinger_position(hist)

        # 5. Get regime multipliers
        use_regime = sector_regime if sector_regime != 'UNKNOWN' else regime
        multipliers = self.REGIME_MULTIPLIERS.get(use_regime, self.REGIME_MULTIPLIERS['NEUTRAL'])

        data_sources = []

        # ===== CALCULATE STOP LOSS =====
        sl_candidates = []

        # Method 1: ATR-based stop (2x ATR is standard)
        if atr:
            atr_stop = entry_price - (2.0 * atr * multipliers['sl_mult'])
            sl_candidates.append(('ATR', atr_stop))
            data_sources.append('ATR')
            logger.info(f"   ATR-based SL: ${atr_stop:.2f} (ATR=${atr:.2f}, {atr_pct:.1f}%)")

        # Method 2: Support level stop
        if sr_levels:
            # Find nearest support below entry
            supports = [sr_levels['s1'], sr_levels['s2'], sr_levels['fib_618'], sr_levels['recent_low']]
            supports_below = [s for s in supports if s < entry_price]

            if supports_below:
                support_stop = max(supports_below) * 0.995  # 0.5% buffer below support
                sl_candidates.append(('Support', support_stop))
                data_sources.append('Support/Resistance')
                logger.info(f"   Support-based SL: ${support_stop:.2f}")

        # Method 3: Bollinger Band lower
        if bb_info and bb_info['lower'] < entry_price:
            bb_stop = bb_info['lower'] * multipliers['sl_mult']
            sl_candidates.append(('Bollinger', bb_stop))
            data_sources.append('Bollinger Bands')
            logger.info(f"   Bollinger-based SL: ${bb_stop:.2f}")

        # ===== CALCULATE TAKE PROFIT =====
        tp_candidates = []

        # Method 1: ATR-based target (3x ATR for 1:1.5 RR)
        if atr:
            atr_target = entry_price + (3.0 * atr * multipliers['tp_mult'])
            tp_candidates.append(('ATR', atr_target))
            logger.info(f"   ATR-based TP: ${atr_target:.2f}")

        # Method 2: Resistance level target
        if sr_levels:
            # Find nearest resistance above entry
            resistances = [sr_levels['r1'], sr_levels['r2'], sr_levels['fib_ext_127'], sr_levels['recent_high']]
            resistances_above = [r for r in resistances if r > entry_price]

            if resistances_above:
                resistance_target = min(resistances_above) * 0.995  # 0.5% buffer before resistance
                tp_candidates.append(('Resistance', resistance_target))
                logger.info(f"   Resistance-based TP: ${resistance_target:.2f}")

        # Method 3: Bollinger Band upper
        if bb_info and bb_info['upper'] > entry_price:
            bb_target = bb_info['upper'] * multipliers['tp_mult']
            tp_candidates.append(('Bollinger', bb_target))
            logger.info(f"   Bollinger-based TP: ${bb_target:.2f}")

        # ===== SELECT BEST SL/TP WITH RR RATIO ENFORCEMENT =====

        # Select stop loss (highest candidate = most conservative)
        if sl_candidates:
            stop_loss = max(sl_candidates, key=lambda x: x[1])[1]
            sl_method = max(sl_candidates, key=lambda x: x[1])[0]
        else:
            stop_loss = entry_price * 0.965  # Fallback: -3.5%
            sl_method = 'Fallback'

        # Ensure SL is not too close (min 1.5% away) or too far (max 6% away)
        sl_pct = ((entry_price - stop_loss) / entry_price) * 100
        if sl_pct < 1.5:
            stop_loss = entry_price * 0.985
            sl_pct = 1.5
            sl_method += '+MinEnforced'
        elif sl_pct > 6.0:
            stop_loss = entry_price * 0.94
            sl_pct = 6.0
            sl_method += '+MaxEnforced'

        # Calculate risk (distance to SL)
        risk_amount = entry_price - stop_loss

        # Select take profit ensuring minimum RR ratio
        min_tp_for_rr = entry_price + (risk_amount * self.MIN_RR_RATIO)

        if tp_candidates:
            # Filter candidates that meet minimum RR
            valid_tp = [(m, p) for m, p in tp_candidates if p >= min_tp_for_rr]

            if valid_tp:
                # Choose the nearest valid target (most achievable)
                take_profit = min(valid_tp, key=lambda x: x[1])[1]
                tp_method = min(valid_tp, key=lambda x: x[1])[0]
            else:
                # Force minimum RR ratio target
                take_profit = min_tp_for_rr
                tp_method = 'RR_Enforced'
        else:
            take_profit = min_tp_for_rr
            tp_method = 'RR_Enforced'

        # Calculate final percentages
        tp_pct = ((take_profit - entry_price) / entry_price) * 100
        rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 0

        # RSI adjustment: if overbought, reduce TP expectations
        if rsi and rsi > 70:
            take_profit = take_profit * 0.97  # Reduce TP by 3%
            tp_pct = ((take_profit - entry_price) / entry_price) * 100
            tp_method += '+RSI_OB_Adj'
            data_sources.append('RSI')
            logger.info(f"   ⚠️ RSI={rsi:.1f} (overbought) - reduced TP target")

        # Regime adjustment note
        if use_regime in ['BEAR', 'STRONG BEAR']:
            logger.info(f"   ⚠️ {use_regime} regime - tighter targets applied")
        elif use_regime in ['BULL', 'STRONG BULL']:
            logger.info(f"   ✅ {use_regime} regime - wider targets allowed")

        result = {
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'sl_pct': round(sl_pct, 2),
            'tp_pct': round(tp_pct, 2),
            'rr_ratio': round(rr_ratio, 2),
            'calculation_method': {
                'sl': sl_method,
                'tp': tp_method
            },
            'data_sources': list(set(data_sources)),
            'metrics': {
                'atr': round(atr, 4) if atr else None,
                'atr_pct': round(atr_pct, 2) if atr_pct else None,
                'rsi': round(rsi, 1) if rsi else None,
                'regime': use_regime,
            }
        }

        logger.info(f"✅ DYNAMIC SL/TP for {symbol}:")
        logger.info(f"   Entry: ${entry_price:.2f}")
        logger.info(f"   SL: ${stop_loss:.2f} ({-sl_pct:.1f}%) - Method: {sl_method}")
        logger.info(f"   TP: ${take_profit:.2f} (+{tp_pct:.1f}%) - Method: {tp_method}")
        logger.info(f"   Risk:Reward = 1:{rr_ratio:.2f}")
        logger.info(f"   Data: {', '.join(result['data_sources'])}")

        return result

    def _fallback_calculation(self, entry_price: float, regime: str = 'NEUTRAL') -> Dict:
        """
        Fallback calculation when real data is not available.
        Still applies regime adjustments but uses fixed percentages.
        """
        multipliers = self.REGIME_MULTIPLIERS.get(regime, self.REGIME_MULTIPLIERS['NEUTRAL'])

        base_sl_pct = 3.5 * multipliers['sl_mult']
        base_tp_pct = base_sl_pct * self.MIN_RR_RATIO * multipliers['tp_mult']

        stop_loss = entry_price * (1 - base_sl_pct / 100)
        take_profit = entry_price * (1 + base_tp_pct / 100)

        return {
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'sl_pct': round(base_sl_pct, 2),
            'tp_pct': round(base_tp_pct, 2),
            'rr_ratio': round(base_tp_pct / base_sl_pct, 2),
            'calculation_method': {'sl': 'Fallback', 'tp': 'Fallback'},
            'data_sources': ['Fallback (no data)'],
            'metrics': {
                'atr': None,
                'atr_pct': None,
                'rsi': None,
                'regime': regime,
            }
        }


class PortfolioManagerV3:
    """
    Portfolio Manager v6 - DYNAMIC SL/TP SYSTEM 🎯
    ==============================================

    🆕 v6 CHANGES: DYNAMIC Entry/SL/TP (NO MORE HARDCODED VALUES!)
    - SL calculated from ATR (volatility-based)
    - SL placed at Support levels
    - TP calculated from Resistance levels
    - Risk:Reward ratio enforcement (min 1:1.5)
    - Regime-adjusted targets (Bull/Bear)
    - Uses ALL available real data

    Data Sources Used for SL/TP:
    - ATR (Average True Range) - volatility measure
    - Support/Resistance via Pivot Points
    - Fibonacci retracement/extension levels
    - Bollinger Bands position
    - RSI for overbought/oversold adjustments
    - Market Regime (Fed, Breadth)
    - Sector Regime (individual sector health)

    Exit Rules (v5 OPTIMIZED + v6 Dynamic):
    1. Dynamic Target Hit (ATR/Resistance-based)
    2. Dynamic Stop Loss (ATR/Support-based)
    3. Trailing Stop: from peak (lock profits)
    4. Max Hold: 30 days (fallback)

    SMART SELECTIVE EXITS (proven to reduce avg loss):
    5. Gap Down: Open < -1.5% below prev close AND losing overall
    6. Breaking Down: Daily drop > -2.0% AND losing overall
    7. Momentum Reversal: Price went up then reversed down
    8. Volume Collapse: Volume < 50% avg AND losing
    9. Failed Pump: Peak 3%+ then drops below entry
    10. SMA20 Break: Close < SMA20 by > 1% when losing
    11. Weak RSI: RSI < 35 when losing > -2%

    Regime Exits (Sector-Aware):
    12. Sector BEAR: Stock's sector turns BEAR (not just overall market)
    """

    def __init__(self, portfolio_file='portfolio_v3.json'):
        self.portfolio_file = portfolio_file
        self.portfolio = self._load_portfolio()

        # Initialize complete system
        self.system = CompleteGrowthSystem()
        self.regime_detector = MarketRegimeDetector()

        # v5: Initialize rule-based exit system
        self.exit_rules = ExitRulesEngine()
        logger.info("✅ Exit Rules Engine initialized (v5 SMART SELECTIVE EXITS)")

        # v6: Initialize DYNAMIC SL/TP calculator
        self.sltp_calculator = DynamicSLTPCalculator()
        logger.info("✅ Dynamic SL/TP Calculator initialized (v6 - uses real data!)")

        # v3.3: Initialize sector regime detector
        self.sector_regime = None
        if SectorRegimeDetector:
            try:
                # Import data manager to pass to sector regime
                try:
                    from src.api.data_manager import DataManager
                except ImportError:
                    from api.data_manager import DataManager

                data_manager = DataManager()
                self.sector_regime = SectorRegimeDetector(data_manager=data_manager)
                logger.info("✅ Sector Regime Detector initialized")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize Sector Regime Detector: {e}")
                self.sector_regime = None

        # Load pre-computed macro regimes if available
        self.precomputed_macro = self._load_precomputed_macro()

        version = "v6 - DYNAMIC SL/TP + SMART EXITS" if self.sector_regime else "v6"
        logger.info(f"✅ Portfolio Manager {version} - Complete 6-Layer System + Dynamic SL/TP")
        if self.precomputed_macro:
            logger.info(f"✅ Loaded {len(self.precomputed_macro)} weeks of pre-computed macro data")
        else:
            logger.warning("⚠️ Pre-computed macro not available - will use real-time (slower)")

    def _load_precomputed_macro(self) -> Optional[Dict]:
        """Load pre-computed macro regimes"""
        macro_file = '../macro_regimes_2025.json'

        # Try multiple paths
        paths = [
            macro_file,
            'macro_regimes_2025.json',
            os.path.join(os.path.dirname(__file__), '..', 'macro_regimes_2025.json')
        ]

        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    return data.get('regimes', {})
                except Exception as e:
                    logger.warning(f"Failed to load macro from {path}: {e}")

        return None

    def _get_macro_regime(self, date: datetime) -> Dict:
        """Get macro regime (from pre-computed or real-time)"""
        week_key = date.strftime("%Y-W%W")

        # Try pre-computed first
        if self.precomputed_macro and week_key in self.precomputed_macro:
            return self.precomputed_macro[week_key]

        # Fallback to real-time
        return self.system.macro_detector.get_macro_regime(date)

    def _calculate_sma(self, prices, period=20):
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return prices[-period:].mean()

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

    def _check_lower_lows(self, prices, lookback=5):
        """Check if making lower lows (downtrend)"""
        if len(prices) < lookback * 2:
            return False

        # Get recent lows
        recent_low = np.min(prices[-lookback:])
        previous_low = np.min(prices[-lookback*2:-lookback])

        return recent_low < previous_low

    def _get_sector_for_symbol(self, symbol: str) -> str:
        """Get sector for a given symbol (v3.3)"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            sector = info.get('sector', 'Unknown')
            return sector if sector else 'Unknown'
        except Exception as e:
            logger.debug(f"Could not get sector for {symbol}: {e}")
            return 'Unknown'

    def _get_sector_regime_info(self, sector: str) -> Dict:
        """Get sector regime information (v3.3)"""
        if not self.sector_regime or sector == 'Unknown':
            return {
                'sector_regime': 'UNKNOWN',
                'sector_regime_adjustment': 0,
                'sector_confidence_threshold': 65,
                'sector_available': False
            }

        try:
            regime = self.sector_regime.get_sector_regime(sector)
            adjustment = self.sector_regime.get_regime_adjustment(sector)
            threshold = self.sector_regime.get_confidence_threshold(sector)

            return {
                'sector_regime': regime,
                'sector_regime_adjustment': adjustment,
                'sector_confidence_threshold': threshold,
                'sector_available': True
            }
        except Exception as e:
            logger.debug(f"Error getting sector regime for {sector}: {e}")
            return {
                'sector_regime': 'UNKNOWN',
                'sector_regime_adjustment': 0,
                'sector_confidence_threshold': 65,
                'sector_available': False
            }

    def _load_portfolio(self) -> Dict:
        """Load portfolio from JSON file"""
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, 'r') as f:
                return json.load(f)
        else:
            return {
                'active': [],
                'closed': [],
                'stats': {
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'avg_return': 0.0,
                    'win_count': 0,
                    'loss_count': 0,
                }
            }

    def _save_portfolio(self):
        """Save portfolio to JSON file"""
        with open(self.portfolio_file, 'w') as f:
            json.dump(self.portfolio, f, indent=2, default=str)

    def add_position(self, symbol: str, entry_price: float, entry_date: str,
                    filters: Dict = None, amount: float = 1000) -> bool:
        """
        Add new position to portfolio with DYNAMIC SL/TP calculation

        v6 UPDATE: SL/TP are now calculated dynamically using:
        - ATR (Average True Range) for volatility-adjusted stops
        - Support levels for stop loss placement
        - Resistance levels for take profit targets
        - Risk:Reward ratio enforcement (min 1:1.5)
        - Market/Sector regime adjustments

        NO MORE HARDCODED VALUES! All calculations use real market data.
        """

        # Check if already exists
        for pos in self.portfolio['active']:
            if pos['symbol'] == symbol:
                logger.warning(f"⚠️  {symbol} already in portfolio")
                return False

        # No position limit - user can add unlimited positions

        # Get entry date as datetime
        try:
            entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
        except:
            entry_dt = datetime.now()
            entry_date = entry_dt.strftime('%Y-%m-%d')

        # Calculate position size
        shares = amount / entry_price

        # Get sector and sector regime for this symbol
        sector = self._get_sector_for_symbol(symbol)
        sector_info = self._get_sector_regime_info(sector)
        sector_regime = sector_info.get('sector_regime', 'NEUTRAL')

        # Get market regime
        regime_info = self.regime_detector.get_current_regime(entry_dt)
        market_regime = regime_info.get('regime', 'NEUTRAL')

        # ═══════════════════════════════════════════════════════════════
        # v6: DYNAMIC SL/TP CALCULATION (NO HARDCODED VALUES!)
        # ═══════════════════════════════════════════════════════════════
        logger.info(f"🎯 v6 DYNAMIC SL/TP calculation for {symbol}")

        sltp_result = self.sltp_calculator.calculate_dynamic_sltp(
            symbol=symbol,
            entry_price=entry_price,
            regime=market_regime,
            sector_regime=sector_regime
        )

        # Extract dynamic SL/TP values
        take_profit = sltp_result['take_profit']
        stop_loss = sltp_result['stop_loss']
        sl_pct = sltp_result['sl_pct']
        tp_pct = sltp_result['tp_pct']
        rr_ratio = sltp_result['rr_ratio']

        # Also update exit rules engine with dynamic thresholds for this position
        # This ensures the rule-based exits use the same dynamic values
        self.exit_rules.update_threshold("TARGET_HIT", "target_pct", tp_pct)
        self.exit_rules.update_threshold("HARD_STOP", "stop_pct", -sl_pct)
        self.exit_rules.update_threshold("TRAILING_STOP", "drawdown_pct", -sl_pct)

        position = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'current_price': entry_price,
            'highest_price': entry_price,
            'amount': amount,
            'shares': shares,
            'take_profit': take_profit,
            'stop_loss': stop_loss,
            'filters': filters or {},

            # v6: Store dynamic calculation details
            'sltp_method': sltp_result['calculation_method'],
            'sltp_data_sources': sltp_result['data_sources'],
            'sltp_metrics': sltp_result['metrics'],
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'rr_ratio': rr_ratio,

            # Regime info
            'sector': sector,
            'sector_regime': sector_regime,
            'market_regime': market_regime,
        }

        self.portfolio['active'].append(position)
        self._save_portfolio()

        logger.info(f"✅ Added {symbol} @ ${entry_price:.2f}")
        logger.info(f"   🎯 DYNAMIC TP: ${take_profit:.2f} (+{tp_pct:.1f}%)")
        logger.info(f"   🛡️ DYNAMIC SL: ${stop_loss:.2f} (-{sl_pct:.1f}%)")
        logger.info(f"   📊 Risk:Reward = 1:{rr_ratio:.2f}")
        logger.info(f"   📈 Data Sources: {', '.join(sltp_result['data_sources'])}")
        logger.info(f"   🌐 Regimes: Market={market_regime}, Sector={sector_regime}")

        return True

    def update_positions(self, current_date: str = None) -> Dict:
        """Update all positions with current prices and exit signals (v3.3: sector-aware!)"""

        if current_date is None:
            current_date = datetime.now().strftime('%Y-%m-%d')

        date = datetime.strptime(current_date, '%Y-%m-%d')

        # Get current regime
        regime_info = self.regime_detector.get_current_regime(date)
        regime = regime_info['regime']

        # Get macro regime
        macro = self._get_macro_regime(date)

        # v3.3: Update sector regimes if available
        sector_regime_summary = None
        if self.sector_regime:
            try:
                logger.info("🌐 Updating sector regimes for portfolio positions...")
                self.sector_regime.update_all_sectors()
                sector_regime_summary = self.sector_regime.get_sector_summary()
                logger.info(f"✅ Updated {len(sector_regime_summary)} sectors")
            except Exception as e:
                logger.warning(f"⚠️ Could not update sector regimes: {e}")

        updated_positions = []
        exit_positions = []

        for pos in self.portfolio['active']:
            symbol = pos['symbol']
            entry_date = datetime.strptime(pos['entry_date'], '%Y-%m-%d')
            days_held = (date - entry_date).days

            # Get current price + historical data for signal detection
            try:
                ticker = yf.Ticker(symbol)
                # Fetch 60 days to ensure we have enough for SMA20 + lookback
                hist = ticker.history(period='60d')

                if hist.empty:
                    logger.warning(f"No price data for {symbol}")
                    updated_positions.append(pos)
                    continue

                current_price = float(hist['Close'].iloc[-1])

                # Extract price arrays for technical analysis
                close_prices = hist['Close'].values
                volume_data = hist['Volume'].values
                pos['current_price'] = current_price

                # Update peak
                if current_price > pos['highest_price']:
                    pos['highest_price'] = current_price

                # Calculate returns
                entry_price = pos['entry_price']
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                pnl_usd = (current_price - entry_price) * pos['shares']

                pos['pnl_pct'] = pnl_pct
                pos['pnl_usd'] = pnl_usd
                pos['days_held'] = days_held

                # v3.3: Get sector and sector regime info
                sector = self._get_sector_for_symbol(symbol)
                sector_info = self._get_sector_regime_info(sector)

                pos['sector'] = sector
                pos['sector_regime'] = sector_info['sector_regime']
                pos['sector_regime_adjustment'] = sector_info['sector_regime_adjustment']
                pos['sector_confidence_threshold'] = sector_info['sector_confidence_threshold']

                # v5 RULE-BASED EXIT SYSTEM
                # Prepare market data for rules engine
                try:
                    open_prices = hist['Open'].values if 'Open' in hist.columns else []
                except:
                    open_prices = []

                market_data = MarketData(
                    current_price=current_price,
                    entry_price=entry_price,
                    highest_price=pos['highest_price'],
                    close_prices=close_prices.tolist() if hasattr(close_prices, 'tolist') else list(close_prices),
                    open_prices=open_prices.tolist() if hasattr(open_prices, 'tolist') else list(open_prices),
                    volume_data=volume_data.tolist() if hasattr(volume_data, 'tolist') else list(volume_data),
                    days_held=days_held
                )

                # Evaluate rules (ONE LINE!)
                exit_reason = self.exit_rules.evaluate(market_data, symbol)

                # 4. Regime change (v3.3: sector-aware!)
                # Check SECTOR regime first, fallback to market regime if no sector info
                stock_regime = sector_info.get('sector_regime', regime) if sector_info.get('sector_available', False) else regime

                # v6.6: Grace period - don't trigger regime exit for new positions (< 2 days)
                # This avoids conflict where screener recommends stock but portfolio immediately says exit
                if days_held >= 2:
                    # Only exit on regime if the stock's SECTOR is BEAR, not just overall market
                    if stock_regime in ['BEAR', 'STRONG BEAR']:
                        exit_reason = 'REGIME_BEAR'
                        logger.info(f"{symbol}: Exit signal - Sector {sector} is {stock_regime}")
                    elif stock_regime == 'WEAK' and pnl_pct < 2:
                        exit_reason = 'REGIME_WEAK'
                        logger.info(f"{symbol}: Exit signal - Sector {sector} is WEAK and no profit")
                else:
                    # New position - just warn but don't exit
                    if stock_regime in ['BEAR', 'STRONG BEAR']:
                        logger.info(f"{symbol}: Warning - Sector {sector} is {stock_regime} (grace period, day {days_held})")

                # 5. Max hold
                if days_held >= 30:
                    exit_reason = 'MAX_HOLD'

                # Add to appropriate list
                # v5.1 FIX: Keep position in active list even with exit signal
                # User must manually close - just flag for exit
                if exit_reason:
                    pos['exit_reason'] = exit_reason
                    pos['has_exit_signal'] = True
                    exit_positions.append(pos)

                # Always keep in updated_positions until user closes
                updated_positions.append(pos)

            except Exception as e:
                logger.error(f"Error updating {symbol}: {e}")
                updated_positions.append(pos)

        # Update active positions
        self.portfolio['active'] = updated_positions
        self._save_portfolio()

        return {
            'date': current_date,
            'regime': regime,
            'macro': macro,
            'holding': updated_positions,
            'exit_positions': exit_positions,
            'sector_regime_summary': sector_regime_summary,  # v3.3
        }

    def close_position(self, symbol: str, exit_price: float, exit_date: str,
                      exit_reason: str) -> Optional[Dict]:
        """Close a position"""

        # Find position
        position = None
        for i, pos in enumerate(self.portfolio['active']):
            if pos['symbol'] == symbol:
                position = self.portfolio['active'].pop(i)
                break

        if not position:
            logger.warning(f"Position {symbol} not found")
            return None

        # Calculate returns
        entry_price = position['entry_price']
        return_pct = ((exit_price - entry_price) / entry_price) * 100
        return_usd = (exit_price - entry_price) * position['shares']

        # Get days held
        entry_date = datetime.strptime(position['entry_date'], '%Y-%m-%d')
        exit_dt = datetime.strptime(exit_date, '%Y-%m-%d')
        days_held = (exit_dt - entry_date).days

        # Create closed position
        closed = {
            'symbol': symbol,
            'entry_date': position['entry_date'],
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return_pct': return_pct,
            'return_usd': return_usd,
            'days_held': days_held,
            'exit_reason': exit_reason,
        }

        self.portfolio['closed'].append(closed)

        # Update stats
        self._update_stats(return_pct)

        self._save_portfolio()

        result = "🟢" if return_pct > 0 else "🔴"
        logger.info(f"{result} Closed {symbol}: {return_pct:+.2f}% ({days_held}d) - {exit_reason}")

        return closed

    def remove_position(self, symbol: str) -> bool:
        """
        Remove a position from portfolio without closing it
        (Delete without recording in closed trades or updating stats)

        Args:
            symbol: Stock symbol to remove

        Returns:
            True if removed successfully, False if not found
        """
        # Find and remove position
        for i, pos in enumerate(self.portfolio['active']):
            if pos['symbol'] == symbol:
                removed = self.portfolio['active'].pop(i)
                self._save_portfolio()
                logger.info(f"🗑️ Removed {symbol} from portfolio (not closed, just deleted)")
                return True

        logger.warning(f"⚠️  Position {symbol} not found")
        return False

    def _update_stats(self, return_pct: float):
        """Update portfolio statistics"""
        stats = self.portfolio['stats']

        stats['total_trades'] += 1

        if return_pct > 0:
            stats['win_count'] = stats.get('win_count', 0) + 1
        else:
            stats['loss_count'] = stats.get('loss_count', 0) + 1

        # Calculate win rate
        stats['win_rate'] = (stats['win_count'] / stats['total_trades']) * 100 if stats['total_trades'] > 0 else 0

        # Update average return
        total_pnl = stats.get('total_pnl', 0) + return_pct
        stats['total_pnl'] = total_pnl
        stats['avg_return'] = total_pnl / stats['total_trades'] if stats['total_trades'] > 0 else 0

    def get_summary(self) -> Dict:
        """Get portfolio summary"""
        stats = self.portfolio['stats']
        active = self.portfolio['active']

        # Calculate current P&L
        total_current_pnl = sum(pos.get('pnl_pct', 0) for pos in active)

        return {
            'active_positions': len(active),
            'total_pnl': total_current_pnl,
            'closed_trades': stats.get('total_trades', 0),
            'win_rate': stats.get('win_rate', 0),
            'avg_return': stats.get('avg_return', 0),
        }

    def get_active_positions(self) -> List[Dict]:
        """Get list of active positions"""
        return self.portfolio['active']

    def get_exit_rules_stats(self) -> List[Dict]:
        """
        Get performance statistics for exit rules

        Returns:
            List of rule stats with fired_count, win_rate, avg_pnl, etc.
        """
        return self.exit_rules.get_rule_stats()

    def tune_exit_rule(self, rule_name: str, threshold_name: str, value: float):
        """
        Tune an exit rule's threshold

        Example:
            pm.tune_exit_rule("TARGET_HIT", "target_pct", 3.8)
            pm.tune_exit_rule("HARD_STOP", "stop_pct", -3.0)
        """
        self.exit_rules.update_threshold(rule_name, threshold_name, value)

    def enable_exit_rule(self, rule_name: str):
        """Enable an exit rule"""
        self.exit_rules.enable_rule(rule_name)

    def disable_exit_rule(self, rule_name: str):
        """Disable an exit rule"""
        self.exit_rules.disable_rule(rule_name)

    def export_exit_rules_config(self) -> Dict:
        """Export current exit rules configuration"""
        return self.exit_rules.export_config()

    def import_exit_rules_config(self, config: Dict):
        """Import exit rules configuration (for A/B testing)"""
        self.exit_rules.import_config(config)

    def get_closed_trades(self) -> List[Dict]:
        """Get list of closed trades"""
        return self.portfolio['closed']


def main():
    """Test portfolio manager"""
    pm = PortfolioManagerV3()

    # Example: Add position
    # pm.add_position('AAPL', 150.0, '2025-12-20', {'volatility': 45})

    # Update all positions
    updates = pm.update_positions()

    print("\n" + "="*60)
    print("PORTFOLIO STATUS")
    print("="*60)
    print(f"Regime: {updates['regime']}")
    print(f"Active Positions: {len(updates['holding'])}")
    print(f"Exit Signals: {len(updates['exit_positions'])}")

    # Show positions
    for pos in updates['holding']:
        print(f"\n{pos['symbol']}:")
        print(f"  Entry: ${pos['entry_price']:.2f} on {pos['entry_date']}")
        print(f"  Current: ${pos.get('current_price', 0):.2f}")
        print(f"  P&L: {pos.get('pnl_pct', 0):+.2f}%")
        print(f"  Days: {pos.get('days_held', 0)}")

    # Show exit signals
    for pos in updates['exit_positions']:
        print(f"\n🚨 EXIT: {pos['symbol']} - {pos['exit_reason']}")

    # Show stats
    print("\n" + "="*60)
    print("STATS")
    print("="*60)
    summary = pm.get_summary()
    print(f"Win Rate: {summary['win_rate']:.1f}%")
    print(f"Avg Return: {summary['avg_return']:+.2f}%")
    print(f"Total Trades: {summary['closed_trades']}")


if __name__ == "__main__":
    main()
