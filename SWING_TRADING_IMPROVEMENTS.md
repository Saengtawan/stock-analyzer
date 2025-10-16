# Swing Trading Screener Improvements

## Overview
Improvements for Support Level Screener to make it more actionable for short-term swing trading.

---

## 1. Detailed Momentum Score Breakdown

### Current Implementation
```python
# Line 164: support_level_screener.py
technical_score = tech_analysis.get('technical_score', {}).get('total_score', 0)
```
**Problem:** Single momentum value (e.g., 4.5/10) without component breakdown.

### Proposed Implementation

#### Backend Changes (`_analyze_stock_for_support` method)

```python
def _calculate_detailed_momentum(self, indicators: Dict) -> Dict[str, Any]:
    """Calculate detailed momentum breakdown"""

    # RSI Component
    rsi = indicators.get('rsi', 50)
    if rsi < 30:
        rsi_score, rsi_signal = 9.0, "Oversold (Strong Buy)"
    elif rsi < 40:
        rsi_score, rsi_signal = 7.0, "Bearish"
    elif rsi < 60:
        rsi_score, rsi_signal = 5.0, "Neutral"
    elif rsi < 70:
        rsi_score, rsi_signal = 7.0, "Bullish"
    else:
        rsi_score, rsi_signal = 3.0, "Overbought (Risk)"

    # MACD Component
    macd_line = indicators.get('macd_line', 0)
    macd_signal = indicators.get('macd_signal', 0)
    macd_hist = indicators.get('macd_histogram', 0)

    if macd_hist > 0 and macd_line > macd_signal:
        macd_score, macd_signal_text = 8.0, "Bullish crossover"
    elif macd_hist < 0 and macd_line < macd_signal:
        macd_score, macd_signal_text = 3.0, "Bearish crossover"
    elif macd_hist > 0:
        macd_score, macd_signal_text = 6.0, "Positive divergence"
    else:
        macd_score, macd_signal_text = 4.0, "Negative divergence"

    # EMA Crossover Component
    ema_20 = indicators.get('ema_20', 0)
    ema_50 = indicators.get('ema_50', 0)

    if ema_20 > ema_50:
        ema_score, ema_signal = 7.0, "20 above 50 (Bullish)"
    elif ema_20 < ema_50:
        ema_score, ema_signal = 3.0, "20 below 50 (Bearish)"
    else:
        ema_score, ema_signal = 5.0, "Neutral"

    # Volume Momentum (already have volume_analysis)
    # Price Momentum (7-day return)

    # Aggregate
    momentum_score = (rsi_score * 0.3 + macd_score * 0.3 +
                     ema_score * 0.2 + volume_score * 0.2)

    return {
        'momentum_score': momentum_score,
        'components': {
            'rsi': {'score': rsi_score, 'signal': rsi_signal, 'value': rsi},
            'macd': {'score': macd_score, 'signal': macd_signal_text, 'histogram': macd_hist},
            'ema': {'score': ema_score, 'signal': ema_signal},
            'volume': {'score': volume_score, 'trend': volume_trend},
            'price_momentum': {'score': price_momentum_score, '7d_return': return_7d}
        }
    }
```

#### Frontend Display (screen.html)
```html
<div class="momentum-breakdown">
    <h6>📈 Momentum: 6.2/10 ⚡</h6>
    <ul>
        <li>• RSI (14): 58 → Neutral (+0.1) <span class="badge bg-secondary">5.0</span></li>
        <li>• MACD: Bullish crossover (+1.2) <span class="badge bg-success">8.0</span></li>
        <li>• EMA: 20 above 50 (+0.8) <span class="badge bg-success">7.0</span></li>
        <li>• Volume: 1.37x avg (+0.5) <span class="badge bg-info">6.5</span></li>
    </ul>
    <small class="text-muted">Overall: Moderate momentum with strong MACD signal</small>
</div>
```

---

## 2. ATR-Based Entry Zones

### Current Implementation
```python
# Lines 149-151: support_level_screener.py
support_1 = support_resistance.get('support_1', current_price)
resistance_1 = support_resistance.get('resistance_1', current_price * 1.05)
# No ATR consideration
```

**Problem:** Entry zones too wide (e.g., $149-$152 = $3 gap)

