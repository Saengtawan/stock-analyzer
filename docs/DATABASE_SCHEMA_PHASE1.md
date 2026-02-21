# Database Schema Design - Phase 1: Signals & Execution Cache

## Overview
Migrate high-frequency JSON files to database for better performance, consistency, and query capabilities.

**Target Files:**
- `data/cache/rapid_signals.json` (45KB, update every 1-5 min)
- `data/cache/execution_status.json` (820KB, update per trade)
- `data/signal_queue.json` (2KB, update when positions full)

---

## 1. Trading Signals Table

### Purpose
Store all trading signals (active, waiting, historical) with full context for analysis and monitoring.

### Schema: `trading_signals`

```sql
CREATE TABLE IF NOT EXISTS trading_signals (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core Signal Data
    symbol TEXT NOT NULL,
    score INTEGER NOT NULL,
    signal_price REAL NOT NULL,  -- entry_price in JSON
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
    market_regime TEXT,  -- BULL, BEAR, NORMAL
    sector_score INTEGER,
    alt_data_score INTEGER,

    -- Strategy Methods
    sl_method TEXT,  -- EMA5, ATR, SwingLow, etc.
    tp_method TEXT,  -- 52wHigh, Resistance, RR, etc.

    -- Signal Status
    status TEXT NOT NULL DEFAULT 'active',  -- active, waiting, executed, expired
    wait_reason TEXT,  -- positions_full, etc.

    -- Scan Context
    scan_session_id INTEGER,  -- FK to scan_sessions
    session_type TEXT,  -- morning, midday, afternoon, etc.
    scan_time_et TEXT,  -- "11:33:02 ET"

    -- Execution Tracking
    executed_at TIMESTAMP,
    execution_result TEXT,  -- BOUGHT, SKIPPED_FILTER, QUEUED, etc.

    -- Signal Reasons (JSON array)
    reasons TEXT,  -- JSON: ["Strong bounce", "Big dip yesterday -3.9%", ...]

    -- Metadata (JSON)
    metadata TEXT,  -- Additional flexible data

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON trading_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_time ON trading_signals(signal_time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON trading_signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_session ON trading_signals(scan_session_id);
CREATE INDEX IF NOT EXISTS idx_signals_regime ON trading_signals(market_regime);
CREATE INDEX IF NOT EXISTS idx_signals_sector ON trading_signals(sector);
CREATE INDEX IF NOT EXISTS idx_signals_score ON trading_signals(score DESC);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading_signals(symbol, signal_time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status_time ON trading_signals(status, signal_time DESC);
```

**Field Mapping from JSON:**
- `entry_price` → `signal_price`
- `reason` → `wait_reason`
- `reasons` (array) → `reasons` (JSON TEXT)
- All other fields map 1:1

**Status Flow:**
1. `active` - Signal generated, can be executed immediately
2. `waiting` - Signal valid but positions full (also in signal_queue)
3. `executed` - Signal executed (BOUGHT or attempted)
4. `expired` - Signal aged out without execution

---

## 2. Execution History Table

### Purpose
Track all execution attempts with outcomes for monitoring and analysis.

### Schema: `execution_history`

```sql
CREATE TABLE IF NOT EXISTS execution_history (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core Data
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,  -- BOUGHT, SKIPPED_FILTER, QUEUED, QUEUE_FULL
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Skip Reason (for SKIPPED_FILTER, QUEUE_FULL)
    skip_reason TEXT,  -- "ATR 5.0%", "positions_full", "Queue Full", etc.

    -- Signal Reference
    signal_id INTEGER,  -- FK to trading_signals (optional)
    signal_score INTEGER,
    signal_price REAL,

    -- Execution Context
    scan_session_id INTEGER,  -- FK to scan_sessions
    session_type TEXT,
    market_regime TEXT,

    -- Position Context (for BOUGHT)
    entry_price REAL,
    qty INTEGER,
    stop_loss REAL,
    take_profit REAL,

    -- Metadata
    metadata TEXT,  -- JSON for additional context

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_exec_symbol ON execution_history(symbol);
CREATE INDEX IF NOT EXISTS idx_exec_time ON execution_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_action ON execution_history(action);
CREATE INDEX IF NOT EXISTS idx_exec_session ON execution_history(scan_session_id);

-- Composite indexes for analytics
CREATE INDEX IF NOT EXISTS idx_exec_symbol_time ON execution_history(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_action_time ON execution_history(action, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_exec_date ON execution_history(DATE(timestamp));
```

