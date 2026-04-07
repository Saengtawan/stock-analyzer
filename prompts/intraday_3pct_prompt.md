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

### ⚠️ Honest Warning: Down Bounce — WR ขึ้นกับ Drop Depth
- Backtest 97K signals: **Drop depth คือตัวแบ่ง #1**
- Drop 2-3% = WR **53%** (edge น้อย) | Drop 3-5% = WR **57%** | Drop 5-8% = WR **68%** | Drop 8%+ = WR **93%** (N น้อย)
- **Morning (09:30-10:00) = WR 59.5%** ดีกว่าทุกช่วง
- **Afternoon (14:00+) = WR 51%** (coin flip — ไม่คุ้ม)
- WR vs open = แค่ 6-12% (หุ้นยังปิดลงจาก open) — edge อยู่ที่ vs entry เท่านั้น
- **SPY direction สำคัญ**: SPY green → WR 58-62% | SPY < -1% → WR **34%** (ต่ำกว่า random มาก)
- **สรุป: หา drop ลึก (5%+) ช่วงเช้า + SPY green = sweet spot**

### ❌ Gap Down + Vol 2x = WR 42% (แย่กว่า random!)
- Gap Down ≥2% + Vol ≥2x → WR 42.4% (backtest 4,347 events)
- Vol สูงบน gap down = selling conviction → ลงต่อ ไม่ใช่ reversal
- **ต่างจาก Down Bounce**: Down Bounce = หุ้นลงจาก open แล้ว bounce | Gap Down = gap จาก prev close

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

## Low WR Setups (ข้อมูลให้ AI พิจารณา)

| Setup | WR | หมายเหตุ |
|-------|----|---------|
| Gap Down + Vol 2x | 42% | ต่ำกว่า random |
| SPY < -1% + bounce | 34% | ต่ำกว่า random มาก |
| Drop แค่ 2-3% | 53% | edge น้อย |
| Gap Up Vol 2x Green $20+ | 44% | ต่ำกว่า random |
| Top Mover 5%+ Green หลัง 11:00 | 40-47% | fade |
| Down Bounce Vol 5x+ | ต่ำ | selling conviction |
| Price < $1 | ต่ำ | extreme manipulation risk |

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

**AI weigh ทุกปัจจัยรวมกัน → ตัดสินเอง**

### Winner vs Loser Profile (จาก backtest — ให้ AI ใช้ judge)

WINNER signs (bounce hold):
- Beta ปานกลาง (~1.3) — volatile พอ bounce แต่ไม่เกิน
- Drop ลึก (4%+) — oversold จริง → bounce แรง
- Bar vol ปกติ (1-2x) — institutional buying ไม่ใช่ retail chase
- Mom 5d flat/ลบ — dip จริง ไม่ใช่ pullback ระหว่าง rally
- MCap ใหญ่กว่า — stable กว่า

LOSER signs (bounce fail):
- Beta สูง (>1.7) — volatile เกิน bounce ไม่ hold
- Drop ตื้น (2-3%) — ยังไม่ oversold จริง จะลงต่อ
- Bar vol spike (>2x) — retail chase ตอน bounce → fade กลับ
- Mom 5d บวก — หุ้นไม่ได้ dip จริง แค่ pullback เล็กก่อนลงต่อ
- VIX สูงมาก — ทุกอย่าง volatile bounce ไม่ hold

**ไม่ใช่กฎตายตัว — AI ดู pattern รวมแล้วตัดสิน**

## Output Format — เฉพาะ BUY เท่านั้น

**แสดงเฉพาะหุ้นที่ BUY ได้เลย — ไม่แสดง SKIP/HOLD/WAIT**
**ถ้าไม่มีตัวดี → บอก "ไม่มี BUY signal" (ดีกว่าฝืน)**

### 🟢 BUY

| # | Symbol | Setup | Entry | SL | TP | เหตุผล |
|---|--------|-------|-------|-----|-----|--------|
| 1 | XXX | DownBounce | $XX | $XX | +X% | SI + sector + news summary |

**ต่อตัว:**
- **ทำไม BUY**: 1-2 บรรทัด (data + reasoning)
- **Entry / SL / TP**: พร้อมซื้อ
- **Risk**: อะไรที่อาจผิด
```

## Data Sources
- 500K+ 5-min bar entries (2024-2026)
- Honest: includes tautology warning for Down Bounce
- WR vs entry (real) not vs open (misleading)
- Includes penny stocks ($1-5) where edge exists
- Gap Up Vol 2x = WR 44% (WORSE than random — removed from recommendations)
