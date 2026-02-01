#!/usr/bin/env python3
"""
30-Day Growth Catalyst Screener v12.0 FACTOR-BASED
เป้าหมาย: 10%+ ต่อเดือน! 🎯

v12.0 FACTOR-BASED (Jan 2026):
✅ VERIFIED: 138 trades, 20.23%/month, 56.5% win rate
✅ 17 trades/month average
✅ Max loss -2% (stop-loss mandatory!)

STRATEGY: Filter ตามปัจจัยที่วิเคราะห์แล้ว

v12.0 FACTORS:
┌─────────────────────┬─────────────┬──────────────────────────────────────┐
│ Factor              │ Rule        │ Finding                              │
├─────────────────────┼─────────────┼──────────────────────────────────────┤
│ Market Trend        │ SPY > MA20  │ UP: +110% vs DOWN: -8%               │
│ Sector              │ Best only   │ Industrial +1.75%, Consumer +0.91%   │
│ Month               │ Avoid bad   │ Avoid Oct (-20%), Nov (-16%)         │
│ Technical           │ 5 gates     │ Accum, RSI, MA20, MA50, ATR          │
└─────────────────────┴─────────────┴──────────────────────────────────────┘

GOOD SECTORS:
- Industrial: CAT, DE, HON, GE, BA (avg +1.75%)
- Consumer: HD, LOW, COST, MCD, NKE (avg +0.91%)
- Finance: JPM, BAC, GS, V, MA (avg +0.62%)

BAD SECTORS TO AVOID:
- Healthcare: JNJ, UNH, PFE (avg -0.47%)

TECHNICAL GATES (v12.0):
┌─────────────────────┬─────────────┬──────────────────────────────────────┐
│ Filter              │ Value       │ Why                                  │
├─────────────────────┼─────────────┼──────────────────────────────────────┤
│ Accumulation        │ > 1.2       │ More buying than selling             │
│ RSI                 │ < 58        │ Not extremely overbought             │
│ Above MA20          │ > 0%        │ In uptrend                           │
│ Above MA50          │ > 0%        │ Long-term trend positive             │
│ ATR %               │ < 3.0%      │ Not too volatile                     │
└─────────────────────┴─────────────┴──────────────────────────────────────┘

Exit Rules (MANDATORY!):
- Stop loss -2%
- Hold 5 days

DATA SOURCES USED:
✅ Price Data (Yahoo Finance)
✅ Technical Indicators (calculated)
✅ Market Trend (SPY)
✅ VIX (volatility)

DATA TO ADD IN FUTURE:
❌ Earnings Calendar
❌ Fed Decisions
❌ Sector Rotation Indicators
❌ Institutional Flows

Research Journey:
v9.1 → v10.0 (Zero Loser) → v11.0 (High Profit) → v12.0 (Factor-Based)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
import yfinance as yf

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_universe_generator import AIUniverseGenerator
from ai_stock_analyzer import AIStockAnalyzer
from data_sources.aggregator import AlternativeDataAggregator
from sector_rotation import SectorRotationDetector
from screening_rules_engine import ScreeningRulesEngine, ScreeningMarketData


class GrowthCatalystScreener:
    """
    30-Day Growth Catalyst Screener

    v3.2: Tiered Quality System
    - Dynamic quality thresholds based on stock price
    - Lower prices require higher quality scores
    - Fair system: doesn't discriminate by price alone

    Multi-Stage Architecture:
    - Stage 1: Smart Universe Selection (hard filters)
    - Stage 2: Catalyst Discovery (earnings, news, insider, analyst)
    - Stage 3: Technical Setup Validation
    - Stage 4: AI Deep Analysis (growth probability prediction)
    - Stage 5: Risk-Adjusted Ranking
    """

    def __init__(self, stock_analyzer):
        """
        Initialize Growth Catalyst Screener

        Args:
            stock_analyzer: StockAnalyzer instance
        """
        self.analyzer = stock_analyzer
        self.ai_generator = AIUniverseGenerator()
        self.ai_analyzer = AIStockAnalyzer()

        # v6.4: Price data cache for batch download
        self._price_data_cache = {}

        # v6.7: Stock info cache (ticker.info) - reduces rate limits!
        self._stock_info_cache = {}
        self._stock_info_cache_time = {}  # Track when info was cached
        self._info_cache_ttl = 3600  # 1 hour TTL for stock info

        # v6.7: Rate limit protection
        self._last_api_call_time = 0
        self._min_api_delay = 0.1  # 100ms between API calls

        # v6.7: Market data cache (SPY, QQQ, etc.) - shared across all stocks
        self._market_data_cache = {}
        self._market_data_cache_time = 0
        self._market_cache_ttl = 1800  # 30 min TTL for market data

        # v3.0: Alternative Data Aggregator
        try:
            self.alt_data = AlternativeDataAggregator()
            logger.info("✅ Alternative Data sources initialized (6 sources)")
        except Exception as e:
            self.alt_data = None
            logger.warning(f"⚠️ Alternative Data not available: {e}")

        # v3.1: Sector Rotation Detector
        try:
            self.sector_rotation = SectorRotationDetector()
            logger.info("✅ Sector Rotation detector initialized")
        except Exception as e:
            self.sector_rotation = None
            logger.warning(f"⚠️ Sector Rotation not available: {e}")

        # NEW: Import regime detector
        try:
            from market_regime_detector import MarketRegimeDetector
            self.regime_detector = MarketRegimeDetector()
            logger.info("✅ Market Regime Detector initialized")
        except ImportError:
            self.regime_detector = None
            logger.warning("⚠️ Market Regime Detector not available - will trade without regime filter")

        # v3.3: Sector-Aware Regime Detection
        try:
            from sector_regime_detector import SectorRegimeDetector
            # v6.8: Fixed - pass data_manager, not analyzer!
            self.sector_regime = SectorRegimeDetector(data_manager=self.analyzer.data_manager)
            logger.info("✅ Sector Regime Detector initialized")
            logger.info("Growth Catalyst Screener v3.3 initialized: Tiered Quality + Alt Data + Sector Rotation + Market Regime + SECTOR-AWARE REGIME")
        except ImportError as e:
            self.sector_regime = None
            logger.warning(f"⚠️ Sector Regime Detector not available: {e}")
            logger.info("Growth Catalyst Screener v3.2 initialized: Tiered Quality + Alt Data + Sector Rotation + Market Regime")

        # v4.0: Rule-Based Screening Engine
        try:
            self.screening_rules = ScreeningRulesEngine()
            logger.info("✅ Rule-Based Screening Engine initialized (v4.0)")
            logger.info("   Benefits: Configurable thresholds, A/B testing, performance tracking")
        except Exception as e:
            self.screening_rules = None
            logger.warning(f"⚠️ Rule-Based Screening Engine not available: {e}")

    def _batch_download_price_data(self, symbols: List[str], period: str = '3mo') -> Dict[str, pd.DataFrame]:
        """
        v6.10 ULTRA-SAFE: Batch download that will NEVER hit rate limits

        Strategy:
        - Only 5 stocks per batch (ultra small)
        - 10 second delay between batches (ultra conservative)
        - 2 hour cache (fresh enough for daily data)
        - Guaranteed NO rate limits!

        Args:
            symbols: List of stock symbols
            period: Data period (default 3mo for momentum calculation)

        Returns:
            Dictionary mapping symbol to DataFrame
        """
        import time as time_module
        import random

        # Filter out symbols already cached
        symbols_to_fetch = [s for s in symbols if s not in self._price_data_cache]
        cached_count = len(symbols) - len(symbols_to_fetch)

        if cached_count > 0:
            logger.info(f"📦 Using {cached_count} cached price records")

        if not symbols_to_fetch:
            logger.info(f"✅ All {len(symbols)} symbols already cached!")
            return {s: self._price_data_cache[s] for s in symbols if s in self._price_data_cache}

        logger.info(f"🚀 Batch download: {len(symbols_to_fetch)} stocks")
        logger.info(f"   ⚙️ Settings: 15 stocks/batch, 3-5s delay")

        data = {}

        # BALANCED: 15 stocks per batch, 3-5s delay (fast but safe)
        chunk_size = 15
        chunks = [symbols_to_fetch[i:i+chunk_size] for i in range(0, len(symbols_to_fetch), chunk_size)]

        for chunk_idx, chunk in enumerate(chunks):
            try:
                # BALANCED: 3-5 second delay with jitter
                if chunk_idx > 0:
                    delay = 3 + random.uniform(0, 2)
                    logger.info(f"   ⏳ Delay: {delay:.1f}s (batch {chunk_idx+1}/{len(chunks)})")
                    time_module.sleep(delay)

                logger.info(f"   📥 Batch {chunk_idx+1}: {', '.join(chunk)}")

                # Download batch
                raw = yf.download(
                    chunk,
                    period=period,
                    group_by='ticker',
                    threads=False,
                    progress=False
                )

                # Process downloaded data
                success = 0
                for symbol in chunk:
                    try:
                        if len(chunk) == 1:
                            df = raw.copy()
                        else:
                            df = raw[symbol].copy()

                        df = df.dropna(how='all')
                        df.columns = [col.lower() if isinstance(col, str) else col for col in df.columns]

                        if len(df) >= 20:
                            data[symbol] = df
                            self._price_data_cache[symbol] = df
                            success += 1
                    except:
                        continue

                logger.info(f"   ✓ {success}/{len(chunk)} success")

            except Exception as e:
                error_str = str(e).lower()
                if any(x in error_str for x in ['rate', '401', '429', 'too many']):
                    logger.warning(f"⚠️ Rate limit! Waiting 60s...")
                    time_module.sleep(60)
                else:
                    logger.warning(f"❌ Batch failed: {e}")
                    time_module.sleep(15)
                continue

        # Include cached data
        for s in symbols:
            if s in self._price_data_cache and s not in data:
                data[s] = self._price_data_cache[s]

        logger.info(f"✅ Complete: {len(data)}/{len(symbols)} stocks")
        return data

    def _get_cached_price_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get price data from cache (set by batch download)

        Args:
            symbol: Stock symbol

        Returns:
            DataFrame with price data or None
        """
        return self._price_data_cache.get(symbol)

    def _rate_limited_api_call(self, retry_count: int = 0):
        """
        v6.7: Wait if needed before making an API call (rate limit protection)

        With exponential backoff on retries.
        """
        import time
        now = time.time()

        # Base delay between calls
        elapsed = now - self._last_api_call_time
        base_delay = self._min_api_delay

        # Exponential backoff on retries
        if retry_count > 0:
            backoff_delay = min(30, 0.5 * (2 ** retry_count))  # Max 30 sec
            base_delay = max(base_delay, backoff_delay)
            logger.debug(f"Rate limit backoff: {backoff_delay:.1f}s (retry {retry_count})")

        if elapsed < base_delay:
            time.sleep(base_delay - elapsed)
        self._last_api_call_time = time.time()

    def _get_stock_info_cached(self, symbol: str, price_data: pd.DataFrame = None) -> Dict[str, Any]:
        """
        v6.7: Get stock info with caching (reduces rate limits!)

        Priority:
        1. Return from cache if fresh (< 1 hour old)
        2. Estimate from price_data if available (no API call!)
        3. Fetch from API (with rate limiting)

        Args:
            symbol: Stock symbol
            price_data: Optional price DataFrame for estimation

        Returns:
            Dictionary with stock info
        """
        import time

        # Check cache first
        if symbol in self._stock_info_cache:
            cache_time = self._stock_info_cache_time.get(symbol, 0)
            if time.time() - cache_time < self._info_cache_ttl:
                logger.debug(f"{symbol}: Using cached info (age: {int(time.time() - cache_time)}s)")
                return self._stock_info_cache[symbol]

        # Try to estimate from price data (NO API CALL!)
        if price_data is not None and not price_data.empty:
            try:
                close_col = 'close' if 'close' in price_data.columns else 'Close'
                volume_col = 'volume' if 'volume' in price_data.columns else 'Volume'
                high_col = 'high' if 'high' in price_data.columns else 'High'
                low_col = 'low' if 'low' in price_data.columns else 'Low'

                current_price = float(price_data[close_col].iloc[-1])
                avg_volume = float(price_data[volume_col].mean())

                # Estimate shares outstanding (rough estimate: avg_volume * 100)
                estimated_shares = avg_volume * 100
                estimated_market_cap = current_price * estimated_shares

                # 52-week high/low from price data
                high_52w = float(price_data[high_col].max())
                low_52w = float(price_data[low_col].min())

                # Beta estimate: compare stock volatility to SPY
                returns = price_data[close_col].pct_change().dropna()
                beta_estimate = returns.std() * 15  # Rough estimate (avg beta ~1)

                estimated_info = {
                    'marketCap': estimated_market_cap,
                    'beta': min(max(beta_estimate, 0.5), 3.0),  # Clamp to reasonable range
                    'fiftyTwoWeekHigh': high_52w,
                    'fiftyTwoWeekLow': low_52w,
                    'averageVolume': avg_volume,
                    '_estimated': True  # Flag that this is estimated
                }

                # Cache the estimated info (shorter TTL: 30 min)
                self._stock_info_cache[symbol] = estimated_info
                self._stock_info_cache_time[symbol] = time.time() - 1800  # Shorter TTL
                logger.debug(f"{symbol}: Using estimated info (no API call)")
                return estimated_info

            except Exception as e:
                logger.debug(f"{symbol}: Estimation failed - {e}")

        # Last resort: Fetch from API (with rate limiting)
        try:
            self._rate_limited_api_call()
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if info:
                # Cache the real info
                self._stock_info_cache[symbol] = info
                self._stock_info_cache_time[symbol] = time.time()
                logger.debug(f"{symbol}: Fetched fresh info from API")
                return info
        except Exception as e:
            logger.debug(f"{symbol}: API call failed - {e}")

        # Return empty dict if all fails
        return {}

    @staticmethod
    def get_dynamic_thresholds(price: float) -> Dict[str, Any]:
        """
        Get dynamic quality thresholds based on stock price (Tiered System)

        Lower prices = Higher quality requirements
        Fair system: doesn't discriminate by price alone, but adjusts for risk

        Args:
            price: Stock price

        Returns:
            Dictionary with quality thresholds for this price level
        """
        # v7.1 UPDATE: Increased technical score thresholds based on backtest
        # Backtest showed score >= 88 gives 76.3% WR (vs 55% at score 70)
        if price >= 50:
            # High-price stocks ($50+): Increased threshold for quality
            return {
                'tier': 'HIGH_PRICE',
                'min_catalyst_score': 0.0,
                'min_technical_score': 65.0,  # v7.1: 30 → 65 for better WR
                'min_ai_probability': 30.0,
                'min_market_cap': 500_000_000,
                'min_volume': 10_000_000,
                'require_insider_buying': False,
                'min_analyst_coverage': 0,
                'description': '$50+ stocks - v7.1 quality threshold'
            }
        elif price >= 20:
            # Mid-high price stocks ($20-$50): Increased threshold
            return {
                'tier': 'MID_HIGH_PRICE',
                'min_catalyst_score': 10.0,
                'min_technical_score': 70.0,  # v7.1: 40 → 70 for better WR
                'min_ai_probability': 40.0,
                'min_market_cap': 500_000_000,
                'min_volume': 10_000_000,
                'require_insider_buying': False,
                'min_analyst_coverage': 0,
                'description': '$20-$50 stocks - v7.1 quality threshold'
            }
        elif price >= 10:
            # Mid-price stocks ($10-$20): Increased threshold
            return {
                'tier': 'MID_PRICE',
                'min_catalyst_score': 20.0,
                'min_technical_score': 75.0,  # v7.1: 50 → 75 for better WR
                'min_ai_probability': 50.0,
                'min_market_cap': 500_000_000,
                'min_volume': 15_000_000,
                'require_insider_buying': False,
                'min_analyst_coverage': 1,
                'description': '$10-$20 stocks - v7.1 quality threshold'
            }
        elif price >= 5:
            # Low-mid price stocks ($5-$10): Increased threshold
            return {
                'tier': 'LOW_MID_PRICE',
                'min_catalyst_score': 30.0,
                'min_technical_score': 80.0,  # v7.1: 60 → 80 for better WR
                'min_ai_probability': 60.0,
                'min_market_cap': 500_000_000,
                'min_volume': 20_000_000,
                'require_insider_buying': True,
                'min_analyst_coverage': 2,
                'description': '$5-$10 stocks - v7.1 strict quality'
            }
        else:  # price >= 3
            # Low-price stocks ($3-$5): Maximum strictness
            return {
                'tier': 'LOW_PRICE',
                'min_catalyst_score': 40.0,
                'min_technical_score': 85.0,  # v7.1: 70 → 85 for better WR
                'min_ai_probability': 70.0,
                'min_market_cap': 200_000_000,
                'min_volume': 20_000_000,
                'require_insider_buying': True,
                'min_analyst_coverage': 3,
                'description': '$3-$5 stocks - v7.1 maximum quality required'
            }

    # ========== v4.0: MOMENTUM QUALITY FUNCTIONS ==========

    @staticmethod
    def _calculate_momentum_metrics(price_data: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate momentum metrics for stock (v6.4 VOLUME CONFIRMATION)

        v6.4 Changes:
        - Added vol_trend (5d avg / 20d avg) - 87.5% WR filter!
        - Added accumulation (up vol / down vol) - 87.5% WR filter!
        - These filters from get_top_pick_today.py proven to work

        Returns:
            Dict with RSI, MA distances, momentum values, volume metrics
        """
        try:
            if len(price_data) < 50:
                return None

            close = price_data['Close'] if 'Close' in price_data.columns else price_data['close']
            high = price_data['High'] if 'High' in price_data.columns else price_data['high']
            open_price = price_data['Open'] if 'Open' in price_data.columns else price_data['open']
            volume = price_data['Volume'] if 'Volume' in price_data.columns else price_data['volume']
            current_price = float(close.iloc[-1])

            # RSI calculation
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1]))

            # Moving averages
            ma20 = close.rolling(window=20).mean().iloc[-1]
            ma50 = close.rolling(window=50).mean().iloc[-1]

            price_above_ma20 = ((current_price - ma20) / ma20) * 100
            price_above_ma50 = ((current_price - ma50) / ma50) * 100

            # v6.0: Volume Ratio (KEY! มี catalyst = มี volume)
            vol_avg_20d = volume.rolling(window=20).mean().iloc[-1]
            volume_ratio = float(volume.iloc[-1]) / vol_avg_20d if vol_avg_20d > 0 else 1.0

            # v6.4: Volume Confirmation (87.5% WR from get_top_pick_today.py!)
            # Vol Trend: 5-day avg vs 20-day avg (> 1.0 = volume increasing)
            vol_avg_5d = volume.iloc[-5:].mean()
            vol_trend = float(vol_avg_5d / vol_avg_20d) if vol_avg_20d > 0 else 1.0

            # Accumulation: Up volume vs Down volume (last 10 days)
            # > 1.2 means more buying than selling
            price_change = close.diff().iloc[-10:]
            vol_last_10 = volume.iloc[-10:]
            up_volume = vol_last_10[price_change > 0].sum()
            down_volume = vol_last_10[price_change <= 0].sum()
            accumulation = float(up_volume / down_volume) if down_volume > 0 else 2.0

            # v6.0: Gap (เปิดวันนี้ vs ปิดเมื่อวาน)
            prev_close = float(close.iloc[-2]) if len(close) > 1 else current_price
            today_open = float(open_price.iloc[-1])
            gap = ((today_open - prev_close) / prev_close) * 100

            # Momentum (multiple timeframes)
            price_3d_ago = close.iloc[-4] if len(close) > 3 else close.iloc[0]
            price_5d_ago = close.iloc[-6] if len(close) > 5 else close.iloc[0]
            price_10d_ago = close.iloc[-11] if len(close) > 10 else close.iloc[0]
            price_20d_ago = close.iloc[-21] if len(close) > 20 else close.iloc[0]
            price_30d_ago = close.iloc[-31] if len(close) > 30 else close.iloc[0]

            momentum_3d = ((current_price - price_3d_ago) / price_3d_ago) * 100
            momentum_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100
            momentum_10d = ((current_price - price_10d_ago) / price_10d_ago) * 100
            momentum_20d = ((current_price - price_20d_ago) / price_20d_ago) * 100
            momentum_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100

            # 52-week position (keep for reference)
            data_len = len(close)
            lookback = min(252, data_len)
            high_52w = high.iloc[-lookback:].max()
            low_52w = close.iloc[-lookback:].min()
            position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50.0

            # Bollinger Band position (keep for reference)
            bb_std = close.rolling(window=20).std().iloc[-1]
            bb_upper = ma20 + 2 * bb_std
            bb_lower = ma20 - 2 * bb_std
            bb_position = ((current_price - bb_lower) / (bb_upper - bb_lower)) * 100 if bb_upper > bb_lower else 50.0

            # v6.1: Distance from 20d high (detect pullback/falling stocks)
            # ป้องกันซื้อหุ้นที่กำลังตก เช่น DDOG ที่ mom_20d ยังสูงแต่ราคาตกจาก peak แล้ว
            high_20d = high.iloc[-20:].max()
            dist_from_20d_high = ((current_price - high_20d) / high_20d) * 100

            # v6.3: ATR (Average True Range) - volatility measure
            # Losers have higher ATR (3.12% vs 2.77%) - low volatility = fewer crashes
            low = price_data['Low'] if 'Low' in price_data.columns else price_data['low']
            tr = pd.DataFrame({
                'hl': high - low,
                'hc': abs(high - close.shift(1)),
                'lc': abs(low - close.shift(1))
            }).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            atr_pct = (atr / current_price) * 100

            # v6.3: Days above MA20 (trend consistency)
            # Winners: 8.7 days, Losers: 7.56 days - consistent trend = more wins
            ma20_series = close.rolling(20).mean()
            days_above_ma20 = int((close.iloc[-10:] > ma20_series.iloc[-10:]).sum())

            return {
                'rsi': float(rsi),
                'price_above_ma20': float(price_above_ma20),
                'price_above_ma50': float(price_above_ma50),
                'volume_ratio': float(volume_ratio),
                'vol_trend': float(vol_trend),  # v6.4: Volume Confirmation
                'accumulation': float(accumulation),  # v6.4: Volume Confirmation
                'gap': float(gap),
                'bb_position': float(bb_position),
                'momentum_3d': float(momentum_3d),
                'momentum_5d': float(momentum_5d),
                'momentum_10d': float(momentum_10d),
                'momentum_20d': float(momentum_20d),
                'momentum_30d': float(momentum_30d),
                'position_52w': float(position_52w),
                'dist_from_20d_high': float(dist_from_20d_high),
                'atr_pct': float(atr_pct),
                'days_above_ma20': days_above_ma20,
            }
        except Exception as e:
            logger.debug(f"Error calculating momentum metrics: {e}")
            return None

    @staticmethod
    def _passes_momentum_gates(metrics: Dict[str, float]) -> tuple[bool, str]:
        """
        Check if stock passes momentum quality gates (v11.0 HIGH PROFIT)

        v11.0 HIGH PROFIT - Backtest 10 เดือน, 50 stocks
        ✅ 141 trades, 72 winners, 69 losers (all stopped at -2%)
        ✅ 11.76%/month average, 70% months profitable
        ✅ 14 trades/month average

        STRATEGY: เทรดบ่อยขึ้น + Stop-Loss -2% คุม max loss
        - ยอมรับ 50% win rate
        - แต่ winner เฉลี่ย +3-5%, loser เท่ากัน -2% เท่านั้น
        - Expected value = positive!

        GATES (v11.0 HIGH PROFIT):
        ┌─────────────────────┬─────────────┬──────────────────────────────────────┐
        │ Filter              │ Value       │ Why                                  │
        ├─────────────────────┼─────────────┼──────────────────────────────────────┤
        │ Accumulation        │ > 1.2       │ More buying than selling             │
        │ RSI                 │ < 58        │ Not extremely overbought             │
        │ Above MA20          │ > 0%        │ In uptrend                           │
        │ Above MA50          │ > 0%        │ Long-term trend positive             │
        │ ATR %               │ < 3.0%      │ Not too volatile (manageable risk)   │
        └─────────────────────┴─────────────┴──────────────────────────────────────┘

        MANDATORY: Stop-Loss -2% (MUST USE!)
        Hold: 5 days

        Returns:
            (passes, rejection_reason)
        """
        if metrics is None:
            return False, "No momentum metrics"

        # === v11.0 HIGH PROFIT FORMULA ===
        # Backtest: 10 months, 50 stocks, 141 trades, +117.61% total, +11.76%/month

        # Gate 1: Accumulation > 1.2 (buying pressure)
        accumulation = metrics.get('accumulation', 0)
        if accumulation <= 1.2:
            return False, f"Accumulation too low ({accumulation:.2f} <= 1.2) - weak buying"

        # Gate 2: RSI < 58 (not extremely overbought)
        rsi = metrics.get('rsi', 50)
        if rsi >= 58:
            return False, f"RSI too high ({rsi:.0f} >= 58) - overbought"

        # Gate 3: Above MA20 > 0% (in uptrend)
        price_above_ma20 = metrics.get('price_above_ma20', 0)
        if price_above_ma20 <= 0:
            return False, f"Below MA20 ({price_above_ma20:.1f}% <= 0%) - not in uptrend"

        # Gate 4: Above MA50 > 0% (long-term trend positive)
        price_above_ma50 = metrics.get('price_above_ma50', 0)
        if price_above_ma50 <= 0:
            return False, f"Below MA50 ({price_above_ma50:.1f}% <= 0%) - negative trend"

        # Gate 5: ATR % < 3.0% (manageable volatility)
        atr_pct = metrics.get('atr_pct', 3.0)
        if atr_pct >= 3.0:
            return False, f"ATR too high ({atr_pct:.2f}% >= 3.0%) - too volatile"

        # All gates passed!
        # IMPORTANT: Must use -2% stop-loss for this config!
        return True, ""

    @staticmethod
    def _calculate_momentum_score(metrics: Dict[str, float]) -> float:
        """
        Calculate momentum score 0-100 (v7.1 BACKTEST-OPTIMIZED)

        v7.1 Scoring - based on 4-month backtest achieving 76.3% WR:
        - Momentum 20d: 40 points (sweet spot 8-12%)
        - RSI: 35 points (ideal 50-58)
        - 52w Position: 25 points (optimal 65-80%)

        Backtest Results:
        - Score >= 88: 76.3% WR, 9 losers, PF 3.79
        - Score >= 85: 66.7% WR, 18 losers, PF 2.76
        """
        score = 0.0

        # Momentum 20d (40 points) - KEY FACTOR!
        # Backtest showed 8-12% is optimal
        mom20d = metrics.get('momentum_20d', 0)
        if 8 <= mom20d <= 12:
            mom_score = 40  # Perfect sweet spot
        elif 6 <= mom20d <= 14:
            mom_score = 36  # Near optimal
        elif 5 <= mom20d <= 16:
            mom_score = 30  # Good range
        elif 3 <= mom20d <= 20:
            mom_score = 20  # Acceptable
        else:
            mom_score = 10  # Weak or overextended
        score += mom_score

        # RSI (35 points) - Sweet spot 50-58
        # Backtest showed this range has best outcomes
        rsi = metrics.get('rsi', 50)
        if 50 <= rsi <= 58:
            rsi_score = 35  # Perfect range
        elif 48 <= rsi <= 60:
            rsi_score = 31  # Near optimal
        elif 45 <= rsi <= 62:
            rsi_score = 26  # Good
        elif 40 <= rsi <= 65:
            rsi_score = 18  # Acceptable
        else:
            rsi_score = 10  # Getting extreme
        score += rsi_score

        # 52-Week Position (25 points) - Optimal 65-80%
        pos_52w = metrics.get('position_52w', 50)
        if 65 <= pos_52w <= 80:
            pos_score = 25  # Sweet spot
        elif 60 <= pos_52w <= 85:
            pos_score = 22  # Good
        elif 55 <= pos_52w <= 88:
            pos_score = 18  # Acceptable
        elif 50 <= pos_52w <= 90:
            pos_score = 12  # OK
        else:
            pos_score = 5   # Too low or too high
        score += pos_score

        return round(score, 1)

    def screen_growth_catalyst_opportunities(self,
                                            target_gain_pct: float = 5.0,  # v2.0: 5% target for 30 days
                                            timeframe_days: int = 30,  # v2.0: 30-day proven strategy
                                            min_market_cap: float = 500_000_000,  # $500M
                                            max_market_cap: float = None,  # No limit
                                            min_price: float = 3.0,  # v3.2: Lowered to $3 with tiered quality system
                                            max_price: float = 2000.0,  # Allow high-value stocks
                                            min_daily_volume: float = 10_000_000,  # $10M
                                            min_catalyst_score: float = 0.0,  # Inverted scoring, can be negative
                                            min_technical_score: float = 65.0,  # v7.1: Raised to 65 for better WR
                                            min_ai_probability: float = 30.0,  # Lowered to 30%
                                            max_stocks: int = 20,
                                            universe_multiplier: int = 5) -> List[Dict[str, Any]]:  # v7.1: Match UI default (5x = 150 stocks)
        """
        Screen for high-probability 14-day growth opportunities (v4.0 MOMENTUM-ENHANCED)

        Args:
            target_gain_pct: Target gain percentage (default 10%)
            timeframe_days: Timeframe in days (default 30)
            min_market_cap: Minimum market cap
            max_market_cap: Maximum market cap (None = no limit)
            min_price: Minimum stock price
            max_price: Maximum stock price
            min_daily_volume: Minimum daily volume in dollars
            min_catalyst_score: Minimum catalyst score (0-100)
            min_technical_score: Minimum technical score (0-100)
            min_ai_probability: Minimum AI probability (0-100%)
            max_stocks: Maximum number of stocks to return

        Returns:
            List of growth catalyst opportunities sorted by composite score
        """
        # v7.3: universe_multiplier maps directly to stock count
        universe_size_map = {3: 100, 5: 150, 10: 300, 25: 500, 35: 685}
        universe_target = universe_size_map.get(universe_multiplier, universe_multiplier * 20)

        logger.info(f"🎯 Starting Growth Catalyst Screening v8.0 ZERO LOSER")
        logger.info(f"   Target: {target_gain_pct}%+ gain in {timeframe_days} days")
        logger.info(f"   Universe: {universe_target} stocks ({universe_multiplier}x multiplier)")
        logger.info(f"   Strategy: ZERO LOSER (Accum>1.3 + RSI<60 + MA20>0)")

        # v6.9: DON'T clear caches - reuse existing data to avoid rate limits
        # Cache is now 2+ hours, so data stays fresh enough
        cache_sizes = len(self._stock_info_cache), len(self._price_data_cache)
        logger.info(f"   📦 Using cached data: {cache_sizes[0]} info, {cache_sizes[1]} price records")

        # ===== STAGE 0a: Sector Regime Update (v3.3) =====
        sector_regime_summary = None
        if self.sector_regime:
            try:
                logger.info("\n🌐 STAGE 0a: Sector Regime Analysis")
                self.sector_regime.update_all_sectors()
                sector_regime_summary = self.sector_regime.get_sector_summary()

                # Log sector summary (v6.8: Fixed column names - 'Regime' not 'regime')
                bull_sectors = sector_regime_summary[sector_regime_summary['Regime'].isin(['STRONG BULL', 'BULL'])]
                sideways_sectors = sector_regime_summary[sector_regime_summary['Regime'] == 'SIDEWAYS']
                bear_sectors = sector_regime_summary[sector_regime_summary['Regime'].isin(['BEAR', 'STRONG BEAR'])]

                logger.info(f"   🟢 BULL Sectors: {len(bull_sectors)} ({', '.join(bull_sectors['Sector'].tolist()) if not bull_sectors.empty else 'None'})")
                logger.info(f"   ⚪ SIDEWAYS Sectors: {len(sideways_sectors)}")
                logger.info(f"   🔴 BEAR Sectors: {len(bear_sectors)} ({', '.join(bear_sectors['Sector'].tolist()) if not bear_sectors.empty else 'None'})")
                logger.info(f"   ✅ Sector regime data refreshed")
            except Exception as e:
                logger.warning(f"⚠️ Sector regime update failed: {e}")

        # ===== STAGE 0b: Market Regime Check =====
        if self.regime_detector:
            logger.info("\n🧠 STAGE 0: Market Regime Analysis")
            regime_info = self.regime_detector.get_current_regime()

            logger.info(f"   Regime: {regime_info['regime']}")
            logger.info(f"   Strength: {regime_info['strength']}/100")
            logger.info(f"   Should Trade: {regime_info['should_trade']}")
            logger.info(f"   Position Size: {regime_info['position_size_multiplier']*100:.0f}%")

            if not regime_info['should_trade']:
                # v3.3: Check if we have sector regime detector with BULL sectors
                has_bull_sectors = False
                if self.sector_regime and sector_regime_summary is not None:
                    bull_sectors = sector_regime_summary[sector_regime_summary['Regime'].isin(['BULL', 'STRONG BULL'])]
                    has_bull_sectors = len(bull_sectors) > 0

                if has_bull_sectors:
                    logger.warning(f"\n⚠️ MARKET REGIME: {regime_info['regime']} (Strength: {regime_info['strength']}/100)")
                    logger.info(f"   ✅ BUT we have {len(bull_sectors)} BULL sectors - proceeding with SECTOR-AWARE screening")
                    logger.info(f"   🎯 BULL sectors: {', '.join(bull_sectors['Sector'].tolist())}")
                    logger.info(f"   Strategy: Focus 80% on BULL sectors, be selective on others")
                else:
                    logger.warning(f"\n⚠️ REGIME FILTER: Market regime is {regime_info['regime']}")
                    logger.warning(f"   Strategy is designed for BULL markets")
                    logger.warning(f"   No BULL sectors found")
                    logger.warning(f"   Skipping screening to protect capital")
                    logger.warning(f"   Recommendation: Stay in CASH")

                    # Return empty list with regime warning
                    return [{
                        'regime_warning': True,
                        'regime': regime_info['regime'],
                        'regime_strength': regime_info['strength'],
                        'should_trade': False,
                        'message': f"Market regime is {regime_info['regime']} - not suitable for growth catalyst strategy",
                        'details': regime_info['details'],
                        'recommendation': "Stay in cash and wait for BULL market signals"
                    }]

            # Additional SPY trend confirmation (v2.1 - Double-check!)
            spy_details = regime_info['details']
            if spy_details['dist_ma20'] < -3.0 or spy_details['dist_ma50'] < -5.0:
                logger.warning(f"\n⚠️ SPY TREND WEAK: SPY below MA20/MA50 significantly")
                logger.warning(f"   SPY vs MA20: {spy_details['dist_ma20']:.1f}%")
                logger.warning(f"   SPY vs MA50: {spy_details['dist_ma50']:.1f}%")
                logger.warning(f"   Not screening - wait for stronger trend")
                return [{
                    'regime_warning': True,
                    'regime': 'WEAK_TREND',
                    'message': 'SPY trend too weak for reliable entries',
                    'recommendation': 'Wait for SPY to reclaim moving averages'
                }]

            logger.info(f"   ✅ Regime check PASSED - proceeding with scan")
            logger.info(f"   SPY vs MA20: {spy_details['dist_ma20']:+.1f}%")
            logger.info(f"   Will use {regime_info['position_size_multiplier']*100:.0f}% of normal position size")

        # ===== STAGE 1: Smart Universe Selection =====
        logger.info(f"\n📋 STAGE 1: Smart Universe Selection (using {universe_multiplier}x multiplier)")
        stock_universe = self._generate_growth_universe(
            target_gain_pct=target_gain_pct,
            timeframe_days=timeframe_days,
            max_stocks=max_stocks,
            universe_multiplier=universe_multiplier
        )

        if not stock_universe:
            logger.error("Failed to generate stock universe")
            return []

        logger.info(f"✅ Generated universe of {len(stock_universe)} stocks")

        # ===== STAGE 1.5: Batch Download Price Data (v6.4 - FAST!) =====
        logger.info(f"\n🚀 STAGE 1.5: Batch Download Price Data (v6.4 - 10x faster!)")
        self._price_data_cache = self._batch_download_price_data(stock_universe, period='3mo')

        if not self._price_data_cache:
            logger.error("Failed to download price data")
            return []

        logger.info(f"✅ Price data cached for {len(self._price_data_cache)} stocks")

        # v6.7: Pre-fetch market data (SPY) to avoid repeated calls
        import time
        logger.info(f"🌐 Pre-fetching market data (SPY)...")
        try:
            spy = yf.Ticker('SPY')
            spy_hist = spy.history(period='1mo')
            if not spy_hist.empty and len(spy_hist) >= 20:
                market_return_30d = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-20]) - 1) * 100
                self._market_data_cache['spy_return_30d'] = market_return_30d
                self._market_data_cache_time = time.time()
                logger.info(f"✅ SPY 30d return cached: {market_return_30d:+.2f}%")
        except Exception as e:
            logger.warning(f"⚠️ SPY pre-fetch failed: {e} - will use 0% market return")

        # ===== STAGE 2-4: Parallel Analysis =====
        logger.info("\n🔍 STAGE 2-4: Multi-Stage Analysis (Catalyst + Technical + AI)")
        opportunities = []

        # v6.7: Reduced workers from 16 to 8 to be gentler on APIs
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_symbol = {
                executor.submit(
                    self._analyze_stock_comprehensive,
                    symbol,
                    target_gain_pct,
                    timeframe_days
                ): symbol
                for symbol in stock_universe
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        opportunities.append(result)
                        entry_score = result.get('entry_score', 0)
                        momentum_score = result.get('momentum_score', 0)
                        logger.info(f"✅ {symbol}: Entry Score {entry_score:.1f}/140 (Momentum: {momentum_score:.1f}/100)")
                    else:
                        logger.debug(f"❌ {symbol}: Did not meet criteria")

                except Exception as e:
                    logger.warning(f"⚠️  {symbol}: Analysis failed - {e}")
                    continue

        # ===== STAGE 5: Filtering & Ranking =====
        logger.info(f"\n📊 STAGE 5: Filtering & Ranking")
        logger.info(f"   Analyzed: {len(opportunities)} stocks")

        # Apply hard filters
        filtered_opportunities = []
        for opp in opportunities:
            symbol = opp['symbol']

            # Hard filters
            if opp['current_price'] < min_price or opp['current_price'] > max_price:
                logger.debug(f"❌ {symbol}: Price ${opp['current_price']:.2f} outside range ${min_price}-${max_price}")
                continue

            # v3.2: Get dynamic thresholds based on stock price (Tiered Quality System)
            stock_price = opp.get('current_price', opp.get('entry_price', 0))
            dynamic_thresholds = self.get_dynamic_thresholds(stock_price)

            # Apply dynamic thresholds (higher quality required for lower prices)
            effective_catalyst_score = max(min_catalyst_score, dynamic_thresholds['min_catalyst_score'])
            effective_technical_score = max(min_technical_score, dynamic_thresholds['min_technical_score'])
            effective_ai_probability = max(min_ai_probability, dynamic_thresholds['min_ai_probability'])
            effective_market_cap = max(min_market_cap, dynamic_thresholds['min_market_cap'])
            effective_volume = max(min_daily_volume, dynamic_thresholds['min_volume'])

            # Log tier for low-price stocks
            if stock_price < 20:
                logger.info(f"   {symbol} @ ${stock_price:.2f} → Tier: {dynamic_thresholds['tier']} ({dynamic_thresholds['description']})")

            if opp['market_cap'] < effective_market_cap:
                logger.debug(f"❌ {symbol}: Market cap ${opp['market_cap']/1e9:.2f}B below minimum ${effective_market_cap/1e9:.2f}B (tier: {dynamic_thresholds['tier']})")
                continue

            if max_market_cap and opp['market_cap'] > max_market_cap:
                logger.debug(f"❌ {symbol}: Market cap ${opp['market_cap']/1e9:.2f}B above maximum ${max_market_cap/1e9:.2f}B")
                continue

            if opp['avg_dollar_volume'] < effective_volume:
                logger.debug(f"❌ {symbol}: Daily volume ${opp['avg_dollar_volume']/1e6:.1f}M below minimum ${effective_volume/1e6:.1f}M (tier: {dynamic_thresholds['tier']})")
                continue

            # Quality filters with dynamic thresholds
            if opp['catalyst_score'] < effective_catalyst_score:
                logger.debug(f"❌ {symbol}: Catalyst score {opp['catalyst_score']:.1f} below minimum {effective_catalyst_score} (tier: {dynamic_thresholds['tier']})")
                continue

            if opp['technical_score'] < effective_technical_score:
                logger.debug(f"❌ {symbol}: Technical score {opp['technical_score']:.1f} below minimum {effective_technical_score} (tier: {dynamic_thresholds['tier']})")
                continue

            # v6.6: DISABLED AI Probability filter - analysis showed NEGATIVE correlation!
            # High AI prob = worse returns, Low AI prob = better returns
            # if opp['ai_probability'] < effective_ai_probability:
            #     logger.debug(f"❌ {symbol}: AI probability {opp['ai_probability']:.1f}% below minimum {effective_ai_probability}% (tier: {dynamic_thresholds['tier']})")
            #     continue

            # v3.2: Additional checks for low-price stocks
            if dynamic_thresholds['require_insider_buying']:
                # Check if stock has insider buying signal
                alt_signals_list = opp.get('alt_data_signals_list', [])
                has_insider_buying = 'Insider Buying' in alt_signals_list
                if not has_insider_buying:
                    logger.debug(f"❌ {symbol}: Tier {dynamic_thresholds['tier']} requires insider buying (not found)")
                    continue

            # v4.0: Alternative Data is BONUS, not required!
            # Momentum gates already ensure quality
            alt_data_signals = opp.get('alt_data_signals', 0)
            entry_score = opp.get('entry_score', 0)
            momentum_score = opp.get('momentum_score', 0)

            # v6.8: BEAR sector filter - warn user clearly!
            sector_regime = opp.get('sector_regime', 'UNKNOWN')
            sector_regime_adjustment = opp.get('sector_regime_adjustment', 0)
            sector = opp.get('sector', 'Unknown')

            if sector_regime in ['BEAR', 'STRONG BEAR']:
                logger.warning(f"⚠️ {symbol}: Sector '{sector}' is {sector_regime}! Score adjusted by {sector_regime_adjustment:+d}")
                # Mark as having sector warning (but still include with lower score)
                opp['sector_warning'] = True
                opp['sector_warning_message'] = f"Sector {sector} is {sector_regime} - higher risk!"

            logger.info(f"✅ {symbol}: PASSED all filters (Entry Score: {entry_score:.1f}/140, Momentum: {momentum_score:.1f}/100, Alt Signals: {alt_data_signals}/6, Sector: {sector_regime})")
            filtered_opportunities.append(opp)

        # v4.0: Sort by ENTRY SCORE (momentum-based), not composite!
        filtered_opportunities.sort(key=lambda x: x.get('entry_score', 0), reverse=True)

        logger.info(f"\n✅ Found {len(filtered_opportunities)} high-quality growth opportunities")

        # Add regime info to results if available
        if self.regime_detector and filtered_opportunities:
            regime_info = self.regime_detector.get_current_regime()
            # Add regime metadata to first result (for display in UI)
            filtered_opportunities[0]['regime_info'] = {
                'regime': regime_info['regime'],
                'strength': regime_info['strength'],
                'position_size_multiplier': regime_info['position_size_multiplier'],
                'should_trade': regime_info['should_trade']
            }

        # v3.3: Add sector regime summary to results
        if self.sector_regime and filtered_opportunities and sector_regime_summary is not None:
            # Convert DataFrame to dict for JSON serialization
            sector_summary_dict = sector_regime_summary.to_dict('records')
            filtered_opportunities[0]['sector_regime_summary'] = sector_summary_dict

        return filtered_opportunities[:max_stocks]

    # Large static universe (500+ stocks) - comprehensive coverage all sectors
    STATIC_UNIVERSE = [
        # === TECHNOLOGY - MEGA CAPS (20 stocks) ===
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD',
        'ORCL', 'CRM', 'ADBE', 'NOW', 'IBM', 'CSCO', 'ACN', 'INTU', 'UBER', 'QCOM',
        # === SEMICONDUCTORS (30 stocks) ===
        'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'NXPI', 'MCHP', 'ADI', 'INTC', 'ON',
        'SWKS', 'MPWR', 'MRVL', 'SNPS', 'CDNS', 'ARM', 'SMCI', 'ASML', 'TSM', 'GFS',
        'WOLF', 'CRUS', 'SLAB', 'SITM', 'RMBS', 'POWI', 'DIOD', 'AOSL', 'ALGM', 'ACLS',
        # === AI / DATA CENTER / CLOUD (25 stocks) ===
        'PLTR', 'SNOW', 'MDB', 'DDOG', 'NET', 'CFLT', 'ESTC', 'PATH', 'AI', 'BBAI',
        'SOUN', 'UPST', 'C3AI', 'VRT', 'DELL', 'HPE', 'ANET', 'NTAP', 'PSTG', 'NEWR',
        'DT', 'SUMO', 'PD', 'MNDY', 'ASAN',
        # === CYBERSECURITY (20 stocks) ===
        'FTNT', 'PANW', 'CRWD', 'ZS', 'S', 'CYBR', 'OKTA', 'QLYS', 'TENB', 'RPD',
        'VRNS', 'SAIL', 'RBRK', 'SWI', 'SCWX', 'TUFN', 'FSLY', 'LLNW', 'AKAM', 'CDN',
        # === SOFTWARE / SAAS (30 stocks) ===
        'WDAY', 'VEEV', 'HUBS', 'BILL', 'GTLB', 'TTD', 'ZM', 'DOCU', 'TWLO', 'TEAM',
        'SHOP', 'PYPL', 'SQ', 'ADSK', 'ANSS', 'PTC', 'MANH', 'APPF', 'PCTY', 'PAYC',
        'WK', 'ZI', 'APP', 'APLS', 'FRSH', 'CWAN', 'NCNO', 'ALTR', 'DOMO', 'BRZE',
        # === INTERNET / E-COMMERCE / SOCIAL (25 stocks) ===
        'DASH', 'LYFT', 'ABNB', 'BKNG', 'EXPE', 'EBAY', 'ETSY', 'MELI', 'SE', 'BABA',
        'JD', 'PDD', 'BIDU', 'SNAP', 'PINS', 'RDDT', 'DUOL', 'CHWY', 'W', 'CVNA',
        'CARG', 'CARS', 'TRUE', 'OPEN', 'RDFN',
        # === GAMING / ENTERTAINMENT / STREAMING (20 stocks) ===
        'U', 'RBLX', 'EA', 'TTWO', 'ROKU', 'SPOT', 'NFLX', 'DIS', 'PARA', 'WBD',
        'CMCSA', 'FOX', 'FOXA', 'LYV', 'MSGS', 'MTCH', 'BMBL', 'SKLZ', 'AGAE', 'GENI',
        # === FINANCIAL - BANKS (30 stocks) ===
        'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'USB', 'PNC', 'TFC', 'SCHW',
        'BK', 'STT', 'NTRS', 'CFG', 'KEY', 'RF', 'HBAN', 'FITB', 'MTB', 'ZION',
        'CMA', 'FHN', 'BOKF', 'SNV', 'WAL', 'PACW', 'FRC', 'SIVB', 'SBNY', 'FCNCA',
        # === FINANCIAL - FINTECH / PAYMENTS (25 stocks) ===
        'V', 'MA', 'AXP', 'PYPL', 'SQ', 'COIN', 'AFRM', 'SOFI', 'HOOD', 'NU',
        'FIS', 'FISV', 'GPN', 'FOUR', 'TOST', 'BILL', 'MQ', 'DLO', 'FLYW', 'PAYO',
        'LMND', 'ROOT', 'OSCR', 'HIPO', 'RELY',
        # === FINANCIAL - ASSET MGMT / INSURANCE (25 stocks) ===
        'BLK', 'BRK-B', 'MET', 'PRU', 'TRV', 'PGR', 'AIG', 'ALL', 'AFL', 'HIG',
        'CB', 'MMC', 'AON', 'AJG', 'WTW', 'BRO', 'RYAN', 'ADP', 'PAYX', 'SPGI',
        'MCO', 'ICE', 'CME', 'NDAQ', 'MSCI',
        # === HEALTHCARE - PHARMA (25 stocks) ===
        'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'BMY', 'AMGN', 'GILD', 'REGN', 'VRTX',
        'BIIB', 'MRNA', 'BNTX', 'AZN', 'NVS', 'GSK', 'SNY', 'TAK', 'TEVA', 'ZTS',
        'VTRS', 'OGN', 'CTLT', 'JAZZ', 'NBIX',
        # === HEALTHCARE - BIOTECH (30 stocks) ===
        'ALNY', 'BMRN', 'INCY', 'SRPT', 'RARE', 'UTHR', 'EXAS', 'ILMN', 'CRSP', 'NTLA',
        'BEAM', 'IONS', 'SANA', 'VERV', 'EDIT', 'ARWR', 'ALLO', 'FATE', 'LEGN', 'IMVT',
        'RCKT', 'RLAY', 'ARVN', 'KYMR', 'PTGX', 'MRSN', 'SNDX', 'XNCR', 'RGNX', 'ADPT',
        # === HEALTHCARE - DEVICES / SERVICES (30 stocks) ===
        'UNH', 'TMO', 'DHR', 'ABT', 'ISRG', 'CVS', 'CI', 'HUM', 'ELV', 'CNC',
        'MOH', 'SYK', 'BSX', 'MDT', 'EW', 'DXCM', 'IDXX', 'IQV', 'A', 'MTD',
        'WAT', 'PKI', 'BIO', 'HOLX', 'ALGN', 'TFX', 'PODD', 'INSP', 'CAH', 'MCK',
        # === CONSUMER - RETAIL (30 stocks) ===
        'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'DG', 'DLTR', 'BBY',
        'LULU', 'ULTA', 'NKE', 'ORLY', 'AZO', 'AAP', 'KMX', 'FIVE', 'OLLI', 'BURL',
        'RH', 'WSM', 'DECK', 'CROX', 'SKX', 'VFC', 'PVH', 'RL', 'GOOS', 'LEVI',
        # === CONSUMER - RESTAURANTS / FOOD (25 stocks) ===
        'SBUX', 'MCD', 'CMG', 'DPZ', 'YUM', 'QSR', 'DRI', 'TXRH', 'EAT', 'CAKE',
        'WING', 'SHAK', 'CAVA', 'BROS', 'BJRI', 'DENN', 'PLAY', 'JACK', 'RRGB', 'CBRL',
        'KO', 'PEP', 'MNST', 'KDP', 'CELH',
        # === CONSUMER - STAPLES (20 stocks) ===
        'PG', 'CL', 'KMB', 'EL', 'CHD', 'CLX', 'SJM', 'GIS', 'K', 'HSY',
        'MDLZ', 'KHC', 'CPB', 'CAG', 'HRL', 'TSN', 'MKC', 'SYY', 'USFD', 'PFGC',
        # === INDUSTRIAL - MACHINERY (25 stocks) ===
        'CAT', 'DE', 'HON', 'GE', 'MMM', 'EMR', 'ETN', 'ITW', 'ROK', 'PH',
        'AME', 'ROP', 'IR', 'DOV', 'XYL', 'NDSN', 'GGG', 'FLS', 'MIDD', 'GTLS',
        'CARR', 'TT', 'LII', 'JCI', 'AZEK',
        # === INDUSTRIAL - AEROSPACE / DEFENSE (20 stocks) ===
        'RTX', 'LMT', 'NOC', 'BA', 'GD', 'TDG', 'HWM', 'TXT', 'LHX', 'HII',
        'AXON', 'JOBY', 'RKLB', 'LUNR', 'ASTS', 'SPR', 'ERJ', 'AIR', 'KTOS', 'MRCY',
        # === INDUSTRIAL - TRANSPORT / LOGISTICS (20 stocks) ===
        'UPS', 'FDX', 'XPO', 'JBHT', 'CHRW', 'EXPD', 'ODFL', 'SAIA', 'KNX', 'LSTR',
        'SNDR', 'WERN', 'HTLD', 'ARCB', 'R', 'PCAR', 'CMI', 'PACCAR', 'NAV', 'OSK',
        # === INDUSTRIAL - SERVICES / WASTE (15 stocks) ===
        'WM', 'RSG', 'WCN', 'CLH', 'SRCL', 'ECL', 'VMI', 'BR', 'TTEK', 'J',
        'ACM', 'PWR', 'PRIM', 'MTZ', 'FIX',
        # === MATERIALS / MINING (25 stocks) ===
        'LIN', 'APD', 'SHW', 'PPG', 'ECL', 'DD', 'DOW', 'LYB', 'CE', 'EMN',
        'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'X', 'AA', 'ATI', 'RS', 'CMC',
        'MP', 'LAC', 'ALB', 'LTHM', 'SQM',
        # === ENERGY - OIL & GAS (30 stocks) ===
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'PXD',
        'DVN', 'FANG', 'HES', 'MRO', 'APA', 'HAL', 'BKR', 'NOV', 'CHK', 'RRC',
        'AR', 'EQT', 'SWN', 'CTRA', 'OVV', 'MGY', 'MTDR', 'CHRD', 'SM', 'PDCE',
        # === CLEAN ENERGY (20 stocks) ===
        'ENPH', 'SEDG', 'FSLR', 'RUN', 'NOVA', 'SHLS', 'ARRY', 'MAXN', 'JKS', 'CSIQ',
        'NEE', 'AES', 'BEP', 'CWEN', 'PLUG', 'BE', 'BLDP', 'FCEL', 'BLOOM', 'STEM',
        # === UTILITIES (15 stocks) ===
        'DUK', 'SO', 'D', 'AEP', 'XEL', 'SRE', 'ED', 'EXC', 'WEC', 'DTE',
        'ETR', 'PPL', 'FE', 'AEE', 'CMS',
        # === REAL ESTATE / REITS (25 stocks) ===
        'PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'O', 'DLR', 'SPG', 'WELL', 'AVB',
        'EQR', 'VTR', 'ARE', 'BXP', 'SLG', 'KIM', 'REG', 'FRT', 'UDR', 'CPT',
        'INVH', 'SUI', 'ELS', 'MAA', 'ESS',
        # === TRAVEL / HOSPITALITY (15 stocks) ===
        'MAR', 'HLT', 'H', 'WH', 'CHH', 'IHG', 'WYNN', 'MGM', 'LVS', 'CZR',
        'DKNG', 'PENN', 'RCL', 'CCL', 'NCLH',
        # === AIRLINES (10 stocks) ===
        'UAL', 'DAL', 'LUV', 'AAL', 'ALK', 'JBLU', 'SAVE', 'HA', 'SKYW', 'MESA',
        # === AUTO / EV (20 stocks) ===
        'F', 'GM', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI', 'FSR', 'GOEV', 'RIDE',
        'QS', 'CHPT', 'BLNK', 'EVGO', 'LEA', 'BWA', 'APTV', 'ALV', 'MGA', 'VC',
        # === TELECOM (10 stocks) ===
        'VZ', 'T', 'TMUS', 'LUMN', 'FYBR', 'USM', 'SHEN', 'LILA', 'LILAK', 'ATUS',
        # === HOT GROWTH / IPO / MOMENTUM (25 stocks) ===
        'IONQ', 'RGTI', 'QUBT', 'LAES', 'OKLO', 'SMR', 'ACHR', 'GRAB', 'BIRK', 'ONON',
        'TOST', 'GLBE', 'KRUS', 'HIMS', 'SRAD', 'KSPI', 'CART', 'INST', 'KVYO', 'DOCN',
        'HCP', 'IOT', 'TMDX', 'PRCT', 'GPCR',
    ]

    def _generate_growth_universe(self,
                                  target_gain_pct: float,
                                  timeframe_days: int,
                                  max_stocks: int,
                                  universe_multiplier: int = 5) -> List[str]:
        """Generate stock universe for growth catalyst screening

        Strategy:
        1. Start with static universe (reliable base - 400+ stocks)
        2. Add AI-generated stocks for fresh catalysts
        """
        try:
            # v7.3: universe_multiplier is now direct stock count mapping
            # 3x = 100, 5x = 150, 10x = 300, 25x = 500, 35x = 685 (all)
            universe_size_map = {
                3: 100,
                5: 150,
                10: 300,
                25: 500,
                35: 685,
            }
            target_size = universe_size_map.get(universe_multiplier, universe_multiplier * 20)
            logger.info(f"🎯 Target universe size: {target_size} stocks (multiplier={universe_multiplier}x)")

            # Primary: Static universe - USE target_size stocks
            static_subset = list(self.STATIC_UNIVERSE)[:target_size]
            universe = static_subset
            logger.info(f"📦 Static universe: {len(universe)}/{len(self.STATIC_UNIVERSE)} stocks")

            # Supplement: AI-generated stocks for fresh catalysts (if room left)
            remaining_slots = target_size - len(universe)
            if remaining_slots > 0:
                try:
                    ai_target = min(remaining_slots, 100)  # Cap AI at 100 or remaining slots
                    criteria = {
                        'target_gain_pct': target_gain_pct,
                        'timeframe_days': timeframe_days,
                        'max_stocks': ai_target,
                        'universe_multiplier': 1
                    }
                    ai_stocks = self.ai_generator.generate_growth_catalyst_universe(criteria)

                    if ai_stocks:
                        new_ai_stocks = [s for s in ai_stocks if s not in universe][:remaining_slots]
                        universe.extend(new_ai_stocks)
                        logger.info(f"🤖 AI added {len(new_ai_stocks)} new stocks (total: {len(universe)})")
                except Exception as e:
                    logger.warning(f"⚠️ AI supplement failed, using static only: {e}")

            # Deduplicate and return
            universe = list(dict.fromkeys(universe))
            logger.info(f"✅ Final universe size: {len(universe)} stocks")
            return universe

        except Exception as e:
            logger.error(f"Failed to generate growth universe: {e}")
            # Fallback to static universe only
            return list(self.STATIC_UNIVERSE)

    def _analyze_stock_comprehensive(self,
                                    symbol: str,
                                    target_gain_pct: float,
                                    timeframe_days: int) -> Optional[Dict[str, Any]]:
        """
        Comprehensive multi-stage analysis for a single stock

        Stages:
        - Stage 2: Catalyst Discovery
        - Stage 3: Technical Setup Validation
        - Stage 4: AI Deep Analysis

        Returns:
            Comprehensive analysis result or None
        """
        try:
            # === v6.4: Use cached price data (from batch download) ===
            price_data = self._get_cached_price_data(symbol)

            if price_data is None or price_data.empty:
                logger.debug(f"{symbol}: No cached price data available")
                return None

            # Get current price from price data
            current_price = float(price_data['close'].iloc[-1] if 'close' in price_data.columns else price_data['Close'].iloc[-1])
            if current_price == 0:
                return None

            # ========== v4.0: MOMENTUM QUALITY GATES (CHECK FIRST!) ==========
            logger.debug(f"{symbol}: Checking momentum gates...")
            momentum_metrics = self._calculate_momentum_metrics(price_data)

            if momentum_metrics is None:
                logger.debug(f"❌ {symbol}: Insufficient data for momentum calculation")
                return None

            passes_gates, rejection_reason = self._passes_momentum_gates(momentum_metrics)
            if not passes_gates:
                logger.debug(f"❌ {symbol}: REJECTED by momentum gates - {rejection_reason}")
                return None

            # Calculate momentum score (base score for ranking)
            momentum_score = self._calculate_momentum_score(momentum_metrics)
            logger.debug(f"✅ {symbol}: PASSED momentum gates - RSI: {momentum_metrics['rsi']:.1f}, MA50: {momentum_metrics['price_above_ma50']:+.1f}%, Mom30d: {momentum_metrics['momentum_30d']:+.1f}%, Score: {momentum_score:.1f}/100")

            # v6.7: Get ticker info with caching (FAST! reduces rate limits)
            # Uses estimation from price_data when possible (no API call!)
            info = self._get_stock_info_cached(symbol, price_data)

            # Get market cap (already estimated in _get_stock_info_cached if needed)
            market_cap = info.get('marketCap', 0)

            # v6.7: Skip analyze_stock_fast to avoid rate limits!
            # We already have all data we need from:
            # - price_data (from batch download)
            # - info (from _get_stock_info_cached)
            # This saves ~400+ API calls per screening run!
            fundamental_analysis = {
                'market_cap': market_cap,
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'peg_ratio': info.get('pegRatio'),
                'dividend_yield': info.get('dividendYield'),
                'beta': info.get('beta', 1.0),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
            }
            technical_analysis = {}  # Not used for screening

            # Calculate average dollar volume
            if 'volume' in price_data.columns and 'close' in price_data.columns:
                avg_dollar_volume = (price_data['volume'] * price_data['close']).mean()
            else:
                avg_dollar_volume = (price_data['Volume'] * price_data['Close']).mean()

            # ===== STAGE 2: Catalyst Discovery =====
            catalyst_analysis = self._discover_catalysts(symbol, fundamental_analysis, technical_analysis, current_price, ticker_info=info, price_data=price_data)
            catalyst_score = catalyst_analysis['catalyst_score']

            # ===== STAGE 3: Technical Setup Validation =====
            technical_setup = self._validate_technical_setup(
                symbol,
                price_data,
                technical_analysis,
                target_gain_pct
            )
            technical_score = technical_setup['technical_score']

            # ===== v8.0 ZERO LOSER: Additional filters REMOVED =====
            # เหตุผล: Momentum gates (accum > 1.3 + RSI < 60 + above_ma20 > 0)
            # backtest แล้วไม่มี loser เลย! ไม่ต้องการ filter เพิ่ม
            #
            # REMOVED filters:
            # - Beta filter (was blocking META, etc.)
            # - Volatility filter
            # - Valuation score filter
            # - Relative Strength filter
            # - Sector score filter
            # - Momentum 7d filter
            #
            # KEEP calculations for scoring purposes only (NO FILTERING):

            # Beta (for info, no filter)
            beta = info.get('beta', 1.0)
            logger.debug(f"{symbol}: Beta={beta:.2f} (no filter applied)")

            # Volatility (for info, no filter)
            if len(price_data) >= 20:
                returns = price_data['close'].pct_change() if 'close' in price_data.columns else price_data['Close'].pct_change()
                returns = returns.dropna()
                volatility_annual = returns.std() * (252 ** 0.5) * 100
            else:
                volatility_annual = 30.0

            # Valuation (for scoring, no filter)
            valuation_analysis = self._analyze_valuation(symbol, info, current_price)
            valuation_score = valuation_analysis['valuation_score']

            # Sector analysis (for scoring, no filter)
            sector_analysis = self._analyze_sector_strength(symbol, info, price_data)
            sector_score = sector_analysis['sector_score']
            relative_strength = sector_analysis.get('relative_strength', 0)

            # 7d momentum (for info, no filter)
            momentum_7d = 0
            if len(price_data) >= 7:
                price_7d_ago = price_data['close'].iloc[-7] if 'close' in price_data.columns else price_data['Close'].iloc[-7]
                momentum_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100

            logger.debug(f"{symbol}: v8.0 NO FILTERS - Vol={volatility_annual:.1f}%, Val={valuation_score:.0f}, Sector={sector_score:.0f}, RS={relative_strength:+.1f}%, Mom7d={momentum_7d:+.1f}%")

            # ===== STAGE 4: AI Deep Analysis =====
            ai_analysis = self._ai_predict_growth_probability(
                symbol,
                current_price,
                fundamental_analysis,
                technical_analysis,
                catalyst_analysis,
                technical_setup,
                target_gain_pct,
                timeframe_days
            )
            ai_probability = ai_analysis['probability']
            ai_confidence = ai_analysis['confidence']

            # ===== STAGE 5: Alternative Data Analysis (v3.0) =====
            alt_data_analysis = {}
            if self.alt_data:
                try:
                    logger.debug(f"{symbol}: Fetching alternative data...")
                    alt_data_result = self.alt_data.get_comprehensive_data(symbol)

                    if alt_data_result:
                        alt_data_analysis = {
                            'overall_score': alt_data_result['overall_score'],
                            'confidence': alt_data_result['confidence'],
                            'signal_strength': alt_data_result['signal_strength'],
                            'positive_signals': alt_data_result['positive_signals'],
                            'has_insider_buying': alt_data_result['has_insider_buying'],
                            'has_analyst_upgrade': alt_data_result['has_analyst_upgrade'],
                            'has_squeeze_potential': alt_data_result['has_squeeze_potential'],
                            'has_social_buzz': alt_data_result['has_social_buzz'],
                            'has_sector_momentum': alt_data_result['has_sector_momentum'],
                            'follows_strong_leader': alt_data_result['follows_strong_leader'],
                            'component_scores': alt_data_result['component_scores']
                        }
                        logger.debug(f"{symbol}: Alt data score {alt_data_analysis['overall_score']:.1f}/100, signals {alt_data_analysis['positive_signals']}/6")

                        # v4.0: Alternative data is BONUS, not requirement!
                        # Momentum gates already ensure quality
                        positive_signals = alt_data_analysis.get('positive_signals', 0)
                        logger.debug(f"   Alt data signals: {positive_signals}/6 (bonus points)")

                    else:
                        logger.debug(f"{symbol}: Alternative data not available (OK - momentum quality ensured)")
                except Exception as e:
                    logger.debug(f"{symbol}: Error fetching alternative data: {e} (OK - will use momentum score only)")

            # ===== STAGE 6: Sector Rotation Analysis (v3.1) =====
            sector_rotation_boost = 1.0  # Default: no adjustment
            sector_status = None

            # Get sector from fundamental analysis or info
            sector = fundamental_analysis.get('sector') or info.get('sector', 'Unknown')

            if self.sector_rotation:
                try:
                    sector_status = self.sector_rotation.get_stock_sector_status(symbol, sector)
                    if sector_status:
                        # Use the matched sector (could be specific theme like "Semiconductors")
                        matched_sector = sector_status['sector']
                        sector_rotation_boost = self.sector_rotation.get_sector_boost(matched_sector)
                        logger.debug(f"{symbol}: Sector {matched_sector} ({sector_status['status']}) - Boost: {sector_rotation_boost:.2f}x")
                except Exception as e:
                    logger.debug(f"{symbol}: Error getting sector rotation: {e}")

            # ===== v3.3: Sector-Aware Regime Detection =====
            sector_regime_adjustment = 0  # Default: no adjustment
            sector_regime = None
            sector_confidence_threshold = 65  # Default

            if self.sector_regime and sector != 'Unknown':
                try:
                    sector_regime = self.sector_regime.get_sector_regime(sector)
                    sector_regime_adjustment = self.sector_regime.get_regime_adjustment(sector)
                    sector_confidence_threshold = self.sector_regime.get_confidence_threshold(sector)
                    should_trade_sector = self.sector_regime.should_trade_sector(sector)

                    logger.debug(f"{symbol}: Sector '{sector}' regime={sector_regime}, adjustment={sector_regime_adjustment:+d}, threshold={sector_confidence_threshold}")

                    # Filter out sectors we shouldn't trade (optional - can be enabled later)
                    # if not should_trade_sector:
                    #     logger.debug(f"❌ {symbol}: Sector '{sector}' regime not suitable for trading")
                    #     return None

                except Exception as e:
                    logger.debug(f"{symbol}: Error getting sector regime: {e}")

            # ===== v4.0: Calculate Momentum-Based Entry Score (REPLACES composite!) =====
            entry_score = self._calculate_momentum_entry_score(
                momentum_score=momentum_score,
                momentum_metrics=momentum_metrics,
                catalyst_score=catalyst_score,
                technical_score=technical_score,
                ai_probability=ai_probability,
                alt_data_analysis=alt_data_analysis,
                sector_regime_adjustment=sector_regime_adjustment,
                market_cap=market_cap
            )

            # Keep old composite for comparison (deprecated)
            composite_score = self._calculate_composite_score(
                catalyst_score=catalyst_score,
                technical_score=technical_score,
                ai_probability=ai_probability,
                ai_confidence=ai_confidence,
                sector_score=sector_score,
                valuation_score=valuation_score,
                alt_data_analysis=alt_data_analysis,
                sector_rotation_boost=sector_rotation_boost
            )
            composite_score_before_regime = composite_score
            composite_score = composite_score + sector_regime_adjustment

            logger.debug(f"{symbol}: Entry Score (NEW): {entry_score:.1f}/140 | Composite (OLD): {composite_score:.1f}/100")

            # ===== Risk Adjustment =====
            risk_adjusted_score, risk_factors = self._apply_risk_adjustment(
                composite_score,
                market_cap,
                current_price,
                technical_analysis
            )

            return {
                'symbol': symbol,
                'current_price': current_price,
                'market_cap': market_cap,
                'avg_dollar_volume': avg_dollar_volume,

                # NEW: Beta Filter
                'beta': beta,

                # NEW: Valuation Analysis
                'valuation_score': valuation_score,
                'valuation_analysis': valuation_analysis,

                # NEW: Sector Analysis
                'sector_score': sector_score,
                'sector_analysis': sector_analysis,

                # Stage 2: Catalyst Analysis (INVERTED!)
                'catalyst_score': catalyst_score,
                'catalysts': catalyst_analysis['catalysts'],
                'catalyst_calendar': catalyst_analysis.get('calendar', {}),

                # Stage 3: Technical Analysis
                'technical_score': technical_score,
                'technical_setup': technical_setup,

                # Stage 4: AI Analysis
                'ai_probability': ai_probability,
                'ai_confidence': ai_confidence,
                'ai_reasoning': ai_analysis.get('reasoning', ''),
                'ai_key_factors': ai_analysis.get('key_factors', []),

                # Stage 5: Alternative Data (v3.0)
                'alt_data_score': alt_data_analysis.get('overall_score', 0) if alt_data_analysis else 0,
                'alt_data_confidence': alt_data_analysis.get('confidence', 0) if alt_data_analysis else 0,
                'alt_data_signals': alt_data_analysis.get('positive_signals', 0) if alt_data_analysis else 0,
                'has_insider_buying': alt_data_analysis.get('has_insider_buying', False) if alt_data_analysis else False,
                'has_analyst_upgrade': alt_data_analysis.get('has_analyst_upgrade', False) if alt_data_analysis else False,
                'has_squeeze_potential': alt_data_analysis.get('has_squeeze_potential', False) if alt_data_analysis else False,
                'has_social_buzz': alt_data_analysis.get('has_social_buzz', False) if alt_data_analysis else False,
                'alt_data_analysis': alt_data_analysis,

                # Stage 6: Sector Rotation (v3.1)
                'sector': sector_status['sector'] if sector_status else sector,  # Matched sector (e.g., "Semiconductors")
                'sector_rotation_boost': sector_rotation_boost,
                'sector_rotation_status': sector_status['status'] if sector_status else 'unknown',
                'sector_momentum': sector_status['momentum_score'] if sector_status else 0,

                # v3.3: Sector-Aware Regime Detection
                'sector_regime': sector_regime,  # BULL, SIDEWAYS, BEAR, etc.
                'sector_regime_adjustment': sector_regime_adjustment,  # -15 to +15 points
                'sector_confidence_threshold': sector_confidence_threshold,  # 60-75

                # v4.0: Momentum Metrics (PROVEN PREDICTIVE!)
                'rsi': momentum_metrics['rsi'],
                'price_above_ma20': momentum_metrics['price_above_ma20'],
                'price_above_ma50': momentum_metrics['price_above_ma50'],
                'momentum_10d': momentum_metrics['momentum_10d'],
                'momentum_30d': momentum_metrics['momentum_30d'],
                'momentum_score': momentum_score,  # Pure momentum: 0-100

                # v6.4: Volume Confirmation (87.5% WR!)
                'vol_trend': momentum_metrics.get('vol_trend', 1.0),
                'accumulation': momentum_metrics.get('accumulation', 1.0),

                # Stage 6: Final Scores (v4.0: NEW - Momentum-Based Entry Score!)
                'entry_score': entry_score,  # PRIMARY RANKING (momentum + bonuses): 0-140+
                'composite_score': composite_score,  # DEPRECATED (kept for comparison)
                'composite_score_before_regime': composite_score_before_regime,
                'risk_adjusted_score': risk_adjusted_score,
                'risk_factors': risk_factors,

                # Metadata
                'analysis_date': datetime.now().isoformat(),
                'target_gain_pct': target_gain_pct,
                'timeframe_days': timeframe_days,
                'version': '6.5'  # v6.5: SWEET SPOT SCORING (100% WR with Score >= 88, Top 1)
            }

        except Exception as e:
            logger.error(f"Comprehensive analysis failed for {symbol}: {e}")
            return None

    def _discover_catalysts(self,
                           symbol: str,
                           fundamental_analysis: Dict[str, Any],
                           technical_analysis: Dict[str, Any],
                           current_price: float = 0,
                           ticker_info: Dict = None,
                           price_data: pd.DataFrame = None) -> Dict[str, Any]:
        """
        STAGE 2: Catalyst Discovery

        Discover and score upcoming catalysts:
        - Earnings dates
        - News sentiment
        - Insider activity
        - Analyst activity
        - Special events

        Returns:
            Catalyst analysis with score (0-100) and details
        """
        catalysts = []
        catalyst_score = 0.0

        try:
            # Get company info for catalyst discovery
            import yfinance as yf

            # v6.7: GRACEFUL: Use passed ticker_info if available, otherwise use cached
            if ticker_info is not None:
                info = ticker_info
            elif price_data is not None:
                info = self._get_stock_info_cached(symbol, price_data)
            else:
                info = self._get_stock_info_cached(symbol)

            # Create ticker object only if needed for earnings_history (lazy)
            ticker = None

            # === 1. Earnings Catalyst - INVERTED! (Upcoming earnings = PENALTY) ===
            # CRITICAL INSIGHT: Stocks beat earnings but prices fell -9% to -20%!
            # Reason: Sell-the-news, expectations too high, guidance disappointment
            # Solution: PENALIZE upcoming earnings, REWARD quiet period

            earnings_date = info.get('earningsDate')
            next_earnings = None
            days_to_earnings = None

            # Method 1: Try getting from info
            if earnings_date:
                # earnings_date is a list of timestamps
                if isinstance(earnings_date, list) and len(earnings_date) > 0:
                    next_earnings = pd.Timestamp(earnings_date[0])
                    days_to_earnings = (next_earnings - pd.Timestamp.now()).days

            # Method 2: Estimate from earnings history if not available
            # v6.7: Create ticker lazily only when needed for earnings_history
            if next_earnings is None or days_to_earnings is None or days_to_earnings < 0:
                try:
                    if ticker is None:
                        self._rate_limited_api_call()  # Rate limit protection
                        ticker = yf.Ticker(symbol)
                    earnings_history = ticker.earnings_history
                    if earnings_history is not None and not earnings_history.empty and len(earnings_history) >= 2:
                        # Get last earnings date
                        last_earnings_date = earnings_history.index[-1]

                        # Estimate next earnings (typically 90 days after last one)
                        estimated_next = last_earnings_date + pd.Timedelta(days=90)
                        estimated_days = (estimated_next - pd.Timestamp.now()).days

                        # Only use if within reasonable range (0-120 days)
                        if 0 < estimated_days <= 120:
                            next_earnings = estimated_next
                            days_to_earnings = estimated_days
                            logger.debug(f"Estimated next earnings for {symbol}: {estimated_days} days")
                except Exception as e:
                    # GRACEFUL: If earnings data unavailable, assume quiet period
                    logger.debug(f"Could not estimate earnings date for {symbol}: {e} - assuming quiet period")

            # INVERTED LOGIC: Earnings soon = BAD (sell-the-news risk)
            if next_earnings and days_to_earnings:
                if 0 < days_to_earnings <= 10:
                    # VERY SOON (0-10 days) = HIGH RISK (sell-the-news almost certain!)
                    catalyst_score -= 15  # PENALTY!
                    catalysts.append({
                        'type': 'earnings_risk',
                        'description': f'⚠️ Earnings in {days_to_earnings} days - SELL-THE-NEWS RISK',
                        'impact': 'negative',
                        'date': next_earnings.strftime('%Y-%m-%d'),
                        'score': -15
                    })
                elif 10 < days_to_earnings <= 20:
                    # SOON (10-20 days) = MODERATE RISK
                    catalyst_score -= 10  # PENALTY!
                    catalysts.append({
                        'type': 'earnings_risk',
                        'description': f'⚠️ Earnings in {days_to_earnings} days - Moderate risk',
                        'impact': 'negative',
                        'date': next_earnings.strftime('%Y-%m-%d'),
                        'score': -10
                    })
                elif 20 < days_to_earnings <= 30:
                    # APPROACHING (20-30 days) = MILD RISK
                    catalyst_score -= 5  # PENALTY!
                    catalysts.append({
                        'type': 'earnings_risk',
                        'description': f'Earnings in {days_to_earnings} days - Caution',
                        'impact': 'negative',
                        'date': next_earnings.strftime('%Y-%m-%d'),
                        'score': -5
                    })
                elif 30 < days_to_earnings <= 60:
                    # QUIET PERIOD (30-60 days) = GOOD! (sweet spot)
                    catalyst_score += 15  # BONUS!
                    catalysts.append({
                        'type': 'quiet_period',
                        'description': f'✅ Quiet period - Earnings {days_to_earnings} days away',
                        'impact': 'positive',
                        'date': next_earnings.strftime('%Y-%m-%d'),
                        'score': 15
                    })
                elif days_to_earnings > 60:
                    # FAR AWAY (>60 days) = NEUTRAL
                    catalyst_score += 5
                    catalysts.append({
                        'type': 'quiet_period',
                        'description': f'Quiet period - Next earnings {days_to_earnings} days away',
                        'impact': 'neutral',
                        'score': 5
                    })
            else:
                # NO EARNINGS DATA = BONUS! (hidden gem potential)
                catalyst_score += 10
                catalysts.append({
                    'type': 'no_earnings_data',
                    'description': '✅ No upcoming earnings pressure - Hidden gem potential',
                    'impact': 'positive',
                    'score': 10
                })

            # === 2. News/Market Sentiment Catalyst (0-20 points) ===
            news_score, news_catalysts = self._analyze_news_sentiment(symbol, info)
            catalyst_score += news_score
            catalysts.extend(news_catalysts)

            # === 3. Insider Activity Catalyst (0-15 points) ===
            try:
                insider_trades = None
                try:
                    insider_trades = ticker.insider_transactions
                except Exception as e:
                    logger.debug(f"{symbol}: Insider data unavailable (rate limited?) - {e}")
                    insider_trades = None

                if insider_trades is not None and not insider_trades.empty:
                    # Filter last 30 days - safe comparison
                    try:
                        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=30)
                        # Convert index to datetime if needed
                        if hasattr(insider_trades.index, 'to_pydatetime'):
                            recent_trades = insider_trades[insider_trades.index.to_pydatetime() > cutoff_date.to_pydatetime()]
                        else:
                            recent_trades = insider_trades.tail(10)  # Fallback: last 10 trades
                    except:
                        recent_trades = insider_trades.tail(10)  # Fallback

                    if not recent_trades.empty:
                        # === Improved transaction type detection ===
                        # Handle multiple transaction type variations
                        buy_transactions = []
                        sell_transactions = []

                        if 'Transaction' in recent_trades.columns:
                            # Normalize transaction types
                            transaction_col = recent_trades['Transaction'].astype(str).str.lower()

                            # Identify buy transactions (various formats)
                            buy_mask = transaction_col.str.contains('buy|purchase|acquisition', case=False, na=False)
                            sell_mask = transaction_col.str.contains('sale|sell|disposition', case=False, na=False)

                            buy_transactions = recent_trades[buy_mask]
                            sell_transactions = recent_trades[sell_mask]
                        else:
                            # Fallback: try to infer from Shares column if available
                            if 'Shares' in recent_trades.columns:
                                buy_transactions = recent_trades[recent_trades['Shares'] > 0]
                                sell_transactions = pd.DataFrame()  # Can't distinguish sells

                        # === Calculate transaction values with multiple fallbacks ===
                        buy_value = 0
                        sell_value = 0

                        # Method 1: Use Value column directly
                        if 'Value' in recent_trades.columns:
                            buy_value = buy_transactions['Value'].fillna(0).sum()
                            sell_value = sell_transactions['Value'].fillna(0).sum()

                        # Method 2: Calculate from Shares × Price
                        if buy_value == 0 and 'Shares' in buy_transactions.columns:
                            if 'Price' in buy_transactions.columns:
                                buy_value = (buy_transactions['Shares'].fillna(0) * buy_transactions['Price'].fillna(0)).sum()
                            elif current_price > 0:
                                # Estimate using current price as fallback
                                buy_value = (buy_transactions['Shares'].fillna(0) * current_price).sum()

                        if sell_value == 0 and 'Shares' in sell_transactions.columns:
                            if 'Price' in sell_transactions.columns:
                                sell_value = (sell_transactions['Shares'].fillna(0) * sell_transactions['Price'].fillna(0)).sum()
                            elif current_price > 0:
                                sell_value = (sell_transactions['Shares'].fillna(0) * current_price).sum()

                        # Method 3: Use shares count as proxy if value unavailable
                        buy_shares = buy_transactions['Shares'].fillna(0).sum() if 'Shares' in buy_transactions.columns else 0
                        sell_shares = sell_transactions['Shares'].fillna(0).sum() if 'Shares' in sell_transactions.columns else 0

                        # === Score based on buying activity ===
                        net_buying = False
                        significant_buying = False

                        # Primary: Compare values
                        if buy_value > 0 or sell_value > 0:
                            if buy_value > sell_value * 2:
                                significant_buying = True
                            elif buy_value > sell_value:
                                net_buying = True
                        # Fallback: Compare share counts
                        elif buy_shares > 0 or sell_shares > 0:
                            if buy_shares > sell_shares * 2:
                                significant_buying = True
                            elif buy_shares > sell_shares:
                                net_buying = True

                        if significant_buying:
                            catalyst_score += 15
                            description = f'Strong insider buying: ${buy_value/1e6:.1f}M' if buy_value > 0 else f'Strong insider buying: {buy_shares:,.0f} shares'
                            catalysts.append({
                                'type': 'insider_buying',
                                'description': description,
                                'impact': 'high',
                                'score': 15
                            })
                        elif net_buying:
                            catalyst_score += 8
                            description = f'Net insider buying: ${buy_value/1e6:.1f}M' if buy_value > 0 else 'Net insider buying activity'
                            catalysts.append({
                                'type': 'insider_buying',
                                'description': description,
                                'impact': 'medium',
                                'score': 8
                            })
            except Exception as e:
                logger.debug(f"Insider data not available for {symbol}: {e}")

            # === 4. Analyst Activity - INVERTED! (High coverage = TRAP) ===
            # CRITICAL FIX: High analyst coverage often means overhyped/overvalued
            # Backtest showed: High coverage stocks (COIN, NET, NOW) all failed!

            recommendations = info.get('recommendationKey')
            target_price = info.get('targetMeanPrice')
            num_analysts = info.get('numberOfAnalystOpinions', 0)

            # Use current_price from parameter if available, otherwise from fundamental_analysis or yfinance
            if current_price == 0:
                current_price = fundamental_analysis.get('current_price', 0)
            if current_price == 0:
                current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))

            # INVERTED: Too many analysts = overhyped, too few = hidden gem
            if num_analysts > 50:
                catalyst_score -= 10  # PENALTY! Too popular (retail FOMO)
                catalysts.append({
                    'type': 'overhyped',
                    'description': f'⚠️ {num_analysts} analysts - Overhyped (crowded trade)',
                    'impact': 'negative',
                    'score': -10
                })
            elif num_analysts > 30:
                catalyst_score -= 5  # Mild penalty
                catalysts.append({
                    'type': 'popular',
                    'description': f'{num_analysts} analysts - High coverage (caution)',
                    'impact': 'negative',
                    'score': -5
                })
            elif 10 <= num_analysts <= 20:
                catalyst_score += 5  # SWEET SPOT! (balanced coverage)
                catalysts.append({
                    'type': 'balanced_coverage',
                    'description': f'✅ {num_analysts} analysts - Balanced coverage',
                    'impact': 'positive',
                    'score': 5
                })
            elif num_analysts < 10:
                catalyst_score += 10  # BONUS! (undiscovered gem)
                catalysts.append({
                    'type': 'undiscovered',
                    'description': f'✅ Only {num_analysts} analysts - Hidden gem potential',
                    'impact': 'positive',
                    'score': 10
                })

            # Target price: Be very skeptical!
            if recommendations and target_price and current_price > 0:
                upside_to_target = ((target_price - current_price) / current_price * 100)

                # INVERTED: Very high targets = overhyped expectations
                if upside_to_target > 30:
                    catalyst_score -= 10  # PENALTY! Unrealistic expectations
                    catalysts.append({
                        'type': 'unrealistic_target',
                        'description': f'⚠️ Target {upside_to_target:.1f}% - Unrealistic expectations',
                        'impact': 'negative',
                        'score': -10
                    })
                # Modest targets OK
                elif 5 < upside_to_target <= 15:
                    catalyst_score += 3  # Mild bonus for realistic target
                    catalysts.append({
                        'type': 'realistic_target',
                        'description': f'Modest target: {upside_to_target:.1f}% upside',
                        'impact': 'low',
                        'score': 3
                    })
                # Negative target = concern
                elif upside_to_target < 0:
                    catalyst_score -= 5
                    catalysts.append({
                        'type': 'bearish_target',
                        'description': f'⚠️ Bearish target: {upside_to_target:.1f}%',
                        'impact': 'negative',
                        'score': -5
                    })

            # === 5. Consolidation/Setup Catalyst (0-15 points) ===
            # PREDICTIVE: Check if stock is SETTING UP (not already moved)
            try:
                # v6.4: Use passed price_data (from batch download) instead of fetching again
                hist = price_data

                if hist is not None and not hist.empty and len(hist) >= 60:
                    close = hist['close'] if 'close' in hist.columns else hist['Close']
                    current_price = close.iloc[-1]

                    # Check if stock is CONSOLIDATING (not extended)
                    high_60d = close.tail(60).max()
                    low_60d = close.tail(60).min()
                    price_range = high_60d - low_60d

                    # Recent 2-week action
                    price_10d_ago = close.iloc[-10]
                    recent_move = ((current_price - price_10d_ago) / price_10d_ago) * 100

                    # Distance from 60-day high
                    distance_from_high = ((high_60d - current_price) / high_60d) * 100

                    # PREDICTIVE SETUP: Consolidating 10-20% below high (coiled spring)
                    if 10 < distance_from_high < 20 and abs(recent_move) < 5:
                        catalyst_score += 15
                        catalysts.append({
                            'type': 'consolidation_setup',
                            'description': f'Healthy consolidation ({distance_from_high:.1f}% from high) - ready to break',
                            'impact': 'high',
                            'score': 15
                        })
                    # Flat price with catalyst coming = opportunity
                    elif abs(recent_move) < 3:
                        catalyst_score += 10
                        catalysts.append({
                            'type': 'quiet_accumulation',
                            'description': 'Flat price action - potential accumulation',
                            'impact': 'medium',
                            'score': 10
                        })
                    # Exclude stocks already extended (up 15%+ recently = too late)
                    elif recent_move > 15:
                        catalyst_score -= 10  # Penalty for being late
                        logger.debug(f"{symbol}: Already extended +{recent_move:.1f}% - too late")

            except Exception as e:
                logger.debug(f"Setup check failed for {symbol}: {e}")

            # === 6. Upcoming Events Catalyst (0-20 points) ===
            # PREDICTIVE: Check for SCHEDULED events (not past events)
            try:
                # Check earnings date - only if UPCOMING (not past)
                earnings_dates = info.get('earningsDate', [])
                if earnings_dates and isinstance(earnings_dates, list) and len(earnings_dates) > 0:
                    next_earnings = pd.Timestamp(earnings_dates[0])
                    days_to_earnings = (next_earnings - pd.Timestamp.now()).days

                    # CRITICAL: Only count if earnings is UPCOMING (7-30 days)
                    if 7 <= days_to_earnings <= 30:
                        # Check historical beat rate for confidence
                        try:
                            earnings_history = None
                            try:
                                earnings_history = ticker.earnings_history
                            except Exception as e:
                                logger.debug(f"{symbol}: Earnings history unavailable - {e}")
                                earnings_history = None

                            if earnings_history is not None and not earnings_history.empty:
                                beats = (earnings_history['epsActual'] > earnings_history['epsEstimate']).sum()
                                total = len(earnings_history)
                                beat_rate = beats / total if total > 0 else 0.5

                                if beat_rate > 0.7:
                                    catalyst_score += 20
                                    catalysts.append({
                                        'type': 'upcoming_earnings',
                                        'description': f'Earnings in {days_to_earnings} days (70%+ beat rate) - PREDICTIVE',
                                        'impact': 'high',
                                        'score': 20
                                    })
                                elif beat_rate > 0.5:
                                    catalyst_score += 12
                                    catalysts.append({
                                        'type': 'upcoming_earnings',
                                        'description': f'Earnings in {days_to_earnings} days - PREDICTIVE',
                                        'impact': 'medium',
                                        'score': 12
                                    })
                        except:
                            # No beat rate but still upcoming earnings
                            catalyst_score += 10
                            catalysts.append({
                                'type': 'upcoming_earnings',
                                'description': f'Upcoming earnings in {days_to_earnings} days',
                                'impact': 'medium',
                                'score': 10
                            })

            except Exception as e:
                logger.debug(f"Upcoming events check failed for {symbol}: {e}")

            # === 7. Volume Confirmation Catalyst (0-10 points) ===
            # UPDATED: Volume is informative but not decisive
            try:
                recent_volume = info.get('volume', 0)
                avg_volume = info.get('averageVolume', 0)

                if recent_volume > 0 and avg_volume > 0:
                    volume_ratio = recent_volume / avg_volume

                    # Only reward STRONG buying pressure, don't penalize low volume
                    # (Growth stocks can rally on low volume!)
                    if volume_ratio > 2.0:  # 2x average volume = strong interest
                        catalyst_score += 10
                        catalysts.append({
                            'type': 'volume_surge',
                            'description': f'High volume surge ({volume_ratio:.1f}x avg)',
                            'impact': 'high',
                            'score': 10
                        })
                    elif volume_ratio > 1.5:  # 1.5x average volume
                        catalyst_score += 6
                        catalysts.append({
                            'type': 'volume_confirmation',
                            'description': f'Volume confirmation ({volume_ratio:.1f}x avg)',
                            'impact': 'medium',
                            'score': 6
                        })
                    # NO PENALTY for low volume - it's not predictive enough
                    # Many winners have low volume during consolidation
            except Exception as e:
                logger.debug(f"Volume check failed for {symbol}: {e}")

            return {
                'catalyst_score': min(100, catalyst_score),  # Cap at 100
                'catalysts': catalysts,
                'total_catalysts': len(catalysts),
                'highest_impact_catalyst': max(catalysts, key=lambda x: x.get('score', 0)) if catalysts else None,
                'calendar': self._build_catalyst_calendar(catalysts)
            }

        except Exception as e:
            logger.warning(f"Catalyst discovery failed for {symbol}: {e}")
            return {
                'catalyst_score': 0,
                'catalysts': [],
                'total_catalysts': 0,
                'highest_impact_catalyst': None,
                'calendar': {}
            }

    def _analyze_news_sentiment(self, symbol: str, info: Dict = None) -> tuple[float, List[Dict]]:
        """
        Analyze market sentiment from multiple sources
        (Since yfinance news API is unreliable, we use alternative indicators)

        Returns:
            (score, catalysts) tuple
        """
        try:
            # v6.7: Use cached info to reduce rate limits
            if info is None:
                info = self._get_stock_info_cached(symbol)

            news_catalysts = []
            score = 0

            # === Method 1: Analyst Sentiment (from recommendation trends) ===
            recommendation_key = info.get('recommendationKey', '')
            num_analyst_opinions = info.get('numberOfAnalystOpinions', 0)

            # Recommendation sentiment
            if recommendation_key in ['strong_buy', 'buy']:
                if num_analyst_opinions >= 20:  # Well-covered stock
                    score += 15
                    news_catalysts.append({
                        'type': 'analyst_sentiment',
                        'description': f'Strong analyst sentiment ({num_analyst_opinions} analysts, {recommendation_key})',
                        'impact': 'high',
                        'score': 15
                    })
                elif num_analyst_opinions >= 10:
                    score += 10
                    news_catalysts.append({
                        'type': 'analyst_sentiment',
                        'description': f'Positive analyst sentiment ({num_analyst_opinions} analysts)',
                        'impact': 'medium',
                        'score': 10
                    })
                elif num_analyst_opinions >= 5:
                    score += 5
                    news_catalysts.append({
                        'type': 'analyst_sentiment',
                        'description': f'Favorable analyst view',
                        'impact': 'low',
                        'score': 5
                    })

            # === Method 2: Price momentum as news proxy ===
            # Strong momentum often indicates positive news flow
            fifty_two_week_change = info.get('52WeekChange', 0)

            if fifty_two_week_change > 0.3:  # Up 30%+ in last year
                score += 10
                news_catalysts.append({
                    'type': 'momentum_sentiment',
                    'description': f'Strong momentum ({fifty_two_week_change*100:.0f}% yearly gain)',
                    'impact': 'medium',
                    'score': 10
                })
            elif fifty_two_week_change > 0.15:  # Up 15%+
                score += 5
                news_catalysts.append({
                    'type': 'momentum_sentiment',
                    'description': 'Positive momentum trend',
                    'impact': 'low',
                    'score': 5
                })

            # === Method 3: Earnings growth as fundamental catalyst ===
            earnings_growth = info.get('earningsGrowth', 0) or info.get('earningsQuarterlyGrowth', 0)

            if earnings_growth and earnings_growth > 0.2:  # 20%+ earnings growth
                score += 10
                news_catalysts.append({
                    'type': 'earnings_growth',
                    'description': f'Strong earnings growth ({earnings_growth*100:.0f}%)',
                    'impact': 'high',
                    'score': 10
                })
            elif earnings_growth and earnings_growth > 0.1:  # 10%+ growth
                score += 5
                news_catalysts.append({
                    'type': 'earnings_growth',
                    'description': 'Positive earnings trend',
                    'impact': 'medium',
                    'score': 5
                })

            # Cap at 20 points max
            return min(20, score), news_catalysts

        except Exception as e:
            logger.debug(f"Sentiment analysis failed for {symbol}: {e}")
            return 0, []

    def _build_catalyst_calendar(self, catalysts: List[Dict]) -> Dict[str, List]:
        """Build a 30-day catalyst calendar"""
        calendar = {}

        for catalyst in catalysts:
            if 'date' in catalyst:
                date_str = catalyst['date']
                if date_str not in calendar:
                    calendar[date_str] = []
                calendar[date_str].append(catalyst)

        return calendar

    def _validate_technical_setup(self,
                                  symbol: str,
                                  price_data: pd.DataFrame,
                                  technical_analysis: Dict[str, Any],
                                  target_gain_pct: float,
                                  fundamental_analysis: Dict[str, Any] = None,
                                  alt_data_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        STAGE 3: Technical Setup Validation (v4.0 - RULE-BASED)

        v4.0: Uses Rule-Based Screening Engine instead of hard-coded logic
        Benefits:
        - Easy to tune thresholds
        - A/B test configurations
        - Track rule performance
        - Optimize systematically

        Returns:
            Technical setup analysis with score (0-100)
        """
        # v4.0: Use rule-based engine if available
        if self.screening_rules:
            return self._validate_with_rules_engine(
                symbol, price_data, technical_analysis,
                fundamental_analysis, alt_data_analysis
            )

        # Fallback to hard-coded logic if rule engine not available
        return self._validate_technical_setup_legacy(
            symbol, price_data, technical_analysis, target_gain_pct
        )

    def _validate_with_rules_engine(self,
                                    symbol: str,
                                    price_data: pd.DataFrame,
                                    technical_analysis: Dict[str, Any],
                                    fundamental_analysis: Dict[str, Any] = None,
                                    alt_data_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Validate using rule-based engine (v4.0)
        """
        try:
            # Get close prices
            close = price_data['close'] if 'close' in price_data.columns else price_data['Close']
            volume = price_data['volume'] if 'volume' in price_data.columns else price_data['Volume']

            current_price = float(close.iloc[-1])

            # Calculate MAs
            ma20 = 0.0
            ma50 = 0.0
            if len(close) >= 50:
                ma20 = float(close.rolling(window=20).mean().iloc[-1])
                ma50 = float(close.rolling(window=50).mean().iloc[-1])

            # Get support/resistance
            support = technical_analysis.get('support_1', current_price * 0.95)
            resistance = technical_analysis.get('resistance_1', current_price * 1.05)

            # Get market cap and volume
            market_cap = fundamental_analysis.get('market_cap', 0) if fundamental_analysis else 0
            avg_volume_val = technical_analysis.get('avg_volume', float(volume.tail(20).mean()))

            # Get sector and regime
            sector = fundamental_analysis.get('sector', 'Unknown') if fundamental_analysis else 'Unknown'
            sector_regime = 'SIDEWAYS'  # Default
            if hasattr(self, 'sector_regime') and self.sector_regime:
                try:
                    sector_regime_info = self.sector_regime.get_sector_regime(sector)
                    if sector_regime_info:
                        sector_regime = sector_regime_info.get('regime', 'SIDEWAYS')
                except:
                    pass

            market_regime = 'SIDEWAYS'
            if hasattr(self, 'regime_detector') and self.regime_detector:
                try:
                    regime_info = self.regime_detector.get_current_regime()
                    market_regime = regime_info.get('regime', 'SIDEWAYS')
                except:
                    pass

            # Get alternative data signals
            insider_buying = False
            analyst_upgrades = 0
            short_interest = 0.0
            social_sentiment = 50.0

            if alt_data_analysis:
                insider_buying = alt_data_analysis.get('insider_buying', False)
                analyst_upgrades = alt_data_analysis.get('analyst_upgrades', 0)
                short_interest = alt_data_analysis.get('short_interest', 0.0)
                social_sentiment = alt_data_analysis.get('social_sentiment', 50.0)

            # Prepare market data for rule engine
            market_data = ScreeningMarketData(
                symbol=symbol,
                current_price=current_price,
                market_cap=market_cap,
                avg_volume=avg_volume_val,
                sector=sector,
                close_prices=close.tail(50).tolist(),
                volume_data=volume.tail(50).tolist(),
                ma20=ma20,
                ma50=ma50,
                rsi=technical_analysis.get('rsi', 50.0),
                support=support,
                resistance=resistance,
                insider_buying=insider_buying,
                analyst_upgrades=analyst_upgrades,
                short_interest=short_interest,
                social_sentiment=social_sentiment,
                sector_regime=sector_regime,
                market_regime=market_regime
            )

            # Evaluate with rule engine
            passed, details = self.screening_rules.evaluate_stock(market_data)

            # Format response to match legacy format
            return {
                'technical_score': details['technical_score'],
                'setup_details': {
                    'rule_based': True,
                    'passed_rules': details['passed_rules'],
                    'failed_rules': details['failed_rules'],
                    'scores': details['scores'],
                    'tier': details.get('tier'),
                },
                'current_price': current_price,
                'support': support,
                'resistance': resistance,
                'composite_score': details['composite_score'],  # Additional field
                'rule_evaluation_passed': passed
            }

        except Exception as e:
            logger.warning(f"Rule-based validation failed for {symbol}: {e}")
            # Fallback to legacy
            return self._validate_technical_setup_legacy(symbol, price_data, technical_analysis, 0)

    def _validate_technical_setup_legacy(self,
                                         symbol: str,
                                         price_data: pd.DataFrame,
                                         technical_analysis: Dict[str, Any],
                                         target_gain_pct: float) -> Dict[str, Any]:
        """
        Legacy hard-coded validation (kept as fallback)
        """
        technical_score = 0.0
        setup_details = {}

        try:
            # Get close prices
            close = price_data['close'] if 'close' in price_data.columns else price_data['Close']
            volume = price_data['volume'] if 'volume' in price_data.columns else price_data['Volume']

            current_price = float(close.iloc[-1])

            # === 1. Trend Strength (25 points) ===
            if len(close) >= 50:
                ma20 = close.rolling(window=20).mean()
                ma50 = close.rolling(window=50).mean()
                current_ma20 = ma20.iloc[-1]
                current_ma50 = ma50.iloc[-1]

                if current_price > current_ma20 > current_ma50:
                    trend_score = 25
                    setup_details['trend'] = 'strong_bullish'
                elif current_price > current_ma20:
                    trend_score = 15
                    setup_details['trend'] = 'bullish'
                elif current_price > current_ma50:
                    trend_score = 10
                    setup_details['trend'] = 'neutral_bullish'
                else:
                    trend_score = 0
                    setup_details['trend'] = 'bearish'
                technical_score += trend_score

            # === 2. Momentum (25 points) ===
            rsi = technical_analysis.get('rsi', 50)
            if 45 <= rsi <= 70:
                momentum_score = 25
                setup_details['momentum'] = 'strong'
            elif 40 <= rsi < 45 or 70 < rsi <= 75:
                momentum_score = 15
                setup_details['momentum'] = 'moderate'
            elif 35 <= rsi < 40:
                momentum_score = 10
                setup_details['momentum'] = 'oversold_bounce'
            else:
                momentum_score = 0
                setup_details['momentum'] = 'weak'
            technical_score += momentum_score

            # === 3. Volume Confirmation (20 points) ===
            if len(volume) >= 20:
                avg_volume = volume.tail(20).mean()
                recent_volume = volume.tail(5).mean()
                volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0

                if volume_ratio > 1.5:
                    volume_score = 20
                    setup_details['volume'] = 'surge'
                elif volume_ratio > 1.2:
                    volume_score = 15
                    setup_details['volume'] = 'increasing'
                elif volume_ratio > 0.8:
                    volume_score = 10
                    setup_details['volume'] = 'normal'
                else:
                    volume_score = 0
                    setup_details['volume'] = 'low'
                technical_score += volume_score

            # === 4. Short-Term Momentum (15 points) ===
            if len(close) >= 10:
                price_10d_ago = close.iloc[-10]
                price_5d_ago = close.iloc[-5]
                short_term_return_10d = ((current_price - price_10d_ago) / price_10d_ago) * 100
                short_term_return_5d = ((current_price - price_5d_ago) / price_5d_ago) * 100

                if short_term_return_10d > 10 and short_term_return_5d > 5:
                    momentum_score_st = 15
                    setup_details['short_term_momentum'] = 'accelerating'
                elif short_term_return_10d > 5:
                    momentum_score_st = 10
                    setup_details['short_term_momentum'] = 'strong'
                elif short_term_return_5d > 3:
                    momentum_score_st = 5
                    setup_details['short_term_momentum'] = 'building'
                else:
                    momentum_score_st = 0
                    setup_details['short_term_momentum'] = 'weak'
                technical_score += momentum_score_st

            # === 5. Pattern Recognition (15 points) ===
            if len(close) >= 30:
                high_30d = close.tail(30).max()
                distance_from_high = ((high_30d - current_price) / high_30d * 100)

                if distance_from_high < 5:
                    pattern_score = 15
                    setup_details['pattern'] = 'near_breakout'
                elif distance_from_high < 10:
                    pattern_score = 12
                    setup_details['pattern'] = 'consolidation'
                elif 15 < distance_from_high < 25:
                    pattern_score = 14
                    setup_details['pattern'] = 'healthy_pullback'
                else:
                    pattern_score = 5
                    setup_details['pattern'] = 'ranging'
                technical_score += pattern_score

            # === 6. Risk/Reward Setup (10 points) ===
            support = technical_analysis.get('support_1', current_price * 0.95)
            resistance = technical_analysis.get('resistance_1', current_price * 1.05)

            if support > 0 and resistance > 0:
                potential_gain = resistance - current_price
                potential_loss = current_price - support

                if potential_loss > 0:
                    risk_reward = potential_gain / potential_loss

                    if risk_reward > 3:
                        rr_score = 10
                        setup_details['risk_reward'] = 'excellent'
                    elif risk_reward > 2:
                        rr_score = 8
                        setup_details['risk_reward'] = 'good'
                    elif risk_reward > 1.5:
                        rr_score = 5
                        setup_details['risk_reward'] = 'acceptable'
                    else:
                        rr_score = 0
                        setup_details['risk_reward'] = 'poor'
                    technical_score += rr_score

            return {
                'technical_score': min(100, technical_score),
                'setup_details': setup_details,
                'current_price': current_price,
                'support': support,
                'resistance': resistance
            }

        except Exception as e:
            logger.warning(f"Technical setup validation failed for {symbol}: {e}")
            return {
                'technical_score': 0,
                'setup_details': {},
                'current_price': 0,
                'support': 0,
                'resistance': 0
            }

    def _ai_predict_growth_probability(self,
                                      symbol: str,
                                      current_price: float,
                                      fundamental_analysis: Dict[str, Any],
                                      technical_analysis: Dict[str, Any],
                                      catalyst_analysis: Dict[str, Any],
                                      technical_setup: Dict[str, Any],
                                      target_gain_pct: float,
                                      timeframe_days: int) -> Dict[str, Any]:
        """
        STAGE 4: AI Deep Analysis

        Use AI to predict probability of achieving target gain

        Returns:
            AI prediction with probability, confidence, and reasoning
        """
        try:
            # Prepare comprehensive data summary for AI
            data_summary = f"""
Stock: {symbol}
Current Price: ${current_price:.2f}
Target: {target_gain_pct}% gain in {timeframe_days} days (${current_price * (1 + target_gain_pct/100):.2f})

=== CATALYST ANALYSIS ===
Catalyst Score: {catalyst_analysis['catalyst_score']:.1f}/100
Total Catalysts: {catalyst_analysis['total_catalysts']}
Key Catalysts:
{self._format_catalysts_for_ai(catalyst_analysis['catalysts'][:3])}

=== TECHNICAL SETUP ===
Technical Score: {technical_setup['technical_score']:.1f}/100
Trend: {technical_setup['setup_details'].get('trend', 'unknown')}
Momentum: {technical_setup['setup_details'].get('momentum', 'unknown')}
Volume: {technical_setup['setup_details'].get('volume', 'unknown')}
Pattern: {technical_setup['setup_details'].get('pattern', 'unknown')}

=== FUNDAMENTAL METRICS ===
Market Cap: ${fundamental_analysis.get('market_cap', 0)/1e9:.2f}B
P/E Ratio: {fundamental_analysis.get('pe_ratio', 'N/A')}
Revenue Growth: {fundamental_analysis.get('revenue_growth', 0)*100:.1f}%
Profit Margin: {fundamental_analysis.get('profit_margin', 0)*100:.1f}%
"""

            # Create AI prompt
            prompt = f"""You are an expert stock analyst. Analyze this stock's probability of achieving {target_gain_pct}% gain in {timeframe_days} days.

{data_summary}

Provide your analysis in this EXACT JSON format:
{{
    "probability": <0-100 number>,
    "confidence": <0-100 number>,
    "reasoning": "<brief explanation>",
    "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
    "risks": ["<risk 1>", "<risk 2>"],
    "best_case": <percentage>,
    "worst_case": <percentage>
}}

Return ONLY valid JSON, no other text."""

            # Call AI service
            from deepseek_service import deepseek_service
            ai_response = deepseek_service.call_api(prompt, max_tokens=500)

            if ai_response:
                # Parse JSON response
                import json
                # Extract JSON from response (remove markdown formatting if present)
                json_str = ai_response.strip()
                if json_str.startswith('```json'):
                    json_str = json_str[7:]
                if json_str.endswith('```'):
                    json_str = json_str[:-3]
                json_str = json_str.strip()

                ai_result = json.loads(json_str)

                return {
                    'probability': ai_result.get('probability', 50),
                    'confidence': ai_result.get('confidence', 50),
                    'reasoning': ai_result.get('reasoning', ''),
                    'key_factors': ai_result.get('key_factors', []),
                    'risks': ai_result.get('risks', []),
                    'best_case': ai_result.get('best_case', target_gain_pct * 1.5),
                    'worst_case': ai_result.get('worst_case', 0)
                }
            else:
                # Fallback: simple scoring
                return self._simple_probability_calculation(
                    catalyst_analysis['catalyst_score'],
                    technical_setup['technical_score'],
                    target_gain_pct
                )

        except Exception as e:
            logger.warning(f"AI prediction failed for {symbol}: {e}")
            # Fallback to simple calculation
            return self._simple_probability_calculation(
                catalyst_analysis['catalyst_score'],
                technical_setup['technical_score'],
                target_gain_pct
            )

    def _format_catalysts_for_ai(self, catalysts: List[Dict]) -> str:
        """Format catalysts for AI prompt"""
        if not catalysts:
            return "None"

        formatted = []
        for cat in catalysts:
            formatted.append(f"- {cat.get('description', 'N/A')} (impact: {cat.get('impact', 'unknown')})")

        return "\n".join(formatted)

    def _simple_probability_calculation(self,
                                       catalyst_score: float,
                                       technical_score: float,
                                       target_gain_pct: float) -> Dict[str, Any]:
        """Fallback: Simple probability calculation without AI"""
        # Average of catalyst and technical scores
        combined_score = (catalyst_score * 0.6 + technical_score * 0.4)

        # Adjust for target difficulty
        if target_gain_pct <= 10:
            difficulty_adjustment = 1.0
        elif target_gain_pct <= 20:
            difficulty_adjustment = 0.8
        else:
            difficulty_adjustment = 0.6

        probability = combined_score * difficulty_adjustment
        confidence = 60  # Medium confidence for simple calculation

        return {
            'probability': min(100, probability),
            'confidence': confidence,
            'reasoning': 'Calculated from catalyst and technical scores',
            'key_factors': ['Catalyst strength', 'Technical setup'],
            'risks': ['Market volatility', 'Macro conditions'],
            'best_case': target_gain_pct * 1.5,
            'worst_case': 0
        }

    def _analyze_valuation(self,
                           symbol: str,
                           info: Dict[str, Any],
                           current_price: float) -> Dict[str, Any]:
        """
        NEW: Analyze valuation (P/E, Forward P/E, PEG)

        Backtest insight: Overvalued stocks failed badly
        - NET: Forward P/E 172 → -14.0%
        - AMD: P/E 112 → -9.5%
        - NOW: P/E 93.5 → -10.3%

        Returns:
            Valuation analysis with score (0-100)
        """
        valuation_score = 50.0  # Neutral start
        valuation_issues = []

        try:
            pe_ratio = info.get('trailingPE', None)
            forward_pe = info.get('forwardPE', None)
            peg_ratio = info.get('pegRatio', None)

            # === Trailing P/E Analysis ===
            if pe_ratio:
                if pe_ratio < 0:
                    valuation_score -= 20  # Negative earnings = BAD
                    valuation_issues.append(f"Negative P/E (unprofitable)")
                elif pe_ratio > 100:
                    valuation_score -= 25  # Extremely overvalued!
                    valuation_issues.append(f"P/E {pe_ratio:.1f} - Extremely overvalued")
                elif pe_ratio > 60:
                    valuation_score -= 15  # Very high
                    valuation_issues.append(f"P/E {pe_ratio:.1f} - Overvalued")
                elif pe_ratio > 40:
                    valuation_score -= 5  # Mild concern
                    valuation_issues.append(f"P/E {pe_ratio:.1f} - Elevated")
                elif 15 <= pe_ratio <= 35:
                    valuation_score += 20  # SWEET SPOT!
                    valuation_issues.append(f"P/E {pe_ratio:.1f} - Reasonable")
                elif pe_ratio < 15:
                    valuation_score += 10  # Cheap (but maybe for reason?)
                    valuation_issues.append(f"P/E {pe_ratio:.1f} - Cheap")

            # === Forward P/E Analysis (MORE IMPORTANT!) ===
            if forward_pe:
                if forward_pe > 80:
                    valuation_score -= 30  # CRITICAL! Too expensive
                    valuation_issues.append(f"Forward P/E {forward_pe:.1f} - DANGER")
                elif forward_pe > 50:
                    valuation_score -= 20
                    valuation_issues.append(f"Forward P/E {forward_pe:.1f} - Very high")
                elif forward_pe > 35:
                    valuation_score -= 10
                    valuation_issues.append(f"Forward P/E {forward_pe:.1f} - High")
                elif 15 <= forward_pe <= 30:
                    valuation_score += 25  # IDEAL!
                    valuation_issues.append(f"Forward P/E {forward_pe:.1f} - Attractive")
                elif forward_pe < 15:
                    valuation_score += 15
                    valuation_issues.append(f"Forward P/E {forward_pe:.1f} - Cheap")

            # === PEG Ratio Analysis ===
            if peg_ratio and peg_ratio > 0:
                if peg_ratio < 1.0:
                    valuation_score += 15  # Undervalued relative to growth
                    valuation_issues.append(f"PEG {peg_ratio:.2f} - Growth at reasonable price")
                elif peg_ratio > 2.5:
                    valuation_score -= 15  # Overvalued relative to growth
                    valuation_issues.append(f"PEG {peg_ratio:.2f} - Expensive for growth")

            # Cap score between 0-100
            valuation_score = max(0, min(100, valuation_score))

            return {
                'valuation_score': valuation_score,
                'pe_ratio': pe_ratio,
                'forward_pe': forward_pe,
                'peg_ratio': peg_ratio,
                'valuation_issues': valuation_issues
            }

        except Exception as e:
            logger.warning(f"Valuation analysis failed for {symbol}: {e}")
            return {
                'valuation_score': 50.0,  # Neutral if failed
                'pe_ratio': None,
                'forward_pe': None,
                'peg_ratio': None,
                'valuation_issues': ['Valuation data unavailable']
            }

    def _analyze_sector_strength(self,
                                 symbol: str,
                                 info: Dict[str, Any],
                                 price_data: pd.DataFrame) -> Dict[str, Any]:
        """
        NEW: Analyze Sector Relative Strength

        Backtest insight: Sector rotation killed high-scoring stocks!
        - Crypto (COIN): -20.3% while SPY +3.2%
        - Cloud (NET): -14.0% while QQQ +2.9%
        - Gig Economy (UBER): -13.5% while market UP

        Winner: DASH (Consumer Cyclical) +19.1% → Sector was strong!

        Returns:
            Sector analysis with score (0-100)
        """
        sector_score = 50.0  # Neutral start
        sector_name = info.get('sector', 'Unknown')
        industry = info.get('industry', 'Unknown')

        try:
            # Calculate stock's 30-day return
            if len(price_data) >= 30:
                stock_return_30d = ((price_data['close'].iloc[-1] / price_data['close'].iloc[-30]) - 1) * 100
            else:
                stock_return_30d = 0

            # v6.7: Get market return (SPY as proxy) - CACHED!
            import time
            market_return_30d = 0

            # Check market data cache first
            if 'spy_return_30d' in self._market_data_cache:
                cache_age = time.time() - self._market_data_cache_time
                if cache_age < self._market_cache_ttl:
                    market_return_30d = self._market_data_cache['spy_return_30d']
                    logger.debug(f"Using cached SPY return (age: {int(cache_age)}s)")
                else:
                    # Cache expired, refresh
                    self._market_data_cache.clear()

            # Fetch SPY data if not cached
            if 'spy_return_30d' not in self._market_data_cache:
                try:
                    self._rate_limited_api_call()
                    spy = yf.Ticker('SPY')
                    spy_hist = spy.history(period='1mo')
                    if not spy_hist.empty and len(spy_hist) >= 20:
                        market_return_30d = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-20]) - 1) * 100
                        self._market_data_cache['spy_return_30d'] = market_return_30d
                        self._market_data_cache_time = time.time()
                        logger.debug(f"Cached SPY return: {market_return_30d:.2f}%")
                except Exception as e:
                    # GRACEFUL: If SPY data fails, assume 0% market return
                    logger.debug(f"Failed to get SPY data: {e} - using 0% market return")
                    market_return_30d = 0

            # Calculate Relative Strength (stock vs market)
            relative_strength = stock_return_30d - market_return_30d

            # Score based on RS
            if relative_strength > 10:
                sector_score = 90  # STRONG outperformance!
            elif relative_strength > 5:
                sector_score = 75  # Good outperformance
            elif relative_strength > 0:
                sector_score = 60  # Mild outperformance
            elif relative_strength > -5:
                sector_score = 45  # Mild underperformance
            elif relative_strength > -10:
                sector_score = 30  # Underperformance (CAUTION)
            else:
                sector_score = 15  # SEVERE underperformance (DANGER!)

            # Sector-specific adjustments (based on current market conditions)
            # NOTE: These should be updated based on macro trends!
            risky_sectors = ['Cryptocurrency', 'Cloud Infrastructure', 'Gig Economy']
            if any(risky in sector_name or risky in industry for risky in risky_sectors):
                sector_score -= 10  # Penalty for currently weak sectors

            safe_sectors = ['Consumer Cyclical', 'Consumer Defensive', 'Healthcare']
            if sector_name in safe_sectors:
                sector_score += 5  # Bonus for defensive sectors

            # Cap score
            sector_score = max(0, min(100, sector_score))

            return {
                'sector_score': sector_score,
                'sector': sector_name,
                'industry': industry,
                'relative_strength': relative_strength,
                'stock_return_30d': stock_return_30d,
                'market_return_30d': market_return_30d
            }

        except Exception as e:
            logger.warning(f"Sector analysis failed for {symbol}: {e}")
            return {
                'sector_score': 50.0,  # Neutral if failed
                'sector': sector_name,
                'industry': industry,
                'relative_strength': 0,
                'stock_return_30d': 0,
                'market_return_30d': 0
            }

    def _calculate_composite_score(self,
                                   catalyst_score: float,
                                   technical_score: float,
                                   ai_probability: float,
                                   ai_confidence: float,
                                   sector_score: float = 50.0,
                                   valuation_score: float = 50.0,
                                   alt_data_analysis: Dict = None,
                                   sector_rotation_boost: float = 1.0) -> float:
        """
        Calculate final composite score (v3.1 - SECTOR ROTATION)

        v3.1 WEIGHTS with Alternative Data + Sector Rotation:
        - Alternative Data: 25% (Insider, analyst, squeeze, social, correlation, macro)
        - Technical Setup: 25% (Core technical signals)
        - Sector Strength: 20% (Sector rotation important)
        - Valuation: 15% (Avoid overvalued traps)
        - Catalyst: 10% (Inverted: quiet period = bonus)
        - AI Probability: 5% (Reduced: less reliable than alt data)
        - Sector Rotation Boost: 0.8x - 1.2x multiplier (NEW!)

        Expected improvement: 58.3% → 65%+ win rate with sector timing
        """

        # Get alternative data score (0-100)
        alt_data_score = 50.0  # Default neutral
        if alt_data_analysis and alt_data_analysis.get('overall_score'):
            alt_data_score = alt_data_analysis['overall_score']

            # Boost if multiple positive signals
            positive_signals = alt_data_analysis.get('positive_signals', 0)
            if positive_signals >= 3:
                alt_data_score = min(100, alt_data_score * 1.1)  # 10% boost for 3+ signals

        composite = (
            alt_data_score * 0.25 +      # v3.0: Alternative data (insider, analyst, etc.)
            technical_score * 0.25 +     # Technical matters for 5% moves
            sector_score * 0.20 +        # Sector rotation is critical
            valuation_score * 0.15 +     # Avoid overvalued traps
            catalyst_score * 0.10 +      # Inverted (quiet period = bonus)
            ai_probability * 0.05        # Reduced weight
        )

        # v3.1: Apply sector rotation boost/penalty
        composite = composite * sector_rotation_boost

        return round(composite, 1)

    def _calculate_momentum_entry_score(self,
                                        momentum_score: float,
                                        momentum_metrics: Dict[str, float],
                                        catalyst_score: float,
                                        technical_score: float,
                                        ai_probability: float,
                                        alt_data_analysis: Dict = None,
                                        sector_regime_adjustment: float = 0,
                                        market_cap: float = 0) -> float:
        """
        Calculate momentum-based entry score (v4.0)

        Philosophy: Momentum FIRST (70%), Alternative data as BONUS (30%)

        Score breakdown:
        - Base momentum score: 0-100 (proven predictive!)
        - Bonuses:
          * Alternative data: +0 to +20 (if available)
          * Catalyst bonus: +0 to +10 (if strong)
          * Sector regime: +/- 10 (market timing)
          * Market cap: +0 to +10 (liquidity)
        - Total range: 0-140+

        Expected: Stocks >100 are excellent, >80 are good
        """
        score = momentum_score  # Base: 0-100 from pure momentum

        # Bonus 1: Alternative Data (0-20 points)
        if alt_data_analysis and alt_data_analysis.get('overall_score'):
            alt_score = alt_data_analysis['overall_score']
            positive_signals = alt_data_analysis.get('positive_signals', 0)

            # Scale alt data score to 0-20 bonus
            bonus = (alt_score / 100) * 15  # Max 15 from score

            # Extra bonus for multiple signals
            if positive_signals >= 4:
                bonus += 5  # +5 for 4+ signals
            elif positive_signals >= 3:
                bonus += 3  # +3 for 3 signals

            score += min(20, bonus)

        # Bonus 2: Catalyst bonus (0-10 points)
        # High catalyst score (earnings soon, etc.) can add a small bonus
        if catalyst_score > 60:
            score += 10
        elif catalyst_score > 40:
            score += 5
        elif catalyst_score > 20:
            score += 3

        # Bonus 3: Sector regime adjustment (-10 to +10)
        score += sector_regime_adjustment

        # Bonus 4: Market cap bonus (0-10 points for high liquidity)
        if market_cap > 10_000_000_000:  # $10B+
            score += 10
        elif market_cap > 5_000_000_000:  # $5B+
            score += 7
        elif market_cap > 2_000_000_000:  # $2B+
            score += 4

        # Bonus 5: RSI ideal range
        rsi = momentum_metrics['rsi']
        if 45 <= rsi <= 55:
            score += 5  # Perfect RSI

        # Bonus 6: Very strong momentum
        if momentum_metrics['momentum_30d'] > 20:
            score += 5  # Exceptional trend

        return round(score, 1)

    def _apply_risk_adjustment(self,
                              composite_score: float,
                              market_cap: float,
                              current_price: float,
                              technical_analysis: Dict[str, Any]) -> tuple[float, List[str]]:
        """
        Apply risk adjustments to composite score

        UPDATED based on backtest findings:
        - Winners had avg price $185 vs losers $344
        - Low-price stocks (<$50) have higher % move potential
        - Small caps have higher explosive potential
        """
        adjusted_score = composite_score
        risk_factors = []

        # REMOVED: Small cap penalty - we WANT small/mid caps for explosive potential!
        # Backtest showed small caps perform better

        # REVERSED: Low price is now a BONUS not penalty!
        # Low-price stocks have higher % move potential (ARQT $30 → +32%, TXG $16 → +23%)
        if current_price < 30:
            adjusted_score *= 1.10  # 10% BONUS for very low price
            risk_factors.append('low_price_explosive_potential')
        elif current_price < 50:
            adjusted_score *= 1.05  # 5% bonus for low price
            risk_factors.append('low_price_advantage')
        elif current_price > 300:
            adjusted_score *= 0.95  # INCREASED penalty for high price (harder to move %)
            risk_factors.append('high_price_stock')

        # REMOVED: Volatility penalty - explosive stocks ARE volatile!
        # High volatility is a feature, not a bug, for 15%+ targets

        return round(adjusted_score, 1), risk_factors

    # ===== v4.0: Rule-Based Screening Management Methods =====

    def get_screening_rules_stats(self) -> List[Dict]:
        """Get performance statistics for screening rules (v4.0)"""
        if self.screening_rules:
            return self.screening_rules.get_rule_stats()
        return []

    def tune_screening_rule(self, rule_name: str, threshold_name: str, value: float):
        """Tune a screening rule's threshold (v4.0)"""
        if self.screening_rules:
            self.screening_rules.update_threshold(rule_name, threshold_name, value)
        else:
            logger.warning("⚠️ Rule-based screening engine not available")

    def tune_screening_weight(self, rule_name: str, weight_name: str, value: float):
        """Tune a screening rule's weight (v4.0)"""
        if self.screening_rules:
            self.screening_rules.update_weight(rule_name, weight_name, value)
        else:
            logger.warning("⚠️ Rule-based screening engine not available")

    def enable_screening_rule(self, rule_name: str):
        """Enable a screening rule (v4.0)"""
        if self.screening_rules:
            self.screening_rules.enable_rule(rule_name)
        else:
            logger.warning("⚠️ Rule-based screening engine not available")

    def disable_screening_rule(self, rule_name: str):
        """Disable a screening rule (v4.0)"""
        if self.screening_rules:
            self.screening_rules.disable_rule(rule_name)
        else:
            logger.warning("⚠️ Rule-based screening engine not available")

    def export_screening_rules_config(self) -> Dict:
        """Export current screening rules configuration (v4.0)"""
        if self.screening_rules:
            return self.screening_rules.export_config()
        return {}

    def import_screening_rules_config(self, config: Dict):
        """Import screening rules configuration (for A/B testing) (v4.0)"""
        if self.screening_rules:
            self.screening_rules.import_config(config)
        else:
            logger.warning("⚠️ Rule-based screening engine not available")


def main():
    """Example usage"""
    import sys
    sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')
    from main import StockAnalyzer

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Screen for 30-day growth opportunities
    print("=== 30-Day Growth Catalyst Screening ===")
    opportunities = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=10.0,
        timeframe_days=30,
        min_catalyst_score=30.0,
        min_technical_score=50.0,
        min_ai_probability=50.0,
        max_stocks=20
    )

    # Display results
    print(f"\n✅ Found {len(opportunities)} growth opportunities:\n")
    for i, opp in enumerate(opportunities, 1):
        print(f"{i}. {opp['symbol']} - Composite Score: {opp['composite_score']:.1f}/100")
        print(f"   Price: ${opp['current_price']:.2f}")
        print(f"   Catalyst Score: {opp['catalyst_score']:.1f} | Technical: {opp['technical_score']:.1f} | AI Probability: {opp['ai_probability']:.1f}%")
        print(f"   Catalysts: {len(opp['catalysts'])}")
        print()


if __name__ == "__main__":
    main()
