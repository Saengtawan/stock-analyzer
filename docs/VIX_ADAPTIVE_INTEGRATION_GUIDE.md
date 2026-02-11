# VIX Adaptive v3.0 - Integration Guide

**Date**: 2026-02-11
**Status**: Ready for Integration

---

## ✅ Prerequisites (DONE)

- [x] Core strategy classes implemented
- [x] VIX data provider ready
- [x] Configuration file created (`config/vix_adaptive.yaml`)
- [x] Required indicators added to `TechnicalIndicators`
- [x] Integration wrapper created (`engine_integration.py`)
- [x] All tests passing (19/19)

---

## 📋 Integration Steps

### Step 1: Add VIX Adaptive to Auto Trading Engine

**File**: `src/auto_trading_engine.py`

**1.1 Import at top of file:**

```python
# Add after other imports
from strategies.vix_adaptive.engine_integration import VIXAdaptiveIntegration
```

**1.2 Initialize in `__init__` method (around line 470):**

```python
# After breakout scanner initialization
# VIX Adaptive Strategy v3.0
self.vix_adaptive = None
if self.VIX_ADAPTIVE_ENABLED:  # Add config parameter
    try:
        self.vix_adaptive = VIXAdaptiveIntegration(
            config_path='config/vix_adaptive.yaml',
            enabled=True
        )
        logger.info(f"VIX Adaptive Strategy initialized: {self.vix_adaptive}")
    except Exception as e:
        logger.warning(f"VIX Adaptive init failed: {e}")
```

**1.3 Add config parameter in `_load_config_from_yaml` method:**

```python
# Add to config loading section
self.VIX_ADAPTIVE_ENABLED = extended_config.get('vix_adaptive_enabled', False)
```

**1.4 Add to `config/trading.yaml`:**

```yaml
# VIX Adaptive Strategy v3.0
vix_adaptive_enabled: false  # Set true to enable
```

---

### Step 2: Integrate Signal Scanning

**File**: `src/auto_trading_engine.py`

**In `_run_loop` method (where signals are scanned):**

```python
# After regular screener signals
all_signals = []

# Regular Rapid Rotation signals
if self.screener:
    regular_signals = self.screener.scan()
    all_signals.extend(regular_signals)

# 🆕 VIX Adaptive signals
if self.vix_adaptive and self.vix_adaptive.enabled:
    try:
        vix_signals = self.vix_adaptive.scan_signals(
            date=datetime.now().date(),
            stock_data=self.stock_data_cache,  # Must have indicators!
            active_positions=list(self.positions.values())
        )

        if vix_signals:
            all_signals.extend(vix_signals)
            logger.info(f"VIX Adaptive: {len(vix_signals)} signals added")

    except Exception as e:
        logger.error(f"VIX Adaptive scan failed: {e}")

# Process all signals
for signal in all_signals:
    # ... existing signal processing logic
```

---

### Step 3: Ensure Indicators Are Calculated

**File**: Wherever stock data is fetched and analyzed (probably `src/rapid_portfolio_manager.py` or in `_run_loop`)

**Make sure these indicators exist in stock DataFrames:**

```python
from analysis.technical.indicators import TechnicalIndicators

def analyze_stock(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators including VIX Adaptive ones."""

    # Calculate all indicators
    ta = TechnicalIndicators(df)
    all_indicators = ta.get_all_indicators()

    # Add to DataFrame
    for key, value in all_indicators.items():
        if isinstance(value, np.ndarray):
            df[key] = value

    # Verify VIX Adaptive indicators exist
    required = ['return_2d', 'dip_from_3d_high', 'yesterday_dip']
    missing = [ind for ind in required if ind not in df.columns]

    if missing:
        logger.warning(f"{symbol}: Missing VIX indicators: {missing}")

    return df
```

---

### Step 4: Handle VIX Adaptive Signals in Position Manager

**File**: Position management code

**VIX Adaptive signals have special fields:**

```python
signal = {
    'symbol': 'AAPL',
    'tier': 'normal',  # or 'high'
    'score': 92.5,
    'entry_price': 150.00,
    'stop_loss': 146.50,
    'atr_pct': 2.5,
    'reason': 'mean_reversion (score=92.5, dip=-1.5%)',
    'strategy': 'vix_adaptive',
    'max_hold_days': 10,

    # HIGH tier only:
    'bounce_gain': 1.2,  # 2-day gain
    'dip_from_high': -3.5,  # Dip from 3d high
}
```

**Handle tier-specific logic:**

```python
if signal.get('strategy') == 'vix_adaptive':
    tier = signal.get('tier')

    if tier == 'high':
        # Bounce strategy: No trailing stop
        use_trailing = False
    else:  # normal
        # Mean reversion: Use trailing stop
        use_trailing = True

    max_hold = signal.get('max_hold_days', 10)
```

---

## 🔍 Verification Checklist

After integration, verify:

### 1. Configuration
```bash
# Check config loaded
grep -A 5 "vix_adaptive_enabled" config/trading.yaml
```

### 2. Indicators Present
```python
# In Python console
from analysis.technical.indicators import TechnicalIndicators
import yfinance as yf

df = yf.download('AAPL', period='1mo')
ta = TechnicalIndicators(df)
vix_indicators = ta.calculate_vix_adaptive_indicators()

print(vix_indicators.keys())
# Should show: dict_keys(['return_2d', 'dip_from_3d_high', 'yesterday_dip'])
```

