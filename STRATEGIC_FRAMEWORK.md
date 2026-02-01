# Strategic Framework - เพื่อกำไร 10-15% ต่อเดือน

## ปัญหาของระบบปัจจุบัน

**ผลลัพธ์ที่ได้**: +0.4-0.6% ต่อเดือน
**เป้าหมาย**: +10-15% ต่อเดือน
**Gap**: ต้องเพิ่ม 20-30 เท่า!

### ทำไมระบบปัจจุบันไม่ถึงเป้า?

1. **ไม่รู้ว่า "ตอนนี้" ควรซื้อหรือไม่** - ซื้อทุกสัปดาห์ไม่ว่าตลาดจะเป็นอย่างไร
2. **ไม่รู้ว่า sector ไหนกำลังจะ "ร้อน"** - ดูแค่ momentum ย้อนหลัง
3. **ไม่มี "เหตุผล" ที่หุ้นจะขึ้น** - ซื้อแค่เพราะ technical ดี
4. **ไม่รู้ว่ามี "ข่าว" อะไรกำลังจะเกิด** - พลาด catalyst สำคัญ

---

## Framework ใหม่: TOP-DOWN + CATALYST

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: MACRO REGIME (โลก/เศรษฐกิจ)                           │
│  ─────────────────────────────────────────                      │
│  Q: ตอนนี้โลกเป็นยังไง? ตลาดเป็นยังไง?                          │
│  • Fed กำลังทำอะไร? (ขึ้น/ลด/คงดอกเบี้ย)                        │
│  • เงินเฟ้อเป็นยังไง? (CPI)                                     │
│  • ตลาดกลัวหรือโลภ? (VIX, Fear & Greed)                        │
│  • เศรษฐกิจอยู่ช่วงไหน? (Expansion/Contraction)                 │
│                                                                  │
│  OUTPUT: RISK-ON หรือ RISK-OFF?                                 │
│          ถ้า RISK-OFF → ไม่ซื้อ / ลดขนาด                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: SECTOR ROTATION (เลือก Sector)                        │
│  ─────────────────────────────────────────                      │
│  Q: Sector ไหนกำลังจะ "ร้อน"?                                   │
│  • ข่าวอะไรกำลังดัง? (AI, EV, Defense, etc.)                    │
│  • เศรษฐกิจช่วงนี้เอื้อ sector ไหน?                             │
│  • เงินไหลเข้า sector ไหน? (Fund flows)                         │
│  • Sector ไหนมี earnings ดี?                                    │
│                                                                  │
│  OUTPUT: TOP 2-3 SECTORS ที่น่าสนใจ                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: STOCK CATALYST (เลือกหุ้น)                            │
│  ─────────────────────────────────────────                      │
│  Q: หุ้นตัวไหนมี "เหตุผล" ที่จะขึ้น?                            │
│  • มี earnings ใกล้ประกาศ + คาดว่าดี?                           │
│  • มี product launch / FDA approval?                            │
│  • มี analyst upgrade?                                          │
│  • Insider กำลังซื้อ?                                           │
│  • Technical setup ดี?                                          │
│                                                                  │
│  OUTPUT: TOP 3-5 STOCKS พร้อม Entry/Stop/Target                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: ENTRY TIMING (จังหวะเข้า)                             │
│  ─────────────────────────────────────────                      │
│  Q: เข้าตอนไหน?                                                 │
│  • รอ pullback ไป support?                                      │
│  • รอ breakout + volume confirm?                                │
│  • รอ catalyst trigger?                                         │
│                                                                  │
│  OUTPUT: EXACT ENTRY PRICE + TIMING                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## ข้อมูลที่ต้องเก็บ

### Layer 1: MACRO DATA (เศรษฐกิจโลก)

| Data | Source | Frequency | Why |
|------|--------|-----------|-----|
| Fed Rate Decision | FRED API | 8x/year | ดอกเบี้ยขึ้น = หุ้นลง |
| CPI (Inflation) | FRED API | Monthly | เงินเฟ้อสูง = Fed ขึ้นดอกเบี้ย |
| GDP Growth | FRED API | Quarterly | เศรษฐกิจโต = หุ้นขึ้น |
| Unemployment | FRED API | Monthly | ว่างงานต่ำ = เศรษฐกิจดี |
| VIX | Yahoo Finance | Daily | ความกลัว/โลภของตลาด |
| 10Y Treasury Yield | FRED API | Daily | Bond vs Stock |
| Dollar Index (DXY) | Yahoo Finance | Daily | Dollar แข็ง = หุ้นลง |
| Oil Price (WTI) | Yahoo Finance | Daily | กระทบ Energy, Transport |
| Gold Price | Yahoo Finance | Daily | Safe haven indicator |

