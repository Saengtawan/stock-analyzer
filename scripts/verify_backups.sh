#!/bin/bash
#
# Backup Verification Script
# Part of Phase 2: Backup & Recovery
#
# Tests backup integrity without restoring
# Schedule: Daily at 05:15 ET (15 min after backup)
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/data/backups"
TEMP_DIR=$(mktemp -d)

trap "rm -rf $TEMP_DIR" EXIT

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Backup Verification - $(date '+%Y-%m-%d %H:%M:%S')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Function to verify a backup
verify_backup() {
    local backup_file=$1
    local db_name=$(basename "$backup_file" .db.gz)
    
    echo "Verifying: $db_name"
    echo "  File: $(basename "$backup_file") ($(du -h "$backup_file" | cut -f1))"
    
    # Decompress to temp
    local temp_db="$TEMP_DIR/$(basename "$backup_file" .gz)"
    gunzip -c "$backup_file" > "$temp_db" 2>/dev/null
    
    if [ $? -ne 0 ]; then
        echo "  ✗ Decompression failed"
        return 1
    fi
    
    # Check integrity
    local result=$(sqlite3 "$temp_db" "PRAGMA integrity_check;" 2>/dev/null)
    
    if [ "$result" = "ok" ]; then
        # Count records (for trade_history)
        if [[ "$db_name" == *"trade_history"* ]]; then
            local count=$(sqlite3 "$temp_db" "SELECT COUNT(*) FROM trades;" 2>/dev/null)
            echo "  ✓ Integrity: OK (${count} trades)"
        # Count records (for stocks)
        elif [[ "$db_name" == *"stocks"* ]]; then
            local count=$(sqlite3 "$temp_db" "SELECT COUNT(*) FROM stock_prices;" 2>/dev/null)
            local tables=$(sqlite3 "$temp_db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)
            echo "  ✓ Integrity: OK (${count} prices, ${tables} tables)"
        else
            echo "  ✓ Integrity: OK"
        fi
        rm -f "$temp_db"
        return 0
    else
        echo "  ✗ Integrity check failed: $result"
        rm -f "$temp_db"
        return 1
    fi
}

# Find today's backups
TODAY=$(date +%Y-%m-%d)
BACKUPS=$(find "$BACKUP_DIR" -name "*_${TODAY}.db.gz" 2>/dev/null)

if [ -z "$BACKUPS" ]; then
    echo "⚠ No backups found for today ($TODAY)"
    echo ""
    echo "Recent backups:"
    ls -lht "$BACKUP_DIR"/*.db.gz 2>/dev/null | head -5 || echo "  No backups found"
    exit 1
fi

# Verify each backup
SUCCESS=0
FAILED=0

while IFS= read -r backup_file; do
    if verify_backup "$backup_file"; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAILED=$((FAILED + 1))
    fi
    echo ""
done <<< "$BACKUPS"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Verification Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Verified: $SUCCESS backups"
echo "  Failed:   $FAILED backups"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✓ All backups verified successfully"
    exit 0
else
    echo "✗ Some backups failed verification"
    exit 1
fi
