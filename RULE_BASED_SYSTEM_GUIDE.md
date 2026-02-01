# Rule-Based Exit System - Complete Guide

## 🎯 ทำไมต้องใช้ Rule-Based?

### ปัญหาของ Hard-coded Logic:

```python
# ❌ Hard to maintain
if days_held >= 2:
    if len(close_prices) >= 2:
        prev_close = close_prices[-2]
        daily_change = (current_price - prev_close) / prev_close * 100
        if daily_change < -2.0 and pnl_pct < -0.5:  # Magic numbers!
            exit_reason = 'SMART_BREAKING_DOWN'
```

**ปัญหา:**
- 🔴 Magic numbers ซ่อนอยู่ในโค้ด
- 🔴 แก้ threshold ยาก (ต้องหาในโค้ด)
- 🔴 Test แต่ละ rule ไม่ได้
- 🔴 ไม่รู้ว่า rule ไหนได้ผลดี
- 🔴 เพิ่ม rule ใหม่ต้องแก้โค้ดเยอะ

### Solution: Rule-Based System

```python
# ✅ Clear, configurable, testable
rule = RuleConfig(
    name="SMART_BREAKING_DOWN",
    priority=RulePriority.HIGH,
    thresholds={
        'daily_drop': -2.0,      # Tunable!
        'overall_loss': -0.5,    # Tunable!
    },
    conditions={
        'min_days': 2,           # Tunable!
    }
)
```

**ข้อดี:**
- ✅ Threshold ชัดเจน, แก้ง่าย
- ✅ Test แต่ละ rule ได้
- ✅ Track performance ของแต่ละ rule
- ✅ A/B test config ต่างๆ
- ✅ ML optimization ได้

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Exit Rules Engine                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  CRITICAL   │  │    HIGH     │  │   MEDIUM    │    │
│  │   Rules     │  │   Rules     │  │   Rules     │    │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤    │
│  │ TARGET_HIT  │  │ GAP_DOWN    │  │ VOL_COLLAPSE│    │
│  │ HARD_STOP   │  │ BREAKING_DN │  │ FAILED_PUMP │    │
│  │ TRAILING    │  │             │  │ SMA20_BREAK │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                         │
│  Priority Order: CRITICAL → HIGH → MEDIUM → LOW        │
│  First Match Wins                                       │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 การใช้งาน

### 1. Basic Usage

```python
from src.exit_rules_engine import ExitRulesEngine, MarketData

# Initialize engine (loads v5 rules)
engine = ExitRulesEngine()

# Prepare market data
data = MarketData(
    current_price=102.5,
    entry_price=100.0,
    highest_price=103.0,
    close_prices=[100, 101, 102, 102.5],
    open_prices=[100, 101, 102, 102],
    volume_data=[1000, 1200, 900, 800],
    days_held=4
)

# Evaluate rules
exit_reason = engine.evaluate(data, symbol="NVDA")

if exit_reason:
    print(f"Exit signal: {exit_reason}")
else:
    print("Hold position")
```

### 2. Tune Thresholds (ปรับ parameters)

```python
# ลด target จาก 4.0% → 3.5%
engine.update_threshold("TARGET_HIT", "target_pct", 3.5)

# ทำ stop แน่นขึ้น -3.5% → -3.0%
engine.update_threshold("HARD_STOP", "stop_pct", -3.0)

# ทำ gap down sensitive ขึ้น
engine.update_threshold("SMART_GAP_DOWN", "gap_pct", -1.0)
```

### 3. Enable/Disable Rules (A/B Testing)

```python
# ปิด rule ที่ไม่อยากใช้
engine.disable_rule("SMART_MOMENTUM_REVERSAL")
engine.disable_rule("SMART_WEAK_RSI")

# เปิดใหม่ถ้าต้องการ
engine.enable_rule("SMART_MOMENTUM_REVERSAL")
```

### 4. Track Performance

```python
# ดู stats ของแต่ละ rule
stats = engine.get_rule_stats()

for stat in stats:
    print(f"{stat['name']:25} | Fired: {stat['fired_count']:3} | "
          f"Win: {stat['win_rate']:.1f}% | Avg: {stat['avg_pnl']:+.2f}%")
```

