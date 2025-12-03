#!/usr/bin/env python3
import requests
import json

# Test API endpoint
url = "http://127.0.0.1:5002/api/analyze"
data = {
    "symbol": "U",
    "time_horizon": "short",
    "account_value": 100000
}

print("Testing enhanced features API...")
response = requests.post(url, json=data)
result = response.json()

# Check if enhanced_features exists
if 'enhanced_features' in result:
    print("✅ enhanced_features found in response!")

    enhanced = result['enhanced_features']
    features = enhanced.get('features', {})

    print(f"\nSymbol: {enhanced.get('symbol')}")
    print(f"Timestamp: {enhanced.get('timestamp')}")
    print(f"\nAvailable features:")

    # Check each feature
    feature_names = [
        'price_monitor',
        'pnl_tracker',
        'trailing_stop',
        'short_interest',
        'decision_matrix',
        'risk_alerts'
    ]

    for feature_name in feature_names:
        if feature_name in features:
            print(f"  ✅ {feature_name}")

            # Show key data for each feature
            feature_data = features[feature_name]

            if feature_name == 'price_monitor':
                readiness = feature_data.get('readiness', {})
                print(f"     Entry Readiness: {readiness.get('score', 0)}/100 - {readiness.get('status', '')}")

            elif feature_name == 'pnl_tracker':
                entry = feature_data.get('entry', {})
                current = feature_data.get('current', {})
                print(f"     Entry: ${entry.get('price', 0):.2f} | P/L: {current.get('profit_pct', 0):+.2f}%")

            elif feature_name == 'trailing_stop':
                print(f"     Should Move: {feature_data.get('should_move', False)}")

            elif feature_name == 'short_interest':
                si = feature_data.get('short_interest', {})
                print(f"     Short Interest: {si.get('short_pct_float', 0):.2f}%")

            elif feature_name == 'decision_matrix':
                decision = feature_data.get('decision', {})
                print(f"     Decision: {decision.get('action', 'N/A')} ({decision.get('confidence', 0)}% confidence)")

            elif feature_name == 'risk_alerts':
                alerts = feature_data.get('alerts', [])
                print(f"     Alerts: {len(alerts)} active")
        else:
            print(f"  ❌ {feature_name} - MISSING")

    print("\n✅ All enhanced features are working!")

else:
    print("❌ enhanced_features NOT found in response")
    print(f"Available keys: {list(result.keys())}")