**Action Types:**
- `BOUGHT` - Successfully purchased
- `SKIPPED_FILTER` - Failed entry filters
- `QUEUED` - Added to queue (positions full)
- `QUEUE_FULL` - Queue full, cannot add

**Query Patterns:**
- Last action for symbol: `SELECT * FROM execution_history WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1`
- Daily summary: `SELECT action, COUNT(*) FROM execution_history WHERE DATE(timestamp) = ? GROUP BY action`
- Skip reasons analysis: `SELECT skip_reason, COUNT(*) FROM execution_history WHERE action = 'SKIPPED_FILTER' GROUP BY skip_reason`

---

## 3. Signal Queue Table

### Purpose
Store signals waiting for position slots (when positions_full).

### Schema: `signal_queue`

```sql
CREATE TABLE IF NOT EXISTS signal_queue (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core Signal Data
    symbol TEXT NOT NULL UNIQUE,  -- Only one entry per symbol
    signal_price REAL NOT NULL,
    score INTEGER NOT NULL,

    -- Risk Management
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    sl_pct REAL,
    tp_pct REAL,

    -- Queue Metadata
    queued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,  -- Execution attempts
    last_attempt_at TIMESTAMP,

    -- Technical Context (minimal)
    atr_pct REAL,
    reasons TEXT,  -- JSON array

    -- Signal Reference
    signal_id INTEGER,  -- FK to trading_signals (optional)

    -- Status
    status TEXT NOT NULL DEFAULT 'waiting',  -- waiting, executing, removed

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_queue_symbol ON signal_queue(symbol);
CREATE INDEX IF NOT EXISTS idx_queue_score ON signal_queue(score DESC);
CREATE INDEX IF NOT EXISTS idx_queue_queued_at ON signal_queue(queued_at);
CREATE INDEX IF NOT EXISTS idx_queue_status ON signal_queue(status);
```

**Queue Operations:**
- Add signal: `INSERT OR REPLACE INTO signal_queue (...)`
- Get top signal: `SELECT * FROM signal_queue WHERE status = 'waiting' ORDER BY score DESC, queued_at ASC LIMIT 1`
- Remove executed: `DELETE FROM signal_queue WHERE symbol = ?`
- Clear all: `DELETE FROM signal_queue WHERE status = 'waiting'`

---

## 4. Scan Sessions Table

### Purpose
Track scan metadata for correlation with signals and execution history.

### Schema: `scan_sessions`

```sql
CREATE TABLE IF NOT EXISTS scan_sessions (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Session Identity
    session_type TEXT NOT NULL,  -- morning, midday, afternoon, pem, ovn, etc.
    scan_time TIMESTAMP NOT NULL,
    scan_time_et TEXT,  -- "11:33:02 ET"

    -- Market State
    mode TEXT,  -- market, premarket, afterhours
    is_market_open BOOLEAN,
    market_regime TEXT,  -- BULL_MODE, BEAR_MODE, NORMAL

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
    status TEXT NOT NULL DEFAULT 'completed',  -- running, completed, failed

    -- Metadata
    metadata TEXT,  -- JSON for additional context

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_scan_time ON scan_sessions(scan_time DESC);
CREATE INDEX IF NOT EXISTS idx_scan_type ON scan_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_scan_regime ON scan_sessions(market_regime);
CREATE INDEX IF NOT EXISTS idx_scan_date ON scan_sessions(DATE(scan_time));
```

**Purpose:**
- Track scan performance over time
- Correlate signals with market conditions
- Analyze regime-based signal quality
- Monitor system health

---

## Data Migration Strategy

### Phase 1A: Create Tables & Models

