# 🎯 Manual Exit Portfolio Manager - คู่มือการใช้งาน

## 💡 แนวคิด

**ปัญหาเดิม:** หุ้นถูกเอาออกอัตโนมัติเมื่อถูก exit rules → หุ้นหาย ไม่เห็นประวัติ

**วิธีแก้ใหม่:** แทนที่จะเอาออกทันที จะ**เปลี่ยนสถานะเป็น "exit_signal"** แล้ว**คุณตัดสินใจเอง**ว่าจะออกหรือไม่

---

## 🔄 ระบบใหม่

### สถานะของหุ้น (3 สถานะ)

1. **`active`** - หุ้นปกติ ยังไม่มี exit signal
2. **`exit_signal`** - มี exit signal แล้ว รอคุณตัดสินใจ ⚠️
3. **`exited`** - ออกแล้ว (ย้ายไปที่ closed)

### ข้อมูล Exit Signal

เมื่อมี exit signal จะบันทึก:
```json
{
  "rule": "TARGET_HIT",
  "detected_date": "2026-01-09 14:30:25",
  "price_at_signal": 104.5,
  "pnl_pct_at_signal": 4.5,
  "pnl_dollar_at_signal": 45.0,
  "days_held": 5,
  "category": "profit",
  "priority": "CRITICAL"
}
```

---

## 🚀 การใช้งาน

### 1. Monitor Positions (ทุกวัน)

```python
from src.portfolio_manager_manual_exit import PortfolioManagerManualExit

# สร้าง manager
manager = PortfolioManagerManualExit('portfolio.json')

# Monitor ทุก positions
summary = manager.monitor_positions(update_signals=True)
```

**Output:**
```
🔍 MONITORING PORTFOLIO POSITIONS
================================================================================

📍 TSLA:
   Entry: $100.00 on 2026-01-01
   Status: active
   Current: $104.50 (+4.50%)
   PnL: $+45.00 | Days: 8
   🚨 EXIT SIGNAL: TARGET_HIT
   ⚠️  Status changed to: exit_signal

📍 AAPL:
   Entry: $150.00 on 2026-01-05
   Status: active
   Current: $152.30 (+1.53%)
   PnL: $+15.33 | Days: 4
   ✅ Active (no exit signal)

================================================================================
📊 SUMMARY
================================================================================
Total Positions: 2
  Active (no signal): 1
  Exit signals (new): 1
  Exit signals (existing): 0

⚠️  NEW EXIT SIGNALS DETECTED!
   1 positions need your attention
   Use 'list_exit_signals()' to see details
   Use 'manual_exit()' to close positions
```

---

### 2. ดู Exit Signals ทั้งหมด

```python
# แสดงรายการทั้งหมดที่มี exit signal
manager.list_exit_signals()
```

**Output:**
```
================================================================================
🚨 POSITIONS WITH EXIT SIGNALS
================================================================================

1. TSLA
   Entry: $100.00 on 2026-01-01
   Exit Signal: TARGET_HIT (CRITICAL)
   Detected: 2026-01-09 14:30:25
   Price: $104.50
   PnL: +4.50% ($+45.00)
   Days Held: 8

2. NVDA
   Entry: $500.00 on 2025-12-28
   Exit Signal: HARD_STOP (CRITICAL)
   Detected: 2026-01-09 10:15:33
   Price: $481.50
   PnL: -3.70% ($-185.00)
   Days Held: 12

================================================================================
💡 Actions:
   - Review each position
   - Use manual_exit('SYMBOL') to close position
   - Use clear_exit_signal('SYMBOL') to ignore signal and keep holding
================================================================================
```

---

### 3. ตัดสินใจแต่ละตัว

#### Option A: ออกจริง (Exit)

```python
# ออก TSLA (ใช้ราคาปัจจุบัน)
manager.manual_exit('TSLA')

# หรือระบุราคาเอง
manager.manual_exit('TSLA', exit_price=105.0)
```

**Output:**
```
================================================================================
✅ CLOSED POSITION: TSLA
================================================================================
Entry: $100.00 on 2026-01-01
Exit:  $104.50 on 2026-01-09
PnL:   +4.50% ($+45.00)
Days:  8
Exit Signal: TARGET_HIT
================================================================================
```

#### Option B: ไม่ออก (ถือต่อ)

```python
# เคลียร์ exit signal และถือต่อ
manager.clear_exit_signal('AAPL')
```

**Output:**
```
🔄 Clearing exit signal for AAPL
   Previous signal: TRAILING_STOP
   ✅ Status changed to: active
   Continuing to hold AAPL
```

---

### 4. ดู Portfolio Summary

```python
manager.show_portfolio()
```

