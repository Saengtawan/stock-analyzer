"""
Adaptive Parameter Learner — learns optimal parameters per (sector × regime).
Part of Discovery v13.1.

Replaces 7 hardcoded values with 231 learned values (7 params × 33 groups).
Each (sector, regime) group learns its own optimal:
  sl_pct, tp_pct, atr_max, mom_cut, d0_close_min, elite_sigma

Walk-forward safe: fit(max_date) only uses data up to max_date.
Auto-refits every 30 days via AutoRefitOrchestrator.
"""
import logging
from database.orm.base import get_session
from sqlalchemy import text
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

SECTORS = [
    'Technology', 'Healthcare', 'Financial Services',
    'Consumer Cyclical', 'Consumer Defensive', 'Industrials',
    'Energy', 'Utilities', 'Basic Materials', 'Real Estate',
    'Communication Services',
]
REGIMES = ['BULL', 'STRESS', 'CRISIS']

PARAM_GRID = {
    'sl_pct':       [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0],
    'tp_pct':       [2.0, 3.0, 4.0, 5.0],
    'atr_max':      [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0],
    'mom_cut':      [-3, -2, -1, 0, 1, 2, 3, 4, 5],
    'd0_close_min': [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40],
    'elite_sigma':  [0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0],
    # v17: beta/PE per sector×regime (used by filter._passes_beta/pe)
    'beta_max':     [0.8, 1.0, 1.2, 1.5, 2.0, 2.5],
    'pe_max':       [15, 20, 25, 30, 35, 50],
    # v17: TP multipliers per sector×regime (used by sizer D0-D3 schedule)
    'tp_d0_mult':   [0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    'tp_d2_mult':   [0.7, 0.85, 1.0, 1.2],
    'tp_d3_mult':   [0.85, 1.0, 1.09, 1.2, 1.5],
    # v17: VIX regime boundaries (used by strategy_router)
    'vix_calm':     [15, 16, 17, 18, 19, 20],
    'vix_fear':     [22, 24, 25, 26, 28, 30],
    # v17: quality filters (used by multi_strategy._filter_quality)
    'min_mcap_b':   [5, 10, 20, 30, 50],
    'max_vol_ratio':[1.5, 2.0, 2.5, 3.0, 4.0],
    # v17: N sectors to block (used by sector_scorer)
    'n_blocked':    [1, 2, 3, 4],
    # v17: UBrain cutoff (used by filter._ubrain_rerank)
    'ubrain_cutoff': [0.30, 0.35, 0.40, 0.45, 0.50],
    # v17: speculative skip threshold (used by context_scorer.should_skip)
    'spec_skip': [-0.9, -0.7, -0.5, -0.3],
    # v17: ranking weights (used by engine._rank_by_context_sharpe)
    'rank_w_strat': [1, 2, 3, 5, 7, 10],
    'rank_w_sect': [0, 1, 2, 3, 5, 7],
    # v17: classify_regime boundaries (used by AdaptiveParams group key + strat_sharpe)
    'regime_vix_bull': [15, 17, 18, 20, 22],
    'regime_vix_crisis': [25, 26, 28, 30, 32],
    'regime_breadth_bull': [40, 45, 50, 55, 60],
    'regime_breadth_crisis': [20, 25, 30, 35],
    # v17: classify_strategy boundaries
    'strat_mom_oversold': [-8, -7, -5, -3],
    'strat_d20h_oversold': [-15, -12, -10, -8, -5],
    'strat_mom_dip_max': [-3, -2, -1, 0],
    'strat_vol_low': [0.3, 0.4, 0.5, 0.6],
    'strat_vol_high': [1.5, 2.0, 2.5, 3.0],
    'strat_pe_value': [10, 12, 15, 20],
    # v17: detect_condition boundaries
    'cond_vix_bull': [15, 16, 18, 20],
    'cond_breadth_bull': [45, 50, 55, 60],
    'cond_vix_stress': [22, 25, 28, 30],
    'cond_breadth_stress': [25, 30, 35, 40],
    # v17: score_batch regime boundaries
    'score_bull_er': [0.3, 0.5, 0.7, 1.0],
    'score_crisis_er': [-1.0, -0.5, -0.3, 0.0],
    # v17: gap filter threshold (used by engine._apply_gap_filter)
    'gap_filter_prob': [0.40, 0.45, 0.50, 0.55, 0.60],
    # v17: divergence boost breadth threshold (used by sizer)
    'div_breadth': [20, 25, 30, 35, 40],
    # v17: VVIX crisis threshold (used by neural_graph)
    'vvix_crisis': [100, 110, 120, 130, 140],
    # v17: washout breadth threshold (used by strategy_router)
    'washout_breadth': [10, 15, 20, 25, 30],
}

DEFAULTS = {
    'sl_pct': 3.0,
    'tp_pct': 6.0,
    'atr_max': 5.0,
    'mom_cut': 3.0,
    'd0_close_min': 0.30,
    'elite_sigma': 0.8,
    'beta_max': 1.5,
    'pe_max': 35,
    'tp_d0_mult': 0.55,
    'tp_d2_mult': 0.85,
    'tp_d3_mult': 1.09,
    'vix_calm': 18,
    'vix_fear': 25,
    'min_mcap_b': 30,
    'max_vol_ratio': 3.0,
    'n_blocked': 3,
    'ubrain_cutoff': 0.40,
    'spec_skip': -0.7,
    'rank_w_strat': 5,
    'rank_w_sect': 3,
    'regime_vix_bull': 20,
    'regime_vix_crisis': 28,
    'regime_breadth_bull': 50,
    'regime_breadth_crisis': 25,
    'strat_mom_oversold': -5,
    'strat_d20h_oversold': -10,
    'strat_mom_dip_max': -1,
    'strat_vol_low': 0.5,
    'strat_vol_high': 2.0,
    'strat_pe_value': 15,
    'cond_vix_bull': 18,
    'cond_breadth_bull': 55,
    'cond_vix_stress': 25,
    'cond_breadth_stress': 35,
    'score_bull_er': 0.5,
    'score_crisis_er': -0.5,
    'gap_filter_prob': 0.50,
    'div_breadth': 30,
    'vvix_crisis': 120,
    'washout_breadth': 20,
}

MIN_GROUP_SIZE = 100
MAX_CHANGE_PCT = 30  # safety: max ±30% change per refit cycle


from discovery.multi_strategy import classify_regime as _classify_regime, classify_strategy as _classify_strategy


def _sim_trade_absolute(d1o, day_hl, d5c, sl_pct, tp_pct):
    """v15.1: Simulate trade with absolute SL/TP %. Walk D1-D5."""
    for h, l in day_hl:
        if (l / d1o - 1) * 100 <= -sl_pct:
            return -sl_pct
        if (h / d1o - 1) * 100 >= tp_pct:
            return tp_pct
    return (d5c / d1o - 1) * 100 if d5c and d5c > 0 else 0


class AdaptiveParameterLearner:
    """Learn optimal parameters per (sector × regime) from historical data."""

    def __init__(self):
        self._params = {}       # {(sector, regime): {param: value}}
        self._fitted = False
        self._fit_date = None
        self._fit_time = 0.0
        self._fit_stats = {}
        self._ensure_tables()

    def fit(self, max_date: str = None) -> bool:
        """Learn optimal parameters from historical data.

        Args:
            max_date: only use data up to this date (walk-forward).
                      None = use all available data.
        """
        t0 = time.time()
        data = self._load_data(max_date)
        if not data:
            logger.warning("AdaptiveParams: no data loaded")
            return False

        # Classify into (sector, regime) groups
        groups = defaultdict(list)
        for row in data:
            sector = row['sector']
            regime = _classify_regime(row['vix'], row['breadth'])
            groups[(sector, regime)].append(row)

        old_params = dict(self._params)
        self._params = {}
        self._fit_stats = {}

        for sector in SECTORS:
            for regime in REGIMES:
                key = (sector, regime)
                sigs = groups.get(key, [])

                if len(sigs) < MIN_GROUP_SIZE:
                    self._params[key] = dict(DEFAULTS)
                    self._fit_stats[key] = {
                        'n': len(sigs), 'source': 'default',
                    }
                    continue

                learned = self._learn_group(sigs, key)
                # Safety guard: cap change at ±30%
                if key in old_params:
                    learned = self._apply_guard(learned, old_params[key])

                self._params[key] = learned
                self._fit_stats[key] = {
                    'n': len(sigs), 'source': 'learned',
                    'params': dict(learned),
                }

        self._fitted = True
        self._fit_date = max_date or 'all'
        self._fit_time = time.time()

        n_learned = sum(1 for s in self._fit_stats.values()
                        if s['source'] == 'learned')
        elapsed = time.time() - t0
        logger.info(
            "AdaptiveParams: fitted %d/%d groups in %.1fs (max_date=%s)",
            n_learned, len(SECTORS) * len(REGIMES), elapsed,
            max_date or 'all')

        self.save_to_db()
        return True

    def get(self, sector: str, regime: str, param: str) -> float:
        """Get learned parameter with fallback chain.

        1. Exact match (sector, regime)
        2. Sector-level median (across regimes)
        3. Regime-level median (across sectors)
        4. Global default
        """
        key = (sector, regime)
        if key in self._params and param in self._params[key]:
            return self._params[key][param]

        # Sector-level fallback
        vals = [self._params[k].get(param)
                for k in self._params if k[0] == sector
                and param in self._params.get(k, {})]
        vals = [v for v in vals if v is not None]
        if vals:
            return float(np.median(vals))

        # Regime-level fallback
        vals = [self._params[k].get(param)
                for k in self._params if k[1] == regime
                and param in self._params.get(k, {})]
        vals = [v for v in vals if v is not None]
        if vals:
            return float(np.median(vals))

        return DEFAULTS.get(param, 0)

    def needs_refit(self, days: int = 30) -> bool:
        if not self._fitted:
            return True
        return (time.time() - self._fit_time) > days * 86400

    # === Learning methods ===

    def _learn_group(self, sigs, key):
        """Learn all parameters for one (sector, regime) group."""
        params = {}

        # 1. sl_pct + tp_pct — absolute % grid search (best Sharpe)
        sl_pct, tp_pct = self._learn_sl_tp_absolute(sigs)
        params['sl_pct'] = sl_pct
        params['tp_pct'] = tp_pct

        # 2. atr_max — WR sweep
        params['atr_max'] = self._learn_threshold(
            sigs, 'atr', PARAM_GRID['atr_max'], mode='upper')

        # 3. mom_cut — WR sweep
        params['mom_cut'] = self._learn_threshold(
            sigs, 'mom', PARAM_GRID['mom_cut'], mode='upper')

        # 4. d0_close_min — WR sweep
        params['d0_close_min'] = self._learn_threshold(
            sigs, 'd0_pos', PARAM_GRID['d0_close_min'], mode='lower')

        # 5. elite_sigma — best E[R] per pick
        params['elite_sigma'] = self._learn_elite_sigma(sigs)

        # 6. v17: beta_max — WR sweep (per sector: Tech=1.5, RE=0.8 etc.)
        beta_sigs = [s for s in sigs if s.get('beta')]
        if len(beta_sigs) >= 50:
            params['beta_max'] = self._learn_threshold(
                beta_sigs, 'beta', PARAM_GRID['beta_max'], mode='upper')
        else:
            params['beta_max'] = DEFAULTS['beta_max']

        # 7. v17: pe_max — WR sweep (per sector: Tech PE=50 ok, Util PE=20 max)
        pe_sigs = [s for s in sigs if s.get('pe') is not None and s['pe'] > 0]
        if len(pe_sigs) >= 50:
            params['pe_max'] = self._learn_threshold(
                pe_sigs, 'pe', PARAM_GRID['pe_max'], mode='upper')
        else:
            params['pe_max'] = DEFAULTS['pe_max']

        # 8. v17: TP multipliers — grid search best D0/D2/D3 ATR mults (Sharpe)
        tp_d0, tp_d2, tp_d3 = self._learn_tp_multipliers(sigs)
        params['tp_d0_mult'] = tp_d0
        params['tp_d2_mult'] = tp_d2
        params['tp_d3_mult'] = tp_d3

        # 9. v17: VIX regime boundaries — grid search CALM/FEAR cutoffs (best overall Sharpe)
        params['vix_calm'], params['vix_fear'] = self._learn_vix_boundaries(sigs)

        # 10. v17: Quality filters — mcap + volume ratio
        params['min_mcap_b'] = self._learn_threshold(
            sigs, 'mcap_b', PARAM_GRID['min_mcap_b'], mode='lower')
        params['max_vol_ratio'] = self._learn_threshold(
            sigs, 'vol', PARAM_GRID['max_vol_ratio'], mode='upper')

        # 11. v17: N sectors to block
        params['n_blocked'] = self._learn_n_blocked(sigs)

        # 12. v17: UBrain cutoff — learn from ubrain_backfill if available
        params['ubrain_cutoff'] = self._learn_ubrain_cutoff(sigs)

        # 13. v17: speculative skip threshold — learn from stock_context outcomes
        params['spec_skip'] = self._learn_spec_skip(sigs)

        # 14. v17: ranking weights — optimal strategy vs sector weight
        params['rank_w_strat'], params['rank_w_sect'] = self._learn_ranking_weights(sigs)

        # 15. v17: divergence boost breadth — when is divergence signal useful?
        breadth_sigs = [s for s in sigs if s.get('breadth') is not None]
        if len(breadth_sigs) >= 100:
            # Find breadth threshold where divergence (mom up + breadth low) works best
            best_sh, best_b = -999, DEFAULTS['div_breadth']
            for b_cut in PARAM_GRID['div_breadth']:
                sub = [s['o5d'] for s in breadth_sigs if s['breadth'] < b_cut and s.get('mom', 0) > 0]
                if len(sub) < 30: continue
                sh = np.mean(sub) / max(np.std(sub), 0.01)
                if sh > best_sh: best_sh, best_b = sh, b_cut
            params['div_breadth'] = best_b
        else:
            params['div_breadth'] = DEFAULTS['div_breadth']

        # 15. v17: VVIX crisis threshold — where does bounce start?
        vvix_sigs = [s for s in sigs if s.get('vvix')]
        if len(vvix_sigs) >= 100:
            best_sh, best_v = -999, DEFAULTS['vvix_crisis']
            for v_cut in PARAM_GRID['vvix_crisis']:
                sub = [s['o5d'] for s in vvix_sigs if s['vvix'] >= v_cut]
                if len(sub) < 20: continue
                sh = np.mean(sub) / max(np.std(sub), 0.01)
                if sh > best_sh: best_sh, best_v = sh, v_cut
            params['vvix_crisis'] = best_v
        else:
            params['vvix_crisis'] = DEFAULTS['vvix_crisis']

        # 16. v17: washout breadth — when does washout bounce work?
        if len(breadth_sigs) >= 100:
            best_sh, best_b = -999, DEFAULTS['washout_breadth']
            for b_cut in PARAM_GRID['washout_breadth']:
                sub = [s['o5d'] for s in breadth_sigs if s['breadth'] < b_cut]
                if len(sub) < 30: continue
                sh = np.mean(sub) / max(np.std(sub), 0.01)
                if sh > best_sh: best_sh, best_b = sh, b_cut
            params['washout_breadth'] = best_b
        else:
            params['washout_breadth'] = DEFAULTS['washout_breadth']

        logger.debug(
            "AdaptiveParams [%s]: SL=%.1f%% TP=%.1f%% atr≤%.1f mom≤%.0f d0≥%.2f σ=%.1f "
            "beta≤%.1f pe≤%.0f tp=%.1f/%.1f/%.1f vix=%d/%d mcap≥%dB vol≤%.1f nblk=%d (n=%d)",
            key, sl_pct, tp_pct, params['atr_max'], params['mom_cut'],
            params['d0_close_min'], params['elite_sigma'],
            params['beta_max'], params['pe_max'],
            tp_d0, tp_d2, tp_d3,
            params['vix_calm'], params['vix_fear'],
            params['min_mcap_b'], params['max_vol_ratio'],
            params['n_blocked'], len(sigs))

        return params

    def _learn_sl_tp_absolute(self, sigs):
        """Grid search absolute SL% × TP% → best Sharpe.

        v15.1: uses absolute % instead of ATR multiples.
        Walks D1-D5 highs/lows for accurate TP/SL simulation.
        """
        ohlc_sigs = [s for s in sigs if s.get('d1o') and s.get('day_hl')]
        if len(ohlc_sigs) < 50:
            return DEFAULTS['sl_pct'], DEFAULTS['tp_pct']

        best_sharpe = -999
        best_sl, best_tp = DEFAULTS['sl_pct'], DEFAULTS['tp_pct']

        for sl in PARAM_GRID['sl_pct']:
            for tp in PARAM_GRID['tp_pct']:
                if tp <= sl:
                    continue  # enforce RR > 1.0
                pnls = []
                for s in ohlc_sigs:
                    d1o = s['d1o']
                    if d1o <= 0:
                        continue
                    hit = False
                    for h, l in s['day_hl']:
                        if (l / d1o - 1) * 100 <= -sl:
                            pnls.append(-sl)
                            hit = True
                            break
                        if (h / d1o - 1) * 100 >= tp:
                            pnls.append(tp)
                            hit = True
                            break
                    if not hit:
                        d5c = s.get('d5c', d1o)
                        pnls.append((d5c / d1o - 1) * 100)

                p = np.array(pnls)
                if len(p) < 30:
                    continue
                sharpe = p.mean() / max(p.std(), 0.01)
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_sl = sl
                    best_tp = tp

        return best_sl, best_tp

    def _learn_threshold(self, sigs, feature, grid, mode='upper'):
        """Sweep threshold to find best WR.

        mode='upper': keep signals where feature <= threshold (e.g. ATR, momentum)
        mode='lower': keep signals where feature >= threshold (e.g. d0_close_min)
        """
        best_wr = 0
        best_cut = grid[len(grid) // 2]  # middle as default

        for cut in grid:
            if mode == 'upper':
                filtered = [s for s in sigs if s.get(feature, 0) <= cut]
            else:
                filtered = [s for s in sigs if s.get(feature, 0) >= cut]

            if len(filtered) < 50:
                continue

            wr = sum(1 for s in filtered if s['o5d'] > 0) / len(filtered)
            if wr > best_wr:
                best_wr = wr
                best_cut = cut

        return float(best_cut)

    def _learn_elite_sigma(self, sigs):
        """Find elite_sigma that maximizes Sharpe(E[R] × sqrt(n_picks)).

        v13.1 fix: was maximizing E[R] alone → always converged to sigma=2.0
        (highest sigma = fewest picks = highest E[R] by selection bias).
        Now uses Sharpe-like metric: E[R] × sqrt(n) / std to balance
        quality (high E[R]) with quantity (enough picks to trade).
        """
        ohlc_sigs = [s for s in sigs if s.get('d1o')]
        if len(ohlc_sigs) < 50:
            return DEFAULTS['elite_sigma']

        ers = np.array([s['o5d'] for s in ohlc_sigs])
        n_days = len(set(s.get('scan_date', '') for s in ohlc_sigs))
        if n_days == 0:
            return DEFAULTS['elite_sigma']

        best_score = -999
        best_sigma = DEFAULTS['elite_sigma']

        for sigma in PARAM_GRID['elite_sigma']:
            threshold = ers.mean() + sigma * ers.std()
            elite_mask = ers >= threshold
            n_elite = elite_mask.sum()
            if n_elite < 5:
                continue
            elite_ers = ers[elite_mask]
            elite_mean = elite_ers.mean()
            elite_std = max(elite_ers.std(), 0.01)
            # Picks per day (want at least ~1-2)
            picks_per_day = n_elite / max(n_days, 1)
            if picks_per_day < 0.5:
                continue  # too few picks
            # Score: Sharpe × sqrt(picks_per_day) — balance quality + quantity
            score = (elite_mean / elite_std) * np.sqrt(picks_per_day)
            if score > best_score:
                best_score = score
                best_sigma = sigma

        return best_sigma

    def _learn_vix_boundaries(self, sigs):
        """v17: Grid search optimal VIX CALM/FEAR thresholds (best avg Sharpe).

        Splits signals into 3 regimes by VIX level, finds boundaries
        that maximize average Sharpe across all 3 regimes.
        """
        vix_sigs = [s for s in sigs if s.get('vix') and s.get('o5d') is not None]
        if len(vix_sigs) < 200:
            return DEFAULTS['vix_calm'], DEFAULTS['vix_fear']

        best_sharpe = -999
        best_calm, best_fear = DEFAULTS['vix_calm'], DEFAULTS['vix_fear']

        for calm_cut in PARAM_GRID['vix_calm']:
            for fear_cut in PARAM_GRID['vix_fear']:
                if fear_cut <= calm_cut + 2:
                    continue
                calm = [s['o5d'] for s in vix_sigs if s['vix'] < calm_cut]
                normal = [s['o5d'] for s in vix_sigs if calm_cut <= s['vix'] < fear_cut]
                fear = [s['o5d'] for s in vix_sigs if s['vix'] >= fear_cut]

                if len(calm) < 50 or len(normal) < 50 or len(fear) < 50:
                    continue

                # Average Sharpe across 3 regimes
                avg_sh = np.mean([
                    np.mean(r) / max(np.std(r), 0.01)
                    for r in [calm, normal, fear]
                ])
                if avg_sh > best_sharpe:
                    best_sharpe = avg_sh
                    best_calm, best_fear = calm_cut, fear_cut

        return best_calm, best_fear

    def _learn_n_blocked(self, sigs):
        """v17: Learn optimal N sectors to block (walk-forward Sharpe)."""
        # This is a global param, not per-sector — use all sigs
        if len(sigs) < 200:
            return DEFAULTS['n_blocked']

        # Group by sector momentum → simulate blocking bottom N
        by_sector = {}
        for s in sigs:
            sect = s.get('sector', '')
            if not sect:
                continue
            if sect not in by_sector:
                by_sector[sect] = []
            by_sector[sect].append(s['o5d'])

        if len(by_sector) < 6:
            return DEFAULTS['n_blocked']

        # Rank sectors by avg outcome
        sector_avg = {s: np.mean(rets) for s, rets in by_sector.items() if len(rets) >= 20}
        if len(sector_avg) < 6:
            return DEFAULTS['n_blocked']

        ranked_sectors = sorted(sector_avg.keys(), key=lambda s: sector_avg[s])

        best_sharpe = -999
        best_n = DEFAULTS['n_blocked']
        for n in PARAM_GRID['n_blocked']:
            blocked = set(ranked_sectors[:n])
            allowed_rets = [s['o5d'] for s in sigs
                            if s.get('sector', '') not in blocked and s.get('o5d') is not None]
            if len(allowed_rets) < 100:
                continue
            sh = np.mean(allowed_rets) / max(np.std(allowed_rets), 0.01)
            if sh > best_sharpe:
                best_sharpe = sh
                best_n = n

        return best_n

    def _learn_ubrain_cutoff(self, sigs):
        """v17: Learn optimal UBrain probability cutoff from backfill data.

        Uses ubrain_backfill table (75K signals with pre-computed probabilities).
        Finds cutoff that maximizes Sharpe while keeping enough candidates.
        """
        try:
            with get_session() as session:
                # Get UBrain probs for signals in this group's sector
                sector = sigs[0].get('sector', '') if sigs else ''
                if sector:
                    rows = session.execute(text("""
                        SELECT u.ubrain_prob, u.outcome_5d
                        FROM ubrain_backfill u
                        JOIN backfill_signal_outcomes b ON u.scan_date = b.scan_date AND u.symbol = b.symbol
                        WHERE b.sector = :p0 AND u.ubrain_prob IS NOT NULL AND u.outcome_5d IS NOT NULL
                    """), {'p0': sector}).fetchall()
                else:
                    rows = session.execute(text("""
                        SELECT ubrain_prob, outcome_5d FROM ubrain_backfill
                        WHERE ubrain_prob IS NOT NULL AND outcome_5d IS NOT NULL
                    """)).fetchall()
        except Exception:
            return DEFAULTS['ubrain_cutoff']

        if len(rows) < 200:
            return DEFAULTS['ubrain_cutoff']

        best_sharpe = -999
        best_cut = DEFAULTS['ubrain_cutoff']
        for cut in PARAM_GRID['ubrain_cutoff']:
            kept = [r[1] for r in rows if r[0] >= cut]
            if len(kept) < 20:
                continue
            sh = np.mean(kept) / max(np.std(kept), 0.01)
            if sh > best_sharpe:
                best_sharpe = sh
                best_cut = cut

        return best_cut

    def _learn_ranking_weights(self, sigs):
        """v17: Grid search optimal ranking weights for strategy vs sector Sharpe."""
        if len(sigs) < 500:
            return DEFAULTS['rank_w_strat'], DEFAULTS['rank_w_sect']

        # Pre-compute strategy×regime and sector×regime Sharpes from this group
        from collections import defaultdict as dd
        strat_rets = dd(list)
        sect_rets = dd(list)
        for s in sigs:
            regime = _classify_regime(s['vix'], s.get('breadth', 50))
            # Classify strategy
            mom = s.get('mom', 0)
            d20h = s.get('d20h', 0)
            vol = s.get('vol', 1)
            strat = _classify_strategy(mom, d20h, vol)
            strat_rets[(regime, strat)].append(s['o5d'])
            sect_rets[(regime, s['sector'])].append(s['o5d'])

        strat_sh = {k: np.mean(v)/max(np.std(v),0.01) for k,v in strat_rets.items() if len(v)>=20}
        sect_sh = {k: np.mean(v)/max(np.std(v),0.01) for k,v in sect_rets.items() if len(v)>=20}

        # Group signals by date for top-N simulation
        by_date = dd(list)
        for s in sigs:
            by_date[s['scan_date']].append(s)

        best_sharpe = -999
        best_ws, best_wse = DEFAULTS['rank_w_strat'], DEFAULTS['rank_w_sect']
        for ws in PARAM_GRID['rank_w_strat']:
            for wse in PARAM_GRID['rank_w_sect']:
                if ws == 0 and wse == 0: continue
                outcomes = []
                for dt, day_sigs in by_date.items():
                    if len(day_sigs) < 5: continue
                    def score_fn(s):
                        regime = _classify_regime(s['vix'], s.get('breadth', 50))
                        mom = s.get('mom', 0)
                        d20h = s.get('d20h', 0)
                        vol = s.get('vol', 1)
                        st = _classify_strategy(mom, d20h, vol)
                        return max(0, strat_sh.get((regime, st), 0)) * ws + max(0, sect_sh.get((regime, s['sector']), 0)) * wse
                    ranked = sorted(day_sigs, key=score_fn, reverse=True)
                    for s in ranked[:3]:
                        outcomes.append(s['o5d'])
                if len(outcomes) < 100: continue
                o = np.array(outcomes)
                sh = o.mean() / max(o.std(), 0.01)
                if sh > best_sharpe:
                    best_sharpe = sh
                    best_ws, best_wse = ws, wse

        return best_ws, best_wse

    def _learn_spec_skip(self, sigs):
        """v17: Learn optimal speculative skip threshold from outcome data."""
        try:
            with get_session() as session:
                spec_scores = {}
                for r in session.execute(
                    text("SELECT symbol, score FROM stock_context WHERE context_type='SPECULATIVE_FLAG'")
                ).fetchall():
                    spec_scores[r[0]] = r[1]
        except Exception:
            return DEFAULTS['spec_skip']

        if not spec_scores:
            return DEFAULTS['spec_skip']

        # Match signals with speculative scores
        spec_sigs = [(spec_scores.get(s['symbol'], 0), s['o5d'])
                     for s in sigs if s['symbol'] in spec_scores and s.get('o5d') is not None]

        if len(spec_sigs) < 50:
            return DEFAULTS['spec_skip']

        best_sharpe = -999
        best_thresh = DEFAULTS['spec_skip']
        for thresh in PARAM_GRID['spec_skip']:
            kept = [o5d for sc, o5d in spec_sigs if sc >= thresh]
            if len(kept) < 20:
                continue
            sh = np.mean(kept) / max(np.std(kept), 0.01)
            if sh > best_sharpe:
                best_sharpe = sh
                best_thresh = thresh

        return best_thresh

    def _learn_tp_multipliers(self, sigs):
        """v17: Grid search optimal TP D0/D2/D3 ATR multipliers (best Sharpe).

        Walks D1-D3 highs/lows with each TP schedule, picks best Sharpe.
        D1 mult = D0 mult (same early TP target).
        """
        ohlc_sigs = [s for s in sigs if s.get('d1o') and s.get('day_hl')]
        if len(ohlc_sigs) < 100:
            return DEFAULTS['tp_d0_mult'], DEFAULTS['tp_d2_mult'], DEFAULTS['tp_d3_mult']

        best_sharpe = -999
        best_d0 = DEFAULTS['tp_d0_mult']
        best_d2 = DEFAULTS['tp_d2_mult']
        best_d3 = DEFAULTS['tp_d3_mult']

        for d0 in PARAM_GRID['tp_d0_mult']:
            for d2 in PARAM_GRID['tp_d2_mult']:
                for d3 in PARAM_GRID['tp_d3_mult']:
                    if d3 < d2:
                        continue  # D3 TP should be >= D2
                    pnls = []
                    for s in ohlc_sigs:
                        atr = s['atr']
                        d1o = s['d1o']
                        if d1o <= 0 or atr <= 0:
                            continue
                        sl_pct = max(1.5, min(3.5, 0.8 * atr))
                        tp_by_day = [max(1.0, d0 * atr), max(1.0, d0 * atr),
                                     max(1.0, d2 * atr), max(1.0, d3 * atr)]
                        hit = False
                        for day_idx, (h, l) in enumerate(s['day_hl'][:3]):
                            tp_pct = tp_by_day[min(day_idx + 1, 3)]
                            if (l / d1o - 1) * 100 <= -sl_pct:
                                pnls.append(-sl_pct)
                                hit = True
                                break
                            if (h / d1o - 1) * 100 >= tp_pct:
                                pnls.append(tp_pct)
                                hit = True
                                break
                        if not hit:
                            d3c = s.get('d3c', d1o)
                            if d3c and d3c > 0:
                                pnls.append((d3c / d1o - 1) * 100)

                    if len(pnls) < 50:
                        continue
                    p = np.array(pnls)
                    sharpe = p.mean() / max(p.std(), 0.01)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_d0, best_d2, best_d3 = d0, d2, d3

        return best_d0, best_d2, best_d3

    def _apply_guard(self, new_params, old_params):
        """Cap parameter changes at ±MAX_CHANGE_PCT per cycle."""
        guarded = {}
        for name, new_val in new_params.items():
            old_val = old_params.get(name)
            if old_val and old_val != 0:
                change_pct = abs(new_val - old_val) / abs(old_val) * 100
                if change_pct > MAX_CHANGE_PCT:
                    if new_val > old_val:
                        new_val = old_val * (1 + MAX_CHANGE_PCT / 100)
                    else:
                        new_val = old_val * (1 - MAX_CHANGE_PCT / 100)
                    new_val = round(new_val, 4)
            guarded[name] = new_val
        return guarded

    # === Data loading ===

    def _load_data(self, max_date=None):
        """Load historical signals with D1-D5 OHLC for SL/TP simulation."""
        with get_session() as session:
            date_filter = f"AND b.scan_date <= '{max_date}'" if max_date else ""
            rows = session.execute(text(f"""
                SELECT b.scan_date, b.symbol, b.sector,
                       b.atr_pct, b.momentum_5d, b.distance_from_20d_high,
                       b.volume_ratio, b.outcome_5d, b.vix_at_signal,
                       COALESCE(m.vix_close, 20) as vix,
                       COALESCE(mb.pct_above_20d_ma, 50) as breadth,
                       d0.high as d0h, d0.low as d0l, d0.close as d0c,
                       d1.open as d1o, d1.high as d1h, d1.low as d1l,
                       d2.high as d2h, d2.low as d2l,
                       d3.high as d3h, d3.low as d3l, d3.close as d3c,
                       d4.high as d4h, d4.low as d4l,
                       d5.high as d5h, d5.low as d5l, d5.close as d5c,
                       sf.beta, sf.pe_forward, sf.market_cap,
                       m.vvix_close
                FROM backfill_signal_outcomes b
                LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
                LEFT JOIN macro_snapshots m ON b.scan_date = m.date
                LEFT JOIN market_breadth mb ON b.scan_date = mb.date
                LEFT JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
                LEFT JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
                LEFT JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
                LEFT JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
                LEFT JOIN signal_daily_bars d4 ON b.scan_date=d4.scan_date AND b.symbol=d4.symbol AND d4.day_offset=4
                LEFT JOIN signal_daily_bars d5 ON b.scan_date=d5.scan_date AND b.symbol=d5.symbol AND d5.day_offset=5
                WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0
                AND b.sector IS NOT NULL
                AND m.vix_close IS NOT NULL AND mb.pct_above_20d_ma IS NOT NULL
                {date_filter}
                ORDER BY b.scan_date
            """)).fetchall()

        if not rows:
            return []

        data = []
        for r in rows:
            d0h = r[11] or 0
            d0l = r[12] or 0
            d0c = r[13] or 0
            d0_range = d0h - d0l
            d0_pos = (d0c - d0l) / d0_range if d0_range > 0 else 0.5

            entry = {
                'scan_date': r[0], 'symbol': r[1], 'sector': r[2],
                'atr': r[3], 'mom': r[4] or 0,
                'd20h': r[5] or -5, 'vol': r[6] or 1,
                'o5d': r[7], 'vix': r[9], 'breadth': r[10],
                'd0_pos': d0_pos,
                'beta': r[27], 'pe': r[28],
                'mcap_b': (r[29] / 1e9) if r[29] else None,
                'vvix': r[30],
            }

            # D1-D5 OHLC for absolute SL/TP simulation
            if r[14] and r[14] > 0:
                entry['d1o'] = r[14]
                entry['d1h'] = r[15]
                entry['d1l'] = r[16]
                entry['d3h'] = r[19]
                entry['d3l'] = r[20]
                entry['d3c'] = r[21]
                entry['d5c'] = r[26] or r[21]  # fallback to D3 close

                # D1-D5 high/low pairs for walking TP/SL
                day_hl = []
                for hi, lo in [(r[15], r[16]), (r[17], r[18]),
                                (r[19], r[20]), (r[22], r[23]),
                                (r[24], r[25])]:
                    if hi and lo and hi > 0 and lo > 0:
                        day_hl.append((hi, lo))
                entry['day_hl'] = day_hl

            data.append(entry)

        logger.info("AdaptiveParams: loaded %d signals (max_date=%s)",
                     len(data), max_date or 'all')
        return data

    # === DB persistence ===

    def _ensure_tables(self):
        with get_session() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS adaptive_parameters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sector TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    param_name TEXT NOT NULL,
                    param_value REAL NOT NULL,
                    n_signals INTEGER,
                    metric_value REAL,
                    fit_date TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(sector, regime, param_name)
                )
            """))
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS adaptive_parameter_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sector TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    param_name TEXT NOT NULL,
                    old_value REAL,
                    new_value REAL,
                    n_signals INTEGER,
                    reason TEXT,
                    changed_at TEXT DEFAULT (datetime('now'))
                )
            """))

    def save_to_db(self):
        """Persist learned parameters to DB."""
        with get_session() as session:
            for (sector, regime), params in self._params.items():
                stats = self._fit_stats.get((sector, regime), {})
                n_sigs = stats.get('n', 0)
                for name, value in params.items():
                    # Check old value for history
                    old = session.execute(text("""
                        SELECT param_value FROM adaptive_parameters
                        WHERE sector=:p0 AND regime=:p1 AND param_name=:p2
                    """), {'p0': sector, 'p1': regime, 'p2': name}).fetchone()
                    old_val = old[0] if old else None

                    session.execute(text("""
                        INSERT INTO adaptive_parameters
                        (sector, regime, param_name, param_value, n_signals, fit_date)
                        VALUES (:p0, :p1, :p2, :p3, :p4, :p5)
                        ON CONFLICT(sector, regime, param_name)
                        DO UPDATE SET param_value=:p3, n_signals=:p4,
                                      fit_date=:p5, created_at=datetime('now')
                    """), {'p0': sector, 'p1': regime, 'p2': name, 'p3': value, 'p4': n_sigs, 'p5': self._fit_date})

                    if old_val is not None and abs(old_val - value) > 0.001:
                        session.execute(text("""
                            INSERT INTO adaptive_parameter_history
                            (sector, regime, param_name, old_value, new_value,
                             n_signals, reason)
                            VALUES (:p0, :p1, :p2, :p3, :p4, :p5, 'auto-refit')
                        """), {'p0': sector, 'p1': regime, 'p2': name, 'p3': old_val, 'p4': value, 'p5': n_sigs})
            logger.info("AdaptiveParams: saved %d groups to DB",
                        len(self._params))

    def load_from_db(self) -> bool:
        """Load previously learned parameters from DB."""
        with get_session() as session:
            rows = session.execute(text("""
                SELECT sector, regime, param_name, param_value, n_signals
                FROM adaptive_parameters
            """)).fetchall()

        if not rows:
            return False

        self._params = {}
        for sector, regime, name, value, n_sigs in rows:
            key = (sector, regime)
            if key not in self._params:
                self._params[key] = {}
            self._params[key][name] = value

        self._fitted = True
        self._fit_date = 'loaded'
        self._fit_time = time.time()
        logger.info("AdaptiveParams: loaded %d groups from DB", len(self._params))
        return True

    # === Stats ===

    def get_all(self) -> dict:
        """All learned parameters as nested dict."""
        result = {}
        for (sector, regime), params in sorted(self._params.items()):
            if sector not in result:
                result[sector] = {}
            result[sector][regime] = dict(params)
        return result

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'fit_date': self._fit_date,
            'n_groups': len(self._params),
            'n_learned': sum(1 for s in self._fit_stats.values()
                            if s.get('source') == 'learned'),
            'n_default': sum(1 for s in self._fit_stats.values()
                            if s.get('source') == 'default'),
        }

    def print_summary(self):
        """Print human-readable parameter table."""
        print(f"\n{'Sector':<25s} {'Regime':<8s} {'SL%':>5s} {'TP%':>5s} {'RR':>4s} "
              f"{'ATR≤':>5s} {'Mom≤':>5s} {'D0≥':>5s} {'σ':>4s} {'N':>5s}")
        print("-" * 80)
        for sector in SECTORS:
            for regime in REGIMES:
                key = (sector, regime)
                p = self._params.get(key, DEFAULTS)
                stats = self._fit_stats.get(key, {})
                n = stats.get('n', 0)
                src = stats.get('source', '?')
                marker = '' if src == 'learned' else ' (D)'
                sl = p.get('sl_pct', 3.0)
                tp = p.get('tp_pct', 6.0)
                rr = tp / sl if sl > 0 else 0
                print(f"{sector:<25s} {regime:<8s} "
                      f"{sl:>4.1f}% "
                      f"{tp:>4.1f}% "
                      f"{rr:>3.1f} "
                      f"{p.get('atr_max', 5.0):>4.1f} "
                      f"{p.get('mom_cut', 3):>+4.0f} "
                      f"{p.get('d0_close_min', 0.3):>4.2f} "
                      f"{p.get('elite_sigma', 0.8):>3.1f} "
                      f"{n:>5d}{marker}")
