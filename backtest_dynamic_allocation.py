#!/usr/bin/env python3
"""
Dynamic Allocation Backtest (Layer 1+2+3)

Tests smart allocation vs fixed allocation:
- Baseline: Fixed 30% dip, 60% overnight, 10% PEM
- Scenario 1: VIX-based allocation (Layer 1)
- Scenario 2: VIX + Performance tracking (Layer 1+2)
- Scenario 3: VIX + Performance + Signal quality (Layer 1+2+3)

Period: 2023-2025 (3 years)
Capital: $5,000
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Tuple
import yfinance as yf
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


class PerformanceTracker:
    """Track rolling performance metrics for each strategy"""

    def __init__(self, window: int = 20):
        self.window = window
        self.trades = defaultdict(lambda: deque(maxlen=window))

    def add_trade(self, strategy: str, pnl_pct: float):
        """Add trade result"""
        self.trades[strategy].append(pnl_pct)

    def get_metrics(self, strategy: str) -> Dict:
        """Get current metrics for strategy"""
        if strategy not in self.trades or len(self.trades[strategy]) == 0:
            return {
                'win_rate': 0.5,
                'avg_pnl': 0.0,
                'expectancy': 0.0,
                'trade_count': 0
            }

        trades = list(self.trades[strategy])
        winners = [t for t in trades if t > 0]
        losers = [t for t in trades if t <= 0]

        win_rate = len(winners) / len(trades) if trades else 0.5
        avg_pnl = np.mean(trades) if trades else 0.0
        expectancy = avg_pnl  # Simplified expectancy

        return {
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'expectancy': expectancy,
            'trade_count': len(trades)
        }

    def get_all_metrics(self) -> Dict:
        """Get metrics for all strategies"""
        return {
            'dip_bounce': self.get_metrics('dip_bounce'),
            'overnight_gap': self.get_metrics('overnight_gap'),
            'pem': self.get_metrics('pem')
        }


class DynamicAllocator:
    """Dynamic position sizing based on market regime and performance"""

    def __init__(self, total_capital: float = 5000):
        self.total_capital = total_capital
        self.tracker = PerformanceTracker(window=20)

    def get_allocation_fixed(self) -> Dict[str, float]:
        """Baseline: Fixed allocation"""
        return {
            'dip_bounce': 0.30,     # 30%
            'overnight_gap': 0.60,  # 60%
            'pem': 0.10             # 10%
        }

    def get_allocation_vix(self, vix: float) -> Dict[str, float]:
        """Layer 1: VIX-based allocation"""
        if vix < 20:  # NORMAL
            return {
                'dip_bounce': 0.50,
                'overnight_gap': 0.40,
                'pem': 0.10
            }
        elif vix < 24:  # SKIP
            return {
                'dip_bounce': 0.30,
                'overnight_gap': 0.60,
                'pem': 0.10
            }
        elif vix < 38:  # HIGH
            return {
                'dip_bounce': 0.00,
                'overnight_gap': 0.00,
                'pem': 1.00
            }
        else:  # EXTREME
            return {
                'dip_bounce': 0.00,
                'overnight_gap': 0.00,
                'pem': 0.00
            }

    def get_allocation_performance(self, vix: float) -> Dict[str, float]:
        """Layer 1+2: VIX + Performance-based allocation"""
        # Start with VIX-based
        base_alloc = self.get_allocation_vix(vix)

        # Get recent performance
        metrics = self.tracker.get_all_metrics()
        dip_exp = metrics['dip_bounce']['expectancy']
        overnight_exp = metrics['overnight_gap']['expectancy']

        # Adjust based on performance (only if both have data)
        if metrics['dip_bounce']['trade_count'] >= 5 and metrics['overnight_gap']['trade_count'] >= 5:
            if dip_exp > overnight_exp * 1.5:
                # Dip bounce performing much better
                base_alloc['dip_bounce'] = min(0.70, base_alloc['dip_bounce'] + 0.20)
                base_alloc['overnight_gap'] = max(0.20, base_alloc['overnight_gap'] - 0.20)
            elif overnight_exp > dip_exp * 1.5:
                # Overnight performing much better
                base_alloc['dip_bounce'] = max(0.20, base_alloc['dip_bounce'] - 0.20)
                base_alloc['overnight_gap'] = min(0.70, base_alloc['overnight_gap'] + 0.20)

        return base_alloc

    def pick_best_signal(self, signals: List[Dict]) -> Dict:
        """Layer 3: Signal quality gating - pick highest score"""
        if not signals:
            return None
        return max(signals, key=lambda s: s['score'])

    def get_position_size(self, strategy: str, allocation: Dict[str, float]) -> float:
        """Calculate position size based on allocation"""
        return self.total_capital * allocation.get(strategy, 0)


class BacktestEngine:
    """Backtest engine with dynamic allocation"""

    def __init__(self, start_date: str, end_date: str, initial_capital: float = 5000):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.allocator = DynamicAllocator(initial_capital)

        # Load VIX data
        logger.info("Loading VIX data...")
        try:
            vix_ticker = yf.Ticker('^VIX')
            vix = vix_ticker.history(start=start_date, end=end_date)
            if len(vix) == 0:
                logger.warning("No VIX data loaded, using default VIX=20")
                self.vix_data = {}
            else:
                # Convert index to datetime and create dict
                vix.index = pd.to_datetime(vix.index)
                self.vix_data = vix['Close'].to_dict()
                logger.info(f"Loaded {len(self.vix_data)} days of VIX data")
        except Exception as e:
            logger.warning(f"Failed to load VIX data: {e}, using default VIX=20")
            self.vix_data = {}

    def get_vix(self, date) -> float:
        """Get VIX for date (or closest previous)"""
        if not self.vix_data:
            return 20.0  # Default if no data loaded

        # Convert to datetime if string
        if isinstance(date, str):
            date = pd.to_datetime(date)

        # Normalize to date only (remove time)
        date = pd.Timestamp(date.date())

        # Try exact match first
        for key in self.vix_data.keys():
            key_date = pd.Timestamp(key.date()) if hasattr(key, 'date') else pd.to_datetime(key).date()
            key_date = pd.Timestamp(key_date)
            if key_date == date:
                return float(self.vix_data[key])

        # Find closest previous date
        dates_dict = {}
        for key in self.vix_data.keys():
            key_date = pd.Timestamp(key.date()) if hasattr(key, 'date') else pd.to_datetime(key).date()
            key_date = pd.Timestamp(key_date)
            dates_dict[key_date] = key

        for d in sorted(dates_dict.keys(), reverse=True):
            if d <= date:
                return float(self.vix_data[dates_dict[d]])

        return 20.0  # Default if no data

    def generate_mock_signals(self, date, num_days: int = 252) -> List[Dict]:
        """
        Generate realistic mock signals based on market conditions

        In real backtest, this would be replaced by actual strategy scanners.
        For now, we simulate signals with realistic distributions:
        - Dip bounce: 0-3 signals/day, score 70-95, WR ~45-55%
        - Overnight gap: 0-2 signals/day, score 65-90, WR ~40-50%
        - PEM: 0-1 signals/week, score 75-95, WR ~55-65%
        """
        signals = []
        vix = self.get_vix(date)

        # Market regime affects signal quality and frequency
        if vix < 20:  # NORMAL - more signals, better quality
            num_dip = np.random.randint(1, 4)
            num_overnight = np.random.randint(1, 3)
            score_boost = 5
        elif vix < 24:  # SKIP - fewer signals, medium quality
            num_dip = np.random.randint(0, 2)
            num_overnight = np.random.randint(1, 2)
            score_boost = 0
        elif vix < 38:  # HIGH - very few signals, poor quality
            num_dip = 0
            num_overnight = 0
            score_boost = -10
        else:  # EXTREME
            return []

        # Generate dip bounce signals
        for i in range(num_dip):
            signals.append({
                'strategy': 'dip_bounce',
                'score': np.random.randint(70, 95) + score_boost,
                'expected_hold_days': np.random.randint(3, 8),
                'sl_pct': 3.5,
                'tp_pct': 10.0
            })

        # Generate overnight gap signals
        for i in range(num_overnight):
            signals.append({
                'strategy': 'overnight_gap',
                'score': np.random.randint(65, 90) + score_boost,
                'expected_hold_days': 1,  # Overnight = 1 day
                'sl_pct': 1.5,
                'tp_pct': 3.0
            })

        # Generate PEM signals (rare - ~8 per year)
        if np.random.random() < 0.03:  # 3% chance per day = ~7-8/year
            signals.append({
                'strategy': 'pem',
                'score': np.random.randint(75, 95),
                'expected_hold_days': np.random.randint(2, 5),
                'sl_pct': 5.0,
                'tp_pct': 15.0
            })

        return signals

    def simulate_trade_outcome(self, signal: Dict, vix: float) -> float:
        """
        Simulate trade P&L based on signal and market conditions

        Uses realistic win rates and P&L distributions:
        - Better scores → higher win rate
        - Lower VIX → better outcomes
        - Strategy-specific characteristics
        """
        strategy = signal['strategy']
        score = signal['score']

        # Base win rates (at score 80)
        base_wr = {
            'dip_bounce': 0.50,
            'overnight_gap': 0.46,
            'pem': 0.58
        }

        # Adjust WR based on score (every 10 points = +5% WR)
        score_adjustment = (score - 80) * 0.005

        # Adjust WR based on VIX
        if vix < 20:
            vix_adjustment = 0.08  # +8% in calm market
        elif vix < 24:
            vix_adjustment = 0.00  # neutral
        elif vix < 38:
            vix_adjustment = -0.10  # -10% in volatile market
        else:
            vix_adjustment = -0.20  # -20% in extreme

        win_rate = base_wr[strategy] + score_adjustment + vix_adjustment
        win_rate = max(0.2, min(0.8, win_rate))  # Clamp between 20-80%

        # Determine win/loss
        is_winner = np.random.random() < win_rate

        if is_winner:
            # Winner: use TP (with some variance)
            avg_winner = signal['tp_pct'] * np.random.uniform(0.7, 1.0)
            return avg_winner
        else:
            # Loser: use SL (with some variance)
            avg_loser = -signal['sl_pct'] * np.random.uniform(0.8, 1.0)
            return avg_loser

    def run_scenario(self, scenario_name: str, allocation_method: str) -> Dict:
        """
        Run backtest for one scenario

        Args:
            scenario_name: Name for logging
            allocation_method: 'fixed', 'vix', 'performance', 'full'
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {scenario_name}")
        logger.info(f"{'='*60}")

        capital = self.initial_capital
        trades = []
        daily_capital = []

        # Reset performance tracker
        self.allocator.tracker = PerformanceTracker(window=20)

        # Simulate trading days
        start = pd.to_datetime(self.start_date)
        end = pd.to_datetime(self.end_date)

        current_date = start
        day_count = 0

        while current_date <= end:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            day_count += 1
            vix = self.get_vix(current_date)

            # Get allocation for today
            if allocation_method == 'fixed':
                allocation = self.allocator.get_allocation_fixed()
            elif allocation_method == 'vix':
                allocation = self.allocator.get_allocation_vix(vix)
            elif allocation_method == 'performance':
                allocation = self.allocator.get_allocation_performance(vix)
            elif allocation_method == 'full':
                allocation = self.allocator.get_allocation_performance(vix)

            # Generate signals for today
            signals = self.generate_mock_signals(current_date)

            if signals:
                # Layer 3: Pick best signal if using full method
                if allocation_method == 'full':
                    signal = self.allocator.pick_best_signal(signals)
                    if signal:
                        signals = [signal]

                # Execute trades based on allocation
                for signal in signals:
                    strategy = signal['strategy']

                    # Check if we should trade this strategy (allocation > 0)
                    if allocation.get(strategy, 0) == 0:
                        continue

                    # Calculate position size
                    position_size = self.allocator.get_position_size(strategy, allocation)
                    if position_size < 100:  # Min $100 position
                        continue

                    # Simulate trade outcome
                    pnl_pct = self.simulate_trade_outcome(signal, vix)
                    pnl_usd = position_size * (pnl_pct / 100)

                    # Update capital
                    capital += pnl_usd

                    # Record trade
                    trades.append({
                        'date': current_date,
                        'strategy': strategy,
                        'score': signal['score'],
                        'position_size': position_size,
                        'pnl_pct': pnl_pct,
                        'pnl_usd': pnl_usd,
                        'vix': vix,
                        'allocation': allocation[strategy],
                        'capital_after': capital
                    })

                    # Update performance tracker
                    self.allocator.tracker.add_trade(strategy, pnl_pct)

            # Record daily capital
            daily_capital.append({
                'date': current_date,
                'capital': capital,
                'vix': vix
            })

            current_date += timedelta(days=1)

        # Calculate metrics
        if not trades:
            logger.warning(f"No trades executed for {scenario_name}")
            return None

        df_trades = pd.DataFrame(trades)
        df_daily = pd.DataFrame(daily_capital)

        total_return = ((capital - self.initial_capital) / self.initial_capital) * 100
        total_months = (end - start).days / 30.44
        monthly_return = (capital / self.initial_capital) ** (1 / total_months) - 1
        cagr = ((capital / self.initial_capital) ** (12 / total_months) - 1) * 100

        winners = df_trades[df_trades['pnl_pct'] > 0]
        losers = df_trades[df_trades['pnl_pct'] <= 0]
        win_rate = len(winners) / len(df_trades) * 100

        avg_winner = winners['pnl_pct'].mean() if len(winners) > 0 else 0
        avg_loser = losers['pnl_pct'].mean() if len(losers) > 0 else 0

        # Max drawdown
        df_daily['peak'] = df_daily['capital'].cummax()
        df_daily['dd'] = (df_daily['capital'] - df_daily['peak']) / df_daily['peak'] * 100
        max_dd = df_daily['dd'].min()

        # Monthly metrics
        monthly_pnl = capital - self.initial_capital
        avg_monthly_usd = monthly_pnl / total_months

        results = {
            'scenario': scenario_name,
            'total_trades': len(df_trades),
            'trades_per_month': len(df_trades) / total_months,
            'win_rate': win_rate,
            'avg_winner': avg_winner,
            'avg_loser': avg_loser,
            'total_return': total_return,
            'cagr': cagr,
            'monthly_return_pct': monthly_return * 100,
            'avg_monthly_usd': avg_monthly_usd,
            'max_drawdown': max_dd,
            'final_capital': capital,
            'sharpe_approx': monthly_return * 100 / abs(max_dd) if max_dd != 0 else 0,
            'trades': df_trades,
            'daily': df_daily
        }

        # Print summary
        logger.info(f"\n📊 {scenario_name} Results:")
        logger.info(f"Total Trades: {len(df_trades)} ({len(df_trades)/total_months:.1f}/month)")
        logger.info(f"Win Rate: {win_rate:.1f}%")
        logger.info(f"Avg Winner: +{avg_winner:.2f}%")
        logger.info(f"Avg Loser: {avg_loser:.2f}%")
        logger.info(f"Total Return: {total_return:.1f}%")
        logger.info(f"CAGR: {cagr:.1f}%")
        logger.info(f"Monthly: ${avg_monthly_usd:.0f} ({monthly_return*100:.1f}%)")
        logger.info(f"Max DD: {max_dd:.1f}%")
        logger.info(f"Final Capital: ${capital:,.0f}")

        # Strategy breakdown
        logger.info(f"\nStrategy Breakdown:")
        for strategy in ['dip_bounce', 'overnight_gap', 'pem']:
            strat_trades = df_trades[df_trades['strategy'] == strategy]
            if len(strat_trades) > 0:
                strat_wins = len(strat_trades[strat_trades['pnl_pct'] > 0])
                strat_wr = strat_wins / len(strat_trades) * 100
                strat_pnl = strat_trades['pnl_usd'].sum()
                logger.info(f"  {strategy}: {len(strat_trades)} trades, {strat_wr:.1f}% WR, ${strat_pnl:.0f} P&L")

        return results


