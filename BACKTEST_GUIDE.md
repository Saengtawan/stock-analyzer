# 🔬 Backtest Guide - ทดสอบความแม่นยำของระบบ

## 📋 คำอธิบาย

Backtesting คือการทดสอบระบบวิเคราะห์โดยใช้ข้อมูลย้อนหลัง เพื่อดูว่า:
- คำแนะนำของระบบถูกต้องหรือไม่
- Target Price (TP) โดน hit กี่ครั้ง
- Stop Loss (SL) โดน hit กี่ครั้ง
- Win rate เท่าไร
- Return เฉลี่ยเท่าไร

---

## 🚀 วิธีใช้งาน

### 1. **Single Backtest** (ทดสอบ 1 ครั้ง)

ทดสอบหุ้นย้อนหลัง 7 วัน:

```bash
python backtest_analyzer.py AAPL --days-back 7
```

**ตัวอย่างผลลัพธ์:**
```
============================================================
📊 BACKTEST RESULTS SUMMARY
============================================================
Symbol: AAPL
Analysis Date: 2024-11-07
Recommendation: BUY (Score: 7.2, Confidence: MEDIUM)
------------------------------------------------------------
Entry Price: $225.50
Target Price: $235.20 (+4.30%)
Stop Loss: $218.90 (-2.93%)
R:R Ratio: 1.47
------------------------------------------------------------
Actual Outcome: 🎯 WIN
Exit Price: $235.20 on 2024-11-12
Return: +4.30%
Max Gain: +5.10% | Max Loss: -1.20%
Days Held: 5
TP Hit: ✅ Yes
SL Hit: ✅ No
------------------------------------------------------------
Recommendation Correct: ✅ YES
============================================================
```

### 2. **Multiple Backtests** (ทดสอบหลายครั้ง)

ทดสอบย้อนหลัง 30 วัน ทุกๆ 7 วัน:

```bash
python backtest_analyzer.py DECK --multiple --period 30 --interval 7
```

**ตัวอย่างผลลัพธ์:**
```
============================================================
📈 AGGREGATE BACKTEST STATISTICS
============================================================
Total Tests: 4
Recommendation Accuracy: 3/4 (75.0%)
Win Rate: 3/4 (75.0%)
Loss Rate: 1/4 (25.0%)
Average Return: +2.35%
TP Hit Rate: 2/4 (50.0%)
SL Hit Rate: 1/4 (25.0%)
============================================================
```

---

## 📊 Parameters

```bash
python backtest_analyzer.py <SYMBOL> [OPTIONS]
```

**Required:**
- `SYMBOL` - รหัสหุ้น (เช่น AAPL, TSLA, DECK)

**Optional:**
- `--days-back N` - ย้อนหลังกี่วัน (default: 7)
- `--multiple` - ทดสอบหลายครั้ง
- `--period N` - ระยะเวลาที่ต้องการทดสอบ (default: 30 วัน)
- `--interval N` - ช่วงห่างระหว่างการทดสอบ (default: 7 วัน)
- `--horizon` - ระยะเวลาลงทุน: short/medium/long (default: short)

---

## 📈 ตัวอย่างการใช้งาน

### 1. ทดสอบหุ้น DECK ย้อนหลัง 1 สัปดาห์

```bash
python backtest_analyzer.py DECK --days-back 7 --horizon short
```

### 2. ทดสอบหุ้น AAPL ย้อนหลัง 2 สัปดาห์

```bash
python backtest_analyzer.py AAPL --days-back 14
```

### 3. ทดสอบหุ้น TSLA ย้อนหลัง 60 วัน ทุกๆ 5 วัน

```bash
python backtest_analyzer.py TSLA --multiple --period 60 --interval 5
```

### 4. ทดสอบหุ้น NVDA ระยะกลาง (medium-term)

```bash
python backtest_analyzer.py NVDA --multiple --period 90 --interval 10 --horizon medium
```

---

## 🎯 Evaluation Criteria

ระบบจะประเมินว่า **คำแนะนำถูกต้อง** ตามเงื่อนไขนี้:

