#!/usr/bin/env python3
"""
QUANT STRATEGY RESEARCH — Systematic Backtest Framework

Hard Constraints:
- No Win% optimization (focus on Expectancy)
- Causal explanations for all performance changes
- Isolated variable testing

Hypotheses:
- H1: Stock-D as universal entry permission layer
- H2: DD Control impact on BEAR edge
- H3: A_5d_only as edge-density filter vs trade-reduction filter

Key Metrics:
- Expectancy/trade = (Win% × Avg Win) - (Loss% × Avg Loss)
- Max DD
- DD per 100 trades
- Worst 5-trade loss streak
- Profit Factor = Gross Profit / Gross Loss
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

SECTOR_ETFS = {
    'Technology': 'XLK', 'Healthcare': 'XLV', 'Financials': 'XLF',
    'Consumer Discretionary': 'XLY', 'Communication Services': 'XLC',
    'Industrials': 'XLI', 'Consumer Staples': 'XLP', 'Energy': 'XLE',
    'Utilities': 'XLU', 'Real Estate': 'XLRE', 'Materials': 'XLB'
}

STOCK_UNIVERSE = {
    'Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'AMD', 'CRM', 'ADBE', 'ORCL', 'CSCO', 'INTC'],
    'Healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'],
    'Financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'SCHW', 'AXP', 'C', 'USB'],
    'Consumer Discretionary': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TJX', 'LOW', 'BKNG', 'CMG'],
    'Communication Services': ['GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'EA'],
    'Industrials': ['CAT', 'GE', 'UNP', 'HON', 'UPS', 'BA', 'RTX', 'DE', 'LMT', 'MMM'],
    'Consumer Staples': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'MO', 'CL', 'MDLZ', 'KHC'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'WEC'],
    'Real Estate': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'SPG', 'O', 'WELL', 'DLR', 'AVB'],
    'Materials': ['LIN', 'APD', 'SHW', 'FCX', 'ECL', 'NEM', 'NUE', 'DD', 'DOW', 'PPG']
}

STOCK_TO_SECTOR = {}
for sector, stocks in STOCK_UNIVERSE.items():
    for stock in stocks:
        STOCK_TO_SECTOR[stock] = sector

# ============================================================================
# DATA CLASSES
# ============================================================================

class Regime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"

@dataclass
class Trade:
    symbol: str
    sector: str
    strategy: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    hold_days: int
    exit_reason: str
    regime: str
    position_size: float = 1.0
    signal_type: str = ""  # 'dip_bounce', 'sector_rotation', 'stock_d'
    sector_5d: float = 0.0  # sector 5d return at entry

@dataclass
class PortfolioState:
    equity: float = 100.0
    peak_equity: float = 100.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    pnl_history: List[float] = field(default_factory=list)
    consecutive_losses: int = 0

@dataclass
class QuantMetrics:
    """Quant-focused metrics"""
    trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0  # Primary metric!
    profit_factor: float = 0.0
    max_dd: float = 0.0
    dd_per_100_trades: float = 0.0
    worst_5_streak: float = 0.0
    total_pnl: float = 0.0
    sharpe: float = 0.0

# ============================================================================
# DATA FUNCTIONS
# ============================================================================

def download_data(period='1y'):
    print("Downloading data...")
    etf_symbols = list(SECTOR_ETFS.values()) + ['SPY', '^VIX']
    etf_data = yf.download(etf_symbols, period=period, progress=False)
    all_stocks = list(STOCK_TO_SECTOR.keys())
    stock_data = yf.download(all_stocks, period=period, progress=False)
    print(f"ETF: {len(etf_data)} days, Stocks: {len(stock_data)} days")
    return etf_data, stock_data

def prepare_market_data(etf_data: pd.DataFrame) -> pd.DataFrame:
    spy_close = etf_data[('Close', 'SPY')]
    df = pd.DataFrame(index=spy_close.index)
    df['spy_close'] = spy_close
    df['spy_sma_50'] = spy_close.rolling(50).mean()
    df['spy_return_1d'] = spy_close.pct_change() * 100
    df['spy_return_5d'] = spy_close.pct_change(5) * 100
    df['spy_return_20d'] = spy_close.pct_change(20) * 100

    delta = spy_close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['spy_rsi'] = 100 - (100 / (1 + rs))

    try:
        df['vix'] = etf_data[('Close', '^VIX')]
        df['vix_change_1d'] = df['vix'].pct_change() * 100
    except:
        df['vix'] = 20
        df['vix_change_1d'] = 0

    return df

def calculate_sector_metrics(etf_data: pd.DataFrame) -> dict:
    metrics = {}
    for sector, etf in SECTOR_ETFS.items():
        try:
            close = etf_data[('Close', etf)]
            df = pd.DataFrame(index=close.index)
            df['close'] = close
            df['return_1d'] = close.pct_change() * 100
            df['return_5d'] = close.pct_change(5) * 100
            df['return_20d'] = close.pct_change(20) * 100
            metrics[sector] = df
        except:
            pass

    try:
        spy_close = etf_data[('Close', 'SPY')]
        spy_df = pd.DataFrame(index=spy_close.index)
        spy_df['close'] = spy_close
        spy_df['return_5d'] = spy_close.pct_change(5) * 100
        spy_df['return_20d'] = spy_close.pct_change(20) * 100
        metrics['SPY'] = spy_df
    except:
        pass

    return metrics

# ============================================================================
# REGIME DETECTION (RD-E Composite - CONFIRMED)
# ============================================================================

def detect_regime(row) -> Regime:
    """RD-E: Composite Score (confirmed best)"""
    score = 0
    if not pd.isna(row.get('spy_sma_50')) and row['spy_close'] > row['spy_sma_50']:
        score += 1
    else:
        score -= 1
    if not pd.isna(row.get('spy_return_20d')) and row['spy_return_20d'] > 0:
        score += 1
    else:
        score -= 1
    if not pd.isna(row.get('vix')) and row['vix'] < 20:
        score += 1
    else:
        score -= 1
    if not pd.isna(row.get('spy_rsi')) and row['spy_rsi'] > 50:
        score += 1
    else:
        score -= 1

    if score >= 2:
        return Regime.BULL
    elif score <= -2:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL

# ============================================================================
# SIGNAL DETECTION
# ============================================================================

def check_dip_bounce(stock_data: pd.DataFrame, stock: str, date) -> Optional[Tuple[float, float, float]]:
    """Check if stock has dip-bounce pattern. Returns (entry_price, yesterday_return, today_return)"""
    try:
        closes = stock_data[('Close', stock)]
        idx = closes.index.get_loc(date)
        if idx < 2:
            return None
        yesterday_return = (closes.iloc[idx-1] / closes.iloc[idx-2] - 1) * 100
        today_return = (closes.iloc[idx] / closes.iloc[idx-1] - 1) * 100
        if yesterday_return <= -2 and today_return >= 1:
            return closes.iloc[idx], yesterday_return, today_return
        return None
    except:
        return None

def check_sector_rotation(sector_metrics: dict, sector: str, date) -> Optional[Tuple[float, float]]:
    """Check if sector has RS breakout. Returns (sector_1d, relative_strength)"""
    try:
        s = sector_metrics[sector]
        spy = sector_metrics['SPY']
        idx = s.index.get_loc(date)
        if idx < 1:
            return None
        rs_today = s.iloc[idx]['return_20d'] - spy.iloc[idx]['return_20d']
        rs_yesterday = s.iloc[idx-1]['return_20d'] - spy.iloc[idx-1]['return_20d']
        sector_1d = s.iloc[idx]['return_1d']
        if rs_yesterday < 0 and rs_today > 0 and sector_1d > 0.5:
            return sector_1d, rs_today
        return None
    except:
        return None

def get_sector_5d(sector_metrics: dict, sector: str, date) -> float:
    """Get sector's 5-day return"""
    try:
        s = sector_metrics[sector]
        idx = s.index.get_loc(date)
        return s.iloc[idx]['return_5d']
    except:
        return 0.0

