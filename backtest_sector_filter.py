#!/usr/bin/env python3
"""
Smart Sector Filter Backtest
Compare different sector filter strategies for Dip-Bounce trading
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financials': 'XLF',
    'Consumer Discretionary': 'XLY',
    'Communication Services': 'XLC',
    'Industrials': 'XLI',
    'Consumer Staples': 'XLP',
    'Energy': 'XLE',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Materials': 'XLB'
}

# Stock universe - top stocks per sector for simulation
STOCK_UNIVERSE = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'AMD', 'CRM', 'ADBE', 'ORCL', 'CSCO', 'INTC'],
    'Healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'],
    'Financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'SCHW', 'AXP', 'C', 'USB'],
    'Consumer Discretionary': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TJX', 'LOW', 'BKNG', 'CMG'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'EA'],
    'Industrials': ['CAT', 'GE', 'UNP', 'HON', 'UPS', 'BA', 'RTX', 'DE', 'LMT', 'MMM'],
    'Consumer Staples': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'MO', 'CL', 'MDLZ', 'KHC'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PXD', 'PSX', 'VLO', 'OXY'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'WEC'],
    'Real Estate': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'SPG', 'O', 'WELL', 'DLR', 'AVB'],
    'Materials': ['LIN', 'APD', 'SHW', 'FCX', 'ECL', 'NEM', 'NUE', 'DD', 'DOW', 'PPG']
}

# Reverse mapping: stock -> sector
STOCK_TO_SECTOR = {}
for sector, stocks in STOCK_UNIVERSE.items():
    for stock in stocks:
        STOCK_TO_SECTOR[stock] = sector

# Trade parameters
DIP_THRESHOLD = -2.0  # Yesterday must dip at least -2%
BOUNCE_THRESHOLD = 1.0  # Today must bounce at least +1%
TAKE_PROFIT = 3.0  # +3% TP
STOP_LOSS = -2.0  # -2% SL
MAX_HOLD_DAYS = 3  # Max hold period

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Trade:
    symbol: str
    sector: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    hold_days: int
    exit_reason: str  # 'TP', 'SL', 'EOD', 'MAX_HOLD'
    sector_1d: float
    sector_5d: float
    sector_20d: float
    spy_20d: float
    vix: float
    market_regime: str

@dataclass
class FilterResult:
    option_name: str
    total_trades: int
    passed_trades: int
    win_rate: float
    avg_pnl: float
    total_pnl: float
    max_drawdown: float
    sharpe: float
    trades_per_month: float
    false_positive_rate: float  # passed but lost
    missed_opportunity_rate: float  # blocked but would have won

# ============================================================================
# DATA DOWNLOAD
# ============================================================================

def download_data(period='1y') -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Download all required data"""
    print("📥 Downloading data...")

    # Download sector ETFs
    etf_symbols = list(SECTOR_ETFS.values()) + ['SPY', '^VIX']
    etf_data = yf.download(etf_symbols, period=period, progress=False)

    # Download stock data
    all_stocks = list(STOCK_TO_SECTOR.keys())
    stock_data = yf.download(all_stocks, period=period, progress=False)

    print(f"✅ Downloaded {len(etf_data)} days of ETF data")
    print(f"✅ Downloaded {len(stock_data)} days of stock data")

    return etf_data, stock_data, etf_symbols

