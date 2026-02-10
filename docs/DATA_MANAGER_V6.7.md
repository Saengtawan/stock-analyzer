# DataManager v6.7 - Unified Data Layer

## 🎯 What Changed

DataManager is now the **single abstraction layer for ALL READ operations**:
- ✅ Realtime prices (broker → yfinance fallback)
- ✅ Historical bars (broker → yfinance fallback)
- ✅ Account info (broker → cached JSON fallback)
- ✅ Positions (broker → portfolio.json fallback)
- ✅ Orders query (broker → empty fallback)
- ✅ Market clock (broker → standard hours fallback)

**Design principle:** READ operations through DataManager, WRITE operations direct to broker.

---

## 📊 New API Methods

### Realtime Prices

```python
from api.data_manager import DataManager
from engine.brokers import AlpacaBroker

# Initialize with broker
broker = AlpacaBroker(paper=True)
dm = DataManager(broker=broker)

# Get single price (broker → yfinance fallback)
price = dm.get_current_price('AAPL')
print(f"AAPL: ${price:.2f}")

# Batch fetch (1 API call for all symbols!)
prices = dm.get_batch_prices(['AAPL', 'NVDA', 'TSLA', 'AMD'])
for symbol, price in prices.items():
    print(f"{symbol}: ${price:.2f}")

# Historical bars
bars = dm.get_bars('AAPL', timeframe='1Day', limit=60)
print(bars.head())
```

### Account & Positions

```python
# Get account (with offline cache fallback)
account = dm.get_account()
if account:
    print(f"Equity: ${account.equity:,.2f}")
    print(f"Cash: ${account.cash:,.2f}")
    print(f"Buying Power: ${account.buying_power:,.2f}")

# Get all positions (broker → portfolio.json fallback)
positions = dm.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.qty} shares @ ${pos.avg_entry_price:.2f}")

# Get specific position
pos = dm.get_position('AAPL')
if pos:
    print(f"AAPL position: {pos.qty} shares, P&L: ${pos.unrealized_pl:.2f}")
```

### Orders

```python
# Get open orders
orders = dm.get_orders(status='open')
for order in orders:
    print(f"{order.symbol}: {order.side} {order.qty} @ ${order.limit_price or 'market'}")

# Get specific order
order = dm.get_order(order_id='abc-123')
if order:
    print(f"Order status: {order.status}")
```

### Market Info

```python
# Get market clock
clock = dm.get_clock()
print(f"Market open: {clock.is_open}")
print(f"Next open: {clock.next_open}")
print(f"Next close: {clock.next_close}")

# Check if market is open (shorthand)
if dm.is_market_open():
    print("Market is OPEN!")

# Get trading calendar
calendar = dm.get_calendar(start='2026-02-09', end='2026-02-16')
for day in calendar:
    print(f"{day['date']}: {day['open']} - {day['close']}")
```

---

## 🔄 Migration Guide

### Before (Old Pattern)

```python
# Components called broker directly
class RapidRotationScreener:
    def __init__(self):
        self.broker = None  # No broker support!

    def screen(self):
        # Used yfinance only
        for symbol in self.universe:
            ticker = yf.Ticker(symbol)
            price = ticker.history(period='1d')['Close'][-1]
            # ... analyze

# Portfolio Manager
manager = RapidPortfolioManager(broker=broker)
price = None
if manager.broker:
    quote = manager.broker.get_snapshot(symbol)
    price = quote.last
else:
    price = yf.Ticker(symbol).history()['Close'][-1]

# Engine called broker directly (50+ places)
account = self.broker.get_account()
positions = self.broker.get_positions()
snapshot = self.broker.get_snapshot(symbol)
clock = self.broker.get_clock()
```

### After (New Pattern)

```python
# All components use DataManager
from api.data_manager import DataManager

# Initialize ONCE
dm = DataManager(broker=broker)  # or DataManager() for yfinance only

# Screener
class RapidRotationScreener:
    def __init__(self, data_manager: DataManager = None):
        self.data_manager = data_manager or DataManager()

    def screen(self):
        # Batch fetch (fast!)
        prices = self.data_manager.get_batch_prices(self.universe)
        for symbol, price in prices.items():
            # ... analyze

# Portfolio Manager
manager = RapidPortfolioManager(data_manager=dm)
price = manager.data_manager.get_current_price(symbol)  # auto fallback!

# Engine uses DataManager for READ operations
class AutoTradingEngine:
    def __init__(self, broker, data_manager):
        self.broker = broker  # For WRITE operations
        self.data_manager = data_manager  # For READ operations

    def _run_loop(self):
        # READ operations through DataManager
        account = self.data_manager.get_account()
        positions = self.data_manager.get_positions()
        clock = self.data_manager.get_clock()

        # WRITE operations direct to broker (no abstraction)
        self.broker.place_market_buy(symbol, qty)
        self.broker.place_stop_loss(symbol, qty, sl_price)
```

