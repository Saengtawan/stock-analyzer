"""
Sector Regime Detector
Analyzes sector ETF performance to determine sector-specific market regimes
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class SectorRegimeDetector:
    """
    Detects market regime at the sector level for more granular trading decisions
    """

    # v4.9.3: Configurable cache TTL
    SECTOR_REGIME_TTL_MINUTES = 20  # ปรับได้ง่าย (ลดจาก 60min)

    # Major sector ETFs
    SECTOR_ETFS = {
        'XLK': 'Technology',
        'XLE': 'Energy',
        'XLF': 'Financial Services',
        'XLV': 'Healthcare',
        'XLY': 'Consumer Cyclical',
        'XLP': 'Consumer Defensive',
        'XLI': 'Industrials',
        'XLU': 'Utilities',
        'XLB': 'Basic Materials',
        'XLC': 'Communication Services',
        'XLRE': 'Real Estate'
    }

    # Yahoo Finance sector names to ETF mapping
    SECTOR_TO_ETF = {
        'Technology': 'XLK',
        'Energy': 'XLE',
        'Financial Services': 'XLF',
        'Healthcare': 'XLV',
        'Consumer Cyclical': 'XLY',
        'Consumer Defensive': 'XLP',
        'Industrials': 'XLI',
        'Utilities': 'XLU',
        'Basic Materials': 'XLB',
        'Communication Services': 'XLC',
        'Real Estate': 'XLRE',
        # Aliases
        'Financial': 'XLF',
        'Financials': 'XLF',
        'Consumer Discretionary': 'XLY',
        'Consumer Staples': 'XLP',
        'Materials': 'XLB',
        'Communications': 'XLC',
        'Telecommunication Services': 'XLC'
    }

    # Regime score bonuses/penalties (v3.7 HYBRID - asymmetric defensive)
    # BEAR penalty > BULL bonus (defensive approach for swing trading)
    REGIME_ADJUSTMENTS = {
        'STRONG BULL': +5,   # Same as BULL (cap bonus)
        'BULL': +5,          # Small bonus
        'SIDEWAYS': 0,       # Neutral
        'BEAR': -10,         # Penalty (defensive)
        'STRONG BEAR': -10,  # Same as BEAR (cap penalty)
        'UNKNOWN': 0
    }

    # Confidence threshold adjustments
    CONFIDENCE_THRESHOLDS = {
        'STRONG BULL': 60,  # Relaxed
        'BULL': 60,         # Relaxed
        'SIDEWAYS': 65,     # Normal
        'BEAR': 70,         # Strict
        'STRONG BEAR': 75,  # Very strict
        'UNKNOWN': 65       # Normal
    }

    def __init__(self, data_manager=None):
        """
        Initialize sector regime detector

        Args:
            data_manager: DataManager instance for fetching price data
        """
        self.data_manager = data_manager
        self.sector_regimes = {}
        self.sector_metrics = {}
        self.last_update = None

    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50.0

        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period

        if down == 0:
            return 100.0

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
            return 100.0

        rs = up_avg / down_avg
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_sector_metrics(self, df: pd.DataFrame) -> Optional[Dict[str, float]]:
        """Calculate momentum indicators for a sector ETF"""
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
        rsi = self.calculate_rsi(prices, period=14)

        # Moving averages
        ma_10 = np.mean(prices[-10:]) if len(prices) >= 10 else prices[-1]
        ma_20 = np.mean(prices)

        # Price relative to MA
        price_vs_ma10 = ((prices[-1] - ma_10) / ma_10) * 100
        price_vs_ma20 = ((prices[-1] - ma_20) / ma_20) * 100

        return {
            'return_20d': return_20d,
            'return_5d': return_5d,
            'rsi': rsi,
            'price_vs_ma10': price_vs_ma10,
            'price_vs_ma20': price_vs_ma20,
            'current_price': prices[-1],
            'ma_10': ma_10,
            'ma_20': ma_20
        }

    def determine_regime(self, metrics: Dict[str, float]) -> str:
        """
        Determine sector regime based on metrics

        Returns:
            Regime: STRONG BULL, BULL, SIDEWAYS, BEAR, STRONG BEAR
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

    def update_all_sectors(self, force_update: bool = False) -> Dict[str, str]:
        """
        Update regime for all sector ETFs

        Args:
            force_update: Force update even if recently updated

        Returns:
            Dictionary mapping sector ETF to regime
        """
        # Check if update needed (v4.9.3: configurable TTL)
        if not force_update and self.last_update:
            time_since_update = datetime.now() - self.last_update
            if time_since_update < timedelta(minutes=self.SECTOR_REGIME_TTL_MINUTES):
                logger.info(f"Using cached sector regimes (updated {time_since_update.seconds // 60}min ago)")
                return self.sector_regimes

        if not self.data_manager:
            logger.error("No data manager provided")
            return {}

        logger.info("Updating sector regimes...")

        for etf, sector_name in self.SECTOR_ETFS.items():
            try:
                # Get 30 days to ensure 20 trading days
                df = self.data_manager.get_price_data(etf, period='1mo', interval='1d')

                if df.empty:
                    logger.warning(f"No data for {etf}")
                    continue

                # Take last 20 rows
                df = df.tail(20)

                # Calculate metrics
                metrics = self.calculate_sector_metrics(df)

                if not metrics:
                    logger.warning(f"Could not calculate metrics for {etf}")
                    continue

                # Determine regime
                regime = self.determine_regime(metrics)

                self.sector_regimes[etf] = regime
                self.sector_metrics[etf] = metrics

                logger.info(f"{etf} ({sector_name}): {regime} | Return: {metrics['return_20d']:.2f}% | RSI: {metrics['rsi']:.1f}")

            except Exception as e:
                logger.error(f"Error analyzing {etf}: {e}")
                continue

        self.last_update = datetime.now()
        return self.sector_regimes

    def get_sector_regime(self, sector: str) -> str:
        """
        Get regime for a specific sector

        Args:
            sector: Sector name (e.g., 'Technology', 'Healthcare') or ETF symbol (e.g., 'XLK')

        Returns:
            Regime string
        """
        # If it's already an ETF symbol
        if sector in self.SECTOR_ETFS:
            return self.sector_regimes.get(sector, 'UNKNOWN')

        # Map sector name to ETF
        etf = self.SECTOR_TO_ETF.get(sector)
        if etf:
            return self.sector_regimes.get(etf, 'UNKNOWN')

        return 'UNKNOWN'

    def get_regime_adjustment(self, sector: str) -> int:
        """
        Get score adjustment for a sector regime

        Args:
            sector: Sector name or ETF symbol

        Returns:
            Score adjustment (-15 to +15)
        """
        regime = self.get_sector_regime(sector)
        return self.REGIME_ADJUSTMENTS.get(regime, 0)

    def get_confidence_threshold(self, sector: str) -> int:
        """
        Get confidence threshold for a sector regime

        Args:
            sector: Sector name or ETF symbol

        Returns:
            Confidence threshold (60-75)
        """
        regime = self.get_sector_regime(sector)
        return self.CONFIDENCE_THRESHOLDS.get(regime, 65)

    def should_trade_sector(self, sector: str, min_regime_level: str = 'SIDEWAYS') -> bool:
        """
        Determine if a sector should be traded based on regime

        Args:
            sector: Sector name or ETF symbol
            min_regime_level: Minimum acceptable regime ('BULL', 'SIDEWAYS', 'BEAR')

        Returns:
            Boolean indicating if sector is tradeable
        """
        regime = self.get_sector_regime(sector)

        regime_hierarchy = {
            'STRONG BULL': 5,
            'BULL': 4,
            'SIDEWAYS': 3,
            'BEAR': 2,
            'STRONG BEAR': 1,
            'UNKNOWN': 3  # Treat as neutral
        }

        min_level_hierarchy = {
            'BULL': 4,
            'SIDEWAYS': 3,
            'BEAR': 2
        }

        regime_score = regime_hierarchy.get(regime, 3)
        min_score = min_level_hierarchy.get(min_regime_level, 3)

        return regime_score >= min_score

    def get_sector_summary(self) -> pd.DataFrame:
        """
        Get summary DataFrame of all sector regimes

        Returns:
            DataFrame with sector analysis
        """
        data = []

        for etf, sector_name in self.SECTOR_ETFS.items():
            regime = self.sector_regimes.get(etf, 'UNKNOWN')
            metrics = self.sector_metrics.get(etf, {})

            data.append({
                'ETF': etf,
                'Sector': sector_name,
                'Regime': regime,
                'Return_20d': metrics.get('return_20d', 0),
                'Return_5d': metrics.get('return_5d', 0),
                'RSI': metrics.get('rsi', 50),
                'Price_vs_MA20': metrics.get('price_vs_ma20', 0),
                'Score_Adjustment': self.REGIME_ADJUSTMENTS.get(regime, 0),
                'Confidence_Threshold': self.CONFIDENCE_THRESHOLDS.get(regime, 65)
            })

        df = pd.DataFrame(data)
        df = df.sort_values('Return_20d', ascending=False)

        return df

    def get_bull_sectors(self) -> list:
        """Get list of sectors in BULL or STRONG BULL regime"""
        return [etf for etf, regime in self.sector_regimes.items()
                if regime in ['BULL', 'STRONG BULL']]

    def get_bear_sectors(self) -> list:
        """Get list of sectors in BEAR or STRONG BEAR regime"""
        return [etf for etf, regime in self.sector_regimes.items()
                if regime in ['BEAR', 'STRONG BEAR']]

    def get_sector_etf(self, sector: str) -> Optional[str]:
        """
        Get ETF symbol for a sector name

        Args:
            sector: Sector name (e.g., 'Technology')

        Returns:
            ETF symbol or None
        """
        return self.SECTOR_TO_ETF.get(sector)

    def format_sector_report(self) -> str:
        """
        Generate formatted text report of sector regimes

        Returns:
            Multi-line string report
        """
        if not self.sector_regimes:
            return "No sector regime data available. Run update_all_sectors() first."

        lines = []
        lines.append("=" * 70)
        lines.append("SECTOR REGIME REPORT")
        lines.append(f"Updated: {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
        lines.append("")

        # Group by regime
        for regime in ['STRONG BULL', 'BULL', 'SIDEWAYS', 'BEAR', 'STRONG BEAR']:
            sectors = [(etf, self.SECTOR_ETFS[etf])
                      for etf, reg in self.sector_regimes.items()
                      if reg == regime]

            if sectors:
                lines.append(f"{regime}:")
                for etf, name in sectors:
                    metrics = self.sector_metrics.get(etf, {})
                    ret = metrics.get('return_20d', 0)
                    rsi = metrics.get('rsi', 50)
                    adj = self.REGIME_ADJUSTMENTS.get(regime, 0)
                    lines.append(f"  {etf} ({name:25s}) | Return: {ret:>6.2f}% | RSI: {rsi:>5.1f} | Score Adj: {adj:>+3d}")
                lines.append("")

        return "\n".join(lines)