Output:
```
TARGET_HIT                | Fired:  42 | Win: 100.0% | Avg: +6.94%
HARD_STOP                 | Fired:  23 | Win:   0.0% | Avg: -6.02%
SMART_GAP_DOWN            | Fired:   2 | Win:   0.0% | Avg: -1.67%
SMART_BREAKING_DOWN       | Fired:  18 | Win:  11.1% | Avg: -2.09%
...
```

**ใช้ data นี้:**
- 🎯 เห็นว่า rule ไหนดี/แย่
- 🎯 ปรับ threshold ของ rule ที่แย่
- 🎯 ปิด rule ที่ไม่ได้ผล

---

## 🔬 Optimization Workflow

### Step 1: Backtest Current Config

```python
# Run backtest with current rules
results = backtest_with_rules_engine(engine)
print(f"Win Rate: {results['win_rate']:.1f}%")
print(f"Avg Loss: {results['avg_loss']:.2f}%")
```

### Step 2: Analyze Rule Performance

```python
stats = engine.get_rule_stats()

# หา rule ที่ทำให้ขาดทุนเยอะ
bad_rules = [s for s in stats if s['avg_pnl'] < -3.0 and s['fired_count'] > 5]

for rule in bad_rules:
    print(f"⚠️  {rule['name']} is causing losses: {rule['avg_pnl']:.2f}%")
    print(f"   Consider tightening thresholds or disabling")
```

### Step 3: Grid Search Optimization

```python
# ทดสอบ threshold combinations
target_options = [3.5, 4.0, 4.5, 5.0]
stop_options = [-3.0, -3.5, -4.0]

best_config = None
best_profit = 0

for target in target_options:
    for stop in stop_options:
        # Clone engine
        test_engine = ExitRulesEngine()
        test_engine.update_threshold("TARGET_HIT", "target_pct", target)
        test_engine.update_threshold("HARD_STOP", "stop_pct", stop)

        # Backtest
        results = backtest_with_rules_engine(test_engine)

        if results['net_profit'] > best_profit:
            best_profit = results['net_profit']
            best_config = (target, stop)

print(f"✅ Best config: Target {best_config[0]}%, Stop {best_config[1]}%")
print(f"   Net Profit: ${best_profit:.0f}")
```

### Step 4: Save Best Config

```python
# Export optimized config
config = engine.export_config()

import json
with open('best_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("✅ Saved best configuration")
```

### Step 5: Load & Use

```python
# Load optimized config
with open('best_config.json', 'r') as f:
    config = json.load(f)

engine = ExitRulesEngine()
engine.import_config(config)

print("✅ Loaded optimized configuration")
```

---

## 🧪 A/B Testing Example

```python
# Config A: Conservative (tight stops, lower target)
config_a = ExitRulesEngine()
config_a.update_threshold("TARGET_HIT", "target_pct", 3.5)
config_a.update_threshold("HARD_STOP", "stop_pct", -3.0)

# Config B: Aggressive (wider stops, higher target)
config_b = ExitRulesEngine()
config_b.update_threshold("TARGET_HIT", "target_pct", 5.0)
config_b.update_threshold("HARD_STOP", "stop_pct", -4.5)

# Backtest both
results_a = backtest_with_rules_engine(config_a)
results_b = backtest_with_rules_engine(config_b)

# Compare
print("Config A (Conservative):")
print(f"  Win Rate: {results_a['win_rate']:.1f}%")
print(f"  Net Profit: ${results_a['net_profit']:.0f}")

print("\nConfig B (Aggressive):")
print(f"  Win Rate: {results_b['win_rate']:.1f}%")
print(f"  Net Profit: ${results_b['net_profit']:.0f}")

# Use winner
winner = config_a if results_a['net_profit'] > results_b['net_profit'] else config_b
```

---

## 📈 ML-Based Optimization (Advanced)

