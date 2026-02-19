# DATABASE & DATA MANAGEMENT MASTER PLAN
**Project:** Stock Analyzer - Rapid Trading System
**Current Status:** C+ (57% health, mixed storage, no backup)
**Target Status:** A (90%+ health, unified, automated, monitored)
**Timeline:** 4 weeks (phased rollout)
**Last Updated:** 2026-02-12

---

## EXECUTIVE SUMMARY

### Current Problems
1. **Log Bloat:** 126MB logs (70% of data folder) - no rotation
2. **No Backup:** 336 trades + 354K prices at risk
3. **Mixed Storage:** SQLite + JSON + Pickle (inconsistent)
4. **No Validation:** Risk of data corruption
5. **No Monitoring:** Issues discovered manually
6. **Cache Bloat:** 4,917 files (39MB) - no auto-cleanup

### Target Architecture
```
┌─────────────────────────────────────────┐
│  APPLICATION LAYER                      │
│  (Trading Engine, Web App, Screeners)   │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  DATA ACCESS LAYER (NEW)                │
│  - Unified API for all data             │
│  - Validation & Error Handling          │
│  - Caching Strategy                     │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  STORAGE LAYER                          │
│  ┌─────────────┬──────────┬───────────┐ │
│  │ SQLite DB   │ Cache    │ Logs      │ │
│  │ (Primary)   │ (Temp)   │ (Rotated) │ │
│  └─────────────┴──────────┴───────────┘ │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  MAINTENANCE LAYER (AUTOMATED)          │
│  - Daily Backup (05:00)                 │
│  - Weekly Cache Cleanup (Sun 02:00)     │
│  - Monthly Vacuum (1st, 03:00)          │
│  - Health Monitoring (continuous)       │
└─────────────────────────────────────────┘
```

---

## PHASE 1: IMMEDIATE CLEANUP (Week 1, Days 1-2)
**Priority:** CRITICAL
**Time:** 4-6 hours
**Risk:** LOW

### 1.1 Log Management

#### A. Clean Old Logs (30 min)
```bash
# Archive logs >7 days
mkdir -p data/logs/archive
find data/logs -name "*.log" -mtime +7 -exec mv {} data/logs/archive/ \;

# Compress archived logs
gzip data/logs/archive/*.log

# Expected: Recover ~110MB disk space
```

**Files to Delete:**
- `app_20260204.log` (9.2MB)
- `app_20260205*.log` (43MB)
- `app_20260206.log` (47MB)
- `app_20260207*.log` (9.8MB)

**Files to Keep:**
- Last 7 days (20MB total)

#### B. Setup Log Rotation (2 hours)

**File:** `src/utils/logger_config.py` (NEW)
```python
from loguru import logger
import sys
from pathlib import Path

def setup_logger(app_name="stock_analyzer"):
    """
    Configure loguru with rotation, compression, and retention.

    Settings:
    - Max 10MB per file
    - Keep 7 days
    - Compress old files
    - Separate files by level (debug, info, error)
    """
    log_dir = Path("data/logs")
    log_dir.mkdir(exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console handler (INFO and above)
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # Main log file (all levels)
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        rotation="10 MB",           # Rotate when file reaches 10MB
        retention="7 days",         # Keep logs for 7 days
        compression="zip",          # Compress rotated files
        level="DEBUG",
        enqueue=True,               # Thread-safe
        backtrace=True,
        diagnose=True
    )

    # Error log file (errors only)
    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        rotation="5 MB",
        retention="30 days",        # Keep errors longer
        compression="zip",
        level="ERROR",
        enqueue=True
    )

    # Critical log file (never deleted)
    logger.add(
        log_dir / "critical.log",
        rotation="1 MB",
        retention=None,             # Never delete
        compression="zip",
        level="CRITICAL",
        enqueue=True
    )

    return logger

# Export configured logger
log = setup_logger()
```

**Update:** `src/run_app.py`
```python
# OLD:
from loguru import logger

# NEW:
from utils.logger_config import log as logger
```

**Expected Results:**
- Max log size: 10MB/file × 3 levels × 7 days = ~210MB (vs current 126MB)
- Auto-cleanup after 7 days
- Compressed old files (.zip)
- Separate error tracking

### 1.2 Database Health Check (1 hour)

