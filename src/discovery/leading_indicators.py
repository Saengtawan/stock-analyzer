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

    def compute_stock_signals(self, symbol: str, scan_date: str) -> dict:
        """Compute per-stock leading signals. Returns score 0-100 and details."""
        score = 50.0  # neutral baseline
        details = {}

        conn = sqlite3.connect(str(DB_PATH))
        try:
            # 1. Options flow: stock's P/C ratio vs normal
            row = conn.execute("""
                SELECT put_call_ratio, unusual_call, unusual_put
                FROM options_flow
                WHERE symbol = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
            """, (symbol, scan_date)).fetchone()
            if row and row[0] is not None:
                pc = row[0]
                unusual_call = row[1] or 0
                unusual_put = row[2] or 0
                # High P/C = fear → contrarian bullish for dip picks
                if pc > 1.5:
                    score += 8
                    details['options'] = {'signal': 'bullish', 'pc_ratio': round(pc, 2), 'desc': f'P/C={pc:.1f} extreme fear'}
                elif pc < 0.5:
                    score -= 5
                    details['options'] = {'signal': 'bearish', 'pc_ratio': round(pc, 2), 'desc': f'P/C={pc:.1f} complacent'}
                else:
                    details['options'] = {'signal': 'neutral', 'pc_ratio': round(pc, 2), 'desc': f'P/C={pc:.1f}'}
                # Unusual activity bonus
                if unusual_call:
                    score += 5
                    details['options']['unusual'] = 'call_sweep'
                elif unusual_put:
                    score -= 3
                    details['options']['unusual'] = 'put_sweep'
            else:
                details['options'] = {'signal': 'neutral', 'pc_ratio': 0, 'desc': 'No data'}

            # 2. Insider transactions: recent buys for this stock
            ins_row = conn.execute("""
                SELECT COUNT(*) as n_buys, COALESCE(SUM(total_value), 0) as total_val
                FROM insider_transactions
                WHERE symbol = ? AND transaction_type = 'P'
                AND transaction_date >= date(?, '-30 days') AND transaction_date <= ?
            """, (symbol, scan_date, scan_date)).fetchone()
            n_buys = ins_row[0] if ins_row else 0
            buy_val = ins_row[1] if ins_row else 0
            if n_buys >= 2 or buy_val > 500000:
                score += 10
                details['insider'] = {'signal': 'bullish', 'buys_30d': n_buys, 'value': round(buy_val),
                                      'desc': f'{n_buys} insider buys ${buy_val/1000:.0f}K'}
            elif n_buys >= 1:
                score += 4
                details['insider'] = {'signal': 'mildly_bullish', 'buys_30d': n_buys, 'value': round(buy_val),
                                      'desc': f'{n_buys} insider buy'}
            else:
                # Check for insider selling
                sell_row = conn.execute("""
                    SELECT COUNT(*) FROM insider_transactions
                    WHERE symbol = ? AND transaction_type = 'S'
                    AND transaction_date >= date(?, '-14 days') AND transaction_date <= ?
                """, (symbol, scan_date, scan_date)).fetchone()
                n_sells = sell_row[0] if sell_row else 0
                if n_sells >= 3:
                    score -= 8
                    details['insider'] = {'signal': 'bearish', 'sells_14d': n_sells, 'desc': f'{n_sells} insider sells'}
                else:
                    details['insider'] = {'signal': 'neutral', 'buys_30d': 0, 'desc': 'No recent'}

            # 3. Short interest: squeeze potential
            si_row = conn.execute("""
                SELECT short_pct_float, short_ratio, short_change_pct
                FROM short_interest
                WHERE symbol = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
            """, (symbol, scan_date)).fetchone()
            if si_row and si_row[0] is not None:
                si_pct = si_row[0]
                si_ratio = si_row[1] or 0
                si_change = si_row[2] or 0
                if si_pct > 15 and si_change < 0:
                    # High SI + shorts covering = squeeze potential
                    score += 10
                    details['short'] = {'signal': 'bullish', 'si_pct': round(si_pct, 1),
                                        'desc': f'SI={si_pct:.0f}% covering → squeeze'}
                elif si_pct > 20:
                    score += 5  # high SI = contrarian
                    details['short'] = {'signal': 'mildly_bullish', 'si_pct': round(si_pct, 1),
                                        'desc': f'SI={si_pct:.0f}% high'}
                elif si_pct > 10 and si_change > 20:
                    score -= 5  # SI rising fast
                    details['short'] = {'signal': 'bearish', 'si_pct': round(si_pct, 1),
                                        'desc': f'SI={si_pct:.0f}% rising +{si_change:.0f}%'}
                else:
                    details['short'] = {'signal': 'neutral', 'si_pct': round(si_pct, 1), 'desc': f'SI={si_pct:.0f}%'}
            else:
                details['short'] = {'signal': 'neutral', 'si_pct': 0, 'desc': 'No data'}

            # 4. Analyst consensus: upside vs market
            ana_row = conn.execute("""
                SELECT upside_pct, bull_score, total_analysts
                FROM analyst_consensus
                WHERE symbol = ?
                ORDER BY updated_at DESC LIMIT 1
            """, (symbol,)).fetchone()
            if ana_row and ana_row[0] is not None:
                upside = ana_row[0]
                bull = ana_row[1] or 0  # 0-2 scale (avg 0.70)
                n_analysts = ana_row[2] or 0
                if upside > 30 and bull > 0.8:
                    score += 8
                    details['analyst'] = {'signal': 'bullish', 'upside': round(upside, 1), 'bull_score': round(bull, 2),
                                          'desc': f'Upside +{upside:.0f}% bull={bull:.2f}'}
                elif upside > 15 and bull > 0.6:
                    score += 6
                    details['analyst'] = {'signal': 'mildly_bullish', 'upside': round(upside, 1), 'bull_score': round(bull, 2),
                                          'desc': f'Upside +{upside:.0f}% bull={bull:.2f}'}
                elif upside > 15:
                    score += 3
                    details['analyst'] = {'signal': 'mildly_bullish', 'upside': round(upside, 1),
                                          'desc': f'Upside +{upside:.0f}% (low conviction)'}
                elif upside < -5:
                    score -= 8
                    details['analyst'] = {'signal': 'bearish', 'upside': round(upside, 1),
                                          'desc': f'Downside {upside:.0f}%'}
                else:
                    details['analyst'] = {'signal': 'neutral', 'upside': round(upside, 1),
                                          'desc': f'Upside +{upside:.0f}%'}
            else:
                details['analyst'] = {'signal': 'neutral', 'upside': 0, 'desc': 'No data'}

        except Exception as e:
            logger.error("LeadingIndicators stock signals error for %s: %s", symbol, e)
        finally:
            conn.close()

        score = max(0, min(100, score))
        return {'score': round(score, 1), 'details': details}
