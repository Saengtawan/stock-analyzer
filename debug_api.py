#!/usr/bin/env python3
import requests
import json

url = "http://127.0.0.1:5002/api/analyze"
data = {"symbol": "AFRM", "time_horizon": "short", "account_value": 100000}

print("🔍 Fetching API data for AFRM...\n")
response = requests.post(url, json=data, timeout=120)
result = response.json()

if 'enhanced_features' not in result:
    print("❌ No enhanced_features")
    exit(1)

ef = result['enhanced_features']
features = ef.get('features', {})

print("="*70)
print("💰 P&L TRACKER RAW DATA:")
print("="*70)
pnl = features.get('pnl_tracker', {})
print(json.dumps(pnl, indent=2, default=str))

print("\n" + "="*70)
print("🛡️ TRAILING STOP RAW DATA:")
print("="*70)
ts = features.get('trailing_stop', {})
print(json.dumps(ts, indent=2, default=str))

print("\n" + "="*70)
print("⚠️ RISK ALERTS RAW DATA:")
print("="*70)
ra = features.get('risk_alerts', {})
print(json.dumps(ra, indent=2, default=str))
