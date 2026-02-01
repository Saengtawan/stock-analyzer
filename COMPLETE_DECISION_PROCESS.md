# Complete Decision Process - กระบวนการตัดสินใจแบบครบถ้วน

## เป้าหมาย: กำไร 10-15% ต่อเดือน อย่างสม่ำเสมอ

---

## Overview: 12 ขั้นตอนครบวงจร

```
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYSIS PYRAMID                              │
│                                                                  │
│                         ▲                                        │
│                        /█\        12. EXIT                       │
│                       /███\       11. MONITOR                    │
│                      /█████\      10. EXECUTE                    │
│                     /███████\     9. POSITION SIZE               │
│                    /█████████\    8. ENTRY TIMING                │
│                   /███████████\   7. TECHNICAL SETUP             │
│                  /█████████████\  6. CATALYST CHECK              │
│                 /███████████████\ 5. STOCK SELECTION             │
│                /█████████████████\4. THEME/TREND                 │
│               /███████████████████\3. SECTOR ROTATION            │
│              /█████████████████████\2. MARKET SENTIMENT          │
│             /███████████████████████\1. GLOBAL MACRO             │
│            ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔                            │
│                                                                  │
│   กว้างสุด → แคบลง → แคบลง → ตัดสินใจ                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## ขั้นตอนที่ 1: GLOBAL MACRO (ภาพใหญ่ระดับโลก)

### วัตถุประสงค์
ดูว่าโลกเป็นยังไง? มีอะไรที่กระทบตลาดหุ้นทั้งหมด?

### ข้อมูลที่ต้องดู

| หมวด | ตัวชี้วัด | ความถี่ | แหล่ง |
|------|----------|---------|-------|
| **Central Banks** | Fed Rate, ECB, BOJ Policy | รายเดือน | FRED, News |
| **Geopolitics** | สงคราม, ความขัดแย้ง, การค้า | ทุกวัน | News |
| **Global Growth** | World GDP, PMI | รายเดือน | IMF, World Bank |
| **Currencies** | DXY (Dollar), EUR, JPY | ทุกวัน | Yahoo Finance |
| **Commodities** | Oil, Gold, Copper | ทุกวัน | Yahoo Finance |
| **Bond Markets** | US 10Y, 2Y, Yield Curve | ทุกวัน | FRED |

### Decision Matrix

```
┌─────────────────────────────────────────────────────────────────────┐
│ Condition                           │ Signal        │ Action        │
├─────────────────────────────────────┼───────────────┼───────────────┤
│ Fed ลดดอกเบี้ย + Growth ดี           │ 🟢 BULLISH    │ เต็มที่         │
│ Fed คงดอกเบี้ย + Growth ปกติ         │ 🟡 NEUTRAL    │ ปกติ           │
│ Fed ขึ้นดอกเบี้ย + Inflation สูง     │ 🔴 BEARISH    │ ลดขนาด/รอ      │
│ Yield Curve Inverted               │ ⚠️ WARNING    │ Defensive      │
│ Geopolitical Crisis                │ ⚠️ WARNING    │ ลดขนาด         │
│ Dollar แข็งมาก (DXY > 105)         │ 🔴 HEADWIND   │ หลีก Multinationals │
│ Oil พุ่ง > $100                    │ 🔴 HEADWIND   │ Energy ดี, อื่นระวัง │
└─────────────────────────────────────┴───────────────┴───────────────┘
```

### Output
→ **Global Backdrop**: Bullish / Neutral / Bearish

---

## ขั้นตอนที่ 2: MARKET SENTIMENT (อารมณ์ตลาด)

### วัตถุประสงค์
ตลาดกลัวหรือโลภ? นักลงทุนรู้สึกยังไง?

### ข้อมูลที่ต้องดู

| ตัวชี้วัด | ระดับ | ความหมาย |
|----------|-------|----------|
| **VIX** | < 12 | Extreme Greed (ระวัง correction) |
| | 12-15 | Low Fear (ดีมาก) |
| | 15-20 | Normal |
| | 20-25 | Elevated Fear (ระวัง) |
| | 25-30 | High Fear (ไม่ซื้อ) |
| | > 30 | Panic (อาจเป็นโอกาสซื้อถูก) |
| **Put/Call Ratio** | < 0.7 | Bullish |
| | 0.7-1.0 | Neutral |
| | > 1.0 | Bearish (contrarian buy?) |
| **Fear & Greed Index** | 0-25 | Extreme Fear |
| | 25-45 | Fear |
| | 45-55 | Neutral |
| | 55-75 | Greed |
| | 75-100 | Extreme Greed |
| **Advance/Decline** | > 2:1 | Strong breadth |
| | 1:1 | Neutral |
| | < 1:2 | Weak breadth |
| **New Highs vs Lows** | Highs >> Lows | Bullish |
| | Lows >> Highs | Bearish |

### Sentiment Score

```
Score = (100 - VIX) × 0.3
      + (Fear&Greed) × 0.3
      + (AD Ratio normalized) × 0.2
      + (Put/Call inverted) × 0.2

