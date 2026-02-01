#!/usr/bin/env python3
"""
PORTFOLIO SYSTEM - ระบบจัดการพอร์ตครบวงจร

Features:
1. ดึงหุ้นเข้าพอร์ต พร้อมราคาเข้า
2. อัพเดตสถานะทุกวัน (กำไร/ขาดทุน)
3. แจ้งเตือนเมื่อถึง target/stop
4. สรุปผลประจำวัน/เดือน
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PORTFOLIO_FILE = os.path.join(DATA_DIR, 'portfolio', 'portfolio.json')
HISTORY_FILE = os.path.join(DATA_DIR, 'portfolio', 'history.json')

os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)


class PortfolioManager:
    """Portfolio Manager - จัดการพอร์ตหุ้น"""

    def __init__(self):
        self.portfolio = self._load_portfolio()
        self.history = self._load_history()

    def _load_portfolio(self) -> Dict:
        """Load current portfolio"""
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, 'r') as f:
                return json.load(f)
        return {
            'positions': [],
            'cash': 100000,  # Starting cash
            'last_update': None,
        }

    def _load_history(self) -> List:
        """Load trade history"""
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        return []

    def _save_portfolio(self):
        """Save portfolio"""
        self.portfolio['last_update'] = datetime.now().isoformat()
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(self.portfolio, f, indent=2)

    def _save_history(self):
        """Save history"""
        with open(HISTORY_FILE, 'w') as f:
            json.dump(self.history, f, indent=2)

    def add_position(self, symbol: str, entry_price: float, shares: int,
                     stop_price: float, target_price: float, sector: str = None,
                     reason: str = None):
        """Add new position to portfolio"""
        position = {
            'symbol': symbol,
            'entry_date': datetime.now().strftime('%Y-%m-%d'),
            'entry_price': entry_price,
            'shares': shares,
            'stop_price': stop_price,
            'target_price': target_price,
            'sector': sector,
            'reason': reason,
            'current_price': entry_price,
            'current_pnl': 0,
            'current_pnl_pct': 0,
            'status': 'OPEN',
            'days_held': 0,
        }

        self.portfolio['positions'].append(position)
        self.portfolio['cash'] -= entry_price * shares
        self._save_portfolio()

        print(f"✓ Added: {symbol} @ ${entry_price:.2f} x {shares} shares")
        print(f"  Stop: ${stop_price:.2f} ({(stop_price/entry_price-1)*100:+.1f}%)")
        print(f"  Target: ${target_price:.2f} ({(target_price/entry_price-1)*100:+.1f}%)")

    def update_prices(self):
        """Update all position prices and check stop/target"""
        if yf is None:
            print("yfinance not available")
            return

        print("\n" + "="*60)
        print("PORTFOLIO UPDATE")
        print("="*60)

        alerts = []

        for position in self.portfolio['positions']:
            if position['status'] != 'OPEN':
                continue

            symbol = position['symbol']
            try:
                ticker = yf.Ticker(symbol)
                current = ticker.fast_info.get('lastPrice', None)
                if current is None:
                    hist = ticker.history(period='1d')
                    if len(hist) > 0:
                        current = float(hist['Close'].iloc[-1])

                if current:
                    position['current_price'] = current
                    position['current_pnl'] = (current - position['entry_price']) * position['shares']
                    position['current_pnl_pct'] = (current / position['entry_price'] - 1) * 100
                    position['days_held'] = (datetime.now() - datetime.strptime(position['entry_date'], '%Y-%m-%d')).days

                    # Check stop loss
                    if current <= position['stop_price']:
                        alerts.append({
                            'symbol': symbol,
                            'type': 'STOP_HIT',
                            'message': f"⚠️ {symbol} hit STOP @ ${current:.2f} (Stop: ${position['stop_price']:.2f})"
                        })
                        position['status'] = 'STOP_HIT'

                    # Check target
                    elif current >= position['target_price']:
                        alerts.append({
                            'symbol': symbol,
                            'type': 'TARGET_HIT',
                            'message': f"🎯 {symbol} hit TARGET @ ${current:.2f} (Target: ${position['target_price']:.2f})"
                        })
                        position['status'] = 'TARGET_HIT'

            except Exception as e:
                print(f"  Error updating {symbol}: {e}")

        self._save_portfolio()

        # Display positions
        self._display_positions()

        # Display alerts
        if alerts:
            print("\n" + "="*60)
            print("ALERTS")
            print("="*60)
            for alert in alerts:
                print(alert['message'])

        return alerts

    def _display_positions(self):
        """Display current positions"""
        open_positions = [p for p in self.portfolio['positions'] if p['status'] == 'OPEN']

        if not open_positions:
            print("\nNo open positions")
            return

        print(f"\nOpen Positions: {len(open_positions)}")
        print("-"*80)
        print(f"{'Symbol':<8} {'Entry':>10} {'Current':>10} {'P&L':>12} {'P&L%':>8} {'Days':>5} {'Status':<12}")
        print("-"*80)

        total_pnl = 0
        for p in open_positions:
            pnl_str = f"${p['current_pnl']:+,.0f}"
            pnl_pct_str = f"{p['current_pnl_pct']:+.1f}%"

            # Color status based on P&L
            if p['current_pnl_pct'] > 3:
                status = "🟢 PROFIT"
            elif p['current_pnl_pct'] < -2:
                status = "🔴 LOSS"
            else:
                status = "🟡 HOLD"

            print(f"{p['symbol']:<8} ${p['entry_price']:>9.2f} ${p['current_price']:>9.2f} {pnl_str:>12} {pnl_pct_str:>8} {p['days_held']:>5} {status:<12}")
            total_pnl += p['current_pnl']

        print("-"*80)
        print(f"{'Total P&L:':<30} ${total_pnl:+,.2f}")
        print(f"{'Cash:':<30} ${self.portfolio['cash']:,.2f}")

    def close_position(self, symbol: str, exit_price: float = None, reason: str = 'manual'):
        """Close a position"""
        for i, position in enumerate(self.portfolio['positions']):
            if position['symbol'] == symbol and position['status'] == 'OPEN':
                if exit_price is None:
                    exit_price = position['current_price']

                pnl = (exit_price - position['entry_price']) * position['shares']
                pnl_pct = (exit_price / position['entry_price'] - 1) * 100

                # Add to history
                trade = {
                    'symbol': symbol,
                    'entry_date': position['entry_date'],
                    'exit_date': datetime.now().strftime('%Y-%m-%d'),
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'shares': position['shares'],
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'days_held': position['days_held'],
                    'exit_reason': reason,
                    'sector': position['sector'],
                }
                self.history.append(trade)

                # Update cash
                self.portfolio['cash'] += exit_price * position['shares']

                # Mark as closed
                position['status'] = 'CLOSED'
                position['exit_price'] = exit_price
                position['exit_date'] = datetime.now().strftime('%Y-%m-%d')
                position['exit_reason'] = reason

                self._save_portfolio()
                self._save_history()

                print(f"✓ Closed: {symbol} @ ${exit_price:.2f}")
                print(f"  P&L: ${pnl:+,.2f} ({pnl_pct:+.1f}%)")
                return trade

        print(f"Position {symbol} not found or already closed")
        return None

    def get_summary(self) -> Dict:
        """Get portfolio summary"""
        open_positions = [p for p in self.portfolio['positions'] if p['status'] == 'OPEN']
        closed_trades = self.history

        # Calculate stats
        total_open_pnl = sum(p['current_pnl'] for p in open_positions)
        total_open_value = sum(p['current_price'] * p['shares'] for p in open_positions)

        if closed_trades:
            total_closed_pnl = sum(t['pnl'] for t in closed_trades)
            win_trades = [t for t in closed_trades if t['pnl'] > 0]
            win_rate = len(win_trades) / len(closed_trades) * 100
            avg_win = np.mean([t['pnl_pct'] for t in win_trades]) if win_trades else 0
            avg_loss = np.mean([t['pnl_pct'] for t in closed_trades if t['pnl'] <= 0]) if closed_trades else 0
        else:
            total_closed_pnl = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0

        return {
            'open_positions': len(open_positions),
            'total_open_value': total_open_value,
            'total_open_pnl': total_open_pnl,
            'closed_trades': len(closed_trades),
            'total_closed_pnl': total_closed_pnl,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'cash': self.portfolio['cash'],
            'total_value': self.portfolio['cash'] + total_open_value,
        }

    def get_monthly_summary(self) -> Dict:
        """Get monthly P&L summary"""
        if not self.history:
            return {}

        monthly = {}
        for trade in self.history:
            month = trade['exit_date'][:7]  # YYYY-MM
            if month not in monthly:
                monthly[month] = {'trades': 0, 'pnl': 0, 'wins': 0}
            monthly[month]['trades'] += 1
            monthly[month]['pnl'] += trade['pnl']
            if trade['pnl'] > 0:
                monthly[month]['wins'] += 1

        return monthly

    def display_monthly_summary(self):
        """Display monthly summary"""
        monthly = self.get_monthly_summary()

        if not monthly:
            print("No closed trades yet")
            return

        print("\n" + "="*60)
        print("MONTHLY SUMMARY")
        print("="*60)
        print(f"{'Month':<10} {'Trades':>8} {'P&L':>15} {'Win Rate':>10}")
        print("-"*60)

        total_pnl = 0
        for month in sorted(monthly.keys()):
            data = monthly[month]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            print(f"{month:<10} {data['trades']:>8} ${data['pnl']:>14,.2f} {wr:>9.0f}%")
            total_pnl += data['pnl']

        print("-"*60)
        print(f"{'TOTAL':<10} {len(self.history):>8} ${total_pnl:>14,.2f}")


class StockScanner:
    """Scanner to find stocks for portfolio"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(DATA_DIR, 'database', 'stocks.db')

    def scan_for_opportunities(self, top_n: int = 5) -> List[Dict]:
        """Scan for trading opportunities"""
        if yf is None:
            return []

        print("\n" + "="*60)
        print("SCANNING FOR OPPORTUNITIES")
        print("="*60)

        # Get best sectors based on momentum
        conn = sqlite3.connect(self.db_path)

        # Get sector momentum
        sector_mom = {}
        cursor = conn.execute("""
            SELECT sector, symbol FROM stock_prices
            WHERE sector NOT LIKE '%_ETF' AND sector != 'INDICATOR'
            GROUP BY sector, symbol
        """)

        sector_symbols = {}
        for row in cursor.fetchall():
            sector, symbol = row
            if sector not in sector_symbols:
                sector_symbols[sector] = []
            sector_symbols[sector].append(symbol)

        # Calculate sector momentum
        for sector, symbols in sector_symbols.items():
            returns = []
            for symbol in symbols[:10]:  # Sample 10 per sector
                df = pd.read_sql(
                    f"SELECT close FROM stock_prices WHERE symbol = ? ORDER BY date DESC LIMIT 20",
                    conn, params=(symbol,)
                )
                if len(df) >= 20:
                    ret = (df['close'].iloc[0] / df['close'].iloc[-1] - 1) * 100
                    returns.append(ret)
            if returns:
                sector_mom[sector] = np.mean(returns)

        # Get top 3 sectors
        top_sectors = sorted(sector_mom.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"\nTop Sectors: {', '.join([f'{s}({m:.1f}%)' for s, m in top_sectors])}")

        # Scan stocks in top sectors
        opportunities = []

        for sector, _ in top_sectors:
            symbols = sector_symbols.get(sector, [])[:20]

            for symbol in symbols:
                try:
                    df = pd.read_sql(
                        f"SELECT date, close, high, low, volume FROM stock_prices WHERE symbol = ? ORDER BY date DESC LIMIT 60",
                        conn, params=(symbol,)
                    )

                    if len(df) < 30:
                        continue

                    closes = df['close'].values[::-1]
                    highs = df['high'].values[::-1]
                    lows = df['low'].values[::-1]
                    volumes = df['volume'].values[::-1]

                    # Current price
                    price = closes[-1]

                    # Momentum
                    mom_5d = (closes[-1] / closes[-5] - 1) * 100
                    mom_20d = (closes[-1] / closes[-20] - 1) * 100

                    # MA
                    ma20 = np.mean(closes[-20:])
                    above_ma = ((price - ma20) / ma20) * 100

                    # RSI
                    deltas = np.diff(closes[-15:])
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    avg_gain = np.mean(gains)
                    avg_loss = np.mean(losses)
                    rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

                    # ATR %
                    tr = []
                    for i in range(-14, 0):
                        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
                    atr_pct = (np.mean(tr) / price) * 100

                    # Volume ratio
                    vol_ratio = volumes[-1] / np.mean(volumes[-20:-1]) if np.mean(volumes[-20:-1]) > 0 else 1

                    # FILTERS
                    if atr_pct > 2.5:  # Too volatile
                        continue
                    if rsi > 70 or rsi < 30:  # Overbought/oversold
                        continue
                    if above_ma < 0:  # Below MA20
                        continue
                    if mom_5d < 2 or mom_5d > 10:  # Not in sweet spot
                        continue

                    # Score
                    score = 0
                    score += min(30, mom_5d * 4)
                    score += max(0, 20 - atr_pct * 8)
                    score += min(20, vol_ratio * 10)
                    score += min(15, above_ma * 2)

                    opportunities.append({
                        'symbol': symbol,
                        'sector': sector,
                        'price': price,
                        'score': score,
                        'mom_5d': mom_5d,
                        'mom_20d': mom_20d,
                        'rsi': rsi,
                        'atr_pct': atr_pct,
                        'above_ma': above_ma,
                        'vol_ratio': vol_ratio,
                        'entry_price': price,
                        'stop_price': price * 0.97,  # -3%
                        'target_price': price * 1.06,  # +6%
                    })

                except Exception as e:
                    continue

        conn.close()

        # Sort by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        top_opps = opportunities[:top_n]

        # Display
        print(f"\nTop {len(top_opps)} Opportunities:")
        print("-"*90)
        print(f"{'Symbol':<8} {'Sector':<20} {'Price':>10} {'Mom5d':>8} {'RSI':>6} {'ATR%':>6} {'Score':>6}")
        print("-"*90)

        for opp in top_opps:
            print(f"{opp['symbol']:<8} {opp['sector']:<20} ${opp['price']:>9.2f} {opp['mom_5d']:>+7.1f}% {opp['rsi']:>5.0f} {opp['atr_pct']:>5.1f}% {opp['score']:>5.0f}")

        print("-"*90)
        print("\nEntry Recommendations:")
        for opp in top_opps:
            print(f"  {opp['symbol']}: Entry ${opp['entry_price']:.2f}, Stop ${opp['stop_price']:.2f}, Target ${opp['target_price']:.2f}")

        return top_opps


def main():
    """Main - Portfolio and Scanner"""
    print("="*70)
    print("PORTFOLIO SYSTEM")
    print("="*70)

    pm = PortfolioManager()
    scanner = StockScanner()

    # Scan for opportunities
    opportunities = scanner.scan_for_opportunities(top_n=5)

    # Update existing positions
    pm.update_prices()

    # Show summary
    summary = pm.get_summary()
    print("\n" + "="*60)
    print("PORTFOLIO SUMMARY")
    print("="*60)
    print(f"Open Positions: {summary['open_positions']}")
    print(f"Open P&L: ${summary['total_open_pnl']:+,.2f}")
    print(f"Closed Trades: {summary['closed_trades']}")
    print(f"Closed P&L: ${summary['total_closed_pnl']:+,.2f}")
    print(f"Win Rate: {summary['win_rate']:.1f}%")
    print(f"Cash: ${summary['cash']:,.2f}")
    print(f"Total Value: ${summary['total_value']:,.2f}")

    # Show monthly
    pm.display_monthly_summary()


if __name__ == '__main__':
    main()
