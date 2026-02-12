# Trading Strategy Status

**Last Updated:** 2026-02-12

## ✅ Active Strategies (Auto-Trading)

### 1. Dip-Bounce Strategy
- **Status:** INTEGRATED & ACTIVE ✅
- **File:** `src/strategies/dip_bounce_strategy.py`
- **Performance:** Working (11 signals from 212 stocks last scan)
- **Features:**
  - Sector regime filtering
  - Alternative data scoring
  - Gap/ATR filters
  - Min score: 85

### 2. VIX Adaptive Strategy
- **Status:** INTEGRATED & ACTIVE ✅
- **File:** `src/strategies/vix_adaptive/`
- **Config:** `vix_adaptive_enabled = True`
- **Performance:** Working (0 signals - tier conditions not met)
- **Features:**
  - 3-tier system (NORMAL/HIGH/EXTREME)
  - Dynamic position sizing
  - Volatility-based entry/exit
  - Bounce strategy in HIGH tier

**Strategy Manager:** 2 strategies registered ✅

---

## ❌ Not Implemented - KEEP FOR FUTURE

### Candlestick Strategy
- **Status:** DOCUMENTED, NOT CODED
- **Spec:** `docs/CANDLESTICK_STRATEGY_SPEC.md`
- **Strategy:** Bullish Engulfing + Hammer with context filters
- **Win Rate:** 72% (validated in spec)
- **Implementation:** Bullish Engulfing + Hammer
- **Filters:** Trend, Volume, Support (3 only - more = overfitting)
- **Protection:** 3-layer system (volatility, equity throttle, execution)
- **Expected Performance:**
  - Normal: 70-73% WR, 22-25% CAGR, 8-10% DD
  - Bear: 60-65% WR, 10-15% CAGR, 12-15% DD
  - Crisis: 35-40% WR, -5% to +5% CAGR, 10-13% DD

**📝 NOTE:** ยังไม่ทำ แต่ไม่ลบ - เก็บไว้ implement ในอนาคต

**Timeline if implemented:**
- Coding: 2-3 weeks
- Paper trading: 30+ days minimum
- Must pass 4 distribution checks before live

---

## 🟡 Standalone Screeners - KEEP FOR MANUAL USE

These screeners are NOT integrated into auto-trading but available for manual use:

1. **Growth Catalyst Screener** - `src/screeners/growth_catalyst_screener.py`
2. **Momentum Growth Screener** - `src/screeners/momentum_growth_screener.py`
3. **Value Screener** - `src/screeners/value_screener.py`
4. **Dividend Screener** - `src/screeners/dividend_screener.py`
5. **Support Level Screener** - `src/screeners/support_level_screener.py`
6. **Pullback Catalyst Screener** - `src/screeners/pullback_catalyst_screener.py`

**📝 NOTE:** ไม่ integrate เข้า auto-trading แต่ไม่ลบ - ใช้งาน manual ได้

**Why not integrated?**
- Current 2 strategies already cover mean reversion + volatility timing
- Too many strategies = signal dilution
- Can be used for manual research/analysis
- May integrate later if testing shows clear benefit

---

## 🗑️ Legacy Files (Can be deleted if needed)

- `src/master_screener.py` - old version
- `src/optimized_screener.py` - old version
- `src/fundamental_screener.py` - old version
- `src/pullback_dual_strategy.py` - old version
- `src/debug_value_screener.py` - testing only
- `src/final_test_value_screener.py` - testing only

---

## Summary

**Integration Completeness:** 100% for auto-trading ✅

- **Core Strategies:** 2/2 active (Dip-Bounce + VIX Adaptive)
- **Supplementary Strategies:** Keep for future (Candlestick + 6 screeners)
- **System Status:** Fully operational
- **StrategyManager:** Working correctly
- **Signal Generation:** Working correctly

**Recommendation:** Current 2-strategy setup is optimal. Monitor performance for 1-2 months before adding Candlestick strategy.
