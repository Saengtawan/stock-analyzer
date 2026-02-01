# Portfolio System Guide - v3.0

**วันที่:** January 1, 2026
**เวอร์ชั่น:** v3.0 (Complete 6-Layer System)
**สถานะ:** ✅ ทำงานปกติ

---

## 📊 สรุป Portfolio ปัจจุบัน

### ตำแหน่งที่เปิดอยู่: 3 ตำแหน่ง

| สัญลักษณ์ | เข้า | ราคาเข้า | ราคาปัจจุบัน | กำไร/ขาดทุน | วันที่ถือ |
|-----------|------|----------|--------------|--------------|----------|
| **MU** | 2025-12-31 | $292.63 | $287.18 | -1.90% (-$18.97) | 1 วัน |
| **LRCX** | 2025-12-31 | $173.78 | $172.03 | -1.07% (-$10.70) | 1 วัน |
| **RIVN** | 2025-12-31 | $19.59 | $19.75 | +0.72% (+$7.20) | 1 วัน |

**รวม P&L:** -$22.47 (-0.75%)

---

## 🎯 ระบบ Portfolio v3.0 คืออะไร?

Portfolio Manager v3.0 เป็นระบบติดตามและจัดการตำแหน่งการลงทุนแบบอัตโนมัติ โดยใช้:

### 1️⃣ Complete 6-Layer System Integration

ระบบใช้ 6 ชั้นในการวิเคราะห์:
- **Layer 1-3:** Macro (Fed, Market Breadth, Sector Rotation)
- **Layer 4-5:** Fundamental + Catalyst Analysis
- **Layer 6:** Technical Exit Signals

### 2️⃣ ฟีเจอร์หลัก

**✅ การจัดการตำแหน่ง**
- จำกัด 3 ตำแหน่งพร้อมกัน (เหมือน backtest)
- $1,000 ต่อตำแหน่ง
- คำนวณ shares อัตโนมัติ
- ตั้ง Take Profit และ Stop Loss อัตโนมัติ

**✅ Exit Rules (กฎออกจากตำแหน่ง)**

1. **Hard Stop Loss:** -6%
   - ตัดขาดทุนทันที

2. **Regime Change Exit:** 
   - ออกทันทีถ้าตลาดเปลี่ยนเป็น BEAR หรือ WEAK

3. **Trailing Stop:**
   - หลัง 5 วัน: -6% จากจุดสูงสุด
   - หลัง 14 วัน: -7% จากจุดสูงสุด

4. **Max Hold Period:** 30 วัน
   - ออกอัตโนมัติหลัง 30 วัน

5. **Dynamic Stop Tightening:**
   - กำไร +3% → ขยับ stop เป็น breakeven (0%)
   - กำไร +5% → ขยับ stop เป็น +2%

**✅ การติดตามแบบ Real-time**
- อัปเดตราคาทุกวัน
- ตรวจจับสัญญาณออกอัตโนมัติ
- ปิดตำแหน่งอัตโนมัติตาม exit rules

**✅ สถิติการเทรด**
- Win rate
- Average returns
- Total P&L
- Win/Loss count

---

## 🖥️ Web Interface

### หน้า Portfolio Monitor

**URL:** `http://localhost:5000/portfolio`

**ฟีเจอร์:**
- แสดงตำแหน่งที่เปิดอยู่แบบ real-time
- แสดง Exit Signals (สัญญาณควรออก)
- แสดง Market Regime (สภาวะตลาด)
- เพิ่มตำแหน่งใหม่ได้
- ปิดตำแหน่งด้วยตัวเอง

**API Endpoints:**

1. **GET `/api/portfolio/status`**
   - ดูสถานะ portfolio ปัจจุบัน
   - ได้ทั้ง positions, stats, regime info

2. **POST `/api/portfolio/add`**
   - เพิ่มตำแหน่งใหม่
   - ต้องระบุ: symbol, entry_price, entry_date

3. **POST `/api/portfolio/close`**
   - ปิดตำแหน่ง
   - ระบุ symbol ที่จะปิด

---

## 📁 ไฟล์ Portfolio

### portfolio_v3.json

```json
{
  "active": [
    {
      "symbol": "MU",
      "entry_date": "2025-12-31",
      "entry_price": 292.63,
      "current_price": 287.18,
      "shares": 3.42,
      "take_profit": 321.89,
      "stop_loss": 275.07,
      "pnl_pct": -1.90,
      "pnl_usd": -18.97,
      "days_held": 1
    }
  ],
  "closed": [],
  "stats": {
    "total_trades": 0,
    "win_rate": 0.0,
    "total_pnl": 0.0
  }
}
```

---

## 🔄 วิธีใช้งาน

### 1. เพิ่มตำแหน่งใหม่

```python
from portfolio_manager_v3 import PortfolioManagerV3

pm = PortfolioManagerV3()

# เพิ่มตำแหน่ง
pm.add_position(
    symbol='AAPL',
    entry_price=150.00,
    entry_date='2026-01-01',
    amount=1000  # $1000
)
```

### 2. อัปเดตและตรวจสอบ Exit Signals

```python
from datetime import datetime

# อัปเดตราคาปัจจุบัน
current_date = datetime.now().strftime('%Y-%m-%d')
updates = pm.update_positions(current_date)

# ดูตำแหน่งที่ควรออก
for pos in updates['exit_positions']:
    print(f"⚠️ {pos['symbol']}: {pos['exit_reason']}")
    print(f"   P&L: {pos['pnl_pct']:+.2f}%")
```

### 3. ปิดตำแหน่งด้วยตัวเอง

