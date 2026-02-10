"""
Sector Regime Detector v6.0
Analyzes sector performance to determine sector-specific market regimes.
v6.0: Composite score approach (1d=45%, 5d=35%, 20d=20%) optimized for Dip-Bounce.
      Market-cap weighted 1d returns + 5-min cache during market hours.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger


class SectorRegimeDetector:
    """
    Detects market regime at the sector level for more granular trading decisions.
    v6.0: Composite score (1d=45%, 5d=35%, 20d=20%) optimized for Dip-Bounce strategy.
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
        # v5.5: Market-cap weighted sector data
        self._sector_company_map = {}       # {sector_name: [symbols]}
        self._sector_market_weights = {}    # {sector_name: {symbol: weight}}
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
        if df.empty or len(df) < 20:  # v6.17: Accept 20+ rows (not strict 21)
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

    # v6.0: Composite score weights for Dip-Bounce strategy (1-3 day hold)
    WEIGHT_1D = 0.45   # Entry timing - most important
    WEIGHT_5D = 0.35   # Short-term momentum
    WEIGHT_20D = 0.20  # Environment - least important for short hold

    # v6.0: Composite score thresholds
    THRESHOLD_STRONG_BULL = 4.0
    THRESHOLD_BULL = 1.5
    THRESHOLD_SIDEWAYS = -2.0
    THRESHOLD_BEAR = -4.0

    def calculate_composite_score(self, metrics: Dict[str, float]) -> float:
        """
        Calculate composite score from returns (v6.0).
        Weights: 1d=45%, 5d=35%, 20d=20% (optimized for Dip-Bounce 1-3 day hold)

        Returns:
            Composite score (higher = more bullish)
        """
        return_1d = metrics.get('return_1d', 0)
        return_5d = metrics.get('return_5d', 0)
        return_20d = metrics.get('return_20d', 0)

        score = (self.WEIGHT_1D * return_1d +
                 self.WEIGHT_5D * return_5d +
                 self.WEIGHT_20D * return_20d)

        # RSI bonus/penalty (small adjustment)
        rsi = metrics.get('rsi', 50)
        if rsi > 70:
            score += 0.5   # Overbought but strong
        elif rsi < 30:
            score -= 0.5   # Oversold and weak

        return score

    def determine_regime(self, metrics: Dict[str, float]) -> str:
        """
        Determine sector regime using composite score (v6.0).

        Composite Score = 0.45×1d + 0.35×5d + 0.20×20d
        Optimized for Dip-Bounce strategy with 1-3 day holding period.

        Returns:
            Regime: STRONG BULL, BULL, SIDEWAYS, BEAR, STRONG BEAR
        """
        if not metrics:
            return 'UNKNOWN'

        score = self.calculate_composite_score(metrics)
        metrics['composite_score'] = score  # Store for logging

        # v6.0: Composite score-based regime determination
        if score > self.THRESHOLD_STRONG_BULL:
            return 'STRONG BULL'
        elif score > self.THRESHOLD_BULL:
            return 'BULL'
        elif score > self.THRESHOLD_SIDEWAYS:
            return 'SIDEWAYS'
        elif score > self.THRESHOLD_BEAR:
            return 'BEAR'
        else:
            return 'STRONG BEAR'

    def _build_sector_company_map(self) -> Dict[str, List[str]]:
        """
        Build mapping of sector -> list of stock symbols using yf.Sector() (v5.5).
        Also extracts market weights for market-cap weighted calculations.
        Results are cached for 7 days via DataCache (data_type='sector_companies').
        """
        if self._sector_company_map and self._sector_market_weights:
            return self._sector_company_map

        if not self.data_manager:
            return {}

        all_symbols_by_sector = {}
        all_weights_by_sector = {}

        for sector_name, yf_key in self.SECTOR_YF_KEYS.items():
            try:
                companies_df = self.data_manager.get_sector_top_companies(yf_key)
                if companies_df is not None and not companies_df.empty:
                    symbols = companies_df.index.tolist()
                    all_symbols_by_sector[sector_name] = symbols
                    # v5.5: Extract market weights for weighted average
                    if 'market weight' in companies_df.columns:
                        weights = companies_df['market weight'].to_dict()
                        all_weights_by_sector[sector_name] = weights
                    else:
                        all_weights_by_sector[sector_name] = {}
                else:
                    all_symbols_by_sector[sector_name] = []
                    all_weights_by_sector[sector_name] = {}
            except Exception as e:
                logger.warning(f"Failed to get companies for '{sector_name}': {e}")
                all_symbols_by_sector[sector_name] = []
                all_weights_by_sector[sector_name] = {}

        self._sector_company_map = all_symbols_by_sector
        self._sector_market_weights = all_weights_by_sector
        total = sum(len(v) for v in all_symbols_by_sector.values())
        logger.info(f"Built sector company map: {total} stocks across {len(all_symbols_by_sector)} sectors (with market weights)")
        return all_symbols_by_sector

    def _fetch_stock_based_1d_returns(self) -> Dict[str, float]:
        """
        Calculate stock-based MARKET-CAP WEIGHTED 1d returns per sector (v5.5).

        Process:
        1. Get sector->symbols mapping with market weights (cached 7 days)
        2. Batch download 5d daily prices for all ~550 symbols (1 API call, cached 5 min)
        3. Calculate 1d pct_change for each stock
        4. Market-cap weighted average per sector (matches Yahoo methodology)

        Returns:
            Dict mapping ETF symbol -> market-cap weighted 1d return (%).
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
            daily_returns = closes.pct_change(fill_method=None).iloc[-1] * 100

            # v5.5: Calculate MARKET-CAP WEIGHTED average per sector
            sector_1d_returns = {}
            for sector_name, symbols in company_map.items():
                etf = self.SECTOR_TO_ETF.get(sector_name)
                if not etf:
                    continue

                # Get market weights for this sector
                weights = self._sector_market_weights.get(sector_name, {})

                # Filter to symbols with valid returns
                valid_returns = []
                valid_weights = []
                for sym in symbols:
                    if sym in daily_returns.index and pd.notna(daily_returns[sym]):
                        ret = daily_returns[sym]
                        wt = weights.get(sym, 0)
                        if wt > 0:  # Only include stocks with known weight
                            valid_returns.append(ret)
                            valid_weights.append(wt)

                if len(valid_returns) == 0:
                    continue

                # Normalize weights to sum to 1
                total_weight = sum(valid_weights)
                if total_weight > 0:
                    normalized_weights = [w / total_weight for w in valid_weights]
                    # Calculate weighted average
                    weighted_return = sum(r * w for r, w in zip(valid_returns, normalized_weights))
                else:
                    # Fallback to equal weight if no weights available
                    weighted_return = sum(valid_returns) / len(valid_returns)

                sector_1d_returns[etf] = float(weighted_return)
                logger.debug(
                    f"{sector_name} ({etf}): MCW 1d = {weighted_return:+.2f}% "
                    f"({len(valid_returns)}/{len(symbols)} stocks, weight={total_weight:.1%})"
                )

            self._stock_based_1d_returns = sector_1d_returns
            logger.info(f"Market-cap weighted 1d returns calculated for {len(sector_1d_returns)} sectors")
            return sector_1d_returns

        except Exception as e:
            logger.error(f"Stock-based 1d return calculation failed: {e}")
            return {}

    def update_all_sectors(self, force_update: bool = False) -> Dict[str, str]:
        """
        Update regime for all sector ETFs.
        v5.5: Market-cap weighted stock-based 1d returns (matches Yahoo methodology).
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

        logger.info("Updating sector regimes (5-min realtime, MCW)...")

        # v5.5: Fetch market-cap weighted stock-based 1d returns
        stock_1d_returns = self._fetch_stock_based_1d_returns()
        if stock_1d_returns:
            logger.info(f"Using market-cap weighted 1d returns for {len(stock_1d_returns)} sectors")
        else:
            logger.warning("MCW returns unavailable, using ETF-only")

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

                # v5.5: Override return_1d with market-cap weighted stock-based if available
                if etf in stock_1d_returns:
                    etf_1d = metrics['return_1d']
                    mcw_1d = stock_1d_returns[etf]
                    metrics['return_1d'] = mcw_1d
                    metrics['return_1d_source'] = 'mcw'
                    metrics['return_1d_etf'] = etf_1d
                else:
                    metrics['return_1d_source'] = 'etf'

                # Determine regime based on metrics
                regime = self.determine_regime(metrics)

                self.sector_regimes[etf] = regime
                self.sector_metrics[etf] = metrics

                src = "[M]" if metrics.get('return_1d_source') == 'mcw' else "[E]"
                score = metrics.get('composite_score', 0)
                logger.info(
                    f"{etf} ({sector_name}): {regime} (score={score:+.1f}) | "
                    f"1d{src}: {metrics['return_1d']:+.1f}% | "
                    f"5d: {metrics['return_5d']:+.1f}% | "
                    f"20d: {metrics['return_20d']:+.2f}%"
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
                'Return_1d_Source': metrics.get('return_1d_source', 'etf'),
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
                    src = "M" if metrics.get('return_1d_source') == 'mcw' else "E"
                    lines.append(f"  {etf} ({name:25s}) | 1d[{src}]: {r1d:>+5.1f}% | 5d: {r5d:>+5.1f}% | 20d: {ret:>+6.2f}% | RSI: {rsi:>5.1f} | Adj: {adj:>+3d}")
                lines.append("")

        return "\n".join(lines)
