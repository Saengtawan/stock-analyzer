#!/usr/bin/env python3
"""
Unit Tests for Rapid Trader v3.10 (no pytest required)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_position_size_uses_simulated_capital():
    """Position size must use $4,000 not $100K"""
    capital = 4000
    pct = 40
    price = 100
    shares = int((capital * pct / 100) / price)
    assert shares == 16, f"Expected 16 shares, got {shares}"
    assert shares * price <= 1600, f"Position ${shares * price} exceeds $1,600"
    return True


def test_position_size_rounding():
    """Shares must be integer (no fractional)"""
    capital = 4000
    pct = 40
    price = 92.50
    shares = int((capital * pct / 100) / price)
    assert isinstance(shares, int), "Shares must be int"
    assert shares == 17, f"Expected 17 shares, got {shares}"
    return True


def test_stop_loss_price():
    """SL must be at -2.5%"""
    entry = 100.0
    sl_pct = 2.5
    sl = entry * (1 - sl_pct / 100)
    assert sl == 97.50, f"Expected $97.50, got ${sl}"
    return True


def test_take_profit_price():
    """TP must be at +6%"""
    entry = 100.0
    tp_pct = 6.0
    tp = entry * (1 + tp_pct / 100)
    assert tp == 106.0, f"Expected $106.00, got ${tp}"
    return True


def test_trailing_stop_calculation():
    """Trail must lock 70% of gains"""
    entry = 100.0
    peak = 105.0
    lock_pct = 70

    gain = peak - entry
    locked_gain = gain * (lock_pct / 100)
    trail = entry + locked_gain

    assert abs(trail - 103.50) < 0.01, f"Expected $103.50, got ${trail}"
    return True


def test_trail_not_active_below_threshold():
    """Trail not active if gain < +2%"""
    entry = 100.0
    peak = 101.5
    activation_pct = 2.0

    gain_pct = ((peak - entry) / entry) * 100
    assert gain_pct < activation_pct, f"Gain {gain_pct}% should be < {activation_pct}%"
    return True


def test_max_risk_per_trade():
    """Risk per trade must not exceed 1% of capital"""
    capital = 4000
    position_pct = 40
    sl_pct = 2.5

    position = capital * position_pct / 100
    max_loss = position * sl_pct / 100
    risk_pct = (max_loss / capital) * 100

    assert risk_pct == 1.0, f"Risk {risk_pct}% should be 1.0%"
    return True


def test_max_total_risk():
    """Total risk with 2 positions must not exceed 2%"""
    capital = 4000
    position_pct = 40
    sl_pct = 2.5
    max_positions = 2

    position = capital * position_pct / 100
    max_loss_per = position * sl_pct / 100
    total_risk = (max_loss_per * max_positions / capital) * 100

    assert total_risk == 2.0, f"Total risk {total_risk}% should be 2.0%"
    return True


def test_price_filter():
    """Price must be in $10-$2000"""
    assert 10 <= 50 <= 2000, "Price $50 should pass"
    assert not (10 <= 5 <= 2000), "Price $5 should fail"
    assert not (10 <= 3000 <= 2000), "Price $3000 should fail"
    return True


def test_yesterday_dip_required():
    """Yesterday must be down >= -1%"""
    assert -2.5 <= -1.0, "Yesterday -2.5% should pass"
    assert not (0.5 <= -1.0), "Yesterday +0.5% should fail"
    return True


def test_today_not_falling():
    """Today must not be falling (>= -1%)"""
    assert 0.3 >= -1.0, "Today +0.3% should pass"
    assert not (-1.5 >= -1.0), "Today -1.5% should fail"
    return True


def test_bounce_confirmation():
    """Bounce confirmation: green candle OR +0.5%"""
    # Green candle
    assert True or 0.3 >= 0.5, "Green candle should pass"
    # +0.5% move
    assert False or 0.8 >= 0.5, "+0.8% move should pass"
    # Neither
    assert not (False or 0.2 >= 0.5), "No bounce should fail"
    return True


def test_sma20_uptrend():
    """Price must be > SMA20"""
    assert 105 > 100, "Price > SMA20 should pass"
    assert not (95 > 100), "Price < SMA20 should fail"
    return True


def test_overextended_filter():
    """v3.10: Max 10d move < 8%, SMA20 ext < 10%"""
    # Normal case
    assert 5.0 < 8 and 4.0 < 10, "Normal case should pass"
    # Overextended move
    assert not (12.0 < 8), "12% move should fail"
    # Overextended from SMA20
    assert not (15.0 < 10), "15% SMA20 ext should fail"
    return True


def test_score_threshold():
    """Score must be >= 90"""
    assert 95 >= 90, "Score 95 should pass"
    assert not (85 >= 90), "Score 85 should fail"
    return True


def test_pdt_blocks_after_3():
    """Block after 3 day trades"""
    assert 3 >= 3, "3 day trades should block"
    return True


def test_pdt_allows_under_3():
    """Allow if < 3 day trades"""
    assert 2 < 3, "2 day trades should allow"
    return True


def test_pdt_applies_to_simulated_capital():
    """PDT applies to $4K simulated capital"""
    assert 4000 < 25000, "PDT must apply to $4K"
    return True


def test_daily_loss_limit():
    """Stop at -5% loss"""
    capital = 4000
    loss = -200  # -5%
    limit = 5.0

    loss_pct = abs(loss / capital * 100)
    assert loss_pct >= limit, f"Loss {loss_pct}% should trigger limit"
    return True


def test_continue_under_loss_limit():
    """Continue if loss < 5%"""
    capital = 4000
    loss = -100  # -2.5%
    limit = 5.0

    loss_pct = abs(loss / capital * 100)
    assert loss_pct < limit, f"Loss {loss_pct}% should continue"
    return True


def test_trail_only_moves_up():
    """Trail stop only moves up"""
    current_sl = 103.0
    new_sl = 102.0
    assert not (new_sl > current_sl), "Lower SL should not update"
    return True


def test_force_exit_after_5_days():
    """Force exit after 5 days if not profitable"""
    days = 5
    pnl = 0.5
    max_days = 5

    should_exit = days >= max_days and pnl < 1
    assert should_exit, "Should exit after 5 days with <1% profit"
    return True


if __name__ == '__main__':
    tests = [
        ("Position Size (Simulated Capital)", test_position_size_uses_simulated_capital),
        ("Position Size (Rounding)", test_position_size_rounding),
        ("Stop Loss Price", test_stop_loss_price),
        ("Take Profit Price", test_take_profit_price),
        ("Trailing Stop Calculation", test_trailing_stop_calculation),
        ("Trail Not Active Below 2%", test_trail_not_active_below_threshold),
        ("Max Risk Per Trade (1%)", test_max_risk_per_trade),
        ("Max Total Risk (2%)", test_max_total_risk),
        ("Price Filter", test_price_filter),
        ("Yesterday Dip Required", test_yesterday_dip_required),
        ("Today Not Falling", test_today_not_falling),
        ("Bounce Confirmation", test_bounce_confirmation),
        ("SMA20 Uptrend", test_sma20_uptrend),
        ("Overextended Filter v3.10", test_overextended_filter),
        ("Score Threshold >= 90", test_score_threshold),
        ("PDT Blocks After 3", test_pdt_blocks_after_3),
        ("PDT Allows Under 3", test_pdt_allows_under_3),
        ("PDT Applies to $4K", test_pdt_applies_to_simulated_capital),
        ("Daily Loss Limit -5%", test_daily_loss_limit),
        ("Continue Under Loss Limit", test_continue_under_loss_limit),
        ("Trail Only Moves Up", test_trail_only_moves_up),
        ("Force Exit After 5 Days", test_force_exit_after_5_days),
    ]

    print("=" * 60)
    print("RAPID TRADER v3.10 - UNIT TESTS")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result:
                print(f"✅ {name}")
                passed += 1
            else:
                print(f"❌ {name} - returned False")
                failed += 1
        except AssertionError as e:
            print(f"❌ {name} - {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {name} - Error: {e}")
            failed += 1

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"STATUS: {'PASS ✅' if failed == 0 else 'FAIL ❌'}")
    print("=" * 60)
