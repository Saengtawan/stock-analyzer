"""
Alternative Data Sources Package
Combines multiple data sources to improve stock predictions
"""

from .insider_trading import InsiderTradingTracker
from .analyst_ratings import AnalystRatingsTracker
from .short_interest import ShortInterestTracker
from .social_sentiment import SocialSentimentTracker
from .correlation_pairs import CorrelationTracker
from .macro_indicators import MacroIndicatorsTracker

__all__ = [
    'InsiderTradingTracker',
    'AnalystRatingsTracker',
    'ShortInterestTracker',
    'SocialSentimentTracker',
    'CorrelationTracker',
    'MacroIndicatorsTracker'
]
