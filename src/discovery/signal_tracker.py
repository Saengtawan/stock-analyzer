"""
Signal IC Tracker — v17 Layer 3.

Tracks the actual Information Coefficient (IC) of each boost signal
and auto-adjusts weights. Replaces hardcoded +0.5/+0.3/-0.3 boosts.

Signals tracked:
  insider_bought:     IC of insider open-market purchases (90d window)
  analyst_upgrade:    IC of analyst PT raise >5%
  analyst_downgrade:  IC of analyst PT drop >5%
  options_bullish:    IC of P/C < 0.7 (when data available)
  options_bearish:    IC of P/C > 1.3 (when data available)

IC computed as correlation(signal_present, 5d_forward_return) on rolling 90d.
If IC > 0.02 and n ≥ 50: weight = IC × 10 (scaled ~0.2-0.5)
If IC < 0.02 or n < 50: weight = 0 (auto-disabled)

Walk-forward safe: fit(max_date) only uses data up to max_date.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import time
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

SIGNALS = ['insider_bought', 'analyst_upgrade', 'analyst_downgrade',
           'options_bullish', 'options_bearish']

MIN_IC = 0.02       # below this → weight = 0 (noise)
MIN_OBS = 50        # minimum observations to compute IC
IC_SCALE = 10.0     # weight = IC × scale (maps IC 0.05 → weight 0.5)
MAX_WEIGHT = 1.0    # cap weight
MAX_CHANGE_PCT = 30  # safety: max ±30% weight change per refit


class SignalTracker:
    """Track signal IC and auto-adjust boost weights."""

    def __init__(self):
        self._weights = {}        # {signal_name: weight}
        self._ic_values = {}      # {signal_name: ic}
        self._obs_counts = {}     # {signal_name: n_observations}
        self._fitted = False
        self._fit_time = 0.0
        self._ensure_tables()

    def fit(self, max_date=None) -> bool:
        """Learn IC-based weights for each signal from historical data."""
        t0 = time.time()
        old_weights = dict(self._weights)

        # conn via get_session()
        conn.execute('PRAGMA busy_timeout=5000')

        try:
            # Load stock forward returns
            date_filter = f"AND s.date <= '{max_date}'" if max_date else ""
            fwd_returns = self._load_forward_returns(conn, date_filter)
            if len(fwd_returns) < 500:
                logger.warning("SignalTracker: insufficient data (%d rows)", len(fwd_returns))
                return False

            # Compute IC for each signal
            for signal_name in SIGNALS:
                signal_data = self._load_signal(conn, signal_name, date_filter)
                ic, n_obs, avg_present, avg_absent = self._compute_ic(
                    fwd_returns, signal_data)

                self._ic_values[signal_name] = ic
                self._obs_counts[signal_name] = n_obs

                # Compute weight
                if ic > MIN_IC and n_obs >= MIN_OBS:
                    weight = min(ic * IC_SCALE, MAX_WEIGHT)
                elif ic < -MIN_IC and n_obs >= MIN_OBS:
                    weight = max(ic * IC_SCALE, -MAX_WEIGHT)
                else:
                    weight = 0.0

                # Safety guard: cap change
                if signal_name in old_weights and old_weights[signal_name] != 0:
                    old_w = old_weights[signal_name]
                    if abs(weight - old_w) / max(abs(old_w), 0.01) > MAX_CHANGE_PCT / 100:
                        if weight > old_w:
                            weight = old_w * (1 + MAX_CHANGE_PCT / 100)
                        else:
                            weight = old_w * (1 - MAX_CHANGE_PCT / 100)

                self._weights[signal_name] = round(weight, 4)

                logger.info("SignalTracker: %s IC=%.4f n=%d weight=%.3f "
                            "avg_present=%.3f avg_absent=%.3f",
                            signal_name, ic, n_obs, self._weights[signal_name],
                            avg_present, avg_absent)

        finally:
            pass

        self._fitted = True
        self._fit_time = time.time()
        self.save_to_db()

        elapsed = time.time() - t0
        logger.info("SignalTracker: fitted in %.1fs — weights=%s", elapsed, self._weights)
        return True

    def boost(self, candidate: dict, scan_date: str = None) -> float:
        """Compute total boost for a candidate based on tracked signal ICs.

        Reads pre-enriched fields from candidate (set by engine._enrich_candidates).
        Returns float boost value to add to score.
        """
        if not self._fitted:
            return 0.0

        total = 0.0
        if candidate.get('insider_bought') and self._weights.get('insider_bought', 0):
            total += self._weights['insider_bought']
        if candidate.get('analyst_upgrade') and self._weights.get('analyst_upgrade', 0):
            total += self._weights['analyst_upgrade']
        if candidate.get('analyst_downgrade') and self._weights.get('analyst_downgrade', 0):
            total += self._weights['analyst_downgrade']
        if candidate.get('options_bullish') and self._weights.get('options_bullish', 0):
            total += self._weights['options_bullish']
        if candidate.get('options_bearish') and self._weights.get('options_bearish', 0):
            total += self._weights['options_bearish']
        return round(total, 4)

    def needs_refit(self, days=30) -> bool:
        if not self._fitted:
            return True
        return (time.time() - self._fit_time) > days * 86400

    # === Data Loading ===

    def _load_forward_returns(self, conn, date_filter):
        """Load (symbol, date, fwd_5d_return) from stock_daily_ohlc."""
        rows = conn.execute(f"""
            SELECT s.symbol, s.date, s.close,
                   LEAD(s.close, 5) OVER (PARTITION BY s.symbol ORDER BY s.date) as c5
            FROM stock_daily_ohlc s
            JOIN stock_fundamentals sf ON s.symbol = sf.symbol
            WHERE s.close > 0 AND sf.market_cap > 3e9 AND sf.avg_volume > 100000
            AND s.date >= date('now', '-15 months')
            {date_filter}
            ORDER BY s.symbol, s.date
        """).fetchall()

        result = {}  # {(symbol, date): fwd_return}
        for sym, dt, close, c5 in rows:
            if c5 and c5 > 0:
                result[(sym, dt)] = (c5 / close - 1) * 100
        return result

    def _load_signal(self, conn, signal_name, date_filter):
        """Load signal presence as {(symbol, date): True} for a given signal."""
        signals = {}

        if signal_name == 'insider_bought':
            # Insider purchases >$10K — mark stock-date as having signal
            # if any purchase in [date-90d, date]
            rows = conn.execute(f"""
                SELECT symbol, trade_date FROM insider_transactions_history
                WHERE (transaction_type LIKE '%Purchase%'
                       OR transaction_type LIKE '%Buy%')
                AND value > 10000
                AND trade_date >= date('now', '-18 months')
                {date_filter.replace('s.date', 'trade_date')}
                ORDER BY symbol, trade_date
            """).fetchall()

            # Build {symbol: [dates]} for efficient 90d window lookup
            from collections import defaultdict
            sym_dates = defaultdict(list)
            for sym, dt in rows:
                sym_dates[sym].append(dt)

            # For each stock in universe, check if any purchase in 90d window
            all_dates = conn.execute("""
                SELECT DISTINCT date FROM stock_daily_ohlc
                WHERE date >= date('now', '-15 months')
                ORDER BY date
            """).fetchall()

            for sym, purchase_dates in sym_dates.items():
                pd_set = set(purchase_dates)
                for (dt,) in all_dates:
                    # Simple: check if any purchase_date in [dt-90d, dt]
                    # Approximate: if symbol has any purchase in last 15 months
                    # More precise: iterate purchase dates
                    for pd in purchase_dates:
                        if pd <= dt and pd >= _date_sub(dt, 90):
                            signals[(sym, dt)] = True
                            break

        elif signal_name == 'analyst_upgrade':
            rows = conn.execute(f"""
                SELECT arh.symbol, arh.date
                FROM analyst_ratings_history arh
                WHERE arh.price_target > arh.prior_price_target * 1.05
                AND arh.price_target > 0 AND arh.prior_price_target > 0
                AND arh.date >= date('now', '-18 months')
                {date_filter.replace('s.date', 'arh.date')}
            """).fetchall()

            from collections import defaultdict
            sym_dates = defaultdict(set)
            for sym, dt in rows:
                sym_dates[sym].add(dt)

            # Mark stock-dates within 90d of upgrade
            all_dates_rows = conn.execute("""
                SELECT DISTINCT date FROM stock_daily_ohlc
                WHERE date >= date('now', '-15 months')
                ORDER BY date
            """).fetchall()

            for sym, upgrade_dates in sym_dates.items():
                for (dt,) in all_dates_rows:
                    for ud in upgrade_dates:
                        if ud <= dt and ud >= _date_sub(dt, 90):
                            signals[(sym, dt)] = True
                            break

        elif signal_name == 'analyst_downgrade':
            rows = conn.execute(f"""
                SELECT arh.symbol, arh.date
                FROM analyst_ratings_history arh
                WHERE arh.price_target < arh.prior_price_target * 0.95
                AND arh.price_target > 0 AND arh.prior_price_target > 0
                AND arh.date >= date('now', '-18 months')
                {date_filter.replace('s.date', 'arh.date')}
            """).fetchall()

            from collections import defaultdict
            sym_dates = defaultdict(set)
            for sym, dt in rows:
                sym_dates[sym].add(dt)

            all_dates_rows = conn.execute("""
                SELECT DISTINCT date FROM stock_daily_ohlc
                WHERE date >= date('now', '-15 months')
                ORDER BY date
            """).fetchall()

            for sym, downgrade_dates in sym_dates.items():
                for (dt,) in all_dates_rows:
                    for dd in downgrade_dates:
                        if dd <= dt and dd >= _date_sub(dt, 90):
                            signals[(sym, dt)] = True
                            break

        elif signal_name == 'options_bullish':
            try:
                rows = conn.execute("""
                    SELECT symbol, collected_date, pc_volume_ratio
                    FROM options_daily_summary
                    WHERE pc_volume_ratio < 0.7 AND pc_volume_ratio > 0
                """).fetchall()
                for sym, dt, pc in rows:
                    signals[(sym, dt)] = True
            except Exception:
                pass  # table may not exist

        elif signal_name == 'options_bearish':
            try:
                rows = conn.execute("""
                    SELECT symbol, collected_date, pc_volume_ratio
                    FROM options_daily_summary
                    WHERE pc_volume_ratio > 1.3
                """).fetchall()
                for sym, dt, pc in rows:
                    signals[(sym, dt)] = True
            except Exception:
                pass  # table may not exist

        return signals

    def _compute_ic(self, fwd_returns, signal_data):
        """Compute IC = correlation(signal_present, fwd_return).

        Returns (ic, n_observations, avg_return_present, avg_return_absent).
        """
        present_returns = []
        absent_returns = []

        for key, fwd_ret in fwd_returns.items():
            if key in signal_data:
                present_returns.append(fwd_ret)
            else:
                absent_returns.append(fwd_ret)

        n_present = len(present_returns)
        n_total = n_present + len(absent_returns)

        if n_present < 10 or n_total < MIN_OBS:
            return 0.0, n_present, 0.0, 0.0

        avg_present = np.mean(present_returns)
        avg_absent = np.mean(absent_returns)

        # IC as point-biserial correlation
        # signal_binary: 1 if present, 0 if absent
        # Equivalent to: (avg_present - avg_absent) * sqrt(n1*n0) / (n * std_all)
        all_returns = np.array(present_returns + absent_returns)
        all_signals = np.array([1.0] * n_present + [0.0] * len(absent_returns))

        std_ret = np.std(all_returns)
        if std_ret < 1e-10:
            return 0.0, n_present, avg_present, avg_absent

        ic = float(np.corrcoef(all_signals, all_returns)[0, 1])
        if np.isnan(ic):
            ic = 0.0

        return round(ic, 4), n_present, round(avg_present, 4), round(avg_absent, 4)

    # === DB Persistence ===

    def _ensure_tables(self):
        # conn via get_session()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_ic_tracker (
                signal_name TEXT NOT NULL,
                fit_date TEXT NOT NULL,
                ic_90d REAL,
                weight REAL,
                n_observations INTEGER,
                avg_return_present REAL,
                avg_return_absent REAL,
                UNIQUE(signal_name, fit_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_tracker_current (
                signal_name TEXT NOT NULL PRIMARY KEY,
                ic_90d REAL,
                weight REAL,
                n_observations INTEGER,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

    def save_to_db(self):
        from datetime import date as date_cls
        fit_date = date_cls.today().isoformat()
        # conn via get_session()
        for name in SIGNALS:
            ic = self._ic_values.get(name, 0)
            weight = self._weights.get(name, 0)
            n_obs = self._obs_counts.get(name, 0)

            conn.execute("""
                INSERT OR REPLACE INTO signal_ic_tracker
                (signal_name, fit_date, ic_90d, weight, n_observations)
                VALUES (?, ?, ?, ?, ?)
            """, (name, fit_date, ic, weight, n_obs))

            conn.execute("""
                INSERT OR REPLACE INTO signal_tracker_current
                (signal_name, ic_90d, weight, n_observations)
                VALUES (?, ?, ?, ?)
            """, (name, ic, weight, n_obs))
        logger.info("SignalTracker: saved %d signal weights to DB", len(SIGNALS))

    def load_from_db(self) -> bool:
        # conn via get_session()
        try:
            rows = conn.execute(
                "SELECT signal_name, ic_90d, weight, n_observations "
                "FROM signal_tracker_current"
            ).fetchall()
        except Exception:
            return False

        if not rows:
            return False

        for name, ic, weight, n_obs in rows:
            self._weights[name] = weight or 0
            self._ic_values[name] = ic or 0
            self._obs_counts[name] = n_obs or 0

        self._fitted = True
        self._fit_time = time.time()
        logger.info("SignalTracker: loaded from DB — weights=%s", self._weights)
        return True

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'weights': dict(self._weights),
            'ic_values': dict(self._ic_values),
            'n_observations': dict(self._obs_counts),
        }


def _date_sub(date_str, days):
    """Subtract days from a date string (YYYY-MM-DD)."""
    from datetime import datetime, timedelta
    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
    return (dt - timedelta(days=days)).strftime('%Y-%m-%d')
