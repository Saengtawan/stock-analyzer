"""
Feature 6: Risk Status Change Alert Manager
Monitor risk changes and alert when conditions deteriorate

Tracks:
- R:R ratio changes
- Volatility spikes
- Volume drops
- Market regime changes
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class RiskAlertManager:
    """
    Monitor and alert on risk status changes

    Features:
    - R:R deterioration alerts
    - Volatility spike warnings
    - Volume drop alerts
    - Market regime change notifications
    - Overall risk score tracking
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def analyze(
        self,
        # Current metrics
        current_rr: Optional[float] = None,
        entry_rr: Optional[float] = None,

        # Volatility
        current_atr: Optional[float] = None,
        entry_atr: Optional[float] = None,
        current_vix: Optional[float] = None,
        entry_vix: Optional[float] = None,

        # Volume
        current_volume_ratio: Optional[float] = None,
        avg_volume_ratio: float = 1.0,

        # Market
        current_regime: Optional[str] = None,
        expected_regime: Optional[str] = None,

        # Additional
        profit_pct: Optional[float] = None,
        days_held: int = 0

    ) -> Dict[str, Any]:
        """
        Analyze risk status and generate alerts

        Returns alerts and risk score
        """

        alerts = []
        risk_changes = []

        # 1. Check R:R deterioration
        if current_rr is not None and entry_rr is not None:
            rr_alert = self._check_rr_deterioration(
                entry_rr, current_rr
            )
            if rr_alert:
                alerts.append(rr_alert)
                risk_changes.append("R:R deteriorated")

        # 2. Check volatility spike
        if current_atr and entry_atr:
            atr_change = ((current_atr - entry_atr) / entry_atr) * 100
            if atr_change > 30:
                alerts.append({
                    "severity": "MEDIUM",
                    "type": "VOLATILITY_SPIKE",
                    "message": f"ATR increased {atr_change:.0f}%",
                    "action": "Consider tightening stop loss"
                })
                risk_changes.append(f"Volatility +{atr_change:.0f}%")

        if current_vix and entry_vix:
            vix_change = ((current_vix - entry_vix) / entry_vix) * 100
            if vix_change > 20:
                alerts.append({
                    "severity": "MEDIUM",
                    "type": "VIX_SPIKE",
                    "message": f"VIX increased {vix_change:.0f}%",
                    "action": "Market fear increasing - reduce risk"
                })
                risk_changes.append(f"VIX +{vix_change:.0f}%")

        # 3. Check volume drop
        if current_volume_ratio is not None and current_volume_ratio < 0.5:
            alerts.append({
                "severity": "LOW",
                "type": "VOLUME_DROP",
                "message": f"Volume only {current_volume_ratio*100:.0f}% of average",
                "action": "Low conviction - watch for breakdown"
            })
            risk_changes.append("Volume dried up")

        # 4. Check market regime change
        if current_regime and expected_regime and current_regime != expected_regime:
            # Convert regime to readable format
            regime_readable = str(current_regime).replace('_', ' ').title()
            expected_readable = str(expected_regime).replace('_', ' ').title()

            alerts.append({
                "severity": "HIGH" if "down" in str(current_regime).lower() or "bear" in str(current_regime).lower() else "MEDIUM",
                "type": "REGIME_CHANGE",
                "message": f"Market changed from {expected_readable} to {regime_readable}",
                "action": "Reassess position validity"
            })
            risk_changes.append(f"Regime: {expected_readable} → {regime_readable}")

        # 5. Check time decay
        if profit_pct is not None and profit_pct < 2 and days_held > 7:
            alerts.append({
                "severity": "MEDIUM",
                "type": "TIME_DECAY",
                "message": f"Held {days_held} days with minimal profit ({profit_pct:.1f}%)",
                "action": "Consider exiting for better opportunities"
            })
            risk_changes.append("Time decay issue")

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            current_rr, current_volume_ratio, len(alerts)
        )

        # Determine overall status
        if risk_score >= 7:
            status = "HIGH RISK"
            status_emoji = "🔴"
        elif risk_score >= 5:
            status = "ELEVATED RISK"
            status_emoji = "🟡"
        elif risk_score >= 3:
            status = "MODERATE"
            status_emoji = "🟡"
        else:
            status = "LOW RISK"
            status_emoji = "🟢"

        # Recommended actions
        actions = self._get_recommended_actions(alerts, risk_score)

        # Format display
        display = self._format_display(
            alerts, risk_score, status, status_emoji, risk_changes, actions
        )

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "risk_score": {
                "current": risk_score,
                "status": status,
                "emoji": status_emoji
            },
            "alerts": alerts,
            "risk_changes": risk_changes,
            "recommended_actions": actions,
            "display": display
        }

    def _check_rr_deterioration(
        self, entry_rr: float, current_rr: float
    ) -> Optional[Dict[str, Any]]:
        """Check if R:R has deteriorated significantly"""

        deterioration = entry_rr - current_rr
        deterioration_pct = (deterioration / entry_rr) * 100 if entry_rr > 0 else 0

        if deterioration > 2.0:
            return {
                "severity": "HIGH",
                "type": "RR_DETERIORATION",
                "message": f"R:R dropped from {entry_rr:.1f}:1 to {current_rr:.1f}:1",
                "action": "Take profit or move stop loss up"
            }
        elif deterioration > 1.0:
            return {
                "severity": "MEDIUM",
                "type": "RR_DETERIORATION",
                "message": f"R:R dropped from {entry_rr:.1f}:1 to {current_rr:.1f}:1",
                "action": "Consider partial exit"
            }

        return None

    def _calculate_risk_score(
        self,
        rr: Optional[float],
        volume_ratio: Optional[float],
        alert_count: int
    ) -> float:
        """Calculate overall risk score (0-10, higher = more risk)"""

        score = 3.0  # Base score

        # R:R factor
        if rr is not None:
            if rr < 0.5:
                score += 3.0
            elif rr < 1.0:
                score += 2.0
            elif rr < 1.5:
                score += 1.0

        # Volume factor
        if volume_ratio is not None:
            if volume_ratio < 0.5:
                score += 1.5
            elif volume_ratio < 0.8:
                score += 0.5

        # Alert factor
        score += min(alert_count * 0.5, 2.5)

        return min(score, 10.0)

    def _get_recommended_actions(
        self, alerts: List[Dict], risk_score: float
    ) -> List[str]:
        """Get recommended actions based on alerts and risk"""

        actions = []

        # Collect unique actions from alerts
        for alert in alerts:
            if alert["action"] and alert["action"] not in actions:
                actions.append(alert["action"])

        # Add general recommendations based on risk
        if risk_score >= 7:
            if "Exit position immediately" not in actions:
                actions.append("Consider exiting position")
        elif risk_score >= 5:
            if "Reduce position size" not in actions and "Take profit" not in actions:
                actions.append("Monitor closely, consider reducing exposure")

        return actions[:3]  # Top 3 actions only

    def _format_display(
        self, alerts, score, status, emoji, changes, actions
    ) -> Dict[str, str]:
        """Format display strings"""

        # Sort alerts by severity
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        sorted_alerts = sorted(
            alerts,
            key=lambda x: severity_order.get(x["severity"], 3)
        )

        return {
            "status": f"{emoji} {status}",
            "score": f"{score:.1f}/10",
            "alert_count": f"{len(alerts)} active warnings",
            "alerts": sorted_alerts,
            "changes": changes,
            "actions": actions
        }