```python
from sklearn.ensemble import RandomForestRegressor
import numpy as np

# Collect training data
X_train = []  # [target, stop, gap_threshold, ...]
y_train = []  # net_profit

for _ in range(100):  # 100 random configs
    # Random thresholds
    target = np.random.uniform(3.0, 5.0)
    stop = np.random.uniform(-4.5, -2.5)
    gap = np.random.uniform(-2.0, -1.0)

    # Create config
    engine = ExitRulesEngine()
    engine.update_threshold("TARGET_HIT", "target_pct", target)
    engine.update_threshold("HARD_STOP", "stop_pct", stop)
    engine.update_threshold("SMART_GAP_DOWN", "gap_pct", gap)

    # Backtest
    results = backtest_with_rules_engine(engine)

    X_train.append([target, stop, gap])
    y_train.append(results['net_profit'])

# Train model
model = RandomForestRegressor()
model.fit(X_train, y_train)

# Find optimal thresholds
best_params = None
best_predicted_profit = 0

for target in np.linspace(3.0, 5.0, 20):
    for stop in np.linspace(-4.5, -2.5, 20):
        for gap in np.linspace(-2.0, -1.0, 10):
            predicted_profit = model.predict([[target, stop, gap]])[0]

            if predicted_profit > best_predicted_profit:
                best_predicted_profit = predicted_profit
                best_params = (target, stop, gap)

print(f"✅ ML-optimized config:")
print(f"   Target: {best_params[0]:.2f}%")
print(f"   Stop: {best_params[1]:.2f}%")
print(f"   Gap: {best_params[2]:.2f}%")
print(f"   Predicted Profit: ${best_predicted_profit:.0f}")
```

---

## 🎯 Benefits Summary

| Feature | Hard-coded | Rule-Based | Benefit |
|---------|-----------|------------|---------|
| **Tune thresholds** | ❌ Edit code | ✅ One line | 10x faster |
| **A/B test configs** | ❌ Copy files | ✅ Export/Import | Easy comparison |
| **Track performance** | ❌ Manual logging | ✅ Auto-tracked | Know what works |
| **Optimize** | ❌ Trial & error | ✅ Grid search / ML | Find optimal faster |
| **Debug** | ❌ Print everywhere | ✅ Rule logs | Clear reasons |
| **Add new rules** | ❌ 50+ lines | ✅ RuleConfig | 10 lines |

---

## 💡 Next Steps

### 1. Integrate with Portfolio Manager (ง่าย!)

```python
# In portfolio_manager_v3.py
from src.exit_rules_engine import ExitRulesEngine, MarketData

class PortfolioManagerV3:
    def __init__(self):
        self.rules_engine = ExitRulesEngine()  # ✅ Use rule engine!

    def update_positions(self):
        for pos in self.portfolio['active']:
            # Prepare data
            data = MarketData(
                current_price=pos['current_price'],
                entry_price=pos['entry_price'],
                highest_price=pos['highest_price'],
                close_prices=close_prices,
                open_prices=open_prices,
                volume_data=volume_data,
                days_held=days_held
            )

            # Evaluate rules
            exit_reason = self.rules_engine.evaluate(data, pos['symbol'])

            if exit_reason:
                exit_positions.append(pos)
```

### 2. Continuous Optimization

```python
# Run monthly optimization
def monthly_optimization():
    # Backtest last month's performance
    engine = ExitRulesEngine()
    results = backtest_last_month(engine)

    # Analyze rule stats
    stats = engine.get_rule_stats()

    # Disable underperforming rules
    for stat in stats:
        if stat['avg_pnl'] < -4.0 and stat['fired_count'] > 10:
            engine.disable_rule(stat['name'])
            print(f"❌ Disabled {stat['name']} (avg pnl: {stat['avg_pnl']:.2f}%)")

    # Save optimized config
    config = engine.export_config()
    save_config(f"config_{datetime.now().strftime('%Y%m')}.json", config)
```

### 3. Market-Adaptive Rules (Advanced)

```python
# Different configs for different market regimes
bull_config = ExitRulesEngine()
bull_config.update_threshold("TARGET_HIT", "target_pct", 5.0)  # Higher target
bull_config.update_threshold("HARD_STOP", "stop_pct", -4.5)    # Wider stop

bear_config = ExitRulesEngine()
bear_config.update_threshold("TARGET_HIT", "target_pct", 3.0)  # Lower target
bear_config.update_threshold("HARD_STOP", "stop_pct", -2.5)    # Tighter stop

# Use appropriate config
if market_regime == 'BULL':
    engine = bull_config
else:
    engine = bear_config
```

---

## 🎉 Conclusion

Rule-Based System > Hard-coded Logic:

✅ **Clearer** - Rules are explicit and documented
✅ **Flexible** - Easy to tune and experiment
✅ **Trackable** - Know which rules work
✅ **Optimizable** - Use ML/grid search
✅ **Maintainable** - No magic numbers in code

**ผลลัพธ์:** ระบบที่ดีขึ้น, optimize ง่ายขึ้น, พัฒนาเร็วขึ้น! 🚀
