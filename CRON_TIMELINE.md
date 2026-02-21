# Stock Analyzer - Complete Cron Timeline

**Auto Trading Engine v6.36 - Scheduled Tasks**

Last Updated: 2026-02-21

---

## 📅 Complete Daily Schedule (ET Time)

### Pre-Market Hours (06:00-09:30 ET)

#### 06:00-09:30: Pre-Market Gap Scanner
- **Method:** `_loop_premarket_gap_scan()`
- **Frequency:** Once per day (checks time window)
- **Purpose:** Scan for high-confidence gap opportunities before market open
- **Criteria:**
  - Gap signals with min 80% confidence
  - Must be worth rotating (rotation_benefit check)
  - Conservative stops: 2% SL, capped TP at 5%
- **Position Limit:** Respects max_positions
- **Status:** Active (runs when market closed)

---

### Market Closed Hours (After 16:00 ET)

#### 20:00 ET: Evening Pre-Filter (Full Universe)
- **Method:** `_loop_evening_prefilter()`
- **Frequency:** Once per day
- **Purpose:** Scan full 987-stock universe, rebuild pool from scratch
- **Output:** ~280 quality stocks → `trade_history.db/filtered_stocks`
- **Subprocess:** `python3 src/pre_filter.py evening`
- **Criteria:**
  - Price: $5-$500
  - Volume: >500k avg 20d
  - ATR: >2%
  - SMA20: Price within ±20%
  - Momentum: Not overextended
  - Sector: Optional filtering
- **Runtime:** ~5-10 min for full scan
- **Next Scan:** 09:00 ET next day

---

### Pre-Open Hours (Before 09:30 ET)

#### 09:00 ET: Pre-Open Pre-Filter (Re-validate Pool)
- **Method:** `_loop_pre_open_prefilter()`
- **Frequency:** Once per day
- **Purpose:** Re-validate existing pool (NOT add new stocks)
- **Time Window:** 09:00-09:30 ET only
- **Subprocess:** `python3 src/pre_filter.py pre_open`
- **Output:** Updates pool status in DB
- **Runtime:** ~2-3 min (validates ~280 stocks)
- **Next Scan:** 10:45 ET (intraday refresh)

---

### Market Open Hours (09:30-16:00 ET)

#### 09:35 ET: Morning Scan [DIP]
- **Method:** `_loop_morning_scan()`
- **Frequency:** Once per day
- **Strategy:** Dip-Bounce (mean reversion)
- **Purpose:** Primary signal generator for DIP strategy
- **Actions:**
  1. Wait for market to settle (09:30-09:35 spread wide)
  2. Get fresh VIX tier (NORMAL/SKIP/HIGH/EXTREME)
  3. Run rapid_rotation_screener with VIX-adaptive params
  4. Filter through 4-layer entry protection
  5. Execute top signals (max 2 DIP positions)
- **Entry Protection:**
  - Layer 1: Adaptive timing (gap-based delay 5-20 min)
  - Layer 2: VWAP filter (max 3% above)
  - Layer 3: Chase limit (max 0.8% from signal)
  - Layer 4: Range filter (avoid top 20%)
- **Next Scan:** Continuous (see below)

#### 09:35 ET: Post-Earnings Momentum Scan [PEM]
- **Method:** `_loop_pem_scan()`
- **Frequency:** Once per day
- **Strategy:** Post-Earnings Momentum
- **Purpose:** Catch strong earnings gaps early
- **Time Window:** 09:35 ET only
- **Criteria:**
  - Gap ≥8% (strong move)
  - Volume 3x average (conviction)
  - After earnings report
  - Not already in positions
- **Position Limit:** 1 concurrent (dedicated slot)
- **Exit:** EOD force exit (intraday only)
- **Bypass:** Skips VWAP/timing filters (gap play)
- **Frequency:** <1 trade/month (rare but high quality)

#### 09:45-15:45: Continuous Scan [DIP]
- **Method:** `_loop_continuous_scan()`
- **Frequency:** Adaptive (volatile vs normal)
  - **09:45-11:00 ET:** Every 5 min (volatile window)
  - **11:00-15:45 ET:** Every 15 min (normal)
