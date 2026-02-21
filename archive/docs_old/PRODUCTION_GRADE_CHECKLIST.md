# Production Grade Checklist - v6.20

**Current Status**: Working code, basic error handling
**Target**: Production-grade reliability, monitoring, resilience

---

## 🎯 High Impact, Low Effort (ทำเลย!)

### 1. Data Quality Checks (ป้องกัน Bad Data)

**ปัญหา**:
```python
# Current: Accept any VIX value
vix = float(vix_data['Close'].iloc[-1])  # ถ้า VIX = 999 ก็รับ!
return vix

# Current: Accept any VWAP
vwap = snapshot.vwap if snapshot.vwap > 0 else None  # ถ้า VWAP = $1,000,000 ก็รับ!
```

**ผลกระทบ**:
- VIX เพี้ยน → ใช้ wrong TTL → miss sector changes
- VWAP เพี้ยน → wrong validation → bad entries
- ราคาเพี้ยน → wrong position sizing

**แก้ไข**:
```python
# VIX validation
def _fetch_vix(self) -> Optional[float]:
    vix_data = vix_ticker.history(period='1d')
    if not vix_data.empty:
        vix = float(vix_data['Close'].iloc[-1])

        # ✅ Sanity checks
        if not (0 <= vix <= 100):  # VIX range 0-100
            logger.warning(f"⚠️ Invalid VIX value: {vix} (out of range 0-100)")
            return None

        # ✅ Spike detection (VIX jump >30 in 1 fetch = suspicious)
        if self._vix_cache and abs(vix - self._vix_cache) > 30:
            logger.warning(f"⚠️ Suspicious VIX jump: {self._vix_cache:.1f} → {vix:.1f}")
            # Use cached value (don't trust spike)
            return self._vix_cache

        return vix
    return None

# VWAP validation
def _get_realtime_data(self, symbol: str, fallback_price: float):
    snapshot = self.broker.get_snapshot(symbol)
    if snapshot:
        price = snapshot.last if snapshot.last > 0 else fallback_price
        vwap = snapshot.vwap if snapshot.vwap > 0 else None

        # ✅ Sanity checks
        if vwap:
            # VWAP should be within ±50% of current price
            if not (price * 0.5 <= vwap <= price * 1.5):
                logger.warning(f"⚠️ {symbol}: Suspicious VWAP ${vwap:.2f} vs price ${price:.2f}")
                vwap = None  # Don't use bad VWAP

        # ✅ Price reasonableness (not $0.01 or $100,000)
        if price > 0 and not (0.1 <= price <= 10000):
            logger.warning(f"⚠️ {symbol}: Suspicious price ${price:.2f}")
            price = fallback_price

        return price, vwap
```

**Effort**: 15 min
**Impact**: ป้องกัน bad data ทำให้ระบบพัง

---

### 2. Config Validation on Startup

**ปัญหา**:
```python
# Current: Load config, assume it's valid
config = RapidRotationConfig.from_yaml('config/trading.yaml')
# ถ้า config ผิด → crash ตอนใช้งาน (not at startup)
```

**แก้ไข**:
```python
# src/config/strategy_config.py

def validate(self) -> List[str]:
    """
    Validate config values on startup

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # VIX settings
    if not (0 <= self.sector_vix_threshold <= 100):
        errors.append(f"Invalid sector_vix_threshold: {self.sector_vix_threshold} (must be 0-100)")

    if self.sector_ttl_volatile_min <= 0:
        errors.append(f"Invalid sector_ttl_volatile_min: {self.sector_ttl_volatile_min} (must be > 0)")

    if self.sector_ttl_normal_min <= 0:
        errors.append(f"Invalid sector_ttl_normal_min: {self.sector_ttl_normal_min} (must be > 0)")

    if self.sector_vix_cache_ttl_sec <= 0:
        errors.append(f"Invalid sector_vix_cache_ttl_sec: {self.sector_vix_cache_ttl_sec} (must be > 0)")

    # Stop loss / take profit
    if self.min_sl_pct >= self.max_sl_pct:
        errors.append(f"min_sl_pct ({self.min_sl_pct}) must be < max_sl_pct ({self.max_sl_pct})")

    if self.min_tp_pct <= self.max_sl_pct:
        errors.append(f"min_tp_pct ({self.min_tp_pct}) must be > max_sl_pct ({self.max_sl_pct})")

    # VWAP distance
    if not (0 < self.entry_vwap_max_distance_pct <= 10):
        errors.append(f"entry_vwap_max_distance_pct must be 0-10% (got {self.entry_vwap_max_distance_pct})")

    return errors

# In __init__.py or run_app.py:
config = RapidRotationConfig.from_yaml('config/trading.yaml')
validation_errors = config.validate()
if validation_errors:
    logger.error("❌ Config validation failed:")
    for error in validation_errors:
        logger.error(f"  - {error}")
    sys.exit(1)
logger.info("✅ Config validated successfully")
```

