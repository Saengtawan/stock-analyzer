"""
Database Access Layer
=====================
Unified interface for all database operations.

Components:
- DatabaseManager: Connection pooling and management
- Models: Type-safe data models
- Repositories: Clean API for data access
- Validators: Data validation layer
"""

from .manager import DatabaseManager, close_all_connections
from .models import Trade, Position, StockPrice
from .repositories import TradeRepository, PositionRepository, StockDataRepository
from .repositories.alerts_repository import AlertsRepository, Alert
from .models.pre_filter_session import PreFilterSession
from .models.filtered_stock import FilteredStock
from .repositories.pre_filter_repository import PreFilterRepository

__all__ = [
    'DatabaseManager',
    'close_all_connections',
    'Trade',
    'Position',
    'StockPrice',
    'TradeRepository',
    'PositionRepository',
    'StockDataRepository',
    'AlertsRepository',
    'Alert',
    'PreFilterSession',
    'FilteredStock',
    'PreFilterRepository',
]
