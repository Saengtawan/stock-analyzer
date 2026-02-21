# 🎨 UI Integration Guide - Alpaca Features v4.7

## วิธีการ Integrate UI เข้า Rapid Trader

---

## ขั้นตอนที่ 1: เพิ่ม Modal Components

### 1.1 Include Modal File ใน `rapid_trader.html`

แก้ไฟล์: `src/web/templates/rapid_trader.html`

เพิ่มก่อน `</body>` tag (บรรทัดท้ายสุดของไฟล์):

```html
<!-- Alpaca Analytics Modals (v4.7) -->
{% include 'rapid_analytics_modals.html' %}
</body>
```

---

## ขั้นตอนที่ 2: เพิ่มปุ่มเปิด Modals

### 2.1 เพิ่มปุ่มใน Header/Toolbar

หาส่วน `.hdr-controls` หรือ toolbar area แล้วเพิ่ม:

```html
<!-- Analytics Buttons -->
<div class="hdr-controls">
  <!-- Existing buttons... -->

  <!-- NEW: Analytics Buttons -->
  <button class="btn btn-sm btn-outline-light" data-bs-toggle="modal" data-bs-target="#performanceModal" title="Portfolio Performance">
    <i class="fas fa-chart-line"></i> Performance
  </button>

  <button class="btn btn-sm btn-outline-light" data-bs-toggle="modal" data-bs-target="#tradeLogModal" title="Trade Log">
    <i class="fas fa-history"></i> Trades
  </button>

  <button class="btn btn-sm btn-outline-light" data-bs-toggle="modal" data-bs-target="#calendarModal" title="Market Calendar">
    <i class="fas fa-calendar-alt"></i> Calendar
  </button>
</div>
```

### 2.2 หรือเพิ่มเป็น Dropdown Menu

```html
<!-- Analytics Dropdown -->
<div class="dropdown">
  <button class="btn btn-sm btn-outline-light dropdown-toggle" type="button" data-bs-toggle="dropdown">
    <i class="fas fa-chart-bar"></i> Analytics
  </button>
  <ul class="dropdown-menu">
    <li>
      <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#performanceModal">
        <i class="fas fa-chart-line"></i> Portfolio Performance
      </a>
    </li>
    <li>
      <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#tradeLogModal">
        <i class="fas fa-history"></i> Trade Log & Slippage
      </a>
    </li>
    <li>
      <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#calendarModal">
        <i class="fas fa-calendar-alt"></i> Market Calendar
      </a>
    </li>
  </ul>
</div>
```

---

## ขั้นตอนที่ 3: เพิ่ม Chart.js (ถ้ายังไม่มี)

### 3.1 เพิ่มใน `base.html` หรือ `rapid_trader.html`

ใน `<head>` section:

```html
<!-- Chart.js for Equity Curve -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

---

## ขั้นตอนที่ 4: Integrate Broker ใน Existing Code

### 4.1 แก้ `web/app.py` - Update Portfolio Endpoints

หาส่วนที่เรียก `RapidPortfolioManager()` และเพิ่ม broker:

**Before:**
```python
@app.route('/api/rapid/portfolio')
def api_rapid_portfolio():
    from rapid_portfolio_manager import RapidPortfolioManager
    manager = RapidPortfolioManager()  # No broker
    statuses = manager.check_all_positions()
```

**After:**
```python
@app.route('/api/rapid/portfolio')
def api_rapid_portfolio():
    from rapid_portfolio_manager import RapidPortfolioManager
    from engine.brokers import AlpacaBroker

    # Initialize broker
    broker = AlpacaBroker(paper=True)

    # Create manager with broker (faster!)
    manager = RapidPortfolioManager(broker=broker)

    # Use live data (17-76× faster)
    statuses = manager.check_all_positions_live()  # ← Changed!
```

### 4.2 Update All RapidPortfolioManager Calls

ค้นหาทุกที่ที่มี `RapidPortfolioManager()` ใน `web/app.py`:

```bash
grep -n "RapidPortfolioManager()" src/web/app.py
```

แก้แต่ละจุด:

```python
# Pattern to find and replace:
# OLD: manager = RapidPortfolioManager()
# NEW: broker = AlpacaBroker(paper=True)
#      manager = RapidPortfolioManager(broker=broker)
```

---

## ขั้นตอนที่ 5: Test UI

### 5.1 Start Web Server

```bash
cd src
python web/app.py
```

### 5.2 เปิด Browser

```
http://localhost:5000/rapid
```

### 5.3 ทดสอบแต่ละ Feature

1. คลิก "Performance" button
   - ✅ Modal เปิด
   - ✅ เห็น equity curve
   - ✅ Sharpe ratio, drawdown แสดงผล

2. คลิก "Trades" button
   - ✅ Modal เปิด
   - ✅ เห็น fills list
   - ✅ Slippage analysis แสดงผล

3. คลิก "Calendar" button
   - ✅ Modal เปิด
   - ✅ เห็น schedule 14 วัน
   - ✅ Holiday warnings แสดงผล

---

## ขั้นตอนที่ 6: เพิ่ม Real-time Badge (Optional)

### 6.1 เพิ่ม Badge แสดงว่าใช้ Real-time Data

ในส่วน Portfolio Summary:

```html
<div class="card-header">
  <strong>Portfolio</strong>
  <!-- NEW: Real-time badge -->
  <span class="badge bg-danger realtime-badge">
    <i class="fas fa-circle"></i> LIVE
  </span>