**Effort**: 20 min
**Impact**: Catch config errors at startup (not in production)

---

### 3. Structured Logging

**ปัญหา**:
```python
# Current: String logs (hard to parse/query)
logger.info(f"VIX={vix:.1f} > 20 → Fast sector refresh (2 min)")
```

**แก้ไข**:
```python
# Add structured fields for important events

# VIX changes
logger.info(
    "VIX-based sector refresh",
    extra={
        "vix": vix,
        "threshold": self._vix_threshold,
        "ttl_minutes": ttl,
        "is_volatile": vix > self._vix_threshold,
        "event_type": "sector_refresh_ttl"
    }
)

# Entry validation
logger.info(
    "Entry validation",
    extra={
        "symbol": symbol,
        "signal_price": signal_price,
        "current_price": current_price,
        "vwap": vwap,
        "vwap_distance_pct": distance_pct,
        "allowed": allowed,
        "event_type": "entry_protection"
    }
)

# Trade execution
logger.info(
    "Trade executed",
    extra={
        "symbol": symbol,
        "side": "BUY",
        "quantity": qty,
        "price": fill_price,
        "sl": stop_loss,
        "tp": take_profit,
        "event_type": "trade"
    }
)
```

**Benefits**:
- Query logs: "Show all trades where vwap_distance > 1%"
- Aggregate: "Average entry price slippage"
- Alert: "If vwap distance > 1.5% in last hour"

**Effort**: 30 min
**Impact**: Much better debugging & monitoring

---

### 4. Health Check Endpoint

**ปัญหา**:
- No way to check if system is healthy
- Load balancer can't detect if app is broken
- Manual checking required

**แก้ไข**:
```python
# src/web/app.py

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for load balancers / monitoring

    Returns:
        200 if healthy, 503 if unhealthy
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "v6.20",
        "checks": {}
    }

    # Check 1: Engine running
    try:
        engine = get_auto_trading_engine()
        health["checks"]["engine"] = {
            "status": "ok" if engine and engine.running else "degraded",
            "running": engine.running if engine else False
        }
    except Exception as e:
        health["checks"]["engine"] = {"status": "error", "error": str(e)}
        health["status"] = "unhealthy"

    # Check 2: Broker connection
    try:
        if engine and engine.broker:
            account = engine.broker.get_account()
            health["checks"]["broker"] = {
                "status": "ok",
                "buying_power": float(account.buying_power) if account else 0
            }
        else:
            health["checks"]["broker"] = {"status": "no_broker"}
    except Exception as e:
        health["checks"]["broker"] = {"status": "error", "error": str(e)}
        health["status"] = "degraded"

    # Check 3: VIX cache
    try:
        if engine and hasattr(engine, 'screener') and engine.screener:
            detector = engine.screener.sector_regime
            if detector and hasattr(detector, '_vix_cache'):
                import time
                vix_age = time.time() - detector._vix_cache_time if detector._vix_cache_time else 999
                health["checks"]["vix_cache"] = {
                    "status": "ok" if vix_age < 120 else "stale",
                    "vix": detector._vix_cache,
                    "age_seconds": int(vix_age)
                }
    except Exception as e:
        health["checks"]["vix_cache"] = {"status": "error", "error": str(e)}

    # Check 4: Recent signal
    try:
        if os.path.exists('data/cache/rapid_signals.json'):
            with open('data/cache/rapid_signals.json') as f:
                signals = json.load(f)
                signal_age = (datetime.now() - datetime.fromisoformat(signals['timestamp'])).total_seconds()
                health["checks"]["signals"] = {
                    "status": "ok" if signal_age < 3600 else "stale",
                    "count": signals.get('count', 0),
                    "age_seconds": int(signal_age)
                }
    except Exception as e:
        health["checks"]["signals"] = {"status": "error", "error": str(e)}

    # Overall status
    if health["status"] == "unhealthy":
        return jsonify(health), 503
    elif any(check.get("status") == "error" for check in health["checks"].values()):
        health["status"] = "degraded"
        return jsonify(health), 200
    else:
        return jsonify(health), 200

# Usage:
# curl http://localhost:5000/health
# Monitoring: Alert if status != 200 for > 5 min
```