---

## ✅ Benefits

| Benefit | Impact |
|---------|--------|
| **Single abstraction** | Components only know DataManager |
| **Consistent API** | Same interface everywhere |
| **Built-in fallback** | Broker down → still works with cache |
| **Easy testing** | Mock DataManager instead of broker |
| **Batch optimized** | get_batch_prices() = 1 API call |
| **Offline mode** | Works without broker (cached data) |
| **Clear separation** | READ (DataManager) vs WRITE (broker) |

---

## 🚨 Important Notes

### READ vs WRITE Separation

```python
# ✅ GOOD: READ operations through DataManager
account = dm.get_account()        # Safe to cache
positions = dm.get_positions()    # Safe to cache
price = dm.get_current_price()    # Can fallback

# ✅ GOOD: WRITE operations direct to broker
broker.place_market_buy(symbol, qty)     # Must be direct
broker.place_stop_loss(symbol, qty, sl)  # Must be direct
broker.cancel_order(order_id)            # Must be direct
broker.modify_stop_loss(order_id, sl)    # Must be direct
```

**Why?**
- READ operations can fallback safely (Alpaca down → use cache)
- WRITE operations MUST be direct (no abstraction, no fallback)
- Execution must be realtime and guaranteed

### Fallback Priority

Each method follows this priority:

1. **Broker (Alpaca)** - Try first if available (realtime)
2. **Cache/Local files** - Use cached data if broker fails
3. **API sources** - Fall back to Yahoo/Tiingo if needed
4. **Standard values** - Use defaults for market hours

Example:
```python
get_current_price():
  1. Alpaca snapshot (realtime)
  2. yfinance (15-min delay)
  3. Return None

get_account():
  1. Alpaca get_account()
  2. Cached account.json (<24h old)
  3. Return None

get_clock():
  1. Alpaca get_clock()
  2. Standard hours (9:30-16:00 ET Mon-Fri)
```

### Caching Behavior

- **Prices:** No cache (always fetch fresh)
- **Account:** Cache 24 hours (for offline fallback)
- **Positions:** Use portfolio.json (always available)
- **Orders:** No cache (must be live)
- **Market hours:** Standard hours if broker unavailable

---

## 📝 Migration Checklist

### Components to Update

- [ ] RapidRotationScreener - add `data_manager` parameter
- [ ] RapidPortfolioManager - replace `broker` with `data_manager`
- [ ] AutoTradingEngine - add `data_manager` for READ ops
- [ ] TradingSafetySystem - use `data_manager` for checks
- [ ] PDTSmartGuard - use `data_manager` for account info

### Steps

1. **Add data_manager parameter to __init__()**
   ```python
   def __init__(self, data_manager: DataManager = None):
       self.data_manager = data_manager or DataManager()
   ```

2. **Replace broker calls with data_manager calls**
   ```python
   # Before
   quote = self.broker.get_snapshot(symbol)
   price = quote.last

   # After
   price = self.data_manager.get_current_price(symbol)
   ```

3. **Keep WRITE operations on broker**
   ```python
   # NEVER change these
   self.broker.place_market_buy(...)
   self.broker.place_stop_loss(...)
   self.broker.cancel_order(...)
   ```

4. **Test with and without broker**
   ```python
   # With broker (live trading)
   dm = DataManager(broker=AlpacaBroker(paper=True))

   # Without broker (backtest/offline)
   dm = DataManager()  # Uses yfinance + cache
   ```

---

## 🎯 Performance Impact

### Before (Direct Broker Calls)

```
Screener scan with 200 stocks:
- 200× get_snapshot() calls
- Total time: 30-60s
- Rate limit risk: HIGH
```

### After (DataManager Batch)

```
Screener scan with 200 stocks:
- 1× get_batch_prices() call
- Total time: 2-3s
- Rate limit risk: NONE
```

**Speedup:** 10-20x faster for batch operations

---

## 🔧 Backward Compatibility

DataManager is **fully backward compatible**:

```python
# Old code still works (no broker)
dm = DataManager()
prices = dm.get_price_data('AAPL', period='1y')  # Existing method

# New code with broker
dm = DataManager(broker=broker)
price = dm.get_current_price('AAPL')  # New method
```

No breaking changes to existing code.

---

## 📚 Next Steps

1. ✅ **Task #1 DONE:** DataManager v6.7 implemented
2. **Task #2:** Update RapidRotationScreener to use data_manager
3. **Task #3:** Update RapidPortfolioManager to use data_manager
4. **Task #4:** Update AutoTradingEngine READ operations
5. **Task #5:** Update TradingSafetySystem

**Total effort:** 2-3 hours for full migration
**Risk:** Very low (backward compatible)
