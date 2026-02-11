# VIX Adaptive v3.0 — Implementation Checklist

**Last Updated**: 2026-02-11
**Status**: Backtest Complete, Ready for Implementation

---

## ✅ Pre-Implementation (COMPLETE)

- [x] Design VIX Adaptive v2.0
- [x] Identify mean reversion failure at high VIX
- [x] Invent bounce strategy for HIGH tier
- [x] Test 270 bounce configurations
- [x] Backtest 2022-2024 (bull market)
- [x] Backtest 2020-2024 (includes COVID)
- [x] Optimize boundaries (20/24/38)
- [x] Validate 3-tier system
- [x] Document results
- [x] Update MEMORY.md

---

## 📋 Implementation Checklist

### Phase 1: Core Components

#### 1.1 VIX Data Integration
- [ ] Create `src/data/vix_data_provider.py`
  - [ ] Fetch VIX from yfinance (^VIX)
  - [ ] Cache VIX data locally
  - [ ] Provide current VIX value
  - [ ] Provide VIX history for direction check
- [ ] Add VIX to existing data pipeline
- [ ] Test VIX data refresh on market open

#### 1.2 VIXTierManager Class
- [ ] Create `src/strategies/vix_adaptive/tier_manager.py`
  - [ ] `__init__(boundaries: dict)`
  - [ ] `get_tier(vix: float) -> str`
  - [ ] `get_vix_direction(vix_today, vix_yesterday) -> str`
  - [ ] Support boundaries: 20/24/38
- [ ] Unit tests for tier detection
- [ ] Test hysteresis (if needed)

#### 1.3 Adaptive Score Threshold
- [ ] Create `src/strategies/vix_adaptive/score_adapter.py`
  - [ ] `detect_market_regime() -> str`
  - [ ] `get_score_threshold(regime: str) -> float`
  - [ ] Bull: 90, Bear: 70, Normal: 80
- [ ] OR: Implement percentile-based (top 30%)
- [ ] Test with historical score distributions
- [ ] Add regime detection logic (VIX-based or SMA200-based)

### Phase 2: Strategy Classes

#### 2.1 MeanReversionStrategy (NORMAL tier)
- [ ] Create `src/strategies/vix_adaptive/mean_reversion.py`
  - [ ] `scan_signals(date, score_threshold) -> List[Signal]`
  - [ ] Entry: score >= threshold, yesterday_dip <= -1.0%
  - [ ] Position sizing: [40%, 40%, 20%] by score
  - [ ] Max 3 positions
- [ ] Stop loss: 2-4% (ATR-based, capped)
- [ ] Trailing stop: +2% activation, 75% lock
- [ ] Time exit: 10 days
- [ ] Unit tests for signal generation

#### 2.2 BounceStrategy (HIGH tier)
- [ ] Create `src/strategies/vix_adaptive/bounce_strategy.py`
  - [ ] `scan_bounce_signals(date, vix_falling) -> List[Signal]`
  - [ ] Entry criteria:
    - [ ] min_score >= 85
    - [ ] gain_2d >= +1.0% (bounce confirmation)
    - [ ] dip_from_3d_high <= -3.0% (dip requirement)
    - [ ] VIX falling (today < yesterday)
  - [ ] Position sizing: [100%] (1 position max)
- [ ] Stop loss: 3-6% (wider for volatility)
- [ ] NO trailing stop
- [ ] Time exit: 10 days
- [ ] Unit tests for bounce detection
- [ ] Calculate return_2d, dip_from_3d_high indicators

### Phase 3: Trading Engine Integration

#### 3.1 Main VIXAdaptiveStrategy Class
- [ ] Create `src/strategies/vix_adaptive/vix_adaptive_strategy.py`
  - [ ] `__init__(config)`
  - [ ] `update(date) -> List[Action]`
  - [ ] `get_current_tier() -> str`
  - [ ] Route to correct strategy based on tier
- [ ] Handle tier transitions
- [ ] EXTREME tier: Close all positions
- [ ] SKIP tier: No new trades, manage existing only
- [ ] NORMAL tier: MeanReversionStrategy
- [ ] HIGH tier: BounceStrategy

#### 3.2 Position Manager Updates
- [ ] Modify position manager to support tier-based rules
- [ ] Track which tier each position was opened in
- [ ] Apply tier-specific stop loss ranges
- [ ] Apply tier-specific time exits

#### 3.3 Risk Manager Updates
- [ ] Add VIX extreme handler (close all when VIX > 38)
- [ ] Add adaptive position sizing (if needed)
- [ ] Ensure stop losses respect tier ranges

