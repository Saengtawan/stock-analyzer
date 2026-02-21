#!/usr/bin/env python3
"""
Simplified Dynamic Allocation Backtest
Tests dynamic allocation with simplified signal generation
(no dependency on complex real-time components)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List
import yfinance as yf
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")


class PerformanceTracker:
    """Track rolling performance for dynamic allocation"""
    def __init__(self, window: int = 20):
        self.window = window
        self.trades = defaultdict(lambda: deque(maxlen=window))

    def add_trade(self, strategy: str, pnl_pct: float):
        self.trades[strategy].append(pnl_pct)

    def get_expectancy(self, strategy: str) -> float:
        if strategy not in self.trades or len(self.trades[strategy]) == 0:
            return 0.0
        return np.mean(list(self.trades[strategy]))


class DynamicAllocator:
    """VIX + Performance based allocation"""
    def __init__(self, capital: float = 5000):
        self.capital = capital
        self.tracker = PerformanceTracker()

    def get_allocation(self, vix: float, use_dynamic: bool = True) -> Dict[str, float]:
        if not use_dynamic:
            # Fixed baseline
            return {'dip_bounce': 0.30, 'overnight_gap': 0.60, 'pem': 0.10}

        # Layer 1: VIX-based
        if vix < 20:
            base = {'dip_bounce': 0.50, 'overnight_gap': 0.40, 'pem': 0.10}
        elif vix < 24:
            base = {'dip_bounce': 0.30, 'overnight_gap': 0.60, 'pem': 0.10}
        elif vix < 38:
            base = {'dip_bounce': 0.00, 'overnight_gap': 0.00, 'pem': 1.00}
        else:
            return {'dip_bounce': 0.00, 'overnight_gap': 0.00, 'pem': 0.00}

        # Layer 2: Performance adjustment
        dip_exp = self.tracker.get_expectancy('dip_bounce')
        overnight_exp = self.tracker.get_expectancy('overnight_gap')

        if dip_exp > overnight_exp * 1.5 and base['dip_bounce'] > 0:
            base['dip_bounce'] = min(0.70, base['dip_bounce'] + 0.20)
            base['overnight_gap'] = max(0.20, base['overnight_gap'] - 0.20)
        elif overnight_exp > dip_exp * 1.5 and base['overnight_gap'] > 0:
            base['dip_bounce'] = max(0.20, base['dip_bounce'] - 0.20)
            base['overnight_gap'] = min(0.70, base['overnight_gap'] + 0.20)

        return base


class SimplifiedBacktest:
    """Simplified backtest with clean signal generation"""

    def __init__(self, start_date: str, end_date: str, capital: float = 5000):
        self.start = pd.to_datetime(start_date)
        self.end = pd.to_datetime(end_date)
        self.initial_capital = capital
        self.capital = capital

        # Load VIX
        logger.info("Loading VIX...")
        vix_ticker = yf.Ticker('^VIX')
        vix_df = vix_ticker.history(start=start_date, end=end_date)
        self.vix_data = vix_df['Close'].to_dict()
        logger.info(f"Loaded {len(self.vix_data)} days of VIX")

        # Load universe
        logger.info("Loading stock universe...")
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
                  'NFLX', 'CRM', 'ADBE', 'QCOM', 'AVGO', 'SNOW', 'NOW',
                  'MU', 'AMAT', 'LRCX', 'KLAC', 'ASML', 'TSM', 'INTC',
                  'ORCL', 'CSCO', 'TXN', 'MRVL', 'ON', 'MPWR'][:20]  # Top 20

        self.universe = {}
        batch = yf.download(symbols, start=start_date, end=end_date,
                           group_by='ticker', progress=False, threads=True)

        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    df = batch
                else:
                    df = batch[symbol]
                if len(df) > 100:
                    self.universe[symbol] = df
            except:
                continue

        logger.info(f"Loaded {len(self.universe)} stocks")

        # Costs
        self.COST_PCT = 0.3  # 0.2% slippage + 0.1% commission

    def get_vix(self, date) -> float:
        date = pd.Timestamp(date.date())
        for key in sorted(self.vix_data.keys(), reverse=True):
            if pd.Timestamp(key.date()) <= date:
                return float(self.vix_data[key])
        return 20.0

    def scan_dip_bounce(self, data_snapshot: Dict, date) -> List[Dict]:
        """Simplified dip bounce scanner"""
        signals = []

        for symbol, df in data_snapshot.items():
            if len(df) < 50:
                continue

            close = df['Close'].values
            high = df['High'].values
            low = df['Low'].values
            volume = df['Volume'].values

            current = float(close[-1])
            sma20 = np.mean(close[-20:])
            sma50 = np.mean(close[-50:])

            # Dip bounce criteria
            dip_from_high = ((current / np.max(high[-10:])) - 1) * 100
            above_sma50 = current > sma50

            vol_ratio = volume[-1] / np.mean(volume[-20:])

            # Score
            score = 0
            if -5 < dip_from_high < -1:  # Dipped 1-5%
                score += 30
            if above_sma50:
                score += 20
            if vol_ratio > 1.2:
                score += 15
            if current > sma20:
                score += 15

            if score >= 60:
                # Calculate ATR
                tr = []
                for i in range(-14, 0):
                    h, l, c = high[i], low[i], close[i-1]
                    tr.append(max(h-l, abs(h-c), abs(l-c)))
                atr_pct = (np.mean(tr) / current) * 100

                signals.append({
                    'symbol': symbol,
                    'strategy': 'dip_bounce',
                    'score': score,
                    'entry_price': current,
                    'sl_pct': 3.5,
                    'tp_pct': 10.0,
                    'hold_days': 7
                })

        return sorted(signals, key=lambda x: x['score'], reverse=True)[:3]

    def scan_overnight_gap(self, data_snapshot: Dict, date) -> List[Dict]:
        """Simplified overnight gap scanner"""
        signals = []

        for symbol, df in data_snapshot.items():
            if len(df) < 25:
                continue

            close = df['Close'].values
            high = df['High'].values
            volume = df['Volume'].values

            current = float(close[-1])
            day_high = float(high[-1])

            # Close near high
            close_to_high = (current / day_high) * 100
            if close_to_high < 97:
                continue

            # Volume
            vol_ratio = volume[-1] / np.mean(volume[-20:])
            if vol_ratio < 1.2:
                continue

            # Positive day
            if close[-1] <= close[-2]:
                continue

            score = 70
            if close_to_high > 99:
                score += 15
            if vol_ratio > 1.5:
                score += 10

            signals.append({
                'symbol': symbol,
                'strategy': 'overnight_gap',
                'score': score,
                'entry_price': current,
                'sl_pct': 1.5,
                'tp_pct': 3.0,
                'hold_days': 1
            })

        return sorted(signals, key=lambda x: x['score'], reverse=True)[:2]

    def run(self, use_dynamic: bool = True) -> Dict:
        """Run backtest"""
        mode = "Dynamic" if use_dynamic else "Fixed"
        logger.info(f"\n{'='*60}")
        logger.info(f"Running {mode} Allocation Backtest")
        logger.info(f"{'='*60}")

        allocator = DynamicAllocator(self.initial_capital)
        capital = self.initial_capital
        positions = {}
        trades = []
        daily_log = []

        current = self.start
        while current <= self.end:
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            # Get data up to this date
            data_snapshot = {}
            for symbol, df in self.universe.items():
                df_until = df[df.index <= current]
                if len(df_until) >= 50:
                    data_snapshot[symbol] = df_until

            if not data_snapshot:
                current += timedelta(days=1)
                continue

            vix = self.get_vix(current)
            allocation = allocator.get_allocation(vix, use_dynamic)

            # Update positions
            for symbol in list(positions.keys()):
                pos = positions[symbol]
                pos['days_held'] += 1

                df = data_snapshot.get(symbol)
                if df is None or len(df) == 0:
                    continue

                curr_price = float(df['Close'].iloc[-1])
                high_price = float(df['High'].iloc[-1])
                low_price = float(df['Low'].iloc[-1])

                # Check exits
                exit_reason = None
                exit_price = curr_price

                if low_price <= pos['sl_price']:
                    exit_reason = 'SL'
                    exit_price = pos['sl_price'] * (1 - self.COST_PCT/100)
                elif high_price >= pos['tp_price']:
                    exit_reason = 'TP'
                    exit_price = pos['tp_price'] * (1 - self.COST_PCT/100)
                elif pos['days_held'] >= pos['hold_days']:
                    exit_reason = 'TIME'
                    exit_price = curr_price * (1 - self.COST_PCT/100)

                if exit_reason:
                    proceeds = pos['qty'] * exit_price
                    cost = pos['qty'] * pos['entry_price']
                    pnl_usd = proceeds - cost
                    pnl_pct = (pnl_usd / cost) * 100

                    capital += proceeds

                    trades.append({
                        'date': current,
                        'symbol': symbol,
                        'strategy': pos['strategy'],
                        'pnl_pct': pnl_pct,
                        'pnl_usd': pnl_usd,
                        'exit_reason': exit_reason
                    })

                    allocator.tracker.add_trade(pos['strategy'], pnl_pct)
                    del positions[symbol]

            # Scan for new signals
            if len(positions) < 4:
                all_signals = []

                if allocation['dip_bounce'] > 0:
                    dip_signals = self.scan_dip_bounce(data_snapshot, current)
                    for sig in dip_signals:
                        sig['allocation'] = allocation['dip_bounce']
                        all_signals.append(sig)

                if allocation['overnight_gap'] > 0:
                    overnight_signals = self.scan_overnight_gap(data_snapshot, current)
                    for sig in overnight_signals:
                        sig['allocation'] = allocation['overnight_gap']
                        all_signals.append(sig)

                # Execute signals
                for signal in all_signals:
                    if len(positions) >= 4:
                        break
                    if signal['symbol'] in positions:
                        continue

                    position_value = capital * signal['allocation']
                    if position_value < 100:
                        continue

                    entry_price = signal['entry_price'] * (1 + self.COST_PCT/100)
                    qty = int(position_value / entry_price)
                    if qty == 0:
                        continue

                    cost = qty * entry_price
                    if cost > capital * 0.9:
                        continue

                    positions[signal['symbol']] = {
                        'symbol': signal['symbol'],
                        'strategy': signal['strategy'],
                        'entry_price': entry_price,
                        'qty': qty,
                        'days_held': 0,
                        'sl_price': entry_price * (1 - signal['sl_pct']/100),
                        'tp_price': entry_price * (1 + signal['tp_pct']/100),
                        'hold_days': signal['hold_days']
                    }

                    capital -= cost

            daily_log.append({
                'date': current,
                'capital': capital,
                'positions': len(positions),
                'vix': vix
            })

            current += timedelta(days=1)

        # Close remaining
        for symbol, pos in positions.items():
            final_price = float(self.universe[symbol]['Close'].iloc[-1])
            proceeds = pos['qty'] * final_price * (1 - self.COST_PCT/100)
            cost = pos['qty'] * pos['entry_price']
            pnl_usd = proceeds - cost
            pnl_pct = (pnl_usd / cost) * 100

            capital += proceeds
            trades.append({
                'date': self.end,
                'symbol': symbol,
                'strategy': pos['strategy'],
                'pnl_pct': pnl_pct,
                'pnl_usd': pnl_usd,
                'exit_reason': 'FINAL'
            })

        return self._calculate_results(mode, trades, daily_log, capital)

    def _calculate_results(self, mode: str, trades: List, daily_log: List, final_capital: float) -> Dict:
        if not trades:
            logger.warning("No trades!")
            return None

        df = pd.DataFrame(trades)

        total_months = (self.end - self.start).days / 30.44
        total_return = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        monthly_return = (final_capital / self.initial_capital) ** (1 / total_months) - 1
        cagr = ((final_capital / self.initial_capital) ** (12 / total_months) - 1) * 100

        winners = df[df['pnl_pct'] > 0]
        losers = df[df['pnl_pct'] <= 0]
        win_rate = len(winners) / len(df) * 100

        avg_winner = winners['pnl_pct'].mean() if len(winners) > 0 else 0
        avg_loser = losers['pnl_pct'].mean() if len(losers) > 0 else 0

        # Max DD
        df_daily = pd.DataFrame(daily_log)
        df_daily['peak'] = df_daily['capital'].cummax()
        df_daily['dd'] = (df_daily['capital'] - df_daily['peak']) / df_daily['peak'] * 100
        max_dd = df_daily['dd'].min()

        avg_monthly_usd = (final_capital - self.initial_capital) / total_months

        results = {
            'mode': mode,
            'total_trades': len(df),
            'trades_per_month': len(df) / total_months,
            'win_rate': win_rate,
            'avg_winner': avg_winner,
            'avg_loser': avg_loser,
            'total_return': total_return,
            'cagr': cagr,
            'monthly_pct': monthly_return * 100,
            'monthly_usd': avg_monthly_usd,
            'max_dd': max_dd,
            'final_capital': final_capital
        }

        logger.info(f"\n📊 {mode} Results:")
        logger.info(f"Trades: {len(df)} ({len(df)/total_months:.1f}/month)")
        logger.info(f"Win Rate: {win_rate:.1f}%")
        logger.info(f"Avg Winner: +{avg_winner:.2f}%")
        logger.info(f"Avg Loser: {avg_loser:.2f}%")
        logger.info(f"CAGR: {cagr:.1f}%")
        logger.info(f"Monthly: ${avg_monthly_usd:.0f} ({monthly_return*100:.1f}%)")
        logger.info(f"Max DD: {max_dd:.1f}%")
        logger.info(f"Final: ${final_capital:,.0f}")

        # Strategy breakdown
        logger.info("\nStrategy Breakdown:")
        for strat in ['dip_bounce', 'overnight_gap']:
            strat_df = df[df['strategy'] == strat]
            if len(strat_df) > 0:
                strat_wr = len(strat_df[strat_df['pnl_pct'] > 0]) / len(strat_df) * 100
                strat_pnl = strat_df['pnl_usd'].sum()
                logger.info(f"  {strat}: {len(strat_df)} trades, {strat_wr:.1f}% WR, ${strat_pnl:.0f} P&L")

        return results


def main():
    logger.info("="*80)
    logger.info("SIMPLIFIED DYNAMIC ALLOCATION BACKTEST")
    logger.info("="*80)
    logger.info("Period: 2023-2025 (3 years)")
    logger.info("Capital: $5,000")
    logger.info("Costs: 0.3% per trade\n")

    bt = SimplifiedBacktest('2023-01-01', '2025-12-31', 5000)

    results = {}
    results['fixed'] = bt.run(use_dynamic=False)

    # Reset for dynamic
    bt.capital = bt.initial_capital
    results['dynamic'] = bt.run(use_dynamic=True)

    # Comparison
    if results['fixed'] and results['dynamic']:
        logger.info("\n" + "="*80)
        logger.info("COMPARISON")
        logger.info("="*80)

        comparison = pd.DataFrame([
            {
                'Mode': r['mode'],
                'Trades/mo': f"{r['trades_per_month']:.1f}",
                'Win%': f"{r['win_rate']:.1f}%",
                'CAGR': f"{r['cagr']:.1f}%",
                'Monthly$': f"${r['monthly_usd']:.0f}",
                'Monthly%': f"{r['monthly_pct']:.1f}%",
                'MaxDD': f"{r['max_dd']:.1f}%",
                'Final$': f"${r['final_capital']:,.0f}"
            }
            for r in [results['fixed'], results['dynamic']]
        ])

        print("\n" + comparison.to_string(index=False))

        # Check target
        target = 6.0
        logger.info(f"\n🎯 Target: {target}% monthly")
        for r in [results['fixed'], results['dynamic']]:
            status = "✅" if r['monthly_pct'] >= target else "❌"
            diff = r['monthly_pct'] - target
            logger.info(f"{status} {r['mode']}: {r['monthly_pct']:.1f}% ({diff:+.1f}%)")

    logger.info("\n" + "="*80)
    logger.info("Backtest Complete!")
    logger.info("="*80)

    return results


if __name__ == '__main__':
    results = main()
