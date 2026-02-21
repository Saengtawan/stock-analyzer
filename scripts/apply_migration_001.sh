#!/bin/bash
# Apply Migration 001: Create Trading Signals Tables

set -e  # Exit on error

DB_PATH="data/trade_history.db"
MIGRATION_FILE="scripts/migrations/001_create_signals_tables.sql"

echo "========================================"
echo "Migration 001: Trading Signals Tables"
echo "========================================"
echo ""

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Error: Database not found at $DB_PATH"
    exit 1
fi

# Check if migration file exists
if [ ! -f "$MIGRATION_FILE" ]; then
    echo "❌ Error: Migration file not found at $MIGRATION_FILE"
    exit 1
fi

echo "📁 Database: $DB_PATH"
echo "📄 Migration: $MIGRATION_FILE"
echo ""

# Backup database
BACKUP_PATH="${DB_PATH}.backup_$(date +%Y%m%d_%H%M%S)"
echo "💾 Creating backup: $BACKUP_PATH"
cp "$DB_PATH" "$BACKUP_PATH"
echo "✅ Backup created"
echo ""

# Apply migration
echo "🚀 Applying migration..."
sqlite3 "$DB_PATH" < "$MIGRATION_FILE"
echo "✅ Migration applied"
echo ""

# Verify tables created
echo "🔍 Verifying tables..."
TABLES=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trading_signals', 'execution_history', 'signal_queue', 'scan_sessions') ORDER BY name")

if [ -z "$TABLES" ]; then
    echo "❌ Error: No tables created"
    exit 1
fi

echo "✅ Tables created:"
echo "$TABLES" | while read table; do
    echo "   - $table"
done
echo ""

# Show table counts
echo "📊 Table row counts:"
for table in trading_signals execution_history signal_queue scan_sessions; do
    COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table" 2>/dev/null || echo "0")
    echo "   - $table: $COUNT rows"
done
echo ""

echo "========================================"
echo "✅ Migration 001 completed successfully"
echo "========================================"
echo ""
echo "Backup saved at: $BACKUP_PATH"
echo ""
echo "To verify schema:"
echo "  sqlite3 $DB_PATH \".schema trading_signals\""
echo ""
echo "To rollback (if needed):"
echo "  cp $BACKUP_PATH $DB_PATH"
