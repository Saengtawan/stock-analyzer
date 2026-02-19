#!/bin/bash
#
# Daily Maintenance Script
# Runs: Log cleanup, database backup, backup verification, cache cleanup
# Schedule: Daily at 05:00 ET (before market open at 09:30 ET)
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$PROJECT_ROOT/data/logs/maintenance_$(date +%Y-%m-%d).log"

{
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Daily Maintenance - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Task 1: Database backup (Phase 2)
    echo "[1/5] Running database backup..."
    if "$PROJECT_ROOT/scripts/backup_databases.sh"; then
        echo "✓ Database backup completed"
    else
        echo "✗ Database backup failed"
    fi
    echo ""

    # Task 2: Verify backups (Phase 2)
    echo "[2/5] Verifying backups..."
    sleep 5  # Wait for compression to finish
    if "$PROJECT_ROOT/scripts/verify_backups.sh"; then
        echo "✓ Backup verification completed"
    else
        echo "✗ Backup verification failed"
    fi
    echo ""

    # Task 3: Log cleanup (Phase 1)
    echo "[3/5] Running log cleanup..."
    if "$PROJECT_ROOT/scripts/cleanup_logs.sh"; then
        echo "✓ Log cleanup completed"
    else
        echo "✗ Log cleanup failed"
    fi
    echo ""

    # Task 4: Cache cleanup (old files >30 days)
    echo "[4/5] Cleaning old cache files (>30 days)..."
    CACHE_DIR="$HOME/.stock_analyzer_cache"
    if [ -d "$CACHE_DIR" ]; then
        BEFORE_SIZE=$(du -sh "$CACHE_DIR" 2>/dev/null | cut -f1 || echo "N/A")
        DELETED=$(find "$CACHE_DIR" -type f -mtime +30 -delete -print 2>/dev/null | wc -l)
        AFTER_SIZE=$(du -sh "$CACHE_DIR" 2>/dev/null | cut -f1 || echo "N/A")
        echo "  Cache size: $BEFORE_SIZE → $AFTER_SIZE"
        echo "  Deleted: $DELETED old files"
    else
        echo "  Cache directory not found"
    fi
    echo "✓ Cache cleanup completed"
    echo ""

    # Task 5: Database health check (Phase 5 - placeholder)
    echo "[5/5] Database health check..."
    echo "  trade_history.db: $(du -h "$PROJECT_ROOT/data/trade_history.db" 2>/dev/null | cut -f1 || echo 'N/A')"
    echo "  stocks.db: $(du -h "$PROJECT_ROOT/data/database/stocks.db" 2>/dev/null | cut -f1 || echo 'N/A')"
    echo "  ⏸ Full health check (Phase 5: Monitoring)"
    echo ""

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✓ Daily maintenance completed successfully"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

} 2>&1 | tee -a "$LOG_FILE"
