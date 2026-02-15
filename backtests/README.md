# Backtest Scripts (v6.26)

## Overview

Backtest scripts to validate new features before production implementation:

1. **Evening Risk Analysis** - Pre-SL exit based on after-hours risk scoring
2. **Weekend Position Review** - Smart rotation based on weekend rescans

## Quick Start

### Run All Backtests (Recommended)

```bash
cd /home/saengtawan/work/project/cc/stock-analyzer
python backtests/run_all_backtests.py
```

This will:
- Run both backtests sequentially
- Generate individual reports
- Create summary comparison report
- Provide implementation recommendation

**Expected Runtime:** 5-10 minutes

### Run Individual Backtests

```bash
# Evening Risk Analysis only
python backtests/backtest_evening_risk_analysis.py

# Weekend Position Review only
python backtests/backtest_weekend_review.py
```

## Output Files

After running backtests, you'll get:

```
backtests/
├── cache/                              # Price data cache (auto-created)
├── evening_risk_results.csv            # Detailed results (Evening Risk)
├── evening_risk_metrics.json           # Summary metrics (Evening Risk)
├── weekend_review_results.csv          # Detailed results (Weekend Review)
├── weekend_review_metrics.json         # Summary metrics (Weekend Review)
├── combined_metrics.json               # Both features combined
└── summary_report.txt                  # Human-readable summary
```

## Decision Criteria

### Evening Risk Analysis

✅ **IMPLEMENT** if:
- Avg improvement > +0.3%
- False exit rate < 30%
- Max loss reduction >= -1.0%

### Weekend Position Review

✅ **IMPLEMENT** if:
- Avg P&L improvement > +0.5%
- Early exit benefit > +1.0%
- False rotation rate < 25%

## Example Output

```
================================================================================
BACKTEST SUMMARY REPORT
================================================================================

📊 Feature 1: Evening Risk Analysis (Pre-SL Exit)
--------------------------------------------------------------------------------
  Total instances analyzed: 147
  Actions taken: 42
  Avg improvement: +0.6%
  False exit rate: 24.0%
  Max loss reduction: +1.8%
  Dollar impact: +$840.00
  Criteria met: 3/3
  Recommendation: IMPLEMENT

📊 Feature 2: Weekend Position Review
--------------------------------------------------------------------------------
  Total reviews analyzed: 89
  Actions taken: 31
  Avg improvement: +0.7%
  False rotation rate: 19.4%
  Early exit benefit: +1.2%
  Avg days saved: 3.2
  Dollar impact: +$721.00
  Criteria met: 3/3
  Recommendation: IMPLEMENT

================================================================================
FINAL RECOMMENDATIONS
================================================================================
🎯 IMPLEMENT BOTH FEATURES
   Both features showed significant improvement

   Next Steps:
   1. Implement Evening Risk Analysis cron (6 PM daily)
   2. Implement Weekend Review cron (Sunday 8 PM)
   3. Integrate with Auto Trading Engine
   4. Paper trade for 2 weeks
   5. Go live with 50% capital
================================================================================
```

## Configuration

### Evening Risk Analysis

Default parameters in `backtest_evening_risk_analysis.py`:
- `risk_threshold = 3` (score >= 3 triggers pre-SL exit)
- Analyzes positions within 2% of SL
- Uses 5 signals: distance, gap, trend, volume, SPY

### Weekend Position Review

Default parameters in `backtest_weekend_review.py`:
- `score_threshold = 85` (score < 85 triggers rotation)
- `min_trading_days = 5` (minimum days before review)
- Reviews every Saturday/Sunday
- Compares vs time stop (10 days)

## Troubleshooting

### No Trade History

If you see "Database not found", scripts will use synthetic test data:
```python
test_positions = [
    {'symbol': 'NVDA', 'entry_date': '2024-01-15', ...},
    {'symbol': 'AMD', 'entry_date': '2024-02-01', ...},
    ...
]
```

To use real data:
- Ensure `data/trade_history.db` exists
- Check BUY/SELL trades are recorded
- Verify date range has data

### Slow Execution

Price data is cached in `backtests/cache/` to speed up reruns.

To clear cache:
```bash
rm -rf backtests/cache/*
```

### Dependencies

Required packages:
```bash
pip install pandas yfinance numpy
```

## Next Steps After Backtesting

### If IMPLEMENT Recommended

1. **Review Results**
   - Check `summary_report.txt`
   - Examine detailed CSV files
   - Understand which scenarios improved

2. **Implement Features**
   - Create production scripts (based on backtest logic)
   - Set up cron jobs
   - Integrate with Auto Trading Engine

3. **Paper Trade**
   - Run for 2 weeks minimum
   - Monitor false exits/rotations
   - Verify criteria still met

4. **Go Live**
   - Start with 50% capital
   - Scale up if successful
   - Monitor weekly

### If SKIP Recommended

1. **Analyze Why**
   - Check false exit/rotation rates
   - Review improvement distribution
   - Look for parameter sensitivity

2. **Adjust & Retest**
   - Tune risk threshold
   - Adjust score threshold
   - Try different date ranges

3. **Consider Alternatives**
   - Different signals
   - Different timing
   - Hybrid approaches

## Support

For questions or issues:
1. Check this README
2. Review backtest code comments
3. Examine output files
4. Adjust parameters and rerun