1. **Create models** in `src/database/models/`:
   - `trading_signal.py` - TradingSignal dataclass
   - `execution_record.py` - ExecutionRecord dataclass
   - `queued_signal.py` - QueuedSignal dataclass
   - `scan_session.py` - ScanSession dataclass

2. **Create repositories** in `src/database/repositories/`:
   - `signal_repository.py` - CRUD for trading_signals
   - `execution_repository.py` - CRUD for execution_history
   - `queue_repository.py` - CRUD for signal_queue
   - `scan_repository.py` - CRUD for scan_sessions

3. **Create migration script**:
   - `scripts/migrations/001_create_signals_tables.sql`
   - Run via `sqlite3 trade_history.db < scripts/migrations/001_create_signals_tables.sql`

### Phase 1B: Dual Write (JSON + DB)

**Update auto_trading_engine.py:**
- Keep existing JSON writes
- Add DB writes via repositories
- Run parallel for 1-2 weeks
- Verify consistency

**Key locations:**
- Line 1107: `_save_signals_cache()` → Add SignalRepository.save_scan()
- Line 3390: `_save_execution_status()` → Add ExecutionRepository.add_record()
- Line 593: `signal_queue.json` → Add QueueRepository operations

### Phase 1C: Switch to DB Primary

**Update read operations:**
- `src/web/app.py` line 2747: Read from SignalRepository instead of JSON
- `src/auto_trading_engine.py`: Load queue from QueueRepository on startup
- Keep JSON as backup (read-only)

### Phase 1D: Remove JSON

After 1-2 weeks of stable DB operations:
- Archive JSON files
- Remove write operations
- Remove read fallbacks
- Clean up `engine/state_manager.py` (atomic_write_json still used elsewhere)

---

## Query Examples

### Get Active Signals
```sql
SELECT symbol, score, signal_price, stop_loss, take_profit, signal_time
FROM trading_signals
WHERE status = 'active'
ORDER BY score DESC, signal_time DESC;
```

### Get Waiting Signals (Queue)
```sql
SELECT symbol, score, signal_price, wait_reason, signal_time
FROM trading_signals
WHERE status = 'waiting'
ORDER BY score DESC, signal_time ASC;
```

### Today's Execution Summary
```sql
SELECT
    action,
    COUNT(*) as count,
    COUNT(DISTINCT symbol) as unique_symbols
FROM execution_history
WHERE DATE(timestamp) = DATE('now')
GROUP BY action;
```

### Signal Conversion Rate (Last 7 Days)
```sql
SELECT
    DATE(signal_time) as date,
    COUNT(*) as total_signals,
    SUM(CASE WHEN execution_result = 'BOUGHT' THEN 1 ELSE 0 END) as bought,
    ROUND(100.0 * SUM(CASE WHEN execution_result = 'BOUGHT' THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
FROM trading_signals
WHERE signal_time >= DATE('now', '-7 days')
GROUP BY DATE(signal_time)
ORDER BY date DESC;
```

### Top Skip Reasons
```sql
SELECT
    skip_reason,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM execution_history WHERE action = 'SKIPPED_FILTER'), 2) as pct
FROM execution_history
WHERE action = 'SKIPPED_FILTER'
    AND skip_reason IS NOT NULL
    AND timestamp >= DATE('now', '-30 days')
GROUP BY skip_reason
ORDER BY count DESC
LIMIT 10;
```

### Signal Quality by Regime
```sql
SELECT
    market_regime,
    COUNT(*) as signals,
    AVG(score) as avg_score,
    SUM(CASE WHEN execution_result = 'BOUGHT' THEN 1 ELSE 0 END) as bought,
    ROUND(100.0 * SUM(CASE WHEN execution_result = 'BOUGHT' THEN 1 ELSE 0 END) / COUNT(*), 2) as buy_rate
FROM trading_signals
WHERE signal_time >= DATE('now', '-30 days')
GROUP BY market_regime;
```

### Queue Performance
```sql
SELECT
    COUNT(*) as total_queued,
    AVG(score) as avg_score,
    MAX(queued_at) as last_added,
    MIN(queued_at) as oldest
FROM signal_queue
WHERE status = 'waiting';
```

