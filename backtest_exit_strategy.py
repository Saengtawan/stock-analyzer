#!/usr/bin/env python3
"""
CORRECT EXIT STRATEGY TEST
===========================
แยก Entry/Exit logic — Trade ทุกวัน + Exit ที่ดี
Test ใน BULL และ BEAR periods
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# PERIODS TO TEST
# =============================================================================

TEST_PERIODS = {
    'BULL_2023_2026': {
        'name': 'BULL 2023-2026',
        'start': '2023-01-01',
        'end': '2026-02-06',
        'type': 'BULL',
    },
    'BEAR_2022': {
        'name': 'BEAR 2022 Fed Hike',
        'start': '2022-01-01',
        'end': '2022-10-31',
        'type': 'BEAR',
    },
    'BEAR_2020': {
        'name': 'BEAR 2020 COVID',
        'start': '2020-02-01',
        'end': '2020-04-30',
        'type': 'BEAR',
    },
    'BEAR_2018': {
        'name': 'BEAR 2018 Q4',
        'start': '2018-10-01',
        'end': '2018-12-31',
        'type': 'BEAR',
    },
}

# =============================================================================
# EXIT STRATEGY CONFIGURATIONS
# =============================================================================

STRATEGIES = {
    'FAST_EXIT': {
        'name': 'FAST (TP2.5x, 5d)',
        'tp_mult': 2.5,
        'sl_mult': 1.5,
        'max_hold': 5,
        'trailing': None,
        'recheck': None,
        'entry_days': None,  # All days
    },
    'MEDIUM_EXIT': {
        'name': 'MEDIUM (TP3.0x, 7d)',
        'tp_mult': 3.0,
        'sl_mult': 1.5,
        'max_hold': 7,
        'trailing': None,
        'recheck': None,
        'entry_days': None,
    },
    'PROTECTED_EXIT': {
        'name': 'PROTECTED (TP3.0x, 7d, R5+R9)',
        'tp_mult': 3.0,
        'sl_mult': 1.5,
        'max_hold': 7,
        'trailing': None,
        'recheck': {
            'R5_sector_weak': True,
            'R5_min_profit': 1.5,
            'R9_momentum_fade': True,
        },
        'trailing_params': {
            'sector': (1.5, 55),
            'momentum': (1.5, 60),
        },
        'entry_days': None,
    },
    'TRAILING_EXIT': {
        'name': 'TRAILING (TP3.5x, Trail2%/60%)',
        'tp_mult': 3.5,
        'sl_mult': 1.5,
        'max_hold': 10,
        'trailing': {
            'activation': 2.0,
            'lock': 60,
        },
        'recheck': None,
        'entry_days': None,
    },
    'v5.6_BASELINE': {
        'name': 'v5.6 (TP5.0x, 30d)',
        'tp_mult': 5.0,
        'sl_mult': 1.5,
        'max_hold': 30,
        'trailing': None,
        'recheck': None,
        'entry_days': None,
    },
    'TIME_BASED': {
        'name': 'TIME-BASED (Mon/Tue)',
        'tp_mult': 2.5,
        'sl_mult': 1.5,
        'max_hold': 5,
        'trailing': None,
        'recheck': None,
        'entry_days': [0, 1],  # Mon, Tue only
    },
}

# Sector ETF mapping
SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financial': 'XLF',
    'Consumer Cyclical': 'XLY', 'Consumer Defensive': 'XLP',
    'Energy': 'XLE', 'Industrials': 'XLI', 'Basic Materials': 'XLB',
    'Utilities': 'XLU', 'Real Estate': 'XLRE', 'Communication Services': 'XLC'
}

# =============================================================================
# DATA & INDICATORS
# =============================================================================

def load_period_data(start: str, end: str) -> Tuple[pd.Series, pd.DataFrame, Dict]:
    """Load market data for period"""
    ext_start = (pd.to_datetime(start) - timedelta(days=60)).strftime('%Y-%m-%d')

    vix = yf.download("^VIX", start=ext_start, end=end, progress=False)['Close']
    spy = yf.download("SPY", start=ext_start, end=end, progress=False)

    etf_data = {}
    symbols = list(set(SECTOR_ETFS.values()))
    data = yf.download(symbols, start=ext_start, end=end, progress=False, group_by='ticker')
    for symbol in symbols:
        try:
            etf_data[symbol] = data[symbol]['Close'] if len(symbols) > 1 else data['Close']
        except:
            pass

    return vix, spy, etf_data

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR"""
    tr = pd.concat([
        df['High'] - df['Low'],
        abs(df['High'] - df['Close'].shift(1)),
        abs(df['Low'] - df['Close'].shift(1))
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_momentum(prices: pd.Series, period: int = 3) -> float:
    """Calculate momentum"""
    if len(prices) < period + 1:
        return 0.0
    return float((prices.iloc[-1] / prices.iloc[-period] - 1) * 100)

def calculate_sector_strength(sector: str, etf_data: Dict, date: pd.Timestamp) -> float:
    """Calculate sector strength"""
    try:
        etf_symbol = SECTOR_ETFS.get(sector)
        if not etf_symbol or etf_symbol not in etf_data:
            return 50.0
        prices = etf_data[etf_symbol].loc[:date]
        if len(prices) < 20:
            return 50.0
        ret_5d = float((prices.iloc[-1] / prices.iloc[-5] - 1) * 100) if len(prices) >= 5 else 0
        ret_20d = float((prices.iloc[-1] / prices.iloc[-20] - 1) * 100) if len(prices) >= 20 else 0
        return max(0, min(100, 50 + ret_5d * 5 + ret_20d * 2))
    except:
        return 50.0

def get_stock_sector(symbol: str) -> str:
    """Get sector"""
    try:
        return yf.Ticker(symbol).info.get('sector', 'Unknown')
    except:
        return 'Unknown'

# =============================================================================
# SIGNAL COLLECTION
# =============================================================================

def collect_signals(start: str, end: str) -> List[Dict]:
    """Collect dip-bounce signals"""
    stocks = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',
        'ORCL', 'ADBE', 'INTC', 'CSCO', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'SCHW', 'BLK',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'TMO', 'ABT', 'LLY', 'BMY', 'AMGN',
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'PSX', 'OXY', 'HAL',
        'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'EA', 'TTWO', 'WBD',
        'HD', 'LOW', 'TGT', 'COST', 'WMT', 'TJX', 'ROST', 'DG', 'DLTR', 'BBY',
        'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'KMB', 'GIS', 'K',
        'CAT', 'DE', 'MMM', 'HON', 'UPS', 'FDX', 'BA', 'LMT', 'RTX', 'GE',
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'XEL', 'EXC', 'SRE', 'ED'
    ]

    signals = []
    ext_start = (pd.to_datetime(start) - timedelta(days=60)).strftime('%Y-%m-%d')
    actual_start = pd.to_datetime(start)
    actual_end = pd.to_datetime(end)

    all_data = yf.download(stocks, start=ext_start, end=end, progress=False, group_by='ticker')

    for symbol in stocks:
        try:
            df = all_data[symbol].dropna() if len(stocks) > 1 else all_data.dropna()
            if len(df) < 50:
                continue

            df['return'] = df['Close'].pct_change() * 100
            df['prev_return'] = df['return'].shift(1)
            df['ATR'] = calculate_atr(df)

            for i in range(2, len(df) - 30):
                entry_date = df.index[i]
                if entry_date < actual_start or entry_date > actual_end:
                    continue

                if df['prev_return'].iloc[i] <= -2.0 and df['return'].iloc[i] >= 1.0:
                    entry_price = float(df['Close'].iloc[i])
                    atr = float(df['ATR'].iloc[i])
                    if pd.isna(atr) or atr <= 0:
                        continue

                    signals.append({
                        'symbol': symbol,
                        'entry_date': entry_date,
                        'entry_price': entry_price,
                        'atr': atr,
                        'sector': get_stock_sector(symbol),
                        'weekday': entry_date.weekday(),
                        'future_data': df.iloc[i:i+31].copy()
                    })
        except:
            continue

    return signals

# =============================================================================
# STRATEGY EXECUTION
# =============================================================================

def run_strategy(signals: List[Dict], strategy: Dict, etf_data: Dict) -> Dict:
    """Run strategy on signals"""
    results = []
    exit_reasons = {}

    for signal in signals:
        # Entry day filter
        entry_days = strategy.get('entry_days')
        if entry_days is not None and signal['weekday'] not in entry_days:
            continue

        entry_price = signal['entry_price']
        atr = signal['atr']
        future_data = signal['future_data']
        sector = signal['sector']
        entry_date = signal['entry_date']

        tp_mult = strategy['tp_mult']
        sl_mult = strategy['sl_mult']
        max_hold = strategy['max_hold']

        sl_price = entry_price - (atr * sl_mult)
        tp_price = entry_price + (atr * tp_mult)

        # Trailing config
        trailing_config = strategy.get('trailing')
        trailing_active = False
        trailing_floor = 0

        # Recheck config
        recheck_config = strategy.get('recheck')
        trailing_params = strategy.get('trailing_params', {})
        entry_sector_strength = calculate_sector_strength(sector, etf_data, entry_date)

        exit_price = None
        exit_reason = None
        exit_day = None
        peak_price = entry_price

        for day in range(1, min(len(future_data), max_hold + 1)):
            current_date = future_data.index[day]
            current_price = float(future_data['Close'].iloc[day])
            high_price = float(future_data['High'].iloc[day])
            low_price = float(future_data['Low'].iloc[day])

            current_pnl = (current_price / entry_price - 1) * 100

            if current_price > peak_price:
                peak_price = current_price

            # Stop Loss
            if low_price <= sl_price:
                exit_price = sl_price
                exit_reason = "STOP_LOSS"
                exit_day = day
                break

            # Take Profit
            if high_price >= tp_price:
                exit_price = tp_price
                exit_reason = "TAKE_PROFIT"
                exit_day = day
                break

            # Trailing Stop (if active)
            if trailing_active and low_price <= trailing_floor:
                exit_price = trailing_floor
                exit_reason = "TRAIL_STOP"
                exit_day = day
                break

            # Auto Trailing activation
            if trailing_config and not trailing_active:
                activation = trailing_config['activation']
                if current_pnl >= activation:
                    trailing_active = True
                    lock_pct = trailing_config['lock']
                    trailing_floor = entry_price * (1 + (current_pnl / 100) * (lock_pct / 100))

            # Update trailing floor
            if trailing_active and current_price > peak_price:
                profit_pct = (current_price / entry_price - 1) * 100
                lock_pct = trailing_config['lock'] if trailing_config else 60
                trailing_floor = entry_price * (1 + (profit_pct / 100) * (lock_pct / 100))

            # Recheck logic (R5, R9)
            if recheck_config and not trailing_active:
                hist_data = future_data.iloc[:day+1]

                # R5: Sector weak
                if recheck_config.get('R5_sector_weak'):
                    curr_sector = calculate_sector_strength(sector, etf_data, current_date)
                    sector_change = curr_sector - entry_sector_strength
                    min_profit = recheck_config.get('R5_min_profit', 1.5)
                    if sector_change < -15 and current_pnl > min_profit:
                        act, lock = trailing_params.get('sector', (1.5, 55))
                        if current_pnl >= act:
                            trailing_active = True
                            trailing_floor = entry_price * (1 + (current_pnl / 100) * (lock / 100))

                # R9: Momentum fade
                if recheck_config.get('R9_momentum_fade') and not trailing_active:
                    mom = calculate_momentum(hist_data['Close'], min(3, day))
                    if mom < -2.0 and current_pnl > 0:
                        act, lock = trailing_params.get('momentum', (1.5, 60))
                        if current_pnl >= act:
                            trailing_active = True
                            trailing_floor = entry_price * (1 + (current_pnl / 100) * (lock / 100))

            # Max Hold
            if day >= max_hold:
                exit_price = current_price
                exit_reason = "MAX_HOLD"
                exit_day = day
                break

        if exit_price is None:
            exit_price = float(future_data['Close'].iloc[-1])
            exit_reason = "MAX_HOLD"
            exit_day = len(future_data) - 1

        pnl = (exit_price / entry_price - 1) * 100
        results.append({
            'pnl': pnl,
            'exit_reason': exit_reason,
            'days_held': exit_day,
        })
        exit_reasons[exit_reason] = exit_reasons.get(exit_reason, 0) + 1

    return calc_metrics(results, exit_reasons, strategy['name'])

def calc_metrics(results: List[Dict], exit_reasons: Dict, name: str) -> Dict:
    """Calculate metrics"""
    if not results:
        return {'name': name, 'trades': 0}

    df = pd.DataFrame(results)
    wins = df[df['pnl'] > 0]
    losses = df[df['pnl'] <= 0]

    win_rate = len(wins) / len(df) * 100
    avg_win = float(wins['pnl'].mean()) if len(wins) > 0 else 0
    avg_loss = abs(float(losses['pnl'].mean())) if len(losses) > 0 else 0
    expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)

    return {
        'name': name,
        'trades': len(df),
        'expectancy': expectancy,
        'win_rate': win_rate,
        'avg_hold': float(df['days_held'].mean()),
        'total_pnl': float(df['pnl'].sum()),
        'worst': float(df['pnl'].min()),
        'big_losses': len(df[df['pnl'] < -5]),
        'exit_dist': exit_reasons,
        'results_df': df,
    }

