#!/usr/bin/env python
"""
Test Multi-Timeframe Analysis
"""
import sys
sys.path.insert(0, '/home/saengtawan/work/project/cc/stock-analyzer')

from src.main import StockAnalyzer
from loguru import logger
import json

# Suppress verbose logging
logger.remove()
logger.add(sys.stderr, level="WARNING")

def test_multi_timeframe(symbol: str = "MARA"):
    """Test multi-timeframe analysis for a symbol"""
    print(f"\n{'='*80}")
    print(f"Testing Multi-Timeframe Analysis for {symbol}")
    print(f"{'='*80}\n")

    try:
        # Initialize analyzer
        analyzer = StockAnalyzer(trading_strategy='swing_trading')

        # Analyze stock (with AI analysis disabled for faster testing)
        print(f"📊 Analyzing {symbol}...")
        result = analyzer.analyze_stock(symbol, time_horizon='medium', include_ai_analysis=False)

        # Extract multi-timeframe analysis
        multi_timeframe = result.get('multi_timeframe_analysis')

        if not multi_timeframe:
            print("❌ No multi-timeframe analysis found")
            print(f"Available keys: {list(result.keys())}")
            return

        # Display results
        selected = multi_timeframe.get('selected', 'Unknown')
        alignment = multi_timeframe.get('alignment', {})
        all_aligned = alignment.get('all_aligned', False)
        warnings = alignment.get('warnings', [])
        summary = alignment.get('summary', '')

        print(f"\n✅ Multi-Timeframe Analysis Generated!")
        print(f"\n🎯 Selected Timeframe: {selected.upper()}")
        print(f"   Alignment Status: {'✅ All Aligned' if all_aligned else '⚠️ Contains Conflicts'}")
        print(f"   Number of Warnings: {len(warnings)}")

        # Show each timeframe recommendation
        for horizon in ['short', 'medium', 'long']:
            rec = multi_timeframe.get(horizon)
            if rec:
                print(f"\n{'='*60}")
                print(f"📈 {horizon.upper()} TERM ({rec.get('time_description', 'N/A')})")
                print(f"{'='*60}")
                print(f"   Recommendation: {rec.get('recommendation', 'N/A')}")
                print(f"   Score: {rec.get('score', 0):.1f}/10")
                print(f"   Confidence: {rec.get('confidence', 'N/A')} ({rec.get('confidence_percentage', 0):.0f}%)")

                # Show component breakdown
                components = rec.get('component_scores', {})
                if components:
                    print(f"\n   Component Scores:")
                    for comp_name, comp_score in sorted(components.items(), key=lambda x: x[1], reverse=True):
                        print(f"      • {comp_name}: {comp_score:.1f}/10")

        # Show alignment summary and warnings
        print(f"\n{'='*80}")
        print(f"⚖️  ALIGNMENT ANALYSIS")
        print(f"{'='*80}")
        print(f"{summary}\n")

        if warnings:
            print(f"⚠️  Warnings ({len(warnings)}):\n")
            for warning in warnings:
                severity = warning.get('severity', 'warning')
                horizon = warning.get('timeframe', 'Unknown')
                action = warning.get('action', 'N/A')
                message = warning.get('message', '')
                reason = warning.get('reason', '')

                # Emoji based on severity
                emoji = '🔴' if severity == 'critical' else '🟡'

                print(f"{emoji} {horizon.upper()} ({action}):")
                print(f"   {message}")
                if reason:
                    print(f"   เหตุผล: {reason}")
                print()

        print(f"{'='*80}")
        print("✅ Multi-Timeframe Test Completed!")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "MARA"
    test_multi_timeframe(symbol)
