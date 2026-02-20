#!/usr/bin/env python3
"""
Sector Filter - v6.33
Filters out weak sectors based on backtest results (2023-2025).

Backtest Results:
- Full universe (987 stocks): 36.2% WR, 20.0% CAGR
- Sector filtered (606 stocks): 38.1% WR, 27.7% CAGR (+48% profit improvement)

Excluded sectors:
- Materials: Cyclical, commodity-driven (weak mean reversion)
- Consumer Staples: Low volatility, defensive (poor dip-bounce candidates)
- Media: Disrupted industry, erratic moves
- Aerospace: Defense spending cycles, low volume
- Energy/Oil: Commodity-driven, geopolitical risk

Good sectors retained:
- Technology, Healthcare, Finance, Consumer Discretionary,
- Industrials, Communications, Utilities, Real Estate
"""
from typing import List, Optional
from loguru import logger


class SectorFilter:
    """Filter signals by sector to improve win rate."""

    # Sectors to EXCLUDE (from backtest analysis)
    WEAK_SECTORS = {
        'Materials',
        'Basic Materials',
        'Consumer Staples',
        'Consumer Defensive',
        'Media',
        'Communication Services',  # If it's primarily media-heavy
        'Aerospace',
        'Aerospace & Defense',
        'Energy',
        'Oil & Gas',
        'Energy/Oil',
    }

    def __init__(self, enabled: bool = True):
        """
        Initialize sector filter.

        Args:
            enabled: Whether to apply sector filtering
        """
        self.enabled = enabled
        self.filtered_count = 0
        self.total_count = 0
        logger.info(f"🏭 Sector Filter initialized (enabled={enabled})")
        logger.info(f"   Excluding sectors: {', '.join(sorted(self.WEAK_SECTORS))}")

    def filter_signals(self, signals: List) -> List:
        """
        Filter out signals from weak sectors.

        Args:
            signals: List of RapidRotationSignal objects

        Returns:
            Filtered list of signals (only good sectors)
        """
        if not self.enabled:
            return signals

        if not signals:
            return []

        self.total_count += len(signals)

        # Filter out weak sectors
        filtered = []
        for signal in signals:
            sector = getattr(signal, 'sector', None)

            # If sector unknown, allow (assume it's OK)
            if not sector or sector == 'Unknown':
                filtered.append(signal)
                continue

            # Check if sector is in weak list
            if sector in self.WEAK_SECTORS:
                self.filtered_count += 1
                logger.debug(f"❌ Filtered {signal.symbol} (sector: {sector})")
                continue

            # Good sector - keep it
            filtered.append(signal)

        removed = len(signals) - len(filtered)
        if removed > 0:
            logger.info(f"🏭 Sector filter: {len(filtered)}/{len(signals)} signals passed "
                       f"({removed} removed from weak sectors)")

        return filtered

    def get_stats(self) -> dict:
        """
        Get filter statistics.

        Returns:
            Dictionary with filter stats
        """
        return {
            'enabled': self.enabled,
            'total_evaluated': self.total_count,
            'total_filtered': self.filtered_count,
            'filter_rate_pct': (self.filtered_count / self.total_count * 100) if self.total_count > 0 else 0,
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self.filtered_count = 0
        self.total_count = 0
        logger.debug("🏭 Sector filter stats reset")

    @classmethod
    def is_good_sector(cls, sector: Optional[str]) -> bool:
        """
        Check if a sector is good (not in weak list).

        Args:
            sector: Sector name to check

        Returns:
            True if sector is good or unknown, False if weak
        """
        if not sector or sector == 'Unknown':
            return True  # Unknown = assume OK
        return sector not in cls.WEAK_SECTORS


if __name__ == '__main__':
    # Quick test
    print("Sector Filter - Weak Sectors List:")
    for sector in sorted(SectorFilter.WEAK_SECTORS):
        print(f"  ❌ {sector}")

    print("\nExample usage:")
    print("  filter = SectorFilter(enabled=True)")
    print("  filtered = filter.filter_signals(signals)")
