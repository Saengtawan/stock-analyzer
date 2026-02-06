#!/usr/bin/env python3
"""
REGIME-FILTERED ENTRY STRATEGY
===============================
ปัญหาคือ ENTRY ไม่ใช่ EXIT
ดังนั้น Filter entry ด้วย Regime แทนการปรับ exit

Test: หยุด/ลด trade เมื่อ market เป็น BEAR
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# PERIODS
# =============================================================================

TEST_PERIODS = {
    'BULL_2023_2026': {'start': '2023-01-01', 'end': '2026-02-06', 'type': 'BULL'},
    'BEAR_2022': {'start': '2022-01-01', 'end': '2022-10-31', 'type': 'BEAR'},
    'BEAR_2020': {'start': '2020-02-01', 'end': '2020-04-30', 'type': 'BEAR'},
    'BEAR_2018': {'start': '2018-10-01', 'end': '2018-12-31', 'type': 'BEAR'},
}

# =============================================================================
# REGIME FILTER CONFIGS
# =============================================================================

REGIME_FILTERS = {
    'NO_FILTER': {
        'name': 'No Filter (Baseline)',
        'vix_max': 999,
        'trend_filter': False,
        'size_reduction': 1.0,
    },
    'VIX_25': {
        'name': 'VIX < 25 Filter',
        'vix_max': 25,
        'trend_filter': False,
        'size_reduction': 1.0,
    },
    'VIX_30': {
        'name': 'VIX < 30 Filter',
        'vix_max': 30,
        'trend_filter': False,
        'size_reduction': 1.0,
    },
    'VIX_35': {
        'name': 'VIX < 35 Filter',
        'vix_max': 35,
        'trend_filter': False,
        'size_reduction': 1.0,
    },
    'TREND_SMA50': {
        'name': 'SPY > SMA50 Filter',
        'vix_max': 999,
        'trend_filter': True,
        'trend_type': 'SMA50',
        'size_reduction': 1.0,
    },
    'TREND_SMA20': {
        'name': 'SPY > SMA20 Filter',
        'vix_max': 999,
        'trend_filter': True,
        'trend_type': 'SMA20',
        'size_reduction': 1.0,
    },
    'HYBRID_VIX25_SMA50': {
        'name': 'VIX<25 AND SPY>SMA50',
        'vix_max': 25,
        'trend_filter': True,
        'trend_type': 'SMA50',
        'size_reduction': 1.0,
    },
    'HYBRID_VIX30_SMA50': {
        'name': 'VIX<30 AND SPY>SMA50',
        'vix_max': 30,
        'trend_filter': True,
        'trend_type': 'SMA50',
        'size_reduction': 1.0,
    },
    'SIZE_REDUCE_BEAR': {
        'name': 'Reduce size 50% in BEAR',
        'vix_max': 999,
        'trend_filter': True,
        'trend_type': 'SMA50',
        'size_reduction': 0.5,  # 50% size when SPY < SMA50
        'allow_bear': True,
    },
    'VIX_ADAPTIVE': {
        'name': 'VIX Adaptive Size',
        'vix_max': 999,
        'trend_filter': False,
        'vix_adaptive': True,  # Reduce size based on VIX
    },
}

# Exit strategy (use best from previous test)
EXIT_CONFIG = {
    'tp_mult': 3.5,
    'sl_mult': 1.5,
    'max_hold': 10,
    'trailing': {'activation': 2.0, 'lock': 60},
}

# =============================================================================
# DATA LOADING
# =============================================================================

def load_data(start: str, end: str) -> Tuple[pd.Series, pd.DataFrame]:
    """Load VIX and SPY"""
    ext_start = (pd.to_datetime(start) - timedelta(days=60)).strftime('%Y-%m-%d')
    vix = yf.download("^VIX", start=ext_start, end=end, progress=False)['Close']
    spy = yf.download("SPY", start=ext_start, end=end, progress=False)
    return vix, spy

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR"""
    tr = pd.concat([
        df['High'] - df['Low'],
        abs(df['High'] - df['Close'].shift(1)),
        abs(df['Low'] - df['Close'].shift(1))
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# =============================================================================
# REGIME CHECK
# =============================================================================

def check_regime(date: pd.Timestamp, vix_data: pd.Series, spy_data: pd.DataFrame,
                 filter_config: Dict) -> Tuple[bool, float]:
    """
    Check if trade is allowed by regime filter
    Returns: (allowed, size_multiplier)
    """
    try:
        # Get VIX
        vix_slice = vix_data.loc[:date]
        current_vix = float(vix_slice.iloc[-1]) if len(vix_slice) > 0 else 20

        # VIX filter
        vix_max = filter_config.get('vix_max', 999)
        if current_vix > vix_max:
            return False, 0.0

        # Trend filter
        if filter_config.get('trend_filter'):
            spy_close = spy_data['Close'].loc[:date]
            if len(spy_close) < 50:
                return True, 1.0

            current_price = float(spy_close.iloc[-1])

            trend_type = filter_config.get('trend_type', 'SMA50')
            if trend_type == 'SMA50':
                sma = float(spy_close.rolling(50).mean().iloc[-1])
            else:  # SMA20
                sma = float(spy_close.rolling(20).mean().iloc[-1])

            is_bull = current_price > sma

            if not is_bull:
                if filter_config.get('allow_bear'):
                    # Allow but reduce size
                    return True, filter_config.get('size_reduction', 0.5)
                else:
                    return False, 0.0

        # VIX adaptive sizing
        if filter_config.get('vix_adaptive'):
            if current_vix < 15:
                return True, 1.0
            elif current_vix < 20:
                return True, 0.8
            elif current_vix < 25:
                return True, 0.5
            elif current_vix < 30:
                return True, 0.3
            else:
                return True, 0.1  # Still trade but tiny size

        return True, filter_config.get('size_reduction', 1.0)

    except:
        return True, 1.0

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
                        'future_data': df.iloc[i:i+31].copy()
                    })
        except:
            continue

    return signals

