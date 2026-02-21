# Stock Analyzer - System Status (2026-02-21)

## 🎯 Current Version: v6.36

### System Overview
Production-ready automated trading system with database-backed architecture,
multi-strategy support, and comprehensive risk management.

---

## ✅ Production Status

### Active Components
- ✅ Auto Trading Engine (v6.36)
- ✅ Web Dashboard (real-time monitoring)
- ✅ Database Storage (single source of truth)
- ✅ VIX Adaptive Strategy (v3.0)
- ✅ Multi-Strategy Support (DIP, OVN, PEM)

### System Health
- **Uptime:** Running since 2026-02-21 12:52 EST
- **Engine PID:** 2665799
- **Web App PID:** 2633866
- **Market Status:** Closed (overnight)
- **Database:** SQLite (trade_history.db)

---

## 🚀 Recent Major Updates

### v6.36: Skip Window + Strategy Tags (2026-02-21)
**Features:**
- Skip window 10:00-11:00 AM ET (no trading during volatile period)
- Strategy tags [DIP], [OVN], [PEM] on positions and alerts
- Enhanced timeline with 8 sessions (Gap, Morning, PEM, SKIP, Midday, Afternoon, OVN, Pre-Close)
- Position limits: 4 total (2 DIP + 1 OVN + 1 PEM)

**Benefits:**
- Avoids volatile mid-morning period → improved win rate
- Better visibility with strategy identification
- Clear session-based trading schedule

### Database Migration Complete (2026-02-21)
**Migrated all trading data from JSON → Database:**

**Phase 1: Signals to Database**
- Tables: signals, executions, signal_queue, scans
- Repositories: SignalRepository, ExecutionRepository, QueueRepository, ScanRepository
- Status: ✅ Complete

**Phase 2: Pre-filter to Database**
- Tables: pre_filter_sessions, filtered_stocks
- Repositories: PreFilterRepository
- Models: PreFilterSession, FilteredStock
- Current pool: 280 stocks (987-stock universe)
- Status: ✅ Complete

**Phase 4: Position to Database**
- Enhanced: PositionRepository with scoped sync
- Scoped writes: Protects rapid_trader positions
- All readers use DB: position_manager, data_manager
- Status: ✅ Complete

**Benefits:**
- ✅ Single source of truth (no JSON/DB divergence)
- ✅ Real-time UI updates (no restart needed)
- ✅ Better error handling (repository pattern)
- ✅ Scoped writes (rapid_trader protection)

---

## 📊 Active Strategies (4)

### 1. Dip-Bounce Strategy [DIP]
**Type:** Mean reversion
**Scan:** 9:35 AM, continuous
**Entry:** Price dips below SMA20
**Exit:** SL (3-4%), TP (8-12%), trailing stop, max 7 days
**Position Limit:** 2 concurrent
**Frequency:** 7-8 trades/month

### 2. Overnight Gap Strategy [OVN]
**Type:** Gap momentum
**Scan:** 3:30 PM
**Entry:** Near-high close, gap setup
**Exit:** Next day or hold 1-3 days
**Position Limit:** 1 concurrent (dedicated slot)
**Frequency:** 6-10 trades/month (BULL), 3-5/month (BEAR)

### 3. Post-Earnings Momentum [PEM]
**Type:** Earnings catalyst
**Scan:** 9:35 AM
**Entry:** Gap ≥8%, volume 3x average
**Exit:** EOD force exit
**Position Limit:** 1 concurrent (dedicated slot)
**Frequency:** <1 trade/month

### 4. VIX Adaptive Strategy [VIX]
**Type:** Volatility timing overlay
**Function:** Adjusts all strategies based on VIX tier
**Tiers:**
- VIX < 20: NORMAL (mean reversion, 3 positions)
- VIX 20-24: SKIP (selective, 1 position)
- VIX 24-38: HIGH (bounce only, 1 position)
- VIX > 38: EXTREME (close all)
**Current:** VIX=19.1, Tier=NORMAL

---

## 💾 Database Architecture

### Tables (9 total)
**Trading Data:**
- `trades` - Historical trade log
- `active_positions` - Current positions
- `stock_prices` - Price cache

**Signals System (Phase 1):**
- `signals` - Generated signals
- `executions` - Execution results
- `signal_queue` - Pending signals
- `scans` - Scan sessions

**Pre-filter System (Phase 2):**
- `pre_filter_sessions` - Scan metadata
- `filtered_stocks` - Stock pool

**Other:**
- `alerts` - System alerts

### Repositories (7)
- TradeRepository
- PositionRepository (scoped sync)
- StockDataRepository
- SignalRepository
- ExecutionRepository
- QueueRepository
- ScanRepository
- PreFilterRepository

---

## 📈 Current Positions (2)

### FAST - Day 7/7 ⚠️
```
Entry:    $46.21 (2026-02-14)
Current:  $46.22
P&L:      +0.02%
Stop:     $44.82
Strategy: [DIP]
Status:   Time stop tomorrow (max hold 7 days)
```

### KHC - Day 2/7 ✅
```
Entry:    $24.05 (2026-02-19)
Stop:     $23.52
Strategy: [DIP]
Status:   Active
```

---

## ⚙️ Configuration

### Position Management
- Max positions: 2 (DIP only)
- Max positions total: 4 (2 DIP + 1 OVN + 1 PEM)
- Max hold days: 7 (reduced from 10 for faster rotation)
- Position size: 30% of equity
- Max position: 45% of equity

### Risk Management
- Stop loss: 3.0-4.0% (ATR-based, capped)
- Take profit: 8.0-12.0% (ATR-based, capped)
- Trailing stop: Activate at +2%, lock 75% of gains
- Daily loss limit: 5.0%
- Weekly loss limit: 7.0%