### Phase 4: Configuration

#### 4.1 Config File
- [ ] Create `config/vix_adaptive.yaml`
```yaml
version: "3.0"

boundaries:
  normal_max: 20
  skip_max: 24
  high_max: 38

tiers:
  normal:
    strategy: mean_reversion
    min_score: 90  # Will be adjusted dynamically
    min_dip_yesterday: -1.0
    max_positions: 3
    position_sizes: [40, 40, 20]
    max_hold_days: 10
    stop_loss_range: [2.0, 4.0]
    trail_activation_pct: 2.0
    trail_lock_pct: 75

  high:
    strategy: bounce
    min_score: 85
    bounce_type: gain_2d_1.0
    dip_requirement: dip_3d_-3
    vix_condition: falling_1d
    max_positions: 1
    position_sizes: [100]
    max_hold_days: 10
    stop_loss_range: [3.0, 6.0]
    use_trailing: false

score_adaptation:
  enabled: true
  method: vix_based  # or: percentile
  thresholds:
    bull: 90   # VIX < 15
    normal: 80 # VIX 15-20
    bear: 70   # VIX > 20
```

#### 4.2 Load Configuration
- [ ] Add config loader in strategy __init__
- [ ] Validate config parameters
- [ ] Allow runtime config updates

### Phase 5: Monitoring & Logging

#### 5.1 Tier Transition Logging
- [ ] Log all tier changes (NORMAL → SKIP → HIGH → EXTREME)
- [ ] Track time spent in each tier
- [ ] Alert on EXTREME tier activation

#### 5.2 Performance Metrics by Tier
- [ ] Separate metrics for each tier:
  - [ ] Win rate by tier
  - [ ] Avg PnL by tier
  - [ ] Trade count by tier
  - [ ] Max DD by tier
- [ ] Track score distribution (for adaptive threshold)
- [ ] Monitor regime detection accuracy

#### 5.3 Alerts
- [ ] VIX > 38 (EXTREME tier)
- [ ] VIX enters HIGH range (24-38)
- [ ] Drawdown thresholds: 3%, 6%, 10%, 15%, 20%
- [ ] Win rate below 45% (rolling 20 trades)
- [ ] Score threshold adjustment (regime change)

### Phase 6: Testing

#### 6.1 Unit Tests
- [ ] Test VIXTierManager
- [ ] Test BounceStrategy signal detection
- [ ] Test MeanReversionStrategy signal detection
- [ ] Test score threshold adaptation
- [ ] Test position sizing

#### 6.2 Integration Tests
- [ ] Test full strategy on historical data
- [ ] Verify tier transitions
- [ ] Verify EXTREME tier closes all positions
- [ ] Verify bounce signals only fire when VIX falling
- [ ] Verify adaptive score threshold changes

#### 6.3 Backtest Validation
- [ ] Re-run backtest with implemented code
- [ ] Compare to original backtest results:
  - [ ] 2022-2024: ~+80-153% return
  - [ ] 2020-2024: ~+149% return
  - [ ] Win rate: ~52-53%
  - [ ] Max DD: ~15-20%
- [ ] If results differ by >5%, investigate

### Phase 7: Paper Trading (MANDATORY)

#### 7.1 Setup Paper Trading
- [ ] Enable VIX Adaptive in paper trading mode
- [ ] Disable other strategies (or run separately)
- [ ] Set initial capital: $10,000 (match backtest)

#### 7.2 Paper Trading Requirements
- [ ] Duration: Minimum 30 trading days
- [ ] Minimum trades: 10 trades (prefer 15-20)
- [ ] Regime coverage: Must include NORMAL and ideally HIGH tier days

#### 7.3 Success Criteria (ALL must pass)
- [ ] Rolling 20-trade win rate >= 45%
- [ ] Max losing streak <= 7
- [ ] Entry miss rate <= 15%
- [ ] Entry slippage <= 0.2%
- [ ] Zero rule violations
- [ ] Drawdown < 20%

#### 7.4 Distribution Checks (NOT averages!)
- [ ] Check win rate in rolling 20-trade windows
- [ ] Verify max losing streak in any window
- [ ] Confirm avg win >= 2.5% in any window

#### 7.5 Stress Scenarios
- [ ] If VIX spikes > 38: Verify EXTREME tier activates
- [ ] If VIX 24-38: Verify bounce signals only on VIX falling
- [ ] If market drops -5%: Verify stop losses work
- [ ] After 5 losses: Verify emotional discipline to follow rules