</div>
```

CSS:
```css
.realtime-badge {
  font-size: 0.7rem;
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

---

## ขั้นตอนที่ 7: Update Existing Portfolio Display

### 7.1 แสดง Data Source

เพิ่มข้อความแสดงว่าข้อมูลมาจาก Alpaca:

```html
<!-- Portfolio Card Footer -->
<div class="card-footer text-muted small">
  <i class="fas fa-bolt text-warning"></i>
  Real-time data via Alpaca
  (17-76× faster than delayed data)
</div>
```

---

## ตัวอย่าง Full Integration

### ไฟล์: `rapid_trader.html` (แก้เฉพาะส่วนที่เกี่ยวข้อง)

```html
<!DOCTYPE html>
<html>
<head>
  <!-- Existing head content... -->

  <!-- ADD: Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>
  <!-- Existing header... -->

  <div class="header-bar">
    <div class="hdr-row hdr-row-1">
      <!-- Existing controls... -->

      <!-- ADD: Analytics Buttons -->
      <div class="hdr-controls">
        <button class="btn btn-sm btn-outline-light"
                data-bs-toggle="modal"
                data-bs-target="#performanceModal">
          <i class="fas fa-chart-line"></i>
        </button>
        <button class="btn btn-sm btn-outline-light"
                data-bs-toggle="modal"
                data-bs-target="#tradeLogModal">
          <i class="fas fa-history"></i>
        </button>
        <button class="btn btn-sm btn-outline-light"
                data-bs-toggle="modal"
                data-bs-target="#calendarModal">
          <i class="fas fa-calendar-alt"></i>
        </button>
      </div>
    </div>
  </div>

  <!-- Existing content... -->

  <!-- ADD: Include Modals (before </body>) -->
  {% include 'rapid_analytics_modals.html' %}
</body>
</html>
```

---

## Troubleshooting

### ปัญหา: Modals ไม่เปิด

**สาเหตุ:** Bootstrap JS ยังไม่โหลด

**แก้:** ตรวจสอบว่ามี Bootstrap 5.x ใน `base.html`:

```html
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
```

### ปัญหา: Chart ไม่แสดง

**สาเหตุ:** Chart.js ยังไม่โหลด

**แก้:** เพิ่ม Chart.js ใน `<head>`:

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

### ปัญหา: API Error "Alpaca API key required"

**สาเหตุ:** ไม่มี API keys ใน environment

**แก้:**
```bash
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"
```

### ปัญหา: Data ยังช้าเหมือนเดิม

**สาเหตุ:** ยังไม่ได้ส่ง `broker` ให้ RapidPortfolioManager

**แก้:** ตรวจสอบว่าทุก endpoint ส่ง broker parameter:

```python
manager = RapidPortfolioManager(broker=broker)  # ← ต้องมี!
```

---

## Summary Checklist

### ✅ Files to Modify:
- [x] `src/web/templates/rapid_trader.html` - เพิ่มปุ่มและ include modals
- [x] `src/web/templates/base.html` - เพิ่ม Chart.js (ถ้ายังไม่มี)
- [x] `src/web/app.py` - แก้ทุก RapidPortfolioManager() ให้ส่ง broker

### ✅ New Files Created:
- [x] `src/web/templates/rapid_analytics_modals.html` - Modal components

### ✅ Features to Test:
- [ ] Performance modal เปิดได้
- [ ] Equity curve แสดงผล
- [ ] Trade log แสดง fills
- [ ] Slippage analysis ถูกต้อง
- [ ] Calendar แสดง holidays
- [ ] Tomorrow status ถูกต้อง

---

## Next Steps

1. **แก้ `rapid_trader.html`** - เพิ่มปุ่มและ include modals
2. **แก้ `web/app.py`** - Update RapidPortfolioManager calls
3. **Test UI** - ทดสอบแต่ละ modal
4. **Deploy** - พร้อมใช้งาน!

---

**ทุกอย่างพร้อมแล้ว! แค่แก้ 2 ไฟล์ก็ใช้งานได้เลย** 🚀
