"""
Enhanced Analysis - Main Integration
Combines all 6 features into one comprehensive analysis

This is the main entry point for enhanced features
"""

from typing import Dict, Any, Optional
from datetime import datetime

from .real_time_monitor import RealTimePriceMonitor, format_real_time_monitor
from .pnl_tracker import ProfitLossTracker, format_pnl_tracker
from .trailing_stop import TrailingStopManager, format_trailing_stop
from .short_interest import ShortInterestAnalyzer, format_short_interest
from .decision_engine import DecisionMatrix, format_decision_matrix
from .risk_alerts import RiskAlertManager, format_risk_alerts


class EnhancedAnalysis:
    """
    Comprehensive analysis combining all 6 enhanced features

    Usage:
        analyzer = EnhancedAnalysis("AAPL")
        result = analyzer.run_full_analysis(...)
        print(result["formatted_output"])
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

        # Initialize all feature modules
        self.price_monitor = RealTimePriceMonitor(symbol)
        self.pnl_tracker = ProfitLossTracker(symbol)
        self.trailing_stop = TrailingStopManager(symbol)
        self.short_interest = ShortInterestAnalyzer(symbol)
        self.decision_matrix = DecisionMatrix(symbol)
        self.risk_alerts = RiskAlertManager(symbol)

    def run_full_analysis(
        self,
        # Required basics
        current_price: float,
        entry_zone: tuple,  # (low, high)
        support: float,
        resistance: float,
        tp1: float,
        tp2: float,
        stop_loss: float,

        # Technical indicators
        rsi: float,
        volume_vs_avg: float,
        market_regime: str,  # 'sideways', 'uptrend', 'downtrend'

        # Position info (optional - for existing positions)
        has_position: bool = False,
        signal_date: Optional[str] = None,  # YYYY-MM-DD when BUY signal generated
        entry_price: Optional[float] = None,  # Custom entry (optional)
        shares: int = 100,
        holding_days: int = 0,

        # Additional metrics (optional)
        selling_pressure: Optional[float] = None,  # 0-100
        current_atr: Optional[float] = None,
        entry_atr: Optional[float] = None,
        short_interest_pct: Optional[float] = None,
        days_to_cover: Optional[float] = None,

        # Timeframe
        target_hold_days: int = 14

    ) -> Dict[str, Any]:
        """
        Run complete enhanced analysis

        Returns all 6 feature results + formatted output
        """

        # Feature 1: Real-Time Price Monitor
        price_analysis = self.price_monitor.analyze(
            current_price=current_price,
            entry_zone=entry_zone,
            support=support,
            resistance=resistance,
            rsi=rsi,
            volume_vs_avg=volume_vs_avg,
            market_regime=market_regime
        )

        # Feature 2: P&L Tracker (only if has position or for simulation)
        pnl_analysis = None
        if has_position or signal_date:  # Run even if no position for simulation
            pnl_analysis = self.pnl_tracker.analyze(
                current_price=current_price,
                entry_zone=entry_zone,
                tp1=tp1,
                tp2=tp2,
                stop_loss=stop_loss,
                signal_date=signal_date,
                shares=shares,
                custom_entry=entry_price
            )

        # Get entry price for further analysis
        if pnl_analysis:
            detected_entry = pnl_analysis["entry"]["price"]
        elif entry_price:
            detected_entry = entry_price
        else:
            # Use mid-point as fallback
            detected_entry = (entry_zone[0] + entry_zone[1]) / 2

        # Calculate profit percentage
        profit_pct = ((current_price - detected_entry) / detected_entry) * 100 if detected_entry else 0

        # Feature 3: Trailing Stop (only if has position)
        trailing_analysis = None
        if has_position and detected_entry:
            trailing_analysis = self.trailing_stop.analyze(
                entry_price=detected_entry,
                current_price=current_price,
                original_sl=stop_loss,
                shares=shares
            )

        # Feature 4: Short Interest
        short_analysis = self.short_interest.analyze(
            short_interest_pct=short_interest_pct,
            days_to_cover=days_to_cover
        )

        # Calculate current R:R ratio
        upside_to_tp1 = tp1 - current_price
        downside_to_sl = current_price - stop_loss
        current_rr = upside_to_tp1 / downside_to_sl if downside_to_sl > 0 else 0

        # Calculate entry R:R ratio
        entry_upside = tp1 - detected_entry
        entry_downside = detected_entry - stop_loss
        entry_rr = entry_upside / entry_downside if entry_downside > 0 else 0

        # Calculate progress to TP1
        progress_to_tp1 = 0
        if pnl_analysis:
            progress_to_tp1 = pnl_analysis["targets"]["tp1"]["progress_pct"]

        # Calculate distance to resistance
        distance_to_resistance = ((resistance - current_price) / current_price) * 100

        # Feature 5: Decision Matrix
        decision_analysis = self.decision_matrix.analyze(
            has_position=has_position,
            entry_price=detected_entry if has_position else None,
            current_price=current_price,
            profit_pct=profit_pct if has_position else None,
            holding_days=holding_days if has_position else 0,
            entry_readiness_score=price_analysis["readiness"]["score"] if not has_position else None,
            entry_conditions_passed=price_analysis["readiness"]["passed"] if not has_position else None,
            progress_to_tp1=progress_to_tp1 if has_position else None,
            current_rr=current_rr,
            stop_loss=stop_loss,
            rsi=rsi,
            volume_vs_avg=volume_vs_avg,
            market_regime=market_regime,
            selling_pressure=selling_pressure,
            distance_to_resistance_pct=distance_to_resistance,
            target_hold_days=target_hold_days
        )

        # Feature 6: Risk Alerts (only if has position)
        risk_analysis = None
        if has_position:
            risk_analysis = self.risk_alerts.analyze(
                current_rr=current_rr,
                entry_rr=entry_rr,
                current_atr=current_atr,
                entry_atr=entry_atr,
                current_volume_ratio=volume_vs_avg,
                current_regime=market_regime,
                expected_regime="sideways",  # Could be parametrized
                profit_pct=profit_pct,
                days_held=holding_days
            )

        # Format complete output
        formatted_output = self._format_complete_output(
            price_analysis,
            pnl_analysis,
            trailing_analysis,
            short_analysis,
            decision_analysis,
            risk_analysis,
            has_position
        )

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "has_position": has_position,
            "current_price": current_price,
            "detected_entry": detected_entry,
            "profit_pct": profit_pct if has_position else None,

            # Individual feature results
            "features": {
                "price_monitor": price_analysis,
                "pnl_tracker": pnl_analysis,
                "trailing_stop": trailing_analysis,
                "short_interest": short_analysis,
                "decision_matrix": decision_analysis,
                "risk_alerts": risk_analysis
            },

            # Formatted output
            "formatted_output": formatted_output
        }

    def _format_complete_output(
        self,
        price, pnl, trailing, short, decision, risk,
        has_position
    ) -> str:
        """Format all features into one comprehensive display"""

        output = f"""
{'='*60}
📊 ENHANCED STOCK ANALYSIS - {self.symbol}
{'='*60}

