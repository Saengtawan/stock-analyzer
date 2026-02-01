# Strategy C: Early Exit + Reinvest

## ผลลัพธ์ Backtest

| กลยุทธ์ | Total Return | Win Rate | คำอธิบาย |
|---------|-------------|----------|----------|
| A: ถือจนจบ | +129.1% | 60.8% | รอ stop loss -7% |
| B: ขายเร็ว | +121.5% | 51.0% | ขายที่ -3% แล้วไม่ทำอะไร |
| **C: ขายเร็ว + ซื้อใหม่** | **+181.8%** | **84.3%** | 🏆 **ดีที่สุด!** |

## หลักการ

1. **ถ้าหุ้น dip ≥3% ใน 3 วันแรก → ขายทันที**
   - 71% ของหุ้นที่ dip แรกยังคงขาดทุนต่อ
   - ขายเร็วช่วยลด loss จาก -7% เป็น -3%

2. **ซื้อหุ้นใหม่ทันที**
   - ใช้เงินที่ได้จากการขายไปซื้อหุ้นตัวใหม่
   - หุ้นใหม่มีโอกาสกำไรมากกว่าหุ้นที่ dip

## การใช้งาน

### Daily Check (ตรวจทุกวัน)

```python
from portfolio_manager import PortfolioManager

pm = PortfolioManager('portfolio.json')

# ตรวจสอบ portfolio
results = pm.strategy_c_daily_check(confirm=False)  # Dry run

# ถ้าพร้อมขายจริง
results = pm.strategy_c_daily_check(confirm=True)

# ถ้า reinvest_signal = True → หาหุ้นใหม่!
if results.get('reinvest_signal'):
    print("🔄 ถึงเวลาหาหุ้นใหม่!")
```

### Manual Check

```python
# เช็ค stop loss แบบ manual
results = pm.check_stop_loss(
    hard_stop_pct=-7.0,      # Stop loss ปกติ
    early_dip_pct=-3.0,      # Early dip threshold
    early_dip_days=3,        # ตรวจใน 3 วันแรก
    enable_early_dip=True    # เปิดใช้ Strategy C
)

# ดู results
print(f"Early Dip Exit: {len(results['early_dip_exit'])} positions")
print(f"Stop Loss: {len(results['sell_now'])} positions")
print(f"Warning: {len(results['warning'])} positions")
print(f"OK: {len(results['ok'])} positions")
```

## Exit Rules Priority

1. **🚀 EARLY DIP EXIT** (Day 1-3, dip ≥3%)
   - ขายทันทีเมื่อ dip ≥3% ใน 3 วันแรก
   - ส่ง reinvest_signal = True

2. **🔴 HARD STOP** (-7%)
   - ขายทันทีเมื่อขาดทุน ≥7%

3. **📉 TRAILING STOP** (-5% from high)
   - ขายเมื่อราคาลงจากจุดสูงสุด 5%
   - ใช้เมื่อเคยกำไรแล้ว

4. **⏰ TIME STOP** (10 days, no profit)
   - ขายเมื่อถือ 10 วันแล้วยังไม่กำไร

5. **🟡 WARNING** (-3%)
   - แจ้งเตือนเมื่อขาดทุน 3%

## Workflow แนะนำ

```
ทุกวัน (ก่อนตลาดเปิด):
│
├─► pm.strategy_c_daily_check()
│   │
│   ├─► มี early_dip_exit?
│   │   └─► ขายทันที + รัน screener หาหุ้นใหม่
│   │
│   ├─► มี sell_now?
│   │   └─► ขายทันที
│   │
│   └─► ไม่มีอะไร
│       └─► ถือต่อ
│
└─► END
```

## Configuration

```python
# ปรับ parameters ได้
pm.check_stop_loss(
    hard_stop_pct=-7.0,      # -7% stop loss (default)
    warning_pct=-3.0,        # -3% warning (default)
    trailing_stop_pct=-5.0,  # -5% trailing (default)
    time_stop_days=10,       # 10 days (default)
    early_dip_pct=-3.0,      # -3% early dip (default)
    early_dip_days=3,        # 3 days (default)
    enable_early_dip=True    # เปิด Strategy C (default)
)
```

## สถิติ Strategy C

```python
# ดูสถิติ
stats = pm.get_strategy_c_stats()
print(f"Total Trades: {stats['total_trades']}")
print(f"Early Dip Exits: {stats['early_dip_exits']}")
print(f"Avg Loss Saved: {stats.get('early_exit_saved_vs_full_stop', 0):.1f}%")
```