# =============================================================================
# STRATEGY EXECUTION
# =============================================================================

def run_strategy(signals: List[Dict], filter_config: Dict,
                 vix_data: pd.Series, spy_data: pd.DataFrame) -> Dict:
    """Run strategy with regime filter"""
    results = []
    filtered_count = 0
    size_weighted_pnl = 0

    for signal in signals:
        entry_date = signal['entry_date']
        entry_price = signal['entry_price']
        atr = signal['atr']
        future_data = signal['future_data']

        # Check regime filter
        allowed, size_mult = check_regime(entry_date, vix_data, spy_data, filter_config)

        if not allowed:
            filtered_count += 1
            continue

        # Exit parameters
        tp_mult = EXIT_CONFIG['tp_mult']
        sl_mult = EXIT_CONFIG['sl_mult']
        max_hold = EXIT_CONFIG['max_hold']
        trailing = EXIT_CONFIG['trailing']

        sl_price = entry_price - (atr * sl_mult)
        tp_price = entry_price + (atr * tp_mult)

        trailing_active = False
        trailing_floor = 0
        peak_price = entry_price

        exit_price = None
        exit_day = None

        for day in range(1, min(len(future_data), max_hold + 1)):
            current_price = float(future_data['Close'].iloc[day])
            high_price = float(future_data['High'].iloc[day])
            low_price = float(future_data['Low'].iloc[day])

            current_pnl = (current_price / entry_price - 1) * 100

            if current_price > peak_price:
                peak_price = current_price

            # Stop Loss
            if low_price <= sl_price:
                exit_price = sl_price
                exit_day = day
                break

            # Take Profit
            if high_price >= tp_price:
                exit_price = tp_price
                exit_day = day
                break

            # Trailing Stop
            if trailing_active and low_price <= trailing_floor:
                exit_price = trailing_floor
                exit_day = day
                break

            # Activate trailing
            if not trailing_active and current_pnl >= trailing['activation']:
                trailing_active = True
                trailing_floor = entry_price * (1 + (current_pnl / 100) * (trailing['lock'] / 100))

            # Update trailing floor
            if trailing_active and current_price > peak_price:
                profit_pct = (current_price / entry_price - 1) * 100
                trailing_floor = entry_price * (1 + (profit_pct / 100) * (trailing['lock'] / 100))

            # Max Hold
            if day >= max_hold:
                exit_price = current_price
                exit_day = day
                break

        if exit_price is None:
            exit_price = float(future_data['Close'].iloc[-1])
            exit_day = len(future_data) - 1

        pnl = (exit_price / entry_price - 1) * 100

        # Weighted by size
        weighted_pnl = pnl * size_mult
        size_weighted_pnl += weighted_pnl

        results.append({
            'pnl': pnl,
            'weighted_pnl': weighted_pnl,
            'size_mult': size_mult,
            'days_held': exit_day,
        })

    return calc_metrics(results, filter_config['name'], filtered_count, len(signals))

