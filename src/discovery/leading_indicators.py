"""
Leading Indicator Engine — detects signals that PRECEDE market moves.
Computes probability-based signals from historical patterns.
Part of Discovery AI v6.0.
"""
import sqlite3
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class LeadingIndicatorEngine:
    """Compute leading indicator signals from historical patterns."""

    def __init__(self):
        self._cache = {}
        self._cache_date = None
        self._historical_patterns = None

    def fit(self) -> bool:
        """Precompute historical patterns for all indicators."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            macro = conn.execute("""
                SELECT date, vix_close, vix3m_close, spy_close, crude_close
                FROM macro_snapshots
                WHERE vix_close IS NOT NULL AND spy_close IS NOT NULL
                ORDER BY date
            """).fetchall()

            breadth = conn.execute("""
                SELECT date, pct_above_20d_ma
                FROM market_breadth
                WHERE pct_above_20d_ma IS NOT NULL
                ORDER BY date
            """).fetchall()
        finally:
            conn.close()

        if len(macro) < 100:
            return False

        self._macro = {r[0]: {'vix': r[1], 'vix3m': r[2], 'spy': r[3], 'crude': r[4]} for r in macro}
        self._macro_dates = [r[0] for r in macro]
        self._breadth = {r[0]: r[1] for r in breadth}

        # Precompute: VIX mean reversion stats
        vix_spikes = []
        for i in range(len(macro)):
            if macro[i][1] and macro[i][1] > 30:
                # Look ahead 5 days: did VIX drop below 25?
                future = [macro[j][1] for j in range(i + 1, min(i + 6, len(macro))) if macro[j][1]]
                if future:
                    reverted = any(v < 25 for v in future)
                    vix_spikes.append(reverted)
        self._vix_reversion_rate = np.mean(vix_spikes) if vix_spikes else 0.5

        # Precompute: breadth recovery stats
        breadth_dips = []
        breadth_dates = [r[0] for r in breadth]
        breadth_vals = [r[1] for r in breadth]
        for i in range(len(breadth_vals)):
            if breadth_vals[i] < 30:
                future = breadth_vals[i + 1:i + 8]
                if future:
                    recovered = any(v > 40 for v in future)
                    breadth_dips.append(recovered)
        self._breadth_recovery_rate = np.mean(breadth_dips) if breadth_dips else 0.5

        # Precompute: consecutive red bounce stats
        spy_vals = [r[3] for r in macro if r[3]]
        red_bounces = []
        for i in range(3, len(spy_vals) - 1):
            if spy_vals[i] < spy_vals[i - 1] < spy_vals[i - 2] < spy_vals[i - 3]:
                # 3+ consecutive red
                bounced = spy_vals[i + 1] > spy_vals[i] if i + 1 < len(spy_vals) else False
                red_bounces.append(bounced)
        self._red_bounce_rate = np.mean(red_bounces) if red_bounces else 0.5

        self._historical_patterns = True
        logger.info(
            "LeadingIndicators: fitted — vix_reversion=%.0f%% breadth_recovery=%.0f%% red_bounce=%.0f%%",
            self._vix_reversion_rate * 100, self._breadth_recovery_rate * 100,
            self._red_bounce_rate * 100,
        )
        return True

    def compute_signals(self, scan_date: str) -> dict:
        """Compute all leading indicator signals for a date."""
        if self._cache_date == scan_date and self._cache:
            return self._cache

        if not self._historical_patterns:
            if not self.fit():
                return {}

        signals = {}
        m = self._macro.get(scan_date, {})
        b = self._breadth.get(scan_date, 50)

        vix = m.get('vix', 20)
        vix3m = m.get('vix3m')
        spy = m.get('spy', 500)

        # 1. VIX mean reversion
        signals['vix_mean_reversion'] = {
            'active': vix > 30,
            'probability': round(self._vix_reversion_rate * 100, 0) if vix > 30 else 0,
            'description': f'VIX={vix:.0f}>30 → {self._vix_reversion_rate:.0%} chance < 25 in 5d' if vix > 30 else 'VIX normal',
            'signal': 'bullish' if vix > 30 and self._vix_reversion_rate > 0.6 else 'neutral',
        }

        # 2. Breadth recovery
        signals['breadth_recovery'] = {
            'active': b < 30,
            'probability': round(self._breadth_recovery_rate * 100, 0) if b < 30 else 0,
            'description': f'Breadth={b:.0f}<30 → {self._breadth_recovery_rate:.0%} chance > 40 in 7d' if b < 30 else 'Breadth normal',
            'signal': 'bullish' if b < 30 and self._breadth_recovery_rate > 0.5 else 'neutral',
        }

        # 3. VIX term structure
        if vix and vix3m and vix3m > 0:
            spread = vix - vix3m
            if spread > 0:
                signals['vix_term_structure'] = {
                    'active': True,
                    'spread': round(spread, 2),
                    'description': f'Backwardation (VIX>{vix3m:.0f}={spread:+.1f}) → DANGER',
                    'signal': 'bearish',
                }
            else:
                signals['vix_term_structure'] = {
                    'active': False,
                    'spread': round(spread, 2),
                    'description': f'Contango (normal, spread={spread:.1f})',
                    'signal': 'neutral',
                }
        else:
            signals['vix_term_structure'] = {'active': False, 'spread': 0, 'description': 'No VIX3M data', 'signal': 'neutral'}

        # 4. Consecutive red bounce
        # Check recent SPY trajectory
        idx = self._macro_dates.index(scan_date) if scan_date in self._macro_dates else -1
        consecutive_red = 0
        if idx > 3:
            for j in range(idx, max(idx - 5, 0), -1):
                prev_date = self._macro_dates[j - 1] if j > 0 else None
                curr_spy = self._macro.get(self._macro_dates[j], {}).get('spy', 0)
                prev_spy = self._macro.get(prev_date, {}).get('spy', 0) if prev_date else 0
                if curr_spy < prev_spy and prev_spy > 0:
                    consecutive_red += 1
                else:
                    break

        signals['consecutive_red_bounce'] = {
            'active': consecutive_red >= 3,
            'consecutive_red': consecutive_red,
            'probability': round(self._red_bounce_rate * 100, 0) if consecutive_red >= 3 else 0,
            'description': f'{consecutive_red} red days → {self._red_bounce_rate:.0%} bounce D+1' if consecutive_red >= 3 else f'{consecutive_red} red days (< 3)',
            'signal': 'bullish' if consecutive_red >= 3 and self._red_bounce_rate > 0.55 else 'neutral',
        }

        # 5. Put/call extreme — contrarian bounce signal
        try:
            conn = sqlite3.connect(str(DB_PATH))
            pc_rows = conn.execute("""
                SELECT AVG(put_call_ratio) FROM options_flow
                WHERE date <= ? AND date >= date(?, '-5 days')
                AND put_call_ratio IS NOT NULL
            """, (scan_date, scan_date)).fetchone()
            conn.close()
            avg_pc = pc_rows[0] if pc_rows and pc_rows[0] else None
            if avg_pc and avg_pc > 1.5:
                signals['put_call_extreme'] = {
                    'active': True, 'ratio': round(avg_pc, 2),
                    'description': f'P/C ratio={avg_pc:.2f}>1.5 → contrarian bullish',
                    'signal': 'bullish',
                }
            else:
                signals['put_call_extreme'] = {
                    'active': False, 'ratio': round(avg_pc, 2) if avg_pc else 0,
                    'description': f'P/C ratio={avg_pc:.2f}' if avg_pc else 'No P/C data',
                    'signal': 'neutral',
                }
        except Exception as e:
            signals['put_call_extreme'] = {'active': False, 'ratio': 0, 'description': f'Error: {e}', 'signal': 'neutral'}

        # 6. Insider surge — 3+ insider buys this week = bullish
        try:
            conn = sqlite3.connect(str(DB_PATH))
            insider_rows = conn.execute("""
                SELECT COUNT(*) FROM insider_transactions
                WHERE transaction_type = 'P' AND transaction_date >= date(?, '-7 days')
                AND transaction_date <= ?
            """, (scan_date, scan_date)).fetchone()
            conn.close()
            n_buys = insider_rows[0] if insider_rows else 0
            signals['insider_surge'] = {
                'active': n_buys >= 3,
                'count': n_buys,
                'description': f'{n_buys} insider buys this week' + (' → bullish' if n_buys >= 3 else ''),
                'signal': 'bullish' if n_buys >= 3 else 'neutral',
            }
        except Exception as e:
            signals['insider_surge'] = {'active': False, 'count': 0, 'description': f'Error: {e}', 'signal': 'neutral'}

        # 7. Earnings cluster — count of stocks with earnings soon (volatility warning)
        try:
            conn = sqlite3.connect(str(DB_PATH))
            # Use discovery_picks if they have days_to_earnings
            ear_rows = conn.execute("""
                SELECT COUNT(*) FROM discovery_picks
                WHERE scan_date = ? AND days_to_earnings IS NOT NULL AND days_to_earnings BETWEEN 0 AND 5
            """, (scan_date,)).fetchone()
            conn.close()
            n_earnings = ear_rows[0] if ear_rows else 0
            signals['earnings_cluster'] = {
                'active': n_earnings >= 3,
                'count': n_earnings,
                'description': f'{n_earnings} picks with earnings in 5d' + (' → HIGH VOL' if n_earnings >= 3 else ''),
                'signal': 'bearish' if n_earnings >= 3 else 'neutral',
            }
        except Exception as e:
            signals['earnings_cluster'] = {'active': False, 'count': 0, 'description': f'Error: {e}', 'signal': 'neutral'}

        # 8. Regime forecast (simple: trend-based)
        bullish_signals = sum(1 for s in signals.values() if isinstance(s, dict) and s.get('signal') == 'bullish')
        bearish_signals = sum(1 for s in signals.values() if isinstance(s, dict) and s.get('signal') == 'bearish')
        if bullish_signals >= 2:
            regime_forecast = 'IMPROVING'
        elif bearish_signals >= 2:
            regime_forecast = 'DETERIORATING'
        else:
            regime_forecast = 'STABLE'

        signals['regime_forecast'] = {
            'forecast': regime_forecast,
            'bullish_count': bullish_signals,
            'bearish_count': bearish_signals,
            'description': f'{regime_forecast} ({bullish_signals} bullish, {bearish_signals} bearish signals)',
        }

        self._cache = signals
        self._cache_date = scan_date

        logger.info(
            "LeadingIndicators: date=%s forecast=%s vix_revert=%s breadth_recov=%s red_bounce=%s",
            scan_date, regime_forecast,
            signals['vix_mean_reversion']['signal'],
            signals['breadth_recovery']['signal'],
            signals['consecutive_red_bounce']['signal'],
        )
        return signals
