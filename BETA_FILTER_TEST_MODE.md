# Beta Filter - Test Mode Active (v6.32)

**Status:** 🧪 Testing (Log Only Mode)
**Started:** 2026-02-19
**Duration:** 1 week minimum
**Goal:** Validate filter before enforcing

---

## ✅ What's Deployed

### Filter Logic:
```
Stock PASSES if ANY of:
✅ Beta >= 0.5 (moderate volatility)
✅ ATR >= 5% (high volatility)
✅ In CORE_STOCKS list (curated high-beta)

Stock FAILS if:
❌ Beta < 0.5 AND ATR < 5%
```

### Test Mode Behavior:
- ✅ Logs would-be rejections to `data/trade_history.db`
- ✅ Reason: `BETA_FILTER_TEST`
- ⚠️ **DOES NOT actually reject** (allows execution)
- 📊 Can analyze impact without affecting trades

---

## 📊 Test Results (Validation)

### Static Test (test_beta_filter.py):
```
✅ KHC rejected    (beta 0.047, ATR 3.2%) ← Would prevent ghost position!
✅ PG rejected     (beta 0.120, ATR 2.8%)
✅ KO rejected     (beta 0.210, ATR 3.2%)
✅ T rejected      (beta 0.330, ATR 2.5%)

✅ NVDA passed     (beta 2.314)
✅ TSLA passed     (beta 1.887)
✅ PLTR passed     (beta 1.430)
✅ XOM passed      (ATR 5.2%)

Result: 4 passed, 4 rejected ✅ Filter working correctly
```

### Live Test (yfinance current data):
- KHC: beta 0.047 → **REJECT** ✅ (exact case we want to prevent!)
- NVDA: beta 2.314 → **PASS** ✅
- TSLA: beta 1.887 → **PASS** ✅
- PG: beta 0.380 → **REJECT** ✅

---

## 📋 Monitoring Checklist (1 Week)

### Daily Tasks:

**1. Check Log Rejections:**
```sql
-- Query trade_history.db for test rejections
SELECT
    date,
    symbol,
    price,
    signal_score,
    full_data->>'$.filters.beta_volatility.reason' as beta_reason
FROM trades
WHERE reason = 'BETA_FILTER_TEST'
ORDER BY date DESC;
```

**2. Count Rejections:**
```bash
sqlite3 data/trade_history.db "SELECT COUNT(*) FROM trades WHERE reason='BETA_FILTER_TEST'"
```

**3. Analyze Rejected Stocks:**
- Are they actually low-volatility? (check beta/ATR)
- Would we have regretted buying them?
- Any false positives (good stocks rejected)?

### Log Messages to Watch For:
```
⚠️ BETA FILTER (log-only): KHC low_volatility (beta=0.047<0.5, atr=3.19%<5.0%) - WOULD REJECT but allowing for testing
```

---

## 📊 Analysis Questions

After 1 week of testing, answer these:

### 1. Rejection Count:
- [ ] Total signals generated: ____
- [ ] BETA_FILTER_TEST rejections: ____
- [ ] Rejection rate: ____% (expect 5-10%)

### 2. Rejection Quality:
- [ ] Were rejected stocks actually low-volatility? (check beta/ATR)
- [ ] Would we regret buying them? (check if they moved slowly)
- [ ] Any good opportunities missed? (false positives)

### 3. Impact Estimation:
- [ ] Average score of rejected stocks: ____
- [ ] Average beta of rejected stocks: ____
- [ ] Sectors most affected: ____

### 4. False Positives Check:
```
SELECT symbol, signal_score, full_data->>'$.beta' as beta, full_data->>'$.atr_pct' as atr
FROM trades
WHERE reason='BETA_FILTER_TEST' AND signal_score >= 90
ORDER BY signal_score DESC;
```
- [ ] High-score rejections (>90): ____
- [ ] Were these actually good stocks? ____

---

## ✅ Success Criteria (Before Enforcing)

**Pass all 4 checks:**
1. ✅ Rejection rate 5-15% (not too high, not zero)
2. ✅ >90% of rejections are correctly low-volatility stocks
3. ✅ <10% false positives (good stocks wrongly rejected)
4. ✅ No high-quality signals (score >120) rejected wrongly

**If ANY fails → adjust thresholds before enforcing**

---

## 🚀 Enforcement (After Validation)

### When to Enable:
- ✅ After 1 week minimum
- ✅ After passing all 4 success criteria
- ✅ After analyzing rejected stocks
- ✅ After confirming no false positives

### How to Enable:
```yaml
# config/trading.yaml
beta_filter_log_only: false  # Change true → false
```

### What Changes:
- ❌ Filter actually **rejects** low-volatility stocks
- 📊 Logs with reason: `BETA_FILTER` (not TEST)
- 🎯 Expected impact: -5-10% trades, +2-4% win rate

---

## 📁 Monitoring Tools

### 1. Test Script:
```bash
python3 test_beta_filter.py
```
- Tests filter logic with known stocks
- Verifies config loaded correctly
- Live beta data from yfinance

### 2. Query Rejections:
```bash
sqlite3 data/trade_history.db "
SELECT symbol, date, signal_score,
       full_data->>'$.filters.beta_volatility.reason' as reason
FROM trades
WHERE reason='BETA_FILTER_TEST'
ORDER BY date DESC
LIMIT 20;
"
```

### 3. Close KHC Script:
```bash
# Tomorrow (Feb 19) when market opens
python3 scripts/close_khc_ghost.py
```
- Closes the ghost position that triggered this whole investigation
- Expected P&L: ~-$5.80 (-0.42%)

---

## 📝 Decision Log

| Date | Event | Decision |
|------|-------|----------|
| 2026-02-19 | Deployed v6.32 test mode | Log only, don't reject |
| 2026-02-26 | 1 week test complete | [TBD: Enable or adjust] |

---

## 🎯 Expected Outcome

**After enforcement (if test validates):**
- ✅ No more KHC-type ghost positions
- ✅ Trade count: -5-10% (acceptable reduction)
- ✅ Win rate: +2-4% (better stock selection)
- ✅ Avg P&L per trade: +0.2-0.5% (faster movers)
- ✅ Avg hold time: -0.5-1 day (quicker exits)

**If test shows problems:**
- Adjust thresholds (e.g., min_beta 0.5 → 0.4)
- Add sector exceptions (e.g., allow Energy beta 0.4)
- Disable if too many false positives

---

## 📞 Support

**Files:**
- Config: `config/trading.yaml` (beta_filter_* settings)
- Code: `src/auto_trading_engine.py` (_check_beta_volatility)
- Test: `test_beta_filter.py`
- Proposal: `BETA_FILTER_PROPOSAL.md` (full spec)

**Questions:**
1. Why beta 0.5? → Empirical: <0.5 too slow for swing trading
2. Why ATR 5%? → Alternative metric for volatility
3. Why both criteria? → Some defensive stocks (XOM) have high ATR during volatility
4. Why log-only first? → Safety: validate before enforcing

---

**Ready to Monitor!** 🚀

Check logs daily, analyze after 1 week, then decide: enforce or adjust.
