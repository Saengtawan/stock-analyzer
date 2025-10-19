#!/usr/bin/env python
"""
Quick test script for market state analysis
"""
import sys
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer')

from src.main import StockAnalyzer
from loguru import logger

# Suppress verbose logging
logger.remove()
logger.add(sys.stderr, level="ERROR")

def test_market_state(symbol: str = "MARA"):
    """Test market state analysis for a symbol"""
    print(f"\n{'='*80}")
    print(f"Testing Market State Analysis for {symbol}")
    print(f"{'='*80}\n")

    try:
        # Initialize analyzer
        analyzer = StockAnalyzer(trading_strategy='swing_trading')

        # Analyze stock (with AI analysis disabled for faster testing)
        print(f"📊 Analyzing {symbol}...")
        result = analyzer.analyze_stock(symbol, time_horizon='medium', include_ai_analysis=False)

        # Extract market state analysis
        enhanced_results = result.get('enhanced_analysis', {})
        technical = enhanced_results.get('technical_analysis', {})
        market_state_data = technical.get('market_state_analysis', {})

        if not market_state_data:
            print("❌ No market state analysis found")
            return

        # Display results
        current_state = market_state_data.get('current_state', 'Unknown')
        strategy = market_state_data.get('strategy', {})
        confidence = market_state_data.get('confidence', {})

        print(f"\n🎯 Current Market State: {current_state}")
        print(f"📈 Strategy: {strategy.get('strategy_name', 'Unknown')}")
        print(f"   Market State: {strategy.get('market_state', 'Unknown')}")

        # Overall Action Signal
        action_signal = strategy.get('action_signal', 'UNKNOWN')
        action_reason = strategy.get('action_reason', '')
        action_color = strategy.get('action_color', 'gray')
        entry_readiness = strategy.get('entry_readiness', 0)

        # Map color to emoji
        color_emoji = {
            'green': '🟢',
            'yellow': '🟡',
            'red': '🔴',
            'gray': '⚪'
        }
        emoji = color_emoji.get(action_color, '⚪')

        print(f"\n{emoji} Overall Action: {action_signal}")
        print(f"   {action_reason}")
        print(f"   Entry Readiness: {entry_readiness:.1f}/100")

        # Confidence Score
        conf_score = confidence.get('confidence', 0)
        conf_level = confidence.get('level', 'Unknown')
        aligned = confidence.get('aligned_count', 0)
        total = confidence.get('total_count', 0)
        conflicts = confidence.get('conflict_count', 0)

        print(f"\n💯 Confidence Score: {conf_score}%")
        print(f"   Level: {conf_level}")
        print(f"   Aligned Indicators: {aligned}/{total}")
        print(f"   Conflicting Indicators: {conflicts}")
        print(f"   Volume Confirmation: {'✅' if confidence.get('volume_confirmation') else '❌'}")

        if confidence.get('reasons'):
            print(f"\n   Reasons:")
            for reason in confidence.get('reasons', []):
                print(f"   - {reason}")

        # Entry Conditions
        print(f"\n✅ Entry Conditions:")
        for cond in strategy.get('entry_conditions', []):
            print(f"   {cond.get('status', '?')} {cond.get('condition', 'N/A')}")
            print(f"      → {cond.get('reason', '')}")

        # Exit Conditions
        print(f"\n🚪 Exit Conditions:")
        for cond in strategy.get('exit_conditions', []):
            print(f"   {cond.get('status', '?')} {cond.get('condition', 'N/A')}")
            print(f"      → {cond.get('reason', '')}")

        # Warnings
        if strategy.get('warnings'):
            print(f"\n⚠️  Warnings:")
            for warning in strategy.get('warnings', []):
                print(f"   - {warning}")

        # Trading Plan
        trading_plan = strategy.get('trading_plan', {})
        if trading_plan:
            print(f"\n📋 Trading Plan:")
            entry_range = trading_plan.get('entry_range', [0, 0])
            print(f"   Entry Range: ${entry_range[0]:.2f} - ${entry_range[1]:.2f}")
            print(f"   Take Profit: ${trading_plan.get('take_profit', 0):.2f}")
            print(f"   Stop Loss: ${trading_plan.get('stop_loss', 0):.2f}")
            print(f"   Risk/Reward Ratio: {trading_plan.get('risk_reward_ratio', 0):.2f}")

        print(f"\n{'='*80}")
        print("✅ Test completed successfully!")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "MARA"
    test_market_state(symbol)