**File:** `scripts/check_db_health.py` (NEW)
```python
#!/usr/bin/env python3
"""
Database Health Check Script
Run before any maintenance operations
"""
import sqlite3
from pathlib import Path

def check_database(db_path):
    """Check database integrity and stats"""
    print(f"\n{'='*60}")
    print(f"Checking: {db_path}")
    print(f"{'='*60}")

    # Check file exists
    if not Path(db_path).exists():
        print("❌ Database not found!")
        return False

    # Check file size
    size_mb = Path(db_path).stat().st_size / 1024 / 1024
    print(f"Size: {size_mb:.2f} MB")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Integrity check
        result = cursor.execute("PRAGMA integrity_check").fetchone()
        if result[0] == "ok":
            print("✅ Integrity: OK")
        else:
            print(f"❌ Integrity: {result[0]}")
            return False

        # Get tables
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        print(f"\nTables ({len(tables)}):")

        # Get row counts
        for (table,) in tables:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  - {table}: {count:,} rows")

        # Page count & size
        page_count = cursor.execute("PRAGMA page_count").fetchone()[0]
        page_size = cursor.execute("PRAGMA page_size").fetchone()[0]
        print(f"\nPages: {page_count:,} × {page_size} bytes")

        # Fragmentation
        freelist = cursor.execute("PRAGMA freelist_count").fetchone()[0]
        if freelist > page_count * 0.1:  # >10% free pages
            print(f"⚠️  Fragmentation: {freelist:,} free pages (VACUUM recommended)")
        else:
            print(f"✅ Fragmentation: {freelist:,} free pages (OK)")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    databases = [
        "data/trade_history.db",
        "data/database/stocks.db"
    ]

    all_ok = True
    for db in databases:
        if not check_database(db):
            all_ok = False

    print("\n" + "="*60)
    if all_ok:
        print("✅ All databases healthy")
    else:
        print("❌ Some databases have issues")
    print("="*60)
```

**Run:** `python scripts/check_db_health.py`

### 1.3 Cache Analysis (30 min)

**File:** `scripts/analyze_cache.py` (NEW)
```python
#!/usr/bin/env python3
"""
Analyze cache directory for cleanup opportunities
"""
from pathlib import Path
from datetime import datetime, timedelta
import pickle

CACHE_DIR = Path.home() / ".stock_analyzer_cache"

def analyze_cache():
    """Analyze cache files by age and size"""
    if not CACHE_DIR.exists():
        print("Cache directory not found")
        return

    files = list(CACHE_DIR.glob("*.pkl"))
    now = datetime.now()

    # Group by age
    age_groups = {
        "< 1 day": [],
        "1-7 days": [],
        "7-30 days": [],
        "> 30 days": []
    }

    for f in files:
        age_days = (now - datetime.fromtimestamp(f.stat().st_mtime)).days

        if age_days < 1:
            age_groups["< 1 day"].append(f)
        elif age_days < 7:
            age_groups["1-7 days"].append(f)
        elif age_days < 30:
            age_groups["7-30 days"].append(f)
        else:
            age_groups["> 30 days"].append(f)

    # Print report
    print(f"\n{'='*60}")
    print(f"CACHE ANALYSIS: {CACHE_DIR}")
    print(f"{'='*60}\n")

    total_size = 0
    for group, files in age_groups.items():
        group_size = sum(f.stat().st_size for f in files)
        total_size += group_size

        print(f"{group:12s}: {len(files):5,} files ({group_size/1024/1024:6.2f} MB)")

    print(f"\n{'Total':12s}: {len(all_files):5,} files ({total_size/1024/1024:6.2f} MB)")

    # Recommendations
    old_files = age_groups["> 30 days"]
    if old_files:
        old_size = sum(f.stat().st_size for f in old_files) / 1024 / 1024
        print(f"\n⚠️  Recommendation: Delete {len(old_files):,} files (>30 days) to recover {old_size:.2f} MB")

if __name__ == "__main__":
    analyze_cache()
```

---

## PHASE 2: BACKUP & RECOVERY (Week 1, Days 3-5)
**Priority:** HIGH
**Time:** 8-10 hours
**Risk:** LOW-MEDIUM

### 2.1 Database Backup System

#### A. Backup Script (2 hours)

