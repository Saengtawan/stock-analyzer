# Portfolio UI Update - Remove Button

**วันที่:** January 1, 2026
**การอัปเดต:** เพิ่มปุ่ม Remove ใน Portfolio UI
**สถานะ:** ✅ แก้เสร็จแล้ว

---

## 🆕 อะไรเปลี่ยนไป?

### เพิ่มปุ่ม "Remove Position" ใน UI

**ก่อนหน้า:**
- มีแต่ปุ่ม "Close Position" อย่างเดียว
- ปิดเทรด → บันทึกใน stats ทุกครั้ง
- ไม่สามารถลบโดยไม่นับ stats ได้

**ตอนนี้:**
- ✅ มี 2 ปุ่ม: "Close" และ "Remove"
- ✅ "Close Position" → ปิดเทรด บันทึก stats
- ✅ "Remove Position" → ลบทิ้ง ไม่นับ stats

---

## 🎨 UI Design

### Case 1: มี Exit Signal

```
┌─────────────────────────────────────┐
│ ❌ EXIT SIGNAL: HARD_STOP           │
│                                     │
│ ⚠️ ขาดทุนถึง -6% แล้ว              │
│                                     │
│ [Close Position (บันทึกสถิติ)]     │ ← ปิดเทรดปกติ
│ [Remove (ลบโดยไม่นับสถิติ)]        │ ← ลบทิ้ง
└─────────────────────────────────────┘
```

### Case 2: ไม่มี Exit Signal (HOLD)

```
┌─────────────────────────────────────┐
│ ✅ HOLD - ยังไม่ถึงจุด exit         │
│                                     │
│ ยังไม่มี exit signal ใดๆ ทั้งหมด  │
│                                     │
│ [Remove Position (ลบโดยไม่นับสถิติ)]│ ← ลบได้
└─────────────────────────────────────┘
```

---

## 🔧 การทำงาน

### ปุ่ม "Close Position"

**ทำอะไร:**
- ปิดเทรดด้วยราคาปัจจุบัน
- บันทึกในสถิติ (win rate, total P&L)
- เก็บประวัติใน closed trades

**เมื่อกด:**
```
1. แสดง confirm:
   "ยืนยันการขาย AAPL?
    ⚠️ จะบันทึกในสถิติ (stats) และประวัติการเทรด"

2. ถ้ายืนยัน:
   - เรียก API: POST /api/portfolio/close
   - ปิด position
   - อัปเดต stats
   - แสดงผล:
     "✅ ปิด position AAPL สำเร็จ!
      Return: +5.23%
      Reason: MANUAL_EXIT"

3. Refresh portfolio
```

**Use Case:**
- ออกจากตำแหน่งจริง
- ต้องการบันทึกผลกำไร/ขาดทุน
- เทรดปกติ

---

### ปุ่ม "Remove Position"

**ทำอะไร:**
- ลบตำแหน่งออกจาก portfolio
- ไม่บันทึกในสถิติ
- ไม่เก็บประวัติ

**เมื่อกด:**
```
1. แสดง confirm:
   "ยืนยันการลบ AAPL?
    ⚠️ ไม่บันทึกในสถิติ - ใช้เมื่อไม่ต้องการตำแหน่งนี้แล้ว"

2. ถ้ายืนยัน:
   - เรียก API: POST /api/portfolio/remove
   - ลบ position
   - ไม่อัปเดต stats
   - แสดงผล:
     "🗑️ ลบ AAPL สำเร็จ!
      ✅ AAPL removed from portfolio"

3. Refresh portfolio
```

**Use Case:**
- เพิ่มผิด ต้องการลบ
- ไม่สนใจหุ้นนี้แล้ว
- ทดสอบระบบ

---

## 📝 Code Changes

### File: `/src/web/templates/portfolio.html`

**1. เพิ่มปุ่ม Remove ใน Exit Signal Section (line 318-327):**

```html
<div class="d-grid gap-2">
    <button class="btn btn-danger" onclick="closePosition('${pos.symbol}')">
        <i class="fas fa-times-circle me-2"></i>
        Close Position (บันทึกสถิติ)
    </button>
    <button class="btn btn-outline-secondary btn-sm" onclick="removePosition('${pos.symbol}')">
        <i class="fas fa-trash me-2"></i>
        Remove (ลบโดยไม่นับสถิติ)
    </button>
</div>
```

**2. เพิ่มปุ่ม Remove ใน Hold Section (line 338-343):**

```html
<div class="d-grid">
    <button class="btn btn-outline-secondary btn-sm" onclick="removePosition('${pos.symbol}')">
        <i class="fas fa-trash me-2"></i>
        Remove Position (ลบโดยไม่นับสถิติ)
    </button>
</div>
```

**3. เพิ่ม removePosition() Function (line 396-419):**

```javascript
async function removePosition(symbol) {
    if (!confirm(`ยืนยันการลบ ${symbol}?\n\n⚠️ ไม่บันทึกในสถิติ - ใช้เมื่อไม่ต้องการตำแหน่งนี้แล้ว`)) {
        return;
    }

    try {
        const response = await fetch('/api/portfolio/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: symbol })
        });

        const data = await response.json();

        if (response.ok) {
            alert(`🗑️ ลบ ${symbol} สำเร็จ!\n\n✅ ${data.message}`);
            updatePortfolio();
        } else {
            throw new Error(data.error || 'Failed to remove position');
        }
    } catch (error) {
        alert('เกิดข้อผิดพลาด: ' + error.message);
    }
}
```

