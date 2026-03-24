"""
Unified Filter — single pipeline for all Discovery candidate filters.
Part of Discovery v13.1 Clean Architecture.

Pipeline order:
  1. Regime bonus gate (STRESS/CRISIS entry requirements)
  2. v16 Smart boost (insider buy + analyst target — replaces negative E[R] skip)
  3. Elite filter (statistical outlier: mean + k*σ)
  4. UnifiedBrain re-rank (drop <40%)
  5. D0 close position (weak candle filter)
  6. ATR filter (with UBrain override for deep dips)
  7. Momentum filter (fake dip detection)
  8. Beta filter (v13.1: beta > 1.5 → skip, worst trades have beta 1.37 avg)
  9. PE filter (v13.1: PE > 35 → skip, worst trades have PE 36.6 avg)
  10. BTC leading signal (v14.0: BTC 3d momentum < threshold → informational)
  11. Weekend risk filter (v15.1: Friday only — skip if gap down risk)
  12. Context skip (high-risk stocks via KnowledgeGraph)
"""
import logging
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# All DIP-eligible sectors
ALL_SECTORS = frozenset({
    'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
    'Consumer Defensive', 'Industrials', 'Energy', 'Utilities',
    'Basic Materials', 'Real Estate', 'Communication Services',
})

# Sectors destroyed when crude spikes (IC < -0.25 with crude_5d_chg)
CRUDE_SENSITIVE = frozenset({
    'Technology', 'Communication Services', 'Consumer Cyclical', 'Healthcare',
})


