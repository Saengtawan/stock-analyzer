"""
Feature 5: Decision Matrix
AI-powered decision engine that combines all factors to recommend specific actions

This is the CORE feature that ties everything together!
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class DecisionMatrix:
    """
    Comprehensive decision engine combining all analysis factors

    Inputs from all other features:
    - Entry readiness
    - P&L status
    - Trailing stop recommendation
    - Short interest
    - Risk alerts

    Output: Clear BUY/SELL/HOLD action with confidence and reasoning
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def analyze(
        self,
        # Position status
        has_position: bool,
        entry_price: Optional[float] = None,
        current_price: Optional[float] = None,
        profit_pct: Optional[float] = None,
        holding_days: int = 0,

        # Entry signals (if no position)
        entry_readiness_score: Optional[int] = None,
        entry_conditions_passed: Optional[int] = None,

        # Targets and risk
        progress_to_tp1: Optional[float] = None,
        current_rr: Optional[float] = None,
        stop_loss: Optional[float] = None,

        # Market conditions
        rsi: Optional[float] = None,
        volume_vs_avg: Optional[float] = None,
        market_regime: Optional[str] = None,

        # Additional factors
        selling_pressure: Optional[float] = None,
        distance_to_resistance_pct: Optional[float] = None,

        # Timeframe
        target_hold_days: int = 14

    ) -> Dict[str, Any]:
        """
        Make trading decision based on all available factors

        Returns comprehensive recommendation with reasoning
        """

        if not has_position:
            # Decision for ENTRY
            decision = self._decide_entry(
                entry_readiness_score,
                entry_conditions_passed,
                rsi,
                volume_vs_avg,
                market_regime
            )
        else:
            # Decision for EXIT
            decision = self._decide_exit(
                profit_pct,
                progress_to_tp1,
                current_rr,
                holding_days,
                target_hold_days,
                rsi,
                selling_pressure,
                distance_to_resistance_pct,
                current_price,
                stop_loss
            )

        # Format display
        display = self._format_display(decision)

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "has_position": has_position,
            "decision": decision,
            "display": display
        }

    def _decide_entry(
        self,
        readiness_score: Optional[int],
        conditions_passed: Optional[int],
        rsi: Optional[float],
        volume: Optional[float],
        regime: Optional[str]
    ) -> Dict[str, Any]:
        """Decision logic for ENTRY"""

        reasons_for = []
        reasons_against = []
        confidence = 50

        # Check entry readiness
        if readiness_score and readiness_score >= 75:
            reasons_for.append("Entry readiness score high (>75)")
            confidence += 20
        elif readiness_score and readiness_score >= 50:
            reasons_for.append("Entry readiness moderate (>50)")
            confidence += 10
        else:
            reasons_against.append("Entry conditions not met")
            confidence -= 15

        # Check RSI
        if rsi and rsi < 45:
            reasons_for.append(f"RSI oversold ({rsi:.0f})")
            confidence += 15
        elif rsi and rsi > 60:
            reasons_against.append(f"RSI overbought ({rsi:.0f})")
            confidence -= 10

        # Check volume
        if volume and volume > 1.0:
            reasons_for.append(f"Volume strong ({volume*100:.0f}%)")
            confidence += 10

        # Determine action
        if confidence >= 70:
            action = "BUY NOW"
            action_plan = ["Enter position at current levels", "Set stop loss as recommended", "Target TP1 first"]
        elif confidence >= 50:
            action = "READY - Wait for entry zone"
            action_plan = ["Wait for price to reach entry zone", "Confirm RSI < 50", "Enter on next pullback"]
        else:
            action = "WAIT"
            action_plan = ["Wait for better setup", "Monitor for improved conditions", "Be patient"]

        return {
            "action": action,
            "confidence": max(0, min(100, confidence)),
            "reasons_for": reasons_for,
            "reasons_against": reasons_against,
            "action_plan": action_plan
        }

    def _decide_exit(
        self,
        profit_pct: Optional[float],
        progress_tp1: Optional[float],
        rr: Optional[float],
        holding_days: int,
        target_days: int,
        rsi: Optional[float],
        selling_pressure: Optional[float],
        dist_resistance: Optional[float],
        current_price: Optional[float],
        stop_loss: Optional[float]
    ) -> Dict[str, Any]:
        """Decision logic for EXIT (most complex!)"""

        reasons_for_selling = []
        reasons_for_holding = []
        confidence = 50
        action_plan = []

        # Check profit level
        if profit_pct is not None:
            if profit_pct > 10:
                reasons_for_selling.append(f"Strong profit ({profit_pct:.1f}%)")
                confidence += 25
            elif profit_pct > 5:
                reasons_for_selling.append(f"Good profit ({profit_pct:.1f}%)")
                confidence += 15
            elif profit_pct > 3:
                reasons_for_holding.append(f"Moderate profit ({profit_pct:.1f}%)")
            elif profit_pct < 0:
                reasons_for_selling.append(f"In loss ({profit_pct:.1f}%)")
                confidence += 20

        # Check progress to TP1
        if progress_tp1 is not None:
            if progress_tp1 > 80:
                reasons_for_selling.append(f"Near TP1 ({progress_tp1:.0f}%)")
                confidence += 15
            elif progress_tp1 < 30:
                reasons_for_holding.append(f"Far from TP1 ({progress_tp1:.0f}%)")
                confidence -= 10

        # Check R:R ratio
        if rr is not None:
            if rr < 1.0:
                reasons_for_selling.append(f"Poor R:R ({rr:.2f}:1)")
                confidence += 20
            elif rr > 2.0:
                reasons_for_holding.append(f"Good R:R ({rr:.2f}:1)")
                confidence -= 15

        # Check holding period
        if holding_days > target_days:
            reasons_for_selling.append(f"Held too long ({holding_days}/{target_days} days)")
            confidence += 15
        elif holding_days > target_days * 0.7:
            reasons_for_selling.append(f"Approaching max hold ({holding_days}/{target_days} days)")
            confidence += 10

        # Check technical indicators
        if rsi and rsi > 70:
            reasons_for_selling.append(f"RSI overbought ({rsi:.0f})")
            confidence += 10

        if selling_pressure and selling_pressure > 60:
            reasons_for_selling.append(f"Selling pressure high ({selling_pressure:.0f}%)")
            confidence += 10

        if dist_resistance is not None and abs(dist_resistance) < 2:
            reasons_for_selling.append(f"Near resistance ({abs(dist_resistance):.1f}%)")
            confidence += 10

        # Determine action
        if confidence >= 75:
            # Strong SELL signal
            if profit_pct and profit_pct > 5:
                action = "SELL ALL"
                action_plan = [
                    f"Exit entire position @ current price",
                    f"Lock in profit of {profit_pct:.1f}%",
                    "Move to next opportunity"
                ]
            else:
                action = "SELL ALL (Cut Loss)"
                action_plan = [
                    "Exit to prevent further loss",
                    "Better opportunities elsewhere",
                    "Reassess strategy"
                ]

        elif confidence >= 60:
            # Partial SELL
            action = "PARTIAL EXIT"
            sell_pct = 50
            action_plan = [
                f"Sell {sell_pct}% @ current price",
                "Move SL to breakeven+",
                f"Hold {100-sell_pct}% for TP2"
            ]

        elif confidence >= 45:
            # HOLD but watch
            action = "HOLD (Monitor Closely)"
            action_plan = [
                "Continue holding",
                "Move trailing stop as recommended",
                "Exit if conditions change"
            ]

        else:
            # Strong HOLD
            action = "HOLD"
            action_plan = [
                "Keep position",
                "Let it run to target",
                "Maintain stop loss"
            ]

        # Add exit conditions
        exit_conditions = []
        if stop_loss:
            exit_conditions.append(f"Price < ${stop_loss:.2f}")
        if holding_days < target_days:
            exit_conditions.append(f"Hold > {target_days} days + sideways")
        exit_conditions.append("TP2 reached")

        return {
            "action": action,
            "confidence": max(0, min(100, confidence)),
            "reasons_for_selling": reasons_for_selling,
            "reasons_for_holding": reasons_for_holding,
            "action_plan": action_plan,
            "exit_conditions": exit_conditions
        }

    def _format_display(self, decision: Dict[str, Any]) -> Dict[str, str]:
        """Format display strings"""

        action = decision["action"]
        confidence = decision["confidence"]

        # Action emoji
        if "BUY" in action:
            emoji = "🟢"
        elif "SELL" in action or "EXIT" in action:
            emoji = "🔴"
        elif "WAIT" in action:
            emoji = "⚪"
        else:
            emoji = "🟡"

        # Confidence bar
        bar_length = 10
        filled = int((confidence / 100) * bar_length)
        conf_bar = "█" * filled + "░" * (bar_length - filled)

        # Reasons
        if "reasons_for" in decision:
            reasons = decision["reasons_for"]
        elif "reasons_for_selling" in decision:
            reasons = decision["reasons_for_selling"] + decision["reasons_for_holding"]
        else:
            reasons = []

        return {
            "action_header": f"{emoji} {action}",
            "confidence": f"{confidence}%",
            "confidence_bar": conf_bar,
            "reasons": reasons,
            "action_plan": decision["action_plan"]
        }


