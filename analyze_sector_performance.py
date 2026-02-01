#!/usr/bin/env python3
"""
Sector Performance Analysis
Analyze major sector ETFs to understand current market regimes by sector
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
from api.data_manager import DataManager

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def calculate_rsi(prices, period=14):
    """Calculate RSI indicator"""
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period

    if down == 0:
        return 100

    rs = up / down
    rsi = 100 - (100 / (1 + rs))

    # Calculate full RSI
    up_avg = up
    down_avg = down

    for delta in deltas[period+1:]:
        if delta > 0:
            up_val = delta
            down_val = 0
        else:
            up_val = 0
            down_val = -delta

        up_avg = (up_avg * (period - 1) + up_val) / period
        down_avg = (down_avg * (period - 1) + down_val) / period

    if down_avg == 0:
        return 100

    rs = up_avg / down_avg
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_momentum_indicators(df):
    """Calculate momentum indicators from price data"""
    if df.empty or len(df) < 20:
        return None

    # Get closing prices
    prices = df['close'].values

    # 20-day return
    return_20d = ((prices[-1] - prices[0]) / prices[0]) * 100

    # 5-day return
    if len(prices) >= 5:
        return_5d = ((prices[-1] - prices[-5]) / prices[-5]) * 100
    else:
        return_5d = return_20d

    # RSI
    rsi = calculate_rsi(prices, period=14)

    # Moving averages
    ma_10 = np.mean(prices[-10:]) if len(prices) >= 10 else prices[-1]
    ma_20 = np.mean(prices)

    # Price relative to MA
    price_vs_ma10 = ((prices[-1] - ma_10) / ma_10) * 100
    price_vs_ma20 = ((prices[-1] - ma_20) / ma_20) * 100

    # Volatility (standard deviation of returns)
    returns = np.diff(prices) / prices[:-1]
    volatility = np.std(returns) * 100

    return {
        'return_20d': return_20d,
        'return_5d': return_5d,
        'rsi': rsi,
        'price_vs_ma10': price_vs_ma10,
        'price_vs_ma20': price_vs_ma20,
        'volatility': volatility,
        'current_price': prices[-1],
        'ma_10': ma_10,
        'ma_20': ma_20
    }


def determine_regime(metrics):
    """
    Determine market regime based on multiple indicators

    Regime Classification:
    - STRONG BULL: Uptrend with strong momentum
    - BULL: Positive trend
    - SIDEWAYS: Consolidation/neutral
    - BEAR: Negative trend
    - STRONG BEAR: Downtrend with strong bearish momentum
    """
    if not metrics:
        return 'UNKNOWN'

    return_20d = metrics['return_20d']
    return_5d = metrics['return_5d']
    rsi = metrics['rsi']
    price_vs_ma10 = metrics['price_vs_ma10']
    price_vs_ma20 = metrics['price_vs_ma20']

    # Strong Bull: Strong uptrend with momentum
    if (return_20d > 5 and return_5d > 2 and
        price_vs_ma10 > 1 and price_vs_ma20 > 2 and rsi > 60):
        return 'STRONG BULL'

    # Bull: Positive trend
    elif (return_20d > 2 and price_vs_ma20 > 0 and rsi > 50):
        return 'BULL'

    # Strong Bear: Strong downtrend with momentum
    elif (return_20d < -5 and return_5d < -2 and
          price_vs_ma10 < -1 and price_vs_ma20 < -2 and rsi < 40):
        return 'STRONG BEAR'

    # Bear: Negative trend
    elif (return_20d < -2 and price_vs_ma20 < 0 and rsi < 50):
        return 'BEAR'

    # Sideways: Mixed signals or consolidation
    else:
        return 'SIDEWAYS'


def analyze_sectors():
    """Analyze all major sector ETFs"""

    # Major Sector ETFs
    sectors = {
        'SPY': 'S&P 500 (Market)',
        'XLK': 'Technology',
        'XLE': 'Energy',
        'XLF': 'Financials',
        'XLV': 'Healthcare',
        'XLY': 'Consumer Discretionary',
        'XLP': 'Consumer Staples',
        'XLI': 'Industrials',
        'XLU': 'Utilities',
        'XLB': 'Materials',
        'XLC': 'Communications',
        'XLRE': 'Real Estate'
    }

    logger.info("=" * 80)
    logger.info("SECTOR PERFORMANCE ANALYSIS - January 1, 2026")
    logger.info("=" * 80)
    logger.info("")

    # Initialize data manager
    dm = DataManager()

    results = []

    for symbol, sector_name in sectors.items():
        try:
            logger.info(f"Analyzing {symbol} ({sector_name})...")

            # Get 30 days of data to ensure we have 20 trading days
            df = dm.get_price_data(symbol, period='1mo', interval='1d')

            if df.empty:
                logger.warning(f"No data available for {symbol}")
                continue

            # Take last 20 rows
            df = df.tail(20)

            # Calculate metrics
            metrics = calculate_momentum_indicators(df)

            if not metrics:
                logger.warning(f"Could not calculate metrics for {symbol}")
                continue

            # Determine regime
            regime = determine_regime(metrics)

            results.append({
                'symbol': symbol,
                'sector': sector_name,
                'regime': regime,
                **metrics
            })

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            continue

    # Convert to DataFrame
    df_results = pd.DataFrame(results)

    # Print detailed results
    logger.info("")
    logger.info("=" * 80)
    logger.info("DETAILED SECTOR ANALYSIS")
    logger.info("=" * 80)
    logger.info("")

    # Sort by return_20d descending
    df_results = df_results.sort_values('return_20d', ascending=False)

    for _, row in df_results.iterrows():
        logger.info(f"{row['symbol']:6s} | {row['sector']:25s} | {row['regime']:12s}")
        logger.info(f"  20-Day Return: {row['return_20d']:>7.2f}%  |  5-Day Return: {row['return_5d']:>7.2f}%")
        logger.info(f"  RSI: {row['rsi']:>6.1f}  |  Price vs MA20: {row['price_vs_ma20']:>7.2f}%  |  Volatility: {row['volatility']:>6.2f}%")
        logger.info("")

    # Summary by regime
    logger.info("=" * 80)
    logger.info("REGIME SUMMARY")
    logger.info("=" * 80)
    logger.info("")

    regime_counts = df_results['regime'].value_counts()

    for regime in ['STRONG BULL', 'BULL', 'SIDEWAYS', 'BEAR', 'STRONG BEAR']:
        count = regime_counts.get(regime, 0)
        if count > 0:
            sectors_in_regime = df_results[df_results['regime'] == regime]['symbol'].tolist()
            logger.info(f"{regime:12s}: {count} sectors - {', '.join(sectors_in_regime)}")

    # Market vs Sector comparison
    logger.info("")
    logger.info("=" * 80)
    logger.info("MARKET vs SECTOR COMPARISON")
    logger.info("=" * 80)
    logger.info("")

    spy_row = df_results[df_results['symbol'] == 'SPY']
    if not spy_row.empty:
        spy_return = spy_row.iloc[0]['return_20d']
        spy_regime = spy_row.iloc[0]['regime']

        logger.info(f"SPY (Market Benchmark): {spy_return:.2f}% | {spy_regime}")
        logger.info("")
        logger.info("Sectors vs Market:")
        logger.info("")

        for _, row in df_results.iterrows():
            if row['symbol'] == 'SPY':
                continue

            relative_performance = row['return_20d'] - spy_return
            outperform = "OUTPERFORM" if relative_performance > 0 else "UNDERPERFORM"

            logger.info(f"  {row['symbol']:6s} ({row['sector']:25s}): "
                       f"{row['return_20d']:>7.2f}% ({relative_performance:>+6.2f}%) - {outperform}")

    # Sector rotation insights
    logger.info("")
    logger.info("=" * 80)
    logger.info("SECTOR ROTATION INSIGHTS")
    logger.info("=" * 80)
    logger.info("")

    # Strongest sectors (top 3)
    top_sectors = df_results.head(3)
    logger.info("STRONGEST SECTORS (20-Day Performance):")
    for _, row in top_sectors.iterrows():
        if row['symbol'] != 'SPY':
            logger.info(f"  {row['symbol']:6s} - {row['sector']:25s}: {row['return_20d']:>7.2f}% ({row['regime']})")

    logger.info("")

    # Weakest sectors (bottom 3)
    bottom_sectors = df_results.tail(3).iloc[::-1]  # Reverse to show weakest first
    logger.info("WEAKEST SECTORS (20-Day Performance):")
    for _, row in bottom_sectors.iterrows():
        if row['symbol'] != 'SPY':
            logger.info(f"  {row['symbol']:6s} - {row['sector']:25s}: {row['return_20d']:>7.2f}% ({row['regime']})")

    # Trading recommendations
    logger.info("")
    logger.info("=" * 80)
    logger.info("TRADING IMPLICATIONS")
    logger.info("=" * 80)
    logger.info("")

    bull_sectors = df_results[df_results['regime'].isin(['BULL', 'STRONG BULL'])]
    bear_sectors = df_results[df_results['regime'].isin(['BEAR', 'STRONG BEAR'])]

    if not bull_sectors.empty:
        logger.info("SECTORS TO FOCUS ON (Bullish):")
        for _, row in bull_sectors.iterrows():
            if row['symbol'] != 'SPY':
                logger.info(f"  - {row['sector']} ({row['symbol']}): Look for long opportunities")

    logger.info("")

    if not bear_sectors.empty:
        logger.info("SECTORS TO AVOID (Bearish):")
        for _, row in bear_sectors.iterrows():
            if row['symbol'] != 'SPY':
                logger.info(f"  - {row['sector']} ({row['symbol']}): Avoid longs, consider shorts")

    # Save results
    output_file = 'sector_analysis_results.csv'
    df_results.to_csv(output_file, index=False)
    logger.info("")
    logger.info(f"Results saved to: {output_file}")

    return df_results


if __name__ == '__main__':
    analyze_sectors()