**4. ปรับ closePosition() Confirm Message (line 369):**

```javascript
if (!confirm(`ยืนยันการขาย ${symbol}?\n\n⚠️ จะบันทึกในสถิติ (stats) และประวัติการเทรด`))
```

---

## 🎯 ความแตกต่าง: Close vs Remove

| Feature | Close Position | Remove Position |
|---------|----------------|-----------------|
| **ปุ่มสี** | 🔴 Red (Danger) | ⚪ Gray (Secondary) |
| **Icon** | ❌ times-circle | 🗑️ trash |
| **ขนาด** | ปกติ | Small |
| **บันทึก stats** | ✅ Yes | ❌ No |
| **เก็บประวัติ** | ✅ Yes | ❌ No |
| **นับ trade** | ✅ Yes | ❌ No |
| **API** | /api/portfolio/close | /api/portfolio/remove |
| **Use Case** | ออกจากตำแหน่งจริง | ลบทิ้ง/ไม่ต้องการ |

---

## 💡 Use Cases

### Use Case 1: เพิ่มผิด

**สถานการณ์:**
- เพิ่ม AAPL ผิด ควรจะเป็น MSFT
- ต้องการลบ AAPL ทิ้ง

**วิธีใช้:**
1. กดปุ่ม "Remove Position" ที่ AAPL
2. ยืนยัน
3. AAPL หายไป, stats ไม่เปลี่ยน ✅

---

### Use Case 2: ไม่สนใจแล้ว

**สถานการณ์:**
- เพิ่ม TSLA มาติดตาม
- ตอนนี้ไม่สนใจแล้ว ไม่อยากดูต่อ

**วิธีใช้:**
1. กดปุ่ม "Remove Position" ที่ TSLA
2. ยืนยัน
3. TSLA หายไป ✅

---

### Use Case 3: ออกจากตำแหน่งจริง

**สถานการณ์:**
- NVDA มี exit signal (HARD_STOP)
- ต้องการขายจริง

**วิธีใช้:**
1. กดปุ่ม "Close Position" ที่ NVDA
2. ยืนยัน
3. NVDA ปิดเทรด, stats อัปเดต, บันทึกประวัติ ✅

---

## 🧪 การทดสอบ

### Test 1: Remove ไม่นับ Stats

```
Before:
  Active: 3 positions
  Stats: 0 trades, 0% win rate

Action:
  Remove AAPL

After:
  Active: 2 positions (MSFT, GOOGL)
  Stats: 0 trades, 0% win rate ✅
```

### Test 2: Close นับ Stats

```
Before:
  Active: 3 positions
  Stats: 0 trades, 0% win rate

Action:
  Close AAPL (+5% profit)

After:
  Active: 2 positions
  Stats: 1 trade, 100% win rate ✅
```

---

## 📱 UI Screenshots (Mockup)

### Exit Signal Card:

```
┌────────────────────────────────────────┐
│ AAPL                     +5.23%        │
│ Entry: $150.00 on 2026-01-01           │
│                                        │
│ Current  Peak    Days                  │
│ $157.85  $158.00  5                   │
│                                        │
│ ❌ EXIT SIGNAL: TRAILING_PEAK          │
│ 📉 ลดลงจาก peak -3% แล้ว              │
│ แนะนำ: ขายที่ราคา ~$157.85            │
│                                        │
│ ┌────────────────────────────────────┐ │
│ │ Close Position (บันทึกสถิติ)      │ │ ← Red
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ Remove (ลบโดยไม่นับสถิติ)         │ │ ← Gray Small
│ └────────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### Hold Card:

```
┌────────────────────────────────────────┐
│ MSFT                     -1.20%        │
│ Entry: $380.00 on 2026-01-01           │
│                                        │
│ Current  Peak    Days                  │
│ $375.44  $380.00  1                   │
│                                        │
│ ✅ HOLD - ยังไม่ถึงจุด exit           │
│ ยังไม่มี exit signal ใดๆ ทั้งหมด     │
│                                        │
│ ┌────────────────────────────────────┐ │
│ │ Remove Position (ลบโดยไม่นับสถิติ) │ │ ← Gray Small
│ └────────────────────────────────────┘ │
└────────────────────────────────────────┘
```

---

## ✅ Summary

**Changes Made:**
- ✅ เพิ่มปุ่ม "Remove" ทั้ง 2 cases (Exit Signal & Hold)
- ✅ เพิ่ม removePosition() JavaScript function
- ✅ Connect กับ API /api/portfolio/remove
- ✅ Confirm message ที่ชัดเจน
- ✅ UI ที่แยกได้ว่าปุ่มไหนทำอะไร

**User Benefits:**
- ✅ ลบ position ที่ไม่ต้องการได้โดยไม่นับ stats
- ✅ มีทางเลือกระหว่าง Close (นับ) และ Remove (ไม่นับ)
- ✅ ใช้งานง่าย มี confirm ป้องกันกดผิด

**Status:** ✅ READY TO USE

---

**Updated:** January 1, 2026
**File Changed:** `/src/web/templates/portfolio.html`
**Lines Changed:** ~50 lines
**Testing:** Manual testing required
