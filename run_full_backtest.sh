#!/bin/bash
# Run Full Backtest - Complete 6-month test
# Runtime: ~10-15 minutes

echo "================================================================================"
echo "🚀 RUNNING FULL 6-MONTH BACKTEST"
echo "================================================================================"
echo "Period: June 1 - Dec 26, 2025"
echo "Using pre-computed macro regimes"
echo "Optimized: 2x/week entry checks"
echo ""
echo "This will take 10-15 minutes..."
echo "Results will be saved to: backtest_results_final.txt"
echo ""

# Run backtest in background
nohup python3 backtest_complete_6layer.py > backtest_results_final.txt 2>&1 &

PID=$!
echo "Backtest running in background (PID: $PID)"
echo ""
echo "Check progress:"
echo "  tail -f backtest_results_final.txt"
echo ""
echo "Check if done:"
echo "  ps -p $PID"
echo ""
echo "View results:"
echo "  cat backtest_results_final.txt | grep -A 40 '📊 COMPLETE 6-LAYER SYSTEM RESULTS'"
echo ""
echo "================================================================================"