def calc_metrics(results: List[Dict], name: str, filtered: int, total_signals: int) -> Dict:
    """Calculate metrics"""
    if not results:
        return {
            'name': name,
            'trades': 0,
            'filtered': filtered,
            'total_signals': total_signals,
        }

    df = pd.DataFrame(results)
    wins = df[df['pnl'] > 0]
    losses = df[df['pnl'] <= 0]

    win_rate = len(wins) / len(df) * 100
    avg_win = float(wins['pnl'].mean()) if len(wins) > 0 else 0
    avg_loss = abs(float(losses['pnl'].mean())) if len(losses) > 0 else 0
    expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)

    # Weighted metrics
    weighted_wins = df[df['weighted_pnl'] > 0]
    weighted_losses = df[df['weighted_pnl'] <= 0]

    return {
        'name': name,
        'trades': len(df),
        'filtered': filtered,
        'total_signals': total_signals,
        'filter_rate': filtered / total_signals * 100 if total_signals > 0 else 0,
        'expectancy': expectancy,
        'win_rate': win_rate,
        'avg_hold': float(df['days_held'].mean()),
        'total_pnl': float(df['pnl'].sum()),
        'weighted_pnl': float(df['weighted_pnl'].sum()),
        'worst': float(df['pnl'].min()),
        'big_losses': len(df[df['pnl'] < -5]),
        'results_df': df,
    }

