# 🚀 Enhanced Features - Quick Start Guide

## 1️⃣ Installation

**No installation needed!** Works with existing setup.

---

## 2️⃣ Basic Usage (30 seconds)

```python
from src.analysis.enhanced_features import analyze_stock

# Analyze any stock
result = analyze_stock(
    symbol="AAPL",
    current_price=175.50,
    entry_zone=(170, 172),
    support=168,
    resistance=180,
    tp1=178,
    tp2=185,
    stop_loss=167,
    rsi=52,
    volume_vs_avg=1.2,
    market_regime="sideways"
)

# See recommendation
print(result["formatted_output"])
```

---

## 3️⃣ Quick Test

```bash
# Run automated test with 3 stocks
python test_enhanced_features.py
```

**Expected output:**
```
Stock      Price      Decision                  Confidence
U          $40.03     WAIT                      60%
AFRM       $73.62     SELL ALL                  85%
CLSK       $15.57     BUY NOW                   85%

✅ ALL TESTS COMPLETED SUCCESSFULLY!
```

---

## 4️⃣ Common Scenarios

### Scenario A: Want to know if I should BUY now?

```python
result = analyze_stock(
    symbol="TSLA",
    current_price=250.00,
    entry_zone=(245, 248),  # Your entry range
    support=242,
    resistance=258,
    tp1=255,
    tp2=265,
    stop_loss=240,
    rsi=45,                  # Current RSI
    volume_vs_avg=1.5,       # 150% of average
    market_regime="sideways"
)

# Get answer
decision = result["features"]["decision_matrix"]["decision"]
print(f"Decision: {decision['action']}")
print(f"Confidence: {decision['confidence']}%")
```

### Scenario B: Already holding, should I SELL?

```python
result = analyze_stock(
    symbol="TSLA",
    current_price=260.00,
    entry_zone=(245, 248),
    support=242,
    resistance=270,
    tp1=265,
    tp2=280,
    stop_loss=240,
    rsi=62,
    volume_vs_avg=0.9,
    market_regime="sideways",

    # ✅ Add position info
    has_position=True,
    signal_date="2025-11-01",  # When you got BUY signal
    shares=100,
    holding_days=5
)

# Get recommendation
decision = result["features"]["decision_matrix"]["decision"]
profit = result["profit_pct"]

print(f"Your Profit: {profit:.2f}%")
print(f"Decision: {decision['action']}")
print(f"Confidence: {decision['confidence']}%")
```

### Scenario C: Custom entry price

```python
result = analyze_stock(
    symbol="NVDA",
    # ... basic params ...
    has_position=True,
    entry_price=450.00,  # ✅ Your actual entry
    shares=50,
    holding_days=10
)
```

---

## 5️⃣ Understanding Output

### Entry Readiness Score

```
75-100 → 🟢 BUY NOW       (All conditions met)
50-74  → 🟡 READY         (Most conditions met)
0-49   → 🔴 WAIT          (Not ready yet)
```

### Decision Confidence

```
85-100% → Very high confidence
70-84%  → High confidence
60-69%  → Moderate confidence
45-59%  → Low confidence
0-44%   → Very low confidence
```

### Decision Actions

```
BUY NOW              → Enter position immediately
READY - Wait         → Wait for better entry
WAIT                 → Not ready, be patient

HOLD                 → Keep position
PARTIAL EXIT         → Sell 50%, keep 50%
SELL ALL             → Exit entire position
```

---

## 6️⃣ Key Features At a Glance

| Feature | What It Does | Key Output |
|---------|--------------|------------|
| Price Monitor | Checks if price is ready to enter | Entry Score (0-100) |
| P&L Tracker | Calculates profit automatically | Profit % + Progress bars |
| Trailing Stop | Recommends when to move SL | New SL price |
| Short Interest | Checks squeeze potential | LOW/MEDIUM/HIGH |
| Decision Matrix | Combines everything | BUY/SELL/HOLD |
| Risk Alerts | Warns of deteriorating conditions | Active warnings |

