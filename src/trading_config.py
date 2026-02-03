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
from typing import Dict, Any, Optional
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


def apply_config(engine, config: Optional[Dict[str, Any]] = None):
    """
    Apply config values to an AutoTradingEngine instance.
    Only sets attributes that exist in config AND as class attributes.

    Args:
        engine: AutoTradingEngine instance
        config: Config dict (loads from file if None)
    """
    if config is None:
        config = load_config()

    if not config:
        return

    # Map YAML keys → class attribute names
    # Keys in YAML are lowercase_snake; class attrs are UPPERCASE_SNAKE
    applied = 0
    for key, value in config.items():
        attr_name = key.upper()
        if hasattr(engine, attr_name) and value is not None:
            old_val = getattr(engine, attr_name)
            if old_val != value:
                setattr(engine, attr_name, value)
                logger.debug(f"Config: {attr_name} = {value} (was {old_val})")
            applied += 1

    logger.info(f"Config applied: {applied} parameters")
