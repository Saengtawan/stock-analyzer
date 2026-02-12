#!/usr/bin/env python3
"""
RAPID PORTFOLIO MANAGER v4.7 - ALPACA INTEGRATION

v4.7 Changes - ALPACA LIVE DATA INTEGRATION:
- Optional broker parameter (AlpacaBroker) for real-time data
- get_current_price(): Auto-uses broker if available, fallback to yfinance
- get_performance_report(): Equity curve, Sharpe ratio, drawdown from Alpaca
- check_all_positions_live(): Batch price fetch (17-76× faster)
- Backwards compatible: Works with or without broker

v4.6 Changes - ATR-BASED DYNAMIC SL/TP:
- SL: 1.5×ATR (clamped 2%-4%) per position
- TP: 3×ATR (clamped 4%-8%) per position
- PDT TP: = SL% (R:R 1:1 minimum for Day 0 sells)
- Trail Activation: 3% (unchanged)
- Trail Lock: 80% (unchanged)
- Each position stores its own sl_pct, tp_pct, atr_pct

Design: Engine = source of truth, Portfolio Manager = display + monitor

Exit Signals:
🔴 CRITICAL - ต้องขายทันที (ถึง SL)
🟠 WARNING - เตรียมขาย
🟡 WATCH - จับตาดู
✅ HOLD - ถือต่อ
🎯 TAKE_PROFIT - ถึงเป้า
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
import yfinance as yf
import pandas as pd
import numpy as np
from loguru import logger

# v6.7: Import unified configuration
try:
    from config.strategy_config import RapidRotationConfig
except ImportError:
    RapidRotationConfig = None

# v6.8: Import SL/TP calculator and PositionManager
try:
    from strategies import SLTPCalculator, SLTPResult
except ImportError:
    SLTPCalculator = None
    SLTPResult = None

try:
    from position_manager import PositionManager as UnifiedPositionManager, Position as UnifiedPosition
except ImportError:
    UnifiedPositionManager = None
    UnifiedPosition = None


class ExitSignal(Enum):
    """Exit signal levels"""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    WATCH = "WATCH"
    HOLD = "HOLD"
    TAKE_PROFIT = "TAKE_PROFIT"


@dataclass
class Position:
    """
    Position in portfolio - v5.0 TRUE SINGLE SOURCE OF TRUTH

    Uses AUTO_TRADING_ENGINE field names (no translation needed):
    - qty (not shares)
    - peak_price (not highest_price)
    - current_sl_price (not current_stop_loss)
    - tp_price (not take_profit)
    - entry_time (not entry_date)
    """
    symbol: str
    entry_time: str             # ISO timestamp (engine format)
    entry_price: float
    qty: int                    # Number of shares (engine: qty)
    current_sl_price: float     # Current SL price (engine: current_sl_price)
    peak_price: float           # Highest price reached (engine: peak_price)
    tp_price: float             # Take profit price (engine: tp_price)
    trailing_active: bool = False
    # Per-position risk parameters
    sl_pct: float = 2.5
    tp_pct: float = 5.0
    atr_pct: float = 0.0
    # Alpaca order IDs
    sl_order_id: str = None
    tp_order_id: str = None
    entry_order_id: str = None
    # Position tracking
    days_held: int = 0
    # Market context (from engine)
    sector: str = None
    trough_price: float = None
    source: str = None
    signal_score: int = 0
    entry_mode: str = None
    entry_regime: str = None
    entry_rsi: float = None
    momentum_5d: float = None

    @property
    def position_value(self) -> float:
        """Total position value"""
        return self.qty * self.entry_price

    @property
    def cost_basis(self) -> float:
        """Alias for position_value (backward compatibility)"""
        return self.position_value


@dataclass
class PositionStatus:
    """Current status of a position"""
    symbol: str
    entry_price: float
    current_price: float
    highest_price: float
    pnl_pct: float
    pnl_usd: float
    days_held: int
    signal: ExitSignal
    reasons: List[str]
    action: str
    new_candidates: List[str]
    # v3.3: Dynamic SL info
    initial_sl: float
    current_sl: float
    sl_updated: bool
    trailing_active: bool
    # v3.4: Dynamic TP info
    initial_tp: float = 0.0
    current_tp: float = 0.0
    tp_updated: bool = False


class RapidPortfolioManager:
    """
    Portfolio Manager v4.7 - ALPACA INTEGRATION

    New in v4.7:
    - Optional broker integration for real-time data (17-76× faster)
    - Performance analytics from Alpaca (equity curve, Sharpe, drawdown)
    - Batch price fetching via get_snapshots()
    - Backwards compatible (works without broker)

    ATR-based per-position SL/TP (same as auto_trading_engine.py v4.6)
    - SL: 1.5×ATR (clamped 2%-4%) per position
    - TP: 3×ATR (clamped 4%-8%) per position
    - Trailing: +3% activation, lock 80% of gains
    - Max Hold: 5 calendar days

    Usage:
        # With Alpaca (recommended):
        from engine.brokers import AlpacaBroker
        broker = AlpacaBroker(paper=True)
        manager = RapidPortfolioManager(broker=broker)

        # Without broker (fallback to yfinance):
        manager = RapidPortfolioManager()
    """

    # Use absolute path to project root for portfolio file
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # v6.19: Use active_positions.json (Auto Trading Engine state file) as single source of truth
    PORTFOLIO_FILE = os.path.join(PROJECT_ROOT, "data", "active_positions.json")

    # v4.6: ATR-based SL/TP (fallback defaults)
    SL_ATR_MULTIPLIER = 1.5      # SL = 1.5 × ATR
    SL_MIN_PCT = 2.0             # Minimum SL%
    SL_MAX_PCT = 2.5             # Maximum SL% (user requested tighter control)
    TP_ATR_MULTIPLIER = 3.0      # TP = 3 × ATR
    TP_MIN_PCT = 4.0             # Minimum TP%
    TP_MAX_PCT = 8.0             # Maximum TP%
    STOP_LOSS_PCT = 2.5          # Fallback fixed SL%
    TAKE_PROFIT_PCT = 5.0        # Fallback fixed TP%
    TRAIL_ACTIVATION_PCT = 3.0   # Start trailing at +3% gain
    TRAIL_PERCENT = 80           # Lock 80% of peak gains
    MAX_HOLD_DAYS = 5            # Max hold days before force exit

    def __init__(self, portfolio_file: str = None, broker=None, config: 'RapidRotationConfig' = None):
        """
        Initialize Portfolio Manager.

        Args:
            portfolio_file: Path to portfolio JSON file
            broker: Optional BrokerInterface (e.g., AlpacaBroker) for live data
                   If provided, will use real-time prices from broker instead of yfinance
            config: Optional RapidRotationConfig for strategy parameters (v6.7)
                   If None, uses class-level defaults or loads from trading.yaml
        """
        self.portfolio_file = portfolio_file or self.PORTFOLIO_FILE
        self.broker = broker  # v4.7: Optional broker for live data

        # v6.7: Load configuration
        if config is None and RapidRotationConfig is not None:
            # Try to load from default YAML
            config_path = os.path.join(self.PROJECT_ROOT, 'config', 'trading.yaml')
            if os.path.exists(config_path):
                try:
                    config = RapidRotationConfig.from_yaml(config_path)
                except Exception:
                    pass  # Fall back to class-level constants

        # Set instance variables from config or defaults
        if config:
            self.sl_atr_multiplier = config.atr_sl_multiplier
            self.sl_min_pct = config.min_sl_pct
            self.sl_max_pct = config.max_sl_pct
            self.tp_atr_multiplier = config.atr_tp_multiplier
            self.tp_min_pct = config.min_tp_pct
            self.tp_max_pct = config.max_tp_pct
            self.stop_loss_pct = config.default_sl_pct
            self.take_profit_pct = config.default_tp_pct
            self.trail_activation_pct = config.trail_activation_pct
            self.trail_percent = config.trail_lock_pct
            self.max_hold_days = config.max_hold_days
        else:
            # Use class-level defaults for backward compatibility
            self.sl_atr_multiplier = RapidPortfolioManager.SL_ATR_MULTIPLIER
            self.sl_min_pct = RapidPortfolioManager.SL_MIN_PCT
            self.sl_max_pct = RapidPortfolioManager.SL_MAX_PCT
            self.tp_atr_multiplier = RapidPortfolioManager.TP_ATR_MULTIPLIER
            self.tp_min_pct = RapidPortfolioManager.TP_MIN_PCT
            self.tp_max_pct = RapidPortfolioManager.TP_MAX_PCT
            self.stop_loss_pct = RapidPortfolioManager.STOP_LOSS_PCT
            self.take_profit_pct = RapidPortfolioManager.TAKE_PROFIT_PCT
            self.trail_activation_pct = RapidPortfolioManager.TRAIL_ACTIVATION_PCT
            self.trail_percent = RapidPortfolioManager.TRAIL_PERCENT
            self.max_hold_days = RapidPortfolioManager.MAX_HOLD_DAYS

        # v6.8: Initialize SL/TP calculator
        if SLTPCalculator is not None:
            # Pass config if available, calculator will use its parameters
            self.sltp_calculator = SLTPCalculator(config=config if config else None)
        else:
            self.sltp_calculator = None

        # v4.10: Use legacy dict-based approach for full auto_trading_engine compatibility
        # UnifiedPositionManager uses incompatible field names, so we use legacy mode
        # which now has full field mapping support (see load_portfolio v4.10)
        self._position_manager = None
        self._positions_dict: Dict[str, Position] = {}
        self.load_portfolio()

    @property
    def positions(self) -> Dict[str, Position]:
        """
        Get positions dict (v6.8: delegates to PositionManager if available)

        Returns unified Position objects with backward compatibility:
        - pos.shares → pos.qty (with property alias)
        - pos.initial_stop_loss → pos.initial_sl (with property alias)
        - pos.current_stop_loss → pos.current_sl (with property alias)
        - pos.initial_take_profit → pos.initial_tp (with property alias)
        """
        if self._position_manager is not None:
            return self._position_manager.positions
        else:
            return self._positions_dict  # Fallback to legacy dict

    @positions.setter
    def positions(self, value: Dict[str, Position]):
        """Set positions (backward compatibility)"""
        if self._position_manager is not None:
            # When setting, update the manager's positions
            self._position_manager.positions = value
        else:
            self._positions_dict = value

    def load_portfolio(self) -> None:
        """
        Load portfolio from file (v5.0: TRUE single source of truth)

        No translation needed - Position class uses same field names as engine:
        - qty, current_sl_price, tp_price, peak_price, entry_time
        """
        if os.path.exists(self.portfolio_file):
            try:
                with open(self.portfolio_file, 'r') as f:
                    data = json.load(f)
                    for symbol, pos_data in data.get('positions', {}).items():
                        # v5.0: Direct load - no field mapping needed!
                        # Position class now uses engine field names

                        # Set defaults for missing optional fields
                        if 'trailing_active' not in pos_data:
                            pos_data['trailing_active'] = False
                        if 'days_held' not in pos_data:
                            pos_data['days_held'] = 0
                        if 'sl_pct' not in pos_data:
                            pos_data['sl_pct'] = 4.0
                        if 'tp_pct' not in pos_data:
                            pos_data['tp_pct'] = 8.0
                        if 'atr_pct' not in pos_data:
                            pos_data['atr_pct'] = 3.0

                        # Create Position directly - no translation!
                        self.positions[symbol] = Position(**pos_data)

            except Exception as e:
                logger.error(f"Error loading portfolio: {e}")
                import traceback
                traceback.print_exc()

    def save_portfolio(self) -> None:
        """
        Save portfolio to file (v5.0: TRUE single source of truth)

        No translation needed - Position class uses same field names as engine.
        Direct save using asdict().

        Format: Auto Trading Engine standard (qty, current_sl_price, tp_price, peak_price, entry_time)
        """
        # v5.0: Direct save - no field mapping needed!
        positions_data = {}

        for symbol, pos in self.positions.items():
            # Convert Position to dict - no translation needed!
            pos_dict = asdict(pos)
            positions_data[symbol] = pos_dict

        data = {
            'positions': positions_data,
            'last_updated': datetime.now().isoformat()
        }

        with open(self.portfolio_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def add_position(self, symbol: str, shares: int, entry_price: float,
                     stop_loss: float = None, take_profit: float = None,
                     sl_pct: float = None, tp_pct: float = None,
                     atr_pct: float = None) -> None:
        """
        Add new position with ATR-based SL/TP (v4.6, v6.8 uses SLTPCalculator)

        If sl_pct/tp_pct provided (from engine), use those.
        Otherwise calculate ATR-based or use fallback fixed values.
        """
        # v6.8: Use SLTPCalculator if available, fallback to manual calculation
        if self.sltp_calculator is not None and (stop_loss is None or take_profit is None):
            # Use provided percentages or defaults
            calc_sl_pct = sl_pct if sl_pct is not None else self.stop_loss_pct
            calc_tp_pct = tp_pct if tp_pct is not None else self.take_profit_pct

            # Calculate using SLTPCalculator
            result = self.sltp_calculator.calculate_simple(
                entry_price=entry_price,
                sl_pct=calc_sl_pct,
                tp_pct=calc_tp_pct
            )

            # Use calculated values if not provided
            if stop_loss is None:
                stop_loss = result.stop_loss
            if take_profit is None:
                take_profit = result.take_profit

            pos_sl_pct = result.sl_pct
            pos_tp_pct = result.tp_pct
        else:
            # v4.6: Fallback to manual calculation (backward compatible)
            pos_sl_pct = sl_pct or self.stop_loss_pct
            pos_tp_pct = tp_pct or self.take_profit_pct

            if stop_loss is None:
                stop_loss = round(entry_price * (1 - pos_sl_pct / 100), 2)
            if take_profit is None:
                take_profit = round(entry_price * (1 + pos_tp_pct / 100), 2)

        pos_atr_pct = atr_pct or 0.0

        # v6.8: Use UnifiedPosition if available (new field names), fallback to legacy Position
        PositionClass = UnifiedPosition if UnifiedPosition is not None else Position

        if UnifiedPosition is not None:
            # Use new field names for unified Position
            pos = PositionClass(
                symbol=symbol,
                entry_date=datetime.now().strftime('%Y-%m-%d'),
                entry_price=entry_price,
                qty=shares,  # New name
                initial_sl=stop_loss,  # New name
                current_sl=stop_loss,  # New name
                take_profit=take_profit,
                cost_basis=shares * entry_price,
                highest_price=entry_price,
                trailing_active=False,
                initial_tp=take_profit,  # New name
                sl_pct=pos_sl_pct,
                tp_pct=pos_tp_pct,
                atr_pct=pos_atr_pct
            )
        else:
            # Legacy Position with old field names
            pos = PositionClass(
                symbol=symbol,
                entry_date=datetime.now().strftime('%Y-%m-%d'),
                entry_price=entry_price,
                shares=shares,
                initial_stop_loss=stop_loss,
                current_stop_loss=stop_loss,
                take_profit=take_profit,
                cost_basis=shares * entry_price,
                highest_price=entry_price,
                trailing_active=False,
                initial_take_profit=take_profit,
                sl_pct=pos_sl_pct,
                tp_pct=pos_tp_pct,
                atr_pct=pos_atr_pct
            )

        self.positions[symbol] = pos
        self.save_portfolio()

        print(f"✅ Added: {symbol} x{shares} @ ${entry_price:.2f}")
        print(f"   SL: ${stop_loss:.2f} (-{pos_sl_pct:.1f}%)")
        print(f"   TP: ${take_profit:.2f} (+{pos_tp_pct:.1f}%)")
        if pos_atr_pct > 0:
            print(f"   ATR: {pos_atr_pct:.1f}% (SL={self.sl_atr_multiplier}x, TP={self.tp_atr_multiplier}x)")
        print(f"   Trailing: +{self.trail_activation_pct}% → lock {self.trail_percent}%")

    def remove_position(self, symbol: str) -> Optional[Position]:
        """Remove position"""
        if symbol in self.positions:
            pos = self.positions.pop(symbol)
            self.save_portfolio()
            return pos
        return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price (v4.9: uses hybrid real-time fetcher).

        Priority:
        1. Broker (real-time) if available
        2. Real-time price fetcher (intraday during market hours)
        3. yfinance as last resort

        v4.9: Replaced yfinance workaround with proper real-time fetcher
        """
        # Try broker first (real-time)
        if self.broker:
            try:
                quote = self.broker.get_snapshot(symbol)
                if quote and quote.last > 0:
                    logger.debug(f"{symbol}: Price ${quote.last:.2f} from broker (real-time)")
                    return quote.last
            except Exception as e:
                logger.warning(f"Broker price fetch failed for {symbol}, falling back: {e}")

        # v4.9: Use real-time price fetcher (proper solution)
        try:
            from data_sources.realtime_price import get_current_price as get_realtime_price

            price, is_realtime, source = get_realtime_price(symbol, fallback_daily_data=None)

            if price > 0:
                logger.debug(f"{symbol}: Price ${price:.2f} from {source} (realtime: {is_realtime})")
                return price

        except Exception as e:
            logger.warning(f"Real-time price fetch failed for {symbol}: {e}")

        # Last resort: direct yfinance (legacy fallback)
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='2d')
            if len(data) > 0:
                latest_price = data['Close'].iloc[-1]
                logger.debug(f"{symbol}: Price ${latest_price:.2f} from yfinance fallback")
                return latest_price
        except Exception as e:
            logger.error(f"All price fetch methods failed for {symbol}: {e}")

        return None

    def get_stock_data(self, symbol: str, days: int = 30) -> Optional[pd.DataFrame]:
        """Get historical data for dynamic calculations"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=f'{days}d')
            if len(data) >= 10:
                data.columns = [c.lower() for c in data.columns]
                return data
        except:
            pass
        return None

    def calculate_dynamic_sl(self, symbol: str, current_price: float,
                             highest_price: float, entry_price: float) -> Dict:
        """
        Calculate dynamic stop loss based on multiple factors

        Returns:
            Dict with:
            - atr_based_sl: SL based on ATR
            - swing_low_sl: SL based on recent swing low
            - ma_based_sl: SL based on EMA
            - recommended_sl: Best SL to use
            - trailing_distance: Distance from high
        """
        data = self.get_stock_data(symbol)
        if data is None or len(data) < 14:
            # Fallback: use 2.5% from highest (v3.6 tight SL)
            fallback_sl = highest_price * 0.975
            return {
                'atr_based_sl': fallback_sl,
                'swing_low_sl': fallback_sl,
                'ma_based_sl': fallback_sl,
                'recommended_sl': fallback_sl,
                'trailing_distance_pct': 2.5,
                'method': 'fallback'
            }

        close = data['close']
        high = data['high']
        low = data['low']

        # 1. ATR-based SL
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / current_price) * 100

        trailing_distance = atr * self.ATR_MULTIPLIER
        atr_based_sl = highest_price - trailing_distance

        # 2. Swing Low based SL (last 5-10 days)
        swing_low_5d = low.iloc[-5:].min()
        swing_low_10d = low.iloc[-10:].min()
        # Use tighter of the two (5d swing low)
        swing_low_sl = swing_low_5d * 0.995  # Slightly below swing low

        # 3. EMA based SL
        ema5 = close.ewm(span=5).mean().iloc[-1]
        ema10 = close.ewm(span=10).mean().iloc[-1]
        # Trail below EMA5 or EMA10 depending on trend strength
        if current_price > ema5:
            ma_based_sl = ema5 * 0.99  # 1% below EMA5
        else:
            ma_based_sl = ema10 * 0.98  # 2% below EMA10

        # 4. Choose best SL (highest = tightest protection)
        all_sls = [atr_based_sl, swing_low_sl, ma_based_sl]
        recommended_sl = max(all_sls)

        # But don't trail tighter than 1.5% from current price
        min_distance = current_price * 0.015
        if current_price - recommended_sl < min_distance:
            recommended_sl = current_price - min_distance

        # Also don't go below entry price if in profit
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        if pnl_pct > 3:
            # If profit > 3%, SL should at least be at breakeven
            recommended_sl = max(recommended_sl, entry_price * 1.005)

        trailing_distance_pct = ((highest_price - recommended_sl) / highest_price) * 100

        # Determine which method gave the highest SL
        if recommended_sl == atr_based_sl:
            method = f'ATR ({atr_pct:.1f}%)'
        elif recommended_sl == swing_low_sl:
            method = f'Swing Low ${swing_low_5d:.2f}'
        else:
            method = f'EMA ({ema5:.2f})'

        return {
            'atr_based_sl': round(atr_based_sl, 2),
            'swing_low_sl': round(swing_low_sl, 2),
            'ma_based_sl': round(ma_based_sl, 2),
            'recommended_sl': round(recommended_sl, 2),
            'trailing_distance_pct': round(trailing_distance_pct, 2),
            'atr_pct': round(atr_pct, 2),
            'method': method
        }

    def calculate_dynamic_tp(self, symbol: str, current_price: float,
                              highest_price: float, entry_price: float) -> Dict:
        """
        Calculate dynamic take profit based on multiple factors (v3.4)

        Returns:
            Dict with:
            - atr_based_tp: TP based on ATR × 3
            - resistance_tp: TP based on resistance level
            - trailing_tp: TP based on trailing high
            - recommended_tp: Best TP to use
            - method: Which method was used
        """
        data = self.get_stock_data(symbol)
        if data is None or len(data) < 20:
            # Fallback: use current TP + 2%
            fallback_tp = highest_price * 1.06
            return {
                'atr_based_tp': fallback_tp,
                'resistance_tp': fallback_tp,
                'trailing_tp': fallback_tp,
                'recommended_tp': fallback_tp,
                'method': 'fallback'
            }

        close = data['close']
        high = data['high']
        low = data['low']

        # Calculate ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # 1. ATR-based TP (ATR × 3 from current price)
        atr_based_tp = current_price + (atr * 3)

        # 2. Resistance-based TP (swing high 20 days)
        swing_high_20d = high.iloc[-20:].max()
        resistance_tp = swing_high_20d * 0.995  # Just below resistance

        # 3. 52-week high as cap
        high_52w = high.max()
        high_52w_tp = high_52w * 0.98

        # 4. Trailing TP (extend target as price rises)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        if pnl_pct > 5:
            # If already up 5%, add ATR × 2 to current price
            trailing_tp = current_price + (atr * 2)
        else:
            trailing_tp = atr_based_tp

        # Choose LOWEST TP = most realistic target
        all_tps = [atr_based_tp, resistance_tp, high_52w_tp, trailing_tp]
        recommended_tp = min(all_tps)

        # But ensure TP is at least 4% above current price
        min_tp = current_price * 1.04
        if recommended_tp < min_tp:
            recommended_tp = min_tp

        # And cap at +15% from entry
        max_tp = entry_price * 1.15
        if recommended_tp > max_tp:
            recommended_tp = max_tp

        # Determine which method gave the TP
        if recommended_tp == atr_based_tp:
            method = f'ATR×3'
        elif recommended_tp == resistance_tp:
            method = f'Resistance ${swing_high_20d:.2f}'
        elif recommended_tp == trailing_tp:
            method = 'Trailing'
        else:
            method = '52wHigh'

        return {
            'atr_based_tp': round(atr_based_tp, 2),
            'resistance_tp': round(resistance_tp, 2),
            'trailing_tp': round(trailing_tp, 2),
            'recommended_tp': round(recommended_tp, 2),
            'method': method
        }

    def handle_realtime_price(self, symbol: str, price: float, data_type: str = 'trade'):
        """
        Handle real-time price updates from AlpacaStreamer (v5.1)

        Called on EVERY price update from WebSocket!
        Updates peak price immediately without waiting for 5-min polling.

        Args:
            symbol: Stock symbol
            price: Current price from stream
            data_type: 'trade' or 'bar'
        """
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        # Update peak immediately if price is higher
        if price > pos.peak_price:
            old_peak = pos.peak_price
            pos.peak_price = price
            logger.info(f"📈 {symbol} peak updated: ${old_peak:.2f} → ${price:.2f} (real-time!)")

            # Trigger trailing stop calculation
            result = self.update_position_sl_tp(symbol, price)

            if result['sl_updated']:
                logger.info(f"🔒 {symbol} trailing SL updated: ${result['new_sl']:.2f} (real-time!)")

        # Also update trough if lower
        if pos.trough_price and price < pos.trough_price:
            pos.trough_price = price

    def update_position_sl_tp(self, symbol: str, current_price: float) -> Dict:
        """
        Update position's SL using simple trailing stop (v4.10: with Alpaca integration)

        Synced with auto_trading_engine.py:
        - SL: Per-position ATR-based (until trailing activates)
        - Trailing: +3% activation, lock 80% of gains
        - TP: Per-position ATR-based (never changes after entry)
        - v4.10: Updates SL order at Alpaca if broker available

        Returns:
            Dict with sl_updated, tp_updated, new_sl, new_tp
        """
        if symbol not in self.positions:
            return {'sl_updated': False, 'tp_updated': False, 'new_sl': 0, 'new_tp': 0}

        pos = self.positions[symbol]
        sl_updated = False
        new_sl = pos.current_sl_price
        old_sl = pos.current_sl_price

        # Update peak price
        peak_updated = False
        if current_price > pos.peak_price:
            pos.peak_price = current_price
            peak_updated = True

        # Calculate P&L from peak
        pnl_pct = ((pos.peak_price - pos.entry_price) / pos.entry_price) * 100

        # v5.0: Simple trailing stop (same as engine)
        if pnl_pct >= self.trail_activation_pct:
            pos.trailing_active = True

            # Trailing SL = entry + (gain × lock_pct)
            gain_from_entry = pos.peak_price - pos.entry_price
            trailing_sl = pos.entry_price + (gain_from_entry * self.trail_percent / 100)

            # SL can only go UP (never reduce protection)
            if trailing_sl > pos.current_sl_price:
                pos.current_sl_price = round(trailing_sl, 2)
                new_sl = pos.current_sl_price
                sl_updated = True

                # v5.0: Update SL order at Alpaca (if broker available and SL order exists)
                if self.broker and pos.sl_order_id and pos.days_held > 0:
                    try:
                        logger.info(f"📈 {symbol} updating SL at Alpaca: ${old_sl:.2f} → ${new_sl:.2f}")

                        # Use broker's modify_stop_loss (cancel + replace)
                        new_order = self.broker.modify_stop_loss(pos.sl_order_id, new_sl)

                        if new_order:
                            pos.sl_order_id = new_order.id
                            logger.info(f"✅ {symbol} SL order updated: {new_order.id}")
                        else:
                            logger.error(f"❌ {symbol} SL update failed - order returned None")

                    except Exception as e:
                        logger.error(f"❌ {symbol} failed to update SL at Alpaca: {e}")
                        # Continue anyway - portfolio file will be updated

        # Save if anything changed
        if sl_updated or peak_updated:
            self.save_portfolio()

            if sl_updated:
                logger.info(f"🔒 {symbol} trailing activated: Peak ${pos.peak_price:.2f} → SL ${new_sl:.2f} (lock {self.trail_percent}%)")

        return {
            'sl_updated': sl_updated,
            'tp_updated': False,  # v5.0: TP never changes
            'new_sl': new_sl,
            'new_tp': pos.tp_price
        }

    def analyze_position(self, symbol: str) -> Optional[PositionStatus]:
        """
        Analyze a position with dynamic SL/TP

        v3.4: Auto-updates both SL and TP when checking
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        current_price = self.get_current_price(symbol)

        if current_price is None:
            return None

        # v3.4: Auto-update SL and TP on check
        update_result = self.update_position_sl_tp(symbol, current_price)
        sl_updated = update_result['sl_updated']
        tp_updated = update_result['tp_updated']

        # Calculate P&L
        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        pnl_usd = (current_price - pos.entry_price) * pos.qty

        # Calculate days held
        try:
            if 'T' in pos.entry_time:
                entry_date = datetime.fromisoformat(pos.entry_time.split('T')[0])
            else:
                entry_date = datetime.strptime(pos.entry_time[:10], '%Y-%m-%d')
        except:
            entry_date = datetime.now()
        days_held = (datetime.now() - entry_date).days

        # Determine exit signal
        signal = ExitSignal.HOLD
        reasons = []
        action = "HOLD"
        new_candidates = []

        # 1. TAKE PROFIT
        if current_price >= pos.tp_price:
            signal = ExitSignal.TAKE_PROFIT
            reasons.append(f"Hit TP ${pos.tp_price:.2f}")
            action = "🎯 SELL - ถึงเป้า!"
            new_candidates = self._get_replacement_candidates(symbol)

        # 2. STOP LOSS (using current dynamic SL)
        elif current_price <= pos.current_sl_price:
            signal = ExitSignal.CRITICAL
            if pos.trailing_active:
                reasons.append(f"Hit Trailing SL ${pos.current_sl_price:.2f}")
                action = "🔴 SELL - Trailing Stop!"
            else:
                reasons.append(f"Hit SL ${pos.current_sl_price:.2f}")
                action = "🔴 SELL NOW!"
            new_candidates = self._get_replacement_candidates(symbol)

        # 3. TIME STOP
        elif days_held >= self.max_hold_days and pnl_pct < 1:
            signal = ExitSignal.WARNING
            reasons.append(f"Held {days_held} days, only +{pnl_pct:.1f}%")
            action = "🟠 SELL - Rotation"
            new_candidates = self._get_replacement_candidates(symbol)

        # 4. WARNING - Close to SL
        elif current_price <= pos.current_sl_price * 1.01:
            signal = ExitSignal.WARNING
            reasons.append(f"Very close to SL ${pos.current_sl_price:.2f}")
            action = "🟠 WATCH CLOSELY"

        # 5. TRAILING ACTIVE - Show info
        elif pos.trailing_active:
            signal = ExitSignal.HOLD
            trail_distance = ((pos.peak_price - pos.current_sl_price) / pos.peak_price) * 100
            reasons.append(f"Trailing active ({trail_distance:.1f}% from high)")
            action = f"✅ HOLD - Trailing SL ${pos.current_sl_price:.2f}"

        # 6. HOLD
        else:
            signal = ExitSignal.HOLD
            if pnl_pct > 0:
                reasons.append(f"Profit +{pnl_pct:.1f}%")
                action = "✅ HOLD"
            else:
                reasons.append("Within tolerance")
                action = "✅ HOLD"

        # Add SL/TP update info
        if sl_updated:
            reasons.append(f"📈 SL raised to ${pos.current_sl_price:.2f}")
        if tp_updated:
            reasons.append(f"🎯 TP raised to ${pos.tp_price:.2f}")

        return PositionStatus(
            symbol=symbol,
            entry_price=pos.entry_price,
            current_price=round(current_price, 2),
            highest_price=round(pos.peak_price, 2),
            pnl_pct=round(pnl_pct, 2),
            pnl_usd=round(pnl_usd, 2),
            days_held=days_held,
            signal=signal,
            reasons=reasons,
            action=action,
            new_candidates=new_candidates,
            initial_sl=round(pos.entry_price * 0.96, 2),  # Calculate from entry
            current_sl=round(pos.current_sl_price, 2),
            sl_updated=sl_updated,
            trailing_active=pos.trailing_active,
            # v5.0: TP info
            initial_tp=round(pos.entry_price * 1.08, 2),  # Calculate from entry
            current_tp=round(pos.tp_price, 2),
            tp_updated=tp_updated
        )

    def _get_replacement_candidates(self, exclude_symbol: str) -> List[str]:
        """Get candidates to replace sold position"""
        try:
            from screeners.rapid_rotation_screener import RapidRotationScreener
            screener = RapidRotationScreener()
            screener.load_data()

            existing = list(self.positions.keys())
            signals = screener.get_portfolio_signals(
                max_positions=4,
                existing_positions=existing + [exclude_symbol]
            )

            return [s.symbol for s in signals[:3]]
        except:
            return []

    def check_all_positions(self) -> List[PositionStatus]:
        """
        Check all positions and return statuses

        v3.3: Auto-updates SL for all positions
        """
        statuses = []
        for symbol in self.positions:
            status = self.analyze_position(symbol)
            if status:
                statuses.append(status)

        # Sort by urgency
        priority = {
            ExitSignal.CRITICAL: 0,
            ExitSignal.WARNING: 1,
            ExitSignal.WATCH: 2,
            ExitSignal.TAKE_PROFIT: 3,
            ExitSignal.HOLD: 4
        }
        statuses.sort(key=lambda x: priority.get(x.signal, 5))

        return statuses

    def get_portfolio_summary(self) -> Dict:
        """Get overall portfolio summary"""
        if not self.positions:
            return {'status': 'empty', 'positions': 0}

        total_cost = sum(p.cost_basis for p in self.positions.values())
        current_values = []
        pnls = []

        for symbol, pos in self.positions.items():
            price = self.get_current_price(symbol)
            if price:
                current_values.append(price * pos.qty)
                pnls.append((price - pos.entry_price) / pos.entry_price * 100)

        total_value = sum(current_values) if current_values else 0
        total_pnl_pct = ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0
        total_pnl_usd = total_value - total_cost

        # Count trailing active
        trailing_count = sum(1 for p in self.positions.values() if p.trailing_active)

        return {
            'positions': len(self.positions),
            'total_cost': round(total_cost, 2),
            'total_value': round(total_value, 2),
            'total_pnl_usd': round(total_pnl_usd, 2),
            'total_pnl_pct': round(total_pnl_pct, 2),
            'avg_pnl_pct': round(sum(pnls) / len(pnls), 2) if pnls else 0,
            'trailing_active': trailing_count,
        }

    def get_performance_report(self, period: str = '1M') -> Dict:
        """
        Get comprehensive performance report from Alpaca (v4.7).

        Requires self.broker to be set (AlpacaBroker instance).
        Falls back to local calculation if broker not available.

        Args:
            period: Time period ('1D', '1W', '1M', '3M', '1A', 'all')

        Returns:
            Dict with:
            - equity_curve: List of equity values
            - timestamps: List of dates
            - metrics: Performance metrics (return, drawdown, Sharpe, etc)
            - summary: Human-readable summary
        """
        if not self.broker:
            logger.warning("No broker configured - using local portfolio summary")
            return {
                'equity_curve': [],
                'timestamps': [],
                'metrics': {},
                'summary': self.get_portfolio_summary(),
                'data_source': 'local_json'
            }

        try:
            # Get portfolio history from Alpaca
            history = self.broker.get_portfolio_history(period=period, timeframe='1D')

            # Calculate performance metrics
            metrics = self.broker.calculate_performance_metrics(history)

            # Convert timestamps to dates
            from datetime import datetime
            timestamps = [
                datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                for ts in history['timestamp']
            ]

            return {
                'equity_curve': history['equity'],
                'timestamps': timestamps,
                'metrics': metrics,
                'summary': {
                    'period': period,
                    'start_equity': history['equity'][0] if history['equity'] else 0,
                    'end_equity': history['equity'][-1] if history['equity'] else 0,
                    'total_return_pct': metrics['total_return_pct'],
                    'total_return_usd': metrics['total_return_usd'],
                    'max_drawdown_pct': metrics['max_drawdown_pct'],
                    'sharpe_ratio': metrics['sharpe_ratio'],
                    'win_rate': metrics['win_rate'],
                },
                'data_source': 'alpaca'
            }

        except Exception as e:
            logger.error(f"Failed to get Alpaca performance: {e}")
            return {
                'equity_curve': [],
                'timestamps': [],
                'metrics': {},
                'summary': self.get_portfolio_summary(),
                'data_source': 'local_json',
                'error': str(e)
            }

    def check_all_positions_live(self) -> List[PositionStatus]:
        """
        Check all positions using live broker data (v4.7).

        Faster than check_all_positions() because:
        - Uses broker.get_snapshots() for batch price fetch
        - Only 1 API call instead of N calls

        Falls back to check_all_positions() if broker not available.

        Returns:
            List of PositionStatus objects
        """
        if not self.broker or not self.positions:
            return self.check_all_positions()

        try:
            # Batch fetch all prices (fast!)
            symbols = list(self.positions.keys())
            quotes = self.broker.get_snapshots(symbols)

            statuses = []
            for symbol in symbols:
                if symbol not in quotes:
                    # Fallback to individual check
                    status = self.analyze_position(symbol)
                    if status:
                        statuses.append(status)
                    continue

                # Use live quote
                current_price = quotes[symbol].last

                pos = self.positions[symbol]

                # Update SL/TP
                update_result = self.update_position_sl_tp(symbol, current_price)
                sl_updated = update_result['sl_updated']
                tp_updated = update_result['tp_updated']

                # Calculate P&L
                pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
                pnl_usd = (current_price - pos.entry_price) * pos.qty

                # Calculate days held
                try:
                    if 'T' in pos.entry_time:
                        entry_date = datetime.fromisoformat(pos.entry_time.split('T')[0])
                    else:
                        entry_date = datetime.strptime(pos.entry_time[:10], '%Y-%m-%d')
                except:
                    entry_date = datetime.now()
                days_held = (datetime.now() - entry_date).days

                # Determine exit signal (same logic as analyze_position)
                signal = ExitSignal.HOLD
                reasons = []
                action = "HOLD"
                new_candidates = []

                # 1. TAKE PROFIT
                if current_price >= pos.tp_price:
                    signal = ExitSignal.TAKE_PROFIT
                    reasons.append(f"Hit TP ${pos.tp_price:.2f}")
                    action = "🎯 SELL - ถึงเป้า!"
                    new_candidates = self._get_replacement_candidates(symbol)

                # 2. STOP LOSS
                elif current_price <= pos.current_sl_price:
                    signal = ExitSignal.CRITICAL
                    if pos.trailing_active:
                        reasons.append(f"Hit Trailing SL ${pos.current_sl_price:.2f}")
                        action = "🔴 SELL - Trailing Stop!"
                    else:
                        reasons.append(f"Hit SL ${pos.current_sl_price:.2f}")
                        action = "🔴 SELL NOW!"
                    new_candidates = self._get_replacement_candidates(symbol)

                # 3. TIME STOP
                elif days_held >= self.max_hold_days and pnl_pct < 1:
                    signal = ExitSignal.WARNING
                    reasons.append(f"Held {days_held} days, only +{pnl_pct:.1f}%")
                    action = "🟠 SELL - Rotation"
                    new_candidates = self._get_replacement_candidates(symbol)

                # 4. WARNING - Close to SL
                elif current_price <= pos.current_sl_price * 1.01:
                    signal = ExitSignal.WARNING
                    reasons.append(f"Very close to SL ${pos.current_sl_price:.2f}")
                    action = "🟠 WATCH CLOSELY"

                # 5. TRAILING ACTIVE
                elif pos.trailing_active:
                    signal = ExitSignal.HOLD
                    trail_distance = ((pos.peak_price - pos.current_sl_price) / pos.peak_price) * 100
                    reasons.append(f"Trailing active ({trail_distance:.1f}% from high)")
                    action = f"✅ HOLD - Trailing SL ${pos.current_sl_price:.2f}"

                # 6. HOLD
                else:
                    signal = ExitSignal.HOLD
                    if pnl_pct > 0:
                        reasons.append(f"Profit +{pnl_pct:.1f}%")
                        action = "✅ HOLD"
                    else:
                        reasons.append("Within tolerance")
                        action = "✅ HOLD"

                # Add SL/TP update info
                if sl_updated:
                    reasons.append(f"📈 SL raised to ${pos.current_sl_price:.2f}")
                if tp_updated:
                    reasons.append(f"🎯 TP raised to ${pos.tp_price:.2f}")

                status = PositionStatus(
                    symbol=symbol,
                    entry_price=pos.entry_price,
                    current_price=round(current_price, 2),
                    highest_price=round(pos.peak_price, 2),
                    pnl_pct=round(pnl_pct, 2),
                    pnl_usd=round(pnl_usd, 2),
                    days_held=days_held,
                    signal=signal,
                    reasons=reasons,
                    action=action,
                    new_candidates=new_candidates,
                    initial_sl=round(pos.entry_price * 0.96, 2),
                    current_sl=round(pos.current_sl_price, 2),
                    sl_updated=sl_updated,
                    trailing_active=pos.trailing_active,
                    initial_tp=round(pos.entry_price * 1.08, 2),
                    current_tp=round(pos.tp_price, 2),
                    tp_updated=tp_updated
                )

                statuses.append(status)

            # Sort by urgency
            priority = {
                ExitSignal.CRITICAL: 0,
                ExitSignal.WARNING: 1,
                ExitSignal.WATCH: 2,
                ExitSignal.TAKE_PROFIT: 3,
                ExitSignal.HOLD: 4
            }
            statuses.sort(key=lambda x: priority.get(x.signal, 5))

            return statuses

        except Exception as e:
            logger.error(f"Live position check failed, falling back to yfinance: {e}")
            return self.check_all_positions()


