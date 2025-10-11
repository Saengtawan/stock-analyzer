# 📋 คู่มือการเพิ่ม Price Change Analysis UI

## 🎯 สรุป
ฟีเจอร์ **Price Change Analysis** ได้ถูกเพิ่มเข้าไปใน Backend แล้ว แต่ยัง**ไม่แสดงใน Frontend**

ข้อมูลอยู่ที่: `results.enhanced_analysis.price_change_analysis`

---

## 📍 ตำแหน่งที่ข้อมูลถูกส่งมา

### Backend (✅ เสร็จแล้ว)
- ไฟล์: `src/analysis/price_change_analyzer.py` (✅ สร้างแล้ว)
- ไฟล์: `src/analysis/enhanced_stock_analyzer.py` (✅ เพิ่ม price_change_analyzer แล้ว)
- API: `/api/analyze` ส่งข้อมูล `enhanced_analysis.price_change_analysis` แล้ว

### Frontend (❌ ยังไม่ทำ)
- ไฟล์: `src/web/templates/analyze.html` (ต้องแก้ไข)

---

## 🔧 วิธีการติดตั้ง

### ขั้นตอนที่ 1: เปิดไฟล์ `analyze.html`

```bash
nano /home/saengtawan/work/project/cc/stock-analyzer/src/web/templates/analyze.html
```

หรือใช้ text editor ที่ถนัด

---

### ขั้นตอนที่ 2: หาบรรทัดที่จะเพิ่มโค้ด

ค้นหาข้อความนี้ในไฟล์ (ประมาณบรรทัด 2608):

```html
<!-- Data Quality Summary -->
```

---

### ขั้นตอนที่ 3: เพิ่มโค้ด HTML

**วางโค้ดนี้ หลังจาก** `<!-- Data Quality Summary -->` (หลังบรรทัด 2608):

