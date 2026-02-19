# SCAN SCHEDULE - ตารางเวลาสแกนทั้งหมด

**Date:** 2026-02-15
**Status:** ✅ 2 Scanners ทำงานแยกกัน

---

## 📊 ระบบมี 2 Scanners

### 1️⃣ Pre-Market Gap Scanner (ใหม่ - v6.11)

**เวลาทำงาน:** 06:00-09:30 AM ET
**วัตถุประสงค์:** จับ overnight gaps ที่เกิดขึ้นแล้ว
**Frequency:** Once per day (ก่อนตลาดเปิด)

```
06:00 AM ET → เริ่มสแกน
06:00-09:30 → ตรวจจับ gaps 5%+ with high volume
09:30 AM → ตลาดเปิด → ซื้อทันที
16:00 PM → ตลาดปิด → ขายทันที (same day)
```

**สิ่งที่มองหา:**
- Gap up/down 5%+ จาก previous close
- Volume spike 2x+ average
- High confidence (80%+)
- Worth rotating (net benefit > 0)

**Strategy:** Intraday (ถือไม่เกิน 1 วัน)

---

### 2️⃣ Rapid Rotation Scanner (เดิม)

**เวลาทำงาน:** 09:35 AM - 15:30 PM ET
**วัตถุประสงค์:** จับ dip-bounce opportunities
**Frequency:** Continuous (ทุก 3-5 นาที)

```
09:35-11:00 AM → Morning scan (3 min)
11:00-14:00    → Midday scan (5 min)
14:00-15:30    → Afternoon scan (5 min)
15:30-16:00    → Pre-close monitor (no new entries)
```

**สิ่งที่มองหา:**
- Dips -3% to -12% (5 days)
- Bounce confirmation (today recovering)
- Above SMA20
- Score >= 85-90

**Strategy:** Swing (ถือ 1-5 วัน)

---

## 🕐 Daily Timeline (Complete)

```
02:00 AM → Universe cleanup (ลบ delisted stocks)

06:00 AM ET → 🆕 Gap Scanner เริ่มสแกน
   ↓
06:00-09:30 → 🆕 Gap Scanner ทำงาน (detect gaps)
   ↓
09:30 AM → ตลาดเปิด
         → 🆕 Gap trades: ซื้อทันที
         → Regular rotation: รอ settle
   ↓
09:35 AM → Regular Rotation Scanner เริ่ม (3 min interval)
   ↓
09:35-11:00 → Morning scan (volatile period)
   ↓
11:00-14:00 → Midday scan (5 min interval)
   ↓
14:00-15:30 → Afternoon scan (5 min interval)
   ↓
15:30-15:50 → Pre-close monitor (no new entries)
   ↓
15:50 PM → Pre-close check
         → อาจขายบาง positions
   ↓
16:00 PM → ตลาดปิด
         → 🆕 Gap trades: ขายทั้งหมด (forced exit)
         → Regular positions: ยังถืออยู่
```

---

## 🎯 Scanner Comparison

| Feature | Gap Scanner | Rotation Scanner |
|---------|-------------|------------------|
| **เวลาทำงาน** | 06:00-09:30 AM | 09:35 AM-15:30 PM |
| **Frequency** | 1x/day | Every 3-5 min |
| **สิ่งที่มองหา** | Overnight gaps | Intraday dips |
| **Entry Time** | 09:30 AM (market open) | Anytime during market |
| **Exit Time** | 16:00 PM (same day) | 1-5 days later |
| **Hold Period** | < 1 day | 1-5 days |
| **Min Gap/Dip** | 5%+ gap | 3-12% dip |
| **Confidence** | 80%+ | Score 85-90+ |
| **Win Rate** | 100% (backtest) | 60% (backtest) |
| **Strategy** | Gap-and-Go | Dip-Bounce |

---

## ❓ คำถามของคุณ: "มันต้องเริ่มสแกนตั้งแต่ 9.00 เลยป่าว"

### คำตอบ:

**ขึ้นอยู่กับว่า Scanner ไหน:**