Score > 70  → GREEDY (ระวัง over-extension)
Score 50-70 → HEALTHY (ดี)
Score 30-50 → CAUTIOUS (ระวัง แต่ซื้อได้)
Score < 30  → FEARFUL (ไม่ซื้อ หรือ ซื้อ contrarian)
```

### Output
→ **Market Mood**: Greedy / Healthy / Cautious / Fearful

---

## ขั้นตอนที่ 3: US ECONOMIC CYCLE (วัฏจักรเศรษฐกิจ)

### วัตถุประสงค์
เศรษฐกิจอยู่ช่วงไหนของ cycle? ใกล้ recession หรือกำลังโต?

### Leading Indicators (บอกอนาคต)

| ตัวชี้วัด | Rising = | Falling = |
|----------|----------|-----------|
| ISM PMI (Manufacturing) | Expansion coming | Contraction coming |
| ISM PMI (Services) | Growth | Slowdown |
| Building Permits | Housing strong | Housing weak |
| Consumer Confidence | Spending will rise | Spending will fall |
| Initial Jobless Claims (inverted) | Job market strong | Layoffs rising |
| S&P 500 (3-month) | Optimism | Pessimism |

### Coincident Indicators (บอกปัจจุบัน)

| ตัวชี้วัด | ความหมาย |
|----------|----------|
| Nonfarm Payrolls | การจ้างงาน |
| Industrial Production | การผลิต |
| Real Personal Income | รายได้ |
| Real Retail Sales | การใช้จ่าย |

### Lagging Indicators (ยืนยัน)

| ตัวชี้วัด | ความหมาย |
|----------|----------|
| CPI | เงินเฟ้อ |
| Unemployment Rate | ว่างงาน |
| Core PCE | Fed's preferred inflation |
| Average Duration Unemployment | ความยากของหางาน |

### Cycle Determination

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ECONOMIC CYCLE                                  │
│                                                                     │
│         EARLY              MID                LATE                  │
│        RECOVERY         EXPANSION          EXPANSION   CONTRACTION │
│            │                │                  │            │       │
│   ┌────────▼────────┬───────▼──────┬──────────▼───────┬─────▼─────┐│
│   │ • Fed cutting   │ • Growth     │ • Peak growth    │ • GDP ↓   ││
│   │ • PMI rising    │   strong     │ • Inflation ↑    │ • Layoffs ││
│   │ • Jobs growing  │ • Confidence │ • Fed hawkish    │ • CPI ↓   ││
│   │ • Credit easing │   high       │ • Yield curve    │ • Fear ↑  ││
│   │                 │ • Earnings ↑ │   flattening     │           ││
│   └─────────────────┴──────────────┴──────────────────┴───────────┘│
│                                                                     │
│   Best Sectors:                                                     │
│   EARLY: Financials, Tech, Consumer Disc, Real Estate               │
│   MID: Tech, Industrials, Materials, Semiconductors                 │
│   LATE: Energy, Materials, Commodities, Staples                     │
│   CONTRACTION: Healthcare, Utilities, Staples, Cash                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Output
→ **Cycle Phase**: Early / Mid / Late / Contraction
→ **Recommended Sectors**: [list]

---

## ขั้นตอนที่ 4: SECTOR ROTATION (เลือก Sector)

### วัตถุประสงค์
จาก Cycle และ Sentiment เลือก sector ที่น่าจะ outperform

### Multi-Factor Sector Scoring

```python
Sector_Score = (
    Momentum_Score × 0.25 +      # 5d, 20d, 60d momentum
    Relative_Strength × 0.20 +   # vs S&P 500
    Fund_Flow_Score × 0.15 +     # เงินไหลเข้า-ออก
    Cycle_Match × 0.20 +         # ตรงกับ cycle หรือไม่
    Earnings_Growth × 0.10 +     # Sector earnings trend
    News_Sentiment × 0.10        # ข่าวดี/ร้าย
)
```

### Sector Dashboard

| Sector | Mom 5d | Mom 20d | RS | Fund Flow | Cycle Match | Score |
|--------|--------|---------|----|-----------| ------------|-------|
| Technology | +2% | +5% | +3% | Inflow | MID ✓ | 78 |
| Financials | +1% | +3% | +1% | Neutral | EARLY ✓ | 65 |
| Energy | +4% | +8% | +6% | Inflow | LATE ✓ | 72 |
| Healthcare | -1% | +2% | 0% | Outflow | CONTR ✓ | 45 |
| ... | ... | ... | ... | ... | ... | ... |

### Sector Rules

```
1. เลือกเฉพาะ TOP 3 Sectors by Score
2. Sector ต้อง match กับ Cycle (หรือได้คะแนน > 70)
3. หลีก Sector ที่มี Fund Outflow ติดต่อกัน 3 สัปดาห์
4. หลีก Sector ที่ RS < -5% (underperform มาก)
```

### Output
→ **Top Sectors**: [Sector1, Sector2, Sector3]
→ **Avoid Sectors**: [SectorX, SectorY]

---

## ขั้นตอนที่ 5: THEME & TREND IDENTIFICATION (หา Theme ที่ร้อน)

### วัตถุประสงค์
นอกจาก Sector แล้ว มี "Theme" อะไรที่กำลังขับเคลื่อนตลาด?

### Current Major Themes (2025-2026)

| Theme | Related Sectors | Key Stocks | Status |
|-------|-----------------|------------|--------|
| **AI/ML** | Tech, Semis | NVDA, AMD, MSFT, GOOGL | 🔥 Hot |
| **EV Transition** | Auto, Batteries | TSLA, RIVN, LI | 🟡 Cooling |
| **Reshoring** | Industrials | CAT, DE, URI | 🔥 Hot |
| **Obesity Drugs** | Pharma | LLY, NVO | 🔥 Hot |
| **Cybersecurity** | Tech | CRWD, PANW, ZS | 🟢 Growing |
| **Clean Energy** | Utilities, Industrials | ENPH, FSLR | 🟡 Volatile |
| **Defense** | Aerospace | LMT, RTX, NOC | 🟢 Steady |
| **Data Centers** | REITs, Tech | EQIX, DLR, AMT | 🔥 Hot |

### Theme Scoring

```
Theme_Strength = (
    News_Mentions × 0.20 +       # บ่อยแค่ไหนในข่าว
    Analyst_Coverage × 0.15 +    # นักวิเคราะห์พูดถึง
    Fund_Flows × 0.25 +          # เงินไหลเข้า ETFs
    Price_Momentum × 0.25 +      # ราคาหุ้น theme ขึ้น
    Duration × 0.15              # Theme อยู่มานานแค่ไหน
)
```

### Theme Rules

```
1. Theme ใหม่ (< 6 เดือน) + Strong momentum = ดีมาก
2. Theme เก่า (> 2 ปี) + Slowing momentum = ระวัง
3. Theme ที่ทุกคนพูดถึง = อาจ late stage แล้ว
4. Theme ที่ยังไม่ค่อยมีคนพูด แต่ fundamental strong = โอกาส
```

### Output
→ **Hot Themes**: [Theme1, Theme2]
→ **Emerging Themes**: [Theme3]
→ **Fading Themes**: [Theme4] (หลีก)

---

## ขั้นตอนที่ 6: STOCK UNIVERSE FILTERING (กรองหุ้น)

### วัตถุประสงค์
จาก Sector และ Theme กรองหุ้นให้เหลือเฉพาะที่มีคุณภาพ

### Filter Layers

```
Universe: 710 stocks
    │
    ▼ Filter 1: Sector Match
    │ เฉพาะหุ้นใน Top 3 Sectors
    │
    ▼ Filter 2: Liquidity
    │ Volume > $1M/day average
    │ Price > $10
    │
    ▼ Filter 3: Volatility
    │ ATR% < 3% (ไม่ volatile เกิน)
    │
    ▼ Filter 4: Trend
    │ Price > MA20 (uptrend)
    │ MA20 > MA50 (healthy trend)
    │
    ▼ Filter 5: Momentum
    │ 5-day return: 1% - 10%
    │ 20-day return: > 0%
    │
    ▼ Filter 6: Not Overbought
    │ RSI < 70
    │
