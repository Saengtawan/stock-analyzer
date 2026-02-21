#!/usr/bin/env python3
"""
Real Backtest with Actual Scanners + Dynamic Allocation (Layer 1+2)

Uses actual screeners:
- rapid_rotation_screener.py (Dip Bounce)
- overnight_gap_scanner.py (Overnight Gap)
- pem_screener.py (PEM)

Period: 2023-2025 (3 years)
Capital: $5,000
Costs: Slippage 0.2% + Commission 0.1% = 0.3% total per trade
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional
import yfinance as yf
from loguru import logger
import pickle

# Import actual scanners
from screeners.rapid_rotation_screener import RapidRotationScreener
from screeners.overnight_gap_scanner import OvernightGapScanner
try:
    from screeners.pem_screener import PEMScreener
except ImportError:
    logger.warning("PEM screener not available")
    PEMScreener = None

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

        win_rate = len(winners) / len(trades) if trades else 0.5
        avg_pnl = np.mean(trades) if trades else 0.0
        expectancy = avg_pnl

        return {
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'expectancy': expectancy,
            'trade_count': len(trades)
        }


class DynamicAllocator:
    """Dynamic position sizing based on VIX and performance"""

    def __init__(self, total_capital: float = 5000):
        self.total_capital = total_capital
        self.tracker = PerformanceTracker(window=20)

    def get_allocation_fixed(self) -> Dict[str, float]:
        """Baseline: Fixed allocation"""
        return {
            'dip_bounce': 0.30,
            'overnight_gap': 0.60,
            'pem': 0.10
        }

    def get_allocation_dynamic(self, vix: float) -> Dict[str, float]:
        """Layer 1+2: VIX + Performance-based allocation"""
        # Layer 1: VIX-based base allocation
        if vix < 20:  # NORMAL
            base_alloc = {
                'dip_bounce': 0.50,
                'overnight_gap': 0.40,
                'pem': 0.10
            }
        elif vix < 24:  # SKIP
            base_alloc = {
                'dip_bounce': 0.30,
                'overnight_gap': 0.60,
                'pem': 0.10
            }
        elif vix < 38:  # HIGH
            base_alloc = {
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

        # Layer 2: Adjust based on performance
        metrics = self.tracker.get_all_metrics()
        dip_exp = metrics['dip_bounce']['expectancy']
        overnight_exp = metrics['overnight_gap']['expectancy']

        # Only adjust if both have sufficient data
        if (metrics['dip_bounce']['trade_count'] >= 5 and
            metrics['overnight_gap']['trade_count'] >= 5):

            if dip_exp > overnight_exp * 1.5:
                # Dip bounce performing much better
                base_alloc['dip_bounce'] = min(0.70, base_alloc['dip_bounce'] + 0.20)
                base_alloc['overnight_gap'] = max(0.20, base_alloc['overnight_gap'] - 0.20)
            elif overnight_exp > dip_exp * 1.5:
                # Overnight performing much better
                base_alloc['dip_bounce'] = max(0.20, base_alloc['dip_bounce'] - 0.20)
                base_alloc['overnight_gap'] = min(0.70, base_alloc['overnight_gap'] + 0.20)

        return base_alloc

    def get_all_metrics(self) -> Dict:
        """Get metrics for all strategies"""
        return {
            'dip_bounce': self.tracker.get_metrics('dip_bounce'),
            'overnight_gap': self.tracker.get_metrics('overnight_gap'),
            'pem': self.tracker.get_metrics('pem')
        }


class Position:
    """Represents an open position"""
    def __init__(self, symbol: str, strategy: str, entry_date, entry_price: float,
                 qty: int, sl_price: float, tp_price: float, score: int):
        self.symbol = symbol
        self.strategy = strategy
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.qty = qty
        self.sl_price = sl_price
        self.tp_price = tp_price
        self.score = score
        self.days_held = 0
        self.peak_price = entry_price


class RealBacktestEngine:
    """Real backtest engine using actual scanners"""

    def __init__(self, start_date: str, end_date: str, initial_capital: float = 5000,
                 use_dynamic: bool = True):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.use_dynamic = use_dynamic

        self.allocator = DynamicAllocator(initial_capital)
        self.positions: Dict[str, Position] = {}
        self.capital = initial_capital

        # Trading costs
        self.SLIPPAGE_PCT = 0.2  # 0.2% slippage
        self.COMMISSION_PCT = 0.1  # 0.1% commission
        self.TOTAL_COST_PCT = self.SLIPPAGE_PCT + self.COMMISSION_PCT  # 0.3%

        # Load VIX data
        logger.info("Loading VIX data...")
        try:
            vix_ticker = yf.Ticker('^VIX')
            vix = vix_ticker.history(start=start_date, end=end_date)
            vix.index = pd.to_datetime(vix.index)
            self.vix_data = vix['Close'].to_dict()
            logger.info(f"Loaded {len(self.vix_data)} days of VIX data")
        except Exception as e:
            logger.warning(f"Failed to load VIX: {e}")
            self.vix_data = {}

        # Load universe data
        logger.info("Loading universe data...")
        self.universe_data = self._load_universe_data()
        logger.info(f"Loaded data for {len(self.universe_data)} symbols")

        # Initialize scanners
        logger.info("Initializing scanners...")
        self.dip_scanner = RapidRotationScreener()
        self.overnight_scanner = OvernightGapScanner()
        self.pem_scanner = PEMScreener() if PEMScreener else None

    def _load_universe_data(self) -> Dict:
        """Load historical data for universe"""
        cache_file = 'data/backtest_universe_cache.pkl'

        # Try to load from cache
        if os.path.exists(cache_file):
            try:
                logger.info("Loading from cache...")
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
            except:
                pass

        # Load fresh data (use pre-filtered list if available)
        try:
            # Try to load pre-filtered list
            prefilter_file = 'data/pre_filtered.json'
            if os.path.exists(prefilter_file):
                import json
                with open(prefilter_file, 'r') as f:
                    data = json.load(f)
                    # Check structure: {'stocks': {symbol: {...}}}
                    if 'stocks' in data:
                        symbols = list(data['stocks'].keys())
                        logger.info(f"Using {len(symbols)} pre-filtered symbols")
                    else:
                        symbols = data.get('symbols', [])
                        logger.info(f"Using {len(symbols)} pre-filtered symbols (legacy format)")
            else:
                # Fallback to common tech stocks
                symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
                          'NFLX', 'CRM', 'ORCL', 'ADBE', 'PYPL', 'INTC', 'CSCO',
                          'QCOM', 'TXN', 'AVGO', 'NOW', 'SNOW', 'MU', 'AMAT', 'LRCX',
                          'KLAC', 'MRVL', 'ON', 'MPWR', 'SWKS', 'QRVO', 'ASML', 'TSM']
                logger.warning(f"Using fallback list of {len(symbols)} tech stocks")

            # Limit to first 100 symbols for faster backtest
            if len(symbols) > 100:
                logger.info(f"Limiting universe to first 100 symbols (from {len(symbols)})")
                symbols = symbols[:100]

        except Exception as e:
            logger.error(f"Error loading symbols: {e}")
            return {}

        # Download data
        universe = {}
        batch_size = 10

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            logger.info(f"Downloading batch {i//batch_size + 1}/{(len(symbols)-1)//batch_size + 1}")

            try:
                data = yf.download(batch, start=self.start_date, end=self.end_date,
                                 group_by='ticker', progress=False)

                for symbol in batch:
                    try:
                        if len(batch) == 1:
                            df = data
                        else:
                            df = data[symbol]

                        if df is not None and len(df) > 100:
                            universe[symbol] = df
                    except:
                        continue

            except Exception as e:
                logger.warning(f"Batch download failed: {e}")
                continue

        # Save cache
        try:
            os.makedirs('data', exist_ok=True)
            with open(cache_file, 'wb') as f:
                pickle.dump(universe, f)
            logger.info(f"Saved cache with {len(universe)} symbols")
        except:
            pass

        return universe

    def get_vix(self, date) -> float:
        """Get VIX for date"""
        if not self.vix_data:
            return 20.0

        date = pd.Timestamp(date.date())

        # Try exact match
        for key in self.vix_data.keys():
            if pd.Timestamp(key.date()) == date:
                return float(self.vix_data[key])

        # Find closest previous
        for key in sorted(self.vix_data.keys(), reverse=True):
            if pd.Timestamp(key.date()) <= date:
                return float(self.vix_data[key])

        return 20.0

    def get_data_for_date(self, date) -> Dict:
        """Get universe data up to date"""
        data_snapshot = {}

        for symbol, df in self.universe_data.items():
            df_until = df[df.index <= date]
            if len(df_until) >= 50:  # Minimum data needed
                data_snapshot[symbol] = df_until

        return data_snapshot

    def scan_for_signals(self, date, data_snapshot: Dict, vix: float) -> List:
        """Run all scanners for the day"""
        signals = []

        # Get allocation
        if self.use_dynamic:
            allocation = self.allocator.get_allocation_dynamic(vix)
        else:
            allocation = self.allocator.get_allocation_fixed()

        # Dip bounce
        if allocation.get('dip_bounce', 0) > 0:
            try:
                dip_signals = self.dip_scanner.screen(
                    universe=data_snapshot,
                    min_score=80,
                    position_pct=allocation['dip_bounce'] * 100,
                    target_pct=10.0,
                    sl_pct=3.5
                )
                for sig in dip_signals[:3]:  # Top 3
                    signals.append({
                        'symbol': sig.symbol,
                        'strategy': 'dip_bounce',
                        'score': sig.score,
                        'entry_price': sig.entry_price,
                        'sl_price': sig.stop_loss,
                        'tp_price': sig.take_profit,
                        'allocation': allocation['dip_bounce']
                    })
            except Exception as e:
                logger.debug(f"Dip scanner error: {e}")

        # Overnight gap
        if allocation.get('overnight_gap', 0) > 0:
            try:
                overnight_signals = self.overnight_scanner.scan(
                    universe=data_snapshot,
                    min_score=80,
                    position_pct=allocation['overnight_gap'] * 100,
                    target_pct=3.0,
                    sl_pct=1.5
                )
                for sig in overnight_signals[:2]:  # Top 2
                    signals.append({
                        'symbol': sig.symbol,
                        'strategy': 'overnight_gap',
                        'score': sig.score,
                        'entry_price': sig.entry_price,
                        'sl_price': sig.stop_loss,
                        'tp_price': sig.take_profit,
                        'allocation': allocation['overnight_gap']
                    })
            except Exception as e:
                logger.debug(f"Overnight scanner error: {e}")

        # PEM
        if self.pem_scanner and allocation.get('pem', 0) > 0:
            try:
                pem_signals = self.pem_scanner.scan(
                    universe=data_snapshot,
                    min_score=80,
                    position_pct=allocation['pem'] * 100
                )
                for sig in pem_signals[:1]:  # Top 1
                    signals.append({
                        'symbol': sig.get('symbol'),
                        'strategy': 'pem',
                        'score': sig.get('score', 80),
                        'entry_price': sig.get('entry_price'),
                        'sl_price': sig.get('stop_loss'),
                        'tp_price': sig.get('take_profit'),
                        'allocation': allocation['pem']
                    })
            except Exception as e:
                logger.debug(f"PEM scanner error: {e}")

        return signals

    def execute_signal(self, signal: Dict, date) -> bool:
        """Execute entry for signal"""
        symbol = signal['symbol']

        # Skip if already have position
        if symbol in self.positions:
            return False

        # Calculate position size
        allocation = signal['allocation']
        position_value = self.capital * allocation

        if position_value < 100:  # Min $100
            return False

        # Entry price with slippage
        entry_price = signal['entry_price'] * (1 + self.SLIPPAGE_PCT / 100)

        # Calculate qty
        qty = int(position_value / entry_price)
        if qty == 0:
            return False

        actual_cost = qty * entry_price
        commission = actual_cost * (self.COMMISSION_PCT / 100)
        total_cost = actual_cost + commission

        if total_cost > self.capital * 0.9:  # Don't use more than 90%
            return False

        # Create position
        self.positions[symbol] = Position(
            symbol=symbol,
            strategy=signal['strategy'],
            entry_date=date,
            entry_price=entry_price,
            qty=qty,
            sl_price=signal['sl_price'],
            tp_price=signal['tp_price'],
            score=signal['score']
        )

        self.capital -= total_cost

        logger.debug(f"BUY {symbol} @ ${entry_price:.2f} x{qty} = ${actual_cost:.0f} ({signal['strategy']})")

        return True

    def update_positions(self, date, data_snapshot: Dict) -> List:
        """Update positions and check exits"""
        exits = []

        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            pos.days_held += 1

            # Get current price
            if symbol not in data_snapshot:
                continue

            df = data_snapshot[symbol]
            if len(df) == 0:
                continue

            current_price = float(df['Close'].iloc[-1])
            high = float(df['High'].iloc[-1])
            low = float(df['Low'].iloc[-1])

            # Update peak
            pos.peak_price = max(pos.peak_price, high)

            # Check exits
            exit_reason = None
            exit_price = current_price

            # SL hit
            if low <= pos.sl_price:
                exit_reason = 'SL'
                exit_price = pos.sl_price * (1 - self.SLIPPAGE_PCT / 100)

            # TP hit
            elif high >= pos.tp_price:
                exit_reason = 'TP'
                exit_price = pos.tp_price * (1 - self.SLIPPAGE_PCT / 100)

            # Time exit (overnight=1 day, others=7 days)
            elif pos.strategy == 'overnight_gap' and pos.days_held >= 1:
                exit_reason = 'TIME'
                exit_price = current_price * (1 - self.SLIPPAGE_PCT / 100)
            elif pos.strategy != 'overnight_gap' and pos.days_held >= 7:
                exit_reason = 'TIME'
                exit_price = current_price * (1 - self.SLIPPAGE_PCT / 100)

            if exit_reason:
                # Calculate P&L
                proceeds = pos.qty * exit_price
                commission = proceeds * (self.COMMISSION_PCT / 100)
                net_proceeds = proceeds - commission

                cost_basis = pos.qty * pos.entry_price
                pnl_usd = net_proceeds - cost_basis
                pnl_pct = (pnl_usd / cost_basis) * 100

                self.capital += net_proceeds

                # Record exit
                exits.append({
                    'date': date,
                    'symbol': symbol,
                    'strategy': pos.strategy,
                    'entry_date': pos.entry_date,
                    'entry_price': pos.entry_price,
                    'exit_price': exit_price,
                    'exit_reason': exit_reason,
                    'qty': pos.qty,
                    'days_held': pos.days_held,
                    'pnl_usd': pnl_usd,
                    'pnl_pct': pnl_pct,
                    'score': pos.score
                })

                # Update performance tracker
                self.allocator.tracker.add_trade(pos.strategy, pnl_pct)

                logger.debug(f"SELL {symbol} @ ${exit_price:.2f} ({exit_reason}) P&L: ${pnl_usd:.0f} ({pnl_pct:+.1f}%)")

                # Remove position
                del self.positions[symbol]

        return exits

    def run(self) -> Dict:
        """Run backtest"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Running {'Dynamic' if self.use_dynamic else 'Fixed'} Allocation Backtest")
        logger.info(f"{'='*60}")

        trades = []
        daily_capital = []

        start = pd.to_datetime(self.start_date)
        end = pd.to_datetime(self.end_date)
        current_date = start

        while current_date <= end:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # Get market data
            vix = self.get_vix(current_date)
            data_snapshot = self.get_data_for_date(current_date)

            if not data_snapshot:
                current_date += timedelta(days=1)
                continue

            # Update existing positions
            exits = self.update_positions(current_date, data_snapshot)
            trades.extend(exits)

            # Scan for new signals
            if len(self.positions) < 4:  # Max 4 positions
                signals = self.scan_for_signals(current_date, data_snapshot, vix)

                for signal in signals:
                    if len(self.positions) >= 4:
                        break
                    self.execute_signal(signal, current_date)

            # Record daily capital
            daily_capital.append({
                'date': current_date,
                'capital': self.capital,
                'positions': len(self.positions),
                'vix': vix
            })

            current_date += timedelta(days=1)

        # Close remaining positions
        logger.info("Closing remaining positions...")
        for symbol, pos in list(self.positions.items()):
            if symbol in self.universe_data:
                df = self.universe_data[symbol]
                final_price = float(df['Close'].iloc[-1])
                proceeds = pos.qty * final_price * (1 - self.TOTAL_COST_PCT / 100)
                cost_basis = pos.qty * pos.entry_price
                pnl_usd = proceeds - cost_basis
                pnl_pct = (pnl_usd / cost_basis) * 100

                self.capital += proceeds

                trades.append({
                    'date': end,
                    'symbol': symbol,
                    'strategy': pos.strategy,
                    'entry_date': pos.entry_date,
                    'entry_price': pos.entry_price,
                    'exit_price': final_price,
                    'exit_reason': 'FINAL',
                    'qty': pos.qty,
                    'days_held': pos.days_held,
                    'pnl_usd': pnl_usd,
                    'pnl_pct': pnl_pct,
                    'score': pos.score
                })

        # Calculate results
        return self._calculate_results(trades, daily_capital)

    def _calculate_results(self, trades: List, daily_capital: List) -> Dict:
        """Calculate backtest results"""
        if not trades:
            logger.warning("No trades executed")
            return None

        df_trades = pd.DataFrame(trades)
        df_daily = pd.DataFrame(daily_capital)

        total_return = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        total_days = (pd.to_datetime(self.end_date) - pd.to_datetime(self.start_date)).days
        total_months = total_days / 30.44

        monthly_return = (self.capital / self.initial_capital) ** (1 / total_months) - 1
        cagr = ((self.capital / self.initial_capital) ** (12 / total_months) - 1) * 100

        winners = df_trades[df_trades['pnl_pct'] > 0]
        losers = df_trades[df_trades['pnl_pct'] <= 0]
        win_rate = len(winners) / len(df_trades) * 100

        avg_winner = winners['pnl_pct'].mean() if len(winners) > 0 else 0
        avg_loser = losers['pnl_pct'].mean() if len(losers) > 0 else 0

        # Max drawdown
        df_daily['peak'] = df_daily['capital'].cummax()
        df_daily['dd'] = (df_daily['capital'] - df_daily['peak']) / df_daily['peak'] * 100
        max_dd = df_daily['dd'].min()

        monthly_pnl = self.capital - self.initial_capital
        avg_monthly_usd = monthly_pnl / total_months

        results = {
            'mode': 'Dynamic' if self.use_dynamic else 'Fixed',
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
            'final_capital': self.capital,
            'trades': df_trades,
            'daily': df_daily
        }

        # Print summary
        logger.info(f"\n📊 Results:")
        logger.info(f"Total Trades: {len(df_trades)} ({len(df_trades)/total_months:.1f}/month)")
        logger.info(f"Win Rate: {win_rate:.1f}%")
        logger.info(f"Avg Winner: +{avg_winner:.2f}%")
        logger.info(f"Avg Loser: {avg_loser:.2f}%")
        logger.info(f"Total Return: {total_return:.1f}%")
        logger.info(f"CAGR: {cagr:.1f}%")
        logger.info(f"Monthly: ${avg_monthly_usd:.0f} ({monthly_return*100:.1f}%)")
        logger.info(f"Max DD: {max_dd:.1f}%")
        logger.info(f"Final Capital: ${self.capital:,.0f}")

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
    """Run real backtest"""

    logger.info("="*80)
    logger.info("REAL BACKTEST WITH ACTUAL SCANNERS + DYNAMIC ALLOCATION")
    logger.info("="*80)
    logger.info(f"Period: 2023-01-01 to 2025-12-31")
    logger.info(f"Capital: $5,000")
    logger.info(f"Costs: Slippage 0.2% + Commission 0.1% = 0.3% per trade")

    # Run both scenarios
    results = {}

    # Baseline: Fixed allocation
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 1: Fixed Allocation (30% dip, 60% overnight, 10% PEM)")
    logger.info("="*80)
    engine_fixed = RealBacktestEngine(
        start_date='2023-01-01',
        end_date='2025-12-31',
        initial_capital=5000,
        use_dynamic=False
    )
    results['fixed'] = engine_fixed.run()

    # Dynamic: Layer 1+2
    logger.info("\n" + "="*80)
    logger.info("SCENARIO 2: Dynamic Allocation (VIX + Performance)")
    logger.info("="*80)
    engine_dynamic = RealBacktestEngine(
        start_date='2023-01-01',
        end_date='2025-12-31',
        initial_capital=5000,
        use_dynamic=True
    )
    results['dynamic'] = engine_dynamic.run()

    # Comparison
    if results['fixed'] and results['dynamic']:
        logger.info("\n" + "="*80)
        logger.info("COMPARISON")
        logger.info("="*80)

        comparison = []
        for name in ['fixed', 'dynamic']:
            r = results[name]
            comparison.append({
                'Mode': r['mode'],
                'Trades/mo': f"{r['trades_per_month']:.1f}",
                'Win%': f"{r['win_rate']:.1f}%",
                'CAGR': f"{r['cagr']:.1f}%",
                'Monthly $': f"${r['avg_monthly_usd']:.0f}",
                'Monthly %': f"{r['monthly_return_pct']:.1f}%",
                'Max DD': f"{r['max_drawdown']:.1f}%",
                'Final $': f"${r['final_capital']:,.0f}"
            })

        df_comp = pd.DataFrame(comparison)
        print("\n" + df_comp.to_string(index=False))

        # Check 6% target
        target = 6.0
        logger.info(f"\n🎯 Target: {target}% monthly")

        for name in ['fixed', 'dynamic']:
            r = results[name]
            monthly_pct = r['monthly_return_pct']
            diff = monthly_pct - target
            status = "✅ HIT" if monthly_pct >= target else "❌ MISS"
            logger.info(f"{status} {r['mode']}: {monthly_pct:.1f}% ({diff:+.1f}%)")

    logger.info("\n" + "="*80)
    logger.info("Real backtest complete!")
    logger.info("="*80)

    return results


if __name__ == '__main__':
    results = main()
