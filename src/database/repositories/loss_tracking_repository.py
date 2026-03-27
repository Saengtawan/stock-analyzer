"""
Loss Tracking Repository - Database access for risk management

Handles CRUD operations for loss counters and risk management:
- Track consecutive losses (trigger cooldowns at 3+)
- Track weekly realized P&L
- Manage sector-specific loss tracking
- Auto-reset and cooldown management
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text, func

from database.orm.base import get_session
from database.orm.models import LossTracking, SectorLossTracking


class LossTrackingRepository:
    """Repository for loss tracking and risk management data"""

    def __init__(self, db_path: str = None):
        # db_path kept for API compatibility; ignored (session handles connection)
        pass

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
        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if row:
                return {
                    'consecutive_losses': row.consecutive_losses,
                    'weekly_realized_pnl': row.weekly_realized_pnl,
                    'cooldown_until': row.cooldown_until,
                    'weekly_reset_date': row.weekly_reset_date,
                    'updated_at': row.updated_at,
                    'saved_at': row.saved_at,
                }
            else:
                return {
                    'consecutive_losses': 0,
                    'weekly_realized_pnl': 0.0,
                    'cooldown_until': None,
                    'weekly_reset_date': None,
                    'updated_at': None,
                    'saved_at': None,
                }

    def increment_losses(self) -> int:
        """
        Increment consecutive losses by 1.

        Returns:
            New consecutive_losses count
        """
        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if row:
                row.consecutive_losses += 1
                session.flush()
                return row.consecutive_losses
            return 0

    def reset_losses(self) -> bool:
        """
        Reset consecutive losses to 0 (after a win).

        Returns:
            True if successful
        """
        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if row:
                row.consecutive_losses = 0
            return True

    def update_weekly_pnl(self, pnl_change: float) -> float:
        """
        Add to weekly realized P&L.

        Args:
            pnl_change: P&L to add (can be negative)

        Returns:
            New weekly_realized_pnl total
        """
        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if row:
                row.weekly_realized_pnl += pnl_change
                session.flush()
                return row.weekly_realized_pnl
            return 0.0

    def set_cooldown(self, cooldown_until: str) -> bool:
        """
        Set cooldown period (blocks trading until date).

        Args:
            cooldown_until: ISO date string (YYYY-MM-DD) or None to clear

        Returns:
            True if successful
        """
        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if row:
                row.cooldown_until = cooldown_until
            return True

    def is_in_cooldown(self) -> bool:
        """
        Check if currently in cooldown period.

        Returns:
            True if cooldown_until > today
        """
        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if not row or not row.cooldown_until:
                return False
            today = date.today().isoformat()
            return row.cooldown_until > today

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

        with get_session() as session:
            row = session.query(LossTracking).filter(LossTracking.id == 1).first()
            if row:
                row.weekly_realized_pnl = 0.0
                row.weekly_reset_date = new_reset_date
            return True

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
        with get_session() as session:
            row = session.query(SectorLossTracking).filter(
                func.lower(SectorLossTracking.sector) == sector.lower()
            ).first()
            return row.losses if row else 0

    def increment_sector_loss(self, sector: str) -> int:
        """
        Increment losses for a sector.

        Args:
            sector: Sector name

        Returns:
            New loss count for this sector
        """
        with get_session() as session:
            row = session.query(SectorLossTracking).filter(
                func.lower(SectorLossTracking.sector) == sector.lower()
            ).first()
            if row:
                row.losses += 1
                session.flush()
                return row.losses
            else:
                new_row = SectorLossTracking(
                    sector=sector.lower(),
                    losses=1,
                    updated_at=datetime.now().isoformat(),
                )
                session.add(new_row)
                session.flush()
                return 1

    def reset_sector_losses(self, sector: str) -> bool:
        """
        Reset losses for a sector to 0 (after a win).

        Args:
            sector: Sector name

        Returns:
            True if successful
        """
        with get_session() as session:
            row = session.query(SectorLossTracking).filter(
                func.lower(SectorLossTracking.sector) == sector.lower()
            ).first()
            if row:
                row.losses = 0
            return True

    def set_sector_cooldown(self, sector: str, cooldown_until: str) -> bool:
        """
        Set cooldown for a specific sector.

        Args:
            sector: Sector name
            cooldown_until: ISO date or None to clear

        Returns:
            True if successful
        """
        with get_session() as session:
            row = session.query(SectorLossTracking).filter(
                func.lower(SectorLossTracking.sector) == sector.lower()
            ).first()
            if not row:
                row = SectorLossTracking(
                    sector=sector.lower(),
                    losses=0,
                    updated_at=datetime.now().isoformat(),
                )
                session.add(row)
            row.cooldown_until = cooldown_until
            return True

    def is_sector_in_cooldown(self, sector: str) -> bool:
        """
        Check if sector is in cooldown.

        Args:
            sector: Sector name

        Returns:
            True if cooldown_until > today
        """
        with get_session() as session:
            row = session.query(SectorLossTracking).filter(
                func.lower(SectorLossTracking.sector) == sector.lower()
            ).first()
            if not row or not row.cooldown_until:
                return False
            today = date.today().isoformat()
            return row.cooldown_until > today

    def get_all_sector_losses(self) -> Dict[str, Dict]:
        """
        Get all sector loss tracking data.

        Returns:
            Dict mapping "strategy:sector" -> {losses, cooldown_until}
            v7.3: includes strategy column for per-strategy isolation
        """
        with get_session() as session:
            rows = session.query(SectorLossTracking).order_by(
                SectorLossTracking.strategy, SectorLossTracking.sector
            ).all()
            return {
                f"{row.strategy}:{row.sector}": {
                    'losses': row.losses,
                    'cooldown_until': row.cooldown_until,
                }
                for row in rows
            }

    # ========================================================================
    # Analytics & Monitoring
    # ========================================================================

    def get_risk_status(self) -> Dict:
        """
        Get current risk assessment.

        Returns:
            Dict with: consecutive_losses, weekly_pnl, risk_level, cooldown_days_remaining
        """
        with get_session() as session:
            result = session.execute(text("SELECT * FROM v_risk_status"))
            row = result.fetchone()
            return dict(row._mapping) if row else {}

    def get_active_cooldowns(self) -> List[Dict]:
        """
        Get all active sector cooldowns.

        Returns:
            List of {sector, losses, cooldown_until, days_remaining}
        """
        with get_session() as session:
            result = session.execute(text("SELECT * FROM v_active_sector_cooldowns"))
            return [dict(row._mapping) for row in result.fetchall()]

    def get_high_risk_sectors(self) -> List[Dict]:
        """
        Get sectors with 2+ losses (not in cooldown).

        Returns:
            List of {sector, losses, risk_level}
        """
        with get_session() as session:
            result = session.execute(text("SELECT * FROM v_high_risk_sectors"))
            return [dict(row._mapping) for row in result.fetchall()]

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
        try:
            with get_session() as session:
                # Import main tracking
                row = session.query(LossTracking).filter(LossTracking.id == 1).first()
                if row:
                    row.consecutive_losses = json_data.get('consecutive_losses', 0)
                    row.weekly_realized_pnl = json_data.get('weekly_realized_pnl', 0.0)
                    row.cooldown_until = json_data.get('cooldown_until')
                    row.weekly_reset_date = json_data.get('weekly_reset_date')
                    row.saved_at = json_data.get('saved_at')

                # Import sector tracking
                sector_tracker = json_data.get('sector_loss_tracker', {})
                for sector, data in sector_tracker.items():
                    existing = session.query(SectorLossTracking).filter(
                        func.lower(SectorLossTracking.sector) == sector.lower()
                    ).first()
                    if existing:
                        existing.losses = data.get('losses', 0)
                        existing.cooldown_until = data.get('cooldown_until')
                    else:
                        session.add(SectorLossTracking(
                            sector=sector.lower(),
                            losses=data.get('losses', 0),
                            cooldown_until=data.get('cooldown_until'),
                            updated_at=datetime.now().isoformat(),
                        ))
            return True
        except Exception as e:
            print(f"Error importing from JSON: {e}")
            return False

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