**Output:**
```
================================================================================
📊 PORTFOLIO SUMMARY
================================================================================

📈 Active Positions: 3
   Active (no signal): 1
   Exit signals: 2

⚠️  Exit signals pending:
   - TSLA: TARGET_HIT
   - NVDA: HARD_STOP

📉 Closed Positions: 5

📊 Statistics:
   Total Trades: 5
   Win Rate: 60.0%
   Total PnL: $+250.00
   Avg Winner: $+125.00
   Avg Loser: $-50.00

================================================================================
```

---

## 📅 Workflow ประจำวัน

### เช้า (ก่อนตลาดเปิด)

```python
manager = PortfolioManagerManualExit('portfolio.json')

# 1. Monitor positions
summary = manager.monitor_positions(update_signals=True)

# 2. ดู exit signals ใหม่
if summary['exit_signals_new'] > 0:
    manager.list_exit_signals()
```

### ตอนเทรด

```python
# ตัดสินใจแต่ละตัว

# ถ้าเห็นด้วย → Exit
manager.manual_exit('TSLA')  # ถึงเป้ากำไร
manager.manual_exit('NVDA')  # ตัด stop loss

# ถ้าไม่เห็นด้วย → Clear signal และถือต่อ
manager.clear_exit_signal('AAPL')  # ยังอยากถือต่อ
```

### เย็น (หลังตลาดปิด)

```python
# Check portfolio summary
manager.show_portfolio()
```

---

## 🎯 ตัวอย่างสถานการณ์

### สถานการณ์ที่ 1: กำไรถึงเป้า

```
วันที่ 1: ซื้อ TSLA $100
วันที่ 8: TSLA $104.50 (กำไร +4.5%)
→ System detect: TARGET_HIT
→ Status: active → exit_signal

คุณตัดสินใจ:
Option A: ออกเลย (ถึงเป้าแล้ว) → manual_exit('TSLA')
Option B: ถือต่อ (คิดว่าจะขึ้นต่อ) → clear_exit_signal('TSLA')
```

### สถานการณ์ที่ 2: ขาดทุนถึง Stop Loss

```
วันที่ 1: ซื้อ NVDA $500
วันที่ 12: NVDA $481.50 (ขาดทุน -3.7%)
→ System detect: HARD_STOP
→ Status: active → exit_signal

คุณตัดสินใจ:
Option A: ตัดเลย (ป้องกันขาดทุนเพิ่ม) → manual_exit('NVDA')
Option B: ถือต่อ (คิดว่าจะฟื้น) → clear_exit_signal('NVDA')
   ⚠️ Risk: อาจขาดทุนเพิ่มถ้าไม่ฟื้น!
```

### สถานการณ์ที่ 3: Gap Down แรง

```
วันที่ 1: ซื้อ AMD $120
วันที่ 5: AMD เปิดตลาด $116 (gap down -3.3%), ขาดทุนรวม -3.3%
→ System detect: SMART_GAP_DOWN
→ Status: active → exit_signal

คุณตัดสินใจ:
Option A: ออกทันที (สัญญาณไม่ดี) → manual_exit('AMD')
Option B: ดูก่อน 1 วัน (อาจฟื้น) → clear_exit_signal('AMD')
   แล้วมา monitor วันพรุ่งนี้อีกรอบ
```

### สถานการณ์ที่ 4: Trailing Stop

```
วันที่ 1: ซื้อ GOOGL $140
วันที่ 10: GOOGL peak $155 (กำไร +10.7%)
วันที่ 15: GOOGL $149.58 (ตกจาก peak -3.5%)
→ System detect: TRAILING_STOP
→ Status: active → exit_signal

คุณตัดสินใจ:
Option A: ออก (ล็อคกำไร +6.8%) → manual_exit('GOOGL')
Option B: ถือต่อ (คิดว่าจะกลับขึ้น) → clear_exit_signal('GOOGL')
```

---

## 📊 เปรียบเทียบระบบเก่า vs ใหม่

| Feature | ระบบเก่า (Auto Exit) | ระบบใหม่ (Manual Exit) |
|---------|---------------------|----------------------|
| **Exit Logic** | Auto exit ทันที | แค่เปลี่ยนสถานะ |
| **User Control** | ไม่มี | คุณตัดสินใจเอง |
| **ความยืดหยุ่น** | ❌ ต้องออก | ✅ เลือกได้ |
| **Review** | ❌ หุ้นหายแล้ว | ✅ ยังดูได้ |
| **False Signal** | ❌ ออกผิด ไม่มีทาง recover | ✅ Clear signal ถือต่อได้ |

---

## 💡 Best Practices

### 1. Monitor ทุกวัน
```python
# ตั้ง cron job
# 0 9 * * 1-5  python3 monitor_daily.py
```