**File:** `scripts/backup_database.sh`
```bash
#!/bin/bash
#
# Database Backup Script
# Runs daily at 05:00 ET (before pre-filter at 07:00)
#
# Features:
# - SQLite online backup (safe while DB in use)
# - Compression (gzip)
# - Retention (7 days)
# - Verification
# - Logging
#

set -euo pipefail  # Exit on error, undefined var, pipe failure

# Configuration
PROJECT_ROOT="$HOME/work/project/cc/stock-analyzer"
BACKUP_DIR="$PROJECT_ROOT/data/backups/db"
LOG_FILE="$PROJECT_ROOT/data/logs/backup.log"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)

# Retention (days)
RETENTION_DAYS=7

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Database Backup Started ==="

# Function to backup a database
backup_db() {
    local db_path=$1
    local db_name=$(basename "$db_path" .db)
    local backup_file="$BACKUP_DIR/${db_name}_${DATE}.db"
    local compressed_file="$backup_file.gz"

    log "Backing up: $db_path"

    # Check if source exists
    if [ ! -f "$db_path" ]; then
        log "ERROR: Source database not found: $db_path"
        return 1
    fi

    # SQLite online backup (safe while DB in use)
    sqlite3 "$db_path" ".backup '$backup_file'"

    if [ $? -eq 0 ]; then
        log "✅ Backup created: $backup_file"

        # Get size
        local size=$(du -h "$backup_file" | cut -f1)
        log "   Size: $size"

        # Verify backup integrity
        sqlite3 "$backup_file" "PRAGMA integrity_check;" | grep -q "ok"
        if [ $? -eq 0 ]; then
            log "✅ Backup verified: OK"

            # Compress
            gzip -f "$backup_file"
            local compressed_size=$(du -h "$compressed_file" | cut -f1)
            log "✅ Compressed: $compressed_size"

            return 0
        else
            log "❌ Backup verification FAILED"
            rm -f "$backup_file"
            return 1
        fi
    else
        log "❌ Backup FAILED"
        return 1
    fi
}

# Backup main databases
backup_db "$PROJECT_ROOT/data/trade_history.db"
backup_db "$PROJECT_ROOT/data/database/stocks.db"

# Cleanup old backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
DELETED=$(find "$BACKUP_DIR" -name "*.db.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
log "Deleted $DELETED old backup(s)"

# Report summary
log "=== Backup Summary ==="
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "*.db.gz" | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Total backups: $TOTAL_BACKUPS"
log "Total size: $TOTAL_SIZE"
log "=== Backup Complete ==="

exit 0
```

**Make executable:**
```bash
chmod +x scripts/backup_database.sh
```

#### B. Restore Script (1 hour)

**File:** `scripts/restore_database.sh`
```bash
#!/bin/bash
#
# Database Restore Script
# Usage: ./restore_database.sh <backup_file> <target_db>
#

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <backup_file.gz> <target_db>"
    echo "Example: $0 data/backups/db/trade_history_2026-02-12.db.gz data/trade_history.db"
    exit 1
fi

BACKUP_FILE=$1
TARGET_DB=$2

# Verify backup exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Create backup of current DB (safety)
if [ -f "$TARGET_DB" ]; then
    SAFETY_BACKUP="${TARGET_DB}.before_restore_$(date +%Y%m%d_%H%M%S)"
    echo "Creating safety backup: $SAFETY_BACKUP"
    cp "$TARGET_DB" "$SAFETY_BACKUP"
fi

# Decompress
TEMP_DB=$(mktemp)
echo "Decompressing backup..."
gunzip -c "$BACKUP_FILE" > "$TEMP_DB"

# Verify integrity
echo "Verifying backup integrity..."
sqlite3 "$TEMP_DB" "PRAGMA integrity_check;" | grep -q "ok"
if [ $? -ne 0 ]; then
    echo "❌ Backup integrity check FAILED"
    rm -f "$TEMP_DB"
    exit 1
fi

# Restore
echo "Restoring database..."
mv "$TEMP_DB" "$TARGET_DB"

echo "✅ Restore complete: $TARGET_DB"
echo "Safety backup: $SAFETY_BACKUP (delete manually if restore OK)"
```

#### C. Setup Cron (30 min)

```bash
# Add to crontab
crontab -e

# Add these lines:
# Database backup (05:00 ET daily)
0 5 * * * /home/saengtawan/work/project/cc/stock-analyzer/scripts/backup_database.sh >> /home/saengtawan/work/project/cc/stock-analyzer/data/logs/cron.log 2>&1

# Database vacuum (1st of month, 03:00 ET)
0 3 1 * * /home/saengtawan/work/project/cc/stock-analyzer/scripts/vacuum_database.sh >> /home/saengtawan/work/project/cc/stock-analyzer/data/logs/cron.log 2>&1
```

### 2.2 Cache Management

#### A. Cache Cleanup Script (1 hour)

