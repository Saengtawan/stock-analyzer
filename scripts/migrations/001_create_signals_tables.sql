-- Migration 001: Create Trading Signals Tables
-- Phase 1: Signals & Execution Cache Migration
-- Created: 2026-02-20

-- ===========================================================================
-- 1. Trading Signals Table
-- ===========================================================================
CREATE TABLE IF NOT EXISTS trading_signals (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core Signal Data
    symbol TEXT NOT NULL,
    score INTEGER NOT NULL,
    signal_price REAL NOT NULL,
    signal_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Risk Management
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    sl_pct REAL,
    tp_pct REAL,
    risk_reward REAL,
    expected_gain REAL,
    max_loss REAL,

    -- Technical Indicators
    atr_pct REAL,
    rsi REAL,
    momentum_5d REAL,
    momentum_20d REAL,
    distance_from_high REAL,
    swing_low REAL,
    resistance REAL,
    volume_ratio REAL,
    vwap REAL,

    -- Market Context
    sector TEXT,
    market_regime TEXT,
    sector_score INTEGER,
    alt_data_score INTEGER,

    -- Strategy Methods
    sl_method TEXT,
    tp_method TEXT,

    -- Signal Status
    status TEXT NOT NULL DEFAULT 'active',
    wait_reason TEXT,

    -- Scan Context
    scan_session_id INTEGER,
    session_type TEXT,
    scan_time_et TEXT,

    -- Execution Tracking
    executed_at TIMESTAMP,
    execution_result TEXT,

    -- Signal Reasons (JSON array)
    reasons TEXT,

    -- Metadata (JSON)
    metadata TEXT,

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (scan_session_id) REFERENCES scan_sessions(id) ON DELETE SET NULL
);

-- Indexes for trading_signals
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON trading_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_time ON trading_signals(signal_time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON trading_signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_session ON trading_signals(scan_session_id);
CREATE INDEX IF NOT EXISTS idx_signals_regime ON trading_signals(market_regime);
CREATE INDEX IF NOT EXISTS idx_signals_sector ON trading_signals(sector);
CREATE INDEX IF NOT EXISTS idx_signals_score ON trading_signals(score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading_signals(symbol, signal_time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status_time ON trading_signals(status, signal_time DESC);

-- ===========================================================================
-- 2. Execution History Table
-- ===========================================================================
CREATE TABLE IF NOT EXISTS execution_history (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core Data
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Skip Reason (for SKIPPED_FILTER, QUEUE_FULL)
    skip_reason TEXT,

    -- Signal Reference
    signal_id INTEGER,
    signal_score INTEGER,
    signal_price REAL,

    -- Execution Context
    scan_session_id INTEGER,
    session_type TEXT,
    market_regime TEXT,

    -- Position Context (for BOUGHT)
    entry_price REAL,
    qty INTEGER,
    stop_loss REAL,
    take_profit REAL,

    -- Metadata
    metadata TEXT,

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (signal_id) REFERENCES trading_signals(id) ON DELETE SET NULL,
    FOREIGN KEY (scan_session_id) REFERENCES scan_sessions(id) ON DELETE SET NULL
);

-- Indexes for execution_history
CREATE INDEX IF NOT EXISTS idx_exec_symbol ON execution_history(symbol);
CREATE INDEX IF NOT EXISTS idx_exec_time ON execution_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_action ON execution_history(action);
CREATE INDEX IF NOT EXISTS idx_exec_session ON execution_history(scan_session_id);
CREATE INDEX IF NOT EXISTS idx_exec_symbol_time ON execution_history(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_action_time ON execution_history(action, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_date ON execution_history(DATE(timestamp));

-- ===========================================================================
-- 3. Signal Queue Table
-- ===========================================================================
CREATE TABLE IF NOT EXISTS signal_queue (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core Signal Data
    symbol TEXT NOT NULL UNIQUE,
    signal_price REAL NOT NULL,
    score INTEGER NOT NULL,

    -- Risk Management
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    sl_pct REAL,
    tp_pct REAL,

    -- Queue Metadata
    queued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMP,

    -- Technical Context (minimal)
    atr_pct REAL,
    reasons TEXT,

    -- Signal Reference
    signal_id INTEGER,

    -- Status
    status TEXT NOT NULL DEFAULT 'waiting',

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (signal_id) REFERENCES trading_signals(id) ON DELETE SET NULL
);

-- Indexes for signal_queue
CREATE INDEX IF NOT EXISTS idx_queue_symbol ON signal_queue(symbol);
CREATE INDEX IF NOT EXISTS idx_queue_score ON signal_queue(score DESC);
CREATE INDEX IF NOT EXISTS idx_queue_queued_at ON signal_queue(queued_at);
CREATE INDEX IF NOT EXISTS idx_queue_status ON signal_queue(status);

-- ===========================================================================
-- 4. Scan Sessions Table
-- ===========================================================================
CREATE TABLE IF NOT EXISTS scan_sessions (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Session Identity
    session_type TEXT NOT NULL,
    scan_time TIMESTAMP NOT NULL,
    scan_time_et TEXT,

    -- Market State
    mode TEXT,
    is_market_open BOOLEAN,
    market_regime TEXT,

    -- Scan Results
    signal_count INTEGER NOT NULL DEFAULT 0,
    waiting_count INTEGER NOT NULL DEFAULT 0,
    pool_size INTEGER,
    scan_duration_seconds REAL,

    -- Position Context
    positions_current INTEGER,
    positions_max INTEGER,
    positions_full BOOLEAN,

    -- Next Scan
    next_scan_et TEXT,
    next_scan_timestamp TIMESTAMP,
    next_open TIMESTAMP,
    next_close TIMESTAMP,

    -- Status
    status TEXT NOT NULL DEFAULT 'completed',

    -- Metadata
    metadata TEXT,

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for scan_sessions
CREATE INDEX IF NOT EXISTS idx_scan_time ON scan_sessions(scan_time DESC);
CREATE INDEX IF NOT EXISTS idx_scan_type ON scan_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_scan_regime ON scan_sessions(market_regime);
CREATE INDEX IF NOT EXISTS idx_scan_date ON scan_sessions(DATE(scan_time));

-- ===========================================================================
-- Migration Complete
-- ===========================================================================
-- To apply this migration:
--   sqlite3 data/databases/trade_history.db < scripts/migrations/001_create_signals_tables.sql
--
-- To verify:
--   sqlite3 data/databases/trade_history.db ".tables"
--   sqlite3 data/databases/trade_history.db ".schema trading_signals"
