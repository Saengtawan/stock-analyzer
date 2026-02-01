#!/usr/bin/env python3
"""
FULL REALISTIC BACKTEST v3.2 - IMPROVED
========================================
Improvements from v3.1 analysis:
1. WIDER SL (3.0-4.0%) - v3.1 had 64% SL rate
2. TRAILING STOP - Many trades peaked +2-3% before SL
3. BOUNCE CONFIRMATION - Don't catch falling knife
4. HIGHER SCORE THRESHOLD - Only best trades

Target: 5-10% monthly return
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
import time
import warnings
warnings.filterwarnings('ignore')


@dataclass
class TradeRecord:
    """Complete trade record"""
    symbol: str
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
    Improved Screener v3.2
    - Bounce confirmation (not catching falling knife)
    - Wider SL range
    - Higher score threshold
    """

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

    # v3.2 Parameters - IMPROVED
    MIN_ATR_PCT = 2.5  # Higher min volatility
    MIN_SCORE = 70     # Higher score threshold (was 60)
    BASE_TP_PCT = 5.0  # Higher TP target
    BASE_SL_PCT = 3.0  # Wider SL (was 2.0)

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
        except:
            return "UNKNOWN"

    def load_historical_data(self, end_date: datetime, days: int = 60):
        """Load historical data ending at specific date"""
        self.data_cache = {}
        start_date = end_date - timedelta(days=days + 10)

        loaded = 0
        for symbol in self.UNIVERSE:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date + timedelta(days=1))

                if not hist.empty:
                    hist.index = hist.index.tz_localize(None)
                    hist = hist[hist.index <= pd.Timestamp(end_date)]

                if len(hist) >= 30:
                    hist.columns = [c.lower() for c in hist.columns]
                    self.data_cache[symbol] = hist
                    loaded += 1
            except:
                pass

            if loaded % 30 == 0:
                time.sleep(0.5)

        return loaded

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
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
        """Screen for buy signals using v3.2 improved logic"""
        if not self.data_cache:
            return []

        signals = []
        for symbol, data in self.data_cache.items():
            try:
                signal = self._analyze_stock(symbol, data, market_regime)
                if signal:
                    signals.append(signal)
            except:
                pass

        signals.sort(key=lambda x: x['score'], reverse=True)
        return signals[:10]

    def _analyze_stock(self, symbol: str, data: pd.DataFrame, market_regime: str) -> Optional[Dict]:
        """
        v3.2 Improved Analysis:
        - BOUNCE CONFIRMATION instead of catching falling knife
        - Higher score threshold
        - Wider SL
        """
        if len(data) < 30:
            return None

        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        open_price = data['open'] if 'open' in data.columns else close

        idx = len(data) - 1
        current_price = close.iloc[idx]

        if current_price < 10 or current_price > 2000:
            return None

        rsi = self.calculate_rsi(close)
        atr = self.calculate_atr(data)
        if atr == 0:
            return None
        atr_pct = (atr / current_price) * 100

        # Momentum
        mom_1d = ((current_price / close.iloc[idx-1]) - 1) * 100 if idx >= 1 else 0
        mom_2d = ((current_price / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0
        mom_5d = ((current_price / close.iloc[idx-5]) - 1) * 100 if idx >= 5 else 0
        mom_20d = ((current_price / close.iloc[idx-20]) - 1) * 100 if idx >= 20 else 0

        # Yesterday's move
        yesterday_move = ((close.iloc[idx-1] / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0

        # SMAs
        sma5 = close.iloc[-5:].mean()
        sma20 = close.iloc[-20:].mean() if len(close) >= 20 else close.mean()
        sma50 = close.iloc[-50:].mean() if len(close) >= 50 else close.mean()

        # Gap
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price
        gap_pct = ((open_price.iloc[idx] - prev_close) / prev_close) * 100

        # Today's candle (for bounce confirmation)
        today_open = open_price.iloc[idx]
        today_is_green = current_price > today_open

        # Distance from high
        high_20d = high.iloc[-20:].max() if len(high) >= 20 else high.max()
        dist_from_high = ((high_20d - current_price) / high_20d) * 100

        # Support
        support = low.iloc[-10:].min() if len(low) >= 10 else low.min()

        # Volume
        avg_volume = volume.iloc[-20:].mean() if len(volume) >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # ==============================
        # v3.2: BOUNCE CONFIRMATION FILTERS
        # ==============================
        # Instead of buying during the dip, wait for bounce

        # FILTER 1: Yesterday was down (the dip)
        if yesterday_move > -0.5:
            return None  # Need yesterday to be a dip day

        # FILTER 2: Today should show recovery (not falling further)
        # Allow small negative but not big drop
        if mom_1d < -1.5:
            return None  # Still falling hard, wait

        # FILTER 3: Green candle preferred (showing bounce)
        bounce_confirmed = today_is_green or mom_1d > 0.3

        # FILTER 4: Skip big gap ups (exhaustion)
        if gap_pct > 2.0:
            return None

        # FILTER 5: Should still be in oversold zone (room to recover)
        if current_price > sma5 * 1.02:
            return None  # Already recovered too much

        # Minimum volatility
        if atr_pct < self.MIN_ATR_PCT:
            return None

        # ==============================
        # SCORING v3.2
        # ==============================
        score = 0
        reasons = []

        # 1. Bounce confirmation (key differentiator)
        if bounce_confirmed:
            score += 25
            reasons.append("Bounce confirmed")

        # 2. Prior dip magnitude (5-day)
        if -10 <= mom_5d <= -4:
            score += 35
            reasons.append(f"Strong prior dip {mom_5d:.1f}%")
        elif -4 < mom_5d <= -2:
            score += 25
            reasons.append(f"Moderate dip {mom_5d:.1f}%")
        elif -2 < mom_5d < 0:
            score += 15
            reasons.append(f"Mild dip {mom_5d:.1f}%")

        # 3. Yesterday's dip (entry catalyst)
        if yesterday_move <= -2:
            score += 20
            reasons.append(f"Yesterday big dip {yesterday_move:.1f}%")
        elif yesterday_move <= -1:
            score += 10
            reasons.append(f"Yesterday dip {yesterday_move:.1f}%")

        # 4. RSI scoring
        if 30 <= rsi <= 40:
            score += 30
            reasons.append(f"Oversold RSI={rsi:.0f}")
        elif 40 < rsi <= 50:
            score += 20
            reasons.append(f"Low RSI={rsi:.0f}")

        # 5. Trend context
        if current_price > sma50 and current_price > sma20:
            score += 20
            reasons.append("Strong uptrend")
        elif current_price > sma20:
            score += 15
            reasons.append("Above SMA20")

        # 6. Volatility
        if atr_pct > 4:
            score += 15
            reasons.append(f"High vol {atr_pct:.1f}%")
        elif atr_pct > 3:
            score += 10
            reasons.append(f"Good vol {atr_pct:.1f}%")

        # 7. Room to recover
        if 8 <= dist_from_high <= 20:
            score += 15
            reasons.append(f"Room {dist_from_high:.0f}%")
        elif 5 <= dist_from_high < 8:
            score += 10
            reasons.append(f"Some room {dist_from_high:.0f}%")

        # 8. Volume confirmation
        if volume_ratio > 1.5:
            score += 10
            reasons.append("High volume bounce")
        elif volume_ratio > 1.2:
            score += 5
            reasons.append("Good volume")

        # Check minimum score (v3.2: higher threshold)
        if score < self.MIN_SCORE:
            return None

        # ==============================
        # CALCULATE SL/TP (v3.2: WIDER SL)
        # ==============================
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = self.BASE_TP_PCT * tp_multiplier

        # Dynamic SL (v3.2: 3.0-4.0%)
        if atr_pct > 5:
            sl_pct = 4.0  # Very volatile
        elif atr_pct > 4:
            sl_pct = 3.5
        elif atr_pct > 3:
            sl_pct = 3.25
        else:
            sl_pct = self.BASE_SL_PCT  # 3.0%

        # Support consideration
        sl_from_support = ((current_price - support * 0.995) / current_price) * 100
        sl_pct = max(sl_pct, min(sl_from_support * 0.8, 4.0))

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
            'yesterday_move': round(yesterday_move, 2),
            'reasons': reasons,
            'market_regime': market_regime,
        }


class FullBacktestV32:
    """Full backtest with trailing stop"""

    STARTING_CAPITAL = 10000
    MAX_POSITIONS = 3
    POSITION_SIZE_PCT = 30
    MAX_HOLD_DAYS = 5  # Slightly longer hold

    # v3.2: Trailing stop
    TRAIL_ACTIVATION = 2.5  # Activate trailing at +2.5%
    TRAIL_PERCENT = 50      # Trail at 50% of peak

    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.monthly_results: Dict = {}
        self.improvement_notes: List[str] = []
        self.capital = self.STARTING_CAPITAL
        self.screener = HistoricalScreener()

    def simulate_trade_with_trailing(self, signal: Dict, entry_date: datetime, position_size: float) -> Optional[TradeRecord]:
        """Simulate trade with trailing stop"""
        symbol = signal['symbol']
        entry_price = signal['entry_price']
        stop_loss = signal['stop_loss']
        take_profit = signal['take_profit']
        sl_pct = signal['sl_pct']
        tp_pct = signal['tp_pct']

        trade = TradeRecord(
            symbol=symbol,
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

        try:
            end = entry_date + timedelta(days=15)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date, end=end)

            if hist.empty or len(hist) < 2:
                return None
        except:
            return None

        peak_price = entry_price
        trough_price = entry_price
        trailing_activated = False
        current_trailing_stop = stop_loss

        for day_idx, (dt, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            high = row['High']
            low = row['Low']
            close = row['Close']

            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

            peak_pct = ((peak_price - entry_price) / entry_price) * 100
            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100
            close_pnl = ((close - entry_price) / entry_price) * 100

            # Check if trailing stop should be activated
            if peak_pct >= self.TRAIL_ACTIVATION and not trailing_activated:
                trailing_activated = True
                # Lock in some profit
                locked_profit = peak_pct * (self.TRAIL_PERCENT / 100)
                current_trailing_stop = entry_price * (1 + locked_profit / 100)

            # Update trailing stop if activated
            if trailing_activated:
                new_trail = entry_price * (1 + (peak_pct * self.TRAIL_PERCENT / 100) / 100)
                if new_trail > current_trailing_stop:
                    current_trailing_stop = new_trail

            # Check trailing stop hit
            if trailing_activated and low <= current_trailing_stop:
                trail_pnl = ((current_trailing_stop - entry_price) / entry_price) * 100
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = current_trailing_stop
                trade.exit_reason = "TRAIL_STOP"
                trade.pnl_pct = trail_pnl
                trade.pnl_usd = position_size * (trail_pnl / 100)
                trade.days_held = day_idx
                break

            # Check original stop loss
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
        """Run full backtest"""
        print(f"\n{'='*70}")
        print(f"FULL REALISTIC BACKTEST v3.2 - IMPROVED")
        print(f"{'='*70}")
        print(f"\nIMPROVEMENTS FROM v3.1:")
        print(f"  1. BOUNCE CONFIRMATION (not catching falling knife)")
        print(f"  2. WIDER SL (3.0-4.0% instead of 2.0-3.0%)")
        print(f"  3. TRAILING STOP (activate at +2.5%)")
        print(f"  4. HIGHER SCORE THRESHOLD (70 instead of 60)")
        print(f"\nSettings:")
        print(f"  Universe: {len(self.screener.UNIVERSE)} stocks")
        print(f"  Starting Capital: ${self.STARTING_CAPITAL:,}")
        print(f"  Max Positions: {self.MAX_POSITIONS}")
        print(f"  Max Hold Days: {self.MAX_HOLD_DAYS}")
        print(f"\nTarget: 5-10% monthly return")
        print(f"{'='*70}\n")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        current = start_date
        week_num = 0
        all_symbols = set()

        while current <= end_date - timedelta(days=7):
            while current.weekday() >= 5:
                current += timedelta(days=1)

            if current > end_date - timedelta(days=7):
                break

            week_num += 1
            date_str = current.strftime('%Y-%m-%d')
            month_key = current.strftime('%Y-%m')

            print(f"\n[Week {week_num}] {date_str}")

            regime = self.screener.get_market_regime(current)
            print(f"  Market: {regime}")

            if regime == "BEAR":
                print(f"  SKIP: Bear market")
                current += timedelta(days=7)
                continue

            print(f"  Loading data...")
            loaded = self.screener.load_historical_data(current)
            print(f"  Loaded: {loaded} stocks")

            if loaded < 20:
                current += timedelta(days=7)
                continue

            signals = self.screener.screen(market_regime=regime)

            if not signals:
                print(f"  No signals (bounce confirmation is selective)")
                current += timedelta(days=7)
                continue

            print(f"  Found {len(signals)} signals")

            new_symbols = [s['symbol'] for s in signals[:5] if s['symbol'] not in all_symbols]
            if new_symbols:
                print(f"  NEW: {', '.join(new_symbols)}")

            trades_this_week = 0
            for sig in signals[:self.MAX_POSITIONS]:
                position_size = self.capital * (self.POSITION_SIZE_PCT / 100)

                print(f"\n    {sig['symbol']}: Score={sig['score']}")
                print(f"      Entry=${sig['entry_price']:.2f}, SL=-{sig['sl_pct']:.1f}%, TP=+{sig['tp_pct']:.1f}%")
                print(f"      Yesterday={sig['yesterday_move']:+.1f}%, Today={sig['mom_1d']:+.1f}%")
                print(f"      Reasons: {', '.join(sig['reasons'][:2])}")

                trade = self.simulate_trade_with_trailing(sig, current, position_size)

                if trade:
                    self.trades.append(trade)
                    trades_this_week += 1
                    all_symbols.add(sig['symbol'])

                    self.capital += trade.pnl_usd

                    emoji = "WIN" if trade.pnl_pct > 0 else "LOSS"
                    print(f"      [{emoji}] {trade.exit_reason}: {trade.pnl_pct:+.2f}% (${trade.pnl_usd:+.2f})")
                    print(f"      Peak: {trade.peak_pct:+.1f}%, Trough: {trade.trough_pct:+.1f}%")

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

            print(f"\n  Week {week_num}: {trades_this_week} trades, Capital: ${self.capital:,.2f}")

            current += timedelta(days=7)
            time.sleep(1)

        print(f"\n{'='*70}")
        print(f"UNIQUE SYMBOLS: {len(all_symbols)}")
        print(f"{'='*70}")

        self._show_results()
        self._save_results()

    def _show_results(self):
        """Show comprehensive results"""
        if not self.trades:
            print("\nNo trades executed")
            return

        print(f"\n{'='*70}")
        print(f"BACKTEST v3.2 RESULTS")
        print(f"{'='*70}")

        total = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        losers = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total * 100
        total_pnl = sum(t.pnl_pct for t in self.trades)
        total_pnl_usd = sum(t.pnl_usd for t in self.trades)
        avg_pnl = total_pnl / total

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        print(f"\nSTATISTICS:")
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

        exit_counts = {}
        for t in self.trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        print(f"\nEXIT BREAKDOWN:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            trades_by_reason = [t for t in self.trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}%")

        print(f"\nMONTHLY BREAKDOWN:")
        print(f"  {'Month':<10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>10}")
        print(f"  {'-'*42}")

        monthly_returns = []
        for month in sorted(self.monthly_results.keys()):
            data = self.monthly_results[month]
            if data['trades'] > 0:
                wr = data['wins'] / data['trades'] * 100
                print(f"  {month:<10} {data['trades']:>7} {data['wins']:>6} {wr:>6.1f}% {data['pnl']:>+9.2f}%")
                monthly_returns.append(data['pnl'])

        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\nMONTHLY AVERAGE: {avg_monthly:+.2f}%")
        print(f"   Target: +5% to +10%")

        if avg_monthly >= 10:
            print(f"   EXCELLENT! Exceeds 10%!")
        elif avg_monthly >= 5:
            print(f"   GOOD! Meets 5% target")
        elif avg_monthly >= 0:
            print(f"   Profitable but below target")
        else:
            print(f"   Not profitable - needs improvement")

        print(f"\nTRADE DETAILS:")
        for t in self.trades:
            emoji = "WIN" if t.pnl_pct > 0 else "LOSS"
            print(f"  [{emoji}] {t.entry_date} {t.symbol}: {t.exit_reason} {t.pnl_pct:+.2f}%")

    def _save_results(self):
        """Save results"""
        output_file = f"backtest_v32_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        results = {
            'version': 'v3.2',
            'improvements': [
                'Bounce confirmation',
                'Wider SL (3.0-4.0%)',
                'Trailing stop at +2.5%',
                'Higher score threshold (70)'
            ],
            'settings': {
                'starting_capital': self.STARTING_CAPITAL,
                'ending_capital': self.capital,
            },
            'summary': {
                'total_trades': len(self.trades),
                'win_rate': len([t for t in self.trades if t.pnl_pct > 0]) / len(self.trades) * 100 if self.trades else 0,
                'total_pnl_pct': sum(t.pnl_pct for t in self.trades),
            },
            'monthly': self.monthly_results,
            'trades': [asdict(t) for t in self.trades],
        }

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to: {output_file}")


def main():
    print("="*70)
    print("RAPID TRADER v3.2 - IMPROVED BACKTEST")
    print("="*70)
    print("\nKEY IMPROVEMENTS:")
    print("  1. BOUNCE CONFIRMATION - Wait for price to recover, not fall")
    print("  2. WIDER SL (3.0-4.0%) - Reduce premature stop-outs")
    print("  3. TRAILING STOP at +2.5% - Lock in gains")
    print("  4. HIGHER THRESHOLD - Only best quality trades")
    print("="*70)

    backtest = FullBacktestV32()
    backtest.run_backtest(months_back=3)


if __name__ == "__main__":
    main()