---

## Benefits

### Performance
- ✅ Indexed queries 100x faster than JSON scan
- ✅ Atomic operations via SQLite transactions
- ✅ No file locking conflicts
- ✅ Efficient memory usage (don't load entire file)

### Analytics
- ✅ Time-series analysis (signal quality over time)
- ✅ Regime correlation (BULL vs BEAR performance)
- ✅ Skip reason analysis (optimize filters)
- ✅ Conversion funnel (signal → execution → trade)

### Reliability
- ✅ ACID guarantees (no partial writes)
- ✅ Foreign key constraints (data integrity)
- ✅ Backup/restore with DB tools
- ✅ Point-in-time recovery

### Monitoring
- ✅ Real-time dashboards via SQL queries
- ✅ Historical comparison
- ✅ Performance metrics
- ✅ Alert triggers (e.g., low conversion rate)

---

## Size Estimation

### Current JSON Sizes
- rapid_signals.json: 45KB
- execution_status.json: 820KB (growing)
- signal_queue.json: 2KB

### DB Size Projections (1 year)

**trading_signals:**
- 500 signals/day × 365 days = 182,500 rows
- ~1KB per row (with JSON) = ~178MB/year
- With indexing: ~250MB/year

**execution_history:**
- 500 records/day × 365 days = 182,500 rows
- ~500 bytes per row = ~87MB/year
- With indexing: ~120MB/year

**signal_queue:**
- Max 10 rows active at any time
- ~10KB total (negligible)

**scan_sessions:**
- ~100 scans/day × 365 days = 36,500 rows
- ~500 bytes per row = ~17MB/year
- With indexing: ~25MB/year

**Total estimated:** ~400MB/year (vs 1GB+ if kept in expanding JSON files)

---

## Partitioning Strategy (Future)

For long-term data (2+ years), consider:

1. **Archive old signals** (>90 days):
   ```sql
   CREATE TABLE trading_signals_archive AS
   SELECT * FROM trading_signals
   WHERE signal_time < DATE('now', '-90 days');

   DELETE FROM trading_signals
   WHERE signal_time < DATE('now', '-90 days');
   ```

2. **Archive old execution history** (>180 days):
   Similar approach for execution_history

3. **Separate DB per year:**
   - `trade_history_2025.db`
   - `trade_history_2026.db`
   - Keep current year in `trade_history.db`

---

## Backward Compatibility

During dual-write phase:

1. **JSON files still work** - No breaking changes
2. **Web UI reads both** - Fallback to JSON if DB fails
3. **Engine uses JSON** - DB is shadow copy
4. **Can rollback** - Just disable DB writes

After migration:
- Keep JSON readers as emergency fallback
- Log warnings if JSON used
- Archive old JSON files (don't delete immediately)

---

## Testing Checklist

- [ ] Create all tables successfully
- [ ] Insert sample signal data
- [ ] Query performance < 10ms for common queries
- [ ] Indexes working (EXPLAIN QUERY PLAN)
- [ ] Foreign key constraints enforced
- [ ] JSON field parsing works
- [ ] Timestamp handling correct (UTC vs ET)
- [ ] Dual write consistency (JSON == DB)
- [ ] Repository CRUD operations
- [ ] Web UI displays DB data correctly
- [ ] Engine loads queue from DB on startup
- [ ] No race conditions in concurrent writes

---

## Next Steps

1. **Review this schema** - Feedback/changes needed?
2. **Create models** - TradingSignal, ExecutionRecord, etc.
3. **Create repositories** - SignalRepository, ExecutionRepository, etc.
4. **Write migration SQL** - 001_create_signals_tables.sql
5. **Test locally** - Insert/query sample data
6. **Implement dual write** - auto_trading_engine.py updates
7. **Monitor 1-2 weeks** - Verify consistency
8. **Switch to DB primary** - Update readers
9. **Archive JSON** - Keep as backup
10. **Proceed to Phase 2** - State & monitoring files