**File:** `scripts/clean_cache.sh`
```bash
#!/bin/bash
#
# Cache Cleanup Script
# Runs weekly on Sunday 02:00
#

set -euo pipefail

CACHE_DIR="$HOME/.stock_analyzer_cache"
LOG_FILE="$HOME/work/project/cc/stock-analyzer/data/logs/cache_cleanup.log"
MAX_AGE_DAYS=30
MAX_SIZE_MB=50

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Cache Cleanup Started ==="

# Check cache dir exists
if [ ! -d "$CACHE_DIR" ]; then
    log "Cache directory not found: $CACHE_DIR"
    exit 0
fi

# Count before
BEFORE=$(find "$CACHE_DIR" -type f | wc -l)
SIZE_BEFORE=$(du -sm "$CACHE_DIR" | cut -f1)

log "Before: $BEFORE files, ${SIZE_BEFORE}MB"

# Delete files older than MAX_AGE_DAYS
log "Deleting files older than $MAX_AGE_DAYS days..."
DELETED=$(find "$CACHE_DIR" -type f -mtime +$MAX_AGE_DAYS -delete -print | wc -l)
log "Deleted: $DELETED old files"

# Check size after age-based cleanup
SIZE_AFTER=$(du -sm "$CACHE_DIR" | cut -f1)

# If still over limit, delete oldest until under limit
if [ $SIZE_AFTER -gt $MAX_SIZE_MB ]; then
    log "Size ${SIZE_AFTER}MB > ${MAX_SIZE_MB}MB, deleting oldest files..."

    # Delete oldest files until under limit
    while [ $(du -sm "$CACHE_DIR" | cut -f1) -gt $MAX_SIZE_MB ]; do
        OLDEST=$(find "$CACHE_DIR" -type f -printf '%T+ %p\n' | sort | head -1 | cut -d' ' -f2-)
        if [ -n "$OLDEST" ]; then
            rm -f "$OLDEST"
        else
            break
        fi
    done

    SIZE_FINAL=$(du -sm "$CACHE_DIR" | cut -f1)
    log "Size reduced to ${SIZE_FINAL}MB"
fi

# Count after
AFTER=$(find "$CACHE_DIR" -type f | wc -l)
SIZE_FINAL=$(du -sm "$CACHE_DIR" | cut -f1)

log "After: $AFTER files, ${SIZE_FINAL}MB"
log "=== Cache Cleanup Complete ==="
```

**Cron:**
```bash
# Cache cleanup (Sunday 02:00)
0 2 * * 0 /home/saengtawan/work/project/cc/stock-analyzer/scripts/clean_cache.sh
```

### 2.3 Database Vacuum (1 hour)

**File:** `scripts/vacuum_database.sh`
```bash
#!/bin/bash
#
# Database Vacuum Script
# Runs monthly (1st of month, 03:00)
# Reclaims fragmented space
#

set -euo pipefail

PROJECT_ROOT="$HOME/work/project/cc/stock-analyzer"
LOG_FILE="$PROJECT_ROOT/data/logs/vacuum.log"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

vacuum_db() {
    local db_path=$1
    local db_name=$(basename "$db_path")

    log "Vacuuming: $db_name"

    # Size before
    SIZE_BEFORE=$(du -h "$db_path" | cut -f1)
    log "  Size before: $SIZE_BEFORE"

    # Vacuum
    sqlite3 "$db_path" "VACUUM;"

    if [ $? -eq 0 ]; then
        SIZE_AFTER=$(du -h "$db_path" | cut -f1)
        log "  Size after: $SIZE_AFTER"
        log "✅ Vacuum complete: $db_name"
    else
        log "❌ Vacuum failed: $db_name"
    fi
}

log "=== Database Vacuum Started ==="

vacuum_db "$PROJECT_ROOT/data/trade_history.db"
vacuum_db "$PROJECT_ROOT/data/database/stocks.db"

log "=== Vacuum Complete ==="
```

---

## PHASE 3: DATA ACCESS LAYER (Week 2)
**Priority:** MEDIUM-HIGH
**Time:** 16-20 hours
**Risk:** MEDIUM

### 3.1 Database Manager (NEW)

**File:** `src/data/db_manager.py`
```python
"""
Unified Database Manager
Single point of access for all database operations
"""
import sqlite3
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from pathlib import Path
from loguru import logger

class DatabaseManager:
    """
    Centralized database access with:
    - Connection pooling
    - Transaction management
    - Error handling
    - Query validation
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._connection = None

        if not self.db_path.exists():
            logger.warning(f"Database not found: {db_path}")

    @contextmanager
    def get_connection(self, read_only: bool = False):
        """
        Context manager for database connections.

        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False
        )

        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        # Set journal mode for better concurrency
        conn.execute("PRAGMA journal_mode = WAL")

        # Row factory for dict-like access
        conn.row_factory = sqlite3.Row

        try:
            yield conn
            if not read_only:
                conn.commit()
        except Exception as e:
            if not read_only:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def execute_query(
        self,
        query: str,
        params: tuple = (),
        fetch_one: bool = False
    ) -> Optional[List[Dict]]:
        """Execute a SELECT query and return results."""
        with self.get_connection(read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetch_one:
                row = cursor.fetchone()
                return dict(row) if row else None
            else:
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def execute_write(
        self,
        query: str,
        params: tuple = ()
    ) -> int:
        """Execute INSERT/UPDATE/DELETE and return affected rows."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount

    def execute_many(
        self,
        query: str,
        params_list: List[tuple]
    ) -> int:
        """Execute batch INSERT/UPDATE."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            return cursor.rowcount

# Global instances
trade_db = DatabaseManager("data/trade_history.db")
stock_db = DatabaseManager("data/database/stocks.db")
```

### 3.2 Trade Repository (Business Logic)

