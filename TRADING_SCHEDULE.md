# ⏰ ตารางเวลาการสแกนและเข้าซื้อ - Rapid Trader

**อัพเดท**: 2026-02-13
**Timezone**: Eastern Time (ET) และเวลาไทย (BKK)

---

## 🚀 เวลาเข้าซื้อ (สำคัญ!)

### ✅ เริ่มซื้อได้: **09:50 ET (21:50 เวลาไทย)**

**เหตุผล**:
- ตลาดเปิด: 09:30 ET
- **Entry Protection**: บล็อกการซื้อ **20 นาทีแรก** (config: `entry_block_minutes_after_open: 20`)
- 09:30 + 20 นาที = **09:50 ET** ← เริ่มซื้อได้ตั้งแต่เวลานี้

**ข้อยกเว้น** (ซื้อได้ก่อน 09:50):
- ถ้าราคาตก >= 0.5% จากราคา signal (config: `entry_discount_exception_pct: -0.5`)

---

## 📊 ตารางเวลาสแกน (Scan Schedule)

| Session | เวลา ET | เวลาไทย | Interval | หมายเหตุ |
|---------|---------|---------|----------|----------|
| **เปิดตลาด** | 09:30 | 21:30 | - | Market opens |
| **Scan เริ่ม** | 09:35 | 21:35 | - | รอ 5 นาทีก่อน scan |
| **Morning** | 09:35-11:00 | 21:35-23:00 | ทุก **3 นาที** | ช่วงผันผวน scan บ่อย |
| **Midday** | 11:00-14:00 | 23:00-02:00 | ทุก **5 นาที** | ช่วงปกติ |
| **Afternoon** | 14:00-15:30 | 02:00-03:30 | ทุก **5 นาที** | ช่วงบ่าย |
| **Pre-Close** | 15:30-16:00 | 03:30-04:00 | **ไม่ scan** | ใกล้ปิดตลาด |
| **ปิดตลาด** | 16:00 | 04:00 | - | Market closes |

---

## 🔄 Continuous Scan (การ Scan อัตโนมัติ)

### เปิดใช้งาน: ✅ YES
- **Interval**: ทุก **5 นาที** (config: `continuous_scan_interval_minutes: 5`)
- **Dynamic VIX-based**:
  - VIX > 20: scan ทุก 5 นาที (volatile)
  - VIX < 20: scan ทุก 5 นาที (calm)
  - (User requested: always 5 min)

### เวลาทำงาน:
```
09:35 ET (21:35 ไทย) → เริ่ม scan
09:38 → scan
09:43 → scan
09:48 → scan
...
15:25 → scan สุดท้าย
15:30 ET (03:30 ไทย) → หยุด scan (pre-close)
```

---

## 🎯 Special Scans (การ Scan พิเศษ)

### 1. Morning Scan
- **เวลา**: 09:35 ET (21:35 เวลาไทย)
- **ความถี่**: ทุก 3 นาที
- **จุดประสงค์**: จับโอกาสช่วงเปิดตลาด (ผันผวนสูง)

### 2. Afternoon Scan
- **เวลา**: 14:00 ET (02:00 เวลาไทย)
- **ความถี่**: ครั้งเดียว
- **Config**: `afternoon_scan_enabled: true`
- **Min Score**: 87 (เข้มงวดกว่าปกติ)

### 3. Overnight Gap Scan
- **เวลา**: 15:30 ET (03:30 เวลาไทย)
- **ความถี่**: ครั้งเดียว
- **จุดประสงค์**: หาหุ้นที่อาจ gap up พรุ่งนี้
- **Position Size**: 35%
- **Target**: +3.0%, SL: -1.5%

---

## 🛡️ Entry Protection (3 Layers)

### Layer 1: Time Filter
- **บล็อก 20 นาทีแรก** หลังเปิดตลาด (09:30-09:50 ET)
- **ข้อยกเว้น**: ราคาตก >= 0.5% จาก signal price

### Layer 2: VWAP Distance
- **บล็อก**: ถ้าราคา > 1.5% above VWAP
- **อนุญาต**: ถ้าราคาต่ำกว่า VWAP

### Layer 3: Limit Orders Only
- **ใช้**: Limit order เท่านั้น (ไม่ใช้ market order)
- **Max Chase**: 0.2% above signal price
- **Timeout**: 5 นาที (ยกเลิก order ถ้าไม่เข้า)

---

## 🚫 เวลาที่ไม่ซื้อ (No Trading Periods)

### 1. First 20 Minutes (09:30-09:50 ET)
- **เหตุผล**: ราคาผันผวนมาก, spread กว้าง
- **ข้อยกเว้น**: Discount exception (-0.5%)