def main():
    """Run portfolio check"""
    print("=" * 70)
    print("🚀 RAPID PORTFOLIO MANAGER v4.6 - ATR-BASED SL/TP")
    print("=" * 70)
    print()
    print("v4.6 Features:")
    print("  - SL: 1.5×ATR (clamped 2%-4%) per position")
    print("  - TP: 3×ATR (clamped 4%-8%) per position")
    print("  - Trail: +3% activation, lock 80%")
    print("  - PDT TP = SL% (R:R 1:1 minimum)")
    print()

    manager = RapidPortfolioManager()

    if not manager.positions:
        print("ไม่มี Position ใน Portfolio")
        print()
        print("วิธีเพิ่ม Position:")
        print("  manager.add_position('NVDA', shares=10, entry_price=180.00,")
        print("                       stop_loss=173.70, take_profit=190.80)")
        return

    # Get summary
    summary = manager.get_portfolio_summary()
    print(f"📊 PORTFOLIO SUMMARY")
    print("-" * 50)
    print(f"Positions: {summary['positions']}")
    print(f"Trailing Active: {summary['trailing_active']}")
    print(f"Total Cost: ${summary['total_cost']:,.2f}")
    print(f"Current Value: ${summary['total_value']:,.2f}")
    print(f"Total P&L: ${summary['total_pnl_usd']:+,.2f} ({summary['total_pnl_pct']:+.2f}%)")
    print()

    # Check all positions
    print("📋 POSITION STATUS (SL updates automatically)")
    print("-" * 50)
    print()

    statuses = manager.check_all_positions()

    for status in statuses:
        icon = {
            ExitSignal.CRITICAL: "🔴",
            ExitSignal.WARNING: "🟠",
            ExitSignal.WATCH: "🟡",
            ExitSignal.TAKE_PROFIT: "🎯",
            ExitSignal.HOLD: "✅"
        }.get(status.signal, "⚪")

        print(f"{icon} {status.symbol}")
        print(f"   Entry: ${status.entry_price:.2f} → Current: ${status.current_price:.2f}")
        print(f"   Highest: ${status.highest_price:.2f}")
        print(f"   P&L: {status.pnl_pct:+.2f}% (${status.pnl_usd:+.2f})")
        print(f"   Days Held: {status.days_held}")

        # Show SL info
        if status.trailing_active:
            print(f"   📈 TRAILING ACTIVE")
            print(f"   SL: ${status.initial_sl:.2f} → ${status.current_sl:.2f} (updated)")
        else:
            print(f"   SL: ${status.current_sl:.2f}")

        print(f"   Action: {status.action}")
        if status.reasons:
            print(f"   Reasons: {', '.join(status.reasons)}")
        if status.new_candidates:
            print(f"   💡 Replace with: {', '.join(status.new_candidates)}")
        print()

    # Critical alerts
    criticals = [s for s in statuses if s.signal == ExitSignal.CRITICAL]
    if criticals:
        print("=" * 70)
        print("⚠️  CRITICAL ALERTS - ต้องขายทันที!")
        print("=" * 70)
        for s in criticals:
            print(f"  🔴 {s.symbol}: {s.action}")
            print(f"     Loss: {s.pnl_pct:.2f}%")
            if s.new_candidates:
                print(f"     → Replace with: {', '.join(s.new_candidates)}")
        print()


if __name__ == "__main__":
    main()