---

## 7️⃣ Tips & Tricks

### ✅ DO:
- Use real RSI from your charts
- Provide actual volume ratio (current / 20-day avg)
- Set `signal_date` for realistic entry price
- Check all 6 features, not just decision

### ❌ DON'T:
- Don't blindly follow recommendations
- Don't ignore your own analysis
- Don't use without understanding outputs
- Don't forget to set stop loss!

---

## 8️⃣ Troubleshooting

### "Cannot import analyze_stock"
```bash
# Make sure you're in project root
cd stock-analyzer
python  # then import
```

### "No data found for symbol"
```python
# Check Yahoo Finance ticker
# Some tickers may have different symbols
```

### "TypeError: missing required argument"
```python
# Check you have all required params:
# current_price, entry_zone, support, resistance,
# tp1, tp2, stop_loss, rsi, volume_vs_avg, market_regime
```

---

## 9️⃣ Advanced Usage

### Access Individual Features

```python
result = analyze_stock(...)

# Get specific feature
monitor = result["features"]["price_monitor"]
pnl = result["features"]["pnl_tracker"]
trailing = result["features"]["trailing_stop"]

# Use the data
print(f"Entry Score: {monitor['readiness']['score']}")
print(f"Profit: {pnl['current']['profit_pct']:.2f}%")
print(f"New SL: ${trailing['recommended_sl']:.2f}")
```

### Multiple Stocks Comparison

```python
stocks = ["AAPL", "TSLA", "NVDA"]
results = []

for symbol in stocks:
    result = analyze_stock(
        symbol=symbol,
        # ... params ...
    )
    results.append((symbol, result))

# Compare
for symbol, result in results:
    decision = result["features"]["decision_matrix"]["decision"]
    print(f"{symbol}: {decision['action']} ({decision['confidence']}%)")
```

---

## 🔟 Full Example

```python
from src.analysis.enhanced_features import analyze_stock

# Complete example with all features
result = analyze_stock(
    # === Required ===
    symbol="AAPL",
    current_price=175.50,
    entry_zone=(170, 172),
    support=168,
    resistance=180,
    tp1=178,
    tp2=185,
    stop_loss=167,
    rsi=52,
    volume_vs_avg=1.2,
    market_regime="sideways",

    # === Optional (Position Tracking) ===
    has_position=True,
    signal_date="2025-11-05",
    shares=100,
    holding_days=3,

    # === Optional (Advanced) ===
    entry_price=172.00,        # Override auto-detection
    selling_pressure=45.0,      # 0-100
    current_atr=3.5,
    entry_atr=2.8,
    target_hold_days=14
)

# === Print Full Report ===
print(result["formatted_output"])

# === Or Extract Specific Info ===
decision = result["features"]["decision_matrix"]["decision"]
pnl = result["features"]["pnl_tracker"]
short = result["features"]["short_interest"]

print(f"\n🎯 Quick Summary:")
print(f"  Decision: {decision['action']}")
print(f"  Confidence: {decision['confidence']}%")
print(f"  Profit: {result['profit_pct']:.2f}%")
print(f"  Progress to TP1: {pnl['targets']['tp1']['progress_pct']:.0f}%")
print(f"  Short Interest: {short['short_interest']['percentage']:.1f}%")
```

---

## 📚 More Info

- **Full Docs**: `ENHANCED_FEATURES_README.md`
- **Summary**: `ENHANCED_FEATURES_SUMMARY.md`
- **Demo**: Run `python demo_enhanced_features.py`
- **Tests**: Run `python test_enhanced_features.py`

---

## 🆘 Need Help?

1. Read the error message carefully
2. Check `ENHANCED_FEATURES_README.md`
3. Look at examples in `test_enhanced_features.py`
4. All functions have docstrings

---

**Ready to use in 30 seconds!** 🚀

*Version 1.0.0 - November 2025*
