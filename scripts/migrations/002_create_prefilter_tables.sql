-- ============================================================================
-- Migration 002: Pre-filter Tables
-- ============================================================================
-- Created: 2026-02-21
-- Purpose: Store pre-filter scan sessions and filtered stock pool
-- ============================================================================

-- Table 1: Pre-filter Scan Sessions
-- ============================================================================
CREATE TABLE IF NOT EXISTS pre_filter_sessions (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Session Identity
    scan_type TEXT NOT NULL,                    -- 'evening' or 'pre_open'
    scan_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Scan Results
    pool_size INTEGER NOT NULL DEFAULT 0,       -- Number of stocks passed filter
    total_scanned INTEGER NOT NULL DEFAULT 0,   -- Total stocks scanned (e.g., 987)

    -- Status
    status TEXT NOT NULL DEFAULT 'running',     -- 'running', 'completed', 'failed'
    is_ready BOOLEAN NOT NULL DEFAULT 0,        -- Ready for trading use

    -- Performance
    duration_seconds REAL,                      -- Scan duration

    -- Metadata
    error_message TEXT,                         -- Error if failed
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CHECK (scan_type IN ('evening', 'pre_open')),
    CHECK (status IN ('running', 'completed', 'failed')),
    CHECK (pool_size >= 0),
    CHECK (total_scanned >= 0)
);

-- Indexes for pre_filter_sessions
CREATE INDEX IF NOT EXISTS idx_prefilter_sessions_time
    ON pre_filter_sessions(scan_time DESC);

CREATE INDEX IF NOT EXISTS idx_prefilter_sessions_type
    ON pre_filter_sessions(scan_type);

CREATE INDEX IF NOT EXISTS idx_prefilter_sessions_status
    ON pre_filter_sessions(status);

CREATE INDEX IF NOT EXISTS idx_prefilter_sessions_ready
    ON pre_filter_sessions(is_ready);


-- Table 2: Filtered Stocks Pool
-- ============================================================================
CREATE TABLE IF NOT EXISTS filtered_stocks (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Foreign Key to Session
    session_id INTEGER NOT NULL,

    -- Stock Identity
    symbol TEXT NOT NULL,
    sector TEXT,

    -- Pre-filter Scores (from pre_filter.py logic)
    score REAL,                                 -- Overall pre-filter score

    -- Technical Indicators (snapshot at filter time)
    close_price REAL,
    volume_avg_20d REAL,
    atr_pct REAL,
    rsi REAL,

    -- Metadata
    filter_reason TEXT,                         -- Why this stock passed
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Key Constraint
    FOREIGN KEY (session_id) REFERENCES pre_filter_sessions(id) ON DELETE CASCADE
);

-- Indexes for filtered_stocks
CREATE INDEX IF NOT EXISTS idx_filtered_stocks_session
    ON filtered_stocks(session_id);

CREATE INDEX IF NOT EXISTS idx_filtered_stocks_symbol
    ON filtered_stocks(symbol);

CREATE INDEX IF NOT EXISTS idx_filtered_stocks_sector
    ON filtered_stocks(sector);

CREATE INDEX IF NOT EXISTS idx_filtered_stocks_score
    ON filtered_stocks(score DESC);

CREATE INDEX IF NOT EXISTS idx_filtered_stocks_symbol_session
    ON filtered_stocks(symbol, session_id);


-- ============================================================================
-- Cleanup Queries (for maintenance)
-- ============================================================================

-- Delete old sessions (keep last 30 days)
-- DELETE FROM pre_filter_sessions
-- WHERE scan_time < datetime('now', '-30 days');

-- Get latest session
-- SELECT * FROM pre_filter_sessions
-- ORDER BY scan_time DESC LIMIT 1;

-- Get filtered pool for latest session
-- SELECT s.* FROM filtered_stocks s
-- JOIN pre_filter_sessions ps ON s.session_id = ps.id
-- WHERE ps.id = (SELECT id FROM pre_filter_sessions ORDER BY scan_time DESC LIMIT 1);

-- Pool size by scan type
-- SELECT scan_type, AVG(pool_size), MIN(pool_size), MAX(pool_size)
-- FROM pre_filter_sessions
-- WHERE scan_time >= datetime('now', '-7 days')
-- GROUP BY scan_type;
