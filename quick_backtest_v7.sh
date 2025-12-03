#!/bin/bash
# Quick Manual Backtest for v7.0
# Tests critical stocks to verify improvements

echo "=================================="
echo "🚀 Quick Backtest v7.0"
echo "=================================="
echo ""

# Function to run single backtest and extract key metrics
run_test() {
    local symbol=$1
    local horizon=$2
    local label=$3

    echo "─────────────────────────────────"
    echo "📊 Testing: $symbol ($horizon) - $label"
    echo "─────────────────────────────────"

    python -c "
from backtest_analyzer import BacktestAnalyzer
from datetime import datetime, timedelta
import sys

backtester = BacktestAnalyzer()
analysis_date = datetime.now() - timedelta(days=14)

result = backtester.backtest_single(
    symbol='$symbol',
    analysis_date=analysis_date,
    days_forward=7,
    time_horizon='$horizon'
)

if result:
    rec = result['recommendation']
    correct = '✅' if result['recommendation_correct'] else '❌'
    ret = result['actual_performance']['return_pct']
    tp_hit = '✅' if result['actual_performance']['tp_hit'] else '❌'

    print(f'Recommendation: {rec} {correct}')
    print(f'Return: {ret:+.2f}%')
    print(f'TP Hit: {tp_hit}')
    print(f'Volatility: {result.get(\"volatility_class\", \"N/A\")}')
else:
    print('❌ Test failed - no result')
    sys.exit(1)
" 2>&1 | grep -E "Recommendation:|Return:|TP Hit:|Volatility:|Test failed"

    echo ""
}

# Test 1: CRITICAL - Swing Stocks (Expected 0% → 70-80%)
echo "🎯 CRITICAL TESTS: Swing Stocks"
echo "Expected: 0% → 70-80% accuracy"
echo ""

run_test "PLTR" "short" "Swing stock - Short term"
run_test "PLTR" "medium" "Swing stock - Medium term"
run_test "SOFI" "short" "Swing stock - Short term"

# Test 2: Regular Stocks (Expected 40-60% → 65-70%)
echo ""
echo "📈 Regular Stocks Tests"
echo "Expected: 40-60% → 65-70% accuracy"
echo ""

run_test "AAPL" "short" "Low volatility - Short term"
run_test "NVDA" "short" "Medium volatility - Short term"

# Test 3: High Volatility
echo ""
echo "⚡ High Volatility Test"
echo ""

run_test "TSLA" "short" "High volatility - Short term"

echo ""
echo "=================================="
echo "✅ Quick Backtest Complete!"
echo "=================================="
