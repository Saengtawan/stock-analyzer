# 📊 Pre-market Scanner - คู่มือการใช้งาน

## 🎯 วิธีดู Results

### 1. ดูที่ Confidence Score ก่อน

| Confidence | สัญลักษณ์ | ความหมาย | การใช้งาน |
|------------|----------|----------|-----------|
| **≥70%** | 🟢 | **แนะนำ** | พิจารณาซื้อ (ถ้ามีหลายตัว = วันดี) |
| **60-69%** | 🟡 | **พอใช้** | ดูเพิ่มเติม ตรวจสอบ volume + price position |
| **<60%** | 🟠 | **ระวัง** | ข้ามไป หรือดูเฉพาะที่ score ≥6.5 |

### 2. ดู Gap Size

| Gap % | ประเมิน | Backtest Result |
|-------|---------|-----------------|
| **2-3%** | ⭐⭐⭐⭐⭐ | Sweet spot - 50% win rate |
| **1-2%** | ⭐⭐⭐⭐ | ดี - มักทำกำไรได้ |
| **3-5%** | ⚠️ ระวัง | Moderate risk - อาจ fade |
| **>5%** | 🚨 อันตราย | High fade probability (0-20% win) |

### 3. ดู Yesterday Volume Ratio

| Volume Ratio | หมายความว่า | คุณภาพ |
|--------------|-------------|--------|
| **≥3x** | 🔥 มีคนสนใจมาก | ดีมาก |
| **2-3x** | 📈 High activity | ดี |
| **1-2x** | 👌 Normal | ปกติ |
| **<1x** | 😴 เงียบ | ระวัง - อาจไม่มีโมเมนตัม |

### 4. ดู Price Position

| Position | หมายความว่า | Signal |
|----------|-------------|--------|
| **≥90%** | ใกล้ PM high มาก | 💪 แข็งแกร่ง |
| **70-90%** | ใกล้ high | ✓ ดี |
| **50-70%** | กลางๆ | ⚠️ Neutral |
| **<50%** | ใกล้ PM low | ❌ อ่อนแอ |

---

## 📋 กฎการตัดสินใจ (Decision Rules)

### ✅ เทรดได้ (BUY) - ต้องผ่านทั้งหมด:

1. ✓ Confidence ≥ 60%
2. ✓ Gap 0.5-3%
3. ✓ Price Position ≥ 70%
4. ✓ Score ≥ 6.0/10

**Bonus:** ถ้ามี Yesterday Volume ≥2x = ดียิ่งขึ้น

### ⚠️ ดูเพิ่มเติม (WATCH):

- Confidence 50-60%
- Score 5.5-6.0
- ต้องมี volume หรือ price position ดี

### ❌ ข้ามไป (SKIP):

- Confidence <50%
- Gap >5%
- Price Position <50%
- Score <5.0

---

## 🎲 ตัวอย่างการใช้งาน

### 📅 วันที่ดี (Good Day)

```
พบ 8 หุ้น confidence ≥70%
พบ 5 หุ้นมี volume ≥3x
ส่วนใหญ่ price position ≥80%

→ วันนี้เป็นวันดี! มีโอกาสหลายตัว
→ เลือก top 3-5 หุ้นที่ดีที่สุด
```

### 📅 วันปานกลาง (OK Day)

```
พบ 2-3 หุ้น confidence ≥70%
Volume ปกติ (1-2x)
Price position แตกต่างกัน

→ มีโอกาสบ้าง แต่ต้องเลือกดีๆ
→ Focus เฉพาะ confidence สูงสุด
```

### 📅 วันแย่ (Bad Day) - วันนี้ตัวอย่าง!

```
พบเพียง 1 หุ้น confidence ≥70%
Volume ส่วนใหญ่ <1x
Confidence ส่วนใหญ่ <60%

→ วันนี้ไม่เหมาะเทรด gap
→ ข้ามไป หรือเทรดเฉพาะ 1 ตัวที่ดีที่สุด (PODD)
```

---

## 🔍 วิธีวิเคราะห์หุ้นแต่ละตัว

### ตัวอย่าง: PODD

```
Symbol: PODD
Gap: +2.23%        ← ใน sweet spot (2-3%) ✓
Confidence: 75%    ← สูง ✓
Score: 7.7/10      ← ดีมาก ✓
Yest Vol: 0.89x    ← ต่ำกว่าเฉลี่ย ⚠️
Price Pos: 100%    ← ที่ PM high ✓✓
Risk: Low          ← ต่ำ ✓
```

**วิเคราะห์:**
- ✅ Gap size ดี (2.23%)
- ✅ Confidence สูงสุด (75%)
- ✅ Price แข็งแกร่ง (100% at high)
- ⚠️  Volume ต่ำกว่าปกติ (0.89x)

**สรุป:** น่าสนใจมาก! แม้ volume จะต่ำ แต่ทุกอย่างอื่นดี

---

## 💡 Tips & Tricks

### 1. ใช้ Confidence เป็นหลัก
- มองหา confidence ≥70% เสมอ
- ถ้าวันไหนไม่มี → พักเทรด

### 2. Yesterday Volume = Leading Indicator
- Volume สูงวันก่อน = คนสนใจ
- แต่ต้องดู price position ด้วย

### 3. Price Position สำคัญ!
- ≥90% = แข็งแกร่ง เทรดได้
- <50% = อ่อนแอ ระวัง

### 4. Gap Size Sweet Spot
- เป้าหมาย: 2-3%
- ยอมรับได้: 1-5%
- อันตราย: >5%

### 5. ดูภาพรวมของวัน
- มี ≥5 หุ้น conf ≥70% = วันดี
- มี 1-2 หุ้น = ระวัง
- ไม่มี = skip

---

## 🚨 สัญญาณเตือน (Red Flags)

❌ **ข้ามทันที:**
- Gap >10% (มักเป็น news/earnings → fade)
- Confidence <40%
- Price Position <30%
- Risk indicators มี "High" หลายตัว

⚠️ **ระวัง:**
- Volume <0.5x (ไม่มีความสนใจ)
- Gap 5-10% (high fade risk)
- Score <5.5/10
- Earnings date ใกล้ (<3 วัน)

---

## 📈 เป้าหมายความสำเร็จ

### Beginner (มือใหม่):
- เทรดเฉพาะ confidence ≥70%
- เลือก 1-2 หุ้นต่อวัน
- เน้นความปลอดภัย

### Intermediate (ปานกลาง):
- เทรดได้ confidence ≥60%
- เลือก 3-5 หุ้น
- ดู volume + price position

### Advanced (ขั้นสูง):
- เทรดได้ confidence ≥50%
- Combine indicators หลายตัว
- เข้าใจ risk management

---

**สรุป:**
- Scanner กรองได้ดี (8.5/10)
- ใช้ confidence เป็นตัวหลัก
- Yesterday volume เป็น bonus indicator
- Price position บอกความแข็งแกร่ง
- วันที่ดี = มีหลาย high confidence stocks

**Happy Trading! 📊**