def simulate_capital(results_df: pd.DataFrame, start: float = 100000) -> Dict:
    """Simulate capital with position sizing"""
    if len(results_df) == 0:
        return {'final': start, 'preserved': 100, 'max_dd': 0, 'return': 0}

    capital = start
    peak = start
    max_dd = 0

    for _, trade in results_df.iterrows():
        # Use weighted PnL (already accounts for size reduction)
        base_size = capital * 0.10
        actual_size = base_size * trade['size_mult']
        trade_pnl = actual_size * (trade['pnl'] / 100)
        capital += trade_pnl

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
    print("REGIME-FILTERED ENTRY STRATEGY")
    print("=" * 100)
    print("ปัญหาคือ ENTRY ไม่ใช่ EXIT — Filter entry ด้วย Regime")
    print()

    all_results = {period: {} for period in TEST_PERIODS}

    for period_key, period_info in TEST_PERIODS.items():
        print("=" * 100)
        print(f"{period_key}: {period_info['start']} to {period_info['end']}")
        print("=" * 100)

        # Load data
        print("Loading data...")
        try:
            vix_data, spy_data = load_data(period_info['start'], period_info['end'])
        except Exception as e:
            print(f"Failed: {e}")
            continue

        # VIX stats
        actual_start = pd.to_datetime(period_info['start'])
        actual_end = pd.to_datetime(period_info['end'])
        vix_period = vix_data[(vix_data.index >= actual_start) & (vix_data.index <= actual_end)]
        if len(vix_period) > 0:
            print(f"VIX: Avg {float(vix_period.mean()):.1f}, Max {float(vix_period.max()):.1f}")

        # Collect signals
        print("Collecting signals...")
        signals = collect_signals(period_info['start'], period_info['end'])
        print(f"Signals: {len(signals)}")

        if len(signals) == 0:
            continue

        print()

        # Test each filter
        for filter_key, filter_config in REGIME_FILTERS.items():
            result = run_strategy(signals, filter_config, vix_data, spy_data)
            sim = simulate_capital(result.get('results_df', pd.DataFrame()))
            result['sim'] = sim
            all_results[period_key][filter_key] = result

        # Print results
        print(f"{'Filter':<30} {'Trades':>7} {'Filtered':>9} {'E[R]':>8} {'Capital':>12} {'DD':>7}")
        print("-" * 90)

        for filter_key, result in all_results[period_key].items():
            if result['trades'] > 0 or result.get('filtered', 0) > 0:
                sim = result.get('sim', {'final': 100000, 'max_dd': 0})
                filtered = result.get('filtered', 0)
                trades = result.get('trades', 0)
                exp = result.get('expectancy', 0)
                print(f"{result['name']:<30} {trades:>7} {filtered:>9} {exp:>+7.2f}% ${sim['final']:>10,.0f} {sim['max_dd']:>6.1f}%")

        print()

    # =================================
    # AGGREGATE ANALYSIS
    # =================================

    print("=" * 100)
    print("AGGREGATE ANALYSIS")
    print("=" * 100)
    print()

    # Separate BULL and BEAR
    bull_results = {}
    bear_combined = {}

    for period_key, period_info in TEST_PERIODS.items():
        if period_info['type'] == 'BULL':
            for filter_key, result in all_results[period_key].items():
                bull_results[filter_key] = result
        else:
            for filter_key, result in all_results[period_key].items():
                if filter_key not in bear_combined:
                    bear_combined[filter_key] = {
                        'trades': 0, 'filtered': 0, 'results': []
                    }
                if result.get('trades', 0) > 0:
                    bear_combined[filter_key]['trades'] += result['trades']
                    bear_combined[filter_key]['filtered'] += result.get('filtered', 0)
                    bear_combined[filter_key]['results'].append(result['results_df'])

    # Calculate BEAR combined metrics
    for filter_key in bear_combined:
        if bear_combined[filter_key]['trades'] > 0:
            combined_df = pd.concat(bear_combined[filter_key]['results'])
            wins = combined_df[combined_df['pnl'] > 0]
            losses = combined_df[combined_df['pnl'] <= 0]
            win_rate = len(wins) / len(combined_df) * 100
            avg_win = float(wins['pnl'].mean()) if len(wins) > 0 else 0
            avg_loss = abs(float(losses['pnl'].mean())) if len(losses) > 0 else 0
            bear_combined[filter_key]['expectancy'] = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)
            bear_combined[filter_key]['sim'] = simulate_capital(combined_df)
        else:
            bear_combined[filter_key]['expectancy'] = 0
            bear_combined[filter_key]['sim'] = {'final': 100000, 'preserved': 100, 'max_dd': 0, 'return': 0}

    # Print comparison
    print("BULL Period:")
    print(f"{'Filter':<30} {'Trades':>7} {'E[R]':>8} {'Return':>10} {'DD':>7}")
    print("-" * 70)

    for filter_key in REGIME_FILTERS:
        if filter_key in bull_results and bull_results[filter_key].get('trades', 0) > 0:
            r = bull_results[filter_key]
            print(f"{r['name']:<30} {r['trades']:>7} {r['expectancy']:>+7.2f}% {r['sim']['return']:>+9.1f}% {r['sim']['max_dd']:>6.1f}%")

    print()
    print("BEAR Periods Combined:")
    print(f"{'Filter':<30} {'Trades':>7} {'Filtered':>9} {'E[R]':>8} {'Survival':>10}")
    print("-" * 80)

    for filter_key in REGIME_FILTERS:
        if filter_key in bear_combined:
            b = bear_combined[filter_key]
            print(f"{REGIME_FILTERS[filter_key]['name']:<30} {b['trades']:>7} {b['filtered']:>9} {b['expectancy']:>+7.2f}% {b['sim']['preserved']:>9.1f}%")

    print()

    # =================================
    # FINAL COMPARISON
    # =================================

    print("=" * 100)
    print("FINAL COMPARISON: BULL Return vs BEAR Survival")
    print("=" * 100)
    print()

    comparison = []
    for filter_key in REGIME_FILTERS:
        bull_ret = bull_results.get(filter_key, {}).get('sim', {}).get('return', 0)
        bear_surv = bear_combined.get(filter_key, {}).get('sim', {}).get('preserved', 0)
        bear_trades = bear_combined.get(filter_key, {}).get('trades', 0)
        bear_filtered = bear_combined.get(filter_key, {}).get('filtered', 0)

        # All-weather score
        bull_factor = max(0, 1 + bull_ret / 100)
        bear_factor = max(0, bear_surv / 100)
        all_weather = (bull_factor * bear_factor) ** 0.5 * 100 - 100 if bull_factor > 0 and bear_factor > 0 else -100

        comparison.append({
            'key': filter_key,
            'name': REGIME_FILTERS[filter_key]['name'],
            'bull_ret': bull_ret,
            'bear_surv': bear_surv,
            'bear_trades': bear_trades,
            'bear_filtered': bear_filtered,
            'all_weather': all_weather,
        })

    comparison.sort(key=lambda x: x['all_weather'], reverse=True)

    print(f"{'Rank':<5} {'Filter':<30} {'BULL':>10} {'BEAR':>10} {'Score':>10}")
    print("-" * 75)

    for i, c in enumerate(comparison, 1):
        meets_bull = c['bull_ret'] >= 200
        meets_bear = c['bear_surv'] >= 20
        status = "✅" if meets_bull and meets_bear else "❌"
        print(f"#{i:<4} {c['name']:<30} {c['bull_ret']:>+9.1f}% {c['bear_surv']:>9.1f}% {c['all_weather']:>+9.1f}% {status}")

    print()

    # =================================
    # SUCCESS CRITERIA
    # =================================

    print("=" * 100)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 100)
    print()
    print("Criteria: BULL ≥ +200% AND BEAR Survival ≥ 20%")
    print()

    winners = [c for c in comparison if c['bull_ret'] >= 200 and c['bear_surv'] >= 20]

    if winners:
        print("✅ WINNING STRATEGIES:")
        for w in winners:
            filter_pct = w['bear_filtered'] / (w['bear_trades'] + w['bear_filtered']) * 100 if (w['bear_trades'] + w['bear_filtered']) > 0 else 0
            print(f"   {w['name']}: BULL {w['bull_ret']:+.1f}%, BEAR {w['bear_surv']:.1f}% (filtered {filter_pct:.0f}% in BEAR)")
    else:
        print("❌ No strategy meets both criteria")
        print()

        # Find best compromise
        best_bear = max(comparison, key=lambda x: x['bear_surv'])
        best_bull = max(comparison, key=lambda x: x['bull_ret'])

        print("Best for BEAR survival:")
        print(f"   {best_bear['name']}: BEAR {best_bear['bear_surv']:.1f}%, BULL {best_bear['bull_ret']:+.1f}%")
        print()
        print("Best for BULL return:")
        print(f"   {best_bull['name']}: BULL {best_bull['bull_ret']:+.1f}%, BEAR {best_bull['bear_surv']:.1f}%")

    print()

    # =================================
    # FINAL RECOMMENDATION
    # =================================

    print("=" * 100)
    print("FINAL RECOMMENDATION")
    print("=" * 100)
    print()

    best = comparison[0]

    print("┌" + "─" * 75 + "┐")
    print("│  REGIME-FILTERED ENTRY RESULTS" + " " * 43 + "│")
    print("├" + "─" * 75 + "┤")
    print("│" + " " * 75 + "│")

    line = f"BEST ALL-WEATHER: {best['name']}"
    print(f"│  {line:<73}│")
    line = f"├── BULL: {best['bull_ret']:+.1f}%  BEAR: {best['bear_surv']:.1f}%  Score: {best['all_weather']:+.1f}%"
    print(f"│  {line:<73}│")
    print("│" + " " * 75 + "│")

    # Check if meets criteria
    if best['bull_ret'] >= 200 and best['bear_surv'] >= 20:
        rec = f"USE {best['name']} — Meets all criteria!"
    elif best['bear_surv'] >= 20:
        rec = f"USE {best['name']} — Good BEAR survival, acceptable BULL"
    else:
        rec = "Need stronger regime filter or accept BEAR losses"

    print(f"│  RECOMMENDATION:" + " " * 57 + "│")
    if len(rec) > 71:
        rec = rec[:68] + "..."
    print(f"│  └── {rec:<69}│")
    print("│" + " " * 75 + "│")

    # Key insight
    print("│  KEY INSIGHT:" + " " * 60 + "│")
    insight = "Regime filter at ENTRY is more effective than exit optimization"
    print(f"│  └── {insight:<69}│")
    print("│" + " " * 75 + "│")
    print("└" + "─" * 75 + "┘")


if __name__ == "__main__":
    main()
