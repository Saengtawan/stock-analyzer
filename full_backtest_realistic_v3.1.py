#!/usr/bin/env python3
"""
FULL REALISTIC BACKTEST v3.1 - HISTORICAL DATA CORRECT
=======================================================
FIXES the critical issue: Now uses HISTORICAL data for each simulated week.

Previous bug: Screener used datetime.now() so same stocks appeared every week.
Fix: Load historical data ending on simulation date.

Target: 5-10% monthly return
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json
import time
import warnings
warnings.filterwarnings('ignore')


@dataclass
class TradeRecord:
    """Complete trade record"""
    symbol: str
    sector: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_pct: float
    tp_pct: float
    score: int
    market_regime: str
    reasons: str
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    days_held: int = 0
    peak_pct: float = 0.0
    trough_pct: float = 0.0


class HistoricalScreener:
    """
    Screener that works with HISTORICAL data.
    Key difference: Uses data ending at simulation date, not today.
    """

    # Universe - use AI universe + fallback
    UNIVERSE = [
        # AI/Semiconductor (high volatility)
        'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
        'QCOM', 'AMAT', 'LRCX', 'KLAC', 'INTC', 'TXN', 'ADI', 'NXPI',
        # High beta tech
        'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG', 'NET', 'CRWD', 'ZS',
        'PANW', 'OKTA', 'MDB', 'ESTC', 'U', 'TTD', 'ZM',
        # Mega cap tech
        'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT', 'ORCL',
        # Cloud/SaaS
        'CRM', 'NOW', 'SHOP', 'SQ', 'PYPL', 'UBER', 'ABNB', 'DASH',
        # EV/Clean energy
        'RIVN', 'LCID', 'ENPH', 'FSLR', 'RUN', 'PLUG', 'BE',
        # Finance
        'JPM', 'GS', 'MS', 'V', 'MA', 'AXP', 'BAC', 'WFC', 'SCHW', 'BLK',
        # Industrial
        'CAT', 'DE', 'BA', 'GE', 'HON', 'RTX', 'LMT', 'UNP', 'UPS',
        # Consumer
        'NKE', 'LULU', 'SBUX', 'MCD', 'HD', 'LOW', 'TGT', 'COST', 'WMT',
        'BKNG', 'MAR', 'CMG', 'DPZ', 'YUM', 'DRI',
        # Healthcare
        'LLY', 'MRNA', 'REGN', 'VRTX', 'BIIB', 'GILD', 'ABBV',
        # Communications
        'DIS', 'CMCSA', 'T', 'VZ', 'TMUS',
        # Energy
        'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'OXY', 'MPC',
        # Additional high-beta
        'ROKU', 'SNAP', 'PINS', 'RBLX', 'MTCH', 'PTON', 'CHWY',
        'ETSY', 'WDAY', 'ADSK', 'SPLK', 'TEAM', 'DOCU', 'CFLT',
        'AI', 'PATH', 'S', 'BILL', 'GTLB', 'HUBS', 'VEEV',
        # Biotech
        'ISRG', 'DXCM', 'IDXX', 'ZBH', 'SYK', 'EW', 'BSX',
        # REITs
        'EQIX', 'AMT', 'CCI', 'PLD', 'SPG',
        # Materials
        'FCX', 'NEM', 'GOLD', 'CLF', 'X', 'AA',
    ]

    # v3.1 Parameters
    MIN_ATR_PCT = 2.0
    MIN_SCORE = 60
    BASE_TP_PCT = 4.0
    BASE_SL_PCT = 2.0

    def __init__(self):
        self.data_cache: Dict[str, pd.DataFrame] = {}

    def get_market_regime(self, end_date: datetime) -> str:
        """Get market regime AS OF specific date"""
        try:
            start = end_date - timedelta(days=40)
            ticker = yf.Ticker('SPY')
            hist = ticker.history(start=start, end=end_date + timedelta(days=1))

            if len(hist) < 20:
                return "UNKNOWN"

            # Filter to only data up to end_date
            hist = hist[hist.index.tz_localize(None) <= pd.Timestamp(end_date)]
            if len(hist) < 20:
                return "UNKNOWN"

            current = hist['Close'].iloc[-1]
            sma20 = hist['Close'].tail(20).mean()
            mom_5d = ((current / hist['Close'].iloc[-5]) - 1) * 100 if len(hist) >= 5 else 0

            if current > sma20 and mom_5d > -2:
                return "BULL"
            elif current < sma20 * 0.98:
                return "BEAR"
            else:
                return "NEUTRAL"
        except Exception as e:
            print(f"      Regime error: {e}")
            return "UNKNOWN"

    def load_historical_data(self, end_date: datetime, days: int = 60):
        """Load historical data ending at specific date"""
        self.data_cache = {}  # Clear cache

        start_date = end_date - timedelta(days=days + 10)

        loaded = 0
        failed = 0

        for symbol in self.UNIVERSE:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date + timedelta(days=1))

                # Filter to only data up to end_date (important for accurate simulation)
                if not hist.empty:
                    hist.index = hist.index.tz_localize(None)  # Remove timezone
                    hist = hist[hist.index <= pd.Timestamp(end_date)]

                if len(hist) >= 30:
                    hist.columns = [c.lower() for c in hist.columns]
                    self.data_cache[symbol] = hist
                    loaded += 1
            except Exception as e:
                failed += 1
                if failed <= 3:
                    print(f"      Warning: {symbol} - {e}")

            # Rate limiting
            if loaded % 30 == 0:
                time.sleep(0.5)

        return loaded

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50.0
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        if loss.iloc[-1] == 0:
            return 100.0
        rs = gain.iloc[-1] / loss.iloc[-1]
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR"""
        if len(data) < period + 1:
            return 0.0
        high = data['high']
        low = data['low']
        close = data['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(period).mean().iloc[-1]

    def screen(self, market_regime: str = "BULL") -> List[Dict]:
        """Screen for buy signals using historical data in cache"""
        if not self.data_cache:
            return []

        signals = []

        for symbol, data in self.data_cache.items():
            try:
                signal = self._analyze_stock(symbol, data, market_regime)
                if signal:
                    signals.append(signal)
            except Exception as e:
                pass

        # Sort by score
        signals.sort(key=lambda x: x['score'], reverse=True)
        return signals[:10]  # Top 10

    def _analyze_stock(self, symbol: str, data: pd.DataFrame, market_regime: str) -> Optional[Dict]:
        """Analyze a stock for v3.1 mean reversion signal"""
        if len(data) < 30:
            return None

        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']

        idx = len(data) - 1
        current_price = close.iloc[idx]

        # Skip penny stocks and very expensive stocks
        if current_price < 10 or current_price > 2000:
            return None

        # Calculate indicators
        rsi = self.calculate_rsi(close)
        atr = self.calculate_atr(data)
        if atr == 0:
            return None
        atr_pct = (atr / current_price) * 100

        # Momentum
        mom_1d = ((current_price / close.iloc[idx-1]) - 1) * 100 if idx >= 1 else 0
        mom_5d = ((current_price / close.iloc[idx-5]) - 1) * 100 if idx >= 5 else 0
        mom_20d = ((current_price / close.iloc[idx-20]) - 1) * 100 if idx >= 20 else 0

        # SMAs
        sma5 = close.iloc[-5:].mean()
        sma20 = close.iloc[-20:].mean() if len(close) >= 20 else close.mean()
        sma50 = close.iloc[-50:].mean() if len(close) >= 50 else close.mean()

        # Gap
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price
        open_price = data['open'].iloc[idx] if 'open' in data.columns else current_price
        gap_pct = ((open_price - prev_close) / prev_close) * 100

        # Distance from high
        high_20d = high.iloc[-20:].max() if len(high) >= 20 else high.max()
        dist_from_high = ((high_20d - current_price) / high_20d) * 100

        # Support
        support = low.iloc[-10:].min() if len(low) >= 10 else low.min()

        # Volume
        avg_volume = volume.iloc[-20:].mean() if len(volume) >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # ==============================
        # v3.1: MEAN REVERSION FILTERS
        # ==============================

        # FILTER 1: Must be TRUE DIP (price falling)
        if mom_1d > 0.5:
            return None

        # FILTER 2: Skip gap-up entries
        if gap_pct > 1.5:
            return None

        # FILTER 3: Must be below SMA5 (oversold zone)
        if current_price > sma5 * 1.01:
            return None

        # Minimum volatility
        if atr_pct < self.MIN_ATR_PCT:
            return None

        # ==============================
        # SCORING
        # ==============================
        score = 0
        reasons = []

        # 1. Pullback scoring
        if -8 <= mom_5d <= -3:
            score += 35
            reasons.append(f"Strong dip {mom_5d:.1f}%")
        elif -3 < mom_5d <= 0:
            score += 25
            reasons.append(f"Mild pullback {mom_5d:.1f}%")

        # 2. 1-day dip bonus
        if mom_1d <= -1.5:
            score += 15
            reasons.append(f"Today dip {mom_1d:.1f}%")

        # 3. RSI scoring
        if 30 <= rsi <= 45:
            score += 30
            reasons.append(f"Oversold RSI={rsi:.0f}")
        elif 45 < rsi <= 55:
            score += 20
            reasons.append(f"Neutral RSI={rsi:.0f}")
        elif rsi < 30:
            score += 15
            reasons.append(f"Very oversold RSI={rsi:.0f}")

        # 4. Trend scoring
        if current_price > sma50 and mom_20d > 0:
            score += 20
            reasons.append("Strong uptrend")
        elif current_price > sma20:
            score += 15
            reasons.append("Above SMA20")
        elif mom_20d > 5:
            score += 10
            reasons.append("Recovery mode")

        # 5. Volatility bonus
        if atr_pct > 4:
            score += 15
            reasons.append(f"High vol {atr_pct:.1f}%")
        elif atr_pct > 3:
            score += 10
            reasons.append(f"Good vol {atr_pct:.1f}%")

        # 6. Room to run
        if 5 <= dist_from_high <= 15:
            score += 10
            reasons.append(f"Room {dist_from_high:.0f}%")

        # 7. Volume confirmation
        if volume_ratio > 1.2:
            score += 5
            reasons.append("High volume")

        # Check minimum score
        if score < self.MIN_SCORE:
            return None

        # ==============================
        # CALCULATE SL/TP (ATR-based)
        # ==============================
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = self.BASE_TP_PCT * tp_multiplier

        # Dynamic SL based on ATR (v3.1: 2.0-3.0%)
        if atr_pct > 5:
            sl_pct = 3.0
        elif atr_pct > 4:
            sl_pct = 2.5
        elif atr_pct > 3:
            sl_pct = 2.25
        else:
            sl_pct = self.BASE_SL_PCT

        # Support consideration
        sl_from_support = ((current_price - support * 0.995) / current_price) * 100
        sl_pct = max(sl_pct, min(sl_from_support * 0.8, 3.0))

        stop_loss = current_price * (1 - sl_pct / 100)
        take_profit = current_price * (1 + tp_pct / 100)

        return {
            'symbol': symbol,
            'score': score,
            'entry_price': round(current_price, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'sl_pct': round(sl_pct, 2),
            'tp_pct': round(tp_pct, 2),
            'rsi': round(rsi, 1),
            'atr_pct': round(atr_pct, 2),
            'mom_1d': round(mom_1d, 2),
            'mom_5d': round(mom_5d, 2),
            'reasons': reasons,
            'market_regime': market_regime,
        }


class FullRealisticBacktest:
    """
    Full realistic backtest using HISTORICAL data for each week.
    """

    STARTING_CAPITAL = 10000
    MAX_POSITIONS = 3
    POSITION_SIZE_PCT = 30
    MAX_HOLD_DAYS = 4

    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.monthly_results: Dict = {}
        self.improvement_notes: List[str] = []
        self.capital = self.STARTING_CAPITAL
        self.screener = HistoricalScreener()

    def simulate_trade(self, signal: Dict, entry_date: datetime, position_size: float) -> Optional[TradeRecord]:
        """Simulate a single trade from entry to exit"""
        symbol = signal['symbol']
        entry_price = signal['entry_price']
        stop_loss = signal['stop_loss']
        take_profit = signal['take_profit']
        sl_pct = signal['sl_pct']
        tp_pct = signal['tp_pct']

        trade = TradeRecord(
            symbol=symbol,
            sector="Unknown",
            entry_date=entry_date.strftime('%Y-%m-%d'),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            score=signal['score'],
            market_regime=signal.get('market_regime', 'UNKNOWN'),
            reasons=', '.join(signal.get('reasons', [])[:3])
        )

        # Get price data AFTER entry for simulation
        try:
            end = entry_date + timedelta(days=15)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date, end=end)

            if hist.empty or len(hist) < 2:
                return None
        except Exception as e:
            return None

        peak_price = entry_price
        trough_price = entry_price

        for day_idx, (dt, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            high = row['High']
            low = row['Low']
            close = row['Close']

            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100
            close_pnl = ((close - entry_price) / entry_price) * 100

            # Check stop loss
            if low_pnl <= -sl_pct:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = -sl_pct
                trade.pnl_usd = position_size * (-sl_pct / 100)
                trade.days_held = day_idx
                break

            # Check take profit
            if high_pnl >= tp_pct:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = take_profit
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.pnl_usd = position_size * (tp_pct / 100)
                trade.days_held = day_idx
                break

            # Check max hold
            if day_idx >= self.MAX_HOLD_DAYS:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = close_pnl
                trade.pnl_usd = position_size * (close_pnl / 100)
                trade.days_held = day_idx
                break

        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trade.trough_pct = ((trough_price - entry_price) / entry_price) * 100

        if not trade.exit_date:
            return None

        return trade

    def run_backtest(self, months_back: int = 3):
        """Run full backtest over specified months"""
        print(f"\n{'='*70}")
        print(f"FULL REALISTIC BACKTEST v3.1")
        print(f"{'='*70}")
        print(f"\nKEY FIX: Uses HISTORICAL data for each week")
        print(f"       (Previous bug: used current data for all weeks)")
        print(f"\nSettings:")
        print(f"  Universe: {len(self.screener.UNIVERSE)} stocks")
        print(f"  Starting Capital: ${self.STARTING_CAPITAL:,}")
        print(f"  Max Positions: {self.MAX_POSITIONS}")
        print(f"  Position Size: {self.POSITION_SIZE_PCT}%")
        print(f"  Max Hold Days: {self.MAX_HOLD_DAYS}")
        print(f"  Test Period: {months_back} months")
        print(f"\nTarget: 5-10% monthly return")
        print(f"{'='*70}\n")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        current = start_date
        week_num = 0

        all_symbols_traded = set()

        while current <= end_date - timedelta(days=7):  # Leave room for trade simulation
            # Skip weekends
            while current.weekday() >= 5:
                current += timedelta(days=1)

            if current > end_date - timedelta(days=7):
                break

            week_num += 1
            date_str = current.strftime('%Y-%m-%d')
            month_key = current.strftime('%Y-%m')

            print(f"\n[Week {week_num}] {date_str}")

            # Check market regime for THIS date
            regime = self.screener.get_market_regime(current)
            print(f"  Market Regime: {regime}")

            # Skip if bear market
            if regime == "BEAR":
                print(f"  SKIP: Bear market")
                self.improvement_notes.append(f"{date_str}: Skipped - BEAR market")
                current += timedelta(days=7)
                continue

            # Load HISTORICAL data ending at simulation date
            print(f"  Loading historical data ending {date_str}...")
            loaded = self.screener.load_historical_data(current)
            print(f"  Loaded: {loaded} stocks")

            if loaded < 20:
                print(f"  SKIP: Insufficient data ({loaded} stocks)")
                current += timedelta(days=7)
                continue

            # Screen using historical data
            signals = self.screener.screen(market_regime=regime)

            if not signals:
                print(f"  No signals found")
                current += timedelta(days=7)
                continue

            print(f"  Found {len(signals)} signals")

            # Show which stocks are different from previous weeks
            new_symbols = [s['symbol'] for s in signals[:5] if s['symbol'] not in all_symbols_traded]
            if new_symbols:
                print(f"  NEW stocks this week: {', '.join(new_symbols)}")

            # Take top positions
            trades_this_week = 0
            for sig in signals[:self.MAX_POSITIONS]:
                position_size = self.capital * (self.POSITION_SIZE_PCT / 100)

                print(f"\n    {sig['symbol']}: Score={sig['score']}")
                print(f"      Entry=${sig['entry_price']:.2f}, SL=-{sig['sl_pct']:.1f}%, TP=+{sig['tp_pct']:.1f}%")
                print(f"      Mom1d={sig['mom_1d']:+.1f}%, RSI={sig['rsi']:.0f}")
                print(f"      Reasons: {', '.join(sig['reasons'][:2])}")

                trade = self.simulate_trade(sig, current, position_size)

                if trade:
                    self.trades.append(trade)
                    trades_this_week += 1
                    all_symbols_traded.add(sig['symbol'])

                    # Update capital
                    self.capital += trade.pnl_usd

                    emoji = "WIN" if trade.pnl_pct > 0 else "LOSS"
                    print(f"      [{emoji}] {trade.exit_reason}: {trade.pnl_pct:+.2f}% (${trade.pnl_usd:+.2f})")
                    print(f"      Peak: {trade.peak_pct:+.1f}%, Trough: {trade.trough_pct:+.1f}%")

                    # Record improvement notes
                    if trade.exit_reason == "STOP_LOSS" and trade.peak_pct > 1:
                        self.improvement_notes.append(
                            f"{trade.symbol}: Hit SL but peaked +{trade.peak_pct:.1f}% - consider trailing"
                        )

                    # Update monthly tracking
                    if month_key not in self.monthly_results:
                        self.monthly_results[month_key] = {
                            'trades': 0, 'wins': 0, 'losses': 0,
                            'pnl': 0, 'pnl_usd': 0
                        }
                    self.monthly_results[month_key]['trades'] += 1
                    self.monthly_results[month_key]['pnl'] += trade.pnl_pct
                    self.monthly_results[month_key]['pnl_usd'] += trade.pnl_usd
                    if trade.pnl_pct > 0:
                        self.monthly_results[month_key]['wins'] += 1
                    else:
                        self.monthly_results[month_key]['losses'] += 1

            print(f"\n  Week {week_num} trades: {trades_this_week}")
            print(f"  Current capital: ${self.capital:,.2f}")

            # Move to next week
            current += timedelta(days=7)
            time.sleep(1)  # Rate limiting

        print(f"\n{'='*70}")
        print(f"UNIQUE SYMBOLS TRADED: {len(all_symbols_traded)}")
        print(f"{'='*70}")

        self._show_results()
        self._save_results()

    def _show_results(self):
        """Show comprehensive results"""
        if not self.trades:
            print("\nNo trades executed")
            return

        print(f"\n{'='*70}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*70}")

        # Overall statistics
        total = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        losers = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total * 100
        total_pnl = sum(t.pnl_pct for t in self.trades)
        total_pnl_usd = sum(t.pnl_usd for t in self.trades)
        avg_pnl = total_pnl / total

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        print(f"\nOVERALL STATISTICS:")
        print(f"  Total Trades: {total}")
        print(f"  Unique Symbols: {len(set(t.symbol for t in self.trades))}")
        print(f"  Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers: {len(losers)} ({100-win_rate:.1f}%)")

        print(f"\nRETURNS:")
        print(f"  Total P&L: {total_pnl:+.2f}% (${total_pnl_usd:+,.2f})")
        print(f"  Avg per Trade: {avg_pnl:+.2f}%")
        print(f"  Avg Win: {avg_win:+.2f}%")
        print(f"  Avg Loss: {avg_loss:+.2f}%")

        print(f"\nCAPITAL:")
        print(f"  Starting: ${self.STARTING_CAPITAL:,}")
        print(f"  Ending: ${self.capital:,.2f}")
        print(f"  Total Return: {((self.capital/self.STARTING_CAPITAL)-1)*100:+.2f}%")

        # Exit breakdown
        exit_counts = {}
        for t in self.trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        print(f"\nEXIT BREAKDOWN:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            trades_by_reason = [t for t in self.trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}%")

        # Monthly breakdown
        print(f"\nMONTHLY BREAKDOWN:")
        print(f"  {'Month':<10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>10} {'P&L $':>12}")
        print(f"  {'-'*55}")

        monthly_returns = []
        for month in sorted(self.monthly_results.keys()):
            data = self.monthly_results[month]
            if data['trades'] > 0:
                wr = data['wins'] / data['trades'] * 100
                print(f"  {month:<10} {data['trades']:>7} {data['wins']:>6} {wr:>6.1f}% {data['pnl']:>+9.2f}% ${data['pnl_usd']:>+10.2f}")
                monthly_returns.append(data['pnl'])

        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\nMONTHLY AVERAGE: {avg_monthly:+.2f}%")
        print(f"   Target: +5% to +10%")

        if avg_monthly >= 10:
            print(f"   EXCELLENT! Exceeds 10% target!")
        elif avg_monthly >= 5:
            print(f"   GOOD! Meets 5% target")
        elif avg_monthly >= 0:
            print(f"   Profitable but below 5% target")
        else:
            print(f"   Not profitable - needs improvement")

        # Trade details
        print(f"\nTRADE DETAILS:")
        for t in self.trades:
            emoji = "WIN" if t.pnl_pct > 0 else "LOSS"
            print(f"  [{emoji}] {t.entry_date} {t.symbol}: {t.exit_reason} {t.pnl_pct:+.2f}% (Score={t.score})")

        # Improvement analysis
        if self.improvement_notes:
            print(f"\nIMPROVEMENT NOTES:")
            for note in self.improvement_notes[:10]:
                print(f"  - {note}")

    def _save_results(self):
        """Save results to file"""
        output_file = f"backtest_realistic_v31_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        results = {
            'settings': {
                'starting_capital': self.STARTING_CAPITAL,
                'ending_capital': self.capital,
                'max_positions': self.MAX_POSITIONS,
                'position_size_pct': self.POSITION_SIZE_PCT,
                'universe_size': len(self.screener.UNIVERSE),
            },
            'summary': {
                'total_trades': len(self.trades),
                'unique_symbols': len(set(t.symbol for t in self.trades)),
                'win_rate': len([t for t in self.trades if t.pnl_pct > 0]) / len(self.trades) * 100 if self.trades else 0,
                'total_pnl_pct': sum(t.pnl_pct for t in self.trades),
                'total_return': ((self.capital / self.STARTING_CAPITAL) - 1) * 100,
            },
            'monthly': self.monthly_results,
            'trades': [asdict(t) for t in self.trades],
            'improvement_notes': self.improvement_notes[:20]
        }

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to: {output_file}")


def main():
    print("="*70)
    print("RAPID TRADER v3.1 - FULL REALISTIC BACKTEST")
    print("="*70)
    print("\nCRITICAL FIX: This version uses HISTORICAL data for each week")
    print("Previous bug: Screener used current data, same stocks every week")
    print("\nThis test will:")
    print("  1. Load historical data ending at each simulation date")
    print("  2. Screen with THAT week's data (different stocks)")
    print("  3. Simulate real trading with SL/TP")
    print("  4. Calculate monthly returns")
    print("\nTarget: 5-10% monthly return")
    print("="*70)

    backtest = FullRealisticBacktest()
    backtest.run_backtest(months_back=3)


if __name__ == "__main__":
    main()
