"""
PDT (Pattern Day Trader) Repository - Database access for PDT tracking

Handles CRUD operations for PDT compliance tracking:
- Record symbol entry dates (to prevent same-day sells)
- Check if symbol can be sold today
- Update exit dates when position closed
- Track PDT violations
"""

import sqlite3
from datetime import datetime, date
from typing import List, Dict, Optional
from pathlib import Path


class PDTRepository:
    """Repository for PDT tracking data"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            project_root = Path(__file__).parent.parent.parent.parent
            db_path = str(project_root / 'data' / 'trade_history.db')
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ========================================================================
    # Core Operations
    # ========================================================================

    def add_entry(self, symbol: str, entry_date: str = None, entry_time: str = None) -> bool:
        """
        Record that a symbol was bought (add to PDT tracking).

        Args:
            symbol: Stock symbol
            entry_date: Entry date (YYYY-MM-DD), defaults to today
            entry_time: Entry time (ISO datetime), defaults to now

        Returns:
            True if successful

        Note:
            Uses UPSERT - if symbol already exists, updates entry_date
        """
        conn = self._get_connection()
        try:
            if entry_date is None:
                entry_date = date.today().isoformat()
            if entry_time is None:
                entry_time = datetime.now().isoformat()

            # Upsert: INSERT or UPDATE if symbol exists
            conn.execute("""
                INSERT INTO pdt_tracking (symbol, entry_date, entry_time)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    entry_date = excluded.entry_date,
                    entry_time = excluded.entry_time,
                    exit_date = NULL,
                    exit_time = NULL,
                    same_day_exit = 0
            """, (symbol, entry_date, entry_time))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding PDT entry for {symbol}: {e}")
            return False
        finally:
            conn.close()

    def can_sell_today(self, symbol: str) -> bool:
        """
        Check if symbol can be sold today (not a same-day trade).

        Args:
            symbol: Stock symbol to check

        Returns:
            True if can sell (entry_date != today OR not in tracking)
            False if cannot sell (entry_date == today → PDT violation)
        """
        conn = self._get_connection()
        try:
            today = date.today().isoformat()

            row = conn.execute("""
                SELECT entry_date, exit_date
                FROM pdt_tracking
                WHERE symbol = ?
            """, (symbol,)).fetchone()

            if row is None:
                # Not in tracking = can sell (no entry recorded)
                return True

            if row['exit_date'] is not None:
                # Already exited = can sell
                return True

            # Check if entry_date is today
            if row['entry_date'] == today:
                # Entered today = CANNOT sell (PDT violation)
                return False

            # Entered before today = can sell
            return True

        finally:
            conn.close()

    def record_exit(self, symbol: str, exit_date: str = None, exit_time: str = None) -> bool:
        """
        Record that a symbol was sold (update PDT tracking).

        Args:
            symbol: Stock symbol
            exit_date: Exit date (YYYY-MM-DD), defaults to today
            exit_time: Exit time (ISO datetime), defaults to now

        Returns:
            True if successful

        Note:
            Automatically sets same_day_exit flag if entry_date == exit_date
        """
        conn = self._get_connection()
        try:
            if exit_date is None:
                exit_date = date.today().isoformat()
            if exit_time is None:
                exit_time = datetime.now().isoformat()

            # Update exit info
            conn.execute("""
                UPDATE pdt_tracking
                SET exit_date = ?,
                    exit_time = ?,
                    same_day_exit = CASE
                        WHEN entry_date = ? THEN 1
                        ELSE 0
                    END
                WHERE symbol = ?
            """, (exit_date, exit_time, exit_date, symbol))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error recording PDT exit for {symbol}: {e}")
            return False
        finally:
            conn.close()

    def remove_entry(self, symbol: str) -> bool:
        """
        Remove symbol from PDT tracking (e.g., after holding overnight).

        Args:
            symbol: Stock symbol

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM pdt_tracking WHERE symbol = ?", (symbol,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error removing PDT entry for {symbol}: {e}")
            return False
        finally:
            conn.close()

    # ========================================================================
    # Query Operations
    # ========================================================================

    def get_active_restrictions(self) -> List[str]:
        """
        Get all symbols with active PDT restrictions (entered today, not exited).

        Returns:
            List of symbols that cannot be sold today
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT symbol FROM v_active_pdt_restrictions
            """).fetchall()

            return [row['symbol'] for row in rows]
        finally:
            conn.close()

    def get_all_entries(self) -> Dict[str, str]:
        """
        Get all active PDT entries (for migration/compatibility).

        Returns:
            Dict mapping symbol -> entry_date (compatible with old JSON format)
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT symbol, entry_date
                FROM pdt_tracking
                WHERE exit_date IS NULL
                ORDER BY entry_date DESC
            """).fetchall()

            return {row['symbol']: row['entry_date'] for row in rows}
        finally:
            conn.close()

    def get_violations(self, days: int = 30) -> List[Dict]:
        """
        Get PDT violations (same-day trades) from last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of violation records
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM v_pdt_violations
                WHERE exit_date >= date('now', '-' || ? || ' days')
                ORDER BY exit_date DESC
            """, (days,)).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ========================================================================
    # Maintenance
    # ========================================================================

    def cleanup_old_entries(self, days: int = 30) -> int:
        """
        Delete old PDT entries (for audit trail cleanup).

        Args:
            days: Keep entries from last N days

        Returns:
            Number of entries deleted
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                DELETE FROM pdt_tracking
                WHERE exit_date IS NOT NULL
                  AND exit_date < date('now', '-' || ? || ' days')
            """, (days,))

            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            conn.close()

    # ========================================================================
    # Migration Support
    # ========================================================================

    def import_from_json(self, json_data: Dict[str, str]) -> int:
        """
        Import PDT entries from old JSON format.

        Args:
            json_data: Dict mapping symbol -> entry_date

        Returns:
            Number of entries imported
        """
        count = 0
        for symbol, entry_date in json_data.items():
            if self.add_entry(symbol, entry_date):
                count += 1
        return count

    def export_to_json(self) -> Dict[str, str]:
        """
        Export PDT entries to JSON format (for backup/compatibility).

        Returns:
            Dict mapping symbol -> entry_date
        """
        return self.get_all_entries()
