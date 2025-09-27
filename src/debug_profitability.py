#!/usr/bin/env python3
"""
Debug TTD profitability scoring
"""

def debug_profitability_scoring():
    """Debug the profitability scoring for TTD"""

    # TTD data from analysis
    roe = 0.0013  # 0.13% = 0.0013 in decimal
    profit_margin = 0.0016  # 0.16% = 0.0016 in decimal
    roa = 0.0006  # 0.06% = 0.0006 in decimal

    print("TTD Profitability Debug:")
    print(f"ROE: {roe} ({roe*100:.3f}%)")
    print(f"Profit Margin: {profit_margin} ({profit_margin*100:.3f}%)")
    print(f"ROA: {roa} ({roa*100:.3f}%)")

    # Simulate scoring logic
    score = 0

    # Helper function to normalize percentage values
    def normalize_percentage(value):
        """Convert percentage to decimal if needed"""
        if value is None:
            return None
        # If value > 1, assume it's in percentage form, convert to decimal
        if abs(value) > 1:
            return value / 100
        return value

    # ROE scoring (more stringent)
    roe_norm = normalize_percentage(roe)
    print(f"\nROE normalized: {roe_norm}")
    if roe_norm is not None:
        if roe_norm > 0.20:
            score += 0.7
            print("ROE: +0.7 (>20%)")
        elif roe_norm > 0.15:
            score += 0.5
            print("ROE: +0.5 (>15%)")
        elif roe_norm > 0.10:
            score += 0.3
            print("ROE: +0.3 (>10%)")
        elif roe_norm > 0.05:
            score += 0.1
            print("ROE: +0.1 (>5%)")
        elif roe_norm < 0:
            score -= 0.8
            print("ROE: -0.8 (<0%)")
        else:  # Very low positive ROE (0-5%)
            score -= 0.3
            print("ROE: -0.3 (0-5%)")

    # Profit Margin scoring (more stringent)
    profit_margin_norm = normalize_percentage(profit_margin)
    print(f"Profit Margin normalized: {profit_margin_norm}")
    if profit_margin_norm is not None:
        if profit_margin_norm > 0.15:
            score += 0.7
            print("Profit Margin: +0.7 (>15%)")
        elif profit_margin_norm > 0.10:
            score += 0.5
            print("Profit Margin: +0.5 (>10%)")
        elif profit_margin_norm > 0.05:
            score += 0.3
            print("Profit Margin: +0.3 (>5%)")
        elif profit_margin_norm > 0.01:
            score += 0.1
            print("Profit Margin: +0.1 (>1%)")
        elif profit_margin_norm < 0:
            score -= 0.8
            print("Profit Margin: -0.8 (<0%)")
        else:  # Very low positive margin (0-1%)
            score -= 0.4
            print("Profit Margin: -0.4 (0-1%)")

    # ROA scoring (more stringent)
    roa_norm = normalize_percentage(roa)
    print(f"ROA normalized: {roa_norm}")
    if roa_norm is not None:
        if roa_norm > 0.08:
            score += 0.6
            print("ROA: +0.6 (>8%)")
        elif roa_norm > 0.05:
            score += 0.4
            print("ROA: +0.4 (>5%)")
        elif roa_norm > 0.02:
            score += 0.2
            print("ROA: +0.2 (>2%)")
        elif roa_norm > 0.005:
            score += 0.1
            print("ROA: +0.1 (>0.5%)")
        elif roa_norm < 0:
            score -= 0.6
            print("ROA: -0.6 (<0%)")
        else:  # Very low positive ROA (0-0.5%)
            score -= 0.3
            print("ROA: -0.3 (0-0.5%)")

    final_score = max(0, min(score, 2))
    print(f"\nTotal Score: {score}")
    print(f"Final Score (capped): {final_score}/2")

if __name__ == "__main__":
    debug_profitability_scoring()