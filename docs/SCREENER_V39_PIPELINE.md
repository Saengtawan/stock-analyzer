# Part 1: SCREENER (RapidRotationScreener v3.9)

## Overview

Screener ใช้ **Bounce Confirmation** strategy:
1. หาหุ้นที่ dip เมื่อวาน (setup)
2. วันนี้เด้งกลับ (confirmation)
3. ยังอยู่ใน uptrend (SMA20 filter)

## Screening Flow

```
Universe: High-Beta Tech + Financials (~100 stocks)
                    │
                    ▼
            ┌───────────────────┐
            │ GATE 1: Price     │  $10 - $2,000
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │ GATE 2: Yesterday │  ลง >= -1% (the dip)
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │ GATE 3: Today     │  ไม่ลงต่อ (mom_1d >= -1%)
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │ GATE 4: Bounce    │  Green candle หรือ +0.5%
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │ GATE 5: Gap       │  Gap up < 2%
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │ GATE 6: Extension │  ไม่เกิน SMA5 +2%
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │ GATE 7: ATR       │  ATR >= 2.5%
            └───────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────────────────────┐
            │ GATE 8: SMA20 (ROOT CAUSE FIX)    │
            │ Price > SMA20 (uptrend)           │
            └───────────────────────────────────┘
                    │ Pass
                    ▼
            ┌───────────────────┐
            │     SCORING       │  0-100 points
            └───────────────────┘
                    │
                    ▼
            ┌───────────────────┐
            │  THRESHOLD: 90    │
            └───────────────────┘
                    │ Pass
                    ▼
              TOP SIGNALS
```

## Gate Details

### Gate 1: Price Filter
```python
if current_price < 10 or current_price > 2000:
    return None
```

**Why?**
- < $10: Penny stocks, spread กว้าง, manipulation ง่าย
- > $2,000: ยังรับได้ (เช่น GOOG, AVGO)

### Gate 2: Yesterday Dip (The Setup)
```python
yesterday_move = ((close[-1] / close[-2]) - 1) * 100

if yesterday_move > -1.0:
    return None  # ต้องลง >= -1%
```

**Why?**
- ต้องมี "dip" ก่อนถึงจะ "bounce" ได้
- Dip >= -1% = มี room ให้เด้ง
- ถ้าเมื่อวานขึ้น = ไม่ใช่ bounce setup

### Gate 3: Today Not Falling
```python
mom_1d = ((close[-1] / close[-2]) - 1) * 100  # Today's move

if mom_1d < -1.0:
    return None  # ยังลงอยู่ รอก่อน
```

**Why?**
- ถ้าวันนี้ยังลง -1% = falling knife
- รอให้หยุดลงก่อนค่อยเข้า

### Gate 4: Bounce Confirmation
```python
today_is_green = current_price > today_open

if not today_is_green and mom_1d < 0.5:
    return None  # ไม่มี bounce signal
```

**Why?**
- Green candle = buyers เข้ามา
- หรือ mom_1d > 0.5% = momentum กลับ
- ต้องมีอย่างใดอย่างหนึ่ง

### Gate 5: Gap Filter
```python
gap_pct = (today_open - prev_close) / prev_close * 100

if gap_pct > 2.0:
    return None  # Gap up เยอะเกินไป
```

**Why?**
- Gap up > 2% = exhaustion risk
- มักจะ fade ระหว่างวัน
- เข้าที่ gap เล็กๆ ดีกว่า

### Gate 6: Extension Filter
```python
if current_price > sma5 * 1.02:
    return None  # เกิน SMA5 ไป 2% แล้ว
```

**Why?**
- ถ้าวิ่งเกิน SMA5 ไปมาก = late entry
- Risk/reward ไม่ดี
- เข้าใกล้ SMA5 ดีกว่า

### Gate 7: Volatility Filter (ATR)
```python
MIN_ATR_PCT = 2.5

if atr_pct < MIN_ATR_PCT:
    return None
```

**Why?**
- ATR < 2.5% = หุ้นเคลื่อนไหวน้อย
- TP +6% ใช้เวลานานเกินไป
- ต้องการหุ้นที่ขยับเร็ว

### Gate 8: SMA20 Filter (ROOT CAUSE FIX)
```python
# v3.5: Based on root cause analysis
# 92% of stop loss trades were below SMA20

if current_price < sma20:
    return None  # Must be above SMA20
```

**Why?**
- จาก backtest: 92% ของ trades ที่โดน SL อยู่ต่ำกว่า SMA20
- SMA20 = short-term trend indicator
- Price > SMA20 = uptrend ยังดี
- Price < SMA20 = downtrend, อย่าเข้า

---

## Scoring System (0-100)