def main():
    """Run all backtest scenarios"""

    logger.info("="*80)
    logger.info("DYNAMIC ALLOCATION BACKTEST (Layer 1+2+3)")
    logger.info("="*80)
    logger.info(f"Period: 2023-01-01 to 2025-12-31 (3 years)")
    logger.info(f"Capital: $5,000")
    logger.info(f"Strategies: Dip Bounce, Overnight Gap, PEM")

    # Initialize backtest
    engine = BacktestEngine(
        start_date='2023-01-01',
        end_date='2025-12-31',
        initial_capital=5000
    )

    # Run scenarios
    scenarios = [
        ('Baseline (Fixed 30/60/10)', 'fixed'),
        ('Layer 1: VIX-based Allocation', 'vix'),
        ('Layer 1+2: VIX + Performance', 'performance'),
        ('Layer 1+2+3: Full Dynamic', 'full'),
    ]

    results = {}
    for name, method in scenarios:
        result = engine.run_scenario(name, method)
        if result:
            results[name] = result

    # Comparison table
    logger.info("\n" + "="*80)
    logger.info("COMPARISON TABLE")
    logger.info("="*80)

    comparison = []
    for name, result in results.items():
        comparison.append({
            'Scenario': name,
            'Trades/mo': f"{result['trades_per_month']:.1f}",
            'Win%': f"{result['win_rate']:.1f}%",
            'CAGR': f"{result['cagr']:.1f}%",
            'Monthly $': f"${result['avg_monthly_usd']:.0f}",
            'Monthly %': f"{result['monthly_return_pct']:.1f}%",
            'Max DD': f"{result['max_drawdown']:.1f}%",
            'Final $': f"${result['final_capital']:,.0f}"
        })

    df_comp = pd.DataFrame(comparison)
    print("\n" + df_comp.to_string(index=False))

    # Find best scenario
    best = max(results.values(), key=lambda x: x['monthly_return_pct'])
    logger.info(f"\n🏆 Best Scenario: {best['scenario']}")
    logger.info(f"   Monthly: ${best['avg_monthly_usd']:.0f} ({best['monthly_return_pct']:.1f}%)")
    logger.info(f"   CAGR: {best['cagr']:.1f}%")
    logger.info(f"   Max DD: {best['max_drawdown']:.1f}%")

    # Check if we hit 6% target
    target_monthly = 6.0
    logger.info(f"\n🎯 Target: {target_monthly}% monthly (${target_monthly/100*5000:.0f}/month)")

    for name, result in results.items():
        monthly_pct = result['monthly_return_pct']
        diff = monthly_pct - target_monthly
        status = "✅ HIT" if monthly_pct >= target_monthly else "❌ MISS"
        logger.info(f"{status} {name}: {monthly_pct:.1f}% ({diff:+.1f}%)")

    logger.info("\n" + "="*80)
    logger.info("Backtest complete!")
    logger.info("="*80)

    return results


if __name__ == '__main__':
    results = main()
