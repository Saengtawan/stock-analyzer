"""
Feature 3: Trailing Stop Loss Manager
Dynamic stop loss adjustment based on profit level

Automatically recommends when to move stop loss to protect profits
"""

from typing import Dict, Any, Optional
from datetime import datetime


class TrailingStopManager:
    """
    Manage trailing stop loss recommendations

    Rules:
    - Profit < 2%: Keep original SL
    - Profit 2-5%: Move to breakeven
    - Profit 5-10%: Lock 50% profit
    - Profit > 10%: Lock 70% profit
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def analyze(
        self,
        entry_price: float,
        current_price: float,
        original_sl: float,
        shares: int = 100
    ) -> Dict[str, Any]:
        """
        Calculate trailing stop recommendation

        Args:
            entry_price: Entry price
            current_price: Current market price
            original_sl: Original stop loss price
            shares: Number of shares

        Returns:
            Dictionary with trailing stop analysis
        """

        # Defensive checks - validate all inputs
        if entry_price is None or entry_price == 0:
            entry_price = current_price * 0.98  # Fallback: assume 2% profit
        if current_price is None or current_price == 0:
            current_price = entry_price * 1.02  # Fallback
        if original_sl is None or original_sl == 0:
            original_sl = entry_price * 0.95  # Fallback: 5% below entry

        # Calculate current profit
        profit_dollars = current_price - entry_price
        profit_pct = (profit_dollars / entry_price) * 100

        # Calculate new stop loss based on profit level
        sl_data = self._calculate_trailing_stop(
            entry_price, current_price, profit_pct
        )

        new_sl = sl_data["new_sl"]
        rule = sl_data["rule"]
        lock_pct = sl_data["lock_pct"]

        # If new_sl is None, use original_sl (profit < 2%)
        if new_sl is None:
            new_sl = original_sl

        # Calculate locked profit
        if new_sl is not None and new_sl > entry_price:
            locked_profit_per_share = new_sl - entry_price
            locked_profit_total = locked_profit_per_share * shares
            locked_profit_pct = (locked_profit_per_share / entry_price) * 100
        else:
            locked_profit_per_share = 0
            locked_profit_total = 0
            locked_profit_pct = 0

        # Determine if SL should be moved
        should_move = new_sl != original_sl and profit_pct > 2

        # Next update trigger
        next_trigger = self._get_next_trigger(profit_pct, current_price, entry_price)

        # Format display
        display = self._format_display(
            original_sl, new_sl, should_move, rule,
            locked_profit_per_share, locked_profit_total,
            locked_profit_pct, profit_pct, next_trigger
        )

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "entry_price": entry_price,
            "current_price": current_price,
            "profit_pct": profit_pct,
            "original_sl": original_sl,
            "recommended_sl": new_sl,
            "should_move": should_move,
            "rule": rule,
            "lock_percentage": lock_pct,
            "locked_profit": {
                "per_share": locked_profit_per_share,
                "total": locked_profit_total,
                "percentage": locked_profit_pct
            },
            "next_trigger": next_trigger,
            "display": display
        }

    def _calculate_trailing_stop(
        self,
        entry: float,
        current: float,
        profit_pct: float
    ) -> Dict[str, Any]:
        """
        Calculate new stop loss based on profit percentage

        Returns:
            Dictionary with new_sl, rule, and lock_pct
        """

        profit = current - entry

        if profit_pct < 2:
            # Keep original SL
            return {
                "new_sl": None,  # Will use original
                "rule": "< 2% profit: Keep original SL",
                "lock_pct": 0
            }

        elif profit_pct < 5:
            # Move to breakeven + small buffer
            new_sl = entry * 1.001  # +0.1% above entry
            return {
                "new_sl": new_sl,
                "rule": "2-5% profit: Breakeven+",
                "lock_pct": 0
            }

        elif profit_pct < 10:
            # Lock 50% of profit
            new_sl = entry + (profit * 0.5)
            return {
                "new_sl": new_sl,
                "rule": "5-10% profit: Lock 50%",
                "lock_pct": 50
            }

        else:
            # Lock 70% of profit
            new_sl = entry + (profit * 0.7)
            return {
                "new_sl": new_sl,
                "rule": "> 10% profit: Lock 70%",
                "lock_pct": 70
            }

    def _get_next_trigger(
        self,
        current_profit_pct: float,
        current_price: float,
        entry_price: float
    ) -> Optional[Dict[str, Any]]:
        """Calculate next SL update trigger"""

        if current_profit_pct < 2:
            # Next trigger at 2%
            target_price = entry_price * 1.02
            return {
                "profit_pct": 2.0,
                "price": target_price,
                "action": "Move to breakeven+"
            }

        elif current_profit_pct < 5:
            # Next trigger at 5%
            target_price = entry_price * 1.05
            return {
                "profit_pct": 5.0,
                "price": target_price,
                "action": "Lock 50% profit"
            }

        elif current_profit_pct < 10:
            # Next trigger at 10%
            target_price = entry_price * 1.10
            return {
                "profit_pct": 10.0,
                "price": target_price,
                "action": "Lock 70% profit"
            }

        else:
            # Already at max, no next trigger
            return None

    def _format_display(
        self, original_sl, new_sl, should_move, rule,
        lock_per_share, lock_total, lock_pct, profit_pct, next_trigger
    ) -> Dict[str, str]:
        """Format display strings"""

        if should_move:
            recommendation = f"🔒 MOVE SL NOW!"
            recommendation_detail = f"Reason: {rule}"
        else:
            recommendation = "Keep original SL"
            recommendation_detail = "Not enough profit yet"

        if lock_total > 0:
            locked_info = f"${lock_per_share:.2f}/share (${lock_total:.0f} total)"
        else:
            locked_info = "None yet"

        if next_trigger:
            next_info = f"@ ${next_trigger['price']:.2f} (+{next_trigger['profit_pct']:.0f}%): {next_trigger['action']}"
        else:
            next_info = "Max protection reached"

        return {
            "recommendation": recommendation,
            "recommendation_detail": recommendation_detail,
            "original_sl": f"${original_sl:.2f}" if original_sl else "N/A",
            "new_sl": f"${new_sl:.2f}" if new_sl else "Keep original",
            "rule": rule,
            "locked_profit": locked_info,
            "locked_pct": f"{lock_pct:.0f}%" if lock_pct > 0 else "0%",
            "next_trigger": next_info
        }


def format_trailing_stop(result: Dict[str, Any]) -> str:
    """Format Trailing Stop result as text display"""

    d = result["display"]
    original = result["original_sl"]
    recommended = result["recommended_sl"]
    should_move = result["should_move"]

    status_emoji = "🟢" if should_move else "⚪"

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ TRAILING STOP MANAGER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{status_emoji} {d['recommendation']}
{d['recommendation_detail']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Stop Loss Levels:
├─ Original SL:  {d['original_sl']}
└─ Recommended:  {d['new_sl']}

🔒 Locked Profit: {d['locked_profit']}
   ({d['locked_pct']} of total profit)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Stop Loss Roadmap:
"""

    # Show current rule
    output += f"✅ Current: {d['rule']}\n"

    # Show next trigger
    if result["next_trigger"]:
        output += f"⏳ Next: {d['next_trigger']}\n"
    else:
        output += "🏁 Max protection reached\n"

    output += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Never let a winner turn into a loser!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    return output