**Effort**: 20 min
**Impact**: Easy monitoring, load balancer integration

---

## ⚠️ High Impact, Medium Effort (ทำเร็วๆ)

### 5. Unit Tests for Critical Paths

**ปัญหา**:
- No automated tests
- Changes might break critical functionality
- Regression testing is manual

**แก้ไข**:
```python
# tests/test_vix_cache.py

import pytest
from sector_regime_detector import SectorRegimeDetector

class TestVIXCache:
    def test_vix_range_validation(self):
        """VIX must be 0-100"""
        detector = SectorRegimeDetector()

        # Mock yfinance to return invalid VIX
        with patch('yfinance.Ticker') as mock:
            mock.return_value.history.return_value = pd.DataFrame({
                'Close': [150]  # Invalid VIX > 100
            })

            vix = detector._fetch_vix()
            assert vix is None  # Should reject invalid VIX

    def test_vix_spike_detection(self):
        """VIX jump >30 should be rejected"""
        detector = SectorRegimeDetector()
        detector._vix_cache = 20.0

        # Mock spike: 20 → 60
        with patch('yfinance.Ticker') as mock:
            mock.return_value.history.return_value = pd.DataFrame({
                'Close': [60]  # Suspicious jump
            })

            vix = detector._fetch_vix()
            assert vix == 20.0  # Should use cached value

    def test_vix_cache_expiry(self):
        """Cache should expire after TTL"""
        detector = SectorRegimeDetector()
        detector._vix_cache_ttl = 60

        # First call - cache miss
        with patch('yfinance.Ticker') as mock:
            mock.return_value.history.return_value = pd.DataFrame({
                'Close': [25.0]
            })
            vix1 = detector._get_cached_vix()

        # Second call - cache hit (within 60s)
        vix2 = detector._get_cached_vix()
        assert vix2 == 25.0

        # Third call - cache expired
        import time
        detector._vix_cache_time = time.time() - 61  # Expired
        with patch('yfinance.Ticker') as mock:
            mock.return_value.history.return_value = pd.DataFrame({
                'Close': [26.0]
            })
            vix3 = detector._get_cached_vix()
        assert vix3 == 26.0  # New fetch

# tests/test_realtime_data.py

class TestRealtimeData:
    def test_vwap_sanity_check(self):
        """VWAP must be within ±50% of price"""
        engine = AutoTradingEngine(...)

        # Mock snapshot with bad VWAP
        mock_snapshot = Quote(
            symbol='TEST',
            last=100.0,
            vwap=500.0  # 5x price = bad!
        )

        with patch.object(engine.broker, 'get_snapshot', return_value=mock_snapshot):
            price, vwap = engine._get_realtime_data('TEST', 100.0)

        assert price == 100.0
        assert vwap is None  # Should reject bad VWAP

    def test_fallback_on_error(self):
        """Should use fallback if snapshot fails"""
        engine = AutoTradingEngine(...)

        with patch.object(engine.broker, 'get_snapshot', side_effect=Exception("API error")):
            price, vwap = engine._get_realtime_data('TEST', 99.0)

        assert price == 99.0  # Fallback
        assert vwap is None

# Run tests:
# pytest tests/ -v
```

**Effort**: 2-3 hours
**Impact**: Prevent regressions, safe refactoring

---

### 6. Circuit Breakers for API Calls

**ปัญหา**:
- If Alpaca API down → keep trying forever
- Waste resources, slow down system
- No graceful degradation