```html
<!-- Price Change Analysis Section (NEW!) -->
${priceChangeAnalysis && priceChangeAnalysis.direction ? `
    <div class="row mt-4">
        <div class="col-12">
            <h6 class="text-warning mb-3">
                <i class="fas fa-chart-line me-2"></i>
                📊 การวิเคราะห์การเปลี่ยนแปลงราคา (Price Change Analysis)
            </h6>

            <!-- Price Movement Summary -->
            <div class="card border-warning border-opacity-25 mb-3">
                <div class="card-header bg-warning bg-opacity-10">
                    <h6 class="mb-0">
                        ${priceChangeAnalysis.direction === 'UP' ? '📈' : priceChangeAnalysis.direction === 'DOWN' ? '📉' : '↔️'}
                        การเปลี่ยนแปลงราคา
                    </h6>
                </div>
                <div class="card-body">
                    <div class="row g-3">
                        <div class="col-md-4">
                            <small class="text-muted d-block">ราคาปัจจุบัน</small>
                            <span class="h4 text-primary">$${formatNumber(priceChangeAnalysis.current_price)}</span>
                        </div>
                        <div class="col-md-4">
                            <small class="text-muted d-block">ราคาก่อนหน้า</small>
                            <span class="h5 text-secondary">$${formatNumber(priceChangeAnalysis.previous_price)}</span>
                        </div>
                        <div class="col-md-4">
                            <small class="text-muted d-block">การเปลี่ยนแปลง</small>
                            <span class="h5 ${priceChangeAnalysis.change_percent >= 0 ? 'text-success' : 'text-danger'}">
                                ${priceChangeAnalysis.change_percent >= 0 ? '+' : ''}${formatNumber(priceChangeAnalysis.change_percent)}%
                                (${priceChangeAnalysis.change_percent >= 0 ? '+' : ''}$${formatNumber(priceChangeAnalysis.change_amount)})
                            </span>
                        </div>
                    </div>

                    ${priceChangeAnalysis.summary ? `
                        <div class="alert alert-info mt-3 mb-0">
                            <small><strong>สรุป:</strong> ${priceChangeAnalysis.summary}</small>
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- Reasons for Price Movement -->
            ${priceChangeAnalysis.reasons && priceChangeAnalysis.reasons.length > 0 ? `
                <div class="card border-info border-opacity-25 mb-3">
                    <div class="card-header bg-info bg-opacity-10">
                        <h6 class="mb-0">
                            🔍 ทำไมราคา${priceChangeAnalysis.direction === 'UP' ? 'ขึ้น' : priceChangeAnalysis.direction === 'DOWN' ? 'ลง' : 'ไม่เปลี่ยนแปลง'}?
                        </h6>
                    </div>
                    <div class="card-body">
                        ${priceChangeAnalysis.reasons.slice(0, 5).map((reason, index) => {
                            const stars = '⭐'.repeat(Math.min(Math.ceil(reason.importance / 20), 5));
                            return `
                                <div class="alert alert-light border-start border-primary border-3 mb-2">
                                    <div class="d-flex justify-content-between align-items-start">
                                        <div>
                                            <strong>${index + 1}. ${reason.reason}</strong> ${stars}
                                            <p class="mb-0 mt-1"><small class="text-muted">📌 ${reason.detail}</small></p>
                                        </div>
                                        <span class="badge bg-primary">${reason.importance}</span>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            ` : ''}

            <!-- Profit Taking Analysis (ควรขายกำไรหรือยัง?) -->
            ${priceChangeAnalysis.profit_taking_analysis && priceChangeAnalysis.profit_taking_analysis.applicable ? `
                <div class="card border-success border-opacity-25 mb-3">
                    <div class="card-header bg-success bg-opacity-10">
                        <h6 class="mb-0">💡 ควรขายกำไรหรือยัง?</h6>
                    </div>
                    <div class="card-body">
                        <!-- Recommendation Badge -->
                        <div class="text-center mb-3">
                            <span class="badge ${priceChangeAnalysis.profit_taking_analysis.confidence === 'HIGH' ? 'bg-success' : priceChangeAnalysis.profit_taking_analysis.confidence === 'MEDIUM' ? 'bg-warning' : 'bg-secondary'} fs-6 px-4 py-2">
                                ${priceChangeAnalysis.profit_taking_analysis.confidence === 'HIGH' ? '🟢' : priceChangeAnalysis.profit_taking_analysis.confidence === 'MEDIUM' ? '🟡' : '🔴'}
                                ${priceChangeAnalysis.profit_taking_analysis.action}
                            </span>
                            <p class="text-muted mt-2 mb-0">
                                <small>ความมั่นใจ: ${priceChangeAnalysis.profit_taking_analysis.confidence}</small>
                            </p>
                        </div>

                        <!-- Probability Progress Bars -->
                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <small class="text-muted d-block mb-1">💎 โอกาสที่ควรถือต่อ</small>
                                <div class="progress" style="height: 25px;">
                                    <div class="progress-bar bg-primary" role="progressbar"
                                         style="width: ${priceChangeAnalysis.profit_taking_analysis.hold_probability}%">
                                        ${formatNumber(priceChangeAnalysis.profit_taking_analysis.hold_probability)}%
                                    </div>
                                </div>
                            </div>
                            <div class="col-6">
                                <small class="text-muted d-block mb-1">💰 โอกาสที่ควรขายกำไร</small>
                                <div class="progress" style="height: 25px;">
                                    <div class="progress-bar bg-warning" role="progressbar"
                                         style="width: ${priceChangeAnalysis.profit_taking_analysis.sell_probability}%">
                                        ${formatNumber(priceChangeAnalysis.profit_taking_analysis.sell_probability)}%
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Reasons to Hold -->
                        ${priceChangeAnalysis.profit_taking_analysis.reasons_to_hold && priceChangeAnalysis.profit_taking_analysis.reasons_to_hold.length > 0 ? `
                            <div class="mb-3">
                                <h6 class="text-success mb-2">✅ เหตุผลที่ควรถือต่อ:</h6>
                                ${priceChangeAnalysis.profit_taking_analysis.reasons_to_hold.map((reason, index) => `
                                    <div class="alert alert-success border-success py-2 mb-2">
                                        <small>
                                            <strong>${index + 1}. ${reason.reason}</strong><br>
                                            <span class="text-muted">📝 ${reason.detail}</span>
                                        </small>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}

                        <!-- Reasons to Sell -->
                        ${priceChangeAnalysis.profit_taking_analysis.reasons_to_sell && priceChangeAnalysis.profit_taking_analysis.reasons_to_sell.length > 0 ? `
                            <div class="mb-3">
                                <h6 class="text-warning mb-2">⚠️ เหตุผลที่ควรขายกำไร:</h6>
                                ${priceChangeAnalysis.profit_taking_analysis.reasons_to_sell.map((reason, index) => `
                                    <div class="alert alert-warning border-warning py-2 mb-2">
                                        <small>
                                            <strong>${index + 1}. ${reason.reason}</strong><br>
                                            <span class="text-muted">📝 ${reason.detail}</span>
                                        </small>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            ` : ''}
        </div>
    </div>
` : ''}
```

---

### ขั้นตอนที่ 4: เพิ่ม JavaScript Variable

ค้นหาฟังก์ชันที่สร้าง HTML template (มักจะอยู่ในส่วน JavaScript ด้านล่าง)

เพิ่มบรรทัดนี้ในส่วนที่ประกาศตัวแปร:

```javascript
// เพิ่มบรรทัดนี้ใน function ที่สร้าง template
const priceChangeAnalysis = data?.enhanced_analysis?.price_change_analysis || null;
```

**หรือ** ถ้าใช้ template string แบบ inline ให้แก้จาก:

```javascript
const yahooData = data?.yahoo_data || {};
const secEdgarData = data?.sec_edgar_data || {};
const aiAnalysis = data?.ai_analysis || {};
```

เป็น:

```javascript
const yahooData = data?.yahoo_data || {};
const secEdgarData = data?.sec_edgar_data || {};
const aiAnalysis = data?.ai_analysis || {};
const priceChangeAnalysis = data?.enhanced_analysis?.price_change_analysis || null; // เพิ่มบรรทัดนี้
```

---

### ขั้นตอนที่ 5: รีสตาร์ท Web Server

```bash
# หยุด server ที่กำลังรันอยู่ (Ctrl+C)

# รัน server ใหม่
cd /home/saengtawan/work/project/cc/stock-analyzer
python3 src/web/app.py
```

หรือถ้าใช้ systemd:

```bash
sudo systemctl restart stock-analyzer
```

---

## 🎨 ตัวอย่างผลลัพธ์ที่จะได้

เมื่อเพิ่มเรียบร้อย หน้าวิเคราะห์หุ้นจะแสดง:

```
┌─────────────────────────────────────────────────────────┐
│ 📊 การวิเคราะห์การเปลี่ยนแปลงราคา                      │
├─────────────────────────────────────────────────────────┤
│ 📈 การเปลี่ยนแปลงราคา                                  │
│                                                         │
│ ราคาปัจจุบัน: $14.86                                   │
│ ราคาก่อนหน้า: $14.34                                   │
│ การเปลี่ยนแปลง: +3.62% (+$0.52)                        │
│                                                         │
│ สรุป: 📈 ราคาขึ้น 3.62% เนื่องจากแรงซื้อเพิ่มขึ้น...  │
├─────────────────────────────────────────────────────────┤
│ 🔍 ทำไมราคาขึ้น?                                      │
│                                                         │
│ 1. แรงซื้อเพิ่มขึ้นอย่างมาก ⭐⭐⭐⭐⭐               │
│    📌 ปริมาณซื้อขายเพิ่ม 52% พบแรงซื้อแข็งแกร่ง       │
│                                                         │
│ 2. สัญญาณซื้อจาก MACD ⭐⭐⭐⭐                        │
│    📌 MACD ตัดเส้น Signal แสดงแนวโน้มขาขึ้น            │
├─────────────────────────────────────────────────────────┤
│ 💡 ควรขายกำไรหรือยัง?                                 │
│                                                         │
│ 🟡 📊 ควรขายบางส่วนเพื่อลดความเสี่ยง                  │
│    ความมั่นใจ: MEDIUM                                   │
│                                                         │
│ 💎 โอกาสถือต่อ: [████████░░] 45.2%                    │
│ 💰 โอกาสขายกำไร: [█████████░] 54.8%                   │
│                                                         │
│ ⚠️ เหตุผลที่ควรขายกำไร:                               │
│ • RSI อยู่ใน Overbought (72.77)                        │
│ • ราคาเข้าใกล้แนวต้าน $15.21                           │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ การตรวจสอบว่าทำงานหรือไม่

1. เปิดเว็บไซต์: `http://localhost:5002/analyze`
2. ใส่ชื่อหุ้น เช่น `PATH` หรือ `AAPL`
3. กดปุ่ม "วิเคราะห์"
4. เลื่อนลงมาหาส่วน **"📊 การวิเคราะห์การเปลี่ยนแปลงราคา"**

ถ้าเห็นแสดงว่าสำเร็จ! 🎉

---

## 🐛 การแก้ปัญหา

### ปัญหา: ไม่แสดงข้อมูล

1. เปิด Browser Console (F12)
2. ดูว่ามี error หรือไม่
3. ตรวจสอบว่า API ส่งข้อมูลมาหรือไม่:
   ```javascript
   console.log(data.enhanced_analysis.price_change_analysis);
   ```

### ปัญหา: ข้อมูลเป็น undefined

- ตรวจสอบว่าประกาศตัวแปร `priceChangeAnalysis` แล้วหรือยัง
- ตรวจสอบว่า path ถูกต้อง: `data?.enhanced_analysis?.price_change_analysis`

---

## 📞 ติดต่อ

หากมีปัญหาหรือข้อสงสัย สามารถตรวจสอบได้ที่:
- Log file: `/var/log/stock-analyzer/app.log`
- Backend: `src/analysis/price_change_analyzer.py`
- API: `http://localhost:5002/api/analyze` (POST)

---

**เอกสารนี้สร้างโดย Claude Code** 🤖