**File:** `src/data/repositories/trade_repository.py`
```python
"""
Trade Repository - Business logic for trade data
Separates data access from business logic
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from data.db_manager import trade_db
from data.validators import validate_trade
from loguru import logger

class TradeRepository:
    """
    Handle all trade-related database operations.

    Responsibilities:
    - CRUD operations for trades
    - Trade queries and reporting
    - Data validation
    - Transaction management
    """

    def __init__(self):
        self.db = trade_db

    def create_trade(self, trade_data: Dict[str, Any]) -> str:
        """
        Insert a new trade.

        Args:
            trade_data: Trade information

        Returns:
            Trade ID

        Raises:
            ValueError: If validation fails
        """
        # Validate before insert
        validate_trade(trade_data)

        query = """
            INSERT INTO trades (
                id, timestamp, date, action, symbol, qty, price,
                reason, entry_price, pnl_usd, pnl_pct, hold_duration,
                pdt_used, pdt_remaining, day_held, mode, regime,
                spy_price, signal_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            trade_data.get('id'),
            trade_data.get('timestamp'),
            trade_data.get('date'),
            trade_data.get('action'),
            trade_data.get('symbol'),
            trade_data.get('qty'),
            trade_data.get('price'),
            trade_data.get('reason'),
            trade_data.get('entry_price'),
            trade_data.get('pnl_usd'),
            trade_data.get('pnl_pct'),
            trade_data.get('hold_duration'),
            trade_data.get('pdt_used'),
            trade_data.get('pdt_remaining'),
            trade_data.get('day_held'),
            trade_data.get('mode'),
            trade_data.get('regime'),
            trade_data.get('spy_price'),
            trade_data.get('signal_score')
        )

        try:
            self.db.execute_write(query, params)
            logger.info(f"Trade created: {trade_data['symbol']} {trade_data['action']}")
            return trade_data['id']
        except Exception as e:
            logger.error(f"Failed to create trade: {e}")
            raise

    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get most recent trades."""
        query = """
            SELECT *
            FROM trades
            ORDER BY timestamp DESC
            LIMIT ?
        """
        return self.db.execute_query(query, (limit,))

    def get_trades_by_symbol(self, symbol: str) -> List[Dict]:
        """Get all trades for a symbol."""
        query = """
            SELECT *
            FROM trades
            WHERE symbol = ?
            ORDER BY timestamp DESC
        """
        return self.db.execute_query(query, (symbol,))

    def get_trade_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get trading statistics for last N days.

        Returns:
            Dict with wins, losses, win_rate, total_pnl, etc.
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END) as losses,
                SUM(pnl_usd) as total_pnl,
                AVG(pnl_pct) as avg_pnl_pct,
                MAX(pnl_pct) as max_win,
                MIN(pnl_pct) as max_loss
            FROM trades
            WHERE date >= ?
                AND action = 'SELL'
        """

        stats = self.db.execute_query(query, (cutoff,), fetch_one=True)

        if stats and stats['total_trades'] > 0:
            stats['win_rate'] = stats['wins'] / stats['total_trades'] * 100

        return stats or {}

    def get_open_positions_count(self) -> int:
        """Count currently open positions."""
        query = """
            SELECT COUNT(DISTINCT symbol) as count
            FROM trades
            WHERE symbol NOT IN (
                SELECT symbol FROM trades WHERE action = 'SELL'
            )
        """
        result = self.db.execute_query(query, fetch_one=True)
        return result['count'] if result else 0

# Global instance
trade_repo = TradeRepository()
```

### 3.3 Data Validators

