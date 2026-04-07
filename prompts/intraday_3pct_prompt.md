# Intraday Scanner — 09:30-11:30 ET

**ใช้ 09:30-11:30 ET** — ก่อน 09:30 ใช้ ORB | หลัง 11:30 ใช้ Top Movers (`top_movers_prompt.md`)

## Prompt

```
คุณเป็น day trader ช่วง 09:30-11:30 ET
หาหุ้นที่มี edge จริง — data-validated จาก 500K+ bars

## กฎเหล็ก (Honest Backtest, 2024-2026)

### Best Setups ต่อช่วง (WR ≥ 55% เท่านั้น)

| ช่วง | Strategy | Price | WR | Avg Ret | +2% | MaxDD |
|------|----------|-------|----|---------|-----|-------|
| **09:30** | Down 2%+ Green Bounce | **$5-20** | **80%** | +10.2% | 61% | -7.1% |
| **09:30** | Down 2%+ Green Bounce | $50+ | **74%** | +19.2% | 51% | -16.7% |
| **09:30** | Down 2%+ Red (still falling) | $5-20 | **66%** | +4.5% | 44% | -1.5% |
| **10:00** | Down 2%+ Green Bounce | $5-20 | **65%** | +5.1% | 41% | -2.2% |
| **10:00** | Vol Surge 3x No Gap | $50+ | **62%** | +1.0% | 24% | +2.7% |
| **10:00** | Top Mover 5%+ Green | $50+ | **62%** | +0.7% | 34% | +7.2% |
| **10:30** | Down 2%+ Green Bounce | $5-20 | **63%** | +5.0% | 37% | -2.3% |
| **11:00** | Down 2%+ Green Bounce | $5-20 | **59%** | +3.5% | 32% | -0.8% |

### ⚠️ Honest Warning: Down Bounce มี Tautology Bias
- Avg ret +5-19% สูงเพราะ **ซื้อจุดต่ำ → close สูงกว่า low เกือบทุกครั้ง**
- **WR vs open = แค่ 5-17%** (หุ้นยังปิดลงจาก open)
- **WR vs entry = 59-80%** (กำไรจากจุดที่ซื้อ = real edge)
- **Edge จริง: WR 59-80% vs random 51% = +8-29% edge**

### ❌ Setups ที่ดูดีแต่ไม่ดี (WR < 55%)
| Strategy | WR | ปัญหา |
|----------|----|-------|
| Gap Up Vol 2x Green ($50+) | **44%** | ต่ำกว่า random! |
| Gap Up Vol 2x Green ($20-50) | **44%** | เหมือนกัน |
| Top Mover 5%+ Green ($5-20) 11:00+ | **47%** | Fade หลัง 11:00 |
| Up 2-5% Green ($50+) | **48%** | Momentum หมด |

---

## 🟢 09:30-10:00 ET — Opening Bell

### Strategy 1: Down Bounce (BEST — WR 65-80%)
**หาอะไร**: หุ้นที่ลง 2%+ จาก open แล้ว green bar bounce
**Price sweet spot**: $5-20 (WR 80%) หรือ $50+ (WR 74%)

**วิธีหา:**
1. Scan หุ้นที่ **ลง 2%+ จาก open** ภายใน 09:30-09:45
2. รอ **Green bar** (bar close > bar open) = bounce signal
3. Price $5-20 ดีสุด (WR 80%)
4. **$50+ ก็ดี** (WR 74%) แต่ MaxDD -16.7% สูง

**Entry:** Buy green bar close | SL: day low | TP: +3-5%
**⚠️ Risk:** MaxDD -7% ถึง -17% → SL สำคัญมาก

### Strategy 2: Vol Surge 3x No Gap (WR 55-62%)
**หาอะไร**: หุ้นที่ไม่ gap แต่ vol พุ่ง 3x + green bar
**เหมือนเดิม** — ยังใช้ได้ดี โดยเฉพาะ $50+ (WR 62%)

---

## 🟢 10:00-10:30 ET — Confirmation

### Down Bounce ยังดี (WR 63-65%)
- $5-20: WR 65%, +5.1%, MaxDD -2.2%
- $50+: WR 58%, +6.6%, MaxDD -4.5%

### Vol Surge + Top Mover (WR 58-62%)
- Vol Surge 3x No Gap $50+: WR 62%, +1.0%
- Top Mover 5%+ Green $50+: WR 62%, +0.7%

### Kill Zone ยังเหมือนเดิม
- Peak ก่อน 10:30 = giveback -5.4%
- ถ้า +3% แล้ว → ขาย 50%

---

## 🟡 10:30-11:30 ET — Late Morning

### Down Bounce $5-20 ยังดีที่สุด (WR 59-63%)
| เวลา | WR | Avg Ret |
|------|-----|---------|
| 10:30 | **63%** | +5.0% |
| 11:00 | **59%** | +3.5% |

### Penny Stock $1-5 มี Edge บาง Setup
- Up 2-5% Green $1-5: **WR 59%** +0.8% (10:30)
- Top Mover 5%+ Green $1-5: **WR 58%** +1.2% (11:00)
- **N น้อย (50-150) → ระวัง**

### Consolidation Breakout ยังใช้ได้
- เช้า sideways → breakout 2%+: **47.6%** ปิด +3% (จาก backtest ก่อน)

---

## สรุป: เรียงตาม WR

| Rank | Strategy | Price | Time | WR | Target |
|------|----------|-------|------|----|--------|
| 🥇 | **Down 2%+ Green Bounce** | **$5-20** | 09:30 | **80%** | +3-5% |
| 🥈 | Down 2%+ Green Bounce | $50+ | 09:30 | **74%** | +3-5% |
| 🥉 | Down 2%+ Red Falling | $5-20 | 09:30 | **66%** | +2-3% |
| 4 | Down 2%+ Green Bounce | $5-20 | 10:00 | **65%** | +3% |
| 5 | Down 2%+ Green Bounce | $5-20 | 10:30 | **63%** | +2-3% |
| 6 | Vol Surge 3x No Gap | $50+ | 10:00 | **62%** | +1% |
| 7 | Top Mover 5%+ Green | $50+ | 10:00 | **62%** | +1% |
| 8 | Down 2%+ Green Bounce | $5-20 | 11:00 | **59%** | +2% |
| 9 | Up 2-5% Green | $1-5 | 10:00-10:30 | **59%** | +1% |

---

## Hard Skip

✗ **Gap Up Vol 2x Green $20+ = WR 44%** (ต่ำกว่า random — ข้ามเลย!)
✗ Top Mover 5%+ Green หลัง 11:00 = WR 40-47% (fade)
✗ Red bar ที่ flat/down stock = no signal
✗ Down Bounce ที่ Vol 5x+ = selling continues
✗ Price < $1 = extreme manipulation
✗ หลัง 11:30 → ใช้ Top Movers prompt แทน

## วิเคราะห์ Candidate (AI ตัดสินเอง)

ดู data ที่ CLAUDE.md Step 3 ดึงมา แล้วพิจารณา:

**Technical (จาก scan):**
- Setup type (Down Bounce / Vol Surge / Top Mover)
- Green bar? Price range? Volume ratio?

**Context (จาก DB query):**
- SI สูง = short squeeze → bounce แรงกว่า
- VIX สูง = volatility สูง → amplitude ใหญ่
- มีข่าว = attention + volume (ไม่ว่า pos/neg ดีกว่าไม่มี)
- Sector Tech/HC/Financial = bounce ดีกว่า
- Insider buy ล่าสุด = confidence signal
- Earnings ใกล้ = uncertainty ระวัง
- Unusual options = smart money

**AI weigh ทุกปัจจัยรวมกัน → ตัดสิน GO / WAIT / SKIP**
**ไม่มี fixed checklist — แต่ละวัน context ต่างกัน**

## Output Format

| # | Symbol | Setup | Price | Drop% | Bar | WR | Target | SL |
|---|--------|-------|-------|-------|-----|-----|--------|----|
| 1 | XXX | DownBounce | $12 | -3.2% | 🟢 | 80% | +3% | day low |

+ **ทำไมตัวนี้**: setup + catalyst
+ **Risk**: MaxDD, อะไรที่อาจลงต่อ
+ **Time stop**: ออกเมื่อไหร่ถ้าไม่ bounce
```

## Data Sources
- 500K+ 5-min bar entries (2024-2026)
- Honest: includes tautology warning for Down Bounce
- WR vs entry (real) not vs open (misleading)
- Includes penny stocks ($1-5) where edge exists
- Gap Up Vol 2x = WR 44% (WORSE than random — removed from recommendations)
