#!/usr/bin/env python3
"""
COMPLETE SYSTEM BACKTEST v2: REAL Data Entry Screening + v3.5 Exits
====================================================================

ปรับปรุง:
1. ใช้ Fundamental data จริง (P/E, Revenue Growth, etc.)
2. เพิ่ม Sector Regime Filter (BULL sectors only)
3. ปรับ Entry Timing (รอ pullback ใกล้ SMA20)

ไม่ใช่ simulation อีกต่อไป!
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
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
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
    """Check if making lower lows (downtrend)"""
    if len(prices) < lookback * 2:
        return False

    recent_low = np.min(prices[-lookback:])
    previous_low = np.min(prices[-lookback*2:-lookback])

    return recent_low < previous_low

def get_real_fundamentals(ticker_obj):
    """
    Get REAL fundamental data from Yahoo Finance

    Returns dict with:
    - pe_ratio: P/E ratio
    - pb_ratio: P/B ratio
    - revenue_growth: Revenue growth %
    - profit_margin: Profit margin %
    - roe: Return on Equity %
    - debt_to_equity: Debt/Equity ratio
    """
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
        logger.warning(f"Error fetching fundamentals: {e}")
        return None

def get_sector_regime(symbol):
    """
    Get sector regime for symbol
    (Simplified - in production, use actual SectorRegimeDetector)

    Returns: 'BULL', 'BEAR', 'SIDEWAYS', or None
    """

    # Sector mapping (simplified)
    sector_map = {
        # Tech
        'NVDA': 'XLK', 'AMD': 'XLK', 'AVGO': 'XLK', 'QCOM': 'XLK', 'MU': 'XLK',
        'PLTR': 'XLK', 'SNOW': 'XLK', 'CRWD': 'XLK', 'ZS': 'XLK', 'NET': 'XLK',
        'DDOG': 'XLK', 'MDB': 'XLK', 'WDAY': 'XLK', 'TEAM': 'XLK', 'OKTA': 'XLK',
        # Healthcare
        'MRNA': 'XLV', 'BNTX': 'XLV', 'VRTX': 'XLV', 'REGN': 'XLV', 'GILD': 'XLV',
        # Consumer Discretionary
        'TSLA': 'XLY', 'SHOP': 'XLY', 'MELI': 'XLY',
        # Financials
        'SQ': 'XLF', 'COIN': 'XLF', 'SOFI': 'XLF', 'AFRM': 'XLF',
        # Energy
        'RIVN': 'XLE', 'LCID': 'XLE', 'ENPH': 'XLE'
    }

    sector_etf = sector_map.get(symbol, 'SPY')

    try:
        # Get sector ETF data
        etf = yf.Ticker(sector_etf)
        hist = etf.history(period='3mo')

        if hist.empty or len(hist) < 50:
            return None

        close_prices = hist['Close'].values

        # Calculate indicators
        sma20 = calculate_sma(close_prices, 20)
        sma50 = calculate_sma(close_prices, 50)

        if not sma20 or not sma50:
            return None

        current_price = close_prices[-1]

        # Determine regime
        if current_price > sma20 and current_price > sma50 and sma20 > sma50:
            return 'BULL'
        elif current_price < sma20 and current_price < sma50 and sma20 < sma50:
            return 'BEAR'
        else:
            return 'SIDEWAYS'

    except Exception as e:
        logger.warning(f"Error getting sector regime for {symbol}: {e}")
        return None

def calculate_6layer_score_v2(hist, ticker_obj, symbol):
    """
    Calculate 6-Layer Scoring with REAL data

    v2 Changes:
    - Use REAL fundamental data from Yahoo Finance
    - Use REAL valuation metrics
    - Sentiment still simulated (need external API)
    - Catalyst based on real price action
    """

    if len(hist) < 50:
        return None

    close_prices = hist['Close'].values
    volumes = hist['Volume'].values

    # Get REAL fundamentals
    fundamentals = get_real_fundamentals(ticker_obj)

    if not fundamentals:
        return None

    # Calculate technical indicators
    current_price = close_prices[-1]
    sma20 = calculate_sma(close_prices, 20)
    sma50 = calculate_sma(close_prices, 50)
    rsi = calculate_rsi(close_prices, 14)

    # Price change metrics
    price_change_5d = ((close_prices[-1] - close_prices[-6]) / close_prices[-6]) * 100 if len(close_prices) > 5 else 0
    price_change_20d = ((close_prices[-1] - close_prices[-21]) / close_prices[-21]) * 100 if len(close_prices) > 20 else 0

    # Volume metrics
    avg_volume = np.mean(volumes[-20:]) if len(volumes) > 20 else np.mean(volumes)
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1

    # Support/Resistance
    recent_high = np.max(close_prices[-20:]) if len(close_prices) > 20 else current_price
    recent_low = np.min(close_prices[-20:]) if len(close_prices) > 20 else current_price

    # Layer Scoring (0-10 each)
    scores = {}

    # === Layer 1: Fundamental (REAL DATA!) ===
    fund_score = 0

    # Revenue Growth
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
        fund_score += 2  # Neutral if no data

    # Profit Margin
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

    # ROE
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

    # === Layer 2: Technical ===
    tech_score = 0
    if rsi and sma20:
        # RSI scoring
        if 40 <= rsi <= 70:
            tech_score += 5
        elif rsi > 70:
            tech_score += 2
        else:
            tech_score += 3

        # SMA position
        if current_price > sma20:
            tech_score += 3
        if sma50 and current_price > sma50:
            tech_score += 2

    scores['technical'] = min(tech_score, 10)

    # === Layer 3: Momentum ===
    momentum_score = 0
    if price_change_5d > 0:
        momentum_score += 3
    if price_change_20d > 0:
        momentum_score += 3
    if volume_ratio > 1.2:
        momentum_score += 4

    scores['momentum'] = min(momentum_score, 10)

    # === Layer 4: Valuation (REAL DATA!) ===
    val_score = 0

    # P/E Ratio
    if fundamentals['pe_ratio'] is not None:
        pe = fundamentals['pe_ratio']
        if pe < 15:
            val_score += 5  # Value
        elif pe < 25:
            val_score += 4  # Fair
        elif pe < 35:
            val_score += 3  # Moderate
        elif pe < 50:
            val_score += 2  # Expensive
        else:
            val_score += 1  # Very expensive
    else:
        val_score += 3  # Neutral if no data

    # P/B Ratio
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

    # Debt/Equity
    if fundamentals['debt_to_equity'] is not None:
        de = fundamentals['debt_to_equity'] / 100  # Convert to ratio
        if de < 0.5:
            val_score += 2  # Low debt
        elif de < 1.5:
            val_score += 1  # Moderate
        # else: 0 (high debt)
    else:
        val_score += 1

    scores['valuation'] = min(val_score, 10)

    # === Layer 5: Sentiment (Simulated - need external API) ===
    scores['sentiment'] = 5.0  # Neutral

    # === Layer 6: Catalyst ===
    catalyst_score = 0
    if current_price >= recent_high * 0.98:
        catalyst_score += 5
    if volume_ratio > 1.5:
        catalyst_score += 5

    scores['catalyst'] = min(catalyst_score, 10)

    # Calculate weighted average
    total_score = sum(scores.values()) / len(scores)

    # Confidence (how many layers >= 5)
    above_5 = sum(1 for s in scores.values() if s >= 5)
    confidence = (above_5 / len(scores)) * 10

    return {
        'total_score': total_score,
        'layer_scores': scores,
        'confidence': confidence,
        'rsi': rsi,
        'sma20': sma20,
        'current_price': current_price,
        'volume_ratio': volume_ratio,
        'fundamentals': fundamentals
    }

def check_entry_timing(hist, current_idx):
    """
    Check if entry timing is good (near pullback/support)

    Good entry:
    - Price near SMA20 (within 2%)
    - OR Price bouncing off recent support
    - NOT overbought (RSI < 70)
    """

    if current_idx < 20:
        return False

    hist_slice = hist.iloc[:current_idx+1]
    close_prices = hist_slice['Close'].values

    if len(close_prices) < 20:
        return False

    current_price = close_prices[-1]
    sma20 = calculate_sma(close_prices, 20)
    rsi = calculate_rsi(close_prices, 14)

    if not sma20 or not rsi:
        return False

    # Check conditions
    distance_from_sma20 = abs(current_price - sma20) / sma20 * 100

    # Good timing conditions:
    # 1. Within 2% of SMA20 (pullback)
    if distance_from_sma20 <= 2.0:
        return True

    # 2. RSI between 35-60 (not overbought, not too weak)
    if 35 <= rsi <= 60:
        # Check if bouncing (yesterday lower, today higher)
        if len(close_prices) >= 3:
            if close_prices[-2] < close_prices[-3] and close_prices[-1] > close_prices[-2]:
                return True

    return False

def should_enter_trade_v2(score_data, sector_regime, min_score=5.5, min_confidence=4.0, allow_sideways=True):
    """
    v2: More strict entry criteria with REAL data

    Criteria:
    1. Total score >= 5.5 (raised from 5.0)
    2. Confidence >= 4.0 (at least 4/6 layers good)
    3. Technical score >= 4 (raised from 3)
    4. Fundamental score >= 4 (must have good fundamentals)
    5. Sector regime = BULL or SIDEWAYS (block BEAR only!)
    """

    if not score_data:
        return False, "no_score_data"

    # Check sector regime - Block BEAR only
    if sector_regime == 'BEAR':
        return False, "sector_BEAR"

    # Optionally require BULL (strict) or allow SIDEWAYS (normal)
    if not allow_sideways and sector_regime != 'BULL':
        return False, f"sector_{sector_regime}"

    # Check minimum thresholds
    if score_data['total_score'] < min_score:
        return False, "low_total_score"

    if score_data['confidence'] < min_confidence:
        return False, "low_confidence"

    if score_data['layer_scores']['technical'] < 4:
        return False, "low_technical"

    if score_data['layer_scores']['fundamental'] < 4:
        return False, "low_fundamental"

    return True, "PASSED"

def backtest_complete_system_v2(
    symbols_universe=None,
    test_period_months=6,
    min_entry_score=5.5,
    min_entry_confidence=4.0,
    require_good_timing=True,
    allow_sideways_sectors=True,
    target_pct=5.0,
    stop_loss_pct=-6.0,
    max_hold_days=30
):
    """
    Complete system backtest v2 with REAL data
    """

    print("=" * 80)
    print("COMPLETE SYSTEM BACKTEST v2: REAL Data + v3.5 Exits")
    print("=" * 80)
    print()
    print("Entry Criteria (6-Layer with REAL Data):")
    print(f"  - Minimum Total Score: {min_entry_score}/10")
    print(f"  - Minimum Confidence: {min_entry_confidence}/6 layers")
    print(f"  - Minimum Technical Score: 4/10")
    print(f"  - Minimum Fundamental Score: 4/10")
    sector_filter = "BULL + SIDEWAYS (block BEAR)" if allow_sideways_sectors else "BULL only"
    print(f"  - Sector Regime: {sector_filter}")
    print(f"  - Entry Timing: {require_good_timing}")
    print()
    print("Exit Rules (v3.5 Signal-Based):")
    print(f"  1. Target: {target_pct}%")
    print(f"  2. Hard Stop: {stop_loss_pct}%")
    print(f"  3. Trailing Stop: -6% from peak (after 5 days)")
    print(f"  4. SIGNAL: Breaking SMA20 (Day 5+, >1% below)")
    print(f"  5. SIGNAL: Weak RSI < 35 (Day 5+)")
    print(f"  6. SIGNAL: Lower Lows (Day 7+, gain < 2%)")
    print(f"  7. SIGNAL: Failed Breakout (peak 3%+ → < 0.5%)")
    print(f"  8. Max Hold: {max_hold_days} days")
    print()

    # Default universe
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

            # Get sector regime
            sector_regime = get_sector_regime(symbol)

            entries_found = 0

            # Simulate weekly entry attempts
            for i in range(50, len(hist) - max_hold_days, 7):
                entry_date = hist.index[i]
                hist_at_entry = hist.iloc[:i+1]

                # Calculate 6-layer score with REAL data
                score_data = calculate_6layer_score_v2(hist_at_entry, ticker, symbol)

                if not score_data:
                    entry_rejections['no_score_data'] = entry_rejections.get('no_score_data', 0) + 1
                    continue

                # Check entry timing
                if require_good_timing:
                    if not check_entry_timing(hist, i):
                        entry_rejections['bad_timing'] = entry_rejections.get('bad_timing', 0) + 1
                        continue

                # Check entry criteria
                should_enter, reason = should_enter_trade_v2(score_data, sector_regime, min_entry_score, min_entry_confidence, allow_sideways_sectors)

                if not should_enter:
                    entry_rejections[reason] = entry_rejections.get(reason, 0) + 1
                    continue

                # PASSED ALL FILTERS - Enter trade!
                entry_price = hist['Close'].iloc[i]
                exit_day = max_hold_days
                exit_price = hist['Close'].iloc[i + min(max_hold_days, len(hist) - i - 1)]
                exit_reason = 'MAX_HOLD'

                peak_price = entry_price

                # Simulate holding period with v3.5 exits
                for day in range(1, min(max_hold_days + 1, len(hist) - i)):
                    current_idx = i + day
                    current_price = hist['Close'].iloc[current_idx]
                    gain_pct = ((current_price - entry_price) / entry_price) * 100

                    if current_price > peak_price:
                        peak_price = current_price

                    peak_gain = ((peak_price - entry_price) / entry_price) * 100

                    # Exit logic (same as v3.5)
                    if gain_pct <= stop_loss_pct:
                        exit_reason = 'HARD_STOP'
                        exit_price = current_price
                        exit_day = day
                        break

                    if gain_pct >= target_pct:
                        exit_reason = 'TARGET_HIT'
                        exit_price = current_price
                        exit_day = day
                        break

                    if day >= 5:
                        drawdown = ((current_price - peak_price) / peak_price) * 100
                        if drawdown < -6.0:
                            exit_reason = 'TRAILING_STOP'
                            exit_price = current_price
                            exit_day = day
                            break

                    if day >= 3:
                        price_history = hist['Close'].iloc[:current_idx+1].values

                        # Signal exits
                        if day >= 5 and len(price_history) >= 20:
                            sma20 = calculate_sma(price_history, 20)
                            if sma20 is not None and current_price < sma20:
                                if len(price_history) >= 2:
                                    prev_price = price_history[-2]
                                    prev_sma20 = calculate_sma(price_history[:-1], 20)
                                    if prev_sma20 is not None and prev_price < prev_sma20:
                                        distance_pct = ((current_price - sma20) / sma20) * 100
                                        if distance_pct < -1.0:
                                            exit_reason = 'SIGNAL_SMA20_BREAK'
                                            exit_price = current_price
                                            exit_day = day
                                            break

                        if day >= 5 and len(price_history) >= 15:
                            rsi = calculate_rsi(price_history, 14)
                            if rsi is not None and rsi < 35:
                                exit_reason = 'SIGNAL_WEAK_RSI'
                                exit_price = current_price
                                exit_day = day
                                break

                        if day >= 7 and len(price_history) >= 10:
                            if check_lower_lows(price_history, lookback=5):
                                if gain_pct < 2.0:
                                    exit_reason = 'SIGNAL_LOWER_LOWS'
                                    exit_price = current_price
                                    exit_day = day
                                    break

                        if peak_gain >= 3.0 and gain_pct < 0.5:
                            exit_reason = 'SIGNAL_FAILED_BREAKOUT'
                            exit_price = current_price
                            exit_day = day
                            break

                final_return = ((exit_price - entry_price) / entry_price) * 100

                trade = {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'return_pct': final_return,
                    'exit_reason': exit_reason,
                    'exit_day': exit_day,
                    'peak_gain': peak_gain,
                    'entry_score': score_data['total_score'],
                    'entry_confidence': score_data['confidence'],
                    'sector_regime': sector_regime
                }

                all_trades.append(trade)
                exit_reasons_count[exit_reason] = exit_reasons_count.get(exit_reason, 0) + 1
                entries_found += 1

            print(f"✅ {entries_found} entries")

        except Exception as e:
            print(f"❌ Error: {e}")
            logger.warning(f"{symbol}: Error - {e}")
            continue

    # ===== ANALYSIS =====

    total = len(all_trades)

    if total == 0:
        print()
        print("=" * 80)
        print("❌ NO TRADES FOUND!")
        print("=" * 80)
        print()
        print("Entry criteria may be too strict, or market conditions unfavorable.")
        print()
        print("Entry Rejections:")
        for reason, count in sorted(entry_rejections.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason:25}: {count:5}")
        return None

    winners = [t for t in all_trades if t['return_pct'] >= target_pct]
    losers = [t for t in all_trades if t['return_pct'] < target_pct]

    print()
    print("=" * 80)
    print("📊 RESULTS (v2 - REAL Data Entry)")
    print("=" * 80)
    print()

    print(f"Total Trades: {total}")
    print(f"Winners: {len(winners)} ({len(winners)/total*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/total*100:.1f}%)")
    print()

    # Entry Quality
    print("=" * 80)
    print("📈 ENTRY QUALITY (REAL Fundamental Data)")
    print("=" * 80)
    print()

    avg_entry_score = np.mean([t['entry_score'] for t in all_trades])
    avg_entry_confidence = np.mean([t['entry_confidence'] for t in all_trades])

    print(f"Average Entry Score: {avg_entry_score:.1f}/10")
    print(f"Average Entry Confidence: {avg_entry_confidence:.1f}/10")
    print()

    print("Entry Rejection Breakdown:")
    total_rejections = sum(entry_rejections.values())
    for reason, count in sorted(entry_rejections.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_rejections * 100) if total_rejections > 0 else 0
        print(f"  {reason:25}: {count:5} ({pct:5.1f}%)")
    print()
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
    else:
        print(f"   ⚠️  Needs improvement")
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
    print("📊 COMPARISON: v1 (Simulated) vs v2 (REAL Data)")
    print("=" * 80)
    print()

    print(f"{'Metric':<25} | {'v1 (Sim)':<15} | {'v2 (REAL)':<15} | {'Change'}")
    print("-" * 80)
    print(f"{'Win Rate':<25} | {'38.3%':<15} | {f'{win_rate*100:.1f}%':<15} | {f'{win_rate*100-38.3:+.1f}%'}")
    print(f"{'R:R Ratio':<25} | {'2.03:1':<15} | {f'{rr_ratio:.2f}:1':<15} | {f'{rr_ratio-2.03:+.2f}'}")
    print(f"{'Expected Value':<25} | {'+0.62%':<15} | {f'{ev:+.2f}%':<15} | {f'{ev-0.62:+.2f}%'}")
    print(f"{'Avg Loss':<25} | {'-3.82%':<15} | {f'{avg_loss:+.2f}%':<15} | {f'{avg_loss-(-3.82):+.2f}%'}")
    print()

    # Final Verdict
    print("=" * 80)
    print("🎯 VERDICT")
    print("=" * 80)
    print()

    if win_rate >= 0.40 and rr_ratio >= 1.5 and ev >= 1.0:
        print("✅ EXCELLENT SYSTEM!")
        print(f"   - Win Rate: {win_rate*100:.1f}% (healthy)")
        print(f"   - R:R: {rr_ratio:.2f}:1 (strong)")
        print(f"   - EV: {ev:+.2f}% (profitable)")
        print()
        print("🚀 PRODUCTION READY with REAL data!")
    elif win_rate >= 0.35 and rr_ratio >= 1.0 and ev >= 0.5:
        print("✅ GOOD SYSTEM")
        print(f"   - Win Rate: {win_rate*100:.1f}%")
        print(f"   - R:R: {rr_ratio:.2f}:1")
        print(f"   - EV: {ev:+.2f}%")
        print(f"   - System works, improvements ongoing")
    else:
        print("⚠️  NEEDS IMPROVEMENT")
        print(f"   - Win Rate: {win_rate*100:.1f}%")
        print(f"   - R:R: {rr_ratio:.2f}:1")
        print(f"   - EV: {ev:+.2f}%")

    print()

    return {
        'total_trades': total,
        'win_rate': win_rate * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio,
        'ev': ev,
        'net_profit': net_profit,
        'avg_entry_score': avg_entry_score,
        'avg_entry_confidence': avg_entry_confidence
    }


if __name__ == "__main__":
    results = backtest_complete_system_v2(
        test_period_months=6,
        min_entry_score=5.0,              # Balanced (not too strict)
        min_entry_confidence=3.5,          # At least 3.5/6 layers good
        require_good_timing=False,         # Disabled (too strict)
        allow_sideways_sectors=True,       # Allow BULL + SIDEWAYS (block BEAR only)
        target_pct=5.0,
        stop_loss_pct=-6.0,
        max_hold_days=30
    )
