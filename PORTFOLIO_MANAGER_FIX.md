# Portfolio Manager Fix - Trailing Stop Improvement

**วันที่**: 12 มกราคม 2026
**ปัญหา**: Trailing Stop เริ่มทำงานช้าเกินไป (>5% เท่านั้น)
**ผลกระทบ**: Big losers ที่เคยกำไร 0.45-2.74% ไม่ได้ถูกป้องกัน

---

## 🐛 ปัญหาที่พบ

### 1. Threshold สูงเกินไป (>5%)

**โค้ดปัจจุบัน** (`advanced_exit_rules.py` บรรทัด 116):
```python
if highest_price > entry_price * 1.05:  # ต้องกำไร >5% ก่อน trailing stop จะทำงาน
    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
    if drawdown_from_peak <= self.rules['trailing_stop']:  # -3%
        return True, 'TRAILING_STOP', current_price
```

**ปัญหา**:
- NVDA เคยกำไร +0.45% → Trailing stop ไม่ทำงาน → ขาดทุน -12.07%
- SNOW เคยกำไร +2.74% → Trailing stop ไม่ทำงาน → ขาดทุน -18.84%
- **รวม 2 ตัว ขาดทุน -30.91%** ที่ป้องกันได้!

---

## ✅ การแก้ไข

### Option 1: ลด Threshold เป็น 2% (แนะนำ!)

```python
# แก้จาก 1.05 (5%) → 1.02 (2%)
if highest_price > entry_price * 1.02:  # เริ่ม trailing stop เมื่อกำไร >2%
    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
    if drawdown_from_peak <= self.rules['trailing_stop']:  # -3%
        return True, 'TRAILING_STOP', current_price
```

**ผลลัพธ์**:
- NVDA +0.45% → ยังไม่ทำงาน (< 2%) ❌
- SNOW +2.74% → ทำงาน! ขายที่ ~break even ✅
- AVGO +6.24% → ทำงาน! ขายที่ ~+3% ✅

**ข้อดี**:
- ป้องกัน SNOW (-18.84% → ~0%)
- ป้องกัน AVGO (-14.64% → ~+3%)
- **ลดขาดทุน ~30%!**

**ข้อเสีย**:
- NVDA ยังไม่ได้รับการป้องกัน (กำไรแค่ 0.45%)

---

### Option 2: ใช้ Tiered Trailing Stop (ยืดหยุ่นกว่า)

```python
# Tiered system: ยิ่งกำไรมาก trailing stop ยิ่งใกล้
if highest_price > entry_price * 1.10:  # กำไร >10%
    trailing_pct = -3.0  # Tight trailing
elif highest_price > entry_price * 1.05:  # กำไร >5%
    trailing_pct = -4.0  # Moderate trailing
elif highest_price > entry_price * 1.02:  # กำไร >2%
    trailing_pct = -5.0  # Loose trailing
else:
    trailing_pct = None  # No trailing yet

if trailing_pct:
    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
    if drawdown_from_peak <= trailing_pct:
        return True, 'TRAILING_STOP', current_price
```

**ผลลัพธ์**:
- SNOW +2.74% → trailing -5% → ยังกำไร (~0% เมื่อลง 2.74%)
- AVGO +6.24% → trailing -4% → ขายที่ +2% เมื่อลง 4%
- ยืดหยุ่นมากขึ้น!

---

### Option 3: Breakeven Protection (ป้องกันทุกกำไร)

```python
# เริ่ม trailing stop ทันทีที่กำไร!
if highest_price > entry_price:  # กำไรเท่าไหร่ก็ได้
    # คำนวณ trailing stop แบบ dynamic
    profit_pct = ((highest_price - entry_price) / entry_price) * 100

    if profit_pct >= 5:
        trailing_pct = -3.0  # Tight
    elif profit_pct >= 2:
        trailing_pct = -4.0  # Moderate
    else:
        trailing_pct = -profit_pct + 0.5  # Break even + 0.5%

    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
    if drawdown_from_peak <= trailing_pct:
        return True, 'TRAILING_STOP', current_price
```

