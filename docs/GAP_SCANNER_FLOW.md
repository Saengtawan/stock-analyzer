# Pre-Market Gap Scanner - Complete Flow

## 📋 Timeline ทั้งหมด (จากเริ่มต้นจนจบ)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DAY 0 (Yesterday)                            │
└─────────────────────────────────────────────────────────────────┘

16:00 PM ET (Market Close)
  └─ NVDA closes at $100


┌─────────────────────────────────────────────────────────────────┐
│                    OVERNIGHT                                     │
└─────────────────────────────────────────────────────────────────┘

20:00 PM ET (After Hours)
  └─ NVDA announces earnings beat
  └─ After-hours trading: $100 → $112


┌─────────────────────────────────────────────────────────────────┐
│                    DAY 1 (Today)                                │
└─────────────────────────────────────────────────────────────────┘

06:00 AM ET - PRE-MARKET GAP SCAN STARTS
  │
  ├─ Scanner wakes up
  ├─ Scans 32 symbols watchlist
  ├─ Detects gaps 5%+ from prev close
  │
  ├─ NVDA detected:
  │   ├─ Prev close: $100
  │   ├─ Current price: $112 (pre-market)
  │   ├─ Gap: +12.0%
  │   ├─ Volume: 3.2x average ✅
  │   └─ Confidence: 80% (CATALYST)
  │
  ├─ Rotation Analysis:
  │   ├─ Estimated gain: 12% × 0.35 = 4.2%
  │   ├─ Rotation cost: 0.1%
  │   ├─ Opportunity cost: 2.0%
  │   └─ Net benefit: 4.2% - 0.1% - 2.0% = +2.1% ✅ WORTH IT
  │
  └─ Signal Generated:
      ├─ Symbol: NVDA
      ├─ Entry: $112 (market open)
      ├─ Stop Loss: $109.76 (-2%)
      ├─ Take Profit: $117.60 (+5%)
      ├─ Exit Strategy: Same day close
      └─ Marked as: gap_trade = True


09:30 AM ET - MARKET OPEN - ENTRY
  │
  ├─ Auto Trading Engine executes signal
  ├─ Places BUY order at market
  │
  ├─ ORDER FILLED:
  │   ├─ Symbol: NVDA
  │   ├─ Qty: 10 shares
  │   ├─ Entry Price: $112.50 (actual fill)
  │   ├─ Stop Loss: $110.25 (-2%)
  │   ├─ Take Profit: $118.13 (+5%)
  │   └─ Marked: gap_trade = True, gap_pct = +12%
  │
  └─ Log: "✅ Bought NVDA x10 @ $112.50"
  └─ Log: "📊 Gap Trade: +12.0% gap, 80% confidence (exit at EOD)"


09:31 AM - 15:50 PM - MONITORING
  │
  ├─ Every 1 minute: Check price
  ├─ Monitor Stop Loss: $110.25
  ├─ Monitor Take Profit: $118.13
  ├─ Monitor trailing stop (if activated)
  │
  ├─ 10:00 AM: NVDA = $115.00 (+2.2%) ✅ Holding
  ├─ 12:00 PM: NVDA = $116.50 (+3.6%) ✅ Holding
  ├─ 14:00 PM: NVDA = $117.80 (+4.7%) ✅ Holding
  └─ 15:30 PM: NVDA = $117.00 (+4.0%) ✅ Still holding


15:50 PM ET - PRE-CLOSE CHECK - EXIT
  │
  ├─ Auto Trading Engine: pre_close_check()
  ├─ Checks all positions
  │
  ├─ NVDA Position Found:
  │   ├─ gap_trade = True ✅
  │   ├─ days_held = 0 ✅
  │   └─ Action: CLOSE AT MARKET CLOSE
  │
  ├─ Log: "⚡ Closing GAP TRADE NVDA at market close"
  ├─ Log: "   (gap: +12.0%, held: intraday)"
  │
  └─ Places SELL order (market on close)


16:00 PM ET - MARKET CLOSE - FINAL EXIT
  │
  ├─ Market closes
  ├─ NVDA closes at $116.80
  │
  ├─ ORDER FILLED:
  │   ├─ Symbol: NVDA
  │   ├─ Qty: 10 shares
  │   ├─ Exit Price: $116.80
  │   ├─ Entry: $112.50
  │   └─ P&L: ($116.80 - $112.50) × 10 = +$43.00
  │
  ├─ Return: +3.8% (actual)
  ├─ Duration: Same day (intraday)
  │
  └─ Log: "✅ Sold NVDA x10 @ $116.80 (+3.8%)"
  └─ Reason: "GAP_TRADE_EOD"


16:01 PM ET - DAILY SUMMARY
  │
  ├─ Gap Trades Today: 1
  ├─ Win: 1, Loss: 0
  ├─ Realized P&L: +$43.00 (+3.8%)
  └─ Gap Scanner Status: ✅ Working as expected
