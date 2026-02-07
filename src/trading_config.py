#!/usr/bin/env python3
"""
Trading Config Loader — YAML as Single Source of Truth

v6.1: YAML is the ONLY source for trading parameters.
      Missing or invalid config = FAIL LOUD (not silent defaults).

Usage:
    from trading_config import load_config, ConfigurationError
    try:
        cfg = load_config()  # Raises if missing/invalid
    except ConfigurationError as e:
        print(f"FATAL: {e}")
        sys.exit(1)
"""

import os
import threading
from typing import Dict, Any, Optional, Tuple, List
from loguru import logger

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ConfigurationError(Exception):
    """Raised when trading config is missing or invalid."""
    pass


_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'config', 'trading.yaml'
)

_cached_config: Optional[Dict[str, Any]] = None
_cached_mtime: float = 0.0
_config_lock = threading.Lock()


# =============================================================================
# REQUIRED CONFIG KEYS — Trading system WILL NOT start without these
# =============================================================================
REQUIRED_CONFIG_KEYS: List[str] = [
    # Position Management
    'max_positions',
    'position_size_pct',
    'max_position_pct',
    # Risk Management
    'stop_loss_pct',
    'take_profit_pct',
    'daily_loss_limit_pct',
    'weekly_loss_limit_pct',
    'max_consecutive_losses',
    # ATR-based SL/TP
    'sl_atr_multiplier',
    'sl_min_pct',
    'sl_max_pct',
    'tp_atr_multiplier',
    'tp_min_pct',
    'tp_max_pct',
    # Trailing Stop
    'trail_enabled',
    'trail_activation_pct',
    'trail_lock_pct',
    'max_hold_days',
    # Entry Filters
    'min_score',
    'gap_filter_enabled',
    'gap_max_up',
    'gap_max_down',
    # Market Regime
    'regime_filter_enabled',
    'regime_vix_max',
    # BEAR Mode
    'bear_max_positions',
    'bear_min_score',
    'bear_position_size_pct',
]


def load_config(path: Optional[str] = None, strict: bool = True) -> Dict[str, Any]:
    """
    Load config from YAML file. Caches result until file changes.

    Args:
        path: Optional config file path (default: config/trading.yaml)
        strict: If True (default), raises ConfigurationError on missing file/keys.
                If False, returns empty dict (for backwards compatibility during migration).

    Returns:
        Dict of config values.

    Raises:
        ConfigurationError: If strict=True and config is missing/invalid.
    """
    global _cached_config, _cached_mtime

    config_path = path or _CONFIG_PATH

    # Check PyYAML availability
    if not YAML_AVAILABLE:
        msg = "FATAL: PyYAML not installed. Run: pip install pyyaml"
        if strict:
            raise ConfigurationError(msg)
        logger.error(msg)
        return {}

    # Check file exists
    if not os.path.exists(config_path):
        msg = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    CONFIGURATION FILE MISSING                      ║
╠══════════════════════════════════════════════════════════════════╣
║  Expected: {config_path:<52} ║
║                                                                    ║
║  Trading system requires config/trading.yaml to operate.          ║
║  This is the SINGLE SOURCE OF TRUTH for all trading parameters.   ║
║                                                                    ║
║  Fix: Copy config/trading.yaml.example to config/trading.yaml     ║
║       and adjust values for your risk tolerance.                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
        if strict:
            raise ConfigurationError(msg)
        logger.error(msg)
        return {}

    with _config_lock:
        try:
            mtime = os.path.getmtime(config_path)
            if _cached_config is not None and mtime == _cached_mtime:
                return _cached_config

            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            # Validate required keys
            if strict:
                missing_keys = [k for k in REQUIRED_CONFIG_KEYS if k not in config]
                if missing_keys:
                    msg = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    MISSING REQUIRED CONFIG KEYS                    ║
╠══════════════════════════════════════════════════════════════════╣
║  The following required parameters are missing from trading.yaml: ║
║                                                                    ║
"""
                    for key in missing_keys[:10]:  # Show first 10
                        msg += f"║    • {key:<58} ║\n"
                    if len(missing_keys) > 10:
                        msg += f"║    ... and {len(missing_keys) - 10} more                                        ║\n"
                    msg += """║                                                                    ║
