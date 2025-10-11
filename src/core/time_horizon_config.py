"""
Time Horizon Configuration
Adjusts analysis parameters based on investment time horizon
"""
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class TimeHorizonConfig:
    """Configuration for a specific time horizon"""
    name: str
    days: int
    rsi_period: int
    macd_fast: int
    macd_slow: int
    macd_signal: int
    sma_short: int
    sma_medium: int
    sma_long: int
    lookback_days: int
    volatility_window: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'days': self.days,
            'rsi_period': self.rsi_period,
            'macd': {'fast': self.macd_fast, 'slow': self.macd_slow, 'signal': self.macd_signal},
            'sma': {'short': self.sma_short, 'medium': self.sma_medium, 'long': self.sma_long},
            'lookback_days': self.lookback_days,
            'volatility_window': self.volatility_window
        }


class TimeHorizonManager:
    """Manages time horizon configurations"""

    CONFIGS = {
        'short': TimeHorizonConfig(
            name='short',
            days=14,
            rsi_period=7,
            macd_fast=6,
            macd_slow=13,
            macd_signal=5,
            sma_short=5,
            sma_medium=10,
            sma_long=20,
            lookback_days=30,
            volatility_window=10
        ),
        'medium': TimeHorizonConfig(
            name='medium',
            days=120,
            rsi_period=14,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            sma_short=20,
            sma_medium=50,
            sma_long=100,
            lookback_days=90,
            volatility_window=20
        ),
        'long': TimeHorizonConfig(
            name='long',
            days=365,
            rsi_period=21,
            macd_fast=19,
            macd_slow=39,
            macd_signal=9,
            sma_short=50,
            sma_medium=100,
            sma_long=200,
            lookback_days=252,
            volatility_window=30
        )
    }

    @classmethod
    def get_config(cls, time_horizon: str) -> TimeHorizonConfig:
        """Get configuration for time horizon"""
        return cls.CONFIGS.get(time_horizon, cls.CONFIGS['medium'])
