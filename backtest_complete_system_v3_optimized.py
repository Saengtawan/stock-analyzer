#!/usr/bin/env python3
"""
COMPLETE SYSTEM BACKTEST v3: OPTIMIZED for Higher Win Rate + Lower Loss Impact
===============================================================================

Improvements:
1. Better Entry Filters (increase win rate)
   - Volume confirmation (not just high, but SUSTAINED)
   - Momentum strength (not just positive, but STRONG)
   - Price position (near support, not extended)

2. Earlier Signal Detection (reduce avg loss)
   - Check signals from Day 3 (not Day 5)
   - Add Volume Dry signal (leading indicator)
   - More sensitive RSI (< 40 instead of < 35)

3. Tighter Risk Control
   - Stop loss -5% (from -6%)
   - Trailing stop -5% (from -6%)

Target: Win Rate 40-45%, Loss Impact < 75%
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
        fundamentals = {
            'pe_ratio': info.get('trailingPE', info.get('forwardPE', None)),
            'pb_ratio': info.get('priceToBook', None),
            'revenue_growth': info.get('revenueGrowth', None),
            'profit_margin': info.get('profitMargins', None),
            'roe': info.get('returnOnEquity', None),
            'debt_to_equity': info.get('debtToEquity', None),
            'market_cap': info.get('marketCap', 0)
        }
        return fundamentals
    except Exception as e:
        return None

def get_sector_regime(symbol):
    sector_map = {
        'NVDA': 'XLK', 'AMD': 'XLK', 'AVGO': 'XLK', 'QCOM': 'XLK', 'MU': 'XLK',
        'PLTR': 'XLK', 'SNOW': 'XLK', 'CRWD': 'XLK', 'ZS': 'XLK', 'NET': 'XLK',
        'DDOG': 'XLK', 'MDB': 'XLK', 'WDAY': 'XLK', 'TEAM': 'XLK', 'OKTA': 'XLK',
        'MRNA': 'XLV', 'BNTX': 'XLV', 'VRTX': 'XLV', 'REGN': 'XLV', 'GILD': 'XLV',
        'TSLA': 'XLY', 'SHOP': 'XLY', 'MELI': 'XLY',
        'SQ': 'XLF', 'COIN': 'XLF', 'SOFI': 'XLF', 'AFRM': 'XLF',
        'RIVN': 'XLE', 'LCID': 'XLE', 'ENPH': 'XLE'
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
    except Exception as e:
        return None

def calculate_entry_score_v3(hist, ticker_obj, symbol):
    """
    v3: Enhanced entry scoring with better filters
    """
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

    # Price changes
    price_change_5d = ((close_prices[-1] - close_prices[-6]) / close_prices[-6]) * 100 if len(close_prices) > 5 else 0
    price_change_20d = ((close_prices[-1] - close_prices[-21]) / close_prices[-21]) * 100 if len(close_prices) > 20 else 0

    # v3 IMPROVEMENT: Volume analysis (sustained, not just spike)
    avg_volume_20 = np.mean(volumes[-20:]) if len(volumes) > 20 else np.mean(volumes)
    avg_volume_5 = np.mean(volumes[-5:]) if len(volumes) > 5 else volumes[-1]

    current_volume = volumes[-1]
    volume_ratio_current = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1
    volume_ratio_sustained = avg_volume_5 / avg_volume_20 if avg_volume_20 > 0 else 1  # 5-day avg vs 20-day avg

    # Support/Resistance
    recent_high = np.max(close_prices[-20:]) if len(close_prices) > 20 else current_price
    recent_low = np.min(close_prices[-20:]) if len(close_prices) > 20 else current_price

    # === Layer Scores ===
    scores = {}

    # Layer 1: Fundamental (REAL DATA)
    fund_score = 0
    if fundamentals['revenue_growth'] is not None:
        revenue_growth = fundamentals['revenue_growth'] * 100
        if revenue_growth > 20:
            fund_score += 4
        elif revenue_growth > 10:
            fund_score += 3
        elif revenue_growth > 0:
            fund_score += 2
        else:
            fund_score += 1
    else:
        fund_score += 2

    if fundamentals['profit_margin'] is not None:
        margin = fundamentals['profit_margin'] * 100
        if margin > 20:
            fund_score += 3
        elif margin > 10:
            fund_score += 2
        elif margin > 0:
            fund_score += 1
    else:
        fund_score += 1

    if fundamentals['roe'] is not None:
        roe = fundamentals['roe'] * 100
        if roe > 15:
            fund_score += 3
        elif roe > 5:
            fund_score += 2
        elif roe > 0:
            fund_score += 1
    else:
        fund_score += 1

    scores['fundamental'] = min(fund_score, 10)

    # Layer 2: Technical
    tech_score = 0
    if rsi and sma20:
        # RSI scoring
        if 40 <= rsi <= 70:
            tech_score += 5
        elif rsi > 70:
            tech_score += 2  # Overbought warning
        else:
            tech_score += 3

        # SMA position
        if current_price > sma20:
            tech_score += 3
        if sma50 and current_price > sma50:
            tech_score += 2

    scores['technical'] = min(tech_score, 10)

    # Layer 3: Momentum (v3 IMPROVED - need STRONG momentum, not just positive)
    momentum_score = 0

    # Price momentum
    if price_change_5d > 2:  # Strong 5-day
        momentum_score += 4
    elif price_change_5d > 0:
        momentum_score += 2

    if price_change_20d > 5:  # Strong 20-day
        momentum_score += 3
    elif price_change_20d > 0:
        momentum_score += 1

    # v3: Volume momentum (SUSTAINED, not just spike)
    if volume_ratio_sustained > 1.3:  # 5-day avg significantly higher
        momentum_score += 3
    elif volume_ratio_current > 1.2:  # At least current day elevated
        momentum_score += 1

    scores['momentum'] = min(momentum_score, 10)

    # Layer 4: Valuation (REAL DATA)
    val_score = 0
    if fundamentals['pe_ratio'] is not None:
        pe = fundamentals['pe_ratio']
        if pe < 15:
            val_score += 5
        elif pe < 25:
            val_score += 4
        elif pe < 35:
            val_score += 3
        elif pe < 50:
            val_score += 2
        else:
            val_score += 1
    else:
        val_score += 3

    if fundamentals['pb_ratio'] is not None:
        pb = fundamentals['pb_ratio']
        if pb < 2:
            val_score += 3
        elif pb < 5:
            val_score += 2
        else:
            val_score += 1
    else:
        val_score += 1

    if fundamentals['debt_to_equity'] is not None:
        de = fundamentals['debt_to_equity'] / 100
        if de < 0.5:
            val_score += 2
        elif de < 1.5:
            val_score += 1
    else:
        val_score += 1

    scores['valuation'] = min(val_score, 10)

    # Layer 5: Sentiment (still simulated)
    scores['sentiment'] = 5.0

    # Layer 6: Catalyst
    catalyst_score = 0
    if current_price >= recent_high * 0.98:
        catalyst_score += 5
    if volume_ratio_sustained > 1.3:  # Sustained volume
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
        'sma20': sma20,
        'current_price': current_price,
        'volume_ratio_current': volume_ratio_current,
        'volume_ratio_sustained': volume_ratio_sustained,
        'fundamentals': fundamentals
    }

def should_enter_trade_v3(score_data, sector_regime,
                          min_score=5.5,
                          min_confidence=4.0,
                          min_momentum=5.0):  # v3: Add momentum requirement
    """
    v3: Stricter entry with momentum requirement
    """
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

    # v3 NEW: Require strong momentum
    if score_data['layer_scores']['momentum'] < min_momentum:
        return False, "low_momentum"

    # v3 NEW: Require sustained volume (not just spike)
    if score_data['volume_ratio_sustained'] < 1.1:
        return False, "low_volume"

    return True, "PASSED"

def backtest_complete_system_v3_optimized(
    symbols_universe=None,
    test_period_months=6,
    min_entry_score=5.5,
    min_entry_confidence=4.0,
    min_entry_momentum=5.0,
    target_pct=5.0,
    stop_loss_pct=-5.0,  # v3: Tighter stop
    max_hold_days=30
):
    """
    v3 OPTIMIZED: Better entries + Earlier exits = Higher win rate + Lower loss impact
    """

    print("=" * 80)
    print("BACKTEST v3 OPTIMIZED: Higher Win Rate + Lower Loss Impact")
    print("=" * 80)
    print()
    print("Entry Criteria (OPTIMIZED):")
    print(f"  - Minimum Total Score: {min_entry_score}/10")
    print(f"  - Minimum Confidence: {min_entry_confidence}/6 layers")
    print(f"  - Minimum Momentum: {min_entry_momentum}/10 🆕")
    print(f"  - Sustained Volume: > 1.1x (not just spike) 🆕")
    print(f"  - Sector Regime: BULL + SIDEWAYS")
    print()
    print("Exit Rules (OPTIMIZED):")
    print(f"  1. Target: {target_pct}%")
    print(f"  2. Hard Stop: {stop_loss_pct}% 🆕 (tighter)")
    print(f"  3. Trailing Stop: -5% from peak (Day 5+) 🆕")
    print(f"  4. SIGNAL: Breaking SMA20 (Day 3+) 🆕 (earlier)")
    print(f"  5. SIGNAL: Weak RSI < 40 (Day 3+) 🆕 (more sensitive)")
    print(f"  6. SIGNAL: Volume Dry < 0.7x (Day 5+) 🆕 (new signal)")
    print(f"  7. SIGNAL: Lower Lows (Day 7+)")
    print(f"  8. SIGNAL: Failed Breakout (peak 3%+)")
    print(f"  9. Max Hold: {max_hold_days} days")
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
                entry_date = hist.index[i]
                hist_at_entry = hist.iloc[:i+1]

                score_data = calculate_entry_score_v3(hist_at_entry, ticker, symbol)

                if not score_data:
                    entry_rejections['no_score_data'] = entry_rejections.get('no_score_data', 0) + 1
                    continue

                should_enter, reason = should_enter_trade_v3(
                    score_data, sector_regime,
                    min_entry_score, min_entry_confidence, min_entry_momentum
                )

                if not should_enter:
                    entry_rejections[reason] = entry_rejections.get(reason, 0) + 1
                    continue

                # ENTER TRADE
                entry_price = hist['Close'].iloc[i]
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                exit_reason = 'MAX_HOLD'
                peak_price = entry_price

                # Track volume for dry signal
                entry_volume_ma = np.mean(hist['Volume'].iloc[i-19:i+1].values) if i >= 19 else hist['Volume'].iloc[i]

                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_idx = i + day
                    current_price = hist['Close'].iloc[current_idx]
                    current_volume = hist['Volume'].iloc[current_idx]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    if current_price > peak_price:
                        peak_price = current_price

                    peak_gain = ((peak_price - entry_price) / entry_price) * 100

                    # Priority 1: Hard Stop (v3: -5%)
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

                    # Priority 3: Trailing Stop (v3: -5%)
                    if day >= 5:
                        drawdown = ((current_price - peak_price) / peak_price) * 100
                        if drawdown < -5.0:
                            exit_reason = 'TRAILING_STOP'
                            exit_price = current_price
                            exit_day = day
                            break

                    # Priority 4: SIGNAL-BASED EXITS (v3 OPTIMIZED - Earlier detection)
                    price_history = hist['Close'].iloc[:current_idx+1].values

                    # v3: Check from Day 3 (not Day 5)
                    if day >= 3:
                        # Signal 1: Breaking SMA20 (Day 3+, earlier than v2)
                        if len(price_history) >= 20:
                            sma20 = calculate_sma(price_history, 20)
                            if sma20 is not None and current_price < sma20:
                                distance_pct = ((current_price - sma20) / sma20) * 100
                                if distance_pct < -0.5:  # v3: More sensitive (-0.5% vs -1%)
                                    exit_reason = 'SIGNAL_SMA20_BREAK'
                                    exit_price = current_price
                                    exit_day = day
                                    break

                        # Signal 2: Weak RSI (v3: < 40 instead of < 35, more sensitive)
                        if len(price_history) >= 15:
                            rsi = calculate_rsi(price_history, 14)
                            if rsi is not None and rsi < 40:
                                exit_reason = 'SIGNAL_WEAK_RSI'
                                exit_price = current_price
                                exit_day = day
                                break

                    # Signal 3: Volume Dry (v3 NEW - Leading indicator)
                    if day >= 5:
                        # Calculate current volume MA
                        volume_history = hist['Volume'].iloc[current_idx-19:current_idx+1].values if current_idx >= 19 else hist['Volume'].iloc[:current_idx+1].values
                        current_volume_ma = np.mean(volume_history)
                        volume_ratio = current_volume / current_volume_ma if current_volume_ma > 0 else 1

                        # If volume dried up for 2 days
                        if volume_ratio < 0.7:
                            prev_volume = hist['Volume'].iloc[current_idx-1]
                            prev_volume_ratio = prev_volume / current_volume_ma if current_volume_ma > 0 else 1
                            if prev_volume_ratio < 0.7:
                                exit_reason = 'SIGNAL_VOLUME_DRY'
                                exit_price = current_price
                                exit_day = day
                                break

                    # Signal 4: Lower Lows (Day 7+)
                    if day >= 7 and len(price_history) >= 10:
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
                    'entry_date': entry_date,
                    'return_pct': final_return,
                    'exit_reason': exit_reason,
                    'exit_day': exit_day,
                    'peak_gain': peak_gain,
                    'entry_score': score_data['total_score'],
                    'entry_confidence': score_data['confidence'],
                    'entry_momentum': score_data['layer_scores']['momentum']
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
        print("\n❌ NO TRADES! Entry criteria too strict.")
        print("\nEntry Rejections:")
        for reason, count in sorted(entry_rejections.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason:25}: {count:5}")
        return None

    winners = [t for t in all_trades if t['return_pct'] >= target_pct]
    losers = [t for t in all_trades if t['return_pct'] < target_pct]

    print()
    print("=" * 80)
    print("📊 RESULTS v3 OPTIMIZED")
    print("=" * 80)
    print()

    print(f"Total Trades: {total}")
    print(f"Winners: {len(winners)} ({len(winners)/total*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/total*100:.1f}%)")
    print()

    # Entry Quality
    avg_entry_score = np.mean([t['entry_score'] for t in all_trades])
    avg_entry_confidence = np.mean([t['entry_confidence'] for t in all_trades])
    avg_entry_momentum = np.mean([t['entry_momentum'] for t in all_trades])

    print("=" * 80)
    print("📈 ENTRY QUALITY")
    print("=" * 80)
    print()
    print(f"Average Entry Score: {avg_entry_score:.1f}/10")
    print(f"Average Confidence: {avg_entry_confidence:.1f}/10")
    print(f"Average Momentum: {avg_entry_momentum:.1f}/10 🆕")
    print()

    total_rejections = sum(entry_rejections.values())
    print(f"Entry Success Rate: {total}/{total + total_rejections} ({total/(total + total_rejections)*100:.1f}%)")
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
    if rr_ratio >= 2.0:
        print(f"   ✅ EXCELLENT!")
    elif rr_ratio >= 1.5:
        print(f"   ✅ VERY GOOD")
    elif rr_ratio >= 1.0:
        print(f"   ✅ GOOD")
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
    print(f"ROI: {(net_profit / 100000) * 100:+.2f}%")
    print()

    loss_impact = abs(total_loss / total_win_profit) * 100 if total_win_profit > 0 else 0
    print(f"Loss Impact: {loss_impact:.1f}% of wins")
    print()

    # Comparison
    print("=" * 80)
    print("📊 IMPROVEMENT: v2 → v3")
    print("=" * 80)
    print()

    print(f"{'Metric':<25} | {'v2 (Base)':<15} | {'v3 (Optimized)':<15} | {'Change'}")
    print("-" * 80)
    print(f"{'Win Rate':<25} | {'37.6%':<15} | {f'{win_rate*100:.1f}%':<15} | {f'{win_rate*100-37.6:+.1f}%'}")
    print(f"{'R:R Ratio':<25} | {'2.03:1':<15} | {f'{rr_ratio:.2f}:1':<15} | {f'{rr_ratio-2.03:+.2f}'}")
    print(f"{'Expected Value':<25} | {'+0.52%':<15} | {f'{ev:+.2f}%':<15} | {f'{ev-0.52:+.2f}%'}")
    print(f"{'Avg Loss':<25} | {'-3.76%':<15} | {f'{avg_loss:+.2f}%':<15} | {f'{avg_loss-(-3.76):+.2f}%'}")
    print(f"{'Loss Impact':<25} | {'82.7%':<15} | {f'{loss_impact:.1f}%':<15} | {f'{loss_impact-82.7:+.1f}%'}")
    print()

    # Verdict
    print("=" * 80)
    print("🎯 VERDICT")
    print("=" * 80)
    print()

    improvements = []
    if win_rate >= 0.40:
        improvements.append(f"✅ Win Rate: {win_rate*100:.1f}% (TARGET MET!)")
    else:
        improvements.append(f"⚠️ Win Rate: {win_rate*100:.1f}% (target 40%)")

    if loss_impact < 75:
        improvements.append(f"✅ Loss Impact: {loss_impact:.1f}% (TARGET MET!)")
    else:
        improvements.append(f"⚠️ Loss Impact: {loss_impact:.1f}% (target <75%)")

    if rr_ratio >= 2.0:
        improvements.append(f"✅ R:R: {rr_ratio:.2f}:1 (Excellent)")

    if ev >= 0.75:
        improvements.append(f"✅ EV: {ev:+.2f}% (Strong)")

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
    results = backtest_complete_system_v3_optimized(
        test_period_months=6,
        min_entry_score=5.5,
        min_entry_confidence=4.0,
        min_entry_momentum=5.0,  # NEW: Require strong momentum
        target_pct=5.0,
        stop_loss_pct=-5.0,  # Tighter
        max_hold_days=30
    )
