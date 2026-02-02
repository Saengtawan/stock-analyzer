#!/usr/bin/env python3
"""
============================================================================
FULL REALISTIC BACKTEST - $4,000 CAPITAL + PDT TRACKING
============================================================================

100% Realistic simulation matching live trading:
1. Capital: $4,000 (matching SIMULATED_CAPITAL)
2. Position size: 40% = $1,600 per trade
3. Integer shares (no fractional)
4. PDT tracking (max 3 day trades / 5 days)
5. All v3.9 parameters

Run time: 5-10 minutes (full 6-month simulation)
============================================================================
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import deque
import json
import warnings
import sys
import os
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


# ============================================================================
# CONFIGURATION - MATCH PRODUCTION + $4,000 CAPITAL
# ============================================================================
class Config:
    """Configuration matching production with realistic capital"""

    # Backtest period
    MONTHS_BACK = 6

    # Capital management - REALISTIC
    STARTING_CAPITAL = 4000  # $4,000 = ~125,000 THB
    MAX_POSITIONS = 2
    POSITION_SIZE_PCT = 40   # 40% = $1,600 per position

    # Trade management
    MAX_HOLD_DAYS = 5

    # Trailing stop (v3.9)
    TRAIL_ACTIVATION_PCT = 2.0
    TRAIL_PERCENT = 70

    # Screening
    MIN_SCORE = 90
    MIN_ATR_PCT = 2.5
    BASE_SL_PCT = 2.5
    MAX_SL_PCT = 2.5
    BASE_TP_PCT = 6.0

    # PDT Rule
    PDT_DAY_TRADE_LIMIT = 3
    PDT_ROLLING_DAYS = 5

    # Sector scoring (v3.7)
    SECTOR_BULL_BONUS = 5
    SECTOR_BEAR_PENALTY = -10


# ============================================================================
# SECTOR ETF MAPPING
# ============================================================================
SECTOR_ETFS = {
    'XLK': 'Technology', 'XLE': 'Energy', 'XLF': 'Financial Services',
    'XLV': 'Healthcare', 'XLY': 'Consumer Cyclical', 'XLP': 'Consumer Defensive',
    'XLI': 'Industrials', 'XLU': 'Utilities', 'XLB': 'Basic Materials',
    'XLC': 'Communication Services', 'XLRE': 'Real Estate'
}

SECTOR_TO_ETF = {
    'Technology': 'XLK', 'Energy': 'XLE', 'Financial Services': 'XLF',
    'Healthcare': 'XLV', 'Consumer Cyclical': 'XLY', 'Consumer Defensive': 'XLP',
    'Industrials': 'XLI', 'Utilities': 'XLU', 'Basic Materials': 'XLB',
    'Communication Services': 'XLC', 'Real Estate': 'XLRE',
    'Financial': 'XLF', 'Financials': 'XLF', 'Consumer Discretionary': 'XLY',
    'Consumer Staples': 'XLP', 'Materials': 'XLB', 'Communications': 'XLC',
}


# ============================================================================
# STOCK UNIVERSE (High-beta tech + financials)
# ============================================================================
UNIVERSE = [
    # Tech
    'NVDA', 'AMD', 'TSLA', 'META', 'GOOGL', 'AMZN', 'MSFT', 'AAPL',
    'AVGO', 'MU', 'QCOM', 'AMAT', 'LRCX', 'KLAC', 'MRVL', 'ON', 'NXPI',
    'CRM', 'NOW', 'SNOW', 'PLTR', 'DDOG', 'NET', 'CRWD', 'ZS', 'PANW',
    'SHOP', 'PYPL', 'COIN', 'AFRM', 'UPST', 'HOOD', 'SOFI',
    'ABNB', 'UBER', 'LYFT', 'DASH', 'RBLX', 'U',
    'ZM', 'DOCU', 'TEAM', 'MDB', 'OKTA', 'TWLO', 'SNAP',
    # Semis
    'SMCI', 'ARM', 'TSM', 'ASML', 'INTC', 'TXN', 'ADI',
    # Financials
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'SCHW', 'BLK', 'AXP',
    'V', 'MA', 'COF', 'DFS', 'SYF',
    # Consumer
    'NKE', 'LULU', 'SBUX', 'MCD', 'HD', 'LOW',
    # High-beta
    'ROKU', 'PATH', 'S', 'BILL', 'CFLT', 'CHWY', 'DXCM',
]


# ============================================================================
# DATA CLASSES
# ============================================================================
@dataclass
class Position:
    symbol: str
    entry_date: datetime
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    peak_price: float
    trailing_active: bool = False


@dataclass
class Trade:
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    days_held: int
    is_day_trade: bool


# ============================================================================
# PDT TRACKER
# ============================================================================
class PDTTracker:
    """Track Pattern Day Trades (rolling 5 days)"""

    def __init__(self, limit: int = 3, rolling_days: int = 5):
        self.limit = limit
        self.rolling_days = rolling_days
        self.day_trades: deque = deque()  # List of (date, symbol)
        self.blocked_dates: List[datetime] = []

    def add_day_trade(self, date: datetime, symbol: str):
        """Record a day trade"""
        self.day_trades.append((date, symbol))
        self._cleanup(date)

    def _cleanup(self, current_date: datetime):
        """Remove day trades older than rolling period"""
        cutoff = current_date - timedelta(days=self.rolling_days)
        while self.day_trades and self.day_trades[0][0] < cutoff:
            self.day_trades.popleft()

    def get_count(self, date: datetime) -> int:
        """Get current day trade count"""
        self._cleanup(date)
        return len(self.day_trades)

    def can_trade(self, date: datetime) -> Tuple[bool, str]:
        """Check if can make new trades without PDT violation"""
        count = self.get_count(date)
        if count >= self.limit:
            self.blocked_dates.append(date)
            return False, f"PDT limit: {count}/{self.limit}"
        return True, f"PDT OK: {count}/{self.limit}"

    def get_stats(self) -> Dict:
        return {
            'total_day_trades': len(self.day_trades),
            'blocked_dates': len(self.blocked_dates),
            'day_trade_list': [(str(d), s) for d, s in self.day_trades]
        }


# ============================================================================
# BACKTEST ENGINE
# ============================================================================
class RealisticBacktest:
    def __init__(self):
        self.capital = Config.STARTING_CAPITAL
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.pdt_tracker = PDTTracker(Config.PDT_DAY_TRADE_LIMIT, Config.PDT_ROLLING_DAYS)
        self.daily_pnl: Dict[str, float] = {}
        self.price_data: Dict[str, pd.DataFrame] = {}
        self.sector_data: Dict[str, pd.DataFrame] = {}

    def load_data(self, end_date: datetime):
        """Load all price data"""
        start_date = end_date - timedelta(days=Config.MONTHS_BACK * 30 + 60)

        print(f"Loading data for {len(UNIVERSE)} stocks...")

        # Load stock data
        for symbol in UNIVERSE:
            try:
                df = yf.download(symbol, start=start_date, end=end_date, progress=False)
                if len(df) > 20:
                    self.price_data[symbol] = df
            except:
                pass

        print(f"Loaded {len(self.price_data)} stocks")

        # Load sector ETFs
        print("Loading sector ETFs...")
        for etf in SECTOR_ETFS.keys():
            try:
                df = yf.download(etf, start=start_date, end=end_date, progress=False)
                if len(df) > 20:
                    self.sector_data[etf] = df
            except:
                pass

        print(f"Loaded {len(self.sector_data)} sector ETFs")

    def get_sector_regime(self, symbol: str, date: datetime) -> str:
        """Get sector regime for a stock"""
        # Simplified: use XLK for tech, XLF for financials
        if symbol in ['JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'SCHW', 'V', 'MA']:
            etf = 'XLF'
        else:
            etf = 'XLK'

        if etf not in self.sector_data:
            return 'SIDEWAYS'

        df = self.sector_data[etf]
        df = df[df.index <= pd.Timestamp(date)]
        if len(df) < 20:
            return 'SIDEWAYS'

        ret_20d = float((df['Close'].iloc[-1] / df['Close'].iloc[-20] - 1) * 100)
        if ret_20d > 3:
            return 'BULL'
        elif ret_20d < -3:
            return 'BEAR'
        return 'SIDEWAYS'

    def screen_stock(self, symbol: str, date: datetime) -> Optional[Dict]:
        """Screen a stock using v3.9 criteria"""
        if symbol not in self.price_data:
            return None

        df = self.price_data[symbol]
        df = df[df.index <= pd.Timestamp(date)]

        if len(df) < 30:
            return None

        # Get values
        close = df['Close']
        open_price = df['Open']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        current_price = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        today_open = float(open_price.iloc[-1])

        # Price filter
        if current_price < 10 or current_price > 2000:
            return None

        # Yesterday's move (must be down >= -1%)
        yesterday_move = float((close.iloc[-2] / close.iloc[-3] - 1) * 100)
        if yesterday_move > -1.0:
            return None

        # Today's move (not falling further)
        today_move = float((current_price / prev_close - 1) * 100)
        if today_move < -1.0:
            return None

        # Bounce confirmation
        today_is_green = current_price > today_open
        if not today_is_green and today_move < 0.5:
            return None

        # Gap filter
        gap_pct = (today_open - prev_close) / prev_close * 100
        if gap_pct > 2.0:
            return None

        # SMA20 filter (ROOT CAUSE FIX)
        sma20 = float(close.rolling(20).mean().iloc[-1])
        if current_price < sma20:
            return None

        # v3.10: OVEREXTENDED FILTER (ARM FIX)
        # Calculate max single-day move in last 10 days (extended window)
        if len(close) >= 11:
            daily_returns = [(float(close.iloc[i]) / float(close.iloc[i-1]) - 1) * 100
                           for i in range(-10, 0)]
            max_daily_move = max(daily_returns)
        else:
            max_daily_move = 0

        # Skip if any day had >8% move (overextended)
        if max_daily_move > 8.0:
            return None

        # Skip if >10% above SMA20 (too extended)
        sma20_extension = ((current_price / sma20) - 1) * 100
        if sma20_extension > 10.0:
            return None

        # SMA5 extension filter
        sma5 = float(close.rolling(5).mean().iloc[-1])
        if current_price > sma5 * 1.02:
            return None

        # ATR filter
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = (atr / current_price) * 100
        if atr_pct < Config.MIN_ATR_PCT:
            return None

        # Calculate RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        gain_val = float(gain.iloc[-1])
        loss_val = float(loss.iloc[-1])
        rs = gain_val / loss_val if loss_val != 0 else 100
        rsi = float(100 - (100 / (1 + rs)))

        # 5-day momentum
        mom_5d = float((current_price / float(close.iloc[-6]) - 1) * 100)

        # Scoring
        score = 0

        # Bounce confirmation (40 pts max)
        if today_is_green and today_move > 0.5:
            score += 40
        elif today_is_green or today_move > 0.3:
            score += 25

        # Prior dip (40 pts max)
        if -12 <= mom_5d <= -5:
            score += 40
        elif -5 < mom_5d <= -3:
            score += 30
        elif -3 < mom_5d < 0:
            score += 15

        # Yesterday dip (15 pts max)
        if yesterday_move <= -3:
            score += 15
        elif yesterday_move <= -1.5:
            score += 10
        elif yesterday_move <= -1:
            score += 5

        # RSI (15 pts max)
        if rsi < 35:
            score += 15
        elif rsi < 45:
            score += 10

        # Trend context
        sma50 = float(close.rolling(50).mean().iloc[-1])
        if current_price > sma20:
            score += 10
            if current_price > sma50:
                score += 5

        # Sector bonus
        regime = self.get_sector_regime(symbol, date)
        if regime == 'BULL':
            score += Config.SECTOR_BULL_BONUS
        elif regime == 'BEAR':
            score += Config.SECTOR_BEAR_PENALTY

        # Volume surge
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        if float(volume.iloc[-1]) > avg_vol * 1.5:
            score += 10

        score = min(100, max(0, score))

        if score < Config.MIN_SCORE:
            return None

        # Calculate SL/TP
        sl_price = current_price * (1 - Config.BASE_SL_PCT / 100)
        tp_price = current_price * (1 + Config.BASE_TP_PCT / 100)

        return {
            'symbol': symbol,
            'price': current_price,
            'score': score,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'rsi': rsi,
            'atr_pct': atr_pct,
            'regime': regime
        }

    def execute_entry(self, signal: Dict, date: datetime) -> bool:
        """Execute entry with realistic position sizing"""
        symbol = signal['symbol']
        price = signal['price']

        # Calculate position size
        position_value = self.capital * (Config.POSITION_SIZE_PCT / 100)
        shares = int(position_value / price)

        if shares <= 0:
            return False

        # Check if enough capital
        cost = shares * price
        if cost > self.capital * 0.95:  # Keep 5% buffer
            return False

        # Create position
        self.positions[symbol] = Position(
            symbol=symbol,
            entry_date=date,
            entry_price=price,
            shares=shares,
            stop_loss=signal['sl_price'],
            take_profit=signal['tp_price'],
            peak_price=price,
            trailing_active=False
        )

        self.capital -= cost

        return True

    def update_positions(self, date: datetime):
        """Update all positions (check SL/TP/Trailing)"""
        closed = []

        for symbol, pos in self.positions.items():
            if symbol not in self.price_data:
                continue

            df = self.price_data[symbol]
            df = df[df.index <= pd.Timestamp(date)]
            if len(df) == 0:
                continue

            current_high = float(df['High'].iloc[-1])
            current_low = float(df['Low'].iloc[-1])
            current_close = float(df['Close'].iloc[-1])
            days_held = (date - pos.entry_date).days

            exit_reason = None
            exit_price = None

            # Update peak for trailing
            if current_high > pos.peak_price:
                pos.peak_price = current_high

            # Check trailing activation
            gain_pct = ((pos.peak_price - pos.entry_price) / pos.entry_price) * 100
            if not pos.trailing_active and gain_pct >= Config.TRAIL_ACTIVATION_PCT:
                pos.trailing_active = True
                # Update SL to trail
                trail_sl = pos.entry_price + (pos.peak_price - pos.entry_price) * (Config.TRAIL_PERCENT / 100)
                if trail_sl > pos.stop_loss:
                    pos.stop_loss = trail_sl

            # Update trailing SL if active
            if pos.trailing_active:
                trail_sl = pos.entry_price + (pos.peak_price - pos.entry_price) * (Config.TRAIL_PERCENT / 100)
                if trail_sl > pos.stop_loss:
                    pos.stop_loss = trail_sl

            # Check SL hit (use low)
            if current_low <= pos.stop_loss:
                exit_reason = 'SL'
                exit_price = pos.stop_loss

            # Check TP hit (use high)
            elif current_high >= pos.take_profit:
                exit_reason = 'TP'
                exit_price = pos.take_profit

            # Check max hold days
            elif days_held >= Config.MAX_HOLD_DAYS:
                exit_reason = 'MAX_DAYS'
                exit_price = current_close

            if exit_reason:
                pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
                pnl_usd = (exit_price - pos.entry_price) * pos.shares
                is_day_trade = (date.date() == pos.entry_date.date())

                trade = Trade(
                    symbol=symbol,
                    entry_date=pos.entry_date,
                    exit_date=date,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    shares=pos.shares,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    exit_reason=exit_reason,
                    days_held=days_held,
                    is_day_trade=is_day_trade
                )
                self.trades.append(trade)
                self.capital += pos.shares * exit_price

                # Track PDT
                if is_day_trade:
                    self.pdt_tracker.add_day_trade(date, symbol)

                closed.append(symbol)

        # Remove closed positions
        for symbol in closed:
            del self.positions[symbol]

    def run(self):
        """Run full backtest"""
        print("=" * 70)
        print("FULL REALISTIC BACKTEST - $4,000 CAPITAL + PDT TRACKING")
        print("=" * 70)
        print()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=Config.MONTHS_BACK * 30)

        # Load data
        self.load_data(end_date)

        # Get trading days
        if 'AAPL' in self.price_data:
            trading_days = self.price_data['AAPL'].index
            trading_days = trading_days[(trading_days >= pd.Timestamp(start_date)) &
                                        (trading_days <= pd.Timestamp(end_date))]
        else:
            print("ERROR: Could not load AAPL for trading days")
            return

        print(f"\nBacktest period: {start_date.date()} to {end_date.date()}")
        print(f"Trading days: {len(trading_days)}")
        print(f"Starting capital: ${Config.STARTING_CAPITAL:,}")
        print()
        print("Running simulation...")

        # Simulate each day
        for i, day in enumerate(trading_days):
            date = day.to_pydatetime()

            # Update existing positions
            self.update_positions(date)

            # Record daily P&L
            portfolio_value = self.capital
            for symbol, pos in self.positions.items():
                if symbol in self.price_data:
                    df = self.price_data[symbol]
                    df = df[df.index <= pd.Timestamp(date)]
                    if len(df) > 0:
                        portfolio_value += pos.shares * float(df['Close'].iloc[-1])

            self.daily_pnl[str(date.date())] = portfolio_value

            # Only scan on Mondays (simulate weekly rotation)
            if date.weekday() != 0:
                continue

            # Check PDT
            can_trade, pdt_msg = self.pdt_tracker.can_trade(date)
            if not can_trade:
                continue

            # Scan for signals
            if len(self.positions) < Config.MAX_POSITIONS:
                signals = []
                for symbol in self.price_data.keys():
                    if symbol in self.positions:
                        continue
                    signal = self.screen_stock(symbol, date)
                    if signal:
                        signals.append(signal)

                # Sort by score
                signals.sort(key=lambda x: x['score'], reverse=True)

                # Execute top signals
                for signal in signals[:Config.MAX_POSITIONS - len(self.positions)]:
                    self.execute_entry(signal, date)

            # Progress
            if i % 20 == 0:
                pct = (i / len(trading_days)) * 100
                print(f"  Progress: {pct:.0f}% ({len(self.trades)} trades)")

        # Close remaining positions at end
        for symbol, pos in list(self.positions.items()):
            if symbol in self.price_data:
                df = self.price_data[symbol]
                exit_price = float(df['Close'].iloc[-1])
                days_held = (end_date - pos.entry_date).days
                pnl_pct = float((exit_price - pos.entry_price) / pos.entry_price * 100)
                pnl_usd = float((exit_price - pos.entry_price) * pos.shares)

                self.trades.append(Trade(
                    symbol=symbol,
                    entry_date=pos.entry_date,
                    exit_date=end_date,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    shares=pos.shares,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    exit_reason='END',
                    days_held=days_held,
                    is_day_trade=False
                ))
                self.capital += pos.shares * exit_price

        self.print_results()

    def print_results(self):
        """Print comprehensive results"""
        print()
        print("=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)

        # Capital
        final_capital = self.capital
        total_return = ((final_capital - Config.STARTING_CAPITAL) / Config.STARTING_CAPITAL) * 100

        print(f"\n{'CAPITAL':^70}")
        print("-" * 70)
        print(f"Starting:     ${Config.STARTING_CAPITAL:,.2f}")
        print(f"Final:        ${final_capital:,.2f}")
        print(f"Total Return: {total_return:+.2f}%")

        # Trade stats
        if self.trades:
            winners = [t for t in self.trades if t.pnl_pct > 0]
            losers = [t for t in self.trades if t.pnl_pct <= 0]
            win_rate = len(winners) / len(self.trades) * 100

            avg_win = np.mean([t.pnl_pct for t in winners]) if winners else 0
            avg_loss = np.mean([t.pnl_pct for t in losers]) if losers else 0
            avg_days = np.mean([t.days_held for t in self.trades])

            print(f"\n{'TRADES':^70}")
            print("-" * 70)
            print(f"Total Trades: {len(self.trades)}")
            print(f"Winners:      {len(winners)} ({win_rate:.1f}%)")
            print(f"Losers:       {len(losers)} ({100-win_rate:.1f}%)")
            print(f"Avg Win:      {avg_win:+.2f}%")
            print(f"Avg Loss:     {avg_loss:+.2f}%")
            print(f"Avg Days:     {avg_days:.1f}")

            # PDT stats
            day_trades = [t for t in self.trades if t.is_day_trade]
            print(f"\n{'PDT TRACKING':^70}")
            print("-" * 70)
            print(f"Day Trades:   {len(day_trades)}")
            print(f"PDT Blocked:  {len(self.pdt_tracker.blocked_dates)} times")

            if day_trades:
                print(f"\nDay Trade Details:")
                for t in day_trades:
                    print(f"  {t.entry_date.date()} {t.symbol}: {t.pnl_pct:+.2f}% ({t.exit_reason})")

            # Position sizing
            print(f"\n{'POSITION SIZING':^70}")
            print("-" * 70)
            print(f"Position Size: ${Config.STARTING_CAPITAL * Config.POSITION_SIZE_PCT / 100:,.0f} (40%)")
            avg_shares = np.mean([t.shares for t in self.trades])
            avg_position = np.mean([t.shares * t.entry_price for t in self.trades])
            print(f"Avg Shares:   {avg_shares:.0f}")
            print(f"Avg Position: ${avg_position:,.0f}")

            # Monthly breakdown
            print(f"\n{'MONTHLY BREAKDOWN':^70}")
            print("-" * 70)
            print(f"{'Month':<12} {'Trades':>8} {'WinRate':>10} {'Return':>10}")
            print("-" * 70)

            monthly_trades = {}
            for t in self.trades:
                month = t.exit_date.strftime('%Y-%m')
                if month not in monthly_trades:
                    monthly_trades[month] = []
                monthly_trades[month].append(t)

            monthly_returns = []
            for month in sorted(monthly_trades.keys()):
                trades = monthly_trades[month]
                wins = sum(1 for t in trades if t.pnl_pct > 0)
                wr = wins / len(trades) * 100 if trades else 0
                ret = sum(t.pnl_pct for t in trades)
                monthly_returns.append(ret)
                print(f"{month:<12} {len(trades):>8} {wr:>9.1f}% {ret:>+9.2f}%")

            print("-" * 70)
            if monthly_returns:
                avg_monthly = np.mean(monthly_returns)
                positive_months = sum(1 for r in monthly_returns if r > 0)
                print(f"{'MONTHLY AVG':<12} {'':<8} {'':<10} {avg_monthly:>+9.2f}%")
                print(f"Positive Months: {positive_months}/{len(monthly_returns)}")

            # Top/Worst trades
            print(f"\n{'TOP 5 TRADES':^70}")
            print("-" * 70)
            sorted_trades = sorted(self.trades, key=lambda x: x.pnl_pct, reverse=True)
            for t in sorted_trades[:5]:
                print(f"  {t.symbol}: {t.pnl_pct:+.2f}% (${t.pnl_usd:+.2f}) - {t.days_held}d")

            print(f"\n{'WORST 5 TRADES':^70}")
            print("-" * 70)
            for t in sorted_trades[-5:]:
                print(f"  {t.symbol}: {t.pnl_pct:+.2f}% (${t.pnl_usd:+.2f}) - {t.days_held}d")

        # Save results
        results = {
            'config': {
                'starting_capital': Config.STARTING_CAPITAL,
                'position_size_pct': Config.POSITION_SIZE_PCT,
                'max_positions': Config.MAX_POSITIONS,
                'trail_activation': Config.TRAIL_ACTIVATION_PCT,
                'trail_percent': Config.TRAIL_PERCENT,
            },
            'results': {
                'final_capital': final_capital,
                'total_return': total_return,
                'total_trades': len(self.trades),
                'win_rate': win_rate if self.trades else 0,
                'day_trades': len([t for t in self.trades if t.is_day_trade]),
            },
            'trades': [asdict(t) for t in self.trades],
            'pdt_stats': self.pdt_tracker.get_stats(),
        }

        # Convert datetime to string for JSON
        for t in results['trades']:
            t['entry_date'] = str(t['entry_date'])
            t['exit_date'] = str(t['exit_date'])

        filename = f"realistic_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {filename}")

        print()
        print("=" * 70)
        print("BACKTEST COMPLETE")
        print("=" * 70)


if __name__ == "__main__":
    bt = RealisticBacktest()
    bt.run()