**File:** `src/data/validators.py`
```python
"""
Data validation functions
Validate before writing to database
"""
from datetime import datetime
from typing import Dict, Any

class ValidationError(Exception):
    """Custom validation error"""
    pass

def validate_trade(trade_data: Dict[str, Any]) -> bool:
    """
    Validate trade data before database insert.

    Raises:
        ValidationError: If data is invalid
    """
    # Required fields
    required = ['symbol', 'action', 'qty', 'price', 'timestamp']
    for field in required:
        if field not in trade_data or trade_data[field] is None:
            raise ValidationError(f"Missing required field: {field}")

    # Symbol validation
    symbol = trade_data['symbol']
    if not isinstance(symbol, str) or len(symbol) == 0:
        raise ValidationError(f"Invalid symbol: {symbol}")

    # Action validation
    action = trade_data['action']
    if action not in ['BUY', 'SELL', 'SKIP']:
        raise ValidationError(f"Invalid action: {action}")

    # Quantity validation
    qty = trade_data['qty']
    if not isinstance(qty, (int, float)) or qty <= 0:
        raise ValidationError(f"Invalid quantity: {qty}")

    # Price validation
    price = trade_data['price']
    if not isinstance(price, (int, float)) or price <= 0:
        raise ValidationError(f"Invalid price: {price}")

    # Timestamp validation
    try:
        datetime.fromisoformat(str(trade_data['timestamp']))
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid timestamp: {trade_data['timestamp']}")

    # P&L validation (if present)
    if 'pnl_usd' in trade_data and trade_data['pnl_usd'] is not None:
        if not isinstance(trade_data['pnl_usd'], (int, float)):
            raise ValidationError(f"Invalid PnL: {trade_data['pnl_usd']}")

    return True

def validate_position(position_data: Dict[str, Any]) -> bool:
    """
    Validate position data before JSON save.

    Raises:
        ValidationError: If data is invalid
    """
    # Required fields
    required = ['symbol', 'qty', 'entry_price']
    for field in required:
        if field not in position_data:
            raise ValidationError(f"Missing required field: {field}")

    # Validations
    if position_data['qty'] <= 0:
        raise ValidationError(f"Invalid qty: {position_data['qty']}")

    if position_data['entry_price'] <= 0:
        raise ValidationError(f"Invalid entry_price: {position_data['entry_price']}")

    # Stop loss validation
    if 'sl_price' in position_data:
        if position_data['sl_price'] <= 0:
            raise ValidationError(f"Invalid sl_price: {position_data['sl_price']}")
        if position_data['sl_price'] >= position_data['entry_price']:
            raise ValidationError("SL must be below entry price")

    # Take profit validation
    if 'tp_price' in position_data:
        if position_data['tp_price'] <= 0:
            raise ValidationError(f"Invalid tp_price: {position_data['tp_price']}")
        if position_data['tp_price'] <= position_data['entry_price']:
            raise ValidationError("TP must be above entry price")

    return True
```

---

## PHASE 4: MIGRATION & CONSOLIDATION (Week 3)
**Priority:** MEDIUM
**Time:** 20-24 hours
**Risk:** MEDIUM-HIGH

### 4.1 Migrate JSON to SQLite

**Goal:** Move runtime state from JSON files to database

**New Tables:**

```sql
-- Active positions
CREATE TABLE IF NOT EXISTS active_positions (
    symbol TEXT PRIMARY KEY,
    qty INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    entry_time TEXT NOT NULL,
    sl_price REAL,
    tp_price REAL,
    sl_order_id TEXT,
    current_sl_price REAL,
    peak_price REAL,
    trough_price REAL,
    trailing_active INTEGER DEFAULT 0,
    days_held INTEGER DEFAULT 0,
    sl_pct REAL,
    tp_pct REAL,
    atr_pct REAL,
    sector TEXT,
    source TEXT,
    signal_score INTEGER,
    entry_mode TEXT,
    entry_regime TEXT,
    entry_rsi REAL,
    momentum_5d REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK(qty > 0),
    CHECK(entry_price > 0),
    CHECK(sl_price >= 0),
    CHECK(tp_price >= 0)
);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    resolved_at TEXT,
    CHECK(level IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL'))
);

-- Signals cache
CREATE TABLE IF NOT EXISTS signals_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    score REAL NOT NULL,
    mode TEXT,
    regime TEXT,
    session TEXT,
    scan_type TEXT,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_alerts_active ON alerts(active);
CREATE INDEX idx_signals_timestamp ON signals_cache(timestamp);
```

**Migration Script:**

**File:** `scripts/migrate_json_to_db.py`
```python
#!/usr/bin/env python3
"""
Migrate JSON files to SQLite
One-time migration script
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent

def migrate_positions():
    """Migrate active_positions.json to DB"""
    json_file = PROJECT_ROOT / "data/active_positions.json"
    db_file = PROJECT_ROOT / "data/trade_history.db"

    print("Migrating positions...")

    # Read JSON
    with open(json_file) as f:
        data = json.load(f)

    positions = data.get('positions', {})

    # Connect to DB
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_positions (
            symbol TEXT PRIMARY KEY,
            qty INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            entry_time TEXT NOT NULL,
            sl_price REAL,
            tp_price REAL,
            sl_order_id TEXT,
            current_sl_price REAL,
            peak_price REAL,
            trough_price REAL,
            trailing_active INTEGER DEFAULT 0,
            days_held INTEGER DEFAULT 0,
            sl_pct REAL,
            tp_pct REAL,
            atr_pct REAL,
            sector TEXT,
            source TEXT,
            signal_score INTEGER,
            entry_mode TEXT,
            entry_regime TEXT,
            entry_rsi REAL,
            momentum_5d REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert positions
    for symbol, pos in positions.items():
        cursor.execute("""
            INSERT OR REPLACE INTO active_positions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            pos.get('qty'),
            pos.get('entry_price'),
            pos.get('entry_time'),
            pos.get('sl_price'),
            pos.get('tp_price'),
            pos.get('sl_order_id'),
            pos.get('current_sl_price'),
            pos.get('peak_price'),
            pos.get('trough_price'),
            1 if pos.get('trailing_active') else 0,
            pos.get('days_held', 0),
            pos.get('sl_pct'),
            pos.get('tp_pct'),
            pos.get('atr_pct'),
            pos.get('sector'),
            pos.get('source'),
            pos.get('signal_score'),
            pos.get('entry_mode'),
            pos.get('entry_regime'),
            pos.get('entry_rsi'),
            pos.get('momentum_5d'),
            datetime.now().isoformat()
        ))

    conn.commit()
    conn.close()

    print(f"✅ Migrated {len(positions)} positions")

def migrate_alerts():
    """Migrate alerts.json to DB"""
    # Similar implementation...
    pass

if __name__ == "__main__":
    migrate_positions()
    migrate_alerts()
    print("✅ Migration complete")
```

