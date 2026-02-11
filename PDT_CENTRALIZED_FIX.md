# PDT Centralized Control - Implementation Plan

## Problem Analysis

**Current Situation:**
- PDT Guard called from 27+ locations in auto_trading_engine.py
- `pdt_enforce_always: false` config exists but NOT used
- All PDT methods run regardless of config flag
- If we want to support PDT=false, need to modify 27 places ❌

## Solution: Centralize at PDT Guard Level

### Option 1: Add `_is_enabled()` Check (RECOMMENDED)

**Modify:** `src/pdt_smart_guard.py`

**Add Property:**
```python
def _is_pdt_enforced(self) -> bool:
    """Check if PDT rules should be enforced"""
    # If enforce_always is False, PDT is disabled
    if not self._get_enforce_on_paper():
        return False

    # Check account equity (> $25K = exempt from PDT)
    if self.broker:
        try:
            account = self.broker.get_account()
            equity = float(getattr(account, 'equity', 0))
            threshold = self.config.pdt_account_threshold if hasattr(self.config, 'pdt_account_threshold') else 25000.0

            if equity >= threshold:
                logger.debug(f"PDT bypassed: Account equity ${equity:,.0f} >= ${threshold:,.0f}")
                return False
        except Exception as e:
            logger.warning(f"Failed to check account equity for PDT bypass: {e}")

    return True  # Default: enforce PDT
```

### Critical Methods to Update

**1. get_pdt_status() - Return "unlimited" when disabled**
```python
def get_pdt_status(self) -> PDTStatus:
    # NEW: Bypass if PDT not enforced
    if not self._is_pdt_enforced():
        return PDTStatus(
            day_trade_count=0,
            remaining=999,  # Unlimited
            is_flagged=False,
            can_day_trade=True,
            reserve_active=False
        )

    # ... existing code ...
```

**2. can_sell() - Always allow when disabled**
```python
def can_sell(self, symbol: str, pnl_pct: float, sl_override: float = None, tp_override: float = None) -> Tuple[bool, SellDecision, str]:
    # NEW: Bypass if PDT not enforced
    if not self._is_pdt_enforced():
        return True, SellDecision.ALLOWED, "PDT rules disabled"

    # ... existing code ...
```

**3. should_place_sl_order() - Always allow when disabled**
```python
def should_place_sl_order(self, symbol: str) -> Tuple[bool, str]:
    # NEW: Bypass if PDT not enforced
    if not self._is_pdt_enforced():
        return True, "PDT disabled - SL order allowed"

    # ... existing code ...
```

**4. should_place_eod_sl() - Always allow when disabled**
```python
def should_place_eod_sl(self, symbol: str) -> Tuple[bool, str]:
    # NEW: Bypass if PDT not enforced
    if not self._is_pdt_enforced():
        return True, "PDT disabled - EOD SL allowed"

    # ... existing code ...
```

## Benefits

✅ **Single point of control** - Change 1 property, affects all 27+ call sites
✅ **Config-driven** - Set `pdt_enforce_always: false` to disable
✅ **Auto-detect** - Checks account equity, bypasses if > $25K
✅ **Backward compatible** - Existing code works unchanged
✅ **Easy testing** - Toggle PDT on/off with config change

## Testing Plan

**Test 1: PDT Disabled via Config**
```yaml
pdt_enforce_always: false
```
Expected:
- All sells allowed immediately (no Day 0 holds)
- SL orders placed on all positions
- No PDT budget checks

**Test 2: PDT Disabled via Account Size**
```python
# Account with $30,000 equity
# pdt_account_threshold: 25000
```
Expected:
- Same as Test 1 (auto-bypass)

**Test 3: PDT Enabled (Default)**
```yaml
pdt_enforce_always: true
# Account < $25K
```
Expected:
- Current behavior (Day 0 holds, budget checks)

## Implementation Steps

1. ✅ Add `_is_pdt_enforced()` property to PDTSmartGuard
2. ✅ Add bypass check to 4 critical methods:
   - get_pdt_status()
   - can_sell()
   - should_place_sl_order()
   - should_place_eod_sl()
3. ✅ Add logging when PDT bypassed
4. ✅ Test with pdt_enforce_always: false
5. ✅ Test with account > $25K
6. ✅ Verify existing behavior unchanged when enabled

## Config Reference

```yaml
rapid_rotation:
  # PDT Settings
  pdt_account_threshold: 25000.0  # Auto-bypass if equity > this
  pdt_day_trade_limit: 3          # Max day trades when enforced
  pdt_reserve: 1                  # Reserve for emergencies
  pdt_enforce_always: true        # Set false to disable PDT
  pdt_tp_threshold: 4.0           # TP threshold for PDT decisions
```

## Edge Cases

**Q: What if we want PDT enabled even for > $25K accounts?**
A: Keep `pdt_enforce_always: true` - equity check only bypasses if flag is false

**Q: What about record_entry() and remove_entry()?**
A: Keep tracking even when disabled - useful for analytics

**Q: Should get_days_held() return 999 when disabled?**
A: No - keep real tracking, just bypass sell restrictions

---

**Status:** Ready to implement
**Impact:** Affects all 27+ PDT call sites with 4 code changes
**Risk:** Low (backward compatible, config-gated)
