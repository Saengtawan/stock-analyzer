# Debugging Summary: weights_applied Empty in Frontend

## Problem Statement
The "Recommendation Comparison" section in the web UI shows `Fundamentals 0% + Technical 0%` instead of actual weight percentages. Console logs show `weights: {}` even though the API returns correct data.

## What Was Fixed (Completed)

### 1. Time Horizon Parameter Bug ✅
**Issue:** Dynamic weighting always used 'short' weights regardless of time_horizon parameter
**Root Cause:**
- `enhanced_stock_analyzer.py` called `self._get_time_horizon()` which returned "1-5 days"
- `unified_recommendation.py` couldn't find 'time_horizon' in analysis_results, defaulted to 'short'

**Fix Applied:**
```python
# enhanced_stock_analyzer.py:80
self.current_time_horizon = time_horizon  # Store as instance variable

# enhanced_stock_analyzer.py:1258
'time_horizon': getattr(self, 'current_time_horizon', 'medium')  # Use stored value

# unified_recommendation.py:1069-1073
performance_expectations = analysis_results.get('performance_expectations', {})
time_horizon = performance_expectations.get('time_horizon', 'short')
```

**Test Results:**
```
✅ SHORT  (1-14 days):   Technical=40%, Momentum=30%
✅ MEDIUM (1-6 months):  Fundamental=30%, Technical=25%
✅ LONG   (6+ months):   Fundamental=55%, Insider=18%
🎉 BUG FIXED! Weights change correctly for different time horizons!
```

### 2. Hardcoded "Why the difference?" Text ✅
**Issue:** Recommendation comparison always showed hardcoded text with 0% weights
**Fix:** Replaced with dynamic JavaScript that extracts from `data.unified_recommendation.weights_applied`

**Changes Made:**
- `analyze.html` lines 2454-2533: Dynamic weight extraction and explanation generation
- Removed fallback values per user request: "เอา fallback ออกเดี่ยวสับสน"

## Current Problem (Unresolved)

### Frontend Receives Empty Weights Object ❌

**Symptoms:**
```javascript
// Console output:
timeHorizon: medium
weights: {}  // ← EMPTY!
fundamental weight: undefined
technical weight: undefined
```

**API Response (via curl):**
```json
{
  "unified_recommendation": {
    "weights_applied": {
      "fundamental": 0.3,
      "technical": 0.25,
      ...
    }
  }
}
```

**Hypothesis:** Data is lost between API response and frontend JavaScript

## Debugging Added

### Backend Logging (app.py:90-108)
```python
# Before cleaning
logger.info(f"🔍 API DEBUG - unified_recommendation exists: {bool(unified_rec)}")
logger.info(f"🔍 API DEBUG - weights_applied exists: {bool(weights)}")
logger.info(f"🔍 API DEBUG - weights_applied content: {weights}")

# After cleaning
logger.info(f"🔍 API DEBUG (after clean) - weights_applied: {cleaned_weights}")
```

### Frontend Logging (analyze.html:535-537, 2456-2466)
```javascript
// At API response
console.log('🔍 API Response received:');
console.log('  unified_recommendation exists:', !!data.unified_recommendation);
console.log('  weights_applied:', data.unified_recommendation?.weights_applied);

// At rendering
console.log('🔍 Recommendation Comparison Debug:');
console.log('  timeHorizon:', timeHorizon);
console.log('  weights:', weights);
console.log('  fundamental weight:', weights.fundamental);
console.log('  technical weight:', weights.technical);
```

## Next Steps for User

1. **Hard Refresh the Browser**
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`
   - This clears browser cache

2. **Analyze a Stock** (e.g., MARA with time_horizon=medium)

3. **Check Console Logs** (F12 → Console tab)
   Look for these two log sections:
   ```
   🔍 API Response received:
     unified_recommendation exists: true/false
     weights_applied: {...} or {}

   🔍 Recommendation Comparison Debug:
     timeHorizon: medium
     weights: {...} or {}
     fundamental weight: 0.3 or undefined
   ```

4. **Report Findings**
   - If `API Response received` shows weights but `Recommendation Comparison Debug` doesn't → Data transformation issue
   - If both show empty → API not returning data (check backend logs)
   - If both show data → Browser cache issue resolved

## Files Modified

1. `/src/analysis/enhanced_stock_analyzer.py` - Store time_horizon as instance variable
2. `/src/analysis/unified_recommendation.py` - Extract time_horizon from performance_expectations
3. `/src/web/app.py` - Added debug logging
4. `/src/web/templates/analyze.html` - Dynamic recommendation comparison + debug logging

## Test Scripts

- `test_time_horizon_fix.py` - Verifies time_horizon changes weights ✅ PASSING
- `test_api_weights.py` - Tests if API returns weights_applied (currently running)

## Important Notes

- Server must be restarted after app.py changes: `pkill -9 python && PYTHONDONTWRITEBYTECODE=1 python src/run_app.py --port 5002 &`
- Frontend changes (HTML/JS) don't require restart but need hard refresh
- All 3 time horizons (short/medium/long) are now properly supported
