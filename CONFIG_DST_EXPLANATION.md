# Config Values & DST Support - Explained ✅

**Date:** 2026-02-21
**Question:** Config hours ใน trading.yaml รองรับ DST หรือไม่?
**Answer:** ✅ **ใช่ รองรับทั้งหมด - ตัวเลขทั้งหมดเป็น ET hours**

---

## Config Values ที่เกี่ยวข้อง

```yaml
# trading.yaml

# -- Market Hours --
market_open_hour: 9         # 09:00 ET (NOT UTC!)
market_open_minute: 30      # 09:30 ET
market_close_hour: 16       # 16:00 ET (NOT UTC!)
market_close_minute: 0      # 16:00 ET
pre_close_minute: 50        # 15:50 ET

# -- Skip Window --
skip_window_enabled: true
skip_window_start_hour: 10  # 10:00 ET (NOT UTC!)
skip_window_start_minute: 0
skip_window_end_hour: 11    # 11:00 ET (NOT UTC!)
skip_window_end_minute: 0
```

---

## คำตอบสั้นๆ

**ตัวเลขทั้งหมดคือ ET hours ไม่ใช่ UTC hours** ✅

```
market_open_hour: 9 = 09:00 ET (ไม่ใช่ 09:00 UTC)
├─ ฤดูหนาว (EST): 09:00 ET = 21:00 Bangkok
└─ ฤดูร้อน (EDT): 09:00 ET = 20:00 Bangkok

skip_window_start_hour: 10 = 10:00 ET (ไม่ใช่ 10:00 UTC)
├─ ฤดูหนาว (EST): 10:00 ET = 22:00 Bangkok
└─ ฤดูร้อน (EDT): 10:00 ET = 21:00 Bangkok
```

**ระบบแปลงเป็นเวลาท้องถิ่นอัตโนมัติตาม DST** ✅

---

## Technical Explanation

### **1. Market Hours Check**

**Code Implementation:**
```python
# auto_trading_engine.py, line 1699-1712
def _is_market_hours(self) -> bool:
    """Check if within market hours"""
    now = self._get_et_time()  # ← Gets current ET time (EST or EDT)

    market_open = now.replace(
        hour=self.MARKET_OPEN_HOUR,    # ← Config value: 9
        minute=self.MARKET_OPEN_MINUTE, # ← Config value: 30
        second=0
    )

    market_close = now.replace(
        hour=self.MARKET_CLOSE_HOUR,   # ← Config value: 16
        minute=self.MARKET_CLOSE_MINUTE,# ← Config value: 0
        second=0
    )

    return market_open <= now <= market_close
```

**How It Works:**

1. **Get current ET time:**
   ```python
   now = self._get_et_time()
   # Winter: 2026-02-21 10:00:00-05:00 EST
   # Summer: 2026-08-15 10:00:00-04:00 EDT
   ```

2. **Replace hour with config value:**
   ```python
   market_open = now.replace(hour=9, minute=30)
   # Winter: 2026-02-21 09:30:00-05:00 EST (preserves EST timezone)
   # Summer: 2026-08-15 09:30:00-04:00 EDT (preserves EDT timezone)
   ```

3. **Compare times:**
   ```python
   return market_open <= now <= market_close
   # Both times are in same timezone → comparison works correctly
   ```

**Key Point:** `now.replace(hour=9)` **preserves the timezone** of `now`
- If `now` is in EST → `market_open` is also in EST
- If `now` is in EDT → `market_open` is also in EDT

---

### **2. Skip Window Check**

**Code Implementation:**
```python
# auto_trading_engine.py, line 1714-1740
def _is_skip_window(self) -> bool:
    """Check if in skip window (default 10:00-11:00 ET)"""
    if not self.SKIP_WINDOW_ENABLED:
        return False

    now = self._get_et_time()  # ← Current ET time

    skip_start = now.replace(
        hour=self.SKIP_WINDOW_START_HOUR,    # ← Config: 10
        minute=self.SKIP_WINDOW_START_MINUTE, # ← Config: 0
        second=0
    )

    skip_end = now.replace(
        hour=self.SKIP_WINDOW_END_HOUR,      # ← Config: 11
        minute=self.SKIP_WINDOW_END_MINUTE,   # ← Config: 0
        second=0
    )

    return skip_start <= now < skip_end
```

