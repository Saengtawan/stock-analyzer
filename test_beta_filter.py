#!/usr/bin/env python3
"""
Test Beta/Volatility Filter - v6.32

Tests the beta filter with known stocks to verify logic works correctly.
"""
import sys
import os
sys.path.insert(0, 'src')

from config.strategy_config import RapidRotationConfig
import yfinance as yf


def test_beta_filter():
    """Test beta filter logic with sample stocks"""

    # Load config
    cfg = RapidRotationConfig.from_yaml('config/trading.yaml')

    print("=" * 70)
    print("  Beta/Volatility Filter Test - v6.32")
    print("=" * 70)
    print()
    print(f"Config:")
    print(f"  Enabled: {cfg.beta_filter_enabled}")
    print(f"  Log Only Mode: {cfg.beta_filter_log_only}")
    print(f"  Min Beta: {cfg.beta_filter_min_beta}")
    print(f"  Min ATR%: {cfg.beta_filter_min_atr_pct}")
    print()

    # Test stocks
    test_stocks = [
        # Should FAIL (low volatility defensive)
        ('KHC', 'Kraft Heinz', 'Consumer Def', 0.047, 3.19),
        ('PG', 'Procter & Gamble', 'Consumer Def', 0.12, 2.8),
        ('KO', 'Coca-Cola', 'Consumer Def', 0.21, 3.2),

        # Should PASS (high beta)
        ('NVDA', 'Nvidia', 'Technology', 1.67, 8.5),
        ('TSLA', 'Tesla', 'Auto', 2.01, 12.3),
        ('PLTR', 'Palantir', 'Technology', 1.43, 9.8),

        # Should PASS (high ATR)
        ('XOM', 'Exxon', 'Energy', 0.42, 5.2),

        # Borderline (should FAIL - both below threshold)
        ('T', 'AT&T', 'Telecom', 0.33, 2.5),
    ]

    print("Testing Stocks:")
    print("-" * 70)
    print(f"{'Symbol':<8} {'Name':<20} {'Beta':<8} {'ATR%':<8} {'Result':<12} {'Reason'}")
    print("-" * 70)

    pass_count = 0
    fail_count = 0

    for symbol, name, sector, beta, atr in test_stocks:
        # Check filter logic
        passed = False
        reason = []

        if beta >= cfg.beta_filter_min_beta:
            passed = True
            reason.append(f"beta={beta:.2f}")

        if atr >= cfg.beta_filter_min_atr_pct:
            passed = True
            reason.append(f"atr={atr:.1f}%")

        if not passed:
            result = "❌ REJECT"
            fail_count += 1
            reason_str = f"beta={beta:.3f}<{cfg.beta_filter_min_beta}, atr={atr:.1f}%<{cfg.beta_filter_min_atr_pct}%"
        else:
            result = "✅ PASS"
            pass_count += 1
            reason_str = "+".join(reason)

        print(f"{symbol:<8} {name:<20} {beta:<8.3f} {atr:<8.1f} {result:<12} {reason_str}")

    print("-" * 70)
    print(f"\nResults: {pass_count} passed, {fail_count} rejected")
    print()

    # Live test with current data
    print("\n" + "=" * 70)
    print("  Live Test: Fetching Current Beta from Yahoo Finance")
    print("=" * 70)
    print()

    live_test = ['KHC', 'NVDA', 'TSLA', 'PG']
    print(f"{'Symbol':<8} {'Beta':<10} {'Result':<12} {'Reason'}")
    print("-" * 70)

    for symbol in live_test:
        try:
            ticker = yf.Ticker(symbol)
            beta = ticker.info.get('beta', None)

            if beta is None:
                print(f"{symbol:<8} {'N/A':<10} {'⚠️ UNKNOWN':<12} No beta data")
                continue

            if beta >= cfg.beta_filter_min_beta:
                result = "✅ PASS"
                reason = f"beta={beta:.3f}>={cfg.beta_filter_min_beta}"
            else:
                result = "❌ REJECT"
                reason = f"beta={beta:.3f}<{cfg.beta_filter_min_beta}"

            print(f"{symbol:<8} {beta:<10.3f} {result:<12} {reason}")

        except Exception as e:
            print(f"{symbol:<8} {'ERROR':<10} {'⚠️ FAILED':<12} {str(e)[:40]}")

    print()
    print("=" * 70)
    print("Test complete!")
    print()
    print("Next Steps:")
    print("1. Monitor logs for 'BETA_FILTER_TEST' rejections (1 week)")
    print("2. Analyze: Are rejections correct? Any false positives?")
    print("3. If validated → set beta_filter_log_only: false to enforce")
    print("=" * 70)


if __name__ == "__main__":
    test_beta_filter()
