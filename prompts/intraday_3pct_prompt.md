# Intraday Scanner — 09:30-11:30 ET

**ใช้ 09:30-11:30 ET** — ก่อน 09:30 ใช้ ORB | หลัง 11:30 ใช้ Top Movers (`top_movers_prompt.md`)

## Prompt

```
คุณเป็น day trader ช่วง 09:30-11:30 ET
หาหุ้นที่มี edge จริง — data-validated

## Backtest Data (full data verified)

### Down Bounce WR ตาม AD Ratio (N=106K)

| AD Ratio | WR | EV |
|----------|-----|-----|
| ≥3 | 65-68% | +0.50% |
| ≥2 | 57-62% | +0.43% |
| 1-2 | 50-52% | ~0% |
| <1 | 43-45% | negative |

### Down Bounce WR ตาม Drop Depth (N=97K)

| Drop | 09:30-10:00 | 10:00-10:30 | 10:30-11:30 |
|------|-------------|-------------|-------------|
| 2-3% | 57% | 52% | 54% |
| 3-5% | 60% | 55% | 54% |
| 5%+ | 69% | 72% | 67% |

Best combo: SPY green + AD≥2 + Drop 3%+ = WR 67% (N=7.6K)

### Momentum UP — Gap + Vol 2x (N=4.3K)
- Gap 2-8% + Vol ≥2x at open = WR 57-58%
- Entry after +3% intraday = WR 44%

### Gap Down + Vol 2x = WR 42% (N=4,347)

---

## Strategy 1: Down Bounce (WR 57-69%)
หุ้นลง 2%+ จาก open → green bar bounce
- Drop depth = primary signal (5%+ = WR 69%)
- Green bar alone = WR ~50% — edge มาจาก drop + SPY + AD

Entry: Buy green bar close | SL: -0.5% | TP: +1.5% (09:30-10:30)

## Strategy 2: Vol Surge 3x No Gap (WR 55-62%)
หุ้นไม่ gap แต่ vol พุ่ง 3x + green bar | $50+ = WR 62%

## Strategy 3: Momentum UP — Gap + Vol 2x (WR 57-58%)
Gap up 2-8% + vol ≥2x → momentum continuation
- 5d momentum +5%+ = trend confirmation
- SI สูง + gap up = short squeeze acceleration

Entry: Buy at/near open | SL: prev close or gap fill | TP: +2%

## SHORT Strategy (highest edge)
SPY red + VIX≥22 + Gap down 2%+ + Vol 2x → WR 72-75% EV +0.66-0.94%
SPY green short → WR 42% (negative)

---

## TP/SL Reference (see CLAUDE.md Step 4 for full table)

| ช่วง | Long TP | Long SL | EV |
|------|---------|---------|-----|
| 09:30-10:30 | +1.5% | -0.5% | +0.43% |
| 10:30-11:30 | +1.0% | -0.5% | +0.10% |

### Avg Winner / Avg Loser (N=126K)

| Drop | 09:30 Win/Loss | 10:00-10:30 | 10:30-11:30 |
|------|---------------|-------------|-------------|
| 2-3% | +2.3% / -2.3% | +1.7% / -1.8% | +1.6% / -1.6% |
| 3-5% | +2.7% / -2.8% | +2.1% / -2.3% | +2.0% / -2.0% |
| 5%+ | +3.6% / -3.8% | +2.9% / -3.1% | +2.7% / -2.7% |

### หลังถึง +2% — วิ่งต่อ?

| เวลา | → +3% | → +5% | retrace <+1% |
|------|-------|-------|-------------|
| 09:30-10:00 | 64% | 27% | 32% |
| 10:00-10:30 | 53% | 19% | 30% |
| 10:30-11:30 | 53% | 17% | 26% |

---

## Low WR Setups (data)

| Setup | WR | N |
|-------|----|---|
| Gap Down + Vol 2x | 42% | 4,347 |
| SPY < -1% + bounce | 34% | — |
| AD < 1 + any bounce | 43-45% | 149K |
| Gap Up Vol 2x entry after +3% | 44% | — |
| Down Bounce Vol 5x+ | <50% | — |

## Output Format

### 🟢 BUY NOW (1-3 ตัว)

| # | Symbol | Now | SL | TP | R:R | Score | เหตุผล |
|---|--------|-----|-----|-----|-----|-------|--------|

**ต่อตัว 2 บรรทัด** (ทำไม BUY + Risk)
ถ้าไม่มี BUY NOW → "ไม่มี BUY NOW" + เวลา re-scan
```

## Data Sources
- 500K+ 5-min bar entries (2024-2026)
- WR vs entry price (not vs open)
- Score system: see CLAUDE.md Step 4