### Phase 8: Live Trading (Gradual Scale-Up)

#### 8.1 Week 1-4: 10% Capital
- [ ] Capital: 10% of intended amount
- [ ] Max positions: 1 (learn execution)
- [ ] Success: Win rate >= 45%, zero violations

#### 8.2 Week 5-8: 25% Capital
- [ ] Capital: 25% of intended amount
- [ ] Max positions: 2
- [ ] Success: Win rate >= 48%, handle 3-loss streak

#### 8.3 Week 9-12: 50% Capital
- [ ] Capital: 50% of intended amount
- [ ] Max positions: 3 (full strategy)
- [ ] Success: Win rate >= 50%, DD < 15%

#### 8.4 Week 13+: Full Capital
- [ ] Capital: 100% of intended amount
- [ ] Max positions: 3
- [ ] Ongoing: Weekly review, monthly check, quarterly review

---

## 🚨 Critical Reminders

### DO:
- ✅ Use VIX direction filter for HIGH tier (VIX falling)
- ✅ Skip trading when VIX 20-24
- ✅ Adapt score threshold to market regime (70-90)
- ✅ Close ALL positions when VIX > 38
- ✅ Use bounce strategy (not mean reversion) for HIGH tier
- ✅ Test on paper for 30+ days before live

### DON'T:
- ❌ Use mean reversion at VIX 24-38 (44.7% win rate)
- ❌ Trade during VIX 20-24 (41.2% win rate)
- ❌ Use fixed min_score=90 across all regimes
- ❌ Ignore VIX direction (drops win rate 50%)
- ❌ Skip paper trading
- ❌ Change locked parameters (20/24/38, gain_2d_1.0, etc.)

### CRITICAL BUGS TO AVOID:
1. **Date Type Mismatch**: Stock data uses `datetime.date`, loop may use `pandas.Timestamp` → convert before lookup
2. **yesterday_dip Calculation**: Must use `.shift(1)` on pct_change, not just pct_change itself
3. **VIX Falling Logic**: Must check `vix_today < vix_yesterday`, not just high VIX level
4. **Score Distribution**: Bull market scores ≠ bear market scores, must adapt threshold

---

## 📊 Expected Results

### If Implementation Correct:
- **2022-2024**: +80-153% return, ~52% win, ~20% max DD
- **2020-2024**: +149% return (20% CAGR), 52.8% win, 14.9% max DD
- **COVID crash**: Max DD ~15% (vs market -35%)

### If Results Differ:
- **<45% win rate**: Check score threshold adaptation, might be too strict
- **>60% win rate**: Possible lookahead bias or missing fees/slippage
- **Too few trades**: Check score threshold (might be too high) or VIX data (missing)
- **Too many trades**: Check SKIP tier (might not be skipping)

---

## 📁 Files to Create

### Source Code:
```
src/strategies/vix_adaptive/
├── __init__.py
├── vix_adaptive_strategy.py   # Main strategy class
├── tier_manager.py             # VIX tier detection
├── mean_reversion.py           # NORMAL tier strategy
├── bounce_strategy.py          # HIGH tier strategy
└── score_adapter.py            # Adaptive score threshold
```

### Data:
```
src/data/
└── vix_data_provider.py        # VIX data fetching
```

### Config:
```
config/
└── vix_adaptive.yaml           # Strategy configuration
```

### Tests:
```
tests/strategies/vix_adaptive/
├── test_tier_manager.py
├── test_bounce_strategy.py
├── test_mean_reversion.py
└── test_integration.py
```

---

## 📚 Reference Documents

- **Backtest Results**: `docs/VIX_ADAPTIVE_BACKTEST_RESULTS.md`
- **Full Spec**: `/tmp/VIX_ADAPTIVE_V3_FINAL.md`
- **MEMORY.md**: `.claude/projects/.../memory/MEMORY.md`
- **Original Scripts**: `/tmp/backtest_2020_2024.py`, `/tmp/backtest_buy_bounce.py`

---

## ⏭️ Next Immediate Step

**START HERE**:
1. Read `docs/VIX_ADAPTIVE_BACKTEST_RESULTS.md` (this doc's parent)
2. Create directory: `mkdir -p src/strategies/vix_adaptive`
3. Begin with VIXTierManager class (simplest component)
4. Follow checklist top to bottom

---

**Status**: Ready to implement
**Confidence**: High (backtest validated, stress tested, lessons learned documented)
**Timeline**: 2-3 days implementation + 30 days paper trading

---

End of Implementation Checklist
