# 🔧 Refactoring Plan - Fix Inconsistencies & Improve Extensibility

## 📊 Problems Found (From Code Audit)

### ❌ Problem 1: Broker Integration Inconsistency

**Current State:**
```
RapidPortfolioManager:
  __init__(broker=None)  ✓ Constructor param

PDTSmartGuard:
  __init__(broker=None)  ✓ Constructor param
  set_broker(broker)     ✓ Setter method
  → TWO PATTERNS! Confusing!

AutoTradingEngine:
  self.broker = broker (hardcoded)
  → 40 direct broker calls
  → No abstraction

Screener:
  → NO broker support at all
```

**Issues:**
- ❌ Inconsistent: 3 different patterns
- ❌ Tight coupling: 40+ direct broker calls
- ❌ Hard to test: Must mock broker everywhere
- ❌ No fallback: Broker down = system down

---

### ❌ Problem 2: Configuration Scattered

**Current State:**
```
Screener:          14 hardcoded constants
Portfolio Manager: 11 hardcoded constants
Engine:            8 hardcoded constants
Trading Safety:    7 hardcoded constants
config/trading.yaml
rapid_portfolio.json
Environment variables
```

**Issues:**
- ❌ No single source of truth
- ❌ Hard to change: Edit 4 files to change SL%
- ❌ Can't reload: Restart app to change config
- ❌ Duplicate values: Same constant in multiple files

**Example:**
```python
# screeners/rapid_rotation_screener.py
MIN_SL_PCT = 2.0
MAX_SL_PCT = 4.0

# rapid_portfolio_manager.py
SL_MIN_PCT = 2.0
SL_MAX_PCT = 4.0

# Same values, different names! 😱
```

---

### ❌ Problem 3: Data Fetching Mixed Patterns

**Current State:**
```python
# Screener: Direct yfinance
import yfinance as yf
ticker = yf.Ticker(symbol)
price = ticker.history()['Close'][-1]

# Portfolio Manager: Mixed broker + yfinance
if self.broker:
    quote = self.broker.get_snapshot(symbol)
    price = quote.last
else:
    price = yf.Ticker(symbol).history()['Close'][-1]

# Engine: Direct broker (no fallback)
snapshot = self.broker.get_snapshot(symbol)
price = snapshot.last
```

**Issues:**
- ❌ Inconsistent: 3 different patterns
- ❌ Duplicate code: Fallback logic repeated
- ❌ No abstraction: Can't swap data source
- ❌ Hard to test: Must mock yfinance + broker

---

### ❌ Problem 4: Duplicate Logic

**Found:**
```
SL/TP Calculation:
  • screeners/rapid_trader_filters.py: calculate_dynamic_sl_tp()
  • rapid_portfolio_manager.py: calculate_dynamic_sl()
  • rapid_portfolio_manager.py: calculate_dynamic_tp()
  • auto_trading_engine.py: (inline SL/TP logic)

Price Fetching:
  • rapid_portfolio_manager.py: get_current_price()
  • auto_trading_engine.py: (inline price fetch)
  • screeners/rapid_rotation_screener.py: (inline yfinance)

Position Tracking:
  • auto_trading_engine.py: self.positions (dict)
  • rapid_portfolio_manager.py: self.positions (dict)
  → Which is source of truth?
```

**Issues:**
- ❌ Code duplication: Same logic in 3 places
- ❌ Inconsistent results: Different implementations
- ❌ Hard to maintain: Fix bug in 3 places
- ❌ Multiple sources of truth: positions dict × 2

---

### ❌ Problem 5: No Clear Architecture

**Current:**
```
Component Dependencies (messy):

                  ┌──────────┐
                  │ Engine   │
                  └────┬─────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐  ┌──────────┐  ┌──────────┐
   │Screener │  │Portfolio │  │ Safety   │
   └────┬────┘  └────┬─────┘  └────┬─────┘
        │            │              │
        └────────────┼──────────────┘
                     │
            Circular Dependencies!
```

**Issues:**
- ❌ Circular dependencies
- ❌ No clear layers (data, business, presentation)
- ❌ Hard to test in isolation
- ❌ Can't reuse components

---

## ✅ Refactoring Goals

1. **Single Responsibility** - Each class does ONE thing
2. **Dependency Injection** - Pass dependencies, don't create them
3. **Single Source of Truth** - Config, logic, data in ONE place
4. **Loose Coupling** - Components don't know each other
5. **Testability** - Easy to mock and test

---

## 🎯 Refactoring Priorities (by Impact)

### 🔴 CRITICAL (High Impact, Must Fix)

#### R1: Unify Configuration Management
**Problem:** 40+ constants scattered across 4 files
**Solution:** Single config module
**Impact:** ⭐⭐⭐⭐⭐
**Effort:** 1-2 hours
**Risk:** Low (backward compatible)