**แก้ไข**:
```python
# src/engine/circuit_breaker.py

class CircuitBreaker:
    """
    Circuit breaker pattern for API calls

    States:
    - CLOSED: Normal operation
    - OPEN: Too many failures, stop trying
    - HALF_OPEN: Testing if API recovered
    """

    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # seconds before retry
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            # Check if timeout passed
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker: HALF_OPEN (testing recovery)")
            else:
                raise Exception("Circuit breaker OPEN (API unavailable)")

        try:
            result = func(*args, **kwargs)
            # Success - reset failures
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                logger.info("Circuit breaker: CLOSED (API recovered)")
            self.failures = 0
            return result

        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()

            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"Circuit breaker: OPEN after {self.failures} failures")

            raise

# Usage in AlpacaBroker:
class AlpacaBroker:
    def __init__(self, ...):
        self.snapshot_breaker = CircuitBreaker(failure_threshold=5, timeout=60)

    def get_snapshot(self, symbol):
        try:
            return self.snapshot_breaker.call(self._get_snapshot_impl, symbol)
        except Exception as e:
            if "Circuit breaker OPEN" in str(e):
                logger.warning(f"Snapshot API circuit open, using fallback for {symbol}")
                return None  # Graceful degradation
            raise
```

**Effort**: 1 hour
**Impact**: System survives API outages

---

### 7. Environment-Specific Configs

**ปัญหา**:
- Same config for dev/staging/prod
- Can't test aggressive settings in dev
- Risk of dev settings in prod

**แก้ไข**:
```yaml
# config/trading.yaml (base config)
# config/trading.dev.yaml (dev overrides)
# config/trading.prod.yaml (prod overrides)

# config/trading.dev.yaml
rapid_rotation:
  sector_vix_threshold: 15.0  # More sensitive in dev
  sector_ttl_volatile_min: 1  # Faster refresh for testing
  entry_vwap_max_distance_pct: 3.0  # More permissive

# config/trading.prod.yaml
rapid_rotation:
  sector_vix_threshold: 20.0  # Conservative
  sector_ttl_volatile_min: 2
  entry_vwap_max_distance_pct: 1.5  # Strict

# Load:
env = os.getenv('ENV', 'dev')
base_config = RapidRotationConfig.from_yaml('config/trading.yaml')
env_config = RapidRotationConfig.from_yaml(f'config/trading.{env}.yaml')
config = base_config.merge(env_config)  # Override with env-specific
```

**Effort**: 30 min
**Impact**: Safe testing, proper prod settings

---

## 📊 Medium Impact, High Effort (ทำทีหลัง)

### 8. Metrics Collection (Prometheus)
- Track: API latency, error rate, cache hit rate, trade count
- Effort: 4 hours
- Impact: Deep observability

### 9. Distributed Tracing (OpenTelemetry)
- Trace: Signal → Snapshot → VWAP → Validation → Order
- Effort: 8 hours
- Impact: Debug complex flows

### 10. High Availability Setup
- Multiple instances, leader election, state sync
- Effort: 2 days
- Impact: Zero downtime

---

## 🎯 Recommended Priority

**Do This Week** (6-8 hours total):
1. ✅ Data quality checks (15 min) - ป้องกัน bad data
2. ✅ Config validation (20 min) - catch errors early
3. ✅ Health check endpoint (20 min) - easy monitoring
4. ✅ Structured logging (30 min) - better debugging
5. ✅ Unit tests (3 hours) - prevent regressions
6. ✅ Circuit breakers (1 hour) - survive API outages

**Do Next Week**:
7. Environment configs (30 min)
8. Metrics collection (4 hours)

**Do Later** (when scaling):
9. Distributed tracing
10. High availability

---

## 🔒 Production Readiness Score

**Current**: 60/100
- ✅ Core functionality works
- ✅ Basic error handling
- ✅ Some caching
- ❌ No data validation
- ❌ No tests
- ❌ No health checks
- ❌ No circuit breakers

**After Week 1 Fixes**: 85/100
- ✅ Data validation
- ✅ Config validation
- ✅ Health checks
- ✅ Unit tests
- ✅ Circuit breakers
- ✅ Structured logging

**Target (Production Grade)**: 95+/100

---

**Created**: 2026-02-13
**Version**: v6.20
**Next Review**: After implementing Week 1 fixes
