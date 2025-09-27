"""
Advanced Risk Management System
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from loguru import logger
from scipy import stats

from .position_sizing import PositionSizingCalculator, RiskManager


class AdvancedRiskManager:
    """Advanced risk management with multiple risk models"""

    def __init__(self, account_value: float, config: Dict[str, Any] = None):
        """
        Initialize advanced risk manager

        Args:
            account_value: Total account value
            config: Configuration dictionary
        """
        self.account_value = account_value
        self.config = config or {}

        # Initialize components
        self.position_calculator = PositionSizingCalculator(account_value, config)
        self.basic_risk_manager = RiskManager(config)

        # Risk limits
        self.max_daily_loss = config.get('max_daily_loss', 0.03)  # 3%
        self.max_drawdown = config.get('max_drawdown', 0.10)  # 10%
        self.correlation_threshold = config.get('correlation_threshold', 0.7)

    def comprehensive_risk_assessment(self,
                                    positions: List[Dict[str, Any]],
                                    market_data: Dict[str, Any] = None,
                                    historical_returns: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Perform comprehensive risk assessment

        Args:
            positions: Current portfolio positions
            market_data: Market context data
            historical_returns: Historical return data for correlation analysis

        Returns:
            Comprehensive risk assessment
        """
        assessment = {
            'assessment_date': datetime.now().isoformat(),
            'portfolio_value': self.account_value
        }

        try:
            # 1. Position-level risk
            assessment['position_risks'] = self._assess_position_risks(positions)

            # 2. Portfolio-level risk
            assessment['portfolio_risk'] = self._assess_portfolio_risk(positions)

            # 3. Concentration risk
            assessment['concentration_risk'] = self._assess_concentration_risk(positions)

            # 4. Correlation risk
            if historical_returns is not None:
                assessment['correlation_risk'] = self._assess_correlation_risk(positions, historical_returns)

            # 5. Market risk
            if market_data:
                assessment['market_risk'] = self._assess_market_risk(market_data)

            # 6. Liquidity risk
            assessment['liquidity_risk'] = self._assess_liquidity_risk(positions)

            # 7. VaR and stress tests
            assessment['var_analysis'] = self._calculate_comprehensive_var(positions, historical_returns)

            # 8. Overall risk score
            assessment['overall_risk'] = self._calculate_overall_risk_score(assessment)

            # 9. Risk recommendations
            assessment['recommendations'] = self._generate_risk_recommendations(assessment)

        except Exception as e:
            logger.error(f"Risk assessment failed: {e}")
            assessment['error'] = str(e)

        return assessment

    def _assess_position_risks(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Assess risk for individual positions"""
        position_risks = []

        for position in positions:
            try:
                symbol = position.get('symbol', 'Unknown')
                entry_price = position.get('entry_price', 0)
                current_price = position.get('current_price', entry_price)
                stop_loss = position.get('stop_loss', entry_price * 0.9)
                position_size = position.get('position_size', 0)
                volatility = position.get('volatility', 0.02)

                # Calculate position risk metrics
                unrealized_pnl = (current_price - entry_price) * position_size
                unrealized_pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

                max_loss = (entry_price - stop_loss) * position_size
                max_loss_pct = max_loss / self.account_value

                # Distance to stop loss
                stop_distance = (current_price - stop_loss) / current_price if current_price > 0 else 0

                # Volatility-adjusted risk
                vol_adjusted_risk = volatility * np.sqrt(252) * position.get('dollar_amount', 0)

                # Risk classification
                if max_loss_pct > 0.05 or volatility > 0.04:
                    risk_level = "HIGH"
                elif max_loss_pct > 0.02 or volatility > 0.025:
                    risk_level = "MODERATE"
                else:
                    risk_level = "LOW"

                position_risks.append({
                    'symbol': symbol,
                    'risk_level': risk_level,
                    'unrealized_pnl': unrealized_pnl,
                    'unrealized_pnl_pct': unrealized_pnl_pct,
                    'max_loss': max_loss,
                    'max_loss_pct': max_loss_pct,
                    'stop_distance': stop_distance,
                    'volatility': volatility,
                    'vol_adjusted_risk': vol_adjusted_risk,
                    'position_value': position.get('dollar_amount', 0)
                })

            except Exception as e:
                logger.error(f"Failed to assess risk for position: {e}")
                position_risks.append({
                    'symbol': position.get('symbol', 'Unknown'),
                    'risk_level': "UNKNOWN",
                    'error': str(e)
                })

        return position_risks

    def _assess_portfolio_risk(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess overall portfolio risk"""
        if not positions:
            return {'total_risk': 0, 'risk_level': 'NONE'}

        total_exposure = sum(pos.get('dollar_amount', 0) for pos in positions)
        total_risk = sum(pos.get('risk_amount', 0) for pos in positions)

        # Portfolio metrics
        portfolio_beta = self._calculate_portfolio_beta(positions)
        portfolio_volatility = self._estimate_portfolio_volatility(positions)

        # Risk percentages
        risk_percentage = total_risk / self.account_value if self.account_value > 0 else 0
        exposure_percentage = total_exposure / self.account_value if self.account_value > 0 else 0

        # Risk level classification
        if risk_percentage > 0.15 or exposure_percentage > 0.95:
            risk_level = "HIGH"
        elif risk_percentage > 0.08 or exposure_percentage > 0.80:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        return {
            'total_exposure': total_exposure,
            'total_risk': total_risk,
            'risk_percentage': risk_percentage,
            'exposure_percentage': exposure_percentage,
            'portfolio_beta': portfolio_beta,
            'portfolio_volatility': portfolio_volatility,
            'risk_level': risk_level,
            'number_of_positions': len(positions)
        }

    def _assess_concentration_risk(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess concentration risk"""
        if not positions:
            return {'concentration_risk': 'NONE'}

        total_value = sum(pos.get('dollar_amount', 0) for pos in positions)

        # Single position concentration
        position_weights = [pos.get('dollar_amount', 0) / total_value for pos in positions if total_value > 0]
        max_single_weight = max(position_weights) if position_weights else 0

        # Sector concentration
        sectors = {}
        for pos in positions:
            sector = pos.get('sector', 'Unknown')
            sectors[sector] = sectors.get(sector, 0) + pos.get('dollar_amount', 0)

        sector_weights = [value / total_value for value in sectors.values()] if total_value > 0 else []
        max_sector_weight = max(sector_weights) if sector_weights else 0

        # Industry concentration
        industries = {}
        for pos in positions:
            industry = pos.get('industry', 'Unknown')
            industries[industry] = industries.get(industry, 0) + pos.get('dollar_amount', 0)

        industry_weights = [value / total_value for value in industries.values()] if total_value > 0 else []
        max_industry_weight = max(industry_weights) if industry_weights else 0

        # Herfindahl-Hirschman Index for diversification
        hhi_positions = sum(w**2 for w in position_weights)
        hhi_sectors = sum(w**2 for w in sector_weights)

        # Risk assessment
        concentration_risks = []
        if max_single_weight > 0.20:
            concentration_risks.append(f"Single position concentration: {max_single_weight:.1%}")
        if max_sector_weight > 0.40:
            concentration_risks.append(f"Sector concentration: {max_sector_weight:.1%}")
        if max_industry_weight > 0.30:
            concentration_risks.append(f"Industry concentration: {max_industry_weight:.1%}")

        if len(concentration_risks) >= 2:
            risk_level = "HIGH"
        elif len(concentration_risks) == 1:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        return {
            'risk_level': risk_level,
            'max_single_position': max_single_weight,
            'max_sector_weight': max_sector_weight,
            'max_industry_weight': max_industry_weight,
            'hhi_positions': hhi_positions,
            'hhi_sectors': hhi_sectors,
            'concentration_risks': concentration_risks,
            'num_positions': len(positions),
            'num_sectors': len(sectors),
            'num_industries': len(industries)
        }

    def _assess_correlation_risk(self,
                               positions: List[Dict[str, Any]],
                               historical_returns: pd.DataFrame) -> Dict[str, Any]:
        """Assess correlation risk between positions"""
        if len(positions) < 2:
            return {'correlation_risk': 'NONE'}

        symbols = [pos.get('symbol') for pos in positions]
        available_symbols = [s for s in symbols if s in historical_returns.columns]

        if len(available_symbols) < 2:
            return {'correlation_risk': 'INSUFFICIENT_DATA'}

        # Calculate correlation matrix
        returns_subset = historical_returns[available_symbols]
        correlation_matrix = returns_subset.corr()

        # Find high correlations
        high_correlations = []
        for i in range(len(available_symbols)):
            for j in range(i + 1, len(available_symbols)):
                correlation = correlation_matrix.iloc[i, j]
                if abs(correlation) > self.correlation_threshold:
                    high_correlations.append({
                        'symbol_1': available_symbols[i],
                        'symbol_2': available_symbols[j],
                        'correlation': correlation
                    })

        # Average correlation
        correlations = []
        for i in range(len(available_symbols)):
            for j in range(i + 1, len(available_symbols)):
                correlations.append(abs(correlation_matrix.iloc[i, j]))

        avg_correlation = np.mean(correlations) if correlations else 0

        # Risk assessment
        if avg_correlation > 0.7 or len(high_correlations) > len(available_symbols) / 2:
            risk_level = "HIGH"
        elif avg_correlation > 0.5 or len(high_correlations) > 0:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        return {
            'risk_level': risk_level,
            'avg_correlation': avg_correlation,
            'high_correlations': high_correlations,
            'correlation_matrix': correlation_matrix.to_dict(),
            'symbols_analyzed': available_symbols
        }

    def _assess_market_risk(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess market risk factors"""
        market_risk = {
            'risk_factors': []
        }

        # VIX level
        vix = market_data.get('vix', 20)
        if vix > 30:
            market_risk['risk_factors'].append(f"High volatility (VIX: {vix})")
        elif vix > 25:
            market_risk['risk_factors'].append(f"Elevated volatility (VIX: {vix})")

        # Market trend
        market_trend = market_data.get('market_trend', 'Neutral')
        if market_trend == 'Bear Market':
            market_risk['risk_factors'].append("Bear market conditions")

        # Interest rates
        interest_rate = market_data.get('interest_rate')
        if interest_rate and interest_rate > 0.05:
            market_risk['risk_factors'].append(f"High interest rates ({interest_rate:.2%})")

        # Risk level
        if len(market_risk['risk_factors']) >= 3:
            market_risk['risk_level'] = "HIGH"
        elif len(market_risk['risk_factors']) >= 1:
            market_risk['risk_level'] = "MODERATE"
        else:
            market_risk['risk_level'] = "LOW"

        return market_risk

    def _assess_liquidity_risk(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess liquidity risk"""
        liquidity_risks = []
        total_value = sum(pos.get('dollar_amount', 0) for pos in positions)

        for position in positions:
            symbol = position.get('symbol', 'Unknown')
            avg_volume = position.get('avg_volume', 0)
            position_value = position.get('dollar_amount', 0)
            current_price = position.get('current_price', 1)

            if avg_volume > 0 and current_price > 0:
                # Daily dollar volume
                daily_dollar_volume = avg_volume * current_price

                # Position as percentage of daily volume
                volume_percentage = position_value / daily_dollar_volume if daily_dollar_volume > 0 else 0

                if volume_percentage > 0.05:  # Position > 5% of daily volume
                    liquidity_risks.append({
                        'symbol': symbol,
                        'volume_percentage': volume_percentage,
                        'risk_level': 'HIGH' if volume_percentage > 0.10 else 'MODERATE'
                    })

        # Overall liquidity risk
        if len(liquidity_risks) > len(positions) / 3:
            risk_level = "HIGH"
        elif len(liquidity_risks) > 0:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        return {
            'risk_level': risk_level,
            'liquidity_risks': liquidity_risks,
            'positions_at_risk': len(liquidity_risks)
        }

    def _calculate_comprehensive_var(self,
                                   positions: List[Dict[str, Any]],
                                   historical_returns: pd.DataFrame = None) -> Dict[str, Any]:
        """Calculate comprehensive Value at Risk"""
        if not positions:
            return {'var_1_day': 0, 'var_10_day': 0}

        # Portfolio value
        portfolio_value = sum(pos.get('dollar_amount', 0) for pos in positions)

        if historical_returns is not None:
            # Historical VaR
            symbols = [pos.get('symbol') for pos in positions]
            weights = [pos.get('dollar_amount', 0) / portfolio_value for pos in positions if portfolio_value > 0]

            available_symbols = [s for s in symbols if s in historical_returns.columns]
            if len(available_symbols) > 0:
                returns_subset = historical_returns[available_symbols]

                # Calculate portfolio returns
                aligned_weights = [weights[symbols.index(s)] for s in available_symbols]
                aligned_weights = np.array(aligned_weights) / sum(aligned_weights) if sum(aligned_weights) > 0 else np.array(aligned_weights)

                portfolio_returns = (returns_subset * aligned_weights).sum(axis=1)

                # Calculate VaR at different confidence levels
                var_95 = np.percentile(portfolio_returns, 5) * portfolio_value
                var_99 = np.percentile(portfolio_returns, 1) * portfolio_value

                # Expected Shortfall (Conditional VaR)
                es_95 = portfolio_returns[portfolio_returns <= np.percentile(portfolio_returns, 5)].mean() * portfolio_value
                es_99 = portfolio_returns[portfolio_returns <= np.percentile(portfolio_returns, 1)].mean() * portfolio_value

                return {
                    'method': 'Historical',
                    'var_95_1day': abs(var_95),
                    'var_99_1day': abs(var_99),
                    'var_95_10day': abs(var_95) * np.sqrt(10),
                    'var_99_10day': abs(var_99) * np.sqrt(10),
                    'expected_shortfall_95': abs(es_95),
                    'expected_shortfall_99': abs(es_99),
                    'portfolio_value': portfolio_value
                }

        # Parametric VaR (fallback)
        avg_volatility = 0.02  # 2% daily volatility assumption
        portfolio_volatility = avg_volatility * np.sqrt(len(positions) / 10)  # Rough diversification

        var_95 = 1.645 * portfolio_volatility * portfolio_value  # 95% VaR
        var_99 = 2.326 * portfolio_volatility * portfolio_value  # 99% VaR

        return {
            'method': 'Parametric',
            'var_95_1day': var_95,
            'var_99_1day': var_99,
            'var_95_10day': var_95 * np.sqrt(10),
            'var_99_10day': var_99 * np.sqrt(10),
            'portfolio_volatility': portfolio_volatility,
            'portfolio_value': portfolio_value
        }

    def _calculate_portfolio_beta(self, positions: List[Dict[str, Any]]) -> float:
        """Calculate portfolio beta"""
        total_value = sum(pos.get('dollar_amount', 0) for pos in positions)
        if total_value == 0:
            return 1.0

        weighted_beta = 0
        for position in positions:
            beta = position.get('beta', 1.0)
            weight = position.get('dollar_amount', 0) / total_value
            weighted_beta += beta * weight

        return weighted_beta

    def _estimate_portfolio_volatility(self, positions: List[Dict[str, Any]]) -> float:
        """Estimate portfolio volatility"""
        if not positions:
            return 0

        total_value = sum(pos.get('dollar_amount', 0) for pos in positions)
        if total_value == 0:
            return 0

        # Weighted average volatility (simplified)
        weighted_vol = 0
        for position in positions:
            vol = position.get('volatility', 0.02)
            weight = position.get('dollar_amount', 0) / total_value
            weighted_vol += vol * weight

        # Apply diversification benefit (simplified)
        diversification_factor = np.sqrt(1 / len(positions))
        return weighted_vol * (1 - diversification_factor * 0.3)

    def _calculate_overall_risk_score(self, assessment: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall risk score (0-10, where 10 is highest risk)"""
        risk_components = {}
        total_score = 0

        # Portfolio risk (25%)
        portfolio_risk = assessment.get('portfolio_risk', {})
        portfolio_risk_level = portfolio_risk.get('risk_level', 'LOW')
        portfolio_score = {'LOW': 2, 'MODERATE': 5, 'HIGH': 8}.get(portfolio_risk_level, 5)
        risk_components['portfolio'] = portfolio_score
        total_score += portfolio_score * 0.25

        # Concentration risk (25%)
        concentration_risk = assessment.get('concentration_risk', {})
        concentration_risk_level = concentration_risk.get('risk_level', 'LOW')
        concentration_score = {'LOW': 2, 'MODERATE': 5, 'HIGH': 8}.get(concentration_risk_level, 5)
        risk_components['concentration'] = concentration_score
        total_score += concentration_score * 0.25

        # Correlation risk (20%)
        correlation_risk = assessment.get('correlation_risk', {})
        correlation_risk_level = correlation_risk.get('risk_level', 'LOW')
        correlation_score = {'LOW': 2, 'MODERATE': 5, 'HIGH': 8}.get(correlation_risk_level, 5)
        risk_components['correlation'] = correlation_score
        total_score += correlation_score * 0.20

        # Market risk (15%)
        market_risk = assessment.get('market_risk', {})
        market_risk_level = market_risk.get('risk_level', 'LOW')
        market_score = {'LOW': 2, 'MODERATE': 5, 'HIGH': 8}.get(market_risk_level, 5)
        risk_components['market'] = market_score
        total_score += market_score * 0.15

        # Liquidity risk (15%)
        liquidity_risk = assessment.get('liquidity_risk', {})
        liquidity_risk_level = liquidity_risk.get('risk_level', 'LOW')
        liquidity_score = {'LOW': 2, 'MODERATE': 5, 'HIGH': 8}.get(liquidity_risk_level, 5)
        risk_components['liquidity'] = liquidity_score
        total_score += liquidity_score * 0.15

        # Overall risk level
        if total_score >= 7:
            overall_level = "HIGH"
        elif total_score >= 5:
            overall_level = "MODERATE"
        else:
            overall_level = "LOW"

        return {
            'overall_score': total_score,
            'overall_level': overall_level,
            'component_scores': risk_components,
            'max_score': 10
        }

    def _generate_risk_recommendations(self, assessment: Dict[str, Any]) -> List[str]:
        """Generate risk management recommendations"""
        recommendations = []

        # Portfolio risk recommendations
        portfolio_risk = assessment.get('portfolio_risk', {})
        if portfolio_risk.get('risk_level') == 'HIGH':
            recommendations.append("Reduce overall portfolio risk by decreasing position sizes")

        # Concentration risk recommendations
        concentration_risk = assessment.get('concentration_risk', {})
        if concentration_risk.get('max_single_position', 0) > 0.20:
            recommendations.append("Reduce single position concentration - max position exceeds 20%")
        if concentration_risk.get('max_sector_weight', 0) > 0.40:
            recommendations.append("Diversify across more sectors - sector concentration too high")

        # Correlation risk recommendations
        correlation_risk = assessment.get('correlation_risk', {})
        if correlation_risk.get('risk_level') == 'HIGH':
            recommendations.append("Reduce correlation risk by diversifying into uncorrelated assets")

        # Market risk recommendations
        market_risk = assessment.get('market_risk', {})
        if market_risk.get('risk_level') == 'HIGH':
            recommendations.append("Consider hedging or reducing exposure due to adverse market conditions")

        # Liquidity risk recommendations
        liquidity_risk = assessment.get('liquidity_risk', {})
        if liquidity_risk.get('risk_level') == 'HIGH':
            recommendations.append("Review positions in low-liquidity stocks")

        # VaR recommendations
        var_analysis = assessment.get('var_analysis', {})
        var_95 = var_analysis.get('var_95_1day', 0)
        if var_95 > self.account_value * 0.05:  # VaR > 5% of account
            recommendations.append("Daily VaR exceeds 5% of account value - consider risk reduction")

        return recommendations