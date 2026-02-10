# 📝 Naming Convention - Stock Analyzer Project

## 🎯 Purpose

This document establishes **ONE standard name** for each core concept across the entire codebase.
Following these conventions ensures consistency, readability, and maintainability.

**Rule:** Use the names defined here **everywhere** - no exceptions, no variants.

---

## 🔑 Core Trading Concepts

### Stop Loss
```python
# ✅ STANDARD (use everywhere)
stop_loss          # Variable/parameter name
initial_stop_loss  # SL at entry (never changes)
current_stop_loss  # Current SL (can be trailed)

# ❌ DON'T USE (deprecated)
sl, SL, stop_price, stoploss, STOP_LOSS, Sl, StopLoss
```

**Rationale:** `stop_loss` is clear, widely understood, follows Python snake_case convention.

---

### Take Profit
```python
# ✅ STANDARD (use everywhere)
take_profit          # Variable/parameter name
initial_take_profit  # TP at entry
current_take_profit  # Current TP (if dynamic)

# ❌ DON'T USE (deprecated)
tp, TP, target, TARGET, takeprofit, TAKE_PROFIT, tP, Target
```

**Rationale:** `take_profit` is explicit and clear. `tp` is too cryptic for new developers.

---

### Quantity (Position Size)
```python
# ✅ STANDARD (use everywhere)
qty                # Short, clear, industry standard
shares             # Alias (acceptable in some contexts)

# ❌ DON'T USE (deprecated)
quantity, size, position_size, Qty, Quantity, SIZE, Size, POSITION_SIZE
```

**Rationale:** `qty` is short, clear, and standard in trading industry. Use `shares` only when specifically referring to stock shares (not forex/crypto).

---

### Entry Price
```python
# ✅ STANDARD (use everywhere)
entry_price        # Price at which position was opened

# ❌ DON'T USE (deprecated)
entry, buy_price, purchase_price, ENTRY, Entry
```

**Rationale:** `entry_price` is explicit and unambiguous.

---

### Exit Price
```python
# ✅ STANDARD (use everywhere)
exit_price         # Price at which position was closed
close_price        # Alias for market close price (OHLC data)

# ❌ DON'T USE (deprecated)
sell_price, exit, EXIT
```

---

### Current Price
```python
# ✅ STANDARD (use everywhere)
current_price      # Latest market price
last_price         # Alias (acceptable from broker APIs)

# ❌ DON'T USE (deprecated)
price, current, latest_price, curr_price
```

---

### Profit & Loss
```python
# ✅ STANDARD (use everywhere)
pnl               # Profit and Loss (dollar amount)
pnl_pct           # P&L as percentage
unrealized_pnl    # Open position P&L
realized_pnl      # Closed position P&L

# ❌ DON'T USE (deprecated)
profit, loss, gain, pl, PL, profit_loss
```

**Rationale:** `pnl` is industry standard, widely recognized.

---

### Position
```python
# ✅ STANDARD (use everywhere)
position          # A trading position
positions         # Dictionary/list of positions

# ❌ DON'T USE (deprecated)
pos, trade, holding
```

---

### Symbol / Ticker
```python
# ✅ STANDARD (use everywhere)
symbol            # Stock ticker symbol (e.g., "AAPL")

# ❌ DON'T USE (deprecated)
ticker, stock, sym, SYMBOL
```

---

## 📊 Technical Indicators

### ATR (Average True Range)
```python
# ✅ STANDARD
atr               # ATR value (absolute)
atr_pct           # ATR as percentage of price

# ❌ DON'T USE
ATR, average_true_range
```

---

### Moving Averages
```python
# ✅ STANDARD
sma_20            # Simple Moving Average (period)
ema_5             # Exponential Moving Average (period)

# ❌ DON'T USE
ma, MA, moving_average, sma20, ema5
```

---

### RSI (Relative Strength Index)
```python
# ✅ STANDARD
rsi               # RSI value
rsi_14            # RSI with specific period

# ❌ DON'T USE
RSI, relative_strength_index
```

---

## 🔧 Code Structure

### Functions/Methods
```python
# ✅ STANDARD: snake_case for functions
def calculate_stop_loss():
def get_current_price():
def update_position():

# ❌ DON'T USE: camelCase
def calculateStopLoss():
def getCurrentPrice():
```

---

### Classes
```python
# ✅ STANDARD: PascalCase for classes
class PositionManager:
class SLTPCalculator:
class RapidRotationConfig:

# ❌ DON'T USE: snake_case or camelCase
class position_manager:
class slTPCalculator:
```

---

### Constants
```python
# ✅ STANDARD: UPPER_SNAKE_CASE for constants
MAX_POSITIONS = 5
MIN_STOP_LOSS_PCT = 2.0

# ❌ DON'T USE: lowercase or mixed
max_positions = 5
MaxPositions = 5
```

---

### Private Methods
```python
# ✅ STANDARD: prefix with single underscore
def _calculate_internal():
def _validate_config():

# ❌ DON'T USE: double underscore (unless name mangling needed)
def __calculate():
```

---

## 📁 File Naming

### Python Files
```python
# ✅ STANDARD: snake_case
position_manager.py
sl_tp_calculator.py
auto_trading_engine.py

# ❌ DON'T USE: camelCase or PascalCase
PositionManager.py
slTPCalculator.py
```

---

### Config Files
```python
# ✅ STANDARD: snake_case
trading.yaml
strategy_config.py
rapid_portfolio.json

# ❌ DON'T USE: mixed case
tradingConfig.yaml
StrategyConfig.py
```

---

## 🔄 Migration Guide

### Step 1: Find All Variants
```bash
# Search for all variants
grep -r "stop_loss\|sl\|SL\|stop_price" --include="*.py" src/
```

### Step 2: Replace with Standard Name
```python
# Before
sl = 98.0
SL = entry_price * 0.98
stop_price = 98.0

# After (all become)
stop_loss = 98.0
```

### Step 3: Update All References
- Function parameters
- Class attributes
- Dictionary keys
- JSON/YAML field names
- Comments and docstrings

### Step 4: Update Tests
- Test data
- Assertions
- Mock objects

---

## 📊 Summary Table

| Concept | Standard Name | Deprecated Names |
|---------|---------------|------------------|
| Stop Loss | `stop_loss` | sl, SL, stop_price, stoploss |
| Take Profit | `take_profit` | tp, TP, target, TARGET |
| Quantity | `qty` | quantity, size, position_size |
| Entry Price | `entry_price` | entry, buy_price, ENTRY |
| Exit Price | `exit_price` | sell_price, exit |
| Current Price | `current_price` | price, current, latest_price |
| P&L | `pnl`, `pnl_pct` | profit, loss, gain, pl |
| Position | `position` | pos, trade, holding |
| Symbol | `symbol` | ticker, stock, sym |

---

## ✅ Enforcement

**All new code MUST follow these conventions.**

**Code review checklist:**
- [ ] Uses standard names (no variants)
- [ ] Follows snake_case for functions/variables
- [ ] Follows PascalCase for classes
- [ ] No deprecated names

**Migration timeline:**
- Phase 2.1: Create this document ✅
- Phase 2.2: Refactor core modules (2-3 hours)
- Phase 2.3: Refactor remaining files (1-2 hours)
- Phase 2.4: Update tests (1 hour)

---

## 📚 References

- PEP 8 - Python Style Guide: https://pep8.org/
- Trading terminology standards
- Industry best practices

---

**Last Updated:** 2026-02-09
**Version:** 1.0
**Status:** Active - Enforce in all new code