"""

        # 1. Real-Time Price Monitor (always show)
        output += format_real_time_monitor(price)

        # 2. P&L Tracker (show if has position or simulation available)
        if pnl:
            output += "\n"
            output += format_pnl_tracker(pnl)

        # 3. Trailing Stop (only if has position)
        if trailing:
            output += "\n"
            output += format_trailing_stop(trailing)

        # 4. Short Interest (always show)
        output += "\n"
        output += format_short_interest(short)

        # 5. Risk Alerts (only if has position)
        if risk:
            output += "\n"
            output += format_risk_alerts(risk)

        # 6. Decision Matrix (always show - most important!)
        output += "\n"
        output += format_decision_matrix(decision)

        output += f"""
{'='*60}
🎯 END OF ANALYSIS
{'='*60}
"""

        return output


# Convenience function for quick analysis
def analyze_stock(
    symbol: str,
    current_price: float,
    entry_zone: tuple,
    support: float,
    resistance: float,
    tp1: float,
    tp2: float,
    stop_loss: float,
    rsi: float,
    volume_vs_avg: float,
    market_regime: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Quick function to run enhanced analysis

    Example:
        result = analyze_stock(
            symbol="AAPL",
            current_price=175.50,
            entry_zone=(170, 172),
            support=168,
            resistance=180,
            tp1=178,
            tp2=185,
            stop_loss=167,
            rsi=52,
            volume_vs_avg=1.2,
            market_regime="sideways",
            has_position=True,
            signal_date="2024-01-15",
            shares=100
        )

        print(result["formatted_output"])
    """
    analyzer = EnhancedAnalysis(symbol)
    return analyzer.run_full_analysis(
        current_price=current_price,
        entry_zone=entry_zone,
        support=support,
        resistance=resistance,
        tp1=tp1,
        tp2=tp2,
        stop_loss=stop_loss,
        rsi=rsi,
        volume_vs_avg=volume_vs_avg,
        market_regime=market_regime,
        **kwargs
    )
