# Configuration Schema - Complete Reference

**Version:** v6.10.1
**Last Updated:** 2026-02-09
**Config File:** `config/trading.yaml`

---

## Table of Contents

1. [Stop Loss / Take Profit](#stop-loss--take-profit)
2. [Trailing Stop](#trailing-stop)
3. [Position Management](#position-management)
4. [Risk Management](#risk-management)
5. [Scoring & Filtering](#scoring--filtering)
6. [PDT Settings](#pdt-settings)
7. [Market Hours & Sessions](#market-hours--sessions)
8. [Regime Detection](#regime-detection)
9. [Sector Scoring](#sector-scoring)
10. [Example Configurations](#example-configurations)
11. [Validation Rules](#validation-rules)

---

## Stop Loss / Take Profit

### ATR-Based SL/TP (Primary Method)

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `atr_sl_multiplier` | float | 0.5-5.0 | 1.5 | Stop loss = ATR × multiplier |
| `atr_tp_multiplier` | float | 1.0-10.0 | 3.0 | Take profit = ATR × multiplier |

**Logic:** `atr_tp_multiplier` must be > `atr_sl_multiplier` for positive risk:reward

### Safety Caps (Prevent Extreme Values)

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `min_sl_pct` | float | 1.0-10.0 | 2.0 | Minimum stop loss % (tightest allowed) |
| `max_sl_pct` | float | 2.0-10.0 | 2.5 | Maximum stop loss % (widest allowed) |
| `min_tp_pct` | float | 3.0-50.0 | 4.0 | Minimum take profit % (shortest allowed) |
| `max_tp_pct` | float | 5.0-50.0 | 8.0 | Maximum take profit % (longest allowed) |

**Critical Constraints:**
- `min_sl_pct` < `max_sl_pct`
- `min_tp_pct` < `max_tp_pct`
- `min_tp_pct` > `max_sl_pct` ← **TP target must exceed worst-case SL**

### Fallback Values (When ATR Unavailable)

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `default_sl_pct` | float | min_sl_pct - max_sl_pct | 2.5 | Default stop loss if ATR fails |
| `default_tp_pct` | float | min_tp_pct - max_tp_pct | 5.0 | Default take profit if ATR fails |

**Validation:** Default values must be within their respective ranges

### PDT-Specific

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `pdt_tp_threshold` | float | > 0 | 4.0 | Profit threshold worth using a day trade |

---

## Trailing Stop

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `trail_enabled` | bool | - | true | Enable trailing stop |
| `trail_activation_pct` | float | >= min_tp_pct | 3.0 | Activate trailing at +N% gain |
| `trail_lock_pct` | float | 0-100 | 75.0 | Lock N% of peak gains |

**Example:**
- Stock gains +5% (activates trailing at +3%)
- Trails at 75% = locks in +3.75%
- If drops to +3.75%, exits with profit

**Validation:** `trail_activation_pct` should be >= `min_tp_pct` to activate at/above TP target

---

## Position Management

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `max_positions` | int | 1-20 | 5 | Max concurrent positions |
| `max_hold_days` | int | 1-30 | 10 | Max days to hold (time stop) |
| `position_size_pct` | float | > 0, <= 100 | 1.0 | Base position size (% of equity) |
| `max_position_pct` | float | > 0, <= 100 | 10.0 | Max position size (% of equity) |
| `simulated_capital` | int/null | > 0 or null | 4000 | Simulated capital (null = use real account) |

**Constraints:**
- `position_size_pct` <= `max_position_pct`
- `max_positions` > 20 → over-diversification warning
- `max_hold_days` > 30 → not rapid rotation warning

**Strategy-Specific:**
- **Rapid Rotation:** max_positions=3-5, max_hold_days=5-10
- **Swing Trading:** max_positions=5-10, max_hold_days=10-30

---

## Risk Management

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `risk_parity_enabled` | bool | - | true | Enable risk-parity position sizing |
| `risk_budget_pct` | float | > 0, <= 5.0 | 1.0 | Max risk per position (% of account) |
| `daily_loss_limit_pct` | float | > 0, <= 50 | 5.0 | Daily loss limit (% of equity) |
| `weekly_loss_limit_pct` | float | > 0, <= 50 | 7.0 | Weekly loss limit (% of equity) |
| `max_consecutive_losses` | int | > 0 | 5 | Circuit breaker trigger count |

**Risk Budget Example:**
```
Account: $10,000
risk_budget_pct: 1.0 → Max risk per trade = $100
SL: 2.5%
Position size = $100 / 2.5% = $4,000 (40% of account)
```

**Safety Limits:**
- `risk_budget_pct` > 5% → excessive per-trade risk warning
- `daily_loss_limit_pct` > 50% → excessive risk warning

---

## Scoring & Filtering

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `min_score` | int | 0-100 | 85 | Minimum score to qualify |
| `min_atr_pct` | float | > 0, <= 10 | 2.5 | Minimum ATR% (volatility filter) |
| `max_rsi_entry` | int | 0-100 | 65 | Block RSI > N (overbought filter) |
| `avoid_mom_range` | list | [min, max] | [10, 12] | Skip momentum in range (unstable zone) |

**Scoring Logic:**
- Base score: 0-100 (technical + momentum + volume)
- Sector bonus/penalty: ±15 points
- Alt data bonus/penalty: ±15 points
- Final score: sum of all components

**Filters:**
- `min_atr_pct` > 10% → excludes most stocks warning
- RSI > 65 historically shows 20% win rate (overbought)

---

## PDT Settings

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `pdt_account_threshold` | float | > 0 | 25000.0 | PDT threshold ($) |
| `pdt_day_trade_limit` | int | >= 0 | 3 | Max day trades for non-PDT accounts |
| `pdt_reserve` | int | 0 - pdt_day_trade_limit | 1 | Reserve N day trades for emergencies |
| `pdt_enforce_always` | bool | - | true | Enforce PDT rules even on paper |

**PDT Logic:**
```
Budget = pdt_day_trade_limit - pdt_reserve
Example: 3 - 1 = 2 usable day trades (1 reserved for SL)

Day 0 Sell Decision:
- SL hit (< -2.5%) → Use day trade (emergency)
- TP hit (> +4.0%) → Use day trade (lock profit)
- Small gain (< +4.0%) → Hold overnight (save day trade)
- Budget = 0 → HOLD (no override, no PDT flag risk)
```

**Constraints:**
- `pdt_reserve` cannot exceed `pdt_day_trade_limit`
- Setting `pdt_reserve` = `pdt_day_trade_limit` → disables all day trades

---

## Market Hours & Sessions

### Market Hours

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `market_open_hour` | int | 0-23 | 9 | Market open hour (ET) |
| `market_open_minute` | int | 0-59 | 30 | Market open minute |
| `market_close_hour` | int | 0-23 | 16 | Market close hour (ET) |
| `market_close_minute` | int | 0-59 | 0 | Market close minute |
| `pre_close_minute` | int | 0-59 | 50 | Pre-close check start (e.g., 15:50 ET) |

**US Market:** 9:30 AM - 4:00 PM ET

### Trading Sessions

Sessions use **minutes from midnight** (ET):
- 9:30 AM = 570 minutes
- 4:00 PM = 960 minutes

**Default Sessions:**

| Session | Start | End | Interval | Description |
|---------|-------|-----|----------|-------------|
| `morning` | 575 (9:35) | 660 (11:00) | 3 min | Volatile period - scan every 3 min |
| `midday` | 660 (11:00) | 840 (14:00) | 5 min | Normal period - scan every 5 min |
| `afternoon` | 840 (14:00) | 930 (15:30) | 5 min | Normal period - scan every 5 min |
| `preclose` | 930 (15:30) | 960 (16:00) | 0 | No continuous scan - manual only |

**Interval = 0:** No continuous scanning (manual triggers only)

**Custom Session Example:**
```yaml
sessions:
  custom_morning:
    start: 570    # 9:30 AM
    end: 600      # 10:00 AM
    interval: 2   # Scan every 2 minutes
    label: "Early Morning"
```

---

## Regime Detection

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `regime_filter_enabled` | bool | - | true | Enable SPY regime filter |
| `regime_sma_period` | int | > 0 | 20 | SMA period for regime check |
| `regime_rsi_min` | float | 0-100 | 40 | Min RSI for BULL confirmation |
| `regime_return_5d_min` | float | -100 to 100 | -2.0 | Min 5-day return (%) for BULL |
| `regime_vix_max` | float | > 0 | 30.0 | Max VIX for trading (< 30 = OK) |

**Regime Logic:**
```
SPY > SMA20 = BULL → Trade normally
SPY < SMA20 = BEAR → Skip ALL new entries (protect capital)
```

**Impact:**
- BULL regime: +5.5%/month, DD 8.9%, WR 49%
- BEAR regime: Capital preservation (no new trades)

**Critical:** VIX < 30 filter = BEAR survival +109% (backtest proven)

---

## Sector Scoring

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `sector_bull_threshold` | float | -100 to 100 | 3.0 | > +N% = BULL sector |
| `sector_bear_threshold` | float | -100 to 100 | -3.0 | < -N% = BEAR sector |
| `sector_bull_bonus` | int | any | 0 | Bonus points for BULL sector (disabled) |
| `sector_bear_penalty` | int | any | 0 | Penalty for BEAR sector (disabled) |
| `sector_sideways_adj` | int | any | 0 | Adjustment for SIDEWAYS sector |

**Note:** v5.5+ sector scoring is DISABLED (backtest showed BEAR sectors perform well)
- Set bonuses/penalties to 0 to disable
- Sector classification still used for diversification

---

## Example Configurations

### Conservative (Low Risk)

**Goal:** Minimize drawdown, accept lower returns

```yaml
rapid_rotation:
  # Tight SL (cut losses fast)
  min_sl_pct: 2.0
  max_sl_pct: 2.5

  # Wide TP (let winners run)
  min_tp_pct: 6.0
  max_tp_pct: 12.0

  # Small positions
  max_positions: 3
  position_size_pct: 0.5      # 0.5% per trade
  risk_budget_pct: 0.5        # 0.5% risk per trade

  # Strict filters
  min_score: 90               # High quality only
  min_atr_pct: 2.0            # Moderate volatility

  # Conservative risk limits
  daily_loss_limit_pct: 2.0   # Stop at -2%
  max_consecutive_losses: 3   # Circuit breaker at 3
```

**Expected:**
- CAGR: 15-20%
- Max DD: 5-8%
- Win Rate: 65-70%

### Balanced (Recommended)

**Goal:** Balance risk and returns

```yaml
rapid_rotation:
  # Balanced SL/TP
  min_sl_pct: 2.0
  max_sl_pct: 2.5
  min_tp_pct: 4.0
  max_tp_pct: 8.0

  # Moderate positions
  max_positions: 5
  position_size_pct: 1.0      # 1% per trade
  risk_budget_pct: 1.0        # 1% risk per trade

  # Balanced filters
  min_score: 85
  min_atr_pct: 2.5

  # Standard risk limits
  daily_loss_limit_pct: 5.0
  max_consecutive_losses: 5
```

**Expected:**
- CAGR: 20-25%
- Max DD: 8-12%
- Win Rate: 60-65%

### Aggressive (High Risk)

**Goal:** Maximize returns, accept higher drawdown

```yaml
rapid_rotation:
  # Wider SL (give room to run)
  min_sl_pct: 2.5
  max_sl_pct: 4.0

  # Higher TP targets
  min_tp_pct: 8.0
  max_tp_pct: 15.0

  # More positions
  max_positions: 8
  position_size_pct: 2.0      # 2% per trade
  risk_budget_pct: 2.0        # 2% risk per trade

  # Relaxed filters
  min_score: 75
  min_atr_pct: 3.0            # High volatility

  # Looser risk limits
  daily_loss_limit_pct: 10.0
  max_consecutive_losses: 7
```

**Expected:**
- CAGR: 30-40%
- Max DD: 15-20%
- Win Rate: 50-55%

⚠️ **Warning:** Aggressive settings increase risk significantly. Only use with proper risk management and emotional discipline.

---

## Validation Rules

### Critical Rules (Auto-Enforced)

All configurations are validated on load. Invalid configs will raise `ValueError` with clear error messages.

**SL/TP Logic:**
```
✅ VALID:   min_sl=2.0, max_sl=2.5, min_tp=4.0, max_tp=8.0
           (TP > SL, ranges valid)

❌ INVALID: min_sl=2.0, max_sl=2.5, min_tp=2.0, max_tp=4.0
           ERROR: "min_tp_pct (2.0%) must be > max_sl_pct (2.5%)"

❌ INVALID: min_sl=3.0, max_sl=2.0
           ERROR: "min_sl_pct (3.0%) must be < max_sl_pct (2.0%)"
```

**Position Sizing:**
```
✅ VALID:   position_size=30%, max_position=50%
           (base <= max)

❌ INVALID: position_size=60%, max_position=50%
           ERROR: "position_size_pct (60%) must be <= max_position_pct (50%)"
```

**PDT Reserve:**
```
✅ VALID:   pdt_day_trade_limit=3, pdt_reserve=1
           (reserve < limit)

❌ INVALID: pdt_day_trade_limit=3, pdt_reserve=5
           ERROR: "pdt_reserve (5) cannot be > pdt_day_trade_limit (3)"
```

### Warning Rules (Best Practices)

These don't block loading but log warnings:

| Condition | Warning | Recommendation |
|-----------|---------|----------------|
| `max_positions` > 20 | Over-diversification | Reduce to 5-10 for focused trading |
| `max_sl_pct` > 10% | Excessive risk | Cap at 5% for risk management |
| `max_hold_days` > 30 | Not rapid rotation | Use 5-15 days for rapid strategy |
| `min_atr_pct` > 10% | Too restrictive | Lower to 2-5% to include more stocks |
| `risk_budget_pct` > 5% | High per-trade risk | Recommended: 0.5-2% per trade |

### Common Mistakes

**Mistake 1: TP < SL**
```yaml
❌ min_tp_pct: 2.0
   max_sl_pct: 3.0
# ERROR: TP target less than SL - guaranteed negative R:R
```

**Fix:**
```yaml
✅ min_tp_pct: 5.0     # At least 2x SL
   max_sl_pct: 2.5
```

**Mistake 2: Tight SL + Aggressive Position Size**
```yaml
❌ max_sl_pct: 1.0      # Very tight
   position_size_pct: 50%  # Large position
# WARNING: Slippage will exceed SL, excessive risk per position
```

**Fix:**
```yaml
✅ max_sl_pct: 2.5      # Reasonable SL
   position_size_pct: 10%  # Moderate position
```

**Mistake 3: Reserve > Day Trade Limit**
```yaml
❌ pdt_day_trade_limit: 3
   pdt_reserve: 4
# ERROR: Cannot reserve more than available
```

**Fix:**
```yaml
✅ pdt_day_trade_limit: 3
   pdt_reserve: 1         # Reserve 1, use 2
```

---

## Config Validation Tool

### Check Your Config

```bash
# Validate current config
python scripts/config_tools.py validate

# Validate specific file
python scripts/config_tools.py validate --file config/custom.yaml

# Show all parameters
python scripts/config_tools.py dump --format text

# Export as JSON
python scripts/config_tools.py dump --format json > my_config.json
```

### Test Changes

```python
# Test config in Python
from config.strategy_config import RapidRotationConfig

try:
    config = RapidRotationConfig.from_yaml('config/trading.yaml')
    print("✅ Config valid!")
except ValueError as e:
    print(f"❌ Invalid config: {e}")
```

---

## Migration Guide

### From v6.9 → v6.10.1

**New Parameters:**
- `pdt_reserve` - Reserve day trades for emergencies (default: 1)

**Deprecated:**
- `PDTConfig` class - Use `RapidRotationConfig` directly

**Action Required:**
1. Add to `config/trading.yaml`:
   ```yaml
   pdt_reserve: 1
   ```

2. Update PDT initialization:
   ```python
   # OLD (deprecated)
   from pdt_smart_guard import PDTConfig
   config = PDTConfig(max_day_trades=3, ...)

   # NEW (recommended)
   from config.strategy_config import RapidRotationConfig
   config = RapidRotationConfig.from_yaml('config/trading.yaml')
   ```

---

## Support

**Documentation:**
- Config Schema (this file)
- Migration Guide: `docs/MIGRATION_GUIDE.md`
- Strategy Spec: `docs/CANDLESTICK_STRATEGY_SPEC.md`

**Validation:**
- Test suite: `tests/test_config_integration.py`
- Tools: `scripts/config_tools.py`

**Questions?**
- Check `CONFIG_SCHEMA.md` first
- Run validation tool
- Review example configurations above

---

**Last Updated:** 2026-02-09
**Version:** v6.10.1
**Status:** ✅ Production Ready
