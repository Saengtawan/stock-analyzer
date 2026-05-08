#!/usr/bin/env python3
"""
PRE-MARKET GAP SCANNER v6.82

Redesigned to use batch yfinance with prepost=True for real pre-market bars.

Strategy:
- Scan at 9:00 AM ET (after 5h pre-market; enough volume to reach 2.0x threshold)
- Detect overnight gaps ≥8% with pre-market volume ≥0.3x avg daily regular volume
- Full universe: ~1000 stocks from UniverseRepository
- Confidence tiers: MAJOR_CATALYST(90%), CATALYST(80%), POSSIBLE_CATALYST(70%)

Fixes from v1.0:
- _get_premarket_price() returned regularMarketPrice (not real pre-market) → gap always ~0%
- _get_previous_close() returned today's close when market was open
- Hardcoded 35-stock watchlist
- MIN_VOLUME_RATIO=1.5x was vs daily volume (wrong basis for 5.5h pre-market window)
- Per-symbol yf.Ticker() calls (slow) → now batch yf.download() (fast)
"""

import os
import pandas as pd
import requests
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Tuple, Dict
from loguru import logger
import pytz


BATCH_SIZE = 200  # v7.9: Alpaca allows 200 symbols per /v2/stocks/bars call
ET_TZ = pytz.timezone('America/New_York')

# v7.9: Alpaca SIP bars config — replaces yfinance which returns Volume=0 for pre-market.
# SIP requires ≥15min delay on paper accounts; 20min buffer is safe.
ALPACA_BARS_URL = 'https://data.alpaca.markets/v2/stocks/bars'
SIP_DELAY_MIN = 20  # minutes


class PreMarketGapSignal:
    """Signal for pre-market gap opportunity"""

    def __init__(self, symbol: str, gap_type: str, gap_pct: float,
                 confidence: int, catalyst_type: str, volume_ratio: float,
                 prev_close: float, current_price: float,
                 day_return_estimate: float, rotation_benefit: float,
                 worth_rotating: bool, reasons: List[str],
                 atr_pct: float = 3.0):
        self.symbol = symbol
        self.gap_type = gap_type          # 'OVERNIGHT_GAP'
        self.gap_pct = gap_pct
        self.confidence = confidence      # 70, 80, or 90
        self.catalyst_type = catalyst_type
        self.volume_ratio = volume_ratio
        self.prev_close = prev_close
        self.current_price = current_price
        self.day_return_estimate = day_return_estimate
        self.rotation_benefit = rotation_benefit
        self.worth_rotating = worth_rotating
        self.reasons = reasons
        self.atr_pct = atr_pct            # v6.87: 5-day ATR % for dynamic SL
        self.timestamp = datetime.now()

    def __repr__(self):
        return (f"PreMarketGapSignal({self.symbol}, gap={self.gap_pct:.1f}%, "
                f"conf={self.confidence}%, rotation_benefit={self.rotation_benefit:+.1f}%)")


