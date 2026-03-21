"""
Decision Arbiter — Council vote aggregator.
Combines Regime Brain + Stock Brain + Risk Brain into final TRADE/SKIP/VETO.
Part of Discovery AI v7.0 Multi-Brain Council.
"""
import logging

logger = logging.getLogger(__name__)


class DecisionArbiter:
    """Aggregate 3 brain outputs into final trading decision."""

    def __init__(self, stock_threshold: float = 0.50,
                 stock_strong_threshold: float = 0.55):
        self.stock_threshold = stock_threshold
        self.stock_strong_threshold = stock_strong_threshold

    def decide(self, stock_result: dict, regime_result: dict,
               risk_result: dict) -> dict:
        """Make final decision from 3 brains.

        Voting logic:
          - Regime SKIP → VETO (no trade regardless)
          - Risk BLOCK → VETO
          - Stock prob < threshold → SKIP
          - Stock prob >= threshold AND regime TRADE AND risk ALLOW → TRADE
          - Stock prob >= strong_threshold AND risk ALLOW → TRADE (override cautious regime)

        Returns:
            dict with decision, confidence, reasons, position_size
        """
        regime_trade = regime_result.get('trade_today', True)
        regime_conf = regime_result.get('confidence', 0)
        regime_name = regime_result.get('regime', 'UNKNOWN')

        stock_prob = stock_result.get('probability', 0.5)
        stock_conf = stock_result.get('confidence', 0)

        risk_action = risk_result.get('risk_action', 'ALLOW')
        risk_size = risk_result.get('size_multiplier', 1.0)
        risk_reasons = risk_result.get('reasons', [])

        reasons = []
        decision = 'SKIP'
        position_size = 1.0

        # Veto checks
        if risk_action == 'BLOCK':
            decision = 'VETO'
            reasons.append(f'Risk: {", ".join(risk_reasons)}')

        elif not regime_trade:
            # Strong stock signal can override cautious regime
            if stock_prob >= self.stock_strong_threshold and risk_action != 'BLOCK':
                decision = 'TRADE'
                position_size = 0.75  # reduced size when overriding regime
                reasons.append(f'Regime SKIP overridden by strong stock signal ({stock_prob:.0%})')
            else:
                decision = 'VETO'
                reasons.append(f'Regime: SKIP (conf={regime_conf:.0f}%)')

        elif stock_prob < self.stock_threshold:
            decision = 'SKIP'
            reasons.append(f'Stock prob {stock_prob:.0%} < {self.stock_threshold:.0%}')

        else:
            decision = 'TRADE'
            reasons.append(f'All brains agree: regime={regime_name} stock={stock_prob:.0%} risk={risk_action}')

        # Size adjustment
        if risk_action == 'REDUCE_SIZE':
            position_size = min(position_size, risk_size)
            reasons.append(f'Risk: size reduced to {risk_size:.0%}')

        # Confidence: weighted average of brain confidences
        confidence = (
            0.50 * regime_conf +
            0.35 * stock_conf +
            0.15 * (100 if risk_action == 'ALLOW' else 50 if risk_action == 'REDUCE_SIZE' else 0)
        )

        result = {
            'decision': decision,
            'confidence': round(confidence, 1),
            'position_size': round(position_size, 2),
            'reasons': reasons,
            'brains': {
                'regime': {'trade': regime_trade, 'confidence': regime_conf, 'regime': regime_name},
                'stock': {'probability': stock_prob, 'confidence': stock_conf},
                'risk': {'action': risk_action, 'size': risk_size, 'reasons': risk_reasons},
            },
        }

        logger.info(
            "Arbiter: %s (conf=%.0f%% size=%.0f%%) | regime=%s stock=%.0f%% risk=%s",
            decision, confidence, position_size * 100,
            'TRADE' if regime_trade else 'SKIP', stock_prob * 100, risk_action,
        )
        return result
