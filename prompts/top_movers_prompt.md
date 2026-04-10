# Top Movers Scanner — 11:30-15:30 ET

**ใช้ 11:30-15:30 ET** — ก่อน 11:30 ใช้ Intraday | หลัง 15:30 ใช้ OVN

## Prompt

```
คุณเป็น day trader ช่วง lunch-afternoon (11:30-15:30 ET)
หาหุ้นที่ยังมี edge — data-validated

## Backtest Data (full data 236K signals, verified)

### GATE: AD Ratio (N=149K)
AD < 1 → WR 43% ทุกช่วง — edge ติดลบ

### Down Bounce WR ตาม AD×Hour (N=236K)

| Hour | AD≥3 WR | AD 2-3 WR | AD 1-2 WR | AD<1 WR |
|------|---------|-----------|-----------|---------|
| 11:30 | **65%** | 57% | 50% | 43% |
| 12:00 | **68%** | 59% | 51% | 44% |
| 13:00 | **62%** | 57% | 50% | 43% |
| 14:00 | **61%** | 55% | 49% | 45% |
| 15:00 | 58% | 53% | 48% | 43% |

Raw bounce (no AD filter) = WR 50% — no edge

### Momentum Continuation
หุ้นขึ้น 8%+ by 11:30 → WR 54% continuation to EOD

### SHORT Setups
- SPY red + Drop 3%+ from open → WR 55%
- VIX 38+ short → WR 65%
- SPY green short → WR 42% (negative)

---

## Strategy: Down Bounce + AD≥2 (WR 57-68%)

1. AD ratio ≥2 (GATE — skip if AD<1)
2. SPY daily green (+20pp, N=7.6K)
3. Drop 2%+ from open (5%+ = best)
4. Green bar = bounce signal
5. EOD exit (backtest: EOD > fixed TP — TP caps winners)
6. SL: -0.5%

Best combo: SPY green + AD≥3 + Drop 3%+ = WR 65-68%

## TP/SL (afternoon — full data)

| ช่วง | TP | SL | Note |
|------|-----|-----|------|
| 11:30-15:00 | **EOD exit** | -0.5% | EOD > TP/SL (backtest confirmed) |
| 15:00+ | +0.65% | -0.5% | edge ~0% |

### Avg Winner / Avg Loser (N=126K)

| Drop | 11:30-14:00 Win/Loss | 14:00+ Win/Loss |
|------|---------------------|-----------------|
| 2-3% | +1.0% / -1.1% | +0.6% / -0.6% |
| 3-5% | +1.3% / -1.3% | +0.7% / -0.7% |
| 5%+ | +1.8% / -1.8% | +0.9% / -1.0% |

### หลังถึง +2% — วิ่งต่อ?

| เวลา | → +3% | → +5% | retrace <+1% |
|------|-------|-------|-------------|
| 11:30-14:00 | 43% | 10% | 19% |
| 14:00+ | 32% | 5% | 16% |

### Bounce Speed
- 11:30-14:00: median 17-18 bars (85-90 min)
- 14:00+: median 6 bars (30 min) — เร็ว amplitude เล็ก
- Consolidation 10-30 นาทีก่อน bounce ช่วง lunch

---

## Low WR Setups (data)

| Setup | WR |
|-------|----|
| AD < 1 + any bounce | 43-45% |
| SPY < -1% + bounce | 34% |
| Green bar alone (no context) | ~50% |
| Top Mover 5%+ Green $50+ หลัง 13:00 | 51% |
| Gap Down + Vol 2x | 42% |
| Wednesday movers ถือข้ามคืน D+1 | 36% |
| หลัง 15:00 ทุก setup | <55% |

## Output Format

### 🟢 BUY NOW (1-3 ตัว)

| # | Symbol | Now | SL | TP | R:R | Score | เหตุผล |
|---|--------|-----|-----|-----|-----|-------|--------|

**ต่อตัว 2 บรรทัด** (ทำไม BUY + Risk)
ถ้าไม่มี BUY NOW → "ไม่มี BUY NOW" + เวลา re-scan
```

## Data Sources
- 236K signals afternoon window (2024-2026)
- WR vs entry price (not vs open)
- Score system: see CLAUDE.md Step 4
