# Comprehensive Backtest Summary — 29 Tests

**Data**: 20.5M 5-min bars, 274K symbol-days, 2025-01-01 to 2026-04-10

## Top 10 Edges (by WR)

| Rank | Factor | WR | EV |
|---|---|---|---|
| 1 | Sec3d ≥ 2% | 95.3% | +9.04% |
| 2 | Sec3d ≥ 1% | 81.0% | +3.74% |
| 3 | Sec3d ≥ 0.5% | 71.6% | +2.55% |
| 4 | VIX 30+ at 12:00 | 68.9% | +1.57% |
| 5 | Deep <-5% from 20d MA | 68.4% | +2.35% |
| 6 | Top 3 sector today | 67.9% | +1.90% |
| 7 | 5d down -5%+ (reversal) | 66.6% | +2.19% |
| 8 | 13:00 + fresh + vol + SPY | 65.2% | +2.79% |
| 9 | SPY green @ 10:00 | 60.3% | — |
| 10 | Wednesday DOW | 59.8% | +2.35% |

## Critical Findings

### Time-of-day
- **Sweet spot**: 09:50-10:30 ET (WR 54-57%)
- **Dead zones**: 10:10-10:15 (pullback noise), 11:00-14:00 (no raw edge)
- **Afternoon strict (13:00)**: WR 65.2% WITH filters (fresh peak + vol + SPY green)
- **14:00+**: genuinely dead, no filter rescues

### Gap patterns (shocking reversal of conventional wisdom)
- **Gap UP +3-5% buy-at-open hold-close**: 43.4% WR -0.35% **LOSING**
- **Gap UP +8-12%**: 37.7% WR -0.78% **WORST**
- **Gap DOWN -3 to -5%**: 55.9% WR +0.47% **BEST**
- Insight: gap up fades through the day; gap down bounces

### SL/TP (wider better)
- SL -0.5% (tight): 28.1% WR (noise stops)
- SL -3.0% TP +5%: 54.3% WR +0.73% ⭐
- **Trail 1% from peak**: +0.93% EV (BEST exit)

### Sector importance
- Sec3d ≥ 0.5% = 71.6% WR (14 pp above baseline)
- Sec3d ≥ 1.0% = 81.0% WR
- Sec3d ≥ 2.0% = 95.3% WR (N=64, small but clear)
- **Top 3 sector today**: +19 pp WR vs not

### SPY direction critical after 10:00
- 10:00 SPY green: 60.3% / red: 52.3% (+8 pp)
- **11:00 SPY green: 56.0% / red: 37.3% (+19 pp!)**
- 12:00: 56.1% / 44.0% (+12 pp)
- 14:00: 55.1% / 40.7% (+14 pp)

### Catalyst (counter-intuitive)
- **No catalyst: 58.1% WR +0.98%** ⭐
- News: 50.5% / insider: 40.0% / SI: 51.3%
- **Having any catalyst HURTS momentum entries**

### Beta
- **1.0-2.0 sweet spot**: 60% WR
- <1.0: 53.2% (too defensive)
- >2.0: 54.5% (too wild)

### 5d momentum
- <-5% (reversal): 66.6% WR ⭐
- -5 to +5%: 53.2% (coin flip)
- **+5 to +15%: 46.2% WR (NEGATIVE, moderate rallies fade)**
- +30%+: 65.8% (parabolic continues)

### Day of week
- **Wednesday: 59.8% WR +2.35% EV** ⭐ BEST
- Monday: 59.3%
- Friday: 58.0%
- Tuesday: 53.4%
- Thursday: 52.8% (worst)

### VIX regime
- <18: 49.6% (no edge in calm)
- 18-24: 51.0%
- 24-30: 50.4%
- **30+: 68.9% WR +1.57% EV** (extreme vol = edge)

### SI sweet spot
- **15-20%: 59.6% WR +1.36%** ⭐
- <15%: ~57%
- >30%: 40% (over-shorted = avoid)

### Distance from 20d MA (mean reversion)
- **Deep <-5%: 68.4% WR +2.35%** ⭐
- 0 to -5%: 59.0%
- Near 0: 53.3%
- **Extended >+10%: 49.8% (overextended)**

### Intraday bounces (DEBUNKED)
- All drop depths, all times: 42-52% WR
- No intraday bounce edge found
- **Contradicts prompts "Down Bounce WR 57-72%"** — prompts measured differently

### Position sizing
- Equal weight: +121.7% total, Sharpe 1.80
- **Inverse beta weighting: +139.3% total, Sharpe 2.09** ⭐

### Mean reversion on P&L
- After 2 wins: -0.088% avg (reverts)
- After 2 losses: +1.034% avg (bounces)
- After 3 wins: -0.728% (bigger revert)
- After 3 losses: +1.103% (bigger bounce)
- **Don't add to winners. Don't skip after losses.**

### Drawdown limits HURT
- Skip after -1.5% day: -8.7% total (terrible)
- Skip after -2.5% day: +59.8%
- Skip after -3.5% day: +73.5%
- **Baseline (no limit): +121.7%** (all limits hurt)
- Counter-intuitive: don't stop trading after bad days

## What to change in scan code

### Score formula v2 (backtest-driven)

```
+2 SPY green daily          (validated: 60% vs 52% WR)
+2 AD ratio ≥ 2             (keep)
+2 In top 3 sector today    (NEW, +19 pp)
+2 Sec3d ≥ 0.5%             (HEAVIER weight: 71% WR)
+1 Beta 1.0-2.0             (CHANGED from <1.5)
+1 VIX > 25                 (NEW)
+1 Vol 1.5-2x (not 2x+)     (refined)
+1 Setup (drop/gain)        (keep)
+1 5d mom <-5% OR >30%      (NEW: extremes only)
-1 Catalyst any             (NEW NEGATIVE: catalyst hurts)
-1 Gap up 5%+               (NEW: gap up = losing)
-2 SPY red day, time ≥11:00 (NEW hard penalty)
-3 Time 14:00+              (NEW: dead zone)
```

### Filters
- Skip: Gap UP 5%+ (losing edge)
- Skip: Time 14:00+ (no edge even with filters)
- Skip: SPY red day + entry time ≥11:00
- ❌ Remove "intraday bounce" mode entirely (no edge)

### Exits
- Use **trail 1% from peak** as primary
- Fallback EOD if no trail trigger
- Fixed TP +5% hard cap (backtest-verified)
- SL -3% floor (not -0.5% noise stop)

### Position sizing
- **Inverse beta weighting** across top 3 picks
- No drawdown limits
- Don't chase winning streaks

### Day-of-week gate
- Wed = full size (1.0x)
- Mon/Fri = normal (1.0x)
- Tue/Thu = half size (0.5x) — lower edge