Filtered Universe: ~30-50 stocks
```

### Quality Score

```python
Quality_Score = (
    Market_Cap_Score × 0.15 +    # ใหญ่กว่าปลอดภัยกว่า
    Profitability × 0.20 +       # ROE, Margins
    Growth × 0.20 +              # Revenue, Earnings growth
    Balance_Sheet × 0.15 +       # Debt/Equity, Current Ratio
    Analyst_Rating × 0.15 +      # Buy ratings %
    Insider_Activity × 0.15      # Net buying
)
```

### Output
→ **Qualified Stocks**: [list of 30-50 stocks]

---

## ขั้นตอนที่ 7: CATALYST IDENTIFICATION (หาตัวเร่ง)

### วัตถุประสงค์
หุ้นที่ผ่าน filter แล้ว ตัวไหนมี "เหตุผล" ที่จะขึ้นเร็วๆ นี้?

### Catalyst Types & Scoring

| Catalyst | Score | Timeframe | Risk |
|----------|-------|-----------|------|
| **Earnings Beat** (just announced) | +25 | Immediate | Low |
| **Earnings Coming** (in 2 weeks) | +15 | 2 weeks | Medium |
| **Analyst Upgrade** | +20 | 1-2 weeks | Low |
| **Insider Buying** (> $100K) | +25 | 1-4 weeks | Low |
| **FDA Approval** (biotech) | +30 | Immediate | High |
| **Product Launch** | +15 | 1-2 weeks | Medium |
| **Contract Win** | +20 | Immediate | Low |
| **Breakout** (technical) | +15 | Days | Medium |
| **Gap Up** (> 3%) | +10 | Days | High |
| **Volume Surge** (> 2x avg) | +10 | Days | Medium |
| **52-Week High** | +5 | Days | Medium |
| **Inclusion in Index** | +15 | Weeks | Low |

### Catalyst Rules

```
1. ต้องมี Catalyst อย่างน้อย 1 ตัว (Score >= 15)
2. ถ้ามีหลาย Catalysts = ดีมาก (compound effect)
3. Catalyst ควรมาก่อนหรือพร้อมกับ Technical setup
4. ไม่มี Catalyst = ไม่ซื้อ (ต่อให้ chart สวยแค่ไหน)
```

### Catalyst Timeline

```
┌────────────────────────────────────────────────────────────────────┐
│                         CATALYST TIMELINE                           │
│                                                                     │
│   -2 weeks     -1 week      TODAY      +1 week      +2 weeks       │
│      │            │           │            │            │           │
│      ▼            ▼           ▼            ▼            ▼           │
│  ┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐        │
│  │Earnings│   │Analyst│   │ BUY  │   │Earnings│   │Take   │        │
│  │Coming  │   │Upgrade│   │ HERE │   │Release │   │Profit │        │
│  └───────┘   └───────┘   └───────┘   └───────┘   └───────┘        │
│                              │                                      │
│                              │                                      │
│                 Best entry: BEFORE catalyst hits                    │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### Output
→ **Stocks with Catalysts**: [list with catalyst details]
→ **Catalyst Score**: [score for each stock]