### Proposed Implementation

```python
def _calculate_atr_zones(self, price_data: pd.DataFrame, current_price: float,
                        support: float, resistance: float) -> List[Dict]:
    """Calculate precise entry zones based on ATR"""

    # Calculate ATR(14)
    atr = self._calculate_atr(price_data, period=14)

    zones = []

    # Zone 1: Near Support (0.5 ATR width)
    zone1_center = support * 1.005  # 0.5% above support
    zones.append({
        'name': 'Near Support',
        'entry_low': zone1_center - (atr * 0.25),
        'entry_high': zone1_center + (atr * 0.25),
        'stop_loss': support - (atr * 0.5),
        'target': resistance,
        'type': 'bounce_play',
        'risk_reward': None,  # Calculate later
        'description': 'Support bounce play'
    })

    # Zone 2: Breakout Confirmation (1.0 ATR width)
    if resistance > current_price:
        zone2_center = (support + resistance) / 2
        zones.append({
            'name': 'Mid Range',
            'entry_low': zone2_center - (atr * 0.5),
            'entry_high': zone2_center + (atr * 0.5),
            'stop_loss': support - (atr * 0.5),
            'target': resistance * 1.05,
            'type': 'consolidation_break',
            'risk_reward': None,
            'description': 'Breakout after consolidation'
        })

    # Calculate R:R for each zone
    for zone in zones:
        risk = zone['entry_high'] - zone['stop_loss']
        reward = zone['target'] - zone['entry_low']
        zone['risk_reward'] = reward / risk if risk > 0 else 0
        zone['width'] = zone['entry_high'] - zone['entry_low']
        zone['width_atr'] = zone['width'] / atr

    # Filter zones with R:R >= 1.5
    zones = [z for z in zones if z['risk_reward'] >= 1.5]

    return zones

def _calculate_atr(self, price_data: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range"""
    high = price_data['High']
    low = price_data['Low']
    close = price_data['Close']

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]

    return float(atr)
```

#### Return Format
```python
{
    'entry_zones': [
        {
            'name': 'Near Support',
            'entry_low': 149.50,
            'entry_high': 150.20,
            'width': 0.70,  # $0.70 width
            'width_atr': 0.5,  # 0.5 × ATR
            'stop_loss': 148.80,
            'target': 154.00,
            'risk_reward': 3.0,
            'type': 'bounce_play',
            'description': 'Support bounce play'
        }
    ],
    'atr': 1.40
}
```

---

## 3. Momentum Threshold Filter

### Current Implementation
```python
# Lines 107-110: support_level_screener.py
technical_score = opp.get('technical_score', 0)
if technical_score < min_technical_score:
    continue
# Uses min_technical_score=4.0 by default
```

**Problem:** Watchlist includes weak momentum stocks (3.5, 4.0) unsuitable for swing trading.

### Proposed Implementation

#### Add Momentum-Specific Filter
```python
def screen_support_opportunities(self,
                               max_distance_from_support: float = 0.05,
                               min_fundamental_score: float = 5.0,
                               min_technical_score: float = 4.0,
                               min_momentum_score: float = 5.0,  # NEW PARAMETER
                               max_stocks: int = 10,
                               time_horizon: str = 'medium') -> List[Dict[str, Any]]:
    """
    Added min_momentum_score parameter for momentum-focused screening
    """
    # ... existing code ...

    for opp in opportunities:
        # ... existing filters ...

        # NEW: Check momentum score specifically
        momentum_score = opp.get('momentum_score', 0)
        if momentum_score < min_momentum_score:
            continue

        filtered_opportunities.append(opp)
```

#### Tiered Display
```python
def categorize_by_momentum(opportunities: List[Dict]) -> Dict[str, List]:
    """Categorize stocks by momentum strength"""

    categories = {
        'strong': [],    # >= 7.0
        'moderate': [],  # 5.0 - 6.9
        'weak': []       # < 5.0
    }

    for opp in opportunities:
        momentum = opp.get('momentum_score', 0)
        if momentum >= 7.0:
            categories['strong'].append(opp)
        elif momentum >= 5.0:
            categories['moderate'].append(opp)
        else:
            categories['weak'].append(opp)

    return categories
```

