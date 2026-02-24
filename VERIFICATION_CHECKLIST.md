# System Verification Checklist
**Created:** 2026-02-24 (After v6.43 fixes)

## 🎯 What We Fixed Today
- [x] Duplicate trade entries (KHC, FAST)
- [x] Time exit bug (shares lock)
- [x] Fill price bug (stop vs actual)
- [x] Heartbeat error
- [x] PDT tracking

## ⚠️ Things to Watch (Next 7 Days)

### Day 1-2: Critical Monitoring

**Every 2 Hours (During Market Hours):**
```bash
# Run this command:
bash /tmp/monitor_system.sh

# Check for:
1. ✅ Engine/Web app running
2. ❌ No errors in logs
3. ❌ No duplicate trades
4. ✅ VIX tier correct
```

**Red Flags:**
- [ ] Duplicate SELL entries for same symbol
- [ ] Time exit not triggering (days_held > 7)
- [ ] Fill price = stop price (should be different)
- [ ] Position stuck with "insufficient qty"

---

### Day 3-7: Watch for Patterns

**Daily Check (End of Day):**
```sql
-- Check for duplicates
SELECT symbol, COUNT(*) FROM trades 
WHERE date(timestamp) = date('now') AND action='SELL'
GROUP BY symbol HAVING COUNT(*) > 1;

-- Check time exits
SELECT symbol, days_held, pnl_pct FROM trades
WHERE reason = 'TIME_EXIT' AND date(timestamp) = date('now');

-- Check fill prices
SELECT symbol, price, entry_price, 
       ABS(price - entry_price) as diff
FROM trades 
WHERE action='SELL' AND date(timestamp) = date('now');
```

**Expected:**
- [ ] No duplicates
- [ ] Time exits trigger at day 7-10
- [ ] Fill prices reasonable (not exactly at stop)

---

## ✅ Signs Everything is Working

### 1. Time Exit Works
```
Position held 7+ days → Auto-sells next market day
Log shows: "⏰ {symbol} held 7 days - time exit"
```

### 2. No Duplicates
```
Each position has exactly 1 SELL entry
No phantom trades
```

### 3. Fill Price Accurate
```
Sell price ≠ Stop price (usually 0.1-0.5% different)
P&L calculation correct
```

---

## 🚨 If Something Goes Wrong

### Duplicate Entries Appear Again
```sql
-- Quick fix:
DELETE FROM trades WHERE id = 'tr_DUPLICATE_ID';

-- Then investigate:
grep "duplicate" logs/auto_trading_engine.log
```

### Time Exit Not Working
```bash
# Check log for:
grep "time exit\|TIME_EXIT" nohup_engine_v643_fixed.out

# Look for:
- "insufficient qty available" → shares still locked
- "shares released after Ns" → should be 1-3s
```

### Fill Price Wrong
```bash
# Check if using stop_price instead of filled_avg_price
grep "SL_FILLED_AT_ALPACA" nohup_engine_v643_fixed.out | tail -5
```

---

## 📊 Success Metrics (Week 1)

- [ ] 0 duplicate trades
- [ ] All time exits trigger correctly
- [ ] All fill prices accurate
- [ ] No "shares locked" errors
- [ ] VIX tier changes detected within 60s

---

## 🔧 Emergency Rollback

**If major issues:**
```bash
# 1. Stop engine
kill $(pgrep -f auto_trading_engine)

# 2. Check last good commit
git log --oneline -5

# 3. Rollback if needed
# git checkout <last-good-commit>

# 4. Restart
nohup python3 src/auto_trading_engine.py > nohup_rollback.out 2>&1 &
```

---

## 📝 Daily Log Template

```
Date: ______
Market: OPEN/CLOSED
VIX: ____ (tier: ____)

Checks:
[ ] Engine running
[ ] No errors
[ ] No duplicates
[ ] Time exits working
[ ] Fill prices accurate

Issues: _______________
Actions: ______________
```

---

## 🎯 After 7 Days

If all checks pass:
- ✅ System verified stable
- ✅ Can reduce monitoring to daily checks
- ✅ Bugs are truly fixed

If issues persist:
- ⚠️ Need deeper investigation
- ⚠️ May need architectural changes
- ⚠️ Consider professional audit