**Behavior by Season:**

**Winter (EST):**
```python
now = 2026-02-21 10:30:00-05:00 EST
skip_start = 2026-02-21 10:00:00-05:00 EST  # Config hour: 10
skip_end = 2026-02-21 11:00:00-05:00 EST    # Config hour: 11

# Is 10:30 between 10:00-11:00? YES → Skip window active
# Bangkok time: 22:30 (skip 22:00-23:00)
```

**Summer (EDT):**
```python
now = 2026-08-15 10:30:00-04:00 EDT
skip_start = 2026-08-15 10:00:00-04:00 EDT  # Config hour: 10 (same!)
skip_end = 2026-08-15 11:00:00-04:00 EDT    # Config hour: 11 (same!)

# Is 10:30 between 10:00-11:00? YES → Skip window active
# Bangkok time: 21:30 (skip 21:00-22:00) ← 1 hour earlier
```

**Result:** Skip window ALWAYS 10:00-11:00 ET, but Bangkok time shifts with DST

---

## Config Hours Interpretation

### **ALL hours are ET hours, NOT UTC hours**

| Config Parameter | Value | Meaning | Winter (Bangkok) | Summer (Bangkok) |
|------------------|-------|---------|------------------|------------------|
| `market_open_hour` | 9 | 09:00 ET | 21:00 | 20:00 |
| `market_open_minute` | 30 | 09:30 ET | 21:30 | 20:30 |
| `market_close_hour` | 16 | 16:00 ET | 04:00 (next day) | 03:00 (next day) |
| `skip_window_start_hour` | 10 | 10:00 ET | 22:00 | 21:00 |
| `skip_window_end_hour` | 11 | 11:00 ET | 23:00 | 22:00 |
| `pre_close_minute` | 50 | 15:50 ET | 03:50 (next day) | 02:50 (next day) |

### **Pre-filter Schedule (from earlier verification):**

```yaml
pre_filter_intraday_schedule: [10, 13, 15]  # All ET hours
```

| Hour | Meaning | Winter (Bangkok) | Summer (Bangkok) |
|------|---------|------------------|------------------|
| 10 | 10:45 ET | 22:45 | 21:45 |
| 13 | 13:45 ET | 01:45 (next day) | 00:45 (next day) |
| 15 | 15:45 ET | 03:45 (next day) | 02:45 (next day) |

---

## Why This Design Works

### **1. Timezone Inheritance**

```python
now = self._get_et_time()
# Returns: 2026-02-21 10:00:00-05:00 EST (winter)
#      or: 2026-08-15 10:00:00-04:00 EDT (summer)

new_time = now.replace(hour=9)
# Returns: 2026-02-21 09:00:00-05:00 EST (winter) ← Inherits EST
#      or: 2026-08-15 09:00:00-04:00 EDT (summer) ← Inherits EDT
```

**Key Feature:** `datetime.replace()` preserves the timezone of the original datetime object.

### **2. Consistent ET Time**

**Config always means ET time:**
```
market_open_hour: 9 = "Market opens at 09:00 in New York"
```

**NOT:**
```
market_open_hour: 9 ≠ "Market opens at 09:00 UTC"
```

**Why:** Because `now` is always in ET timezone (from `_get_et_time()`)

### **3. Automatic DST Adjustment**

```python
# Code NEVER checks DST manually
# Code NEVER calculates UTC offsets
# Code NEVER converts timezones manually

# Code ONLY does:
now = self._get_et_time()          # Get ET time
market_open = now.replace(hour=9)  # Set to 09:00 (same timezone)
return market_open <= now          # Compare (both in ET)
```