### 2. Pre-Close (15:30-16:00 ET)
- **เหตุผล**: ใกล้ปิดตลาด, สภาพคล่องต่ำ
- **ทำอะไร**: ไม่ scan, ไม่ซื้อ (เฉพาะปิด positions ถ้าจำเป็น)

### 3. Late Start Protection
- **ถ้า start หลัง 09:50 ET**: ข้าม morning scan
- **Config**: `market_open_scan_window: 20` นาที

---

## ⏱️ Timeline สำหรับคนไทย (Bangkok Time)

```
21:30 ━━━━━━━━━━ ตลาดเปิด (09:30 ET)
21:35 ━━━━━━━━━━ เริ่ม scan (ทุก 3 นาที)
21:50 ━━━━━━━━━━ 🟢 เริ่มซื้อได้!
23:00 ━━━━━━━━━━ Morning → Midday (ทุก 5 นาที)
02:00 ━━━━━━━━━━ Afternoon scan (พิเศษ)
03:30 ━━━━━━━━━━ Overnight gap scan + หยุด scan
04:00 ━━━━━━━━━━ ตลาดปิด (16:00 ET)
```

---

## 📋 Config References

### Entry Protection (line 86-96):
```yaml
entry_protection_enabled: true
entry_block_minutes_after_open: 20       # 20 นาทีแรก
entry_allow_discount_exception: true     # ยกเว้นถ้าราคาตก
entry_discount_exception_pct: -0.5       # -0.5%
entry_vwap_max_distance_pct: 1.5         # Max 1.5% above VWAP
entry_max_chase_pct: 0.2                 # Max chase 0.2%
entry_limit_timeout_minutes: 5           # Cancel after 5 min
```

### Session Timeline (line 203-223):
```yaml
sessions:
  morning:    # 09:35-11:00 ET, scan ทุก 3 min
  midday:     # 11:00-14:00 ET, scan ทุก 5 min
  afternoon:  # 14:00-15:30 ET, scan ทุก 5 min
  preclose:   # 15:30-16:00 ET, no scan
```

### Continuous Scan (line 225-236):
```yaml
continuous_scan_enabled: true
continuous_scan_interval_minutes: 5
continuous_scan_dynamic_enabled: true
continuous_scan_vix_threshold: 20.0
continuous_scan_dynamic_volatile_interval: 5
continuous_scan_dynamic_calm_interval: 5
```

---

## 💡 คำแนะนำ

### สำหรับคนไทย:
1. **เวลาดีที่สุด**: 21:50-23:00 (Morning session - scan บ่อย)
2. **เวลารอง**: 23:00-02:00 (Midday - scan ทุก 5 นาที)
3. **ระวัง**: 21:30-21:50 (ซื้อไม่ได้ - entry protection)
4. **หลีกเลี่ยง**: 03:30-04:00 (Pre-close - ไม่ scan)

### Strategy:
- ระบบจะ **scan อัตโนมัติ** ตามตาราง
- พอเจอสัญญาณจะเข้า **queue**
- **ตั้งแต่ 21:50** ถึงจะเริ่มซื้อจาก queue
- ถ้าราคาตกเกิน 0.5% → อาจซื้อก่อน 21:50 ได้

---

## ❓ FAQ

**Q: ทำไมไม่ซื้อทันทีตอน 21:30?**
A: เพราะ entry protection - ป้องกันราคาผันผวนช่วงเปิดตลาด

**Q: ถ้าเจอสัญญาณตอน 21:35 จะซื้อเมื่อไหร่?**
A: เข้า queue แล้วรอถึง 21:50 ถึงซื้อ (เว้นแต่ราคาตก >= 0.5%)

**Q: Scan บ่อยแค่ไหน?**
A:
- Morning (21:35-23:00): ทุก 3 นาที
- Midday/Afternoon (23:00-03:30): ทุก 5 นาที
- Pre-close (03:30-04:00): ไม่ scan

**Q: ซื้อได้กี่ตำแหน่งพร้อมกัน?**
A: Max 5 positions (config: `max_positions: 5`)

**Q: ถ้า start ระบบตอน 22:00 จะ scan morning ไหม?**
A: ไม่ - เพราะเกิน 20 นาทีหลังเปิดตลาด (late start protection)

---

**สรุป**:
- **สแกน**: เริ่ม 21:35 (scan ทุก 3-5 นาที)
- **ซื้อ**: เริ่ม 21:50 (หลังผ่าน 20 นาทีแรก)
- **หยุด**: 03:30 (pre-close)

**Config File**: `config/trading.yaml`