- **Purpose:** Catch new dip signals throughout day
- **Filters:**
  - Same VIX-adaptive params as morning scan
  - Skip window 10:00-11:00 AM (volatile period)
  - Pre-filter pool (280 stocks)
- **Position Limit:** 2 DIP positions total
- **Cutoff:** Stops at 15:45 (pre-close)

#### 10:00-11:00: SKIP WINDOW ⛔
- **Status:** No trading allowed
- **Reason:** Volatile mid-morning period
  - Options expiry effects
  - Institutional rebalancing
  - Wide spreads
  - False breakouts
- **Impact:** Improves win rate by avoiding bad entries
- **Implementation:** `_is_skip_window()` check in entry filters

#### 10:45 ET: Intraday Pre-Filter Refresh #1
- **Method:** `_loop_intraday_prefilter()` (first call)
- **Purpose:** Refresh pool with new dip candidates since open
- **Pool Source:** Re-run full 987-stock scan (NOT just re-validate)
- **Subprocess:** `python3 src/pre_filter.py evening`
- **Runtime:** ~5-10 min
- **Next Scan:** 13:45 ET

#### 13:45 ET: Intraday Pre-Filter Refresh #2
- **Method:** `_loop_intraday_prefilter()` (second call)
- **Purpose:** Update RSI/momentum for afternoon session
- **Pool Source:** Re-run full 987-stock scan
- **Subprocess:** `python3 src/pre_filter.py evening`
- **Runtime:** ~5-10 min
- **Next Scan:** 15:45 ET

#### Afternoon Scan (Configurable)
- **Method:** `_loop_afternoon_scan()`
- **Default:** Disabled (no specific time in v6.36)
- **Config:** `afternoon_scan_hour`, `afternoon_scan_minute` in trading.yaml
- **Purpose:** Optional second DIP scan (if enabled)
- **Strategy:** Uses afternoon-specific params (more conservative)

#### 15:30 ET: Overnight Gap Scan [OVN]
- **Method:** `_loop_overnight_gap_scan()`
- **Frequency:** Once per day
- **Strategy:** Overnight Gap (gap momentum)
- **Time Window:** 15:30-15:50 ET only (during pre-close)
- **Purpose:** Find stocks closing near high, setup for next-day gap
- **Criteria:**
  - Near-high close (within 2% of HOD)
  - Strong intraday momentum
  - Sector strength
  - NOT overextended
- **Position Limit:** 1 concurrent (dedicated slot)
- **Hold Period:** Next day or 1-3 days
- **Frequency:** 6-10 trades/month (BULL), 3-5/month (BEAR)
- **Bypass:** May bypass some filters (gap play)

#### 15:45 ET: Intraday Pre-Filter Refresh #3
- **Method:** `_loop_intraday_prefilter()` (third call)
- **Purpose:** Final pool refresh for next morning
- **Pool Source:** Re-run full 987-stock scan
- **Subprocess:** `python3 src/pre_filter.py evening`
- **Runtime:** ~5-10 min
- **Ready For:** Next day 09:35 gap scanner + morning scan

#### 15:50-16:00 ET: Pre-Close Check
- **Method:** `pre_close_check()`
- **Frequency:** Continuous during window
- **Purpose:** EOD risk management
- **Actions:**
  1. Force exit PEM positions (intraday only)
  2. Check day trade count (PDT protection)
  3. Trailing stop updates (lock gains)
  4. Position health check
  5. Daily summary prep

---

## 🔄 Continuous Monitoring (All Market Hours)

### Position Monitoring
- **Method:** `monitor_positions()`
- **Frequency:** Every 30 seconds (MONITOR_INTERVAL_SECONDS)
- **Purpose:** Real-time position management
- **Actions:**
  1. Check stop loss triggers
  2. Check take profit triggers
  3. Update trailing stops
  4. Track peak/trough prices
  5. Increment days held
  6. Time exit check (max 7 days)
  7. Loss limit checks (daily/weekly)

### VIX Tier Updates
- **Method:** `_check_fresh_vix()` (called by monitor)
- **Frequency:** Every position check (~30s)
- **Purpose:** React to volatility changes
- **Actions:**
  - Check VIX level (< 20, 20-24, 24-38, > 38)
  - Check VIX direction (falling/rising) for SKIP tier
  - Update strategy params (NORMAL/SKIP/HIGH/EXTREME)
  - EXTREME tier (VIX > 38): Close all positions immediately

