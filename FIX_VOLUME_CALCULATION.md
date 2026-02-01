# FIX: Volume Calculation Issue

**Date**: January 15, 2026
**Issue**: Growth Catalyst Screener rejects all stocks due to abnormally low volume ratio

## 🔍 Root Cause

Yahoo Finance returns incomplete volume data for the most recent trading day:

```
AMZN: Day -2: 41M → Day -1: 5.6M (85% drop!) ❌
TSLA: Day -2: 57M → Day -1: 6.2M (90% drop!) ❌
AAPL: Day -2: 40M → Day -1: 3.7M (90% drop!) ❌
NVDA: Day -2: 160M → Day -1: 159M ✅ (normal)
```

**Why?**
- Market may not be closed yet (partial day data)
- Or data lag from Yahoo Finance
- Or today is a holiday/half-day

## 💡 Solution

**Use the most recent COMPLETE trading day for volume calculation:**

### Code Changes in `growth_catalyst_screener.py`:

```python
# BEFORE (Line 300-303):
# Volume ratio (current vs 20-day average)
avg_volume = volume.rolling(window=20).mean().iloc[-1]
current_volume = volume.iloc[-1]  # ❌ Uses last day (might be partial)
volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

# AFTER:
# Volume ratio - use most recent COMPLETE trading day
# Skip last day if volume is suspiciously low (<20% of recent average)
if len(volume) >= 21:
    recent_avg = volume.iloc[-10:-1].mean()  # Avg of days -10 to -2
    last_volume = volume.iloc[-1]

    # If last day volume is <20% of recent average, it's likely incomplete
    if last_volume < recent_avg * 0.2:
        # Use day -2 instead
        current_volume = volume.iloc[-2]
        avg_volume = volume.iloc[-21:-1].rolling(window=20).mean().iloc[-1]
    else:
        # Last day looks normal, use it
        current_volume = volume.iloc[-1]
        avg_volume = volume.rolling(window=20).mean().iloc[-1]
else:
    # Fallback for short data
    avg_volume = volume.rolling(window=20).mean().iloc[-1]
    current_volume = volume.iloc[-1]

volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
```

### Alternative: Simpler Fix

```python
# Use day -2 if last day volume is abnormally low
avg_volume = volume.rolling(window=20).mean().iloc[-1]
current_volume = volume.iloc[-1]

# Safety check: if current volume is <20% of average, use previous day
if current_volume < avg_volume * 0.2 and len(volume) >= 2:
    current_volume = volume.iloc[-2]
    logger.debug(f"{symbol}: Using previous day volume (last day incomplete)")

volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
```

## 🎯 Expected Impact

**Before Fix:**
- 32/32 stocks rejected (100%)
- Reason: "Volume too low (0.01-0.20 < 0.8)"

**After Fix:**
- Normal volume ratios (0.5-2.0)
- Expected pass rate: 15-25% (based on v4.2 criteria)

## 📝 Implementation Steps

1. **Edit**: `src/screeners/growth_catalyst_screener.py`
2. **Locate**: Line 300-303 (volume ratio calculation)
3. **Replace**: With safety check code above
4. **Test**: Run screener again
5. **Verify**: Volume ratios should be 0.5-2.0 range

## 🔬 Testing

```bash
# After fix, test with:
python test_screener_web_params.py

# Should see:
# - Volume ratios 0.5-2.0 (not 0.01-0.20)
# - Some stocks pass momentum gates
# - Entry Score filter can work properly
```

## ✅ Success Criteria

- [ ] Volume ratios return to normal range (0.5-2.0)
- [ ] At least some stocks pass momentum gates
- [ ] Screener finds 1-10 stocks (not 0)
- [ ] Entry Score ≥55 filter works as expected

---

**Status**: 🟡 Fix identified, pending implementation
**Priority**: 🔴 Critical (blocks all screening)
**Impact**: All stocks currently rejected due to this bug