def simulate_capital(results_df: pd.DataFrame, start: float = 100000) -> Dict:
    """Simulate capital"""
    if len(results_df) == 0:
        return {'final': start, 'preserved': 100, 'max_dd': 0}

    capital = start
    peak = start
    max_dd = 0

    for _, trade in results_df.iterrows():
        capital += capital * 0.10 * (trade['pnl'] / 100)
        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return {
        'final': capital,
        'preserved': capital / start * 100,
        'max_dd': max_dd,
        'return': (capital / start - 1) * 100,
    }

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 100)
    print("CORRECT EXIT STRATEGY TEST")
    print("=" * 100)
    print("Entry: ทุกวัน (Dip-Bounce signal)")
    print("Compare: Different EXIT strategies")
    print()

    all_results = {period: {} for period in TEST_PERIODS}

    for period_key, period_info in TEST_PERIODS.items():
        print("=" * 100)
        print(f"{period_info['name']} ({period_info['start']} to {period_info['end']})")
        print("=" * 100)

        # Load data
        print("Loading data...")
        try:
            vix_data, spy_data, etf_data = load_period_data(period_info['start'], period_info['end'])
        except Exception as e:
            print(f"Failed: {e}")
            continue

        # Collect signals
        print("Collecting signals...")
        signals = collect_signals(period_info['start'], period_info['end'])
        print(f"Signals: {len(signals)}")

        if len(signals) == 0:
            continue

        # Test each strategy
        print()
        for strat_key, strategy in STRATEGIES.items():
            result = run_strategy(signals, strategy, etf_data)
            sim = simulate_capital(result.get('results_df', pd.DataFrame()))
            result['sim'] = sim
            all_results[period_key][strat_key] = result

        # Print results
        print(f"{'Strategy':<30} {'Trades':>7} {'E[R]':>8} {'Win%':>7} {'Hold':>6} {'Capital':>12} {'DD':>7}")
        print("-" * 90)

        for strat_key, result in all_results[period_key].items():
            if result['trades'] > 0:
                sim = result['sim']
                print(f"{result['name']:<30} {result['trades']:>7} {result['expectancy']:>+7.2f}% {result['win_rate']:>6.1f}% {result['avg_hold']:>5.1f}d ${sim['final']:>10,.0f} {sim['max_dd']:>6.1f}%")

        print()

    # =================================
    # AGGREGATE ANALYSIS
    # =================================

    print("=" * 100)
    print("AGGREGATE ANALYSIS")
    print("=" * 100)
    print()

    # Separate BULL and BEAR results
    bull_results = {}
    bear_results = {}

    for period_key, period_info in TEST_PERIODS.items():
        if period_info['type'] == 'BULL':
            for strat_key, result in all_results[period_key].items():
                bull_results[strat_key] = result
        else:
            if period_key not in all_results:
                continue
            for strat_key, result in all_results[period_key].items():
                if strat_key not in bear_results:
                    bear_results[strat_key] = {
                        'trades': 0, 'total_pnl': 0, 'wins': 0, 'losses': 0,
                        'wins_sum': 0, 'losses_sum': 0, 'big_losses': 0,
                        'results': []
                    }
                if result['trades'] > 0:
                    bear_results[strat_key]['trades'] += result['trades']
                    bear_results[strat_key]['total_pnl'] += result['total_pnl']
                    bear_results[strat_key]['big_losses'] += result['big_losses']
                    bear_results[strat_key]['results'].append(result['results_df'])

    # Calculate BEAR aggregate E[R]
    for strat_key in bear_results:
        if bear_results[strat_key]['trades'] > 0:
            combined_df = pd.concat(bear_results[strat_key]['results'])
            wins = combined_df[combined_df['pnl'] > 0]
            losses = combined_df[combined_df['pnl'] <= 0]
            win_rate = len(wins) / len(combined_df) * 100
            avg_win = float(wins['pnl'].mean()) if len(wins) > 0 else 0
            avg_loss = abs(float(losses['pnl'].mean())) if len(losses) > 0 else 0
            bear_results[strat_key]['expectancy'] = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)
            bear_results[strat_key]['win_rate'] = win_rate
            bear_results[strat_key]['combined_df'] = combined_df

    # Simulate BEAR capital
    for strat_key in bear_results:
        if 'combined_df' in bear_results[strat_key]:
            bear_results[strat_key]['sim'] = simulate_capital(bear_results[strat_key]['combined_df'])

    # Print comparison
    print("BULL Period (2023-2026):")
    print(f"{'Strategy':<30} {'Trades':>7} {'E[R]':>8} {'Return':>10} {'Capital':>12}")
    print("-" * 80)

    for strat_key in STRATEGIES:
        if strat_key in bull_results and bull_results[strat_key]['trades'] > 0:
            r = bull_results[strat_key]
            print(f"{r['name']:<30} {r['trades']:>7} {r['expectancy']:>+7.2f}% {r['sim']['return']:>+9.1f}% ${r['sim']['final']:>10,.0f}")

    print()
    print("BEAR Periods Combined (2022+2020+2018):")
    print(f"{'Strategy':<30} {'Trades':>7} {'E[R]':>8} {'Preserved':>10} {'Capital':>12}")
    print("-" * 80)

    for strat_key in STRATEGIES:
        if strat_key in bear_results and bear_results[strat_key]['trades'] > 0:
            r = bear_results[strat_key]
            if 'sim' in r:
                print(f"{STRATEGIES[strat_key]['name']:<30} {r['trades']:>7} {r['expectancy']:>+7.2f}% {r['sim']['preserved']:>9.1f}% ${r['sim']['final']:>10,.0f}")

    print()

    # =================================
    # FINAL COMPARISON
    # =================================

    print("=" * 100)
    print("FINAL COMPARISON")
    print("=" * 100)
    print()

    print(f"{'Strategy':<30} {'BULL Return':>12} {'BEAR Survive':>13} {'ALL-WEATHER':>12}")
    print("-" * 80)

    comparison = []
    for strat_key in STRATEGIES:
        bull_ret = bull_results[strat_key]['sim']['return'] if strat_key in bull_results and bull_results[strat_key]['trades'] > 0 else 0
        bear_surv = bear_results[strat_key]['sim']['preserved'] if strat_key in bear_results and 'sim' in bear_results[strat_key] else 0

        # All-weather score: geometric mean of BULL return factor and BEAR survival
        bull_factor = (1 + bull_ret / 100)
        bear_factor = bear_surv / 100
        all_weather = (bull_factor * bear_factor) ** 0.5 * 100 - 100  # Geometric mean as %

        comparison.append({
            'key': strat_key,
            'name': STRATEGIES[strat_key]['name'],
            'bull_ret': bull_ret,
            'bear_surv': bear_surv,
            'all_weather': all_weather,
        })

        print(f"{STRATEGIES[strat_key]['name']:<30} {bull_ret:>+11.1f}% {bear_surv:>12.1f}% {all_weather:>+11.1f}%")

    # Sort by all-weather score
    comparison.sort(key=lambda x: x['all_weather'], reverse=True)

    print()
    print("=" * 100)
    print("RANKING BY ALL-WEATHER PERFORMANCE")
    print("=" * 100)
    print()

    for i, c in enumerate(comparison, 1):
        meets_bull = c['bull_ret'] >= 200
        meets_bear = c['bear_surv'] >= 20
        status = "✅" if meets_bull and meets_bear else "❌"
        print(f"#{i}: {c['name']:<30} BULL: {c['bull_ret']:>+.1f}% | BEAR: {c['bear_surv']:>.1f}% | Score: {c['all_weather']:>+.1f}% {status}")

    print()

    # =================================
    # SUCCESS CRITERIA CHECK
    # =================================

    print("=" * 100)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 100)
    print()

    print("Criteria:")
    print("  1. Trade ทุกวัน (not Mon/Tue only)")
    print("  2. BEAR Survival ≥ 20%")
    print("  3. BULL Return ≥ +200%")
    print()

    winners = []
    for c in comparison:
        if c['key'] == 'TIME_BASED':
            continue  # Skip - not all days

        trades_all_days = True  # All except TIME_BASED
        meets_bear = c['bear_surv'] >= 20
        meets_bull = c['bull_ret'] >= 200

        if trades_all_days and meets_bear and meets_bull:
            winners.append(c)
            print(f"✅ {c['name']}: BULL {c['bull_ret']:+.1f}%, BEAR {c['bear_surv']:.1f}%")

    if not winners:
        print("❌ No strategy meets all criteria")
        print()
        print("Best compromise:")
        # Find best that trades all days
        all_day_strats = [c for c in comparison if c['key'] != 'TIME_BASED']
        if all_day_strats:
            best = max(all_day_strats, key=lambda x: x['all_weather'])
            print(f"  {best['name']}: BULL {best['bull_ret']:+.1f}%, BEAR {best['bear_surv']:.1f}%")

    print()

    # =================================
    # FINAL VERDICT
    # =================================

    print("=" * 100)
    print("FINAL VERDICT")
    print("=" * 100)
    print()

    best_all = comparison[0]
    best_all_days = max([c for c in comparison if c['key'] != 'TIME_BASED'], key=lambda x: x['all_weather'])

    print("┌" + "─" * 75 + "┐")
    print("│  EXIT STRATEGY TEST RESULTS" + " " * 46 + "│")
    print("├" + "─" * 75 + "┤")
    print("│" + " " * 75 + "│")

    line = f"BEST OVERALL: {best_all['name']}"
    print(f"│  {line:<73}│")
    line = f"├── BULL: {best_all['bull_ret']:+.1f}%  BEAR: {best_all['bear_surv']:.1f}%  Score: {best_all['all_weather']:+.1f}%"
    print(f"│  {line:<73}│")
    print("│" + " " * 75 + "│")

    line = f"BEST (ALL DAYS): {best_all_days['name']}"
    print(f"│  {line:<73}│")
    line = f"├── BULL: {best_all_days['bull_ret']:+.1f}%  BEAR: {best_all_days['bear_surv']:.1f}%  Score: {best_all_days['all_weather']:+.1f}%"
    print(f"│  {line:<73}│")
    print("│" + " " * 75 + "│")

    # Recommendation
    if best_all_days['bear_surv'] >= 20 and best_all_days['bull_ret'] >= 200:
        rec = f"USE {best_all_days['name']} - Meets all criteria"
    elif best_all['bear_surv'] >= 20:
        rec = f"USE {best_all['name']} even though Mon/Tue only"
    else:
        rec = "Dip-bounce strategy needs regime filter for BEAR protection"

    print(f"│  RECOMMENDATION:" + " " * 57 + "│")
    if len(rec) > 71:
        rec = rec[:68] + "..."
    print(f"│  └── {rec:<69}│")
    print("│" + " " * 75 + "│")
    print("└" + "─" * 75 + "┘")


if __name__ == "__main__":
    main()
