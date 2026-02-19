# Auto Trading Engine - Auto Start Setup

## ปัญหา:
**Auto Trading Engine ไม่ start อัตโนมัติ!**
- Gap Scanner จะไม่ทำงาน
- ต้อง run manual ทุกครั้ง
- ถ้าระบบรีบูต engine จะหยุด

---

## วิธีแก้: เลือก 1 ใน 3 วิธี

### 🥇 **Option 1: Systemd Service** (แนะนำ - Production)

**ข้อดี:**
- Start อัตโนมัติเมื่อบูต
- Auto-restart เมื่อ crash
- จัดการ logs อัตโนมัติ
- Control ง่าย (start/stop/status)

**Installation:**

```bash
# 1. Copy service file
sudo cp scripts/auto-trading.service /etc/systemd/system/

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Enable auto-start
sudo systemctl enable auto-trading

# 4. Start service
sudo systemctl start auto-trading

# 5. Check status
sudo systemctl status auto-trading
```

**Management:**

```bash
# Start
sudo systemctl start auto-trading

# Stop
sudo systemctl stop auto-trading

# Restart
sudo systemctl restart auto-trading

# Status
sudo systemctl status auto-trading

# Logs
sudo journalctl -u auto-trading -f

# Disable auto-start
sudo systemctl disable auto-trading
```

---

### 🥈 **Option 2: Startup Script** (แนะนำ - Development)

**ข้อดี:**
- ง่าย ไม่ต้อง sudo
- ควบคุมได้เอง
- ดี for testing

**Usage:**

```bash
# Make executable
chmod +x scripts/start_auto_trading.sh

# Start
./scripts/start_auto_trading.sh

# Stop
pkill -f auto_trading_engine.py

# Status
ps aux | grep auto_trading_engine

# Logs
tail -f logs/auto_trading_engine.log
```

**Auto-start on login:**

Add to `~/.bashrc` or `~/.profile`:

```bash
# Auto-start trading engine on login
if ! pgrep -f "auto_trading_engine.py" > /dev/null; then
    cd ~/work/project/cc/stock-analyzer
    ./scripts/start_auto_trading.sh
fi
```

---

### 🥉 **Option 3: Cron Job** (สำหรับ daily restart)

**ข้อดี:**
- Restart อัตโนมัติทุกวัน
- Ensure fresh start

**Setup:**

```bash
# Edit crontab
crontab -e

# Add these lines:

# Start at 5:30 AM ET every weekday (before market)
30 5 * * 1-5 cd /home/saengtawan/work/project/cc/stock-analyzer && ./scripts/start_auto_trading.sh

# Kill at 5:00 PM ET (after market close)
0 17 * * 1-5 pkill -f auto_trading_engine.py
```

**Note:** Requires script to handle "already running" check

---

## ✅ Verification

### 1. Check if running:
```bash
ps aux | grep auto_trading_engine.py
```

Expected output:
```
saengtawan  12345  python src/auto_trading_engine.py
```

### 2. Check logs:
```bash
tail -f logs/auto_trading_engine.log
```

Expected output:
```
06:00 AM: PreMarketGapScanner: Scanning 32 symbols...
06:15 AM: Found 1 gap signals
09:30 AM: Bought NVDA x10 @ $112.50
```

### 3. Check Gap Scanner:
```bash
grep "PreMarket Gap" logs/auto_trading_engine.log
```

Should see scans between 6:00 AM - 9:30 AM

---

## 🔧 Troubleshooting

### Engine won't start:

**Check Python environment:**
```bash
which python
python --version  # Should be 3.11+
```

**Check .env file:**
```bash
cat .env | grep ALPACA
# Should show API keys
```

**Check permissions:**
```bash
ls -la scripts/start_auto_trading.sh
# Should be executable (x)
```

### Engine crashes:

**Check error logs:**
```bash
tail -50 logs/auto_trading_engine_error.log
```

**Common issues:**
- Missing API keys → add to .env
- Database locked → kill other processes
- Network issues → check internet

### Gap Scanner not working:

**Check time:**
```bash
date
# Should be 6:00 AM - 9:30 AM ET for scanning
```

**Check logs:**
```bash
grep "PreMarket" logs/auto_trading_engine.log | tail -20
```

**Force scan (testing):**
```python
from screeners.premarket_gap_scanner import scan_premarket_gaps
signals = scan_premarket_gaps(min_confidence=80)
print(signals)
```

---

## 📊 Expected Behavior

### Daily Timeline:

```
05:30 AM ET  → Engine starts (systemd/cron)
06:00 AM     → Gap scanning begins
06:15 AM     → Gaps detected (if any)
09:30 AM     → Market opens → Buy orders executed
09:31-15:50  → Monitor positions
15:50 PM     → Pre-close check → Sell gap trades
16:00 PM     → Market closes
17:00 PM     → Engine stops (optional, via cron)
```

### Logs to monitor:

```bash
# Real-time monitoring
tail -f logs/auto_trading_engine.log | grep -E "Gap|PreMarket|Bought|Sold"

# Daily summary
grep -E "Gap Trade|GAP_TRADE_EOD" logs/auto_trading_engine.log
```

---

## 🚨 Important Notes

1. **Engine MUST be running for Gap Scanner to work**
   - Scanner is part of engine loop
   - No engine = no scanning = no trades

2. **Only ONE engine instance at a time**
   - Multiple instances = duplicate orders
   - Check before starting: `pgrep -f auto_trading_engine`

3. **Logs rotation**
   - Logs can get large
   - Enable log rotation in systemd
   - Or clean manually: `rm logs/*.log.old`

4. **Testing before production**
   - Test with ALPACA_PAPER=true first
   - Verify all trades in paper account
   - Switch to live only after 30+ days success

---

## 📝 Checklist

Before going live:

- [ ] Auto-start configured (systemd/cron/script)
- [ ] Verified engine starts on boot
- [ ] Tested gap scanner (found gaps in logs)
- [ ] Tested entry (bought at 9:30 AM)
- [ ] Tested exit (sold at 4:00 PM)
- [ ] API keys in .env (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- [ ] Paper trading tested (ALPACA_PAPER=true)
- [ ] Alerts working (Telegram/Discord/Email)
- [ ] Logs monitored daily
- [ ] Backup plan if system fails

---

**Version:** v6.11
**Status:** Setup Required
**Priority:** CRITICAL (Engine won't work without auto-start)
