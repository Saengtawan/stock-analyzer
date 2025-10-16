"""
Quick test to check if weights_applied is in API response
"""
import requests
import json

url = "http://localhost:5002/api/analyze"
payload = {
    "symbol": "AAPL",
    "time_horizon": "medium",
    "include_ai": False
}

print("🔍 Testing API endpoint...")
print(f"Payload: {payload}")

response = requests.post(url, json=payload, timeout=30)

if response.status_code == 200:
    data = response.json()

    # Check if unified_recommendation exists
    unified_rec = data.get('unified_recommendation', {})
    weights = unified_rec.get('weights_applied', {})

    print("\n✅ API Response received")
    print(f"  unified_recommendation exists: {bool(unified_rec)}")
    print(f"  weights_applied exists: {bool(weights)}")
    print(f"  weights_applied content: {weights}")

    if weights:
        print("\n📊 Weights breakdown:")
        for component, weight in weights.items():
            print(f"    {component}: {weight * 100:.1f}%")
    else:
        print("\n❌ weights_applied is EMPTY!")
        print("\nFull unified_recommendation structure:")
        print(json.dumps(unified_rec, indent=2))
else:
    print(f"\n❌ API request failed: {response.status_code}")
    print(f"Response: {response.text[:500]}")
