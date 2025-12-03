"""
Feature 4: Short Interest Analyzer
Analyze short interest data and squeeze potential

Uses Yahoo Finance data (free) for short interest metrics
"""

from typing import Dict, Any, Optional
from datetime import datetime
import yfinance as yf


class ShortInterestAnalyzer:
    """
    Analyze short interest and squeeze potential

    Features:
    - Short interest percentage
    - Days to cover
    - Squeeze potential score
    - Risk/opportunity analysis
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def analyze(
        self,
        short_interest_pct: Optional[float] = None,
        days_to_cover: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyze short interest data

        Args:
            short_interest_pct: Short interest as % of float (optional, will fetch if None)
            days_to_cover: Days to cover ratio (optional, will fetch if None)

        Returns:
            Dictionary with short interest analysis
        """

        # Fetch data from Yahoo Finance if not provided
        if short_interest_pct is None or days_to_cover is None:
            fetched = self._fetch_short_data()
            short_interest_pct = fetched.get("short_pct", short_interest_pct)
            days_to_cover = fetched.get("days_to_cover", days_to_cover)

        # If still None, use defaults
        if short_interest_pct is None:
            short_interest_pct = 0
        if days_to_cover is None:
            days_to_cover = 0

        # Calculate squeeze potential
        squeeze_data = self._calculate_squeeze_potential(
            short_interest_pct, days_to_cover
        )

        squeeze_potential = squeeze_data["level"]
        squeeze_probability = squeeze_data["probability"]

        # Determine risk level
        risk_level = self._determine_risk_level(short_interest_pct)

        # Sector comparison (rough benchmarks)
        sector_avg = 8.5  # Typical market average
        percentile = self._calculate_percentile(short_interest_pct, sector_avg)

        # Generate interpretation
        interpretation = self._generate_interpretation(
            short_interest_pct, days_to_cover, squeeze_potential
        )

        # Format display
        display = self._format_display(
            short_interest_pct, days_to_cover, squeeze_potential,
            squeeze_probability, risk_level, sector_avg, percentile,
            interpretation
        )

        return {
            "symbol": self.symbol,
            "timestamp": datetime.now().isoformat(),
            "short_interest": {
                "short_pct_float": short_interest_pct,  # Changed from 'percentage' for UI compatibility
                "percentage": short_interest_pct,  # Keep for backward compatibility
                "days_to_cover": days_to_cover,
                "trend": "stable"  # Could enhance with historical data
            },
            "squeeze_potential": squeeze_potential,  # Add at top level for UI
            "squeeze": {
                "potential": squeeze_potential,
                "probability": squeeze_probability,
                "conditions": squeeze_data["conditions"]
            },
            "risk": {
                "level": risk_level,
                "interpretation": interpretation
            },
            "comparison": {
                "sector_avg": sector_avg,
                "percentile": percentile,
                "rank": self._get_rank(percentile)
            },
            "interpretation": interpretation,  # Add at top level for UI
            "display": display,
            "data_source": "Yahoo Finance"
        }

    def _fetch_short_data(self) -> Dict[str, Optional[float]]:
        """Fetch short interest data from Yahoo Finance"""
        try:
            ticker = yf.Ticker(self.symbol)
            info = ticker.info

            # Get short interest data
            short_pct = info.get('shortPercentOfFloat')
            if short_pct:
                short_pct = short_pct * 100  # Convert to percentage

            # Calculate days to cover
            short_ratio = info.get('shortRatio')  # This is days to cover

            return {
                "short_pct": short_pct,
                "days_to_cover": short_ratio
            }

        except Exception as e:
            print(f"Warning: Could not fetch short data: {e}")
            return {
                "short_pct": None,
                "days_to_cover": None
            }

    def _calculate_squeeze_potential(
        self,
        short_pct: float,
        days_to_cover: float
    ) -> Dict[str, Any]:
        """
        Calculate short squeeze potential

        High squeeze potential if:
        - Short interest > 15%
        - Days to cover > 5
        """

        conditions = []
        score = 0

        # Check short interest level
        if short_pct > 20:
            conditions.append("Very high short interest (>20%)")
            score += 40
        elif short_pct > 15:
            conditions.append("High short interest (>15%)")
            score += 30
        elif short_pct > 10:
            conditions.append("Moderate short interest (>10%)")
            score += 15

        # Check days to cover
        if days_to_cover > 7:
            conditions.append("High days to cover (>7)")
            score += 30
        elif days_to_cover > 5:
            conditions.append("Moderate days to cover (>5)")
            score += 20
        elif days_to_cover > 3:
            conditions.append("Some coverage risk (>3)")
            score += 10

        # Determine level
        if score >= 50:
            level = "HIGH"
            probability = min(score, 80)
        elif score >= 30:
            level = "MEDIUM"
            probability = min(score, 50)
        else:
            level = "LOW"
            probability = min(score, 25)

        return {
            "level": level,
            "probability": probability,
            "score": score,
            "conditions": conditions
        }

    def _determine_risk_level(self, short_pct: float) -> str:
        """Determine overall risk level"""
        if short_pct > 20:
            return "HIGH"
        elif short_pct > 10:
            return "MODERATE"
        else:
            return "LOW"

    def _calculate_percentile(self, short_pct: float, sector_avg: float) -> int:
        """Calculate rough percentile vs sector"""
        if short_pct > sector_avg * 2:
            return 90
        elif short_pct > sector_avg * 1.5:
            return 75
        elif short_pct > sector_avg:
            return 60
        elif short_pct > sector_avg * 0.5:
            return 40
        else:
            return 20

    def _get_rank(self, percentile: int) -> str:
        """Get rank description"""
        if percentile >= 80:
            return "Top 20% (very high SI)"
        elif percentile >= 60:
            return "Above average"
        elif percentile >= 40:
            return "Average"
        else:
            return "Below average"

    def _generate_interpretation(
        self,
        short_pct: float,
        days_to_cover: float,
        squeeze_potential: str
    ) -> str:
        """Generate human-readable interpretation"""

        if squeeze_potential == "HIGH":
            return (
                f"High short squeeze risk with {short_pct:.1f}% short interest. "
                f"Shorts may be forced to cover if price rises, creating upward pressure."
            )
        elif squeeze_potential == "MEDIUM":
            return (
                f"Moderate short interest ({short_pct:.1f}%). "
                f"Could see some short covering on positive news."
            )
        else:
            return (
                f"Low short interest ({short_pct:.1f}%). "
                f"Limited short squeeze potential."
            )

    def _format_display(
        self, short_pct, dtc, squeeze, prob, risk,
        sector_avg, percentile, interpretation
    ) -> Dict[str, str]:
        """Format display strings"""

        # Squeeze emoji
        if squeeze == "HIGH":
            squeeze_emoji = "🔴"
        elif squeeze == "MEDIUM":
            squeeze_emoji = "🟡"
        else:
            squeeze_emoji = "🟢"

        return {
            "short_pct": f"{short_pct:.1f}%",
            "days_to_cover": f"{dtc:.1f} days" if dtc > 0 else "N/A",
            "squeeze_potential": f"{squeeze_emoji} {squeeze}",
            "squeeze_probability": f"{prob}%",
            "risk_level": risk,
            "sector_avg": f"{sector_avg:.1f}%",
            "percentile": f"Top {100-percentile}%",
            "interpretation": interpretation
        }


def format_short_interest(result: Dict[str, Any]) -> str:
    """Format Short Interest result as text display"""

    d = result["display"]
    si = result["short_interest"]
    sq = result["squeeze"]
    comp = result["comparison"]

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 SHORT INTEREST ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Short Metrics:
├─ Short Interest: {d['short_pct']} of float
├─ Days to Cover: {d['days_to_cover']}
└─ Trend: {si['trend'].title()}

⚡ Squeeze Potential: {d['squeeze_potential']}
   Probability: {d['squeeze_probability']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 What This Means:
{d['interpretation']}

"""

    # Squeeze conditions
    if sq["conditions"]:
        output += "📋 Squeeze Conditions:\n"
        for cond in sq["conditions"]:
            output += f"   • {cond}\n"
        output += "\n"

    output += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Sector Comparison:
├─ Your Stock: {d['short_pct']}
├─ Sector Avg: {d['sector_avg']}
└─ Rank: {comp['rank']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Watch For:
• Price breakout above resistance → Could trigger squeeze
• Volume spike > 200% → Shorts may be covering
• If SI > 20% → High squeeze risk

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Data Source: {result['data_source']}
Updated: {result['timestamp'][:10]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    return output
