#!/usr/bin/env python3
"""
AGGRESSIVE CATALYST SYSTEM - เป้าหมาย 10-15% ต่อเดือน

Strategy:
1. เทรดเฉพาะหุ้นที่มี STRONG CATALYST
2. Position size ใหญ่ขึ้น (concentrated)
3. Target สูงขึ้น (+10-15%)
4. ถือสั้นลง (3-5 วัน)
5. ใช้ News เป็นตัวนำ

เพื่อได้ 10-15%/เดือน ต้อง:
- 3-5 trades/เดือน
- Win Rate > 70%
- Average Win > 8%
- Average Loss < 3%
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import requests
import json
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')

# News API Keys
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_KEY', '')


class NewsSentimentAnalyzer:
    """Analyze news sentiment for stocks"""

    def __init__(self):
        self.positive_words = [
            'beat', 'beats', 'surge', 'surges', 'jump', 'jumps', 'soar', 'soars',
            'rally', 'record', 'high', 'upgrade', 'upgraded', 'buy', 'bullish',
            'strong', 'growth', 'profit', 'gain', 'positive', 'outperform',
            'exceed', 'exceeds', 'boom', 'breakout', 'momentum'
        ]
        self.negative_words = [
            'miss', 'misses', 'fall', 'falls', 'drop', 'drops', 'plunge', 'crash',
            'sell', 'downgrade', 'downgraded', 'bearish', 'weak', 'loss', 'losses',
            'decline', 'negative', 'underperform', 'cut', 'layoff', 'warning'
        ]

    def analyze_text(self, text: str) -> float:
        """Return sentiment score -1 to +1"""
        if not text:
            return 0

        text_lower = text.lower()
        pos = sum(1 for w in self.positive_words if w in text_lower)
        neg = sum(1 for w in self.negative_words if w in text_lower)

        total = pos + neg
        if total == 0:
            return 0

        return (pos - neg) / total

    def get_stock_news_sentiment(self, symbol: str) -> Dict:
        """Get news sentiment for a stock using yfinance"""
        if not yf:
            return {'score': 0, 'count': 0}

        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news

            if not news:
                return {'score': 0, 'count': 0}

            scores = []
            for article in news[:10]:
                title = article.get('title', '')
                score = self.analyze_text(title)
                scores.append(score)

            return {
                'score': np.mean(scores) if scores else 0,
                'count': len(scores),
                'recent_headlines': [n.get('title', '')[:50] for n in news[:3]]
            }
        except:
            return {'score': 0, 'count': 0}


class AggressiveCatalystSystem:
    """Aggressive trading system targeting 10-15% monthly"""

    def __init__(self):
        self.news_analyzer = NewsSentimentAnalyzer()
        self.db_path = DB_PATH

    def find_catalyst_stocks(self, date: str = None) -> List[Dict]:
        """Find stocks with strong catalysts"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        print(f"\n🔍 Scanning for STRONG CATALYSTS...")

        conn = sqlite3.connect(self.db_path)

        # Get all stocks from best sectors
        best_sectors = [
            'Finance_Banks', 'Healthcare_Pharma', 'Semiconductors',
            'Technology', 'Consumer_Retail'
        ]

        placeholders = ','.join(['?' for _ in best_sectors])
        cursor = conn.execute(f"""
            SELECT DISTINCT symbol, sector FROM stock_prices
            WHERE sector IN ({placeholders})
        """, best_sectors)

        stocks = [(row[0], row[1]) for row in cursor.fetchall()]

        candidates = []

        for symbol, sector in stocks[:100]:  # Limit for speed
            # Get price data
            df = pd.read_sql("""
                SELECT date, open, high, low, close, volume FROM stock_prices
                WHERE symbol = ? ORDER BY date DESC LIMIT 60
            """, conn, params=(symbol,))

            if len(df) < 30:
                continue

            df = df.iloc[::-1]  # Reverse to chronological
            closes = df['close'].values
            highs = df['high'].values
            lows = df['low'].values
            volumes = df['volume'].values

            price = closes[-1]
            if price < 20:
                continue

            # ===== CATALYST DETECTION =====
            catalyst_score = 0
            catalysts = []

            # 1. BREAKOUT (very strong)
            recent_high = max(closes[-20:-1])
            if closes[-1] > recent_high * 1.02:
                catalyst_score += 30
                catalysts.append('BREAKOUT')

            # 2. VOLUME EXPLOSION
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

            if vol_ratio > 3:
                catalyst_score += 25
                catalysts.append('VOLUME_EXPLOSION')
            elif vol_ratio > 2:
                catalyst_score += 15
                catalysts.append('VOLUME_SURGE')

            # 3. GAP UP
            if len(df) > 1:
                gap = (df['open'].iloc[-1] / closes[-2] - 1) * 100
                if gap > 3:
                    catalyst_score += 20
                    catalysts.append(f'GAP_UP_{gap:.1f}%')

            # 4. MOMENTUM ACCELERATION
            mom_5d = (closes[-1] / closes[-5] - 1) * 100
            mom_3d = (closes[-1] / closes[-3] - 1) * 100

            if mom_3d > 5:
                catalyst_score += 20
                catalysts.append('STRONG_MOMENTUM')
            elif mom_3d > 3:
                catalyst_score += 10
                catalysts.append('MOMENTUM')

            # 5. NEWS SENTIMENT
            news = self.news_analyzer.get_stock_news_sentiment(symbol)
            if news['score'] > 0.5:
                catalyst_score += 25
                catalysts.append('POSITIVE_NEWS')
            elif news['score'] > 0.2:
                catalyst_score += 10
                catalysts.append('NEWS_BULLISH')

            # 6. NEAR 52W HIGH
            high_52w = max(highs)
            pct_from_high = (price / high_52w - 1) * 100
            if pct_from_high > -2:
                catalyst_score += 15
                catalysts.append('52W_HIGH')

            # ===== FILTERS =====
            # Skip if no strong catalyst
            if catalyst_score < 40:
                continue

            # ATR check
            tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(-14, 0)]
            atr_pct = np.mean(tr) / price * 100

            # RSI check
            deltas = np.diff(closes[-15:])
            rsi = 100 - 100/(1 + np.mean(np.maximum(deltas,0))/np.mean(np.maximum(-deltas,0))) if np.mean(np.maximum(-deltas,0)) > 0 else 50

            if rsi > 75:  # Overbought
                continue

            candidates.append({
                'symbol': symbol,
                'sector': sector,
                'price': price,
                'catalyst_score': catalyst_score,
                'catalysts': catalysts,
                'momentum_3d': mom_3d,
                'momentum_5d': mom_5d,
                'volume_ratio': vol_ratio,
                'rsi': rsi,
                'atr_pct': atr_pct,
                'news_score': news['score'],
                'news_headlines': news.get('recent_headlines', []),
            })

        conn.close()

        # Sort by catalyst score
        candidates.sort(key=lambda x: x['catalyst_score'], reverse=True)

        print(f"Found {len(candidates)} stocks with strong catalysts")

        return candidates[:10]

    def generate_trading_signals(self) -> Dict:
        """Generate trading signals for today"""
        print("="*70)
        print("🎯 AGGRESSIVE CATALYST SYSTEM")
        print("="*70)
        print(f"Target: 10-15% per month")
        print(f"Strategy: High-conviction catalyst trades")
        print("="*70)

        # Find catalyst stocks
        candidates = self.find_catalyst_stocks()

        if not candidates:
            print("\n⚠️ No strong catalysts found today")
            return {'signals': [], 'action': 'WAIT'}

        # Generate signals for top picks
        signals = []

        for cand in candidates[:3]:  # Top 3 only
            # Calculate entry/stop/target
            entry = cand['price']
            stop = entry * 0.96  # -4% stop (tighter risk)
            target1 = entry * 1.08  # +8% first target
            target2 = entry * 1.12  # +12% second target
            target3 = entry * 1.15  # +15% moon target

            signal = {
                'symbol': cand['symbol'],
                'sector': cand['sector'],
                'action': 'BUY',
                'entry': entry,
                'stop': stop,
                'target1': target1,
                'target2': target2,
                'target3': target3,
                'catalyst_score': cand['catalyst_score'],
                'catalysts': cand['catalysts'],
                'momentum': cand['momentum_3d'],
                'volume_ratio': cand['volume_ratio'],
                'confidence': 'HIGH' if cand['catalyst_score'] >= 60 else 'MEDIUM',
                'position_size': '25%' if cand['catalyst_score'] >= 60 else '15%',
            }
            signals.append(signal)

        # Print signals
        print("\n" + "="*70)
        print("📊 TODAY'S SIGNALS")
        print("="*70)

        for sig in signals:
            print(f"\n🎯 {sig['symbol']} ({sig['sector']})")
            print(f"   Catalysts: {', '.join(sig['catalysts'])}")
            print(f"   Catalyst Score: {sig['catalyst_score']}")
            print(f"   Momentum (3d): {sig['momentum']:+.1f}%")
            print(f"   Volume Ratio: {sig['volume_ratio']:.1f}x")
            print(f"   Confidence: {sig['confidence']}")
            print(f"   Position Size: {sig['position_size']}")
            print(f"   ---")
            print(f"   Entry: ${sig['entry']:.2f}")
            print(f"   Stop: ${sig['stop']:.2f} (-4%)")
            print(f"   Target 1: ${sig['target1']:.2f} (+8%)")
            print(f"   Target 2: ${sig['target2']:.2f} (+12%)")
            print(f"   Target 3: ${sig['target3']:.2f} (+15%)")

        # Save signals
        output = {
            'timestamp': datetime.now().isoformat(),
            'signals': signals,
            'market_conditions': 'ACTIVE' if len(signals) >= 2 else 'CAUTIOUS',
        }

        output_path = os.path.join(DATA_DIR, 'predictions', 'catalyst_signals.json')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ Signals saved to: {output_path}")

        return output