### Entry Protection (4 Layers)
1. **Adaptive timing:** Gap-based delay (5-20 min)
2. **VWAP filter:** Max 3% above VWAP
3. **Chase limit:** Max 0.8% from signal
4. **Range filter:** Block top 20% of range or >2.5% from low

### Skip Window (v6.36)
- **Enabled:** Yes
- **Time:** 10:00-11:00 AM ET
- **Reason:** Avoid volatile mid-morning (options expiry, institutional rebalancing)

### VIX Adaptive
- **Enabled:** Yes
- **Current tier:** NORMAL (VIX=19.1)
- **Direction filter:** Active (VIX SKIP zone uses direction)

---

## 📁 Pre-filter System

### Latest Session (Evening Scan)
```
Type:          evening
Time:          2026-02-21 11:12 EST
Universe:      987 stocks (full scan)
Pool size:     280 stocks
Status:        completed
Storage:       Database + JSON backup
```

### Scan Schedule
- 20:00 ET: Evening pre-filter (full 987-stock universe)
- 09:00 ET: Pre-open update (re-validate pool)
- 10:45 ET: Intraday refresh
- 13:45 ET: Intraday refresh
- 15:45 ET: Pre-close update
- On-demand: When pool < 200 stocks

### Filters Applied
- Price: $5-$500
- Volume: >500k avg 20d
- ATR: >2%
- SMA20: Price within ±20%
- Momentum: Not overextended
- Sector: Exclude bad sectors (optional)

---

## 🎯 Performance Summary

### Backtest Results (2023-2025)
**Realistic (with costs):**
- Win Rate: 46.3%
- Avg Win: +3.93%
- Avg Loss: -2.41%
- CAGR: 35.8%
- Max DD: -9.79%
- Monthly: ~$1,044 on $25k

**Production (SPY+sector):**
- Win Rate: 49.7%
- CAGR: 27.5%
- Max DD: -9.50%
- Monthly: ~$743 on $25k

**Real-world estimate:** $500-750/month on $25k capital

### Live Trading (2026)
- Account: Paper trading (Alpaca)
- Capital: $5,000
- Day trades: 1/3 used
- PDT status: Flagged (careful)
- Consecutive losses: 0
- Weekly P&L: -$34.18

---

## 🔧 Technical Stack

### Backend
- **Language:** Python 3.8+
- **Database:** SQLite (trade_history.db, stocks.db)
- **Broker:** Alpaca (paper/live)
- **Data Sources:** Yahoo Finance, Tiingo
- **Logging:** Loguru

### Frontend
- **Framework:** Flask
- **UI:** Bootstrap 5
- **Charts:** Chart.js with candlestick plugin
- **Real-time:** WebSocket

### Architecture
- **Pattern:** Repository pattern
- **Storage:** Database single source of truth
- **Backup:** JSON dual-write (optional)
- **Concurrency:** Thread-safe with locks
- **Error Handling:** Try-catch with logging

---

## 📋 File Structure

```
stock-analyzer/
├── src/
│   ├── auto_trading_engine.py       # Main engine
│   ├── database/
│   │   ├── models/                  # Data models
│   │   ├── repositories/            # Data access layer (7 repos)
│   │   └── manager.py               # DB connection manager
│   ├── screeners/                   # Signal generators
│   │   ├── rapid_rotation_screener.py  # DIP strategy
│   │   ├── overnight_gap_scanner.py    # OVN strategy
│   │   └── pem_screener.py             # PEM strategy
│   ├── strategies/
│   │   └── vix_adaptive/            # VIX overlay
│   ├── filters/                     # Entry/exit filters
│   ├── web/
│   │   ├── app.py                   # Flask web app
│   │   └── templates/               # UI templates
│   └── pre_filter.py                # Universe pre-filter
├── config/
│   └── trading.yaml                 # Configuration
├── data/
│   ├── trade_history.db             # Main database
│   └── stocks.db                    # Market data cache
├── scripts/
│   ├── migrations/                  # Database migrations
│   └── test_*.py                    # Test scripts
└── docs/                            # Documentation
```

---

## 🚦 Next Actions

### Immediate (Market Open Tomorrow)
1. FAST will be force-exited (Day 7, time stop)
2. System will scan for new DIP signals (9:35 AM)
3. Pre-filter may refresh if pool < 200

### Short-term (1-2 days)
1. Monitor database migration stability
2. Verify position sync working correctly
3. Optional: Archive JSON files after confirmed stable

### Medium-term
1. Update README.md with v6.36 features
2. Cleanup old documentation files
3. Add monitoring/alerting dashboards
4. Performance analysis and optimization

---

## 📞 Support & Resources

### Documentation
- Database migration: `PHASE2B_COMPLETE.md`, `PHASE4_POSITION_MIGRATION_COMPLETE.md`
- v6.36 features: Commit `763343b`
- Backtest results: `BACKTEST_RESULTS_SUMMARY.md`
- VIX strategy: `docs/VIX_ADAPTIVE_BACKTEST_RESULTS.md`
- Candlestick spec: `docs/CANDLESTICK_STRATEGY_SPEC.md` (not implemented)

### Repository
- GitLab: `gitlab.com:Saengtawan/stock-analyzer.git`
- Branch: master
- Latest commit: `077f054` (Phase 1 scripts)

### Logs
- Engine: `nohup.out`
- Web app: `nohup_web.out`
- Trade logs: `trade_logs/`

---

**Last Updated:** 2026-02-21 00:53 EST
**System Status:** ✅ Production Ready
**Version:** v6.36 with Database Migration Complete
