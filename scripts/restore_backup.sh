#!/bin/bash
#
# Database Restore Script
# Part of Phase 2: Backup & Recovery
#
# Usage: ./scripts/restore_backup.sh [date]
# Example: ./scripts/restore_backup.sh 2026-02-12
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/data/backups"

# Parse arguments
RESTORE_DATE=${1:-$(date +%Y-%m-%d)}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Database Restore - $RESTORE_DATE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Function to list available backups
list_backups() {
    echo "Available backups:"
    echo ""
    ls -lh "$BACKUP_DIR"/*.db.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    echo ""
}

# Function to restore a database
restore_database() {
    local db_name=$1
    local backup_file="$BACKUP_DIR/${db_name}_${RESTORE_DATE}.db.gz"
    
    # Determine target path
    if [ "$db_name" = "trade_history" ]; then
        local target_path="$PROJECT_ROOT/data/trade_history.db"
    elif [ "$db_name" = "stocks" ]; then
        local target_path="$PROJECT_ROOT/data/database/stocks.db"
    else
        echo "✗ Unknown database: $db_name"
        return 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        echo "✗ Backup not found: $backup_file"
        return 1
    fi
    
    echo "Restoring: $db_name"
    echo "  Backup: $backup_file ($(du -h "$backup_file" | cut -f1))"
    echo "  Target: $target_path"
    
    # Create backup of current database (if exists)
    if [ -f "$target_path" ]; then
        local current_backup="${target_path}.before_restore_$(date +%Y%m%d_%H%M%S)"
        echo "  Creating safety backup: $(basename "$current_backup")"
        cp "$target_path" "$current_backup"
    fi
    
    # Decompress and restore
    echo "  Decompressing..."
    gunzip -c "$backup_file" > "${target_path}.tmp"
    
    # Verify integrity
    echo "  Verifying integrity..."
    sqlite3 "${target_path}.tmp" "PRAGMA integrity_check;" > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        # Move to final location
        mv "${target_path}.tmp" "$target_path"
        echo "  ✓ Restore completed successfully"
        
        # Show record count
        local count=$(sqlite3 "$target_path" "SELECT COUNT(*) FROM (SELECT name FROM sqlite_master WHERE type='table' LIMIT 1);" 2>/dev/null || echo "N/A")
        echo "  Database size: $(du -h "$target_path" | cut -f1)"
        return 0
    else
        echo "  ✗ Backup file is corrupted!"
        rm -f "${target_path}.tmp"
        return 1
    fi
}

# Check if backup exists
if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR"/*.db.gz 2>/dev/null)" ]; then
    echo "✗ No backups found in $BACKUP_DIR"
    exit 1
fi

# If no date specified, show available backups
if [ -z "$1" ]; then
    list_backups
    echo "Usage: $0 [date]"
    echo "Example: $0 2026-02-12"
    exit 1
fi

# Confirm restore
echo "⚠ WARNING: This will replace current databases with backups from $RESTORE_DATE"
echo ""
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

echo ""

# Restore databases
SUCCESS=0
FAILED=0

if restore_database "trade_history"; then
    SUCCESS=$((SUCCESS + 1))
else
    FAILED=$((FAILED + 1))
fi

if restore_database "stocks"; then
    SUCCESS=$((SUCCESS + 1))
else
    FAILED=$((FAILED + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Restore Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Success: $SUCCESS databases"
echo "  Failed:  $FAILED databases"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✓ All databases restored successfully from $RESTORE_DATE"
    echo ""
    echo "Safety backups created (in case you need to revert):"
    ls -lht data/*.before_restore_* data/database/*.before_restore_* 2>/dev/null | head -5 || true
    exit 0
else
    echo "✗ Some restores failed"
    exit 1
fi