def backtest_aggressive_system(
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-31',
    initial_capital: float = 100000,
):
    """Backtest the aggressive catalyst system"""

    print("="*70)
    print("🎯 BACKTEST: AGGRESSIVE CATALYST SYSTEM")
    print("="*70)
    print(f"Target: 10-15% per month")
    print(f"Period: {start_date} to {end_date}")
    print("="*70)

    conn = sqlite3.connect(DB_PATH)

    # Get dates
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
    """, (start_date, end_date))
    dates = [row[0] for row in cursor.fetchall()]

    # Get stocks from best sectors
    sectors = ['Finance_Banks', 'Healthcare_Pharma', 'Semiconductors', 'Technology']
    placeholders = ','.join(['?' for _ in sectors])
    cursor = conn.execute(f"""
        SELECT DISTINCT symbol, sector FROM stock_prices
        WHERE sector IN ({placeholders})
    """, sectors)
    stocks = {row[0]: row[1] for row in cursor.fetchall()}

    # Load data
    print(f"Loading data...")
    stock_data = {}
    for symbol in stocks:
        df = pd.read_sql("""
            SELECT date, open, high, low, close, volume FROM stock_prices
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, conn, params=(symbol, start_date, end_date))
        if len(df) >= 30:
            df.set_index('date', inplace=True)
            stock_data[symbol] = df

    print(f"Loaded: {len(stock_data)} stocks")

    # Portfolio
    portfolio = {'cash': initial_capital, 'positions': [], 'history': []}
    monthly_pnl = {}

    # AGGRESSIVE PARAMETERS
    stop_loss = 0.04  # -4%
    target1 = 0.08    # +8%
    target2 = 0.12    # +12%
    max_positions = 3
    position_pct = 0.30  # 30% per position (concentrated)
    max_hold = 5  # 5 days max

    for i, date in enumerate(dates):
        if i < 30:
            continue

        # Total value
        total_value = portfolio['cash']
        for pos in portfolio['positions']:
            if pos['symbol'] in stock_data and date in stock_data[pos['symbol']].index:
                total_value += stock_data[pos['symbol']].loc[date, 'close'] * pos['shares']

        # Manage positions
        for pos in portfolio['positions'][:]:
            if pos['symbol'] not in stock_data:
                continue
            df = stock_data[pos['symbol']]
            if date not in df.index:
                continue

            price = df.loc[date, 'close']
            pnl_pct = price / pos['entry_price'] - 1

            if price > pos.get('highest', pos['entry_price']):
                pos['highest'] = price

            exit_reason = None
            exit_pct = 1.0  # Exit all by default

            # Stop loss
            if pnl_pct <= -stop_loss:
                exit_reason = 'STOP'

            # Target 1: Sell 50%
            elif pnl_pct >= target1 and not pos.get('t1_hit'):
                exit_reason = 'TARGET1'
                exit_pct = 0.5
                pos['t1_hit'] = True

            # Target 2: Sell remaining
            elif pnl_pct >= target2:
                exit_reason = 'TARGET2'

            # Trailing after T1
            elif pos.get('t1_hit') and pos['highest'] > pos['entry_price'] * 1.10:
                if price < pos['highest'] * 0.96:
                    exit_reason = 'TRAIL'

            # Time stop
            elif pos['days'] >= max_hold:
                exit_reason = 'TIME'

            if exit_reason:
                shares_to_sell = int(pos['shares'] * exit_pct)
                if shares_to_sell == 0:
                    shares_to_sell = pos['shares']

                pnl = (price - pos['entry_price']) * shares_to_sell

                portfolio['history'].append({
                    'symbol': pos['symbol'],
                    'sector': pos['sector'],
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': price,
                    'shares': shares_to_sell,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'days': pos['days'],
                })

                portfolio['cash'] += price * shares_to_sell
                pos['shares'] -= shares_to_sell

                if pos['shares'] <= 0:
                    portfolio['positions'].remove(pos)

                month = date[:7]
                if month not in monthly_pnl:
                    monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
                monthly_pnl[month]['pnl'] += pnl
                monthly_pnl[month]['trades'] += 1
                if pnl > 0:
                    monthly_pnl[month]['wins'] += 1
            else:
                pos['days'] += 1

        # Find new entries (every 2 days)
        if i % 2 != 0:
            continue
        if len(portfolio['positions']) >= max_positions:
            continue

        candidates = []

        for symbol, df in stock_data.items():
            if date not in df.index:
                continue
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
            if price < 20:
                continue

            # ===== STRONG CATALYST DETECTION =====
            catalyst_score = 0

            # Breakout
            recent_high = max(closes[-20:-1])
            if closes[-1] > recent_high * 1.02:
                catalyst_score += 30

            # Volume explosion
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1
            if vol_ratio > 3:
                catalyst_score += 25
            elif vol_ratio > 2:
                catalyst_score += 15

            # Gap up
            if idx > 0:
                gap = (df['open'].values[idx] / closes[-2] - 1) * 100
                if gap > 3:
                    catalyst_score += 20

            # Momentum acceleration
            mom_3d = (closes[-1] / closes[-3] - 1) * 100
            if mom_3d > 5:
                catalyst_score += 20
            elif mom_3d > 3:
                catalyst_score += 10

            # Near 52W high
            if closes[-1] / max(highs) > 0.98:
                catalyst_score += 15

            # STRICT: Only trade strong catalysts
            if catalyst_score < 50:
                continue

            # ATR check
            tr = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(-14, 0)]
            atr_pct = np.mean(tr) / price * 100

            # RSI
            deltas = np.diff(closes[-15:])
            rsi = 100 - 100/(1 + np.mean(np.maximum(deltas,0))/np.mean(np.maximum(-deltas,0))) if np.mean(np.maximum(-deltas,0)) > 0 else 50

            if rsi > 72:
                continue

            candidates.append({
                'symbol': symbol,
                'sector': stocks.get(symbol, ''),
                'price': price,
                'catalyst_score': catalyst_score,
                'vol_ratio': vol_ratio,
                'mom_3d': mom_3d,
            })

        candidates.sort(key=lambda x: x['catalyst_score'], reverse=True)

        for c in candidates[:max_positions - len(portfolio['positions'])]:
            pos_value = total_value * position_pct
            shares = int(pos_value / c['price'])

            if shares > 0 and portfolio['cash'] >= c['price'] * shares:
                portfolio['positions'].append({
                    'symbol': c['symbol'],
                    'sector': c['sector'],
                    'entry_date': date,
                    'entry_price': c['price'],
                    'shares': shares,
                    'days': 0,
                    'highest': c['price'],
                    't1_hit': False,
                })
                portfolio['cash'] -= c['price'] * shares

    conn.close()

    # ===== RESULTS =====
    trades = portfolio['history']
    if not trades:
        print("No trades")
        return

    total_pnl = sum(t['pnl'] for t in trades)
    wins = [t for t in trades if t['pnl'] > 0]
    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in trades if t['pnl'] <= 0]) if len(trades) > len(wins) else 0

    print("\n" + "="*70)
    print("🏆 AGGRESSIVE CATALYST RESULTS")
    print("="*70)
    print(f"Trades: {len(trades)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total P&L: ${total_pnl:+,.2f} ({total_pnl/initial_capital*100:+.1f}%)")
    print(f"Avg Win: {avg_win:+.2f}%")
    print(f"Avg Loss: {avg_loss:+.2f}%")

    # Exit breakdown
    exits = {}
    for t in trades:
        r = t['exit_reason']
        if r not in exits:
            exits[r] = {'n': 0, 'pnl': 0, 'w': 0}
        exits[r]['n'] += 1
        exits[r]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            exits[r]['w'] += 1

    print("\n📋 EXIT BREAKDOWN:")
    for r, d in sorted(exits.items(), key=lambda x: x[1]['pnl'], reverse=True):
        wr = d['w']/d['n']*100 if d['n'] > 0 else 0
        print(f"  {r:<10} {d['n']:>4} trades, {wr:>5.0f}% WR, ${d['pnl']:>+10,.2f}")

    # Monthly
    print("\n📋 MONTHLY PERFORMANCE:")
    positive = 0
    returns = []
    target_months = 0

    for m in sorted(monthly_pnl.keys()):
        d = monthly_pnl[m]
        pct = d['pnl']/initial_capital*100
        returns.append(pct)
        wr = d['wins']/d['trades']*100 if d['trades'] > 0 else 0

        emoji = "🎯" if pct >= 10 else "✅" if pct > 0 else "❌"
        print(f"  {emoji} {m} | {d['trades']:>3} trades | ${d['pnl']:>+10,.2f} ({pct:>+6.1f}%) | {wr:>4.0f}% WR")

        if d['pnl'] > 0:
            positive += 1
        if pct >= 10:
            target_months += 1

    print(f"\n  Avg Monthly: {np.mean(returns):+.2f}%")
    print(f"  Best: {max(returns):+.2f}%")
    print(f"  Worst: {min(returns):+.2f}%")
    print(f"  Positive: {positive}/{len(monthly_pnl)} ({positive/len(monthly_pnl)*100:.0f}%)")
    print(f"  🎯 Months >= 10%: {target_months}/{len(monthly_pnl)}")

    final_value = initial_capital + total_pnl
    print(f"\n🏆 FINAL: ${initial_capital:,.0f} → ${final_value:,.0f} ({(final_value/initial_capital-1)*100:+.1f}%)")

    return {
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_monthly': np.mean(returns),
        'target_months': target_months,
        'months': len(monthly_pnl),
    }


def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--backtest':
        backtest_aggressive_system()
    else:
        system = AggressiveCatalystSystem()
        system.generate_trading_signals()


if __name__ == '__main__':
    main()
