"""
Engine Module - Refactored from auto_trading_engine.py
=======================================================

Phase 1: models.py - TradingState, SignalSource, ManagedPosition, DailyStats, QueuedSignal
Phase 2: time_utils.py - Market hours helpers
Phase 3: state_manager.py - Persistence (save/load)
Phase 4: regime_checker.py - VIX, Bear/Bull mode
Phase 5: filter_engine.py - All trade filters
Phase 6: risk_manager.py - Loss limits, daily checks
Phase 7: signal_queue.py - Queue management
Phase 8: position_monitor.py - Position monitoring
Phase 9: order_executor.py - Order execution
Phase 10: core.py - Main trading loop (placeholder)

All phases complete - modules provide utility functions for the engine.
The main AutoTradingEngine class remains in auto_trading_engine.py but can
use these extracted utilities for cleaner, more testable code.
"""

# Phase 1: Models
from .models import (
    TradingState,
    SignalSource,
    ManagedPosition,
    DailyStats,
    QueuedSignal,
)

# Phase 2: Time utilities
from .time_utils import (
    get_et_time,
    is_market_hours,
    is_pre_close,
    is_weekend,
    get_market_open_time,
    get_market_close_time,
    minutes_since_market_open,
    minutes_until_market_close,
    is_late_start,
    format_et_time,
    ET_TZ,
)

# Phase 3: State management
from .state_manager import (
    get_state_dir,
    atomic_write_json,
    safe_read_json,
    cleanup_old_files,
    create_backup,
    write_heartbeat,
    read_heartbeat,
    StateFile,
    serialize_position,
    deserialize_position,
    serialize_queued_signal,
    deserialize_queued_signal,
)

# Phase 4: Regime checking
from .regime_checker import (
    check_vix_threshold,
    get_vix_risk_level,
    calculate_vix_position_factor,
    is_bear_mode,
    filter_sectors_by_regime,
    calculate_regime_score,
    determine_regime_from_score,
    is_regime_allowed,
)

# Phase 5: Trade filters
from .filter_engine import (
    check_gap_filter,
    check_earnings_filter,
    check_late_start_filter,
    check_stock_d_filter,
    check_atr_volatility,
    check_price_range,
    apply_all_filters,
)

# Phase 6: Risk management
from .risk_manager import (
    check_daily_loss_limit,
    check_weekly_loss_limit,
    check_consecutive_loss_cooldown,
    calculate_position_size,
    calculate_risk_adjusted_size,
    calculate_stop_loss,
    calculate_take_profit,
    check_max_drawdown,
    get_risk_summary,
)

# Phase 7: Signal queue
from .signal_queue import (
    check_price_deviation,
    is_signal_fresh,
    prioritize_queue,
    filter_expired_signals,
    should_add_to_queue,
    select_best_from_queue,
    get_queue_summary,
)

# Phase 8: Position monitoring
from .position_monitor import (
    update_peak_price,
    update_trough_price,
    calculate_trailing_stop,
    should_update_stop_order,
    check_take_profit,
    check_stop_loss,
    calculate_days_held,
    check_pdt_day_trade,
    get_position_health,
    should_close_position,
)

# Phase 9: Order execution
from .order_executor import (
    calculate_order_qty,
    validate_order_params,
    calculate_sl_tp_prices,
    calculate_conviction_size,
    format_order_summary,
    should_use_day_trade,
    prepare_bracket_order,
    prepare_trailing_stop_order,
)

# Phase 10: Core loop utilities
from .core import (
    create_loop_schedule,
    calculate_next_scan_time,
    sleep_until,
    format_loop_status,
    LoopTimer,
    safe_call,
)

__all__ = [
    # Models (Phase 1)
    'TradingState',
    'SignalSource',
    'ManagedPosition',
    'DailyStats',
    'QueuedSignal',

    # Time utilities (Phase 2)
    'get_et_time',
    'is_market_hours',
    'is_pre_close',
    'is_weekend',
    'get_market_open_time',
    'get_market_close_time',
    'minutes_since_market_open',
    'minutes_until_market_close',
    'is_late_start',
    'format_et_time',
    'ET_TZ',

    # State management (Phase 3)
    'get_state_dir',
    'atomic_write_json',
    'safe_read_json',
    'cleanup_old_files',
    'create_backup',
    'write_heartbeat',
    'read_heartbeat',
    'StateFile',
    'serialize_position',
    'deserialize_position',
    'serialize_queued_signal',
    'deserialize_queued_signal',

    # Regime checking (Phase 4)
    'check_vix_threshold',
    'get_vix_risk_level',
    'calculate_vix_position_factor',
    'is_bear_mode',
    'filter_sectors_by_regime',
    'calculate_regime_score',
    'determine_regime_from_score',
    'is_regime_allowed',

    # Trade filters (Phase 5)
    'check_gap_filter',
    'check_earnings_filter',
    'check_late_start_filter',
    'check_stock_d_filter',
    'check_atr_volatility',
    'check_price_range',
    'apply_all_filters',

    # Risk management (Phase 6)
    'check_daily_loss_limit',
    'check_weekly_loss_limit',
    'check_consecutive_loss_cooldown',
    'calculate_position_size',
    'calculate_risk_adjusted_size',
    'calculate_stop_loss',
    'calculate_take_profit',
    'check_max_drawdown',
    'get_risk_summary',

    # Signal queue (Phase 7)
    'check_price_deviation',
    'is_signal_fresh',
    'prioritize_queue',
    'filter_expired_signals',
    'should_add_to_queue',
    'select_best_from_queue',
    'get_queue_summary',

    # Position monitoring (Phase 8)
    'update_peak_price',
    'update_trough_price',
    'calculate_trailing_stop',
    'should_update_stop_order',
    'check_take_profit',
    'check_stop_loss',
    'calculate_days_held',
    'check_pdt_day_trade',
    'get_position_health',
    'should_close_position',

    # Order execution (Phase 9)
    'calculate_order_qty',
    'validate_order_params',
    'calculate_sl_tp_prices',
    'calculate_conviction_size',
    'format_order_summary',
    'should_use_day_trade',
    'prepare_bracket_order',
    'prepare_trailing_stop_order',

    # Core loop utilities (Phase 10)
    'create_loop_schedule',
    'calculate_next_scan_time',
    'sleep_until',
    'format_loop_status',
    'LoopTimer',
    'safe_call',
]
