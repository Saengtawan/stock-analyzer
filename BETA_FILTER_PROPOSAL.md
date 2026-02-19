# Beta/Volatility Filter Proposal - v6.32

**Problem:** System scores defensive stocks high in BEAR mode (correct!) but doesn't filter out low-volatility stocks unsuitable for swing trading (wrong!)

**Example:** KHC scored 150 (defensive quality) but has beta 0.047 (too slow for rapid rotation)

---

## 🎯 Proposed Solution

### Add Beta/Volatility Filter (Post-Scoring, Pre-Execution)

**Location:** `src/auto_trading_engine.py` → `execute_signal()`
**After:** Quality filters (score threshold)
**Before:** Order execution

### Filter Logic:

```python
def _check_beta_volatility(self, symbol: str, signal) -> Tuple[bool, str]:
    """
    v6.32: Filter out low-volatility stocks unsuitable for swing trading

    Criteria (ANY of these passes):
    1. Beta >= 0.5 (moderate to high volatility)
    2. ATR >= 5% (high recent volatility)
    3. In CORE_STOCKS list (manually curated high-beta)

    Returns:
        (passed, reason)
    """
    import yfinance as yf

    # Check if in curated list (bypass beta check)
    if symbol in self.CORE_STOCKS:
        return True, "in_core_stocks"

    # Get beta and ATR
    try:
        ticker = yf.Ticker(symbol)
        beta = ticker.info.get('beta', None)
        atr_pct = getattr(signal, 'atr_pct', None)

        # Pass if beta >= 0.5
        if beta and beta >= 0.5:
            return True, f"beta_{beta:.2f}"

        # Pass if ATR >= 5%
        if atr_pct and atr_pct >= 5.0:
            return True, f"atr_{atr_pct:.1f}%"

        # Fail if both low
        beta_str = f"{beta:.3f}" if beta else "N/A"
        atr_str = f"{atr_pct:.1f}%" if atr_pct else "N/A"
        return False, f"low_volatility (beta={beta_str}, atr={atr_str})"

    except Exception as e:
        # If can't fetch data, allow (don't block on API failure)
        return True, f"data_unavailable"
```

### Integration Point:

```python
# In execute_signal(), after quality filters:

# EXISTING: Quality Filters
score_ok, score_reason = self._exec_quality_filters(...)
if not score_ok:
    return False

# NEW: Beta/Volatility Filter
beta_ok, beta_reason = self._check_beta_volatility(symbol, signal)
if not beta_ok:
    self._log_filter_rejection(
        symbol, current_price, "LOW_VOLATILITY",
        f"Stock too slow for swing trading: {beta_reason}",
        {"beta_filter": {"passed": False, "reason": beta_reason}},
        ...
    )
    return False

# Continue with execution...
```

---

## 📊 Expected Impact

### Stocks That Would Be Rejected:

| Symbol | Beta | ATR% | Sector | Why Rejected |
|--------|------|------|--------|--------------|
| KHC | 0.047 | 3.19 | Consumer Def | Both too low ❌ |
| PG | 0.12 | 2.8 | Consumer Def | Both too low ❌ |
| KO | 0.21 | 3.2 | Consumer Def | Both too low ❌ |
| T | 0.33 | 2.5 | Telecom | Both too low ❌ |

### Stocks That Would Still Pass:

| Symbol | Beta | ATR% | Reason |
|--------|------|------|--------|
| NVDA | 1.67 | 8.5 | Beta high ✅ |
| TSLA | 2.01 | 12.3 | Beta high ✅ |
| PLTR | 1.43 | 9.8 | Beta high ✅ |
| XOM | 0.42 | 5.2 | ATR high ✅ (energy volatile) |
| AAPL | 0.89 | 4.8 | In CORE_STOCKS ✅ |

### Trade-offs:

**Pros:**
- ✅ Prevents buying slow-moving stocks (KHC-type)
- ✅ Focuses on stocks that can move quickly
- ✅ Better fit for rapid rotation strategy
- ✅ May improve average holding time (faster exits)

**Cons:**
- ⚠️ May reduce trade count by 5-10%
- ⚠️ Loses some BEAR mode defensive trades
- ⚠️ API call to yfinance (adds ~0.5s per signal)
- ⚠️ Beta data can be stale or missing

---

## 🧪 Testing Plan

### Backtest Analysis:
1. Re-run 2023-2025 backtest WITH beta filter
2. Compare metrics vs baseline:
   - Trade count (expect -5-10%)
   - Win rate (expect +2-4%)
   - Avg P&L per trade (expect +0.2-0.5%)
   - Avg hold time (expect -0.5-1 day)

### Paper Trading:
1. Deploy with logging only (don't reject, just log)
2. Track for 1 week:
   - How many signals would be rejected?
   - Were those rejections correct?
   - Did we miss good trades?

### Production:
1. Enable filter after paper trading validates
2. Monitor for 2 weeks:
   - Trade quality improvement?
   - No unintended rejections?

---

## ⚙️ Configuration

Add to `config/trading.yaml`:

```yaml
# Beta/Volatility Filter (v6.32)
beta_filter:
  enabled: true
  min_beta: 0.5           # Minimum beta for entry
  min_atr_pct: 5.0        # Minimum ATR% for entry
  bypass_core_stocks: true # Skip check for CORE_STOCKS
  log_only: false         # Set true for testing (log but don't reject)
```

---

## 📝 Implementation Checklist

- [ ] Add `_check_beta_volatility()` method to auto_trading_engine.py
- [ ] Integrate into `execute_signal()` after quality filters
- [ ] Add config fields to trading.yaml
- [ ] Load config in `_load_config_from_yaml()`
- [ ] Add logging for rejections
- [ ] Update trade_logger to track beta_filter rejections
- [ ] Test with KHC-like stocks
- [ ] Backtest with historical data
- [ ] Deploy to paper trading
- [ ] Monitor and validate

---

## 🎯 Success Criteria

**After 1 month:**
- ✅ No more low-beta defensive stocks bought (beta < 0.5 rejected)
- ✅ Average trade P&L improved by >0.2%
- ✅ Win rate maintained or improved
- ✅ No false rejections of high-quality signals

---

## 📌 Related Issues

- Ghost Position Fix (v6.31) - Fixed order execution
- **This Fix (v6.32)** - Prevent wrong signals from being executed
- Future: Add sector-specific beta thresholds (Energy beta 0.4 OK, Tech beta 0.8 minimum)
