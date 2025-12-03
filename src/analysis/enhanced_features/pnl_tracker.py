"""
Feature 2: P&L Tracker + Target Progress (Auto-Entry)
Auto-calculates entry price and tracks profit/loss to targets

No need for user to input entry price - system auto-detects!
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd


class ProfitLossTracker:
    """
    Track P&L with automatic entry price detection

    Features:
    - Auto-detect entry price (signal date or mid-point)
    - Calculate unrealized P&L
    - Progress to TP1, TP2
    - Risk metrics
    - Alternative scenarios (optional)
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def analyze(
        self,
        current_price: float,
        entry_zone: tuple,
        tp1: float,
        tp2: float,
        stop_loss: float,
        signal_date: Optional[str] = None,
        shares: int = 100,
        custom_entry: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyze P&L with auto-detected entry price

        Args:
            current_price: Current market price
            entry_zone: (low, high) recommended entry range
            tp1: Take profit target 1
            tp2: Take profit target 2
            stop_loss: Stop loss price
            signal_date: Date when BUY signal was generated (YYYY-MM-DD)
            shares: Number of shares (for dollar calculations)
            custom_entry: Custom entry price (optional override)

        Returns:
            Dictionary with P&L analysis
        """

        # Auto-detect entry price
        entry_data = self._get_entry_price(
            entry_zone, signal_date, custom_entry
        )

        entry_price = entry_data["price"]
        entry_method = entry_data["method"]

        # Calculate P&L
        profit_dollars = current_price - entry_price
        profit_pct = (profit_dollars / entry_price) * 100

        total_profit_dollars = profit_dollars * shares

        # Calculate progress to targets
        entry_to_tp1 = tp1 - entry_price
        current_to_tp1 = current_price - entry_price
        progress_to_tp1 = (current_to_tp1 / entry_to_tp1) * 100 if entry_to_tp1 > 0 else 0

        entry_to_tp2 = tp2 - entry_price
        current_to_tp2 = current_price - entry_price
        progress_to_tp2 = (current_to_tp2 / entry_to_tp2) * 100 if entry_to_tp2 > 0 else 0

        # Remaining to targets
        remaining_to_tp1_pct = ((tp1 - current_price) / current_price) * 100
        remaining_to_tp1_dollars = tp1 - current_price

        remaining_to_tp2_pct = ((tp2 - current_price) / current_price) * 100
        remaining_to_tp2_dollars = tp2 - current_price

        # Risk metrics
        max_loss_dollars = stop_loss - entry_price
        max_loss_pct = (max_loss_dollars / entry_price) * 100

        max_gain_to_tp2_dollars = tp2 - entry_price
        max_gain_to_tp2_pct = (max_gain_to_tp2_dollars / entry_price) * 100

        # Current R:R (remaining upside vs downside)
        upside_to_tp1 = tp1 - current_price
        downside_to_sl = current_price - stop_loss
        current_rr = upside_to_tp1 / downside_to_sl if downside_to_sl > 0 else 0

        # Get alternative scenarios
        alternatives = self._get_alternative_scenarios(
            entry_zone, signal_date, current_price, entry_price
        )

        # Calculate historical probability for targets
        tp1_probability = self._calculate_historical_probability(tp1, period_days=60)
        tp2_probability = self._calculate_historical_probability(tp2, period_days=60)

        # Format display
        display = self._format_display(
            entry_price, entry_method, current_price, profit_pct,
            total_profit_dollars, shares, tp1, tp2, progress_to_tp1,
            progress_to_tp2, remaining_to_tp1_pct, remaining_to_tp1_dollars,
            entry_data
        )

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "entry": {
                "price": entry_price,
                "method": entry_method,
                "description": entry_data["description"],
                "source": entry_data["source"],
                "signal_date": entry_data.get("signal_date")
            },
            "current": {
                "price": current_price,
                "profit_dollars": profit_dollars,
                "profit_pct": profit_pct,
                "total_profit_dollars": total_profit_dollars,
                "shares": shares
            },
            "targets": {
                "tp1": {
                    "price": tp1,
                    "progress_pct": progress_to_tp1,
                    "remaining_pct": remaining_to_tp1_pct,
                    "remaining_dollars": remaining_to_tp1_dollars,
                    "probability": tp1_probability  # Add historical probability
                },
                "tp2": {
                    "price": tp2,
                    "progress_pct": progress_to_tp2,
                    "remaining_pct": remaining_to_tp2_pct,
                    "remaining_dollars": remaining_to_tp2_dollars,
                    "probability": tp2_probability  # Add historical probability
                }
            },
            "risk": {
                "stop_loss": stop_loss,
                "max_loss_dollars": max_loss_dollars,
                "max_loss_pct": max_loss_pct,
                "max_gain_dollars": max_gain_to_tp2_dollars,
                "max_gain_pct": max_gain_to_tp2_pct,
                "current_rr": current_rr
            },
            "alternatives": alternatives,
            "display": display
        }

    def _get_entry_price(
        self,
        entry_zone: tuple,
        signal_date: Optional[str],
        custom_entry: Optional[float]
    ) -> Dict[str, Any]:
        """
        Auto-detect entry price with priority:
        1. Custom (if provided)
        2. Signal next day open (if signal_date available)
        3. Mid-point (fallback)
        """

        entry_low, entry_high = entry_zone
        midpoint = (entry_low + entry_high) / 2

        # Priority 1: Custom
        if custom_entry is not None:
            return {
                "price": custom_entry,
                "method": "Custom",
                "description": f"Your entry: ${custom_entry:.2f}",
                "source": "user_input"
            }

        # Priority 2: Signal next day open
        if signal_date:
            try:
                next_day = self._get_next_trading_day(signal_date)
                open_price = self._get_open_price(next_day)

                if open_price is not None:
                    return {
                        "price": open_price,
                        "method": "Signal Follow",
                        "description": f"{next_day} open price",
                        "source": "market_data",
                        "signal_date": signal_date,
                        "entry_date": next_day
                    }
            except Exception as e:
                print(f"Warning: Could not fetch signal open price: {e}")

        # Priority 3: Mid-point (fallback)
        return {
            "price": midpoint,
            "method": "Zone Mid-point",
            "description": "Entry zone center",
            "source": "calculated"
        }

    def _get_next_trading_day(self, date_str: str) -> str:
        """Get next trading day (skip weekends)"""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        next_day = date + timedelta(days=1)

        # Skip weekends
        while next_day.weekday() >= 5:  # 5=Saturday, 6=Sunday
            next_day += timedelta(days=1)

        return next_day.strftime("%Y-%m-%d")

    def _get_open_price(self, date_str: str) -> Optional[float]:
        """Fetch actual open price from market data"""
        try:
            ticker = yf.Ticker(self.symbol)
            # Get data for that specific day
            hist = ticker.history(start=date_str, end=date_str, interval="1d")

            if not hist.empty:
                return float(hist['Open'].iloc[0])
        except Exception as e:
            print(f"Warning: Could not fetch open price for {date_str}: {e}")

        return None

    def _get_alternative_scenarios(
        self,
        entry_zone: tuple,
        signal_date: Optional[str],
        current_price: float,
        default_entry: float
    ) -> list:
        """Get alternative entry scenarios for comparison"""

        alternatives = []
        entry_low, entry_high = entry_zone
        midpoint = (entry_low + entry_high) / 2

        # Midpoint scenario (if not already used)
        if abs(default_entry - midpoint) > 0.01:
            profit_pct = ((current_price - midpoint) / midpoint) * 100
            alternatives.append({
                "label": "Entry zone mid-point",
                "price": midpoint,
                "profit_pct": profit_pct
            })

        # Signal scenario (if not already used and available)
        if signal_date:
            try:
                next_day = self._get_next_trading_day(signal_date)
                open_price = self._get_open_price(next_day)

                if open_price and abs(default_entry - open_price) > 0.01:
                    profit_pct = ((current_price - open_price) / open_price) * 100
                    alternatives.append({
                        "label": f"Following signal ({next_day} open)",
                        "price": open_price,
                        "profit_pct": profit_pct
                    })
            except:
                pass

        return alternatives

    def _format_display(
        self, entry, method, current, profit_pct, total_profit,
        shares, tp1, tp2, prog_tp1, prog_tp2, rem_tp1_pct,
        rem_tp1_dollars, entry_data
    ) -> Dict[str, str]:
        """Format display strings"""

        # Profit color
        if profit_pct > 5:
            profit_emoji = "🟢"
        elif profit_pct > 0:
            profit_emoji = "🟡"
        else:
            profit_emoji = "🔴"

        # Progress bar
        bar_length = 20
        filled = int((prog_tp1 / 100) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)

        return {
            "entry_info": f"${entry:.2f} ({method})",
            "entry_description": entry_data["description"],
            "current_price": f"${current:.2f}",
            "profit": f"+${total_profit:.2f} ({profit_pct:+.2f}%) {profit_emoji}",
            "shares": f"{shares} shares",
            "tp1_progress": f"[{bar}] {prog_tp1:.0f}% to TP1",
            "tp1_remaining": f"${rem_tp1_dollars:+.2f} ({rem_tp1_pct:+.1f}%)",
            "tp1_price": f"${tp1:.2f}",
            "tp2_price": f"${tp2:.2f}",
            "tp2_progress": f"{prog_tp2:.0f}%"
        }

    def _calculate_historical_probability(
        self, target_price: float, period_days: int = 60
    ) -> Dict[str, Any]:
        """
        Calculate probability of reaching target price based on historical data

        Args:
            target_price: Target price to check
            period_days: Number of days to look back (default 60)

        Returns:
            Dict with probability metrics
        """
        try:
            ticker = yf.Ticker(self.symbol)
            hist = ticker.history(period=f"{period_days}d")

            if len(hist) == 0:
                return {
                    "probability_pct": 0,
                    "days_reached": 0,
                    "total_days": 0,
                    "last_reached": None,
                    "days_since": None
                }

            # Count days where High price reached or exceeded target
            days_reached = len(hist[hist['High'] >= target_price])
            total_days = len(hist)
            probability_pct = (days_reached / total_days) * 100 if total_days > 0 else 0

            # Find last time it reached target
            prices_at_target = hist[hist['High'] >= target_price]
            last_reached = None
            days_since = None

            if len(prices_at_target) > 0:
                last_reached_date = prices_at_target.index[-1]
                last_reached = last_reached_date.strftime('%Y-%m-%d')
                days_since = (pd.Timestamp.now(tz='UTC') - last_reached_date).days

            return {
                "probability_pct": round(probability_pct, 1),
                "days_reached": days_reached,
                "total_days": total_days,
                "last_reached": last_reached,
                "days_since": days_since
            }

        except Exception as e:
            print(f"Warning: Could not fetch historical data: {e}")
            return {
                "probability_pct": 0,
                "days_reached": 0,
                "total_days": 0,
                "last_reached": None,
                "days_since": None
            }


def format_pnl_tracker(result: Dict[str, Any]) -> str:
    """Format P&L Tracker result as text display"""

    d = result["display"]
    entry = result["entry"]
    current = result["current"]
    tp1 = result["targets"]["tp1"]
    tp2 = result["targets"]["tp2"]
    risk = result["risk"]
    alts = result["alternatives"]

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 POSITION TRACKER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Entry: {d['entry_info']}
   ({d['entry_description']})

📊 Current: {d['current_price']}
💵 Profit: {d['profit']}
   Position: {d['shares']}

"""

    # Alternatives section (collapsible)
    if alts:
        output += "🔍 [Alternative Scenarios ▼]\n"
        for alt in alts:
            sign = "+" if alt['profit_pct'] >= 0 else ""
            output += f"   • {alt['label']}: ${alt['price']:.2f} → {sign}{alt['profit_pct']:.2f}%\n"
        output += "\n"

    output += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 TARGET PROGRESS

Entry    Current         TP1      TP2
${entry['price']:.2f}   ${current['price']:.2f}         {d['tp1_price']}  {d['tp2_price']}

{d['tp1_progress']}
Remaining: {d['tp1_remaining']}

TP2 Progress: {d['tp2_progress']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Risk Metrics:
├─ Stop Loss: ${risk['stop_loss']:.2f} ({risk['max_loss_pct']:.1f}%)
├─ Max Loss: ${risk['max_loss_dollars']:.2f}
├─ Max Gain: ${risk['max_gain_dollars']:.2f} ({risk['max_gain_pct']:.1f}%)
└─ Current R:R: {risk['current_rr']:.2f}:1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return output