║  Trading system cannot operate with missing parameters.            ║
║  Wrong config = REAL MONEY LOSS. Fix config before running.       ║
╚══════════════════════════════════════════════════════════════════╝
"""
                    raise ConfigurationError(msg)

            _cached_config = config
            _cached_mtime = mtime
            logger.info(f"✅ Config loaded: {config_path} ({len(config)} params)")
            return config

        except ConfigurationError:
            raise  # Re-raise validation errors
        except Exception as e:
            msg = f"Failed to parse config file: {e}"
            if strict:
                raise ConfigurationError(msg)
            logger.error(msg)
            return _cached_config or {}


def get_config_value(key: str, default: Any = None) -> Any:
    """
    Get a single config value. Raises if config not loaded and strict mode.

    Usage:
        max_pos = get_config_value('max_positions')
    """
    config = load_config(strict=False)
    if key not in config and default is None:
        logger.warning(f"Config key '{key}' not found and no default provided")
    return config.get(key, default)


def validate_config() -> Tuple[bool, List[str]]:
    """
    Validate the entire config file without raising.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    try:
        config = load_config(strict=False)
    except Exception as e:
        return False, [str(e)]

    if not config:
        return False, ["Config file is empty or not found"]

    # Check required keys
    for key in REQUIRED_CONFIG_KEYS:
        if key not in config:
            errors.append(f"Missing required key: {key}")

    # Validate values against schema
    for key, value in config.items():
        attr_name = key.upper()
        valid, reason = _validate_config_value(attr_name, value)
        if not valid:
            errors.append(f"{key}: {reason}")

    return len(errors) == 0, errors


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
    'TRAIL_ENABLED': {'type': bool},
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
    # v5.1 P2-16: ATR-based SL/TP
    'SL_ATR_MULTIPLIER': {'type': (int, float), 'min': 0.5, 'max': 5.0},
    'SL_MIN_PCT': {'type': (int, float), 'min': 0.5, 'max': 10.0},
    'SL_MAX_PCT': {'type': (int, float), 'min': 1.0, 'max': 15.0},
    'TP_ATR_MULTIPLIER': {'type': (int, float), 'min': 1.0, 'max': 10.0},
    'TP_MIN_PCT': {'type': (int, float), 'min': 1.0, 'max': 20.0},
    'TP_MAX_PCT': {'type': (int, float), 'min': 2.0, 'max': 30.0},
    # v5.1 P2-16: Signal Queue
    'QUEUE_ATR_MULT': {'type': (int, float), 'min': 0.1, 'max': 3.0},
    'QUEUE_MIN_DEVIATION': {'type': (int, float), 'min': 0.1, 'max': 3.0},
    'QUEUE_MAX_DEVIATION': {'type': (int, float), 'min': 0.5, 'max': 5.0},
    'QUEUE_MAX_SIZE': {'type': int, 'min': 1, 'max': 20},
    'QUEUE_FRESHNESS_WINDOW': {'type': int, 'min': 5, 'max': 120},
    # v5.1 P2-16: Gap Filter
    'GAP_MAX_UP': {'type': (int, float), 'min': 0.5, 'max': 10.0},
    'GAP_MAX_DOWN': {'type': (int, float), 'min': -15.0, 'max': -1.0},
    # v5.1 P2-16: Low Risk Mode
    'LOW_RISK_GAP_MAX_UP': {'type': (int, float), 'min': 0.5, 'max': 5.0},
    'LOW_RISK_MIN_SCORE': {'type': int, 'min': 50, 'max': 100},
    'LOW_RISK_POSITION_SIZE_PCT': {'type': (int, float), 'min': 5, 'max': 40},
    'LOW_RISK_MAX_ATR_PCT': {'type': (int, float), 'min': 1.0, 'max': 8.0},
    # v5.1 P2-16: Regime Filter
    'REGIME_SMA_PERIOD': {'type': int, 'min': 5, 'max': 50},
    'REGIME_RSI_MIN': {'type': (int, float), 'min': 20, 'max': 60},
    'REGIME_RETURN_5D_MIN': {'type': (int, float), 'min': -10.0, 'max': 0.0},
    'REGIME_VIX_MAX': {'type': (int, float), 'min': 15.0, 'max': 50.0},
    # v5.1 P2-16: Risk Parity
    'RISK_BUDGET_PCT': {'type': (int, float), 'min': 0.5, 'max': 5.0},
    # v5.1 P2-16: Sector
    'MAX_SECTOR_CONSECUTIVE_LOSS': {'type': int, 'min': 1, 'max': 5},
    'SECTOR_COOLDOWN_DAYS': {'type': int, 'min': 1, 'max': 10},
    # v5.1 P2-16: Afternoon
    'AFTERNOON_MIN_SCORE': {'type': int, 'min': 50, 'max': 100},
    # v5.3: Quant Research Findings
    'STOCK_D_FILTER_ENABLED': {'type': bool},
    'BEAR_DD_CONTROL_EXEMPT': {'type': bool},
    # v6.2: Stock Quality Filters
    'MAX_RSI_ENTRY': {'type': (int, float), 'min': 50, 'max': 80},
    'AVOID_MOM_RANGE': {'type': list},  # [min, max] momentum range to skip
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


def apply_config(engine, config: Optional[Dict[str, Any]] = None, broker=None):
    """
    Apply config values to an AutoTradingEngine instance.
    Only sets attributes that exist in config AND as class attributes.
    Validates type and bounds before applying.

    Args:
        engine: AutoTradingEngine instance
        config: Config dict (loads from file if None)
        broker: Optional BrokerInterface instance. If provided,
                max_slippage_pct → MAX_SLIPPAGE_PCT is applied to the broker
                instead of the engine.
    """
    if config is None:
        config = load_config()

    if not config:
        return

    # Keys that should be applied to the broker, not the engine
    BROKER_KEYS = {'MAX_SLIPPAGE_PCT'}

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

        # Determine target: broker or engine
        target = engine
        if attr_name in BROKER_KEYS and broker is not None:
            target = broker

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