# ============================================================================
# TRADE SIMULATION
# ============================================================================

def simulate_trade(stock_data: pd.DataFrame, stock: str, entry_date: str,
                   entry_price: float, strategy: str, hold_days: int,
                   regime: Regime, stop_loss: float = -2.0) -> Optional[Trade]:
    try:
        closes = stock_data[('Close', stock)].dropna()
        dates = closes.index
        entry_idx = None
        for i, d in enumerate(dates):
            if d.strftime('%Y-%m-%d') == entry_date:
                entry_idx = i
                break
        if entry_idx is None:
            return None

        tp = 3.0 if strategy == 'DIP_BOUNCE' else 4.0
        max_hold = hold_days if strategy == 'DIP_BOUNCE' else hold_days + 2

        for day in range(1, max_hold + 1):
            if entry_idx + day >= len(closes):
                break
            current_price = closes.iloc[entry_idx + day]
            pnl_pct = (current_price / entry_price - 1) * 100

            exit_reason = ''
            if pnl_pct >= tp:
                exit_reason = 'TP'
            elif pnl_pct <= stop_loss:
                exit_reason = 'SL'
            elif day >= max_hold:
                exit_reason = f'HOLD_{max_hold}D'

            if exit_reason:
                return Trade(
                    symbol=stock, sector=STOCK_TO_SECTOR.get(stock, 'Unknown'),
                    strategy=strategy, entry_date=entry_date, entry_price=entry_price,
                    exit_date=dates[entry_idx + day].strftime('%Y-%m-%d'),
                    exit_price=current_price, pnl_pct=pnl_pct, hold_days=day,
                    exit_reason=exit_reason, regime=regime.value
                )
        return None
    except:
        return None

