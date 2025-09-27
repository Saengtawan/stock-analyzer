#!/usr/bin/env python3
"""
Quick test of improved AI universe generation
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_ai_improvement():
    """Quick test of AI universe improvement"""
    try:
        from ai_universe_generator import AIUniverseGenerator

        generator = AIUniverseGenerator()

        criteria = {
            'max_stocks': 15,
            'screen_type': 'value',
            'max_pe_ratio': 20.0,
            'max_pb_ratio': 4.0,
            'min_roe': 8.0
        }

        print("🤖 Testing improved AI universe...")
        symbols = generator.generate_value_universe(criteria)

        print(f"✅ Generated {len(symbols)} symbols:")
        print(f"Symbols: {symbols}")

        # Check for value characteristics
        value_indicators = ['KEY', 'FITB', 'RF', 'T', 'VZ', 'XOM', 'CVX', 'COP', 'CAT', 'MMM', 'BAC', 'C', 'WFC']
        growth_indicators = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META']

        value_count = sum(1 for s in symbols if s in value_indicators)
        growth_count = sum(1 for s in symbols if s in growth_indicators)

        print(f"\n📊 ANALYSIS:")
        print(f"Value-oriented stocks: {value_count}")
        print(f"Growth-oriented stocks: {growth_count}")

        if value_count > growth_count:
            print("✅ SUCCESS: More value stocks than growth stocks!")
            return True
        else:
            print("⚠️  Still getting growth stocks")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    test_ai_improvement()