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
    # v6.5: New quality fields
    rsi: float = 50.0
    dollar_volume: float = 0.0
    return_5d: float = 0.0
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
    UNIVERSE_FILE = os.path.join(DATA_DIR, 'full_universe_cache.json')  # v6.17: Universe from maintain_universe_1000.py (987 stocks)
    PRE_FILTERED_FILE = os.path.join(DATA_DIR, 'pre_filtered.json')
    STATUS_FILE = os.path.join(DATA_DIR, 'pre_filter_status.json')

    # Structural filter thresholds (defaults, overridden by config)
    MIN_PRICE = 5.0
    MIN_VOLUME = 500_000
    MIN_ATR_PCT = 2.3  # v6.12: Relaxed from 2.5 to allow lower volatility stocks
    MAX_OVEREXTENDED_PCT = 10.0  # Max % above SMA20

    # v6.5: Quality filter thresholds
    MAX_RSI = 70.0  # v6.12: Relaxed from 65 to allow slightly higher RSI
    MIN_DOLLAR_VOLUME = 5_000_000  # $5M
    MIN_DIP_5D = -1.0   # v6.12: Relaxed from -2.0% to allow smaller dips
    MAX_DIP_5D = -15.0  # But not crash > 15%

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

        # v6.5: Load config values
        self._load_config()

        logger.info(f"PreFilterRunner initialized. Pool: {self.status.pool_size}, Ready: {self.status.is_ready}")

    def _load_config(self):
        """Load filter thresholds from config."""
        try:
            from trading_config import load_config
            cfg = load_config(strict=False)

            self.MIN_PRICE = cfg.get('pre_filter_min_price', self.MIN_PRICE)
            self.MIN_VOLUME = cfg.get('pre_filter_min_volume', self.MIN_VOLUME)
            self.MIN_ATR_PCT = cfg.get('pre_filter_min_atr_pct', self.MIN_ATR_PCT)
            self.MAX_OVEREXTENDED_PCT = cfg.get('pre_filter_max_overextended', self.MAX_OVEREXTENDED_PCT)

            # v6.5: Quality filters
            self.MAX_RSI = cfg.get('pre_filter_max_rsi', self.MAX_RSI)
            self.MIN_DOLLAR_VOLUME = cfg.get('pre_filter_min_dollar_volume', self.MIN_DOLLAR_VOLUME)
            self.MIN_DIP_5D = cfg.get('pre_filter_min_dip_5d', self.MIN_DIP_5D)
            self.MAX_DIP_5D = cfg.get('pre_filter_max_dip_5d', self.MAX_DIP_5D)

            logger.debug(f"PreFilter config: RSI<={self.MAX_RSI}, DollarVol>=${self.MIN_DOLLAR_VOLUME/1e6:.1f}M, "
                        f"Dip5d: {self.MAX_DIP_5D}% to {self.MIN_DIP_5D}%")
        except Exception as e:
            logger.warning(f"Failed to load pre-filter config: {e}")

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
        """Save status to file and database."""
        # Write to JSON (legacy/backup)
        try:
            with open(self.STATUS_FILE, 'w') as f:
                json.dump(self.status.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save pre-filter status to JSON: {e}")

        # Phase 2: Write to database
        try:
            from database import PreFilterRepository, PreFilterSession
            repo = PreFilterRepository()

            # Create or update session
            if hasattr(self, '_current_session_id') and self._current_session_id:
                # Update existing session
                repo.update_session_status(
                    session_id=self._current_session_id,
                    status=self.status.evening_status or self.status.pre_open_status or 'completed',
                    pool_size=self.status.pool_size
                )
            else:
                # Create new session (should not happen - session created in run_scan)
                logger.warning("No current session ID - status not saved to DB")
        except Exception as e:
            logger.error(f"Failed to save pre-filter status to DB: {e}")

    def _load_sector_cache(self) -> Dict[str, Dict]:
        """
        Load universe for pre-filter scanning.

        v6.17: Uses full_universe_cache.json (maintained by maintain_universe_1000.py cron job)
        This contains 987 stocks from FULL_UNIVERSE with sector info.
        """
        try:
            if os.path.exists(self.UNIVERSE_FILE):
                with open(self.UNIVERSE_FILE, 'r') as f:
                    cache = json.load(f)
                logger.info(f"📦 Pre-filter using full_universe_cache: {len(cache)} stocks")
                return cache
        except Exception as e:
            logger.error(f"Failed to load universe cache: {e}")
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
        """Save pre-filtered data (atomic write via tempfile → rename)."""
        try:
            import numpy as np
            import tempfile

            def default_encoder(obj):
                if isinstance(obj, (np.bool_, np.integer)):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            target = self.PRE_FILTERED_FILE
            dir_ = os.path.dirname(target) or '.'
            with tempfile.NamedTemporaryFile('w', dir=dir_, suffix='.tmp', delete=False) as tmp:
                json.dump(data, tmp, indent=2, default=default_encoder)
                tmp_path = tmp.name
            os.replace(tmp_path, target)  # atomic on Linux
            logger.info(f"Saved pre-filtered data to JSON: {len(data.get('stocks', {}))} stocks")

            # Phase 2: Save to database
            try:
                from database import PreFilterRepository, FilteredStock

                if not hasattr(self, '_current_session_id') or not self._current_session_id:
                    logger.warning("No current session ID - stocks not saved to DB")
                    return

                repo = PreFilterRepository()
                stocks_data = data.get('stocks', {})

                # Convert to FilteredStock objects
                filtered_stocks = []
                for symbol, stock_data in stocks_data.items():
                    if isinstance(stock_data, dict):
                        stock = FilteredStock(
                            session_id=self._current_session_id,
                            symbol=symbol,
                            sector=stock_data.get('sector'),
                            score=stock_data.get('score'),
                            close_price=stock_data.get('close') or stock_data.get('close_price'),
                            volume_avg_20d=stock_data.get('volume_avg_20d'),
                            atr_pct=stock_data.get('atr_pct'),
                            rsi=stock_data.get('rsi')
                        )
                        filtered_stocks.append(stock)

                # Bulk insert
                if filtered_stocks:
                    added = repo.add_stocks_bulk(filtered_stocks)
                    logger.info(f"Saved {added} stocks to database (session {self._current_session_id})")

                    # Update session pool size
                    repo.update_session_status(
                        session_id=self._current_session_id,
                        pool_size=added
                    )
            except Exception as db_err:
                logger.error(f"Failed to save pre-filtered data to DB: {db_err}")

        except Exception as e:
            logger.error(f"Failed to save pre-filtered data: {e}")

    def _fetch_stock_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch stock data for analysis.

        Returns dict with: close, sma20, sma50, atr_pct, avg_volume, rsi, dollar_volume, return_5d
        or None if failed.
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

            # v6.5: RSI calculation (14-period)
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, 0.0001)  # Avoid div by zero
            rsi = 100 - (100 / (1 + rs))
            rsi_value = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

            # v6.5: Dollar volume (price × volume)
            dollar_volume = close * avg_volume

            # v6.5: 5-day return (for dip detection)
            if len(df) >= 5:
                close_5d_ago = df['close'].iloc[-5]
                return_5d = ((close - close_5d_ago) / close_5d_ago) * 100
            else:
                return_5d = 0.0

            return {
                'close': close,
                'sma20': sma20,
                'sma50': sma50,
                'atr_pct': atr_pct,
                'avg_volume': avg_volume,
                'rsi': rsi_value,
                'dollar_volume': dollar_volume,
                'return_5d': return_5d,
            }
        except Exception as e:
            logger.debug(f"Failed to fetch data for {symbol}: {e}")
            return None

    def _apply_structural_filter(self, symbol: str, data: Dict, sector: str) -> Tuple[Optional[PreFilterStock], str]:
        """
        Apply structural filters to a stock.

        Returns (PreFilterStock, "") if passes, (None, reason) if filtered out.
        """
        close = data['close']
        sma20 = data['sma20']
        sma50 = data['sma50']
        atr_pct = data['atr_pct']
        avg_volume = data['avg_volume']
        rsi = data.get('rsi', 50.0)
        dollar_volume = data.get('dollar_volume', 0)
        return_5d = data.get('return_5d', 0)

        # Filter 1: Minimum price
        if close < self.MIN_PRICE:
            return None, 'price'

        # Filter 2: Minimum ATR (volatility)
        if atr_pct < self.MIN_ATR_PCT:
            return None, 'atr'

        # Filter 3: Above SMA20 (uptrend) - v6.17: Reverted to strict > 0%
        pct_from_sma20 = ((close - sma20) / sma20) * 100 if sma20 > 0 else 0
        above_sma20 = close > sma20
        # v6.17: Strict filter - must be above SMA20
        if pct_from_sma20 < 0:
            return None, 'sma20'

        # Filter 4: Not overextended (pct_from_sma20 already calculated above)
        if pct_from_sma20 > self.MAX_OVEREXTENDED_PCT:
            return None, 'overextended'

        # v6.5: Quality filters
        # Filter 5: RSI not overbought
        if rsi > self.MAX_RSI:
            return None, 'rsi_high'

        # Filter 6: Minimum dollar volume (liquidity)
        if dollar_volume < self.MIN_DOLLAR_VOLUME:
            return None, 'dollar_vol'

        # Filter 7: Must have dipped (dip-bounce requirement)
        # return_5d should be between MAX_DIP_5D and MIN_DIP_5D
        # e.g., between -15% and -2%
        # Skip if MIN_DIP_5D > 0 (disabled)
        if self.MIN_DIP_5D < 0:
            if return_5d > self.MIN_DIP_5D:  # Not dipped enough (e.g., > -2%)
                return None, 'no_dip'

            if return_5d < self.MAX_DIP_5D:  # Crashed too much (e.g., < -15%)
                return None, 'crash'

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
            rsi=rsi,
            dollar_volume=dollar_volume,
            return_5d=return_5d,
            last_updated=datetime.now().isoformat()
        ), ''

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

        # Phase 2: Create database session
        from database import PreFilterRepository, PreFilterSession
        from datetime import datetime
        repo = PreFilterRepository()
        db_session = PreFilterSession(
            scan_type='evening',
            scan_time=datetime.now(),
            total_scanned=0,  # Will update later
            status='running',
            is_ready=False
        )
        self._current_session_id = repo.create_session(db_session)
        logger.info(f"📊 Created DB session ID: {self._current_session_id}")

        # v6.35: Reset pre_open_status (new evening scan invalidates old pre-open scan)
        self.status.evening_status = "running"
        self.status.pre_open_status = "pending"
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

            # Update DB session with total count
            repo.update_session_status(
                session_id=self._current_session_id,
                total_scanned=total
            )

            # Import pandas here (lazy import)
            global pd
            import pandas as pd

            # Scan each stock
            passed_stocks = {}
            filtered_counts = {
                'price': 0,
                'atr': 0,
                'sma20': 0,
                'overextended': 0,
                'rsi_high': 0,
                'dollar_vol': 0,
                'no_dip': 0,
                'crash': 0,
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

                # Apply filters (returns tuple now)
                stock, reason = self._apply_structural_filter(symbol, data, sector)
                if stock is None:
                    if reason in filtered_counts:
                        filtered_counts[reason] += 1
                    else:
                        filtered_counts['error'] += 1
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
            logger.info(f"  Filtered breakdown:")
            logger.info(f"    - price<${self.MIN_PRICE}: {filtered_counts['price']}")
            logger.info(f"    - atr<{self.MIN_ATR_PCT}%: {filtered_counts['atr']}")
            logger.info(f"    - below_sma20: {filtered_counts['sma20']}")
            logger.info(f"    - overextended>{self.MAX_OVEREXTENDED_PCT}%: {filtered_counts['overextended']}")
            logger.info(f"    - rsi>{self.MAX_RSI}: {filtered_counts['rsi_high']}")
            logger.info(f"    - dollar_vol<${self.MIN_DOLLAR_VOLUME/1e6:.1f}M: {filtered_counts['dollar_vol']}")
            logger.info(f"    - no_dip (>{self.MIN_DIP_5D}%): {filtered_counts['no_dip']}")
            logger.info(f"    - crash (<{self.MAX_DIP_5D}%): {filtered_counts['crash']}")
            logger.info(f"    - error: {filtered_counts['error']}")
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

        # Phase 2: Create database session
        from database import PreFilterRepository, PreFilterSession
        from datetime import datetime
        repo = PreFilterRepository()
        db_session = PreFilterSession(
            scan_type='pre_open',
            scan_time=datetime.now(),
            total_scanned=0,  # Will update later
            status='running',
            is_ready=False
        )
        self._current_session_id = repo.create_session(db_session)
        logger.info(f"📊 Created DB session ID: {self._current_session_id}")

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

            # Update DB session with total count
            repo.update_session_status(
                session_id=self._current_session_id,
                total_scanned=total
            )

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

                # Re-apply filters (returns tuple now)
                stock, reason = self._apply_structural_filter(symbol, data, stock_data.get('sector', 'Unknown'))
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
    parser.add_argument('scan', choices=['evening', 'pre_open', 'intraday', 'status'],
                       help="Which scan to run or 'status' to check status")
    args = parser.parse_args()

    runner = PreFilterRunner()

    if args.scan == 'evening':
        count = runner.evening_scan()
        print(f"\nEvening scan complete: {count} stocks passed")
    elif args.scan == 'pre_open':
        count = runner.pre_open_scan()
        print(f"\nPre-open scan complete: {count} stocks in pool")
    elif args.scan == 'intraday':
        # v6.27: Intraday scans use pre_open logic (re-validate pool, don't add new stocks)
        count = runner.pre_open_scan()
        print(f"\nIntraday scan complete: {count} stocks in pool")
    else:
        status = runner.get_status()
        print(f"\nPre-Filter Status:")
        print(f"  Pool Size: {status.pool_size}")
        print(f"  Evening: {status.evening_status} ({status.evening_count} @ {status.evening_time})")
        print(f"  Pre-Open: {status.pre_open_status} ({status.pre_open_count} @ {status.pre_open_time})")
        print(f"  Ready: {status.is_ready}")
        print(f"  Fresh: {runner.is_pool_fresh()}")
