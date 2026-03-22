"""
Decision Arbiter — Council vote aggregator.
Combines Regime Brain + Stock Brain + Risk Brain into final decision.
Part of Discovery AI v7.0 Multi-Brain Council.

v7.1: No more VETO from regime — always TRADE with adaptive sizing.
  TRADE day (regime prob >= 0.50): full size, top 3 picks
  CAUTIOUS day (0.35-0.50): 50% size, top 1 pick
  LEAN day (< 0.35): 25% size, top 1 pick (minimum exposure)
Only Risk BLOCK can fully stop a trade.
"""
import logging

logger = logging.getLogger(__name__)


class DecisionArbiter:
    """Aggregate 3 brain outputs into final trading decision."""

    def __init__(self, param_manager=None):
        self._params = param_manager
        # Defaults (overridden by param_manager if available)
        self.stock_threshold = 0.50

    def decide(self, stock_result: dict, regime_result: dict,
               risk_result: dict, calibrator_confidence: float = 50.0) -> dict:
        """Make final decision from 3 brains.

        Sizing tiers (always trade, adjust size):
          - Risk BLOCK → VETO (only hard stop)
          - Regime TRADE (prob >= 0.50) → TRADE 100% size
          - Regime CAUTIOUS (0.35-0.50) → TRADE 50% size
          - Regime LEAN (< 0.35) → TRADE 25% size
          - Stock prob < threshold → reduces confidence, not decision
        """
        regime_trade = regime_result.get('trade_today', True)
        regime_prob = regime_result.get('probability', 0.5)
        regime_conf = regime_result.get('confidence', 0)
        regime_name = regime_result.get('regime', 'UNKNOWN')

        stock_prob = stock_result.get('probability', 0.49)
        stock_conf = stock_result.get('confidence', 0)

        risk_action = risk_result.get('risk_action', 'ALLOW')
        risk_size = risk_result.get('size_multiplier', 1.0)
        risk_reasons = risk_result.get('reasons', [])

        reasons = []
        decision = 'TRADE'

        # Get thresholds from ParamManager (auto-optimizable)
        p = self._params
        trade_thresh = p.get('arbiter', 'trade_threshold', 0.50) if p else 0.50
        cautious_thresh = p.get('arbiter', 'cautious_threshold', 0.35) if p else 0.35
        cal_thresh = p.get('arbiter', 'calibrator_low_threshold', 30.0) if p else 30.0

        # Only hard stop: Risk BLOCK
        if risk_action == 'BLOCK':
            decision = 'VETO'
            position_size = 0.0
            tier = 'BLOCKED'
            reasons.append(f'Risk: {", ".join(risk_reasons)}')

        # Adaptive sizing by regime probability
        elif regime_prob >= trade_thresh:
            tier = 'TRADE'
            position_size = 1.0
            reasons.append(f'Regime TRADE (prob={regime_prob:.0%}) → full size')

        elif regime_prob >= cautious_thresh:
            tier = 'CAUTIOUS'
            position_size = 0.50
            reasons.append(f'Regime cautious (prob={regime_prob:.0%}) → 50% size')

        else:
            tier = 'LEAN'
            position_size = 0.25
            reasons.append(f'Regime lean (prob={regime_prob:.0%}) → 25% size')

        # Stock brain adjusts confidence display but doesn't block
        if stock_prob < self.stock_threshold and decision == 'TRADE':
            reasons.append(f'Stock prob low ({stock_prob:.0%}) — lower confidence')

        # Risk REDUCE_SIZE
        if risk_action == 'REDUCE_SIZE' and decision == 'TRADE':
            position_size = min(position_size, risk_size)
            reasons.append(f'Risk: size capped at {risk_size:.0%}')

        # Calibrator: reduce size when system accuracy is low
        if calibrator_confidence < cal_thresh and decision == 'TRADE':
            position_size *= 0.5
            reasons.append(f'Calibrator low ({calibrator_confidence:.0f}%) → size halved')

        # Confidence: blend regime + stock + risk
        confidence = (
            0.50 * regime_conf +
            0.35 * stock_conf +
            0.15 * (100 if risk_action == 'ALLOW' else 50 if risk_action == 'REDUCE_SIZE' else 0)
        )

        result = {
            'decision': decision,
            'tier': tier,
            'confidence': round(confidence, 1),
            'position_size': round(position_size, 2),
            'reasons': reasons,
            'brains': {
                'regime': {'trade': regime_trade, 'probability': regime_prob,
                           'confidence': regime_conf, 'regime': regime_name},
                'stock': {'probability': stock_prob, 'confidence': stock_conf},
                'risk': {'action': risk_action, 'size': risk_size, 'reasons': risk_reasons},
            },
        }

        logger.info(
            "Arbiter: %s/%s (conf=%.0f%% size=%.0f%%) | regime=%.0f%% stock=%.0f%% risk=%s",
            decision, tier, confidence, position_size * 100,
            regime_prob * 100, stock_prob * 100, risk_action,
        )
        return result
