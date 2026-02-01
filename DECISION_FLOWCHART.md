# Decision Flowchart - ขั้นตอนการตัดสินใจ

## เป้าหมาย: กำไร 10-15% ต่อเดือน

---

## ขั้นตอน 1-2-3 ที่ต้องทำทุกวัน

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   1️⃣ CHECK MACRO FIRST (ก่อนดูหุ้น ต้องดูภาพใหญ่)                        │
│   ═══════════════════════════════════════════════                        │
│                                                                          │
│   คำสั่ง: python src/macro_data_collector.py                             │
│                                                                          │
│   ดูอะไร?                                                                │
│   ┌───────────────┬────────────┬─────────────────────────────────────┐  │
│   │ Indicator     │ Level      │ Meaning                             │  │
│   ├───────────────┼────────────┼─────────────────────────────────────┤  │
│   │ VIX           │ < 15       │ ✅ ตลาดไม่กลัว → ซื้อได้เต็มที่       │  │
│   │               │ 15-20      │ 🟡 ปกติ → ระวังบ้าง                   │  │
│   │               │ 20-25      │ ⚠️ กลัว → ลดขนาด                      │  │
│   │               │ > 25       │ 🔴 กลัวมาก → ไม่ซื้อ / รอ            │  │
│   ├───────────────┼────────────┼─────────────────────────────────────┤  │
│   │ Fed           │ ลดดอกเบี้ย   │ ✅ ดีสำหรับหุ้น                      │  │
│   │               │ คงที่       │ 🟡 ปกติ                              │  │
│   │               │ ขึ้นดอกเบี้ย  │ ⚠️ ระวัง (โดยเฉพาะ Growth stocks)   │  │
│   ├───────────────┼────────────┼─────────────────────────────────────┤  │
│   │ 10Y Yield     │ < 4%       │ ✅ หุ้น attractive                   │  │
│   │               │ 4-5%       │ 🟡 ปกติ                              │  │
│   │               │ > 5%       │ ⚠️ Bond attractive กว่าหุ้น          │  │
│   └───────────────┴────────────┴─────────────────────────────────────┘  │
│                                                                          │
│   OUTPUT: RISK-ON ✅ หรือ RISK-OFF ❌ ?                                  │
│                                                                          │
│   ถ้า RISK-OFF → หยุด ไม่ต้องไปต่อ รอให้ conditions ดีขึ้น               │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   2️⃣ CHOOSE SECTOR (เลือก sector ที่กำลัง "ร้อน")                        │
│   ═══════════════════════════════════════════════                        │
│                                                                          │
│   คำสั่ง: python src/sector_analyzer.py                                  │
│                                                                          │
│   ดูอะไร?                                                                │
│   ┌───────────────────────────────────────────────────────────────────┐ │
│   │ 1. MOMENTUM: Sector ไหน momentum ดีที่สุด? (5-day, 20-day)        │ │
│   │ 2. RELATIVE STRENGTH: Sector ไหนแข็งกว่า S&P 500?                 │ │
│   │ 3. FUND FLOWS: เงินไหลเข้า sector ไหน?                            │ │
│   │ 4. NEWS: มีข่าวอะไรที่ support sector นี้?                        │ │
│   │ 5. CYCLE: เศรษฐกิจตอนนี้เอื้อ sector ไหน?                         │ │
│   └───────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│   Economic Cycle กับ Sector ที่ควรเลือก:                                │
│   ┌────────────────┬──────────────────────────────────────────────────┐ │
│   │ Cycle          │ Best Sectors                                     │ │
│   ├────────────────┼──────────────────────────────────────────────────┤ │
│   │ Early Recovery │ Financials, Tech, Consumer Discretionary         │ │
│   │ Mid Expansion  │ Tech, Industrials, Materials, Semiconductors     │ │
│   │ Late Expansion │ Energy, Materials, Commodities                   │ │
│   │ Contraction    │ Healthcare, Utilities, Consumer Staples          │ │
│   └────────────────┴──────────────────────────────────────────────────┘ │
│                                                                          │
│   OUTPUT: TOP 2-3 SECTORS ที่น่าสนใจ                                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   3️⃣ FIND STOCKS WITH CATALYST (หาหุ้นที่มีเหตุผลจะขึ้น)                 │
│   ═══════════════════════════════════════════════════                    │
│                                                                          │
│   คำสั่ง: python src/catalyst_scanner.py                                 │
│   หรือ: python src/master_screener.py (ครบทุกขั้นตอน)                    │
│                                                                          │
│   CATALYST คืออะไร? = เหตุผลที่หุ้นจะขึ้น                                │
│                                                                          │
│   ┌──────────────────┬────────────────────┬────────────────────────────┐│
│   │ Catalyst Type    │ Signal             │ Action                     ││
│   ├──────────────────┼────────────────────┼────────────────────────────┤│
│   │ EARNINGS         │ ประกาศงบใน 2 สัปดาห์  │ ซื้อก่อนถ้าคาดว่าดี        ││
│   │ ANALYST UPGRADE  │ นักวิเคราะห์อัพเกรด   │ ✅ Bullish signal         ││
│   │ INSIDER BUYING   │ ผู้บริหารซื้อ        │ ✅ Strong signal          ││
│   │ BREAKOUT         │ ทะลุแนวต้าน         │ ✅ Technical signal       ││
│   │ VOLUME SURGE     │ Volume พุ่ง         │ ✅ Interest increasing    ││
│   │ GAP UP           │ เปิด Gap ขึ้น        │ ✅ Strong momentum        ││
│   │ 52W HIGH         │ ใกล้ high สุดปี      │ 🟡 อาจไปต่อหรือพักตัว      ││
│   └──────────────────┴────────────────────┴────────────────────────────┘│
│                                                                          │
│   กฎ: ไม่มี Catalyst = ไม่ซื้อ (ต่อให้ technical ดีแค่ไหน)               │
│                                                                          │
│   OUTPUT: รายชื่อหุ้น + Entry/Stop/Target + เหตุผล                       │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## ข้อมูลที่ต้องดูทุกวัน