```

---

## 🎯 สรุป Exit Strategy

### **ซื้อตอนไหน:**
- **9:30 AM** (Market Open)
- ราคา: Current price ตอน pre-market
- Entry type: Market order

### **ขายตอนไหน:**
- **3:50 PM - 4:00 PM** (Pre-Close → Market Close)
- ราคา: Market close price
- Exit type: Market on close order
- Duration: **Same day (intraday)**

### **Exit Conditions:**
1. **Primary**: Same day close (3:50 PM pre-close check)
   - Condition: `gap_trade = True` AND `days_held = 0`
   - Reason: Gap strategy is intraday (not overnight hold)

2. **Secondary** (Early exits):
   - Hit Take Profit (+5%) → Sell immediately
   - Hit Stop Loss (-2%) → Sell immediately
   - Trailing stop triggered → Sell immediately

3. **Emergency**:
   - Market regime turns BEAR → Close all
   - Safety circuit breaker → Close all

---

## 📊 Expected Outcomes

### **Normal Case** (70% of time):
```
Entry: $112.50 (9:30 AM)
Exit:  $116.80 (4:00 PM close)
Return: +3.8% intraday
Result: ✅ WIN
```

### **Hit Take Profit** (20% of time):
```
Entry: $112.50 (9:30 AM)
Exit:  $118.13 (whenever TP hit, e.g., 2:00 PM)
Return: +5.0%
Result: ✅ WIN (early exit)
```

### **Hit Stop Loss** (10% of time):
```
Entry: $112.50 (9:30 AM)
Exit:  $110.25 (whenever SL hit, e.g., 10:30 AM)
Return: -2.0%
Result: ❌ LOSS (protected)
```

---

## ⚙️ Configuration

### **Key Settings:**

```python
# Scanner
MIN_GAP_PCT = 5.0          # Minimum gap to consider
MIN_CONFIDENCE = 80        # Only 80-90% confidence signals
MIN_VOLUME_RATIO = 1.5     # Volume vs 20-day average

# Entry
ENTRY_TIME = "09:30 AM"    # Market open

# Exit
EXIT_STRATEGY = "SAME_DAY_CLOSE"
EXIT_TIME = "15:50 PM"     # Pre-close check
EXIT_TYPE = "MARKET_ON_CLOSE"

# Risk Management
STOP_LOSS_PCT = 2.0        # -2% SL
TAKE_PROFIT_PCT = 5.0      # +5% TP (estimated)
MAX_GAPS_PER_DAY = 2       # Max 2 gap trades/day
```

---

## 🔧 Implementation Status

### ✅ Completed:

1. **Scanner Module** (`src/screeners/premarket_gap_scanner.py`)
   - Gap detection ✅
   - Confidence scoring ✅
   - Rotation analysis ✅

2. **Engine Integration** (`src/auto_trading_engine.py`)
   - Scanner init (line 477-495) ✅
   - Scan function (line 5178-5303) ✅
   - Schedule in loop (line 5370) ✅

3. **Entry Logic**
   - Signal generation ✅
   - Metadata tagging (gap_trade = True) ✅
   - Position creation (line 3569-3600) ✅

4. **Exit Logic**
   - Pre-close check (line 4737-4752) ✅
   - Gap trade detection ✅
   - Same day close ✅

5. **Testing**
   - Unit tests ✅
   - Integration tests ✅
   - Documentation ✅

---

## 🚀 How to Use

### **Start Engine:**
```bash
python src/run_app.py
```

### **Monitor Logs:**
```bash
tail -f logs/auto_trading_engine.log | grep -E "PreMarket|Gap Trade|GAP_TRADE_EOD"
```

### **Check Positions:**
```bash
cat rapid_portfolio.json | jq '.positions[] | select(.gap_trade == true)'
```

### **Expected Log Output:**

```
06:15 AM: PreMarketGapScanner: Scanning 32 symbols...
06:15 AM: ✅ Found 1 gap signals
06:15 AM:   NVDA: Gap +12.0% (conf 80%) - WORTH ROTATING (benefit: +2.1%)

09:30 AM: 🔍 Pre-Market Gap Scan starting (0/5 positions)
09:30 AM: Pre-Market Gap: Processed 1 signals
09:31 AM: ✅ Bought NVDA x10 @ $112.50
09:31 AM:   📊 Gap Trade: +12.0% gap, 80% confidence (exit at EOD)

15:50 PM: Pre-close check...
15:50 PM: ⚡ Closing GAP TRADE NVDA at market close (gap: +12.0%, held: intraday)
16:00 PM: ✅ Sold NVDA x10 @ $116.80 (+3.8%)
```

---

## 📈 Performance Tracking

**Daily KPIs:**
- Gaps detected: Target 1-2/month
- Gaps traded: Only worth_rotating = True
- Win rate: Target >= 60%
- Avg return: Target >= 3%
- Exit timing: All at market close

**Weekly Review:**
- Total gaps: X
- Traded: Y (only if net benefit > 0)
- Wins: Z
- Avg return: A%
- Issues: None / [describe]

---

## ⚠️ Important Notes

### **DO:**
- ✅ Only trade gaps with 80-90% confidence
- ✅ Check rotation worthiness before entry
- ✅ Exit ALL gap trades at market close same day
- ✅ Max 2 gap trades per day

### **DON'T:**
- ❌ Hold gap trades overnight
- ❌ Trade gaps < 80% confidence
- ❌ Force trades if no gaps found
- ❌ Skip rotation analysis

### **Remember:**
- Gap strategy = **INTRADAY ONLY**
- Exit time = **4:00 PM close (same day)**
- No overnight holds for gap trades
- Focus on quality over quantity

---

**Version:** v6.11
**Status:** ✅ Production Ready
**Last Updated:** 2026-02-15
