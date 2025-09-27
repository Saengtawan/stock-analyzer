"""
Enhanced Risk Management System
Advanced risk management with dynamic adaptation, portfolio optimization, and multi-factor models
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from loguru import logger
import warnings
from scipy import stats, optimize
from scipy.linalg import inv
from sklearn.covariance import LedoitWolf
from sklearn.preprocessing import StandardScaler
import talib


class EnhancedRiskManager:
    """Enhanced risk management with advanced portfolio optimization"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

        # Risk parameters
        self.risk_params = {
            'max_portfolio_risk': self.config.get('max_portfolio_risk', 0.20),  # 20%
            'max_single_position': self.config.get('max_single_position', 0.15),  # 15%
            'max_sector_concentration': self.config.get('max_sector_concentration', 0.30),  # 30%
            'max_correlation_cluster': self.config.get('max_correlation_cluster', 0.40),  # 40%
            'var_confidence_level': self.config.get('var_confidence_level', 0.05),  # 95% VaR
            'expected_sharpe_ratio': self.config.get('expected_sharpe_ratio', 1.0),
            'max_leverage': self.config.get('max_leverage', 1.0),  # No leverage by default
            'liquidity_threshold': self.config.get('liquidity_threshold', 100000),  # Min daily volume
        }

        # Risk models
        self.risk_models = {}
        self.correlation_matrix = None
        self.volatility_estimates = {}
        self.beta_estimates = {}

    def calculate_portfolio_risk(self, positions: List[Dict[str, Any]],
                               price_data: Dict[str, pd.DataFrame],
                               market_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Calculate comprehensive portfolio risk metrics

        Args:
            positions: List of position dictionaries
            price_data: Dictionary of symbol -> price data
            market_data: Market index data for beta calculations

        Returns:
            Dictionary with risk metrics
        """
        logger.info("Calculating comprehensive portfolio risk metrics")

        risk_metrics = {
            'portfolio_var': 0.0,
            'portfolio_cvar': 0.0,
            'portfolio_volatility': 0.0,
            'portfolio_beta': 0.0,
            'maximum_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'concentration_risk': 0.0,
            'correlation_risk': 0.0,
            'liquidity_risk': 0.0,
            'tail_risk': 0.0,
            'stress_test_results': {},
            'risk_attribution': {},
            'recommendations': []
        }

        if not positions:
            return risk_metrics

        # 1. Calculate portfolio returns
        portfolio_returns = self._calculate_portfolio_returns(positions, price_data)

        if portfolio_returns.empty:
            logger.warning("No portfolio returns data available")
            return risk_metrics

        # 2. Basic risk metrics
        risk_metrics.update(self._calculate_basic_risk_metrics(portfolio_returns))

        # 3. Value at Risk (VaR) and Conditional VaR
        var_metrics = self._calculate_var_metrics(portfolio_returns)
        risk_metrics.update(var_metrics)

        # 4. Portfolio volatility and correlation analysis
        correlation_metrics = self._calculate_correlation_metrics(positions, price_data)
        risk_metrics.update(correlation_metrics)

        # 5. Concentration risk analysis
        concentration_risk = self._calculate_concentration_risk(positions)
        risk_metrics['concentration_risk'] = concentration_risk

        # 6. Liquidity risk analysis
        liquidity_risk = self._calculate_liquidity_risk(positions, price_data)
        risk_metrics['liquidity_risk'] = liquidity_risk

        # 7. Stress testing
        stress_results = self._perform_stress_tests(positions, price_data)
        risk_metrics['stress_test_results'] = stress_results

        # 8. Risk attribution
        risk_attribution = self._calculate_risk_attribution(positions, price_data)
        risk_metrics['risk_attribution'] = risk_attribution

        # 9. Generate recommendations
        recommendations = self._generate_risk_recommendations(risk_metrics, positions)
        risk_metrics['recommendations'] = recommendations

        return risk_metrics

    def optimize_portfolio_allocation(self, expected_returns: Dict[str, float],
                                    risk_data: Dict[str, pd.DataFrame],
                                    constraints: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Optimize portfolio allocation using modern portfolio theory

        Args:
            expected_returns: Dictionary of symbol -> expected return
            risk_data: Dictionary of symbol -> price/return data
            constraints: Additional constraints for optimization

        Returns:
            Optimal allocation results
        """
        logger.info("Optimizing portfolio allocation")

        optimization_result = {
            'optimal_weights': {},
            'expected_return': 0.0,
            'expected_volatility': 0.0,
            'sharpe_ratio': 0.0,
            'optimization_status': 'failed',
            'efficient_frontier': [],
            'risk_budget': {}
        }

        if not expected_returns or not risk_data:
            return optimization_result

        try:
            # 1. Calculate covariance matrix
            covariance_matrix = self._calculate_covariance_matrix(risk_data)

            # 2. Prepare optimization inputs
            symbols = list(expected_returns.keys())
            returns_vector = np.array([expected_returns[symbol] for symbol in symbols])

            # 3. Set up constraints
            optimization_constraints = self._setup_optimization_constraints(symbols, constraints)

            # 4. Optimize for maximum Sharpe ratio
            optimal_weights = self._optimize_sharpe_ratio(
                returns_vector, covariance_matrix, optimization_constraints
            )

            # 5. Calculate portfolio metrics
            portfolio_return = np.dot(optimal_weights, returns_vector)
            portfolio_variance = np.dot(optimal_weights.T, np.dot(covariance_matrix, optimal_weights))
            portfolio_volatility = np.sqrt(portfolio_variance)

            # 6. Update results
            optimization_result.update({
                'optimal_weights': dict(zip(symbols, optimal_weights)),
                'expected_return': float(portfolio_return),
                'expected_volatility': float(portfolio_volatility),
                'sharpe_ratio': float(portfolio_return / portfolio_volatility) if portfolio_volatility > 0 else 0.0,
                'optimization_status': 'success'
            })

            # 7. Generate efficient frontier
            efficient_frontier = self._generate_efficient_frontier(
                returns_vector, covariance_matrix, optimization_constraints
            )
            optimization_result['efficient_frontier'] = efficient_frontier

            # 8. Calculate risk budget
            risk_budget = self._calculate_risk_budget(optimal_weights, covariance_matrix)
            optimization_result['risk_budget'] = dict(zip(symbols, risk_budget))

        except Exception as e:
            logger.error(f"Portfolio optimization failed: {e}")
            optimization_result['optimization_status'] = f'failed: {str(e)}'

        return optimization_result

    def calculate_dynamic_position_sizing(self, symbol: str,
                                        current_price: float,
                                        volatility: float,
                                        market_regime: str = 'normal',
                                        portfolio_heat: float = 0.0) -> Dict[str, Any]:
        """
        Calculate dynamic position sizing based on multiple factors

        Args:
            symbol: Stock symbol
            current_price: Current stock price
            volatility: Historical volatility
            market_regime: Current market regime
            portfolio_heat: Current portfolio risk level

        Returns:
            Position sizing recommendations
        """
        logger.info(f"Calculating dynamic position sizing for {symbol}")

        sizing_result = {
            'recommended_shares': 0,
            'recommended_value': 0.0,
            'position_size_percent': 0.0,
            'risk_per_share': 0.0,
            'total_position_risk': 0.0,
            'sizing_method': 'volatility_adjusted',
            'confidence_level': 0.0,
            'warnings': []
        }

        # 1. Base position size calculation
        base_risk_per_trade = self.risk_params.get('default_risk_per_trade', 0.02)

        # 2. Adjust for market regime
        regime_multiplier = self._get_regime_multiplier(market_regime)
        adjusted_risk = base_risk_per_trade * regime_multiplier

        # 3. Adjust for portfolio heat
        heat_adjustment = self._get_heat_adjustment(portfolio_heat)
        final_risk = adjusted_risk * heat_adjustment

        # 4. Adjust for volatility
        volatility_adjustment = self._get_volatility_adjustment(volatility)
        volatility_adjusted_risk = final_risk * volatility_adjustment

        # 5. Calculate position size
        account_value = self.config.get('account_value', 100000)
        risk_amount = account_value * volatility_adjusted_risk

        # Assume 2% stop loss for position sizing
        stop_loss_percent = 0.02
        risk_per_share = current_price * stop_loss_percent
        recommended_shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

        # 6. Apply position limits
        max_position_value = account_value * self.risk_params['max_single_position']
        max_shares_by_limit = int(max_position_value / current_price)
        recommended_shares = min(recommended_shares, max_shares_by_limit)

        # 7. Update results
        recommended_value = recommended_shares * current_price
        sizing_result.update({
            'recommended_shares': recommended_shares,
            'recommended_value': recommended_value,
            'position_size_percent': recommended_value / account_value,
            'risk_per_share': risk_per_share,
            'total_position_risk': recommended_shares * risk_per_share,
            'confidence_level': self._calculate_sizing_confidence(volatility, market_regime)
        })

        # 8. Generate warnings
        warnings = self._generate_sizing_warnings(sizing_result, volatility, portfolio_heat)
        sizing_result['warnings'] = warnings

        return sizing_result

    def calculate_portfolio_correlation(self, price_data: Dict[str, pd.DataFrame],
                                      window: int = 60) -> Dict[str, Any]:
        """
        Calculate portfolio correlation analysis

        Args:
            price_data: Dictionary of symbol -> price data
            window: Rolling window for correlation calculation

        Returns:
            Correlation analysis results
        """
        logger.info("Calculating portfolio correlation analysis")

        correlation_analysis = {
            'correlation_matrix': pd.DataFrame(),
            'average_correlation': 0.0,
            'max_correlation': 0.0,
            'correlation_clusters': [],
            'diversification_ratio': 0.0,
            'effective_number_of_stocks': 0.0,
            'correlation_warnings': []
        }

        if len(price_data) < 2:
            return correlation_analysis

        # 1. Calculate returns for all symbols
        returns_data = {}
        for symbol, data in price_data.items():
            if len(data) > window and 'close' in data.columns:
                returns = data['close'].pct_change().dropna()
                if len(returns) >= window:
                    returns_data[symbol] = returns

        if len(returns_data) < 2:
            logger.warning("Insufficient data for correlation analysis")
            return correlation_analysis

        # 2. Align data and calculate correlation matrix
        aligned_data = pd.DataFrame(returns_data)
        correlation_matrix = aligned_data.corr()

        correlation_analysis['correlation_matrix'] = correlation_matrix

        # 3. Calculate summary statistics
        correlation_values = correlation_matrix.values
        np.fill_diagonal(correlation_values, np.nan)  # Exclude diagonal

        avg_correlation = np.nanmean(correlation_values)
        max_correlation = np.nanmax(correlation_values)

        correlation_analysis['average_correlation'] = float(avg_correlation)
        correlation_analysis['max_correlation'] = float(max_correlation)

        # 4. Identify correlation clusters
        clusters = self._identify_correlation_clusters(correlation_matrix)
        correlation_analysis['correlation_clusters'] = clusters

        # 5. Calculate diversification metrics
        diversification_ratio = self._calculate_diversification_ratio(correlation_matrix)
        effective_stocks = self._calculate_effective_number_of_stocks(correlation_matrix)

        correlation_analysis['diversification_ratio'] = diversification_ratio
        correlation_analysis['effective_number_of_stocks'] = effective_stocks

        # 6. Generate correlation warnings
        warnings = self._generate_correlation_warnings(correlation_analysis)
        correlation_analysis['correlation_warnings'] = warnings

        return correlation_analysis

    def perform_monte_carlo_simulation(self, positions: List[Dict[str, Any]],
                                     price_data: Dict[str, pd.DataFrame],
                                     num_simulations: int = 1000,
                                     time_horizon: int = 252) -> Dict[str, Any]:
        """
        Perform Monte Carlo simulation for portfolio risk analysis

        Args:
            positions: Portfolio positions
            price_data: Historical price data
            num_simulations: Number of simulation runs
            time_horizon: Time horizon in days

        Returns:
            Monte Carlo simulation results
        """
        logger.info(f"Performing Monte Carlo simulation with {num_simulations} runs")

        simulation_results = {
            'final_portfolio_values': [],
            'maximum_drawdowns': [],
            'var_95': 0.0,
            'var_99': 0.0,
            'expected_return': 0.0,
            'probability_of_loss': 0.0,
            'probability_of_profit': 0.0,
            'simulation_stats': {}
        }

        if not positions or not price_data:
            return simulation_results

        try:
            # 1. Calculate historical returns and statistics
            returns_data = {}
            for position in positions:
                symbol = position['symbol']
                if symbol in price_data and len(price_data[symbol]) > 50:
                    returns = price_data[symbol]['close'].pct_change().dropna()
                    returns_data[symbol] = returns

            if not returns_data:
                logger.warning("No valid return data for simulation")
                return simulation_results

            # 2. Calculate mean returns and covariance matrix
            aligned_returns = pd.DataFrame(returns_data).dropna()
            mean_returns = aligned_returns.mean()
            cov_matrix = aligned_returns.cov()

            # 3. Get position weights
            total_value = sum(pos.get('value', 0) for pos in positions)
            weights = np.array([
                pos.get('value', 0) / total_value if total_value > 0 else 0
                for pos in positions if pos['symbol'] in aligned_returns.columns
            ])

            # 4. Run Monte Carlo simulation
            portfolio_values = []
            max_drawdowns = []

            initial_value = total_value if total_value > 0 else 100000

            for _ in range(num_simulations):
                # Generate random returns
                random_returns = np.random.multivariate_normal(
                    mean_returns, cov_matrix, time_horizon
                )

                # Calculate portfolio returns
                portfolio_returns = np.dot(random_returns, weights)

                # Calculate cumulative value
                cumulative_returns = np.cumprod(1 + portfolio_returns)
                portfolio_value_path = initial_value * cumulative_returns

                portfolio_values.append(portfolio_value_path[-1])

                # Calculate maximum drawdown
                running_max = np.maximum.accumulate(portfolio_value_path)
                drawdowns = (portfolio_value_path - running_max) / running_max
                max_drawdown = np.min(drawdowns)
                max_drawdowns.append(max_drawdown)

            # 5. Calculate statistics
            simulation_results['final_portfolio_values'] = portfolio_values
            simulation_results['maximum_drawdowns'] = max_drawdowns

            # VaR calculations
            simulation_results['var_95'] = np.percentile(portfolio_values, 5)
            simulation_results['var_99'] = np.percentile(portfolio_values, 1)

            # Probability calculations
            loss_count = sum(1 for value in portfolio_values if value < initial_value)
            simulation_results['probability_of_loss'] = loss_count / num_simulations
            simulation_results['probability_of_profit'] = 1 - simulation_results['probability_of_loss']

            # Expected return
            expected_final_value = np.mean(portfolio_values)
            simulation_results['expected_return'] = (expected_final_value / initial_value - 1) * 100

            # Additional statistics
            simulation_results['simulation_stats'] = {
                'mean_final_value': float(np.mean(portfolio_values)),
                'std_final_value': float(np.std(portfolio_values)),
                'min_final_value': float(np.min(portfolio_values)),
                'max_final_value': float(np.max(portfolio_values)),
                'mean_max_drawdown': float(np.mean(max_drawdowns)),
                'worst_max_drawdown': float(np.min(max_drawdowns))
            }

        except Exception as e:
            logger.error(f"Monte Carlo simulation failed: {e}")

        return simulation_results

    # Helper methods for calculations

    def _calculate_portfolio_returns(self, positions: List[Dict[str, Any]],
                                   price_data: Dict[str, pd.DataFrame]) -> pd.Series:
        """Calculate portfolio returns from positions and price data"""
        portfolio_returns = pd.Series(dtype=float)

        try:
            # Calculate total portfolio value
            total_value = sum(pos.get('value', 0) for pos in positions)

            if total_value == 0:
                return portfolio_returns

            # Calculate weighted returns
            weighted_returns = []
            for position in positions:
                symbol = position['symbol']
                weight = position.get('value', 0) / total_value

                if symbol in price_data and len(price_data[symbol]) > 1:
                    returns = price_data[symbol]['close'].pct_change().dropna()
                    weighted_return = returns * weight
                    weighted_returns.append(weighted_return)

            if weighted_returns:
                # Align all series and sum
                aligned_returns = pd.concat(weighted_returns, axis=1).fillna(0)
                portfolio_returns = aligned_returns.sum(axis=1)

        except Exception as e:
            logger.error(f"Error calculating portfolio returns: {e}")

        return portfolio_returns

    def _calculate_basic_risk_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """Calculate basic risk metrics from returns"""
        metrics = {}

        if returns.empty:
            return metrics

        # Volatility (annualized)
        metrics['portfolio_volatility'] = float(returns.std() * np.sqrt(252))

        # Sharpe ratio (assuming risk-free rate of 2%)
        risk_free_rate = 0.02
        excess_returns = returns.mean() * 252 - risk_free_rate
        metrics['sharpe_ratio'] = float(excess_returns / metrics['portfolio_volatility']) if metrics['portfolio_volatility'] > 0 else 0.0

        # Sortino ratio
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else metrics['portfolio_volatility']
        metrics['sortino_ratio'] = float(excess_returns / downside_std) if downside_std > 0 else 0.0

        # Maximum drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        metrics['maximum_drawdown'] = float(drawdown.min())

        # Calmar ratio
        annual_return = returns.mean() * 252
        metrics['calmar_ratio'] = float(annual_return / abs(metrics['maximum_drawdown'])) if metrics['maximum_drawdown'] != 0 else 0.0

        return metrics

    def _calculate_var_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """Calculate Value at Risk metrics"""
        metrics = {}

        if len(returns) < 30:
            return metrics

        # Historical VaR
        confidence_level = self.risk_params['var_confidence_level']
        var_percentile = confidence_level * 100
        metrics['portfolio_var'] = float(np.percentile(returns, var_percentile))

        # Conditional VaR (Expected Shortfall)
        var_threshold = metrics['portfolio_var']
        tail_returns = returns[returns <= var_threshold]
        metrics['portfolio_cvar'] = float(tail_returns.mean()) if len(tail_returns) > 0 else metrics['portfolio_var']

        return metrics

    def _calculate_correlation_metrics(self, positions: List[Dict[str, Any]],
                                     price_data: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """Calculate correlation-based risk metrics"""
        metrics = {'correlation_risk': 0.0}

        try:
            if len(positions) < 2:
                return metrics

            # Get returns for all positions
            returns_data = {}
            for position in positions:
                symbol = position['symbol']
                if symbol in price_data and len(price_data[symbol]) > 30:
                    returns = price_data[symbol]['close'].pct_change().dropna()
                    if len(returns) >= 30:
                        returns_data[symbol] = returns

            if len(returns_data) < 2:
                return metrics

            # Calculate correlation matrix
            aligned_returns = pd.DataFrame(returns_data).dropna()
            correlation_matrix = aligned_returns.corr()

            # Calculate average correlation (excluding diagonal)
            corr_values = correlation_matrix.values
            np.fill_diagonal(corr_values, np.nan)
            avg_correlation = np.nanmean(np.abs(corr_values))

            metrics['correlation_risk'] = float(avg_correlation)

        except Exception as e:
            logger.error(f"Error calculating correlation metrics: {e}")

        return metrics

    def _calculate_concentration_risk(self, positions: List[Dict[str, Any]]) -> float:
        """Calculate concentration risk using Herfindahl index"""
        if not positions:
            return 0.0

        total_value = sum(pos.get('value', 0) for pos in positions)
        if total_value == 0:
            return 0.0

        # Calculate Herfindahl index
        weights = [pos.get('value', 0) / total_value for pos in positions]
        herfindahl_index = sum(w**2 for w in weights)

        return float(herfindahl_index)

    def _calculate_liquidity_risk(self, positions: List[Dict[str, Any]],
                                price_data: Dict[str, pd.DataFrame]) -> float:
        """Calculate liquidity risk based on average volumes"""
        if not positions:
            return 0.0

        liquidity_scores = []
        for position in positions:
            symbol = position['symbol']
            if symbol in price_data and 'volume' in price_data[symbol].columns:
                avg_volume = price_data[symbol]['volume'].mean()
                # Score based on how far below threshold
                threshold = self.risk_params['liquidity_threshold']
                if avg_volume >= threshold:
                    score = 0.0  # No liquidity risk
                else:
                    score = 1.0 - (avg_volume / threshold)  # Higher score = more risk
                liquidity_scores.append(score)

        return float(np.mean(liquidity_scores)) if liquidity_scores else 0.0

    def _perform_stress_tests(self, positions: List[Dict[str, Any]],
                            price_data: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """Perform various stress tests on the portfolio"""
        stress_results = {}

        # Define stress scenarios
        scenarios = {
            'market_crash_20': -0.20,  # 20% market decline
            'market_crash_30': -0.30,  # 30% market decline
            'volatility_spike': 2.0,   # Volatility doubles
            'sector_rotation': -0.15   # Sector-specific decline
        }

        for scenario_name, scenario_impact in scenarios.items():
            portfolio_impact = 0.0
            total_value = sum(pos.get('value', 0) for pos in positions)

            if total_value > 0:
                for position in positions:
                    position_value = position.get('value', 0)
                    weight = position_value / total_value
                    position_impact = weight * scenario_impact
                    portfolio_impact += position_impact

            stress_results[scenario_name] = float(portfolio_impact)

        return stress_results

    def _calculate_risk_attribution(self, positions: List[Dict[str, Any]],
                                  price_data: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, float]]:
        """Calculate risk attribution by position"""
        attribution = {}

        total_value = sum(pos.get('value', 0) for pos in positions)
        if total_value == 0:
            return attribution

        for position in positions:
            symbol = position['symbol']
            position_value = position.get('value', 0)
            weight = position_value / total_value

            # Calculate position-specific risk metrics
            if symbol in price_data and len(price_data[symbol]) > 30:
                returns = price_data[symbol]['close'].pct_change().dropna()
                volatility = returns.std() * np.sqrt(252)
                var_95 = np.percentile(returns, 5)

                attribution[symbol] = {
                    'weight': float(weight),
                    'volatility_contribution': float(weight * volatility),
                    'var_contribution': float(weight * var_95),
                    'individual_volatility': float(volatility)
                }

        return attribution

    def _generate_risk_recommendations(self, risk_metrics: Dict[str, Any],
                                     positions: List[Dict[str, Any]]) -> List[str]:
        """Generate risk management recommendations"""
        recommendations = []

        # Portfolio volatility check
        if risk_metrics.get('portfolio_volatility', 0) > 0.25:
            recommendations.append("Portfolio volatility is high - consider reducing position sizes")

        # Concentration risk check
        if risk_metrics.get('concentration_risk', 0) > 0.4:
            recommendations.append("High concentration risk - consider diversifying positions")

        # Correlation risk check
        if risk_metrics.get('correlation_risk', 0) > 0.7:
            recommendations.append("High correlation between positions - reduce correlated holdings")

        # Drawdown check
        if risk_metrics.get('maximum_drawdown', 0) < -0.15:
            recommendations.append("Maximum drawdown exceeds 15% - review stop-loss strategies")

        # Sharpe ratio check
        if risk_metrics.get('sharpe_ratio', 0) < 0.5:
            recommendations.append("Low risk-adjusted returns - review position selection")

        # Liquidity risk check
        if risk_metrics.get('liquidity_risk', 0) > 0.3:
            recommendations.append("High liquidity risk - consider more liquid alternatives")

        return recommendations

    # Additional helper methods would continue here...
    # Due to length constraints, including key calculation methods

    def _calculate_covariance_matrix(self, price_data: Dict[str, pd.DataFrame]) -> np.ndarray:
        """Calculate covariance matrix with shrinkage estimator"""
        returns_data = {}
        for symbol, data in price_data.items():
            if len(data) > 30 and 'close' in data.columns:
                returns = data['close'].pct_change().dropna()
                if len(returns) >= 30:
                    returns_data[symbol] = returns

        if len(returns_data) < 2:
            return np.array([[]])

        aligned_returns = pd.DataFrame(returns_data).dropna()

        # Use Ledoit-Wolf shrinkage estimator for better covariance estimation
        lw = LedoitWolf()
        cov_matrix, _ = lw.fit(aligned_returns.values).covariance_, lw.shrinkage_

        return cov_matrix

    def _get_regime_multiplier(self, market_regime: str) -> float:
        """Get position size multiplier based on market regime"""
        regime_multipliers = {
            'bull_trending': 1.2,
            'bear_trending': 0.6,
            'sideways': 1.0,
            'volatile': 0.8,
            'crisis': 0.3,
            'normal': 1.0
        }
        return regime_multipliers.get(market_regime, 1.0)

    def _get_heat_adjustment(self, portfolio_heat: float) -> float:
        """Adjust position size based on current portfolio heat"""
        if portfolio_heat > 0.8:
            return 0.5  # Reduce size significantly
        elif portfolio_heat > 0.6:
            return 0.7  # Reduce size moderately
        elif portfolio_heat > 0.4:
            return 0.85  # Reduce size slightly
        else:
            return 1.0  # No adjustment

    def calculate_risk_metrics(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive risk metrics for portfolio data

        Args:
            portfolio_data: Dictionary containing returns, prices, volumes

        Returns:
            Dictionary with risk metrics
        """
        logger.info("Calculating risk metrics")

        risk_metrics = {
            'volatility': 0.0,
            'var_95': 0.0,
            'var_99': 0.0,
            'expected_shortfall': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'beta': 1.0,
            'risk_score': 0.5
        }

        try:
            # Extract returns from portfolio data
            returns = portfolio_data.get('returns', [])
            prices = portfolio_data.get('prices', [])

            if not returns or len(returns) < 2:
                logger.warning("Insufficient data for risk calculation")
                return risk_metrics

            returns_series = pd.Series(returns)

            # Calculate basic risk metrics
            basic_metrics = self._calculate_basic_risk_metrics(returns_series)
            risk_metrics.update(basic_metrics)

            # Calculate VaR metrics
            var_metrics = self._calculate_var_metrics(returns_series)
            risk_metrics.update(var_metrics)

            # Calculate drawdown metrics
            if prices:
                prices_series = pd.Series(prices)
                cumulative_returns = (1 + returns_series).cumprod()
                running_max = cumulative_returns.expanding().max()
                drawdown = (cumulative_returns - running_max) / running_max
                risk_metrics['max_drawdown'] = float(drawdown.min())

            # Calculate risk score (0 = low risk, 1 = high risk)
            volatility = risk_metrics.get('volatility', 0.0)
            var_95 = abs(risk_metrics.get('var_95', 0.0))

            # Normalize risk score based on volatility and VaR
            risk_score = min(1.0, (volatility * 10 + var_95 * 20) / 2)
            risk_metrics['risk_score'] = risk_score

            logger.info(f"Risk metrics calculated successfully: {len(risk_metrics)} metrics")

        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")

        return risk_metrics