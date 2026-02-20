"""
Post-Earnings Momentum (PEM) Screener v1.0

Detects stocks with positive earnings gaps at market open (9:35 ET):
- Gap up 8%+ from prev close to open
- Elevated early-session volume (confirms real catalyst)

Backtest (2023-2025, 148 stocks):
- Win Rate: 57.6% | Avg P&L: +3.24% | Events: ~2.3/month
- Estimated monthly: ~$396 on $25k capital
- Source: backtests/backtest_post_earnings_momentum.py

Exit: Same-day at market close (gap_trade=True → pre_close_check() closes at EOD)
"""

import os
import json
from typing import List, Optional, Dict
from loguru import logger

try:
    import yfinance as yf
    import pandas as pd
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class PEMScreener:
    """
    Post-Earnings Momentum Screener.

    Scans for confirmed earnings gaps at 9:35 ET when open prices are known.
    Uses broker snapshots for fast open/prev_close detection.
    Uses yfinance for 20d avg volume (cached to avoid repeated calls).

    Run once per day at 9:35 ET via _loop_pem_scan() in auto_trading_engine.
    """

    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'
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
        # Volume check: today's partial volume (9:35) / 20d avg.
        # At 9:35 (~5 min of trading), earnings stocks typically have 30%+ of daily vol already.
        # Normal stocks at 9:35 have ~5-10% of daily vol.
        # Threshold 0.15 = "already 15% of daily avg in first 5 min" → ~2-3x by EOD.
        self.volume_early_ratio_min = float(self.config.get('pem_volume_early_ratio_min', 0.15))

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
        Get scan universe from pre-filter pool.

        Pre-filter pool has ~200-400 quality stocks. PEM looks for earnings gaps
        among these stocks. Not all earnings gaps will be in the pool, but this
        provides a quality-screened starting point without rate limit issues.
        """
        try:
            if os.path.exists(self.PRE_FILTERED_FILE):
                with open(self.PRE_FILTERED_FILE, 'r') as f:
                    data = json.load(f)
                stocks = data.get('stocks', [])
                if isinstance(stocks, list) and stocks:
                    if isinstance(stocks[0], dict):
                        return [s['symbol'] for s in stocks if s.get('symbol')]
                    return [s for s in stocks if isinstance(s, str)]
        except Exception as e:
            logger.debug(f"PEM: Error loading pre-filtered pool: {e}")

        logger.warning("PEM: Pre-filtered pool unavailable, using fallback list")
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
        Scan for PEM signals at market open (call at 9:35 ET).

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

        signals = []
        for symbol in universe:
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
            return None

        # Step 4: ATR-based stop loss (wider for earnings day volatility)
        atr_pct = self._estimate_atr(symbol, prev_close)
        sl_pct = max(5.0, atr_pct * 1.5)  # Wider SL for earnings day
        sl_pct = min(sl_pct, 8.0)          # Cap at 8%

        entry_price = current_price or today_open
        stop_loss = round(entry_price * (1 - sl_pct / 100), 2)

        # Step 5: Score (higher gap + higher volume = higher conviction)
        score = min(100, int(50 + gap_pct * 2 + volume_early_ratio * 10))

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
        }

    def _get_data_yfinance(self, symbol: str):
        """Get OHLCV data from yfinance as fallback."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='25d', interval='1d')
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
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='30d', interval='1d')
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
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='25d', interval='1d')
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
