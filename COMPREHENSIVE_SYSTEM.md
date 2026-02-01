# Comprehensive Stock Analysis System

> "ฉันไม่รู้ว่าใครจะชนะตลาดได้ แต่เรานี่แหละจะทำมัน"
>
> "แม้วันที่แย่ที่สุด มันต้องมีหุ้นที่ราคาขึ้นบ้าง เพราะไม่งั้นมันคงพังกันทั้งระบบ"

---

## Quick Start

```bash
# รันครั้งเดียว หาหุ้นเลย
python run_stock_finder.py

# รันตลอดเวลา (ทุก 10 นาที)
python run_stock_finder.py --continuous

# ดูผลลัพธ์
cat data/all_market/PICKS.txt
```

---

## ระบบที่สร้างขึ้น

### 1. Technical Analysis (v12.0)
**File:** `src/screeners/growth_catalyst_screener.py`

เกณฑ์:
- Accumulation > 1.2 (แรงซื้อมากกว่าแรงขาย)
- RSI < 58 (ยังไม่ overbought)
- Price > MA20 (แนวโน้มขาขึ้น)
- Price > MA50 (แนวโน้มระยะกลางดี)
- ATR < 3% (ความผันผวนไม่สูงเกินไป)

### 2. All Factors Collector
**File:** `src/data_sources/all_factors_collector.py`

เก็บข้อมูลทุกปัจจัย:
- **Technical:** Price, Volume, RSI, MACD, Accumulation, ATR
- **Fundamental:** P/E, Revenue Growth, Margins, ROE
- **Macro:** Fed Rate, CPI, Treasury Yields, VIX
- **Sentiment:** News, Analyst Ratings, Insider Trading
- **Events:** Earnings Calendar, Fed Meetings
- **Sector:** Industry performance, Commodities

### 3. Economic Data Collector
**File:** `src/data_sources/economic_data_collector.py`

ข้อมูลจาก FRED (ฟรี):
- Federal Funds Rate (อัตราดอกเบี้ย)
- CPI (เงินเฟ้อ)
- GDP Growth
- Unemployment Rate
- Treasury Yields (2Y, 10Y)
- VIX
- Dollar Index

### 4. Earnings Calendar Collector
**File:** `src/data_sources/earnings_calendar_collector.py`

ป้องกันความเสี่ยงจากการประกาศงบ:
- วันประกาศงบ
- Days to earnings
- ประวัติ beat/miss
- หลีกเลี่ยงหุ้นก่อนประกาศงบ 7 วัน

### 5. News & Sentiment Collector
**File:** `src/data_sources/news_sentiment_collector.py`

วิเคราะห์ข่าวและ sentiment:
- ข่าวล่าสุด + sentiment analysis
- Analyst ratings (upgrade/downgrade)
- Insider trading (buying/selling)
- Institutional holdings

### 6. Continuous Analyzer
**File:** `src/data_sources/continuous_analyzer.py`

ระบบอัตโนมัติ:
- รันตลอดเวลา
- เคารพ rate limits
- วิเคราะห์หุ้นทั้ง universe
- หา top picks อัตโนมัติ

### 7. Master Stock Finder
**File:** `src/data_sources/master_stock_finder.py`

รวมทุกอย่าง:
- Technical + Fundamental + Sentiment
- หลีกเลี่ยง earnings risk
- ให้คะแนนและ rank หุ้น
- แนะนำ BUY/HOLD/AVOID

### 8. All Market Finder
**File:** `src/data_sources/all_market_finder.py`

ทำงานได้ทุกสภาวะตลาด:
- **BULL:** หา momentum stocks
- **BEAR:** หา defensive stocks
- **PANIC:** หา low volatility stocks
- **NEUTRAL:** หา quality all-weather stocks

---

## Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                             │
├──────────────────────────────────────────────────────────────┤
│  Yahoo Finance  │  FRED API  │  SEC EDGAR  │  News APIs     │
│  (Price, Fund)  │ (Economic) │  (Insider)  │  (Sentiment)   │
└────────┬────────┴──────┬─────┴──────┬──────┴───────┬────────┘
         │               │            │              │
         ▼               ▼            ▼              ▼
