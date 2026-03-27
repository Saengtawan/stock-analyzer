"""
PDT (Pattern Day Trader) Repository - Database access for PDT tracking

Handles CRUD operations for PDT compliance tracking:
- Record symbol entry dates (to prevent same-day sells)
- Check if symbol can be sold today
- Update exit dates when position closed
- Track PDT violations
"""

from datetime import datetime, date
from typing import List, Dict, Optional

from sqlalchemy import text

from database.orm.base import get_session
from database.orm.models import PDTTracking


class PDTRepository:
    """Repository for PDT tracking data"""

    def __init__(self, db_path: str = None):
        # db_path kept for API compatibility; ignored (session handles connection)
        pass

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
        try:
            if entry_date is None:
                entry_date = date.today().isoformat()
            if entry_time is None:
                entry_time = datetime.now().isoformat()

            with get_session() as session:
                existing = session.query(PDTTracking).filter(
                    PDTTracking.symbol == symbol
                ).first()
                if existing:
                    existing.entry_date = entry_date
                    existing.entry_time = entry_time
                    existing.exit_date = None
                    existing.exit_time = None
                    existing.same_day_exit = 0
                else:
                    session.add(PDTTracking(
                        symbol=symbol,
                        entry_date=entry_date,
                        entry_time=entry_time,
                        created_at=datetime.now().isoformat(),
                    ))
            return True
        except Exception as e:
            print(f"Error adding PDT entry for {symbol}: {e}")
            return False

    def can_sell_today(self, symbol: str) -> bool:
        """
        Check if symbol can be sold today (not a same-day trade).

        Args:
            symbol: Stock symbol to check

        Returns:
            True if can sell (entry_date != today OR not in tracking)
            False if cannot sell (entry_date == today -> PDT violation)
        """
        with get_session() as session:
            today = date.today().isoformat()
            row = session.query(PDTTracking).filter(
                PDTTracking.symbol == symbol
            ).first()

            if row is None:
                return True
            if row.exit_date is not None:
                return True
            if row.entry_date == today:
                return False
            return True

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
        try:
            if exit_date is None:
                exit_date = date.today().isoformat()
            if exit_time is None:
                exit_time = datetime.now().isoformat()

            with get_session() as session:
                row = session.query(PDTTracking).filter(
                    PDTTracking.symbol == symbol
                ).first()
                if row:
                    row.exit_date = exit_date
                    row.exit_time = exit_time
                    row.same_day_exit = 1 if row.entry_date == exit_date else 0
            return True
        except Exception as e:
            print(f"Error recording PDT exit for {symbol}: {e}")
            return False

    def remove_entry(self, symbol: str) -> bool:
        """
        Remove symbol from PDT tracking (e.g., after holding overnight).

        Args:
            symbol: Stock symbol

        Returns:
            True if successful
        """
        try:
            with get_session() as session:
                session.query(PDTTracking).filter(
                    PDTTracking.symbol == symbol
                ).delete()
            return True
        except Exception as e:
            print(f"Error removing PDT entry for {symbol}: {e}")
            return False

    # ========================================================================
    # Query Operations
    # ========================================================================

    def get_active_restrictions(self) -> List[str]:
        """
        Get all symbols with active PDT restrictions (entered today, not exited).

        Returns:
            List of symbols that cannot be sold today
        """
        with get_session() as session:
            result = session.execute(text("SELECT symbol FROM v_active_pdt_restrictions"))
            return [row[0] for row in result.fetchall()]

    def get_all_entries(self) -> Dict[str, str]:
        """
        Get all active PDT entries (for migration/compatibility).

        Returns:
            Dict mapping symbol -> entry_date (compatible with old JSON format)
        """
        with get_session() as session:
            rows = session.query(PDTTracking).filter(
                PDTTracking.exit_date.is_(None)
            ).order_by(PDTTracking.entry_date.desc()).all()
            return {row.symbol: row.entry_date for row in rows}

    def get_violations(self, days: int = 30) -> List[Dict]:
        """
        Get PDT violations (same-day trades) from last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of violation records
        """
        with get_session() as session:
            result = session.execute(
                text("SELECT * FROM v_pdt_violations "
                     "WHERE exit_date >= date('now', '-' || :days || ' days') "
                     "ORDER BY exit_date DESC"),
                {'days': days}
            )
            return [dict(row._mapping) for row in result.fetchall()]

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
        with get_session() as session:
            result = session.execute(
                text("DELETE FROM pdt_tracking "
                     "WHERE exit_date IS NOT NULL "
                     "AND exit_date < date('now', '-' || :days || ' days')"),
                {'days': days}
            )
            return result.rowcount

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
