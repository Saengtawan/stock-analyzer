#!/bin/bash
#
# Test Database API Endpoints
# =============================
#

BASE_URL="http://localhost:5000"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Testing Database API Endpoints"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test 1: Database stats
echo "[1/6] GET /api/db/stats"
curl -s "$BASE_URL/api/db/stats" | python3 -m json.tool | head -30
echo ""

# Test 2: Recent trades
echo "[2/6] GET /api/db/trades/recent?days=7"
curl -s "$BASE_URL/api/db/trades/recent?days=7" | python3 -m json.tool | head -20
echo ""

# Test 3: Trade statistics
echo "[3/6] GET /api/db/trades/stats?days=30"
curl -s "$BASE_URL/api/db/trades/stats?days=30" | python3 -m json.tool | head -30
echo ""

# Test 4: Trades by symbol
echo "[4/6] GET /api/db/trades/symbol/AAPL"
curl -s "$BASE_URL/api/db/trades/symbol/AAPL" | python3 -m json.tool | head -20
echo ""

# Test 5: Active positions
echo "[5/6] GET /api/db/positions"
curl -s "$BASE_URL/api/db/positions" | python3 -m json.tool | head -30
echo ""

# Test 6: Price data
echo "[6/6] GET /api/db/prices/AAPL?days=7"
curl -s "$BASE_URL/api/db/prices/AAPL?days=7" | python3 -m json.tool | head -40
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ All API tests completed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