---

## ขั้นตอนที่ 8: TECHNICAL ANALYSIS (วิเคราะห์กราฟ)

### วัตถุประสงค์
หุ้นที่มี Catalyst แล้ว Technical setup เหมาะสำหรับเข้าหรือยัง?

### Technical Checklist

```
┌─────────────────────────────────────────────────────────────────────┐
│ □ TREND                                                             │
│   □ Price > MA20 > MA50                 (uptrend confirmed)         │
│   □ Higher highs, Higher lows           (healthy structure)         │
│   □ Not extended (< 10% above MA20)     (not chasing)               │
│                                                                     │
│ □ MOMENTUM                                                          │
│   □ RSI 40-65                           (room to run)               │
│   □ MACD above signal line              (momentum positive)         │
│   □ 5-day momentum 2-8%                 (sweet spot)                │
│                                                                     │
│ □ VOLUME                                                            │
│   □ Recent volume > 20-day avg          (interest)                  │
│   □ Up days have higher volume          (accumulation)              │
│                                                                     │
│ □ SUPPORT/RESISTANCE                                                │
│   □ Clear support level identified       (stop loss point)          │
│   □ No major resistance nearby           (room to target)           │
│   □ Risk:Reward > 2:1                    (worth the trade)          │
│                                                                     │
│ □ PATTERNS (Bonus)                                                  │
│   □ Bull flag                            (+10 score)                │
│   □ Cup & Handle                         (+15 score)                │
│   □ Breakout from base                   (+15 score)                │
│   □ Pullback to support                  (+10 score)                │
└─────────────────────────────────────────────────────────────────────┘
```

