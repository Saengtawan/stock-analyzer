# AUTO SERVICES - ครบทุกอย่าง

## ระบบทั้งหมด (รันครั้งเดียว auto หมด)

```bash
./scripts/run_all.sh
```

---

## ✅ ระบบที่รันอัตโนมัติ (COMPLETE LIST)

### 1. Auto Trading Engine (`auto_trading_engine.py`)

**หน้าที่:**
- 🔍 Pre-market Gap Scanner (6:00-9:30 AM ET)
- 📊 Rapid Rotation Scanner (ตลอดเวลาที่ตลาดเปิด)
- 🤖 Order Execution (ซื้อ/ขายอัตโนมัติ)
- 👁️ Position Monitoring (ติดตามหุ้นที่ถือ)

**Auto Jobs:**
```
06:00 AM - Pre-market gap scan starts
06:00-09:30 - Scan every 5 minutes
09:30 AM - Market open, execute gap trades
09:30-16:00 - Continuous monitoring & scanning
15:50 PM - Pre-close check
16:00 PM - Close all gap trades (same day exit)
```

---

### 2. Web App (`run_app.py`)

**หน้าที่:**
- 🌐 Web UI (http://localhost:5000)
- 📊 Portfolio Monitor
- 📡 Price Streamer
- 🏥 Health Checker
- 🧹 Universe Maintenance

**Auto Jobs:**

| Job | Frequency | Description |
|-----|-----------|-------------|
| Portfolio Monitor | Every 5 minutes | เช็คหุ้นที่ถือ, ตัดขาดทุน/เอากำไร auto |
| Price Streamer | Real-time | รับราคาแบบ real-time (WebSocket) |
| Health Checker | Every 5 minutes | เช็คระบบ, restart ถ้า thread ตาย |
| Universe Cleanup | Daily 2:00 AM | ลบหุ้นที่ delisted |

---

## 🎯 ทั้งหมดที่ AUTO (Complete Feature List)

### A. Gap Trading (Auto 100%)
- ✅ Scan pre-market gaps (6:00-9:30 AM)
- ✅ Calculate confidence score (80%+)
- ✅ Check rotation worthiness
- ✅ Buy at market open (9:30 AM)
- ✅ Sell at market close (4:00 PM same day)

### B. Rapid Rotation (Auto 100%)
- ✅ Scan for dip-bounce signals
- ✅ Check market regime (Bull/Bear)
- ✅ Check sector regime (Hot sectors)
- ✅ Score stocks (85+ required)
- ✅ Queue signals when positions full
- ✅ Execute orders automatically

### C. Portfolio Protection (Auto 100%)
- ✅ Monitor P&L every 5 minutes
- ✅ Auto-sell on CRITICAL signal (SL hit)
- ✅ Auto-sell on TAKE_PROFIT signal
- ✅ Trailing stop activation (+3%)
- ✅ Cancel SL/TP orders on exit

### D. Risk Management (Auto 100%)
- ✅ PDT Guard (prevent pattern day trader violation)
- ✅ Position sizing (ATR-based)
- ✅ Max positions limit (5)
- ✅ Max hold days (4 days)
- ✅ Gap filter (skip large gaps)
- ✅ Earnings filter (skip earnings week)

### E. Data Maintenance (Auto 100%)
- ✅ Universe cleanup daily 2:00 AM
- ✅ Remove delisted stocks
- ✅ Log rotation (10 MB, 7 days retention)
- ✅ Cache management

### F. Monitoring (Auto 100%)
- ✅ Health checks every 5 minutes
- ✅ Thread restart if dead
- ✅ Real-time price streaming
- ✅ Position sync check (Alpaca vs memory)
- ✅ Scan freshness check

---

## 📋 คำสั่งจัดการ

**รันทั้งหมด:**
```bash
./scripts/run_all.sh
```

**ดู Status:**
```bash
./scripts/status.sh
```

**หยุดทั้งหมด:**
```bash
./scripts/stop_all.sh
```

**ดู Logs:**
```bash
# Auto Trading Engine
tail -f logs/auto_trading_engine.log

# Web App
tail -f logs/web_app.log

# Gap Scanner only
tail -f logs/auto_trading_engine.log | grep -i "gap\|premarket"
```

---

## ⚠️ สิ่งที่ไม่มี (NOT INCLUDED)

❌ **Systemd / Boot Auto-Start**
- เอาออกแล้ว ตามคำสั่ง
- ต้องรัน `./scripts/run_all.sh` เองทุกครั้ง
- ไม่ start on boot

❌ **Cron Jobs**
- ไม่ใช้ crontab
- ทุกอย่าง auto จาก 2 processes หลัก
- Universe cleanup ทำผ่าน run_app.py scheduler

---

## 🔍 ตรวจสอบว่า Auto ครบทุกอย่าง

```bash
# 1. Check processes
./scripts/status.sh

# 2. Expected output:
# ✅ Auto Trading Engine - Running
# ✅ Web App - Running

# 3. Check auto jobs from logs
tail -20 logs/auto_trading_engine.log
tail -20 logs/web_app.log
```

---

## 🚀 Daily Flow (All Automatic)

```
02:00 AM - Universe cleanup
06:00 AM - Gap scanner wakes up
06:00-09:30 - Scan for gaps every 5 min
09:30 AM - Market open
          → Execute gap trades
          → Start rotation scanning
09:30-16:00 - Continuous monitoring
            → Portfolio check every 5 min
            → Price updates real-time
            → Auto sell on SL/TP hit
15:50 PM - Pre-close check
16:00 PM - Market close
         → Close all gap trades
         → Stop scanning
```

---

## ✅ CHECKLIST

**Before running:**
- [ ] .env file exists (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- [ ] ALPACA_PAPER=true (for paper trading)
- [ ] Python environment active (pyenv activate cc)

**After running:**
- [ ] Both processes running (./scripts/status.sh)
- [ ] Web UI accessible (http://localhost:5000)
- [ ] Logs showing activity (tail -f logs/*.log)
- [ ] No errors in logs

**Daily monitoring:**
- [ ] Check gap scanner logs (6:00-9:30 AM)
- [ ] Verify trades executed (9:30 AM)
- [ ] Monitor positions (Web UI)
- [ ] Check for alerts/errors

---

**Version:** v6.11
**Last Updated:** 2026-02-15
**Status:** ✅ Complete - All auto jobs running from 2 main processes
