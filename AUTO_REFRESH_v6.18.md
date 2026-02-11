# Pre-filter Auto-Refresh Feature v6.18

**Date:** 2026-02-11
**Status:** ✅ IMPLEMENTED & ACTIVE
**Purpose:** Auto-refresh pre-filtered pool when it drops below threshold

---

## 🎯 Problem Solved

**Before:**
```
Buy Signals Pool: 79 stocks
Threshold: 200 stocks minimum
Status: ❌ Manual refresh required
```

**After:**
```
Buy Signals Pool: 212 stocks
Threshold: 200 stocks minimum
Status: ✅ Auto-refreshes when low
```

---

## 🚀 Feature Overview

### Automatic Pool Monitoring

The system now **continuously monitors** the pre-filtered pool size and automatically triggers a refresh when:

1. **Pool Size** < 200 stocks (configurable)
2. **Pool File** doesn't exist (initial setup)
3. **Zero Signals** for 3 consecutive scans (future enhancement)

### Smart Safeguards

- **Daily Limit:** Max 6 refreshes per day (prevents excessive API usage)
- **Background Execution:** Non-blocking (doesn't slow down trading)
- **Date Reset:** Counter resets daily at midnight

---

## ⚙️ Configuration

**File:** `config/trading.yaml`

```yaml
# Pre-Filter Auto-Refresh (v6.18)
pre_filter_on_demand_enabled: true       # Enable auto-refresh
pre_filter_on_demand_min_pool: 200       # Refresh if pool < 200
pre_filter_on_demand_zero_signals: 3     # Refresh after N scans with 0 signals
pre_filter_intraday_enabled: true        # Enable scheduled refresh (future)
pre_filter_intraday_schedule: [11, 13]   # Hours to refresh (future)
pre_filter_max_per_day: 6                # Max refreshes per day (safety limit)
```

### Recommended Settings

**Default (Balanced):**
```yaml
pre_filter_on_demand_min_pool: 200  # Good balance
pre_filter_max_per_day: 6           # Prevents runaway refreshes
```

**Aggressive (More Fresh):**
```yaml
pre_filter_on_demand_min_pool: 300  # Higher threshold
pre_filter_max_per_day: 10          # Allow more refreshes
```

**Conservative (Less Refreshes):**
```yaml
pre_filter_on_demand_min_pool: 100  # Lower threshold
pre_filter_max_per_day: 3           # Fewer refreshes
```

---

## 📊 How It Works

### Trigger Flow

```
Scan Start
    ↓
generate_universe() called
    ↓
_check_prefilter_pool_health()
    ↓
Load data/pre_filtered.json
    ↓
Count stocks
    ↓
If < 200 → _trigger_prefilter_refresh()
    ↓
Run src/pre_filter.py in background
    ↓
2-3 minutes later → New pool ready (400-600 stocks)
    ↓
Next scan uses refreshed pool
```

### Background Process

**Command:** `python3 src/pre_filter.py`

**Runtime:** 2-3 minutes
**Output:** `data/pre_filtered.json` (400-600 stocks)
**Logging:** Background process logs to its own stdout

---

## 🧪 Testing

### Manual Test

```bash
python3 test_pool_autorefresh.py
```

**Expected Output:**
```
📊 Current pool size: 212
   Min threshold: 200
   ✅ Pool is HEALTHY (212 >= 200)
   No refresh needed
```

### Simulate Low Pool

```bash
# Backup current pool
cp data/pre_filtered.json data/pre_filtered.json.backup

# Create small pool (force trigger)
echo '{"generated_at":"2026-02-11T00:00:00","stocks":{}}' > data/pre_filtered.json

# Run test
python3 test_pool_autorefresh.py

# Expected:
# ⚠️ Pool low: 0 < 200 → Triggering refresh
# 🔄 Pre-filter refresh triggered (reason: low_pool_0, count: 1/6)

# Restore backup
mv data/pre_filtered.json.backup data/pre_filtered.json
```

---

## 📈 Monitoring

### Check Pool Status

```bash
# View current pool size
python3 -c "import json; print(f'Pool: {len(json.load(open(\"data/pre_filtered.json\")).get(\"stocks\", {}))} stocks')"
```

### Check Refresh Logs

```bash
# Real-time monitoring
tail -f nohup.out | grep -E "Pool|refresh|Pre-filter"

# Check daily refresh count
grep "Pre-filter refresh triggered" nohup.out | grep "$(date +%Y-%m-%d)" | wc -l
```

### Expected Log Messages

**Pool Healthy:**
```
(No messages - silent when pool is good)
```

**Pool Low (Triggered):**
```
⚠️ Pool low: 150 < 200 → Triggering refresh
🔄 Pre-filter refresh triggered (reason: low_pool_150, count: 1/6)
```

**Daily Limit Hit:**
```
Pre-filter refresh limit reached (6/6)
```

---

## 🔧 Implementation Details

### Files Modified

**1. src/config/strategy_config.py**
- Added 6 new config fields
- Added to rapid_rotation_keys
- Set defaults in __post_init__

**2. src/screeners/rapid_rotation_screener.py**
- Added tracking variables in __init__:
  - `_prefilter_refresh_count`
  - `_prefilter_last_refresh_date`
  - `_prefilter_zero_signal_count`

- Added 2 new methods:
  - `_check_prefilter_pool_health()` - Check pool size
  - `_trigger_prefilter_refresh()` - Run refresh

- Integrated in `generate_universe()`:
  - Calls `_check_prefilter_pool_health()` at start

### Code Locations

**Health Check (line ~359):**
```python
def _check_prefilter_pool_health(self) -> bool:
    """Check if pool needs refresh"""
    # Check daily limit
    # Load pool file
    # Compare size vs threshold
    # Trigger if needed
```

**Trigger Refresh (line ~395):**
```python
def _trigger_prefilter_refresh(self, reason: str) -> bool:
    """Run pre_filter.py in background"""
    # Use subprocess.Popen with detach
    # Increment counter
    # Log trigger
```

---

## ❓ FAQ

**Q: Pool shows 79 but test says 212?**
A: Pool was refreshed recently (2026-02-11 21:05). Check file timestamp.

**Q: How often does it check pool health?**
A: Every scan (morning + afternoon = 2-3x per day normally)

**Q: What if refresh fails?**
A: Falls back to AI universe → cached AI → static fallback (graceful degradation)

**Q: Does it slow down scanning?**
A: No - refresh runs in background, check is < 1ms

**Q: Can I disable it?**
A: Yes - set `pre_filter_on_demand_enabled: false` in config

**Q: What triggers refresh besides low pool?**
A: Currently only low pool. Zero signals feature is planned for v6.19.

---

## 🎓 Expected Behavior

### Normal Operation

```
Pool starts: 400-600 stocks
Day 1-7: Pool gradually shrinks as stocks get filtered out
Day 8: Pool hits 180 stocks
Auto-refresh triggers → New pool 400-600 stocks
Cycle repeats
```

### Edge Cases

**Multiple scans in short time:**
- Only triggers once (tracks last trigger)
- Respects daily limit (6 max)

**Pool file deleted:**
- Detected as "not exists"
- Triggers initial refresh

**Background refresh fails:**
- Logged as error
- Next scan will retry
- Falls back to other universe sources

---

## ✅ Production Status

**Commit:** e39df62
**Deployed:** 2026-02-11 22:41
**Running:** Yes (PID 1064482)

**Verified:**
- ✅ Config loaded correctly
- ✅ Screener initializes with tracking vars
- ✅ Pool health check integrated
- ✅ Trigger mechanism works
- ✅ Background process launches

**Current Pool:** 212 stocks (healthy)
**Last Refresh:** 2026-02-11 21:05:40
**Refresh Count Today:** 0/6

---

**Next:** Monitor over next few days to verify triggers when pool drops below 200.
