"""
Unified Sizer — SL/TP computation + council decision building.
Part of Discovery v13.0 Clean Architecture.

Replaces: arbiter + risk_brain + calibrator + context_scorer + profile WR
all applied independently in engine._score_v3.

Single method: create_pick() → DiscoveryPick with all sizing + council data.
"""
import logging
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from discovery.models import DiscoveryPick
from discovery.risk_brain import RiskBrain
from discovery.arbiter import DecisionArbiter
from discovery.calibrator import Calibrator
from discovery.context_scorer import ContextScorer
from discovery.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class UnifiedSizer:
    """Compute SL/TP and build council decision for each pick."""

    def __init__(self, config, param_manager, adaptive_params=None):
        self._config = config
        self._params = param_manager
        self._adaptive = adaptive_params

        self._knowledge_graph = KnowledgeGraph()
        self._context_scorer = ContextScorer(self._knowledge_graph)
        self._risk_brain = RiskBrain()
        self._arbiter = DecisionArbiter(param_manager=param_manager)
        self._calibrator = Calibrator()

    @property
    def knowledge_graph(self):
        return self._knowledge_graph

    @property
    def context_scorer(self):
        return self._context_scorer

    def build_knowledge_graph(self):
        """Build KG (called once during fit)."""
        if not self._knowledge_graph._built:
            try:
                self._knowledge_graph.build_all()
                logger.info("Sizer: KnowledgeGraph built (%s)",
                            self._knowledge_graph.get_stats())
            except Exception as e:
                logger.error("Sizer: KnowledgeGraph build error: %s", e)

    def compute_sl_tp(self, candidate, regime, config):
        """Compute SL/TP prices for a candidate.

        Uses adaptive params if available, else falls back to config.
        Returns dict with sl_pct, tp_pct, sl_price, tp1_price, tp2_price,
        limit_pct, entry_status.
        """
        price = candidate['close']
        atr = candidate.get('atr_pct', 0) or 0
        sector = candidate.get('sector', '')

        dsl_floor = config.get('dynamic_sl', {}).get('floor', 1.5)
        dsl_cap = config.get('dynamic_sl', {}).get('cap', 5.0)

        # Limit-buy config
        lb_cfg = config.get('limit_buy', {})
        lb_enabled = lb_cfg.get('enabled', False)
        lb_pullback_mult = lb_cfg.get('pullback_atr_mult', 0.3)
        lb_max_atr = lb_cfg.get('max_atr_pct', 3.5)
        lb_sl_pct = lb_cfg.get('sl_pct', 2.5)

        # Get TP/SL ratios — adaptive or config
        if self._adaptive:
            tp_ratio = self._adaptive.get(sector, regime, 'tp_ratio')
            sl_mult = self._adaptive.get(sector, regime, 'sl_mult')
        else:
            v3_cfg = config.get('v3', {})
            stp_cfg = v3_cfg.get('smart_tp', {})
            tp_ratios = stp_cfg.get('tp_regime_ratios',
                                    {'BULL': 1.0, 'STRESS': 0.75, 'CRISIS': 0.5})
            tp_ratio = tp_ratios.get(regime, 0.75)
            dsl_cfg = config.get('dynamic_sl', {})
            sl_mult = {
                'BULL': dsl_cfg.get('bull_mult', 2.0),
                'STRESS': dsl_cfg.get('stress_mult', 1.5),
                'CRISIS': dsl_cfg.get('crisis_mult', 1.0),
            }.get(regime, 1.5)

        # Compute SL
        if lb_enabled and atr < lb_max_atr:
            pick_sl_pct = round(max(lb_sl_pct, atr), 1)
            pick_limit_pct = round(lb_pullback_mult * atr, 2)
        else:
            if atr > 0:
                pick_sl_pct = max(dsl_floor, min(dsl_cap, sl_mult * atr))
                pick_sl_pct = round(pick_sl_pct, 1)
            else:
                pick_sl_pct = config.get('v3', {}).get('sl_pct', 3.0)
            pick_limit_pct = None

        # Compute TP
        pick_tp_pct = round(max(0.5, tp_ratio * atr), 1)

        # Ensure TP > SL (minimum RR ratio 1.0)
        if pick_tp_pct <= pick_sl_pct:
            pick_tp_pct = round(pick_sl_pct * 1.5, 1)

        # TP2 = TP1 × 2.0 (extended target)
        pick_tp2_pct = round(pick_tp_pct * 2.0, 1)

        sl_price = price * (1 - pick_sl_pct / 100)
        tp1_price = price * (1 + pick_tp_pct / 100)
        tp2_price = price * (1 + pick_tp2_pct / 100)

        return {
            'sl_pct': pick_sl_pct,
            'tp_pct': pick_tp_pct,
            'tp2_pct': pick_tp2_pct,
            'sl_price': round(sl_price, 2),
            'tp1_price': round(tp1_price, 2),
            'tp2_price': round(tp2_price, 2),
            'limit_pct': pick_limit_pct,
            'entry_status': 'pending' if pick_limit_pct else 'filled',
        }

    def create_pick(self, candidate, score, macro, regime, macro_er,
                    strategy_info, regime_decision, scan_date,
                    existing_picks, scorer):
        """Create a complete DiscoveryPick with SL/TP and council decision.

        Args:
            candidate: dict with technical + macro features
            score: blended E[R] score
            macro: macro features dict
            regime: 'BULL', 'STRESS', 'CRISIS'
            macro_er: macro kernel E[R]
            strategy_info: dict from StrategyRouter
            regime_decision: dict from RegimeBrain
            scan_date: str
            existing_picks: list of already-created DiscoveryPick
            scorer: UnifiedScorer instance (for predictions)

        Returns:
            DiscoveryPick or None
        """
        config = self._config
        c = candidate
        price = c['close']
        atr = c.get('atr_pct', 0) or 0

        # 1. Compute SL/TP
        sl_tp = self.compute_sl_tp(c, regime, config)

        # 2. Divergence boost — stock UP while market weak
        breadth = macro.get('pct_above_20d_ma') or 50
        d0_ret = ((price / c.get('open', price)) - 1) * 100 if c.get('open') else 0
        if d0_ret > 0.5 and breadth < 40:
            score += 0.5
            c['divergence_boost'] = True

        logger.info(
            "Sizer [%s]: %s sER=%+.2f%% TP=%.1f%% SL=%.1f%% "
            "atr=%.1f vol=%.2f mom5d=%.1f sector=%s",
            regime, c['symbol'], score, sl_tp['tp_pct'], sl_tp['sl_pct'],
            atr, c.get('volume_ratio', 0) or 0,
            c.get('momentum_5d', 0) or 0, c.get('sector', ''),
        )

        # 3. Create DiscoveryPick
        pick = DiscoveryPick(
            symbol=c['symbol'], scan_date=scan_date, scan_price=price,
            current_price=price, layer2_score=round(score, 2),
            beta=c.get('beta', 0), atr_pct=c.get('atr_pct', 0),
            distance_from_high=c.get('distance_from_high', 0),
            distance_from_20d_high=c.get('distance_from_20d_high', 0),
            rsi=c.get('rsi', 0), momentum_5d=c.get('momentum_5d', 0),
            momentum_20d=c.get('momentum_20d', 0),
            volume_ratio=c.get('volume_ratio', 0),
            sl_price=sl_tp['sl_price'], sl_pct=sl_tp['sl_pct'],
            tp1_price=sl_tp['tp1_price'], tp1_pct=sl_tp['tp_pct'],
            tp2_price=sl_tp['tp2_price'], tp2_pct=sl_tp.get('tp2_pct', sl_tp['tp_pct']),
            expected_gain=round(macro_er, 2),
            rr_ratio=round(sl_tp['tp_pct'] / sl_tp['sl_pct'], 2) if sl_tp['sl_pct'] > 0 else 0,
            limit_pct=sl_tp['limit_pct'],
            entry_status=sl_tp['entry_status'],
            sector=c.get('sector', ''), market_cap=c.get('market_cap', 0),
            vix_close=macro.get('vix_close', 0),
            pct_above_20d_ma=macro.get('pct_above_20d_ma', 0),
            vix_term_structure=c.get('vix_term_structure', 0),
            new_52w_highs=c.get('new_52w_highs', 0),
            bull_score=c.get('bull_score'),
            news_count=c.get('news_count', 0),
            news_pos_ratio=c.get('news_pos_ratio'),
            highs_lows_ratio=c.get('highs_lows_ratio', 0),
            ad_ratio=c.get('ad_ratio', 0),
            mcap_log=c.get('mcap_log', 0),
            sector_1d_change=c.get('sector_1d_change', 0),
            vix3m_close=c.get('vix3m_close', 0),
            upside_pct=c.get('upside_pct'),
            days_to_earnings=c.get('days_to_earnings'),
            put_call_ratio=c.get('put_call_ratio'),
            short_pct_float=c.get('short_pct_float'),
            breadth_delta_5d=macro.get('breadth_delta_5d'),
            vix_delta_5d=macro.get('vix_delta_5d'),
            crude_close=macro.get('crude_close'),
            gold_close=macro.get('gold_close'),
            dxy_delta_5d=macro.get('dxy_delta_5d'),
            stress_score=macro.get('stress_score'),
        )

        # 4. TP timeline prediction
        timeline = scorer.predict_tp_timeline(
            atr, c.get('volume_ratio') or 1,
            sl_tp['tp_pct'], sl_tp['sl_pct'],
            stock_er=score, mom5=c.get('momentum_5d') or 0,
            d20h=c.get('distance_from_20d_high') or -5)
        if timeline:
            pick.tp_timeline = timeline

        # 5. Weekend play prediction
        is_friday = datetime.now(ZoneInfo('America/New_York')).weekday() == 4
        if is_friday and scorer.has_weekend_data():
            weekend = scorer.predict_weekend(
                atr, c.get('volume_ratio') or 1,
                c.get('momentum_5d') or 0,
                c.get('distance_from_20d_high') or -5,
                macro.get('vix_close') or 20,
            )
            if weekend:
                pick.weekend_play = weekend

        # 6. Council decision
        try:
            council = self._build_council(
                c, pick, macro, regime_decision, strategy_info,
                scan_date, existing_picks, scorer)
            pick.council = council
        except Exception as e:
            logger.error("Sizer: council error for %s: %s", c['symbol'], e)
            pick.council = {
                'decision': 'TRADE', 'tier': 'LEAN', 'confidence': 0,
                'position_size': 0.25, 'reasons': ['fallback'],
                'brains': {}, 'strategy': strategy_info,
                'stock_signals': {}, 'stock_profile': {},
                'context': {}, 'sensors': {},
            }

        return pick

    def _build_council(self, candidate, pick, macro, regime_decision,
                       strategy_info, scan_date, existing_picks, scorer):
        """Build unified council decision for a pick."""
        c = candidate

        # Per-stock signals from leading indicators
        stock_signals = scorer.compute_stock_signals(c['symbol'], scan_date)

        # Stock profile matching
        stock_profile = scorer.predict_stock_profile(
            c.get('atr_pct') or 3,
            c.get('momentum_5d') or 0,
            c.get('volume_ratio') or 1,
            c.get('distance_from_20d_high') or -5,
            sector=c.get('sector', ''))

        # Sensor signals
        sensor_signals = scorer.compute_sensors(
            c['symbol'], scan_date, macro, c)

        # Brain prediction (UnifiedBrain or StockBrain fallback)
        regime_prob = (regime_decision or {}).get('probability', 0.5)
        stock_brain_result = scorer.predict_stock(c, sensor_signals, regime_prob)

        # Risk evaluation
        risk_result = self._risk_brain.evaluate(
            [{'symbol': c['symbol'], 'sector': c.get('sector', ''),
              'sl_pct': pick.sl_pct, 'tp1_pct': pick.tp1_pct}],
            [{'symbol': p.symbol, 'sector': p.sector, 'sl_pct': p.sl_pct}
             for p in existing_picks]
        )[0]

        # Calibrator confidence
        cal = self._calibrator.compute_confidence()

        # Arbiter decision
        council = self._arbiter.decide(
            stock_brain_result, regime_decision or {},
            risk_result,
            calibrator_confidence=cal.get('confidence', 50))

        # Context scoring — penalize speculative/risky stocks
        try:
            ctx_result = self._context_scorer.score(c['symbol'], macro)
            ctx_size = self._context_scorer.size_adjustment(c['symbol'], macro)
            council['position_size'] = round(
                council.get('position_size', 1) * ctx_size, 2)
            if ctx_result['penalty'] < -0.1:
                council['reasons'] = council.get('reasons', []) + [
                    f'Context: {" | ".join(ctx_result["penalties"])}']
        except Exception as e:
            logger.warning("Sizer: context error for %s: %s", c['symbol'], e)
            ctx_result = {'penalty': 0, 'penalties': [], 'flags': [],
                          'is_speculative': False}

        # Profile WR red flag — reduce size if historical match is bad
        profile_wr = stock_profile.get('wr', 50) if stock_profile else 50
        if profile_wr < 10:
            council['position_size'] = round(
                council.get('position_size', 1) * 0.25, 2)
            council['reasons'] = council.get('reasons', []) + [
                f'Profile WR={profile_wr:.0f}% → size quartered']
        elif profile_wr < 30:
            council['position_size'] = round(
                council.get('position_size', 1) * 0.5, 2)
            council['reasons'] = council.get('reasons', []) + [
                f'Profile WR={profile_wr:.0f}% → size halved']

        # Floor: position_size never below 0.05 (5%)
        if council.get('position_size', 1) < 0.05:
            council['position_size'] = 0.05

        # Build unified council dict
        council.update({
            'strategy': strategy_info,
            'stock_signals': stock_signals,
            'stock_profile': {
                'wr': profile_wr,
                'er': stock_profile.get('er', 0) if stock_profile else 0,
            },
            'exit_rules': {
                'gap_cut': 'If D1 gap < -0.5% → CUT immediately (WR=44% if hold)',
                'green_sell': 'If D1 close > entry → SELL at D1 close (WR=70%)',
                'hold_d5': 'If D1 red → HOLD to D5 (recovery time)',
            },
            'hammer': c.get('d0_hammer', False),
            'hammer_shadow': c.get('d0_lower_shadow', 0),
            'context': ctx_result,
            'sensors': sensor_signals,
        })

        return council

    def get_confidence(self):
        """Get calibrator confidence score."""
        try:
            return self._calibrator.compute_confidence()
        except Exception as e:
            logger.error("Sizer: calibrator error: %s", e)
            return {'confidence': 50, 'error': str(e)}

    def get_stats(self):
        return {
            'risk_brain': self._risk_brain.get_stats(),
            'knowledge_graph': self._knowledge_graph.get_stats(),
        }