def calculate_returns(prices: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Calculate 1d, 5d, 20d returns for each symbol"""
    returns = {}

    for col in prices.columns:
        df = pd.DataFrame()
        df['close'] = prices[col]
        df['return_1d'] = prices[col].pct_change() * 100
        df['return_5d'] = prices[col].pct_change(5) * 100
        df['return_20d'] = prices[col].pct_change(20) * 100
        returns[col] = df

    return returns

# ============================================================================
# SECTOR FILTER OPTIONS
# ============================================================================

def filter_option_a(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option A: 5d Return Only"""
    return sector_5d > 0

def filter_option_b(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option B: 20d Up + 5d Down (Pullback in Uptrend)"""
    return sector_20d > 0 and sector_5d < 0

def filter_option_c(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option C: 20d Up + (5d Down OR 1d Up)"""
    return sector_20d > 0 and (sector_5d < 0 or sector_1d > 0)

def filter_option_d(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option D: Relative Strength vs SPY"""
    return (sector_20d - spy_20d) > 0

def filter_option_e(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option E: Multi-Timeframe Composite Score"""
    score = (sector_20d * 0.3) + (sector_5d * 0.3) + (sector_1d * 0.4)
    return score > 0

def filter_option_f(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option F: Smart Sector (Adaptive by Regime)"""
    if regime == 'BULL':
        return sector_20d > -5
    elif regime == 'BEAR':
        return sector_20d > 0 and sector_5d < 0 and sector_1d > 0
    else:  # NEUTRAL
        return sector_20d > 0 or (sector_5d > 0 and sector_1d > 0)

def filter_option_g(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option G: 20d Up + Low Volatility (proxy: not extreme moves)"""
    return sector_20d > 0 and abs(sector_1d) < 3

def filter_option_h(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Option H: No Filter (Baseline)"""
    return True

def filter_current(sector_1d, sector_5d, sector_20d, spy_20d, regime) -> bool:
    """Current System: 20d Return Only"""
    return sector_20d > 0

FILTER_OPTIONS = {
    'A_5d_only': filter_option_a,
    'B_pullback': filter_option_b,
    'C_20d_flex': filter_option_c,
    'D_rel_strength': filter_option_d,
    'E_composite': filter_option_e,
    'F_adaptive': filter_option_f,
    'G_low_vol': filter_option_g,
    'H_no_filter': filter_option_h,
    'CURRENT_20d': filter_current,
}

# ============================================================================
# MARKET REGIME DETECTION
# ============================================================================

def get_market_regime(spy_20d: float, vix: float) -> str:
    """Determine market regime based on SPY and VIX"""
    if spy_20d > 5 and vix < 20:
        return 'BULL'
    elif spy_20d < -5 or vix > 25:
        return 'BEAR'
    else:
        return 'NEUTRAL'

# ============================================================================
# TRADE SIMULATION
# ============================================================================

def find_dip_bounce_signals(stock_data: pd.DataFrame, stock: str) -> List[Tuple[str, float]]:
    """Find dip-bounce entry signals for a stock"""
    signals = []

    try:
        if ('Close', stock) not in stock_data.columns:
            return signals

        closes = stock_data[('Close', stock)].dropna()

        for i in range(2, len(closes)):
            date = closes.index[i]
            today_close = closes.iloc[i]
            yesterday_close = closes.iloc[i-1]
            day_before_close = closes.iloc[i-2]

            # Calculate returns
            yesterday_return = (yesterday_close / day_before_close - 1) * 100
            today_return = (today_close / yesterday_close - 1) * 100

            # Dip-bounce signal
            if yesterday_return <= DIP_THRESHOLD and today_return >= BOUNCE_THRESHOLD:
                signals.append((date.strftime('%Y-%m-%d'), today_close))
    except Exception as e:
        pass

    return signals

def simulate_trade(stock_data: pd.DataFrame, stock: str, entry_date: str, entry_price: float) -> Optional[Tuple[str, float, float, int, str]]:
    """Simulate a trade from entry to exit"""
    try:
        closes = stock_data[('Close', stock)].dropna()
        dates = closes.index

        # Find entry date index
        entry_idx = None
        for i, d in enumerate(dates):
            if d.strftime('%Y-%m-%d') == entry_date:
                entry_idx = i
                break

        if entry_idx is None:
            return None

        # Simulate holding period
        for hold_days in range(1, MAX_HOLD_DAYS + 1):
            if entry_idx + hold_days >= len(closes):
                break

            current_price = closes.iloc[entry_idx + hold_days]
            pnl_pct = (current_price / entry_price - 1) * 100

            # Check TP/SL
            if pnl_pct >= TAKE_PROFIT:
                exit_date = dates[entry_idx + hold_days].strftime('%Y-%m-%d')
                return (exit_date, current_price, pnl_pct, hold_days, 'TP')
            elif pnl_pct <= STOP_LOSS:
                exit_date = dates[entry_idx + hold_days].strftime('%Y-%m-%d')
                return (exit_date, current_price, pnl_pct, hold_days, 'SL')

        # Exit at max hold
        if entry_idx + MAX_HOLD_DAYS < len(closes):
            exit_price = closes.iloc[entry_idx + MAX_HOLD_DAYS]
            pnl_pct = (exit_price / entry_price - 1) * 100
            exit_date = dates[entry_idx + MAX_HOLD_DAYS].strftime('%Y-%m-%d')
            return (exit_date, exit_price, pnl_pct, MAX_HOLD_DAYS, 'MAX_HOLD')

        return None
    except Exception as e:
        return None

# ============================================================================
# BACKTEST ENGINE
# ============================================================================

def run_backtest(etf_data: pd.DataFrame, stock_data: pd.DataFrame) -> List[Trade]:
    """Run backtest and generate all trades"""
    print("\n🔄 Running backtest simulation...")

    # Calculate sector returns
    sector_returns = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            closes = etf_data[('Close', etf)].dropna()
            df = pd.DataFrame(index=closes.index)
            df['return_1d'] = closes.pct_change() * 100
            df['return_5d'] = closes.pct_change(5) * 100
            df['return_20d'] = closes.pct_change(20) * 100
            sector_returns[sector] = df
        except:
            pass

    # SPY returns
    spy_closes = etf_data[('Close', 'SPY')].dropna()
    spy_returns = pd.DataFrame(index=spy_closes.index)
    spy_returns['return_20d'] = spy_closes.pct_change(20) * 100

    # VIX
    try:
        vix_data = etf_data[('Close', '^VIX')].dropna()
    except:
        vix_data = pd.Series(index=spy_closes.index, data=20)  # default

    all_trades = []

    # Find all signals and simulate trades
    for stock, sector in STOCK_TO_SECTOR.items():
        signals = find_dip_bounce_signals(stock_data, stock)

        for entry_date, entry_price in signals:
            # Get sector metrics for this date
            try:
                date_idx = pd.Timestamp(entry_date)

                if sector not in sector_returns:
                    continue
                if date_idx not in sector_returns[sector].index:
                    continue

                sector_1d = sector_returns[sector].loc[date_idx, 'return_1d']
                sector_5d = sector_returns[sector].loc[date_idx, 'return_5d']
                sector_20d = sector_returns[sector].loc[date_idx, 'return_20d']

                spy_20d = spy_returns.loc[date_idx, 'return_20d'] if date_idx in spy_returns.index else 0
                vix = vix_data.loc[date_idx] if date_idx in vix_data.index else 20

                if pd.isna(sector_1d) or pd.isna(sector_5d) or pd.isna(sector_20d):
                    continue

                regime = get_market_regime(spy_20d, vix)

            except Exception as e:
                continue

            # Simulate trade
            result = simulate_trade(stock_data, stock, entry_date, entry_price)
            if result is None:
                continue

            exit_date, exit_price, pnl_pct, hold_days, exit_reason = result

            trade = Trade(
                symbol=stock,
                sector=sector,
                entry_date=entry_date,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=exit_price,
                pnl_pct=pnl_pct,
                hold_days=hold_days,
                exit_reason=exit_reason,
                sector_1d=sector_1d,
                sector_5d=sector_5d,
                sector_20d=sector_20d,
                spy_20d=spy_20d,
                vix=vix,
                market_regime=regime
            )
            all_trades.append(trade)

    print(f"✅ Generated {len(all_trades)} trades")
    return all_trades

def evaluate_filter(trades: List[Trade], filter_name: str, filter_func) -> FilterResult:
    """Evaluate a filter option against all trades"""

    passed_trades = []
    blocked_trades = []

    for trade in trades:
        passed = filter_func(
            trade.sector_1d,
            trade.sector_5d,
            trade.sector_20d,
            trade.spy_20d,
            trade.market_regime
        )
        if passed:
            passed_trades.append(trade)
        else:
            blocked_trades.append(trade)

    if len(passed_trades) == 0:
        return FilterResult(
            option_name=filter_name,
            total_trades=len(trades),
            passed_trades=0,
            win_rate=0,
            avg_pnl=0,
            total_pnl=0,
            max_drawdown=0,
            sharpe=0,
            trades_per_month=0,
            false_positive_rate=0,
            missed_opportunity_rate=0
        )

    # Calculate metrics
    wins = [t for t in passed_trades if t.pnl_pct > 0]
    losses = [t for t in passed_trades if t.pnl_pct <= 0]
    blocked_wins = [t for t in blocked_trades if t.pnl_pct > 0]

    win_rate = len(wins) / len(passed_trades) * 100
    avg_pnl = np.mean([t.pnl_pct for t in passed_trades])
    total_pnl = sum([t.pnl_pct for t in passed_trades])

    # Max drawdown
    cumulative = np.cumsum([t.pnl_pct for t in passed_trades])
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0

    # Sharpe (simplified)
    pnls = [t.pnl_pct for t in passed_trades]
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    # Trades per month (assuming 1 year of data)
    trades_per_month = len(passed_trades) / 12

    # False positive rate (passed but lost)
    false_positive_rate = len(losses) / len(passed_trades) * 100 if len(passed_trades) > 0 else 0

    # Missed opportunity rate (blocked but would have won)
    missed_opportunity_rate = len(blocked_wins) / len(blocked_trades) * 100 if len(blocked_trades) > 0 else 0

    return FilterResult(
        option_name=filter_name,
        total_trades=len(trades),
        passed_trades=len(passed_trades),
        win_rate=win_rate,
        avg_pnl=avg_pnl,
        total_pnl=total_pnl,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        trades_per_month=trades_per_month,
        false_positive_rate=false_positive_rate,
        missed_opportunity_rate=missed_opportunity_rate
    )

def evaluate_by_regime(trades: List[Trade], filter_name: str, filter_func) -> Dict[str, float]:
    """Evaluate filter performance by market regime"""
    results = {}

    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t.market_regime == regime]
        if len(regime_trades) == 0:
            results[regime] = 0
            continue

        passed = [t for t in regime_trades if filter_func(
            t.sector_1d, t.sector_5d, t.sector_20d, t.spy_20d, t.market_regime
        )]

        if len(passed) == 0:
            results[regime] = 0
        else:
            wins = [t for t in passed if t.pnl_pct > 0]
            results[regime] = len(wins) / len(passed) * 100

    return results

def get_trade_examples(trades: List[Trade], filter_func) -> Dict[str, List[Trade]]:
    """Get example trades for each category"""
    examples = {
        'true_positive': [],  # passed and won
        'false_positive': [],  # passed but lost
        'missed_opportunity': [],  # blocked but would have won
        'true_negative': []  # blocked and lost
    }

    for trade in trades:
        passed = filter_func(
            trade.sector_1d, trade.sector_5d, trade.sector_20d,
            trade.spy_20d, trade.market_regime
        )
        won = trade.pnl_pct > 0

        if passed and won:
            examples['true_positive'].append(trade)
        elif passed and not won:
            examples['false_positive'].append(trade)
        elif not passed and won:
            examples['missed_opportunity'].append(trade)
        else:
            examples['true_negative'].append(trade)

    # Limit to 5 each
    for key in examples:
        examples[key] = examples[key][:5]

    return examples

# ============================================================================
# MAIN ANALYSIS
# ============================================================================

def main():
    print("=" * 80)
    print("🧪 SMART SECTOR FILTER BACKTEST")
    print("=" * 80)

    # Download data
    etf_data, stock_data, _ = download_data(period='1y')

    # Run backtest
    trades = run_backtest(etf_data, stock_data)

    if len(trades) == 0:
        print("❌ No trades generated!")
        return

    # Evaluate each filter
    print("\n" + "=" * 80)
    print("📊 TABLE 1: OVERALL COMPARISON")
    print("=" * 80)

    results = []
    for name, func in FILTER_OPTIONS.items():
        result = evaluate_filter(trades, name, func)
        results.append(result)

    # Sort by win rate
    results.sort(key=lambda x: x.win_rate, reverse=True)

    # Print table
    print(f"\n{'Option':<20} {'Win%':>8} {'AvgP&L':>8} {'TotalP&L':>10} {'MaxDD':>8} {'Sharpe':>8} {'Trades':>8} {'FalsePos%':>10} {'Missed%':>10}")
    print("-" * 110)

    for i, r in enumerate(results):
        rank = f"#{i+1}"
        print(f"{r.option_name:<20} {r.win_rate:>7.1f}% {r.avg_pnl:>+7.2f}% {r.total_pnl:>+9.1f}% {r.max_drawdown:>7.1f}% {r.sharpe:>8.2f} {r.passed_trades:>8} {r.false_positive_rate:>9.1f}% {r.missed_opportunity_rate:>9.1f}%")

    # By regime analysis
    print("\n" + "=" * 80)
    print("📊 TABLE 2: BY MARKET REGIME")
    print("=" * 80)

    print(f"\n{'Option':<20} {'BULL Win%':>12} {'BEAR Win%':>12} {'NEUTRAL Win%':>14} {'Best For':>15}")
    print("-" * 80)

    for name, func in FILTER_OPTIONS.items():
        regime_results = evaluate_by_regime(trades, name, func)
        best = max(regime_results.items(), key=lambda x: x[1])[0] if any(regime_results.values()) else 'N/A'
        print(f"{name:<20} {regime_results.get('BULL', 0):>11.1f}% {regime_results.get('BEAR', 0):>11.1f}% {regime_results.get('NEUTRAL', 0):>13.1f}% {best:>15}")

    # Trade distribution
    print("\n" + "=" * 80)
    print("📊 TRADE DISTRIBUTION")
    print("=" * 80)

    regime_counts = defaultdict(int)
    for t in trades:
        regime_counts[t.market_regime] += 1

    print(f"\nTotal trades: {len(trades)}")
    for regime, count in regime_counts.items():
        pct = count / len(trades) * 100
        print(f"  {regime}: {count} trades ({pct:.1f}%)")

    # Sector breakdown
    sector_counts = defaultdict(int)
    sector_wins = defaultdict(int)
    for t in trades:
        sector_counts[t.sector] += 1
        if t.pnl_pct > 0:
            sector_wins[t.sector] += 1

    print(f"\nBy Sector:")
    for sector in sorted(sector_counts.keys()):
        count = sector_counts[sector]
        wins = sector_wins[sector]
        win_rate = wins / count * 100 if count > 0 else 0
        print(f"  {sector:<25}: {count:>3} trades, {win_rate:>5.1f}% win rate")

    # Trade examples for best option
    print("\n" + "=" * 80)
    print("📊 TABLE 3: TRADE EXAMPLES (Best Option)")
    print("=" * 80)

    best_option = results[0].option_name
    best_func = FILTER_OPTIONS[best_option]
    examples = get_trade_examples(trades, best_func)

    for category, category_trades in examples.items():
        print(f"\n{category.upper().replace('_', ' ')}:")
        if not category_trades:
            print("  (no examples)")
            continue
        for t in category_trades[:3]:
            print(f"  {t.symbol:<6} | Entry: {t.entry_date} @ ${t.entry_price:.2f} | P&L: {t.pnl_pct:+.2f}% | Sector 1d/5d/20d: {t.sector_1d:+.1f}%/{t.sector_5d:+.1f}%/{t.sector_20d:+.1f}%")

    # Key findings
    print("\n" + "=" * 80)
    print("🎯 KEY FINDINGS & RECOMMENDATIONS")
    print("=" * 80)

    # Best options
    best_win_rate = results[0]
    best_sharpe = max(results, key=lambda x: x.sharpe)
    lowest_false_pos = min(results, key=lambda x: x.false_positive_rate)

    print(f"""
1. BEST WIN RATE: {best_win_rate.option_name}
   - Win Rate: {best_win_rate.win_rate:.1f}%
   - Avg P&L: {best_win_rate.avg_pnl:+.2f}%
   - Trades: {best_win_rate.passed_trades}

2. BEST RISK-ADJUSTED (Sharpe): {best_sharpe.option_name}
   - Sharpe: {best_sharpe.sharpe:.2f}
   - Win Rate: {best_sharpe.win_rate:.1f}%
   - Max Drawdown: {best_sharpe.max_drawdown:.1f}%

3. LOWEST FALSE POSITIVES: {lowest_false_pos.option_name}
   - False Positive Rate: {lowest_false_pos.false_positive_rate:.1f}%
   - Win Rate: {lowest_false_pos.win_rate:.1f}%
""")

    # Answer the 5 questions
    print("\n" + "=" * 80)
    print("❓ ANSWERS TO KEY QUESTIONS")
    print("=" * 80)

    current_result = next(r for r in results if r.option_name == 'CURRENT_20d')
    no_filter_result = next(r for r in results if r.option_name == 'H_no_filter')

    print(f"""
Q1: 20d return เหมาะกับ dip-bounce ไหม?
A1: {'ไม่เหมาะ' if current_result.win_rate < no_filter_result.win_rate else 'เหมาะพอใช้'}
    - CURRENT_20d win rate: {current_result.win_rate:.1f}%
    - No Filter win rate: {no_filter_result.win_rate:.1f}%
    - Difference: {current_result.win_rate - no_filter_result.win_rate:+.1f}%

Q2: Option ไหนเพิ่ม win rate มากสุด?
A2: {best_win_rate.option_name} ({best_win_rate.win_rate:.1f}%)
    - เทียบกับ Current: {best_win_rate.win_rate - current_result.win_rate:+.1f}%
    - เทียบกับ No Filter: {best_win_rate.win_rate - no_filter_result.win_rate:+.1f}%

Q3: Option ไหน reduce false signals ดีสุด?
A3: {lowest_false_pos.option_name}
    - False Positive Rate: {lowest_false_pos.false_positive_rate:.1f}%
    - แต่อาจ miss โอกาส: {lowest_false_pos.missed_opportunity_rate:.1f}%

Q4: ควรใช้ fixed logic หรือ adaptive by regime?
A4: ดู F_adaptive performance:
    - Win Rate: {next(r for r in results if r.option_name == 'F_adaptive').win_rate:.1f}%
    - ถ้าสูงกว่า fixed options มาก → ใช้ adaptive
    - ถ้าใกล้เคียง → ใช้ fixed (simpler)

Q5: Sector filter ควรเป็น hard filter หรือ scoring bonus?
A5: ดูจาก missed opportunity rate:
    - ถ้า missed opportunity สูง → ควรเป็น scoring bonus
    - ถ้า false positive สูงกว่า missed → ควรเป็น hard filter
    - Current: FP={current_result.false_positive_rate:.1f}%, MO={current_result.missed_opportunity_rate:.1f}%
    - Recommendation: {'Scoring Bonus' if current_result.missed_opportunity_rate > current_result.false_positive_rate else 'Hard Filter'}
""")

    # Final recommendation
    print("\n" + "=" * 80)
    print("✅ FINAL RECOMMENDATION")
    print("=" * 80)

    print(f"""
BEST OVERALL: {best_win_rate.option_name}

Recommended Implementation:
""")

    if best_win_rate.option_name == 'B_pullback':
        print("""
def smart_sector_filter(sector_1d, sector_5d, sector_20d):
    # Option B: Pullback in Uptrend
    return sector_20d > 0 and sector_5d < 0

Rationale: ซื้อตอน sector กำลัง pullback ใน uptrend
- 20d up = sector มี momentum ดี
- 5d down = กำลัง pullback (dip)
- Perfect for dip-bounce!
""")
    elif best_win_rate.option_name == 'A_5d_only':
        print("""
def smart_sector_filter(sector_1d, sector_5d, sector_20d):
    # Option A: 5d Only
    return sector_5d > 0

Rationale: ดู momentum สั้นๆ 5 วัน
- เหมาะกับ hold 1-3 วัน
- ไม่สนใจ trend ยาว
""")
    elif best_win_rate.option_name == 'F_adaptive':
        print("""
def smart_sector_filter(sector_1d, sector_5d, sector_20d, regime):
    # Option F: Adaptive by Regime
    if regime == 'BULL':
        return sector_20d > -5
    elif regime == 'BEAR':
        return sector_20d > 0 and sector_5d < 0 and sector_1d > 0
    else:  # NEUTRAL
        return sector_20d > 0 or (sector_5d > 0 and sector_1d > 0)

Rationale: ปรับ logic ตามสภาวะตลาด
- BULL: ผ่อนปรน
- BEAR: เข้มงวด + ต้องเห็น bounce
""")
    else:
        print(f"""
Best option: {best_win_rate.option_name}
Win Rate: {best_win_rate.win_rate:.1f}%
Avg P&L: {best_win_rate.avg_pnl:+.2f}%
""")

    print("\n" + "=" * 80)
    print("🏁 BACKTEST COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    main()
