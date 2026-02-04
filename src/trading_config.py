#!/usr/bin/env python3
"""
Trading Config Loader

Loads trading parameters from config/trading.yaml.
Supports hot-reload (call load() again to re-read).

Usage:
    from trading_config import load_config
    cfg = load_config()
    print(cfg['max_positions'])
"""

import os
import threading
from typing import Dict, Any, Optional, Tuple
from loguru import logger

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'config', 'trading.yaml'
)

_cached_config: Optional[Dict[str, Any]] = None
_cached_mtime: float = 0.0
_config_lock = threading.Lock()


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load config from YAML file. Caches result until file changes.

    Returns:
        Dict of config values (empty dict on error).
    """
    global _cached_config, _cached_mtime

    config_path = path or _CONFIG_PATH

    if not YAML_AVAILABLE:
        logger.warning("PyYAML not installed - using default config")
        return {}

    if not os.path.exists(config_path):
        logger.debug(f"Config file not found: {config_path}")
        return {}

    with _config_lock:
        try:
            mtime = os.path.getmtime(config_path)
            if _cached_config is not None and mtime == _cached_mtime:
                return _cached_config

            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            _cached_config = config
            _cached_mtime = mtime
            logger.info(f"Config loaded: {config_path} ({len(config)} params)")
            return config

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return _cached_config or {}


# Validation schema: attr_name → {type, min, max}
# Values use whole-number percentages to match engine class attributes
# (e.g. STOP_LOSS_PCT=2.5 means 2.5%, not 0.025)
CONFIG_SCHEMA: Dict[str, Dict[str, Any]] = {
    'MAX_POSITIONS': {'type': int, 'min': 1, 'max': 10},
    'MAX_POSITION_SIZE_PCT': {'type': (int, float), 'min': 5, 'max': 50},
    'STOP_LOSS_PCT': {'type': (int, float), 'min': 1.0, 'max': 15.0},
    'TAKE_PROFIT_PCT': {'type': (int, float), 'min': 2.0, 'max': 30.0},
    'MONITOR_INTERVAL_SECONDS': {'type': int, 'min': 5, 'max': 300},
    'CIRCUIT_BREAKER_MAX_ERRORS': {'type': int, 'min': 2, 'max': 20},
    'MAX_SLIPPAGE_PCT': {'type': (int, float), 'min': 0.1, 'max': 5.0},
    'TRAIL_ACTIVATION_PCT': {'type': (int, float), 'min': 1.0, 'max': 20.0},
    'TRAIL_LOCK_PCT': {'type': (int, float), 'min': 10, 'max': 100},
    'MAX_HOLD_DAYS': {'type': int, 'min': 1, 'max': 30},
    'MAX_PER_SECTOR': {'type': int, 'min': 1, 'max': 5},
    'DAILY_LOSS_LIMIT_PCT': {'type': (int, float), 'min': 1.0, 'max': 20.0},
    'WEEKLY_LOSS_LIMIT_PCT': {'type': (int, float), 'min': 2.0, 'max': 30.0},
    'MAX_CONSECUTIVE_LOSSES': {'type': int, 'min': 1, 'max': 10},
    'MIN_SCORE': {'type': int, 'min': 50, 'max': 100},
    'POSITION_SIZE_PCT': {'type': (int, float), 'min': 5, 'max': 50},
    # v4.9.4: Conviction-Based Sizing
    'CONVICTION_A_PLUS_PCT': {'type': (int, float), 'min': 20, 'max': 50},
    'CONVICTION_A_PCT': {'type': (int, float), 'min': 20, 'max': 50},
    'CONVICTION_B_PCT': {'type': (int, float), 'min': 15, 'max': 40},
    # v4.9.4: Smart Day Trade
    'DAY_TRADE_GAP_THRESHOLD': {'type': (int, float), 'min': 1.0, 'max': 10.0},
    'DAY_TRADE_MOMENTUM_THRESHOLD': {'type': (int, float), 'min': 2.0, 'max': 15.0},
    # v4.9.4: Overnight Gap
    'OVERNIGHT_GAP_MIN_SCORE': {'type': int, 'min': 40, 'max': 100},
    'OVERNIGHT_GAP_POSITION_PCT': {'type': (int, float), 'min': 10, 'max': 50},
    'OVERNIGHT_GAP_TARGET_PCT': {'type': (int, float), 'min': 1.0, 'max': 10.0},
    'OVERNIGHT_GAP_SL_PCT': {'type': (int, float), 'min': 0.5, 'max': 5.0},
    # v4.9.4: Breakout Scanner
    'BREAKOUT_MIN_VOLUME_MULT': {'type': (int, float), 'min': 1.0, 'max': 5.0},
    'BREAKOUT_MIN_SCORE': {'type': int, 'min': 40, 'max': 100},
    'BREAKOUT_TARGET_PCT': {'type': (int, float), 'min': 2.0, 'max': 15.0},
    'BREAKOUT_SL_PCT': {'type': (int, float), 'min': 1.0, 'max': 10.0},
    'MAX_POSITION_PCT': {'type': (int, float), 'min': 10, 'max': 60},
    # v4.9.4: BEAR Mode params (configurable)
    'BEAR_MAX_POSITIONS': {'type': int, 'min': 1, 'max': 5},
    'BEAR_MIN_SCORE': {'type': int, 'min': 60, 'max': 100},
    'BEAR_GAP_MAX_UP': {'type': (int, float), 'min': 0.5, 'max': 5.0},
    'BEAR_GAP_MAX_DOWN': {'type': (int, float), 'min': -10.0, 'max': -1.0},
    'BEAR_POSITION_SIZE_PCT': {'type': (int, float), 'min': 10, 'max': 40},
    'BEAR_MAX_ATR_PCT': {'type': (int, float), 'min': 2.0, 'max': 6.0},
}


def _validate_config_value(attr_name: str, value: Any) -> Tuple[bool, str]:
    """Validate a config value against the schema. Returns (valid, reason)."""
    schema = CONFIG_SCHEMA.get(attr_name)
    if not schema:
        return True, ""  # No schema = allow anything

    expected_type = schema['type']
    # Handle tuple of types (e.g. (int, float))
    if isinstance(expected_type, tuple):
        if not isinstance(value, expected_type):
            type_names = '/'.join(t.__name__ for t in expected_type)
            return False, f"expected {type_names}, got {type(value).__name__}"
    else:
        # Allow int for float fields
        if expected_type == float and isinstance(value, int):
            value = float(value)
        if not isinstance(value, expected_type):
            return False, f"expected {expected_type.__name__}, got {type(value).__name__}"

    if 'min' in schema and value < schema['min']:
        return False, f"value {value} below minimum {schema['min']}"
    if 'max' in schema and value > schema['max']:
        return False, f"value {value} above maximum {schema['max']}"

    return True, ""


def apply_config(engine, config: Optional[Dict[str, Any]] = None, trader=None):
    """
    Apply config values to an AutoTradingEngine instance.
    Only sets attributes that exist in config AND as class attributes.
    Validates type and bounds before applying.

    Args:
        engine: AutoTradingEngine instance
        config: Config dict (loads from file if None)
        trader: Optional AlpacaTrader instance. If provided,
                max_slippage_pct → MAX_SLIPPAGE_PCT is applied to the trader
                instead of the engine.
    """
    if config is None:
        config = load_config()

    if not config:
        return

    # Keys that should be applied to the trader, not the engine
    TRADER_KEYS = {'MAX_SLIPPAGE_PCT'}

    # Keys that affect open positions — skip if positions are open
    POSITION_SENSITIVE_KEYS = {
        'STOP_LOSS_PCT', 'TAKE_PROFIT_PCT', 'TRAIL_ACTIVATION_PCT',
        'TRAIL_LOCK_PCT', 'POSITION_SIZE_PCT', 'MAX_POSITION_SIZE_PCT',
    }

    has_positions = hasattr(engine, 'positions') and bool(engine.positions)

    # Map YAML keys → class attribute names
    # Keys in YAML are lowercase_snake; class attrs are UPPERCASE_SNAKE
    applied = 0
    skipped = 0
    for key, value in config.items():
        attr_name = key.upper()

        # Determine target: trader or engine
        target = engine
        if attr_name in TRADER_KEYS and trader is not None:
            target = trader

        if hasattr(target, attr_name) and value is not None:
            # v4.9: Skip position-sensitive params while positions are open
            if has_positions and attr_name in POSITION_SENSITIVE_KEYS:
                logger.warning(f"Config SKIPPED (positions open): {attr_name} = {value}")
                skipped += 1
                continue

            # Validate before applying
            valid, reason = _validate_config_value(attr_name, value)
            if not valid:
                logger.warning(f"Config REJECTED: {attr_name} = {value} ({reason})")
                skipped += 1
                continue

            old_val = getattr(target, attr_name)
            if old_val != value:
                setattr(target, attr_name, value)
                logger.debug(f"Config: {attr_name} = {value} (was {old_val})")
            applied += 1

    logger.info(f"Config applied: {applied} parameters" + (f", {skipped} rejected/skipped" if skipped else ""))
