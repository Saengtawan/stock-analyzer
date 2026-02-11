"""
Utilities Package - Single Source of Truth for common functions
"""

# Import JSON serialization utilities from parent utils.py
import json
import numpy as np
import pandas as pd
from typing import Any
from enum import Enum


def make_json_serializable(obj: Any) -> Any:
    """Convert numpy arrays, pandas DataFrames and other non-serializable objects to JSON-serializable format"""
    if isinstance(obj, pd.DataFrame):
        records = obj.to_dict('records')
        return [make_json_serializable(record) for record in records]
    elif isinstance(obj, pd.Series):
        series_dict = obj.to_dict()
        return {str(key): make_json_serializable(value) for key, value in series_dict.items()}
    elif isinstance(obj, np.ndarray):
        return [make_json_serializable(item) for item in obj.tolist()]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, int):
        return obj
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return [make_json_serializable(item) for item in obj]
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif pd.isna(obj):
        return None
    else:
        try:
            return str(obj)
        except:
            return None


def clean_analysis_results(results: dict) -> dict:
    """Clean analysis results to ensure JSON serializability"""
    return make_json_serializable(results)


# Import market utilities
from .market_hours import (
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
    PRE_CLOSE_HOUR, PRE_CLOSE_MINUTE,
    MARKET_OPEN_STR, MARKET_CLOSE_STR, PRE_CLOSE_STR,
    MARKET_OPEN_TIME, MARKET_CLOSE_TIME, PRE_CLOSE_TIME,
    MARKET_OPEN_MINUTES, MARKET_CLOSE_MINUTES, PRE_CLOSE_MINUTES,
    MARKET_TIMEZONE,
    get_et_time, is_market_hours, is_pre_close,
    minutes_to_market_open, minutes_to_market_close,
    get_market_status, format_market_time,
    # Alpaca integration
    get_market_hours_from_broker, get_actual_market_close_time,
    is_early_close_today, clear_market_hours_cache
)

from .market_calendar import (
    is_trading_day_today, is_holiday_today,
    get_market_calendar_status,
    get_next_trading_day,
    format_next_open_display
)

# Import account info utilities
from .account_info import (
    get_account_info_from_broker, get_buying_power, get_account_equity,
    get_margin_multiplier, calculate_max_position_value,
    clear_account_cache
)

# Import asset info utilities
from .asset_info import (
    get_asset_info_from_broker, is_asset_tradable, is_asset_marginable,
    is_asset_shortable, can_buy_fractional,
    validate_symbols_tradability, clear_asset_cache
)

__all__ = [
    # JSON Utilities
    'make_json_serializable', 'clean_analysis_results',
    # Market Hours
    'MARKET_OPEN_HOUR', 'MARKET_OPEN_MINUTE',
    'MARKET_CLOSE_HOUR', 'MARKET_CLOSE_MINUTE',
    'PRE_CLOSE_HOUR', 'PRE_CLOSE_MINUTE',
    'MARKET_OPEN_STR', 'MARKET_CLOSE_STR', 'PRE_CLOSE_STR',
    'MARKET_OPEN_TIME', 'MARKET_CLOSE_TIME', 'PRE_CLOSE_TIME',
    'MARKET_OPEN_MINUTES', 'MARKET_CLOSE_MINUTES', 'PRE_CLOSE_MINUTES',
    'MARKET_TIMEZONE',
    'get_et_time', 'is_market_hours', 'is_pre_close',
    'minutes_to_market_open', 'minutes_to_market_close',
    'get_market_status', 'format_market_time',
    # Alpaca Integration
    'get_market_hours_from_broker', 'get_actual_market_close_time',
    'is_early_close_today', 'clear_market_hours_cache',
    # Market Calendar
    'is_trading_day_today', 'is_holiday_today',
    'get_market_calendar_status',
    'get_next_trading_day',
    'format_next_open_display',
    # Account Info
    'get_account_info_from_broker', 'get_buying_power', 'get_account_equity',
    'get_margin_multiplier', 'calculate_max_position_value',
    'clear_account_cache',
    # Asset Info
    'get_asset_info_from_broker', 'is_asset_tradable', 'is_asset_marginable',
    'is_asset_shortable', 'can_buy_fractional',
    'validate_symbols_tradability', 'clear_asset_cache',
]
