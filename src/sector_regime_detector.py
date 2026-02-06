"""
Sector Regime Detector v5.4
Analyzes sector performance to determine sector-specific market regimes.
Uses ETF returns (market-cap weighted) which match Yahoo Finance sector returns.
v5.4: Realtime sector data with 5-min cache during market hours.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger


class SectorRegimeDetector:
    """
    Detects market regime at the sector level for more granular trading decisions.
    v5.4: Realtime ETF data with 5-min cache during market hours for fast flip detection.
    """

    # v5.4: Realtime sector data during market hours
    SECTOR_REGIME_TTL_MINUTES = 5   # 5 min during market hours (detect fast BULL→BEAR flip)

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

    # v5.2: yfinance Sector API keys (for yf.Sector(key).top_companies)
    SECTOR_YF_KEYS = {
        'Technology': 'technology',
        'Energy': 'energy',
        'Financial Services': 'financial-services',
        'Healthcare': 'healthcare',
        'Consumer Cyclical': 'consumer-cyclical',
        'Consumer Defensive': 'consumer-defensive',
        'Industrials': 'industrials',
        'Utilities': 'utilities',
        'Basic Materials': 'basic-materials',
        'Communication Services': 'communication-services',
        'Real Estate': 'real-estate',
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
        # v5.2: Stock-based sector data
        self._sector_company_map = {}       # {sector_name: [symbols]}
        self._stock_based_1d_returns = {}   # {etf_symbol: float}

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
        if df.empty or len(df) < 21:
            return None

        # Get closing prices
        prices = df['close'].values

        # 20-day return
        return_20d = ((prices[-1] - prices[0]) / prices[0]) * 100

        # 1-day return (today's change)
        return_1d = ((prices[-1] - prices[-2]) / prices[-2]) * 100 if len(prices) >= 2 else 0

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
            'return_1d': return_1d,
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

        return_1d = metrics.get('return_1d', 0)
        return_20d = metrics['return_20d']
        return_5d = metrics['return_5d']
        rsi = metrics['rsi']
        price_vs_ma10 = metrics['price_vs_ma10']
        price_vs_ma20 = metrics['price_vs_ma20']

        # Strong Bull: Strong uptrend + recent momentum still positive
        # v5.1: require 1d > -1% (not selling off today)
        if (return_20d > 5 and return_5d > 2 and return_1d > -1 and
            price_vs_ma10 > 1 and price_vs_ma20 > 2 and rsi > 60):
            return 'STRONG BULL'

        # Bull: Positive trend + 5d not declining + today not crashing
        # v5.1: require 5d > 0% and 1d > -2%
        elif (return_20d > 2 and return_5d > 0 and return_1d > -2 and
              price_vs_ma20 > 0 and rsi > 50):
            return 'BULL'

        # Strong Bear: Strong downtrend with momentum
        elif (return_20d < -5 and return_5d < -2 and
              price_vs_ma10 < -1 and price_vs_ma20 < -2 and rsi < 40):
            return 'STRONG BEAR'

        # Bear: Negative trend
        elif (return_20d < -2 and price_vs_ma20 < 0 and rsi < 50):
            return 'BEAR'

        # v5.1: Short-term crash override — sharp daily/weekly drop → BEAR
        elif return_1d < -3 or return_5d < -5:
            return 'BEAR'

        # Sideways: Mixed signals or consolidation
        else:
            return 'SIDEWAYS'

    def _build_sector_company_map(self) -> Dict[str, List[str]]:
        """
        Build mapping of sector -> list of stock symbols using yf.Sector() (v5.2).
        Results are cached for 7 days via DataCache (data_type='sector_companies').
        """
        if self._sector_company_map:
            return self._sector_company_map

        if not self.data_manager:
            return {}

        all_symbols_by_sector = {}

        for sector_name, yf_key in self.SECTOR_YF_KEYS.items():
            try:
                companies_df = self.data_manager.get_sector_top_companies(yf_key)
                if companies_df is not None and not companies_df.empty:
                    symbols = companies_df.index.tolist()
                    all_symbols_by_sector[sector_name] = symbols
                else:
                    all_symbols_by_sector[sector_name] = []
            except Exception as e:
                logger.warning(f"Failed to get companies for '{sector_name}': {e}")
                all_symbols_by_sector[sector_name] = []

        self._sector_company_map = all_symbols_by_sector
        total = sum(len(v) for v in all_symbols_by_sector.values())
        logger.info(f"Built sector company map: {total} stocks across {len(all_symbols_by_sector)} sectors")
        return all_symbols_by_sector

    def _fetch_stock_based_1d_returns(self) -> Dict[str, float]:
        """
        Calculate stock-based equal-weight 1d returns per sector (v5.2).

        Process:
        1. Get sector->symbols mapping (cached 7 days)
        2. Batch download 5d daily prices for all ~550 symbols (1 API call, cached 20 min)
        3. Calculate 1d pct_change for each stock
        4. Equal-weight average per sector

        Returns:
            Dict mapping ETF symbol -> equal-weight 1d return (%).
            Empty dict on failure (caller falls back to ETF).
        """
        try:
            company_map = self._build_sector_company_map()
            if not company_map:
                return {}

            # Collect all unique symbols
            all_symbols = list(set(
                sym for symbols in company_map.values() for sym in symbols
            ))

            if not all_symbols:
                return {}

            logger.info(f"Batch downloading {len(all_symbols)} sector stocks for 1d returns...")

            batch_data = self.data_manager.batch_download_prices(
                all_symbols, period='5d', interval='1d', data_type='sector_price'
            )

            if batch_data is None or batch_data.empty:
                logger.warning("Batch download returned empty data")
                return {}

            # Extract Close prices (MultiIndex columns from batch download)
            if isinstance(batch_data.columns, pd.MultiIndex):
                if 'Close' in batch_data.columns.get_level_values(0):
                    closes = batch_data['Close']
                else:
                    logger.warning("No 'Close' column in batch data")
                    return {}
            else:
                closes = batch_data[['Close']] if 'Close' in batch_data.columns else batch_data

            if len(closes) < 2:
                logger.warning("Insufficient price data for 1d return calculation")
                return {}

            # Calculate 1d returns: latest pct_change * 100
            daily_returns = closes.pct_change().iloc[-1] * 100

            # Calculate equal-weight average per sector
            sector_1d_returns = {}
            for sector_name, symbols in company_map.items():
                etf = self.SECTOR_TO_ETF.get(sector_name)
                if not etf:
                    continue

                sector_returns = daily_returns.reindex(symbols).dropna()

                if len(sector_returns) == 0:
                    continue

                avg_return = float(sector_returns.mean())
                sector_1d_returns[etf] = avg_return
                logger.debug(
                    f"{sector_name} ({etf}): EW 1d = {avg_return:+.2f}% "
                    f"({len(sector_returns)}/{len(symbols)} stocks)"
                )

            self._stock_based_1d_returns = sector_1d_returns
            logger.info(f"Stock-based 1d returns calculated for {len(sector_1d_returns)} sectors")
            return sector_1d_returns

        except Exception as e:
            logger.error(f"Stock-based 1d return calculation failed: {e}")
            return {}

    def update_all_sectors(self, force_update: bool = False) -> Dict[str, str]:
        """
        Update regime for all sector ETFs.
        v5.4: Realtime ETF data with 5-min cache during market hours.
        """
        # Check if update needed (v5.4: 5-min TTL for fast flip detection)
        if not force_update and self.last_update:
            time_since_update = datetime.now() - self.last_update
            if time_since_update < timedelta(minutes=self.SECTOR_REGIME_TTL_MINUTES):
                logger.info(f"Using cached sector regimes (updated {time_since_update.seconds // 60}min ago)")
                return self.sector_regimes

        if not self.data_manager:
            logger.error("No data manager provided")
            return {}

        logger.info("Updating sector regimes (5-min realtime)...")

        for etf, sector_name in self.SECTOR_ETFS.items():
            try:
                # v5.4: Use sector_etf data_type for 5-min cache TTL
                df = self.data_manager.get_price_data(etf, period='1mo', interval='1d',
                                                       data_type='sector_etf')

                if df.empty:
                    logger.warning(f"No data for {etf}")
                    continue

                # Take last 21 rows (for true 20-day return: row[0] to row[20])
                df = df.tail(21)

                # Calculate metrics (ETF-based: 1d, 5d, 20d, RSI, MAs)
                metrics = self.calculate_sector_metrics(df)

                if not metrics:
                    logger.warning(f"Could not calculate metrics for {etf}")
                    continue

                # v5.3: Always use ETF returns (market-cap weighted like Yahoo)
                metrics['return_1d_source'] = 'etf'

                # Determine regime based on ETF metrics
                regime = self.determine_regime(metrics)

                self.sector_regimes[etf] = regime
                self.sector_metrics[etf] = metrics

                logger.info(
                    f"{etf} ({sector_name}): {regime} | "
                    f"1d: {metrics['return_1d']:+.1f}% | "
                    f"5d: {metrics['return_5d']:+.1f}% | "
                    f"20d: {metrics['return_20d']:+.2f}% | RSI: {metrics['rsi']:.1f}"
                )

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
                'Return_1d': metrics.get('return_1d', 0),
                'Return_5d': metrics.get('return_5d', 0),
                'Return_20d': metrics.get('return_20d', 0),
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
                    r1d = metrics.get('return_1d', 0)
                    r5d = metrics.get('return_5d', 0)
                    ret = metrics.get('return_20d', 0)
                    rsi = metrics.get('rsi', 50)
                    adj = self.REGIME_ADJUSTMENTS.get(regime, 0)
                    lines.append(f"  {etf} ({name:25s}) | 1d: {r1d:>+5.1f}% | 5d: {r5d:>+5.1f}% | 20d: {ret:>+6.2f}% | RSI: {rsi:>5.1f} | Adj: {adj:>+3d}")
                lines.append("")

        return "\n".join(lines)