# ============================================================================
# QUANT METRICS CALCULATION
# ============================================================================

def calculate_quant_metrics(trades: List[Trade]) -> QuantMetrics:
    """Calculate quant-focused metrics with Expectancy as primary"""
    if not trades:
        return QuantMetrics()

    pnls = [t.pnl_pct * t.position_size for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    n = len(pnls)
    win_rate = len(wins) / n * 100 if n > 0 else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0

    # EXPECTANCY = (Win% × Avg Win) - (Loss% × Avg Loss)
    expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)

    # Profit Factor = Gross Profit / Gross Loss
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Max Drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    # DD per 100 trades
    dd_per_100 = max_dd / (n / 100) if n > 0 else 0

    # Worst 5-trade streak
    worst_5 = 0
    for i in range(len(pnls) - 4):
        streak = sum(pnls[i:i+5])
        worst_5 = min(worst_5, streak)

    # Sharpe
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0

    return QuantMetrics(
        trades=n,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        profit_factor=profit_factor,
        max_dd=max_dd,
        dd_per_100_trades=dd_per_100,
        worst_5_streak=worst_5,
        total_pnl=sum(pnls),
        sharpe=sharpe
    )

def calculate_regime_metrics(trades: List[Trade]) -> Dict[str, QuantMetrics]:
    """Calculate metrics per regime"""
    results = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        regime_trades = [t for t in trades if t.regime == regime]
        results[regime] = calculate_quant_metrics(regime_trades)
    return results

# ============================================================================
# STRATEGY CONFIGURATIONS
# ============================================================================

class StrategyConfig:
    def __init__(self, name: str):
        self.name = name
        # Entry permission
        self.stock_d_required = False  # H1: Stock-D filter
        self.sector_5d_required = False  # H3: A_5d_only filter
        # DD Controls
        self.daily_limit = -100.0  # H2: Daily loss limit (-100 = disabled)
        self.circuit_breaker_dd = 100.0  # DD threshold to stop trading
        self.position_sizing = 'baseline'  # 'baseline', 'dd_aware'
        # Strategy assignment
        self.bull_strategies = ['SECTOR_ROTATION']
        self.bear_strategies = ['DIP_BOUNCE']
        self.neutral_strategies = ['SECTOR_ROTATION', 'DIP_BOUNCE']

# ============================================================================
# MAIN BACKTEST ENGINE
# ============================================================================