**ผลลัพธ์**:
- NVDA +0.45% → trailing -(0.45-0.5) = break even → ขายที่ ~0% ✅
- SNOW +2.74% → trailing -4% → ขายที่ ~break even ✅
- AVGO +6.24% → trailing -3% → ขายที่ +3% ✅
- **ป้องกันได้ทุกตัว!**

**ข้อดี**:
- ป้องกันทุก loser ที่เคยกำไร (100%!)
- Break even protection

**ข้อเสีย**:
- อาจขายเร็วเกินไปบางทีถ้าหุ้นแกว่งเล็กน้อย

---

## 🏆 คำแนะนำ (เรียงตามความเหมาะสม)

### 🥇 แนะนำ #1: Option 3 - Breakeven Protection
**เหมาะกับ**: v4.2 Anti-Extended Strategy
**เหตุผล**:
- 100% ของ v4.2 losers เคยกำไรระหว่างทาง
- Break even protection = ไม่ขาดทุน!
- เหมาะกับ philosophy "Better median return"

**ผลลัพธ์ที่คาดหวัง**:
- 16 losers → 0-5 losers
- Win rate: 66% → 80-85%
- Median return: +4.80% → +5.5-6.0%

---

### 🥈 แนะนำ #2: Option 1 - Simple 2% Threshold
**เหมาะกับ**: ใครอยากแก้ง่ายๆ
**เหตุผล**:
- แก้แค่เปลี่ยน 1.05 → 1.02
- ป้องกัน SNOW, AVGO (2 ใน 3 big losers)
- ง่าย เข้าใจง่าย

**ผลลัพธ์ที่คาดหวัง**:
- 16 losers → 8-10 losers
- Win rate: 66% → 72-75%
- Median return: +4.80% → +5.2-5.5%

---

### 🥉 แนะนำ #3: Option 2 - Tiered System
**เหมาะกับ**: ใครอยากความยืดหยุ่น
**เหตุผล**:
- ให้หุ้นมีพื้นที่แกว่งตามระดับกำไร
- กำไรมากขึ้น = trailing ใกล้ขึ้น
- Balance ระหว่าง protection และ upside

**ผลลัพธ์ที่คาดหวัง**:
- 16 losers → 6-8 losers
- Win rate: 66% → 75-78%
- Median return: +4.80% → +5.3-5.7%

---

## 🔧 Implementation Steps

### Step 1: Backup Current Code
```bash
cp src/advanced_exit_rules.py src/advanced_exit_rules.py.backup
```

### Step 2: Edit advanced_exit_rules.py

แก้บรรทัด 115-120 จาก:
```python
# 3. TRAILING STOP (Lock in profits)
if highest_price > entry_price * 1.05:  # If up 5%+ at some point
    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
    if drawdown_from_peak <= self.rules['trailing_stop']:
        logger.info(f"📉 {symbol}: Trailing stop hit ({drawdown_from_peak:.2f}% from peak)")
        return True, 'TRAILING_STOP', current_price
```

เป็น (Option 3 - Breakeven Protection):
```python
# 3. TRAILING STOP (Breakeven Protection - v4.2 Optimized)
if highest_price > entry_price:  # Protect ANY profit
    profit_pct = ((highest_price - entry_price) / entry_price) * 100

    # Dynamic trailing based on profit level
    if profit_pct >= 5:
        trailing_pct = -3.0  # Tight trailing for big gains
    elif profit_pct >= 2:
        trailing_pct = -4.0  # Moderate trailing
    else:
        # Break even + small buffer (0.5%)
        trailing_pct = min(-1.0, -(profit_pct - 0.5))

    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
    if drawdown_from_peak <= trailing_pct:
        logger.info(f"📉 {symbol}: Trailing stop hit ({drawdown_from_peak:.2f}% from peak of +{profit_pct:.2f}%)")
        return True, 'TRAILING_STOP', current_price
```

