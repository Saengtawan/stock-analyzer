"""
Pre-Earnings Drift (PED) Screener v1.2 (v6.66)

Detects stocks 5 trading days before earnings announcement.
Live signal_outcomes analysis (2026):
- D-5 buy → D-1 exit via EARNINGS_AUTO_SELL
- DIP-quality stocks at D-5: WR1d=79%, WR3d=79% ← key insight
- Low-quality stocks at D-5: WR3d=12% ← quality is the driver, not just timing
- ~2-4 trades/month

Exit: EARNINGS_AUTO_SELL in _check_position() (no new exit code needed).

v6.66 (full universe):
- Universe: full 987-stock universe (was pre-filter pool ~200-300)
- Earnings lookup: DB-first via EarningsCalendarRepository (instant, no yfinance per symbol)
- scan() pre-filters to D-5 candidates in O(1) before any OHLCV fetch
- Requires DB seeded: python3 src/batch/fetch_earnings_dates.py
- Engine refreshes DB daily at 7 AM ET via _loop_earnings_calendar_refresh()

v6.58 fixes (kept):
- D-5 only (dropped D-4: WR3d=38% at exit point)
- vol_avg excludes today (was including today's volume → circular reference)
- proximity_score fixed for D-5
- earnings_dates as primary API
- Green day filter: close > prev_close
- volume_ratio_min raised: 0.8 → 1.0
- SPY intraday filter
"""

import os
import json
from datetime import datetime, date
from typing import List, Optional, Dict
from loguru import logger