### Layer 2: SECTOR DATA (ข้อมูลกลุ่มอุตสาหกรรม)

| Data | Source | Frequency | Why |
|------|--------|-----------|-----|
| Sector ETF Performance | Yahoo Finance | Daily | วัด momentum |
| Sector Fund Flows | ETF.com / ICI | Weekly | เงินไหลเข้า-ออก |
| Sector Earnings Growth | Earnings Calendar | Quarterly | Sector ไหนโต |
| Sector News Sentiment | News API | Daily | ข่าวดี/ร้าย |
| Sector Relative Strength | Calculate | Daily | เทียบกับ SPY |

### Layer 3: CATALYST DATA (ตัวเร่ง)

| Data | Source | Frequency | Why |
|------|--------|-----------|-----|
| Earnings Calendar | Yahoo/Nasdaq | Daily | รู้ล่วงหน้าว่าประกาศเมื่อไร |
| FDA Calendar | FDA.gov | Daily | Biotech catalyst |
| Product Launch News | News API | Daily | Tech catalyst |
| Conference/Events | Company IR | Weekly | Investor day, etc. |
| Analyst Ratings | Yahoo Finance | Daily | Upgrade/Downgrade |

### Layer 4: SMART MONEY DATA (เงินฉลาด)

| Data | Source | Frequency | Why |
|------|--------|-----------|-----|
| Insider Trading | SEC EDGAR | Daily | ผู้บริหารซื้อ/ขาย |
| Institutional Holdings | 13F Filings | Quarterly | กองทุนถือหุ้นอะไร |
| Short Interest | FINRA | Bi-weekly | Short squeeze potential |
| Options Flow | Unusual Whales | Daily | Big money bets |
| Dark Pool Activity | FINRA ADF | Daily | Hidden volume |

### Layer 5: NEWS & SENTIMENT (ข่าวและอารมณ์ตลาด)

| Data | Source | Frequency | Why |
|------|--------|-----------|-----|
| Breaking News | News API | Real-time | React to events |
| Social Sentiment | StockTwits API | Daily | Retail sentiment |
| Fear & Greed Index | CNN | Daily | Market mood |
| Put/Call Ratio | CBOE | Daily | Options sentiment |
| Advance/Decline | NYSE | Daily | Market breadth |

---

## Economic Cycle & Sector Rotation

```
                    ECONOMIC CYCLE

     ┌──────────────────────────────────────┐
     │           EARLY EXPANSION            │
     │  • Fed cutting rates                 │
     │  • Recovery begins                   │
     │  → BUY: Financials, Tech, Consumer   │
     └────────────────┬─────────────────────┘
                      │
     ┌────────────────▼─────────────────────┐
     │           MID EXPANSION              │
     │  • Economy strong                    │
     │  • Earnings growing                  │
     │  → BUY: Industrials, Materials, Tech │
     └────────────────┬─────────────────────┘
                      │
     ┌────────────────▼─────────────────────┐
     │           LATE EXPANSION             │
     │  • Peak growth                       │
     │  • Inflation rising                  │
     │  → BUY: Energy, Materials, Commodities│
     └────────────────┬─────────────────────┘
                      │
     ┌────────────────▼─────────────────────┐
     │           CONTRACTION                │
     │  • Economy slowing                   │
     │  • Fed raising rates                 │
     │  → BUY: Healthcare, Utilities, Staples│
     │  → AVOID: Most cyclicals             │
     └────────────────┬─────────────────────┘
                      │
                      └───────→ (cycle repeats)
```

---

## Decision Tree: เมื่อไรควรซื้อ?