### Technical Score

```python
Technical_Score = (
    Trend_Score × 0.30 +
    Momentum_Score × 0.25 +
    Volume_Score × 0.20 +
    Support_Resistance × 0.15 +
    Pattern_Bonus × 0.10
)

# Minimum Technical_Score to proceed: 60
```

### Entry Signals

| Signal Type | Description | Strength |
|-------------|-------------|----------|
| **Breakout** | Price closes above resistance with volume | Strong |
| **Pullback to Support** | Price touches MA20 or support | Strong |
| **Gap & Go** | Gap up + holds + continues | Medium |
| **Bounce from Oversold** | RSI < 30 then reverses | Medium |
| **MACD Crossover** | MACD crosses above signal | Weak (confirm with others) |

### Output
→ **Technical Setup**: Ready / Wait / Avoid
→ **Entry Point**: [specific price level]
→ **Stop Loss Level**: [specific price level]
→ **Target Levels**: [T1, T2, T3]

---

## ขั้นตอนที่ 9: ENTRY TIMING (จังหวะเข้า)

### วัตถุประสงค์
รู้แล้วว่าจะซื้อหุ้นอะไร ต้องรู้ว่า "เมื่อไหร่" ถึงจะดีที่สุด

### Entry Strategies

```
┌─────────────────────────────────────────────────────────────────────┐
│ Strategy 1: PULLBACK ENTRY (Conservative)                           │
│ ─────────────────────────────                                       │
│ • รอราคา pullback มาที่ MA20 หรือ support                          │
│ • เข้าเมื่อเด้งจาก support + volume confirm                        │
│ • Risk:Reward ดีที่สุด                                              │
│ • แต่อาจพลาดถ้าหุ้นไม่ pullback                                    │
│                                                                     │
│        ╱╲                                                           │
│       ╱  ╲        MA20                                              │
│      ╱    ╲   ════════════                                          │
│     ╱      ╲ ╱                                                      │
│    ╱        ●  ← BUY HERE                                           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Strategy 2: BREAKOUT ENTRY (Aggressive)                             │
│ ─────────────────────────────                                       │
│ • เข้าทันทีเมื่อ breakout resistance + volume                       │
│ • ได้ momentum ทันที                                                │
│ • Risk สูงกว่า (อาจ fake breakout)                                  │
│                                                                     │
│                    ● BUY HERE                                       │
│                   ╱                                                 │
│     ═══════════════ ← Resistance                                    │
│         ╱╲    ╱                                                     │
│        ╱  ╲  ╱                                                      │
│       ╱    ╲╱                                                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Strategy 3: SCALE-IN ENTRY (Balanced)                               │
│ ─────────────────────────────                                       │
│ • เข้า 50% ก่อนที่ราคาปัจจุบัน                                      │
│ • เพิ่มอีก 50% เมื่อ confirm (breakout หรือ hold support)          │
│ • ลด risk ถ้าผิดทาง แต่ยังได้ upside                                │
│                                                                     │
│   Entry 1 (50%) ────●                                               │
│                      ╲                                              │
│                       ╲  ● Entry 2 (50%) ถ้า confirm                │
│                        ╲╱                                           │
│                        ╱                                            │
│                       ╱                                             │
│                      ● Stop Loss                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Pre-Market vs Market Hours

| Timing | Pros | Cons | Best For |
|--------|------|------|----------|
| **Pre-market** | ได้ราคาก่อนคนอื่น | Spread กว้าง, Volume น้อย | Gap plays |
| **First 30 min** | Volume สูง, เห็น direction | Volatile มาก | Momentum |
| **Mid-day** | Stable, clear trend | Volume ต่ำ | Pullback entry |
| **Last hour** | เห็นว่าวันนี้จบยังไง | อาจ reverse | Swing trades |

### Entry Rules

```
1. ไม่ซื้อ first 15 minutes (เว้นแต่ gap play ที่วางแผนไว้)
2. ถ้า pullback entry: ใช้ limit order ที่ support
3. ถ้า breakout entry: ใช้ stop-limit order above resistance
4. ไม่ chase ถ้าราคาขึ้นไปเกิน 5% จาก planned entry
5. ถ้าพลาด entry ที่ดี: รอวันพรุ่งนี้ หรือ หาหุ้นตัวอื่น
```

### Output
→ **Entry Strategy**: Pullback / Breakout / Scale-in
→ **Entry Price**: [exact price or range]
→ **Entry Condition**: [what must happen to trigger]

---

## ขั้นตอนที่ 10: POSITION SIZING (ขนาด Position)

### วัตถุประสงค์
ซื้อเท่าไหร่? Risk เท่าไหร่?

### Risk-Based Position Sizing

```python
# กฎพื้นฐาน: ไม่ loss เกิน 1-2% ของ portfolio ต่อ trade

