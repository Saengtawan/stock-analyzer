# Pandas Series Comparison Fixes

## Problem
Both backtest scripts (`backtest_evening_risk_analysis.py` and `backtest_weekend_review.py`) had pandas Series comparison errors. The issue was that yfinance returns DataFrames with MultiIndex columns, and when accessing values using `.iloc[]` or `.loc[]`, the result could be a Series instead of a scalar value.

## Root Cause
- **yfinance behavior**: Even when downloading a single symbol, yfinance returns DataFrames with MultiIndex columns like `('Close', 'AAPL')` instead of simple column names like `'Close'`.
- **Series comparisons**: When code tried to compare values directly (e.g., `if distance_pct < 2.0`), Python raised errors because it was comparing a Series object instead of a scalar.

## Fixes Applied

### 1. Flatten MultiIndex Columns on Download
Added column flattening in `get_price_data()` method for both scripts:

```python
if isinstance(data.columns, pd.MultiIndex):
    data.columns = data.columns.get_level_values(0)
```

This ensures that when data is downloaded, column names are simple strings like `'Close'` instead of tuples like `('Close', 'AAPL')`.

### 2. Extract Scalar Values Before Comparisons
Added scalar extraction logic wherever values are used in comparisons or calculations:

```python
if isinstance(value, pd.Series):
    value = value.iloc[0]
```

Applied to all locations where values are extracted from DataFrames, including:
- Close prices
- Open prices
- Volume values
- Calculated metrics (distance_pct, momentum, etc.)

## Files Fixed

### `/home/saengtawan/work/project/cc/stock-analyzer/backtests/backtest_evening_risk_analysis.py`

**Locations fixed:**
- Line 44-58: `get_price_data()` - Added MultiIndex flattening
- Line 235-239: Close price extraction in `simulate_position()`
- Line 152-167: Next day gap calculation in `calculate_evening_risk_score()`
- Line 180-187: Volume spike calculation
- Line 192-201: SPY sentiment calculation
- Line 248-255: Next day open price extraction

### `/home/saengtawan/work/project/cc/stock-analyzer/backtests/backtest_weekend_review.py`

**Locations fixed:**
- Line 44-58: `get_price_data()` - Added MultiIndex flattening
- Line 137-152: Momentum calculation in `calculate_stock_score()`
- Line 157-166: Volume trend calculation
- Line 180-189: Relative to entry calculation
- Line 192-202: Volatility (ATR) calculation
- Line 268-283: Monday open and Friday close extraction
- Line 335-347: Decision logic with proper scalar comparisons

## Testing

Both scripts now run successfully:

```bash
# Test evening risk analysis
python3 backtests/backtest_evening_risk_analysis.py

# Test weekend review
python3 backtests/backtest_weekend_review.py
```

Output files are generated correctly:
- `backtests/evening_risk_results.csv`
- `backtests/evening_risk_metrics.json`
- `backtests/weekend_review_results.csv`
- `backtests/weekend_review_metrics.json`

## Verification

The fixes handle both scenarios:
1. **MultiIndex columns**: Flattened during data download
2. **Series values**: Converted to scalars before use

This ensures robust handling of yfinance data regardless of version or download parameters.

## Best Practices for Future Code

When working with yfinance data:

1. **Always flatten MultiIndex columns** after download:
   ```python
   if isinstance(data.columns, pd.MultiIndex):
       data.columns = data.columns.get_level_values(0)
   ```

2. **Always extract scalars** before comparisons:
   ```python
   value = df['Close'].iloc[0]
   if isinstance(value, pd.Series):
       value = value.iloc[0]
   ```

3. **Test with actual data** - yfinance behavior can vary, so always test with real downloads, not just synthetic data.

## Status
✅ All pandas Series comparison errors fixed
✅ Both backtest scripts running successfully
✅ Output files generated correctly
