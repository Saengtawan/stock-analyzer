"""
Demo Script for Enhanced Features
Tests all 6 features with real stock data (U, AFRM, CLSK)

Run: python demo_enhanced_features.py
"""

from src.analysis.enhanced_features import analyze_stock


def demo_u_stock():
    """Demo with U (Unity Software) - from user's data"""
    print("\n" + "="*60)
    print("🎮 DEMO: U (Unity Software)")
    print("="*60 + "\n")

    result = analyze_stock(
        symbol="U",
        current_price=40.03,
        entry_zone=(37.96, 38.73),
        support=38.35,
        resistance=41.22,
        tp1=40.80,
        tp2=42.50,
        stop_loss=37.58,
        rsi=54.52,
        volume_vs_avg=1.0,  # Normal volume
        market_regime="sideways",

        # Simulating position
        has_position=False,  # Not holding yet
        signal_date="2025-11-05",
        shares=100,
        holding_days=0,

        # Additional
        selling_pressure=60.0,  # 60% selling pressure
        target_hold_days=14
    )

    print(result["formatted_output"])

    print("\n📊 Quick Summary:")
    print(f"Decision: {result['features']['decision_matrix']['decision']['action']}")
    print(f"Confidence: {result['features']['decision_matrix']['decision']['confidence']}%")
    print(f"Entry Readiness: {result['features']['price_monitor']['readiness']['score']}/100")


def demo_afrm_stock():
    """Demo with AFRM (Affirm) - from user's data"""
    print("\n" + "="*60)
    print("💳 DEMO: AFRM (Affirm)")
    print("="*60 + "\n")

    result = analyze_stock(
        symbol="AFRM",
        current_price=73.62,
        entry_zone=(69.22, 70.62),
        support=69.92,
        resistance=75.61,
        tp1=74.86,
        tp2=80.00,
        stop_loss=68.52,
        rsi=50.06,
        volume_vs_avg=2.8,  # High volume!
        market_regime="sideways",

        # Simulating held position
        has_position=True,
        signal_date="2025-11-06",
        entry_price=70.00,  # Custom entry
        shares=100,
        holding_days=3,

        # Additional
        selling_pressure=40.0,
        target_hold_days=14
    )

    print(result["formatted_output"])

    print("\n📊 Quick Summary:")
    print(f"Decision: {result['features']['decision_matrix']['decision']['action']}")
    print(f"Profit: {result['profit_pct']:.2f}%")
    if result['features']['trailing_stop']:
        print(f"Should Move SL: {result['features']['trailing_stop']['should_move']}")


def demo_clsk_stock():
    """Demo with CLSK (CleanSpark) - from user's data"""
    print("\n" + "="*60)
    print("⚡ DEMO: CLSK (CleanSpark)")
    print("="*60 + "\n")

    result = analyze_stock(
        symbol="CLSK",
        current_price=15.57,
        entry_zone=(14.41, 14.70),
        support=14.56,
        resistance=16.09,
        tp1=15.93,
        tp2=17.50,
        stop_loss=14.27,
        rsi=42.78,
        volume_vs_avg=1.0,
        market_regime="sideways",

        # No position yet
        has_position=False,
        signal_date="2025-11-05",
        shares=300,  # More shares (cheaper stock)
        holding_days=0,

        # Additional
        target_hold_days=14
    )

    print(result["formatted_output"])

    print("\n📊 Quick Summary:")
    print(f"Decision: {result['features']['decision_matrix']['decision']['action']}")
    print(f"Entry Readiness: {result['features']['price_monitor']['readiness']['score']}/100")


def demo_comparison():
    """Quick comparison of all 3 stocks"""
    print("\n" + "="*60)
    print("📊 QUICK COMPARISON")
    print("="*60 + "\n")

    stocks = [
        ("U", 40.03, (37.96, 38.73), 54.52, False),
        ("AFRM", 73.62, (69.22, 70.62), 50.06, True),
        ("CLSK", 15.57, (14.41, 14.70), 42.78, False)
    ]

    print(f"{'Stock':<10} {'Price':<10} {'RSI':<8} {'Position':<12} {'Recommendation'}")
    print("-" * 60)

    for symbol, price, entry_zone, rsi, has_pos in stocks:
        pos_status = "Holding" if has_pos else "Watching"

        # Quick decision
        if has_pos:
            decision = "HOLD/SELL"
        else:
            in_zone = entry_zone[0] <= price <= entry_zone[1]
            if in_zone and rsi < 50:
                decision = "🟢 BUY NOW"
            elif rsi < 50:
                decision = "🟡 READY"
            else:
                decision = "🔴 WAIT"

        print(f"{symbol:<10} ${price:<9.2f} {rsi:<8.1f} {pos_status:<12} {decision}")


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║  Enhanced Features Demo - Version 1.0.0 (MVP)           ║
    ║                                                          ║
    ║  Testing 6 Features:                                    ║
    ║  1. Real-Time Price Monitor                             ║
    ║  2. P&L Tracker (Auto-entry)                            ║
    ║  3. Trailing Stop Manager                               ║
    ║  4. Short Interest Analyzer                             ║
    ║  5. Decision Matrix                                     ║
    ║  6. Risk Alert Manager                                  ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    try:
        # Run demos
        demo_u_stock()
        input("\nPress Enter to continue to AFRM...")

        demo_afrm_stock()
        input("\nPress Enter to continue to CLSK...")

        demo_clsk_stock()
        input("\nPress Enter to see comparison...")

        demo_comparison()

        print("\n" + "="*60)
        print("✅ Demo completed successfully!")
        print("="*60)

    except KeyboardInterrupt:
        print("\n\n⚠️ Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
