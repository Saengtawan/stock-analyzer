"""
Database Manager
================
Unified database connection manager with connection pooling,
WAL mode, and proper error handling.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from loguru import logger


class DatabaseManager:
    """
    Centralized database connection manager.
    
    Features:
    - Connection pooling (thread-local connections)
    - WAL mode for concurrent reads
    - Foreign key enforcement
    - Automatic error handling and rollback
    - Context manager support
    """
    
    def __init__(self, db_path: str, read_only: bool = False):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
            read_only: If True, open in read-only mode
        """
        self.db_path = str(Path(db_path).resolve())
        self.read_only = read_only
        self._local = threading.local()
        
        # Ensure database file exists (unless read-only)
        if not read_only:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
        # Initialize database with WAL mode
        if not read_only and os.path.exists(self.db_path):
            self._init_wal_mode()
    
    def _init_wal_mode(self):
        """Initialize WAL mode for better concurrent access."""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA temp_store = MEMORY")
                conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to set WAL mode: {e}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local connection (connection pooling).
        
        Returns:
            Thread-local SQLite connection
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            # Create new connection for this thread
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False
            )
            
            # Enable optimizations
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA cache_size = -32000")  # 32MB cache
            
            # Row factory for dict-like access
            conn.row_factory = sqlite3.Row
            
            self._local.connection = conn
            
        return self._local.connection
    
    @contextmanager
    def get_connection(self, read_only: bool = False) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for database connections.
        
        Usage:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trades")
                
        Args:
            read_only: If True, don't commit changes
            
        Yields:
            SQLite connection
        """
        conn = self._get_connection()
        
        try:
            yield conn
            
            # Commit if not read-only
            if not read_only and not self.read_only:
                conn.commit()
                
        except Exception as e:
            # Rollback on error
            if not read_only and not self.read_only:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
    
    def execute(self, query: str, params: tuple = (), commit: bool = True) -> sqlite3.Cursor:
        """
        Execute a single query.
        
        Args:
            query: SQL query
            params: Query parameters
            commit: Whether to commit after execution
            
        Returns:
            Cursor with results
        """
        with self.get_connection(read_only=not commit) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor
    
    def execute_many(self, query: str, params_list: list, commit: bool = True) -> sqlite3.Cursor:
        """
        Execute query with multiple parameter sets.
        
        Args:
            query: SQL query
            params_list: List of parameter tuples
            commit: Whether to commit after execution
            
        Returns:
            Cursor with results
        """
        with self.get_connection(read_only=not commit) as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            return cursor
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """
        Fetch single row.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Single row or None
        """
        with self.get_connection(read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    
    def fetch_all(self, query: str, params: tuple = ()) -> list:
        """
        Fetch all rows.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            List of rows
        """
        with self.get_connection(read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def close(self):
        """Close thread-local connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._local.connection = None
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()


# Global database managers (lazy initialization)
_db_managers = {}
_db_lock = threading.Lock()


def get_db_manager(db_name: str = 'trade_history') -> DatabaseManager:
    """
    Get or create database manager (singleton per database).

    Args:
        db_name: Database name ('trade_history', 'stocks')

    Returns:
        DatabaseManager instance
    """
    if db_name not in _db_managers:
        with _db_lock:
            if db_name not in _db_managers:
                # Determine database path
                if db_name == 'trade_history':
                    db_path = 'data/trade_history.db'
                elif db_name == 'stocks':
                    db_path = 'data/database/stocks.db'
                else:
                    raise ValueError(f"Unknown database: {db_name}")

                _db_managers[db_name] = DatabaseManager(db_path)

    return _db_managers[db_name]


def close_all_connections():
    """
    Close all database connections (for graceful shutdown).

    This should be called during application shutdown to ensure
    all database connections are properly closed.
    """
    with _db_lock:
        for db_name, manager in _db_managers.items():
            try:
                manager.close()
                logger.debug(f"Closed connection for {db_name}")
            except Exception as e:
                logger.warning(f"Error closing {db_name}: {e}")
        _db_managers.clear()
