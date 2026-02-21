-- Migration 004: Create PDT Tracking Table
-- Purpose: Migrate PDT (Pattern Day Trader) tracking from JSON to database
-- Date: 2026-02-21
-- Author: Claude Sonnet 4.5

-- ============================================================================
-- PDT Tracking Table
-- ============================================================================
-- Tracks symbols that were bought today to prevent same-day sells (PDT violations)
-- SEC Pattern Day Trader Rule: Can't buy and sell same stock on same day > 3 times/5 days
-- unless account has $25k+ equity

CREATE TABLE IF NOT EXISTS pdt_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Symbol tracking
    symbol TEXT NOT NULL UNIQUE,

    -- Entry tracking
    entry_date TEXT NOT NULL,           -- ISO date (YYYY-MM-DD) when position opened
    entry_time TEXT,                    -- ISO datetime (optional, for audit)

    -- Exit tracking (NULL if position still open)
    exit_date TEXT,                     -- ISO date when position closed
    exit_time TEXT,                     -- ISO datetime (optional, for audit)

    -- Flags
    same_day_exit INTEGER DEFAULT 0,   -- 1 if exited same day (PDT violation)

    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_pdt_symbol ON pdt_tracking(symbol);
CREATE INDEX IF NOT EXISTS idx_pdt_entry_date ON pdt_tracking(entry_date);
CREATE INDEX IF NOT EXISTS idx_pdt_exit_date ON pdt_tracking(exit_date);
CREATE INDEX IF NOT EXISTS idx_pdt_same_day ON pdt_tracking(same_day_exit) WHERE same_day_exit = 1;

-- ============================================================================
-- Trigger: Auto-update updated_at timestamp
-- ============================================================================
CREATE TRIGGER IF NOT EXISTS pdt_tracking_updated_at
AFTER UPDATE ON pdt_tracking
FOR EACH ROW
BEGIN
    UPDATE pdt_tracking SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- View: Active PDT Restrictions (entries from today)
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_active_pdt_restrictions AS
SELECT
    symbol,
    entry_date,
    entry_time,
    created_at
FROM pdt_tracking
WHERE exit_date IS NULL              -- Still in position
  AND entry_date = date('now')       -- Entered today
ORDER BY entry_time DESC;

-- ============================================================================
-- View: PDT Violation History
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_pdt_violations AS
SELECT
    symbol,
    entry_date,
    exit_date,
    entry_time,
    exit_time,
    created_at
FROM pdt_tracking
WHERE same_day_exit = 1              -- Same-day exit
ORDER BY exit_date DESC, exit_time DESC;

-- ============================================================================
-- Notes
-- ============================================================================
-- Usage:
--   1. On BUY: INSERT symbol with entry_date = today
--   2. On SELL check: SELECT from v_active_pdt_restrictions WHERE symbol = ?
--   3. On SELL complete: UPDATE with exit_date, same_day_exit flag
--   4. Cleanup: DELETE entries older than 30 days for audit trail