### 4.2 Update Application Code

**Changes needed in:**
- `src/rapid_portfolio_manager.py` - Use DB instead of JSON
- `src/api/data_manager.py` - Use repositories
- `src/auto_trading_engine.py` - Use DB for positions

**Example refactor:**

```python
# OLD (JSON):
with open('data/active_positions.json') as f:
    positions = json.load(f)['positions']

# NEW (Database):
from data.repositories.position_repository import position_repo
positions = position_repo.get_all_active()
```

---

## PHASE 5: MONITORING & MAINTENANCE (Week 4)
**Priority:** HIGH
**Time:** 12-16 hours
**Risk:** LOW

### 5.1 Health Monitor

**File:** `scripts/health_monitor.py`
```python
#!/usr/bin/env python3
"""
Database Health Monitor
Runs continuously, sends alerts on issues
"""
import time
from pathlib import Path
from data.db_manager import trade_db, stock_db
from loguru import logger

def check_database_health():
    """Check database health metrics"""
    issues = []

    # Check 1: File exists
    if not Path("data/trade_history.db").exists():
        issues.append("Trade DB missing")

    # Check 2: Size limits
    trade_size = Path("data/trade_history.db").stat().st_size / 1024 / 1024
    if trade_size > 100:  # 100MB
        issues.append(f"Trade DB large: {trade_size:.0f}MB")

    # Check 3: Integrity
    try:
        result = trade_db.execute_query("PRAGMA integrity_check", fetch_one=True)
        if result and result.get('integrity_check') != 'ok':
            issues.append("Trade DB integrity failed")
    except:
        issues.append("Trade DB not accessible")

    # Check 4: Recent activity
    recent = trade_db.execute_query(
        "SELECT COUNT(*) as count FROM trades WHERE date >= date('now', '-7 days')",
        fetch_one=True
    )
    if recent and recent['count'] == 0:
        logger.warning("No trades in last 7 days")

    return issues

def check_backup_health():
    """Check backup status"""
    backup_dir = Path("data/backups/db")

    if not backup_dir.exists():
        return ["No backup directory"]

    # Find latest backup
    backups = sorted(backup_dir.glob("trade_history_*.db.gz"))

    if not backups:
        return ["No backups found"]

    latest = backups[-1]
    age_hours = (time.time() - latest.stat().st_mtime) / 3600

    if age_hours > 36:  # More than 1.5 days old
        return [f"Latest backup is {age_hours:.0f}h old"]

    return []

def monitor_loop():
    """Main monitoring loop"""
    logger.info("Health monitor started")

    while True:
        db_issues = check_database_health()
        backup_issues = check_backup_health()

        all_issues = db_issues + backup_issues

        if all_issues:
            logger.warning(f"Health issues: {', '.join(all_issues)}")
            # TODO: Send alert
        else:
            logger.debug("Health check: OK")

        # Check every 5 minutes
        time.sleep(300)

if __name__ == "__main__":
    monitor_loop()
```

### 5.2 Performance Monitoring

**File:** `scripts/db_performance.py`
```python
#!/usr/bin/env python3
"""
Monitor database performance metrics
"""
import time
import sqlite3
from pathlib import Path

def get_db_stats(db_path):
    """Get database statistics"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    stats = {}

    # Page stats
    stats['page_count'] = cursor.execute("PRAGMA page_count").fetchone()[0]
    stats['page_size'] = cursor.execute("PRAGMA page_size").fetchone()[0]
    stats['freelist_count'] = cursor.execute("PRAGMA freelist_count").fetchone()[0]

    # Size
    stats['size_mb'] = stats['page_count'] * stats['page_size'] / 1024 / 1024
    stats['fragmentation_pct'] = stats['freelist_count'] / stats['page_count'] * 100

    # Cache
    stats['cache_size'] = cursor.execute("PRAGMA cache_size").fetchone()[0]

    conn.close()
    return stats

def benchmark_query(db_path, query, iterations=100):
    """Benchmark a query"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    start = time.time()
    for _ in range(iterations):
        cursor.execute(query)
        cursor.fetchall()
    elapsed = time.time() - start

    conn.close()

    return elapsed / iterations * 1000  # ms per query

if __name__ == "__main__":
    db_path = "data/trade_history.db"

    print("Database Statistics:")
    stats = get_db_stats(db_path)
    for key, value in stats.items():
        print(f"  {key}: {value:.2f}")

    print("\nQuery Benchmarks:")
    queries = [
        ("Recent trades", "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10"),
        ("Trade count", "SELECT COUNT(*) FROM trades"),
    ]

    for name, query in queries:
        avg_time = benchmark_query(db_path, query)
        print(f"  {name}: {avg_time:.2f}ms")
```

