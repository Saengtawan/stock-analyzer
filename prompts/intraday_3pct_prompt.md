# Intraday Scanner — หาหุ้นตลอดวันตั้งแต่ตลาดเปิด (09:30-16:00 ET)

**ใช้ตอนตลาดเปิดเท่านั้น** — ก่อนเปิดใช้ ORB prompt (`orb_breakout_prompt.md`)

## Prompt

```
คุณเป็น day trader ที่หาหุ้นตามช่วงเวลาตลอดวัน (09:30-16:00 ET)
แต่ละช่วงมี setup ต่างกัน target ต่างกัน — ยิ่งสาย target ยิ่งเล็ก
ก่อนตลาดเปิด (06:00-09:25) → ใช้ ORB prompt แทน

## กฎเหล็ก (จาก 557K daily bars + 55M 5-min bars + 6,385 peak-time trades)

### Volume คือตัวแบ่งทุกช่วงเวลา
- Vol 2x+ = โอกาส 2 เท่า
- Vol 3x+ = institutional buyer signal
- Vol ปกติ = fake move, จะ fade
- ⚠️ **ยกเว้น Gap Down Reversal: Vol ปกติ ดีกว่า Vol สูง** (ดูด้านล่าง)

### 3 Play Types — เลือกตาม 5d momentum + gap direction

| Type | เงื่อนไข | Target | Exit | +3% |
|------|----------|--------|------|-----|
| **Momentum** | Gap up + 5d mom ≥ +5% + Vol 2x+ | +3-5% | ถือได้ถึงบ่าย | **45%** |
| **Bounce** | Gap up + 5d mom **ลบ** + Vol 2x+ | **+1-2%** | **ขายก่อน 10:30** | **35-40%** |
| **Gap Down Reversal** | Gap **down 5%+** + Vol **ปกติ** | +2-3% | ถือได้ | **41%** |

### ยิ่งสาย target ยิ่งเล็ก (Momentum play)
| ช่วง | Target จริง | เหตุผล |
|------|------------|--------|
| 09:30 | +3-5% | Momentum เต็ม, volume สูงสุด |
| 10:00 | +2-3% | ยังมี momentum |
| 10:30-12:00 | +1-2% | Momentum ลด, scalp |
| 13:00-14:00 | +0.5-1% | Breakout play, scalp |
| 14:00+ | +0.3-0.5% | Power hour scalp เร็ว |

---

## 🔵 Pre-Market (06:00-09:25 ET) → ใช้ ORB Prompt

**ดู `prompts/orb_breakout_prompt.md`** สำหรับ pre-market gap scan + OR breakout entry
Intraday prompt เริ่มตั้งแต่ตลาดเปิด (09:30) เป็นต้นไป

---

## 🟢 09:30-10:00 ET — First Bar + Confirmation

**หาอะไร**: หุ้นที่ first bar วิ่งแรง
**Target**: +3-5%

### First Bar (09:30-09:35) บอกอะไร
| First Bar | ปิด +3% | Avg High |
|-----------|---------|----------|
| ขึ้น 1%+ | **34%** | +6.24% |
| ลง 1%+ (bounce) | **29%** | +6.12% |
| ขึ้นเล็กน้อย | 15% | +2.61% |
| ลงเล็กน้อย | 11% | +2.28% |

→ First bar วิ่ง 1%+ (ขึ้นหรือลง) = มี momentum จริง
→ First bar เฉยๆ = ข้าม

### 10:00 Confirmation
| สถานะ 10:00 | ปิด +3% | ปิด +5% | ทำอะไร |
|-------------|---------|---------|--------|
| **ขึ้น 2%+ จาก open** | **61%** | **42%** | **ถือ/เข้าเพิ่ม** |
| ขึ้นเล็กน้อย | 23% | 12% | รอ 10:30 |
| ลง 2%+ จาก open | 11% | 7% | **ออก/ข้าม** |

---

## 🟢 09:30-10:30 ET — Bounce Mode (Gap Up + Mom ลบ)

**หาอะไร**: หุ้นที่ gap up แต่ 5d momentum ลบ = bounce จากลง ไม่ใช่ trend
**Target**: +1-2% (ไม่ใช่ +3-5%)

### เงื่อนไข (ต้อง Vol 2x+ เท่านั้น!)
| Bounce + Vol | Avg High | Avg Close | +3% Close |
|-------------|----------|-----------|-----------|
| **5d ลง 5%+ & Vol 2x+** | **+7.44%** | **+2.25%** | **40.1%** |
| 5d ลง 2%+ & Vol 2x+ | +4.92% | +1.47% | 35.7% |
| 5d ลง ใดๆ & **Vol ปกติ** | +2.64% | **-0.98%** | 14.5% |

**⚠️ Vol ปกติ + mom ลบ = avg close -0.98% → ขาดทุน! ห้ามเล่น**

### วิธีหา
1. Gap up ≥ 2% แต่ **5d momentum ลบ**
2. **Vol ≥ 2x** (ต้องมี — vol ปกติ = ขาดทุน)
3. Entry: OR high breakout เหมือน momentum
4. **TP: +2% ขายหมด** (ไม่รอ +3%)
5. **ขายก่อน 10:30 เด็ดขาด** (48% ปิดใกล้ low ของวัน)

### Bounce Fade Risk
| Close Position | N | Avg Ret |
|---------------|---|---------|
| Close near high (>0.7) | 3,589 | +3.61% |
| Close mid | 2,950 | +0.45% |
| **Close near low (<0.4)** | **5,988** | **-3.47%** |

**48% ของ bounce ปิดใกล้ low** → ต้องออกเร็ว

### Sector ที่ bounce ดี
| Sector | Bounce +2% |
|--------|-----------|
| **Utilities** | **30.5%** |
| **Technology** | 24.5% |
| Energy | 20.3% |

---

## 🟣 09:30-10:30 ET — Gap Down Reversal

**หาอะไร**: หุ้นที่ gap down -5%+ แต่ volume ไม่สูง = panic exhausted → bounce intraday
**Target**: +2-3%

### เงื่อนไข (ตรงข้ามกับ gap up!)
| Gap Down | Vol | N | +2% Close | +3% Close |
|----------|-----|---|-----------|-----------|
| **-5%+ & Vol ปกติ** | normal | 2,960 | **49.9%** | **41.1%** |
| -5%+ & Vol 2x+ | 2x+ | 2,137 | 25.2% | 20.6% |
| -2% & Vol ปกติ | normal | 22,829 | 27.2% | 17.0% |

**⚠️ ตรงข้ามกับ gap up: Vol ปกติ ดีกว่า Vol สูง!**
- Vol ปกติ = panic sell หมดแรง → bounce
- Vol สูง = selling ยังดำเนินต่อ → ลงต่อ

### วิธีหา
1. Scan หุ้นที่ gap down **≥ 5%** จาก prev close
2. Volume **ไม่สูง** (< 2x avg) = selling exhaustion
3. ถ้า Vol 2x+ → **ข้าม** (selling continues)
4. รอ first 15-30 min ดูว่า stabilize → entry เมื่อ higher low

### Entry
- รอ 09:45-10:00 ดู stabilize (ไม่ทำ new low)
- Buy เมื่อ higher low + green bar
- SL: day low | TP: +2-3% จาก entry
- Time stop: ถ้าไม่ bounce ภายใน 11:00 → ออก

---

## 🟢 10:00 ET — Volume Surge Scan (Entry ใหม่ได้)

**หาอะไร**: หุ้นที่เพิ่ง volume spike — **ไม่ต้อง gap เลย**
**Target**: +2-3%

### เงื่อนไข
| 10:00 Bar | Gap? | ปิด +3% |
|-----------|------|---------|
| **Vol 3x + Green 1%+** | **ไม่ gap** | **47%** |
| Vol 3x + Green 1%+ | Gap 2%+ | 44% |
| Vol 2x + Green | ไม่ gap | 27% |
| ปกติ | - | 6% |

### วิธีหา
1. ดู bar 10:00 ที่ **volume ≥ 3x avg + green ≥ 1%**
2. ไม่ต้อง gap = **ดีกว่า gap ด้วยซ้ำ** (47% vs 44%)
3. = institutional buyer เข้ามาหลังเปิด ไม่ใช่ retail chase
4. Check news/catalyst ที่ออกหลังเปิดตลาด

### Entry
- Buy 10:00-10:05 bar close | SL = 10:00 bar low
- TP1: +2% | TP2: +3%

---

## ⚠️ 10:00-10:30 ET — Kill Zone

**Peak Time Risk**: 14.3% peak ที่ 09:30 + 13.9% peak ที่ 10:30 = **28% ของหุ้นทำ peak ตรงนี้**

| Peak เมื่อไหร่ | Avg Peak | Avg Close | Giveback |
|---------------|----------|-----------|----------|
| **ก่อน 10:30** | +5.0% | **-0.4%** | **-5.4%** |
| หลัง 14:00 | +6.8% | +5.8% | -1.0% |

**กฎ**:
- ถ้าหุ้น +3% ก่อน 10:00 → **ขาย 50% ทันที** (83% จะ giveback)
- 10:30 higher high → ถือต่อได้
- 10:30 หลุดต่ำกว่า open → **ออกเลย** (ปิด +3% แค่ 8%)

---

## 🟡 10:30-12:00 ET — Noon Volume Surge (Entry ใหม่ได้)

**หาอะไร**: หุ้นที่ volume spike ช่วง sideways = institutional เข้ามาตอนคนอื่นพัก
**Target**: +1-2%

### เงื่อนไข
| Pattern | N | ปิด +3% Day | Max Gain |
|---------|---|------------|----------|
| **เช้า sideways (<2% range) → breakout 2%+** | 5,899 | **47.6%** | +1.72% |
| **Vol 3x + Green 1%+** | 18,904 | **38.1%** | +3.95% |
| Vol 3x + Green 0.5%+ | 26,942 | 24.7% | +2.95% |

### วิธีหา
1. **Consolidation Breakout**: หุ้นที่เช้า sideways แคบ (<2% range) แล้วเริ่ม breakout 2%+ ตอนเที่ยง = **47.6% ปิด +3%** (ดีมาก!)
2. **Vol Surge**: Scan หา bar ที่ **volume 3x + green 1%+** = institutional accumulation
3. ทั้ง 2 แบบดีกว่า setup เช้าที่ vol ไม่ถึง

### Entry
- Buy ที่ bar close ของ volume surge | SL = bar low
- TP: +1.5% | Time stop: ถ้าไม่ถึง +1% ภายใน 13:30 → ออก

### Confirm Hold (ไม่ใช่ entry)
ถ้าถือหุ้นจาก Scan 1/2 อยู่:
| 12:00 Status | ปิด +3%? | ทำอะไร |
|-------------|----------|--------|
| **ยืน +2% จาก open** | **51%** | **ถือต่อ** |
| ขึ้นแค่ 1% | 8% | **ออก** |
| ลงจาก open | 1% | **ออกทันที** |

---

## 🟠 13:00-14:00 ET — Pre-Power Hour Breakout (Entry ใหม่ได้)

**หาอะไร**: หุ้นที่ break morning high + volume = เริ่ม leg ใหม่ก่อน power hour
**Target**: +0.5-1%

### เงื่อนไข
| Pattern | N | +1% จาก break |
|---------|---|--------------|
| **New high + Vol 3x** | 6,860 | **13.5%** |
| New high + Vol 2x | 5,737 | 9.9% |
| New high + Vol ปกติ | 52,876 | 5.9% |

### วิธีหา
1. คำนวณ morning high (09:30-12:55)
2. Scan หาหุ้นที่ **break above morning high** ช่วง 13:00-14:00
3. ต้อง break ด้วย **volume 2x+** (ไม่มี vol = 11% ไม่คุ้ม)
4. Vol surge 3x ที่ยังไม่ break high ก็ดี = กำลังจะ break

### Entry
- Buy ที่ break above AM high + volume confirm | SL = AM high (support ใหม่)
- TP: +0.7% | Time stop: ถ้าไม่วิ่งภายใน 30 นาที → ออก

---

## 🔴 14:00-15:30 ET — Power Hour (Scalp/Confirm เท่านั้น)

**หาอะไร**: หุ้นที่ volume surge ช่วงปิด
**Target**: +0.3-0.5% (scalp เร็ว)

### เงื่อนไข
| Pattern | N | +1% |
|---------|---|-----|
| **Surge no new high (Vol 3x)** | 2,804 | **18.1%** |
| New high + Vol 2x | 26,979 | 9.6% |

### Confirm Hold (สำคัญกว่า entry ใหม่)
| 14:00 Status | ปิด +3%? | ทำอะไร |
|-------------|----------|--------|
| **ยืน +3% จาก open** | **80%** | **ถือถึงปิด** |
| ขึ้น 2% | 24% | พิจารณาออก |
| ขึ้น <1% | 4% | **ออก** |

**14:00 → close = แทบ 0% avg return** → อย่าเข้าใหม่ ใช้ confirm เท่านั้น

---

## สรุปทุกช่วง

| เวลา | หาอะไร | เงื่อนไข | Target | โอกาส |
|------|--------|----------|--------|-------|
| 06:00-09:25 | → ใช้ **ORB Prompt** | Gap + Vol + OR breakout | +3-5% | 62-66% |
| **09:30-09:35** | First Bar Momentum | Bar ±1%+ | +3-5% | **29-34%** |
| **09:30-10:30** | **🟣 Gap Down Reversal** | Gap **-5%+ & Vol ปกติ** | **+2-3%** | **41%** |
| **10:00** | **Vol Surge (no gap!)** | **Vol 3x + Green 1%+** | **+2-3%** | **47%** |
| ⚠️ 10:00-10:30 | Kill Zone (gap up) | ขาย 50% ถ้า +3% แล้ว | - | - |
| **10:30-12:00** | **Consolidation Breakout** | เช้า sideways → breakout 2%+ | +1-2% | **47.6%** |
| **10:30-12:00** | **Noon Vol Surge** | Vol 3x + Green 1%+ | +1-2% | **38.1%** |
| 12:00 | Confirm Hold | ยืน +2%? | - | 51% hold |
| **13:00-14:00** | **AM High Breakout** | New high + Vol 3x | +0.5-1% | **13.5%** |
| 14:00 | Confirm Hold | ยืน +3%? | - | 80% hold |
| 14:00-15:30 | Power Hour Scalp | Vol 3x surge | +0.3-0.5% | 18% |

**3 Play Types: Momentum (gap up + mom up) / Bounce (gap up + mom dn + vol 2x) / Gap Down Reversal (gap dn + vol ปกติ)**

---

## Hard Skip (ห้ามเทรด)

✗ Volume < 1.5x → fake move (ยกเว้น Gap Down Reversal ที่ vol ปกติ ดีกว่า)
✗ Yest +3%+ แต่ Vol < 1.5x → noise 82% ไม่ใช่ signal จริง
✗ 5d Mom > 20% + Vol < 2x → extreme profit-taking risk (peak เช้าแล้ว fade)
✗ Bounce play + Vol < 2x → avg close -0.98% ขาดทุน
✗ Gap Down + Vol 2x+ → selling continues ลงต่อ (ตรงข้ามกับ gap up!)
✗ Gap > 10% + ไม่มี catalyst → pump & dump
✗ Price < $5 → spread กว้าง
✗ First bar เฉยๆ (<0.3%) → ไม่มี momentum
✗ ราคาหลุด VWAP ก่อน 10:00 → buyer หมดแรง
✗ 10:30 หลุดต่ำกว่า open → momentum จบ (8% ปิด +3%)
✗ Sector = Utilities / Real Estate / Consumer Defensive → วิ่งน้อยมาก
✗ Peak ก่อน 10:30 + ลง VWAP → ขายทำกำไรเริ่มแล้ว ออก
✗ หลัง 14:00 + ยังไม่ถึง +2% → หมดเวลา ไม่คุ้มเข้า

---

## Output Format

สำหรับแต่ละช่วงเวลาที่ scan ให้ตอบ:

### [เวลา] Top Picks

| # | Symbol | Signal | Vol | Catalyst | Target | SL | Score |
|---|--------|--------|-----|----------|--------|----|-------|
| 1 | XXX | Gap/Surge/Break | X.Xx | ... | +X% | $XX | X/6 |

+ **ทำไมตัวนี้**: 1 บรรทัด
+ **Risk**: อะไรที่อาจ fail
+ **Time stop**: ออกเมื่อไหร่ถ้าไม่วิ่ง

### Market Context
- VIX + SPY trend
- Sector ไหน hot/cold
- Overall: AGGRESSIVE / NORMAL / DEFENSIVE
```

## Data Sources
- 557,833 daily bars (2024-2026, 856 symbols)
- 55,342,388 5-min bars (2023-2026)
- 6,385 peak-time trade analysis
- 162,346 Friday-Monday pairs
- Volume = #1 predictor across ALL time slots
