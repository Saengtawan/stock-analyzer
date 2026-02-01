# Smart Exit System v5.0 - Quick Guide

## Overview

Structure-Based Exit System ที่ใช้หลักการเทรดจริง:
- **100% Win Rate** ใน backtest 4 เดือน
- **+48.7% Total Return** (vs +32.9% Fixed)

---

## Exit Rules

### 1. Stop Loss (SL) - โครงสร้างพัง = ออก

```
SL = ต่ำกว่า Swing Low / Support 1%
Max SL = -8% (ไม่กว้างกว่านี้)
```

ตัวอย่าง:
- Swing Low: $95
- Support: $94
- SL = $93.06 (ต่ำกว่า $94 อีก 1%)

### 2. Take Profit (TP) - Scale Out

```
TP1 = R:R 1:2 → ขาย 50%
TP2 = R:R 1:3 หรือ Resistance → ขายที่เหลือ
```

ตัวอย่าง (Entry $100, SL $95):
- Risk = $5
- TP1 = $100 + ($5 × 2) = $110 → ขาย 50%
- TP2 = $100 + ($5 × 3) = $115 → ขายที่เหลือ

### 3. Trailing Stop - ล็อคกำไร

```
หลัง TP1 hit:
- เลื่อน SL มา breakeven+1%
- อัพเดท SL ตาม Higher Low ใหม่
```

---

## วิธีใช้งาน

### 1. เริ่มต้น Portfolio Manager

```python
from portfolio_manager import PortfolioManager

pm = PortfolioManager(use_smart_exit=True)
```

### 2. เพิ่ม Position (พร้อมคำนวณ SL/TP อัตโนมัติ)

```python
pm.add_position(
    symbol='AAPL',
    entry_price=180.00,
    entry_date='2026-01-30',
    filters={'source': 'growth_catalyst'},
    amount=5000  # หรือใช้ risk-based sizing
)
```

Output:
```
✅ Added AAPL @ $180.00 (Smart Exit Mode)
   📍 SL: $172.00 (-4.4%)
   🎯 TP1: $196.00 (+8.9%) → ขาย 50%
   🎯 TP2: $204.00 (+13.3%) → ขายที่เหลือ
```

### 3. Risk-Based Position Sizing

```python
pm.add_position(
    symbol='AAPL',
    entry_price=180.00,
    entry_date='2026-01-30',
    filters={'source': 'growth_catalyst'},
    account_balance=100000,  # พอร์ต $100,000
    risk_pct=2.0  # เสี่ยง 2% = $2,000
)
```

### 4. ดูสถานะ

```python
pm.display_status()
```

### 5. Check Exit ทุกวัน

```python
# Check ว่าควร exit หรือไม่
results = pm.check_smart_exit()

# Execute exits
pm.execute_smart_exit(results)
```

---

## Position Size Calculator

```python
from smart_exit_rules import calculate_position_size

result = calculate_position_size(
    account_balance=100000,  # พอร์ต
    entry_price=50.00,       # ราคาซื้อ
    sl_price=47.50,          # Stop Loss
    risk_per_trade_pct=2.0   # เสี่ยง 2%
)

print(f"Shares: {result['shares']}")
print(f"Amount: ${result['amount']}")
```

---

## Backtest Results (Oct 2025 - Jan 2026)

| Strategy | Win Rate | Total Return | Avg Win |
|----------|----------|--------------|---------|
| Fixed (SL -6%, TP +5%) | 100% | +32.9% | +4.7% |
| **Structure-Based** | **100%** | **+48.7%** | **+7.0%** |

ตัวอย่าง Trades:
```
✅ AA     +10.2% (TP2 hit)
✅ NOV    +12.2% (Scale out)
✅ SBUX   +8.4%  (TP2 hit)
✅ CSCO   +5.5%  (MAX_HOLD)
```

---

## Checklist ก่อนซื้อ

- [ ] รู้ SL ก่อนซื้อ (จากโครงสร้างราคา)
- [ ] R:R >= 1:2
- [ ] เสี่ยงไม่เกิน 2% ต่อไม้
- [ ] SL อยู่ที่ "โครงสร้างพัง" (ใต้ Swing Low / Support)

---

## Files

- `src/smart_exit_rules.py` - Smart Exit Rules engine
- `src/portfolio_manager.py` - Portfolio Manager v5.0
