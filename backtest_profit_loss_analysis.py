#!/usr/bin/env python3
"""
Backtest: วิเคราะห์ว่าการแพ้ทำให้กำไรหายไปเยอะมั้ย
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

def analyze_profit_loss_impact(target_pct=5.0, max_hold_days=30, test_period_months=6):
    """
    วิเคราะห์ว่าการแพ้ส่งผลต่อกำไรรวมยังไง
    """

    print("=" * 80)
    print(f"DEEP ANALYSIS: Profit vs Loss Impact")
    print("=" * 80)
    print()

    # Test symbols
    symbols = [
        'NVDA', 'AMD', 'AVGO', 'PLTR', 'SNOW', 'CRWD',
        'MRNA', 'BNTX', 'VRTX', 'REGN',
        'TSLA', 'RIVN', 'LCID', 'ENPH',
        'SQ', 'COIN', 'SOFI',
        'SHOP', 'NET', 'DDOG', 'ZS', 'MDB'
    ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * test_period_months)

    all_trades = []
    winning_trades = []
    losing_trades = []

    # Collect all trades
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < max_hold_days:
                continue

            # Simulate entries every 7 days
            for i in range(0, len(hist) - max_hold_days, 7):
                entry_price = hist['Close'].iloc[i]

                # Track for max_hold_days
                hit_target = False
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                max_gain = 0
                max_loss = 0

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_price = hist['Close'].iloc[i + day]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    if gain_pct > max_gain:
                        max_gain = gain_pct
                    if gain_pct < max_loss:
                        max_loss = gain_pct

                    # Hit target
                    if gain_pct >= target_pct and not hit_target:
                        hit_target = True
                        exit_price = current_price
                        exit_day = day
                        break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'return_pct': final_return,
                    'hit_target': hit_target,
                    'exit_day': exit_day,
                    'max_gain': max_gain,
                    'max_loss': max_loss
                }

                all_trades.append(trade)

                if hit_target:
                    winning_trades.append(trade)
                else:
                    losing_trades.append(trade)

        except Exception as e:
            continue

    # Analysis
    print(f"Total Trades: {len(all_trades)}")
    print(f"Winners: {len(winning_trades)} ({len(winning_trades)/len(all_trades)*100:.1f}%)")
    print(f"Losers: {len(losing_trades)} ({len(losing_trades)/len(all_trades)*100:.1f}%)")
    print()

    # Winning trades analysis
    print("=" * 80)
    print("🟢 WINNING TRADES (Hit 5%+ Target)")
    print("=" * 80)
    print()

    winning_returns = [t['return_pct'] for t in winning_trades]
    avg_win = np.mean(winning_returns)
    median_win = np.median(winning_returns)
    max_win = np.max(winning_returns)
    min_win = np.min(winning_returns)

    print(f"Average Win:  {avg_win:+.2f}%")
    print(f"Median Win:   {median_win:+.2f}%")
    print(f"Biggest Win:  {max_win:+.2f}%")
    print(f"Smallest Win: {min_win:+.2f}%")
    print()

    # Losing trades analysis
    print("=" * 80)
    print("🔴 LOSING TRADES (Didn't Hit 5% Target)")
    print("=" * 80)
    print()

    losing_returns = [t['return_pct'] for t in losing_trades]
    avg_loss = np.mean(losing_returns)
    median_loss = np.median(losing_returns)
    max_loss = np.max(losing_returns)  # Least loss
    min_loss = np.min(losing_returns)  # Biggest loss

    print(f"Average Loss:  {avg_loss:+.2f}%")
    print(f"Median Loss:   {median_loss:+.2f}%")
    print(f"Smallest Loss: {max_loss:+.2f}%")
    print(f"Biggest Loss:  {min_loss:+.2f}%")
    print()

    # Analyze WHY they lost
    print("=" * 80)
    print("🔍 WHY DID THEY LOSE?")
    print("=" * 80)
    print()

    # Category 1: Got close but didn't make it
    almost_won = [t for t in losing_trades if t['max_gain'] >= 4.0]
    print(f"1. Almost Won (4%+ peak but didn't hold):")
    print(f"   {len(almost_won)} trades ({len(almost_won)/len(losing_trades)*100:.1f}% of losers)")
    if almost_won:
        avg_peak = np.mean([t['max_gain'] for t in almost_won])
        avg_final = np.mean([t['return_pct'] for t in almost_won])
        print(f"   Average peak: {avg_peak:+.2f}%")
        print(f"   Average final: {avg_final:+.2f}%")
        print(f"   → ปัญหา: EXIT TIMING - ถือนานเกิน, ควร exit ที่ 4%+")
    print()

    # Category 2: Small loss (holding period issue)
    small_loss = [t for t in losing_trades if -5 < t['return_pct'] < 4.0]
    print(f"2. Small Loss/Flat (-5% to +4%):")
    print(f"   {len(small_loss)} trades ({len(small_loss)/len(losing_trades)*100:.1f}% of losers)")
    if small_loss:
        avg_return = np.mean([t['return_pct'] for t in small_loss])
        print(f"   Average return: {avg_return:+.2f}%")
        print(f"   → ปัญหา: ไม่มี MOMENTUM - หุ้นไม่เคลื่อนไหว")
    print()

    # Category 3: Big loss (bad trades)
    big_loss = [t for t in losing_trades if t['return_pct'] <= -5.0]
    print(f"3. Big Loss (<-5%):")
    print(f"   {len(big_loss)} trades ({len(big_loss)/len(losing_trades)*100:.1f}% of losers)")
    if big_loss:
        avg_loss_big = np.mean([t['return_pct'] for t in big_loss])
        worst = np.min([t['return_pct'] for t in big_loss])
        print(f"   Average loss: {avg_loss_big:+.2f}%")
        print(f"   Worst loss: {worst:+.2f}%")
        print(f"   → ปัญหา: BAD ENTRY - เข้าผิดจังหวะ หรือหุ้นแย่")
    print()

    # R:R Analysis
    print("=" * 80)
    print("💰 PROFIT/LOSS RATIO & EXPECTED VALUE")
    print("=" * 80)
    print()

    win_rate = len(winning_trades) / len(all_trades)
    loss_rate = len(losing_trades) / len(all_trades)

    print(f"Win Rate:  {win_rate*100:.1f}%")
    print(f"Loss Rate: {loss_rate*100:.1f}%")
    print()

    print(f"Average Win:  {avg_win:+.2f}%")
    print(f"Average Loss: {avg_loss:+.2f}%")
    print()

    # R:R Ratio
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"Reward:Risk Ratio: {rr_ratio:.2f}:1")

    if rr_ratio > 1:
        print(f"   ✅ GOOD - กำไรเฉลี่ย {rr_ratio:.1f}x มากกว่าขาดทุนเฉลี่ย")
    else:
        print(f"   ⚠️  BAD - กำไรเฉลี่ยน้อยกว่าขาดทุนเฉลี่ย")
    print()

    # Expected Value (EV)
    ev = (win_rate * avg_win) + (loss_rate * avg_loss)
    print(f"Expected Value (EV): {ev:+.2f}%")

    if ev > 2:
        print(f"   ✅ EXCELLENT - คาดหวังกำไร {ev:.2f}% ต่อ trade")
    elif ev > 1:
        print(f"   ✅ GOOD - คาดหวังกำไร {ev:.2f}% ต่อ trade")
    elif ev > 0:
        print(f"   ⚠️  MARGINAL - คาดหวังกำไรเพียง {ev:.2f}% ต่อ trade")
    else:
        print(f"   ❌ NEGATIVE - คาดหวังขาดทุน {ev:.2f}% ต่อ trade")
    print()

    # Net Profit Simulation
    print("=" * 80)
    print("📊 NET PROFIT SIMULATION (100 Trades, $1000 each)")
    print("=" * 80)
    print()

    num_trades = 100
    capital_per_trade = 1000

    expected_wins = int(num_trades * win_rate)
    expected_losses = int(num_trades * loss_rate)

    total_win_profit = expected_wins * capital_per_trade * (avg_win / 100)
    total_loss_amount = expected_losses * capital_per_trade * (avg_loss / 100)
    net_profit = total_win_profit + total_loss_amount  # avg_loss is negative

    print(f"Expected Winners: {expected_wins} trades")
    print(f"  Total Win Profit: ${total_win_profit:,.2f}")
    print()

    print(f"Expected Losers: {expected_losses} trades")
    print(f"  Total Loss Amount: ${total_loss_amount:,.2f}")
    print()

    print(f"NET PROFIT: ${net_profit:,.2f}")
    print(f"ROI: {(net_profit / (num_trades * capital_per_trade)) * 100:+.2f}%")
    print()

    # Loss Impact
    loss_impact_pct = abs(total_loss_amount / total_win_profit) * 100
    print(f"Loss Impact: {loss_impact_pct:.1f}% of total wins")

    if loss_impact_pct < 30:
        print(f"   ✅ EXCELLENT - ขาดทุนน้อยมาก ({loss_impact_pct:.1f}%)")
    elif loss_impact_pct < 50:
        print(f"   ✅ GOOD - ขาดทุนปานกลาง ({loss_impact_pct:.1f}%)")
    elif loss_impact_pct < 70:
        print(f"   ⚠️  MODERATE - ขาดทุนค่อนข้างมาก ({loss_impact_pct:.1f}%)")
    else:
        print(f"   ❌ HIGH - ขาดทุนมาก ({loss_impact_pct:.1f}%)")
    print()

    # Kelly Criterion
    print("=" * 80)
    print("📐 KELLY CRITERION (Position Sizing)")
    print("=" * 80)
    print()

    # Kelly = (Win% * RR - Loss%) / RR
    kelly = (win_rate * rr_ratio - loss_rate) / rr_ratio if rr_ratio > 0 else 0
    kelly_pct = kelly * 100

    print(f"Optimal Position Size (Kelly): {kelly_pct:.1f}% of capital")

    if kelly_pct > 25:
        print(f"   ⚠️  Very aggressive - recommend max 25%")
        kelly_pct = 25
    elif kelly_pct > 15:
        print(f"   ✅ Aggressive but manageable")
    elif kelly_pct > 5:
        print(f"   ✅ Moderate - safe for most traders")
    else:
        print(f"   ⚠️  Very conservative - edge may be too small")

    print()
    print(f"Recommendation: Use {kelly_pct/2:.1f}% - {kelly_pct:.1f}% per position")
    print(f"   (Half Kelly to Full Kelly for safety)")
    print()

    # Top losers by symbol
    print("=" * 80)
    print("🔻 WORST PERFORMING SYMBOLS (Most Losses)")
    print("=" * 80)
    print()

    # Count losses by symbol
    from collections import Counter
    loser_symbols = Counter([t['symbol'] for t in losing_trades])

    print("Symbol  | Losses | Avg Loss")
    print("-" * 35)
    for symbol, count in loser_symbols.most_common(10):
        symbol_losses = [t['return_pct'] for t in losing_trades if t['symbol'] == symbol]
        avg_symbol_loss = np.mean(symbol_losses)
        print(f"{symbol:7} | {count:6} | {avg_symbol_loss:+.2f}%")

    print()

    # Summary
    print("=" * 80)
    print("💡 KEY FINDINGS")
    print("=" * 80)
    print()

    print(f"1. Win Rate: {win_rate*100:.1f}% (Excellent!)")
    print(f"2. R:R Ratio: {rr_ratio:.2f}:1 ({'Good' if rr_ratio > 1 else 'Needs Improvement'})")
    print(f"3. Expected Value: {ev:+.2f}% per trade")
    print(f"4. Loss Impact: {loss_impact_pct:.1f}% of wins")
    print()

    if ev > 1 and loss_impact_pct < 50:
        print("✅ VERDICT: ระบบดีมาก!")
        print("   - กำไรรวมมากกว่าขาดทุนอย่างชัดเจน")
        print("   - การแพ้ไม่กินกำไรมาก")
        print("   - คุ้มค่าที่จะเทรด")
    elif ev > 0 and loss_impact_pct < 70:
        print("⚠️  VERDICT: ระบบใช้ได้ แต่ต้องระวัง")
        print("   - กำไรรวมยังเป็นบวก")
        print("   - แต่ขาดทุนกินกำไรไปพอสมควร")
        print("   - ควรปรับปรุง exit strategy")
    else:
        print("❌ VERDICT: ระบบต้องปรับปรุง")
        print("   - ขาดทุนกินกำไรมากเกินไป")
        print("   - ต้องปรับ filters หรือ exit rules")

    print()


if __name__ == "__main__":
    analyze_profit_loss_impact(
        target_pct=5.0,
        max_hold_days=30,
        test_period_months=6
    )
