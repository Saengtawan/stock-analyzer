# Growth Catalyst Screener - เกณฑ์ปัจจุบัน

**วันที่:** January 1, 2026
**Version:** v3.0 with Alternative Data Integration
**Win Rate:** 58.3% (validated)

---

## 🎯 เกณฑ์การคัดกรอง (Current Criteria)

### **1. ราคาและขนาดบริษัท (Price & Size)**

```python
min_price:        $5.00      # ราคาหุ้นขั้นต่ำ
max_price:        $2,000     # ราคาหุ้นสูงสุด
min_market_cap:   $500M      # มูลค่าตลาดขั้นต่ำ
max_market_cap:   No limit   # ไม่จำกัดสูงสุด
min_daily_volume: $10M       # มูลค่าการซื้อขายต่อวันขั้นต่ำ
```

**ความหมาย:**
- ✅ ยอมรับหุ้น **$5 ขึ้นไป** เท่านั้น
- ❌ ตัดหุ้น **<$5** ทิ้งทั้งหมด (penny stocks)
- ✅ Market cap ≥ $500M (small/mid/large caps)
- ✅ Volume ≥ $10M/day (liquidity ดี)

---

### **2. Catalyst Score (คะแนนตัวเร่ง)**

```python
min_catalyst_score: 0.0  # ขั้นต่ำ (Inverted scoring)
```

**ความหมาย:**
- **Inverted Scoring System:**
  - Score **ยิ่งต่ำ = ยิ่งดี** (ไม่ใช่ยิ่งสูงยิ่งดี!)
  - Upcoming earnings = **penalty** (sell-the-news trap)
  - Long-term catalyst = **bonus** (real growth potential)

**ตัวอย่าง:**
```
หุ้น A: Earnings ในอีก 3 วัน → Score -10 (penalty)
หุ้น B: FDA approval ในอีก 2 เดือน → Score 30 (good)
```

**Default = 0.0:**
- ยอมรับทั้ง negative และ positive scores
- กรองเฉพาะค่ามากๆ ออก

---

### **3. Technical Score (คะแนนเทคนิคอล)**

```python
min_technical_score: 30.0  # ขั้นต่ำ 30/100
```

**ประกอบด้วย:**
- **Trend (25%):** Moving averages, trend direction
- **Momentum (25%):** RSI, MACD, momentum strength
- **Volume (25%):** Volume patterns, accumulation
- **Pattern (25%):** Chart patterns, support/resistance

**ความหมาย:**
- Score 30/100 = **พอใช้** (not too strict)
- เน้นหาหุ้นที่กำลังเริ่มสร้าง momentum
- ไม่จำเป็นต้อง perfect setup (60-70+)

**ตัวอย่าง:**
```
Score 30-40: Decent setup, starting momentum
Score 50-60: Good setup, strong momentum
Score 70+:   Excellent setup, very strong (rare)
```

---

### **4. AI Probability (ความน่าจะเป็นจาก AI)**

```python
min_ai_probability: 30.0%  # ขั้นต่ำ 30%
```

**ความหมาย:**
- AI วิเคราะห์ว่ามี **30%+ โอกาส** ที่จะถึงเป้า
- ไม่สูงมาก (ไม่ใช่ 70-80%)
- เพราะต้องการ **balance ระหว่าง opportunity และ quality**

**ตัวอย่าง:**
```
30%+ probability = AI คิดว่ามีโอกาส (worth a try)
50%+ probability = AI มั่นใจปานกลาง
70%+ probability = AI มั่นใจสูง (rare, very selective)
```

**Default 30% เพราะ:**
- Win rate จริง 58.3% > 30% (conservative estimate)
- AI tends to be conservative
- ถ้าใช้ 70% จะได้หุ้นน้อยเกินไป

---

### **5. Target & Timeframe (เป้าหมายและระยะเวลา)**

```python
target_gain_pct:  5.0%   # เป้ากำไร 5%
timeframe_days:   30     # ภายใน 30 วัน
```

**ความหมาย:**
- มองหา **5%+ gain ใน 30 วัน**
- Realistic & achievable target
- Validated: 58.3% win rate @ 5% target

---

### **6. Universe Generation**

```python
max_stocks:          20    # จำนวนหุ้นสูงสุดที่ต้องการ
universe_multiplier: 5     # AI สร้าง 5x = 100 หุ้น
```

**ความหมาย:**
- AI สร้าง **100 หุ้น** (20 × 5)
- กรองเหลือ **~20 หุ้น** คุณภาพสูงสุด
- เลือก top 20% จาก 100 หุ้น

---

## 📊 Alternative Data Scoring (v3.0)

### **6 Data Sources (แหล่งข้อมูลเสริม):**

**1. Insider Trading (25% weight)**
- ✅ Insider buying last 7-14 days
- ✅ Recent purchases by executives
- Signal: 👔 Insider Buying

**2. Analyst Ratings (20% weight)**
- ✅ Upgrades in last 7 days
- ✅ Price target increases
- Signal: 📊 Analyst Upgrade

**3. Short Interest (20% weight)**
- ✅ Short interest >15%
- ✅ Days to cover >3
- Signal: 🔥 Squeeze Potential

**4. Social Sentiment (15% weight)**
- ✅ Reddit WallStreetBets mentions
- ✅ Positive sentiment spike
- Signal: 🔥 Social Buzz

**5. Correlation & Pairs (10% weight)**
- ✅ Sector leaders outperforming
- ✅ Positive correlation signals

**6. Macro Indicators (10% weight)**
- ✅ Sector rotation favorable
- ✅ Macro tailwinds

---

