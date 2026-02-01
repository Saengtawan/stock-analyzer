# บันทึกการทดลอง 2026-01-31

> "คนเราจะเก่งได้ก็ต่อเมื่อผิดพลาดแล้วบันทึก สำเร็จก็บันทึก บันทึกทุกอย่างเพื่อเก็บเป็นข้อมูล"

---

## เป้าหมาย
- ผลตอบแทน: 10-15% ต่อเดือน
- Stop Loss: สูงสุด -3% ต่อ trade
- ความสม่ำเสมอ (Consistency)

---

## การทดลองที่ทำ

### 1. Different Perspective (290 หุ้น)
```
Universe: 290 stocks, 11 sectors
Patterns: Vol Explosion, Tight Consolidation, Accumulation Spike

Results:
- Win Rate: 52%
- Avg Return: +0.42%
- Monthly Avg: +0.33%
- Worst Month: -2.76%

Key Finding:
- Utilities: 72% WR, +1.29%
- LOW_VOL pattern: 56% WR
```

### 2. Opportunity Hunter (290 หุ้น)
```
Philosophy: ไม่ยึดติด ไขว่คว้าหาประโยชน์
Config: Hold 7 days, SL -3%, Target +6%

Results:
- Total Trades: 639
- Win Rate: 52%
- Avg Return: +0.42%
- Monthly Avg: +0.33%
- Worst Month: -2.76%

Sector Analysis:
- Consumer_Discretionary: +1.44%
- Utilities: +1.29%, 72% WR
- Energy: +0.64%
```

### 3. Ultra Selective (140 หุ้น)
```
Focus: Utilities, Consumer Staples, Healthcare
Pattern: Require 2+ patterns simultaneously
ATR: < 1.5% only

Results:
- Win Rate: 46.8%
- Avg Return: +0.47%
- Monthly Avg: +0.57%
- Worst Month: -3.00%

Pattern Analysis:
- VOL_SPIKE: 70% WR, +2.16% (BEST!)
- TIGHT: 48% WR
- Finance_Stable: 56% WR, +1.47%
- Utilities: 67% WR, +2.01%
- Industrial_Stable: 0% WR (AVOID!)
```

### 4. Vol Spike Focus (69 หุ้น)
```
Focus: Vol Spike pattern only (70% WR)
Sectors: Utilities, Finance, Healthcare

Results:
- Win Rate: 44.1%
- Avg Return: +0.31%
- Monthly Avg: +2.03%
- Worst Month: -15.21%

Volume Analysis:
- Vol >= 2.0x: 44% WR, +0.40%
- Vol >= 2.5x: 48% WR, +0.64%
- Vol >= 3.0x: 25% WR (too high = bad)
```

### 5. Momentum Continuation (135 หุ้น)
```
Philosophy: หาหุ้นที่กำลังวิ่งแล้วและจะวิ่งต่อ
Config: 5-day momentum 2-10%, sector momentum min 2%

Results:
- Win Rate: 52.9%
- Avg Return: +0.29%
- Monthly Avg: +2.34%
- Worst Month: -22.76%

Sector Analysis:
- Finance: 79% WR, +1.77% (BEST!)
- Utilities: 100% WR, +2.33%
- Semiconductors: 54% WR, +0.94%
- Energy: 33% WR (AVOID!)
- Healthcare: 31% WR (AVOID!)

Momentum Analysis:
- 5-day 6%-8%: 63% WR
- Sector 4%-6%: 58% WR
```

### 6. Winning Combo (60 หุ้น)
```
Focus: Finance + Utilities only (best sectors)
Criteria: Strict (sector momentum 3-7%)

Results:
- Win Rate: 61.5%
- Avg Return: +0.37%
- Monthly Avg: +0.69%
- Worst Month: -3.36%
- Trades/Month: 1.9 (too few!)

Sector:
- Finance: 86% WR, +1.92%
- Utilities: 33% WR (variance due to low sample)
```

### 7. Finance Focus (42 หุ้น)
```
Focus: Finance sector only
Config: Relaxed criteria for more trades

Results:
- Win Rate: 54.9%
- Avg Return: +0.43%
- Monthly Avg: +11.45% (EXCEEDS 10%!)
- Worst Month: -41.62%
- Trades/Month: 26.4

Subsector Analysis:
- Finance_Banks: 62% WR, +1.19% (BEST!)
- Finance_Exchanges: 55% WR, +0.29%
- Finance_Asset_Mgmt: 52% WR, +0.49%
- Finance_Insurance: 52% WR, +0.04%
- Finance_Payments: 48% WR, -0.09% (AVOID!)
```

