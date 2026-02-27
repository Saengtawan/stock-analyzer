"""
Pre-Earnings Drift (PED) Screener v1.1 (v6.58)

Detects stocks 5 trading days before earnings announcement.
Live signal_outcomes analysis (2026):
- D-5 buy → D-1 exit via EARNINGS_AUTO_SELL
- DIP-quality stocks at D-5: WR1d=79%, WR3d=79% ← key insight
- Low-quality stocks at D-5: WR3d=12% ← quality is the driver, not just timing
- ~2-4 trades/month

Exit: EARNINGS_AUTO_SELL in _check_position() (no new exit code needed).

v6.58 fixes:
- D-5 only (dropped D-4: WR3d=38% at exit point)
- vol_avg excludes today (was including today's volume → circular reference)
- proximity_score fixed for D-5 (was scoring D-4 higher)
- earnings_dates as primary API (more reliable than calendar-only)
- Green day filter: close > prev_close (stock trending up on entry day)
- volume_ratio_min raised: 0.8 → 1.0 (match DIP quality)
- SPY intraday filter: don't buy when SPY down >1% at scan time
"""

import os
import json
from datetime import datetime
from typing import List, Optional, Dict
from loguru import logger

try:
    import yfinance as yf
    import pandas as pd
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class PEDScreener:
    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'
    )

    def __init__(self, broker=None, config: dict = None):
        self.broker = broker
        self.config = config or {}
        self.days_before_min = int(self.config.get('ped_days_before_min', 5))
        self.days_before_max = int(self.config.get('ped_days_before_max', 5))
        self.rsi_min = float(self.config.get('ped_rsi_min', 35.0))
        self.rsi_max = float(self.config.get('ped_rsi_max', 65.0))
        self.volume_ratio_min = float(self.config.get('ped_volume_ratio_min', 1.0))  # v6.58: 0.8→1.0
        self._earnings_cache: Dict[str, Optional[int]] = {}  # {sym: days_until or None}

    def get_universe(self) -> List[str]:
        """Load pre-filter pool (evening scan ~200-300 stocks)."""
        try:
            from database.repositories.pre_filter_repository import PreFilterRepository
            repo = PreFilterRepository()
            session = repo.get_latest_session(scan_type='evening')
            if session and session.status == 'completed' and session.is_ready:
                pool = repo.get_filtered_pool(session_id=session.id)
                if pool:
                    return [s.symbol for s in pool]
        except Exception as e:
            logger.debug(f"PED: Error loading pre-filter pool: {e}")
        # Fallback: full universe
        try:
            universe_file = os.path.join(self.DATA_DIR, 'full_universe_cache.json')
            with open(universe_file) as f:
                return list(json.load(f).keys())
        except Exception:
            return []

    def scan(self) -> List[dict]:
        """
        Scan for PED signals. Call at 9:35 ET after market open.
        Returns list of signal dicts sorted by score descending.
        """
        if not YFINANCE_AVAILABLE:
            return []
        universe = self.get_universe()
        if not universe:
            logger.warning("PED: Empty universe")
            return []

        logger.info(f"PED: Scanning {len(universe)} symbols for D-{self.days_before_min}/D-{self.days_before_max} setups...")
        signals = []

        for symbol in universe:
            try:
                sig = self._check_symbol(symbol)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.debug(f"PED: Error checking {symbol}: {e}")

        signals.sort(key=lambda s: s['score'], reverse=True)
        if signals:
            logger.info(f"PED: ✅ Found {len(signals)} pre-earnings drift signals")
            for s in signals[:5]:
                logger.info(f"  {s['symbol']}: D-{s['days_until_earnings']} earnings, RSI={s['rsi']:.0f}, score={s['score']}")
        else:
            logger.info("PED: No pre-earnings drift signals today")
        return signals

    def _check_symbol(self, symbol: str) -> Optional[dict]:
        # Step 1: Check earnings timing
        days_until = self._get_trading_days_until_earnings(symbol)
        if days_until is None:
            return None
        if not (self.days_before_min <= days_until <= self.days_before_max):
            return None

        # Step 2: Fetch OHLCV data
        ticker = yf.Ticker(symbol)
        df = ticker.history(period='30d', interval='1d', auto_adjust=True)
        if df is None or len(df) < 20:
            return None

        close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if len(df) >= 2 else close
        sma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        if close <= 0 or sma20 <= 0:
            return None

        # Step 3: Quality filters

        # v6.58: Green day — stock must be up on entry day (trending into earnings)
        # Data: SKIPPED_FILTER D-5 stocks had avg_1d=-3.96% → they were already falling
        if close <= prev_close:
            logger.debug(f"PED: {symbol} rejected — red day ({close:.2f} <= {prev_close:.2f})")
            return None

        # Must be above SMA20 (uptrend context)
        if close < sma20 * 0.97:
            return None

        # RSI check
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.0001)
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        if not (self.rsi_min <= rsi <= self.rsi_max):
            return None

        # Volume ratio vs 20d avg (v6.58: exclude today to avoid circular reference)
        vol_avg = float(df['Volume'].iloc[:-1].rolling(20).mean().iloc[-1])
        today_vol = float(df['Volume'].iloc[-1])
        volume_ratio = today_vol / vol_avg if vol_avg > 0 else 1.0
        if volume_ratio < self.volume_ratio_min:
            return None

        # v6.58: SPY intraday check — don't buy on broad market selloff days
        try:
            spy_df = yf.Ticker('SPY').history(period='1d', interval='5m', auto_adjust=True)
            if spy_df is not None and len(spy_df) >= 2:
                spy_open = float(spy_df['Open'].iloc[0])
                spy_now = float(spy_df['Close'].iloc[-1])
                spy_intraday = (spy_now - spy_open) / spy_open * 100
                if spy_intraday < -1.0:
                    logger.debug(f"PED: {symbol} rejected — SPY intraday {spy_intraday:+.1f}% (market selloff)")
                    return None
        except Exception:
            pass  # Skip SPY check on error, don't block signal

        # Step 4: ATR-based SL/TP
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

        # Step 5: Score
        rsi_score = 15 if 45 <= rsi <= 60 else 10 if 40 <= rsi <= 65 else 5
        vol_score = min(15, int(volume_ratio * 10))
        momentum_5d = float((close - df['Close'].iloc[-6]) / df['Close'].iloc[-6] * 100) if len(df) >= 6 else 0
        momentum_score = 10 if 0 < momentum_5d < 5 else 5 if momentum_5d <= 0 else 3
        proximity_score = 5 if days_until == 5 else 3  # v6.58: D-5 is the target (was D-4)
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

    def _get_trading_days_until_earnings(self, symbol: str) -> Optional[int]:
        """Get trading days until next earnings. Cached per scan run.

        Uses ticker.earnings_dates as primary (tz-aware index, most reliable),
        falls back to ticker.calendar if unavailable.
        """
        if symbol in self._earnings_cache:
            return self._earnings_cache[symbol]

        result = None
        today = datetime.now().date()
        try:
            ticker = yf.Ticker(symbol)

            # Primary: ticker.earnings_dates (tz-aware DatetimeIndex, more reliable)
            ed_series = ticker.earnings_dates
            if ed_series is not None and not ed_series.empty:
                # Normalize tz-aware index to date strings → avoid tz comparison bugs
                future_dates = sorted([
                    datetime.strptime(i.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
                    for i in ed_series.index
                    if i.strftime('%Y-%m-%d') > today.strftime('%Y-%m-%d')
                ])
                if future_dates:
                    nearest = future_dates[0]
                    bdays = pd.bdate_range(start=today, end=nearest)
                    days = max(0, len(bdays) - 1)  # exclude today
                    if 0 < days <= 10:
                        result = days
                    self._earnings_cache[symbol] = result
                    return result

            # Fallback: ticker.calendar
            cal = ticker.calendar
            if cal and isinstance(cal, dict):
                earnings_dates = cal.get('Earnings Date')
                if earnings_dates:
                    if not isinstance(earnings_dates, (list, tuple)):
                        earnings_dates = [earnings_dates]
                    for ed in earnings_dates:
                        if hasattr(ed, 'date'):
                            ed = ed.date()
                        elif isinstance(ed, str):
                            ed = datetime.strptime(ed[:10], '%Y-%m-%d').date()
                        if ed > today:
                            bdays = pd.bdate_range(start=today, end=ed)
                            days = max(0, len(bdays) - 1)
                            if 0 < days <= 10:
                                result = days
                            break
        except Exception as e:
            logger.debug(f"PED: earnings lookup failed for {symbol}: {e}")

        self._earnings_cache[symbol] = result
        return result
