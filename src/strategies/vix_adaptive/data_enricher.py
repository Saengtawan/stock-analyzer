"""
VIX Adaptive Data Enricher

Adds required indicators to stock data for VIX Adaptive Strategy.

Required indicators:
- score: Calculated by screener
- atr_pct: ATR as % of price
- yesterday_dip: Previous day return
- return_2d: 2-day return (bounce confirmation)
- dip_from_3d_high: Dip from 3-day high
"""

import pandas as pd
import numpy as np
from typing import Dict
from loguru import logger


def enrich_data_for_vix_adaptive(
    data_cache: Dict[str, pd.DataFrame],
    calculate_score_func=None
) -> Dict[str, pd.DataFrame]:
    """
    Enrich stock data with VIX Adaptive indicators.

    Args:
        data_cache: Dict of {symbol: DataFrame} with OHLCV data
        calculate_score_func: Optional function to calculate score

    Returns:
        Enriched data_cache with additional indicators
    """
    enriched = {}

    for symbol, df in data_cache.items():
        try:
            df_enriched = df.copy()

            # Calculate ATR if not present
            if 'atr' not in df_enriched.columns:
                df_enriched['atr'] = calculate_atr(df_enriched)

            # Calculate atr_pct
            if 'atr_pct' not in df_enriched.columns:
                df_enriched['atr_pct'] = (df_enriched['atr'] / df_enriched['close']) * 100

            # Calculate yesterday_dip (previous day return)
            if 'yesterday_dip' not in df_enriched.columns:
                daily_return = df_enriched['close'].pct_change() * 100
                df_enriched['yesterday_dip'] = daily_return.shift(1)

            # Calculate return_2d (2-day return for bounce confirmation)
            if 'return_2d' not in df_enriched.columns:
                df_enriched['return_2d'] = df_enriched['close'].pct_change(2) * 100

            # Calculate dip_from_3d_high
            if 'dip_from_3d_high' not in df_enriched.columns:
                high_3d = df_enriched['high'].rolling(3).max()
                df_enriched['dip_from_3d_high'] = (
                    (df_enriched['close'] - high_3d) / high_3d * 100
                )

            # Calculate score if function provided and score not present
            if calculate_score_func and 'score' not in df_enriched.columns:
                # This would require more context - skip for now
                pass

            enriched[symbol] = df_enriched

        except Exception as e:
            logger.warning(f"Failed to enrich {symbol}: {e}")
            enriched[symbol] = df  # Use original if enrichment fails

    return enriched


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate ATR (Average True Range).

    Args:
        df: DataFrame with high, low, close columns
        period: ATR period (default 14)

    Returns:
        ATR series
    """
    high = df['high']
    low = df['low']
    close = df['close']

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR = EMA of TR
    atr = tr.ewm(span=period, adjust=False).mean()

    return atr


def validate_vix_indicators(df: pd.DataFrame, symbol: str = None) -> bool:
    """
    Validate that all required VIX Adaptive indicators exist.

    Args:
        df: DataFrame to validate
        symbol: Optional symbol name for logging

    Returns:
        True if all required indicators present, False otherwise
    """
    required = ['score', 'atr_pct', 'yesterday_dip', 'return_2d', 'dip_from_3d_high']

    missing = [ind for ind in required if ind not in df.columns]

    if missing:
        sym_str = f"{symbol}: " if symbol else ""
        logger.warning(f"{sym_str}Missing VIX indicators: {missing}")
        return False

    return True


def calculate_simple_score(df: pd.DataFrame) -> pd.Series:
    """
    Calculate a simple technical score (0-100).

    Components:
    - SMA trend (0-30): Price above SMA20, SMA50, SMA200
    - Volume (0-30): Volume vs 20-day average
    - Momentum (0-40): 20-day return

    Args:
        df: DataFrame with OHLCV data

    Returns:
        Score series (0-100)
    """
    close = df['close']
    volume = df['volume']

    # SMA trend (0-30 points)
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()

    score = pd.Series(0.0, index=df.index)

    # Above SMA20: +10
    score += (close > sma_20).astype(int) * 10

    # Above SMA50: +10
    score += (close > sma_50).astype(int) * 10

    # Above SMA200: +10
    score += (close > sma_200).astype(int) * 10

    # Volume score (0-30)
    volume_20d_avg = volume.rolling(20).mean()
    volume_ratio = volume / volume_20d_avg
    volume_score = volume_ratio.clip(0.5, 2.5)
    volume_score = ((volume_score - 0.5) / 2.0) * 30
    score += volume_score

    # Momentum score (0-40)
    return_20d = close.pct_change(20) * 100
    momentum_score = return_20d.clip(-20, 20)
    momentum_score = ((momentum_score + 20) / 40) * 40
    score += momentum_score

    # Clip to 0-100
    score = score.clip(0, 100)

    return score


def add_vix_indicators_to_cache(data_cache: Dict[str, pd.DataFrame]) -> int:
    """
    Add VIX Adaptive indicators to existing data_cache in-place.

    Args:
        data_cache: Dict of {symbol: DataFrame} to modify

    Returns:
        Number of stocks successfully enriched
    """
    success_count = 0

    for symbol, df in data_cache.items():
        try:
            # Calculate ATR if not present
            if 'atr' not in df.columns:
                df['atr'] = calculate_atr(df)

            # Calculate atr_pct
            if 'atr_pct' not in df.columns:
                df['atr_pct'] = (df['atr'] / df['close']) * 100

            # Calculate yesterday_dip
            if 'yesterday_dip' not in df.columns:
                daily_return = df['close'].pct_change() * 100
                df['yesterday_dip'] = daily_return.shift(1)

            # Calculate return_2d
            if 'return_2d' not in df.columns:
                df['return_2d'] = df['close'].pct_change(2) * 100

            # Calculate dip_from_3d_high
            if 'dip_from_3d_high' not in df.columns:
                high_3d = df['high'].rolling(3).max()
                df['dip_from_3d_high'] = (
                    (df['close'] - high_3d) / high_3d * 100
                )

            # Calculate score if not present
            if 'score' not in df.columns:
                df['score'] = calculate_simple_score(df)

            success_count += 1

        except Exception as e:
            logger.warning(f"Failed to add VIX indicators to {symbol}: {e}")

    logger.info(f"✅ Added VIX indicators to {success_count}/{len(data_cache)} stocks")

    return success_count
