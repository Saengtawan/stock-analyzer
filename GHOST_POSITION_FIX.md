# Ghost Position Fix - v6.31
**Date:** 2026-02-19
**Issue:** KHC ghost position (58 shares @ $24.05, not tracked in DB)

---

## 🔍 Root Cause Analysis

### What Happened:
```
11:30:38 EST - System placed limit buy order for KHC @ $24.055
11:30:40 EST - Waited 2 seconds → Order NOT FILLED → Logged as SKIP
11:30:41 EST - System moved to next signal
11:31:00 EST - KHC order actually filled in Alpaca (22 seconds later)
11:31:23 EST - TradingSafety auto-added SL @ $23.44
RESULT:     - Position exists in Alpaca ✅
            - SL order exists ✅
            - But active_positions DB never updated ❌
```

### Technical Root Cause:
1. **Insufficient wait time:** System only waits 2 seconds for order fill
2. **Limit orders can be slow:** May take 10-30 seconds to fill
3. **Safety system creates SL:** TradingSafety detects unprotected position
4. **But DB never updated:** ManagedPosition never created

### Code Location:
- **File:** `src/auto_trading_engine.py`
- **Method:** `_exec_place_order()` lines 3995-4011
- **Bug:** `time.sleep(2)` only - single check, no retry loop

---

## ✅ Fix Applied - v6.31

### Changes Made:

**Before (v6.30):**
```python
if buy_order.status != 'filled':
    time.sleep(2)  # Single 2-second wait
    buy_order = self.broker.get_order(buy_order.id)
```

**After (v6.31):**
```python
if buy_order.status != 'filled':
    for _ in range(15):  # Up to 30 seconds (15 x 2s)
        time.sleep(2)
        buy_order = self.broker.get_order(buy_order.id)
        if buy_order and buy_order.status == 'filled':
            break  # Exit loop when filled
```

### Impact:
- ✅ Prevents premature ORDER_NOT_FILLED logs
- ✅ Waits up to 30 seconds for limit orders to fill
- ✅ Matches buy_with_stop_loss() behavior (10s wait)
- ✅ No performance penalty (exits early when filled)
- ⚠️ Adds max 30s delay per order (acceptable trade-off)

---

## 🔧 Immediate Action - Close KHC Ghost

### When to Run:
**Tomorrow (Feb 19) when market opens at 9:30 AM EST**

### How to Close:
```bash
cd /home/saengtawan/work/project/cc/stock-analyzer
python3 scripts/close_khc_ghost.py
```

### What the Script Does:
1. Checks if KHC position still exists
2. Cancels existing SL order @ $23.44
3. Closes position with market order
4. Reports final P&L

### Expected Result:
```
Position: 58 shares @ $24.05
Current:  ~$23.95 (after-hours)
P&L:      ~-$5.80 (-0.42%)
```

### If Script Fails:
1. Market might be closed → wait until open
2. Cancel stuck → try again in 5 minutes
3. Manual close via Alpaca web UI as backup

---

## 🚀 Testing the Fix

### Test Plan:
1. **Deploy:** Restart engine with v6.31
2. **Monitor:** Watch next 5-10 limit order executions
3. **Verify:** Check logs for "waiting for fill" messages
4. **Confirm:** No more ORDER_NOT_FILLED for orders that actually fill

### Log Messages to Watch For:
```
✅ Good: "Waiting for fill... (attempt 3/15)"
✅ Good: "Order filled after 8 seconds"
❌ Bad:  "ORDER_NOT_FILLED" followed by SL creation
```

---

## 📊 Prevention Checklist

### Monitoring:
- [ ] Check for ghost positions daily (reconcile log)
- [ ] Alert on "missing SL added" events (sign of ghost fill)
- [ ] Track ORDER_NOT_FILLED count (should decrease)

### Code Quality:
- [x] Increase wait time 2s → 30s (v6.31) ✅
- [x] Add retry loop instead of single check ✅
- [ ] Add webhook for order fill notifications (future)
- [ ] Add background order status checker (future)

### Documentation:
- [x] Root cause analysis ✅
- [x] Fix implementation ✅
- [x] Close ghost position script ✅
- [x] Prevention guidelines ✅

---

## 🎯 Success Criteria

**Fix is successful if:**
1. ✅ No new ghost positions after v6.31 deployment
2. ✅ ORDER_NOT_FILLED logs decrease by >80%
3. ✅ All filled orders have matching DB positions
4. ✅ No "missing SL added" warnings for fresh orders

**Timeline:**
- **Immediate:** Deploy v6.31
- **Tomorrow:** Close KHC ghost position
- **Week 1:** Monitor for new ghost positions
- **Week 2:** Declare fix successful if no issues

---

## 📝 Related Files

- **Fix:** `src/auto_trading_engine.py` (v6.31)
- **Close Script:** `scripts/close_khc_ghost.py`
- **Safety System:** `src/trading_safety.py` (auto SL logic)
- **Trade Log:** `data/trade_history.db` (KHC SKIP record)

---

## 🔗 GitHub Commit

**Commit:** e796fd1
**Message:** "v6.31: Fix ghost position bug - increase order fill wait time 2s→30s"
**Date:** 2026-02-19
