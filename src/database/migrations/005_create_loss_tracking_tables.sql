-- Migration 005: Create Loss Tracking Tables
-- Purpose: Migrate loss counters & risk management from JSON to database
-- Date: 2026-02-21
-- Author: Claude Sonnet 4.5

-- ============================================================================
-- Loss Tracking Table (Main)
-- ============================================================================
-- Tracks overall consecutive losses and weekly P&L for risk management
-- Single-row table (id=1 always) - represents current system state

CREATE TABLE IF NOT EXISTS loss_tracking (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Single row constraint

    -- Consecutive loss tracking
    consecutive_losses INTEGER NOT NULL DEFAULT 0,

    -- Weekly P&L tracking
    weekly_realized_pnl REAL NOT NULL DEFAULT 0.0,
    weekly_reset_date TEXT,                 -- ISO date for weekly reset

    -- Cooldown management
    cooldown_until TEXT,                    -- ISO date (NULL if no cooldown)

    -- Audit
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    saved_at TEXT                           -- Legacy field (for JSON compatibility)
);

-- Insert default row (id=1)
INSERT OR IGNORE INTO loss_tracking (id, consecutive_losses, weekly_realized_pnl)
VALUES (1, 0, 0.0);

-- ============================================================================
-- Sector Loss Tracking Table
-- ============================================================================
-- Tracks losses per sector for sector-specific cooldowns

CREATE TABLE IF NOT EXISTS sector_loss_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Sector tracking
    sector TEXT NOT NULL UNIQUE,            -- Sector name (lowercase)

    -- Loss counting
    losses INTEGER NOT NULL DEFAULT 0,      -- Consecutive losses in this sector

    -- Cooldown management
    cooldown_until TEXT,                    -- ISO date (NULL if no cooldown)

    -- Audit
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sector_loss_sector ON sector_loss_tracking(sector);
CREATE INDEX IF NOT EXISTS idx_sector_loss_cooldown ON sector_loss_tracking(cooldown_until)
    WHERE cooldown_until IS NOT NULL;

-- ============================================================================
-- Triggers: Auto-update timestamps
-- ============================================================================

CREATE TRIGGER IF NOT EXISTS loss_tracking_updated_at
AFTER UPDATE ON loss_tracking
FOR EACH ROW
BEGIN
    UPDATE loss_tracking SET updated_at = datetime('now') WHERE id = 1;
END;

CREATE TRIGGER IF NOT EXISTS sector_loss_tracking_updated_at
AFTER UPDATE ON sector_loss_tracking
FOR EACH ROW
BEGIN
    UPDATE sector_loss_tracking SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- Views: Analytics & Monitoring
-- ============================================================================

-- View: Current risk status
CREATE VIEW IF NOT EXISTS v_risk_status AS
SELECT
    consecutive_losses,
    weekly_realized_pnl,
    cooldown_until,
    CASE
        WHEN cooldown_until IS NOT NULL AND cooldown_until > date('now') THEN 'COOLDOWN'
        WHEN consecutive_losses >= 3 THEN 'HIGH_RISK'
        WHEN consecutive_losses >= 2 THEN 'ELEVATED_RISK'
        ELSE 'NORMAL'
    END as risk_level,
    CASE
        WHEN cooldown_until IS NOT NULL AND cooldown_until > date('now') THEN
            julianday(cooldown_until) - julianday(date('now'))
        ELSE 0
    END as cooldown_days_remaining
FROM loss_tracking
WHERE id = 1;

-- View: Active sector cooldowns
CREATE VIEW IF NOT EXISTS v_active_sector_cooldowns AS
SELECT
    sector,
    losses,
    cooldown_until,
    julianday(cooldown_until) - julianday(date('now')) as days_remaining
FROM sector_loss_tracking
WHERE cooldown_until IS NOT NULL
  AND cooldown_until > date('now')
ORDER BY cooldown_until ASC;

-- View: High-risk sectors (2+ losses but not in cooldown)
CREATE VIEW IF NOT EXISTS v_high_risk_sectors AS
SELECT
    sector,
    losses,
    CASE
        WHEN losses >= 3 THEN 'CRITICAL'
        WHEN losses >= 2 THEN 'HIGH'
        ELSE 'ELEVATED'
    END as risk_level
FROM sector_loss_tracking
WHERE losses >= 2
  AND (cooldown_until IS NULL OR cooldown_until <= date('now'))
ORDER BY losses DESC;

-- ============================================================================
-- Helper Functions (via triggers)
-- ============================================================================

-- Auto-reset weekly P&L if past reset date
CREATE TRIGGER IF NOT EXISTS auto_reset_weekly_pnl
BEFORE UPDATE ON loss_tracking
FOR EACH ROW
WHEN NEW.weekly_reset_date IS NOT NULL
    AND NEW.weekly_reset_date < date('now')
BEGIN
    UPDATE loss_tracking
    SET weekly_realized_pnl = 0.0,
        weekly_reset_date = date('now', '+7 days')
    WHERE id = 1;
END;

-- ============================================================================
-- Notes
-- ============================================================================
-- Usage:
--   1. On LOSS: INCREMENT consecutive_losses, UPDATE weekly_pnl
--   2. On WIN: RESET consecutive_losses = 0
--   3. Check cooldown: SELECT cooldown_until > date('now') FROM loss_tracking
--   4. Sector loss: UPSERT sector_loss_tracking
--   5. Weekly reset: Auto-triggered or manual UPDATE weekly_reset_date

-- Risk Management Rules:
--   - consecutive_losses >= 3: Trigger cooldown
--   - cooldown_until > today: Block all trading
--   - Sector losses >= 2: Consider sector-specific cooldown
--   - Weekly P&L < -X%: Reduce position sizes
