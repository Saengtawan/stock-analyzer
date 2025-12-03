#!/usr/bin/env python3
"""Debug script to see what's in the analysis results"""

import pandas as pd
import numpy as np
from src.analysis.technical.technical_analyzer import TechnicalAnalyzer
import json

# Create simple test data
dates = pd.date_range('2024-01-01', periods=100, freq='D')
np.random.seed(42)
close = 100 + np.cumsum(np.random.randn(100) * 2 + 0.5)
high = close + np.random.rand(100) * 2
low = close - np.random.rand(100) * 2
open_price = close + np.random.randn(100) * 1
volume = np.random.randint(1000000, 3000000, 100)

data = pd.DataFrame({
    'date': dates,
    'open': open_price,
    'high': high,
    'low': low,
    'close': close,
    'volume': volume,
    'symbol': ['TEST'] * 100
})

print("Analyzing...")
analyzer = TechnicalAnalyzer(data)
results = analyzer.analyze()

print("\nTop-level keys in results:")
for key in results.keys():
    print(f"  - {key}")

print("\nRecommendation:")
strategy = results.get('recommendation', {})
if strategy:
    print(f"  Keys: {list(strategy.keys())}")
    print(f"  Strategy Name: {strategy.get('strategy_name', 'N/A')}")
    print(f"  Market State: {strategy.get('market_state', 'N/A')}")
    print(f"  Action Signal: {strategy.get('action_signal', 'N/A')}")
else:
    print("  ❌ No recommendation found!")

    # Try strategy_recommendation too
    strategy = results.get('strategy_recommendation', {})
    if strategy:
        print("  Found in 'strategy_recommendation' instead!")
        print(f"  Keys: {list(strategy.keys())}")
    else:
        print("  Not in 'strategy_recommendation' either!")

print("\nTrading Plan:")
trading_plan = strategy.get('trading_plan', {})
if trading_plan:
    print(f"  Keys: {list(trading_plan.keys())[:10]}...")  # First 10 keys
    print(f"  Entry Price: {trading_plan.get('entry_price', 'N/A')}")
    print(f"  Entry Method: {trading_plan.get('entry_method', 'N/A')}")
    print(f"  Has immediate_entry: {'immediate_entry' in trading_plan}")
else:
    print("  ❌ No trading plan found!")

print("\n✅ Done")