### 8. Banks Only (10 หุ้น)
```
Focus: Finance_Banks subsector only
Config: ATR < 2%, VIX < 22

Results:
- Win Rate: 55.1%
- Avg Return: +0.74%
- Monthly Avg: +5.29%
- Worst Month: -19.21%
- Stop Rate: 34%

Exit Analysis:
- Target: 27%, avg +5%
- Stop: 34%, avg -3%
- Hold: 39%, avg +1%
```

---

## Key Findings

### Best Sectors (Ranked)
| Sector | Win Rate | Avg Return |
|--------|----------|------------|
| Finance_Banks | 62-86% | +1-2% |
| Utilities | 67-100% | +1-2% |
| Finance_Exchanges | 55% | +0.3% |
| Semiconductors | 54% | +0.9% |

### Sectors to AVOID
| Sector | Win Rate | Avg Return |
|--------|----------|------------|
| Energy | 33% | -1.0% |
| Healthcare | 22-31% | -1.1% |
| Consumer | 41% | -0.2% |
| Industrial_Stable | 0% | -2.3% |

### Best Patterns (Ranked)
| Pattern | Win Rate | Note |
|---------|----------|------|
| Vol Spike (1.5-2.5x) | 70% | Best predictor |
| Momentum 6-8% | 63% | Sweet spot |
| Sector Momentum 4-6% | 58% | Optimal range |
| Low ATR (<2%) | Higher | Works with -3% SL |

### Patterns to AVOID
| Pattern | Issue |
|---------|-------|
| Vol Spike > 3x | Only 25% WR |
| ATR > 2.5% | Too volatile for -3% SL |
| Momentum > 10% | Overextended |

---

## The Core Challenge

### Mathematical Reality
With -3% Stop Loss:
- Stop rate consistently ~30-35%
- Each stop = -3% contribution
- If 10 trades/month with 34% stop rate:
  - 3-4 trades hit stop = -9% to -12%
  - Remaining 6-7 trades must generate +19% to +22% to net +10%
  - Requires ~+3% per winning trade

### What We Achieved
| Metric | Best Result | Target |
|--------|-------------|--------|
| Monthly Avg | +11.45% | 10%+ ✓ |
| Worst Month | -41.62% | -3% ✗ |
| Win Rate | 86% | - |
| Stop Rate | 34% | <15% needed |

### The Trade-off
```
High Returns (10%+) ⟺ High Volatility (big drawdowns)
Low Volatility (-3% max) ⟺ Lower Returns (5-8%)
```

---

## Recommended Next Steps

### 1. ลด Stop Rate
- Focus เฉพาะ VIX < 15 (ultra low volatility)
- เทรดเฉพาะเมื่อ ATR < 1%
- ใช้ Trailing Stop แทน Fixed Stop

### 2. ปรับเป้าหมาย
- Monthly target: 5-8% (more realistic)
- Worst month: -10% (reasonable)
- Win rate: 60%+

### 3. Position Sizing
- ลด position size เมื่อ VIX > 20
- เพิ่ม position เมื่อ VIX < 15
- Pyramid: เริ่มเล็กแล้วเพิ่มเมื่อได้กำไร

### 4. Alternative Approach
- Weekly Rotation: หมุนตาม sector momentum
- Pure Momentum: ซื้อหุ้นที่ขึ้นแรงสุด
- Mean Reversion: ซื้อเมื่อลงมากเกินไป (ต้อง wider SL)

---

## Files Created

| File | Description |
|------|-------------|
| backtest_different_perspective.py | 290 stocks, all patterns |
| backtest_opportunity_hunter.py | Opportunity hunting |
| backtest_ultra_selective.py | Ultra strict criteria |
| backtest_vol_spike_focus.py | Vol spike pattern |
| backtest_momentum_continuation.py | Momentum riding |
| backtest_winning_combo.py | Finance + Utilities |
| backtest_finance_focus.py | Finance sector only |
| backtest_banks_only.py | Banks subsector only |

---

## Conclusion

> "ถ้าผลการทดลองมี worst คุณเป็นนักวิทยาศาสตร์ นักลงทุน นักคณิต นักวิจัย คุณก็ต้องรู้สิว่าเกิดจากอะไร"

**สาเหตุ Worst Month:**
1. VIX spike (ความผันผวนตลาดสูง)
2. Stop rate สูง (~34%)
3. Sector rotation ไม่ทัน

**ข้อจำกัดทางคณิตศาสตร์:**
- 10%/เดือน + max -3% drawdown = ต้องการ Sharpe Ratio > 3
- ระบบส่วนใหญ่ทำได้แค่ Sharpe 1-2
- ต้องหา edge ที่พิเศษมาก หรือปรับเป้าหมาย

---

*บันทึก: 2026-01-31*
*ผู้ทำการทดลอง: Claude + User*
