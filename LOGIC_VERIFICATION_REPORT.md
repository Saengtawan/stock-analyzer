# Logic Verification Report - Growth Catalyst vs Backtest
**Date:** 2025-12-26
**Status:** ⚠️ **MISMATCHES FOUND**

---

## 🔍 Executive Summary

**CRITICAL FINDINGS:**
1. ❌ **Timeframe Mismatch**: Implementation uses 14 days, but we discussed "30-Day Growth Catalyst v2.0"
2. ⚠️ **Relaxed Filters**: Current filters are MORE PERMISSIVE than backtest v7.1
3. ⚠️ **Hybrid Logic**: Code mixes v7.1 (30-day) and v8.0 (14-day) filters
4. ❌ **Exit Rules Not Backtested**: No backtest data for current exit parameters

---

## 📊 Backtest Versions vs Current Implementation

### Version Timeline
```
v7.1 (30-day)          v8.0 (14-day)           CURRENT IMPLEMENTATION
---------------        ---------------         ---------------------
Target: 5% in 30d  →   Target: 5% in 14d   →   Target: 5% in 14d ✅
Win Rate: 100%         Win Rate: 88.9%         Win Rate: ???

ENTRY FILTERS:         ENTRY FILTERS:          ENTRY FILTERS:
- Beta 0.8-2.0         - RSI > 49              - Beta 0.8-2.0 ✅
- Vol > 25%            - Momentum 7d > 3.5%    - Vol > 20% ⚠️ RELAXED
- RS > 0%              - RS 14d > 1.9%         - RS > -3% ⚠️ RELAXED
- Sector > 40          - MA20 dist > -2.8%     - Sector > 30 ⚠️ RELAXED
- Valuation > 20                               - Valuation > 20 ✅
- Inverted catalyst                            - Inverted catalyst ✅
                                                + RSI > 49 ✅
                                                + Momentum 7d > 3.5% ✅
                                                + RS 14d > 1.9% ✅
                                                + MA20 dist > -2.8% ✅

EXIT RULES:            EXIT RULES:             EXIT RULES:
(not specified)        (not specified)         - Hard stop: -6%
                                                - Trailing: -3%
                                                - Time: 10 days
                                                - Filter score ≤1
                                                - Regime: BEAR exit
```

---

## ⚠️ CRITICAL MISMATCHES

### 1. Timeframe Confusion ❌
**Backtest v7.1:**
- Timeframe: **30 days**
- Target: 5% in 30 days
- Win Rate: **100% (6/6 stocks)**

**Current Implementation:**
- Timeframe: **14 days** (Line 70 in growth_catalyst_screener.py)
- Comment says "14-Day Growth Catalyst Screener v8.0"
- Default parameter: `timeframe_days: int = 14`

**Issue:**
- User asked for "30-Day Growth Catalyst v2.0"
- But code implements 14-day version
- **Different timeframe = different expected results!**

**Recommendation:**
- Decide: 14-day or 30-day strategy?
- If 30-day: Change default back to 30
- If 14-day: Update all documentation to say "14-Day"

---

### 2. Relaxed Filters ⚠️

| Filter | v7.1 (100% win) | v8.0 (14-day) | CURRENT | Status |
|--------|----------------|---------------|---------|--------|
| **Volatility** | > 25% | (not used) | **> 20%** | ⚠️ TOO PERMISSIVE |
| **RS (30d)** | > 0% | (not used) | **> -3%** | ⚠️ TOO PERMISSIVE |
| **Sector Score** | > 40 | (not used) | **> 30** | ⚠️ TOO PERMISSIVE |
| **RS (14d)** | (not used) | > 1.9% | > 1.9% | ✅ OK |
| **RSI** | (not used) | > 49 | > 49 | ✅ OK |
| **Momentum 7d** | (not used) | > 3.5% | > 3.5% | ✅ OK |
| **MA20 Distance** | (not used) | > -2.8% | > -2.8% | ✅ OK |

**Issue:**
- Code RELAXED critical filters from v7.1:
  - Volatility: 25% → **20%** (Line 335)
  - RS: 0% → **-3%** (Line 358)
  - Sector: 40 → **30** (Line 364)
- Comments say "RELAXED to adapt to current market"
- **BUT: This was NOT backtested!**