### Sector Regime Updates
- **Method:** `_update_sector_regime()` (called by scans)
- **Frequency:** Before each scan
- **Purpose:** Detect BULL/BEAR market
- **Source:** SPY performance (5d, 20d momentum)
- **Impact:** Adjusts min_score threshold
  - BULL: min_score = 85-90
  - BEAR: min_score = 70-75 (lower bar)

### Position Reconciliation
- **Method:** `_reconcile_positions()`
- **Frequency:** Every loop iteration (market open)
- **Purpose:** Sync broker positions with local state
- **Actions:**
  1. Get broker positions via API
  2. Compare with local DB
  3. Add missing positions
  4. Remove closed positions
  5. Update quantities

### Heartbeat
- **Method:** `_write_heartbeat()`
- **Frequency:** Every loop iteration (~30s)
- **File:** `data/heartbeat.json`
- **Purpose:** External watchdog monitoring
- **Data:** state, positions count, running flag

---

## 📊 On-Demand Tasks (Triggered)

### Pre-Filter Refresh (Pool < 200)
- **Trigger:** `rapid_rotation_screener.py` detects pool_size < 200
- **Method:** `_trigger_prefilter_refresh()` (detached subprocess)
- **Subprocess:** `python3 src/pre_filter.py evening`
- **Purpose:** Emergency pool rebuild (pool shrinks from re-validation)
- **Frequency:** As needed (typically 1-2x per week)

### Daily Summary
- **Method:** `daily_summary()`
- **Trigger:** Engine shutdown or midnight
- **Purpose:** Performance summary log
- **Data:** Trades, win rate, P&L, positions

### Emergency Position Close
- **Trigger:** VIX > 38 (EXTREME tier)
- **Method:** Close all positions immediately
- **Purpose:** Crisis protection (COVID, flash crash)
- **Historical:** Limited COVID DD to 14.9% vs market -35%

---

## 🛡️ Safety Checks (Continuous)

### PDT Protection
- **Check:** Before every entry
- **Limits:**
  - Reserve 1 day trade (never use all 3)
  - Flagged accounts: Overnight holds only
  - Day trade counter tracking

### Loss Limits
- **Daily:** 5.0% of equity
- **Weekly:** 7.0% of equity
- **Check:** Before every entry + continuous monitoring
- **Action:** Block new entries if exceeded

### Position Limits
- **DIP:** Max 2 positions
- **OVN:** Max 1 position (dedicated slot)
- **PEM:** Max 1 position (dedicated slot)
- **Total:** Max 4 positions combined
- **Check:** Before every entry

### Sector Diversification
- **Limit:** Max 2 positions per sector (NORMAL tier)
- **Limit:** Max 1 position per sector (HIGH tier)
- **Check:** Before every entry

---

## 📈 Timeline Summary (Market Day)

```
06:00 ─┬─ Pre-Market Gap Scan (06:00-09:30)
       │
09:00 ─┼─ Pre-Open Pre-Filter (re-validate pool)
       │
09:30 ─┼─ Market Opens
       │
09:35 ─┼─ Morning Scan [DIP] + PEM Scan
       │
09:45 ─┼─ Continuous Scan starts (5 min interval)
       │
10:00 ─┼─ SKIP WINDOW START ⛔
       │
10:45 ─┼─ Intraday Pre-Filter #1 (fresh pool)
       │
11:00 ─┼─ SKIP WINDOW END, Continuous Scan (15 min interval)
       │
13:45 ─┼─ Intraday Pre-Filter #2 (RSI/momentum update)
       │
15:30 ─┼─ Overnight Gap Scan [OVN]
       │
15:45 ─┼─ Intraday Pre-Filter #3 (next-day prep)
       │   Continuous Scan stops
       │
15:50 ─┼─ Pre-Close Check starts
       │
16:00 ─┼─ Market Closes
       │
20:00 ─┴─ Evening Pre-Filter (full 987-stock scan)

Continuous: Position monitoring (every 30s)
            VIX updates (every 30s)
            Heartbeat (every 30s)
```

