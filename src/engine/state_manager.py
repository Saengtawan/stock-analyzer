"""
Engine State Manager - Extracted from auto_trading_engine.py (Phase 3)
=======================================================================

Utility functions for state persistence:
- Atomic file writing
- JSON serialization/deserialization
- Path management
- State file operations

These are standalone utilities that the engine uses for persistence.
The actual save/load methods remain in the engine due to tight coupling
with engine state, but they use these utilities for the I/O operations.
"""

import os
import json
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional, Callable
from pathlib import Path
from loguru import logger


# Default state directory
DEFAULT_STATE_DIR = 'state'


def get_state_dir(base_dir: str = None) -> str:
    """
    Get state directory path, creating it if needed.

    Args:
        base_dir: Base directory (default: project root)

    Returns:
        Path to state directory
    """
    if base_dir is None:
        # Default to project root/state
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    state_dir = os.path.join(base_dir, DEFAULT_STATE_DIR)
    os.makedirs(state_dir, exist_ok=True)
    return state_dir


def atomic_write_json(filepath: str, data: Any, indent: int = 2) -> bool:
    """
    Write JSON data atomically using temp file + rename.

    This ensures the file is never in a corrupted state if the process
    crashes during write.

    Args:
        filepath: Target file path
        data: Data to serialize to JSON
        indent: JSON indentation (default 2)

    Returns:
        True if successful, False otherwise
    """
    directory = os.path.dirname(filepath)
    os.makedirs(directory, exist_ok=True)

    try:
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=indent, default=str)
            os.replace(tmp_path, filepath)
            return True
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except Exception as e:
        logger.error(f"Atomic write failed for {filepath}: {e}")
        return False


def safe_read_json(filepath: str, default: Any = None) -> Any:
    """
    Safely read JSON file with error handling.

    Args:
        filepath: Path to JSON file
        default: Default value if file doesn't exist or is invalid

    Returns:
        Parsed JSON data or default value
    """
    try:
        if not os.path.exists(filepath):
            return default

        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in {filepath}: {e}")
        return default
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return default


def cleanup_old_files(directory: str, max_age_days: int = 90, pattern: str = "*.json") -> int:
    """
    Remove files older than max_age_days.

    Args:
        directory: Directory to clean
        max_age_days: Maximum age in days
        pattern: Glob pattern for files to check

    Returns:
        Number of files removed
    """
    from pathlib import Path
    import time

    removed = 0
    cutoff = time.time() - (max_age_days * 86400)

    try:
        for filepath in Path(directory).glob(pattern):
            if filepath.stat().st_mtime < cutoff:
                filepath.unlink()
                removed += 1
    except Exception as e:
        logger.error(f"Cleanup failed for {directory}: {e}")

    if removed > 0:
        logger.info(f"Cleaned up {removed} old files from {directory}")

    return removed


def create_backup(filepath: str, backup_suffix: str = ".bak") -> bool:
    """
    Create a backup of a file.

    Args:
        filepath: File to backup
        backup_suffix: Suffix for backup file

    Returns:
        True if backup created successfully
    """
    if not os.path.exists(filepath):
        return False

    backup_path = filepath + backup_suffix
    try:
        import shutil
        shutil.copy2(filepath, backup_path)
        return True
    except Exception as e:
        logger.error(f"Failed to create backup of {filepath}: {e}")
        return False


def write_heartbeat(filepath: str, status: Dict[str, Any] = None) -> bool:
    """
    Write heartbeat file to indicate engine is alive.

    Args:
        filepath: Path to heartbeat file
        status: Optional status data to include

    Returns:
        True if successful
    """
    data = {
        'timestamp': datetime.now().isoformat(),
        'alive': True,
    }
    if status:
        data.update(status)

    return atomic_write_json(filepath, data)


def read_heartbeat(filepath: str, max_age_seconds: int = 120) -> Dict[str, Any]:
    """
    Read heartbeat file and check if engine is alive.

    Args:
        filepath: Path to heartbeat file
        max_age_seconds: Maximum age to consider alive

    Returns:
        Dict with 'alive' bool and 'last_seen' datetime
    """
    data = safe_read_json(filepath, {})

    result = {
        'alive': False,
        'last_seen': None,
        'data': data
    }

    if not data:
        return result

    try:
        timestamp = datetime.fromisoformat(data.get('timestamp', ''))
        age_seconds = (datetime.now() - timestamp).total_seconds()
        result['alive'] = age_seconds < max_age_seconds
        result['last_seen'] = timestamp
    except Exception:
        pass

    return result


