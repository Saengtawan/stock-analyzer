#!/usr/bin/env python3
"""
RAPID TRADER OPTIMIZER
Goal: Achieve 5-15% monthly profit with minimal losers

This script will:
1. Analyze current system performance
2. Find root causes of losses
3. Implement and test improvements iteratively
4. Keep optimizing until target is reached
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import json
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
START_DATE = datetime(2025, 9, 1)
END_DATE = datetime(2026, 1, 31)
INITIAL_CAPITAL = 100000
MAX_POSITION_SIZE = 0.1  # 10% per position
MAX_POSITIONS = 5

@dataclass
class Trade:
    symbol: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    stop_loss: float = 0
    take_profit: float = 0
    pnl_pct: float = 0
    exit_reason: str = ""
    hold_days: int = 0
    score: int = 0

    # Entry conditions
    rsi: float = 0
    mom_1d: float = 0
    mom_5d: float = 0
    gap_pct: float = 0
    atr_pct: float = 0
    volume_ratio: float = 0
    distance_from_high: float = 0


class RapidTraderBacktester:
    """Backtest engine for Rapid Trader"""

    def __init__(self, config: Dict):
        self.config = config
        self.trades: List[Trade] = []
        self.data_cache: Dict[str, pd.DataFrame] = {}

    def load_data(self, symbols: List[str]) -> None:
        """Load historical data for all symbols"""
        print(f"Loading data for {len(symbols)} symbols...")

        def fetch_one(symbol):
            try:
                df = yf.download(symbol, start=START_DATE - timedelta(days=60),
                               end=END_DATE + timedelta(days=1), progress=False)
                if len(df) > 20:
                    return symbol, df
            except:
                pass
            return symbol, None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_one, s): s for s in symbols}
            for future in as_completed(futures):
                symbol, df = future.result()
                if df is not None:
                    self.data_cache[symbol] = df

        print(f"Loaded {len(self.data_cache)} symbols")

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        df = df.copy()

        # Price changes
        df['pct_change'] = df['Close'].pct_change() * 100
        df['gap_pct'] = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1) * 100

        # Momentum
        df['mom_1d'] = df['Close'].pct_change(1) * 100
        df['mom_5d'] = df['Close'].pct_change(5) * 100
        df['mom_20d'] = df['Close'].pct_change(20) * 100

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_pct'] = df['atr'] / df['Close'] * 100

        # Moving averages
        df['sma5'] = df['Close'].rolling(5).mean()
        df['sma20'] = df['Close'].rolling(20).mean()
        df['sma50'] = df['Close'].rolling(50).mean()

        # Volume
        df['vol_sma20'] = df['Volume'].rolling(20).mean()
        df['volume_ratio'] = df['Volume'] / df['vol_sma20']

        # 52-week high distance
        df['high_52w'] = df['High'].rolling(252).max()
        df['distance_from_high'] = (df['high_52w'] - df['Close']) / df['high_52w'] * 100

        return df

    def check_entry_signal(self, df: pd.DataFrame, date: datetime, config: Dict) -> Optional[Dict]:
        """Check if entry conditions are met"""
        try:
            idx = df.index.get_loc(date)
            if idx < 30:
                return None

            row = df.iloc[idx]
            prev = df.iloc[idx-1]

            # Basic data validation
            if pd.isna(row['Close']) or row['Close'] <= 0:
                return None

            # === ENTRY FILTERS ===

            # 1. TRUE DIP - Must be down today
            if row['mom_1d'] > config.get('max_mom_1d', 0):
                return None

            # 2. NO GAP UP - Avoid gap traps
            if row['gap_pct'] > config.get('max_gap_pct', 1.5):
                return None

            # 3. BELOW SMA5 - Confirm pullback
            if config.get('require_below_sma5', True):
                if row['Close'] > row['sma5'] * 1.01:
                    return None

            # 4. RSI FILTER - Not overbought
            if row['rsi'] > config.get('max_rsi', 70):
                return None

            # 5. MINIMUM PULLBACK - Need some dip
            if row['mom_5d'] > config.get('max_mom_5d', 2):
                return None

            # 6. UPTREND FILTER - Only buy in uptrends
            if config.get('require_uptrend', True):
                if row['sma20'] < row['sma50']:
                    return None

            # 7. VOLATILITY FILTER - Need some movement
            if row['atr_pct'] < config.get('min_atr_pct', 1.5):
                return None
            if row['atr_pct'] > config.get('max_atr_pct', 8):
                return None

            # 8. VOLUME FILTER - Need liquidity
            if row['volume_ratio'] < config.get('min_volume_ratio', 0.5):
                return None

            # 9. DISTANCE FROM HIGH - Room to recover
            if row['distance_from_high'] < config.get('min_distance_high', 3):
                return None
            if row['distance_from_high'] > config.get('max_distance_high', 30):
                return None

            # 10. OVERSOLD BONUS
            score = 50
            if row['rsi'] < 35:
                score += 20
            elif row['rsi'] < 45:
                score += 10

            # 11. DIP STRENGTH BONUS
            if row['mom_5d'] < -5:
                score += 15
            elif row['mom_5d'] < -3:
                score += 10

            # 12. UPTREND STRENGTH
            if row['mom_20d'] > 10:
                score += 15
            elif row['mom_20d'] > 5:
                score += 10

            # Calculate stop loss and take profit
            atr_mult = config.get('atr_sl_multiplier', 1.0)
            min_sl = config.get('min_stop_loss', 1.5)
            max_sl = config.get('max_stop_loss', 2.5)

            sl_pct = min(max(row['atr_pct'] * atr_mult, min_sl), max_sl)
            tp_pct = sl_pct * config.get('risk_reward', 2.5)

            return {
                'price': row['Close'],
                'stop_loss': row['Close'] * (1 - sl_pct / 100),
                'take_profit': row['Close'] * (1 + tp_pct / 100),
                'sl_pct': sl_pct,
                'tp_pct': tp_pct,
                'score': score,
                'rsi': row['rsi'],
                'mom_1d': row['mom_1d'],
                'mom_5d': row['mom_5d'],
                'gap_pct': row['gap_pct'],
                'atr_pct': row['atr_pct'],
                'volume_ratio': row['volume_ratio'],
                'distance_from_high': row['distance_from_high'],
            }

        except Exception as e:
            return None

    def simulate_trade(self, symbol: str, entry_date: datetime,
                      entry_signal: Dict, config: Dict) -> Trade:
        """Simulate a single trade"""
        df = self.data_cache[symbol]

        trade = Trade(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_signal['price'],
            stop_loss=entry_signal['stop_loss'],
            take_profit=entry_signal['take_profit'],
            score=entry_signal['score'],
            rsi=entry_signal['rsi'],
            mom_1d=entry_signal['mom_1d'],
            mom_5d=entry_signal['mom_5d'],
            gap_pct=entry_signal['gap_pct'],
            atr_pct=entry_signal['atr_pct'],
            volume_ratio=entry_signal['volume_ratio'],
            distance_from_high=entry_signal['distance_from_high'],
        )

        max_hold = config.get('max_hold_days', 5)

        try:
            entry_idx = df.index.get_loc(entry_date)

            for i in range(1, max_hold + 1):
                if entry_idx + i >= len(df):
                    break

                day = df.iloc[entry_idx + i]

                # Check stop loss (use Low for intraday)
                if day['Low'] <= trade.stop_loss:
                    trade.exit_date = day.name
                    trade.exit_price = trade.stop_loss
                    trade.exit_reason = "STOP_LOSS"
                    trade.hold_days = i
                    break

                # Check take profit (use High for intraday)
                if day['High'] >= trade.take_profit:
                    trade.exit_date = day.name
                    trade.exit_price = trade.take_profit
                    trade.exit_reason = "TAKE_PROFIT"
                    trade.hold_days = i
                    break

                # Time-based exit
                if i >= max_hold:
                    trade.exit_date = day.name
                    trade.exit_price = day['Close']
                    trade.exit_reason = "TIME_EXIT"
                    trade.hold_days = i
                    break

            # Calculate P&L
            if trade.exit_price:
                trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100

        except Exception as e:
            pass

        return trade

    def run_backtest(self, symbols: List[str], config: Dict) -> Dict:
        """Run full backtest"""
        self.trades = []

        # Generate trading days
        trading_days = pd.date_range(start=START_DATE, end=END_DATE, freq='B')

        for date in trading_days:
            date = pd.Timestamp(date)

            # Find entry signals
            signals = []
            for symbol in symbols:
                if symbol not in self.data_cache:
                    continue
                df = self.data_cache[symbol]
                if date not in df.index:
                    continue

                signal = self.check_entry_signal(df, date, config)
                if signal:
                    signals.append((symbol, signal))

            # Sort by score and take top picks
            signals.sort(key=lambda x: x[1]['score'], reverse=True)

            for symbol, signal in signals[:config.get('max_daily_trades', 3)]:
                trade = self.simulate_trade(symbol, date, signal, config)
                if trade.exit_price:
                    self.trades.append(trade)

        return self.analyze_results()

    def analyze_results(self) -> Dict:
        """Analyze backtest results"""
        if not self.trades:
            return {'error': 'No trades'}

        df = pd.DataFrame([{
            'symbol': t.symbol,
            'entry_date': t.entry_date,
            'exit_date': t.exit_date,
            'entry_price': t.entry_price,
            'exit_price': t.exit_price,
            'pnl_pct': t.pnl_pct,
            'exit_reason': t.exit_reason,
            'hold_days': t.hold_days,
            'score': t.score,
            'rsi': t.rsi,
            'mom_1d': t.mom_1d,
            'mom_5d': t.mom_5d,
            'atr_pct': t.atr_pct,
        } for t in self.trades])

        # Basic stats
        total_trades = len(df)
        winners = len(df[df['pnl_pct'] > 0])
        losers = len(df[df['pnl_pct'] <= 0])
        win_rate = winners / total_trades * 100 if total_trades > 0 else 0

        # P&L stats
        total_pnl = df['pnl_pct'].sum()
        avg_win = df[df['pnl_pct'] > 0]['pnl_pct'].mean() if winners > 0 else 0
        avg_loss = df[df['pnl_pct'] <= 0]['pnl_pct'].mean() if losers > 0 else 0

        # Monthly breakdown
        df['month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
        monthly = df.groupby('month').agg({
            'pnl_pct': ['sum', 'count'],
            'symbol': 'count'
        }).round(2)

        # Same-day stop loss (PDT risk)
        same_day_sl = len(df[(df['exit_reason'] == 'STOP_LOSS') & (df['hold_days'] <= 1)])

        # Exit reason breakdown
        exit_reasons = df['exit_reason'].value_counts().to_dict()

        return {
            'total_trades': total_trades,
            'winners': winners,
            'losers': losers,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'same_day_sl': same_day_sl,
            'same_day_sl_pct': same_day_sl / total_trades * 100 if total_trades > 0 else 0,
            'exit_reasons': exit_reasons,
            'monthly': monthly,
            'trades_df': df,
        }


def optimize_parameters():
    """Run optimization to find best parameters"""

    # Universe of stocks to test
    UNIVERSE = [
        # Large cap tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'CRM',
        'ADBE', 'NFLX', 'PYPL', 'SQ', 'SHOP', 'SNOW', 'PLTR', 'NET', 'DDOG', 'ZS',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
        'AMGN', 'GILD', 'ISRG', 'VRTX', 'REGN', 'MRNA', 'BIIB', 'ILMN', 'DXCM', 'ALGN',
        # Consumer
        'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'COST', 'LOW', 'TJX', 'ROST',
        'CMG', 'DG', 'DLTR', 'LULU', 'ULTA', 'ETSY', 'W', 'CHWY', 'DECK', 'CROX',
        # Financial
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'V', 'MA', 'BLK',
        # Industrial
        'CAT', 'DE', 'BA', 'HON', 'UNP', 'UPS', 'RTX', 'LMT', 'GE', 'MMM',
        # Energy
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'VLO', 'PSX', 'OXY', 'DVN',
    ]

    backtester = RapidTraderBacktester({})
    backtester.load_data(UNIVERSE)

    # Optimization iterations
    best_result = None
    best_config = None
    best_score = -float('inf')

    iteration = 0

    # Parameter ranges to explore
    param_grid = {
        'max_mom_1d': [-0.5, 0, 0.5],
        'max_gap_pct': [1.0, 1.5, 2.0],
        'max_rsi': [60, 65, 70],
        'max_mom_5d': [0, 2, 5],
        'min_atr_pct': [1.5, 2.0, 2.5],
        'max_atr_pct': [6, 8, 10],
        'atr_sl_multiplier': [0.8, 1.0, 1.2],
        'min_stop_loss': [1.5, 2.0],
        'max_stop_loss': [2.5, 3.0],
        'risk_reward': [2.0, 2.5, 3.0],
        'max_hold_days': [3, 5, 7],
        'min_distance_high': [3, 5, 8],
        'max_distance_high': [25, 30, 40],
    }

    # Start with base config
    base_config = {
        'max_mom_1d': 0,
        'max_gap_pct': 1.5,
        'require_below_sma5': True,
        'max_rsi': 65,
        'max_mom_5d': 2,
        'require_uptrend': True,
        'min_atr_pct': 2.0,
        'max_atr_pct': 8,
        'min_volume_ratio': 0.5,
        'min_distance_high': 5,
        'max_distance_high': 30,
        'atr_sl_multiplier': 1.0,
        'min_stop_loss': 1.5,
        'max_stop_loss': 2.5,
        'risk_reward': 2.5,
        'max_hold_days': 5,
        'max_daily_trades': 3,
    }

    print("=" * 70)
    print("  RAPID TRADER OPTIMIZER")
    print("  Goal: 5-15% monthly profit, minimal losers")
    print("=" * 70)
    print()

    # Test base config first
    print("Testing base configuration...")
    result = backtester.run_backtest(list(backtester.data_cache.keys()), base_config)

    # Initialize with base config
    best_config = base_config.copy()
    best_result = result

    if 'error' not in result:
        months = (END_DATE - START_DATE).days / 30
        monthly_pnl = result['total_pnl'] / months

        print(f"\nBase Results:")
        print(f"  Trades: {result['total_trades']}")
        print(f"  Win Rate: {result['win_rate']:.1f}%")
        print(f"  Total P&L: {result['total_pnl']:.1f}%")
        print(f"  Monthly P&L: {monthly_pnl:.1f}%")
        print(f"  Same-day SL: {result['same_day_sl']} ({result['same_day_sl_pct']:.1f}%)")

        # Score = monthly_pnl * win_rate - same_day_sl_penalty
        score = monthly_pnl * (result['win_rate'] / 100) - result['same_day_sl_pct']
        best_score = score
    else:
        print("Base config had error, using defaults...")

    # Iterative optimization
    print("\n" + "=" * 70)
    print("  STARTING OPTIMIZATION")
    print("=" * 70)

    # Try different parameter combinations
    import itertools

    # Focus on most impactful parameters
    key_params = ['max_mom_1d', 'max_rsi', 'risk_reward', 'max_hold_days', 'min_distance_high']

    for param in key_params:
        print(f"\nOptimizing: {param}")

        for value in param_grid.get(param, []):
            iteration += 1
            test_config = best_config.copy()
            test_config[param] = value

            result = backtester.run_backtest(list(backtester.data_cache.keys()), test_config)

            if 'error' in result:
                continue

            months = (END_DATE - START_DATE).days / 30
            monthly_pnl = result['total_pnl'] / months

            # Calculate score
            score = monthly_pnl * (result['win_rate'] / 100) - result['same_day_sl_pct']

            status = "  "
            if score > best_score:
                best_score = score
                best_result = result
                best_config = test_config.copy()
                status = "✓ "

            print(f"{status}[{iteration}] {param}={value}: "
                  f"Win={result['win_rate']:.0f}% "
                  f"Monthly={monthly_pnl:.1f}% "
                  f"PDT={result['same_day_sl_pct']:.0f}%")

    # Print final results
    print("\n" + "=" * 70)
    print("  OPTIMIZATION COMPLETE")
    print("=" * 70)

    if best_result:
        months = (END_DATE - START_DATE).days / 30
        monthly_pnl = best_result['total_pnl'] / months

        print(f"\nBest Configuration:")
        for k, v in best_config.items():
            print(f"  {k}: {v}")

        print(f"\nBest Results:")
        print(f"  Total Trades: {best_result['total_trades']}")
        print(f"  Winners: {best_result['winners']} ({best_result['win_rate']:.1f}%)")
        print(f"  Losers: {best_result['losers']}")
        print(f"  Total P&L: {best_result['total_pnl']:.1f}%")
        print(f"  Monthly P&L: {monthly_pnl:.1f}%")
        print(f"  Same-day SL: {best_result['same_day_sl']} ({best_result['same_day_sl_pct']:.1f}%)")
        print(f"  Avg Win: +{best_result['avg_win']:.1f}%")
        print(f"  Avg Loss: {best_result['avg_loss']:.1f}%")

        # Save best config
        with open('data/best_rapid_config.json', 'w') as f:
            json.dump(best_config, f, indent=2)

        return best_config, best_result

    return None, None


if __name__ == '__main__':
    best_config, best_result = optimize_parameters()
