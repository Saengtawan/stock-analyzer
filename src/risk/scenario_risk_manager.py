"""
Scenario-Based Risk Management
Manages risk based on multiple downside scenarios with proper buffers
"""
from typing import Dict, Any, List
from dataclasses import dataclass
import numpy as np
from loguru import logger


@dataclass
class RiskScenario:
    """Risk scenario definition"""
    name: str
    probability: float
    price_target: float
    max_drawdown: float
    required_buffer: float  # Extra safety margin needed


class ScenarioRiskManager:
    """Manage risk based on multiple scenarios"""

    def __init__(self):
        """Initialize scenario risk manager"""
        self.buffer_configs = {
            'conservative': {
                'worst_case_weight': 0.5,
                'bad_case_weight': 0.3,
                'base_case_weight': 0.2,
                'minimum_buffer_pct': 0.15  # 15% buffer
            },
            'medium': {
                'worst_case_weight': 0.3,
                'bad_case_weight': 0.4,
                'base_case_weight': 0.3,
                'minimum_buffer_pct': 0.10  # 10% buffer
            },
            'aggressive': {
                'worst_case_weight': 0.1,
                'bad_case_weight': 0.3,
                'base_case_weight': 0.6,
                'minimum_buffer_pct': 0.05  # 5% buffer
            }
        }

    def calculate_scenario_based_stops(self,
                                      current_price: float,
                                      scenarios: Dict[str, Any],
                                      risk_tolerance: str = 'medium') -> Dict[str, Any]:
        """
        Calculate stop-loss and position sizing based on scenarios

        Args:
            current_price: Current stock price
            scenarios: Risk scenarios from _generate_risk_scenarios()
            risk_tolerance: 'conservative', 'medium', or 'aggressive'

        Returns:
            Dictionary with scenario-based risk management recommendations
        """
        logger.info(f"Calculating scenario-based risk management for price ${current_price:.2f}")

        if not scenarios or 'scenarios' in scenarios:
            scenarios = scenarios.get('scenarios', {})

        if not scenarios:
            logger.warning("No scenarios provided, using conservative defaults")
            return self._get_default_risk_management(current_price, risk_tolerance)

        config = self.buffer_configs.get(risk_tolerance, self.buffer_configs['medium'])

        # Extract scenario returns
        worst_return = scenarios.get('worst_case', {}).get('return', -0.20)
        bad_return = scenarios.get('bad_case', {}).get('return', -0.10)
        base_return = scenarios.get('base_case', {}).get('return', 0.00)

        # Calculate weighted downside
        weighted_downside = (
            worst_return * config['worst_case_weight'] +
            bad_return * config['bad_case_weight'] +
            base_return * config['base_case_weight']
        )

        # Calculate stop-loss with buffer
        scenario_stop_loss = current_price * (1 + weighted_downside - config['minimum_buffer_pct'])

        # Calculate maximum loss in worst case
        worst_case_price = scenarios.get('worst_case', {}).get('price_target', current_price * 0.8)
        max_potential_loss = ((worst_case_price - current_price) / current_price) * 100

        # Adjust position size based on worst-case scenario
        position_size_adjustment = self._calculate_position_adjustment(
            max_potential_loss, risk_tolerance
        )

        # Calculate expected value across scenarios
        expected_value = self._calculate_expected_value(scenarios, current_price)

        return {
            'scenario_based_stop_loss': round(scenario_stop_loss, 2),
            'weighted_downside_pct': round(weighted_downside * 100, 2),
            'worst_case_max_loss_pct': round(max_potential_loss, 2),
            'recommended_position_size_multiplier': position_size_adjustment,
            'buffer_applied_pct': round(config['minimum_buffer_pct'] * 100, 2),
            'risk_tolerance': risk_tolerance,
            'expected_value': expected_value,
            'scenario_breakdown': {
                'worst_case': {
                    'price': worst_case_price,
                    'loss_pct': round(((worst_case_price - current_price) / current_price) * 100, 2),
                    'weight': config['worst_case_weight'],
                    'probability': scenarios.get('worst_case', {}).get('probability', 0.05)
                },
                'bad_case': {
                    'price': scenarios.get('bad_case', {}).get('price_target', current_price * 0.90),
                    'loss_pct': round(((scenarios.get('bad_case', {}).get('price_target', current_price * 0.90) - current_price) / current_price) * 100, 2),
                    'weight': config['bad_case_weight'],
                    'probability': scenarios.get('bad_case', {}).get('probability', 0.20)
                },
                'base_case': {
                    'price': scenarios.get('base_case', {}).get('price_target', current_price),
                    'return_pct': round(((scenarios.get('base_case', {}).get('price_target', current_price) - current_price) / current_price) * 100, 2),
                    'weight': config['base_case_weight'],
                    'probability': scenarios.get('base_case', {}).get('probability', 0.50)
                },
                'good_case': {
                    'price': scenarios.get('good_case', {}).get('price_target', current_price * 1.10),
                    'return_pct': round(((scenarios.get('good_case', {}).get('price_target', current_price * 1.10) - current_price) / current_price) * 100, 2),
                    'probability': scenarios.get('good_case', {}).get('probability', 0.20)
                },
                'best_case': {
                    'price': scenarios.get('best_case', {}).get('price_target', current_price * 1.20),
                    'return_pct': round(((scenarios.get('best_case', {}).get('price_target', current_price * 1.20) - current_price) / current_price) * 100, 2),
                    'probability': scenarios.get('best_case', {}).get('probability', 0.05)
                }
            },
            'risk_assessment': self._assess_risk_level(max_potential_loss, expected_value)
        }

    def _calculate_position_adjustment(self, max_loss_pct: float,
                                      risk_tolerance: str) -> float:
        """Adjust position size based on worst-case scenario"""

        # Base position sizes
        base_sizes = {
            'conservative': 0.60,  # 60% of normal
            'medium': 0.80,        # 80% of normal
            'aggressive': 1.00     # 100% of normal
        }

        base_size = base_sizes.get(risk_tolerance, 0.80)

        # Further reduce if worst case is catastrophic
        if abs(max_loss_pct) > 50:
            return base_size * 0.5  # Cut in half
        elif abs(max_loss_pct) > 30:
            return base_size * 0.75
        elif abs(max_loss_pct) > 20:
            return base_size * 0.9
        else:
            return base_size

    def _calculate_expected_value(self, scenarios: Dict[str, Any],
                                  current_price: float) -> Dict[str, Any]:
        """Calculate expected value across all scenarios"""

        # Extract probabilities and returns
        scenario_data = []
        for scenario_name in ['worst_case', 'bad_case', 'base_case', 'good_case', 'best_case']:
            scenario = scenarios.get(scenario_name, {})
            if scenario:
                prob = scenario.get('probability', 0)
                price = scenario.get('price_target', current_price)
                ret = scenario.get('return', 0)

                scenario_data.append({
                    'name': scenario_name,
                    'probability': prob,
                    'price': price,
                    'return': ret
                })

        # Calculate expected return
        expected_return = sum(s['probability'] * s['return'] for s in scenario_data)

        # Calculate expected price
        expected_price = sum(s['probability'] * s['price'] for s in scenario_data)

        # Calculate variance and std dev
        variance = sum(
            s['probability'] * (s['return'] - expected_return) ** 2
            for s in scenario_data
        )
        std_dev = np.sqrt(variance)

        return {
            'expected_return': round(expected_return, 4),
            'expected_price': round(expected_price, 2),
            'expected_return_pct': round(expected_return * 100, 2),
            'std_dev': round(std_dev, 4),
            'risk_reward_ratio': round(expected_return / std_dev, 2) if std_dev > 0 else 0
        }

    def _assess_risk_level(self, max_loss_pct: float,
                          expected_value: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall risk level"""

        risk_score = 0

        # Factor 1: Max potential loss
        if abs(max_loss_pct) > 50:
            risk_score += 4
            max_loss_risk = 'Very High'
        elif abs(max_loss_pct) > 30:
            risk_score += 3
            max_loss_risk = 'High'
        elif abs(max_loss_pct) > 20:
            risk_score += 2
            max_loss_risk = 'Medium'
        else:
            risk_score += 1
            max_loss_risk = 'Low'

        # Factor 2: Expected return
        expected_ret = expected_value.get('expected_return_pct', 0)
        if expected_ret < -10:
            risk_score += 3
            expected_return_risk = 'High'
        elif expected_ret < 0:
            risk_score += 2
            expected_return_risk = 'Medium'
        else:
            risk_score += 0
            expected_return_risk = 'Low'

        # Factor 3: Risk-reward ratio
        risk_reward = expected_value.get('risk_reward_ratio', 0)
        if risk_reward < 0.5:
            risk_score += 2
            risk_reward_assessment = 'Poor'
        elif risk_reward < 1.0:
            risk_score += 1
            risk_reward_assessment = 'Fair'
        else:
            risk_score += 0
            risk_reward_assessment = 'Good'

        # Overall assessment
        if risk_score >= 7:
            overall_risk = 'Very High'
            recommendation = 'Avoid or use minimal position size'
        elif risk_score >= 5:
            overall_risk = 'High'
            recommendation = 'Reduce position size significantly'
        elif risk_score >= 3:
            overall_risk = 'Medium'
            recommendation = 'Use moderate position size with tight stops'
        else:
            overall_risk = 'Low'
            recommendation = 'Normal position sizing acceptable'

        return {
            'overall_risk': overall_risk,
            'risk_score': risk_score,
            'recommendation': recommendation,
            'factors': {
                'max_loss_risk': max_loss_risk,
                'expected_return_risk': expected_return_risk,
                'risk_reward_assessment': risk_reward_assessment
            }
        }

    def _get_default_risk_management(self, current_price: float,
                                    risk_tolerance: str) -> Dict[str, Any]:
        """Get default risk management if scenarios not available"""

        default_stop_pcts = {
            'conservative': 0.05,  # 5% stop
            'medium': 0.08,        # 8% stop
            'aggressive': 0.10     # 10% stop
        }

        stop_pct = default_stop_pcts.get(risk_tolerance, 0.08)
        stop_price = current_price * (1 - stop_pct)

        return {
            'scenario_based_stop_loss': round(stop_price, 2),
            'weighted_downside_pct': round(-stop_pct * 100, 2),
            'worst_case_max_loss_pct': round(-stop_pct * 100, 2),
            'recommended_position_size_multiplier': 0.8,
            'buffer_applied_pct': 0,
            'risk_tolerance': risk_tolerance,
            'note': 'Using default risk management (scenarios not available)'
        }


# Test function
if __name__ == "__main__":
    # Create sample scenarios
    scenarios = {
        'worst_case': {'probability': 0.05, 'return': -0.40, 'price_target': 60.0},
        'bad_case': {'probability': 0.20, 'return': -0.15, 'price_target': 85.0},
        'base_case': {'probability': 0.50, 'return': 0.05, 'price_target': 105.0},
        'good_case': {'probability': 0.20, 'return': 0.25, 'price_target': 125.0},
        'best_case': {'probability': 0.05, 'return': 0.50, 'price_target': 150.0}
    }

    manager = ScenarioRiskManager()

    # Test with different risk tolerances
    for tolerance in ['conservative', 'medium', 'aggressive']:
        print(f"\n{'='*60}")
        print(f"Risk Tolerance: {tolerance.upper()}")
        print('='*60)

        result = manager.calculate_scenario_based_stops(
            current_price=100.0,
            scenarios=scenarios,
            risk_tolerance=tolerance
        )

        print(f"\nScenario-Based Stop Loss: ${result['scenario_based_stop_loss']}")
        print(f"Weighted Downside: {result['weighted_downside_pct']}%")
        print(f"Worst Case Max Loss: {result['worst_case_max_loss_pct']}%")
        print(f"Position Size Multiplier: {result['recommended_position_size_multiplier']:.2f}x")
        print(f"Buffer Applied: {result['buffer_applied_pct']}%")

        print(f"\nExpected Value:")
        ev = result['expected_value']
        print(f"  Expected Return: {ev['expected_return_pct']}%")
        print(f"  Expected Price: ${ev['expected_price']}")
        print(f"  Risk/Reward Ratio: {ev['risk_reward_ratio']}")

        print(f"\nRisk Assessment:")
        ra = result['risk_assessment']
        print(f"  Overall Risk: {ra['overall_risk']}")
        print(f"  Recommendation: {ra['recommendation']}")