| Recommendation | ถือว่าถูกเมื่อ |
|---|---|
| **STRONG BUY / BUY** | Return > 0% (ราคาขึ้น) |
| **HOLD** | \|Return\| < 2% (ไซด์เวย์) |
| **SELL / AVOID** | Return ≤ 0% (ราคาลง หรือหลีกเลี่ยงได้) |

**Outcome Types:**
- `WIN` 🎯 - TP hit (กำไรเต็มตามเป้า)
- `LOSS` ❌ - SL hit (ขาดทุนตาม SL)
- `SMALL_WIN` 📈 - ไม่โดน TP แต่กำไร
- `SMALL_LOSS` 📉 - ไม่โดน SL แต่ขาดทุน
- `NEUTRAL` ➖ - ไซด์เวย์

---

## 📊 Metrics Explained

### 1. **Recommendation Accuracy**
```
ถูกต้อง / ทั้งหมด (%)
```
เปอร์เซ็นต์ที่คำแนะนำ (BUY/SELL/HOLD) ตรงกับผลลัพธ์จริง

### 2. **Win Rate**
```
ชนะ / ทั้งหมด (%)
```
เปอร์เซ็นต์ที่ได้กำไร (return > 0%)

### 3. **Average Return**
```
เฉลี่ย Return ทั้งหมด (%)
```
ผลตอบแทนเฉลี่ยต่อ trade

### 4. **TP Hit Rate**
```
TP hit / ทั้งหมด (%)
```
เปอร์เซ็นต์ที่ Target Price ถูก hit

### 5. **SL Hit Rate**
```
SL hit / ทั้งหมด (%)
```
เปอร์เซ็นต์ที่ Stop Loss ถูก hit (ยิ่งต่ำยิ่งดี)

---

## ⚠️ ข้อจำกัด (Limitations)

1. **ข้อมูล Fundamental เก่า**
   - งบการเงินดึงจากปัจจุบัน ไม่ใช่ข้อมูลย้อนหลัง
   - อาจทำให้ผลลัพธ์ดีเกินจริงเล็กน้อย

2. **Slippage & Commission**
   - ไม่ได้คำนวณค่า commission
   - ไม่ได้คำนวณ slippage

3. **Market Hours**
   - ใช้ราคา Close ของวัน ไม่ใช่ราคาจริงเวลาเข้า

4. **Limited Historical Period**
   - ทดสอบได้แค่ข้อมูลที่มีอยู่ใน Yahoo Finance
   - ข้อมูลเก่ามากเกินไปอาจไม่แม่นยำ

---

## 💡 Best Practices

### 1. **เริ่มจากระยะสั้นก่อน**
```bash
# ทดสอบ 1-2 สัปดาห์ก่อน
python backtest_analyzer.py AAPL --days-back 7
python backtest_analyzer.py AAPL --days-back 14
```

### 2. **ทดสอบหลายหุ้น**
```bash
# ทดสอบหลายหุ้นในอุตสาหกรรมเดียวกัน
python backtest_analyzer.py AAPL --multiple --period 30
python backtest_analyzer.py MSFT --multiple --period 30
python backtest_analyzer.py GOOGL --multiple --period 30
```

### 3. **ทดสอบหลาย Time Horizon**
```bash
# Short-term (1-14 วัน)
python backtest_analyzer.py DECK --multiple --period 30 --interval 5 --horizon short

# Medium-term (15-90 วัน)
python backtest_analyzer.py DECK --multiple --period 90 --interval 10 --horizon medium
```

### 4. **ดูทั้ง Win Rate และ Average Return**
- Win rate สูง ≠ กำไรสูง
- อาจชนะบ่อยแต่ได้น้อย, แพ้น้อยแต่เสียเยอะ
- ดูทั้ง 2 ตัวประกอบกัน

---

## 🎓 การตีความผลลัพธ์

### ✅ ระบบดี (Good System)
```
Recommendation Accuracy: ≥ 60%
Win Rate: ≥ 55%
Average Return: > 0%
TP Hit Rate: ≥ 40%
SL Hit Rate: ≤ 30%
```