```python
# ปิดตำแหน่ง
closed = pm.close_position(
    symbol='AAPL',
    exit_price=155.00,
    exit_date='2026-01-15',
    exit_reason='MANUAL_EXIT'
)

print(f"Closed {closed['symbol']}")
print(f"P&L: {closed['pnl_pct']:+.2f}%")
```

### 4. ดูสถิติ

```python
summary = pm.get_summary()

print(f"Active Positions: {summary['active_count']}")
print(f"Total P&L: ${summary['total_pnl']:+.2f}")
print(f"Win Rate: {summary['win_rate']:.1f}%")
```

---

## 🎯 Exit Rules อธิบายเพิ่มเติม

### ตัวอย่าง Exit Scenarios:

**Scenario 1: Hard Stop (-6%)**
- เข้า: $100
- ราคาตก: $94 → **ออกทันที** (Stop Loss)

**Scenario 2: Regime Change**
- ตลาดเปลี่ยนจาก BULL → BEAR → **ออกทันที**

**Scenario 3: Trailing Stop**
- เข้า: $100
- ขึ้น: $110 (peak)
- วันที่ 6: ราคา $103 → ยังถือ (>$104.6)
- วันที่ 7: ราคา $103 → **ออก** (-6% from peak)

**Scenario 4: Dynamic Tightening**
- เข้า: $100
- ขึ้น: $103 (+3%) → Stop ขยับเป็น $100 (breakeven)
- ขึ้น: $105 (+5%) → Stop ขยับเป็น $102 (+2%)
- ถ้าราคากลับมา $101 → **ออก** (hit new stop)

**Scenario 5: Max Hold**
- เข้า: วันที่ 1
- วันที่ 30: ยังไม่ถึง target → **ออกอัตโนมัติ**

---

## 📈 Performance Tracking

ระบบติดตามผลแบบนี้:

**Per Position:**
- Entry price, date
- Current price
- Highest price (for trailing stop)
- P&L (% และ $)
- Days held

**Overall Stats:**
- Total trades
- Win rate
- Total P&L
- Average winner/loser
- Win/Loss count

---

## 🔍 การทำงานภายใน

### Update Flow:

1. **Fetch Current Prices**
   - ดึงราคาล่าสุดจาก Yahoo Finance

2. **Update Position Data**
   - คำนวณ P&L
   - อัปเดต highest_price
   - นับ days_held

3. **Check Exit Rules**
   - Hard stop (-6%)
   - Regime change
   - Trailing stop
   - Max hold (30 days)
   - Dynamic tightening

4. **Generate Signals**
   - Exit positions: ต้องออกเพราะ hit exit rule
   - Holding: ยังถือต่อ
   - Closed: ปิดอัตโนมัติแล้ว

5. **Update Portfolio File**
   - บันทึกการเปลี่ยนแปลง
   - อัปเดตสถิติ

---

## 🚀 การใช้งานกับ Web App

### 1. เปิด Web Server

```bash
cd src/web
python3 app.py
```

### 2. เข้า Portfolio Page

```
http://localhost:5000/portfolio
```

### 3. ดู Real-time Status

หน้า web จะแสดง:
- ✅ ตำแหน่งที่เปิดอยู่
- ⚠️ Exit Signals (ถ้ามี)
- 📊 Portfolio Stats
- 🌍 Market Regime

### 4. เพิ่ม/ปิดตำแหน่ง

- กด "Add Position" เพื่อเพิ่ม
- กด "Close" ที่ตำแหน่งที่ต้องการปิด

---

## ⚙️ Configuration

### ค่าที่ปรับได้:

**Portfolio Settings:**
```python
MAX_POSITIONS = 3      # Max positions พร้อมกัน
AMOUNT_PER_POS = 1000  # $ ต่อตำแหน่ง
```

**Exit Rules:**
```python
HARD_STOP = -6         # Hard stop loss %
MAX_HOLD_DAYS = 30     # Max holding period
TRAILING_STOP_1 = -6   # วันที่ 5-13
TRAILING_STOP_2 = -7   # วันที่ 14+
```

---

## 🐛 Troubleshooting

### ปัญหาที่อาจเจอ:

**1. "Portfolio full (max 3 positions)"**
- ปิดบางตำแหน่งก่อนเพิ่มใหม่

**2. "Symbol already in portfolio"**
- หุ้นนี้มีอยู่แล้ว ไม่สามารถเพิ่มซ้ำ

**3. "Could not fetch current price"**
- Yahoo Finance API อาจช้า ลองใหม่

**4. Exit signals ไม่ถูกต้อง**
- ตรวจสอบว่า pre-computed macro มีครบ
- ดูที่ `macro_regimes_2025.json`

---

## ✅ สรุป

### Portfolio System v3.0 ให้อะไร:

1. **✅ Automated Position Tracking**
   - เพิ่ม/ปิดตำแหน่งอัตโนมัติ
   - คำนวณ P&L real-time

2. **✅ Smart Exit Rules**
   - 5 exit rules ที่ validated จาก backtest
   - ป้องกันขาดทุนมาก
   - Lock in profits

3. **✅ Real-time Monitoring**
   - Web interface สวยงาม
   - API สำหรับ integrate
   - Daily updates

4. **✅ Performance Analytics**
   - Win rate tracking
   - P&L analysis
   - Trade history

5. **✅ 6-Layer System Integration**
   - ใช้ complete system ในการวิเคราะห์
   - Pre-computed macro (เร็ว!)
   - Regime-aware exits

---

**สร้างเมื่อ:** January 1, 2026
**สถานะ:** ✅ OPERATIONAL
**ตำแหน่งปัจจุบัน:** 3 (MU, LRCX, RIVN)
