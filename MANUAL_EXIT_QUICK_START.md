# ⚡ Manual Exit - Quick Start

## 💡 แนวคิด

**เดิม:** หุ้นถูก auto exit → หายไป ❌
**ใหม่:** แค่เปลี่ยนสถานะ → คุณตัดสินใจเอง ✅

---

## 🚀 การใช้งาน (3 ขั้นตอน)

### 1. Monitor ประจำวัน

```python
from src.portfolio_manager_manual_exit import PortfolioManagerManualExit

manager = PortfolioManagerManualExit('portfolio.json')
summary = manager.monitor_positions(update_signals=True)
```

### 2. ดู Exit Signals

```python
manager.list_exit_signals()
```

**Output:**
```
🚨 POSITIONS WITH EXIT SIGNALS

1. TSLA
   Exit Signal: TARGET_HIT (CRITICAL)
   PnL: +4.50% ($+45.00)

2. NVDA
   Exit Signal: HARD_STOP (CRITICAL)
   PnL: -3.70% ($-185.00)
```

### 3. ตัดสินใจ

```python
# Option A: ออกจริง
manager.manual_exit('TSLA')

# Option B: ถือต่อ
manager.clear_exit_signal('NVDA')
```

---

## 🎯 สถานะหุ้น

| สถานะ | ความหมาย | Action |
|-------|----------|--------|
| `active` | ปกติ ไม่มี signal | - |
| `exit_signal` | มี signal แล้ว ⚠️ | ตัดสินใจ! |
| `exited` | ออกแล้ว | - |

---

## 💡 ตัวอย่าง

### กรณี 1: กำไรถึงเป้า

```
TSLA: กำไร +4.5% → TARGET_HIT signal
คุณ: ออกเลย → manual_exit('TSLA')
```

### กรณี 2: อยากถือต่อ

```
AAPL: ตกจาก peak -3.5% → TRAILING_STOP signal
คุณ: ยังอยากถือ → clear_exit_signal('AAPL')
```

---

## 📋 Commands

```python
# Monitor
summary = manager.monitor_positions(update_signals=True)

# ดู signals
manager.list_exit_signals()

# ตัดสินใจ
manager.manual_exit('TSLA')           # ออก
manager.clear_exit_signal('AAPL')     # ถือต่อ

# Summary
manager.show_portfolio()
```

---

## ⚠️ ข้อควรระวัง

1. **ฟัง CRITICAL signals** (TARGET_HIT, HARD_STOP, TRAILING_STOP)
2. **Clear signal ด้วยความระมัดระวัง** (อาจขาดทุนเพิ่ม)
3. **Monitor ทุกวัน**

---

## 📚 เอกสารเพิ่มเติม

- **Full Guide:** `MANUAL_EXIT_GUIDE.md`
- **Exit Rules:** `PORTFOLIO_EXIT_RULES.md`
- **Test:** `python3 test_manual_exit.py`

---

**ข้อดี:**
- ✅ คุณตัดสินใจเอง
- ✅ หุ้นไม่หายทันที
- ✅ ยืดหยุ่น แต่มี system คอยเตือน

**เป้าหมาย:** สมดุลระหว่าง systematic discipline และ human judgment 🎯
