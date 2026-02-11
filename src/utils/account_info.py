"""
Account Info from Alpaca - Single Source of Truth
==================================================

This module provides real-time account information from Alpaca broker.
Use this instead of hardcoding or calculating values locally.

IMPORTANT: Respects simulated_capital from config/trading.yaml
If simulated_capital is set, it limits the capital to that amount.

Usage:
    from utils.account_info import get_buying_power, get_account_equity
"""

from typing import Dict, Any, Optional
from loguru import logger
import os
import yaml


# Cache for account info (to reduce API calls)
_account_cache = {
    'data': None,
    'timestamp': None,
    'ttl_seconds': 300  # Cache for 5 minutes (PDT count doesn't change frequently)
}

# Cache for config
_config_cache = None


def _load_simulated_capital() -> Optional[float]:
    """
    Load simulated_capital from config/trading.yaml.

    If set, this limits the capital used for trading regardless of actual account value.
    This allows testing strategies with limited capital on a larger account.

    Returns:
        Simulated capital amount or None if not set
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    try:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'config', 'trading.yaml'
        )

        with open(config_path) as f:
            config = yaml.safe_load(f)

        simulated_capital = config.get('simulated_capital')

        if simulated_capital:
            logger.info(f"💰 Simulated capital: ${simulated_capital:,} (locked)")

        _config_cache = simulated_capital
        return simulated_capital

    except Exception as e:
        logger.debug(f"Could not load simulated_capital from config: {e}")
        _config_cache = None
        return None


def get_account_info_from_broker(broker=None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Get real-time account information from Alpaca.

    Args:
        broker: Broker interface (AlpacaBroker instance)
        force_refresh: Force refresh from API (ignore cache)

    Returns:
        Dict with:
            - equity: Total account equity
            - cash: Available cash
            - buying_power: Total buying power (includes margin)
            - multiplier: Margin multiplier (2 or 4)
            - day_trade_count: Number of day trades (rolling 5 days)
            - pattern_day_trader: True if flagged as PDT
            - long_market_value: Value of long positions
            - initial_margin: Initial margin requirement
            - maintenance_margin: Maintenance margin requirement
            - source: "alpaca" or "fallback"

    Example:
        >>> from engine.brokers import AlpacaBroker
        >>> broker = AlpacaBroker(paper=True)
        >>> info = get_account_info_from_broker(broker)
        >>> print(f"Buying Power: ${info['buying_power']:,.2f}")
    """
    import time

    # Check cache first
    if not force_refresh and _account_cache['data'] is not None:
        if _account_cache['timestamp'] is not None:
            age = time.time() - _account_cache['timestamp']
            if age < _account_cache['ttl_seconds']:
                logger.debug(f"Account info: cache hit (age: {age:.0f}s, PDT: {_account_cache['data']['day_trade_count']}/3)")
                return _account_cache['data']

    # Get from broker
    try:
        if broker is None:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)

        account = broker.get_account()

        result = {
            'equity': float(getattr(account, 'equity', 0)),
            'cash': float(getattr(account, 'cash', 0)),
            'buying_power': float(getattr(account, 'buying_power', 0)),
            'multiplier': float(getattr(account, 'multiplier', 1)),
            'day_trade_count': int(getattr(account, 'day_trade_count', 0)),
            'pattern_day_trader': bool(getattr(account, 'pattern_day_trader', False)),
            'long_market_value': float(getattr(account, 'long_market_value', 0)),
            'initial_margin': float(getattr(account, 'initial_margin', 0)),
            'maintenance_margin': float(getattr(account, 'maintenance_margin', 0)),
            'source': 'alpaca'
        }

        # Cache it
        _account_cache['data'] = result
        _account_cache['timestamp'] = time.time()

        logger.debug(f"✅ Account info: fresh data (PDT: {result['day_trade_count']}/3, equity: ${result['equity']:,.0f})")

        return result

    except Exception as e:
        logger.warning(f"⚠️ Failed to get account info from Alpaca (using fallback): {type(e).__name__}: {e}")
        logger.warning("   → PDT status may show as 'N/A' until next successful API call")

        # Fallback values
        result = {
            'equity': 0,
            'cash': 0,
            'buying_power': 0,
            'multiplier': 1,
            'day_trade_count': 0,
            'pattern_day_trader': False,
            'long_market_value': 0,
            'initial_margin': 0,
            'maintenance_margin': 0,
            'source': 'fallback'
        }

        return result


