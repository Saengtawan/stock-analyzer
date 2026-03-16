"""
Post-Earnings Momentum (PEM) Screener v1.0

Detects stocks with positive earnings gaps at market open (9:32 ET):
- Gap up 8%+ from prev close to open
- Elevated early-session volume (confirms real catalyst)

Backtest (2023-2025, 148 stocks):
- Win Rate: 57.6% | Avg P&L: +3.24% | Events: ~2.3/month
- Estimated monthly: ~$396 on $25k capital
- Source: backtests/backtest_post_earnings_momentum.py

v6.67: volume_early_ratio_min 0.30→0.05
  Backtest calibrated on EOD volume; screener measures at 9:32 (2 min).
  Observed ratios for major gap stocks: NFLX+11.6%=0.02x, DELL+13.1%=0.01x,
  HCI+9.4%=0.11x. Threshold 0.30 was near-impossible at 9:32.
  New 0.05 = stock trading at ~4× normal rate in first 5 min (meaningful filter).

Exit: Same-day at market close (gap_trade=True → pre_close_check() closes at EOD)
"""

import os
import json
from typing import List, Optional, Dict
from loguru import logger

try:
    import pandas as pd
    from api.yfinance_utils import fetch_history
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class PEMScreener:
    """
    Post-Earnings Momentum Screener.

    Scans for confirmed earnings gaps at 9:32 ET when open prices are known.
    Uses broker snapshots for fast open/prev_close detection.
    Uses yfinance for 20d avg volume (cached to avoid repeated calls).

    Run once per day at 9:32 ET via _loop_pem_scan() in auto_trading_engine.
    """

    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data'
    )
    PRE_FILTERED_FILE = os.path.join(DATA_DIR, 'pre_filtered.json')

    def __init__(self, broker=None, config: dict = None):
        """
        Args:
            broker: BrokerInterface instance for real-time snapshots
            config: Config dict with PEM thresholds
        """
        self.broker = broker
        self.config = config or {}

        self.gap_threshold = float(self.config.get('pem_gap_threshold_pct', 8.0))
        # Volume check: today's partial volume (9:32) / 20d avg full-day volume.
        # At 9:32 (~2 min of 390-min session), baseline rate = 2/390 = 0.5% (0.005x).
        # Threshold 0.05 = "already 5% of daily avg in first 2 min" → ~10× normal trading rate.
        # Gap stocks at 9:32 observed: 0.01-0.11x (NFLX 0.02, DELL 0.01, HCI 0.11).
        self.volume_early_ratio_min = float(self.config.get('pem_volume_early_ratio_min', 0.05))

        # Cache for 20d avg volume (expensive to fetch, cache per run)
        self._vol_cache: Dict[str, float] = {}

        # v6.33: Sector filter for win rate improvement
        try:
            from filters.sector_filter import SectorFilter
            self.sector_filter = SectorFilter(enabled=True)
        except ImportError:
            logger.warning("Sector filter not available")
            self.sector_filter = None

    def get_universe(self) -> List[str]:
        """
        Get full 987-stock universe for PEM scanning.

        v6.73: Primary source is universe_stocks DB (UniverseRepository),
        consistent with v6.72 DB-only storage pattern.
        Falls back to full_universe_cache.json → DIP pre-filter pool → static list.
        """
        # Primary: universe_stocks DB (v6.73)
        try:
            from database.repositories.universe_repository import UniverseRepository
            symbols = UniverseRepository().get_symbols()
            if symbols:
                logger.info(f"PEM: Loaded {len(symbols)} stocks from universe_stocks DB")
                return symbols
        except Exception as e:
            logger.warning(f"PEM: universe_stocks DB unavailable: {e}")

        # Fallback 1: full_universe_cache.json
        try:
            universe_file = os.path.join(self.DATA_DIR, 'full_universe_cache.json')
            with open(universe_file) as f:
                symbols = list(json.load(f).keys())
            if len(symbols) >= 100:
                logger.warning(f"PEM: Fallback to full_universe_cache.json ({len(symbols)} stocks)")
                return symbols
        except Exception as e:
            logger.debug(f"PEM: full_universe_cache.json unavailable: {e}")

        # Fallback 2: DIP pre-filter pool
        try:
            from database.repositories.pre_filter_repository import PreFilterRepository
            repo = PreFilterRepository()
            latest_session = repo.get_latest_session(scan_type='evening')
            if latest_session and latest_session.status == 'completed' and latest_session.is_ready:
                pool_stocks = repo.get_filtered_pool(session_id=latest_session.id)
                if pool_stocks:
                    symbols = [stock.symbol for stock in pool_stocks]
                    logger.warning(f"PEM: Fallback to pre-filtered pool ({len(symbols)} stocks)")
                    return symbols
        except Exception as e:
            logger.debug(f"PEM: Error loading pre-filtered pool: {e}")

        logger.warning("PEM: Using static fallback list")
        return self._get_fallback_universe()

    def _get_fallback_universe(self) -> List[str]:
        """High-liquidity fallback universe when pre-filter pool is unavailable."""
        return [
            # Large-cap tech (frequent earnings gaps)
            'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN',
            'NFLX', 'COIN', 'SHOP', 'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS',
            # High-beta growth
            'PLTR', 'HOOD', 'RBLX', 'SOFI', 'UPST', 'MDB', 'OKTA', 'PATH',
            'BILL', 'HUBS', 'TTD', 'AFRM', 'CFLT', 'U', 'RIVN', 'LCID',
        ]

    def scan(self) -> List[dict]:
        """
        Scan for PEM signals at market open (call at 9:32 ET).

        Returns list of signal dicts. The engine converts these to
        RapidRotationSignal format and marks them as gap_trade=True.

        Returns:
            List of dicts sorted by gap_pct descending (biggest gap first)
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("PEM: yfinance not available, skipping scan")
            return []

        universe = self.get_universe()
        if not universe:
            logger.warning("PEM: Empty universe, skipping scan")
            return []

        logger.info(f"PEM: Scanning {len(universe)} symbols for earnings gaps ≥{self.gap_threshold}%...")

        # v6.50: Batch pre-filter — fetch all snapshots in ONE API call, then
        # deep-check only stocks that already show gap ≥ threshold.
        # Avoids 987 individual snapshot calls; only ~0-5 stocks need deep analysis.
        gap_candidates = list(universe)  # fallback: check all if no broker
        if self.broker:
            try:
                batch_snaps = self.broker.get_snapshots(universe)
                gap_candidates = []
                _pem_gap_rejects = []
                for symbol, snap in batch_snaps.items():
                    if snap and snap.open > 0 and snap.prev_close > 0:
                        gap_pct = ((snap.open - snap.prev_close) / snap.prev_close) * 100
                        if gap_pct >= self.gap_threshold:
                            gap_candidates.append(symbol)
                        elif gap_pct > 0:
                            # v7.5: Log earnings stocks with gap but below threshold
                            _pem_gap_rejects.append({
                                'screener': 'pem', 'symbol': symbol, 'reject_reason': 'gap_below_threshold',
                                'scan_price': round(float(snap.open), 2), 'gap_pct': round(gap_pct, 2),
                            })
                        else:
                            # gap <= 0: earnings stock that gapped down or flat
                            _pem_gap_rejects.append({
                                'screener': 'pem', 'symbol': symbol, 'reject_reason': 'gap_down_or_flat',
                                'scan_price': round(float(snap.open), 2), 'gap_pct': round(gap_pct, 2),
                            })
                logger.info(f"PEM: Batch snapshot done — {len(gap_candidates)} gap candidates from {len(batch_snaps)} stocks")
                if _pem_gap_rejects:
                    try:
                        from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                        ScreenerRejectionRepository().bulk_insert(_pem_gap_rejects)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"PEM: Batch snapshot failed ({e}), falling back to individual checks")

        signals = []
        for symbol in gap_candidates:
            try:
                sig = self._check_symbol(symbol)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.debug(f"PEM: Error checking {symbol}: {e}")

        signals.sort(key=lambda s: s['gap_pct'], reverse=True)

        # v6.33: Apply sector filter (remove weak sectors)
        # PEM signals are dicts, need to convert for filtering
        if self.sector_filter and self.sector_filter.enabled and signals:
            before_count = len(signals)
            # Filter by sector field
            filtered = []
            for sig in signals:
                sector = sig.get('sector', 'Unknown')
                if self.sector_filter.is_good_sector(sector):
                    filtered.append(sig)
                else:
                    logger.debug(f"PEM: Filtered {sig['symbol']} (sector: {sector})")
            signals = filtered
            if before_count != len(signals):
                logger.info(f"🏭 PEM sector filter: {len(signals)}/{before_count} passed")

        if signals:
            logger.info(f"PEM: ✅ Found {len(signals)} earnings gap signals")
            for s in signals[:5]:
                logger.info(
                    f"  {s['symbol']}: gap {s['gap_pct']:+.1f}%, "
                    f"early_vol_ratio {s['volume_early_ratio']:.2f}x, "
                    f"score {s['score']}"
                )
        else:
            logger.info("PEM: No earnings gap signals found today")

        return signals

    def _check_symbol(self, symbol: str) -> Optional[dict]:
        """Check if a symbol has an earnings gap at current open."""

        # Step 1: Get open + prev_close + current volume from broker snapshot
        today_open = prev_close = current_price = today_volume = None

        if self.broker:
            try:
                snap = self.broker.get_snapshot(symbol)
                if snap and snap.open > 0 and snap.prev_close > 0:
                    today_open = snap.open
                    prev_close = snap.prev_close
                    current_price = snap.last or snap.open
                    today_volume = snap.volume
            except Exception as e:
                logger.debug(f"PEM: Broker snapshot failed for {symbol}: {e}")

        # Fallback: use yfinance if broker didn't provide data
        if today_open is None or prev_close is None:
            result = self._get_data_yfinance(symbol)
            if result is None:
                return None
            today_open, prev_close, current_price, today_volume = result

        if today_open <= 0 or prev_close <= 0:
            return None

        # v7.07: Override today_volume with 1m intraday sum.
        # broker daily_bar.v under-reports at 9:32 ET in paper trading (~200K vs real 5M+).
        # yfinance 1d partial bar at 9:32 is also near-zero.
        # 1m bars give actual cumulative market volume from open to now.
        intraday_vol = self._get_intraday_volume(symbol)
        if intraday_vol is not None and intraday_vol > 0:
            today_volume = intraday_vol

        # Step 2: Gap filter — must be ≥ threshold
        gap_pct = ((today_open - prev_close) / prev_close) * 100
        if gap_pct < self.gap_threshold:
            return None

        # Step 3: Volume check — early volume must confirm real catalyst
        vol_20d_avg = self._get_20d_avg_volume(symbol)
        if vol_20d_avg is None or vol_20d_avg <= 0:
            # Can't verify volume — skip (avoid unconfirmed signals)
            return None

        volume_early_ratio = (today_volume or 0) / vol_20d_avg
        if volume_early_ratio < self.volume_early_ratio_min:
            logger.debug(f"PEM: {symbol} gap {gap_pct:+.1f}% but volume too low "
                        f"({volume_early_ratio:.2f}x < {self.volume_early_ratio_min}x)")
            # v7.5: Log PEM volume rejection
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                _px = round(float(current_price or today_open or 0), 2)
                ScreenerRejectionRepository().log_rejection(
                    screener='pem', symbol=symbol, reject_reason='volume_too_low',
                    scan_price=_px, gap_pct=round(gap_pct, 2),
                    volume_ratio=round(volume_early_ratio, 3),
                )
            except Exception:
                pass
            return None

        # Step 4: ATR-based stop loss (wider for earnings day volatility)
        atr_pct = self._estimate_atr(symbol, prev_close)
        sl_pct = max(5.0, atr_pct * 1.5)  # Wider SL for earnings day
        sl_pct = min(sl_pct, 8.0)          # Cap at 8%

        entry_price = current_price or today_open
        stop_loss = round(entry_price * (1 - sl_pct / 100), 2)

        # Step 5: Score (higher gap + higher volume = higher conviction)
        score = min(100, int(50 + gap_pct * 2 + volume_early_ratio * 10))

        # Step 6: Determine BMO/AMC timing from EarningsCalendarRepository (non-blocking)
        timing = None
        try:
            from database.repositories.earnings_calendar_repository import EarningsCalendarRepository
            import sqlite3 as _sqlite3
            from pathlib import Path as _Path
            _db_path = str(_Path(__file__).resolve().parent.parent.parent / 'data' / 'trade_history.db')
            _conn = _sqlite3.connect(_db_path)
            _conn.row_factory = _sqlite3.Row
            _row = _conn.execute(
                "SELECT next_earnings_date FROM earnings_calendar WHERE symbol = ?",
                (symbol,)
            ).fetchone()
            _conn.close()
            if _row and _row['next_earnings_date']:
                import datetime as _dt
                _today = _dt.date.today().isoformat()
                if _row['next_earnings_date'] == _today:
                    # Today is earnings day — check yfinance for BMO vs AMC
                    try:
                        import yfinance as _yf
                        _tk = _yf.Ticker(symbol)
                        _cal = _tk.earnings_dates
                        if _cal is not None and not _cal.empty:
                            import pytz as _pytz
                            _et = _pytz.timezone('US/Eastern')
                            # Find today's row (within last 2 entries)
                            for _idx in _cal.index[:4]:
                                _idx_et = _idx.astimezone(_et) if _idx.tzinfo else _idx
                                if _idx_et.strftime('%Y-%m-%d') == _today:
                                    _hour = _idx_et.hour
                                    timing = 'BMO' if _hour < 12 else 'AMC'
                                    break
                    except Exception:
                        timing = None
        except Exception:
            timing = None

        # Step 7: EPS surprise % from yfinance (non-blocking, best-effort)
        eps_surprise_pct = None
        try:
            import yfinance as _yf
            _tk = _yf.Ticker(symbol)
            _ed = _tk.earnings_dates
            if _ed is not None and not _ed.empty and 'Surprise(%)' in _ed.columns:
                _recent = _ed.dropna(subset=['Surprise(%)'])
                if not _recent.empty:
                    eps_surprise_pct = round(float(_recent['Surprise(%)'].iloc[0]), 2)
        except Exception:
            eps_surprise_pct = None

        # v7.5: first_5min_return — proxy for gap-and-go vs fade at scan time (9:32)
        first_5min_return = None
        try:
            if today_open > 0 and entry_price > 0:
                first_5min_return = round((entry_price / today_open - 1) * 100, 3)
        except Exception:
            pass

        return {
            'symbol': symbol,
            'gap_pct': gap_pct,
            'volume_early_ratio': volume_early_ratio,
            'vol_20d_avg': vol_20d_avg,
            'today_volume': today_volume or 0,
            'prev_close': prev_close,
            'open_price': today_open,
            'current_price': entry_price,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'sl_pct': sl_pct,
            'atr_pct': atr_pct,
            'score': score,
            'gap_trade': True,   # EOD exit via pre_close_check()
            'source': 'pem',
            'timing': timing,
            'eps_surprise_pct': eps_surprise_pct,
            'first_5min_return': first_5min_return,
        }

    def _get_intraday_volume(self, symbol: str) -> Optional[int]:
        """Get today's cumulative intraday volume using 1m bars.

        v7.07: Broker daily_bar.v under-reports volume in paper trading at 9:32 ET
        (~200K vs actual 5M+). yfinance 1d partial bar is also near-zero.
        1m bars accumulate real market volume from open to current minute.
        Only called for gap candidates (0-5 stocks), so API cost is minimal.
        """
        try:
            df = fetch_history(symbol, period='1d', interval='1m')
            if df is None or len(df) == 0:
                return None
            return int(df['Volume'].sum())
        except Exception:
            return None

    def _get_data_yfinance(self, symbol: str):
        """Get OHLCV data from yfinance as fallback."""
        try:
            df = fetch_history(symbol, period='25d', interval='1d')
            if df is None or len(df) < 2:
                return None

            today_open = float(df['Open'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            current_price = float(df['Close'].iloc[-1]) if not pd.isna(df['Close'].iloc[-1]) else today_open
            today_volume = int(df['Volume'].iloc[-1])

            return today_open, prev_close, current_price, today_volume
        except Exception:
            return None

    def _get_20d_avg_volume(self, symbol: str) -> Optional[float]:
        """Get 20-day average volume (cached — expensive to fetch)."""
        if symbol in self._vol_cache:
            return self._vol_cache[symbol]

        try:
            df = fetch_history(symbol, period='30d', interval='1d')
            if df is None or len(df) < 20:
                return None

            # Exclude today's partial volume from average
            vol_20d_avg = float(df['Volume'].iloc[-21:-1].mean())
            self._vol_cache[symbol] = vol_20d_avg
            return vol_20d_avg
        except Exception:
            return None

    def _estimate_atr(self, symbol: str, prev_close: float) -> float:
        """Estimate ATR% from recent daily data."""
        try:
            df = fetch_history(symbol, period='25d', interval='1d')
            if df is None or len(df) < 10:
                return 3.0  # Default for volatile earnings stocks

            df = df.iloc[-21:-1]  # 20 days before today
            tr = pd.concat([
                df['High'] - df['Low'],
                (df['High'] - df['Close'].shift(1)).abs(),
                (df['Low'] - df['Close'].shift(1)).abs(),
            ], axis=1).max(axis=1)

            atr = float(tr.mean())
            return (atr / prev_close) * 100 if prev_close > 0 else 3.0
        except Exception:
            return 3.0  # Default ATR%