```
START: มีเงินพร้อมลงทุน
       │
       ▼
Q1: VIX > 25? ────YES────→ ⚠️ WAIT (ตลาดกลัวมาก)
       │
       NO
       │
       ▼
Q2: Fed กำลังขึ้นดอกเบี้ยแรง? ────YES────→ ⚠️ REDUCE SIZE
       │
       NO
       │
       ▼
Q3: มี Sector ที่มีข่าวดี? ────NO────→ ⚠️ WAIT
       │
       YES
       │
       ▼
Q4: มีหุ้นใน Sector ที่มี Catalyst? ────NO────→ ⚠️ WAIT
       │
       YES
       │
       ▼
Q5: Technical Setup ดี? ────NO────→ ⚠️ WAIT for pullback
       │
       YES
       │
       ▼
✅ BUY with confidence!
```

---

## ตัวอย่างการใช้งาน

### สถานการณ์: มกราคม 2025

**Step 1: Macro Check**
- VIX = 15 (ต่ำ = ตลาดไม่กลัว) ✅
- Fed = คงดอกเบี้ย (ไม่ขึ้นไม่ลง) ✅
- CPI = 2.5% (ใกล้เป้า) ✅
- GDP = +2.5% (โตปานกลาง) ✅

**ผลลัพธ์**: RISK-ON → พร้อมซื้อ

**Step 2: Sector Selection**
- ข่าว: AI กำลังบูม (CES 2025)
- Fund flows: Tech, Semis รับเงินเยอะ
- Earnings: Tech companies beat estimates

**ผลลัพธ์**: Focus on Semiconductors, AI-related

**Step 3: Stock Selection**
- NVDA: มี earnings 2/20, AI leader
- AMD: กำลัง gain market share
- AVGO: AI networking play

**ผลลัพธ์**: ดู technical ของ 3 ตัวนี้

**Step 4: Entry**
- NVDA pullback to $800 (support) → BUY
- Stop: $760 (-5%)
- Target: $900 (+12.5%)

---

## Implementation Plan

### Phase 1: Data Collection (Week 1-2)
```python
# src/macro_data_collector.py
- เก็บ Fed data, CPI, GDP, VIX
- อัพเดตทุกวัน/สัปดาห์

# src/sector_data_collector.py
- เก็บ Sector ETF performance
- เก็บ Fund flows
- คำนวณ Relative Strength

# src/catalyst_collector.py
- Earnings calendar
- FDA calendar
- News headlines
```

### Phase 2: Analysis Engine (Week 3-4)
```python
# src/regime_detector.py
- วิเคราะห์ว่าเศรษฐกิจอยู่ช่วงไหน
- ให้คะแนน Risk-On/Risk-Off

# src/sector_ranker.py
- จัดอันดับ Sector ตาม conditions
- เลือก Top 3 sectors

# src/catalyst_scanner.py
- หาหุ้นที่มี catalyst ใกล้ๆ
- ให้คะแนน catalyst strength
```

### Phase 3: Integration (Week 5-6)
```python
# src/master_screener.py
- รวมทุก layer เข้าด้วยกัน
- Decision tree อัตโนมัติ
- Output: ซื้อ/ไม่ซื้อ + เหตุผล
```

---

## Expected Improvement

| Metric | Current | With Framework |
|--------|---------|----------------|
| Win Rate | 52% | 65-70% |
| Avg Win | +4% | +8-10% |
| Avg Loss | -3% | -3% |
| Monthly Return | +0.5% | +5-8% |
| Positive Months | 62% | 80%+ |

### ทำไมถึงดีขึ้น?

1. **เลือกซื้อเฉพาะเมื่อ conditions ดี** - ไม่ซื้อตอนตลาดแย่
2. **เลือก Sector ที่มีแรงหนุน** - news + fund flows + cycle
3. **เลือกหุ้นที่มี Catalyst** - มีเหตุผลที่จะขึ้น
4. **Entry timing ดีขึ้น** - รอจังหวะที่ดี

---

## Next Steps

1. ✅ ออกแบบ Framework (นี่แหละ)
2. 🔄 สร้าง Data Collectors
3. 🔄 สร้าง Analysis Engine
4. 🔄 Backtest ด้วย Framework ใหม่
5. 🔄 ปรับจูน Parameters

---

*"ไม่ใช่แค่หาหุ้นที่ technical ดี แต่ต้องหาหุ้นที่มีเหตุผลที่จะขึ้น"*
