---
name: deep-backtest
description: Run comprehensive backtest across ALL dimensions using 56M intraday bars + 1.5M OHLC — find edges humans miss
allowed-tools: Read, Bash, Agent, Grep, Glob
---

# Deep Backtest — วิเคราะห์ทุกมิติจาก DB จริง

DB: `data/trade_history.db`
- `intraday_bars_5m`: 56M bars, 1000 symbols, 2024-2026
- `stock_daily_ohlc`: 1.5M rows
- `macro_snapshots`: VIX, SPY, crude, gold, BTC
- `market_breadth`: pct_above_20d_ma, ad_ratio
- `short_interest`: SI% per stock
- `stock_fundamentals`: beta, market_cap, pe
- `insider_transactions`: insider buy/sell
- `options_daily_summary`: PC ratio, unusual calls/puts
- `earnings_calendar`: next earnings date
- `sector_etf_daily_returns`: sector performance

## รัน Agent 5 ตัวพร้อมกัน (parallel)

### Agent 1: VIX Tier × Setup WR
```sql
-- Join macro_snapshots (VIX) กับ intraday setups
-- แยก VIX tiers: <18, 18-22, 22-28, 28-35, 35+
-- หา WR per setup (Down Bounce, Momentum, Vol Surge) per VIX tier
-- Output: ตาราง VIX tier × setup × WR × avg return × N
```

### Agent 2: Market Breadth × Bounce WR
```sql
-- Join market_breadth กับ daily bounce setups
-- แยก breadth tiers: <30%, 30-50%, 50-70%, 70%+
-- หา WR ของ Down Bounce per breadth tier
-- AD ratio tiers: <1, 1-2, 2-3, 3+
-- Output: breadth tier × WR × avg return
```

### Agent 3: Short Interest × Bounce Strength
```sql
-- Join short_interest กับ intraday bounce
-- แยก SI tiers: <5%, 5-10%, 10-20%, 20%+
-- หา: avg bounce %, WR, max gain per SI tier
-- ดูว่า SI สูงจริงๆ ช่วย bounce มั้ย หรือแค่ volatile
```

### Agent 4: Options Flow → Next Day Return
```sql
-- Join options_daily_summary กับ stock_daily_ohlc D+1
-- PC ratio tiers: <0.5 (call heavy), 0.5-1.0, 1.0-1.5, 1.5+ (put heavy)
-- Unusual calls > 10 vs < 10 → D+1 return
-- Output: PC ratio tier × D+1 WR × avg return
```

### Agent 5: Insider Buying → Return
```sql
-- Join insider_transactions กับ stock_daily_ohlc D+1..D+5
-- ดู return หลัง insider buy vs no insider buy
-- Filter: buy > $100K (meaningful size)
-- Output: insider buy → D+1, D+3, D+5 WR + avg return
```

## หลัง Agent เสร็จ

1. สรุปผลทั้ง 5 มิติ
2. ระบุ findings ที่มี statistical significance (N > 100)
3. แนะนำว่าควรเพิ่ม data ไหนเข้า prompt
4. ถาม "เพิ่มเข้า prompt เลยมั้ย?"

## Bonus: Cross-tab ที่น่าสนใจ

ถ้ามีเวลา รันเพิ่ม:
- Day of week × setup × WR
- Earnings proximity (D-5 to D-1 before earnings) × WR
- Consecutive up days × next day WR
- Sector × VIX tier × WR (3-way cross)
- Time of day × sector × WR
- Volume spike (3x+) timing → intraday return pattern

## Output Format

```
=== Deep Backtest Results ===

1. VIX Tier (N=XXK)
| VIX | Down Bounce WR | Momentum WR | Avg Return |
| <18 | XX% | XX% | +X.X% |
...

2. Breadth (N=XXK)
...

สรุป: findings ที่ actionable + ควรเพิ่มเข้า prompt
```
