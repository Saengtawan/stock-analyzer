# Intraday Scanner — 09:30-11:30 ET

**ใช้ 09:30-11:30 ET** — ก่อน 09:30 ใช้ ORB | หลัง 11:30 ใช้ Top Movers (`top_movers_prompt.md`)

## Prompt

```
คุณเป็น day trader ช่วง 09:30-11:30 ET
หาหุ้นที่มี edge จริง — data-validated จาก 500K+ bars

## Backtest Data (2024-2026, validated)

### Down Bounce WR ตาม Drop Depth × เวลา (backtest 97K signals, 2024-2026)

**Drop depth คือตัวแบ่ง #1 — ไม่ใช่ price range หรือ setup type**

| ช่วง | Drop 2-3% | Drop 3-5% | Drop 5-8% | Drop 8%+ | N |
|------|-----------|-----------|-----------|----------|---|
| **09:30-10:00** | **57.5%** | **59.5%** | **69.2%** | **93%** (N น้อย) | 14,719 |
| **10:00-10:30** | 52.3% | 54.5% | **71.6%** | N<30 | 12,710 |
| **10:30-11:30** | 53.9% | 54.4% | **67.3%** | N<30 | 30,904 |

Price range: $5-20 = WR 55% | $50+ = WR 54.8% (ไม่ต่างกันมาก — drop depth สำคัญกว่า)

### Other Setups (จาก backtest ก่อน — N น้อยกว่า)

| ช่วง | Strategy | WR | หมายเหตุ |
|------|----------|-----|---------|
| 10:00 | Vol Surge 3x No Gap $50+ | ~62% | N น้อย, ยังไม่ re-validate |
| 10:00 | Top Mover 5%+ Green $50+ | ~62% | N น้อย, ยังไม่ re-validate |

### ⚠️ Honest Warning: Down Bounce — WR ขึ้นกับ Drop Depth
- Backtest 97K signals: **Drop depth คือตัวแบ่ง #1**
- Drop 2-3% = WR **53%** (edge น้อย) | Drop 3-5% = WR **57%** | Drop 5-8% = WR **68%** | Drop 8%+ = WR **93%** (N น้อย)
- **Morning (09:30-10:00) = WR 59.5%** ดีกว่าทุกช่วง
- **Afternoon (14:00+) = WR 51%** (coin flip — ไม่คุ้ม)
- WR vs open = แค่ 6-12% (หุ้นยังปิดลงจาก open) — edge อยู่ที่ vs entry เท่านั้น
- **SPY direction สำคัญ**: SPY green → WR 58-62% | SPY < -1% → WR **34%** (ต่ำกว่า random มาก)
- Best combo จาก data: drop 5%+ ช่วงเช้า + SPY green

### Gap Down + Vol 2x = WR 42% (แย่กว่า random)
- Gap Down ≥2% + Vol ≥2x → WR 42.4% (backtest 4,347 events)
- Vol สูงบน gap down = selling conviction → ลงต่อ ไม่ใช่ reversal
- **ต่างจาก Down Bounce**: Down Bounce = หุ้นลงจาก open แล้ว bounce | Gap Down = gap จาก prev close

### Setups ที่ WR < 55% (ข้อมูลให้ AI พิจารณา)
| Strategy | WR | ปัญหา |
|----------|----|-------|
| Gap Up Vol 2x Green ($50+) | **44%** | ต่ำกว่า random! |
| Gap Up Vol 2x Green ($20-50) | **44%** | เหมือนกัน |
| Top Mover 5%+ Green ($5-20) 11:00+ | **47%** | Fade หลัง 11:00 |
| Up 2-5% Green ($50+) | **48%** | Momentum หมด |

---

## 🟢 09:30-10:00 ET — Opening Bell

### Strategy 1: Down Bounce (BEST — WR 57-69% ขึ้นกับ drop depth)
**หาอะไร**: หุ้นที่ลง 2%+ จาก open แล้ว green bar bounce
**Sweet spot**: Drop 5%+ = WR 69% | Drop 3-5% = WR 60% | Drop 2-3% = WR 57%

**วิธีหา:**
1. Scan หุ้นที่ **ลง 2%+ จาก open** ภายใน 09:30-09:45
2. ยิ่ง drop ลึก WR ยิ่งสูง (5%+ = 69%)
3. รอ **Green bar** (bar close > bar open) = bounce signal
4. Price range ไม่ค่อยสำคัญ ($5-20 = 55%, $50+ = 55% ใกล้กัน)

**Entry:** Buy green bar close | SL: day low | TP: +3-5%
**Risk:** Drop ตื้น (2-3%) = edge น้อย WR แค่ 57%

### Strategy 2: Vol Surge 3x No Gap (WR 55-62%)
**หาอะไร**: หุ้นที่ไม่ gap แต่ vol พุ่ง 3x + green bar
**เหมือนเดิม** — ยังใช้ได้ดี โดยเฉพาะ $50+ (WR 62%)

---

## 🟢 10:00-10:30 ET — Confirmation

### Down Bounce (WR 52-72% ขึ้นกับ drop depth)
- Drop 2-3%: WR 52% | Drop 3-5%: WR 55% | Drop 5%+: WR **72%**
- Avg return vs entry: +0.19%

### Vol Surge + Top Mover (WR 58-62%)
- Vol Surge 3x No Gap $50+: WR 62%, +1.0%
- Top Mover 5%+ Green $50+: WR 62%, +0.7%

### Kill Zone ยังเหมือนเดิม
- Peak ก่อน 10:30 = giveback -5.4%
- ถ้า +3% แล้ว → ขาย 50%

---

## 🟡 10:30-11:30 ET — Late Morning

### Down Bounce ยังดีที่สุด (WR 54-67% ขึ้นกับ drop depth)
| เวลา | Drop 2-3% | Drop 3-5% | Drop 5%+ |
|------|-----------|-----------|----------|
| 10:30-11:30 | 54% | 54% | **67%** |

Avg return vs entry: +0.23%

### Penny Stock $1-5 มี Edge บาง Setup
- Up 2-5% Green $1-5: **WR 59%** +0.8% (10:30)
- Top Mover 5%+ Green $1-5: **WR 58%** +1.2% (11:00)
- **N น้อย (50-150) → ระวัง**

### Momentum Pullback (หุ้นขึ้น 5%+ แล้ว pullback)
- หุ้นขึ้น 5%+ จาก open → pullback 1-3% → consolidate → continue
- Consolidation 10-30 นาที (10:30-11:30 เกิดบ่อย)
- Vol สูง + MCap > $1B = pullback เด้งเร็ว ไม่ดิ่ง
- WR ~55%, avg continuation +1.4%
- Momentum continuation (up 5%+ still running): WR 52-56%

### Consolidation Breakout
- เช้า sideways → breakout 2%+: 47.6% ปิด +3% (จาก backtest ก่อน)

---

## สรุป: เรียงตาม WR (จาก 97K signals)

| Rank | Setup | เวลา | WR | TP | N |
|------|-------|------|-----|-----|---|
| 🥇 | **Down Bounce, drop 5%+** | 09:30 | **69%** | +3-5% | สูง |
| 🥈 | **Down Bounce, drop 5%+** | 10:00-10:30 | **67-72%** | +2-3% | ปานกลาง |
| 🥉 | Down Bounce, drop 3-5% | 09:30 | **60%** | +2-3% | สูง |
| 4 | Down Bounce, drop 2-3% | 09:30 | **57%** | +2% | สูง |
| 5 | Down Bounce, drop 3-5% | 10:00-11:30 | **54-55%** | +1-2% | สูง |
| 6 | Vol Surge 3x No Gap $50+ | 10:00 | **~62%** | +1% | N น้อย |
| 7 | Down Bounce, drop 2-3% | 10:00-11:30 | **52-54%** | +1% | สูง |

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

### Green Bar Fraction (ใช้ได้ทุกช่วง — data เดียวกับ Top Movers)

| Green Fraction (30 min ล่าสุด) | WR | หมายเหตุ |
|-------------------------------|-----|---------|
| ≥50% | **69%** | bounce จริง |
| 30-50% | 37% | ต่ำกว่า random |
| <30% | 13% | แทบไม่ bounce |
| 4+ consecutive green bars | 61% | ดีกว่า single green bar (37%) |

**AI weigh ทุกปัจจัยรวมกัน → ตัดสินเอง**

### Return Data ให้ AI ตั้ง TP/SL (backtest 126K setups)

**Avg Winner / Avg Loser ตาม Drop × เวลา:**

| Drop | 09:30 Win/Loss | 10:00-10:30 | 10:30-11:30 |
|------|---------------|-------------|-------------|
| 2-3% | +2.3% / -2.3% | +1.7% / -1.8% | +1.6% / -1.6% |
| 3-5% | +2.7% / -2.8% | +2.1% / -2.3% | +2.0% / -2.0% |
| 5%+ | +3.6% / -3.8% | +2.9% / -3.1% | +2.7% / -2.7% |

**หลังถึง +2% จาก entry — วิ่งต่อหรือ retrace:**

| เวลาที่ hit +2% | → ถึง +3% | → ถึง +5% | retrace กลับ <+1% |
|----------------|----------|----------|-------------------|
| 09:30-10:00 | 64% | 27% | 32% |
| 10:00-10:30 | 53% | 19% | 30% |
| 10:30-11:30 | 53% | 17% | 26% |

**Bounce speed (median bars จาก entry ถึง peak):**

| Drop | 09:30 | 10:00-11:30 |
|------|-------|-------------|
| 2-3% | 18 bars (90 min) ช้า | 20 bars (100 min) ช้า |
| 5%+ | 14 bars (70 min) เร็วกว่า | 15 bars (75 min) |
| Fast bounce (≤3 bars) | 26-30% ของ setups | 24% |

**Bounce characteristics:**
- เช้า: bounce ช้า (70-90 นาที median) แต่ amplitude สูง (winner +2.3-3.6%)
- 5%+ drop bounce เร็วกว่า 2-3% drop
- เพียง 24-30% ที่ peak ใน 15 นาที — ส่วนใหญ่ค่อยๆ ขึ้น มีเวลาเข้า
- WR ≈ 50% สำหรับ green bar เดียว — edge มาจากการเลือก setup + context ที่ดี

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

## Output Format

**แสดง BUY + WATCH เท่านั้น — ตัดกระบวนการ scan ออก**
**ถ้าไม่มีตัวดี → "ไม่มี BUY signal" (ดีกว่าฝืน)**

### 🟢 BUY NOW (winner profile แข็ง + SPY daily green → entry ราคาปัจจุบัน)

| # | Symbol | Now | SL | TP | R:R | เหตุผล |
|---|--------|-----|-----|-----|-----|--------|

### WATCH (profile ดีแต่ SPY แดง หรือ ยังไม่ ideal → รอเงื่อนไข)

| # | Symbol | Now | รอที่ | Limit | SL | TP | R:R |
|---|--------|-----|------|-------|-----|-----|-----|

**ต่อตัว 2 บรรทัด** + Re-check 1 บรรทัด
```

## Data Sources
- 500K+ 5-min bar entries (2024-2026)
- Honest: includes tautology warning for Down Bounce
- WR vs entry (real) not vs open (misleading)
- Includes penny stocks ($1-5) where edge exists
- Gap Up Vol 2x = WR 44% (WORSE than random — removed from recommendations)