### Morning Routine (เช้าก่อนตลาดเปิด)

```
1. VIX Level           → ตลาดกลัวหรือโลภ?
2. Futures (S&P, Nasdaq) → ตลาดจะเปิดบวกหรือลบ?
3. Sector ETFs         → Sector ไหนแข็ง?
4. News Headlines      → มีข่าวอะไรสำคัญ?
5. Economic Calendar   → มีประกาศอะไรวันนี้?
```

### Weekly Analysis (สัปดาห์ละครั้ง)

```
1. Fed Commentary      → จะขึ้นหรือลดดอกเบี้ย?
2. Sector Rotation     → เงินไหลไป sector ไหน?
3. Earnings Calendar   → บริษัทไหนจะประกาศงบ?
4. Economic Data       → GDP, Jobs, CPI เป็นไง?
5. Technical Levels    → S&P 500 support/resistance
```

---

## Decision Tree ฉบับย่อ

```
START
  │
  ├─ VIX > 25? ───YES───→ ❌ DON'T BUY (รอ)
  │
  NO
  │
  ├─ มี Sector ที่ momentum ดี? ───NO───→ ❌ DON'T BUY (รอ)
  │
  YES
  │
  ├─ มีหุ้นที่มี Catalyst? ───NO───→ ❌ DON'T BUY (รอ)
  │
  YES
  │
  ├─ Technical Setup ดี? ───NO───→ ⏳ WAIT for pullback
  │
  YES
  │
  └─→ ✅ BUY!
      • Entry: ราคาปัจจุบัน หรือ รอ pullback
      • Stop: -3%
      • Target: +8% (ขั้นต่ำ)
```

---

## ตัวอย่างการใช้งานจริง

### วันนี้ (2026-01-31)

**Step 1: Macro Check**
```
VIX = 17.44 → 🟡 NEUTRAL (ซื้อได้แต่ระวัง)
10Y Yield = 4.24% → 🟡 ปกติ
Dollar = 97.15 → 🟡 ปกติ
```
**ผล: RISK-ON แบบระวัง ✅**

**Step 2: Sector Selection**
```
Top Sectors:
1. Semiconductors (+8.08% 20d, RS +6.79%)
2. Communication (+2.72% 20d)
3. Regional Banks (+5.47% 20d)
```
**ผล: เลือก Semiconductors ✅**

**Step 3: Stock with Catalyst**
```
ADI (Analog Devices):
- Sector: Semiconductors ✅
- Catalyst: NEAR_52W_HIGH (momentum แรง)
- Technical: RSI ไม่ overbought
```
**ผล: ADI เป็น top pick ✅**

**Final Action:**
```
BUY ADI @ $310.88
STOP @ $301.55 (-3%)
TARGET @ $335.75 (+8%)
```

---

## ทำไมแนวคิดนี้ดีกว่าเดิม?

| เดิม | ใหม่ |
|------|------|
| ซื้อทุกสัปดาห์ไม่ว่าตลาดจะเป็นไง | ซื้อเฉพาะเมื่อ conditions ดี |
| ดูแค่ Technical | ดู Macro + Sector + Catalyst + Technical |
| ไม่มีเหตุผลว่าหุ้นจะขึ้นทำไม | มี Catalyst = มีเหตุผลที่จะขึ้น |
| ซื้อทุก sector | เลือกเฉพาะ sector ที่กำลัง "ร้อน" |
| Win Rate 52% | Expected Win Rate 65-70% |

---

## Commands ที่ใช้

```bash
# Full analysis (ทำทุกวัน)
python src/master_screener.py

# Quick scan (เร็วแต่ไม่ละเอียด)
python src/master_screener.py --quick

# Macro only
python src/macro_data_collector.py

# Sector only
python src/sector_analyzer.py

# Catalyst only
python src/catalyst_scanner.py
```

---

## สรุป: สูตรสำเร็จ

```
กำไร = (โอกาส × ขนาด × จำนวนครั้ง) - ขาดทุน

เพิ่มกำไรได้โดย:
1. เพิ่ม "โอกาส" (Win Rate) → เลือกเฉพาะหุ้นที่มี Catalyst
2. เพิ่ม "ขนาด" (Position Size) → ซื้อเยอะขึ้นเมื่อ conditions ดี
3. เพิ่ม "จำนวนครั้ง" → เทรดบ่อยขึ้นใน sector ที่ร้อน
4. ลด "ขาดทุน" → หยุดซื้อเมื่อ RISK-OFF
```

---

*"ไม่ใช่แค่หาหุ้น แต่ต้องหาหุ้นที่มีเหตุผลที่จะขึ้น ในเวลาที่เหมาะสม"*
