#!/usr/bin/env python3
"""
v4: AGGRESSIVE LOSS PROTECTION
================================

Problem: Loss ยังเยอะเกิน (75% ของกำไร)
Solution: ตัด Loss เร็วมาก!

Strategy:
1. Tighter Stop: -4% (แทน -6%)
2. Early Exit Signals: Day 2+ (แทน Day 5+)
3. No Movement Stop: Exit ถ้า 3 วันแล้วยัง < 1%
4. Volume Dry: Exit ทันทีถ้า volume หาย
5. Micro Breakdown: ทะลุ SMA20 แม้แค่ -0.5%

Goal: Avg Loss -2.5% to -3.0%
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
from loguru import logger

def calculate_sma(prices, period=20):
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def check_lower_lows(prices, lookback=5):
    if len(prices) < lookback * 2:
        return False
    recent_low = np.min(prices[-lookback:])
    previous_low = np.min(prices[-lookback*2:-lookback])
    return recent_low < previous_low

def get_real_fundamentals(ticker_obj):
    try:
        info = ticker_obj.info
        return {
            'pe_ratio': info.get('trailingPE', info.get('forwardPE', None)),
            'pb_ratio': info.get('priceToBook', None),
            'revenue_growth': info.get('revenueGrowth', None),
            'profit_margin': info.get('profitMargins', None),
            'roe': info.get('returnOnEquity', None),
            'debt_to_equity': info.get('debtToEquity', None),
            'market_cap': info.get('marketCap', 0)
        }
    except:
        return None

def get_sector_regime(symbol):
    sector_map = {
        'NVDA': 'XLK', 'AMD': 'XLK', 'AVGO': 'XLK', 'QCOM': 'XLK', 'MU': 'XLK',
        'PLTR': 'XLK', 'SNOW': 'XLK', 'CRWD': 'XLK', 'ZS': 'XLK', 'NET': 'XLK',
        'DDOG': 'XLK', 'MDB': 'XLK', 'MRNA': 'XLV', 'BNTX': 'XLV', 'VRTX': 'XLV',
        'REGN': 'XLV', 'GILD': 'XLV', 'TSLA': 'XLY', 'SHOP': 'XLY', 'MELI': 'XLY',
        'SQ': 'XLF', 'COIN': 'XLF', 'SOFI': 'XLF', 'RIVN': 'XLE', 'LCID': 'XLE'
    }
    sector_etf = sector_map.get(symbol, 'SPY')
    try:
        etf = yf.Ticker(sector_etf)
        hist = etf.history(period='3mo')
        if hist.empty or len(hist) < 50:
            return None
        close_prices = hist['Close'].values
        sma20 = calculate_sma(close_prices, 20)
        sma50 = calculate_sma(close_prices, 50)
        if not sma20 or not sma50:
            return None
        current_price = close_prices[-1]
        if current_price > sma20 and current_price > sma50 and sma20 > sma50:
            return 'BULL'
        elif current_price < sma20 and current_price < sma50 and sma20 < sma50:
            return 'BEAR'
        else:
            return 'SIDEWAYS'
    except:
        return None

def calculate_entry_score(hist, ticker_obj):
    """Same as v2"""
    if len(hist) < 50:
        return None

    close_prices = hist['Close'].values
    volumes = hist['Volume'].values
    fundamentals = get_real_fundamentals(ticker_obj)

    if not fundamentals:
        return None

    current_price = close_prices[-1]
    sma20 = calculate_sma(close_prices, 20)
    sma50 = calculate_sma(close_prices, 50)
    rsi = calculate_rsi(close_prices, 14)

    price_change_5d = ((close_prices[-1] - close_prices[-6]) / close_prices[-6]) * 100 if len(close_prices) > 5 else 0
    price_change_20d = ((close_prices[-1] - close_prices[-21]) / close_prices[-21]) * 100 if len(close_prices) > 20 else 0

    avg_volume = np.mean(volumes[-20:]) if len(volumes) > 20 else np.mean(volumes)
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1

    recent_high = np.max(close_prices[-20:]) if len(close_prices) > 20 else current_price

    scores = {}

    # Fundamental
    fund_score = 0
    if fundamentals['revenue_growth'] is not None:
        revenue_growth = fundamentals['revenue_growth'] * 100
        fund_score += 4 if revenue_growth > 20 else 3 if revenue_growth > 10 else 2 if revenue_growth > 0 else 1
    else:
        fund_score += 2

    if fundamentals['profit_margin'] is not None:
        margin = fundamentals['profit_margin'] * 100
        fund_score += 3 if margin > 20 else 2 if margin > 10 else 1 if margin > 0 else 0
    else:
        fund_score += 1

    if fundamentals['roe'] is not None:
        roe = fundamentals['roe'] * 100
        fund_score += 3 if roe > 15 else 2 if roe > 5 else 1 if roe > 0 else 0
    else:
        fund_score += 1

    scores['fundamental'] = min(fund_score, 10)

    # Technical
    tech_score = 0
    if rsi and sma20:
        tech_score += 5 if 40 <= rsi <= 70 else 2 if rsi > 70 else 3
        if current_price > sma20:
            tech_score += 3
        if sma50 and current_price > sma50:
            tech_score += 2
    scores['technical'] = min(tech_score, 10)

    # Momentum
    momentum_score = 0
    if price_change_5d > 0:
        momentum_score += 3
    if price_change_20d > 0:
        momentum_score += 3
    if volume_ratio > 1.2:
        momentum_score += 4
    scores['momentum'] = min(momentum_score, 10)

    # Valuation
    val_score = 0
    if fundamentals['pe_ratio'] is not None:
        pe = fundamentals['pe_ratio']
        val_score += 5 if pe < 15 else 4 if pe < 25 else 3 if pe < 35 else 2 if pe < 50 else 1
    else:
        val_score += 3

    if fundamentals['pb_ratio'] is not None:
        pb = fundamentals['pb_ratio']
        val_score += 3 if pb < 2 else 2 if pb < 5 else 1
    else:
        val_score += 1

    if fundamentals['debt_to_equity'] is not None:
        de = fundamentals['debt_to_equity'] / 100
        val_score += 2 if de < 0.5 else 1 if de < 1.5 else 0
    else:
        val_score += 1

    scores['valuation'] = min(val_score, 10)
    scores['sentiment'] = 5.0

    # Catalyst
    catalyst_score = 0
    if current_price >= recent_high * 0.98:
        catalyst_score += 5
    if volume_ratio > 1.5:
        catalyst_score += 5
    scores['catalyst'] = min(catalyst_score, 10)

    total_score = sum(scores.values()) / len(scores)
    above_5 = sum(1 for s in scores.values() if s >= 5)
    confidence = (above_5 / len(scores)) * 10

    return {
        'total_score': total_score,
        'layer_scores': scores,
        'confidence': confidence,
        'rsi': rsi,
        'sma20': sma20
    }

def should_enter_trade(score_data, sector_regime, min_score=5.0, min_confidence=3.5):
    """Same as v2"""
    if not score_data:
        return False, "no_score_data"
    if sector_regime == 'BEAR':
        return False, "sector_BEAR"
    if score_data['total_score'] < min_score:
        return False, "low_total_score"
    if score_data['confidence'] < min_confidence:
        return False, "low_confidence"
    if score_data['layer_scores']['technical'] < 4:
        return False, "low_technical"
    if score_data['layer_scores']['fundamental'] < 4:
        return False, "low_fundamental"
    return True, "PASSED"

def backtest_v4_aggressive_loss_protection(
    symbols_universe=None,
    test_period_months=6,
    target_pct=4.0,
    stop_loss_pct=-4.0,  # v4: TIGHTER! -4% แทน -6%
    max_hold_days=30
):
    """
    v4: AGGRESSIVE LOSS PROTECTION
    """

    print("=" * 80)
    print("BACKTEST v4: AGGRESSIVE LOSS PROTECTION")
    print("=" * 80)
    print()
    print("Goal: ลด Avg Loss จาก -4.28% → -2.5% ถึง -3.0%")
    print()
    print("Entry: Same as v2 (52.7% success)")
    print()
    print("Exit (AGGRESSIVE):")
    print(f"  1. Target: {target_pct}%")
    print(f"  2. Hard Stop: {stop_loss_pct}% 🆕 (TIGHTER!)")
    print(f"  3. No Movement: Exit ถ้า Day 3 ยัง < 1% 🆕")
    print(f"  4. SIGNAL SMA20: Day 2+, > -0.5% below 🆕 (SENSITIVE)")
    print(f"  5. SIGNAL RSI: Day 2+, < 45 🆕 (EARLY)")
    print(f"  6. SIGNAL Volume Dry: < 0.8x 🆕")
    print(f"  7. SIGNAL Lower Lows: Day 5+ (earlier)")
    print(f"  8. Trailing Stop: -4% from peak")
    print()

    if not symbols_universe:
        symbols_universe = [
            'NVDA', 'AMD', 'AVGO', 'QCOM', 'MU',
            'PLTR', 'SNOW', 'CRWD', 'ZS', 'NET', 'DDOG', 'MDB',
            'MRNA', 'BNTX', 'VRTX', 'REGN', 'GILD',
            'TSLA', 'RIVN', 'LCID',
            'SQ', 'COIN', 'SOFI',
            'SHOP', 'MELI'
        ]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * test_period_months)

    all_trades = []
    entry_rejections = {}
    exit_reasons_count = {}

    print(f"📊 Backtesting {len(symbols_universe)} symbols...")
    print()

    for symbol in symbols_universe:
        try:
            print(f"Processing {symbol}...", end=" ")

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date - timedelta(days=60), end=end_date)

            if hist.empty or len(hist) < max_hold_days + 50:
                print("❌ No data")
                entry_rejections['no_data'] = entry_rejections.get('no_data', 0) + 1
                continue

            sector_regime = get_sector_regime(symbol)
            entries_found = 0

            for i in range(50, len(hist) - max_hold_days, 7):
                hist_at_entry = hist.iloc[:i+1]
                score_data = calculate_entry_score(hist_at_entry, ticker)

                if not score_data:
                    entry_rejections['no_score_data'] = entry_rejections.get('no_score_data', 0) + 1
                    continue

                should_enter, reason = should_enter_trade(score_data, sector_regime)

                if not should_enter:
                    entry_rejections[reason] = entry_rejections.get(reason, 0) + 1
                    continue

                # ENTER TRADE
                entry_price = hist['Close'].iloc[i]
                entry_volume_ma = np.mean(hist['Volume'].iloc[i-19:i+1].values) if i >= 19 else hist['Volume'].iloc[i]

                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                exit_reason = 'MAX_HOLD'
                peak_price = entry_price

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_idx = i + day
                    current_price = hist['Close'].iloc[current_idx]
                    current_volume = hist['Volume'].iloc[current_idx]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    if current_price > peak_price:
                        peak_price = current_price

                    peak_gain = ((peak_price - entry_price) / entry_price) * 100

                    # Priority 1: Hard Stop (v4: -4%!)
                    if gain_pct <= stop_loss_pct:
                        exit_reason = 'HARD_STOP'
                        exit_price = current_price
                        exit_day = day
                        break

                    # Priority 2: Target Hit
                    if gain_pct >= target_pct:
                        exit_reason = 'TARGET_HIT'
                        exit_price = current_price
                        exit_day = day
                        break

                    # v4 Priority 3: NO MOVEMENT STOP (NEW!)
                    if day == 3 and gain_pct < 1.0:
                        exit_reason = 'NO_MOVEMENT'
                        exit_price = current_price
                        exit_day = day
                        break

                    # Priority 4: Trailing Stop (v4: -4%)
                    if day >= 5:
                        drawdown = ((current_price - peak_price) / peak_price) * 100
                        if drawdown < -4.0:
                            exit_reason = 'TRAILING_STOP'
                            exit_price = current_price
                            exit_day = day
                            break

                    # v4 AGGRESSIVE SIGNALS (from Day 2!)
                    price_history = hist['Close'].iloc[:current_idx+1].values

                    if day >= 2:
                        # Signal 1: SMA20 Break (VERY SENSITIVE: -0.5%)
                        if len(price_history) >= 20:
                            sma20 = calculate_sma(price_history, 20)
                            if sma20 is not None and current_price < sma20:
                                distance_pct = ((current_price - sma20) / sma20) * 100
                                if distance_pct < -0.5:  # v4: Very sensitive
                                    exit_reason = 'SIGNAL_SMA20_BREAK'
                                    exit_price = current_price
                                    exit_day = day
                                    break

                        # Signal 2: RSI Weak (v4: < 45, earlier warning)
                        if len(price_history) >= 15:
                            rsi = calculate_rsi(price_history, 14)
                            if rsi is not None and rsi < 45:
                                exit_reason = 'SIGNAL_WEAK_RSI'
                                exit_price = current_price
                                exit_day = day
                                break

                    # Signal 3: Volume Dry (Day 3+)
                    if day >= 3:
                        volume_history = hist['Volume'].iloc[current_idx-19:current_idx+1].values if current_idx >= 19 else hist['Volume'].iloc[:current_idx+1].values
                        current_volume_ma = np.mean(volume_history)
                        volume_ratio = current_volume / current_volume_ma if current_volume_ma > 0 else 1

                        if volume_ratio < 0.8:  # v4: Volume dried up
                            exit_reason = 'SIGNAL_VOLUME_DRY'
                            exit_price = current_price
                            exit_day = day
                            break

                    # Signal 4: Lower Lows (Day 5+, earlier)
                    if day >= 5 and len(price_history) >= 10:
                        if check_lower_lows(price_history, lookback=5):
                            if gain_pct < 2.0:
                                exit_reason = 'SIGNAL_LOWER_LOWS'
                                exit_price = current_price
                                exit_day = day
                                break

                    # Signal 5: Failed Breakout
                    if peak_gain >= 3.0 and gain_pct < 0.5:
                        exit_reason = 'SIGNAL_FAILED_BREAKOUT'
                        exit_price = current_price
                        exit_day = day
                        break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': hist.index[i],
                    'return_pct': final_return,
                    'exit_reason': exit_reason,
                    'exit_day': exit_day,
                    'peak_gain': peak_gain,
                    'entry_score': score_data['total_score'],
                    'entry_confidence': score_data['confidence']
                }

                all_trades.append(trade)
                exit_reasons_count[exit_reason] = exit_reasons_count.get(exit_reason, 0) + 1
                entries_found += 1

            print(f"✅ {entries_found} entries")

        except Exception as e:
            print(f"❌ Error: {e}")
            continue

    # === ANALYSIS ===
    total = len(all_trades)

    if total == 0:
        print("\n❌ NO TRADES!")
        return None

    winners = [t for t in all_trades if t['return_pct'] >= target_pct]
    losers = [t for t in all_trades if t['return_pct'] < target_pct]

    print()
    print("=" * 80)
    print("📊 RESULTS v4 (AGGRESSIVE LOSS PROTECTION)")
    print("=" * 80)
    print()

    print(f"Total Trades: {total}")
    print(f"Winners: {len(winners)} ({len(winners)/total*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/total*100:.1f}%)")
    print()

    # Entry Quality
    avg_entry_score = np.mean([t['entry_score'] for t in all_trades])
    avg_entry_confidence = np.mean([t['entry_confidence'] for t in all_trades])

    total_rejections = sum(entry_rejections.values())
    print(f"Entry Success: {total}/{total + total_rejections} ({total/(total + total_rejections)*100:.1f}%)")
    print()

    # Exit Breakdown
    print("=" * 80)
    print("🚪 EXIT REASONS")
    print("=" * 80)
    print()

    for reason, count in sorted(exit_reasons_count.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total) * 100
        avg_return = np.mean([t['return_pct'] for t in all_trades if t['exit_reason'] == reason])
        avg_day = np.mean([t['exit_day'] for t in all_trades if t['exit_reason'] == reason])
        emoji = '🎯' if reason == 'TARGET_HIT' else '⚠️' if 'STOP' in reason else '📊' if 'SIGNAL' in reason else '⏳'
        print(f"{emoji} {reason:25} | {count:3} ({pct:5.1f}%) | Avg: {avg_return:+6.2f}% | Day: {avg_day:4.1f}")

    print()

    # Performance
    winning_returns = [t['return_pct'] for t in winners]
    losing_returns = [t['return_pct'] for t in losers]

    avg_win = np.mean(winning_returns) if winning_returns else 0
    avg_loss = np.mean(losing_returns) if losing_returns else 0
    worst_loss = np.min([t['return_pct'] for t in all_trades]) if all_trades else 0
    best_win = np.max([t['return_pct'] for t in all_trades]) if all_trades else 0

    print("=" * 80)
    print("💰 PERFORMANCE")
    print("=" * 80)
    print()

    print(f"Average Win:   {avg_win:+.2f}%")
    print(f"Average Loss:  {avg_loss:+.2f}%")
    print(f"Best Win:      {best_win:+.2f}%")
    print(f"Worst Loss:    {worst_loss:+.2f}%")
    print()

    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"Reward:Risk Ratio: {rr_ratio:.2f}:1")
    print()

    win_rate = len(winners) / total
    loss_rate = len(losers) / total
    ev = (win_rate * avg_win) + (loss_rate * avg_loss)

    print(f"Expected Value: {ev:+.2f}%")
    print()

    # Net Profit
    print("=" * 80)
    print("💵 NET PROFIT (100 Trades × $1000)")
    print("=" * 80)
    print()

    expected_winners = int(100 * win_rate)
    expected_losers = int(100 * loss_rate)

    total_win_profit = expected_winners * 1000 * (avg_win / 100)
    total_loss = expected_losers * 1000 * (avg_loss / 100)
    net_profit = total_win_profit + total_loss

    print(f"Winners: {expected_winners} trades → ${total_win_profit:,.2f}")
    print(f"Losers:  {expected_losers} trades → ${total_loss:,.2f}")
    print(f"NET PROFIT: ${net_profit:,.2f}")
    print()

    loss_impact = abs(total_loss / total_win_profit) * 100 if total_win_profit > 0 else 0
    print(f"Loss Impact: {loss_impact:.1f}% of wins")
    print()

    # Comparison
    print("=" * 80)
    print("📊 IMPROVEMENT: Target 4% Base → v4 Aggressive")
    print("=" * 80)
    print()

    print(f"{'Metric':<25} | {'Base (4%)':<15} | {'v4 Aggressive':<15} | {'Target':<15}")
    print("-" * 80)
    print(f"{'Win Rate':<25} | {'46.1%':<15} | {f'{win_rate*100:.1f}%':<15} | {'~45%':<15}")
    print(f"{'Avg Loss':<25} | {'-4.28%':<15} | {f'{avg_loss:+.2f}%':<15} | {'-2.5 to -3.0%':<15}")
    print(f"{'Loss Impact':<25} | {'75.6%':<15} | {f'{loss_impact:.1f}%':<15} | {'< 50%':<15}")
    print(f"{'R:R Ratio':<25} | {'1.52:1':<15} | {f'{rr_ratio:.2f}:1':<15} | {'≥ 1.5:1':<15}")
    print(f"{'Net Profit':<25} | {'$734':<15} | {f'${net_profit:,.0f}':<15} | {'> $734':<15}")
    print()

    # Verdict
    print("=" * 80)
    print("🎯 VERDICT")
    print("=" * 80)
    print()

    improvements = []
    if avg_loss >= -3.0:
        improvements.append(f"✅ Avg Loss: {avg_loss:+.2f}% (TARGET MET!)")
    elif avg_loss >= -3.5:
        improvements.append(f"⚠️ Avg Loss: {avg_loss:+.2f}% (close to target)")
    else:
        improvements.append(f"❌ Avg Loss: {avg_loss:+.2f}% (need < -3%)")

    if loss_impact < 50:
        improvements.append(f"✅ Loss Impact: {loss_impact:.1f}% (TARGET MET!)")
    elif loss_impact < 60:
        improvements.append(f"⚠️ Loss Impact: {loss_impact:.1f}% (close)")
    else:
        improvements.append(f"❌ Loss Impact: {loss_impact:.1f}% (need < 50%)")

    if net_profit > 734:
        improvements.append(f"✅ Net Profit: ${net_profit:,.0f} (BETTER!)")

    for imp in improvements:
        print(f"   {imp}")

    print()

    return {
        'total_trades': total,
        'win_rate': win_rate * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio,
        'ev': ev,
        'loss_impact': loss_impact,
        'net_profit': net_profit
    }


if __name__ == "__main__":
    results = backtest_v4_aggressive_loss_protection(
        test_period_months=6,
        target_pct=4.0,
        stop_loss_pct=-4.0,  # Tighter!
        max_hold_days=30
    )