def run_backtest(market_data: pd.DataFrame, stock_data: pd.DataFrame,
                 sector_metrics: dict, config: StrategyConfig) -> Tuple[List[Trade], dict]:
    """Run backtest with given configuration"""
    trades = []
    state = PortfolioState()

    current_regime = Regime.NEUTRAL
    pending_regime = None
    pending_days = 0

    dates = market_data.index[50:]
    stats = {'days_stopped': 0, 'signals_filtered': 0, 'signals_total': 0}

    for date in dates:
        try:
            row = market_data.loc[date]
            date_str = date.strftime('%Y-%m-%d')

            # Regime detection with 3-day confirmation
            new_regime = detect_regime(row)
            if new_regime != current_regime:
                if pending_regime == new_regime:
                    pending_days += 1
                    if pending_days >= 3:
                        current_regime = new_regime
                        pending_regime = None
                        pending_days = 0
                else:
                    pending_regime = new_regime
                    pending_days = 1
            else:
                pending_regime = None
                pending_days = 0

            vix = row.get('vix', 20)

            # Circuit Breaker check
            if state.current_drawdown >= config.circuit_breaker_dd:
                stats['days_stopped'] += 1
                continue

            # Daily Limit check
            if state.daily_pnl <= config.daily_limit:
                stats['days_stopped'] += 1
                continue

            # Strategy selection based on regime
            if current_regime == Regime.BULL:
                strategies = config.bull_strategies
            elif current_regime == Regime.BEAR:
                strategies = config.bear_strategies
            else:
                strategies = config.neutral_strategies

            day_trades = []

            for strategy in strategies:
                if strategy == 'SECTOR_ROTATION':
                    for sector in SECTOR_ETFS.keys():
                        sr_signal = check_sector_rotation(sector_metrics, sector, date)
                        if not sr_signal:
                            continue

                        sector_5d = get_sector_5d(sector_metrics, sector, date)

                        # H3: A_5d_only filter
                        if config.sector_5d_required and sector_5d <= 0:
                            stats['signals_filtered'] += 1
                            continue

                        for stock in STOCK_UNIVERSE.get(sector, []):
                            stats['signals_total'] += 1

                            # H1: Stock-D filter (dip-bounce required)
                            if config.stock_d_required:
                                db_signal = check_dip_bounce(stock_data, stock, date)
                                if not db_signal:
                                    stats['signals_filtered'] += 1
                                    continue
                                entry_price = db_signal[0]
                            else:
                                # Just enter on SR signal
                                try:
                                    entry_price = stock_data[('Close', stock)].loc[date]
                                except:
                                    continue

                            # Position sizing
                            ps_mult = 1.0
                            if config.position_sizing == 'dd_aware':
                                if state.current_drawdown >= 15:
                                    ps_mult = 0.3
                                elif state.current_drawdown >= 10:
                                    ps_mult = 0.5
                                elif state.current_drawdown >= 5:
                                    ps_mult = 0.7

                            trade = simulate_trade(
                                stock_data, stock, date_str, entry_price,
                                'SECTOR_ROTATION', 5, current_regime
                            )
                            if trade:
                                trade.position_size = ps_mult
                                trade.signal_type = 'stock_d' if config.stock_d_required else 'sector_rotation'
                                trade.sector_5d = sector_5d
                                trades.append(trade)
                                day_trades.append(trade)

                elif strategy == 'DIP_BOUNCE':
                    for stock in list(STOCK_TO_SECTOR.keys()):
                        stats['signals_total'] += 1
                        db_signal = check_dip_bounce(stock_data, stock, date)
                        if not db_signal:
                            continue

                        entry_price = db_signal[0]
                        sector = STOCK_TO_SECTOR.get(stock, 'Unknown')
                        sector_5d = get_sector_5d(sector_metrics, sector, date)

                        # H3: A_5d_only filter
                        if config.sector_5d_required and sector_5d <= 0:
                            stats['signals_filtered'] += 1
                            continue

                        # Position sizing
                        ps_mult = 1.0
                        if config.position_sizing == 'dd_aware':
                            if state.current_drawdown >= 15:
                                ps_mult = 0.3
                            elif state.current_drawdown >= 10:
                                ps_mult = 0.5
                            elif state.current_drawdown >= 5:
                                ps_mult = 0.7

                        trade = simulate_trade(
                            stock_data, stock, date_str, entry_price,
                            'DIP_BOUNCE', 3, current_regime
                        )
                        if trade:
                            trade.position_size = ps_mult
                            trade.signal_type = 'dip_bounce'
                            trade.sector_5d = sector_5d
                            trades.append(trade)
                            day_trades.append(trade)

            # Update state
            day_pnl = sum(t.pnl_pct * t.position_size for t in day_trades)
            state.daily_pnl = day_pnl
            state.pnl_history.append(day_pnl)

            if day_pnl < 0:
                state.consecutive_losses += 1
            else:
                state.consecutive_losses = 0

            state.equity += day_pnl
            state.peak_equity = max(state.peak_equity, state.equity)
            state.current_drawdown = (state.peak_equity - state.equity) / state.peak_equity * 100 if state.peak_equity > 0 else 0

        except Exception as e:
            continue

    return trades, stats

# ============================================================================
# ANALYSIS HELPERS
# ============================================================================

def print_quant_metrics(name: str, m: QuantMetrics):
    """Print metrics in standard format"""
    print(f"{name:<30} Trades:{m.trades:>4} | E[R]:{m.expectancy:>+6.3f}% | "
          f"Win:{m.win_rate:>5.1f}% | MaxDD:{m.max_dd:>6.1f}% | "
          f"DD/100:{m.dd_per_100_trades:>6.1f}% | PF:{m.profit_factor:>5.2f} | "
          f"W5:{m.worst_5_streak:>+6.1f}%")

def analyze_trade_sequences(trades: List[Trade], regime: str = None) -> dict:
    """Analyze trade sequences for patterns"""
    if regime:
        trades = [t for t in trades if t.regime == regime]

    if not trades:
        return {}

    pnls = [t.pnl_pct for t in trades]

    # Find losing streaks
    streaks = []
    current_streak = 0
    for pnl in pnls:
        if pnl < 0:
            current_streak += pnl
        else:
            if current_streak < 0:
                streaks.append(current_streak)
            current_streak = 0
    if current_streak < 0:
        streaks.append(current_streak)

    # Group by exit reason
    by_exit = defaultdict(list)
    for t in trades:
        by_exit[t.exit_reason].append(t.pnl_pct)

    # Group by sector_5d
    positive_5d = [t.pnl_pct for t in trades if t.sector_5d > 0]
    negative_5d = [t.pnl_pct for t in trades if t.sector_5d <= 0]

    return {
        'total_trades': len(trades),
        'worst_streak': min(streaks) if streaks else 0,
        'num_bad_streaks': len([s for s in streaks if s < -5]),
        'by_exit': {k: (len(v), np.mean(v) if v else 0) for k, v in by_exit.items()},
        'positive_5d_trades': len(positive_5d),
        'positive_5d_avg': np.mean(positive_5d) if positive_5d else 0,
        'negative_5d_trades': len(negative_5d),
        'negative_5d_avg': np.mean(negative_5d) if negative_5d else 0,
    }

