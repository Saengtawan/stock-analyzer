#!/usr/bin/env python3
"""
v5.4 Combined Validation Test

Validates that P1-P6 changes work well together before implementing v5.4.

Configs to test:
- v5.3 Baseline
- v5.4 All Changes
- v5.4 Conservative (VIX_30)
- v5.4 Partial (keep gap filter)

Primary metric: Expectancy (NOT Win Rate)
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("yfinance not available")


# ============================================================
# CONFIGURATION DEFINITIONS
# ============================================================

CONFIGS = {
    'v5.3_BASELINE': {
        'rsi_penalty': True,          # -4 for RSI>70, -2 for RSI>60
        'volume_penalty': True,       # -3 for vol<0.3, -2 for vol<0.5
        'min_score': 80,
        'gap_filter': 'original',     # block gap_up >2%
        'vix_regime': 25,             # skip if VIX > 25
        'sector_cooldown': True,
        'max_per_sector': 2,
        'desc': 'Current v5.3 settings',
    },
    'v5.4_ALL': {
        'rsi_penalty': False,         # REMOVED
        'volume_penalty': False,      # REMOVED
        'min_score': 85,              # CHANGED
        'gap_filter': 'block_down_1_3',  # Block gap down 1-3%
        'vix_regime': None,           # REMOVED
        'sector_cooldown': True,
        'max_per_sector': 2,
        'desc': 'All P1-P6 changes applied',
    },
    'v5.4_CONSERVATIVE': {
        'rsi_penalty': False,
        'volume_penalty': False,
        'min_score': 85,
        'gap_filter': 'block_down_1_3',
        'vix_regime': 30,             # Keep but relaxed to 30
        'sector_cooldown': True,
        'max_per_sector': 2,
        'desc': 'Conservative - keep VIX_30',
    },
    'v5.4_PARTIAL': {
        'rsi_penalty': False,
        'volume_penalty': False,
        'min_score': 85,
        'gap_filter': 'original',     # Keep original gap filter
        'vix_regime': None,
        'sector_cooldown': True,
        'max_per_sector': 2,
        'desc': 'Partial - keep original gap filter',
    },
}


# Sample stocks by sector
STOCKS_BY_SECTOR = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AVGO', 'QCOM', 'CRM', 'ADBE', 'NOW', 'ORCL'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN'],
    'Financial': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'V', 'MA', 'AXP'],
    'Consumer': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'WMT', 'COST', 'LOW'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'MPC', 'VLO', 'PSX', 'DVN'],
    'Industrial': ['CAT', 'DE', 'UNP', 'HON', 'GE', 'RTX', 'LMT', 'UPS', 'FDX', 'WM'],
    'Communication': ['GOOGL', 'META', 'NFLX', 'DIS', 'VZ', 'T', 'TMUS', 'CMCSA'],
}

SYMBOL_TO_SECTOR = {}
ALL_SYMBOLS = []
for sector, symbols in STOCKS_BY_SECTOR.items():
    for symbol in symbols:
        SYMBOL_TO_SECTOR[symbol] = sector
        ALL_SYMBOLS.append(symbol)


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def get_market_data(start_date: str, end_date: str):
    """Get SPY and VIX data"""
    try:
        spy = yf.Ticker('SPY').history(start=start_date, end=end_date)
        vix = yf.Ticker('^VIX').history(start=start_date, end=end_date)
        spy['sma50'] = spy['Close'].rolling(window=50).mean()
        return spy, vix
    except:
        return None, None


def calculate_base_score(yesterday_ret: float, today_ret: float, rsi: float,
                         sma20_above: bool, sma50_above: bool, atr_pct: float,
                         volume_ratio: float, config: Dict) -> Tuple[int, Dict]:
    """
    Calculate score based on config.
    Returns (score, details)
    """
    score = 50
    details = {'rsi_penalty': 0, 'vol_penalty': 0}

    # Dip-bounce
    if yesterday_ret <= -3:
        score += 30
    elif yesterday_ret <= -2:
        score += 20
    elif yesterday_ret <= -1:
        score += 10

    # Bounce
    if today_ret >= 3:
        score += 20
    elif today_ret >= 2:
        score += 15
    elif today_ret >= 1:
        score += 10

    # RSI scoring
    if 25 <= rsi <= 40:
        score += 35
    elif 40 < rsi <= 50:
        score += 20

    # RSI penalty (v5.3 only)
    if config['rsi_penalty']:
        if rsi > 70:
            score -= 4
            details['rsi_penalty'] = -4
        elif rsi > 60:
            score -= 2
            details['rsi_penalty'] = -2

    # Volume penalty (v5.3 only)
    if config['volume_penalty']:
        if volume_ratio < 0.3:
            score -= 3
            details['vol_penalty'] = -3
        elif volume_ratio < 0.5:
            score -= 2
            details['vol_penalty'] = -2

    # Trend
    if sma50_above and sma20_above:
        score += 25
    elif sma20_above:
        score += 15

    # Volatility
    if atr_pct > 5:
        score += 20
    elif atr_pct > 4:
        score += 15
    elif atr_pct > 3:
        score += 10

    details['final_score'] = score
    return score, details


def passes_gap_filter(gap_pct: float, config: Dict) -> bool:
    """Check if signal passes gap filter"""
    gap_filter = config['gap_filter']

    if gap_filter == 'original':
        # v5.3: block gap up > 2%
        if gap_pct > 2:
            return False
    elif gap_filter == 'block_down_1_3':
        # v5.4: block gap down 1-3%
        if -3 <= gap_pct <= -1:
            return False

    return True


def passes_vix_filter(vix: float, config: Dict) -> bool:
    """Check if signal passes VIX regime filter"""
    vix_threshold = config['vix_regime']

    if vix_threshold is None:
        return True  # No filter

    return vix <= vix_threshold


def get_all_raw_signals(start_date: str, end_date: str, spy: pd.DataFrame,
                        vix: pd.DataFrame) -> List[Dict]:
    """
    Get all raw signals with all data needed for filtering.
    No config applied yet.
    """
    all_signals = []

    for symbol in ALL_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist is None or len(hist) < 50:
                continue

            # Calculate indicators
            hist['prev_close'] = hist['Close'].shift(1)
            hist['daily_return'] = (hist['Close'] - hist['prev_close']) / hist['prev_close'] * 100
            hist['yesterday_return'] = hist['daily_return'].shift(1)
            hist['rsi'] = calculate_rsi(hist['Close'])
            hist['sma20'] = hist['Close'].rolling(window=20).mean()
            hist['sma50'] = hist['Close'].rolling(window=50).mean()

            # Gap
            hist['gap_pct'] = (hist['Open'] - hist['prev_close']) / hist['prev_close'] * 100

            # Volume ratio
            hist['avg_volume'] = hist['Volume'].rolling(window=20).mean()
            hist['volume_ratio'] = hist['Volume'] / hist['avg_volume']

            # ATR
            hist['tr'] = pd.concat([
                hist['High'] - hist['Low'],
                (hist['High'] - hist['Close'].shift(1)).abs(),
                (hist['Low'] - hist['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)
            hist['atr'] = hist['tr'].rolling(window=14).mean()
            hist['atr_pct'] = hist['atr'] / hist['Close'] * 100

            for i in range(50, len(hist) - 5):
                row = hist.iloc[i]
                signal_date = hist.index[i]

                yesterday_ret = row.get('yesterday_return', 0)
                today_ret = row.get('daily_return', 0)
                rsi = row.get('rsi', 50)
                gap_pct = row.get('gap_pct', 0)
                volume_ratio = row.get('volume_ratio', 1)

                if pd.isna(yesterday_ret) or pd.isna(today_ret) or pd.isna(rsi):
                    continue

                # Basic dip-bounce filter
                if not (yesterday_ret <= -2.0 and today_ret >= 1.0):
                    continue

                # Get VIX for this date
                try:
                    vix_dates = vix.index[vix.index <= signal_date]
                    vix_value = vix.loc[vix_dates[-1]]['Close'] if len(vix_dates) > 0 else 20

                    spy_dates = spy.index[spy.index <= signal_date]
                    if len(spy_dates) > 0:
                        spy_row = spy.loc[spy_dates[-1]]
                        spy_close = spy_row['Close']
                        spy_sma50 = spy_row.get('sma50', spy_close)
                    else:
                        spy_close = 0
                        spy_sma50 = 0
                except:
                    vix_value = 20
                    spy_close = 0
                    spy_sma50 = 0

                # Determine regime
                if vix_value > 25:
                    regime = 'BEAR'
                elif vix_value < 15 and spy_close > spy_sma50:
                    regime = 'BULL'
                else:
                    regime = 'NEUTRAL'

                # Calculate outcome
                entry_price = row['Close']
                future_highs = hist.iloc[i+1:i+6]['High'].values
                future_lows = hist.iloc[i+1:i+6]['Low'].values
                future_closes = hist.iloc[i+1:i+6]['Close'].values

                if len(future_closes) < 3:
                    continue

                # Simulate with TP +4%, SL -2%, max 4 days
                exit_return = 0
                max_drawdown = 0
                for j in range(min(4, len(future_closes))):
                    high_pct = (future_highs[j] - entry_price) / entry_price * 100
                    low_pct = (future_lows[j] - entry_price) / entry_price * 100
                    close_pct = (future_closes[j] - entry_price) / entry_price * 100

                    max_drawdown = min(max_drawdown, low_pct)

                    if low_pct <= -2.0:  # SL hit
                        exit_return = -2.0
                        break
                    elif high_pct >= 4.0:  # TP hit
                        exit_return = 4.0
                        break
                    exit_return = close_pct

                sma20_above = row['Close'] > row['sma20'] if not pd.isna(row['sma20']) else False
                sma50_above = row['Close'] > row['sma50'] if not pd.isna(row['sma50']) else False
                atr_pct = row['atr_pct'] if not pd.isna(row['atr_pct']) else 3.0

                all_signals.append({
                    'symbol': symbol,
                    'sector': SYMBOL_TO_SECTOR[symbol],
                    'date': signal_date,
                    'yesterday_return': yesterday_ret,
                    'today_return': today_ret,
                    'rsi': rsi,
                    'gap_pct': gap_pct,
                    'volume_ratio': volume_ratio if not pd.isna(volume_ratio) else 1,
                    'vix': vix_value,
                    'regime': regime,
                    'sma20_above': sma20_above,
                    'sma50_above': sma50_above,
                    'atr_pct': atr_pct,
                    'exit_return': exit_return,
                    'max_drawdown': max_drawdown,
                    'is_winner': exit_return > 0,
                })

        except Exception as e:
            continue

    # Sort by date then by potential score (rough estimate)
    all_signals.sort(key=lambda x: x['date'])
    return all_signals


def simulate_config(signals: List[Dict], config: Dict) -> Dict:
    """
    Simulate trading with a specific config.
    Returns performance metrics.
    """
    trades = []
    blocked = []

    current_date = None
    current_positions = []
    sector_counts = defaultdict(int)

    # Track sector cooldowns
    sector_losses = defaultdict(int)
    sector_cooldown_until = {}

    for signal in signals:
        signal_date = signal['date'].date()

        # New day reset
        if current_date != signal_date:
            current_positions = []
            sector_counts = defaultdict(int)
            current_date = signal_date

        # Calculate score for this config
        score, details = calculate_base_score(
            signal['yesterday_return'],
            signal['today_return'],
            signal['rsi'],
            signal['sma20_above'],
            signal['sma50_above'],
            signal['atr_pct'],
            signal['volume_ratio'],
            config
        )

        # Apply filters
        blocked_reason = None

        # 1. Score filter
        if score < config['min_score']:
            blocked_reason = 'SCORE'

        # 2. Gap filter
        if blocked_reason is None and not passes_gap_filter(signal['gap_pct'], config):
            blocked_reason = 'GAP'

        # 3. VIX filter
        if blocked_reason is None and not passes_vix_filter(signal['vix'], config):
            blocked_reason = 'VIX'

        # 4. Sector limit
        sector = signal['sector']
        if blocked_reason is None and sector_counts[sector] >= config['max_per_sector']:
            blocked_reason = 'SECTOR_LIMIT'

        # 5. Max positions
        if blocked_reason is None and len(current_positions) >= 3:
            blocked_reason = 'MAX_POS'

        # 6. Sector cooldown
        if blocked_reason is None and config['sector_cooldown']:
            if sector in sector_cooldown_until:
                if signal_date < sector_cooldown_until[sector]:
                    blocked_reason = 'SECTOR_COOLDOWN'

        if blocked_reason:
            signal['blocked_reason'] = blocked_reason
            blocked.append(signal)
        else:
            signal['score'] = score
            trades.append(signal)
            current_positions.append(signal['symbol'])
            sector_counts[sector] += 1

            # Update sector cooldown tracking
            if not signal['is_winner']:
                sector_losses[sector] += 1
                if sector_losses[sector] >= 2:
                    sector_cooldown_until[sector] = signal_date + timedelta(days=2)
                    sector_losses[sector] = 0
            else:
                sector_losses[sector] = 0

    # Calculate metrics
    if not trades:
        return {
            'trades': 0, 'win_rate': 0, 'expectancy': 0,
            'total_return': 0, 'max_dd': 0, 'profit_factor': 0,
            'blocked': len(blocked), 'blocked_winners': 0,
        }

    wins = [t for t in trades if t['is_winner']]
    losses = [t for t in trades if not t['is_winner']]

    win_rate = len(wins) / len(trades) * 100
    total_return = sum(t['exit_return'] for t in trades)
    avg_win = statistics.mean([t['exit_return'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['exit_return'] for t in losses]) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

    gross_profit = sum(t['exit_return'] for t in wins)
    gross_loss = abs(sum(t['exit_return'] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Max drawdown (simplified)
    max_dd = min(t['max_drawdown'] for t in trades) if trades else 0

    # Blocked analysis
    blocked_winners = len([b for b in blocked if b['is_winner']])

    # By regime
    regime_stats = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t['regime'] == regime]
        if regime_trades:
            r_wins = [t for t in regime_trades if t['is_winner']]
            r_losses = [t for t in regime_trades if not t['is_winner']]
            r_win_rate = len(r_wins) / len(regime_trades) * 100
            r_avg_win = statistics.mean([t['exit_return'] for t in r_wins]) if r_wins else 0
            r_avg_loss = statistics.mean([t['exit_return'] for t in r_losses]) if r_losses else 0
            r_expectancy = (r_win_rate / 100 * r_avg_win) + ((100 - r_win_rate) / 100 * r_avg_loss)
            regime_stats[regime] = {
                'trades': len(regime_trades),
                'win_rate': r_win_rate,
                'expectancy': r_expectancy,
            }
        else:
            regime_stats[regime] = {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    # By VIX level
    vix_stats = {}
    for vix_level, condition in [('VIX<15', lambda v: v < 15),
                                  ('VIX_15-25', lambda v: 15 <= v <= 25),
                                  ('VIX>25', lambda v: v > 25)]:
        vix_trades = [t for t in trades if condition(t['vix'])]
        if vix_trades:
            v_wins = [t for t in vix_trades if t['is_winner']]
            v_losses = [t for t in vix_trades if not t['is_winner']]
            v_win_rate = len(v_wins) / len(vix_trades) * 100
            v_avg_win = statistics.mean([t['exit_return'] for t in v_wins]) if v_wins else 0
            v_avg_loss = statistics.mean([t['exit_return'] for t in v_losses]) if v_losses else 0
            v_expectancy = (v_win_rate / 100 * v_avg_win) + ((100 - v_win_rate) / 100 * v_avg_loss)
            vix_stats[vix_level] = {
                'trades': len(vix_trades),
                'win_rate': v_win_rate,
                'expectancy': v_expectancy,
            }
        else:
            vix_stats[vix_level] = {'trades': 0, 'win_rate': 0, 'expectancy': 0}

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'expectancy': expectancy,
        'total_return': total_return,
        'max_dd': max_dd,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'blocked': len(blocked),
        'blocked_winners': blocked_winners,
        'regime_stats': regime_stats,
        'vix_stats': vix_stats,
    }


def test_interaction(signals: List[Dict], change1: str, change2: str) -> Dict:
    """Test interaction between two changes"""
    # Create configs with/without each change
    configs = {
        'neither': {'rsi_penalty': True, 'volume_penalty': True, 'min_score': 80,
                   'gap_filter': 'original', 'vix_regime': 25, 'sector_cooldown': True, 'max_per_sector': 2},
        'change1_only': {'rsi_penalty': True, 'volume_penalty': True, 'min_score': 80,
                        'gap_filter': 'original', 'vix_regime': 25, 'sector_cooldown': True, 'max_per_sector': 2},
        'change2_only': {'rsi_penalty': True, 'volume_penalty': True, 'min_score': 80,
                        'gap_filter': 'original', 'vix_regime': 25, 'sector_cooldown': True, 'max_per_sector': 2},
        'both': {'rsi_penalty': True, 'volume_penalty': True, 'min_score': 80,
                'gap_filter': 'original', 'vix_regime': 25, 'sector_cooldown': True, 'max_per_sector': 2},
    }

    # Apply changes
    if change1 == 'rsi_removal':
        configs['change1_only']['rsi_penalty'] = False
        configs['both']['rsi_penalty'] = False
    elif change1 == 'vix_removal':
        configs['change1_only']['vix_regime'] = None
        configs['both']['vix_regime'] = None
    elif change1 == 'score_85':
        configs['change1_only']['min_score'] = 85
        configs['both']['min_score'] = 85

    if change2 == 'vix_removal':
        configs['change2_only']['vix_regime'] = None
        configs['both']['vix_regime'] = None
    elif change2 == 'gap_change':
        configs['change2_only']['gap_filter'] = 'block_down_1_3'
        configs['both']['gap_filter'] = 'block_down_1_3'
    elif change2 == 'score_85':
        configs['change2_only']['min_score'] = 85
        configs['both']['min_score'] = 85

    results = {}
    for name, cfg in configs.items():
        results[name] = simulate_config(signals, cfg)

    # Calculate synergy
    neither_exp = results['neither']['expectancy']
    c1_exp = results['change1_only']['expectancy']
    c2_exp = results['change2_only']['expectancy']
    both_exp = results['both']['expectancy']

    individual_sum = (c1_exp - neither_exp) + (c2_exp - neither_exp)
    actual_combined = both_exp - neither_exp

    if individual_sum != 0:
        synergy_ratio = actual_combined / individual_sum
    else:
        synergy_ratio = 1.0

    return {
        'neither': neither_exp,
        'change1_only': c1_exp,
        'change2_only': c2_exp,
        'both': both_exp,
        'individual_sum': individual_sum,
        'actual_combined': actual_combined,
        'synergy_ratio': synergy_ratio,
        'synergy_type': 'POSITIVE' if synergy_ratio > 1.1 else ('NEGATIVE' if synergy_ratio < 0.9 else 'NEUTRAL'),
    }


def main():
    if not YFINANCE_AVAILABLE:
        print("Cannot run without yfinance")
        return

    print("=" * 70)
    print("v5.4 COMBINED VALIDATION TEST")
    print("=" * 70)
    print()

    # Date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

    print(f"Period: {start_date} to {end_date}")
    print(f"Stocks: {len(ALL_SYMBOLS)} across {len(STOCKS_BY_SECTOR)} sectors")
    print()

    # Get market data
    print("Loading market data...")
    spy, vix = get_market_data(start_date, end_date)
    if spy is None:
        print("Failed to load market data")
        return

    # Get all signals
    print("Collecting signals...")
    all_signals = get_all_raw_signals(start_date, end_date, spy, vix)
    print(f"Total raw signals: {len(all_signals)}")
    print()

    # ============================================================
    # SECTION A: MAIN CONFIG COMPARISON
    # ============================================================
    print("=" * 70)
    print("A. CONFIGURATION COMPARISON")
    print("=" * 70)
    print()

    results = {}
    for name, config in CONFIGS.items():
        results[name] = simulate_config(all_signals, config)

    print(f"{'Config':<20} {'Trades':<8} {'Win%':<8} {'E[R]':<10} {'Total%':<10} {'PF':<6} {'Blocked':<8}")
    print("-" * 75)

    for name, res in results.items():
        marker = " ← baseline" if name == 'v5.3_BASELINE' else ""
        print(f"{name:<20} {res['trades']:<8} {res['win_rate']:.1f}%{'':<3} "
              f"{res['expectancy']:+.3f}%{'':<4} {res['total_return']:+.1f}%{'':<5} "
              f"{res['profit_factor']:.2f}{'':<2} {res['blocked']:<8}{marker}")

    print()

    # ============================================================
    # SECTION B: REGIME PERFORMANCE
    # ============================================================
    print("=" * 70)
    print("B. PERFORMANCE BY REGIME")
    print("=" * 70)
    print()

    print(f"{'Config':<20} {'BULL E[R]':<12} {'BEAR E[R]':<12} {'NEUTRAL E[R]':<12}")
    print("-" * 60)

    for name, res in results.items():
        rs = res['regime_stats']
        bull_e = rs['BULL']['expectancy'] if rs['BULL']['trades'] > 0 else 0
        bear_e = rs['BEAR']['expectancy'] if rs['BEAR']['trades'] > 0 else 0
        neut_e = rs['NEUTRAL']['expectancy'] if rs['NEUTRAL']['trades'] > 0 else 0
        print(f"{name:<20} {bull_e:+.3f}%{'':<6} {bear_e:+.3f}%{'':<6} {neut_e:+.3f}%")

    print()

    # ============================================================
    # SECTION C: VIX STRESS TEST
    # ============================================================
    print("=" * 70)
    print("C. VIX LEVEL STRESS TEST")
    print("=" * 70)
    print()

    print(f"{'Config':<20} {'VIX<15 E[R]':<14} {'VIX 15-25 E[R]':<16} {'VIX>25 E[R]':<14}")
    print("-" * 65)

    for name, res in results.items():
        vs = res['vix_stats']
        v_low = vs['VIX<15']['expectancy'] if vs['VIX<15']['trades'] > 0 else 0
        v_mid = vs['VIX_15-25']['expectancy'] if vs['VIX_15-25']['trades'] > 0 else 0
        v_high = vs['VIX>25']['expectancy'] if vs['VIX>25']['trades'] > 0 else 0
        print(f"{name:<20} {v_low:+.3f}%{'':<8} {v_mid:+.3f}%{'':<10} {v_high:+.3f}%")

    print()

    # ============================================================
    # SECTION D: INTERACTION ANALYSIS
    # ============================================================
    print("=" * 70)
    print("D. INTERACTION ANALYSIS")
    print("=" * 70)
    print()

    interactions = [
        ('rsi_removal', 'score_85', 'RSI Removal + Score 85'),
        ('rsi_removal', 'vix_removal', 'RSI Removal + VIX Removal'),
        ('vix_removal', 'gap_change', 'VIX Removal + Gap Change'),
    ]

    print(f"{'Interaction':<30} {'Neither':<10} {'C1 Only':<10} {'C2 Only':<10} {'Both':<10} {'Synergy':<10}")
    print("-" * 85)

    for c1, c2, desc in interactions:
        interaction_result = test_interaction(all_signals, c1, c2)
        print(f"{desc:<30} {interaction_result['neither']:+.3f}%{'':<4} "
              f"{interaction_result['change1_only']:+.3f}%{'':<4} "
              f"{interaction_result['change2_only']:+.3f}%{'':<4} "
              f"{interaction_result['both']:+.3f}%{'':<4} "
              f"{interaction_result['synergy_type']:<10}")

    print()

    # ============================================================
    # SECTION E: KEY QUESTIONS
    # ============================================================
    print("=" * 70)
    print("E. KEY QUESTIONS ANSWERED")
    print("=" * 70)
    print()

    baseline = results['v5.3_BASELINE']
    v54_all = results['v5.4_ALL']
    v54_cons = results['v5.4_CONSERVATIVE']
    v54_partial = results['v5.4_PARTIAL']

    print("Q1: v5.4 All Changes ดีกว่า v5.3?")
    exp_diff = v54_all['expectancy'] - baseline['expectancy']
    print(f"    v5.3 Expectancy: {baseline['expectancy']:+.3f}%")
    print(f"    v5.4 Expectancy: {v54_all['expectancy']:+.3f}%")
    print(f"    Improvement: {exp_diff:+.3f}%")
    print(f"    Answer: {'YES ✅' if exp_diff > 0 else 'NO ❌'}")
    print()

    print("Q2: Changes ทำงานร่วมกันดี?")
    # Check interactions
    rsi_vix = test_interaction(all_signals, 'rsi_removal', 'vix_removal')
    print(f"    RSI + VIX removal: {rsi_vix['synergy_type']}")
    score_gap = test_interaction(all_signals, 'score_85', 'gap_change')
    print(f"    Score 85 + Gap change: {score_gap['synergy_type']}")
    print()

    print("Q3: Robust across conditions?")
    v54_vix = v54_all['vix_stats']
    works_low_vix = v54_vix['VIX<15']['expectancy'] > 0
    works_mid_vix = v54_vix['VIX_15-25']['expectancy'] > 0
    works_high_vix = v54_vix['VIX>25']['expectancy'] > 0
    print(f"    Low VIX (<15): {'✅' if works_low_vix else '❌'} E[R]={v54_vix['VIX<15']['expectancy']:+.3f}%")
    print(f"    Mid VIX (15-25): {'✅' if works_mid_vix else '❌'} E[R]={v54_vix['VIX_15-25']['expectancy']:+.3f}%")
    print(f"    High VIX (>25): {'✅' if works_high_vix else '❌'} E[R]={v54_vix['VIX>25']['expectancy']:+.3f}%")
    print()

    print("Q4: Best Config?")
    best_config = max(results.keys(), key=lambda k: results[k]['expectancy'])
    print(f"    Best: {best_config}")
    print(f"    E[R]: {results[best_config]['expectancy']:+.3f}%")
    print(f"    Trades: {results[best_config]['trades']}")
    print()

    # ============================================================
    # SECTION F: SUCCESS CRITERIA CHECK
    # ============================================================
    print("=" * 70)
    print("F. SUCCESS CRITERIA CHECK")
    print("=" * 70)
    print()

    best = results[best_config]

    criteria = [
        ('Expectancy > v5.3', best['expectancy'] > baseline['expectancy'],
         f"{best['expectancy']:+.3f}% vs {baseline['expectancy']:+.3f}%"),
        ('Max DD acceptable', best['max_dd'] >= -20, f"{best['max_dd']:.1f}%"),
        ('Works in BULL', best['regime_stats']['BULL']['expectancy'] > 0,
         f"E[R]={best['regime_stats']['BULL']['expectancy']:+.3f}%"),
        ('Works in BEAR', best['regime_stats']['BEAR']['expectancy'] > 0,
         f"E[R]={best['regime_stats']['BEAR']['expectancy']:+.3f}%"),
        ('Works in high VIX', best['vix_stats']['VIX>25']['expectancy'] > 0,
         f"E[R]={best['vix_stats']['VIX>25']['expectancy']:+.3f}%"),
        ('Trades >= 80% of v5.3', best['trades'] >= baseline['trades'] * 0.8,
         f"{best['trades']} vs {baseline['trades']}"),
    ]

    passed = 0
    for name, result, detail in criteria:
        status = '✅' if result else '❌'
        print(f"  {status} {name}: {detail}")
        if result:
            passed += 1

    print()
    print(f"Passed: {passed}/{len(criteria)}")
    print()

    # ============================================================
    # SECTION G: FINAL RECOMMENDATION
    # ============================================================
    print("=" * 70)
    print("G. FINAL RECOMMENDATION")
    print("=" * 70)
    print()

    print("┌" + "─" * 68 + "┐")
    print("│  v5.4 VALIDATION RESULTS" + " " * 43 + "│")
    print("├" + "─" * 68 + "┤")
    print(f"│  BEST CONFIG: {best_config:<53}│")
    print("│" + " " * 68 + "│")
    print("│  PERFORMANCE vs v5.3:" + " " * 45 + "│")
    exp_imp = ((best['expectancy'] - baseline['expectancy']) / abs(baseline['expectancy']) * 100) if baseline['expectancy'] != 0 else 0
    wr_imp = best['win_rate'] - baseline['win_rate']
    tr_imp = best['total_return'] - baseline['total_return']
    print(f"│  ├── Expectancy: {exp_imp:+.1f}% improvement ({best['expectancy']:+.3f}% vs {baseline['expectancy']:+.3f}%)" + " " * 5 + "│")
    print(f"│  ├── Win Rate: {wr_imp:+.1f}% ({best['win_rate']:.1f}% vs {baseline['win_rate']:.1f}%)" + " " * 15 + "│")
    print(f"│  ├── Total Return: {tr_imp:+.1f}% ({best['total_return']:+.1f}% vs {baseline['total_return']:+.1f}%)" + " " * 5 + "│")
    print(f"│  └── Trades: {best['trades']} vs {baseline['trades']}" + " " * 38 + "│")
    print("│" + " " * 68 + "│")

    # Determine decision
    if passed >= 5 and best['expectancy'] > baseline['expectancy']:
        decision = "IMPLEMENT v5.4"
        confidence = 85
    elif passed >= 4:
        decision = "IMPLEMENT with CAUTION"
        confidence = 70
    else:
        decision = "MODIFY before implement"
        confidence = 50

    print(f"│  DECISION: {decision:<56}│")
    print(f"│  CONFIDENCE: {confidence}%" + " " * 52 + "│")
    print("└" + "─" * 68 + "┘")
    print()

    # ============================================================
    # SECTION H: IMPLEMENTATION CONFIG
    # ============================================================
    if 'IMPLEMENT' in decision:
        print("=" * 70)
        print("H. IMPLEMENTATION CONFIG")
        print("=" * 70)
        print()
        print("```python")
        print("# v5.4 Final Configuration")
        print("V54_CONFIG = {")
        print("    # From v5.3 (keep)")
        print('    "stock_d_filter": True,')
        print('    "bear_dd_exempt": True,')
        print('    "sector_cooldown": True,')
        print('    "max_per_sector": 2,')
        print()
        print("    # P1: Scoring Penalties")
        print('    "rsi_penalty": None,      # REMOVED')
        print('    "volume_penalty": None,   # REMOVED')
        print()
        print("    # P2: Score Threshold")
        print('    "min_score": 85,          # CHANGED from 80')
        print()
        print("    # P5: Gap Filter")
        if best_config in ['v5.4_ALL', 'v5.4_CONSERVATIVE']:
            print('    "gap_filter": {')
            print('        "block_gap_down": [-0.03, -0.01],  # Block -1% to -3%')
            print('        "block_gap_up": None,')
            print('    },')
        else:
            print('    "gap_filter": "original",  # Keep +2%/-5%')
        print()
        print("    # P6: VIX Regime")
        if best_config == 'v5.4_CONSERVATIVE':
            print('    "vix_regime": 30,         # Relaxed to VIX_30')
        else:
            print('    "vix_regime": None,       # REMOVED')
        print("}")
        print("```")


if __name__ == '__main__':
    main()