#### 🆕 Gap Scanner (ใหม่)
```
✅ ต้องเริ่มตั้งแต่ 06:00 AM ET
   (ก่อน 9:00 AM เยอะ)

เหตุผล:
- Gaps เกิดขึ้น overnight (ก่อนตลาดเปิด)
- ต้องสแกน pre-market เพื่อจับ gaps
- มีเวลา 3.5 ชม. เตรียมตัวก่อนซื้อ (6:00-9:30)
```

#### Regular Rotation Scanner (เดิม)
```
✅ เริ่ม 09:35 AM ET
   (หลังตลาดเปิด 5 นาที)

เหตุผล:
- รอให้ราคา settle หลังเปิดตลาด
- Spread กว้างตอน 9:30-9:35
- 9:35 ราคาเริ่มปกติ
```

---

## 🔍 UI ที่คุณเห็น

```
Morning    09:35-11:00  3min   ← Regular Rotation
Midday     11:00-14:00  5min   ← Regular Rotation
Afternoon  14:00-15:30  5min   ← Regular Rotation
Pre-Close  15:30-16:00  Monitor
```

**นี่คือ Regular Rotation Scanner** (เดิม)
**ไม่ได้แสดง Gap Scanner** (ใหม่)

---

## 🆕 Gap Scanner ไม่แสดงใน UI เพราะ:

1. **รันก่อนตลาดเปิด** (6:00-9:30 AM)
2. **รันครั้งเดียวต่อวัน** (ไม่ continuous)
3. **Integrated ใน engine** (ไม่ใช่ standalone)

**UI จะแสดง:**
- "Buy Signals" เมื่อเจอ gaps (ตอน 6:00-9:30)
- Signals จะมี metadata `gap_trade: true`
- ขายอัตโนมัติตอน 16:00 PM

---

## ✅ สรุป: ตอบคำถาม

### "มันต้องเริ่มสแกนตั้งแต่ 9.00 เลยป่าว"

**คำตอบ:**

1. **Gap Scanner** (ใหม่):
   ✅ **ต้องเริ่มตั้งแต่ 06:00 AM** (ก่อน 9:00 เยอะ)
   → เพื่อจับ gaps ที่เกิดขึ้น overnight

2. **Rotation Scanner** (เดิม):
   ✅ **เริ่ม 09:35 AM** (หลัง 9:00 นิดหน่อย)
   → เพื่อรอราคา settle หลังเปิดตลาด

**ทั้ง 2 ระบบ:** ทำงานถูกต้องแล้ว ✅

---

## 🎯 Recommendations

### ถ้าอยากให้ Gap Scanner เด่นชัดใน UI

**Option 1: เพิ่ม Timeline Section**

```
Pre-Market Gap Scan
06:00-09:30
Once/day

Morning Rotation
09:35-11:00
3min

Midday Rotation
11:00-14:00
5min

...
```

### Option 2: แสดง Badge

```
Buy Signals: 5 (3 gaps, 2 dips)
```

### Option 3: แยก Tab

```
[Gap Signals] [Rotation Signals] [All]
```

---

## 📊 Current Status

```
✅ Gap Scanner: Implemented, Running (6:00-9:30 AM)
✅ Rotation Scanner: Running (9:35 AM-3:30 PM)
✅ Both working independently
✅ No conflicts

UI Shows: Rotation Scanner only (9:35-15:30)
UI Missing: Gap Scanner timeline (6:00-9:30)
```

**ต้องการแก้ UI ให้แสดง Gap Scanner มั้ย?**

---

**สรุปสั้นๆ:**

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   Gap Scanner: เริ่ม 06:00 AM ✅ (ถูกต้อง)                 ║
║   Rotation Scanner: เริ่ม 09:35 AM ✅ (ถูกต้อง)            ║
║                                                              ║
║   UI แสดงแค่ Rotation Scanner (09:35-15:30)                ║
║   Gap Scanner ทำงานแล้ว แต่ไม่แสดงใน timeline              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**ต้องการ:** เพิ่ม Gap Scanner ใน UI timeline มั้ย?
