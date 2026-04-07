# Top Movers Scanner — 11:30-15:30 ET

**ใช้ 11:30-15:30 ET** — ก่อน 11:30 ใช้ Intraday | หลัง 15:30 ใช้ OVN

## Prompt

```
คุณเป็น day trader ช่วง lunch-afternoon (11:30-15:30 ET)
หุ้นปกติ volume ช้า → หาหุ้นที่ยังมี momentum/bounce

## กฎเหล็ก (Honest Backtest, 2024-2026)

### Best Setups ต่อช่วง (WR ≥ 55% เท่านั้น)

| ช่วง | Strategy | Price | WR | Avg Ret | +2% |
|------|----------|-------|----|---------|-----|
| **11:30** | Down 2%+ Green Bounce | $5-20 | **57%** | +2.8% | 27% |
| **11:30** | Top Mover 5%+ Green | **$1-5** | **62%** | +1.5% | 44% |
| **12:00** | Down 2%+ Green Bounce | $5-20 | **59%** | +2.6% | 27% |
| **12:00** | Down 2%+ Red Falling | $5-20 | **57%** | +2.5% | 23% |
| **13:00** | Green Bar Any | any | **60%** | +1.3% | 27% |
| **13:00** | Down 2%+ Green Bounce | $5-20 | **57%** | +2.6% | 20% |
| **14:00** | Down 2%+ Green Bounce | $5-20 | **57%** | +2.5% | 20% |

### 3 Strategies ที่ Work (sorted by reliability)

**1. Down Bounce + Green Bar Fraction ≥50% (WR 57-69%)**
- ลง 2%+ จาก open → **green bar fraction ≥50% ใน 30 นาทีล่าสุด** → ซื้อ
- ⚠️ **Single green bar = FALSE signal (WR 37%)** — ต้องดู fraction หรือ 4+ consecutive
- **SPY gate สำคัญสุด**: SPY green → WR 58-62% | SPY < -1% → WR **34%** (skip!)
- Green bar fraction ≥50% = WR **69%** | <30% = WR **13%** (ข้ามเลย)
- Drop depth ช่วย: 3-5% drop = WR 57% | 5%+ drop = WR 68%

**2. Top Mover 5%+ Green ($1-5 penny = WR 62%)**
- หุ้นขึ้น 5%+ ใน penny range → green bar
- **WR สูงสุดใน lunch zone!**
- ⚠️ N น้อย (55 trades) + MaxDD +8.8% (สูง)
- Penny stock risk: spread กว้าง, manipulation

**3. Green Bar (any stock ที่ขึ้นอยู่) 13:00+ (WR 60%)**
- หลัง 13:00 ไม่ต้องเลือก setup ซับซ้อน
- แค่หา **green bar ที่กำลังขึ้น** = WR 60%, +1.3%
- Simple แต่ work

---

## 🟡 11:30-12:30 ET — Lunch Zone

### Strategy 1: Down Bounce + SPY Green + Green Fraction (WR 57-69%)
1. **เช็ค SPY ก่อน**: SPY green → OK | SPY < -1% → SKIP bounce วันนี้
2. Scan หุ้น ที่ **ลง 2%+ จาก open**
3. ดู **green bar fraction** (30 นาทีล่าสุด): ≥50% → entry | <30% → skip
4. ⚠️ **อย่ารอแค่ 1 green bar** (WR 37% = worse than random!)
5. SL: day low | TP: +2%
6. Time stop: 1 ชม.

### Strategy 2: Top Mover Penny $1-5 (WR 62%)
1. Scan หุ้น $1-5 ที่ **ขึ้น 5%+ จาก open**
2. **Green bar** → entry
3. SL: -3% (tight เพราะ penny volatile)
4. TP: +1.5%
5. ⚠️ **Size เล็ก** เพราะ penny risk

### Lunch Pullback (จาก backtest ก่อน)
- หุ้นขึ้น 5%+ แล้ว pullback 1%+ lunch → PM +1.4%
- ยัง work แต่ **Down Bounce WR ดีกว่า** (57-59% vs ~55%)

---

## 🟠 13:00-14:00 ET — Afternoon

### Best: Green Bar Fraction ≥50% (WR 60-69%)
- ดู green bar fraction 30 นาทีล่าสุด ≥50% + volume
- **Single green bar = noise (WR 37%)** — ต้องดู pattern ไม่ใช่ 1 bar

### Down Bounce ยังดี (WR 57%)
- $5-20 ลง 2%+ green bounce: +2.6%
- Consistent แต่ N ลดลง

### ⚠️ Top Mover 5%+ หลัง 13:00
- Green $50+: WR 51% (coin flip)
- Red: WR 49% (ไม่คุ้ม)
- **Top Mover fade หลัง 13:00** → ไม่แนะนำ

---

## 🔴 14:00-15:30 ET — Power Hour

### ทุก setup WR ลดลง
| Strategy | WR | Avg Ret |
|----------|----|---------|
| Down Bounce $5-20 Green | 57% | +2.5% |
| Green Bar Any | 50% | +0.1% |
| Top Mover Green | 54% | +0.2% |

**Down Bounce เป็น setup เดียวที่ยัง WR > 55%**

### OVN Prep (15:00+)
- ถ้าถือ position: close > entry +3% → ถือถึงปิด (80%)
- ดู Top Mover weak close → OVN gap up potential

---

## สรุป: Best Setup ต่อช่วง

| ช่วง | #1 Pick | WR | #2 Pick | WR |
|------|---------|-----|---------|-----|
| **11:30-12:30** | Down Bounce $5-20 Green | **59%** | Penny Mover $1-5 Green | **62%** |
| **13:00-14:00** | Green Bar Any | **60%** | Down Bounce $5-20 | **57%** |
| **14:00-15:30** | Down Bounce $5-20 Green | **57%** | (others < 55%) | - |

---

## Hard Skip

✗ **SPY < -1% = SKIP bounce ทั้งวัน** (WR 34% — ลงต่อ)
✗ **Green bar fraction <30% = WR 13%** (ยังไม่ bounce จริง)
✗ **Single green bar after red streak = WR 37%** (dead cat bounce)
✗ Top Mover 5%+ Green $50+ หลัง 13:00 = WR 51% (coin flip)
✗ Top Mover 5%+ Red ทุกช่วง = WR 49-54% (ไม่คุ้ม)
✗ Gap Down + Vol 2x = WR 42% (แย่กว่า random!)
✗ Down Bounce Vol 5x+ = selling continues
✗ Price < $1 = extreme manipulation
✗ Red bar ที่ flat stock = no signal
✗ หลัง 15:00 + WR < 55% = ไม่คุ้มเข้าใหม่
✗ **Wednesday movers D+1 = WR 36%** (strong fade — ขายวันเดียวกัน)

## วิเคราะห์ Candidate (AI ตัดสินเอง)

ดู data ที่ CLAUDE.md Step 3 ดึงมา แล้วพิจารณา:

**Technical (จาก scan):**
- Green bar? (สำคัญสุดจาก backtest)
- Position: pullback vs at high vs still falling?
- Price range: $1-5 penny / $5-20 / $50+?
- Volume ratio: ไม่ spike เกิน 5x?

**Context (จาก DB query):**
- SI สูง = short squeeze → bounce แรงกว่า
- มีข่าว = มี attention (ดีกว่าไม่มี)
- Sector ดี (Tech/HC) vs แย่ (Consumer Defensive)?
- VIX level = amplitude ของ bounce
- Insider/analyst signals?

**AI weigh ทุกปัจจัยรวมกัน → ตัดสิน GO / WAIT / SKIP**
**ไม่มี fixed checklist — context วันนั้นสำคัญกว่ากฎตายตัว**

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

### 🟢 BUY

| # | Symbol | Setup | Entry | SL | TP | เหตุผล |
|---|--------|-------|-------|-----|-----|--------|
| 1 | XXX | DownBounce | $XX | $XX | +2% | เหตุผลสั้น |

**ต่อตัว:**
- **ทำไม BUY**: data + reasoning
- **Entry / SL / TP**: พร้อมซื้อ
- **Risk**: อะไรที่อาจ fade
```

## Data Sources
- 500K+ 5-min bar entries (2024-2026)
- Honest WR vs entry price (not vs open)
- Includes penny stocks where edge validated
- Down Bounce = best ทุกช่วง (WR 57-59%) with tautology awareness
- Top Mover fade after 13:00 (WR drops to 51%)
- Green bar = most important signal across all setups
