# Stock Analyzer — AI-Powered Intraday Trading System

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Status](https://img.shields.io/badge/status-production-green.svg)
![Data](https://img.shields.io/badge/data-Alpaca%20realtime-green.svg)

AI scans 200+ stocks via Alpaca real-time API, analyzes with backtest-validated data (126K setups), and recommends BUY NOW 1-3 picks with Entry/SL/TP.

**Account:** Alpaca Paper ($5K, dynamic budget)
**AI:** Claude Code + CLAUDE.md + 5 prompt files
**Data:** 56M intraday bars + 1.5M daily OHLC + 1000 stock universe

---

## Quick Start

### From Google Drive backup (5 min)

```bash
git clone git@gitlab.com:Saengtawan/stock-analyzer.git
cd stock-analyzer
./setup.sh
# Download from Drive → วาง .env (root) + trade_history.db.gz (data/)
gunzip data/trade_history.db.gz
# พร้อมใช้ → "scan หุ้น" ใน Claude Code
```

### From scratch (2-3 days)

```bash
git clone git@gitlab.com:Saengtawan/stock-analyzer.git
cd stock-analyzer
./setup.sh
# แก้ .env ใส่ Alpaca keys (https://app.alpaca.markets)
# สร้าง DB + backfill:
python3 scripts/maintain_universe_1000.py
python3 scripts/update_stock_ohlc.py
python3 scripts/collect_intraday_5m_daily.py
python3 scripts/macro_snapshot_cron.py
python3 scripts/collect_stock_fundamentals.py
```

---

## How It Works

```
User: "scan หุ้น"
  ↓
CLAUDE.md → เช็คเวลา → เลือก prompt → Alpaca scan 200 stocks (2 วิ)
  ↓
DB query: news, SI, beta, mcap, insider, options, breadth
  ↓
AI วิเคราะห์ data + prompt knowledge → BUY NOW 1-3 ตัว
```

### 5 Scan Modes (by time)

| เวลา ET | Mode | ทำอะไร |
|---------|------|--------|
| 06:00-09:30 | ORB | PM gap + vol + catalyst → watchlist |
| 09:30-11:30 | Intraday | Down Bounce + Momentum + Vol Surge |
| 11:30-15:30 | Top Movers | Sector momentum + Down Bounce + Drop depth |
| 15:30-15:55 | OVN | 5d mom + vol + close position → overnight gap |
| Friday 15:00 | Fri-Mon | Friday rally/bounce → Monday close |

### AI Judgment (not hardcode)

- Prompts give DATA only (WR%, avg return, bounce speed)
- No directives ("skip!", "ห้าม", "ต้อง")
- No hardcoded sector/threshold
- AI weighs all factors and decides per stock per day

---

## Architecture

```
src/
├── auto_trading_engine.py    # Main engine (systemd service)
├── discovery/engine.py       # Discovery scanner + MacroDayGate ML
├── database/                 # ORM + repositories
├── web/app.py                # Flask dashboard
config/
├── trading.yaml              # Trading params
├── discovery.yaml            # Discovery config
prompts/                      # AI scan prompts (5 files)
├── orb_breakout_prompt.md
├── intraday_3pct_prompt.md
├── top_movers_prompt.md
├── ovn_gap_prompt.md
├── friday_monday_prompt.md
CLAUDE.md                     # Master AI instructions + scan code
data/trade_history.db          # SQLite 13GB (not in git)
```

### Key DB Tables

| Table | Rows | Purpose |
|-------|------|---------|
| stock_daily_ohlc | 1.5M | Daily OHLC 1000 stocks |
| intraday_bars_5m | 56M | 5-min bars 2024-2026 |
| macro_snapshots | 2K+ | VIX, SPY, crude, gold, BTC |
| stock_fundamentals | 1K | Beta, MCap, PE (98% coverage) |
| universe_stocks | 1K | Top 1000 by dollar volume |
| news_events | 50K+ | Stock news + sentiment |
| short_interest | 8K+ | SI% per stock |

### Services

```bash
systemctl --user start auto-trading.service   # Trading engine
systemctl --user start stock-webapp.service   # Web dashboard :5002
# NEVER pkill — always use systemctl
```

### Cron (40+ jobs)

All times Bangkok (ET + 11h during EDT). Key jobs:
- 04:05 BKK: update_stock_ohlc (daily OHLC)
- 04:20 BKK: collect_intraday_5m_daily (5-min bars)
- 07:00 BKK: evening pre-filter
- 07:30 BKK: discovery scan
- 20:00 BKK: pre-open scan

---

## Data Sources

| Source | API | Used For |
|--------|-----|----------|
| **Alpaca** | Real-time snapshots | Scan (2 sec for 200 stocks) |
| **yfinance** | Historical | Backfill only (not for scan) |
| **SQLite DB** | Local | All historical data + context |

---

## Claude Code Integration

### Scan

```bash
# ใน Claude Code พิมพ์:
scan หุ้น
# → AI อ่าน CLAUDE.md → เลือก prompt ตามเวลา → scan → BUY NOW
```

### Audit prompts

```bash
/audit-prompts
# → ตรวจ directive, bias, inconsistency ใน CLAUDE.md + prompts
```

### Skills

| Skill | ทำอะไร |
|-------|--------|
| `/audit-prompts` | Audit CLAUDE.md + 5 prompts for issues |

---

**Last Updated:** 2026-04-09