#### Frontend Display
```html
<div class="momentum-tiers">
    <div class="tier strong">
        <h6>🔥 Strong Momentum (7.0+)</h6>
        <p>17 stocks ready for swing trades</p>
    </div>
    <div class="tier moderate">
        <h6>⚡ Moderate Momentum (5.0-6.9)</h6>
        <p>32 stocks for patient entries</p>
    </div>
    <div class="tier weak collapsed">
        <h6>📊 Weak Momentum (<5.0)</h6>
        <p>Hidden by default - click to show</p>
    </div>
</div>
```

---

## 4. Relative Volume Analysis

### Current Implementation
```python
# Lines 208-223: support_level_screener.py
def _analyze_volume_at_support(self, results: Dict) -> Dict:
    # Simplified, returns static values
    return {
        'volume_trend': 'normal',
        'volume_score': 5.0,
        'volume_confirmation': True
    }
```

**Problem:** No actual volume analysis, just placeholder values.

### Proposed Implementation

```python
def _analyze_relative_volume(self, price_data: pd.DataFrame) -> Dict[str, Any]:
    """
    Comprehensive relative volume analysis
    """
    volume_col = self._get_column_name(price_data, ['Volume', 'volume'])

    if volume_col is None:
        return self._volume_placeholder()

    current_volume = price_data[volume_col].iloc[-1]
    avg_volume_20 = price_data[volume_col].rolling(20).mean().iloc[-1]
    avg_volume_50 = price_data[volume_col].rolling(50).mean().iloc[-1]

    # Relative Volume (current vs 20-day average)
    rel_volume = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1.0

    # Volume Trend (last 5 days)
    recent_volumes = price_data[volume_col].tail(5)
    volume_trend_pct = ((recent_volumes.iloc[-1] - recent_volumes.iloc[0]) /
                       recent_volumes.iloc[0] * 100)

    # Intraday Volume Pattern (if available)
    # Note: This requires intraday data, simplified here
    morning_volume = None  # Placeholder for intraday analysis
    afternoon_volume = None

    # Unusual Volume Alert
    unusual = rel_volume > 2.0

    # Volume-Price Correlation
    returns = price_data['Close'].pct_change()
    volume_changes = price_data[volume_col].pct_change()
    correlation = returns.tail(20).corr(volume_changes.tail(20))

    # Scoring
    volume_score = 5.0  # Base score

    if rel_volume > 1.5:
        volume_score += 2.0  # High interest
    elif rel_volume < 0.7:
        volume_score -= 1.5  # Low interest

    if correlation > 0.5:
        volume_score += 1.0  # Volume confirms price moves

    if unusual:
        volume_score += 1.0  # Institutional activity

    volume_score = max(0, min(10, volume_score))

    # Signal
    if rel_volume > 1.5:
        signal = "⚡ Above average interest"
    elif rel_volume < 0.7:
        signal = "📉 Below average interest"
    else:
        signal = "➡️ Normal interest"

    return {
        'current_volume': int(current_volume),
        'avg_volume_20': int(avg_volume_20),
        'relative_volume': round(rel_volume, 2),
        'volume_trend_pct': round(volume_trend_pct, 1),
        'unusual_volume': unusual,
        'volume_price_correlation': round(correlation, 2),
        'volume_score': round(volume_score, 1),
        'signal': signal,
        'interpretation': self._interpret_volume(rel_volume, correlation, unusual)
    }

def _interpret_volume(self, rel_volume: float, correlation: float, unusual: bool) -> str:
    """Generate volume interpretation"""

    if unusual and correlation > 0.5:
        return "Institutional accumulation detected - breakout likely"
    elif unusual and correlation < -0.3:
        return "Distribution pattern - exercise caution"
    elif rel_volume > 1.3:
        return "Higher than usual interest - monitor for momentum"
    elif rel_volume < 0.7:
        return "Low participation - wait for volume confirmation"
    else:
        return "Normal trading activity"
```

#### Return Format
```python
{
    'current_volume': 8500000,
    'avg_volume_20': 6200000,
    'relative_volume': 1.37,  # 1.37x average
    'volume_trend_pct': 12.5,  # +12.5% over last 5 days
    'unusual_volume': False,
    'volume_price_correlation': 0.68,
    'volume_score': 7.5,
    'signal': '⚡ Above average interest',
    'interpretation': 'Higher than usual interest - monitor for momentum'
}
```

