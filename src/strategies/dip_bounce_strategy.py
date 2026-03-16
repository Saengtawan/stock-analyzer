"""
Dip-Bounce Strategy

Buy stocks that have dipped and are showing bounce confirmation.
This is the extracted version of the original Rapid Rotation logic.

Strategy Logic:
- BOUNCE CONFIRMATION: Wait for recovery after dip (not falling knife)
- Dynamic SL/TP based on market structure
- Sector regime scoring (soft penalty/bonus)
- SPY regime awareness
"""

from typing import List, Optional, Dict, Any
from loguru import logger
import pandas as pd
import numpy as np
import time

from .base_strategy import BaseStrategy, TradingSignal
from screeners.rapid_trader_filters import (
    calculate_score,
    check_bounce_confirmation,
    check_sma20_filter,
    check_momentum_5d_filter,
    calculate_dynamic_sl_tp,
)
from data_sources.realtime_price import get_current_price


class DipBounceStrategy(BaseStrategy):
    """
    Dip-Bounce Strategy - Buy dips with bounce confirmation

    Core Filters:
    1. Bounce Confirmation - Yesterday down, today recovering
    2. Above SMA20 - Trend filter (92% of losers were below)
    3. Not overextended - Prevents buying exhaustion moves
    4. Sufficient volatility - ATR >= 1.5%

    Scoring Factors:
    - Green candle recovery
    - Momentum (1d, 5d, 20d)
    - RSI oversold/overbought
    - Volume surge
    - Distance from 20d high
    - Sector regime (soft penalty/bonus)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize Dip-Bounce Strategy

        Args:
            config: Strategy configuration dict with optional parameters:
                - min_score: Minimum score threshold (default: 90)
                - min_atr_pct: Minimum ATR % (default: 1.5)
                - gap_max_up: Max gap up % allowed (default: 2.0)
                - sector_regime: SectorRegimeDetector instance (optional)
                - alt_data: AlternativeDataAggregator instance (optional)
        """
        super().__init__(config)

        # Scoring thresholds
        self.min_score = self.config.get('min_score', 90)
        self.min_atr_pct = self.config.get('min_atr_pct', 1.5)
        self.gap_max_up = self.config.get('gap_max_up', 2.0)

        # External dependencies (optional)
        self.sector_regime = self.config.get('sector_regime')
        self.alt_data = self.config.get('alt_data')

        # Sector cache (for performance)
        self._sector_cache: Dict[str, str] = {}

        # Filter statistics
        self._filter_stats = {
            'no_dip': 0, 'still_falling': 0, 'no_bounce': 0,
            'gap_up': 0, 'above_sma5': 0, 'low_atr': 0,
            'below_sma20': 0, 'mom_5d_reject': 0, 'overextended': 0,
            'sma20_extended': 0, 'low_volume': 0, 'high_volume': 0,
            'mom_5d_extended': 0, 'low_score': 0, '_low_score_values': [],
        }

        # v7.5: Screener rejection log (Dimension 3 — flushed to DB after each scan)
        self.rejection_batch: list = []

        # NOTE: Trace system now handled by BaseStrategy.__init__()
        # - self.enable_trace
        # - self.execution_trace
        # - self.stage_timings
        # All auto-initialized from define_stages()

    @property
    def name(self) -> str:
        return "dip_bounce"

    @property
    def display_name(self) -> str:
        return "Dip-Bounce"

    @property
    def description(self) -> str:
        return "Buy stocks that have dipped and are showing bounce confirmation"

    def define_stages(self) -> List[Dict[str, str]]:
        """
        Define DipBounce pipeline stages.

        Pipeline flow:
        INPUT → BASIC_FILTERS → BOUNCE_FILTERS → SCORING → THRESHOLD → OUTPUT

        Returns:
            List of stage definitions with metadata for UI visualization
        """
        return [
            {
                'name': 'INPUT',
                'icon': '📥',
                'title': 'Input',
                'description': 'Initial stock list from universe'
            },
            {
                'name': 'BASIC_FILTERS',
                'icon': '🔍',
                'title': 'Basic Filters',
                'description': 'Price range ($10-$2000), data quality checks'
            },
            {
                'name': 'BOUNCE_FILTERS',
                'icon': '🎯',
                'title': 'Bounce Confirmation',
                'description': 'Yesterday dip, today recovery signal'
            },
            {
                'name': 'SCORING',
                'icon': '📊',
                'title': 'Scoring',
                'description': 'Calculate signal strength (momentum, RSI, volume, sector)'
            },
            {
                'name': 'THRESHOLD',
                'icon': '✅',
                'title': 'Threshold',
                'description': 'Score >= 90 check (configurable)'
            },
            {
                'name': 'OUTPUT',
                'icon': '🚀',
                'title': 'Output',
                'description': 'Generate trading signal with SL/TP'
            },
        ]

    def scan(
        self,
        universe: List[str],
        data_cache: Dict[str, pd.DataFrame],
        market_data: Dict[str, Any] = None,
        progress_callback = None
    ) -> List[TradingSignal]:
        """
        Scan universe for dip-bounce opportunities

        Args:
            universe: List of stock symbols to scan
            data_cache: Dict mapping symbol -> DataFrame with OHLCV data
            market_data: Optional market context (regime, sector data, etc.)
            progress_callback: Optional callback for progress updates

        Returns:
            List of TradingSignal objects
        """
        signals = []

        # Clear execution trace from previous scan (v6.17: fix duplicate trace entries)
        if self.enable_trace:
            self.clear_trace()

        # Reset filter stats
        self._filter_stats = {
            'no_dip': 0, 'still_falling': 0, 'no_bounce': 0,
            'gap_up': 0, 'above_sma5': 0, 'low_atr': 0,
            'below_sma20': 0, 'mom_5d_reject': 0, 'overextended': 0,
            'sma20_extended': 0, 'low_volume': 0, 'high_volume': 0,
            'mom_5d_extended': 0, 'low_score': 0, '_low_score_values': [],
        }
        # v7.5: Clear per-scan rejection batch
        self.rejection_batch = []

        analyzed_count = 0
        for symbol in universe:
            try:
                # Progress callback
                analyzed_count += 1
                if progress_callback:
                    progress_callback(
                        phase="analyzing",
                        current=analyzed_count,
                        total=len(universe),
                        symbol=symbol,
                    )

                # Analyze stock
                signal = self.analyze_stock(
                    symbol=symbol,
                    data=data_cache.get(symbol),
                    market_data=market_data
                )

                if signal:
                    signals.append(signal)
                    if progress_callback:
                        progress_callback(
                            phase="signal",
                            symbol=symbol,
                            score=signal.score,
                            passed=True
                        )

            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")

        # Log filter diagnostics
        fs = self._filter_stats
        total_filtered = sum(v for k, v in fs.items() if k != '_low_score_values')
        logger.info(f"📋 {self.display_name} filter breakdown ({total_filtered} rejected, min_score={self.min_score}): "
                    f"no_dip={fs['no_dip']} still_falling={fs['still_falling']} "
                    f"no_bounce={fs['no_bounce']} gap_up={fs['gap_up']} "
                    f"above_sma5={fs['above_sma5']} low_atr={fs['low_atr']} "
                    f"below_sma20={fs['below_sma20']} mom_5d_reject={fs['mom_5d_reject']} "
                    f"overextended={fs['overextended']} sma20_ext={fs['sma20_extended']} "
                    f"low_vol={fs['low_volume']} high_vol={fs['high_volume']} "
                    f"mom_5d_ext={fs['mom_5d_extended']} low_score={fs['low_score']}")

        # Sort by score (descending)
        signals.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"📊 {self.display_name}: Found {len(signals)} signals from {len(universe)} stocks")

        return signals

    def analyze_stock(
        self,
        symbol: str,
        data: pd.DataFrame,
        market_data: Dict[str, Any] = None
    ) -> Optional[TradingSignal]:
        """
        Analyze a single stock for dip-bounce opportunity

        Args:
            symbol: Stock symbol
            data: OHLCV DataFrame for the stock
            market_data: Optional market context

        Returns:
            TradingSignal if criteria met, None otherwise
        """
        # Initialize trace entry
        trace = {
            'symbol': symbol,
            'stages': {},
            'final_result': None,
            'rejection_stage': None,
            'rejection_reason': None,
        } if self.enable_trace else None

        # Track INPUT stage timing
        input_start = time.time()
        if self.enable_trace:
            self.stage_timings['INPUT'].append(0)  # INPUT stage is instant

        # STAGE 1: Basic Filters
        basic_start = time.time()
        if data is None or data.empty or len(data) < 30:
            if trace:
                basic_duration = (time.time() - basic_start) * 1000
                self.stage_timings['BASIC_FILTERS'].append(basic_duration)
                trace['stages']['BASIC_FILTERS'] = {
                    'passed': False,
                    'reason': 'Insufficient data' if data is not None else 'No data',
                    'duration_ms': round(basic_duration, 2),
                }
                trace['rejection_stage'] = 'BASIC_FILTERS'
                trace['rejection_reason'] = trace['stages']['BASIC_FILTERS']['reason']
                trace['final_result'] = 'REJECTED'
                self.execution_trace.append(trace)
            return None

        idx = len(data) - 1
        current_price = data['close'].iloc[idx]

        # Basic price filters
        if current_price < 10 or current_price > 2000:
            if trace:
                basic_duration = (time.time() - basic_start) * 1000
                self.stage_timings['BASIC_FILTERS'].append(basic_duration)
                trace['stages']['BASIC_FILTERS'] = {
                    'passed': False,
                    'reason': f'Price ${current_price:.2f} out of range ($10-$2000)',
                    'price': current_price,
                    'duration_ms': round(basic_duration, 2),
                }
                trace['rejection_stage'] = 'BASIC_FILTERS'
                trace['rejection_reason'] = trace['stages']['BASIC_FILTERS']['reason']
                trace['final_result'] = 'REJECTED'
                self.execution_trace.append(trace)
            return None

        if trace:
            basic_duration = (time.time() - basic_start) * 1000  # Convert to ms
            self.stage_timings['BASIC_FILTERS'].append(basic_duration)
            trace['stages']['BASIC_FILTERS'] = {
                'passed': True,
                'price': current_price,
                'data_points': len(data),
                'duration_ms': round(basic_duration, 2),
            }

        # Calculate indicators (with real-time price if market is open)
        ind = self._calc_indicators(data, idx, symbol)

        # STAGE 2: Bounce Filters
        bounce_start = time.time()
        filter_hit, filter_details = self._apply_filters_with_trace(ind)
        if trace:
            bounce_duration = (time.time() - bounce_start) * 1000
            self.stage_timings['BOUNCE_FILTERS'].append(bounce_duration)
            filter_details['duration_ms'] = round(bounce_duration, 2)
            trace['stages']['BOUNCE_FILTERS'] = filter_details

        if filter_hit:
            self._filter_stats[filter_hit] += 1
            if trace:
                trace['rejection_stage'] = 'BOUNCE_FILTERS'
                trace['rejection_reason'] = filter_hit
                trace['final_result'] = 'REJECTED'
                self.execution_trace.append(trace)
            # v7.5: Log to screener rejection batch (flushed to DB at end of scan)
            _d = ind.get('dist_from_high', 0) or 0
            _a = ind.get('atr_pct', 0) or 0
            _m = ind.get('mom_5d', 0) or 0
            _r = ind.get('rsi', 50) or 50
            _ns = round((0.481 * max(0.0, 1.0 - _d / 25.0)
                         + 0.288 * max(0.0, 1.0 - (_a - 0.5) / 11.5)
                         + 0.130 * max(0.0, min(1.0, (_m + 20.0) / 25.0))
                         + 0.101 * max(0.0, 1.0 - (_r - 20.0) / 60.0)) * 100, 1)
            self.rejection_batch.append({
                'screener': 'dip_bounce', 'symbol': symbol, 'reject_reason': filter_hit,
                'scan_price': ind.get('current_price'), 'gap_pct': ind.get('gap_pct'),
                'volume_ratio': ind.get('volume_ratio'), 'rsi': ind.get('rsi'),
                'momentum_5d': ind.get('mom_5d'), 'atr_pct': ind.get('atr_pct'),
                'distance_from_high': ind.get('dist_from_high'),
                'sector': self._get_sector(symbol),
                'momentum_20d': ind.get('mom_20d'),
                'distance_from_20d_high': ind.get('dist_from_high'),
                'new_score': _ns,
            })
            return None

        # STAGE 3: Scoring
        scoring_start = time.time()
        score, reasons, sector, sector_score = self._calc_score(ind, symbol)
        if trace:
            scoring_duration = (time.time() - scoring_start) * 1000
            self.stage_timings['SCORING'].append(scoring_duration)
            trace['stages']['SCORING'] = {
                'passed': True,
                'score': score,
                'sector': sector,
                'sector_adj': sector_score,
                'reasons': reasons,
                'duration_ms': round(scoring_duration, 2),
            }

        # STAGE 4: Threshold Check
        threshold_start = time.time()
        if score < self.min_score:
            self._filter_stats['low_score'] += 1
            self._filter_stats['_low_score_values'].append((symbol, score))
            if trace:
                threshold_duration = (time.time() - threshold_start) * 1000
                self.stage_timings['THRESHOLD'].append(threshold_duration)
                trace['stages']['THRESHOLD'] = {
                    'passed': False,
                    'score': score,
                    'min_score': self.min_score,
                    'reason': f'Score {score} < {self.min_score}',
                    'duration_ms': round(threshold_duration, 2),
                }
                trace['rejection_stage'] = 'THRESHOLD'
                trace['rejection_reason'] = f'Low score ({score} < {self.min_score})'
                trace['final_result'] = 'REJECTED'
                self.execution_trace.append(trace)
            # v7.5: Log to screener rejection batch
            _d2 = ind.get('dist_from_high', 0) or 0
            _a2 = ind.get('atr_pct', 0) or 0
            _m2 = ind.get('mom_5d', 0) or 0
            _r2 = ind.get('rsi', 50) or 50
            _ns2 = round((0.481 * max(0.0, 1.0 - _d2 / 25.0)
                          + 0.288 * max(0.0, 1.0 - (_a2 - 0.5) / 11.5)
                          + 0.130 * max(0.0, min(1.0, (_m2 + 20.0) / 25.0))
                          + 0.101 * max(0.0, 1.0 - (_r2 - 20.0) / 60.0)) * 100, 1)
            self.rejection_batch.append({
                'screener': 'dip_bounce', 'symbol': symbol, 'reject_reason': 'low_score',
                'scan_price': ind.get('current_price'), 'gap_pct': ind.get('gap_pct'),
                'volume_ratio': ind.get('volume_ratio'), 'rsi': ind.get('rsi'),
                'momentum_5d': ind.get('mom_5d'), 'atr_pct': ind.get('atr_pct'),
                'distance_from_high': ind.get('dist_from_high'), 'score': score,
                'sector': sector,
                'momentum_20d': ind.get('mom_20d'),
                'distance_from_20d_high': ind.get('dist_from_high'),
                'new_score': _ns2,
            })
            return None

        if trace:
            threshold_duration = (time.time() - threshold_start) * 1000
            self.stage_timings['THRESHOLD'].append(threshold_duration)
            trace['stages']['THRESHOLD'] = {
                'passed': True,
                'score': score,
                'min_score': self.min_score,
                'duration_ms': round(threshold_duration, 2),
            }

        # Calculate SL/TP
        output_start = time.time()
        sl_tp = self._calc_sl_tp(ind, data, idx)
        reasons.append(f"SL:{sl_tp['sl_method']}({sl_tp['sl_pct']:.1f}%)")
        reasons.append(f"TP:{sl_tp['tp_method']}({sl_tp['tp_pct']:.1f}%)")

        # Get market regime
        market_regime = market_data.get('regime', 'UNKNOWN') if market_data else 'UNKNOWN'

        # STAGE 5: Signal Created
        if trace:
            output_duration = (time.time() - output_start) * 1000
            self.stage_timings['OUTPUT'].append(output_duration)
            trace['final_result'] = 'SIGNAL'
            trace['stages']['OUTPUT'] = {
                'passed': True,  # Mark as passed
                'entry_price': round(ind['current_price'], 2),
                'stop_loss': round(sl_tp['stop_loss'], 2),
                'take_profit': round(sl_tp['take_profit'], 2),
                'score': score,
                'risk_reward': round(sl_tp['risk_reward'], 2),
                'duration_ms': round(output_duration, 2),
            }
            self.execution_trace.append(trace)

        # Create TradingSignal
        # v6.23: Add gap_pct to metadata for adaptive entry timing
        return TradingSignal(
            symbol=symbol,
            strategy=self.name,
            entry_price=round(ind['current_price'], 2),
            stop_loss=round(sl_tp['stop_loss'], 2),
            take_profit=round(sl_tp['take_profit'], 2),
            score=score,
            confidence=min(100.0, score / 1.5),  # Convert score to 0-100%
            risk_reward=round(sl_tp['risk_reward'], 2),
            max_loss_pct=round(sl_tp['sl_pct'], 2),
            expected_gain_pct=round(sl_tp['tp_pct'], 2),
            atr_pct=round(ind['atr_pct'], 2),
            rsi=round(ind['rsi'], 1),
            momentum_5d=round(ind['mom_5d'], 2),
            momentum_20d=round(ind['mom_20d'], 2),
            distance_from_high=round(ind['dist_from_high'], 2),
            reasons=reasons,
            sector=sector,
            market_regime=market_regime,
            sector_score=sector_score,
            sl_method=sl_tp['sl_method'],
            tp_method=sl_tp['tp_method'],
            swing_low=round(sl_tp['swing_low'], 2),
            resistance=round(sl_tp['resistance'], 2),
            volume_ratio=round(ind['volume_ratio'], 2),
            metadata={'gap_pct': round(ind['gap_pct'], 2)},
        )

    # =========================================================================
    # TRACE METHODS
    # =========================================================================

    # NOTE: get_trace_summary() now inherited from BaseStrategy
    # It auto-generates summary from define_stages() metadata
    # No need to override - generic implementation works for all strategies!

    def get_full_trace(self) -> List[Dict[str, Any]]:
        """Get full execution trace for all stocks"""
        return self.execution_trace

    def clear_trace(self):
        """Clear execution trace"""
        self.execution_trace = []

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calc_indicators(self, data: pd.DataFrame, idx: int, symbol: str = '') -> dict:
        """Calculate all technical indicators for a stock"""
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        open_price = data['open'] if 'open' in data.columns else close

        # Get real-time price (hybrid approach)
        daily_price = close.iloc[idx]  # Fallback to daily bars
        current_price, is_realtime, price_source = get_current_price(symbol, data)

        # If real-time fetch failed, use daily bars
        if current_price == 0.0:
            current_price = daily_price
            is_realtime = False
            price_source = "daily bars (forced fallback)"

        logger.debug(f"{symbol}: Price ${current_price:.2f} from {price_source} "
                    f"(realtime: {is_realtime})")

        rsi = self._calculate_rsi(close).iloc[idx]
        atr = self._calculate_atr(data).iloc[idx]

        # Momentum - use real-time price for today's movement
        yesterday_close = close.iloc[idx-1] if idx >= 1 else current_price
        mom_1d = (current_price / yesterday_close - 1) * 100 if idx >= 1 else 0
        mom_5d = (current_price / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
        mom_20d = (current_price / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0
        yesterday_move = ((close.iloc[idx-1] / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0

        # SMAs
        sma5 = close.iloc[idx-4:idx+1].mean() if idx >= 4 else close.iloc[:idx+1].mean()
        sma20 = close.iloc[idx-19:idx+1].mean() if idx >= 19 else close.iloc[:idx+1].mean()
        sma50 = close.iloc[idx-49:idx+1].mean() if idx >= 49 else close.iloc[:idx+1].mean()

        # Distance from high
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        dist_from_high = (high_20d - current_price) / high_20d * 100

        # Overextended detection
        if idx >= 11:
            daily_returns = [(close.iloc[i] / close.iloc[i-1] - 1) * 100 for i in range(idx-10, idx)]
            max_daily_move = max(abs(r) for r in daily_returns) if daily_returns else 0
        else:
            max_daily_move = 0
        sma20_extension = ((current_price / sma20) - 1) * 100 if sma20 > 0 else 0

        # Volume
        avg_volume = volume.iloc[idx-20:idx].mean() if idx >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # Gap and candle - use real-time price for today's candle color
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price

        # Determine today's open:
        # - If real-time: use yesterday's close as proxy for today's open
        # - If not real-time: use daily bar's open
        if is_realtime:
            # Real-time during market hours - today's open ≈ gap from yesterday
            today_open = prev_close  # Approximate (actual open might differ)
            gap_pct = 0.0  # Can't calculate exact gap without today's open bar
        else:
            # Using daily bars - have today's complete bar
            today_open = open_price.iloc[idx]
            gap_pct = (today_open - prev_close) / prev_close * 100

        today_is_green = current_price > prev_close  # Green if above yesterday's close

        return {
            'current_price': current_price, 'rsi': rsi, 'atr': atr,
            'atr_pct': (atr / current_price) * 100,
            'mom_1d': mom_1d, 'mom_5d': mom_5d, 'mom_20d': mom_20d,
            'yesterday_move': yesterday_move,
            'sma5': sma5, 'sma20': sma20, 'sma50': sma50,
            'dist_from_high': dist_from_high,
            'max_daily_move': max_daily_move, 'sma20_extension': sma20_extension,
            'volume_ratio': volume_ratio, 'gap_pct': gap_pct,
            'today_is_green': today_is_green, 'today_open': today_open,
            'is_realtime': is_realtime, 'price_source': price_source,  # Track data source
        }

    def _apply_filters(self, ind: dict) -> Optional[str]:
        """
        Apply bounce confirmation filters

        Returns:
            Filter name if blocked, None if passed
        """
        filter_hit, _ = self._apply_filters_with_trace(ind)
        return filter_hit

    def _apply_filters_with_trace(self, ind: dict) -> tuple:
        """
        Apply bounce confirmation filters with detailed trace

        Returns:
            Tuple of (filter_name_if_blocked, filter_details_dict)
        """
        details = {
            'passed': True,
            'checks': [],
        }

        # Core filters from filters.py (single source of truth)
        passed, reason = check_bounce_confirmation(
            yesterday_move=ind['yesterday_move'],
            mom_1d=ind['mom_1d'],
            today_is_green=ind['today_is_green'],
            gap_pct=ind['gap_pct'],
            current_price=ind['current_price'],
            sma5=ind['sma5'],
            atr_pct=ind['atr_pct'],
        )

        details['checks'].append({
            'name': 'bounce_confirmation',
            'passed': passed,
            'reason': reason if not passed else 'OK',
            'values': {
                'yesterday_move': round(ind['yesterday_move'], 2),
                'mom_1d': round(ind['mom_1d'], 2),
                'today_is_green': ind['today_is_green'],
                'gap_pct': round(ind['gap_pct'], 2),
                'atr_pct': round(ind['atr_pct'], 2),
            }
        })

        if not passed:
            details['passed'] = False
            details['rejection_reason'] = reason
            # Map reason to filter stat key
            reason_map = {
                'Yesterday': 'no_dip',
                'Still': 'still_falling',
                'No clear': 'no_bounce',
                'Gap': 'gap_up',
                'Too extended': 'above_sma5',
                'Volatility': 'low_atr',
            }
            for key, val in reason_map.items():
                if reason.startswith(key):
                    return val, details
            return 'no_dip', details  # fallback

        # Gap override (screener allows custom gap_max_up)
        gap_check_passed = ind['gap_pct'] <= self.gap_max_up
        details['checks'].append({
            'name': 'gap_override',
            'passed': gap_check_passed,
            'reason': f'Gap {ind["gap_pct"]:.2f}% > {self.gap_max_up}%' if not gap_check_passed else 'OK',
            'values': {
                'gap_pct': round(ind['gap_pct'], 2),
                'max_allowed': self.gap_max_up,
            }
        })
        if not gap_check_passed:
            details['passed'] = False
            details['rejection_reason'] = f'Gap too large ({ind["gap_pct"]:.2f}%)'
            return 'gap_up', details

        # SMA20 filter (from filters.py)
        passed, reason = check_sma20_filter(ind['current_price'], ind['sma20'])
        details['checks'].append({
            'name': 'sma20_filter',
            'passed': passed,
            'reason': reason if not passed else 'OK',
            'values': {
                'current_price': round(ind['current_price'], 2),
                'sma20': round(ind['sma20'], 2),
                'distance': round(((ind['current_price'] / ind['sma20']) - 1) * 100, 2),
            }
        })
        if not passed:
            details['passed'] = False
            details['rejection_reason'] = reason
            return 'below_sma20', details

        # Momentum 5d filter (from filters.py; validates -15% to -1% range + deep dip RSI guard)
        passed, reason = check_momentum_5d_filter(ind['mom_5d'], config=None, rsi=ind['rsi'])
        details['checks'].append({
            'name': 'momentum_5d_filter',
            'passed': passed,
            'reason': reason if not passed else 'OK',
            'values': {
                'mom_5d': round(ind['mom_5d'], 2),
                'rsi': round(ind['rsi'], 1),
            }
        })
        if not passed:
            details['passed'] = False
            details['rejection_reason'] = reason
            return 'mom_5d_reject', details

        # Strategy-specific filters (not in filters.py)
        overextended_check = ind['max_daily_move'] <= 8.0
        details['checks'].append({
            'name': 'overextended_check',
            'passed': overextended_check,
            'reason': f'Max daily move {ind["max_daily_move"]:.2f}% > 8%' if not overextended_check else 'OK',
            'values': {
                'max_daily_move': round(ind['max_daily_move'], 2),
                'threshold': 8.0,
            }
        })
        if not overextended_check:
            details['passed'] = False
            details['rejection_reason'] = f'Overextended (max daily {ind["max_daily_move"]:.2f}%)'
            return 'overextended', details

        sma20_ext_check = ind['sma20_extension'] <= 10.0
        details['checks'].append({
            'name': 'sma20_extension_check',
            'passed': sma20_ext_check,
            'reason': f'SMA20 extension {ind["sma20_extension"]:.2f}% > 10%' if not sma20_ext_check else 'OK',
            'values': {
                'sma20_extension': round(ind['sma20_extension'], 2),
                'threshold': 10.0,
            }
        })
        if not sma20_ext_check:
            details['passed'] = False
            details['rejection_reason'] = f'Too extended from SMA20 ({ind["sma20_extension"]:.2f}%)'
            return 'sma20_extended', details

        # Volume range filter (v6.69: sweet spot 0.3-1.2x)
        vol_ratio = ind['volume_ratio']
        if vol_ratio < 0.3:
            details['checks'].append({
                'name': 'volume_range',
                'passed': False,
                'reason': f'Volume ratio {vol_ratio:.2f}x < 0.3 (no buyer interest)',
                'values': {'volume_ratio': round(vol_ratio, 2), 'min': 0.3, 'max': 1.2}
            })
            details['passed'] = False
            details['rejection_reason'] = f'Volume too low ({vol_ratio:.2f}x < 0.3)'
            return 'low_volume', details
        if vol_ratio > 1.2:
            details['checks'].append({
                'name': 'volume_range',
                'passed': False,
                'reason': f'Volume ratio {vol_ratio:.2f}x > 1.2 (panic selling)',
                'values': {'volume_ratio': round(vol_ratio, 2), 'min': 0.3, 'max': 1.2}
            })
            details['passed'] = False
            details['rejection_reason'] = f'Volume too high ({vol_ratio:.2f}x > 1.2)'
            return 'high_volume', details
        details['checks'].append({
            'name': 'volume_range',
            'passed': True,
            'reason': 'OK',
            'values': {'volume_ratio': round(vol_ratio, 2), 'min': 0.3, 'max': 1.2}
        })

        # Momentum 5d upper cap (v6.69: >+2% = not a dip)
        mom_5d_ext_check = ind['mom_5d'] <= 2.0
        details['checks'].append({
            'name': 'mom_5d_upper_cap',
            'passed': mom_5d_ext_check,
            'reason': f'mom_5d {ind["mom_5d"]:.2f}% > 2.0% (not a dip)' if not mom_5d_ext_check else 'OK',
            'values': {'mom_5d': round(ind['mom_5d'], 2), 'threshold': 2.0}
        })
        if not mom_5d_ext_check:
            details['passed'] = False
            details['rejection_reason'] = f'Momentum 5d too high ({ind["mom_5d"]:.2f}% > 2.0%)'
            return 'mom_5d_extended', details

        # All filters passed
        details['passed'] = True
        return None, details

    def _calc_score(self, ind: dict, symbol: str) -> tuple:
        """
        Calculate score and reasons

        Returns:
            Tuple of (score, reasons, sector, sector_score)
        """
        # Core scoring from filters.py (single source of truth)
        score, reasons = calculate_score(
            today_is_green=ind['today_is_green'],
            mom_1d=ind['mom_1d'],
            mom_5d=ind['mom_5d'],
            yesterday_move=ind['yesterday_move'],
            rsi=ind['rsi'],
            current_price=ind['current_price'],
            sma20=ind['sma20'],
            sma50=ind['sma50'],
            atr_pct=ind['atr_pct'],
            dist_from_high=ind['dist_from_high'],
            volume_ratio=ind['volume_ratio'],
        )

        # Strategy-specific: sector scoring
        sector = self._get_sector(symbol)
        sector_adj, sector_regime, sector_reason = self._get_sector_regime_score(sector)
        score += sector_adj
        if sector_reason:
            reasons.append(sector_reason)

        return score, reasons, sector, sector_adj

    def _calc_sl_tp(self, ind: dict, data: pd.DataFrame, idx: int) -> dict:
        """Calculate dynamic SL/TP levels"""
        close = data['close']
        high = data['high']
        low = data['low']

        swing_low_5d = low.iloc[idx-5:idx].min() if idx >= 5 else low.min()
        ema5 = close.ewm(span=5).mean().iloc[idx]
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        high_52w = high.max()

        # Use filters.py (single source of truth)
        result = calculate_dynamic_sl_tp(
            current_price=ind['current_price'],
            atr=ind['atr'],
            swing_low_5d=swing_low_5d,
            ema5=ema5,
            high_20d=high_20d,
            high_52w=high_52w,
        )

        result['swing_low'] = swing_low_5d
        result['resistance'] = high_20d
        return result

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol (cached)"""
        if symbol in self._sector_cache:
            return self._sector_cache[symbol]

        # Try to fetch via rate-limited Yahoo
        try:
            from data_sources.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            info = rl.get_info(symbol)
            sector = info.get('sector', 'Unknown') if info else 'Unknown'
        except Exception:
            sector = 'Unknown'

        # Cache if valid
        if sector != 'Unknown':
            self._sector_cache[symbol] = sector

        return sector

    def _get_sector_regime_score(self, sector: str) -> tuple:
        """
        Get sector regime score using HYBRID v2 approach

        Uses simple ±3% rule on 20-day sector ETF performance:
        - > +3%  = BULL    → +5 points
        - -3% to +3% = SIDEWAYS → 0 points
        - < -3%  = BEAR    → -10 points (defensive - penalize harder)

        Returns:
            Tuple of (score_adjustment, regime, reason)
        """
        if not self.sector_regime:
            return 0, 'UNKNOWN', ''

        try:
            # Get ETF symbol for sector
            etf = self.sector_regime.SECTOR_TO_ETF.get(sector)
            if not etf:
                return 0, 'UNKNOWN', ''

            # Get sector metrics (20-day return)
            metrics = self.sector_regime.sector_metrics.get(etf)
            if not metrics:
                return 0, 'UNKNOWN', ''

            return_20d = metrics.get('return_20d', 0)

            # Determine regime based on simple ±3% rule
            if return_20d > 3.0:
                regime = 'BULL'
                score_adj = 5
                reason = f"BULL sector +{return_20d:.1f}%"
            elif return_20d < -3.0:
                regime = 'BEAR'
                score_adj = -10
                reason = f"BEAR sector {return_20d:.1f}%"
            else:
                regime = 'SIDEWAYS'
                score_adj = 0
                reason = f"Sideways sector {return_20d:+.1f}%"

            return score_adj, regime, reason

        except Exception as e:
            logger.debug(f"Sector regime score failed for {sector}: {e}")
            return 0, 'UNKNOWN', ''

    # =========================================================================
    # TECHNICAL INDICATORS
    # =========================================================================

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR"""
        high = data['high']
        low = data['low']
        close = data['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(period).mean()