```python
# NEW: src/config/strategy_config.py
from dataclasses import dataclass
from typing import Optional
import yaml

@dataclass
class RapidRotationConfig:
    """Single source of truth for all strategy parameters"""
    # Stop Loss / Take Profit
    min_sl_pct: float = 2.0
    max_sl_pct: float = 4.0
    min_tp_pct: float = 4.0
    max_tp_pct: float = 8.0

    # Trailing Stop
    trail_activation_pct: float = 3.0
    trail_lock_pct: float = 80.0

    # Position Management
    max_positions: int = 5
    max_hold_days: int = 5
    position_size_pct: float = 1.0

    # Scoring
    min_score: int = 85
    min_atr_pct: float = 2.5

    @classmethod
    def from_yaml(cls, path: str) -> 'RapidRotationConfig':
        """Load from YAML file"""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data.get('rapid_rotation', {}))

    @classmethod
    def from_dict(cls, data: dict) -> 'RapidRotationConfig':
        """Load from dict"""
        return cls(**data)

# Usage:
config = RapidRotationConfig.from_yaml('config/trading.yaml')
screener = RapidRotationScreener(config=config)
portfolio = RapidPortfolioManager(config=config)
engine = AutoTradingEngine(config=config)
```

**Benefits:**
- ✅ Single source of truth
- ✅ Easy to change (edit YAML, no code changes)
- ✅ Type-safe (dataclass validation)
- ✅ Can reload without restart
- ✅ Easy to test different configs

---

#### R2: Extract SL/TP Calculation Module
**Problem:** Duplicate SL/TP logic in 3 files
**Solution:** Single calculation module
**Impact:** ⭐⭐⭐⭐⭐
**Effort:** 1 hour
**Risk:** Very Low (pure functions)

```python
# NEW: src/strategies/sl_tp_calculator.py
from dataclasses import dataclass
from typing import Tuple

@dataclass
class SLTPResult:
    """Result from SL/TP calculation"""
    stop_loss: float
    take_profit: float
    sl_pct: float
    tp_pct: float
    sl_method: str
    tp_method: str
    risk_reward: float

class SLTPCalculator:
    """
    Single source of truth for SL/TP calculation

    Uses strategy from rapid_trader_filters.py:
    - SL: 1.5×ATR (clamped 2%-4%)
    - TP: 3×ATR (clamped 4%-8%)
    """

    def __init__(self, config: RapidRotationConfig):
        self.config = config

    def calculate(
        self,
        entry_price: float,
        atr: float,
        swing_low: float = None,
        ema5: float = None,
        high_20d: float = None,
        high_52w: float = None
    ) -> SLTPResult:
        """
        Calculate dynamic SL/TP

        This is the ONLY place where SL/TP is calculated.
        All other code must use this module.
        """
        # Import from filters.py (single source)
        from screeners.rapid_trader_filters import calculate_dynamic_sl_tp

        result = calculate_dynamic_sl_tp(
            current_price=entry_price,
            atr=atr,
            swing_low_5d=swing_low or entry_price * 0.98,
            ema5=ema5 or entry_price,
            high_20d=high_20d or entry_price * 1.05,
            high_52w=high_52w or entry_price * 1.10
        )

        return SLTPResult(
            stop_loss=result['stop_loss'],
            take_profit=result['take_profit'],
            sl_pct=result['sl_pct'],
            tp_pct=result['tp_pct'],
            sl_method=result['sl_method'],
            tp_method=result['tp_method'],
            risk_reward=result['risk_reward']
        )

# Usage:
calculator = SLTPCalculator(config)
result = calculator.calculate(
    entry_price=100.0,
    atr=2.5,
    swing_low=98.0
)
print(f"SL: ${result.stop_loss}, TP: ${result.take_profit}")
```

**Benefits:**
- ✅ Single source of truth
- ✅ No duplication
- ✅ Easy to test
- ✅ Consistent results everywhere

---

#### R3: Separate Position Sources of Truth
**Problem:** 2 position dicts (engine, portfolio)
**Solution:** Single PositionManager
**Impact:** ⭐⭐⭐⭐⭐
**Effort:** 2 hours
**Risk:** Medium (need careful migration)