**Impact:**
- Allows stocks that would have been filtered out in v7.1
- May reduce win rate from 100% to lower value
- **Risk:** Trading stocks that don't meet proven criteria

**Recommendation:**
- **Either:** Revert to strict v7.1 thresholds (25%, 0%, 40)
- **Or:** Run backtest with relaxed thresholds to validate

---

### 3. Hybrid Logic (v7.1 + v8.0) ⚠️

**Current Implementation Uses BOTH:**

From v7.1 (30-day backtest):
- Beta filter: 0.8-2.0 ✅
- Volatility filter: >20% (relaxed from 25%) ⚠️
- RS filter: >-3% (relaxed from 0%) ⚠️
- Sector score: >30 (relaxed from 40) ⚠️
- Valuation score: >20 ✅
- Inverted catalyst scoring ✅
- Inverted analyst coverage ✅

From v8.0 (14-day backtest):
- RSI > 49 ✅
- Momentum 7d > 3.5% ✅
- RS 14d > 1.9% ✅
- MA20 distance > -2.8% ✅

**Issue:**
- v7.1 was backtested for **30 days**
- v8.0 was backtested for **14 days**
- **Current code mixes both but runs on 14 days!**
- This combination was **NEVER backtested**

**Risk:**
- Unknown win rate with this hybrid approach
- May have conflicting signals (e.g., 30-day RS vs 14-day RS)

---

### 4. Exit Rules Not Backtested ❌

**Current Exit Rules** (from advanced_exit_rules.py):
```python
Hard stop loss: -6%
Trailing stop: -3% from peak
Time stop: 10 days (if return < 2%)
Filter score: Exit if ≤1 filters pass
Regime exit: BEAR = immediate exit
```

**Backtest Coverage:**
- ✅ Entry filters: Fully backtested (v7.1 and v8.0)
- ❌ **Exit rules: NO BACKTEST FOUND**
- No documentation showing win rate with these exits

**Issues:**
1. **Hard stop -6%:**
   - v7.1 doesn't specify stop loss
   - -6% may be too tight or too loose
   - Not validated against historical data

2. **Trailing stop -3%:**
   - Never tested in backtest
   - May exit winning trades too early
   - Or may not protect profits enough

3. **Time stop 10 days:**
   - Not tested with 14-day OR 30-day strategy
   - May exit before target reached
   - Arbitrary threshold?

4. **Filter score exit:**
   - Uses v8.0 filters (RSI, Momentum, RS 14d, MA20)
   - But what if we're on 30-day strategy?
   - Filter relevance unclear

**Recommendation:**
- **URGENTLY backtest exit rules!**
- Run same stocks through v7.1/v8.0 with current exit logic
- Validate: Does -6% stop improve or hurt win rate?
- Validate: Does 10-day time stop align with 14-day target?

---

## 📋 Detailed Comparison Tables

### Entry Filters: Backtest v7.1 vs Current

| Filter | v7.1 Threshold | Current Threshold | Match? | Notes |
|--------|---------------|-------------------|--------|-------|
| Beta Range | 0.8 - 2.0 | 0.8 - 2.0 | ✅ | Perfect match |
| Volatility | > 25% | **> 20%** | ❌ | TOO PERMISSIVE |
| RS (30-day) | > 0% | **> -3%** | ❌ | TOO PERMISSIVE |
| Sector Score | > 40 | **> 30** | ❌ | TOO PERMISSIVE |
| Valuation Score | > 20 | > 20 | ✅ | Perfect match |
| Catalyst Scoring | Inverted | Inverted | ✅ | Perfect match |
| Analyst Coverage | Inverted | Inverted | ✅ | Perfect match |

**Win Rate Impact:**
- v7.1 with strict thresholds: **100% (6/6)**
- Current with relaxed thresholds: **Unknown - NOT TESTED**

### Entry Filters: Backtest v8.0 vs Current

| Filter | v8.0 Threshold | Current Threshold | Match? | Notes |
|--------|---------------|-------------------|--------|-------|
| RSI | > 49.0 | > 49.0 | ✅ | Perfect match |
| Momentum 7d | > 3.5% | > 3.5% | ✅ | Perfect match |
| RS 14-day | > 1.9% | > 1.9% | ✅ | Perfect match |
| MA20 Distance | > -2.8% | > -2.8% | ✅ | Perfect match |

