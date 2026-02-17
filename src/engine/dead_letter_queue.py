"""
Dead Letter Queue (DLQ) for failed operations (Production Grade v6.21)

Captures operations that fail after max retries for:
- Manual review
- Automatic retry with exponential backoff
- Alerting on repeated failures

Usage:
    from engine.dead_letter_queue import DeadLetterQueue

    dlq = DeadLetterQueue()

    # Add failed operation
    dlq.add(
        operation_type="order_submission",
        operation_data={"symbol": "AAPL", "qty": 10, "side": "buy"},
        error="API timeout after 3 retries",
        context={"account_id": "123", "timestamp": "2026-02-13 21:00:00"}
    )

    # Get pending items
    items = dlq.get_pending()

    # Retry item
    dlq.retry(item_id)

    # Mark as resolved
    dlq.resolve(item_id, "Manually fixed")
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from threading import Lock
from loguru import logger


class DLQStatus(Enum):
    """DLQ item status"""
    PENDING = "pending"           # Waiting for review/retry
    RETRYING = "retrying"         # Currently being retried
    RESOLVED = "resolved"         # Successfully resolved
    FAILED = "failed"             # Permanently failed (max retries exceeded)
    IGNORED = "ignored"           # Manually ignored


@dataclass
class DLQItem:
    """Dead letter queue item"""
    id: str                          # Unique ID
    operation_type: str              # Type of operation (e.g., "order_submission", "position_sync")
    operation_data: Dict[str, Any]   # Operation details
    error: str                       # Error message
    context: Dict[str, Any]          # Additional context
    status: str                      # Current status
    created_at: str                  # When item was added
    retry_count: int = 0             # Number of retry attempts
    last_retry_at: Optional[str] = None  # Last retry timestamp
    resolved_at: Optional[str] = None    # When resolved
    resolution_note: Optional[str] = None  # How it was resolved
    next_retry_at: Optional[str] = None   # Next scheduled retry time


class DeadLetterQueue:
    """
    Dead Letter Queue for failed operations

    Features:
    - Persistent storage (JSON file)
    - Automatic retry with exponential backoff
    - Manual review and resolution
    - Alerting on accumulated failures
    """

    def __init__(
        self,
        storage_file: str = None,
        max_retries: int = 3,
        initial_retry_delay: int = 60,  # 1 minute
        max_retry_delay: int = 3600     # 1 hour
    ):
        """
        Initialize DLQ

        Args:
            storage_file: Path to JSON file for persistent storage
            max_retries: Maximum automatic retry attempts
            initial_retry_delay: Initial retry delay in seconds
            max_retry_delay: Maximum retry delay in seconds
        """
        if storage_file is None:
            storage_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'dlq')
            os.makedirs(storage_dir, exist_ok=True)
            storage_file = os.path.join(storage_dir, 'dead_letter_queue.json')

        self.storage_file = storage_file
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.max_retry_delay = max_retry_delay

        # Thread safety
        self.lock = Lock()

        # In-memory cache
        self.items: Dict[str, DLQItem] = {}

        # Load from disk
        self._load()

        logger.info(f"DLQ initialized: {len(self.items)} items loaded from {storage_file}")

    def _load(self):
        """Load DLQ from disk"""
        if not os.path.exists(self.storage_file):
            return

        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)

            for item_data in data.get('items', []):
                item = DLQItem(**item_data)
                self.items[item.id] = item

            logger.info(f"Loaded {len(self.items)} DLQ items from disk")

        except Exception as e:
            logger.error(f"Failed to load DLQ from disk: {e}")

    def _save(self):
        """Save DLQ to disk"""
        try:
            data = {
                'items': [asdict(item) for item in self.items.values()],
                'last_updated': datetime.now().isoformat()
            }

            # Atomic write (write to temp file, then rename)
            temp_file = f"{self.storage_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)

            os.replace(temp_file, self.storage_file)

        except Exception as e:
            logger.error(f"Failed to save DLQ to disk: {e}")

    def add(
        self,
        operation_type: str,
        operation_data: Dict[str, Any],
        error: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add failed operation to DLQ

        Args:
            operation_type: Type of operation (e.g., "order_submission")
            operation_data: Operation details
            error: Error message
            context: Additional context

        Returns:
            Item ID
        """
        with self.lock:
            # Generate unique ID
            item_id = f"{operation_type}_{int(time.time() * 1000)}"

            # Calculate next retry time (exponential backoff)
            next_retry_at = (
                datetime.now() + timedelta(seconds=self.initial_retry_delay)
            ).isoformat()

            # Create item
            item = DLQItem(
                id=item_id,
                operation_type=operation_type,
                operation_data=operation_data,
                error=error,
                context=context or {},
                status=DLQStatus.PENDING.value,
                created_at=datetime.now().isoformat(),
                next_retry_at=next_retry_at
            )

            self.items[item_id] = item
            self._save()

            logger.warning(
                f"⚠️ DLQ: Added {operation_type} - {error} "
                f"(retry scheduled in {self.initial_retry_delay}s)"
            )

            return item_id

    def get_pending(self, operation_type: Optional[str] = None) -> List[DLQItem]:
        """
        Get pending DLQ items

        Args:
            operation_type: Filter by operation type (optional)

        Returns:
            List of pending items
        """
        with self.lock:
            items = [
                item for item in self.items.values()
                if item.status == DLQStatus.PENDING.value
            ]

            if operation_type:
                items = [item for item in items if item.operation_type == operation_type]

            # Sort by created_at (oldest first)
            items.sort(key=lambda x: x.created_at)

            return items

    def get_ready_for_retry(self) -> List[DLQItem]:
        """
        Get items ready for retry (next_retry_at <= now)

        Returns:
            List of items ready for retry
        """
        with self.lock:
            now = datetime.now()
            items = []

            for item in self.items.values():
                if item.status != DLQStatus.PENDING.value:
                    continue

                if item.retry_count >= self.max_retries:
                    # Mark as permanently failed
                    item.status = DLQStatus.FAILED.value
                    logger.error(f"❌ DLQ: {item.id} exceeded max retries ({self.max_retries})")
                    continue

                if item.next_retry_at:
                    next_retry = datetime.fromisoformat(item.next_retry_at)
                    if next_retry <= now:
                        items.append(item)

            if items:
                self._save()

            return items

    def retry(self, item_id: str) -> bool:
        """
        Retry a DLQ item

        Args:
            item_id: Item ID

        Returns:
            True if retry scheduled, False otherwise
        """
        with self.lock:
            item = self.items.get(item_id)
            if not item:
                logger.warning(f"DLQ: Item {item_id} not found")
                return False

            if item.status not in [DLQStatus.PENDING.value, DLQStatus.FAILED.value]:
                logger.warning(f"DLQ: Item {item_id} status is {item.status}, cannot retry")
                return False

            # Update retry count
            item.retry_count += 1
            item.last_retry_at = datetime.now().isoformat()
            item.status = DLQStatus.RETRYING.value

            # Calculate next retry delay (exponential backoff: 1min, 2min, 4min, ...)
            retry_delay = min(
                self.initial_retry_delay * (2 ** (item.retry_count - 1)),
                self.max_retry_delay
            )
            item.next_retry_at = (
                datetime.now() + timedelta(seconds=retry_delay)
            ).isoformat()

            self._save()

            logger.info(
                f"🔄 DLQ: Retrying {item.id} (attempt {item.retry_count}/{self.max_retries}, "
                f"next retry in {retry_delay}s)"
            )

            return True

    def resolve(self, item_id: str, resolution_note: str = ""):
        """
        Mark item as resolved

        Args:
            item_id: Item ID
            resolution_note: How it was resolved
        """
        with self.lock:
            item = self.items.get(item_id)
            if not item:
                logger.warning(f"DLQ: Item {item_id} not found")
                return

            item.status = DLQStatus.RESOLVED.value
            item.resolved_at = datetime.now().isoformat()
            item.resolution_note = resolution_note

            self._save()

            logger.info(f"✅ DLQ: Resolved {item.id} - {resolution_note}")

    def ignore(self, item_id: str, reason: str = ""):
        """
        Mark item as ignored (won't be retried)

        Args:
            item_id: Item ID
            reason: Why it was ignored
        """
        with self.lock:
            item = self.items.get(item_id)
            if not item:
                logger.warning(f"DLQ: Item {item_id} not found")
                return

            item.status = DLQStatus.IGNORED.value
            item.resolved_at = datetime.now().isoformat()
            item.resolution_note = f"Ignored: {reason}"

            self._save()

            logger.info(f"🚫 DLQ: Ignored {item.id} - {reason}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get DLQ statistics

        Returns:
            Statistics dictionary
        """
        with self.lock:
            stats = {
                'total': len(self.items),
                'pending': 0,
                'retrying': 0,
                'resolved': 0,
                'failed': 0,
                'ignored': 0,
                'by_operation_type': {}
            }

            for item in self.items.values():
                stats[item.status] = stats.get(item.status, 0) + 1

                op_type = item.operation_type
                if op_type not in stats['by_operation_type']:
                    stats['by_operation_type'][op_type] = {
                        'total': 0,
                        'pending': 0,
                        'failed': 0
                    }

                stats['by_operation_type'][op_type]['total'] += 1
                if item.status == DLQStatus.PENDING.value:
                    stats['by_operation_type'][op_type]['pending'] += 1
                elif item.status == DLQStatus.FAILED.value:
                    stats['by_operation_type'][op_type]['failed'] += 1

            return stats

    def cleanup_old_items(self, days: int = 30):
        """
        Remove resolved/ignored items older than N days

        Args:
            days: Number of days to keep
        """
        with self.lock:
            cutoff = datetime.now() - timedelta(days=days)
            removed = 0

            items_to_remove = []
            for item_id, item in self.items.items():
                if item.status not in [DLQStatus.RESOLVED.value, DLQStatus.IGNORED.value]:
                    continue

                if item.resolved_at:
                    resolved_time = datetime.fromisoformat(item.resolved_at)
                    if resolved_time < cutoff:
                        items_to_remove.append(item_id)

            for item_id in items_to_remove:
                del self.items[item_id]
                removed += 1

            if removed > 0:
                self._save()
                logger.info(f"🧹 DLQ: Cleaned up {removed} old items (>{days} days)")


# =========================================================================
# GLOBAL DLQ INSTANCE
# =========================================================================

_dlq: Optional[DeadLetterQueue] = None


def get_dlq() -> DeadLetterQueue:
    """Get global DLQ instance"""
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue()
    return _dlq


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == '__main__':
    print("🧪 Testing Dead Letter Queue...")

    # Create DLQ
    dlq = DeadLetterQueue(storage_file='/tmp/test_dlq.json')

    # Test 1: Add failed operations
    print("\n1. Adding failed operations:")
    dlq.add(
        operation_type="order_submission",
        operation_data={"symbol": "AAPL", "qty": 10, "side": "buy"},
        error="API timeout after 3 retries",
        context={"account_id": "123"}
    )

    dlq.add(
        operation_type="position_sync",
        operation_data={"symbol": "TSLA", "qty": 5},
        error="Position not found in broker",
        context={"expected_qty": 5, "actual_qty": 0}
    )

    # Test 2: Get pending items
    print("\n2. Pending items:")
    pending = dlq.get_pending()
    for item in pending:
        print(f"   - {item.id}: {item.operation_type} - {item.error}")

    # Test 3: Statistics
    print("\n3. Statistics:")
    stats = dlq.get_statistics()
    print(f"   Total: {stats['total']}")
    print(f"   Pending: {stats['pending']}")
    print(f"   By operation type: {stats['by_operation_type']}")

    # Test 4: Resolve item
    print("\n4. Resolving item:")
    if pending:
        dlq.resolve(pending[0].id, "Manually fixed via Alpaca UI")
        print(f"   ✅ Resolved {pending[0].id}")

    print("\n✅ Tests complete!")