### Step 3: Update Documentation
แก้ docstring บรรทัด 32:
```python
# เดิม:
4. Trailing stop: -3% from peak (lock in profits after 5%+ gain)

# ใหม่:
4. Trailing stop: Dynamic (breakeven protection - activates on ANY profit!)
   - Profit <2%: Break even protection
   - Profit 2-5%: -4% trailing
   - Profit >5%: -3% trailing
```

### Step 4: Test

สร้าง test file:
```python
# test_trailing_stop_fix.py
from src.advanced_exit_rules import AdvancedExitRules
import pandas as pd
from datetime import datetime

exit_rules = AdvancedExitRules()

# Test cases จาก v4.2 big losers
test_cases = [
    {
        'symbol': 'NVDA',
        'entry_price': 199.04,
        'highest_price': 199.04 * 1.0045,  # +0.45%
        'current_price': 175.02,
        'expected': 'Should trigger trailing stop at breakeven'
    },
    {
        'symbol': 'SNOW',
        'entry_price': 268.51,
        'highest_price': 268.51 * 1.0274,  # +2.74%
        'current_price': 217.93,
        'expected': 'Should trigger trailing stop around breakeven'
    },
    {
        'symbol': 'AVGO',
        'entry_price': 389.49,
        'highest_price': 389.49 * 1.0624,  # +6.24%
        'current_price': 332.48,
        'expected': 'Should trigger trailing stop around +3%'
    }
]

# Run tests...
```

### Step 5: Backtest
```bash
# รัน backtest กับ v4.2 data
python backtest_v4.2_with_new_trailing.py
```

คาดหวัง:
- Big losers: 3 → 0-1
- Total losers: 16 → 5-8
- Win rate: 66% → 75-85%

---

## 📊 Expected Impact

### Before Fix (v4.2 Current):
- Losers: 16 trades (34.0%)
- Losers avg: -6.66%
- Big losers (< -10%): 3 trades
- Median return: +4.80%

### After Fix (v4.2 + Trailing Stop Fix):
- Losers: 5-8 trades (10-15%)
- Losers avg: -3.0% to -4.0%
- Big losers (< -10%): 0-1 trades
- **Median return: +5.5% to +6.5%** ✅

### Impact on Specific Cases:
| Stock | Before | After | Improvement |
|-------|--------|-------|-------------|
| AVGO  | -14.64% | ~+3.0% | **+17.64%** |
| NVDA  | -12.07% | ~0.0% | **+12.07%** |
| SNOW  | -18.84% | ~0.0% | **+18.84%** |
| **Total** | **-45.55%** | **~+3%** | **+48.55%** |

---

## ⚠️ Potential Issues & Solutions

### Issue 1: ขายเร็วเกินไปในหุ้นที่แกว่ง
**Solution**: ใช้ Option 2 (Tiered) แทน Option 3

### Issue 2: Break even protection อาจทำให้พลาด upside
**Solution**:
- เพิ่ม buffer 0.5% (ในโค้ดมีอยู่แล้ว)
- หรือใช้ 1% buffer สำหรับกำไร < 2%

### Issue 3: ต้องมีข้อมูล highest_price ที่ถูกต้อง
**Solution**:
- Portfolio Manager ต้อง update highest_price ทุกวัน
- เช็คว่า update_positions() ทำงานถูกต้อง

---

## 🎯 Conclusion

**Problem**: Trailing Stop threshold (5%) สูงเกินไป
**Root Cause**: พลาด losers ที่เคยกำไร 0.45-2.74%
**Solution**: Breakeven Protection (Option 3)
**Expected Result**: Win rate 66% → 80%+, Median +4.80% → +6.0%+

**Status**: ⏳ รอ implement และ test
**Priority**: 🔥 HIGH (ป้องกันขาดทุนหนักได้!)