**Win Rate:**
- v8.0 predicted: **88.9%**
- v8.0 with hybrid (adding v7.1 filters): **Unknown**

### Exit Rules: No Backtest Available

| Exit Trigger | Current Value | Backtested? | Source |
|-------------|---------------|-------------|--------|
| Hard Stop | -6% | ❌ NO | advanced_exit_rules.py:33 |
| Trailing Stop | -3% from peak | ❌ NO | advanced_exit_rules.py:34 |
| Time Stop | 10 days | ❌ NO | advanced_exit_rules.py:35 |
| Filter Score | ≤1 pass | ❌ NO | advanced_exit_rules.py:36 |
| Regime Exit | BEAR | ❌ NO | advanced_exit_rules.py:37 |
| Max Hold | 20 days | ❌ NO | Implied fallback |

---

## 🔧 Code Evidence

### Current Timeframe (14 days)
**File:** `src/screeners/growth_catalyst_screener.py`
```python
Line 4: """14-Day Growth Catalyst Screener v8.0 (OPTIMIZED FOR SHORT-TERM)"""
Line 70: timeframe_days: int = 14,  # v8.0: Changed from 30 to 14 days
```

### Relaxed Filters
**File:** `src/screeners/growth_catalyst_screener.py`
```python
Line 335: if volatility_annual < 20.0:  # RELAXED from 25% to 20%
Line 358: if relative_strength < -3.0:  # RELAXED from 0% to -3%
Line 364: if sector_score < 30:  # RELAXED from 40 to 30
```

### Exit Rules
**File:** `src/advanced_exit_rules.py`
```python
Line 33: 'hard_stop_loss': -6.0,  # TIGHTER! (was -10%)
Line 34: 'trailing_stop': -3.0,   # Lock profits
Line 35: 'time_stop_days': 10,    # FASTER! (was 20 days)
Line 36: 'min_filter_score': 1,   # Exit if ≤1 filters pass
```

---

## 🎯 Recommendations

### IMMEDIATE ACTIONS (High Priority)

1. **Decide on Timeframe** ⚠️
   - Choose: 14-day OR 30-day strategy
   - Update documentation to match
   - User asked for "30-Day Growth Catalyst v2.0"
   - But code runs 14-day

   **Options:**
   - A) Keep 14-day → Update user expectation + all docs
   - B) **Change to 30-day → Revert timeframe_days to 30**

2. **Restore Strict Filters** ⚠️
   - **Revert to v7.1 proven thresholds:**
     ```python
     volatility_annual < 25.0  # Was 20% (TOO PERMISSIVE)
     relative_strength < 0.0   # Was -3% (TOO PERMISSIVE)
     sector_score < 40         # Was 30 (TOO PERMISSIVE)
     ```
   - v7.1 had **100% win rate** with these thresholds
   - Current relaxed thresholds are **UNPROVEN**

3. **Backtest Exit Rules** ❌ CRITICAL
   - Run full backtest with current exit logic
   - Test on same stocks as v7.1/v8.0
   - Validate:
     - Does -6% stop help or hurt?
     - Is 10-day time stop too fast?
     - Does trailing -3% lock profits or exit too early?

   **Script to create:**
   ```bash
   backtest_exit_rules.py
   # Test v7.1 winners with current exits
   # Test v8.0 stocks with current exits
   # Compare win rates before/after
   ```

### MEDIUM PRIORITY

4. **Separate v7.1 and v8.0**
   - Don't mix 30-day and 14-day logic
   - Create two separate screeners:
     ```
     growth_catalyst_screener_30day.py  # v7.1 proven
     growth_catalyst_screener_14day.py  # v8.0 experimental
     ```

5. **Document What Was Actually Tested**
   - Update GROWTH_CATALYST_COMPLETE.md
   - Clearly state which filters have backtests
   - Mark untested parameters as "EXPERIMENTAL"

### LOW PRIORITY

6. **Add Backtest Validation**
   - Before going live, run:
     ```bash
     python backtest_current_implementation.py
     # Test EXACT current code against historical data
     # Don't assume hybrid logic works!
     ```

7. **Track Real Results**
   - Monitor first 10 trades carefully
   - Compare actual vs expected win rate
   - If < 70% win rate → something's wrong

---

## 🚨 Risk Assessment