### 🌟 ระบบดีมาก (Excellent System)
```
Recommendation Accuracy: ≥ 70%
Win Rate: ≥ 65%
Average Return: > +2%
TP Hit Rate: ≥ 50%
SL Hit Rate: ≤ 20%
```

### ⚠️ ระบบต้องปรับปรุง (Needs Improvement)
```
Recommendation Accuracy: < 50%
Win Rate: < 50%
Average Return: < 0%
TP Hit Rate: < 30%
SL Hit Rate: > 40%
```

---

## 📝 Example Output Breakdown

```
============================================================
📊 BACKTEST RESULTS SUMMARY
============================================================
Symbol: DECK                           ← หุ้นที่ทดสอบ
Analysis Date: 2024-11-07             ← วันที่วิเคราะห์ (ย้อนหลัง)
Recommendation: BUY                    ← คำแนะนำ
  Score: 7.2                          ← คะแนน (0-10)
  Confidence: MEDIUM                   ← ความมั่นใจ
------------------------------------------------------------
Entry Price: $82.75                    ← ราคาเข้า (ราคาวันนั้น)
Target Price: $89.53 (+8.19%)         ← เป้าหมาย
Stop Loss: $74.61 (-9.84%)            ← จุดตัดขาดทุน
R:R Ratio: 0.83                       ← Risk/Reward
------------------------------------------------------------
Actual Outcome: 🎯 WIN                 ← ผลลัพธ์จริง
Exit Price: $89.53 on 2024-11-14      ← ราคาออก (TP hit)
Return: +8.19%                         ← ผลตอบแทน
Max Gain: +10.50%                      ← กำไรสูงสุดระหว่างถือ
Max Loss: -2.30%                       ← ขาดทุนสูงสุดระหว่างถือ
Days Held: 7                           ← ถือกี่วัน
TP Hit: ✅ Yes                         ← เป้าหมายโดนไหม
SL Hit: ✅ No                          ← SL โดนไหม (No = ดี)
------------------------------------------------------------
Recommendation Correct: ✅ YES          ← คำแนะนำถูกไหม
============================================================
```

---

## 🔧 Troubleshooting

### ปัญหา: "No historical data found"
```bash
# ลองเปลี่ยนวันที่ย้อนหลังน้อยลง
python backtest_analyzer.py DECK --days-back 5
```

### ปัญหา: "Analysis failed"
```bash
# ตรวจสอบว่ารหัสหุ้นถูกต้อง
# ลองหุ้นอื่นดู
python backtest_analyzer.py AAPL --days-back 7
```

### ปัญหา: "Rate limit exceeded"
```bash
# รอสักครู่แล้วลองใหม่
# หรือเพิ่ม interval ระหว่างการทดสอบ
python backtest_analyzer.py DECK --multiple --period 30 --interval 10
```

---

## 📚 Next Steps

1. **Run Single Backtest First**
   ```bash
   python backtest_analyzer.py DECK --days-back 7
   ```

2. **If Results Look Good, Run Multiple**
   ```bash
   python backtest_analyzer.py DECK --multiple --period 30
   ```

3. **Compare Multiple Stocks**
   - Test different stocks in same sector
   - Compare win rates and average returns

4. **Test Different Time Horizons**
   - Short-term: --horizon short
   - Medium-term: --horizon medium
   - Long-term: --horizon long

5. **Analyze Results**
   - Note which stocks perform better
   - Note which time horizon works best
   - Identify patterns in failures

---

## 🎯 Goal

เป้าหมายคือให้ระบบมี:
- **Win Rate ≥ 60%** (ชนะมากกว่าแพ้)
- **Average Return > 0%** (กำไรเฉลี่ยเป็นบวก)
- **TP Hit Rate ≥ 40%** (เป้าหมายโดนพอสมควร)
- **SL Hit Rate ≤ 30%** (SL ไม่โดนบ่อย)

ถ้าได้ตามนี้ = **ระบบใช้งานได้จริง!** 🎉