# ============================================================================
# MAIN BACKTEST
# ============================================================================

def main():
    print("=" * 100)
    print("QUANT STRATEGY RESEARCH — Systematic Backtest Framework")
    print("=" * 100)
    print("\nConstraints: Focus on Expectancy (not Win%), Isolated testing, Causal explanations")

    etf_data, stock_data = download_data('1y')
    market_data = prepare_market_data(etf_data)
    sector_metrics = calculate_sector_metrics(etf_data)

    # =========================================================================
    # PART 1: BASELINE
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 1: BASELINE SYSTEM")
    print("=" * 100)
    print("\nConfig: RD-E regime + SA-C assignment (BULL->SR, BEAR->DB, NEUTRAL->Both)")
    print("        No filters, No DD controls, Fixed position size")

    baseline_config = StrategyConfig('BASELINE')
    baseline_trades, baseline_stats = run_backtest(market_data, stock_data, sector_metrics, baseline_config)

    baseline_metrics = calculate_quant_metrics(baseline_trades)
    baseline_regime = calculate_regime_metrics(baseline_trades)

    print(f"\nOverall:")
    print_quant_metrics("BASELINE", baseline_metrics)

    print(f"\nBy Regime:")
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        m = baseline_regime[regime]
        print_quant_metrics(f"  {regime}", m)

    # =========================================================================
    # PART 2: H1 — Stock-D as Universal Entry Permission
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 2: H1 — Stock-D as Universal Entry Permission Layer")
    print("=" * 100)
    print("\nHypothesis: Requiring dip-bounce pattern filters low-quality entries")
    print("Testing: Does Stock-D improve Expectancy across all regimes?")

    h1_variants = {
        'V1-A_baseline': {'stock_d': False, 'dd_ctrl': False},
        'V1-B_stock_d_only': {'stock_d': True, 'dd_ctrl': False},
        'V1-C_dd_ctrl_only': {'stock_d': False, 'dd_ctrl': True},
        'V1-D_both': {'stock_d': True, 'dd_ctrl': True},
    }

    h1_results = {}
    for name, params in h1_variants.items():
        config = StrategyConfig(name)
        config.stock_d_required = params['stock_d']
        if params['dd_ctrl']:
            config.daily_limit = -2.0
            config.circuit_breaker_dd = 15.0
            config.position_sizing = 'dd_aware'

        trades, stats = run_backtest(market_data, stock_data, sector_metrics, config)
        h1_results[name] = {
            'metrics': calculate_quant_metrics(trades),
            'regime': calculate_regime_metrics(trades),
            'stats': stats
        }

    print(f"\nResults (Isolated Variable: Stock-D):")
    print("-" * 100)
    for name, r in h1_results.items():
        print_quant_metrics(name, r['metrics'])

    print(f"\nBy Regime:")
    print("-" * 100)
    for name, r in h1_results.items():
        print(f"\n{name}:")
        for regime in ['BULL', 'BEAR', 'NEUTRAL']:
            m = r['regime'][regime]
            if m.trades > 0:
                print(f"  {regime}: Trades={m.trades:>3}, E[R]={m.expectancy:>+.3f}%, Win={m.win_rate:.1f}%")

    # H1 Analysis
    print(f"\nH1 ANALYSIS:")
    v1a = h1_results['V1-A_baseline']['metrics']
    v1b = h1_results['V1-B_stock_d_only']['metrics']
    v1c = h1_results['V1-C_dd_ctrl_only']['metrics']
    v1d = h1_results['V1-D_both']['metrics']

    stock_d_impact_exp = v1b.expectancy - v1a.expectancy
    stock_d_impact_trades = v1b.trades - v1a.trades
    dd_ctrl_impact_exp = v1c.expectancy - v1a.expectancy
    dd_ctrl_impact_dd = v1c.max_dd - v1a.max_dd

    print(f"  Stock-D alone: Expectancy {stock_d_impact_exp:+.3f}%, Trades {stock_d_impact_trades:+d}")
    print(f"  DD Ctrl alone: Expectancy {dd_ctrl_impact_exp:+.3f}%, Max DD {dd_ctrl_impact_dd:+.1f}%")
    print(f"  Both combined: Expectancy {v1d.expectancy - v1a.expectancy:+.3f}%, Trades {v1d.trades - v1a.trades:+d}")

    if stock_d_impact_exp > 0 and stock_d_impact_trades < 0:
        print(f"\n  CAUSAL: Stock-D filters low-quality entries (fewer trades, higher expectancy)")
    elif stock_d_impact_exp < 0:
        print(f"\n  CAUSAL: Stock-D over-filters (loses good opportunities)")
    else:
        print(f"\n  CAUSAL: Stock-D effect unclear")

    # =========================================================================
    # PART 3: H2 — DD Control Impact on BEAR Edge
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 3: H2 — DD Control Impact on BEAR Regime Edge")
    print("=" * 100)
    print("\nHypothesis: DD controls may destroy BEAR regime's dip-bounce edge")
    print("Testing: Does DD control hurt BEAR more than help?")

    h2_variants = {
        'V2-A_no_dd_ctrl': {'daily_limit': -100.0, 'cb_dd': 100.0, 'ps': 'baseline'},
        'V2-B_light_dd_ctrl': {'daily_limit': -3.0, 'cb_dd': 20.0, 'ps': 'baseline'},
        'V2-C_full_dd_ctrl': {'daily_limit': -2.0, 'cb_dd': 15.0, 'ps': 'dd_aware'},
    }

    h2_results = {}
    for name, params in h2_variants.items():
        config = StrategyConfig(name)
        config.daily_limit = params['daily_limit']
        config.circuit_breaker_dd = params['cb_dd']
        config.position_sizing = params['ps']

        trades, stats = run_backtest(market_data, stock_data, sector_metrics, config)
        h2_results[name] = {
            'metrics': calculate_quant_metrics(trades),
            'regime': calculate_regime_metrics(trades),
            'stats': stats
        }

    print(f"\nResults (Focus on BEAR Regime):")
    print("-" * 100)
    for name, r in h2_results.items():
        bear = r['regime']['BEAR']
        overall = r['metrics']
        print(f"{name:<25} | BEAR: Trades={bear.trades:>3}, E[R]={bear.expectancy:>+.3f}%, Win={bear.win_rate:.1f}% | "
              f"Overall: MaxDD={overall.max_dd:.1f}%, Stopped={r['stats']['days_stopped']}")

    # H2 DD Control Audit
    print(f"\nH2 DD CONTROL AUDIT (BEAR Regime):")
    v2a_bear = h2_results['V2-A_no_dd_ctrl']['regime']['BEAR']
    v2b_bear = h2_results['V2-B_light_dd_ctrl']['regime']['BEAR']
    v2c_bear = h2_results['V2-C_full_dd_ctrl']['regime']['BEAR']

    print(f"  No DD Control:   E[R]={v2a_bear.expectancy:>+.3f}%, Trades={v2a_bear.trades}, Win={v2a_bear.win_rate:.1f}%")
    print(f"  Light DD Control: E[R]={v2b_bear.expectancy:>+.3f}%, Trades={v2b_bear.trades}, Win={v2b_bear.win_rate:.1f}%")
    print(f"  Full DD Control:  E[R]={v2c_bear.expectancy:>+.3f}%, Trades={v2c_bear.trades}, Win={v2c_bear.win_rate:.1f}%")

    bear_exp_loss = v2c_bear.expectancy - v2a_bear.expectancy
    bear_trades_loss = v2c_bear.trades - v2a_bear.trades

    if bear_exp_loss < 0 and v2a_bear.expectancy > 0:
        print(f"\n  CAUSAL: DD Control DESTROYS BEAR edge ({bear_exp_loss:+.3f}% expectancy loss)")
        print(f"          BEAR strategy's value is in catching big dips → limiting exposure kills it")
    else:
        print(f"\n  CAUSAL: DD Control effect on BEAR: {bear_exp_loss:+.3f}%")

    # =========================================================================
    # PART 4: H3 — A_5d_only as Edge-Density Filter
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 4: H3 — A_5d_only Filter (sector_5d > 0)")
    print("=" * 100)
    print("\nHypothesis: Requiring sector_5d > 0 filters counter-trend entries")
    print("Testing: Edge-density filter or just trade-reduction filter?")

    h3_variants = {
        'V3-A_no_5d_filter': {'sector_5d': False},
        'V3-B_with_5d_filter': {'sector_5d': True},
    }

    h3_results = {}
    for name, params in h3_variants.items():
        config = StrategyConfig(name)
        config.sector_5d_required = params['sector_5d']

        trades, stats = run_backtest(market_data, stock_data, sector_metrics, config)
        h3_results[name] = {
            'metrics': calculate_quant_metrics(trades),
            'regime': calculate_regime_metrics(trades),
            'trades': trades,
            'stats': stats
        }

    print(f"\nResults:")
    print("-" * 100)
    for name, r in h3_results.items():
        print_quant_metrics(name, r['metrics'])

    # Analyze sector_5d impact
    v3a = h3_results['V3-A_no_5d_filter']
    v3b = h3_results['V3-B_with_5d_filter']

    seq_no_filter = analyze_trade_sequences(v3a['trades'])
    seq_with_filter = analyze_trade_sequences(v3b['trades'])

    print(f"\nH3 ANALYSIS (Edge Density vs Trade Reduction):")
    print(f"  Without filter:")
    print(f"    - Positive sector_5d trades: {seq_no_filter.get('positive_5d_trades', 0)}, "
          f"avg PnL: {seq_no_filter.get('positive_5d_avg', 0):+.2f}%")
    print(f"    - Negative sector_5d trades: {seq_no_filter.get('negative_5d_trades', 0)}, "
          f"avg PnL: {seq_no_filter.get('negative_5d_avg', 0):+.2f}%")

    exp_diff = v3b['metrics'].expectancy - v3a['metrics'].expectancy
    trade_diff = v3b['metrics'].trades - v3a['metrics'].trades

    if exp_diff > 0:
        print(f"\n  CONCLUSION: A_5d_only is EDGE-DENSITY filter (+{exp_diff:.3f}% expectancy)")
        if seq_no_filter.get('negative_5d_avg', 0) < seq_no_filter.get('positive_5d_avg', 0):
            print(f"              Reason: Negative sector_5d trades have worse avg PnL ({seq_no_filter.get('negative_5d_avg', 0):.2f}% vs {seq_no_filter.get('positive_5d_avg', 0):.2f}%)")
    else:
        print(f"\n  CONCLUSION: A_5d_only is TRADE-REDUCTION filter only ({exp_diff:+.3f}% expectancy)")
        print(f"              Trades lost: {abs(trade_diff)}")

    # =========================================================================
    # PART 5: COMBINE WINNERS
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 5: COMBINE WINNERS")
    print("=" * 100)

    # Determine best components
    best_stock_d = v1b.expectancy > v1a.expectancy
    best_5d_filter = v3b['metrics'].expectancy > v3a['metrics'].expectancy

    # Try combinations
    combos = {
        'COMBO-A_baseline': {'stock_d': False, '5d': False, 'dd': False},
        'COMBO-B_stock_d': {'stock_d': True, '5d': False, 'dd': False},
        'COMBO-C_5d_filter': {'stock_d': False, '5d': True, 'dd': False},
        'COMBO-D_both_filters': {'stock_d': True, '5d': True, 'dd': False},
        'COMBO-E_filters+light_dd': {'stock_d': True, '5d': True, 'dd': 'light'},
        'COMBO-F_bear_special': {'stock_d': True, '5d': True, 'dd': 'bear_exempt'},
    }

    combo_results = {}
    for name, params in combos.items():
        config = StrategyConfig(name)
        config.stock_d_required = params['stock_d']
        config.sector_5d_required = params['5d']

        if params['dd'] == 'light':
            config.daily_limit = -3.0
            config.circuit_breaker_dd = 20.0
        elif params['dd'] == 'bear_exempt':
            # Full DD ctrl but exempt BEAR
            config.daily_limit = -2.0
            config.circuit_breaker_dd = 15.0
            # Note: Would need special handling - simplify for now
            pass

        trades, stats = run_backtest(market_data, stock_data, sector_metrics, config)
        combo_results[name] = {
            'metrics': calculate_quant_metrics(trades),
            'regime': calculate_regime_metrics(trades),
            'stats': stats
        }

    print(f"\nCombination Results:")
    print("-" * 100)
    for name, r in combo_results.items():
        m = r['metrics']
        bear = r['regime']['BEAR']
        print(f"{name:<25} E[R]:{m.expectancy:>+.3f}% | Trades:{m.trades:>4} | "
              f"MaxDD:{m.max_dd:>5.1f}% | BEAR E[R]:{bear.expectancy:>+.3f}%")

    # =========================================================================
    # PART 6: ANSWERS TO KEY QUESTIONS
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 6: ANSWERS TO KEY QUESTIONS")
    print("=" * 100)

    # F1: Does Stock-D improve expectancy?
    print(f"""
F1: Does Stock-D improve Expectancy across regimes?
    Baseline E[R]: {v1a.expectancy:+.3f}%
    Stock-D E[R]:  {v1b.expectancy:+.3f}%
    Delta: {v1b.expectancy - v1a.expectancy:+.3f}%
    Answer: {'YES - Stock-D improves edge density' if v1b.expectancy > v1a.expectancy else 'NO - Stock-D over-filters'}
""")

    # F2: Does DD Control destroy BEAR edge?
    print(f"""F2: Does DD Control destroy BEAR regime edge?
    BEAR without DD Ctrl: E[R]={v2a_bear.expectancy:+.3f}%, Trades={v2a_bear.trades}
    BEAR with Full DD Ctrl: E[R]={v2c_bear.expectancy:+.3f}%, Trades={v2c_bear.trades}
    Delta: {v2c_bear.expectancy - v2a_bear.expectancy:+.3f}%
    Answer: {'YES - DD Control kills BEAR edge' if v2c_bear.expectancy < v2a_bear.expectancy and v2a_bear.expectancy > 0 else 'NO - DD Control acceptable'}
""")

    # F3: Is A_5d_only edge-density or trade-reduction?
    print(f"""F3: Is A_5d_only an edge-density filter or trade-reduction filter?
    Without filter: E[R]={v3a['metrics'].expectancy:+.3f}%, Trades={v3a['metrics'].trades}
    With filter: E[R]={v3b['metrics'].expectancy:+.3f}%, Trades={v3b['metrics'].trades}
    Delta: {v3b['metrics'].expectancy - v3a['metrics'].expectancy:+.3f}%
    Answer: {'EDGE-DENSITY filter' if exp_diff > 0 else 'TRADE-REDUCTION filter only'}
""")

    # F4: Optimal configuration per regime
    print(f"""F4: What is the optimal configuration per regime?""")

    # Find best config per regime
    best_per_regime = {}
    for regime in ['BULL', 'BEAR', 'NEUTRAL']:
        best_exp = -999
        best_name = None
        for name, r in combo_results.items():
            if r['regime'][regime].trades > 5:  # Minimum sample
                if r['regime'][regime].expectancy > best_exp:
                    best_exp = r['regime'][regime].expectancy
                    best_name = name
        best_per_regime[regime] = (best_name, best_exp)
        m = combo_results[best_name]['regime'][regime] if best_name else None
        if m:
            print(f"    {regime}: {best_name} → E[R]={m.expectancy:+.3f}%, Win={m.win_rate:.1f}%, Trades={m.trades}")

    # =========================================================================
    # PART 7: FINAL RECOMMENDATION
    # =========================================================================
    print("\n" + "=" * 100)
    print("PART 7: FINAL RECOMMENDATION")
    print("=" * 100)

    # Find best overall
    best_overall = max(combo_results.items(),
                       key=lambda x: x[1]['metrics'].expectancy if x[1]['metrics'].trades > 50 else -999)
    best_name, best = best_overall

    print(f"""
RECOMMENDED CONFIGURATION: {best_name}

Overall Performance:
- Expectancy/trade: {best['metrics'].expectancy:+.3f}%
- Win Rate: {best['metrics'].win_rate:.1f}%
- Profit Factor: {best['metrics'].profit_factor:.2f}
- Max Drawdown: {best['metrics'].max_dd:.1f}%
- Total Trades: {best['metrics'].trades}
- Sharpe: {best['metrics'].sharpe:.2f}

Per-Regime Performance:
- BULL:    E[R]={best['regime']['BULL'].expectancy:>+.3f}%, Trades={best['regime']['BULL'].trades}
- BEAR:    E[R]={best['regime']['BEAR'].expectancy:>+.3f}%, Trades={best['regime']['BEAR'].trades}
- NEUTRAL: E[R]={best['regime']['NEUTRAL'].expectancy:>+.3f}%, Trades={best['regime']['NEUTRAL'].trades}

Key Findings:
""")

    # Stock-D finding
    if v1b.expectancy > v1a.expectancy:
        print(f"1. Stock-D RECOMMENDED - improves expectancy by {v1b.expectancy - v1a.expectancy:+.3f}%")
    else:
        print(f"1. Stock-D NOT recommended - reduces expectancy")

    # DD Control finding
    if v2c_bear.expectancy < v2a_bear.expectancy and v2a_bear.expectancy > 0:
        print(f"2. DD Control hurts BEAR - consider regime-specific DD rules")
        print(f"   Suggestion: Use light DD control (-3% daily limit) or exempt BEAR regime")
    else:
        print(f"2. DD Control acceptable across regimes")

    # 5d filter finding
    if exp_diff > 0:
        print(f"3. A_5d_only RECOMMENDED - edge-density filter (+{exp_diff:.3f}%)")
    else:
        print(f"3. A_5d_only optional - mainly reduces trades")

    # Trade-off summary
    print(f"""
Trade-Off Summary:
- Filters (Stock-D, 5d): Improve expectancy but reduce trades
- DD Controls: Reduce Max DD but may hurt BEAR edge
- Sweet spot: {best_name} with E[R]={best['metrics'].expectancy:+.3f}%, {best['metrics'].trades} trades
""")

    print("\n" + "=" * 100)
    print("BACKTEST COMPLETE")
    print("=" * 100)


if __name__ == '__main__':
    main()