**pytz handles everything:**
- Detects current date
- Looks up DST rules for US/Eastern
- Applies correct offset (UTC-5 or UTC-4)
- Returns timezone-aware datetime

---

## DST Transition Example

### **March 8, 2026 (EST → EDT)**

**Saturday, March 7 (Last day of EST):**
```yaml
market_open_hour: 9  # Interpreted as 09:00 EST
```
```python
now = self._get_et_time()  # 09:30:00-05:00 EST
market_open = now.replace(hour=9, minute=30)  # 09:30:00-05:00 EST
# Bangkok: 21:30 ✅
```

**Monday, March 9 (First day of EDT):**
```yaml
market_open_hour: 9  # SAME value, but now interpreted as 09:00 EDT
```
```python
now = self._get_et_time()  # 09:30:00-04:00 EDT (notice -04:00)
market_open = now.replace(hour=9, minute=30)  # 09:30:00-04:00 EDT
# Bangkok: 20:30 ✅ (1 hour earlier)
```

**What Changed:**
- ✅ Config value: NO CHANGE (still `9`)
- ✅ ET time: NO CHANGE (still `09:30`)
- ✅ Code: NO CHANGE
- ✅ Bangkok time: CHANGED (21:30 → 20:30)

**Why It Works:**
- `_get_et_time()` returns EDT instead of EST (pytz handles this)
- `now.replace(hour=9)` creates 09:00 EDT (not 09:00 EST)
- Market still opens at 09:30 ET (correct)

---

## Skip Window Example

### **Config:**
```yaml
skip_window_start_hour: 10
skip_window_end_hour: 11
```

### **Behavior:**

**Winter (February 21, 2026):**
```
Skip window: 10:00-11:00 EST
Bangkok equivalent: 22:00-23:00 Bangkok time
```

**Summer (August 15, 2026):**
```
Skip window: 10:00-11:00 EDT (SAME ET hours)
Bangkok equivalent: 21:00-22:00 Bangkok time (1 hour earlier)
```

**For Thai Trader:**
- "I want to avoid trading 10:00-11:00 ET"
- Config: `skip_window_start_hour: 10`
- Winter: System blocks 22:00-23:00 Bangkok
- Summer: System blocks 21:00-22:00 Bangkok
- ✅ Always blocks 10:00-11:00 ET as intended

---

## Common Misunderstandings

### ❌ WRONG: "Config hours are UTC hours"

**NO!** Config hours are **ET hours**.

If you set:
```yaml
market_open_hour: 9
```

This means:
- ✅ "Market opens at 09:00 ET" (New York time)
- ❌ NOT "Market opens at 09:00 UTC"

### ❌ WRONG: "Need different configs for EST vs EDT"

**NO!** Same config works for both.

You do NOT need:
```yaml
# Winter config (WRONG - don't do this)
market_open_hour_est: 9
market_open_hour_edt: 9
```

You only need:
```yaml
# Works for all seasons (CORRECT)
market_open_hour: 9  # Always means 09:00 ET
```

### ❌ WRONG: "Need to manually adjust for DST"

**NO!** System adjusts automatically.

You do NOT need to:
- Change config on March 8
- Restart service on March 8
- Calculate UTC offsets
- Write special DST handling code

System handles everything automatically via `pytz`.

---

## Verification Commands

### **Check Current Interpretation:**

```bash
# Run during market hours to see how config is interpreted
python3 -c "
import sys
sys.path.insert(0, 'src')
from auto_trading_engine import AutoTradingEngine
from config.strategy_config import RapidRotationConfig

config = RapidRotationConfig.from_yaml('config/trading.yaml')
print(f'market_open_hour: {config.market_open_hour}')
print(f'market_close_hour: {config.market_close_hour}')
print(f'skip_window: {config.skip_window_start_hour}:00 - {config.skip_window_end_hour}:00 ET')

from utils.market_hours import get_et_time
et_now = get_et_time()
print(f'Current ET time: {et_now}')
print(f'Timezone: {et_now.tzname()} (offset: {et_now.utcoffset()})')
"

# Output (Winter):
# market_open_hour: 9
# market_close_hour: 16
# skip_window: 10:00 - 11:00 ET
# Current ET time: 2026-02-21 10:30:00-05:00
# Timezone: EST (offset: -5:00:00)

# Output (Summer):
# market_open_hour: 9
# market_close_hour: 16
# skip_window: 10:00 - 11:00 ET
# Current ET time: 2026-08-15 10:30:00-04:00
# Timezone: EDT (offset: -4:00:00)
```

