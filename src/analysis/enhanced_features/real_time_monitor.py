"""
Feature 1: Real-Time Price Action + Entry Readiness
Monitors current price and determines entry readiness based on multiple conditions
"""

from typing import Dict, Any, Optional
from datetime import datetime


class RealTimePriceMonitor:
    """
    Monitor real-time price action and calculate entry readiness

    Features:
    - Distance to entry zone
    - Entry conditions checklist
    - Readiness score (0-100)
    - Action recommendations
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def analyze(
        self,
        current_price: float,
        entry_zone: tuple,
        support: float,
        resistance: float,
        rsi: float,
        volume_vs_avg: float,
        market_regime: str,
        target_rsi_threshold: float = 50,
        volume_threshold: float = 0.8
    ) -> Dict[str, Any]:
        """
        Analyze real-time price action and entry readiness

        Args:
            current_price: Current market price
            entry_zone: (low, high) recommended entry range
            support: Support level
            resistance: Resistance level
            rsi: Current RSI value
            volume_vs_avg: Volume ratio vs average (e.g., 1.5 = 150% of average)
            market_regime: 'sideways', 'uptrend', 'downtrend'
            target_rsi_threshold: RSI must be below this (default 50 for sideways)
            volume_threshold: Minimum volume ratio (default 0.8 = 80% of average)

        Returns:
            Dictionary with analysis results
        """
        entry_low, entry_high = entry_zone

        # Calculate distances
        distance_to_entry_low = ((current_price - entry_low) / entry_low) * 100
        distance_to_entry_high = ((current_price - entry_high) / entry_high) * 100
        distance_to_support = ((current_price - support) / support) * 100
        distance_to_resistance = ((current_price - resistance) / resistance) * 100

        # Check if price is in entry zone
        price_in_zone = entry_low <= current_price <= entry_high

        # Entry conditions checklist
        conditions = {
            "price_in_zone": {
                "passed": price_in_zone,
                "value": f"${current_price:.2f}",
                "target": f"${entry_low:.2f}-${entry_high:.2f}",
                "message": "ราคาอยู่ใน zone" if price_in_zone else f"ราคาห่างรับ {abs(distance_to_entry_low):.1f}%"
            },
            "rsi_ready": {
                "passed": rsi < target_rsi_threshold,
                "value": f"{rsi:.1f}",
                "target": f"< {target_rsi_threshold}",
                "message": "RSI พร้อม" if rsi < target_rsi_threshold else f"รอ RSI ต่ำกว่า {target_rsi_threshold}"
            },
            "volume_confirmed": {
                "passed": volume_vs_avg >= volume_threshold,
                "value": f"{volume_vs_avg*100:.0f}%",
                "target": f">= {volume_threshold*100:.0f}%",
                "message": "Volume ดี" if volume_vs_avg >= volume_threshold else "Volume อ่อน"
            },
            "market_regime_ok": {
                "passed": market_regime in ['sideways', 'uptrend'],
                "value": market_regime,
                "target": "sideways/uptrend",
                "message": f"ตลาด {market_regime}"
            }
        }

        # Calculate readiness score
        passed_conditions = sum(1 for c in conditions.values() if c["passed"])
        total_conditions = len(conditions)
        readiness_score = int((passed_conditions / total_conditions) * 100)

        # Determine action
        if readiness_score >= 75:
            action = "BUY NOW"
            action_color = "🟢"
            status = "READY"
        elif readiness_score >= 50:
            action = "READY"
            action_color = "🟡"
            status = "READY"
        else:
            action = "WAIT"
            action_color = "🔴"
            status = "WAIT"

        # Determine what to wait for
        next_triggers = []
        if not price_in_zone:
            next_triggers.append({
                "type": "price",
                "target": entry_high if current_price > entry_high else entry_low,
                "current": current_price,
                "distance_pct": abs(distance_to_entry_low if current_price > entry_high else distance_to_entry_high)
            })

        if not conditions["rsi_ready"]["passed"]:
            next_triggers.append({
                "type": "rsi",
                "target": target_rsi_threshold,
                "current": rsi,
                "distance": rsi - target_rsi_threshold
            })

        # Estimate wait time (simple heuristic)
        if not price_in_zone:
            distance_pct = abs(distance_to_entry_low)
            if distance_pct < 2:
                estimated_wait = "ไม่กี่ชั่วโมง"
            elif distance_pct < 5:
                estimated_wait = "1-2 วัน"
            else:
                estimated_wait = "2-5 วัน"
        else:
            estimated_wait = "พร้อมแล้ว"

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "current_price": current_price,
            "entry_zone": {
                "low": entry_low,
                "high": entry_high,
                "in_zone": price_in_zone
            },
            "distances": {
                "to_entry_low_pct": distance_to_entry_low,
                "to_entry_high_pct": distance_to_entry_high,
                "to_support_pct": distance_to_support,
                "to_resistance_pct": distance_to_resistance
            },
            "key_levels": {
                "support": support,
                "resistance": resistance,
                "entry_low": entry_low,
                "entry_high": entry_high
            },
            "conditions": conditions,
            "readiness": {
                "score": readiness_score,
                "passed": passed_conditions,
                "total": total_conditions,
                "status": status,
                "action": action,
                "action_color": action_color
            },
            "next_action": {
                "triggers": next_triggers,
                "estimated_wait": estimated_wait
            },
            "display": self._format_display(
                current_price, entry_zone, support, resistance,
                conditions, readiness_score, action, action_color,
                next_triggers, estimated_wait, distance_to_support,
                distance_to_resistance
            )
        }

    def _format_display(
        self, current_price, entry_zone, support, resistance,
        conditions, score, action, color, triggers, wait,
        dist_support, dist_resistance
    ) -> Dict[str, str]:
        """Format display strings for UI"""

        entry_low, entry_high = entry_zone

        # Build checklist display
        checklist_lines = []
        for key, cond in conditions.items():
            symbol = "✅" if cond["passed"] else "❌"
            checklist_lines.append(f"{symbol} {cond['message']}")

        # Build next action message
        if not triggers:
            next_msg = "✅ พร้อมเข้าได้!"
        else:
            trigger_msgs = []
            for t in triggers:
                if t["type"] == "price":
                    trigger_msgs.append(f"ราคาลง → ${t['target']:.2f}")
                elif t["type"] == "rsi":
                    trigger_msgs.append(f"RSI ลง < {t['target']:.0f}")
            next_msg = " หรือ ".join(trigger_msgs)

        return {
            "header": f"{color} {action}",
            "price_status": f"📍 ${current_price:.2f}",
            "entry_zone": f"🎯 ${entry_low:.2f} - ${entry_high:.2f}",
            "checklist": "\n".join(checklist_lines),
            "score": f"Entry Score: {score}/100",
            "next_action": next_msg,
            "estimated_wait": f"⏰ {wait}",
            "support_distance": f"Support (${support:.2f}): {abs(dist_support):.1f}% {'⬇️' if dist_support > 0 else '⬆️'}",
            "resistance_distance": f"Resistance (${resistance:.2f}): {abs(dist_resistance):.1f}% {'⬆️' if dist_resistance > 0 else '⬇️'}"
        }


def format_real_time_monitor(result: Dict[str, Any]) -> str:
    """
    Format Real-Time Monitor result as text display

    Args:
        result: Output from RealTimePriceMonitor.analyze()

    Returns:
        Formatted string for display
    """
    d = result["display"]
    r = result["readiness"]

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚦 ENTRY READINESS DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{d['header']}
Status: {r['status']}

{d['price_status']}
{d['entry_zone']}

✅ Entry Conditions ({r['passed']}/{r['total']} Passed)
{d['checklist']}

{d['score']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Key Levels:
{d['support_distance']}
{d['resistance_distance']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Next Action:
{d['next_action']}
{d['estimated_wait']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return output