def format_decision_matrix(result: Dict[str, Any]) -> str:
    """Format Decision Matrix result as text display"""

    d = result["display"]
    decision = result["decision"]
    has_pos = result["has_position"]

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 DECISION MATRIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{d['action_header']}
Confidence: {d['confidence']} [{d['confidence_bar']}]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

    # Show reasons
    if has_pos:
        if decision.get("reasons_for_selling"):
            output += "✅ Reasons to Sell:\n"
            for reason in decision["reasons_for_selling"]:
                output += f"   • {reason}\n"
            output += "\n"

        if decision.get("reasons_for_holding"):
            output += "⚠️ Reasons to Hold:\n"
            for reason in decision["reasons_for_holding"]:
                output += f"   • {reason}\n"
            output += "\n"
    else:
        if decision.get("reasons_for"):
            output += "✅ Reasons to Enter:\n"
            for reason in decision["reasons_for"]:
                output += f"   • {reason}\n"
            output += "\n"

        if decision.get("reasons_against"):
            output += "⚠️ Reasons to Wait:\n"
            for reason in decision["reasons_against"]:
                output += f"   • {reason}\n"
            output += "\n"

    # Action plan
    output += "📋 Action Plan:\n"
    for i, step in enumerate(decision["action_plan"], 1):
        output += f"   {i}. {step}\n"

    # Exit conditions (if holding position)
    if has_pos and decision.get("exit_conditions"):
        output += "\n🚨 Exit ALL if:\n"
        for cond in decision["exit_conditions"]:
            output += f"   • {cond}\n"

    output += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    return output
