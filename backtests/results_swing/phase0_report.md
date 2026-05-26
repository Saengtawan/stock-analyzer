# Phase 0 Report — Swing ML Feasibility

**Date:** 2026-05-26
**Status:** ✅ PASS — data sufficient, base rates favorable

## Data Inventory

| Resource | Coverage | Notes |
|---|---|---|
| `stock_daily_ohlc` | 2020-2026 (6.4y) | 1,572,687 rows × 1046 symbols ⭐ |
| `earnings_history` | 2006-2026 | 985 symbols, 25K rows — usable for filter |
| `stock_fundamentals` | current snapshot | 1008 symbols (PE, beta, sector, mcap) |
| `macro_snapshots` | 2018-2026 | 2163 days (VIX, SPY, sector ETFs) |
| `market_breadth` | 2020-2026 | 1413 days |
| `short_interest` | partial | 11K rows |
| `news_events` | Mar 2026+ only | ❌ too short for backtest |
| `insider_transactions` | Mar 2026+ only | ❌ too short for backtest |
| `intraday_bars_5m` | available | ✅ for intraday features if needed |

**Conclusion:** Daily OHLC + earnings + fundamentals + macro = plenty for swing research.
News/insider too recent to use as backtest features.

## Forward Return Distribution (1.57M rows)

| Window | Median fhigh | p95 fhigh | Median flow | p5 flow |
|---|---|---|---|---|
| 3d | +2.2% | +10.4% | -2.1% | -9.8% |
| 5d | +3.0% | +13.7% | -2.7% | -12.5% |
| 7d | +3.6% | +16.3% | -3.2% | -14.7% |
| 14d | +5.3% | +23.8% | -4.6% | -20.2% |
| 30d | +8.2% | +36.8% | -6.8% | -28.5% |

**Key insight:** Median forward return is *positive* (slight upward drift), variance grows with window.

## Base Rates (overall, 2020-2026)

### Tier 1: High base rate (70%+) — best for WR 85-90% target
| Label | Base Rate | ML target WR | Lift needed |
|---|---|---|---|
| L_touch_1.5_in_5d | 71.8% | 88% | +16% |
| L_touch_2_in_7d | 69.6% | 88% | +18% |
| L_touch_3_in_14d | 69.4% | 88% | +19% |

⭐ **Easiest to reach 85-90% WR** — modest target, short-medium window.

### Tier 2: Moderate base rate (50-70%)
| Label | Base Rate | ML target WR | Lift needed |
|---|---|---|---|
| L_touch_5_in_30d | 67.3% | 85% | +18% |
| L_touch_2_in_5d | 63.9% | 85% | +21% |
| L_touch_1.5_in_3d | 63.5% | 85% | +22% |
| L_touch_3_in_7d | 56.9% | 85% | +28% |
| L_touch_7_in_30d | 56.1% | 80% | +24% |
| L_close_green_30d | 55.1% | 80% | +25% |
| L_touch_5_in_14d | 52.5% | 80% | +27% |
| L_touch_2_dd-5_in_5d | 52.2% | 80% | +28% ⭐ DD constraint |
| L_touch_5_dd-10_in_30d | 51.2% | 80% | +29% ⭐ DD constraint |

### Tier 3: Lower base rate (35-50%) — higher avg_win, harder WR
| Label | Base Rate | ML target WR | Lift needed |
|---|---|---|---|
| L_touch_3_in_5d | 49.7% | 75% | +25% |
| L_touch_3_dd-5_in_7d | 44.3% | 70% | +26% |
| L_touch_7_dd-10_in_30d | 43.9% | 70% | +26% |
| L_touch_10_in_30d | 42.2% | 65% | +23% |
| L_touch_5_dd-7_in_14d | 41.2% | 70% | +29% |
| L_touch_5_in_7d | 37.0% | 65% | +28% |

### Tier 4: Very hard (<35%) — likely impractical
| Label | Base Rate |
|---|---|
| L_touch_5_dd-5_in_14d | 35.8% |
| L_touch_3_dd-3_in_7d | 35.1% |
| L_close_3_at_7d | 30.1% |
| L_close_5_at_14d | 28.1% |
| L_close_10_at_30d | 23.0% |

## Phase 1 Candidates (top 10 for label exploration)

For WR ≥85% target with reasonable avg_win:

1. **L_touch_2_in_7d** (base 70%) — modest target, 7d window, easiest for WR 85%+
2. **L_touch_3_in_14d** (base 69%) — slightly bigger target, 14d window
3. **L_touch_1.5_in_5d** (base 72%) — easiest target
4. **L_touch_3_in_7d** (base 57%) — sweet spot avg_win vs WR
5. **L_touch_2_dd-5_in_5d** (base 52%) — DD-constrained (risk-adjusted)
6. **L_touch_5_in_30d** (base 67%) — user's original ask
7. **L_touch_5_dd-10_in_30d** (base 51%) — risk-adjusted version of #6
8. **L_touch_3_in_5d** (base 50%) — tight window aggressive
9. **L_touch_7_in_30d** (base 56%) — bigger win, longer hold
10. **L_close_green_5d** (base 53%) — simplest "any profit"

## Risks Identified

1. **Survivorship bias**: universe = 1046 currently-listed. Delisted/merged excluded.
   Mitigation: accept this; document live ≠ backtest.
2. **No news/insider feature**: <2 months data — not usable for backtest.
3. **Earnings noise**: must filter from labels (like label_smart_v2 in v2.6.0).
4. **Multiple testing**: 30 labels tested → high false discovery risk.
   Mitigation: TRUE OOS holdout untouched until Phase 5.

## Next Step

→ Phase 1: deeply analyze top 10 label variants with per-year base rates,
  fundamental sanity (signal-noise per sector/mcap), feature signal correlation.