---

## 🔧 Configuration Variables

### Scan Timing (auto_trading_engine.py)
```python
OVERNIGHT_GAP_SCAN_HOUR = 15        # 15:30 ET
OVERNIGHT_GAP_SCAN_MINUTE = 30

PEM_SCAN_HOUR = 9                   # 09:35 ET
PEM_SCAN_MINUTE = 35

AFTERNOON_SCAN_HOUR = 13            # Configurable (disabled by default)
AFTERNOON_SCAN_MINUTE = 0

CONTINUOUS_SCAN_VOLATILE_INTERVAL = 5      # 09:45-11:00 (5 min)
CONTINUOUS_SCAN_INTERVAL_MINUTES = 15      # 11:00-15:45 (15 min)
CONTINUOUS_SCAN_VOLATILE_END_HOUR = 11     # Switch to normal interval

MONITOR_INTERVAL_SECONDS = 30              # Position monitoring
```

### Pre-Filter Schedule (hardcoded in _loop methods)
```python
# Evening: 20:00 ET (full scan)
# Pre-open: 09:00 ET (re-validate)
# Intraday: 10:45, 13:45, 15:45 ET (fresh scans)
```

### Skip Window (trading.yaml)
```yaml
skip_window_enabled: true
skip_window_start_hour: 10    # 10:00 AM ET
skip_window_end_hour: 11      # 11:00 AM ET
```

---

## 📝 Implementation Notes

### Pre-Filter Pool Size Evolution
**Issue:** Intraday pre-filter was using `pre_open_scan()` which only re-validates existing pool.
- Pool starts: 280 stocks (evening scan)
- After re-validation: ~200 stocks (some fail criteria)
- After multiple re-validations: <200 stocks (pool shrinks)

**Fix (v6.27):** All intraday refreshes now use full `evening_scan()` (987 stocks).
- Pool always rebuilds from full universe
- Maintains ~280 quality stocks throughout day

### Subprocess Architecture
All pre-filter scans run as detached subprocess:
```python
subprocess.Popen(['python3', 'src/pre_filter.py', 'evening'], ...)
```
**Benefits:**
- Non-blocking (engine continues)
- Isolated memory space
- Clean error handling
- Background processing

**Gotcha:** Must pass `evening` or `pre_open` arg (no arg = crash!)

### Database Writes
**Engine writes DB** via scoped sync:
```python
repo.sync_positions_scoped(positions, source_filter=['dip_bounce', 'overnight_gap', 'pem'])
```
- Protects rapid_trader positions (different source)
- DELETE only specified sources
- INSERT OR REPLACE for current positions

**position_manager.save()** is now no-op (engine owns all writes).

### Strategy Tags
All positions tagged with source:
- `[DIP]` - Dip-Bounce Strategy
- `[OVN]` - Overnight Gap Strategy
- `[PEM]` - Post-Earnings Momentum
- `rapid_trader` - Rapid Trader (separate system)

---

## ✅ Verification Checklist

- [ ] Evening pre-filter runs at 20:00 ET (check logs)
- [ ] Pre-open pre-filter runs at 09:00 ET
- [ ] Morning scan fires at 09:35 ET (once per day)
- [ ] PEM scan fires at 09:35 ET (once per day)
- [ ] Continuous scan respects skip window (10:00-11:00)
- [ ] Continuous scan uses 5 min (09:45-11:00) and 15 min (11:00-15:45)
- [ ] Intraday pre-filter runs at 10:45, 13:45, 15:45 ET
- [ ] OVN scan fires at 15:30 ET (only during 15:30-15:50 window)
- [ ] Pre-close check runs during 15:50-16:00 ET
- [ ] Position monitoring every 30s
- [ ] VIX updates every 30s
- [ ] Heartbeat writes every 30s
- [ ] Pool size stays ~280 (check `data/pre_filter_status.json`)
- [ ] Database sync working (check `trade_history.db/active_positions`)

---

**System Version:** v6.36
**Database Migration:** Complete (Phases 1, 2, 4)
**Status:** Production Ready ✅
**Last Review:** 2026-02-21