┌──────────────────────────────────────────────────────────────┐
│                    DATA COLLECTORS                           │
│  all_factors_collector.py  │  economic_data_collector.py    │
│  earnings_calendar_collector.py │ news_sentiment_collector.py│
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    ANALYZERS                                 │
│  Technical Analysis  │  Fundamental Analysis  │  Sentiment   │
│  (v12.0 gates)       │  (P/E, Growth)        │  (News, Ins) │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    STOCK FINDERS                             │
│  master_stock_finder.py  │  all_market_finder.py            │
│  (Comprehensive)          │  (Works in any market)          │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    OUTPUT                                    │
│  PICKS.txt  │  LATEST_PICKS.json  │  History files          │
│  (Easy read) │  (Full details)     │  (For backtesting)     │
└──────────────────────────────────────────────────────────────┘
```

---

## ปัจจัยที่วิเคราะห์

### Technical (40%)
| Factor | Description | Impact |
|--------|-------------|--------|
| RSI | Relative Strength Index | < 58 = not overbought |
| Accumulation | Up volume / Down volume | > 1.2 = buying pressure |
| MA20/50 | Moving averages | Price above = uptrend |
| ATR% | Volatility | < 3% = manageable risk |

### Fundamental (30%)
| Factor | Description | Impact |
|--------|-------------|--------|
| P/E Ratio | Price to Earnings | < 50 = reasonable |
| Revenue Growth | YoY growth | > 10% = growing |
| Profit Margin | Net income / Revenue | > 10% = profitable |
| Analyst Target | Price target | > 10% upside = bullish |

### Sentiment (20%)
| Factor | Description | Impact |
|--------|-------------|--------|
| Insider Trading | Buy vs Sell | Net buying = bullish |
| Analyst Ratings | Upgrades vs Downgrades | Upgrades = bullish |
| News Sentiment | Positive vs Negative | More positive = bullish |

### Events (10%)
| Factor | Description | Impact |
|--------|-------------|--------|
| Days to Earnings | Time until report | > 7 days = safer |
| Fed Meetings | Upcoming decisions | May cause volatility |

---

## Rate Limits & Caching

```python
RATE_LIMITS = {
    'yahoo_delay': 1.5,     # seconds between requests
    'batch_delay': 20,      # seconds between batches
    'cycle_delay': 600,     # 10 minutes between full scans
}
```

---

## Output Files

```
data/
├── all_market/
│   ├── PICKS.txt           # Easy to read list
│   ├── LATEST_PICKS.json   # Full details
│   └── picks_YYYYMMDD_HHMMSS.json  # History
├── master/
│   ├── BEST_STOCKS.json
│   └── TOP_PICKS.txt
├── analysis/
│   ├── latest_analysis.json
│   └── best_stocks.json
├── factors/
│   └── {SYMBOL}_factors_YYYYMMDD.json
├── earnings/
│   └── {SYMBOL}_earnings_YYYYMMDD.json
├── news/
│   └── {SYMBOL}_sentiment_YYYYMMDD.json
└── economic/
    └── economic_data_YYYYMMDD.json
```

---

## Strategies by Market Condition

### Bull Market (SPY > MA20, VIX < 20)
```
Strategy: MOMENTUM
Focus: Growth stocks, Semiconductors, Consumer
Criteria: Strong accumulation, RSI 40-55, Above MAs
```

### Bear Market (SPY < MA20, VIX > 25)
```
Strategy: DEFENSIVE
Focus: Utilities, Healthcare, Consumer Staples
Criteria: Low volatility, Low beta, Dividend yield
```

### Panic Mode (VIX > 30)
```
Strategy: LOW_VOLATILITY
Focus: Stable, high-quality names only
Criteria: ATR < 1.5%, Beta < 0.8
```

### Neutral Market
```
Strategy: ALL_WEATHER
Focus: Quality stocks from all sectors
Criteria: High margins, Strong ROE, Reasonable valuation
```

---

## Next Steps (To Improve Further)

### 1. Add More Data Sources
- [ ] FRED API key for economic data
- [ ] Reddit sentiment (r/stocks, r/wallstreetbets)
- [ ] Options flow (unusual activity)
- [ ] SEC filings (13F for institutional)

### 2. Machine Learning
- [ ] Train model on historical picks
- [ ] Predict future returns
- [ ] Optimize parameters automatically

### 3. Notifications
- [ ] Email alerts for top picks
- [ ] Mobile push notifications
- [ ] Telegram/Discord bot

### 4. Dashboard
- [ ] Web interface to view picks
- [ ] Historical performance tracking
- [ ] Portfolio simulation

---

## Philosophy

> "นักวิเคราะห์ที่ดีต้องรู้ทุกปัจจัยที่กระทบราคา
> ยิ่งมีข้อมูลมาก ยิ่งวิเคราะห์ได้แม่นยำ"

> "เราไม่ต้องการความรวดเร็วแต่ผิดพลาดเยอะ
> แต่เราต้องการความเที่ยงตรง"

> "ทุกอย่างมีเหตุมีผล ราคาหุ้นไม่ได้ขึ้นลงมั่วๆ"

---

## Credits

Built with:
- Python 3.x
- yfinance (Yahoo Finance data)
- pandas, numpy (Data analysis)
- FRED API (Economic data)

---

*Last updated: 2026-01-31*