class PreMarketGapScanner:
    """
    v6.82: Batch pre-market gap scanner using real hourly bars with prepost=True.

    Downloads 1h bars (period='5d', prepost=True) in batches of 100 symbols.
    For each symbol:
      - prev_close: last Close in regular hours (9:30-15:30 ET) before today
      - premarket_price: last Close in pre-market bars (before 9:30 ET) today
      - premarket_volume: total Volume of today's pre-market bars
      - volume_ratio: premarket_volume / avg daily regular-hours volume (past days)
    """

    # Gap thresholds (v7.9: re-backtested on 204 real gaps past 90 days with Alpaca SIP vol)
    # Sweet spot = 15-25% gap with SPY green (WR 87.5%, avg +5.50%, n=8)
    # Below 15% = fade risk, above 25% = rug-pull risk
    MIN_GAP_PCT = 15.0            # v7.9: 8.0 → 15.0 (backtest: 8-10% WR 27%, 15%+ WR 50%+)
    MAX_GAP_PCT = 25.0            # v7.9: NEW — skip mega-gaps (gap≥25% WR 7.7%, rug)
    POSSIBLE_CATALYST_GAP = 15.0  # aligned with MIN_GAP_PCT
    CATALYST_GAP = 18.0
    MAJOR_CATALYST_GAP = 22.0

    # Volume ratio — backtest showed NO edge from this metric (pm_vol / avg_daily_vol)
    # Previous 2.0x was impossible to achieve (max observed 0.14x on INTC +28% gap)
    # v7.9: effectively disabled (0.01x ≈ any non-zero pm volume)
    # v7.10: 0.01 → 0.0 fully disabled. Apr 2026 paper data showed pm_vol=0.000x consistently
    # (URI +15.2%, PI +19.7% rejected for vol=0.000x though gap was real). Backtest already
    # confirmed no edge from this metric — gating on it just penalizes paper-data quirks.
    MIN_VOLUME_RATIO = 0.0        # v7.10: 0.01 → 0.0 (fully disabled)
    HIGH_VOLUME_RATIO = 0.05
    VERY_HIGH_VOLUME_RATIO = 0.15

    # v7.9: New quality filters (backtest-validated)
    MAX_ATR_PCT = 8.0             # Skip volatile stocks (USAR ATR 11.5% lost -15%)
    MIN_DOLLAR_VOLUME = 50_000_000  # $50M daily — liquidity floor (NINE was $0M penny)
    # v7.10: SPY threshold +0.3% → 0.0% (allow flat SPY).
    # Apr 2026 lost 4 actionable gaps (OMCL +20.4 SPY -0.57; NXPI/HAIN/BE +18-20% all
    # SPY -0.08%). The 0.3% bar excludes regimes where SPY is just noisy-flat.
    # Trade-off: backtest WR 75% was on SPY-green only — this widens to "not red" which
    # may dilute. Monitor: if WR drifts < 60% after n≥10, restore to +0.3%.
    REQUIRE_SPY_CHANGE_PCT = 0.0  # v7.10: 0.30 → 0.0 (flat SPY OK; tighten back if WR drifts)

    # Rotation parameters
    ROTATION_COST = 0.1           # Slippage + fees
    OPPORTUNITY_COST = 2.0        # Expected return from existing position

    def __init__(self):
        self._universe: List[str] = []
        self._spy_day_change: Optional[float] = None  # v7.9: SPY intraday change for regime gate
        self._load_universe()

    def _fetch_spy_day_change(self) -> Optional[float]:
        """v7.9: Fetch SPY open→current intraday % change for regime filter.
        Returns None if fetch fails (scanner will let all gaps pass SPY gate)."""
        try:
            bars = self._fetch_alpaca_bars(['SPY'])
            spy_df = bars.get('SPY')
            if spy_df is None or spy_df.empty:
                return None
            today = datetime.now(ET_TZ).date()
            today_bars = spy_df[spy_df.index.date == today]
            if today_bars.empty:
                return None
            # Use first bar as "open" (may be pre-market), latest as "current"
            reg_bars = today_bars[today_bars.index.time >= time(9, 30)]
            if not reg_bars.empty:
                day_open = float(reg_bars['Open'].iloc[0])
                day_current = float(reg_bars['Close'].iloc[-1])
            else:
                # Pre-market only — use pre-market open/current as rough estimate
                day_open = float(today_bars['Open'].iloc[0])
                day_current = float(today_bars['Close'].iloc[-1])
            if day_open > 0:
                return (day_current / day_open - 1) * 100
        except Exception as e:
            logger.debug(f"SPY day change fetch error: {e}")
        return None

    def _load_universe(self):
        """Load full universe from UniverseRepository (~1000 stocks)."""
        try:
            try:
                from database.repositories.universe_repository import UniverseRepository
            except ImportError:
                from src.database.repositories.universe_repository import UniverseRepository
            universe_dict = UniverseRepository().get_all()
            self._universe = list(universe_dict.keys()) if universe_dict else []
            logger.info(f"PreMarketGapScanner: Loaded {len(self._universe)} symbols from universe")
        except Exception as e:
            logger.warning(f"PreMarketGapScanner: Could not load universe ({e}), using fallback")
            self._universe = [
                'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX',
                'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN', 'COIN', 'HOOD',
                'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'SHOP',
            ]

    def scan_premarket(self, min_confidence: int = 80) -> List[PreMarketGapSignal]:
        """
        Scan all universe symbols for pre-market gaps.

        Args:
            min_confidence: Minimum confidence level (70, 80, or 90)

        Returns:
            List of gap signals sorted by rotation_benefit descending
        """
        if not self._universe:
            logger.warning("PreMarketGapScanner: No universe symbols loaded")
            return []

        today = datetime.now(ET_TZ).date()

        # v7.9: Fetch SPY day change once for regime filter (used in _analyze_symbol)
        self._spy_day_change = self._fetch_spy_day_change()
        spy_str = f"SPY={self._spy_day_change:+.2f}%" if self._spy_day_change is not None else "SPY=unknown"
        logger.info(f"PreMarketGapScanner: Scanning {len(self._universe)} symbols "
                    f"for gaps {self.MIN_GAP_PCT}-{self.MAX_GAP_PCT}% (ATR≤{self.MAX_ATR_PCT}%, "
                    f"$vol≥${self.MIN_DOLLAR_VOLUME/1e6:.0f}M, SPY≥{self.REQUIRE_SPY_CHANGE_PCT}%, {spy_str})...")

        signals: List[PreMarketGapSignal] = []
        total_with_data = 0

        for batch_start in range(0, len(self._universe), BATCH_SIZE):
            batch = self._universe[batch_start:batch_start + BATCH_SIZE]
            try:
                batch_signals, n_ok = self._scan_batch(batch, today, min_confidence)
                signals.extend(batch_signals)
                total_with_data += n_ok
            except Exception as e:
                logger.debug(f"Batch {batch_start}-{batch_start + len(batch)} error: {e}")

        signals.sort(key=lambda x: x.rotation_benefit, reverse=True)

        if signals:
            logger.info(f"PreMarketGapScanner: Found {len(signals)} gap signals "
                        f"({total_with_data}/{len(self._universe)} had data)")
            for sig in signals[:5]:
                logger.info(f"  {sig.symbol}: {sig.gap_pct:+.1f}% gap, "
                            f"{sig.catalyst_type}, vol={sig.volume_ratio:.2f}x, "
                            f"benefit={sig.rotation_benefit:+.1f}%")
        else:
            logger.info(f"PreMarketGapScanner: No gaps ≥{self.MIN_GAP_PCT}% found "
                        f"({total_with_data}/{len(self._universe)} had data)")

        return signals

    def _fetch_alpaca_bars(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """
        v7.9: Fetch 5-min bars from Alpaca SIP feed (20-min delayed on paper).
        Replaces yfinance which returned Volume=0 for pre-market bars.

        Returns dict {symbol: DataFrame with Open/High/Low/Close/Volume cols}.
        Index is ET-localized DatetimeIndex.
        """
        api_key = os.getenv('ALPACA_API_KEY')
        secret = os.getenv('ALPACA_SECRET_KEY')
        if not api_key or not secret:
            logger.error("Alpaca API keys not configured")
            return {}

        now_utc = datetime.now(timezone.utc)
        end = (now_utc - timedelta(minutes=SIP_DELAY_MIN)).isoformat().replace('+00:00', 'Z')
        start = (now_utc - timedelta(days=5)).isoformat().replace('+00:00', 'Z')

        headers = {'APCA-API-KEY-ID': api_key, 'APCA-API-SECRET-KEY': secret}

        # Paginate through all bars
        all_bars: Dict[str, list] = {}
        page_token = None
        for _ in range(20):  # safety cap
            params = {
                'symbols': ','.join(symbols),
                'timeframe': '5Min',
                'start': start, 'end': end,
                'feed': 'sip', 'limit': 10000,
                'adjustment': 'raw',
            }
            if page_token:
                params['page_token'] = page_token
            try:
                r = requests.get(ALPACA_BARS_URL, headers=headers, params=params, timeout=30)
                if r.status_code != 200:
                    logger.warning(f"Alpaca bars {r.status_code}: {r.text[:200]}")
                    break
                j = r.json()
            except Exception as e:
                logger.warning(f"Alpaca bars fetch error: {e}")
                break

            for sym, bars in (j.get('bars') or {}).items():
                all_bars.setdefault(sym, []).extend(bars)

            page_token = j.get('next_page_token')
            if not page_token:
                break

        # Convert to DataFrames with ET-localized index
        result: Dict[str, pd.DataFrame] = {}
        for sym, bars in all_bars.items():
            if not bars:
                continue
            df = pd.DataFrame(bars)
            # Alpaca fields: t,o,h,l,c,v,n,vw
            df['t'] = pd.to_datetime(df['t'], utc=True)
            df = df.set_index('t').rename(columns={
                'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'
            })[['Open', 'High', 'Low', 'Close', 'Volume']]
            df.index = df.index.tz_convert(ET_TZ)
            result[sym] = df
        return result

    def _scan_batch(self, symbols: List[str], today: date,
                    min_confidence: int) -> Tuple[List[PreMarketGapSignal], int]:
        """
        v7.9: Batch-fetch 5-min bars from Alpaca SIP, analyze each symbol.
        Returns (signals, n_symbols_with_data).
        """
        try:
            per_symbol = self._fetch_alpaca_bars(symbols)
        except Exception as e:
            logger.debug(f"Alpaca bars batch failed ({len(symbols)} symbols): {e}")
            return [], 0

        if not per_symbol:
            return [], 0

        signals = []
        n_ok = 0

        for symbol in symbols:
            try:
                sym_df = per_symbol.get(symbol)
                if sym_df is None or sym_df.empty:
                    continue

                n_ok += 1
                sig = self._analyze_symbol(symbol, sym_df, today, min_confidence)
                if sig:
                    signals.append(sig)

            except Exception as e:
                logger.debug(f"  {symbol}: analysis error: {e}")

        return signals, n_ok

    def _analyze_symbol(self, symbol: str, sym_df: pd.DataFrame,
                        today: date, min_confidence: int) -> Optional[PreMarketGapSignal]:
        """
        Detect pre-market gap for a single symbol from its 1h bar DataFrame.

        prev_close: last Close in regular hours (9:30-15:30 ET) BEFORE today
        premarket_price: last Close in pre-market bars (before 9:30 ET) TODAY
        premarket_volume: total Volume of today's pre-market bars
        volume_ratio: premarket_volume / avg daily regular-hours volume (past days)
        """
        try:
            today_idx = sym_df.index.date == today
            prev_idx = sym_df.index.date < today

            # Regular-hours bars before today (9:30 AM - 3:30 PM ET)
            regular_prev = sym_df[
                prev_idx &
                (sym_df.index.time >= time(9, 30)) &
                (sym_df.index.time <= time(15, 30))
            ]
            if regular_prev.empty:
                return None

            prev_close = float(regular_prev['Close'].iloc[-1])
            if prev_close <= 0 or pd.isna(prev_close):
                return None

            # Pre-market bars: today before 9:30 AM ET
            premarket = sym_df[
                today_idx &
                (sym_df.index.time < time(9, 30))
            ]
            if premarket.empty:
                return None  # No pre-market data yet

            premarket_price = float(premarket['Close'].iloc[-1])
            if premarket_price <= 0 or pd.isna(premarket_price):
                return None

            premarket_volume = float(premarket['Volume'].sum())

            # Gap calculation
            gap_pct = (premarket_price - prev_close) / prev_close * 100
            if gap_pct < self.MIN_GAP_PCT:
                if gap_pct > 0:
                    try:
                        from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                        ScreenerRejectionRepository().log_rejection(
                            screener='gap', symbol=symbol, reject_reason='gap_below_threshold',
                            scan_price=round(float(premarket_price), 2),
                            gap_pct=round(gap_pct, 2),
                        )
                    except Exception:
                        pass
                return None

            # v7.9: Gap ceiling — backtest: gap ≥ 25% → WR 7.7%, rug-pull risk
            if gap_pct >= self.MAX_GAP_PCT:
                logger.info(f"  GAP_TOO_BIG {symbol}: gap={gap_pct:+.1f}% ≥ {self.MAX_GAP_PCT}% (rug-pull risk)")
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='gap', symbol=symbol, reject_reason='gap_too_big',
                        scan_price=round(float(premarket_price), 2),
                        gap_pct=round(gap_pct, 2),
                    )
                except Exception:
                    pass
                return None

            # v7.9: SPY green requirement (macro tailwind) — backtest WR 75% vs 33% without
            if self._spy_day_change is not None and self._spy_day_change < self.REQUIRE_SPY_CHANGE_PCT:
                logger.info(f"  GAP_SPY_RED {symbol}: gap={gap_pct:+.1f}% but SPY={self._spy_day_change:+.2f}% < {self.REQUIRE_SPY_CHANGE_PCT}%")
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='gap', symbol=symbol, reject_reason='spy_not_green',
                        scan_price=round(float(premarket_price), 2),
                        gap_pct=round(gap_pct, 2),
                    )
                except Exception:
                    pass
                return None

            # Volume ratio: pre-market vol vs avg daily regular-hours vol (past days)
            daily_vols = regular_prev.groupby(regular_prev.index.date)['Volume'].sum()
            if daily_vols.empty:
                return None
            avg_daily_vol = float(daily_vols.mean())
            if avg_daily_vol <= 0:
                return None

            volume_ratio = premarket_volume / avg_daily_vol
            if volume_ratio < self.MIN_VOLUME_RATIO:
                # v7.4: log gap candidates rejected by volume so we can calibrate threshold
                logger.info(f"  GAP_VOL_SKIP {symbol}: gap={gap_pct:+.1f}% vol={volume_ratio:.3f}x < {self.MIN_VOLUME_RATIO}x (pm_vol={premarket_volume:,.0f} avg_daily={avg_daily_vol:,.0f})")
                # v7.5: Log to screener_rejections DB
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='gap', symbol=symbol, reject_reason='volume_too_low',
                        scan_price=round(float(premarket_price), 2),
                        gap_pct=round(gap_pct, 2), volume_ratio=round(volume_ratio, 3),
                    )
                except Exception:
                    pass
                return None

            # Classify catalyst and confidence
            catalyst_type, confidence, day_return_estimate = self._classify_catalyst(
                gap_pct, volume_ratio
            )
            if confidence < min_confidence:
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='gap', symbol=symbol, reject_reason='low_confidence',
                        scan_price=round(float(premarket_price), 2),
                        gap_pct=round(gap_pct, 2), volume_ratio=round(volume_ratio, 3),
                        catalyst_type=catalyst_type,
                    )
                except Exception:
                    pass
                return None

            rotation_benefit, worth_rotating = self._calculate_rotation_benefit(day_return_estimate)

            # v6.87: Compute 5-day ATR % from regular-hours daily H/L
            daily_atr_pct = 3.0  # fallback
            try:
                dates = sorted(set(regular_prev.index.date))
                daily_ranges = []
                for i, d in enumerate(dates):
                    day_bars = regular_prev[regular_prev.index.date == d]
                    if day_bars.empty:
                        continue
                    day_high  = float(day_bars['High'].max())
                    day_low   = float(day_bars['Low'].min())
                    if i > 0:
                        prev_day_bars = regular_prev[regular_prev.index.date == dates[i - 1]]
                        prev_close_day = float(prev_day_bars['Close'].iloc[-1]) if not prev_day_bars.empty else day_low
                        tr = max(day_high - day_low,
                                 abs(day_high - prev_close_day),
                                 abs(day_low  - prev_close_day))
                    else:
                        tr = day_high - day_low
                    daily_ranges.append(tr)
                if len(daily_ranges) >= 2:
                    atr = sum(daily_ranges[-4:]) / len(daily_ranges[-4:])
                    daily_atr_pct = round(atr / prev_close * 100, 2)
            except Exception:
                pass

            # v7.9: ATR ceiling — backtest: ATR > 8% → USAR-style −15% intraday crashes
            if daily_atr_pct > self.MAX_ATR_PCT:
                logger.info(f"  GAP_HIGH_ATR {symbol}: gap={gap_pct:+.1f}% ATR={daily_atr_pct:.1f}% > {self.MAX_ATR_PCT}% (volatility risk)")
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='gap', symbol=symbol, reject_reason='atr_too_high',
                        scan_price=round(float(premarket_price), 2),
                        gap_pct=round(gap_pct, 2), atr_pct=daily_atr_pct,
                    )
                except Exception:
                    pass
                return None

            # v7.9: Liquidity floor — backtest: NINE ($0M) penny was 0% win
            # dollar_volume = avg of (day_close × day_volume) from regular_prev
            try:
                dollar_vols = []
                for d in dates:
                    day_bars = regular_prev[regular_prev.index.date == d]
                    if day_bars.empty:
                        continue
                    day_close = float(day_bars['Close'].iloc[-1])
                    day_vol = float(day_bars['Volume'].sum())
                    dollar_vols.append(day_close * day_vol)
                avg_dollar_vol = sum(dollar_vols) / len(dollar_vols) if dollar_vols else 0
            except Exception:
                avg_dollar_vol = 0
            if avg_dollar_vol < self.MIN_DOLLAR_VOLUME:
                logger.info(f"  GAP_ILLIQUID {symbol}: gap={gap_pct:+.1f}% $vol=${avg_dollar_vol/1e6:.1f}M < ${self.MIN_DOLLAR_VOLUME/1e6:.0f}M")
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='gap', symbol=symbol, reject_reason='illiquid',
                        scan_price=round(float(premarket_price), 2),
                        gap_pct=round(gap_pct, 2),
                    )
                except Exception:
                    pass
                return None

            # v7.5: pm_range_pct — pre-market high/low range (conviction proxy)
            pm_range_pct = None
            try:
                pm_high = float(premarket['High'].max())
                pm_low = float(premarket['Low'].min())
                if premarket_price > 0 and pm_high > 0 and pm_low >= 0:
                    pm_range_pct = round((pm_high - pm_low) / premarket_price * 100, 2)
            except Exception:
                pass

            reasons = [
                f"Gap: {gap_pct:+.1f}%",
                f"Volume: {volume_ratio:.2f}x daily avg",
                f"Catalyst: {catalyst_type}",
                f"Prev close: ${prev_close:.2f} → ${premarket_price:.2f}",
                f"ATR: {daily_atr_pct:.1f}% (SL≈{daily_atr_pct * 0.3:.1f}%)",
            ]
            if worth_rotating:
                reasons.append(f"Worth rotating (+{rotation_benefit:.1f}% benefit)")

            sig = PreMarketGapSignal(
                symbol=symbol,
                gap_type='OVERNIGHT_GAP',
                gap_pct=gap_pct,
                confidence=confidence,
                catalyst_type=catalyst_type,
                volume_ratio=volume_ratio,
                prev_close=prev_close,
                current_price=premarket_price,
                day_return_estimate=day_return_estimate,
                rotation_benefit=rotation_benefit,
                worth_rotating=worth_rotating,
                reasons=reasons,
                atr_pct=daily_atr_pct,
            )
            sig.pm_range_pct = pm_range_pct
            return sig

        except Exception as e:
            logger.debug(f"  {symbol}: _analyze_symbol error: {e}")
            return None

    def _classify_catalyst(self, gap_pct: float, volume_ratio: float) -> Tuple[str, int, float]:
        """
        Classify catalyst type and assign confidence.
        Returns (catalyst_type, confidence, estimated_day_return_pct).
        """
        if gap_pct >= self.MAJOR_CATALYST_GAP and volume_ratio >= self.VERY_HIGH_VOLUME_RATIO:
            return 'MAJOR_CATALYST', 90, gap_pct * 0.40
        elif gap_pct >= self.CATALYST_GAP and volume_ratio >= self.HIGH_VOLUME_RATIO:
            return 'CATALYST', 80, gap_pct * 0.35
        elif gap_pct >= self.POSSIBLE_CATALYST_GAP and volume_ratio >= self.MIN_VOLUME_RATIO:
            return 'POSSIBLE_CATALYST', 70, gap_pct * 0.30
        else:
            return 'UNCERTAIN', 50, 0.0

    def _calculate_rotation_benefit(self, gap_return: float) -> Tuple[float, bool]:
        """Net benefit of rotating into gap vs holding current position."""
        net = gap_return - self.ROTATION_COST - self.OPPORTUNITY_COST
        return net, net > 0


# Convenience function
def scan_premarket_gaps(min_confidence: int = 80) -> List[PreMarketGapSignal]:
    """
    Scan for pre-market gaps using full universe.

    Args:
        min_confidence: Minimum confidence (70, 80, or 90)

    Returns:
        List of high-confidence gap signals
    """
    scanner = PreMarketGapScanner()
    return scanner.scan_premarket(min_confidence)


if __name__ == '__main__':
    logger.info("Testing Pre-Market Gap Scanner v6.82...")
    signals = scan_premarket_gaps(min_confidence=70)

    if signals:
        print(f"\n✅ Found {len(signals)} gap signals:\n")
        for sig in signals:
            print(f"{sig.symbol}:")
            print(f"  Gap: {sig.gap_pct:+.1f}%")
            print(f"  Confidence: {sig.confidence}%")
            print(f"  Catalyst: {sig.catalyst_type}")
            print(f"  Volume: {sig.volume_ratio:.2f}x daily avg")
            print(f"  Rotation benefit: {sig.rotation_benefit:+.1f}%")
            print(f"  Worth rotating: {'✅ YES' if sig.worth_rotating else '❌ NO'}")
            print()
    else:
        print("\n❌ No gaps found (market may be closed or no significant gaps today)")
