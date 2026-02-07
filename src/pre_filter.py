#!/usr/bin/env python3
"""
Pre-Filter Runner v1.0
======================
Scans full universe (~1,000+ stocks) during market close hours
to create a filtered pool (~200-400 stocks) for fast realtime scanning.

Scan Windows:
- Evening (20:00 ET): Full universe scan, structural filters
- Pre-Open (09:00 ET): Update filtered pool with latest data

Usage:
    from pre_filter import PreFilterRunner
    runner = PreFilterRunner()

    # Evening scan (run at 20:00 ET)
    runner.evening_scan()

    # Pre-open scan (run at 09:00 ET)
    runner.pre_open_scan()

    # Get current pool for trading
    pool = runner.get_filtered_pool()
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from loguru import logger

# Add src to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from api.data_manager import DataManager
except ImportError:
    DataManager = None

try:
    from sector_regime_detector import SectorRegimeDetector
except ImportError:
    SectorRegimeDetector = None


@dataclass
class PreFilterStock:
    """Stock data from pre-filter scan"""
    symbol: str
    sector: str
    price: float
    sma20: float
    sma50: float
    atr_pct: float
    avg_volume: float
    above_sma20: bool
    above_sma50: bool
    pct_from_sma20: float  # How far from SMA20 (for overextended check)
    pass_count: int = 0    # How many windows passed
    windows: List[str] = None  # Which windows passed
    last_updated: str = ""

    def __post_init__(self):
        if self.windows is None:
            self.windows = []


@dataclass
class PreFilterStatus:
    """Status of pre-filter system"""
    pool_size: int = 0
    evening_count: int = 0
    evening_time: str = ""
    evening_status: str = "pending"  # pending, running, completed, failed
    pre_open_count: int = 0
    pre_open_time: str = ""
    pre_open_status: str = "pending"
    last_updated: str = ""
    is_ready: bool = False
    using_fallback: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


class PreFilterRunner:
    """
    Pre-Filter Runner for overnight stock screening.

    Scans full universe during market close to create filtered pool
    for fast realtime scanning during market hours.
    """

    # File paths
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    SECTOR_CACHE_FILE = os.path.join(DATA_DIR, 'sector_cache.json')
    PRE_FILTERED_FILE = os.path.join(DATA_DIR, 'pre_filtered.json')
    STATUS_FILE = os.path.join(DATA_DIR, 'pre_filter_status.json')

    # Structural filter thresholds
    MIN_PRICE = 5.0
    MIN_VOLUME = 500_000
    MIN_ATR_PCT = 2.5
    MAX_OVEREXTENDED_PCT = 10.0  # Max % above SMA20

    # Target pool size
    TARGET_POOL_MIN = 200
    TARGET_POOL_MAX = 400

    def __init__(self, data_manager: Optional[Any] = None):
        """
        Initialize PreFilterRunner.

        Args:
            data_manager: Optional DataManager instance. Creates new one if not provided.
        """
        self.data_manager = data_manager
        self.status = self._load_status()
        self._sector_regime = None

        # Ensure data directory exists
        os.makedirs(self.DATA_DIR, exist_ok=True)

        logger.info(f"PreFilterRunner initialized. Pool: {self.status.pool_size}, Ready: {self.status.is_ready}")

    def _get_data_manager(self) -> Any:
        """Get or create DataManager instance."""
        if self.data_manager is None:
            if DataManager is None:
                raise ImportError("DataManager not available")
            self.data_manager = DataManager()
        return self.data_manager

    def _get_sector_regime(self) -> Any:
        """Get or create SectorRegimeDetector instance."""
        if self._sector_regime is None:
            if SectorRegimeDetector is None:
                logger.warning("SectorRegimeDetector not available")
                return None
            self._sector_regime = SectorRegimeDetector()
        return self._sector_regime

    def _load_status(self) -> PreFilterStatus:
        """Load status from file."""
        try:
            if os.path.exists(self.STATUS_FILE):
                with open(self.STATUS_FILE, 'r') as f:
                    data = json.load(f)
                return PreFilterStatus(**data)
        except Exception as e:
            logger.warning(f"Failed to load pre-filter status: {e}")
        return PreFilterStatus()

    def _save_status(self):
        """Save status to file."""
        try:
            with open(self.STATUS_FILE, 'w') as f:
                json.dump(self.status.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save pre-filter status: {e}")

    def _load_sector_cache(self) -> Dict[str, Dict]:
        """Load sector cache (full universe)."""
        try:
            if os.path.exists(self.SECTOR_CACHE_FILE):
                with open(self.SECTOR_CACHE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load sector cache: {e}")
        return {}

    def _load_pre_filtered(self) -> Dict[str, Any]:
        """Load pre-filtered data."""
        try:
            if os.path.exists(self.PRE_FILTERED_FILE):
                with open(self.PRE_FILTERED_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load pre-filtered data: {e}")
        return {"stocks": {}, "generated_at": "", "windows_completed": []}

    def _save_pre_filtered(self, data: Dict[str, Any]):
        """Save pre-filtered data."""
        try:
            # Custom encoder to handle numpy types
            import numpy as np

            def default_encoder(obj):
                if isinstance(obj, (np.bool_, np.integer)):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            with open(self.PRE_FILTERED_FILE, 'w') as f:
                json.dump(data, f, indent=2, default=default_encoder)
            logger.info(f"Saved pre-filtered data: {len(data.get('stocks', {}))} stocks")
        except Exception as e:
            logger.error(f"Failed to save pre-filtered data: {e}")

    def _fetch_stock_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock data for analysis.

        Returns dict with: close, sma20, sma50, atr_pct, avg_volume, or None if failed.
        """
        try:
            dm = self._get_data_manager()

            # Fetch 60 days of price data
            df = dm.get_price_data(symbol, period='60d')
            if df is None or len(df) < 20:
                return None

            # Handle MultiIndex columns from yfinance
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Normalize column names to lowercase (cache uses lowercase)
            df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]

            close = df['close'].iloc[-1]

            # Calculate indicators
            sma20 = df['close'].rolling(20).mean().iloc[-1]
            sma50 = df['close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else sma20

            # ATR calculation
            high = df['high']
            low = df['low']
            prev_close = df['close'].shift(1)
            tr = pd.concat([
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs()
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            atr_pct = (atr / close) * 100 if close > 0 else 0

            # Average volume
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]

            return {
                'close': close,
                'sma20': sma20,
                'sma50': sma50,
                'atr_pct': atr_pct,
                'avg_volume': avg_volume
            }
        except Exception as e:
            logger.debug(f"Failed to fetch data for {symbol}: {e}")
            return None

    def _apply_structural_filter(self, symbol: str, data: Dict, sector: str) -> Optional[PreFilterStock]:
        """
        Apply structural filters to a stock.

        Returns PreFilterStock if passes, None if filtered out.
        """
        close = data['close']
        sma20 = data['sma20']
        sma50 = data['sma50']
        atr_pct = data['atr_pct']
        avg_volume = data['avg_volume']

        # Filter 1: Minimum price
        if close < self.MIN_PRICE:
            return None

        # Filter 2: Minimum volume
        if avg_volume < self.MIN_VOLUME:
            return None

        # Filter 3: Minimum ATR (volatility)
        if atr_pct < self.MIN_ATR_PCT:
            return None

        # Filter 4: Above SMA20 (uptrend)
        above_sma20 = close > sma20
        if not above_sma20:
            return None

        # Filter 5: Not overextended
        pct_from_sma20 = ((close - sma20) / sma20) * 100 if sma20 > 0 else 0
        if pct_from_sma20 > self.MAX_OVEREXTENDED_PCT:
            return None

        # Above SMA50
        above_sma50 = close > sma50

        return PreFilterStock(
            symbol=symbol,
            sector=sector,
            price=close,
            sma20=sma20,
            sma50=sma50,
            atr_pct=atr_pct,
            avg_volume=avg_volume,
            above_sma20=above_sma20,
            above_sma50=above_sma50,
            pct_from_sma20=pct_from_sma20,
            last_updated=datetime.now().isoformat()
        )

    def evening_scan(self, progress_callback=None) -> int:
        """
        Run evening scan (20:00 ET).

        Scans full universe from sector_cache.json.

        Args:
            progress_callback: Optional callback(current, total, symbol, status)

        Returns:
            Number of stocks that passed filters.
        """
        logger.info("="*60)
        logger.info("EVENING SCAN - Starting full universe scan")
        logger.info("="*60)

        self.status.evening_status = "running"
        self._save_status()

        start_time = time.time()

        try:
            # Load full universe
            sector_cache = self._load_sector_cache()
            if not sector_cache:
                logger.error("No sector cache found!")
                self.status.evening_status = "failed"
                self._save_status()
                return 0

            universe = list(sector_cache.keys())
            total = len(universe)
            logger.info(f"Universe: {total} stocks")

            # Import pandas here (lazy import)
            global pd
            import pandas as pd

            # Scan each stock
            passed_stocks = {}
            filtered_counts = {
                'price': 0,
                'volume': 0,
                'atr': 0,
                'sma20': 0,
                'overextended': 0,
                'error': 0
            }

            for i, symbol in enumerate(universe):
                if progress_callback:
                    progress_callback(i + 1, total, symbol, "scanning")

                # Get sector info
                sector_info = sector_cache.get(symbol, {})
                sector = sector_info.get('sector', 'Unknown') if isinstance(sector_info, dict) else 'Unknown'

                # Fetch data
                data = self._fetch_stock_data(symbol)
                if data is None:
                    filtered_counts['error'] += 1
                    continue

                # Apply filters
                stock = self._apply_structural_filter(symbol, data, sector)
                if stock is None:
                    # Count filter reasons (simplified)
                    if data['close'] < self.MIN_PRICE:
                        filtered_counts['price'] += 1
                    elif data['avg_volume'] < self.MIN_VOLUME:
                        filtered_counts['volume'] += 1
                    elif data['atr_pct'] < self.MIN_ATR_PCT:
                        filtered_counts['atr'] += 1
                    else:
                        filtered_counts['sma20'] += 1
                    continue

                # Passed all filters
                stock.pass_count = 1
                stock.windows = ['evening']
                passed_stocks[symbol] = asdict(stock)

                # Log progress every 100 stocks
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - start_time
                    logger.info(f"Progress: {i+1}/{total} ({len(passed_stocks)} passed) - {elapsed:.1f}s")

            # Update sector regime
            try:
                sr = self._get_sector_regime()
                if sr:
                    sr.update_all_sectors()
                    logger.info("Sector regime updated")
            except Exception as e:
                logger.warning(f"Failed to update sector regime: {e}")

            # Save results
            elapsed = time.time() - start_time
            now = datetime.now()

            pre_filtered_data = {
                "generated_at": now.isoformat(),
                "windows_completed": ["evening"],
                "pool_size": len(passed_stocks),
                "scan_duration_sec": round(elapsed, 1),
                "filter_stats": filtered_counts,
                "stocks": passed_stocks
            }
            self._save_pre_filtered(pre_filtered_data)

            # Update status
            self.status.evening_count = len(passed_stocks)
            self.status.evening_time = now.strftime("%H:%M")
            self.status.evening_status = "completed"
            self.status.pool_size = len(passed_stocks)
            self.status.last_updated = now.isoformat()
            self.status.is_ready = True
            self._save_status()

            logger.info("="*60)
            logger.info(f"EVENING SCAN COMPLETE")
            logger.info(f"  Scanned: {total} stocks")
            logger.info(f"  Passed: {len(passed_stocks)} stocks")
            logger.info(f"  Filtered: price={filtered_counts['price']}, volume={filtered_counts['volume']}, "
                       f"atr={filtered_counts['atr']}, sma20={filtered_counts['sma20']}, error={filtered_counts['error']}")
            logger.info(f"  Duration: {elapsed:.1f}s ({elapsed/60:.1f} min)")
            logger.info("="*60)

            return len(passed_stocks)

        except Exception as e:
            logger.error(f"Evening scan failed: {e}")
            self.status.evening_status = "failed"
            self._save_status()
            return 0

    def pre_open_scan(self, progress_callback=None) -> int:
        """
        Run pre-open scan (09:00 ET).

        Updates filtered pool with latest data.

        Args:
            progress_callback: Optional callback(current, total, symbol, status)

        Returns:
            Number of stocks in final pool.
        """
        logger.info("="*60)
        logger.info("PRE-OPEN SCAN - Updating filtered pool")
        logger.info("="*60)

        self.status.pre_open_status = "running"
        self._save_status()

        start_time = time.time()

        try:
            # Load evening results
            pre_filtered = self._load_pre_filtered()
            evening_stocks = pre_filtered.get('stocks', {})

            if not evening_stocks:
                logger.warning("No evening scan data found. Running full scan...")
                return self.evening_scan(progress_callback)

            # Import pandas
            global pd
            import pandas as pd

            total = len(evening_stocks)
            logger.info(f"Updating {total} stocks from evening scan")

            # Re-validate each stock
            updated_stocks = {}
            removed = 0

            for i, (symbol, stock_data) in enumerate(evening_stocks.items()):
                if progress_callback:
                    progress_callback(i + 1, total, symbol, "updating")

                # Fetch fresh data
                data = self._fetch_stock_data(symbol)
                if data is None:
                    removed += 1
                    continue

                # Re-apply filters
                stock = self._apply_structural_filter(symbol, data, stock_data.get('sector', 'Unknown'))
                if stock is None:
                    removed += 1
                    continue

                # Update pass count
                stock.pass_count = stock_data.get('pass_count', 1) + 1
                stock.windows = stock_data.get('windows', ['evening']) + ['pre_open']
                updated_stocks[symbol] = asdict(stock)

            # Update sector regime
            try:
                sr = self._get_sector_regime()
                if sr:
                    sr.update_all_sectors()
                    logger.info("Sector regime updated")
            except Exception as e:
                logger.warning(f"Failed to update sector regime: {e}")

            # Save results
            elapsed = time.time() - start_time
            now = datetime.now()

            pre_filtered_data = {
                "generated_at": now.isoformat(),
                "windows_completed": ["evening", "pre_open"],
                "pool_size": len(updated_stocks),
                "scan_duration_sec": round(elapsed, 1),
                "stocks": updated_stocks
            }
            self._save_pre_filtered(pre_filtered_data)

            # Update status
            self.status.pre_open_count = len(updated_stocks)
            self.status.pre_open_time = now.strftime("%H:%M")
            self.status.pre_open_status = "completed"
            self.status.pool_size = len(updated_stocks)
            self.status.last_updated = now.isoformat()
            self.status.is_ready = True
            self._save_status()

            logger.info("="*60)
            logger.info(f"PRE-OPEN SCAN COMPLETE")
            logger.info(f"  Checked: {total} stocks")
            logger.info(f"  Passed: {len(updated_stocks)} stocks")
            logger.info(f"  Removed: {removed} stocks")
            logger.info(f"  Duration: {elapsed:.1f}s")
            logger.info("="*60)

            return len(updated_stocks)

        except Exception as e:
            logger.error(f"Pre-open scan failed: {e}")
            self.status.pre_open_status = "failed"
            self._save_status()
            return 0

    def get_filtered_pool(self) -> List[str]:
        """
        Get list of symbols from filtered pool.

        Returns:
            List of stock symbols ready for realtime scanning.
        """
        try:
            pre_filtered = self._load_pre_filtered()
            stocks = pre_filtered.get('stocks', {})
            return list(stocks.keys())
        except Exception as e:
            logger.error(f"Failed to get filtered pool: {e}")
            return []

    def get_pool_with_metadata(self) -> Dict[str, Dict]:
        """
        Get filtered pool with metadata.

        Returns:
            Dict mapping symbol to metadata (sector, atr_pct, etc.)
        """
        try:
            pre_filtered = self._load_pre_filtered()
            return pre_filtered.get('stocks', {})
        except Exception as e:
            logger.error(f"Failed to get pool metadata: {e}")
            return {}

    def get_status(self) -> PreFilterStatus:
        """Get current pre-filter status."""
        # Reload from file to get latest
        self.status = self._load_status()
        return self.status

    def is_pool_fresh(self, max_age_hours: float = 12) -> bool:
        """
        Check if pool is fresh enough for trading.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            True if pool is fresh, False if stale or missing.
        """
        try:
            pre_filtered = self._load_pre_filtered()
            generated_at = pre_filtered.get('generated_at', '')
            if not generated_at:
                return False

            gen_time = datetime.fromisoformat(generated_at)
            age = datetime.now() - gen_time
            return age.total_seconds() < (max_age_hours * 3600)
        except Exception as e:
            logger.warning(f"Failed to check pool freshness: {e}")
            return False


# CLI for manual runs
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pre-Filter Runner")
    parser.add_argument('scan', choices=['evening', 'pre_open', 'status'],
                       help="Which scan to run or 'status' to check status")
    args = parser.parse_args()

    runner = PreFilterRunner()

    if args.scan == 'evening':
        count = runner.evening_scan()
        print(f"\nEvening scan complete: {count} stocks passed")
    elif args.scan == 'pre_open':
        count = runner.pre_open_scan()
        print(f"\nPre-open scan complete: {count} stocks in pool")
    else:
        status = runner.get_status()
        print(f"\nPre-Filter Status:")
        print(f"  Pool Size: {status.pool_size}")
        print(f"  Evening: {status.evening_status} ({status.evening_count} @ {status.evening_time})")
        print(f"  Pre-Open: {status.pre_open_status} ({status.pre_open_count} @ {status.pre_open_time})")
        print(f"  Ready: {status.is_ready}")
        print(f"  Fresh: {runner.is_pool_fresh()}")
