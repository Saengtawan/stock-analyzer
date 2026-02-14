#!/usr/bin/env python3
"""
Check After-Hours P&L
Shows real-time portfolio P&L including after-hours movement

Usage:
    python3 check_afterhours_pnl.py
"""

import yfinance as yf
import json
from datetime import datetime

# Hardcoded positions (update as needed)
positions = {
    "AIT": {
        "entry_price": 282.83,
        "shares": 1
    },
    "FAST": {
        "entry_price": 46.21,
        "shares": 8
    }
}

# Alternatively, try to load from rapid_portfolio.json if it exists
import os
portfolio_path = os.path.join(os.path.dirname(__file__), 'rapid_portfolio.json')
if os.path.exists(portfolio_path):
    try:
        with open(portfolio_path, 'r') as f:
            portfolio = json.load(f)
            positions = portfolio.get('positions', positions)
    except Exception as e:
        print(f"Warning: Could not load portfolio file, using hardcoded positions: {e}\n")

print("\n" + "=" * 80)
print("📊 AFTER-HOURS P&L CHECK")
print("=" * 80)
print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

total_regular_pnl = 0
total_afterhours_pnl = 0

for symbol, pos_data in positions.items():
    ticker = yf.Ticker(symbol)
    info = ticker.info

    entry = pos_data['entry_price']
    shares = pos_data['shares']

    # Get prices
    regular_close = info.get('regularMarketPrice', 0)
    after_hours = info.get('postMarketPrice', regular_close)
    has_afterhours = 'postMarketPrice' in info and info.get('postMarketPrice')

    # Calculate P&L
    regular_pnl_pct = ((regular_close - entry) / entry) * 100
    regular_pnl_usd = (regular_close - entry) * shares

    ah_pnl_pct = ((after_hours - entry) / entry) * 100
    ah_pnl_usd = (after_hours - entry) * shares

    # Emoji indicators
    emoji_regular = "🟢" if regular_pnl_pct > 0 else "🔴" if regular_pnl_pct < 0 else "⚪"
    emoji_ah = "🟢" if ah_pnl_pct > 0 else "🔴" if ah_pnl_pct < 0 else "⚪"

    print(f"{symbol} ({shares} shares @ ${entry:.2f}):")
    print(f"  {emoji_regular} Regular Close:   ${regular_close:.2f}  ({regular_pnl_pct:+.2f}%, ${regular_pnl_usd:+.2f})")

    if has_afterhours:
        ah_change = after_hours - regular_close
        ah_change_pct = (ah_change / regular_close) * 100 if regular_close > 0 else 0
        print(f"  {emoji_ah} After-Hours:     ${after_hours:.2f}  ({ah_pnl_pct:+.2f}%, ${ah_pnl_usd:+.2f})")
        print(f"     AH Movement:    ${ah_change:+.2f}  ({ah_change_pct:+.2f}%)")
    else:
        print(f"  ⚪ After-Hours:     No data (using close)")

    print()

    total_regular_pnl += regular_pnl_usd
    total_afterhours_pnl += ah_pnl_usd

print("=" * 80)
print(f"💰 Total P&L (Regular Close):  ${total_regular_pnl:+.2f}")
print(f"💰 Total P&L (After-Hours):    ${total_afterhours_pnl:+.2f}")

difference = total_afterhours_pnl - total_regular_pnl
if abs(difference) > 0.01:
    diff_emoji = "📉" if difference < 0 else "📈"
    print(f"{diff_emoji} Difference:                ${difference:+.2f}")

print("=" * 80)

# Show summary
print(f"\n📋 Summary:")
print(f"   Positions: {len(positions)}")
print(f"   Regular Close P&L: ${total_regular_pnl:+.2f}")
print(f"   After-Hours P&L:   ${total_afterhours_pnl:+.2f}")

if abs(difference) > 0.01:
    pct_worse = (difference / abs(total_regular_pnl)) * 100 if total_regular_pnl != 0 else 0
    print(f"   Impact: {pct_worse:+.1f}% worse after hours")

print()
