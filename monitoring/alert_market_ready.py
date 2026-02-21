#!/usr/bin/env python3
"""
Market Regime Alert System
Monitors SPY and notifies when conditions are met for trading
"""
import sys
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
from datetime import datetime
import json
import os

# Alert thresholds
ALERT_FILE = '/tmp/market_alerts.json'
SPY_BULL_THRESHOLD = 689.14  # SMA20 from Feb 19

def get_market_status():
    """Get current market status."""
    spy = yf.Ticker("SPY")
    hist = spy.history(period="60d")

    current = hist['Close'].iloc[-1]
    sma20 = hist['Close'].rolling(20).mean().iloc[-1]
    sma50 = hist['Close'].rolling(50).mean().iloc[-1]

    # Calculate VIX
    vix = yf.Ticker("^VIX")
    vix_hist = vix.history(period="5d")
    current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else 0

    regime = "BULL" if current > sma20 else "BEAR"
    distance_pct = ((current - sma20) / sma20) * 100

    # Determine VIX tier
    if current_vix < 20:
        vix_tier = "NORMAL"
    elif current_vix < 24:
        vix_tier = "SKIP"
    elif current_vix < 38:
        vix_tier = "HIGH"
    else:
        vix_tier = "EXTREME"

    return {
        'timestamp': datetime.now().isoformat(),
        'spy_price': round(current, 2),
        'spy_sma20': round(sma20, 2),
        'spy_sma50': round(sma50, 2),
        'regime': regime,
        'distance_pct': round(distance_pct, 3),
        'distance_usd': round(current - sma20, 2),
        'vix': round(current_vix, 2),
        'vix_tier': vix_tier,
        'previous_regime': None
    }

def load_previous_status():
    """Load previous market status."""
    if not os.path.exists(ALERT_FILE):
        return None

    try:
        with open(ALERT_FILE, 'r') as f:
            return json.load(f)
    except:
        return None

def save_current_status(status):
    """Save current market status."""
    with open(ALERT_FILE, 'w') as f:
        json.dump(status, f, indent=2)

def check_alerts(current, previous):
    """Check if any alert conditions are met."""
    alerts = []

    # Alert 1: Regime changed from BEAR to BULL
    if previous and previous['regime'] == 'BEAR' and current['regime'] == 'BULL':
        alerts.append({
            'type': 'REGIME_CHANGE',
            'priority': 'HIGH',
            'message': f"🚨 SPY ENTERED BULL MODE! ${current['spy_price']} > ${current['spy_sma20']}",
            'action': "Trading can resume! Engine will start evaluating signals."
        })

    # Alert 2: Close to regime change (within 0.5%)
    elif current['regime'] == 'BEAR' and abs(current['distance_pct']) < 0.5:
        if not previous or abs(previous['distance_pct']) >= 0.5:
            alerts.append({
                'type': 'NEAR_REGIME_CHANGE',
                'priority': 'MEDIUM',
                'message': f"⚠️ SPY close to BULL mode! Only {abs(current['distance_usd']):.2f} away (${current['spy_price']} vs ${current['spy_sma20']})",
                'action': "Monitor closely. May enter BULL mode soon."
            })

    # Alert 3: VIX tier changed
    if previous and previous['vix_tier'] != current['vix_tier']:
        tier_change = f"{previous['vix_tier']} → {current['vix_tier']}"
        alerts.append({
            'type': 'VIX_TIER_CHANGE',
            'priority': 'MEDIUM' if current['vix_tier'] != 'EXTREME' else 'HIGH',
            'message': f"📊 VIX Tier Changed: {tier_change} (VIX {current['vix']})",
            'action': f"Strategy will adapt to {current['vix_tier']} tier behavior."
        })

    # Alert 4: VIX EXTREME (close all positions)
    if current['vix_tier'] == 'EXTREME':
        if not previous or previous['vix_tier'] != 'EXTREME':
            alerts.append({
                'type': 'VIX_EXTREME',
                'priority': 'CRITICAL',
                'message': f"🔴 VIX EXTREME! VIX {current['vix']} > 38",
                'action': "Close all positions immediately! Market panic mode."
            })

    # Alert 5: Regime changed from BULL to BEAR
    if previous and previous['regime'] == 'BULL' and current['regime'] == 'BEAR':
        alerts.append({
            'type': 'REGIME_CHANGE',
            'priority': 'HIGH',
            'message': f"📉 SPY ENTERED BEAR MODE! ${current['spy_price']} < ${current['spy_sma20']}",
            'action': "No new entries. Monitor existing positions."
        })

    return alerts

def print_status_report(status, alerts):
    """Print current status and alerts."""
    print("=" * 80)
    print("🔔 MARKET REGIME ALERT SYSTEM")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Market Status
    print("📊 CURRENT MARKET STATUS")
    print("-" * 80)
    print(f"SPY Price:        ${status['spy_price']}")
    print(f"SPY SMA20:        ${status['spy_sma20']}")
    print(f"Regime:           {status['regime']}")
    print(f"Distance:         {status['distance_pct']:+.3f}% (${status['distance_usd']:+.2f})")
    print(f"VIX:              {status['vix']}")
    print(f"VIX Tier:         {status['vix_tier']}")
    print()

    # Alerts
    if alerts:
        print("🚨 ALERTS")
        print("-" * 80)
        for alert in alerts:
            priority_icon = {
                'CRITICAL': '🔴',
                'HIGH': '🟠',
                'MEDIUM': '🟡',
                'LOW': '🟢'
            }.get(alert['priority'], '⚪')

            print(f"{priority_icon} [{alert['priority']}] {alert['message']}")
            print(f"   → Action: {alert['action']}")
            print()
    else:
        print("✅ No new alerts")
        print()

    # Status Summary
    print("📋 STATUS SUMMARY")
    print("-" * 80)

    if status['regime'] == 'BULL':
        print("✅ Trading: ACTIVE (BULL mode)")
        print("   Engine evaluating signals")
    else:
        print("⏸️  Trading: PAUSED (BEAR mode)")
        print(f"   Need ${abs(status['distance_usd']):.2f} to enter BULL mode")

    if status['vix_tier'] == 'NORMAL':
        print(f"✅ VIX: Calm market ({status['vix']} < 20)")
        print("   Mean reversion strategy active")
    elif status['vix_tier'] == 'SKIP':
        print(f"⚠️  VIX: Uncertainty zone ({status['vix']} 20-24)")
        print("   No trading (SKIP tier)")
    elif status['vix_tier'] == 'HIGH':
        print(f"🟡 VIX: High volatility ({status['vix']} 24-38)")
        print("   Bounce strategy active")
    elif status['vix_tier'] == 'EXTREME':
        print(f"🔴 VIX: EXTREME ({status['vix']} > 38)")
        print("   Close all positions!")

    print()
    print("=" * 80)

def main():
    """Main alert check."""
    current = get_market_status()
    previous = load_previous_status()

    alerts = check_alerts(current, previous)

    print_status_report(current, alerts)

    # Save current status
    save_current_status(current)

    # Return exit code based on alerts
    if any(a['priority'] == 'CRITICAL' for a in alerts):
        return 2  # Critical alert
    elif any(a['priority'] == 'HIGH' for a in alerts):
        return 1  # High priority alert
    else:
        return 0  # No critical alerts

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
