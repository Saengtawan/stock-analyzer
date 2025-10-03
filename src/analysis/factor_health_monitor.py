"""
Factor Health Monitor - Simplified
Provides basic factor health monitoring without SEC EDGAR dependencies
"""
from typing import Dict, Any
from datetime import datetime
from loguru import logger
from analysis.fundamental.insider_institutional import InsiderInstitutionalAnalyzer


class FactorHealthMonitor:
    """Simplified factor health monitoring"""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper()

    def get_all_factors(self) -> Dict[str, Any]:
        """Get basic factor health without complex dependencies"""
        logger.info(f"Calculating factor health for {self.symbol}")

        # Get simplified insider/institutional data (will be empty/disabled)
        insider_analyzer = InsiderInstitutionalAnalyzer(self.symbol)
        insider_data = insider_analyzer.get_comprehensive_analysis()

        return {
            'symbol': self.symbol,
            'fundamental_health': {
                'revenue_growth': 5,
                'earnings_quality': 5,
                'debt_levels': 5,
                'cash_position': 5
            },
            'technical_health': {
                'trend_strength': 5,
                'momentum': 5,
                'volatility': 5,
                'volume_health': 5
            },
            'insider_institutional': insider_data,
            'overall_health_score': 5,
            'timestamp': datetime.now().isoformat(),
            'status': 'simplified_mode'
        }

    def get_technical_momentum_factor(self, data: Any) -> float:
        """Simplified technical momentum calculation"""
        try:
            # Return neutral score to avoid errors
            return 5.0
        except Exception as e:
            logger.error(f"Error calculating technical momentum factor: {e}")
            return 5.0