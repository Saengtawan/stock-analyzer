# Stock Analyzer - Automated Trading System

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Version](https://img.shields.io/badge/version-6.36-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

Production-ready automated trading system with database-backed architecture, multi-strategy support, and comprehensive risk management.

**Current Version:** v6.36 (Database Migration Complete)
**Last Updated:** 2026-02-21
**Status:** ✅ Production Ready

---

## 🎯 Overview

Automated trading system that combines multiple strategies with intelligent risk management. Features database-backed storage, real-time monitoring, and adaptive strategy selection based on market volatility.

### Key Features

- **4 Active Strategies:** DIP-bounce, Overnight Gap, Post-Earnings Momentum, VIX Adaptive
- **Database Architecture:** Single source of truth with SQLite
- **Real-time Monitoring:** Web dashboard with live updates
- **Risk Management:** Multi-layer protection with PDT compliance
- **Skip Window:** Avoids volatile 10:00-11:00 AM trading period
- **Strategy Tags:** Clear identification ([DIP], [OVN], [PEM])

---

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.8+
python --version

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your Alpaca API keys
```

### Installation

```bash
# 1. Clone repository
git clone https://gitlab.com/Saengtawan/stock-analyzer.git
cd stock-analyzer

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply database migrations
bash scripts/apply_migration_001.sh  # Signals tables
bash scripts/apply_migration_002.sh  # Pre-filter tables

# 4. Configure settings
cp config/trading.yaml.example config/trading.yaml
# Edit trading.yaml with your preferences
```

### Running the System

```bash
# Start auto trading engine
nohup python src/auto_trading_engine.py > nohup.out 2>&1 &

# Start web dashboard
nohup python src/run_app.py > nohup_web.out 2>&1 &

# Check status
ps aux | grep -E "auto_trading|run_app"

# View logs
tail -f nohup.out
```

---

## 📊 Active Strategies

### 1. Dip-Bounce Strategy [DIP]
**Type:** Mean reversion
**Entry:** Price dips below SMA20, oversold conditions
**Exit:** SL (3-4%), TP (8-12%), trailing stop, max 7 days
**Position Limit:** 2 concurrent
**Frequency:** ~7-8 trades/month

**Performance (Backtest 2023-2025):**
- Win Rate: 46.3%
- CAGR: 35.8%
- Max DD: -9.79%
- Monthly: ~$1,044 on $25k

### 2. Overnight Gap Strategy [OVN]
**Type:** Gap momentum
**Entry:** Near-high close (3:30 PM), gap setup for next day
**Exit:** Next day or hold 1-3 days
**Position Limit:** 1 concurrent (dedicated slot)
**Frequency:** 6-10 trades/month (BULL), 3-5/month (BEAR)

### 3. Post-Earnings Momentum [PEM]
**Type:** Earnings catalyst
**Entry:** Gap ≥8%, volume 3x average, after earnings
**Exit:** EOD force exit
**Position Limit:** 1 concurrent (dedicated slot)
**Frequency:** <1 trade/month

### 4. VIX Adaptive Strategy [VIX]
**Type:** Volatility timing overlay
**Function:** Adjusts all strategies based on VIX tier

**VIX Tiers:**
- **VIX < 20:** NORMAL (mean reversion, 3 positions)
- **VIX 20-24:** SKIP (selective, VIX direction matters)
- **VIX 24-38:** HIGH (bounce only, 1 position)
- **VIX > 38:** EXTREME (close all positions)

---

## 🏗️ Architecture

### Database Schema

```
trade_history.db
├── trading_signals      # Signal generation log
├── execution_history    # Trade execution results
├── signal_queue         # Pending signals
├── scan_sessions        # Scan metadata
├── pre_filter_sessions  # Pre-filter runs (280 stocks)
├── filtered_stocks      # Stock pool
├── active_positions     # Current positions
├── trades               # Historical trades
└── alerts               # System alerts
```

### System Components

```
┌─────────────────────────────────────────────────────┐
│                  Auto Trading Engine                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │   Screeners  │  │  Strategies  │  │  Filters  │ │
│  │ - DIP        │  │ - VIX        │  │ - Entry   │ │
│  │ - OVN        │  │ - Adaptive   │  │ - Risk    │ │
│  │ - PEM        │  │              │  │ - Sector  │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│              Database (Single Source)               │
│  - Positions (scoped sync)                          │
│  - Signals (212/day avg)                            │
│  - Pre-filter (280 stocks)                          │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│                  Web Dashboard                      │
│  - Real-time monitoring                             │
│  - Position tracking                                │
│  - Signal history                                   │
│  - Performance metrics                              │
└─────────────────────────────────────────────────────┘
```

---

## ⚙️ Configuration

### Position Management (`config/trading.yaml`)

```yaml
rapid_rotation:
  max_positions: 2              # DIP strategy limit
  max_positions_total: 4        # Total: 2 DIP + 1 OVN + 1 PEM
  max_hold_days: 7              # Time stop
  position_size_pct: 30.0       # % of equity per position
  max_position_pct: 45.0        # Max single position size
```

### Risk Management

```yaml
  # Stop Loss / Take Profit (ATR-based)
  atr_sl_multiplier: 1.5        # SL = 1.5 × ATR%
  min_sl_pct: 3.0               # Min 3% stop loss
  max_sl_pct: 4.0               # Max 4% stop loss
  atr_tp_multiplier: 3.0        # TP = 3.0 × ATR%
  min_tp_pct: 8.0               # Min 8% take profit
  max_tp_pct: 12.0              # Max 12% take profit

  # Trailing Stop
  trail_activation_pct: 2.0     # Activate at +2%
  trail_lock_pct: 75.0          # Lock 75% of gains

  # Risk Limits
  daily_loss_limit_pct: 5.0     # Daily loss limit
  weekly_loss_limit_pct: 7.0    # Weekly loss limit
```

### Skip Window (v6.36)

```yaml
  # No trading during volatile mid-morning period
  skip_window_enabled: true
  skip_window_start_hour: 10    # 10:00 AM ET
  skip_window_end_hour: 11      # 11:00 AM ET
```

### Entry Protection (4 Layers)

```yaml
  # Layer 1: Adaptive timing based on gap
  # Layer 2: VWAP filter (max 3% above)
  # Layer 3: Chase limit (max 0.8% from signal)
  # Layer 4: Range filter (avoid top 20%)
```

---

## 📈 Performance

### Backtest Results (2023-2025, Realistic)

**With Costs (0.2% slippage + 0.1% commission):**
- **Total Trades:** 866
- **Win Rate:** 46.3%
- **Avg Win:** +3.93%
- **Avg Loss:** -2.41%
- **CAGR:** 35.8%
- **Max Drawdown:** -9.79%
- **Monthly Return:** ~$1,044 on $25k capital

**Production Estimate (SPY+Sector Filter):**
- **Win Rate:** 49.7%
- **CAGR:** 27.5%
- **Monthly Return:** ~$750 on $25k capital

### Live Performance Metrics

Monitor via web dashboard at `http://localhost:5002`

---

## 🖥️ Web Dashboard

### Features

- **Real-time Position Tracking**
  - Current P&L with strategy tags
  - Stop loss / Take profit levels
  - Days held counter
  - Risk visualization

- **Signal History**
  - 212+ signals/day analyzed
  - Filter by strategy, score, time
  - Execution results

- **Timeline View**
  - 8 trading sessions (Gap, Morning, PEM, SKIP, Midday, Afternoon, OVN, Pre-Close)
  - Live session status
  - Next scan countdown

- **Performance Metrics**
  - Win rate, P&L, trades
  - Drawdown tracking
  - Strategy breakdown

### Access

```
URL: http://localhost:5002
Default Port: 5002
```

---

## 🔧 Advanced Usage

### Pre-filter System

Scans 987-stock universe daily, maintains pool of ~280 quality stocks.

**Scan Schedule:**
- 20:00 ET: Evening pre-filter (full scan)
- 09:00 ET: Pre-open update
- 10:45 ET: Intraday refresh
- 13:45 ET: Afternoon refresh
- 15:45 ET: Pre-close update
- On-demand: When pool < 200 stocks

**Manual Pre-filter:**
```bash
# Run evening scan
python src/pre_filter.py evening

# Run pre-open scan
python src/pre_filter.py pre_open

# Check status
python scripts/test_prefilter_db_integration.py
```

### Database Queries

```bash
# Check positions
sqlite3 data/trade_history.db "SELECT * FROM active_positions"

# Check recent signals
sqlite3 data/trade_history.db "SELECT symbol, score, signal_price, signal_time FROM trading_signals ORDER BY signal_time DESC LIMIT 10"

# Check pre-filter pool
sqlite3 data/trade_history.db "SELECT COUNT(*) FROM filtered_stocks WHERE session_id = (SELECT id FROM pre_filter_sessions ORDER BY id DESC LIMIT 1)"
```

### Testing

```bash
# Test database integration
python scripts/test_position_db_integration.py
python scripts/test_prefilter_db_integration.py

# Test pre-filter models
python scripts/test_prefilter_models.py
```

---

## 📁 Project Structure

```
stock-analyzer/
├── src/
│   ├── auto_trading_engine.py       # Main engine
│   ├── pre_filter.py                # Universe pre-filter
│   ├── database/
│   │   ├── models/                  # Data models
│   │   └── repositories/            # Data access (7 repos)
│   ├── screeners/                   # Signal generators
│   │   ├── rapid_rotation_screener.py
│   │   ├── overnight_gap_scanner.py
│   │   └── pem_screener.py
│   ├── strategies/
│   │   └── vix_adaptive/            # VIX overlay
│   ├── filters/                     # Entry/exit filters
│   └── web/
│       ├── app.py                   # Flask web app
│       └── templates/               # UI templates
├── config/
│   └── trading.yaml                 # Configuration
├── data/
│   ├── trade_history.db             # Main database
│   └── stocks.db                    # Market data cache
├── scripts/
│   ├── migrations/                  # Database migrations
│   └── test_*.py                    # Test scripts
├── docs/                            # Documentation
└── SYSTEM_STATUS_2026-02-21.md      # Current status
```

---

## 🛡️ Safety Features

### PDT Protection
- Day trade tracking
- Reserve day trades
- Flagged account handling
- Overnight holds for PDT accounts

### Risk Limits
- Daily loss limit: 5%
- Weekly loss limit: 7%
- Max consecutive losses: 3
- Position size caps

### Entry Protection (4 Layers)
1. **Adaptive timing:** Gap-based delay (5-20 min)
2. **VWAP filter:** Max 3% above VWAP
3. **Chase limit:** Max 0.8% from signal price
4. **Range filter:** Avoid top 20% of range

### VIX EXTREME Protection
- Auto-close all positions if VIX > 38
- Max drawdown protection: 2.35× better than market during COVID

---

## 📚 Documentation

### Core Documents
- **SYSTEM_STATUS_2026-02-21.md** - Current system status
- **PHASE2B_COMPLETE.md** - Pre-filter migration
- **PHASE4_POSITION_MIGRATION_COMPLETE.md** - Position migration
- **BACKTEST_RESULTS_SUMMARY.md** - Performance analysis

### Strategy Documentation
- **docs/VIX_ADAPTIVE_BACKTEST_RESULTS.md** - VIX strategy details
- **docs/CANDLESTICK_STRATEGY_SPEC.md** - Candlestick spec (not implemented)

### Migration Guides
- **docs/DATABASE_MIGRATION_COMPLETE.md** - Full migration summary
- **docs/DATABASE_SCHEMA_PHASE1.md** - Schema documentation

---

## 🔄 Recent Updates

### v6.36 (2026-02-21)
- ✅ Skip window 10:00-11:00 AM (avoid volatile period)
- ✅ Strategy tags [DIP], [OVN], [PEM]
- ✅ Enhanced timeline (8 sessions)
- ✅ Position limits: 4 total (2 DIP + 1 OVN + 1 PEM)

### Database Migration (2026-02-21)
- ✅ All data → Database single source of truth
- ✅ Phase 1: Signals to DB
- ✅ Phase 2: Pre-filter to DB
- ✅ Phase 4: Positions to DB (scoped sync)

### v6.35 (2026-02-20)
- Overnight Gap gets dedicated slot
- Expanded entry criteria
- Multi-strategy position management

---

## 🤝 Contributing

This is a personal trading system. Not accepting external contributions.

---

## ⚠️ Disclaimer

This software is for educational and personal use only. Trading involves risk of loss. Past performance does not guarantee future results. Use at your own risk.

**NOT FINANCIAL ADVICE**

---

## 📞 Support

### Repository
- GitLab: `gitlab.com:Saengtawan/stock-analyzer.git`
- Branch: master

### System Status
Check `SYSTEM_STATUS_2026-02-21.md` for current configuration and performance.

### Logs
- Engine: `nohup.out`
- Web App: `nohup_web.out`
- Trade Logs: `trade_logs/`

---

## 📊 Statistics

- **Version:** v6.36
- **Active Strategies:** 4 (DIP, OVN, PEM, VIX)
- **Database Tables:** 9
- **Repositories:** 7
- **Average Signals/Day:** ~212
- **Pre-filter Pool:** ~280 stocks
- **Production Status:** ✅ Ready

---

**Last Updated:** 2026-02-21
**System Status:** Production Ready
**Database:** Migrated & Verified
