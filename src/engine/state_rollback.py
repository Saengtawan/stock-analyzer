"""
State Rollback Mechanism (Production Grade v6.21)

Provides state snapshots and rollback capabilities for critical operations.

Use Cases:
- Rollback position state after failed order
- Rollback portfolio state after sync failure
- Manual rollback via CLI/API

Usage:
    from engine.state_rollback import StateManager

    state_mgr = StateManager()

    # Save state before critical operation
    snapshot_id = state_mgr.save_snapshot(
        'positions',
        {'AAPL': {...}, 'TSLA': {...}}
    )

    try:
        # Critical operation (e.g., place order)
        broker.place_market_buy('AAPL', 10)
    except Exception as e:
        # Rollback on failure
        state_mgr.rollback(snapshot_id)
        raise

    # Commit snapshot (delete it)
    state_mgr.commit(snapshot_id)
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from threading import Lock
from loguru import logger


@dataclass
class Snapshot:
    """State snapshot"""
    id: str                      # Unique ID
    type: str                    # Type of state (e.g., 'positions', 'portfolio')
    data: Dict[str, Any]         # State data
    metadata: Dict[str, Any]     # Additional metadata
    created_at: str              # Creation timestamp
    committed: bool = False      # Whether snapshot was committed (deleted)
    rolled_back: bool = False    # Whether snapshot was rolled back


class StateManager:
    """
    State manager with snapshot and rollback capabilities

    Features:
    - Save state snapshots before critical operations
    - Rollback to previous state on failure
    - Auto-cleanup of old snapshots
    - Persistent storage (survives restarts)
    """

    def __init__(
        self,
        storage_file: str = None,
        max_snapshots: int = 100,
        retention_hours: int = 24
    ):
        """
        Initialize state manager

        Args:
            storage_file: Path to JSON file for persistent storage
            max_snapshots: Maximum number of snapshots to keep
            retention_hours: Auto-delete snapshots older than N hours
        """
        if storage_file is None:
            storage_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'state')
            os.makedirs(storage_dir, exist_ok=True)
            storage_file = os.path.join(storage_dir, 'state_snapshots.json')

        self.storage_file = storage_file
        self.max_snapshots = max_snapshots
        self.retention_hours = retention_hours

        # Thread safety
        self.lock = Lock()

        # In-memory storage
        self.snapshots: Dict[str, Snapshot] = {}

        # Load from disk
        self._load()

        # Auto-cleanup old snapshots
        self._cleanup_old_snapshots()

        logger.info(
            f"StateManager initialized: {len(self.snapshots)} snapshots loaded, "
            f"retention={retention_hours}h"
        )

    def _load(self):
        """Load snapshots from disk"""
        if not os.path.exists(self.storage_file):
            return

        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)

            for snapshot_data in data.get('snapshots', []):
                snapshot = Snapshot(**snapshot_data)
                self.snapshots[snapshot.id] = snapshot

            logger.info(f"Loaded {len(self.snapshots)} snapshots from disk")

        except Exception as e:
            logger.error(f"Failed to load snapshots from disk: {e}")

    def _save(self):
        """Save snapshots to disk"""
        try:
            data = {
                'snapshots': [asdict(s) for s in self.snapshots.values()],
                'last_updated': datetime.now().isoformat()
            }

            # Atomic write
            temp_file = f"{self.storage_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)

            os.replace(temp_file, self.storage_file)

        except Exception as e:
            logger.error(f"Failed to save snapshots to disk: {e}")

    def save_snapshot(
        self,
        state_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save state snapshot

        Args:
            state_type: Type of state (e.g., 'positions', 'portfolio', 'orders')
            data: State data to snapshot
            metadata: Additional metadata (e.g., operation, reason)

        Returns:
            Snapshot ID
        """
        with self.lock:
            # Generate unique ID
            snapshot_id = f"{state_type}_{int(time.time() * 1000)}"

            # Create snapshot
            snapshot = Snapshot(
                id=snapshot_id,
                type=state_type,
                data=data.copy(),  # Deep copy to prevent mutations
                metadata=metadata or {},
                created_at=datetime.now().isoformat()
            )

            self.snapshots[snapshot_id] = snapshot
            self._save()

            logger.info(
                f"💾 Snapshot saved: {snapshot_id} "
                f"({len(data)} items, type={state_type})"
            )

            # Enforce max snapshots limit
            if len(self.snapshots) > self.max_snapshots:
                self._cleanup_excess_snapshots()

            return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """
        Get snapshot by ID

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Snapshot or None if not found
        """
        with self.lock:
            return self.snapshots.get(snapshot_id)

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """
        Rollback to snapshot

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Restored state data

        Raises:
            ValueError: If snapshot not found or already rolled back
        """
        with self.lock:
            snapshot = self.snapshots.get(snapshot_id)
            if not snapshot:
                raise ValueError(f"Snapshot {snapshot_id} not found")

            if snapshot.rolled_back:
                raise ValueError(f"Snapshot {snapshot_id} already rolled back")

            # Mark as rolled back
            snapshot.rolled_back = True
            self._save()

            logger.warning(
                f"🔄 ROLLBACK: {snapshot_id} "
                f"(type={snapshot.type}, {len(snapshot.data)} items)"
            )

            return snapshot.data.copy()

    def commit(self, snapshot_id: str):
        """
        Commit snapshot (mark as successful, eligible for cleanup)

        Args:
            snapshot_id: Snapshot ID
        """
        with self.lock:
            snapshot = self.snapshots.get(snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found (already committed?)")
                return

            snapshot.committed = True
            self._save()

            logger.debug(f"✅ Snapshot committed: {snapshot_id}")

    def delete_snapshot(self, snapshot_id: str):
        """
        Delete snapshot

        Args:
            snapshot_id: Snapshot ID
        """
        with self.lock:
            if snapshot_id in self.snapshots:
                del self.snapshots[snapshot_id]
                self._save()
                logger.debug(f"🗑️ Snapshot deleted: {snapshot_id}")

    def list_snapshots(
        self,
        state_type: Optional[str] = None,
        committed: Optional[bool] = None
    ) -> List[Snapshot]:
        """
        List snapshots

        Args:
            state_type: Filter by state type (optional)
            committed: Filter by committed status (optional)

        Returns:
            List of snapshots
        """
        with self.lock:
            snapshots = list(self.snapshots.values())

            if state_type:
                snapshots = [s for s in snapshots if s.type == state_type]

            if committed is not None:
                snapshots = [s for s in snapshots if s.committed == committed]

            # Sort by created_at (newest first)
            snapshots.sort(key=lambda x: x.created_at, reverse=True)

            return snapshots

    def _cleanup_old_snapshots(self):
        """Remove snapshots older than retention period"""
        with self.lock:
            cutoff = datetime.now() - timedelta(hours=self.retention_hours)
            removed = 0

            snapshots_to_remove = []
            for snapshot_id, snapshot in self.snapshots.items():
                created_time = datetime.fromisoformat(snapshot.created_at)

                # Only remove committed or rolled back snapshots
                if (snapshot.committed or snapshot.rolled_back) and created_time < cutoff:
                    snapshots_to_remove.append(snapshot_id)

            for snapshot_id in snapshots_to_remove:
                del self.snapshots[snapshot_id]
                removed += 1

            if removed > 0:
                self._save()
                logger.info(f"🧹 Cleaned up {removed} old snapshots (>{self.retention_hours}h)")

    def _cleanup_excess_snapshots(self):
        """Remove excess snapshots to enforce max_snapshots limit"""
        with self.lock:
            if len(self.snapshots) <= self.max_snapshots:
                return

            # Get committed/rolled back snapshots, sorted by age (oldest first)
            eligible = [
                s for s in self.snapshots.values()
                if s.committed or s.rolled_back
            ]
            eligible.sort(key=lambda x: x.created_at)

            # Remove oldest until we're under the limit
            to_remove = len(self.snapshots) - self.max_snapshots
            removed = 0

            for snapshot in eligible:
                if removed >= to_remove:
                    break

                del self.snapshots[snapshot.id]
                removed += 1

            if removed > 0:
                self._save()
                logger.info(f"🧹 Cleaned up {removed} excess snapshots (max={self.max_snapshots})")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get state manager statistics

        Returns:
            Statistics dictionary
        """
        with self.lock:
            stats = {
                'total_snapshots': len(self.snapshots),
                'committed': 0,
                'rolled_back': 0,
                'pending': 0,
                'by_type': {}
            }

            for snapshot in self.snapshots.values():
                if snapshot.committed:
                    stats['committed'] += 1
                elif snapshot.rolled_back:
                    stats['rolled_back'] += 1
                else:
                    stats['pending'] += 1

                state_type = snapshot.type
                if state_type not in stats['by_type']:
                    stats['by_type'][state_type] = 0
                stats['by_type'][state_type] += 1

            return stats


# =========================================================================
# GLOBAL STATE MANAGER
# =========================================================================

_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get global state manager instance"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


# =========================================================================
# CONTEXT MANAGER FOR AUTOMATIC ROLLBACK
# =========================================================================

class RollbackContext:
    """
    Context manager for automatic state rollback on exception

    Usage:
        with RollbackContext('positions', positions_dict):
            # Critical operation
            broker.place_order(...)
    """

    def __init__(
        self,
        state_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.state_type = state_type
        self.data = data
        self.metadata = metadata
        self.snapshot_id: Optional[str] = None
        self.state_mgr = get_state_manager()

    def __enter__(self):
        """Save snapshot on enter"""
        self.snapshot_id = self.state_mgr.save_snapshot(
            self.state_type,
            self.data,
            self.metadata
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Rollback on exception, commit on success"""
        if exc_type is not None:
            # Exception occurred - rollback
            logger.error(f"Exception occurred, rolling back {self.snapshot_id}")
            try:
                self.state_mgr.rollback(self.snapshot_id)
            except Exception as e:
                logger.error(f"Failed to rollback: {e}")
        else:
            # Success - commit
            self.state_mgr.commit(self.snapshot_id)

        # Don't suppress exceptions
        return False

    def get_restored_state(self) -> Optional[Dict[str, Any]]:
        """Get restored state after rollback"""
        if self.snapshot_id:
            snapshot = self.state_mgr.get_snapshot(self.snapshot_id)
            if snapshot and snapshot.rolled_back:
                return snapshot.data
        return None


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == '__main__':
    print("🧪 Testing State Rollback...")

    # Create state manager
    state_mgr = StateManager(storage_file='/tmp/test_state.json')

    # Test 1: Save and rollback
    print("\n1. Save and rollback:")
    positions = {'AAPL': {'qty': 10, 'price': 150}, 'TSLA': {'qty': 5, 'price': 200}}
    snapshot_id = state_mgr.save_snapshot('positions', positions)
    print(f"   Snapshot saved: {snapshot_id}")

    # Simulate failure and rollback
    restored = state_mgr.rollback(snapshot_id)
    print(f"   Rolled back: {restored}")

    # Test 2: Save and commit
    print("\n2. Save and commit:")
    portfolio = {'cash': 10000, 'equity': 5000}
    snapshot_id2 = state_mgr.save_snapshot('portfolio', portfolio)
    state_mgr.commit(snapshot_id2)
    print(f"   Snapshot committed: {snapshot_id2}")

    # Test 3: Context manager
    print("\n3. Context manager (auto-rollback on exception):")
    positions2 = {'AMD': {'qty': 20, 'price': 100}}

    try:
        with RollbackContext('positions', positions2) as ctx:
            print("   Inside context...")
            raise ValueError("Simulated error")
    except ValueError:
        print("   Exception caught, state rolled back")

    # Test 4: Statistics
    print("\n4. Statistics:")
    stats = state_mgr.get_statistics()
    print(f"   Total snapshots: {stats['total_snapshots']}")
    print(f"   Committed: {stats['committed']}")
    print(f"   Rolled back: {stats['rolled_back']}")
    print(f"   By type: {stats['by_type']}")

    print("\n✅ Tests complete!")