try:
    import pandas as pd
    from api.yfinance_utils import fetch_history
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class PEDScreener:
    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data'
    )

    def __init__(self, broker=None, config: dict = None):
        self.broker = broker
        self.config = config or {}
        self.days_before_min = int(self.config.get('ped_days_before_min', 5))
        self.days_before_max = int(self.config.get('ped_days_before_max', 5))
        self.rsi_min = float(self.config.get('ped_rsi_min', 35.0))
        self.rsi_max = float(self.config.get('ped_rsi_max', 65.0))
        self.volume_ratio_min = float(self.config.get('ped_volume_ratio_min', 1.0))

        # v6.66: DB-backed earnings calendar
        self._earnings_repo = None
        self._earnings_days_cache: Dict[str, Optional[int]] = {}  # {sym: days_until}
        self._earnings_cache_date: Optional[str] = None           # date str when cache was loaded
        try:
            from database.repositories.earnings_calendar_repository import EarningsCalendarRepository
            self._earnings_repo = EarningsCalendarRepository()
            logger.debug("PED: EarningsCalendarRepository initialized")
        except Exception as e:
            logger.warning(f"PED: EarningsCalendarRepository unavailable: {e}")

    # -------------------------------------------------------------------------
    # Universe
    # -------------------------------------------------------------------------

    def get_universe(self) -> List[str]:
        """
        v6.72: Full 987-stock universe from universe_stocks DB.
        Falls back to full_universe_cache.json if DB is empty.
        """
        try:
            from database.repositories.universe_repository import UniverseRepository
            symbols = UniverseRepository().get_symbols()
            if symbols:
                logger.info(f"PED: Loaded {len(symbols)} stocks from universe_stocks DB")
                return symbols
        except Exception as e:
            logger.warning(f"PED: universe_stocks DB unavailable: {e}")
        # JSON fallback
        try:
            universe_file = os.path.join(self.DATA_DIR, 'full_universe_cache.json')
            with open(universe_file) as f:
                symbols = list(json.load(f).keys())
            if symbols:
                logger.info(f"PED: Loaded {len(symbols)} stocks from full_universe_cache.json (fallback)")
                return symbols
        except Exception as e:
            logger.warning(f"PED: full_universe_cache.json unavailable: {e}")
        return []

    # -------------------------------------------------------------------------
    # Scan
    # -------------------------------------------------------------------------

    def scan(self) -> List[dict]:
        """
        Scan for PED signals. Call at 9:32 ET after market open.

        v6.66 flow:
        1. Load earnings calendar from DB → instant dict {sym: days_until}
        2. Pre-filter to D-5 candidates (~5-20 stocks)
        3. Fetch OHLCV only for those candidates
        4. Apply quality filters
        """
        if not YFINANCE_AVAILABLE:
            return []

        universe = self.get_universe()
        if not universe:
            logger.warning("PED: Empty universe")
            return []

        # Load earnings calendar from DB (O(1) per symbol after initial load)
        days_map = self._load_earnings_days_map()
        if not days_map:
            logger.warning("PED: Earnings calendar DB empty — run: python3 src/batch/fetch_earnings_dates.py")
            return []

        # Pre-filter: only symbols at D-5 window
        candidates = [
            sym for sym in universe
            if days_map.get(sym) is not None
            and self.days_before_min <= days_map[sym] <= self.days_before_max
        ]

        logger.info(
            f"PED: {len(universe)} universe → {len(candidates)} D-{self.days_before_min} candidates "
            f"(DB lookup instant)"
        )

        if not candidates:
            logger.info("PED: No D-5 candidates today")
            return []

        # Deep check only the candidates
        signals = []
        for symbol in candidates:
            try:
                sig = self._check_symbol(symbol, days_map[symbol])
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.debug(f"PED: Error checking {symbol}: {e}")

        signals.sort(key=lambda s: s['score'], reverse=True)
        if signals:
            logger.info(f"PED: ✅ Found {len(signals)} pre-earnings drift signals")
            for s in signals[:5]:
                logger.info(
                    f"  {s['symbol']}: D-{s['days_until_earnings']} earnings, "
                    f"RSI={s['rsi']:.0f}, score={s['score']}"
                )
        else:
            logger.info("PED: No pre-earnings drift signals today")
        return signals

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _load_earnings_days_map(self) -> Dict[str, Optional[int]]:
        """
        Load {symbol: days_until_earnings} from DB.
        Cached per calendar date — reloads once per day.
        """
        today_str = date.today().isoformat()
        if self._earnings_cache_date == today_str and self._earnings_days_cache:
            return self._earnings_days_cache

        if self._earnings_repo is None:
            return {}

        try:
            self._earnings_days_cache = self._earnings_repo.get_days_until_all()
            self._earnings_cache_date = today_str
            cached = sum(1 for v in self._earnings_days_cache.values() if v is not None)
            logger.debug(f"PED: Loaded earnings calendar from DB ({len(self._earnings_days_cache)} symbols, {cached} with upcoming earnings)")
            return self._earnings_days_cache
        except Exception as e:
            logger.warning(f"PED: Failed to load earnings calendar from DB: {e}")
            return {}

    def _check_symbol(self, symbol: str, days_until: int) -> Optional[dict]:
        """Deep check: OHLCV + quality filters for a D-5 candidate."""

        # Fetch OHLCV
        df = fetch_history(symbol, period='30d', interval='1d')
        if df is None or len(df) < 20:
            return None

        close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if len(df) >= 2 else close
        sma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        if close <= 0 or sma20 <= 0:
            return None

        def _log_ped_reject(reason, **kwargs):
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                ScreenerRejectionRepository().log_rejection(
                    screener='ped', symbol=symbol, reject_reason=reason,
                    scan_price=round(close, 2), **kwargs
                )
            except Exception:
                pass

        # Green day filter
        if close <= prev_close:
            logger.debug(f"PED: {symbol} rejected — red day ({close:.2f} <= {prev_close:.2f})")
            _log_ped_reject('red_day')
            return None

        # Above SMA20
        if close < sma20 * 0.97:
            _log_ped_reject('below_sma20')
            return None

        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.0001)
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if not (self.rsi_min <= rsi <= self.rsi_max):
            _log_ped_reject('rsi_out_of_range', rsi=round(rsi, 1))
            return None

        # Volume ratio (exclude today)
        vol_avg = float(df['Volume'].iloc[:-1].rolling(20).mean().iloc[-1])
        today_vol = float(df['Volume'].iloc[-1])
        volume_ratio = today_vol / vol_avg if vol_avg > 0 else 1.0
        if volume_ratio < self.volume_ratio_min:
            _log_ped_reject('volume_too_low', volume_ratio=round(volume_ratio, 3))
            return None

        # SPY intraday filter
        try:
            spy_df = fetch_history('SPY', period='1d', interval='5m')
            if spy_df is not None and len(spy_df) >= 2:
                spy_open = float(spy_df['Open'].iloc[0])
                spy_now = float(spy_df['Close'].iloc[-1])
                spy_intraday = (spy_now - spy_open) / spy_open * 100
                if spy_intraday < -1.0:
                    logger.debug(f"PED: {symbol} rejected — SPY intraday {spy_intraday:+.1f}%")
                    _log_ped_reject('spy_intraday_bad')
                    return None
        except Exception:
            pass

        # ATR-based SL
        prev_c = df['Close'].shift(1)
        tr = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - prev_c).abs(),
            (df['Low'] - prev_c).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = (atr / close * 100) if close > 0 else 3.0
        sl_pct = max(3.0, min(atr_pct * 1.5, 5.0))
        stop_loss = round(close * (1 - sl_pct / 100), 2)

        # Score
        rsi_score = 15 if 45 <= rsi <= 60 else 10 if 40 <= rsi <= 65 else 5
        vol_score = min(15, int(volume_ratio * 10))
        momentum_5d = float(
            (close - df['Close'].iloc[-6]) / df['Close'].iloc[-6] * 100
        ) if len(df) >= 6 else 0
        momentum_score = 10 if 0 < momentum_5d < 5 else 5 if momentum_5d <= 0 else 3
        proximity_score = 5 if days_until == 5 else 3
        score = min(100, 60 + rsi_score + vol_score + momentum_score + proximity_score)

        return {
            'symbol': symbol,
            'days_until_earnings': days_until,
            'entry_price': close,
            'stop_loss': stop_loss,
            'sl_pct': sl_pct,
            'atr_pct': atr_pct,
            'rsi': rsi,
            'volume_ratio': volume_ratio,
            'momentum_5d': momentum_5d,
            'score': score,
            'source': 'ped',
        }
