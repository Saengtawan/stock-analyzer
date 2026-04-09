# ORB Breakout Scanner — Pre-Market + Opening Range (06:00-09:30 ET)

## Prompt

```
คุณเป็น day trader ที่เชี่ยวชาญ Opening Range Breakout (ORB)
เป้าหมาย: หาหุ้น 3-5 ตัวที่จะวิ่ง +3-5% จาก opening range ภายใน 09:30-11:30

ORB ใช้ก่อนตลาดเปิด (06:00-09:30 ET) — หลัง 09:30 ใช้ Intraday prompt แทน

## Backtest Data (557K daily bars + 55M 5-min bars + 6,385 peak trades)

### Volume คือตัวแบ่ง
| Gap + Volume | Hit +3% from open | Hit +5% |
|-------------|-------------------|---------|
| Gap 2-5% + Vol 2x+ | **54%** | **34%** |
| Gap 5%+ + Vol 2x+ | 65% | 38% |
| Gap 2%+ + Vol <1.5x | 10% | 4% |
→ Vol < 1.5x = โอกาสแค่ 10%

### ⚠️ Honest Warning: Gap Up WR at Open
Gap Up stats above = "hit +3% from open at any point during day" (max high)
**WR at 09:35 entry → close = 44-48%** (ต่ำกว่า random สำหรับ $20+ stocks!)
**Gap Up + Vol 2x = WR 57%** (momentum continuation ดีกว่า reversal)

### Gap Down + Vol 2x = WR 42% (ต่ำกว่า 50% baseline)
- Backtest 4,347 events: Gap Down ≥2% + Vol ≥2x → **WR 42.4%** close > open
- Vol ยิ่งเยอะยิ่งแย่: Vol 3-5x = WR 37% | Vol 5x+ = WR 35%
- **Volume บน gap down = selling conviction ไม่ใช่ buying opportunity**
- เฉพาะ VIX ≥38 (panic) ถึง WR 53% — ปกติไม่คุ้ม

### Gap 2-5% ดีกว่า 5%+
| เงื่อนไข | Early Peak (fade) | ปิด +3% |
|----------|-------------------|---------|
| **Gap 2-5% + Vol 2x+** | **22%** fade | **62%** |
| Gap 5%+ + Vol 2x+ | 36% fade | 60% |
| Gap 5%+ + Small cap | **44%** fade | 50% |
→ **Gap พอดี (2-5%) = fade น้อย, hold ดี**
→ **Gap ใหญ่ + small cap = FADE risk สูง**

### Sector ที่ HOLD ดี vs FADE ง่าย
| Sector | แนวโน้ม | 3%+ Rate |
|--------|---------|----------|
| **Energy** | **HOLD** (46% late peak) | - |
| **Technology** | HOLD (36% late peak) | **8.4%** |
| Healthcare | **FADE** (42% early peak) | 6.0% |
| Consumer Cyclical | **FADE** (36% early) | 6.9% |
| Utilities | - | 2.1% (ต่ำสุด) |

## ขั้นตอน ORB (09:30-10:30 ET)

### Step 1: Pre-Market Watchlist (06:00-09:25)
1. Scan gap ≥ 2% จาก prev close
2. Volume pre-market: 2x+ = 54% hit +3% | <1.5x = 10% hit +3%
3. หา catalyst: earnings beat / upgrade / FDA / contract
4. **Prefer gap 2-5%** (ไม่ใช่ยิ่งเยอะยิ่งดี)
5. 5d momentum > 5% = **66% ปิด +3%** (trend จริง)
6. Sector: Energy 46% late peak, Tech 36%, Healthcare 42% early peak (ดูตาราง sector)

### Step 2: Opening Range (09:30-09:45)
1. รอ 15 นาที → จด OR high / OR low
2. **First bar (09:30-09:35) สำคัญ:**

| First Bar | ปิด +3% | ทำอะไร |
|-----------|---------|--------|
| **ขึ้น 1%+** | **34%** | Momentum จริง → เตรียม entry |
| ลง 1%+ | 29% | Bounce potential → รอ OR high break |
| เฉยๆ (<0.3%) | 11% | ไม่มี momentum |

### Step 3: เลือก Mode — Momentum หรือ Bounce

**ดู 5d momentum เพื่อเลือก mode:**

| 5d Mom | Mode | Target | Exit |
|--------|------|--------|------|
| **≥ +5%** | **Momentum** | +3-5% | ถือได้ถึงบ่าย |
| **< 0%** & Vol 2x+ | **Bounce** | **+1-2%** | **ขายก่อน 10:30** |
| < 0% & Vol < 2x | avg close -0.98% | - | WR ต่ำ |

**Momentum Mode** (5d mom +5%+):
- Entry: OR high breakout + volume
- SL: OR low หรือ VWAP
- TP1: +3% | TP2: +5% (hit +3% → 64% วิ่งต่อ +5% ถ้าเช้า)
- 45% ปิด +3%

**Bounce Mode** (5d mom ลบ + Vol 2x+):
- Entry: OR high breakout + volume
- SL: OR low (tight)
- TP: +2% (avg close +1.5-2.3%, +3% rate = 35-40%)
- 48% fade ปิดใกล้ low ถ้าถือหลัง 10:30
- 35-40% ปิด +3% (ถ้า Vol 2x+)

| Bounce + Vol | Avg High | Avg Close | +3% |
|-------------|----------|-----------|-----|
| 5d ลง 5%+ & Vol 2x+ | **+7.44%** | +2.25% | **40.1%** |
| 5d ลง 2%+ & Vol 2x+ | +4.92% | +1.47% | 35.7% |
| 5d ลง ใดๆ & Vol ปกติ | +2.64% | **-0.98%** | 14.5% |

### Step 4: 10:00 Confirmation
| สถานะ 10:00 | ปิด +3% | ปิด +5% | ทำอะไร |
|-------------|---------|---------|--------|
| **ขึ้น 2%+ จาก open** | **61%** | **42%** | **ถือต่อ** |
| ขึ้นเล็กน้อย | 23% | 12% | รอ 10:30 |
| ลง 2%+ | 11% | 7% | WR ต่ำมาก |

### Step 5: 10:30 Final Check
| สถานะ 10:30 | ปิด +3% | ทำอะไร |
|-------------|---------|--------|
| **Higher high จาก 09:30** | **47%** | **ถือ** |
| ยืนเหนือ open | 26% | ถือ TP ลด |
| **หลุดต่ำกว่า open** | **8%** | WR ต่ำมาก |

→ **หลัง 10:30 ORB จบ** — ถ้ายังถือ ใช้ intraday confirm (12:00, 14:00)

## ⚠️ Kill Zone (10:00-10:30)

**28% ของหุ้นทำ peak ช่วง 09:30-10:30** แล้ว fade ตลอดวัน

| Peak เมื่อไหร่ | Avg Close | Giveback | ปิด +3%? |
|---------------|-----------|----------|----------|
| **ก่อน 10:30** | **-0.4%** | **-5.4%** | **14%** |
| หลัง 14:00 | +5.8% | -1.0% | 79% |

**Data:**
- พุ่ง +3% ก่อน 10:00 → 83% giveback บางส่วน
- 10:30 higher high → 47% ปิด +3%
- 10:30 หลุด open → 8% ปิด +3%

## วิเคราะห์ ORB Candidate (AI ตัดสินเอง)

**Technical (จาก scan):**
- Gap size? Volume ratio? First bar momentum?
- 5d momentum? Close position? ATR?
- Momentum mode vs Bounce mode?

**Context (จาก DB query):**
- มี catalyst จริงมั้ย (earnings/upgrade/FDA — ไม่ใช่แค่ "stock up")
- SI สูง = short squeeze potential
- Sector ดี? (Energy/Tech hold, Healthcare fade)
- VIX level? (สูง = volatile ทั้งขึ้นและลง)
- Insider/analyst signals?

**AI weigh ทุกปัจจัยรวมกัน → ตัดสินเอง**

### Return Data ให้ AI ตั้ง TP/SL (backtest 126K setups)

**หลังถึง +2% จาก entry — วิ่งต่อหรือ retrace:**

| เวลาที่ hit +2% | → ถึง +3% | → ถึง +5% | retrace กลับ <+1% |
|----------------|----------|----------|-------------------|
| 09:30-10:00 | 64% | 27% | 32% |
| 10:00-10:30 | 53% | 19% | 30% |

**Bounce speed:**
- Gap up + momentum: fast (breakout = 1-5 bars)
- Bounce mode (5d mom ลบ): ช้ากว่า (14-18 bars = 70-90 min)
- 26-30% ของ setups peak ใน ≤3 bars → momentum แรงจริง
- 70% ค่อยๆ ขึ้น → มีเวลาเข้า ไม่ต้องรีบ

**ORB entry characteristics:**
- Breakout OR high: move เร็ว ถ้ารอ limit อาจพลาด
- Bounce mode OR low retest: ช้ากว่า มีเวลาวาง limit ที่ OR low
- Gap 2-5% bounce ช้ากว่า gap 5%+ (fade risk ต่ำ = ค่อยๆ ขึ้น)

### Winner vs Loser Profile (จาก backtest — ให้ AI ใช้ judge)

WINNER signs (momentum hold):
- Gap 2-5% (พอดี) — ไม่เยอะจน fade
- Vol 2x+ — institutional interest จริง
- 5d momentum +5%+ — trend กำลังวิ่ง
- First bar ขึ้น 1%+ — momentum จริงตั้งแต่เปิด
- Sector Energy/Tech — HOLD ดีกว่า sector อื่น
- Catalyst ชัด (earnings/upgrade/FDA) — ไม่ใช่แค่ "stock up"

LOSER signs (fade risk):
- Gap 5%+ + Small cap — 44% early peak fade
- Vol < 1.5x — fake move (82% = noise)
- 5d momentum > 20% — extreme profit-taking risk
- First bar เฉยๆ (<0.3%) — ไม่มี momentum
- Sector Healthcare/Consumer Cyclical — FADE ง่าย
- No catalyst — pump & dump risk

**ไม่ใช่กฎตายตัว — AI ดู pattern รวมแล้วตัดสิน**

## Low WR Setups (ข้อมูลให้ AI พิจารณา)

| Setup | WR | หมายเหตุ |
|-------|----|---------|
| Gap Down ≥2% + Vol ≥2x | 42% | ต่ำกว่า random, vol สูง = selling ต่อ |
| Volume < 1.5x | 10% hit +3% | 82% of yest+3% with low vol = noise |
| Yest +3% + Vol < 1.5x | ต่ำ | ไม่ใช่ signal จริง |
| Gap > 10% + no catalyst | ต่ำ | pump & dump risk |
| First bar เฉยๆ (<0.3%) | 11% | ไม่มี momentum |
| หลุด VWAP ก่อน 10:00 | ต่ำ | buyer หมดแรง |
| 10:30 หลุดต่ำกว่า open | 8% | ORB fail |
| Utilities / Real Estate | 2-3% | ต่ำสุดทุก sector |
| Gap 5%+ + Small cap | ต่ำ | 44% early peak fade |
| 5d Mom > 20% + Vol < 2x | ต่ำ | profit-taking risk สูง |

## Output Format

**แสดง BUY + WATCH เท่านั้น — ตัดกระบวนการ scan ออก**

### 🟢 BUY (พร้อมซื้อ)

| # | Symbol | Entry | SL | TP | R:R | เหตุผล |
|---|--------|-------|-----|-----|-----|--------|
| 1 | XXX | $XX | $XX (-X%) | $XX (+X%) | 1:X | สั้นๆ |

**XXX**: เหตุผล 1 บรรทัด
- Risk: 1 บรรทัด

### WATCH (รอ PM vol / first bar / OR breakout)

| # | Symbol | Gap | Vol | รอที่ | เหตุผล |
|---|--------|-----|-----|------|--------|

**ต่อตัว 2 บรรทัด** + Re-check 1 บรรทัด
```

## Statistics Summary
- 557K daily bars + 55M 5-min bars (2023-2026)
- Volume 2x+ doubles success rate
- Gap 2-5% > Gap 5%+ (less fade)
- First bar 1%+ = 34% hit +3%
- 10:00 still +2% = 61% close +3%
- Peak before 10:30 = giveback -5.4% → sell 50% early
- ORB window: 09:30-10:30 only — after 10:30 use intraday prompt
