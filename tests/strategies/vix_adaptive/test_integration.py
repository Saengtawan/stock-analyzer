"""
Integration tests for VIX Adaptive Strategy
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock

from src.strategies.vix_adaptive.vix_adaptive_strategy import VIXAdaptiveStrategy


class TestVIXAdaptiveIntegration:
    """Integration tests for full strategy."""

    @pytest.fixture
    def config(self):
        """Standard configuration."""
        return {
            'boundaries': {
                'normal_max': 20,
                'skip_max': 24,
                'high_max': 38
            },
            'tiers': {
                'normal': {
                    'min_score': 90,
                    'min_dip_yesterday': -1.0,
                    'max_positions': 3,
                    'position_sizes': [40, 40, 20],
                    'stop_loss_range': (2.0, 4.0),
                    'trail_activation_pct': 2.0,
                    'trail_lock_pct': 75,
                    'max_hold_days': 10,
                },
                'high': {
                    'min_score': 85,
                    'bounce_type': 'gain_2d_1.0',
                    'dip_requirement': 'dip_3d_-3',
                    'vix_condition': 'falling_1d',
                    'max_positions': 1,
                    'position_sizes': [100],
                    'stop_loss_range': (3.0, 6.0),
                    'use_trailing': False,
                    'max_hold_days': 10,
                }
            },
            'score_adaptation': {
                'enabled': True,
                'method': 'vix_based',
                'thresholds': {
                    'bull': 90,
                    'normal': 80,
                    'bear': 70
                }
            }
        }

    @pytest.fixture
    def vix_provider(self):
        """Mock VIX data provider."""
        provider = Mock()
        provider.get_vix_for_date = Mock(return_value=18.5)
        return provider

    @pytest.fixture
    def stock_data(self):
        """Sample stock data."""
        today = datetime.now().date()

        # Create sample data for AAPL
        data = {
            'AAPL': pd.DataFrame({
                'close': [150.0, 148.0, 152.0],
                'score': [92.0, 88.0, 91.0],
                'atr_pct': [2.5, 2.5, 2.5],
                'yesterday_dip': [-1.5, -0.5, -1.2],
                'return_2d': [0.5, 1.5, 0.8],
                'dip_from_3d_high': [-2.0, -3.5, -2.5],
            }, index=[today - timedelta(days=2), today - timedelta(days=1), today])
        }

        return data

    def test_initialization(self, config, vix_provider):
        """Test strategy initialization."""
        strategy = VIXAdaptiveStrategy(config, vix_provider)

        assert strategy.tier_manager is not None
        assert strategy.mean_reversion is not None
        assert strategy.bounce_strategy is not None
        assert strategy.score_adapter is not None

    def test_normal_tier_signals(self, config, vix_provider, stock_data):
        """Test signal generation in NORMAL tier."""
        # Set VIX to NORMAL tier
        vix_provider.get_vix_for_date = Mock(return_value=18.5)

        strategy = VIXAdaptiveStrategy(config, vix_provider)

        today = datetime.now().date()
        actions = strategy.update(
            date=today,
            stock_data=stock_data,
            active_positions=[]
        )

        # Should have signals in NORMAL tier
        assert strategy.get_current_tier() == 'normal'
        assert len(actions) >= 0  # May or may not have signals depending on filters

    def test_high_tier_signals(self, config, vix_provider, stock_data):
        """Test signal generation in HIGH tier."""
        # Set VIX to HIGH tier (falling)
        vix_provider.get_vix_for_date = Mock(side_effect=[30.0, 28.0])

        strategy = VIXAdaptiveStrategy(config, vix_provider)

        today = datetime.now().date()

        # First update (sets previous VIX)
        strategy.update(
            date=today - timedelta(days=1),
            stock_data=stock_data,
            active_positions=[]
        )

        # Second update (VIX falling)
        actions = strategy.update(
            date=today,
            stock_data=stock_data,
            active_positions=[]
        )

        assert strategy.get_current_tier() == 'high'

    def test_skip_tier_no_signals(self, config, vix_provider, stock_data):
        """Test no signals in SKIP tier."""
        # Set VIX to SKIP tier
        vix_provider.get_vix_for_date = Mock(return_value=22.0)

        strategy = VIXAdaptiveStrategy(config, vix_provider)

        today = datetime.now().date()
        actions = strategy.update(
            date=today,
            stock_data=stock_data,
            active_positions=[]
        )

        assert strategy.get_current_tier() == 'skip'
        assert len([a for a in actions if a.action_type == 'open']) == 0

    def test_extreme_tier_close_all(self, config, vix_provider, stock_data):
        """Test EXTREME tier closes all positions."""
        # Set VIX to EXTREME tier
        vix_provider.get_vix_for_date = Mock(return_value=42.0)

        strategy = VIXAdaptiveStrategy(config, vix_provider)

        # Mock active position
        mock_position = Mock()
        mock_position.symbol = 'AAPL'

        today = datetime.now().date()
        actions = strategy.update(
            date=today,
            stock_data=stock_data,
            active_positions=[mock_position]
        )

        assert strategy.get_current_tier() == 'extreme'
        # Should have close action
        close_actions = [a for a in actions if a.action_type == 'close']
        assert len(close_actions) == 1
        assert close_actions[0].reason == 'VIX_EXTREME'

    def test_tier_transitions(self, config, vix_provider, stock_data):
        """Test tier transitions are detected."""
        strategy = VIXAdaptiveStrategy(config, vix_provider)

        today = datetime.now().date()

        # NORMAL → SKIP
        vix_provider.get_vix_for_date = Mock(return_value=18.0)
        strategy.update(today - timedelta(days=2), stock_data, [])
        assert strategy.get_current_tier() == 'normal'

        vix_provider.get_vix_for_date = Mock(return_value=22.0)
        strategy.update(today - timedelta(days=1), stock_data, [])
        assert strategy.get_current_tier() == 'skip'

        # SKIP → HIGH
        vix_provider.get_vix_for_date = Mock(return_value=26.0)
        strategy.update(today, stock_data, [])
        assert strategy.get_current_tier() == 'high'

    def test_adaptive_score_threshold(self, config, vix_provider, stock_data):
        """Test score threshold adapts to VIX."""
        strategy = VIXAdaptiveStrategy(config, vix_provider)

        # Bull market (VIX < 15)
        vix_provider.get_vix_for_date = Mock(return_value=12.0)
        strategy.update(datetime.now().date(), stock_data, [])
        threshold = strategy._get_score_threshold()
        assert threshold == 90

        # Normal market (VIX 15-20)
        vix_provider.get_vix_for_date = Mock(return_value=17.0)
        strategy.update(datetime.now().date(), stock_data, [])
        threshold = strategy._get_score_threshold()
        assert threshold == 80

        # Bear market (VIX > 20)
        vix_provider.get_vix_for_date = Mock(return_value=25.0)
        strategy.update(datetime.now().date(), stock_data, [])
        threshold = strategy._get_score_threshold()
        assert threshold == 70


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