Portfolio = $100,000
Max_Risk_Per_Trade = 1.5%  # $1,500

Entry_Price = $100
Stop_Loss = $97  # -3%
Risk_Per_Share = $100 - $97 = $3

Position_Size = Max_Risk_Per_Trade / Risk_Per_Share
             = $1,500 / $3
             = 500 shares
             = $50,000 (50% of portfolio)

# ถ้าเกิน 20% of portfolio → ลดลง
Max_Position = Portfolio × 0.20 = $20,000
Actual_Position = min($50,000, $20,000) = $20,000
Actual_Shares = $20,000 / $100 = 200 shares
```

### Position Size Matrix

| Conviction | Conditions Alignment | Max Position |
|------------|---------------------|--------------|
| **Very High** | All 12 steps align | 20% |
| **High** | 10-11 steps align | 15% |
| **Medium** | 8-9 steps align | 10% |
| **Low** | 6-7 steps align | 5% |
| **Don't Trade** | < 6 steps | 0% |

### Portfolio Allocation Rules

```
1. Max 5 positions at a time
2. Max 20% per position
3. Max 40% in one sector
4. Always keep 20% cash for opportunities
5. ลดขนาดทุก position ถ้า Market Sentiment = Fearful
```

### Risk Adjustment

| Condition | Adjustment |
|-----------|------------|
| VIX > 20 | Reduce all sizes by 25% |
| VIX > 25 | Reduce all sizes by 50% |
| Earnings coming (< 3 days) | Max 10% position |
| High beta stock (> 1.5) | Max 10% position |
| First trade in new sector | Max 10% position |

### Output
→ **Position Size**: [shares or $ amount]
→ **Risk Amount**: [$ at risk]
→ **Portfolio %**: [% of portfolio]

---

## ขั้นตอนที่ 11: EXECUTION (ลงมือซื้อ)

### วัตถุประสงค์
ซื้อจริงแล้ว! ต้องทำอะไรบ้าง?

### Order Types

| Order Type | When to Use | Pros | Cons |
|------------|-------------|------|------|
| **Market** | ต้องการเข้าทันที | รับประกันได้หุ้น | ราคาไม่แน่นอน |
| **Limit** | มีราคาเป้าหมายชัด | ได้ราคาที่ต้องการ | อาจไม่ได้เข้า |
| **Stop-Limit** | Breakout plays | เข้าเมื่อ confirm | อาจพลาดถ้า gap |
| **Trailing Stop** | Protect profits | Auto-adjust | อาจโดน shake out |

### Execution Checklist

```
□ Pre-Trade Checklist
  □ ทบทวน thesis อีกครั้ง
  □ เช็คว่าไม่มีข่าวสำคัญก่อนเข้า
  □ กำหนด Entry, Stop, Target แน่นอน
  □ คำนวณ position size แล้ว
  □ มี cash พอ

