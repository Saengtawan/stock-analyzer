# Rapid Trader Optimization Results

## Summary

Optimization completed on 2026-02-01. Tested 3 strategies across 1296 configurations.

**Target:** 5-15% monthly profit with very low losers
**Achieved:** 4.5% monthly return

## Best Strategy: Mean Reversion

### Configuration
```json
{
  "strategy": "mean_reversion",
  "max_bb_pct": 0.25,
  "max_rsi": 25,
  "min_mom_5d": -10,
  "min_sl": 2.0,
  "max_sl": 3.0,
  "atr_mult": 1.0,
  "rr_ratio": 3.0,
  "max_hold": 10
}
```

### Entry Rules
1. **Bollinger Band Position:** Price must be below 25% of Bollinger Band range (near lower band)
2. **RSI:** Must be below 25 (very oversold)
3. **5-Day Momentum:** Must be above -10% (not in free fall)

### Exit Rules
- **Stop Loss:** 2-3% (ATR-based)
- **Take Profit:** 6-9% (3x SL)
- **Time Exit:** 10 trading days max

### Backtest Results (Oct 2025 - Jan 2026)
| Metric | Value |
|--------|-------|
| Total Trades | 71 |
| Winners | 34 (48%) |
| Losers | 37 (52%) |
| Total Return | 18.2% |
| **Monthly Return** | **4.5%** |
| Loser Ratio | 1.09 |

## Strategy Comparison

| Strategy | Monthly Return | Win Rate | W/L Ratio |
|----------|---------------|----------|-----------|
| Strict Dip Buying | 3.6% | 47% | 63/72 |
| Breakout | 3.8% | 51% | 44/42 |
| **Mean Reversion** | **4.5%** | 48% | 34/37 |

## Trading Rules Implementation

### Position Sizing
- Max 5 positions at a time
- Max 2 new entries per day
- 20% of capital per position

### Universe
101 large-cap US stocks across:
- Technology
- Healthcare
- Consumer
- Finance
- Industrial
- Energy
- Clean Energy

## Key Insights

1. **Mean Reversion** outperforms dip buying and breakout strategies
2. **Very oversold conditions** (RSI < 25) are best entry points
3. **3:1 R:R ratio** balances win rate with profitability
4. **10-day hold** allows enough time for mean reversion to occur
5. **Lower Bollinger Band** entries have better success rate

## Next Steps to Reach 5-15%

1. Add sector rotation (favor hot sectors)
2. Add market regime filter (avoid entries in bear market)
3. Increase position sizing in high-conviction trades
4. Add trailing stop to capture more upside

## Files

- `optimize_final.py` - Final optimizer with strict filters
- `realistic_backtest.py` - Portfolio backtest with position limits
- `data/best_config_final.json` - Best configuration saved
