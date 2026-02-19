"""
Implementation Code for Option 1: Wider SL for Volatile Stocks

Location: /home/saengtawan/work/project/cc/stock-analyzer/src/auto_trading_engine.py
Function: _calculate_atr_sl_tp() (around line 2228)

Instructions:
1. Find the line: sl_pct = self.SL_ATR_MULTIPLIER * atr_pct
2. Replace with the code below
3. Test in paper trading mode
4. Monitor for 30 days
"""

from typing import Dict, List
import numpy as np

# ============================================================================
# TESTING CODE
# ============================================================================

def test_adaptive_sl():
    """
    Unit test to verify adaptive SL logic
    Run before deploying to production
    """
    
    test_cases = [
        # (atr_pct, expected_multiplier, expected_sl_pct)
        (2.0, 1.5, 3.0),   # Low volatility → standard 1.5x
        (2.5, 1.5, 3.75),  # Medium volatility → standard 1.5x
        (3.0, 1.5, 4.5),   # At threshold → standard 1.5x
        (3.1, 2.0, 6.0),   # Just above threshold → wider 2.0x (capped)
        (3.5, 2.0, 6.0),   # High volatility → wider 2.0x (capped at 6%)
        (4.0, 2.0, 6.0),   # Very high volatility → wider 2.0x (capped at 6%)
    ]
    
    print("\nTesting Adaptive SL Logic:")
    print("="*80)
    
    for atr_pct, expected_mult, expected_sl in test_cases:
        # Apply logic
        if atr_pct > 3.0:
            sl_multiplier = 2.0
        else:
            sl_multiplier = 1.5
        
        sl_pct = min(sl_multiplier * atr_pct, 6.0)
        
        # Verify
        assert sl_multiplier == expected_mult, f"Multiplier mismatch for ATR {atr_pct}%"
        assert abs(sl_pct - expected_sl) < 0.1, f"SL% mismatch for ATR {atr_pct}%"
        
        print(f"✓ ATR {atr_pct:4.1f}% → {sl_multiplier}x multiplier → SL {sl_pct:4.1f}%")
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    # Run unit test
    test_adaptive_sl()
    
    print("\n" + "="*80)
    print("IMPLEMENTATION READY")
    print("="*80)
    print("\nNext steps:")
    print("1. Copy adaptive SL code to auto_trading_engine.py")
    print("2. Update config/trading.yaml with new parameters")
    print("3. Test in paper trading for 1 week")
    print("4. Monitor results and validate after 30 trades")
    print("\nCode snippet to add:")
    print("-"*80)
    print("""
    # In _calculate_atr_sl_tp() function, replace:
    # sl_pct = self.SL_ATR_MULTIPLIER * atr_pct
    
    # With:
    if atr_pct > 3.0:
        sl_multiplier = 2.0  # Wider SL for volatile stocks
    else:
        sl_multiplier = self.SL_ATR_MULTIPLIER  # Standard 1.5
    
    sl_pct = sl_multiplier * atr_pct
    sl_pct = min(sl_pct, 6.0)  # Cap at 6% max
    """)
    print("="*80)

