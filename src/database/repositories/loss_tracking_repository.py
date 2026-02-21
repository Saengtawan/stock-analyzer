"""
Loss Tracking Repository - Database access for risk management

Handles CRUD operations for loss counters and risk management:
- Track consecutive losses (trigger cooldowns at 3+)
- Track weekly realized P&L
- Manage sector-specific loss tracking
- Auto-reset and cooldown management
"""

import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class LossTrackingRepository:
    """Repository for loss tracking and risk management data"""

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
    # Main Loss Tracking Operations
    # ========================================================================

    def get_state(self) -> Dict:
        """
        Get current loss tracking state.

        Returns:
            Dict with: consecutive_losses, weekly_realized_pnl, cooldown_until,
                      weekly_reset_date, updated_at
        """
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT consecutive_losses, weekly_realized_pnl, cooldown_until,
                       weekly_reset_date, updated_at, saved_at
                FROM loss_tracking
                WHERE id = 1
            """).fetchone()

            if row:
                return dict(row)
            else:
                # Should never happen (default row inserted), but handle gracefully
                return {
                    'consecutive_losses': 0,
                    'weekly_realized_pnl': 0.0,
                    'cooldown_until': None,
                    'weekly_reset_date': None,
                    'updated_at': None,
                    'saved_at': None
                }
        finally:
            conn.close()

    def increment_losses(self) -> int:
        """
        Increment consecutive losses by 1.

        Returns:
            New consecutive_losses count
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE loss_tracking
                SET consecutive_losses = consecutive_losses + 1
                WHERE id = 1
            """)
            conn.commit()

            # Get new count
            row = conn.execute("""
                SELECT consecutive_losses FROM loss_tracking WHERE id = 1
            """).fetchone()

            return row['consecutive_losses'] if row else 0
        finally:
            conn.close()

    def reset_losses(self) -> bool:
        """
        Reset consecutive losses to 0 (after a win).

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE loss_tracking
                SET consecutive_losses = 0
                WHERE id = 1
            """)
            conn.commit()
            return True
        finally:
            conn.close()

    def update_weekly_pnl(self, pnl_change: float) -> float:
        """
        Add to weekly realized P&L.

        Args:
            pnl_change: P&L to add (can be negative)

        Returns:
            New weekly_realized_pnl total
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE loss_tracking
                SET weekly_realized_pnl = weekly_realized_pnl + ?
                WHERE id = 1
            """, (pnl_change,))
            conn.commit()

            # Get new total
            row = conn.execute("""
                SELECT weekly_realized_pnl FROM loss_tracking WHERE id = 1
            """).fetchone()

            return row['weekly_realized_pnl'] if row else 0.0
        finally:
            conn.close()

    def set_cooldown(self, cooldown_until: str) -> bool:
        """
        Set cooldown period (blocks trading until date).

        Args:
            cooldown_until: ISO date string (YYYY-MM-DD) or None to clear

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE loss_tracking
                SET cooldown_until = ?
                WHERE id = 1
            """, (cooldown_until,))
            conn.commit()
            return True
        finally:
            conn.close()

    def is_in_cooldown(self) -> bool:
        """
        Check if currently in cooldown period.

        Returns:
            True if cooldown_until > today
        """
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT cooldown_until FROM loss_tracking WHERE id = 1
            """).fetchone()

            if not row or not row['cooldown_until']:
                return False

            today = date.today().isoformat()
            return row['cooldown_until'] > today
        finally:
            conn.close()

    def reset_weekly(self, new_reset_date: str = None) -> bool:
        """
        Reset weekly P&L to 0 and set next reset date.

        Args:
            new_reset_date: Next reset date (defaults to +7 days)

        Returns:
            True if successful
        """
        if new_reset_date is None:
            new_reset_date = (date.today() + timedelta(days=7)).isoformat()

        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE loss_tracking
                SET weekly_realized_pnl = 0.0,
                    weekly_reset_date = ?
                WHERE id = 1
            """, (new_reset_date,))
            conn.commit()
            return True
        finally:
            conn.close()

    # ========================================================================
    # Sector Loss Tracking Operations
    # ========================================================================

    def get_sector_losses(self, sector: str) -> int:
        """
        Get consecutive losses for a sector.

        Args:
            sector: Sector name (case-insensitive)

        Returns:
            Number of consecutive losses (0 if no record)
        """
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT losses FROM sector_loss_tracking
                WHERE LOWER(sector) = LOWER(?)
            """, (sector,)).fetchone()

            return row['losses'] if row else 0
        finally:
            conn.close()

    def increment_sector_loss(self, sector: str) -> int:
        """
        Increment losses for a sector.

        Args:
            sector: Sector name

        Returns:
            New loss count for this sector
        """
        conn = self._get_connection()
        try:
            # Upsert
            conn.execute("""
                INSERT INTO sector_loss_tracking (sector, losses)
                VALUES (LOWER(?), 1)
                ON CONFLICT(sector) DO UPDATE
                SET losses = losses + 1
            """, (sector,))
            conn.commit()

            # Get new count
            row = conn.execute("""
                SELECT losses FROM sector_loss_tracking
                WHERE LOWER(sector) = LOWER(?)
            """, (sector,)).fetchone()

            return row['losses'] if row else 0
        finally:
            conn.close()

    def reset_sector_losses(self, sector: str) -> bool:
        """
        Reset losses for a sector to 0 (after a win).

        Args:
            sector: Sector name

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE sector_loss_tracking
                SET losses = 0
                WHERE LOWER(sector) = LOWER(?)
            """, (sector,))
            conn.commit()
            return True
        finally:
            conn.close()

    def set_sector_cooldown(self, sector: str, cooldown_until: str) -> bool:
        """
        Set cooldown for a specific sector.

        Args:
            sector: Sector name
            cooldown_until: ISO date or None to clear

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            # Ensure sector exists
            conn.execute("""
                INSERT OR IGNORE INTO sector_loss_tracking (sector, losses)
                VALUES (LOWER(?), 0)
            """, (sector,))

            # Update cooldown
            conn.execute("""
                UPDATE sector_loss_tracking
                SET cooldown_until = ?
                WHERE LOWER(sector) = LOWER(?)
            """, (cooldown_until, sector))
            conn.commit()
            return True
        finally:
            conn.close()

    def is_sector_in_cooldown(self, sector: str) -> bool:
        """
        Check if sector is in cooldown.

        Args:
            sector: Sector name

        Returns:
            True if cooldown_until > today
        """
        conn = self._get_connection()
        try:
            row = conn.execute("""
                SELECT cooldown_until FROM sector_loss_tracking
                WHERE LOWER(sector) = LOWER(?)
            """, (sector,)).fetchone()

            if not row or not row['cooldown_until']:
                return False

            today = date.today().isoformat()
            return row['cooldown_until'] > today
        finally:
            conn.close()

    def get_all_sector_losses(self) -> Dict[str, Dict]:
        """
        Get all sector loss tracking data.

        Returns:
            Dict mapping sector -> {losses, cooldown_until}
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT sector, losses, cooldown_until
                FROM sector_loss_tracking
                ORDER BY sector
            """).fetchall()

            return {
                row['sector']: {
                    'losses': row['losses'],
                    'cooldown_until': row['cooldown_until']
                }
                for row in rows
            }
        finally:
            conn.close()

    # ========================================================================
    # Analytics & Monitoring
    # ========================================================================

    def get_risk_status(self) -> Dict:
        """
        Get current risk assessment.

        Returns:
            Dict with: consecutive_losses, weekly_pnl, risk_level, cooldown_days_remaining
        """
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM v_risk_status").fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_active_cooldowns(self) -> List[Dict]:
        """
        Get all active sector cooldowns.

        Returns:
            List of {sector, losses, cooldown_until, days_remaining}
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM v_active_sector_cooldowns
            """).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_high_risk_sectors(self) -> List[Dict]:
        """
        Get sectors with 2+ losses (not in cooldown).

        Returns:
            List of {sector, losses, risk_level}
        """
        conn = self._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM v_high_risk_sectors
            """).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ========================================================================
    # Migration Support
    # ========================================================================

    def import_from_json(self, json_data: Dict) -> bool:
        """
        Import loss tracking data from old JSON format.

        Args:
            json_data: Dict with keys:
                - consecutive_losses
                - weekly_realized_pnl
                - cooldown_until
                - weekly_reset_date
                - sector_loss_tracker (dict)

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            # Import main tracking
            conn.execute("""
                UPDATE loss_tracking
                SET consecutive_losses = ?,
                    weekly_realized_pnl = ?,
                    cooldown_until = ?,
                    weekly_reset_date = ?,
                    saved_at = ?
                WHERE id = 1
            """, (
                json_data.get('consecutive_losses', 0),
                json_data.get('weekly_realized_pnl', 0.0),
                json_data.get('cooldown_until'),
                json_data.get('weekly_reset_date'),
                json_data.get('saved_at')
            ))

            # Import sector tracking
            sector_tracker = json_data.get('sector_loss_tracker', {})
            for sector, data in sector_tracker.items():
                conn.execute("""
                    INSERT INTO sector_loss_tracking (sector, losses, cooldown_until)
                    VALUES (LOWER(?), ?, ?)
                    ON CONFLICT(sector) DO UPDATE
                    SET losses = excluded.losses,
                        cooldown_until = excluded.cooldown_until
                """, (
                    sector,
                    data.get('losses', 0),
                    data.get('cooldown_until')
                ))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error importing from JSON: {e}")
            return False
        finally:
            conn.close()

    def export_to_json(self) -> Dict:
        """
        Export to JSON format (for backup/compatibility).

        Returns:
            Dict in old JSON format
        """
        state = self.get_state()
        sectors = self.get_all_sector_losses()

        return {
            'consecutive_losses': state['consecutive_losses'],
            'weekly_realized_pnl': state['weekly_realized_pnl'],
            'cooldown_until': state['cooldown_until'],
            'weekly_reset_date': state['weekly_reset_date'],
            'sector_loss_tracker': sectors,
            'saved_at': datetime.now().isoformat()
        }
