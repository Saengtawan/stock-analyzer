#!/usr/bin/env python3
"""
BACKTEST 12-STEP SYSTEM

Simulate the complete 12-step analysis process over historical data:
1. Global Macro (VIX check)
2. Market Sentiment (SPY momentum)
3. Economic Cycle (sector leadership)
4. Sector Rotation (pick best sectors)
5. Theme/Trend (momentum leaders)
6. Stock Filtering (quality filters)
7. Catalyst Check (breakout, volume surge)
8. Technical Analysis (trend, RSI)
9. Entry Timing (pullback vs breakout)
10. Position Sizing (risk-based)
11. Execution
12. Position Management (stop, target, trail)
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')


class TwelveStepBacktester:
    """Backtest the 12-step analysis system"""

    def __init__(self,
                 start_date: str = '2024-01-01',
                 end_date: str = '2025-12-31',
                 initial_capital: float = 100000,
                 max_positions: int = 5,
                 max_risk_per_trade: float = 0.015,  # 1.5%
                 max_position_pct: float = 0.15,  # 15%
                 stop_loss_pct: float = 0.03,  # 3%
                 target_pct: float = 0.08,  # 8%
                 ):

        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.max_risk_per_trade = max_risk_per_trade
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.target_pct = target_pct

        self.db_path = DB_PATH

    def run_backtest(self) -> Dict:
        """Run the complete backtest"""
        print("="*70)
        print("🎯 BACKTEST: 12-STEP ANALYSIS SYSTEM")
        print("="*70)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Max Positions: {self.max_positions}")
        print(f"Risk per Trade: {self.max_risk_per_trade*100:.1f}%")
        print(f"Stop Loss: {self.stop_loss_pct*100:.1f}%")
        print(f"Target: {self.target_pct*100:.1f}%")
        print("="*70)

        conn = sqlite3.connect(self.db_path)

        # Get all trading dates
        cursor = conn.execute("""
            SELECT DISTINCT date FROM stock_prices
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """, (self.start_date, self.end_date))
        dates = [row[0] for row in cursor.fetchall()]

        print(f"\nTrading days: {len(dates)}")

        # Load VIX data for macro check
        vix_data = self._load_indicator_data(conn, 'VIX')
        spy_data = self._load_indicator_data(conn, 'SPY')

        # Load all stock data
        print("Loading stock data...")
        stock_data = self._load_all_stock_data(conn)
        print(f"Stocks loaded: {len(stock_data)}")

        # Sector mapping
        sector_stocks = self._get_sector_stocks(conn)

        # Initialize portfolio
        portfolio = {
            'cash': self.initial_capital,
            'positions': [],
            'history': [],
            'equity_curve': [],
        }

        monthly_pnl = {}
        step_stats = {i: {'triggered': 0, 'blocked': 0} for i in range(1, 13)}

        # Main backtest loop
        for i, date in enumerate(dates):
            if i < 60:  # Need lookback
                continue

            # Calculate current portfolio value
            total_value = portfolio['cash']
            for pos in portfolio['positions']:
                if pos['symbol'] in stock_data and date in stock_data[pos['symbol']].index:
                    total_value += stock_data[pos['symbol']].loc[date, 'close'] * pos['shares']

            portfolio['equity_curve'].append({'date': date, 'value': total_value})

            # ===============================================
            # STEP 1: GLOBAL MACRO CHECK
            # ===============================================
            vix = self._get_value(vix_data, date, 'close', 20)

            if vix > 25:
                step_stats[1]['blocked'] += 1
                continue  # Skip trading when VIX > 25
            step_stats[1]['triggered'] += 1

            # ===============================================
            # STEP 2: MARKET SENTIMENT
            # ===============================================
            spy_mom_5d = self._get_momentum(spy_data, date, 5)
            spy_mom_20d = self._get_momentum(spy_data, date, 20)

            sentiment_score = 50
            if spy_mom_5d > 1:
                sentiment_score += 15
            elif spy_mom_5d < -1:
                sentiment_score -= 15
            if spy_mom_20d > 3:
                sentiment_score += 10
            elif spy_mom_20d < -3:
                sentiment_score -= 10

            if sentiment_score < 35:
                step_stats[2]['blocked'] += 1
                continue  # Skip when sentiment is fearful
            step_stats[2]['triggered'] += 1

            # ===============================================
            # STEP 3 & 4: ECONOMIC CYCLE & SECTOR ROTATION
            # ===============================================
            # Determine best sectors based on recent performance
            sector_momentum = {}
            for sector, symbols in sector_stocks.items():
                momentums = []
                for symbol in symbols[:5]:  # Sample 5 per sector
                    if symbol in stock_data:
                        mom = self._get_momentum(stock_data[symbol], date, 20)
                        if mom is not None:
                            momentums.append(mom)
                if momentums:
                    sector_momentum[sector] = np.mean(momentums)

            if not sector_momentum:
                step_stats[3]['blocked'] += 1
                continue

            # Get top 3 sectors
            top_sectors = sorted(sector_momentum.items(), key=lambda x: x[1], reverse=True)[:3]
            top_sector_names = [s[0] for s in top_sectors]
            step_stats[3]['triggered'] += 1
            step_stats[4]['triggered'] += 1

            # ===============================================
            # MANAGE EXISTING POSITIONS
            # ===============================================
            for pos in portfolio['positions'][:]:
                if pos['symbol'] not in stock_data:
                    continue

                df = stock_data[pos['symbol']]
                if date not in df.index:
                    continue

                current_price = df.loc[date, 'close']
                high_price = df.loc[date, 'high']
                pnl_pct = (current_price / pos['entry_price']) - 1

                # Update highest price for trailing stop
                if current_price > pos.get('highest_price', pos['entry_price']):
                    pos['highest_price'] = current_price

                exit_reason = None

                # STEP 12: Position Management Rules

                # Rule 1: Stop Loss
                if pnl_pct <= -self.stop_loss_pct:
                    exit_reason = 'STOP'

                # Rule 2: Target Hit
                elif pnl_pct >= self.target_pct:
                    exit_reason = 'TARGET'

                # Rule 3: Trailing Stop (after +3% profit)
                elif pos['highest_price'] > pos['entry_price'] * 1.03:
                    trail_stop = pos['highest_price'] * 0.975  # -2.5% from high
                    if current_price < trail_stop:
                        exit_reason = 'TRAIL'

                # Rule 4: Time Stop (10 days max hold)
                elif pos['days_held'] >= 10:
                    exit_reason = 'TIME'

                # Rule 5: Thesis Broken (sector no longer top)
                elif pos['sector'] not in top_sector_names and pos['days_held'] >= 3:
                    exit_reason = 'SECTOR_ROTATE'

                if exit_reason:
                    pnl = (current_price - pos['entry_price']) * pos['shares']

                    trade = {
                        'symbol': pos['symbol'],
                        'sector': pos['sector'],
                        'entry_date': pos['entry_date'],
                        'exit_date': date,
                        'entry_price': pos['entry_price'],
                        'exit_price': current_price,
                        'shares': pos['shares'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct * 100,
                        'exit_reason': exit_reason,
                        'days_held': pos['days_held'],
                    }
                    portfolio['history'].append(trade)
                    portfolio['cash'] += current_price * pos['shares']
                    portfolio['positions'].remove(pos)

                    # Track monthly
                    month = date[:7]
                    if month not in monthly_pnl:
                        monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
                    monthly_pnl[month]['pnl'] += pnl
                    monthly_pnl[month]['trades'] += 1
                    if pnl > 0:
                        monthly_pnl[month]['wins'] += 1

                    step_stats[12]['triggered'] += 1
                else:
                    pos['days_held'] += 1

            # ===============================================
            # LOOK FOR NEW ENTRIES (Weekly)
            # ===============================================
            if i % 5 != 0:  # Only scan weekly
                continue

            if len(portfolio['positions']) >= self.max_positions:
                continue

            # ===============================================
            # STEPS 5-9: Find and Score Candidates
            # ===============================================
            candidates = []

            for sector in top_sector_names:
                symbols = sector_stocks.get(sector, [])

                for symbol in symbols:
                    if symbol not in stock_data:
                        continue

                    # Skip if already in portfolio
                    if any(p['symbol'] == symbol for p in portfolio['positions']):
                        continue

                    df = stock_data[symbol]
                    if date not in df.index:
                        continue

                    idx = df.index.get_loc(date)
                    if idx < 60:
                        continue

                    closes = df['close'].values[idx-60:idx+1]
                    highs = df['high'].values[idx-60:idx+1]
                    lows = df['low'].values[idx-60:idx+1]
                    volumes = df['volume'].values[idx-60:idx+1]

                    price = closes[-1]

                    # STEP 6: Stock Filtering
                    if price < 10:
                        continue

                    mom_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0
                    mom_20d = (closes[-1] / closes[-20] - 1) * 100 if closes[-20] > 0 else 0

                    # ATR%
                    tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                          for i in range(-14, 0)]
                    atr_pct = (np.mean(tr) / price) * 100

                    if atr_pct > 2.5:  # Too volatile
                        continue

                    # MA20
                    ma20 = np.mean(closes[-20:])
                    if price < ma20:  # Below MA20
                        continue

                    # RSI
                    deltas = np.diff(closes[-15:])
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    rsi = 100 - (100 / (1 + np.mean(gains) / np.mean(losses))) if np.mean(losses) > 0 else 50

                    if rsi > 70:  # Overbought
                        continue

                    # Momentum filter
                    if mom_5d < 1 or mom_5d > 10:
                        continue

                    step_stats[6]['triggered'] += 1

                    # STEP 7: Catalyst Check
                    catalyst_score = 0
                    catalysts = []

                    # Volume surge
                    vol_avg = np.mean(volumes[-20:-1])
                    vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1
                    if vol_ratio > 1.5:
                        catalyst_score += 15
                        catalysts.append('VOLUME')

                    # Breakout
                    recent_high = max(closes[-20:-1])
                    if closes[-1] > recent_high:
                        catalyst_score += 20
                        catalysts.append('BREAKOUT')

                    # Near 52W high
                    high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
                    if closes[-1] / high_52w > 0.95:
                        catalyst_score += 10
                        catalysts.append('52W_HIGH')

                    # Gap up
                    if idx > 0:
                        prev_close = df['close'].values[idx-1]
                        gap = (df['open'].values[idx] / prev_close - 1) * 100
                        if gap > 2:
                            catalyst_score += 10
                            catalysts.append('GAP')

                    if catalyst_score < 15:  # No catalyst
                        step_stats[7]['blocked'] += 1
                        continue
                    step_stats[7]['triggered'] += 1

                    # STEP 8: Technical Score
                    tech_score = 0

                    # Trend
                    ma50 = np.mean(closes[-50:]) if len(closes) >= 50 else ma20
                    if price > ma20 > ma50:
                        tech_score += 30
                    elif price > ma20:
                        tech_score += 15

                    # RSI
                    if 40 < rsi < 60:
                        tech_score += 20
                    elif 35 < rsi < 65:
                        tech_score += 10

                    # Volume
                    if vol_ratio > 1:
                        tech_score += 15

                    if tech_score < 30:
                        step_stats[8]['blocked'] += 1
                        continue
                    step_stats[8]['triggered'] += 1

                    # STEP 9: Entry Strategy
                    above_ma = (price / ma20 - 1) * 100
                    if above_ma > 5:
                        entry_strategy = 'WAIT'  # Too extended
                        continue
                    elif above_ma > 2:
                        entry_strategy = 'PULLBACK'
                    else:
                        entry_strategy = 'NOW'

                    step_stats[9]['triggered'] += 1

                    # Total score
                    total_score = catalyst_score + tech_score + (sector_momentum.get(sector, 0) * 2)

                    candidates.append({
                        'symbol': symbol,
                        'sector': sector,
                        'price': price,
                        'score': total_score,
                        'catalyst_score': catalyst_score,
                        'tech_score': tech_score,
                        'catalysts': catalysts,
                        'atr_pct': atr_pct,
                        'rsi': rsi,
                        'entry_strategy': entry_strategy,
                    })

            # Sort by score
            candidates.sort(key=lambda x: x['score'], reverse=True)

            # STEP 10: Position Sizing
            for cand in candidates[:self.max_positions - len(portfolio['positions'])]:
                entry_price = cand['price']
                stop_price = entry_price * (1 - self.stop_loss_pct)
                risk_per_share = entry_price - stop_price

                # Risk-based sizing
                max_risk_amount = total_value * self.max_risk_per_trade
                shares_by_risk = int(max_risk_amount / risk_per_share) if risk_per_share > 0 else 0

                # Position limit
                max_pos_value = total_value * self.max_position_pct
                shares_by_position = int(max_pos_value / entry_price)

                shares = min(shares_by_risk, shares_by_position)

                if shares > 0 and portfolio['cash'] >= entry_price * shares:
                    step_stats[10]['triggered'] += 1

                    # STEP 11: Execute
                    portfolio['positions'].append({
                        'symbol': cand['symbol'],
                        'sector': cand['sector'],
                        'entry_date': date,
                        'entry_price': entry_price,
                        'shares': shares,
                        'days_held': 0,
                        'highest_price': entry_price,
                        'catalysts': cand['catalysts'],
                        'score': cand['score'],
                    })
                    portfolio['cash'] -= entry_price * shares

                    step_stats[11]['triggered'] += 1

        conn.close()

        # ===============================================
        # CALCULATE RESULTS
        # ===============================================
        return self._calculate_results(portfolio, monthly_pnl, step_stats)

    def _load_indicator_data(self, conn, symbol: str) -> pd.DataFrame:
        """Load indicator data (VIX, SPY, etc.)"""
        df = pd.read_sql("""
            SELECT date, close, high, low, volume FROM stock_prices
            WHERE symbol = ?
            ORDER BY date
        """, conn, params=(symbol,))
        if len(df) > 0:
            df.set_index('date', inplace=True)
        return df

    def _load_all_stock_data(self, conn) -> Dict[str, pd.DataFrame]:
        """Load all stock data"""
        cursor = conn.execute("""
            SELECT DISTINCT symbol FROM stock_prices
            WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
        """)
        symbols = [row[0] for row in cursor.fetchall()]

        stock_data = {}
        for symbol in symbols:
            df = pd.read_sql("""
                SELECT date, open, high, low, close, volume FROM stock_prices
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date
            """, conn, params=(symbol, self.start_date, self.end_date))
            if len(df) >= 30:
                df.set_index('date', inplace=True)
                stock_data[symbol] = df

        return stock_data

    def _get_sector_stocks(self, conn) -> Dict[str, List[str]]:
        """Get stocks by sector"""
        cursor = conn.execute("""
            SELECT DISTINCT symbol, sector FROM stock_prices
            WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
        """)

        sector_stocks = {}
        for row in cursor.fetchall():
            symbol, sector = row
            if sector not in sector_stocks:
                sector_stocks[sector] = []
            sector_stocks[sector].append(symbol)

        return sector_stocks

    def _get_value(self, df: pd.DataFrame, date: str, column: str, default: float) -> float:
        """Get value from dataframe"""
        if df is None or df.empty:
            return default
        if date in df.index:
            return df.loc[date, column]
        # Get closest date before
        valid_dates = [d for d in df.index if d <= date]
        if valid_dates:
            return df.loc[valid_dates[-1], column]
        return default

    def _get_momentum(self, df: pd.DataFrame, date: str, lookback: int) -> float:
        """Calculate momentum"""
        if df is None or df.empty:
            return None
        if date not in df.index:
            return None
        idx = df.index.get_loc(date)
        if idx < lookback:
            return None
        current = df['close'].iloc[idx]
        past = df['close'].iloc[idx - lookback]
        return (current / past - 1) * 100 if past > 0 else 0

    def _calculate_results(self, portfolio: Dict, monthly_pnl: Dict, step_stats: Dict) -> Dict:
        """Calculate and print results"""
        trades = portfolio['history']

        if not trades:
            print("No trades executed")
            return None

        total_pnl = sum(t['pnl'] for t in trades)
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]

        win_rate = len(wins) / len(trades) * 100
        avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
        ev = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

        # Exit reason breakdown
        exit_reasons = {}
        for t in trades:
            r = t['exit_reason']
            if r not in exit_reasons:
                exit_reasons[r] = {'count': 0, 'pnl': 0, 'wins': 0}
            exit_reasons[r]['count'] += 1
            exit_reasons[r]['pnl'] += t['pnl']
            if t['pnl'] > 0:
                exit_reasons[r]['wins'] += 1

        # Print results
        print("\n" + "="*70)
        print("📊 BACKTEST RESULTS: 12-STEP SYSTEM")
        print("="*70)
        print(f"Total Trades: {len(trades)}")
        print(f"Winners: {len(wins)} ({win_rate:.1f}%)")
        print(f"Losers: {len(losses)}")
        print(f"Total P&L: ${total_pnl:+,.2f} ({total_pnl/self.initial_capital*100:+.1f}%)")
        print(f"Average Win: {avg_win:+.2f}%")
        print(f"Average Loss: {avg_loss:+.2f}%")
        print(f"Expected Value: {ev:+.2f}% per trade")

        # Step statistics
        print("\n" + "="*70)
        print("📋 STEP STATISTICS")
        print("="*70)
        print(f"{'Step':<5} {'Name':<25} {'Triggered':>10} {'Blocked':>10}")
        print("-"*55)

        step_names = {
            1: 'Global Macro (VIX)',
            2: 'Market Sentiment',
            3: 'Economic Cycle',
            4: 'Sector Rotation',
            5: 'Theme/Trend',
            6: 'Stock Filtering',
            7: 'Catalyst Check',
            8: 'Technical Analysis',
            9: 'Entry Timing',
            10: 'Position Sizing',
            11: 'Execution',
            12: 'Position Management',
        }

        for step, stats in step_stats.items():
            name = step_names.get(step, f'Step {step}')
            print(f"{step:<5} {name:<25} {stats['triggered']:>10} {stats['blocked']:>10}")

        # Exit reason breakdown
        print("\n" + "="*70)
        print("📋 EXIT REASON BREAKDOWN")
        print("="*70)
        print(f"{'Reason':<15} {'Count':>8} {'Win Rate':>10} {'P&L':>15}")
        print("-"*55)

        for reason in sorted(exit_reasons.keys()):
            data = exit_reasons[reason]
            wr = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
            print(f"{reason:<15} {data['count']:>8} {wr:>9.0f}% ${data['pnl']:>14,.2f}")

        # Monthly summary
        print("\n" + "="*70)
        print("📋 MONTHLY SUMMARY")
        print("="*70)
        print(f"{'Month':<10} {'Trades':>8} {'P&L':>15} {'Monthly %':>10} {'Win Rate':>10}")
        print("-"*60)

        positive_months = 0
        monthly_returns = []

        for month in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            pnl_pct = (data['pnl'] / self.initial_capital) * 100
            monthly_returns.append(pnl_pct)
            print(f"{month:<10} {data['trades']:>8} ${data['pnl']:>14,.2f} {pnl_pct:>+9.1f}% {wr:>9.0f}%")
            if data['pnl'] > 0:
                positive_months += 1

        print("-"*60)
        avg_monthly = np.mean(monthly_returns) if monthly_returns else 0
        max_monthly = max(monthly_returns) if monthly_returns else 0
        min_monthly = min(monthly_returns) if monthly_returns else 0

        print(f"Average Monthly: {avg_monthly:+.2f}%")
        print(f"Best Month: {max_monthly:+.2f}%")
        print(f"Worst Month: {min_monthly:+.2f}%")
        print(f"Positive Months: {positive_months}/{len(monthly_pnl)} ({positive_months/len(monthly_pnl)*100:.0f}%)")

        # Final summary
        final_value = self.initial_capital + total_pnl
        total_return = (final_value / self.initial_capital - 1) * 100

        print("\n" + "="*70)
        print("📋 PORTFOLIO SUMMARY")
        print("="*70)
        print(f"Starting Capital: ${self.initial_capital:,.2f}")
        print(f"Ending Value: ${final_value:,.2f}")
        print(f"Total Return: {total_return:+.1f}%")
        print(f"Annualized Return: {total_return/2:+.1f}%")

        # Sector performance
        print("\n" + "="*70)
        print("📋 SECTOR PERFORMANCE")
        print("="*70)

        sector_stats = {}
        for t in trades:
            s = t['sector']
            if s not in sector_stats:
                sector_stats[s] = {'trades': 0, 'wins': 0, 'pnl': 0}
            sector_stats[s]['trades'] += 1
            sector_stats[s]['pnl'] += t['pnl']
            if t['pnl'] > 0:
                sector_stats[s]['wins'] += 1

        print(f"{'Sector':<25} {'Trades':>8} {'Win Rate':>10} {'P&L':>15}")
        print("-"*60)

        for sector in sorted(sector_stats.keys(), key=lambda x: sector_stats[x]['pnl'], reverse=True):
            stats = sector_stats[sector]
            wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
            print(f"{sector[:25]:<25} {stats['trades']:>8} {wr:>9.0f}% ${stats['pnl']:>14,.2f}")

        return {
            'trades': len(trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'expected_value': ev,
            'avg_monthly_pct': avg_monthly,
            'positive_months_pct': positive_months/len(monthly_pnl)*100 if monthly_pnl else 0,
            'total_return': total_return,
            'best_month': max_monthly,
            'worst_month': min_monthly,
            'monthly_pnl': monthly_pnl,
            'exit_reasons': exit_reasons,
            'sector_stats': sector_stats,
        }


def compare_with_simple():
    """Compare 12-step system with simple approach"""
    print("\n\n" + "="*70)
    print("📊 COMPARISON: 12-STEP vs SIMPLE SYSTEM")
    print("="*70)

    # Run 12-step backtest
    print("\n🔵 Running 12-Step System...")
    bt_12step = TwelveStepBacktester()
    result_12step = bt_12step.run_backtest()

    # Simple comparison (from previous backtests)
    simple_result = {
        'win_rate': 47.9,
        'avg_monthly_pct': 0.20,
        'total_return': 4.3,
    }

    if result_12step:
        print("\n\n" + "="*70)
        print("📊 FINAL COMPARISON")
        print("="*70)
        print(f"{'Metric':<25} {'Simple':>15} {'12-Step':>15} {'Improvement':>15}")
        print("-"*70)
        print(f"{'Win Rate':<25} {simple_result['win_rate']:>14.1f}% {result_12step['win_rate']:>14.1f}% {result_12step['win_rate'] - simple_result['win_rate']:>+14.1f}%")
        print(f"{'Avg Monthly Return':<25} {simple_result['avg_monthly_pct']:>+14.2f}% {result_12step['avg_monthly_pct']:>+14.2f}% {result_12step['avg_monthly_pct'] - simple_result['avg_monthly_pct']:>+14.2f}%")
        print(f"{'Total Return (2yr)':<25} {simple_result['total_return']:>+14.1f}% {result_12step['total_return']:>+14.1f}% {result_12step['total_return'] - simple_result['total_return']:>+14.1f}%")


def main():
    """Main entry point"""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--compare':
        compare_with_simple()
    else:
        bt = TwelveStepBacktester()
        result = bt.run_backtest()


if __name__ == '__main__':
    main()
