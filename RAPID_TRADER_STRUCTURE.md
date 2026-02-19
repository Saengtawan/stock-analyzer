# RAPID TRADER - COMPLETE STRUCTURE ANALYSIS

## 📊 OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER BAR (2 rows)                                        │
│  - Mode, Version, Market Status, SPY, VIX, RSI, Countdown   │
│  - PDT, Positions, Trail, Today W/L, P&L, Queue, Crons      │
├─────────────────────────────────────────────────────────────┤
│  SECTOR STRIP (scrolling sector badges)                     │
├─────────────────────────────────────────────────────────────┤
│  TIMELINE (5 sessions: Gap→Morning→Midday→Afternoon→Close)  │
├────────────────┬──────────────────┬─────────────────────────┤
│   LEFT (40%)   │   CENTER (33%)   │   RIGHT (27%)           │
│  Buy Signals   │   Portfolio      │   Operations            │
│                │   Alerts         │   Filters & Rules       │
│                │   Account        │   Bear/Bull Config      │
│                │   Queue          │   Risk Settings         │
│                │   Stats          │                         │
└────────────────┴──────────────────┴─────────────────────────┘
```

---

## 🔍 PHASE 1: HEADER & TOP BARS

### 1.1 Header Bar (Row 1)
**Location:** Lines 473-500
**Components:**
- `headerModeBadge` - BEAR+LOW_RISK / BULL
- `hdrVersion` - v6.11 (from backend)
- `hdrMarketStatus` - CLOSED / OPEN / HOLIDAY
- `hdrNextOpen` - Opens Tue 09:30
- `hdrSpyPrice` - SPY $681.61
- `hdrSpyPct` - ▼ 1.09%
- `hdrSpyVIX` - VIX 20.6
- `hdrVixIcon` - ✅ / ⚠️
- `hdrSpyRSI` - RSI 40.4
- `hdrCountdown` - Timer to open/close

**Data Sources:**
- WebSocket: `regime_update`, `status_update`
- API: `/api/rapid/spy-regime`, `/api/auto/status`

**Issues to Check:**
- [ ] Version shows correct (v6.11)
- [ ] Market status updates real-time
- [ ] SPY/VIX/RSI refresh every 10s
- [ ] Countdown timer accurate

---

### 1.2 Header Bar (Row 2)
**Location:** Lines 504-540
**Components:**
- `hdrPDT` - PDT 0/3
- `hdrPositions` - Pos 2/2
- `hdrTrailCount` - Trail 0/2
- `hdrTodayWL` - Today 0W 0L
- `hdrPnL` - P&L $-8.05
- `hdrQueueCount` - Queue 0
- Cron status indicators (5 icons)
- Mode buttons (Manual/Auto)
- Control buttons (Emergency Stop, Close All)
- Health indicators (WebSocket, Health Dot)

**Data Sources:**
- WebSocket: `status_update`
- API: `/api/auto/status`, `/api/cron/status`

**Issues to Check:**
- [ ] PDT counter accurate
- [ ] Position count matches portfolio
- [ ] P&L updates real-time
- [ ] Cron icons show correct status
- [ ] Health dot shows correct color

---

### 1.3 Sector Strip
**Location:** Lines 547-550
**Component:** `sectorStrip`
**Function:** Scrolling badges showing sector performance

**Data Sources:**
- WebSocket: `regime_update`
- API: `/api/rapid/sector-regimes`

**Format:**
```
Energy ▲1.0% | Material ▲1.2% | Utility ▲2.7% | Tech ▼0.5%
```

**Issues to Check:**
- [ ] Sectors update every 5min
- [ ] Colors correct (green=up, red=down)
- [ ] Shows all 11 sectors
- [ ] Scrolling works on mobile

---

### 1.4 Timeline Bar
**Location:** Lines 552-562
**Component:** `timelineBar`, `timelineContainer`
**Sessions:** 5 total (NEW: Gap Scan added v6.11)

```javascript
DEFAULT_SESSIONS = [
  { name: 'gapscan',   start: 360, end: 575, interval: -1 },  // 06:00-09:35
  { name: 'morning',   start: 575, end: 660, interval: 3 },   // 09:35-11:00
  { name: 'midday',    start: 660, end: 840, interval: 5 },   // 11:00-14:00
  { name: 'afternoon', start: 840, end: 930, interval: 5 },   // 14:00-15:30
  { name: 'preclose',  start: 930, end: 960, interval: 0 },   // 15:30-16:00
]
```

**Data Sources:**
- Rendered on page load from backend config
- Updates from `scanner_schedule` in API

**Issues to Check:**
- [x] Shows 5 sessions (was 4, now 5 with Gap Scan)
- [ ] Gap Scan shows purple color
- [ ] Morning shows orange (volatile)
- [ ] Progress bars animate
- [ ] Active session has glow effect
- [ ] Completed sessions show green ✅

---

## 🔍 PHASE 2: LEFT COLUMN (Buy Signals)

### 2.1 Buy Signals Card
**Location:** Lines 570-590
**Component:** `signalsContainer`
**Header:** "Buy Signals" + badge count

**Data Sources:**
- WebSocket: `signals_update`
- API: `/api/rapid/signals`

**Display:**
- Signal count badge (top right)
- Pre-filter status (pool size)
- Cache age indicator
- Signal cards (scrollable, max 75vh)

**Signal Card Format:**
```
🌕 SYMBOL  Score 92
E: $45.23  N: $46.10  +1.9% ($+3.50)
SL $43.50  4.2% away | TP $47.80  3.7% away
Dip -5.2% (5d) → Bounce +2.1% (today)
[Add] [Skip] [Analyze]
```

**Issues to Check:**
- [ ] Signals sorted by score (highest first)
- [ ] Entry/Now/SL/TP prices correct
- [ ] Dip & bounce percentages accurate
- [ ] Buttons work (Add, Skip, Analyze)
- [ ] Gap trades tagged with metadata
- [ ] Cache age shows time since last scan

---

## 🔍 PHASE 3: CENTER COLUMN (Portfolio)

### 3.1 Portfolio Alerts
**Location:** Lines 595-607
**Component:** `alertsContainer`
**Header:** "Portfolio Alerts" + badge count

**Data Sources:**
- WebSocket: `positions_update`
- Real-time: Price updates via WebSocket

**Alert Types:**
- SL approaching (< 0.5% away)
- TP approaching (< 1% away)
- Time exit warning (Day 9/10)
- Trailing stop activated
- Position down > 2%

**Issues to Check:**
- [ ] Alerts update real-time
- [ ] Colors correct (red=danger, yellow=warning)
- [ ] Alert count badge accurate
- [ ] Dismissible alerts work

---

### 3.2 Account Summary
**Location:** Lines 609-622
**Component:** `alpacaAccountBox`
**Display:** Portfolio, Safety, Cash, Invested, Unrealized P&L

**Data Sources:**
- API: `/api/auto/status` (account info)

**Format:**
```
Portfolio: $99,870  Safety: OK
Cash: $99,219 | Invested: $651 | Unreal: -$8.05
```

**Issues to Check:**
- [ ] Portfolio value accurate
- [ ] Safety status correct
- [ ] Cash + Invested = Portfolio
- [ ] Unrealized P&L matches positions

---

### 3.3 Signal Queue
**Location:** Lines 624-633
**Component:** `signalQueueBox`, `queueContainer`
**Display:** Signals waiting to be executed

**Data Sources:**
- API: `/api/auto/status` (queue array)

**Queue Item Format:**
```
SYMBOL - Score 92 - Waiting for entry...
E: $45.23 | SL $43.50 | TP $47.80
[Execute Now] [Remove]
```

**Issues to Check:**
- [ ] Queue count badge matches items
- [ ] Shows reason for delay
- [ ] Execute Now button works
- [ ] Auto-executes when conditions met

---

### 3.4 Today's Stats
**Location:** Lines 636-660
**Component:** Stats card
**Metrics:**
- Executed trades
- Skipped signals
- Day P&L
- Gap rejected
- Earnings rejected
- Stock-D rejected
- Low risk trades

**Data Sources:**
- API: `/api/auto/status` (daily_stats)

**Issues to Check:**
- [ ] Stats update after each trade
- [ ] Rejection counts accurate
- [ ] Day P&L matches header
- [ ] Low risk trades counted separately

---

## 🔍 PHASE 4: RIGHT COLUMN (Operations)

### 4.1 Filters & Protection
**Location:** Lines 663-695
**Component:** Filter rules card
**Rules:**
- SPY Regime (4-criteria)
- Score threshold (≥90)
- Gap filter (+1% / -3%)
- Earnings (5d before)
- Late Start (>20min)
- Stock-D (ON/OFF)

**Data Sources:**
- API: `/api/engine/config`

**Issues to Check:**
- [ ] Filters show current config
- [ ] Icons correct (✅/❌)
- [ ] Score threshold dynamic
- [ ] Stock-D status updates

---

### 4.2 BEAR Mode Config
**Location:** Lines 697-722
**Component:** `bearModeBox`
**Settings:**
- Allow: score > -2 (BULL/SIDEWAYS)
- Score: 90 | Gap: +1%/-3%
- Position: 40%, Max 2
- DD Control: EXEMPT
- Allowed sectors list

**Data Sources:**
- API: `/api/auto/status` (bear_allowed_sectors)

**Issues to Check:**
- [ ] Shows only in BEAR mode
- [ ] Allowed sectors list correct
- [ ] Position size shows 40%
- [ ] Max positions = 2

---

### 4.3 BULL Filter
**Location:** Lines 725-736
**Component:** `bullSectorBox`
**Function:** Block sectors with ret_20d < -5%

**Issues to Check:**
- [ ] Shows only in BULL mode
- [ ] Blocked sectors list correct
- [ ] Shows "none" if no blocks

---

### 4.4 Low Risk Mode
**Location:** Lines 739-756
**Component:** `lowRiskModeBox`
**Settings:**
- Gap: 1% (tighter than normal)
- Score: 90
- Position: 40%
- ATR: ≤4% (volatility filter)

**Issues to Check:**
- [ ] Shows when LOW_RISK active
- [ ] Settings different from normal
- [ ] ATR filter applied

---

### 4.5 Rules (SL/TP/Trail/Hold)
**Location:** Lines 759-780
**Settings:**
- SL: 1.5xATR [2.5-3.5%]
- TP: 3xATR [4.5-8%]
- Trail: +2.5% lock 80%
- Hold: 10d Max 2

**Issues to Check:**
- [ ] SL range accurate
- [ ] TP calculation correct
- [ ] Trail activation level shown
- [ ] Max hold days = 10

---

### 4.6 Features
**Location:** Lines 782-806
**Features:**
- Conversion: 45/40/30%
- Day Trade: +3%/+4%
- Overnight: buy 15:30
- Breakout: 1.5x vol

**Issues to Check:**
- [ ] Feature toggles work
- [ ] Conversion levels correct
- [ ] DT/Overnight enabled
- [ ] Breakout multiplier shown

---

### 4.7 PDT Guard
**Location:** Lines 809-825
**Rules:**
- D0 + Budget: Sell
- D0 + No Budget: HOLD
- D1+: Sell OK

**Issues to Check:**
- [ ] Shows PDT rules
- [ ] Current day trade count
- [ ] Budget status shown

---

### 4.8 Risk Settings
**Location:** Lines 828-842
**Limits:**
- Per trade: 2.5%
- Daily: 5%
- Weekly: 7%

**Issues to Check:**
- [ ] Risk percentages correct
- [ ] Matches config
- [ ] Updates if changed

---

## 📋 PHASE BREAKDOWN FOR DETAILED CHECK

### **PHASE 1: Top Bars (Header, Sectors, Timeline)**
Focus: Layout, data updates, visual indicators
- Lines 473-562

### **PHASE 2: Left Column (Signals)**
Focus: Signal display, scoring, filtering
- Lines 570-590

### **PHASE 3: Center Column (Portfolio & Stats)**
Focus: Position management, alerts, queue
- Lines 592-660

### **PHASE 4: Right Column (Config & Rules)**
Focus: Trading rules, risk settings, mode configs
- Lines 663-850

---

## ✅ VERIFICATION CHECKLIST

### Data Flow
- [ ] WebSocket connected and updating
- [ ] API endpoints responding
- [ ] Real-time prices updating
- [ ] Cache indicators showing age

### Visual
- [ ] 5 sessions in timeline (Gap Scan added)
- [ ] Gap Scan purple, Morning orange
- [ ] Progress bars animating
- [ ] Sector colors correct

### Functional
- [ ] Add signal button works
- [ ] Skip signal removes from list
- [ ] Position alerts trigger correctly
- [ ] Emergency stop functional

### Configuration
- [ ] Version v6.11 displayed
- [ ] Single source of truth (config → backend → frontend)
- [ ] All sections show current config
- [ ] Rules match trading.yaml

---

**Total Sections:** 21 major components
**Total Lines:** ~850 (HTML content section)
**Phases:** 4 main phases
**Priority:** PHASE 1 (Timeline) > PHASE 2 (Signals) > PHASE 3 (Portfolio) > PHASE 4 (Config)