```python
# NEW: src/position_manager.py
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json

@dataclass
class Position:
    """Unified position representation"""
    symbol: str
    entry_date: str
    entry_price: float
    qty: int
    initial_sl: float
    current_sl: float
    take_profit: float
    cost_basis: float
    highest_price: float
    trailing_active: bool
    sl_pct: float
    tp_pct: float
    atr_pct: float
    # Engine-specific
    sl_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None

class PositionManager:
    """
    Single source of truth for positions

    Used by both Engine and Portfolio Manager.
    Persists to rapid_portfolio.json
    """

    def __init__(self, portfolio_file: str):
        self.portfolio_file = portfolio_file
        self.positions: Dict[str, Position] = {}
        self.load()

    def load(self):
        """Load from disk"""
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file) as f:
                data = json.load(f)
            for symbol, pos_data in data.get('positions', {}).items():
                self.positions[symbol] = Position(**pos_data)

    def save(self):
        """Save to disk"""
        data = {
            'positions': {s: asdict(p) for s, p in self.positions.items()},
            'last_updated': datetime.now().isoformat()
        }
        with open(self.portfolio_file, 'w') as f:
            json.dump(data, f, indent=2)

    def add(self, position: Position):
        """Add new position"""
        self.positions[position.symbol] = position
        self.save()

    def remove(self, symbol: str) -> Optional[Position]:
        """Remove position"""
        pos = self.positions.pop(symbol, None)
        if pos:
            self.save()
        return pos

    def get(self, symbol: str) -> Optional[Position]:
        """Get position"""
        return self.positions.get(symbol)

    def all(self) -> List[Position]:
        """Get all positions"""
        return list(self.positions.values())

    def update(self, symbol: str, **kwargs):
        """Update position fields"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            for key, value in kwargs.items():
                if hasattr(pos, key):
                    setattr(pos, key, value)
            self.save()

# Usage:
# Engine and Portfolio share the same instance
pos_manager = PositionManager('rapid_portfolio.json')
engine = AutoTradingEngine(position_manager=pos_manager)
portfolio = RapidPortfolioManager(position_manager=pos_manager)

# Add position
pos = Position(symbol='AAPL', entry_price=100, qty=10, ...)
pos_manager.add(pos)

# Both engine and portfolio see the same data
assert engine.position_manager.get('AAPL') is portfolio.position_manager.get('AAPL')
```

**Benefits:**
- ✅ Single source of truth
- ✅ No sync issues
- ✅ Atomic saves (no partial writes)
- ✅ Easy to query

---

### 🟡 IMPORTANT (Should Fix)

#### R4: Standardize Broker Integration
**Problem:** 3 different patterns
**Solution:** Consistent pattern everywhere
**Impact:** ⭐⭐⭐⭐
**Effort:** 2 hours
**Risk:** Low

**Decision:**
```python
# STANDARD PATTERN (use this everywhere):

class Component:
    def __init__(self, data_manager: DataManager, config: Config):
        self.data_manager = data_manager  # For READ operations
        self.config = config

    # READ operations through DataManager
    def check_something(self):
        price = self.data_manager.get_current_price('AAPL')
        account = self.data_manager.get_account()

    # WRITE operations need broker directly
    def execute(self, broker):
        broker.place_market_buy('AAPL', 10)

# NO MORE:
# - self.broker parameter
# - set_broker() method
# - Direct broker calls for READ
```

**Migration:**
1. Replace `broker` param with `data_manager`
2. Replace `self.broker.get_*` with `self.data_manager.get_*`
3. Keep WRITE operations as function parameters

---

#### R5: Clean Up PDTSmartGuard
**Problem:** Two patterns (constructor + setter)
**Solution:** Remove setter, use constructor only
**Impact:** ⭐⭐⭐
**Effort:** 15 minutes
**Risk:** Very Low

```python
# BEFORE:
guard = PDTSmartGuard()
guard.set_broker(broker)  # ← Remove this pattern

# AFTER:
guard = PDTSmartGuard(data_manager=data_manager)
```

---

### 🟢 NICE TO HAVE (Future)

#### R6: Layer Architecture
**Problem:** Circular dependencies
**Solution:** Clear layers
**Impact:** ⭐⭐⭐⭐
**Effort:** 4-6 hours
**Risk:** High (major refactor)

```
┌─────────────────────────────────────────┐
│ Presentation Layer (UI, API, CLI)       │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ Application Layer (Engine, Orchestration)│
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ Domain Layer (Strategy, Filters, Calc)  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ Infrastructure (DataManager, Broker)    │
└─────────────────────────────────────────┘
```

**Skip for now** - Too complex, low immediate value

---

## 📋 Implementation Order

### Phase 1: Quick Wins (3-4 hours)
1. ✅ R1: Unify Configuration (1-2h) - **HIGHEST IMPACT**
2. ✅ R2: Extract SL/TP Calculator (1h)
3. ✅ R5: Clean PDTSmartGuard (15min)

### Phase 2: Core Improvements (2-3 hours)
4. ✅ R3: Single PositionManager (2h)
5. ✅ R4: Standardize Broker Integration (2h)

### Phase 3: Future (Skip for now)
6. ⏸️ R6: Layer Architecture (4-6h)

---

## 🎯 Expected Results

**Before Refactoring:**
- ❌ 40+ constants scattered
- ❌ 3 SL/TP implementations
- ❌ 2 position sources
- ❌ 3 broker patterns
- ❌ Mixed data fetching

**After Refactoring:**
- ✅ Single config source
- ✅ Single SL/TP calculator
- ✅ Single position manager
- ✅ Consistent data_manager pattern
- ✅ Clean DataManager abstraction

**Benefits:**
- 🎯 Easier to extend (add new strategies)
- 🎯 Easier to test (mock one place)
- 🎯 Easier to maintain (fix once)
- 🎯 More reliable (no inconsistencies)
- 🎯 Better performance (no duplication)

---

## 🚀 Start Here

**Recommended: Start with R1 (Config Management)**

Why?
- Highest impact (affects everything)
- Lowest risk (pure data)
- Fastest (1-2 hours)
- Enables other refactorings

**Ready to start R1?**