class StateFile:
    """
    Wrapper for a state file with atomic read/write operations.

    Usage:
        state = StateFile('/path/to/state.json')
        data = state.load()
        data['key'] = 'value'
        state.save(data)
    """

    def __init__(self, filepath: str, default: Any = None):
        self.filepath = filepath
        self.default = default if default is not None else {}

    def load(self) -> Any:
        """Load state from file"""
        return safe_read_json(self.filepath, self.default)

    def save(self, data: Any) -> bool:
        """Save state to file atomically"""
        return atomic_write_json(self.filepath, data)

    def exists(self) -> bool:
        """Check if state file exists"""
        return os.path.exists(self.filepath)

    def backup(self) -> bool:
        """Create backup of state file"""
        return create_backup(self.filepath)

    def delete(self) -> bool:
        """Delete state file"""
        try:
            if self.exists():
                os.unlink(self.filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {self.filepath}: {e}")
            return False


def serialize_position(pos) -> Dict[str, Any]:
    """
    Serialize a ManagedPosition to dict for JSON storage.

    Args:
        pos: ManagedPosition instance

    Returns:
        Dict representation
    """
    return {
        'symbol': pos.symbol,
        'qty': pos.qty,
        'entry_price': pos.entry_price,
        'entry_time': pos.entry_time.isoformat() if hasattr(pos.entry_time, 'isoformat') else str(pos.entry_time),
        'sl_order_id': pos.sl_order_id,
        'current_sl_price': pos.current_sl_price,
        'peak_price': pos.peak_price,
        'trailing_active': pos.trailing_active,
        'days_held': pos.days_held,
        'sl_pct': pos.sl_pct,
        'tp_price': pos.tp_price,
        'tp_pct': pos.tp_pct,
        'atr_pct': pos.atr_pct,
        'sector': pos.sector,
        'trough_price': pos.trough_price,
        'source': pos.source,
        'signal_score': pos.signal_score,
        'entry_mode': pos.entry_mode,
        'entry_regime': pos.entry_regime,
        'entry_rsi': pos.entry_rsi,
        'momentum_5d': pos.momentum_5d,
    }


def deserialize_position(data: Dict[str, Any], position_class):
    """
    Deserialize dict to ManagedPosition.

    Args:
        data: Dict from JSON
        position_class: ManagedPosition class

    Returns:
        ManagedPosition instance
    """
    entry_time = data.get('entry_time')
    if isinstance(entry_time, str):
        entry_time = datetime.fromisoformat(entry_time)

    return position_class(
        symbol=data['symbol'],
        qty=data['qty'],
        entry_price=data['entry_price'],
        entry_time=entry_time,
        sl_order_id=data.get('sl_order_id', ''),
        current_sl_price=data.get('current_sl_price', 0),
        peak_price=data.get('peak_price', data['entry_price']),
        trailing_active=data.get('trailing_active', False),
        days_held=data.get('days_held', 0),
        sl_pct=data.get('sl_pct', 2.5),
        tp_price=data.get('tp_price', 0),
        tp_pct=data.get('tp_pct', 5.0),
        atr_pct=data.get('atr_pct', 0),
        sector=data.get('sector', ''),
        trough_price=data.get('trough_price', 0),
        source=data.get('source', 'dip_bounce'),
        signal_score=data.get('signal_score', 0),
        entry_mode=data.get('entry_mode', 'NORMAL'),
        entry_regime=data.get('entry_regime', 'BULL'),
        entry_rsi=data.get('entry_rsi', 0),
        momentum_5d=data.get('momentum_5d', 0),
    )


def serialize_queued_signal(q) -> Dict[str, Any]:
    """
    Serialize a QueuedSignal to dict for JSON storage.

    Args:
        q: QueuedSignal instance

    Returns:
        Dict representation
    """
    return {
        'symbol': q.symbol,
        'signal_price': q.signal_price,
        'score': q.score,
        'stop_loss': q.stop_loss,
        'take_profit': q.take_profit,
        'queued_at': q.queued_at.isoformat() if hasattr(q.queued_at, 'isoformat') else str(q.queued_at),
        'reasons': q.reasons,
        'atr_pct': q.atr_pct,
        'sl_pct': q.sl_pct,
        'tp_pct': q.tp_pct,
    }


def deserialize_queued_signal(data: Dict[str, Any], signal_class):
    """
    Deserialize dict to QueuedSignal.

    Args:
        data: Dict from JSON
        signal_class: QueuedSignal class

    Returns:
        QueuedSignal instance
    """
    queued_at = data.get('queued_at')
    if isinstance(queued_at, str):
        queued_at = datetime.fromisoformat(queued_at)

    return signal_class(
        symbol=data['symbol'],
        signal_price=data['signal_price'],
        score=data['score'],
        stop_loss=data['stop_loss'],
        take_profit=data['take_profit'],
        queued_at=queued_at,
        reasons=data.get('reasons', []),
        atr_pct=data.get('atr_pct', 5.0),
        sl_pct=data.get('sl_pct', 0.0),
        tp_pct=data.get('tp_pct', 0.0),
    )