def get_buying_power(broker=None, respect_simulated_capital: bool = True) -> float:
    """
    Get current buying power from Alpaca.

    This is the total amount available to buy securities,
    including margin if account is approved for margin trading.

    IMPORTANT: If simulated_capital is set in config, returns the LESSER of:
    - Real buying power from Alpaca
    - Simulated capital from config

    Args:
        broker: Broker interface (optional)
        respect_simulated_capital: If True, respects simulated_capital setting (default: True)

    Returns:
        Buying power in dollars (limited by simulated_capital if set)

    Example:
        >>> bp = get_buying_power()  # Returns min($4000, real_bp) if simulated_capital=$4000
        >>> max_position = bp * 0.1  # Use 10% of (limited) buying power
    """
    info = get_account_info_from_broker(broker)
    real_buying_power = info['buying_power']

    if respect_simulated_capital:
        simulated_capital = _load_simulated_capital()
        if simulated_capital:
            # Use the LESSER of simulated capital and real buying power
            return min(simulated_capital, real_buying_power)

    return real_buying_power


def get_account_equity(broker=None, respect_simulated_capital: bool = True) -> float:
    """
    Get current account equity from Alpaca.

    Equity = Cash + Long Market Value - Short Market Value

    IMPORTANT: If simulated_capital is set in config, returns the LESSER of:
    - Real equity from Alpaca
    - Simulated capital from config

    Args:
        broker: Broker interface (optional)
        respect_simulated_capital: If True, respects simulated_capital setting (default: True)

    Returns:
        Account equity in dollars (limited by simulated_capital if set)
    """
    info = get_account_info_from_broker(broker)
    real_equity = info['equity']

    if respect_simulated_capital:
        simulated_capital = _load_simulated_capital()
        if simulated_capital:
            # Use the LESSER of simulated capital and real equity
            return min(simulated_capital, real_equity)

    return real_equity


def get_margin_multiplier(broker=None) -> float:
    """
    Get margin multiplier from Alpaca.

    Returns:
        Margin multiplier (1.0 for cash account, 2.0 or 4.0 for margin)
    """
    info = get_account_info_from_broker(broker)
    return info['multiplier']


def calculate_max_position_value(broker=None, pct_of_equity: float = 10.0) -> float:
    """
    Calculate maximum position value based on account limits.

    Uses the LESSER of:
    1. X% of equity (risk management)
    2. Available buying power (broker limit)

    IMPORTANT: Respects simulated_capital from config.
    If simulated_capital=$4000, equity is capped at $4000.

    Args:
        broker: Broker interface (optional)
        pct_of_equity: Max % of equity per position (default 10%)

    Returns:
        Maximum position value in dollars

    Example:
        >>> # With simulated_capital=$4000
        >>> max_value = calculate_max_position_value(pct_of_equity=10.0)
        >>> # Returns: 10% of $4,000 = $400
        >>> shares = int(max_value / stock_price)
    """
    # Get equity and buying power (respects simulated_capital)
    equity = get_account_equity(broker, respect_simulated_capital=True)
    buying_power = get_buying_power(broker, respect_simulated_capital=True)

    # Calculate max based on equity %
    max_from_equity = equity * (pct_of_equity / 100.0)

    # Take the lesser of the two (respect both risk limit and broker limit)
    max_value = min(max_from_equity, buying_power)

    return max_value


def clear_account_cache():
    """Clear account info cache (useful for testing or forcing refresh)"""
    global _account_cache
    _account_cache['data'] = None
    _account_cache['timestamp'] = None