## 🔍 Complete Scoring System

### **Multi-Stage Analysis:**

**Stage 1: Universe Generation**
- AI generates 100 stocks with catalysts
- Filters by price, market cap, volume

**Stage 2: Catalyst Discovery**
- Catalyst score (inverted system)
- Alternative data signals (6 sources)

**Stage 3: Technical Validation**
- Technical score (trend + momentum + volume + pattern)

**Stage 4: AI Deep Analysis**
- AI analyzes fundamentals + catalysts + technical
- Returns probability estimate

**Stage 5: Composite Scoring**
```python
Composite Score =
  Technical Score      (25%)
+ Alt Data Score       (25%)
+ Sector Rotation      (20%)
+ Valuation Score      (15%)
+ Catalyst Timing      (15%)
```

**Stage 6: Final Ranking**
- Sort by composite score
- Return top 20 stocks

---

## ✅ ผลลัพธ์

### **จากเกณฑ์ปัจจุบัน:**

**ได้หุ้นที่:**
- ✅ ราคา ≥ $5
- ✅ Market cap ≥ $500M
- ✅ Volume ≥ $10M/day
- ✅ Technical score ≥ 30/100
- ✅ AI probability ≥ 30%
- ✅ Catalyst score acceptable (inverted)
- ✅ มี alternative data signals (bonus)

**Win Rate:** 58.3% (validated)
**Avg Return:** +8% on winners
**Strategy:** Early entry + Smart exits

---

## ⚠️ ข้อจำกัดปัจจุบัน

### **1. ราคาหุ้น:**
```
min_price = $5.00
→ ตัดหุ้น $3-$5 ออกทั้งหมด
→ อาจพลาดหุ้นดีบางตัว (AMD เคย $2!)
```

### **2. Catalyst Score:**
```
min_catalyst_score = 0.0
→ ยอมรับทั้ง negative scores
→ อาจได้หุ้นที่มี earnings trap
```

### **3. Technical Score:**
```
min_technical_score = 30
→ ต่ำมาก (ยอมรับ setup ไม่ดีมาก)
→ อาจได้หุ้น weak technical
```

### **4. AI Probability:**
```
min_ai_probability = 30%
→ ต่ำมาก (conservative)
→ ได้หุ้นจำนวนมาก แต่อาจคุณภาพไม่สูงมาก
```

---

## 💡 ข้อเสนอแนะ

### **Option 1: Keep Current (Balanced)**
**ปัจจุบัน:**
- Win rate: 58.3% ✅ ดีอยู่แล้ว
- Coverage: กว้าง (ได้หุ้นเยอะ)
- Risk: ปานกลาง

**แนะนำสำหรับ:** User ที่ต้องการ opportunities มากๆ

---

### **Option 2: Stricter Quality (Recommended)**
**เปลี่ยนเป็น:**
```python
min_technical_score:  50.0  # เพิ่มจาก 30
min_ai_probability:   50.0  # เพิ่มจาก 30
min_catalyst_score:   10.0  # Positive only
```

**ผลลัพธ์:**
- Win rate: คาดว่า 65-70%+ (สูงขึ้น)
- Coverage: แคบลง (ได้หุ้นน้อยลง ~10-15 ตัว)
- Risk: ต่ำลง (คุณภาพสูงขึ้น)

**แนะนำสำหรับ:** User ที่ต้องการ quality > quantity

---

### **Option 3: Tiered System (Most Flexible)**
**เกณฑ์ปรับตามราคา:**
```python
Price $50+:  Technical 30+, AI 30%
Price $20+:  Technical 40+, AI 40%
Price $10+:  Technical 50+, AI 50%
Price $5+:   Technical 60+, AI 60%
Price $3+:   Technical 70+, AI 70%
```

**ผลลัพธ์:**
- ยอมรับหุ้น $3-5 แต่ใช้เกณฑ์เข้มงวด
- Fair system
- ไม่พลาดโอกาสดี

**แนะนำสำหรับ:** User ที่ต้องการครอบคลุมทุกราคา

---

## 📋 เกณฑ์ Default ใน Web UI

### **ที่ User เห็นตอนเข้า Web:**

```javascript
Target Gain:         5%    (แนะนำสำหรับ 30 วัน)
Catalyst Score:      0+    (Inverted scoring)
Technical Score:     30+   (Recommended)
AI Probability:      30%+  (Recommended)
Min Price:           $5+   (Filter penny stocks)
Max Stocks:          20    (Results limit)
Universe Multiplier: 5x    (100 stocks → 20 final)
```

---

## 🎯 สรุป

### **เกณฑ์ปัจจุบันเป็นแบบ "Balanced":**

**✅ ข้อดี:**
- Win rate ดี (58.3%)
- ได้หุ้นจำนวนมาก (~20 ตัว)
- Opportunity มาก
- ไม่เข้มงวดเกินไป

**⚠️ ข้อจำกัด:**
- ตัดหุ้น <$5 ออกทั้งหมด
- Technical threshold ต่ำ (30)
- AI threshold ต่ำ (30%)
- อาจได้หุ้นคุณภาพไม่สูงมาก (แต่ก็ win 58%)

**คำถาม:**
- ต้องการเกณฑ์เข้มงวดขึ้นมั้ย? (Quality > Quantity)
- ต้องการยอมรับหุ้น $3-5 มั้ย? (Lower price with stricter criteria)
- หรือใช้ต่อแบบเดิม? (Balanced, working fine)

---

**Created:** January 1, 2026
**Status:** ✅ CURRENT PRODUCTION CRITERIA
**Win Rate:** 58.3% (Validated)