#### Frontend Display
```html
<div class="volume-analysis">
    <h6>📊 Volume Analysis</h6>
    <div class="volume-header">
        <span class="volume-value">8.5M</span>
        <span class="volume-relative">1.37x avg ⚡</span>
    </div>

    <div class="volume-breakdown">
        <div class="row">
            <div class="col-6">
                <small>20-day avg:</small><br>
                <strong>6.2M</strong>
            </div>
            <div class="col-6">
                <small>Trend (5d):</small><br>
                <strong class="text-success">+12.5% ↗️</strong>
            </div>
        </div>
    </div>

    <div class="volume-profile mt-2">
        <small class="text-muted d-block">Intraday Pattern:</small>
        <div class="progress" style="height: 20px;">
            <div class="progress-bar bg-success" style="width: 40%;"
                 title="Morning: 1.8x avg">
                Morning 🔥
            </div>
            <div class="progress-bar bg-info" style="width: 60%;"
                 title="Afternoon: 1.1x avg">
                Afternoon
            </div>
        </div>
    </div>

    <small class="text-muted mt-2 d-block">
        <strong>Interpretation:</strong> Higher than usual interest - monitor for momentum
    </small>
</div>
```

---

## Implementation Priority

### Phase 1 (Critical - 2 hours):
1. **ATR-Based Entry Zones** - Most impactful for day/swing traders
2. **Relative Volume** - Essential confirmation signal

### Phase 2 (High Value - 2 hours):
3. **Momentum Breakdown** - Better understanding of signals
4. **Momentum Threshold** - Filter out weak candidates

### Phase 3 (Polish - 1 hour):
5. **Frontend UI improvements**
6. **Testing and refinement**

---

## Expected Results

### Before:
```
AMD - Entry: $149-$152 (gap: $3)
Momentum: 4.5/10
Volume: Normal
```

### After:
```
AMD - Advanced Micro Devices

📈 Momentum: 6.2/10 ⚡ (Moderate)
  • RSI (14): 58 → Neutral (5.0)
  • MACD: Bullish crossover (8.0) 🔥
  • EMA: 20 above 50 (7.0) ✓
  • Volume: 1.37x avg (6.5) ⚡

🎯 Entry Zones (ATR: $1.40)

Zone 1: $149.50 - $150.20 (0.5 ATR)
  Support bounce play
  Stop: $148.80 | Target: $154 (R:R 3.0:1) ✓

Zone 2: $156.80 - $157.60 (0.6 ATR)
  Breakout confirmation
  Stop: $155.40 | Target: $163 (R:R 2.5:1) ✓

📊 Volume: 8.5M (1.37x avg) ⚡
  Morning: 1.8x 🔥 | Afternoon: 1.1x
  Interpretation: Institutional interest detected
```

---

## Files to Modify

1. **`/src/screeners/support_level_screener.py`**
   - Add `_calculate_detailed_momentum()`
   - Add `_calculate_atr_zones()`
   - Add `_calculate_atr()`
   - Add `_analyze_relative_volume()`
   - Update `_analyze_stock_for_support()` to use new methods
   - Add `min_momentum_score` parameter

2. **`/src/web/templates/screen.html`**
   - Add momentum breakdown display
   - Add ATR zones display
   - Add volume analysis display
   - Add momentum tier categorization

3. **`/src/web/app.py`**
   - Update screener API endpoint to return new fields
   - Add momentum tier filtering

---

## Testing Plan

1. **Unit Tests:**
   - Test ATR calculation accuracy
   - Test relative volume calculations
   - Test momentum component scoring

2. **Integration Tests:**
   - Test full screening with new features
   - Verify R:R calculations in zones
   - Verify momentum filtering works

3. **Manual Testing:**
   - Screen 10 stocks and verify zones are narrow
   - Check momentum breakdown makes sense
   - Verify volume analysis matches market data

---

## Notes

- ATR zones will adapt to stock volatility automatically
- Momentum threshold can be adjusted per user preference
- Relative volume calculation requires sufficient historical data
- Consider adding user preferences for threshold customization