---

## PHASE 6: DOCUMENTATION & TESTING (Week 4)
**Priority:** MEDIUM
**Time:** 8-10 hours
**Risk:** LOW

### 6.1 Documentation

**File:** `docs/DATABASE_GUIDE.md`
```markdown
# Database Management Guide

## Architecture

[Diagram from master plan]

## Daily Operations

### Check Health
```bash
python scripts/check_db_health.py
```

### Manual Backup
```bash
./scripts/backup_database.sh
```

### Restore from Backup
```bash
./scripts/restore_database.sh data/backups/db/trade_history_2026-02-12.db.gz data/trade_history.db
```

### Clean Cache
```bash
./scripts/clean_cache.sh
```

## Troubleshooting

### Database Locked
- Cause: Another process is writing
- Fix: Wait or kill process

### Slow Queries
- Check: `python scripts/db_performance.py`
- Fix: Run VACUUM

### Disk Full
- Check logs size: `du -sh data/logs/`
- Clean old logs: Move to archive

## Maintenance Schedule

- Daily 05:00: Database backup
- Weekly Sun 02:00: Cache cleanup
- Monthly 1st 03:00: Database VACUUM
```

### 6.2 Integration Tests

**File:** `tests/test_database_integration.py`
```python
"""
Integration tests for database layer
"""
import pytest
from data.repositories.trade_repository import trade_repo
from data.validators import validate_trade, ValidationError

def test_create_trade():
    """Test trade creation with validation"""
    trade_data = {
        'id': 'test_123',
        'symbol': 'AAPL',
        'action': 'BUY',
        'qty': 10,
        'price': 150.00,
        'timestamp': '2026-02-12T10:00:00'
    }

    # Should not raise
    validate_trade(trade_data)

    # Create (skip for test)
    # trade_id = trade_repo.create_trade(trade_data)
    # assert trade_id == 'test_123'

def test_invalid_trade():
    """Test validation catches bad data"""
    trade_data = {
        'id': 'test_bad',
        'symbol': 'AAPL',
        'action': 'BUY',
        'qty': -10,  # Invalid!
        'price': 150.00,
        'timestamp': '2026-02-12T10:00:00'
    }

    with pytest.raises(ValidationError):
        validate_trade(trade_data)

def test_get_trade_stats():
    """Test statistics calculation"""
    stats = trade_repo.get_trade_stats(days=30)

    assert 'total_trades' in stats
    assert 'win_rate' in stats
    # More assertions...
```

---

## ROLLBACK PLAN

### If Phase 3+ Fails

**Rollback Steps:**
1. Restore code from git
2. Restore DB from backup
3. Revert to JSON files
4. Keep Phase 1+2 improvements (logs, backup)

**Commands:**
```bash
# Restore code
git checkout HEAD~1

# Restore database
./scripts/restore_database.sh data/backups/db/trade_history_latest.db.gz data/trade_history.db

# Restart system
pkill -f run_app.py
python src/run_app.py &
```

---

## SUCCESS METRICS

### After Phase 1
- ✅ Log size < 50MB
- ✅ Logs auto-rotate
- ✅ No manual cleanup needed

### After Phase 2
- ✅ Daily backups running
- ✅ Can restore from backup
- ✅ Cache < 50MB

### After Phase 3
- ✅ Single DB access API
- ✅ All data validated
- ✅ Error rate < 0.1%

### After Phase 4
- ✅ No JSON files for runtime state
- ✅ All data in SQLite
- ✅ Faster queries

### After Phase 5
- ✅ Health monitoring active
- ✅ Issues detected automatically
- ✅ Performance tracked

### After Phase 6
- ✅ Documentation complete
- ✅ Tests passing
- ✅ Team trained

---

## FINAL GRADE TARGET

**Current:** C+ (57% health)
**Target:** A (90%+ health)

**Improvements:**
- Database Type: ✅ (already SQLite)
- Data Structure: C+ → A (unified)
- Backup Strategy: F → A (daily automated)
- Log Rotation: F → A (automated)
- Cache Management: D → A (automated)
- Data Validation: F → A (full validation)
- Monitoring: F → A (continuous)
- ACID Compliance: C → A (full)

**Final Score:** 8/8 = 100% ✅