□ Order Placement
  □ ใส่ order ถูกประเภท
  □ ใส่จำนวนหุ้นถูกต้อง
  □ ใส่ราคาถูกต้อง
  □ Double-check ก่อน submit

□ Post-Entry
  □ บันทึก trade ลง journal
  □ ตั้ง stop loss order ทันที
  □ ตั้ง alert ที่ target
  □ อัพเดต portfolio tracking
```

### Trade Journal Entry

```
Date: 2026-01-31
Symbol: ADI
Action: BUY
Shares: 100
Entry: $310.88
Stop: $301.55 (-3%)
Target: $335.75 (+8%)

Thesis:
- Macro: NEUTRAL (ok to trade)
- Sector: Semiconductors (Top 1)
- Theme: AI/Data Center demand
- Catalyst: Near 52W high, volume surge
- Technical: Above MA20, RSI 55

Risk: $933 (0.93% of portfolio)
Expected Reward: $2,487 (2.5% of portfolio)
R:R = 2.7:1
```

### Output
→ **Order Executed**: [confirmation]
→ **Actual Entry**: [price filled]
→ **Stop Order Set**: [confirmed]

---

## ขั้นตอนที่ 12: POSITION MANAGEMENT (จัดการ Position)

### วัตถุประสงค์
หลังจากซื้อแล้ว ต้อง monitor และ exit อย่างไร?

### Daily Monitoring

```
Every Day:
□ เช็คราคาปัจจุบัน vs Entry
□ เช็คว่ายังอยู่เหนือ Stop หรือไม่
□ เช็คว่ามีข่าวอะไรใหม่
□ เช็คว่า Sector ยังแข็งแรง
□ เช็คว่า Market Sentiment เปลี่ยนไหม
```

### Exit Strategies

```
┌─────────────────────────────────────────────────────────────────────┐
│ Exit Strategy 1: STOP LOSS (Cut Loss)                               │
│ ─────────────────────────────────────                               │
│ Trigger: Price hits stop level                                      │
│ Action: SELL ALL immediately                                        │
│ Rule: ไม่ขยับ stop loss ลงล่าง EVER                                  │
│                                                                     │
│ Exit Strategy 2: TARGET HIT (Take Profit)                           │
│ ─────────────────────────────────────────                           │
│ Trigger: Price hits target                                          │
│ Options:                                                            │
│   a) Sell 100% at target                                            │
│   b) Sell 50% at T1, trail rest to T2                               │
│   c) Sell 33% at T1, 33% at T2, trail rest                          │
│                                                                     │
│ Exit Strategy 3: TRAILING STOP (Lock Profits)                       │
│ ─────────────────────────────────────────────                       │
│ When: Profit > 3%                                                   │
│ Rule: Move stop to breakeven                                        │
│ When: Profit > 5%                                                   │
│ Rule: Trail stop at -2.5% from high                                 │
│ When: Profit > 8%                                                   │
│ Rule: Trail stop at -2% from high                                   │
│                                                                     │
│ Exit Strategy 4: TIME STOP                                          │
│ ─────────────────────────────────────                               │
│ Rule: ถ้าหุ้นไม่ไปไหนใน 5-7 วัน                                      │
│ Action: ขายเพื่อหาโอกาสที่ดีกว่า                                     │
│                                                                     │
│ Exit Strategy 5: THESIS BROKEN                                      │
│ ─────────────────────────────────────                               │
│ Trigger: เหตุผลที่ซื้อไม่ valid แล้ว                                  │
│   - Sector rotate ออก                                               │
│   - Catalyst ไม่เกิด                                                │
│   - News เปลี่ยน narrative                                          │
│ Action: ขายทันที ไม่ว่า P&L จะเป็นยังไง                               │
└─────────────────────────────────────────────────────────────────────┘
```

### Scaling Out

```
Position: 100 shares @ $100 (Entry)

