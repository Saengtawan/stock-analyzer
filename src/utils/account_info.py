"""
Account Info from Alpaca - Single Source of Truth
==================================================

This module provides real-time account information from Alpaca broker.
Use this instead of hardcoding or calculating values locally.

Usage:
    from utils.account_info import get_buying_power, get_account_equity
"""

from typing import Dict, Any, Optional
from loguru import logger


# Cache for account info (to reduce API calls)
_account_cache = {
    'data': None,
    'timestamp': None,
    'ttl_seconds': 60  # Cache for 1 minute
}


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

        return result

    except Exception as e:
        logger.warning(f"Failed to get account info from Alpaca: {e}, using fallback")

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


def get_buying_power(broker=None) -> float:
    """
    Get current buying power from Alpaca.

    This is the total amount available to buy securities,
    including margin if account is approved for margin trading.

    Args:
        broker: Broker interface (optional)

    Returns:
        Buying power in dollars

    Example:
        >>> bp = get_buying_power()
        >>> max_position = bp * 0.1  # Use 10% of buying power
    """
    info = get_account_info_from_broker(broker)
    return info['buying_power']


def get_account_equity(broker=None) -> float:
    """
    Get current account equity from Alpaca.

    Equity = Cash + Long Market Value - Short Market Value

    Args:
        broker: Broker interface (optional)

    Returns:
        Account equity in dollars
    """
    info = get_account_info_from_broker(broker)
    return info['equity']


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

    Args:
        broker: Broker interface (optional)
        pct_of_equity: Max % of equity per position (default 10%)

    Returns:
        Maximum position value in dollars

    Example:
        >>> max_value = calculate_max_position_value(pct_of_equity=10.0)
        >>> shares = int(max_value / stock_price)
    """
    info = get_account_info_from_broker(broker)

    equity = info['equity']
    buying_power = info['buying_power']

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