class UnifiedFilter:
    """Single filter pipeline for Discovery picks."""

    def __init__(self, adaptive_params=None):
        self._adaptive = adaptive_params

    def apply(self, scored, macro, regime, strategy_mode, config,
              unified_brain=None, sensors=None, temporal_features=None,
              scan_date=None, context_scorer=None, regime_decision=None,
              weekend_risk=None):
        """Apply all filters in order.

        Args:
            scored: list of (score, candidate_dict) sorted by score desc
            macro: macro features dict
            regime: 'BULL', 'STRESS', or 'CRISIS'
            strategy_mode: e.g. 'CALM_PULLBACK', 'SELECTIVE', 'DIP_BOUNCE'
            config: discovery config dict
            unified_brain: UnifiedBrain instance (for re-rank + ATR override)
            sensors: SensorNetwork instance
            temporal_features: dict of temporal features
            scan_date: str date
            context_scorer: ContextScorer instance
            regime_decision: dict from RegimeBrain

        Returns:
            Filtered list of (score, candidate) tuples
        """
        n_input = len(scored)

        # Phase 1: Regime bonus gates
        filtered = self._regime_gate(scored, regime, strategy_mode, macro)
        if len(filtered) < n_input:
            logger.info("Filter: %d→%d after regime gate [%s]", n_input, len(filtered), regime)

        # Phase 2: v16 smart boost (replaces negative E[R] skip — IC=0 proven)
        # Insider buying + analyst target upgrades boost score instead of filtering
        filtered = self._apply_smart_boost(filtered, scan_date)

        # Phase 3: Elite filter (statistical outlier)
        filtered = self._elite_filter(filtered, regime, config)

        # Phase 4: UnifiedBrain re-rank
        if unified_brain and unified_brain._fitted and len(filtered) > 1:
            filtered = self._ubrain_rerank(
                filtered, unified_brain, sensors, macro,
                temporal_features, scan_date, regime_decision)

        # Phase 5-12: Per-stock filters
        # Phase 10: BTC leading (informational)
        btc_3d = macro.get('btc_momentum_3d')
        if btc_3d is not None and btc_3d < -3.0:
            logger.info("Filter: BTC 3d=%+.1f%% DANGER signal (informational)", btc_3d)

        # Phase 11: Weekend risk (Friday only)
        is_friday = datetime.now(ZoneInfo('America/New_York')).weekday() == 4
        weekend_skip = False
        if is_friday and weekend_risk:
            action = weekend_risk.get('weekend_action', 'NEUTRAL')
            wscore = weekend_risk.get('weekend_score', 0)
            if action == 'GAP_DOWN_RISK':
                logger.info("Filter: WEEKEND GAP DOWN RISK (score=%+.2f) — filtering picks", wscore)
                weekend_skip = True

        result = []
        for er, c in filtered:
            if not self._passes_d0_close(c, strategy_mode, regime):
                continue
            if not self._passes_atr(c, strategy_mode, regime, unified_brain,
                                     sensors, macro, temporal_features,
                                     scan_date, regime_decision):
                continue
            if not self._passes_momentum(c, strategy_mode, regime):
                continue
            if not self._passes_beta(c):
                continue
            if not self._passes_pe(c):
                continue
            if weekend_skip:
                continue  # Friday + gap down risk → skip all picks
            if context_scorer:
                try:
                    skip, reason = context_scorer.should_skip(c['symbol'], macro)
                    if skip:
                        logger.debug("Filter: SKIP %s — %s", c['symbol'], reason)
                        continue
                except Exception:
                    pass
            result.append((er, c))

        logger.info("Filter: %d→%d after per-stock filters", len(filtered), len(result))
        return result

    # --- Filter stages ---

    def _apply_smart_boost(self, scored, scan_date):
        """v16: Boost stocks with insider buying or analyst target upgrades.
        Replaces negative E[R] skip (which killed good stocks — IC=0 proven).
        Insider+dip WR=61.5%, analyst target up >5% WR=55.4%."""
        if not scan_date:
            return scored
        try:
            import sqlite3
            from pathlib import Path
            db = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'
            conn = sqlite3.connect(str(db), timeout=5)
            conn.execute('PRAGMA busy_timeout=5000')

            # Insider open-market purchases in last 90 days (value > $10K)
            insider_syms = set()
            try:
                for r in conn.execute("""
                    SELECT DISTINCT symbol FROM insider_transactions_history
                    WHERE trade_date >= date(?, '-90 days') AND trade_date <= ?
                    AND (transaction_type LIKE '%Purchase%'
                         OR transaction_type LIKE '%Buy%')
                    AND value > 10000
                """, (scan_date, scan_date)):
                    insider_syms.add(r[0])
            except Exception:
                pass  # table may not exist yet

            # Analyst target changes in last 90 days
            analyst_up = set()
            analyst_down = set()
            try:
                for r in conn.execute("""
                    SELECT symbol,
                           AVG((price_target / prior_price_target - 1) * 100) as chg
                    FROM analyst_ratings_history
                    WHERE date >= date(?, '-90 days') AND date <= ?
                    AND price_target > 0 AND prior_price_target > 0
                    GROUP BY symbol
                """, (scan_date, scan_date)):
                    if r[1] and r[1] > 5:
                        analyst_up.add(r[0])
                    elif r[1] and r[1] < -5:
                        analyst_down.add(r[0])
            except Exception:
                pass  # table may not exist yet

            conn.close()

            boosted = []
            n_insider = 0
            n_analyst = 0
            for er, c in scored:
                sym = c.get('symbol', '')
                boost = 0
                if sym in insider_syms:
                    boost += 0.5
                    c['insider_bought'] = True
                    n_insider += 1
                if sym in analyst_up:
                    boost += 0.3
                    c['analyst_upgrade'] = True
                    n_analyst += 1
                if sym in analyst_down:
                    boost -= 0.3
                boosted.append((er + boost, c))

            if n_insider or n_analyst:
                logger.info("Filter v16: smart boost — %d insider, %d analyst_up",
                            n_insider, n_analyst)

            return boosted

        except Exception as e:
            logger.debug("Filter v16: smart boost error: %s", e)
            return scored

    def _regime_gate(self, scored, regime, strategy_mode, macro):
        """STRESS/CRISIS bonus gate — require defensive characteristics."""
        if strategy_mode.startswith('CALM') or strategy_mode == 'SELECTIVE':
            return scored

        crisis_sectors = get_crisis_sectors(macro)
        stress_sectors = get_stress_sectors(macro)

        result = []
        for er, c in scored:
            if regime == 'STRESS':
                atr = c.get('atr_pct') or 99
                mom5 = c.get('momentum_5d') or 0
                sector = c.get('sector') or ''
                bonus = 0
                if atr < 3.0:
                    bonus += 2
                elif atr < 4.0:
                    bonus += 1
                if mom5 < 0:
                    bonus += 1
                if sector in stress_sectors:
                    bonus += 2
                if bonus < 2:
                    continue

            elif regime == 'CRISIS':
                atr = c.get('atr_pct') or 99
                mom5 = c.get('momentum_5d') or 0
                vol = c.get('volume_ratio') or 0
                sector = c.get('sector') or ''
                if mom5 >= 0:
                    continue
                bonus = 0
                if mom5 < -5:
                    bonus += 2
                if vol > 1.0:
                    bonus += 1
                if atr < 3.0:
                    bonus += 1
                if sector in crisis_sectors:
                    bonus += 2
                if bonus < 2:
                    continue

            result.append((er, c))
        return result

    def _elite_filter(self, scored, regime, config):
        """Keep only statistical outliers (mean + k*σ)."""
        if self._adaptive:
            # Use first candidate's sector for sector-aware sigma,
            # fallback chain in adaptive handles unknown sectors
            sector = scored[0][1].get('sector', '') if scored else ''
            elite_k = self._adaptive.get(sector, regime, 'elite_sigma')
        else:
            regime_cfg = config.get('v3', {}).get('regimes', {})
            elite_k = regime_cfg.get('elite_sigma', 1.5)
        pre = len(scored)

        if len(scored) >= 3:
            ers = np.array([e for e, _ in scored])
            elite_threshold = ers.mean() + elite_k * ers.std()
            elite = [(e, c) for e, c in scored if e >= elite_threshold]
            scored = elite if elite else scored[:1]

        logger.info("Filter: %d→%d elite [%s] (mean+%.1fσ)", pre, len(scored), regime, elite_k)
        return scored

    def _ubrain_rerank(self, scored, unified_brain, sensors, macro,
                        temporal_features, scan_date, regime_decision):
        """Drop picks where UnifiedBrain says <40%, re-rank by blend."""
        re_ranked = []
        for er, c in scored:
            sensor_sigs = sensors.compute_all(
                c['symbol'], scan_date, macro, c, temporal_features or {})
            rp = (regime_decision or {}).get('probability', 0.5)
            ub_result = unified_brain.predict(c, sensor_sigs, rp)
            ub_prob = ub_result.get('probability', 0.5)

            if ub_prob < 0.40:
                logger.debug("Filter: DROP %s — UnifiedBrain=%.0f%%",
                             c['symbol'], ub_prob * 100)
                continue

            # Re-rank: kernel E[R] (70%) + UnifiedBrain (30%)
            blended = er * 0.7 + (ub_prob - 0.5) * 10 * 0.3
            re_ranked.append((blended, c))

        if re_ranked:
            re_ranked.sort(key=lambda x: x[0], reverse=True)
            return re_ranked
        return scored  # fallback: don't drop everything

    def _passes_d0_close(self, c, strategy_mode, regime='BULL'):
        """D0 close position filter — remove weak candles (close near low)."""
        d0_high = c.get('day_high') or c.get('high') or c['close']
        d0_low = c.get('day_low') or c.get('low') or c['close']
        d0_range = d0_high - d0_low
        price = c['close']

        if d0_range > 0:
            d0_close_pos = (price - d0_low) / d0_range
        else:
            d0_close_pos = 0.5

        c['d0_close_position'] = round(d0_close_pos, 2)

        if self._adaptive:
            sector = c.get('sector', '')
            d0_min = self._adaptive.get(sector, regime, 'd0_close_min')
        else:
            d0_min = 0.2 if strategy_mode.startswith('CALM') else 0.3
        return d0_close_pos >= d0_min

    def _passes_atr(self, c, strategy_mode, regime, unified_brain=None,
                     sensors=None, macro=None, temporal_features=None,
                     scan_date=None, regime_decision=None):
        """ATR filter — adaptive per sector, with UBrain override for deep dips."""
        atr = c.get('atr_pct') or 0
        d20h_val = c.get('distance_from_20d_high') or 0
        is_friday = datetime.now(ZoneInfo('America/New_York')).weekday() == 4

        # UBrain override for deep dips (d20h < -15)
        ub_override = False
        if unified_brain and unified_brain._fitted and d20h_val < -15:
            try:
                sensor_sigs = sensors.compute_all(
                    c['symbol'], scan_date, macro, c,
                    temporal_features or {}) if sensors else {}
                rp = (regime_decision or {}).get('probability', 0.5)
                ub_quick = unified_brain.predict(c, sensor_sigs, rp)
                if ub_quick.get('probability', 0) > 0.50:
                    ub_override = True
            except Exception:
                pass

        # Adaptive ATR threshold per sector
        if self._adaptive:
            sector = c.get('sector', '')
            atr_max = self._adaptive.get(sector, regime, 'atr_max')
        else:
            # Legacy hardcoded thresholds
            if strategy_mode.startswith('CALM'):
                atr_max = 5.0
            elif strategy_mode in ('DIP_BOUNCE', 'WASHOUT'):
                atr_max = 8.0 if is_friday or d20h_val < -15 else 5.0
            else:
                atr_max = 5.0

        if atr > atr_max and not ub_override:
            return False

        c['_weekend_only'] = atr > 5.0 and not (d20h_val < -15)
        return True

    def _passes_momentum(self, c, strategy_mode, regime='BULL'):
        """Momentum filter — adaptive per sector."""
        mom_val = c.get('momentum_5d') or 0
        d20h_val = c.get('distance_from_20d_high') or 0

        if self._adaptive:
            sector = c.get('sector', '')
            mom_cut = self._adaptive.get(sector, regime, 'mom_cut')
            if mom_val > mom_cut:
                return False
        else:
            if strategy_mode in ('DIP_BOUNCE', 'WASHOUT') and mom_val > 3:
                return False
            if strategy_mode == 'SELECTIVE' and mom_val > 2:
                return False
            if mom_val > 0 and d20h_val > -8:
                return False

        # Hammer candle detection (set attributes for later use)
        d0_high = c.get('day_high') or c.get('high') or c['close']
        d0_low = c.get('day_low') or c.get('low') or c['close']
        price = c['close']
        d0_range = d0_high - d0_low
        d0_lower_shadow = (
            (min(price, c.get('open', price)) - d0_low) / d0_range
        ) if d0_range > 0 else 0
        c['d0_hammer'] = d0_lower_shadow > 0.5
        c['d0_lower_shadow'] = round(d0_lower_shadow, 2)

        return True

    def _passes_btc_leading(self, macro):
        """v14.0 BTC 3-day leading signal.
        Data: worst trades have BTC 3d avg = -0.21% vs normal +0.95% (diff -1.16%).
        BTC trades 24/7, reacts to risk-off BEFORE equities.
        """
        btc_3d = macro.get('btc_momentum_3d')
        if btc_3d is None:
            return True
        if btc_3d < -3.0:
            logger.info("Filter: BTC 3d momentum = %+.1f%% < -3%% → DANGER", btc_3d)
            return False
        return True

    def _passes_beta(self, c):
        """v13.1 Beta filter — high-beta stocks are overrepresented in worst trades.
        Data: worst 5% avg beta=1.37 vs best 20% avg beta=1.16.
        Walk-forward: worst month -$1,594 → -$1,195 with beta≤1.5.
        """
        beta = c.get('beta')
        if beta is None:
            return True  # no data = allow
        return beta <= 1.5

    def _passes_pe(self, c):
        """v13.1 PE filter — overvalued stocks are overrepresented in worst trades.
        Data: worst 5% avg PE=36.6 vs best 20% avg PE=22.0.
        Walk-forward: worst month -$1,195 → -$1,039 with PE≤35.
        """
        pe = c.get('pe_forward')
        if pe is None or pe <= 0:
            return True  # no data or negative PE (profitable) = allow
        return pe <= 35


# --- Module-level sector selection functions ---

def get_crisis_sectors(macro):
    """Dynamic sector selection for CRISIS regime based on crude_5d_chg.

    Uses crude_5d_chg (IC=-0.209) and vix_term_spread to classify crisis type.
    """
    crude_5d = macro.get('crude_delta_5d_pct') or 0
    vix_spread = macro.get('vix_term_spread') or 0

    if crude_5d > 5:
        return frozenset({'Basic Materials', 'Utilities'})
    if crude_5d > 3:
        return ALL_SECTORS - CRUDE_SENSITIVE
    if vix_spread > 2 and crude_5d <= 0:
        return ALL_SECTORS
    if crude_5d <= 0:
        return ALL_SECTORS
    return ALL_SECTORS - frozenset({'Communication Services'})


def get_stress_sectors(macro):
    """Dynamic sector selection for STRESS regime."""
    crude_5d = macro.get('crude_delta_5d_pct') or 0
    if crude_5d > 5:
        return ALL_SECTORS - CRUDE_SENSITIVE
    return ALL_SECTORS
