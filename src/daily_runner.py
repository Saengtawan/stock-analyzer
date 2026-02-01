#!/usr/bin/env python3
"""
DAILY RUNNER - ระบบอัตโนมัติ 24/7

Features:
1. อัพเดตราคาหุ้นทุกวัน
2. สแกนหาโอกาสใหม่
3. อัพเดตพอร์ต / ตรวจ stop-loss, target
4. ส่งรายงานสรุปประจำวัน
5. รันได้ทั้งวัน (schedule ได้)

Usage:
    python src/daily_runner.py              # Run once
    python src/daily_runner.py --schedule   # Run scheduled (every day)
    python src/daily_runner.py --backtest   # Run comprehensive backtest
"""

import os
import sys
import json
import time
import schedule
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    import yfinance as yf
except ImportError:
    yf = None

from portfolio_system import PortfolioManager, StockScanner

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
LOG_DIR = os.path.join(DATA_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


class DailyRunner:
    """Daily automation runner"""

    def __init__(self):
        self.db_path = os.path.join(DATA_DIR, 'database', 'stocks.db')
        self.pm = PortfolioManager()
        self.scanner = StockScanner(self.db_path)
        self.log_file = os.path.join(LOG_DIR, f"daily_{datetime.now().strftime('%Y%m%d')}.log")

    def log(self, message: str):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        with open(self.log_file, 'a') as f:
            f.write(log_msg + '\n')

    def update_prices(self):
        """Update stock prices in database"""
        self.log("="*60)
        self.log("UPDATING STOCK PRICES")
        self.log("="*60)

        if yf is None:
            self.log("yfinance not available")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT DISTINCT symbol, sector FROM stock_prices")
        symbols = [(row[0], row[1]) for row in cursor.fetchall()]

        # Get last date in DB
        cursor = conn.execute("SELECT MAX(date) FROM stock_prices")
        last_date = cursor.fetchone()[0]

        self.log(f"Total symbols: {len(symbols)}")
        self.log(f"Last data date: {last_date}")

        # Only update if market was open today
        today = datetime.now().strftime('%Y-%m-%d')
        if today <= last_date:
            self.log("Database already up to date")
            conn.close()
            return

        updated = 0
        failed = 0

        for symbol, sector in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=last_date, end=today)

                if len(hist) > 0:
                    for date, row in hist.iterrows():
                        date_str = date.strftime('%Y-%m-%d')
                        if date_str > last_date:
                            conn.execute("""
                                INSERT OR REPLACE INTO stock_prices
                                (symbol, date, open, high, low, close, volume, sector)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (symbol, date_str, row['Open'], row['High'],
                                  row['Low'], row['Close'], int(row['Volume']), sector))
                            updated += 1
            except Exception as e:
                failed += 1

        conn.commit()
        conn.close()

        self.log(f"Updated: {updated} records, Failed: {failed}")

    def run_scanner(self) -> List[Dict]:
        """Run opportunity scanner"""
        self.log("="*60)
        self.log("RUNNING SCANNER")
        self.log("="*60)

        opportunities = self.scanner.scan_for_opportunities(top_n=10)

        # Log opportunities
        for opp in opportunities:
            self.log(f"  {opp['symbol']}: ${opp['price']:.2f} (Score: {opp['score']:.0f})")

        return opportunities

    def update_portfolio(self):
        """Update portfolio and check alerts"""
        self.log("="*60)
        self.log("UPDATING PORTFOLIO")
        self.log("="*60)

        alerts = self.pm.update_prices()

        # Log alerts
        for alert in alerts:
            self.log(f"ALERT: {alert['message']}")

        return alerts

    def generate_report(self) -> Dict:
        """Generate daily report"""
        self.log("="*60)
        self.log("GENERATING DAILY REPORT")
        self.log("="*60)

        summary = self.pm.get_summary()
        monthly = self.pm.get_monthly_summary()

        report = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'portfolio': summary,
            'monthly': monthly,
        }

        # Log summary
        self.log(f"Open Positions: {summary['open_positions']}")
        self.log(f"Open P&L: ${summary['total_open_pnl']:+,.2f}")
        self.log(f"Total Value: ${summary['total_value']:,.2f}")
        self.log(f"Win Rate: {summary['win_rate']:.1f}%")

        # Save report
        report_file = os.path.join(LOG_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.json")
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        return report

    def run_daily_job(self):
        """Run all daily tasks"""
        self.log("\n" + "="*70)
        self.log("STARTING DAILY JOB")
        self.log("="*70)

        start_time = time.time()

        # 1. Update prices
        self.update_prices()

        # 2. Update portfolio
        alerts = self.update_portfolio()

        # 3. Scan for opportunities
        opportunities = self.run_scanner()

        # 4. Generate report
        report = self.generate_report()

        elapsed = time.time() - start_time
        self.log(f"\nDaily job completed in {elapsed:.1f} seconds")

        return {
            'alerts': alerts,
            'opportunities': opportunities,
            'report': report,
        }

    def run_scheduled(self, run_time: str = "06:00"):
        """Run scheduled job (every day at specified time)"""
        self.log(f"Scheduler started. Running daily at {run_time}")

        schedule.every().day.at(run_time).do(self.run_daily_job)

        # Also run immediately on start
        self.run_daily_job()

        while True:
            schedule.run_pending()
            time.sleep(60)


class ComprehensiveBacktester:
    """Comprehensive backtester for the full 710-stock universe"""

    def __init__(self):
        self.db_path = os.path.join(DATA_DIR, 'database', 'stocks.db')
        self.results = []

    def run_backtest(self, start_date: str = '2024-01-01', end_date: str = '2025-12-31',
                     stop_loss: float = -0.03, target_profit: float = 0.06,
                     max_positions: int = 5, position_size: float = 10000):
        """Run comprehensive backtest"""
        print("="*70)
        print("COMPREHENSIVE BACKTEST - 710 Stock Universe")
        print("="*70)
        print(f"Period: {start_date} to {end_date}")
        print(f"Stop Loss: {stop_loss*100:.1f}%")
        print(f"Target: {target_profit*100:.1f}%")
        print(f"Max Positions: {max_positions}")
        print(f"Position Size: ${position_size:,.0f}")
        print("="*70)

        conn = sqlite3.connect(self.db_path)

        # Get all trading dates
        cursor = conn.execute("""
            SELECT DISTINCT date FROM stock_prices
            WHERE date >= ? AND date <= ?
            ORDER BY date
        """, (start_date, end_date))
        dates = [row[0] for row in cursor.fetchall()]

        print(f"\nTrading days: {len(dates)}")

        # Get all symbols and sectors
        cursor = conn.execute("""
            SELECT DISTINCT symbol, sector FROM stock_prices
            WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
        """)
        symbol_sectors = {row[0]: row[1] for row in cursor.fetchall()}
        symbols = list(symbol_sectors.keys())

        print(f"Total symbols: {len(symbols)}")

        # Preload price data
        print("\nLoading price data...")
        price_data = {}
        for symbol in symbols:
            df = pd.read_sql("""
                SELECT date, open, high, low, close, volume FROM stock_prices
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date
            """, conn, params=(symbol, start_date, end_date))
            if len(df) >= 30:
                df.set_index('date', inplace=True)
                price_data[symbol] = df

        print(f"Symbols with data: {len(price_data)}")

        # Initialize
        portfolio = {
            'cash': 100000,
            'positions': [],
            'history': [],
        }

        monthly_pnl = {}

        # Backtest loop
        for i, date in enumerate(dates):
            if i < 30:  # Need 30 days lookback
                continue

            # Check existing positions
            for pos in portfolio['positions'][:]:
                if pos['symbol'] not in price_data:
                    continue

                df = price_data[pos['symbol']]
                if date not in df.index:
                    continue

                current_price = df.loc[date, 'close']
                pnl_pct = (current_price / pos['entry_price']) - 1

                exit_reason = None

                # Check stop loss
                if pnl_pct <= stop_loss:
                    exit_reason = 'STOP'

                # Check target
                elif pnl_pct >= target_profit:
                    exit_reason = 'TARGET'

                # Check max hold (14 days)
                elif pos['days_held'] >= 14:
                    exit_reason = 'TIME'

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
                else:
                    pos['days_held'] += 1

            # Look for new entries (once per week)
            if len(portfolio['positions']) < max_positions and i % 5 == 0:
                candidates = []

                for symbol, df in price_data.items():
                    if date not in df.index:
                        continue

                    # Skip if already in portfolio
                    if any(p['symbol'] == symbol for p in portfolio['positions']):
                        continue

                    idx = df.index.get_loc(date)
                    if idx < 30:
                        continue

                    closes = df['close'].values[idx-30:idx+1]
                    highs = df['high'].values[idx-30:idx+1]
                    lows = df['low'].values[idx-30:idx+1]
                    volumes = df['volume'].values[idx-30:idx+1]

                    price = closes[-1]

                    # Skip penny stocks
                    if price < 5:
                        continue

                    # Momentum (5-day)
                    mom_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0

                    # 20-day momentum
                    mom_20d = (closes[-1] / closes[-20] - 1) * 100 if closes[-20] > 0 else 0

                    # MA20
                    ma20 = np.mean(closes[-20:])
                    above_ma = (price / ma20 - 1) * 100

                    # ATR %
                    tr = []
                    for j in range(-14, 0):
                        tr.append(max(highs[j] - lows[j],
                                      abs(highs[j] - closes[j-1]),
                                      abs(lows[j] - closes[j-1])))
                    atr_pct = (np.mean(tr) / price) * 100 if price > 0 else 0

                    # RSI
                    deltas = np.diff(closes[-15:])
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    avg_gain = np.mean(gains)
                    avg_loss = np.mean(losses)
                    rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

                    # Volume ratio
                    vol_avg = np.mean(volumes[-20:-1]) if len(volumes) >= 20 else 1
                    vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

                    # FILTERS
                    if atr_pct > 2.5:  # Too volatile
                        continue
                    if rsi > 70:  # Overbought
                        continue
                    if above_ma < 0:  # Below MA20
                        continue
                    if mom_5d < 2 or mom_5d > 10:  # Momentum sweet spot
                        continue

                    # Score
                    score = 0
                    score += min(30, mom_5d * 4)
                    score += max(0, 20 - atr_pct * 8)
                    score += min(20, vol_ratio * 10)

                    # Sector bonus (Finance_Banks, Utilities)
                    sector = symbol_sectors.get(symbol, '')
                    if sector in ['Finance_Banks', 'Finance_Diversified', 'Utilities']:
                        score += 15
                    elif sector in ['Semiconductors', 'Technology']:
                        score += 10

                    candidates.append({
                        'symbol': symbol,
                        'sector': sector,
                        'price': price,
                        'score': score,
                        'mom_5d': mom_5d,
                        'atr_pct': atr_pct,
                    })

                # Sort by score and pick top
                candidates.sort(key=lambda x: x['score'], reverse=True)

                for cand in candidates[:max_positions - len(portfolio['positions'])]:
                    if portfolio['cash'] >= position_size:
                        shares = int(position_size / cand['price'])
                        if shares > 0:
                            portfolio['positions'].append({
                                'symbol': cand['symbol'],
                                'sector': cand['sector'],
                                'entry_date': date,
                                'entry_price': cand['price'],
                                'shares': shares,
                                'days_held': 0,
                            })
                            portfolio['cash'] -= cand['price'] * shares

        conn.close()

        # Calculate results
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

        # Print results
        print("\n" + "="*70)
        print("BACKTEST RESULTS")
        print("="*70)
        print(f"Total Trades: {len(trades)}")
        print(f"Winners: {len(wins)} ({win_rate:.1f}%)")
        print(f"Losers: {len(losses)}")
        print(f"Total P&L: ${total_pnl:+,.2f}")
        print(f"Average Win: {avg_win:+.2f}%")
        print(f"Average Loss: {avg_loss:+.2f}%")

        # Monthly breakdown
        print("\n" + "="*70)
        print("MONTHLY SUMMARY")
        print("="*70)
        print(f"{'Month':<10} {'Trades':>8} {'P&L':>15} {'Win Rate':>10}")
        print("-"*50)

        for month in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            pnl_pct = (data['pnl'] / 100000) * 100
            print(f"{month:<10} {data['trades']:>8} ${data['pnl']:>13,.2f} ({pnl_pct:+.1f}%) {wr:>9.0f}%")

        print("-"*50)
        avg_monthly = sum(d['pnl'] for d in monthly_pnl.values()) / len(monthly_pnl) if monthly_pnl else 0
        print(f"Average Monthly P&L: ${avg_monthly:+,.2f} ({avg_monthly/100000*100:+.2f}%)")

        # Sector performance
        print("\n" + "="*70)
        print("SECTOR PERFORMANCE")
        print("="*70)

        sector_stats = {}
        for trade in trades:
            sector = trade['sector']
            if sector not in sector_stats:
                sector_stats[sector] = {'trades': 0, 'wins': 0, 'pnl': 0}
            sector_stats[sector]['trades'] += 1
            sector_stats[sector]['pnl'] += trade['pnl']
            if trade['pnl'] > 0:
                sector_stats[sector]['wins'] += 1

        print(f"{'Sector':<25} {'Trades':>8} {'Win Rate':>10} {'P&L':>15}")
        print("-"*60)

        for sector in sorted(sector_stats.keys(), key=lambda x: sector_stats[x]['pnl'], reverse=True):
            stats = sector_stats[sector]
            wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
            print(f"{sector:<25} {stats['trades']:>8} {wr:>9.0f}% ${stats['pnl']:>14,.2f}")

        return {
            'trades': len(trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'monthly': monthly_pnl,
            'by_sector': sector_stats,
        }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Daily Runner')
    parser.add_argument('--schedule', action='store_true', help='Run in scheduled mode')
    parser.add_argument('--backtest', action='store_true', help='Run comprehensive backtest')
    parser.add_argument('--time', default='06:00', help='Daily run time (default: 06:00)')
    args = parser.parse_args()

    if args.backtest:
        backtester = ComprehensiveBacktester()
        results = backtester.run_backtest(
            start_date='2024-01-01',
            end_date='2025-12-31',
            stop_loss=-0.03,
            target_profit=0.06,
            max_positions=5,
            position_size=10000,
        )

        if results:
            # Save results
            results_file = os.path.join(LOG_DIR, 'backtest_results.json')
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nResults saved to: {results_file}")

    elif args.schedule:
        runner = DailyRunner()
        runner.run_scheduled(run_time=args.time)

    else:
        runner = DailyRunner()
        runner.run_daily_job()


if __name__ == '__main__':
    main()