```python
def calculate_score(stock):
    score = 0

    # 1. BOUNCE CONFIRMATION (40 pts max)
    if today_is_green and mom_1d > 0.5:
        score += 40  # Strong bounce
    elif today_is_green or mom_1d > 0.3:
        score += 25  # Bounce confirmed

    # 2. PRIOR DIP MAGNITUDE - 5 day (40 pts max)
    if -12 <= mom_5d <= -5:
        score += 40  # Deep dip (best setup)
    elif -5 < mom_5d <= -3:
        score += 30  # Good dip
    elif -3 < mom_5d < 0:
        score += 15  # Mild dip

    # 3. YESTERDAY'S DIP (15 pts max)
    if yesterday_move <= -3:
        score += 15  # Big dip
    elif yesterday_move <= -1.5:
        score += 10  # Good dip
    elif yesterday_move <= -1:
        score += 5   # Minimum dip

    # 4. RSI SCORING (15 pts max)
    if rsi < 35:
        score += 15  # Very oversold
    elif rsi < 45:
        score += 10  # Oversold zone

    # 5. TREND CONTEXT (10 pts max)
    if current_price > sma20:
        score += 10  # Uptrend
        if current_price > sma50:
            score += 5  # Strong uptrend

    # 6. VOLUME SURGE (10 pts max)
    if volume_ratio > 1.5:
        score += 10  # High volume bounce

    # 7. SECTOR REGIME (±10 pts)
    if sector_regime == 'BULL':
        score += 5   # Hot sector bonus
    elif sector_regime == 'BEAR':
        score -= 10  # Cold sector penalty

    return min(100, max(0, score))
```

## Score Breakdown

| Component | Max Points | Condition |
|-----------|------------|-----------|
| Bounce confirmation | 40 | Green + mom > 0.5% |
| Prior dip (5d) | 40 | -12% to -5% |
| Yesterday dip | 15 | <= -3% |
| RSI oversold | 15 | RSI < 35 |
| Trend (SMA20/50) | 15 | Above both |
| Volume surge | 10 | > 1.5x avg |
| Sector regime | +5/-10 | BULL/BEAR |
| **Total possible** | **~130** | Capped at 100 |

## Score Threshold

```python
MIN_SCORE = 90  # Only take high-conviction signals
```

**Why 90?**
- ต้องผ่านหลาย conditions
- Deep dip + Strong bounce + Uptrend = score สูง
- ลด false signals

---

## Examples

### Example: Qualifying Stock

```
NVDA Analysis:
─────────────────────────────────────
Yesterday: -2.1% (dip day)        ✓ Gate 2
Today: +1.2% (green candle)       ✓ Gate 3, 4
Gap: +0.3%                        ✓ Gate 5
Price vs SMA5: +0.8%              ✓ Gate 6
ATR: 3.2%                         ✓ Gate 7
Price vs SMA20: +4.5%             ✓ Gate 8

Scoring:
- Bounce: 40 (green + strong)
- 5d dip: 30 (-4.2%)
- Yesterday: 10 (-2.1%)
- RSI: 10 (RSI=42)
- Trend: 10 (above SMA20)
- Volume: 0 (normal)
- Sector: +5 (Tech = BULL)
─────────────────────────────────────
Total Score: 105 → Capped at 100  ✓ PASS

Signal: BUY NVDA
```

### Example: Rejected Stock (No Dip)

```
XOM Analysis:
─────────────────────────────────────
Yesterday: -0.5%                  ✗ Gate 2 FAIL
                                    (need >= -1%)

Result: REJECTED (no dip setup)
```

### Example: Rejected Stock (Falling Knife)

```
ROKU Analysis:
─────────────────────────────────────
Yesterday: -3.2%                  ✓ Gate 2
Today: -1.5%                      ✗ Gate 3 FAIL
                                    (still falling)

Result: REJECTED (falling knife)
```

### Example: Rejected Stock (Below SMA20)

```
META Analysis:
─────────────────────────────────────
Yesterday: -1.8%                  ✓ Gate 2
Today: +0.8%                      ✓ Gate 3
Green candle: Yes                 ✓ Gate 4
Gap: +0.5%                        ✓ Gate 5
Price vs SMA5: +1.5%              ✓ Gate 6
ATR: 2.8%                         ✓ Gate 7
Price vs SMA20: -1.2%             ✗ Gate 8 FAIL
                                    (below SMA20 = downtrend)

Result: REJECTED (below SMA20)
```

---

## Summary: v3.9 Screener Pipeline

| Step | Filter | Condition | Purpose |
|------|--------|-----------|---------|
| 1 | Price | $10-$2,000 | Tradeable range |
| 2 | Yesterday | Down >= -1% | Setup day |
| 3 | Today mom | >= -1% | Not falling |
| 4 | Bounce | Green OR +0.5% | Confirmation |
| 5 | Gap | < 2% | Not exhausted |
| 6 | Extension | < SMA5 +2% | Good entry |
| 7 | ATR | >= 2.5% | Volatile enough |
| 8 | SMA20 | Price > SMA20 | Uptrend only |
| 9 | Score | >= 90 | High conviction |

**Philosophy: "Buy the dip in an uptrend, after bounce confirmation"**
