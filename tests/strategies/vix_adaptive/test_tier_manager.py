"""
Unit tests for VIXTierManager
"""

import pytest
from src.strategies.vix_adaptive.tier_manager import VIXTierManager


class TestVIXTierManager:
    """Test VIX tier detection."""

    @pytest.fixture
    def manager(self):
        """Create VIXTierManager with standard boundaries."""
        return VIXTierManager({
            'normal_max': 20,
            'skip_max': 24,
            'high_max': 38
        })

    def test_normal_tier(self, manager):
        """Test NORMAL tier detection (VIX < 20)."""
        assert manager.get_tier(12.5) == 'normal'
        assert manager.get_tier(19.9) == 'normal'

    def test_skip_tier(self, manager):
        """Test SKIP tier detection (VIX 20-24)."""
        assert manager.get_tier(20.0) == 'skip'
        assert manager.get_tier(22.5) == 'skip'
        assert manager.get_tier(23.9) == 'skip'

    def test_high_tier(self, manager):
        """Test HIGH tier detection (VIX 24-38)."""
        assert manager.get_tier(24.0) == 'high'
        assert manager.get_tier(30.0) == 'high'
        assert manager.get_tier(37.9) == 'high'

    def test_extreme_tier(self, manager):
        """Test EXTREME tier detection (VIX >= 38)."""
        assert manager.get_tier(38.0) == 'extreme'
        assert manager.get_tier(50.0) == 'extreme'
        assert manager.get_tier(82.7) == 'extreme'  # COVID peak

    def test_boundary_edges(self, manager):
        """Test exact boundary values."""
        # VIX = 20 should be SKIP, not NORMAL
        assert manager.get_tier(20.0) == 'skip'

        # VIX = 24 should be HIGH, not SKIP
        assert manager.get_tier(24.0) == 'high'

        # VIX = 38 should be EXTREME, not HIGH
        assert manager.get_tier(38.0) == 'extreme'

    def test_vix_direction_falling(self, manager):
        """Test VIX falling detection."""
        assert manager.get_vix_direction(18.5, 20.0) == 'falling'
        assert manager.get_vix_direction(25.0, 30.0) == 'falling'

    def test_vix_direction_rising(self, manager):
        """Test VIX rising detection."""
        assert manager.get_vix_direction(20.0, 18.5) == 'rising'
        assert manager.get_vix_direction(30.0, 25.0) == 'rising'

    def test_vix_direction_flat(self, manager):
        """Test VIX flat detection (< 0.1 change)."""
        assert manager.get_vix_direction(18.5, 18.5) == 'flat'
        assert manager.get_vix_direction(18.5, 18.45) == 'flat'

    def test_is_vix_falling(self, manager):
        """Test simple VIX falling check."""
        assert manager.is_vix_falling(18.5, 20.0) is True
        assert manager.is_vix_falling(20.0, 18.5) is False
        assert manager.is_vix_falling(18.5, 18.5) is False

    def test_invalid_boundaries(self):
        """Test that invalid boundaries raise error."""
        with pytest.raises(ValueError, match="Boundaries must be in order"):
            VIXTierManager({
                'normal_max': 24,  # Wrong order
                'skip_max': 20,
                'high_max': 38
            })

    def test_repr(self, manager):
        """Test string representation."""
        repr_str = repr(manager)
        assert 'VIXTierManager' in repr_str
        assert '20' in repr_str
        assert '24' in repr_str
        assert '38' in repr_str


class TestVIXTierManagerCustomBoundaries:
    """Test with custom boundaries."""

    def test_custom_boundaries(self):
        """Test manager with non-standard boundaries."""
        manager = VIXTierManager({
            'normal_max': 15,
            'skip_max': 20,
            'high_max': 30
        })

        assert manager.get_tier(10) == 'normal'
        assert manager.get_tier(17) == 'skip'
        assert manager.get_tier(25) == 'high'
        assert manager.get_tier(35) == 'extreme'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