| Risk | Severity | Probability | Impact |
|------|----------|-------------|--------|
| **Timeframe mismatch** | HIGH | 100% | User expects 30d, gets 14d results |
| **Relaxed filters reduce win rate** | HIGH | 75% | May drop from 100% to 60-70% |
| **Untested exit rules** | CRITICAL | 90% | Could turn winners into losers |
| **Hybrid logic conflicts** | MEDIUM | 50% | Unknown interaction effects |
| **Over-optimization** | MEDIUM | 40% | Filters tuned to past, may not work forward |

**Overall Risk Level: 🔴 HIGH**

**Expected Outcome with Current Code:**
- Win rate likely **70-80%** (down from 100%)
- Average return may be **lower** due to early exits
- **Exit rules may be too aggressive** (10 days = 71% of 14-day window)

---

## ✅ What DOES Match Backtest

### Correctly Implemented (v7.1):
- ✅ Beta filter: 0.8-2.0
- ✅ Valuation score: > 20
- ✅ Inverted catalyst scoring
- ✅ Inverted analyst coverage
- ✅ Composite score weights

### Correctly Implemented (v8.0):
- ✅ RSI > 49
- ✅ Momentum 7d > 3.5%
- ✅ RS 14d > 1.9%
- ✅ MA20 distance > -2.8%

### Correctly Implemented (Infrastructure):
- ✅ Regime detection (STAGE 0)
- ✅ Portfolio manager v2.0
- ✅ Advanced exit rules class
- ✅ Market regime detector

---

## 📝 Action Items Checklist

**BEFORE TRADING REAL MONEY:**

- [ ] **Decide timeframe: 14-day or 30-day?**
- [ ] **Revert to strict v7.1 filters (25%, 0%, 40)**
- [ ] **Backtest current exit rules (-6%, -3%, 10d)**
- [ ] **Run comprehensive backtest on current EXACT code**
- [ ] **Validate hybrid v7.1+v8.0 logic works together**
- [ ] **Update all documentation to match implementation**
- [ ] **Paper trade for 2-4 weeks minimum**
- [ ] **Compare paper results to backtest predictions**

**IF WIN RATE < 70% IN PAPER TRADING:**
- [ ] Revert to pure v7.1 (30-day, strict filters, 100% win rate)
- [ ] Remove untested modifications
- [ ] Only use proven, backtested parameters

---

## 📄 File Locations

**Backtest Files:**
- `GROWTH_CATALYST_v7.1_SUMMARY.md` - 100% win rate, 30-day, strict filters
- `backtest_v8_14day.py` - 88.9% predicted, 14-day, 4 new filters
- `SCANNER_UPDATE_v8.0.md` - Premarket scanner (different strategy)

**Implementation Files:**
- `src/screeners/growth_catalyst_screener.py` - **14-day hybrid** (NOT backtested)
- `src/advanced_exit_rules.py` - Exit logic (NOT backtested)
- `src/portfolio_manager.py` - Portfolio tracking (infrastructure only)
- `src/market_regime_detector.py` - Regime detection (infrastructure only)

---

## 💡 Final Recommendation

**CRITICAL: DO NOT TRADE WITH CURRENT CODE AS-IS**

**Reason:**
1. Relaxed filters not backtested (may reduce win rate)
2. Exit rules not backtested (may turn winners to losers)
3. Timeframe confusion (14d vs 30d)
4. Hybrid logic never validated together

**Safe Path Forward:**

**Option A: Conservative (RECOMMENDED)**
- Revert to pure v7.1
- 30-day timeframe
- Strict filters (25%, 0%, 40)
- Add simple exit: 5% target OR -10% stop OR 30 days max
- This has **proven 100% win rate**

**Option B: Validate Current**
1. Backtest exit rules on v7.1 stocks
2. Backtest relaxed filters on historical data
3. Run 30-day paper trading
4. Only go live if results match predictions

**Option C: Separate Strategies**
- Strategy 1: v7.1 pure (30d, 100% win rate) ← Use this!
- Strategy 2: v8.0 pure (14d, 88.9% predicted) ← Test this
- Don't mix them until both proven separately

---

**Status:** ⚠️ **VERIFICATION FAILED - MISMATCHES FOUND**
**Next Step:** User decision required on timeframe and filters
**Date:** 2025-12-26
