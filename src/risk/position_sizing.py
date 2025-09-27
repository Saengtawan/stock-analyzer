"""
Position Sizing and Risk Management
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from loguru import logger


class PositionSizingCalculator:
    """Calculate optimal position sizes based on various methodologies"""

    def __init__(self, account_value: float, config: Dict[str, Any] = None):
        """
        Initialize position sizing calculator

        Args:
            account_value: Total account/portfolio value
            config: Configuration dictionary
        """
        self.account_value = account_value
        self.config = config or {}

        # Default risk parameters
        self.default_risk_per_trade = self.config.get('default_risk_per_trade', 0.02)  # 2%
        self.max_portfolio_risk = self.config.get('max_portfolio_risk', 0.20)  # 20%
        self.max_single_position = self.config.get('max_single_position', 0.15)  # 15%

    def calculate_position_size(self,
                              entry_price: float,
                              stop_loss: float,
                              method: str = 'fixed_fractional',
                              risk_percentage: float = None,
                              additional_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calculate position size using specified method

        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            method: Position sizing method
            risk_percentage: Risk percentage (overrides default)
            additional_params: Additional parameters for specific methods

        Returns:
            Position sizing results
        """
        if risk_percentage is None:
            risk_percentage = self.default_risk_per_trade

        additional_params = additional_params or {}

        try:
            if method == 'fixed_fractional':
                return self._fixed_fractional_sizing(entry_price, stop_loss, risk_percentage)

            elif method == 'kelly_criterion':
                win_rate = additional_params.get('win_rate', 0.55)
                avg_win = additional_params.get('avg_win', 0.06)
                avg_loss = additional_params.get('avg_loss', 0.03)
                return self._kelly_criterion_sizing(entry_price, stop_loss, win_rate, avg_win, avg_loss)

            elif method == 'volatility_adjusted':
                volatility = additional_params.get('volatility', 0.02)
                return self._volatility_adjusted_sizing(entry_price, stop_loss, volatility, risk_percentage)

            elif method == 'atr_based':
                atr = additional_params.get('atr', entry_price * 0.02)
                atr_multiplier = additional_params.get('atr_multiplier', 2.0)
                return self._atr_based_sizing(entry_price, atr, atr_multiplier, risk_percentage)

            elif method == 'monte_carlo':
                expected_return = additional_params.get('expected_return', 0.08)
                volatility = additional_params.get('volatility', 0.02)
                time_horizon = additional_params.get('time_horizon', 30)
                return self._monte_carlo_sizing(entry_price, stop_loss, expected_return, volatility, time_horizon, risk_percentage)

            else:
                raise ValueError(f"Unknown position sizing method: {method}")

        except Exception as e:
            logger.error(f"Position sizing calculation failed: {e}")
            return {
                'error': str(e),
                'position_size': 0,
                'dollar_amount': 0
            }

    def _fixed_fractional_sizing(self, entry_price: float, stop_loss: float, risk_percentage: float) -> Dict[str, Any]:
        """
        Fixed fractional position sizing

        Position Size = Risk Amount / (Entry Price - Stop Loss)
        """
        if entry_price <= 0 or stop_loss <= 0 or entry_price <= stop_loss:
            raise ValueError("Invalid price parameters")

        risk_amount = self.account_value * risk_percentage
        risk_per_share = entry_price - stop_loss
        position_size = risk_amount / risk_per_share

        # Apply position limits
        max_dollar_amount = self.account_value * self.max_single_position
        max_position_size = max_dollar_amount / entry_price

        if position_size > max_position_size:
            position_size = max_position_size
            actual_risk_amount = position_size * risk_per_share
            actual_risk_percentage = actual_risk_amount / self.account_value
        else:
            actual_risk_amount = risk_amount
            actual_risk_percentage = risk_percentage

        dollar_amount = position_size * entry_price

        return {
            'method': 'Fixed Fractional',
            'position_size': int(position_size),
            'dollar_amount': dollar_amount,
            'risk_amount': actual_risk_amount,
            'risk_percentage': actual_risk_percentage,
            'risk_per_share': risk_per_share,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'max_loss': actual_risk_amount,
            'position_limited': position_size != int(position_size)
        }

    def _kelly_criterion_sizing(self,
                               entry_price: float,
                               stop_loss: float,
                               win_rate: float,
                               avg_win: float,
                               avg_loss: float) -> Dict[str, Any]:
        """
        Kelly Criterion position sizing

        Kelly % = (bp - q) / b
        where:
        b = odds received (avg_win / avg_loss)
        p = probability of winning
        q = probability of losing (1 - p)
        """
        if not (0 < win_rate < 1):
            raise ValueError("Win rate must be between 0 and 1")

        if avg_win <= 0 or avg_loss <= 0:
            raise ValueError("Average win and loss must be positive")

        # Calculate Kelly percentage
        b = avg_win / avg_loss  # Odds ratio
        p = win_rate
        q = 1 - win_rate

        kelly_percentage = (b * p - q) / b

        # Apply Kelly fraction limits (never risk more than 25%)
        kelly_percentage = max(0, min(kelly_percentage, 0.25))

        # Convert to position size
        kelly_dollar_amount = self.account_value * kelly_percentage
        position_size = kelly_dollar_amount / entry_price

        # Apply additional position limits
        max_dollar_amount = self.account_value * self.max_single_position
        if kelly_dollar_amount > max_dollar_amount:
            kelly_dollar_amount = max_dollar_amount
            position_size = kelly_dollar_amount / entry_price

        risk_per_share = entry_price - stop_loss
        risk_amount = position_size * risk_per_share
        risk_percentage = risk_amount / self.account_value

        return {
            'method': 'Kelly Criterion',
            'position_size': int(position_size),
            'dollar_amount': kelly_dollar_amount,
            'kelly_percentage': kelly_percentage,
            'risk_amount': risk_amount,
            'risk_percentage': risk_percentage,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'odds_ratio': b,
            'entry_price': entry_price,
            'stop_loss': stop_loss
        }

    def _volatility_adjusted_sizing(self,
                                   entry_price: float,
                                   stop_loss: float,
                                   volatility: float,
                                   base_risk_percentage: float) -> Dict[str, Any]:
        """
        Volatility-adjusted position sizing

        Adjusts position size based on asset volatility
        Higher volatility = smaller position size
        """
        # Normalize volatility (assume 2% is "normal")
        normal_volatility = 0.02
        volatility_ratio = volatility / normal_volatility

        # Adjust risk percentage inversely to volatility
        adjusted_risk_percentage = base_risk_percentage / volatility_ratio

        # Ensure we don't exceed maximum risk
        adjusted_risk_percentage = min(adjusted_risk_percentage, self.default_risk_per_trade * 2)

        # Calculate position using adjusted risk
        risk_amount = self.account_value * adjusted_risk_percentage
        risk_per_share = entry_price - stop_loss
        position_size = risk_amount / risk_per_share

        # Apply position limits
        max_dollar_amount = self.account_value * self.max_single_position
        max_position_size = max_dollar_amount / entry_price

        if position_size > max_position_size:
            position_size = max_position_size
            actual_risk_amount = position_size * risk_per_share
            actual_risk_percentage = actual_risk_amount / self.account_value
        else:
            actual_risk_amount = risk_amount
            actual_risk_percentage = adjusted_risk_percentage

        dollar_amount = position_size * entry_price

        return {
            'method': 'Volatility Adjusted',
            'position_size': int(position_size),
            'dollar_amount': dollar_amount,
            'risk_amount': actual_risk_amount,
            'risk_percentage': actual_risk_percentage,
            'base_risk_percentage': base_risk_percentage,
            'adjusted_risk_percentage': adjusted_risk_percentage,
            'volatility': volatility,
            'volatility_ratio': volatility_ratio,
            'entry_price': entry_price,
            'stop_loss': stop_loss
        }

    def _atr_based_sizing(self,
                         entry_price: float,
                         atr: float,
                         atr_multiplier: float,
                         risk_percentage: float) -> Dict[str, Any]:
        """
        ATR-based position sizing

        Uses ATR to determine stop loss distance and position size
        """
        # Calculate stop loss based on ATR
        stop_loss = entry_price - (atr * atr_multiplier)

        if stop_loss <= 0:
            raise ValueError("ATR-based stop loss results in negative price")

        # Use fixed fractional sizing with ATR-based stop
        result = self._fixed_fractional_sizing(entry_price, stop_loss, risk_percentage)

        # Update method and add ATR-specific info
        result.update({
            'method': 'ATR Based',
            'atr': atr,
            'atr_multiplier': atr_multiplier,
            'atr_stop_distance': atr * atr_multiplier
        })

        return result

    def _monte_carlo_sizing(self,
                           entry_price: float,
                           stop_loss: float,
                           expected_return: float,
                           volatility: float,
                           time_horizon: int,
                           risk_percentage: float,
                           num_simulations: int = 1000) -> Dict[str, Any]:
        """
        Monte Carlo simulation-based position sizing

        Simulates potential outcomes to determine optimal position size
        """
        # Run Monte Carlo simulations
        np.random.seed(42)  # For reproducibility

        # Generate random price paths
        dt = 1 / 252  # Daily time step
        price_paths = []

        for _ in range(num_simulations):
            prices = [entry_price]
            for day in range(time_horizon):
                random_return = np.random.normal(expected_return * dt, volatility * np.sqrt(dt))
                new_price = prices[-1] * (1 + random_return)
                prices.append(new_price)
            price_paths.append(prices)

        # Analyze outcomes for different position sizes
        test_sizes = np.linspace(100, self.account_value / entry_price, 50)
        results = []

        for size in test_sizes:
            profits = []
            for path in price_paths:
                final_price = path[-1]
                min_price = min(path)

                # Check if stop loss was hit
                if min_price <= stop_loss:
                    profit = size * (stop_loss - entry_price)
                else:
                    profit = size * (final_price - entry_price)

                profits.append(profit)

            # Calculate statistics
            mean_profit = np.mean(profits)
            std_profit = np.std(profits)
            prob_profit = sum(1 for p in profits if p > 0) / len(profits)
            max_loss = min(profits)

            results.append({
                'position_size': size,
                'mean_profit': mean_profit,
                'std_profit': std_profit,
                'prob_profit': prob_profit,
                'max_loss': max_loss,
                'sharpe_ratio': mean_profit / std_profit if std_profit > 0 else 0
            })

        # Find optimal position size (maximize Sharpe ratio with risk constraints)
        valid_results = [r for r in results if abs(r['max_loss']) / self.account_value <= risk_percentage * 2]

        if not valid_results:
            # Fall back to fixed fractional if no valid results
            return self._fixed_fractional_sizing(entry_price, stop_loss, risk_percentage)

        optimal_result = max(valid_results, key=lambda x: x['sharpe_ratio'])
        optimal_size = optimal_result['position_size']

        # Apply position limits
        max_dollar_amount = self.account_value * self.max_single_position
        max_position_size = max_dollar_amount / entry_price

        if optimal_size > max_position_size:
            optimal_size = max_position_size

        dollar_amount = optimal_size * entry_price
        risk_per_share = entry_price - stop_loss
        risk_amount = optimal_size * risk_per_share
        actual_risk_percentage = risk_amount / self.account_value

        return {
            'method': 'Monte Carlo',
            'position_size': int(optimal_size),
            'dollar_amount': dollar_amount,
            'risk_amount': risk_amount,
            'risk_percentage': actual_risk_percentage,
            'expected_return': expected_return,
            'volatility': volatility,
            'time_horizon': time_horizon,
            'num_simulations': num_simulations,
            'optimal_sharpe_ratio': optimal_result['sharpe_ratio'],
            'prob_profit': optimal_result['prob_profit'],
            'entry_price': entry_price,
            'stop_loss': stop_loss
        }

    def calculate_portfolio_risk(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate overall portfolio risk from individual positions

        Args:
            positions: List of position dictionaries

        Returns:
            Portfolio risk analysis
        """
        total_exposure = sum(pos.get('dollar_amount', 0) for pos in positions)
        total_risk = sum(pos.get('risk_amount', 0) for pos in positions)

        portfolio_risk_percentage = total_risk / self.account_value
        portfolio_exposure_percentage = total_exposure / self.account_value

        # Calculate concentration risk
        position_weights = [pos.get('dollar_amount', 0) / total_exposure for pos in positions if total_exposure > 0]
        max_single_weight = max(position_weights) if position_weights else 0

        # Calculate correlation risk (simplified)
        sectors = [pos.get('sector', 'Unknown') for pos in positions]
        sector_concentration = {}
        for sector in sectors:
            sector_concentration[sector] = sector_concentration.get(sector, 0) + 1

        max_sector_concentration = max(sector_concentration.values()) if sector_concentration else 0

        return {
            'total_portfolio_value': self.account_value,
            'total_exposure': total_exposure,
            'total_risk_amount': total_risk,
            'portfolio_risk_percentage': portfolio_risk_percentage,
            'portfolio_exposure_percentage': portfolio_exposure_percentage,
            'max_single_position_weight': max_single_weight,
            'max_sector_concentration': max_sector_concentration,
            'number_of_positions': len(positions),
            'risk_status': self._assess_portfolio_risk_status(portfolio_risk_percentage, max_single_weight),
            'diversification_score': self._calculate_diversification_score(position_weights, sector_concentration)
        }

    def _assess_portfolio_risk_status(self, portfolio_risk: float, max_position_weight: float) -> str:
        """Assess overall portfolio risk status"""
        if portfolio_risk > self.max_portfolio_risk:
            return "HIGH - Exceeds maximum portfolio risk"
        elif max_position_weight > self.max_single_position:
            return "HIGH - Single position too large"
        elif portfolio_risk > self.max_portfolio_risk * 0.8:
            return "MODERATE - Approaching risk limits"
        else:
            return "LOW - Within acceptable risk parameters"

    def _calculate_diversification_score(self,
                                       position_weights: List[float],
                                       sector_concentration: Dict[str, int]) -> float:
        """Calculate diversification score (0-10)"""
        if not position_weights:
            return 10.0

        # Position concentration score (0-5)
        position_hhi = sum(w**2 for w in position_weights)  # Herfindahl-Hirschman Index
        max_hhi = 1.0  # Completely concentrated
        min_hhi = 1.0 / len(position_weights)  # Perfectly diversified

        if max_hhi > min_hhi:
            position_score = 5 * (1 - (position_hhi - min_hhi) / (max_hhi - min_hhi))
        else:
            position_score = 5.0

        # Sector concentration score (0-5)
        total_positions = sum(sector_concentration.values())
        sector_weights = [count / total_positions for count in sector_concentration.values()]
        sector_hhi = sum(w**2 for w in sector_weights)

        num_sectors = len(sector_concentration)
        max_sector_hhi = 1.0
        min_sector_hhi = 1.0 / num_sectors if num_sectors > 0 else 1.0

        if max_sector_hhi > min_sector_hhi:
            sector_score = 5 * (1 - (sector_hhi - min_sector_hhi) / (max_sector_hhi - min_sector_hhi))
        else:
            sector_score = 5.0

        return min(position_score + sector_score, 10.0)


class RiskManager:
    """Comprehensive risk management system"""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize risk manager"""
        self.config = config or {}

    def assess_trade_risk(self,
                         entry_price: float,
                         stop_loss: float,
                         take_profit: float,
                         position_size: int,
                         volatility: float = None) -> Dict[str, Any]:
        """
        Assess risk for a specific trade

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            position_size: Number of shares
            volatility: Price volatility (optional)

        Returns:
            Risk assessment results
        """
        # Basic risk metrics
        risk_per_share = entry_price - stop_loss
        reward_per_share = take_profit - entry_price
        risk_reward_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0

        total_risk = position_size * risk_per_share
        total_reward = position_size * reward_per_share

        # Risk percentages
        risk_percentage = abs(risk_per_share) / entry_price
        reward_percentage = reward_per_share / entry_price

        # Volatility-adjusted risk (if volatility provided)
        volatility_adjusted_risk = None
        if volatility:
            # Number of standard deviations the stop loss represents
            volatility_adjusted_risk = risk_percentage / volatility

        # Risk classification
        risk_level = self._classify_risk_level(risk_percentage, risk_reward_ratio, volatility_adjusted_risk)

        return {
            'risk_per_share': risk_per_share,
            'reward_per_share': reward_per_share,
            'risk_reward_ratio': risk_reward_ratio,
            'total_risk': total_risk,
            'total_reward': total_reward,
            'risk_percentage': risk_percentage,
            'reward_percentage': reward_percentage,
            'volatility_adjusted_risk': volatility_adjusted_risk,
            'risk_level': risk_level,
            'recommendation': self._generate_risk_recommendation(risk_level, risk_reward_ratio)
        }

    def calculate_var(self,
                     positions: List[Dict[str, Any]],
                     confidence_level: float = 0.05,
                     time_horizon: int = 1) -> Dict[str, Any]:
        """
        Calculate Value at Risk (VaR)

        Args:
            positions: List of positions
            confidence_level: Confidence level (default 5% = 95% VaR)
            time_horizon: Time horizon in days

        Returns:
            VaR calculation results
        """
        # Simplified VaR calculation
        # In practice, this would use historical data and correlation matrices

        total_value = sum(pos.get('dollar_amount', 0) for pos in positions)

        if total_value == 0:
            return {'var': 0, 'expected_shortfall': 0}

        # Estimate portfolio volatility (simplified)
        # This should be calculated from historical correlation matrix
        avg_volatility = 0.02  # 2% daily volatility assumption
        portfolio_volatility = avg_volatility * np.sqrt(len(positions) / 10)  # Rough diversification adjustment

        # Calculate VaR using normal distribution approximation
        from scipy import stats
        z_score = stats.norm.ppf(confidence_level)  # Negative for lower tail
        var_1_day = abs(z_score) * portfolio_volatility * total_value

        # Scale for time horizon
        var = var_1_day * np.sqrt(time_horizon)

        # Calculate Expected Shortfall (Conditional VaR)
        expected_shortfall = var * 1.2  # Simplified calculation

        return {
            'var': var,
            'var_percentage': var / total_value,
            'expected_shortfall': expected_shortfall,
            'confidence_level': 1 - confidence_level,
            'time_horizon': time_horizon,
            'portfolio_value': total_value,
            'portfolio_volatility': portfolio_volatility
        }

    def _classify_risk_level(self,
                           risk_percentage: float,
                           risk_reward_ratio: float,
                           volatility_adjusted_risk: float = None) -> str:
        """Classify risk level for a trade"""
        # High risk indicators
        if risk_percentage > 0.05:  # >5% risk
            return "HIGH"
        if risk_reward_ratio < 1.5:  # Poor risk/reward
            return "HIGH"
        if volatility_adjusted_risk and volatility_adjusted_risk > 2.0:  # >2 standard deviations
            return "HIGH"

        # Low risk indicators
        if risk_percentage < 0.02 and risk_reward_ratio > 2.0:
            return "LOW"

        return "MODERATE"

    def _generate_risk_recommendation(self, risk_level: str, risk_reward_ratio: float) -> str:
        """Generate risk-based recommendation"""
        if risk_level == "HIGH":
            return "Consider reducing position size or widening stop loss"
        elif risk_level == "LOW" and risk_reward_ratio > 3.0:
            return "Excellent risk/reward - consider increasing position size"
        else:
            return "Acceptable risk level"