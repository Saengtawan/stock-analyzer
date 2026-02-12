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

from .manager import DatabaseManager
from .models import Trade, Position, StockPrice
from .repositories import TradeRepository, PositionRepository, StockDataRepository
from .repositories.alerts_repository import AlertsRepository, Alert

__all__ = [
    'DatabaseManager',
    'Trade',
    'Position',
    'StockPrice',
    'TradeRepository',
    'PositionRepository',
    'StockDataRepository',
    'AlertsRepository',
    'Alert',
]