### 2. ตัดสินใจอย่างมีหลักการ

**CRITICAL signals** (TARGET_HIT, HARD_STOP, TRAILING_STOP):
- ⚠️ **แนะนำออก** - เป็น rule สำคัญที่ควรฟัง

**HIGH signals** (GAP_DOWN, BREAKING_DOWN):
- ⚠️ **พิจารณาออก** - สัญญาณแรง แต่อาจดู 1 วันก่อนได้

**MEDIUM/LOW signals**:
- ℹ️ **ดูสถานการณ์** - อาจถือต่อได้ถ้ามีเหตุผล

### 3. ติดตามผลการตัดสินใจ

```python
# บันทึกว่าตัดสินใจยังไง
# ถ้า clear signal แล้วหุ้นตกต่อ → ควรฟัง signal ในครั้งต่อไป
# ถ้า clear signal แล้วหุ้นขึ้น → ตัดสินใจถูก
```

### 4. อย่า Clear Signal บ่อยเกินไป

ถ้าคุณ clear signal บ่อยมาก แสดงว่า:
- Exit rules อาจเข้มเกินไป → ปรับ threshold
- หรือคุณ over-confident → ควรฟัง system มากขึ้น

---

## 🛠️ Advanced Usage

### ปรับ Exit Rules

```python
# ถ้า target 4% น้อยเกินไป อยากได้ 5%
manager.exit_rules.update_threshold('TARGET_HIT', 'target_pct', 5.0)

# ถ้า stop loss -3.5% เข้มเกินไป อยาก -5%
manager.exit_rules.update_threshold('HARD_STOP', 'stop_pct', -5.0)

# ถ้าไม่อยาก MAX_HOLD 30 วัน
manager.exit_rules.disable_rule('MAX_HOLD')
```

### Export/Import Config

```python
# Export current config
config = manager.exit_rules.export_config()
with open('my_exit_rules.json', 'w') as f:
    json.dump(config, f)

# Import config
with open('my_exit_rules.json', 'r') as f:
    config = json.load(f)
manager.exit_rules.import_config(config)
```

---

## ⚠️ ข้อควรระวัง

### 1. ไม่ใช่ไม่มี Stop Loss!

แม้คุณจะตัดสินใจเอง แต่**ควรฟัง HARD_STOP (-3.5%)**

ถ้า clear signal แล้วหุ้นตกต่อ → อาจขาดทุนมากขึ้น

### 2. CRITICAL signals มีเหตุผล

- **TARGET_HIT**: ถึงเป้ากำไรแล้ว → ออกเพื่อล็อคกำไร
- **HARD_STOP**: ขาดทุนเกินกำหนด → ตัดก่อนขาดทุนมากขึ้น
- **TRAILING_STOP**: ตกจาก peak → ออกเพื่อปกป้องกำไร

**แนะนำ: ฟัง CRITICAL signals เป็นหลัก**

### 3. ติดตามผลการตัดสินใจ

ถ้าคุณ clear signal แล้ว:
- ✅ หุ้นขึ้นต่อ → ตัดสินใจถูก
- ❌ หุ้นตกต่อ → ควรฟัง signal ครั้งต่อไป

---

## 📞 Quick Reference

```python
from src.portfolio_manager_manual_exit import PortfolioManagerManualExit

manager = PortfolioManagerManualExit('portfolio.json')

# Monitor ทุกวัน
summary = manager.monitor_positions(update_signals=True)

# ดู exit signals
manager.list_exit_signals()

# ตัดสินใจ
manager.manual_exit('TSLA')              # ออกจริง
manager.clear_exit_signal('AAPL')        # ถือต่อ

# ดู portfolio
manager.show_portfolio()
```

---

## 🎯 สรุป

**ระบบใหม่:**
- ✅ ไม่ auto exit → คุณตัดสินใจเอง
- ✅ เปลี่ยนสถานะเป็น "exit_signal" แทน
- ✅ ยังเห็นหุ้นและข้อมูล exit signal
- ✅ เลือกได้: `manual_exit()` หรือ `clear_exit_signal()`
- ✅ ยืดหยุ่น แต่ยังมี exit rules คอยเตือน

**Best Practice:**
- Monitor ทุกวัน
- ฟัง CRITICAL signals (TARGET_HIT, HARD_STOP, TRAILING_STOP)
- พิจารณา HIGH/MEDIUM signals
- ติดตามผลการตัดสินใจ

**เป้าหมาย:** สมดุลระหว่าง systematic discipline และ human judgment 🎯

---

*Last Updated: Jan 9, 2026*
*Portfolio Manager with Manual Exit v1.0*
