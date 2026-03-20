"""
Temporal Feature Builder — understands time sequences, not just snapshots.
Computes trajectory features from last 30 days of macro + breadth data.
Part of Discovery AI v6.0.
"""
import sqlite3
import logging
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class TemporalFeatureBuilder:
    """Build temporal (time-aware) features from macro + breadth history."""

    def __init__(self):
        self._cache = {}
        self._cache_date = None

    def build_features(self, scan_date: str) -> dict:
        """Build temporal features for a given date.

        Returns dict with trajectory features computed from last 30 days.
        """
        if self._cache_date == scan_date and self._cache:
            return self._cache

        conn = sqlite3.connect(str(DB_PATH))
        try:
            features = {}

            # Load macro last 30 days
            macro_rows = conn.execute("""
                SELECT date, vix_close, vix3m_close, spy_close, crude_close,
                       yield_10y, yield_3m, gold_close
                FROM macro_snapshots
                WHERE date <= ? ORDER BY date DESC LIMIT 30
            """, (scan_date,)).fetchall()

            # Load breadth last 30 days
            breadth_rows = conn.execute("""
                SELECT date, pct_above_20d_ma, new_52w_highs, new_52w_lows, ad_ratio
                FROM market_breadth
                WHERE date <= ? ORDER BY date DESC LIMIT 30
            """, (scan_date,)).fetchall()

            if len(macro_rows) < 5 or len(breadth_rows) < 5:
                logger.warning("Temporal: insufficient data for %s", scan_date)
                return {}

            # Reverse to chronological order
            macro_rows = list(reversed(macro_rows))
            breadth_rows = list(reversed(breadth_rows))

            # Extract arrays
            vix = [r[1] for r in macro_rows if r[1] is not None]
            vix3m = [r[2] for r in macro_rows if r[2] is not None]
            spy = [r[3] for r in macro_rows if r[3] is not None]
            crude = [r[4] for r in macro_rows if r[4] is not None]
            y10 = [r[5] for r in macro_rows if r[5] is not None]
            y3m = [r[6] for r in macro_rows if r[6] is not None]
            breadth = [r[1] for r in breadth_rows if r[1] is not None]

            # --- VIX trajectory ---
            features['vix_trend_5d'] = self._slope(vix[-5:]) if len(vix) >= 5 else 0
            features['vix_acceleration'] = (
                self._slope(vix[-5:]) - self._slope(vix[-10:-5])
            ) if len(vix) >= 10 else 0

            # VIX regime duration: consecutive days above threshold
            vix_thresh = 25
            duration = 0
            for v in reversed(vix):
                if v > vix_thresh:
                    duration += 1
                else:
                    break
            features['vix_regime_duration'] = duration

            # VIX term spread trend
            if len(vix) >= 5 and len(vix3m) >= 5:
                spreads = [v - v3 for v, v3 in zip(vix[-5:], vix3m[-5:])]
                features['vix_term_spread_trend'] = self._slope(spreads)
            else:
                features['vix_term_spread_trend'] = 0

            # --- Breadth trajectory ---
            features['breadth_trend_5d'] = self._slope(breadth[-5:]) if len(breadth) >= 5 else 0

            # Breadth just broke 30
            features['breadth_just_broke_30'] = False
            if len(breadth) >= 3:
                if breadth[-1] < 30 and breadth[-2] >= 30:
                    features['breadth_just_broke_30'] = True
                elif breadth[-1] < 30 and len(breadth) >= 3 and breadth[-3] >= 30:
                    features['breadth_just_broke_30'] = True

            # Breadth recovery speed: if below 30, how fast rising
            features['breadth_recovery_speed'] = 0
            if len(breadth) >= 5 and breadth[-1] < 40:
                below_30 = [b for b in breadth[-5:] if b < 30]
                if below_30:
                    features['breadth_recovery_speed'] = breadth[-1] - min(below_30)

            # --- SPY trajectory ---
            features['spy_consecutive_red'] = 0
            features['spy_consecutive_green'] = 0
            if len(spy) >= 2:
                count = 0
                for i in range(len(spy) - 1, 0, -1):
                    if spy[i] < spy[i - 1]:
                        count += 1
                    else:
                        break
                features['spy_consecutive_red'] = count

                count = 0
                for i in range(len(spy) - 1, 0, -1):
                    if spy[i] > spy[i - 1]:
                        count += 1
                    else:
                        break
                features['spy_consecutive_green'] = count

            # SPY drawdown from 20d high
            if len(spy) >= 5:
                spy_high = max(spy[-20:]) if len(spy) >= 20 else max(spy)
                features['spy_drawdown_from_20d_high'] = (spy[-1] / spy_high - 1) * 100
            else:
                features['spy_drawdown_from_20d_high'] = 0

            # --- Crude trajectory ---
            features['crude_trend_5d'] = self._slope(crude[-5:]) if len(crude) >= 5 else 0

            # Crude level break 90
            features['crude_level_break_90'] = False
            if len(crude) >= 5:
                recent_above = crude[-1] > 90
                prev_below = any(c <= 90 for c in crude[-5:-1])
                features['crude_level_break_90'] = recent_above and prev_below

            # --- Yield spread trajectory ---
            if len(y10) >= 5 and len(y3m) >= 5:
                spreads = [a - b for a, b in zip(y10[-5:], y3m[-5:])]
                features['yield_spread_trend'] = self._slope(spreads)
                features['yield_spread_current'] = y10[-1] - y3m[-1] if y10 and y3m else 0
            else:
                features['yield_spread_trend'] = 0
                features['yield_spread_current'] = 0

            # --- Current values for context ---
            features['vix_current'] = vix[-1] if vix else 0
            features['breadth_current'] = breadth[-1] if breadth else 50
            features['spy_current'] = spy[-1] if spy else 0
            features['crude_current'] = crude[-1] if crude else 0

            self._cache = features
            self._cache_date = scan_date

            logger.info(
                "Temporal: date=%s vix_trend=%+.2f vix_dur=%dd breadth_trend=%+.2f spy_red=%d crude_trend=%+.2f",
                scan_date, features['vix_trend_5d'], features['vix_regime_duration'],
                features['breadth_trend_5d'], features['spy_consecutive_red'],
                features['crude_trend_5d'],
            )

            return features

        except Exception as e:
            logger.error("Temporal: error building features: %s", e)
            return {}
        finally:
            conn.close()

    @staticmethod
    def _slope(values: list) -> float:
        """Linear regression slope of values."""
        if len(values) < 2:
            return 0.0
        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)
        mask = ~np.isnan(y)
        if mask.sum() < 2:
            return 0.0
        x, y = x[mask], y[mask]
        n = len(x)
        slope = (n * (x * y).sum() - x.sum() * y.sum()) / (n * (x * x).sum() - x.sum() ** 2)
        return round(float(slope), 4)
