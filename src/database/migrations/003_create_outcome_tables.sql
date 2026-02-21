-- Migration 003: Create Outcome Tables
-- Purpose: Migrate outcome tracking from JSON to database
-- Date: 2026-02-21
-- Author: Claude Sonnet 4.5

-- ============================================================================
-- Sell Outcomes Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS sell_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Trade Reference
    trade_id TEXT NOT NULL UNIQUE,  -- Links to trade_history
    symbol TEXT NOT NULL,

    -- Sell Details
    sell_date TEXT NOT NULL,
    sell_price REAL NOT NULL,
    sell_reason TEXT,
    sell_pnl_pct REAL,

    -- Post-Sell Price Action (tracked over 5 days)
    post_sell_close_1d REAL,        -- Close price 1 day after sell
    post_sell_close_3d REAL,        -- Close price 3 days after sell
    post_sell_close_5d REAL,        -- Close price 5 days after sell
    post_sell_max_5d REAL,          -- Highest price in 5 days after sell
    post_sell_min_5d REAL,          -- Lowest price in 5 days after sell

    -- Performance Metrics
    post_sell_pnl_pct_1d REAL,      -- % change from sell price (1 day)
    post_sell_pnl_pct_5d REAL,      -- % change from sell price (5 days)

    -- Audit
    tracked_at TEXT NOT NULL,
    updated_at TEXT,

    -- Indexes
    FOREIGN KEY (trade_id) REFERENCES trade_history(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sell_outcomes_symbol ON sell_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_sell_outcomes_date ON sell_outcomes(sell_date);
CREATE INDEX IF NOT EXISTS idx_sell_outcomes_reason ON sell_outcomes(sell_reason);
CREATE INDEX IF NOT EXISTS idx_sell_outcomes_tracked ON sell_outcomes(tracked_at);

-- ============================================================================
-- Signal Outcomes Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Scan Reference
    scan_id TEXT NOT NULL,
    scan_date TEXT NOT NULL,
    scan_type TEXT,                 -- continuous_afternoon, morning, etc.

    -- Signal Details
    symbol TEXT NOT NULL,
    signal_rank INTEGER,            -- Rank in scan results (1 = top signal)
    action_taken TEXT,              -- EXECUTED, SKIPPED_FILTER, QUEUED, etc.
    score INTEGER,
    signal_source TEXT,             -- dip_bounce, vix_adaptive, etc.
    scan_price REAL,

    -- Outcome Metrics (tracked over 5 days)
    outcome_1d REAL,                -- % change 1 day after scan
    outcome_3d REAL,                -- % change 3 days after scan
    outcome_5d REAL,                -- % change 5 days after scan
    outcome_max_gain_5d REAL,       -- Max gain % in 5 days
    outcome_max_dd_5d REAL,         -- Max drawdown % in 5 days

    -- Audit
    tracked_at TEXT NOT NULL,
    updated_at TEXT,

    -- Unique constraint (one outcome per scan+symbol)
    UNIQUE(scan_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_symbol ON signal_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_date ON signal_outcomes(scan_date);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_action ON signal_outcomes(action_taken);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_source ON signal_outcomes(signal_source);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_score ON signal_outcomes(score);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_tracked ON signal_outcomes(tracked_at);

-- ============================================================================
-- Rejected Outcomes Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS rejected_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Scan Reference
    scan_id TEXT NOT NULL,
    scan_date TEXT NOT NULL,
    scan_type TEXT,

    -- Rejected Signal Details
    symbol TEXT NOT NULL,
    signal_rank INTEGER,
    rejection_reason TEXT,          -- Why it was rejected
    score INTEGER,
    signal_source TEXT,
    scan_price REAL,

    -- Outcome Metrics (same as signal_outcomes)
    outcome_1d REAL,
    outcome_3d REAL,
    outcome_5d REAL,
    outcome_max_gain_5d REAL,
    outcome_max_dd_5d REAL,

    -- Audit
    tracked_at TEXT NOT NULL,
    updated_at TEXT,

    UNIQUE(scan_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_rejected_outcomes_symbol ON rejected_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_rejected_outcomes_date ON rejected_outcomes(scan_date);
CREATE INDEX IF NOT EXISTS idx_rejected_outcomes_reason ON rejected_outcomes(rejection_reason);
CREATE INDEX IF NOT EXISTS idx_rejected_outcomes_tracked ON rejected_outcomes(tracked_at);

-- ============================================================================
-- Views for Analytics
-- ============================================================================

-- View: Sell decisions were good or bad?
CREATE VIEW IF NOT EXISTS v_sell_decision_quality AS
SELECT
    symbol,
    sell_date,
    sell_reason,
    sell_pnl_pct,
    post_sell_pnl_pct_1d,
    post_sell_pnl_pct_5d,
    CASE
        WHEN post_sell_pnl_pct_5d < 0 THEN 'Good Sell'  -- Price went down after sell
        WHEN post_sell_pnl_pct_5d > 5 THEN 'Bad Sell'   -- Price rallied >5% after sell
        ELSE 'Neutral'
    END as decision_quality
FROM sell_outcomes
WHERE post_sell_pnl_pct_5d IS NOT NULL;

-- View: Signal quality by source
CREATE VIEW IF NOT EXISTS v_signal_quality_by_source AS
SELECT
    signal_source,
    action_taken,
    COUNT(*) as count,
    AVG(outcome_5d) as avg_outcome_5d,
    AVG(outcome_max_gain_5d) as avg_max_gain,
    AVG(outcome_max_dd_5d) as avg_max_dd,
    SUM(CASE WHEN outcome_5d > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
FROM signal_outcomes
WHERE outcome_5d IS NOT NULL
GROUP BY signal_source, action_taken;

-- View: Rejection analysis (did we miss good trades?)
CREATE VIEW IF NOT EXISTS v_rejection_analysis AS
SELECT
    rejection_reason,
    COUNT(*) as count,
    AVG(outcome_5d) as avg_outcome_5d,
    SUM(CASE WHEN outcome_5d > 5 THEN 1 ELSE 0 END) as missed_winners,
    SUM(CASE WHEN outcome_5d < -5 THEN 1 ELSE 0 END) as avoided_losers
FROM rejected_outcomes
WHERE outcome_5d IS NOT NULL
GROUP BY rejection_reason
ORDER BY avg_outcome_5d DESC;
