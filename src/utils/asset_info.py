"""
Asset Info from Alpaca - Tradability & Status Checks
=====================================================

This module checks if assets are tradable via Alpaca before creating signals.
Prevents order rejections due to halts, delistings, or restrictions.

Usage:
    from utils.asset_info import is_asset_tradable, get_asset_info
"""

from typing import Dict, Any, Tuple
from loguru import logger


# Cache for asset info (key: symbol, value: asset info dict)
_asset_cache = {}
_CACHE_TTL_SECONDS = 3600  # Cache for 1 hour (asset status doesn't change often)


def get_asset_info_from_broker(symbol: str, broker=None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Get asset information from Alpaca.

    Args:
        symbol: Stock symbol
        broker: Broker interface (optional)
        force_refresh: Force refresh from API (ignore cache)

    Returns:
        Dict with:
            - tradable: Can be traded
            - marginable: Can be bought on margin
            - shortable: Can be shorted
            - easy_to_borrow: Easy to borrow for shorting
            - fractionable: Can buy fractional shares
            - status: Asset status (active, inactive)
            - exchange: Exchange (e.g., NASDAQ, NYSE)
            - source: "alpaca" or "fallback"

    Example:
        >>> info = get_asset_info_from_broker('AAPL')
        >>> if not info['tradable']:
        >>>     print("AAPL is not tradable (halted or delisted)")
    """
    import time

    # Check cache first
    cache_key = symbol
    if not force_refresh and cache_key in _asset_cache:
        cached_data, cached_time = _asset_cache[cache_key]
        age = time.time() - cached_time
        if age < _CACHE_TTL_SECONDS:
            return cached_data

    # Get from broker
    try:
        if broker is None:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)

        asset = broker.get_asset(symbol)

        result = {
            'tradable': bool(getattr(asset, 'tradable', False)),
            'marginable': bool(getattr(asset, 'marginable', False)),
            'shortable': bool(getattr(asset, 'shortable', False)),
            'easy_to_borrow': bool(getattr(asset, 'easy_to_borrow', False)),
            'fractionable': bool(getattr(asset, 'fractionable', False)),
            'status': str(getattr(asset, 'status', 'unknown')),
            'exchange': str(getattr(asset, 'exchange', 'unknown')),
            'source': 'alpaca'
        }

        # Cache it
        _asset_cache[cache_key] = (result, time.time())

        return result

    except Exception as e:
        logger.warning(f"Failed to get asset info for {symbol} from Alpaca: {e}")

        # Fallback: assume tradable (will fail at order time if not)
        result = {
            'tradable': True,  # Optimistic assumption
            'marginable': False,
            'shortable': False,
            'easy_to_borrow': False,
            'fractionable': False,
            'status': 'unknown',
            'exchange': 'unknown',
            'source': 'fallback'
        }

        return result


def is_asset_tradable(symbol: str, broker=None, require_marginable: bool = False) -> Tuple[bool, str]:
    """
    Check if asset is tradable via Alpaca.

    Args:
        symbol: Stock symbol
        broker: Broker interface (optional)
        require_marginable: If True, also require asset to be marginable

    Returns:
        (is_tradable: bool, reason: str)

    Example:
        >>> tradable, reason = is_asset_tradable('AAPL')
        >>> if not tradable:
        >>>     print(f"Skip AAPL: {reason}")
    """
    info = get_asset_info_from_broker(symbol, broker)

    # Check if tradable
    if not info['tradable']:
        return False, f"Not tradable (status: {info['status']})"

    # Check if marginable (if required)
    if require_marginable and not info['marginable']:
        return False, "Not marginable"

    return True, "OK"


def is_asset_marginable(symbol: str, broker=None) -> bool:
    """
    Check if asset can be bought on margin.

    Args:
        symbol: Stock symbol
        broker: Broker interface (optional)

    Returns:
        True if asset is marginable
    """
    info = get_asset_info_from_broker(symbol, broker)
    return info['marginable']


def is_asset_shortable(symbol: str, broker=None) -> bool:
    """
    Check if asset can be shorted.

    Args:
        symbol: Stock symbol
        broker: Broker interface (optional)

    Returns:
        True if asset is shortable
    """
    info = get_asset_info_from_broker(symbol, broker)
    return info['shortable']


def can_buy_fractional(symbol: str, broker=None) -> bool:
    """
    Check if asset supports fractional shares.

    Args:
        symbol: Stock symbol
        broker: Broker interface (optional)

    Returns:
        True if fractional shares are supported
    """
    info = get_asset_info_from_broker(symbol, broker)
    return info['fractionable']


def validate_symbols_tradability(symbols: list, broker=None) -> Dict[str, Tuple[bool, str]]:
    """
    Validate tradability for multiple symbols at once.

    Args:
        symbols: List of stock symbols
        broker: Broker interface (optional)

    Returns:
        Dict mapping symbol to (is_tradable, reason)

    Example:
        >>> results = validate_symbols_tradability(['AAPL', 'GOOGL', 'TSLA'])
        >>> for symbol, (tradable, reason) in results.items():
        >>>     if not tradable:
        >>>         print(f"{symbol}: {reason}")
    """
    results = {}

    for symbol in symbols:
        tradable, reason = is_asset_tradable(symbol, broker)
        results[symbol] = (tradable, reason)

    return results


def clear_asset_cache(symbol: str = None):
    """
    Clear asset info cache.

    Args:
        symbol: Specific symbol to clear (if None, clear all)
    """
    global _asset_cache

    if symbol is None:
        _asset_cache = {}
    elif symbol in _asset_cache:
        del _asset_cache[symbol]