### 3. Strategy Initialization
```python
# Check logs for:
✅ VIX Adaptive v3.0 initialized
   Boundaries: {'normal_max': 20, 'skip_max': 24, 'high_max': 38}
   Score adaptation: True
```

### 4. Signal Generation
```python
# Check logs for:
VIX Adaptive: 2 signals (VIX=18.5, tier=NORMAL)
VIX Adaptive: 2 signals added
```

### 5. Tier Transitions
```python
# When VIX changes tiers, check logs:
🔄 Tier transition: NORMAL → HIGH (VIX: 25.00)
🚨 EXTREME tier activated! VIX=42.0 > 38 - CLOSING ALL
```

---

## 🎯 Testing Procedure

### Phase 1: Dry Run (No Trading)

1. **Set `vix_adaptive_enabled: false`**
2. **Add debug logging:**

```python
if self.vix_adaptive:
    current_vix = self.vix_adaptive.get_current_vix()
    current_tier = self.vix_adaptive.get_current_tier()
    logger.info(f"VIX Adaptive: VIX={current_vix:.2f}, Tier={current_tier}")
```

3. **Run engine for 1 day - verify:**
   - VIX data fetched successfully
   - Tier detected correctly
   - No errors in logs

### Phase 2: Signal Generation (No Execution)

1. **Set `vix_adaptive_enabled: true`**
2. **Disable order execution** (add `if False:` around order placement)
3. **Run for 3-5 days - verify:**
   - Signals generated when appropriate
   - No signals during SKIP tier (VIX 20-24)
   - Bounce signals only on VIX falling days
   - Score threshold adapts to VIX level

### Phase 3: Paper Trading

1. **Enable full execution** in paper account
2. **Run for 30+ trading days**
3. **Track metrics:**
   - Win rate >= 45%
   - Max losing streak <= 7
   - Entry success rate >= 85%
   - Drawdown < 20%

### Phase 4: Live (Gradual Scale-Up)

1. **Week 1-4**: 10% capital, 1 position max
2. **Week 5-8**: 25% capital, 2 positions max
3. **Week 9-12**: 50% capital, 3 positions max
4. **Week 13+**: Full capital

---

## 📊 Monitoring Dashboard

**Key Metrics to Track:**

```python
# Daily report
VIX Adaptive Daily Report:
  VIX: 18.5 (NORMAL tier)
  Signals: 3 scanned, 2 entered
  Active Positions: 2/3 (NORMAL tier)
  Tier Distribution: NORMAL 90%, HIGH 10%, SKIP 0%
  Win Rate (20-trade): 54.3%
  Avg PnL: +3.2%
  Current Drawdown: -2.1%
```

**Alerts to Set:**
- VIX > 38 (EXTREME tier)
- Drawdown > 6%, 10%, 15%
- Win rate < 45% (rolling 20 trades)
- Missing indicators warning

---

## 🐛 Troubleshooting

### Issue: "Missing indicators [return_2d, dip_from_3d_high]"

**Solution**: Make sure `TechnicalIndicators.calculate_vix_adaptive_indicators()` is called and added to DataFrame.

```python
# In stock analysis code
indicators = ta.get_all_indicators()  # This includes VIX indicators now
```

### Issue: "No VIX data for date"

**Solution**: VIX data may not be available for all dates (weekends, holidays).

```python
# The strategy handles this gracefully:
if self.current_vix is None:
    logger.warning(f"No VIX data for {date}, skipping")
    return []
```

### Issue: "VIX Adaptive scan failed"

**Check**:
1. Config file exists at `config/vix_adaptive.yaml`
2. VIX data provider initialized successfully
3. Stock data has required columns: `['close', 'high', 'low', 'score', 'atr_pct', ...]`

### Issue: "Strategy always returns 0 signals"

**Check**:
1. Current VIX tier (might be SKIP or EXTREME)
2. Score threshold too high (should adapt: 70-90)
3. VIX direction (HIGH tier only trades when VIX falling)

---

## 📚 Reference

- **Full Backtest Results**: `docs/VIX_ADAPTIVE_BACKTEST_RESULTS.md`
- **Implementation Checklist**: `docs/VIX_ADAPTIVE_IMPLEMENTATION_CHECKLIST.md`
- **Implementation Status**: `docs/VIX_ADAPTIVE_IMPLEMENTATION_STATUS.md`
- **Config File**: `config/vix_adaptive.yaml`
- **Demo Script**: `examples/vix_adaptive_demo.py`

---

## ⏭️ Next Steps

1. ✅ Add integration code to `auto_trading_engine.py` (Steps 1-2 above)
2. ✅ Verify indicators are calculated (Step 3)
3. ⏳ Run Phase 1 testing (Dry run)
4. ⏳ Run Phase 2 testing (Signal generation)
5. ⏳ Paper trade for 30+ days
6. ⏳ Gradual live deployment

---

**Status**: Ready to integrate
**Estimated Time**: 1-2 hours for integration + testing
**Risk Level**: Low (can be toggled off easily)

---

End of Integration Guide