### **Verify Skip Window:**

```bash
python3 -c "
import sys
sys.path.insert(0, 'src')
from utils.market_hours import get_et_time
import pytz

et_now = get_et_time()
skip_start = et_now.replace(hour=10, minute=0, second=0)
skip_end = et_now.replace(hour=11, minute=0, second=0)

bangkok = pytz.timezone('Asia/Bangkok')
print(f'Skip window (ET): {skip_start.time()} - {skip_end.time()}')
print(f'Skip window (Bangkok): {skip_start.astimezone(bangkok).time()} - {skip_end.astimezone(bangkok).time()}')
print(f'Timezone: {et_now.tzname()}')
"

# Output (Winter):
# Skip window (ET): 10:00:00 - 11:00:00
# Skip window (Bangkok): 22:00:00 - 23:00:00
# Timezone: EST

# Output (Summer):
# Skip window (ET): 10:00:00 - 11:00:00
# Skip window (Bangkok): 21:00:00 - 22:00:00
# Timezone: EDT
```

---

## Summary

### **Config Values DST Support: ✅ FULL**

| Config Parameter | Timezone | DST Support | Auto-Adjust |
|------------------|----------|-------------|-------------|
| `market_open_hour` | ET | ✅ Yes | ✅ Yes |
| `market_close_hour` | ET | ✅ Yes | ✅ Yes |
| `skip_window_start_hour` | ET | ✅ Yes | ✅ Yes |
| `skip_window_end_hour` | ET | ✅ Yes | ✅ Yes |
| `pre_filter_intraday_schedule` | ET | ✅ Yes | ✅ Yes |

### **How It Works:**

1. **Config values = ET hours** (not UTC)
2. **Code uses `_get_et_time()`** → Always returns ET time
3. **Code uses `now.replace(hour=X)`** → Creates ET time with hour X
4. **pytz handles DST** → Automatically applies correct offset

### **User Impact:**

**Thai Trader Perspective:**
- Config: `skip_window_start_hour: 10` (10:00 ET)
- Winter: Skip 22:00-23:00 Bangkok time
- Summer: Skip 21:00-22:00 Bangkok time
- ✅ Always skips 10:00-11:00 ET as intended

**Developer Perspective:**
- ✅ Write config in ET hours
- ✅ Never calculate UTC offsets
- ✅ Never write DST logic
- ✅ pytz handles everything

### **DST Transition (March 8, 2026):**

**What Happens:**
- Config values: NO CHANGE ✅
- ET times: NO CHANGE ✅
- Code: NO CHANGE ✅
- Bangkok times: SHIFT 1 hour ✅
- Downtime: ZERO ✅

---

## Conclusion

**คำตอบ: ใช่ รองรับหมด** ✅

```yaml
# Config values ทั้งหมดเป็น ET hours
market_open_hour: 9         # 09:00 ET (รองรับ DST ✅)
market_close_hour: 16       # 16:00 ET (รองรับ DST ✅)
skip_window_start_hour: 10  # 10:00 ET (รองรับ DST ✅)
skip_window_end_hour: 11    # 11:00 ET (รองรับ DST ✅)
```

**ไม่ต้องแก้ไข config เมื่อเปลี่ยน DST** ✅
**ระบบปรับเวลาอัตโนมัติ** ✅
**เวลา ET คงที่ แต่เวลาไทยเปลี่ยน** ✅

---

**🎉 All Config Hours Support DST Automatically! 🎉**
