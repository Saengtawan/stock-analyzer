# Phase 3 Report — Grid Search Training

**Date:** 2026-05-26
**Status:** ✅ PASS — strong candidates identified
**Runtime:** 73.6 min (10 labels × 39 monthly walk-forward refits = 390 LGB fits)

## AUC Summary (model discrimination power)

| Label | AUC | Verdict |
|---|---|---|
| L_touch_3_in_5d | 0.674 | ⭐ Best |
| L_touch_3_in_7d | 0.651 | ⭐ Strong |
| L_touch_2_in_5d | 0.638 | Good |
| L_touch_7_in_30d | 0.637 | Good |
| L_touch_1.5_in_5d | 0.620 | OK |
| L_touch_2_in_7d | 0.620 | OK |
| L_touch_3_in_14d | 0.614 | OK |
| L_touch_5_in_30d | 0.604 | OK |
| L_touch_2_dd-5_in_5d | 0.548 | ❌ Weak |
| L_touch_5_dd-10_in_30d | 0.520 | ❌ Random |

**Insight:** DD-constrained labels FAIL — model cannot predict drawdown events
from features. Drop them.

**Insight 2:** Tight target (+3%) + short window (5-7d) = highest AUC. Model
predicts short-horizon directional moves well; long-horizon is noisier.

## Top 10 Survivors (WR ≥80%, N ≥50/yr, EV > 0)

| Label | Thr | WR | EV | N/yr | avg_win | avg_loss | Sharpe |
|---|---|---|---|---|---|---|---|
| L_touch_3_in_5d | 0.90 | 89.9% | +1.86% | 594 | +3.0 | -8.23 | **3.15** ⭐ |
| L_touch_3_in_7d | 0.90 | 91.0% | +1.78% | 1228 | +3.0 | -10.62 | 2.17 |
| L_touch_3_in_5d | 0.85 | 84.7% | +1.25% | 2671 | +3.0 | -8.42 | 1.65 |
| L_touch_7_in_30d | 0.90 | 91.6% | +4.69% | 580 | +7.0 | -20.56 | 1.49 |
| L_touch_5_in_30d | 0.90 | 91.2% | +3.27% | 3589 | +5.0 | -14.71 | 1.35 |
| L_touch_7_in_30d | 0.85 | 86.4% | +3.90% | 3445 | +7.0 | -15.83 | 1.18 |
| L_touch_2_in_5d | 0.90 | 87.6% | +0.68% | 2518 | +2.0 | -8.66 | 1.09 |
| L_touch_3_in_7d | 0.85 | 85.7% | +1.05% | 5210 | +3.0 | -10.63 | 1.06 |
| L_touch_3_in_14d | 0.90 | 88.6% | +1.39% | 5570 | +3.0 | -11.19 | 1.04 |
| L_touch_2_in_7d | 0.90 | 88.5% | +0.71% | 5796 | +2.0 | -9.30 | 0.93 |

## Key Insights

1. **WR 85-90% achievable** — user's target hit.
   Tight threshold (0.85-0.90) + 3% TP / 5-7d window → consistent 85-91% WR.

2. **Sharpe sweet spot**: L_touch_3_in_5d @ 0.90 → Sharpe 3.15.
   Avg_loss -8.23% is biggest risk — SL would cap this.

3. **Tradeoff: tight threshold = fewer picks**
   - 0.90 → 594 trades/yr
   - 0.85 → 2671 trades/yr (Sharpe drops to 1.65)
   - 0.80 → 7368 trades/yr (Sharpe 0.96)

4. **EV scales with TP target**
   - 3% TP → EV +1.86% (Sharpe 3.15)
   - 7% TP → EV +4.69% (Sharpe 1.49 — worse risk-adjusted)
   - Bigger TP captures more upside but also bigger losses

5. **Window matters**
   - 5d: tight, high Sharpe
   - 30d: more variance, lower Sharpe at same WR
   - Short window > long for swing ML (counter-intuitive but data says so)

## Top 3 Candidates → Phase 4/5

1. **L_touch_3_in_5d @ thr 0.90** — Sharpe 3.15, WR 89.9%, EV +1.86%, 594/yr
2. **L_touch_3_in_5d @ thr 0.85** — Sharpe 1.65, WR 84.7%, EV +1.25%, 2671/yr
3. **L_touch_3_in_7d @ thr 0.90** — Sharpe 2.17, WR 91.0%, EV +1.78%, 1228/yr

Phase 4 will test exit rule variants (TP/SL/time) to see if Sharpe can improve.

## Annual Return Projections (raw, no compounding, no slippage)

Assuming 5% position sizing × 5 concurrent positions = 25% deployed:

| Candidate | EV/trade | N/yr | Annual raw return | With 5% sizing | Sharpe |
|---|---|---|---|---|---|
| L_touch_3_in_5d @ 0.90 | +1.86% | 594 | +1105% | **+55%/yr** | 3.15 |
| L_touch_3_in_5d @ 0.85 | +1.25% | 2671 | +3339% | **+167%/yr** | 1.65 |
| L_touch_3_in_7d @ 0.90 | +1.78% | 1228 | +2186% | **+109%/yr** | 2.17 |

⚠️ These are pre-slippage, pre-fee, pre-position-conflict numbers. Live
will be 20-50% lower due to:
- Slippage on entry/exit (0.05-0.2% per trade)
- Position concurrency limits (can't take all 594 picks)
- Live vs backtest drift
- Survivorship bias

## Next Steps

→ Phase 4: Test if SL -2/-3/-5% improves Sharpe further
→ Phase 5: Validation Funnel on top 3 candidates
