#!/bin/bash
# Apply Migration 002: Create Pre-filter Tables

set -e  # Exit on error

DB_PATH="data/trade_history.db"
MIGRATION_FILE="scripts/migrations/002_create_prefilter_tables.sql"
BACKUP_DIR="data/backups"

echo "========================================"
echo "Applying Migration 002: Pre-filter Tables"
echo "========================================"

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Error: Database not found at $DB_PATH"
    exit 1
fi

# Create backup
echo "📦 Creating backup..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/trade_history_before_migration_002_$(date +%Y%m%d_%H%M%S).db"
cp "$DB_PATH" "$BACKUP_FILE"
echo "✅ Backup created: $BACKUP_FILE"

# Apply migration
echo ""
echo "🔧 Applying migration..."
sqlite3 "$DB_PATH" < "$MIGRATION_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Migration applied successfully"
else
    echo "❌ Migration failed"
    exit 1
fi

# Verify tables
echo ""
echo "🔍 Verifying tables..."
TABLES=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('pre_filter_sessions', 'filtered_stocks') ORDER BY name;")

if echo "$TABLES" | grep -q "pre_filter_sessions" && echo "$TABLES" | grep -q "filtered_stocks"; then
    echo "✅ Tables created:"
    echo "   - pre_filter_sessions"
    echo "   - filtered_stocks"
else
    echo "❌ Table verification failed"
    exit 1
fi

# Show table schema
echo ""
echo "📋 Table Schemas:"
echo "===================="
echo ""
echo "pre_filter_sessions:"
sqlite3 "$DB_PATH" ".schema pre_filter_sessions"
echo ""
echo "filtered_stocks:"
sqlite3 "$DB_PATH" ".schema filtered_stocks"

echo ""
echo "========================================"
echo "✅ Migration 002 Complete!"
echo "========================================"
echo ""
echo "Backup location: $BACKUP_FILE"
echo "To rollback, run: cp $BACKUP_FILE $DB_PATH"