def format_risk_alerts(result: Dict[str, Any]) -> str:
    """Format Risk Alerts result as text display"""

    d = result["display"]
    risk = result["risk_score"]
    alerts = result["alerts"]
    changes = result["risk_changes"]
    actions = result["recommended_actions"]

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ RISK CHANGE ALERTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{d['status']}
Risk Score: {d['score']}

"""

    # Show alerts
    if alerts:
        output += f"🚨 {d['alert_count'].upper()}\n\n"

        for i, alert in enumerate(d['alerts'], 1):
            severity_emoji = {
                "HIGH": "🔴",
                "MEDIUM": "🟡",
                "LOW": "⚪"
            }.get(alert["severity"], "⚪")

            output += f"{i}. {severity_emoji} {alert['type'].replace('_', ' ').title()}\n"
            output += f"   {alert['message']}\n"
            output += f"   💡 {alert['action']}\n\n"
    else:
        output += "✅ No active warnings\n\n"

    # Show risk changes
    if changes:
        output += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        output += "📊 Risk Changes Detected:\n"
        for change in changes:
            output += f"   • {change}\n"
        output += "\n"

    # Show recommended actions
    if actions:
        output += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        output += "💡 Recommended Actions:\n"
        for i, action in enumerate(actions, 1):
            output += f"   {i}. {action}\n"
        output += "\n"

    output += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    return output