At $108 (+8%): Sell 30 shares → Lock $240 profit
At $112 (+12%): Sell 30 shares → Lock $360 profit
Remaining 40 shares: Trail stop at $110 (-2% from high)

Total locked: $600
Remaining upside: Unlimited with protection
```

### Post-Trade Review

```
After EVERY trade (win or lose):

1. Was the thesis correct?
2. Did I follow my rules?
3. What would I do differently?
4. What did I learn?

Update:
- Win/Loss statistics
- Sector performance tracking
- Strategy effectiveness
- Personal trading patterns
```

### Output
→ **Exit Reason**: [Stop/Target/Trail/Time/Thesis]
→ **P&L**: [$ amount and %]
→ **Lessons Learned**: [notes]

---

## Daily Workflow Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DAILY WORKFLOW                                  │
│                                                                     │
│  MORNING (Before Market Open)                                       │
│  ══════════════════════════════                                     │
│  6:00 AM  │ Check overnight news, futures                           │
│  6:30 AM  │ Run macro_data_collector.py                             │
│  7:00 AM  │ Run sector_analyzer.py                                  │
│  7:30 AM  │ Run catalyst_scanner.py                                 │
│  8:00 AM  │ Review master_screener.py output                        │
│  8:30 AM  │ Prepare orders for market open                          │
│  ─────────┼─────────────────────────────────────────────────────────│
│  MARKET HOURS                                                       │
│  ══════════════════════════════                                     │
│  9:30 AM  │ Market open - observe first 15 min                      │
│  9:45 AM  │ Execute planned entries if conditions met               │
│  10:00 AM │ Monitor positions, adjust stops if needed               │
│  12:00 PM │ Mid-day review                                          │
│  3:30 PM  │ Last hour - final decisions                             │
│  4:00 PM  │ Market close                                            │
│  ─────────┼─────────────────────────────────────────────────────────│
│  AFTER HOURS                                                        │
│  ══════════════════════════════                                     │
│  4:30 PM  │ Review today's trades                                   │
│  5:00 PM  │ Update portfolio tracking                               │
│  5:30 PM  │ Plan for tomorrow                                       │
│  6:00 PM  │ Scan for overnight opportunities                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Success Factors

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SUCCESS FORMULA                                  │
│                                                                     │
│  1. PATIENCE                                                        │
│     ไม่ซื้อถ้า conditions ไม่ดี                                       │
│     รอโอกาสที่ดีกว่า รีบไปก็ไม่มีประโยชน์                              │
│                                                                     │
│  2. DISCIPLINE                                                      │
│     ทำตาม process ทุกครั้ง                                           │
│     ไม่ bypass ขั้นตอนใดขั้นตอนหนึ่ง                                   │
│                                                                     │
│  3. RISK MANAGEMENT                                                 │
│     ไม่ loss เกิน 1-2% ต่อ trade                                     │
│     ไม่ขยับ stop loss ลง                                             │
│                                                                     │
│  4. ADAPTATION                                                      │
│     ปรับตัวตาม market conditions                                     │
│     ลดขนาดเมื่อ uncertainty สูง                                      │
│                                                                     │
│  5. CONTINUOUS LEARNING                                             │
│     บันทึกทุก trade                                                   │
│     วิเคราะห์ผิดพลาด                                                  │
│     ปรับปรุงตลอด                                                      │
│                                                                     │
│  Remember:                                                          │
│  "It's not about being right, it's about making money"              │
│  "Cut losses short, let winners run"                                │
│  "The market is always right"                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 2.0*
*Last Updated: 2026-01-31*
