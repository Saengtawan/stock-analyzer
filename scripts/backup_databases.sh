#!/bin/bash
#
# Database Backup Script
# Part of Phase 2: Backup & Recovery
#
# Schedule: Daily at 05:00 ET (before market open)
# Retention: 30 days
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/data/backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y-%m-%d)

# Databases to backup
DB1="$PROJECT_ROOT/data/trade_history.db"
DB2="$PROJECT_ROOT/data/database/stocks.db"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Database Backup - $TIMESTAMP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Function to backup a database
backup_database() {
    local db_path=$1
    local db_name=$(basename "$db_path" .db)
    local backup_file="$BACKUP_DIR/${db_name}_${TIMESTAMP}.db"
    local compressed_file="${backup_file}.gz"
    
    if [ ! -f "$db_path" ]; then
        echo "⚠ Warning: $db_path not found, skipping"
        return 1
    fi
    
    echo "Backing up: $db_name"
    echo "  Source: $db_path ($(du -h "$db_path" | cut -f1))"
    
    # Use SQLite backup API (online backup - safe even if database is in use)
    sqlite3 "$db_path" ".backup '$backup_file'" 2>/dev/null
    
    if [ $? -eq 0 ] && [ -f "$backup_file" ]; then
        # Verify backup integrity
        sqlite3 "$backup_file" "PRAGMA integrity_check;" > /dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            # Compress backup
            gzip -9 "$backup_file"
            
            local original_size=$(du -h "$db_path" | cut -f1)
            local backup_size=$(du -h "$compressed_file" | cut -f1)
            
            echo "  ✓ Backup: $compressed_file ($backup_size, compressed from $original_size)"
            return 0
        else
            echo "  ✗ Backup verification failed!"
            rm -f "$backup_file"
            return 1
        fi
    else
        echo "  ✗ Backup failed!"
        return 1
    fi
}

# Backup databases
SUCCESS=0
FAILED=0

if backup_database "$DB1"; then
    SUCCESS=$((SUCCESS + 1))
else
    FAILED=$((FAILED + 1))
fi

if backup_database "$DB2"; then
    SUCCESS=$((SUCCESS + 1))
else
    FAILED=$((FAILED + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Cleanup old backups (>$RETENTION_DAYS days)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Delete old backups
DELETED=$(find "$BACKUP_DIR" -name "*.db.gz" -mtime +$RETENTION_DAYS -delete -print 2>/dev/null | wc -l)
echo "Deleted $DELETED old backup(s)"
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Backup Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Success: $SUCCESS databases"
echo "  Failed:  $FAILED databases"
echo ""
echo "Backup directory size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""
echo "Recent backups:"
ls -lht "$BACKUP_DIR"/*.db.gz 2>/dev/null | head -5 || echo "  No backups found"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✓ All backups completed successfully"
    exit 0
else
    echo "✗ Some backups failed"
    exit 1
fi
