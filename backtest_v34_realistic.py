#!/usr/bin/env python3
"""
REALISTIC BACKTEST v3.4 - FULLY DYNAMIC SL/TP

ทดสอบแบบ realistic:
1. ใช้ screener จริง scan หาหุ้น
2. ใช้ dynamic SL/TP จาก screener (ATR-based, SwingLow, Resistance)
3. หลัง entry ใช้ dynamic trailing จาก portfolio manager
4. Simulate ทุกวัน ไม่ใช่แค่สัปดาห์
5. แสดงผลรายเดือน

Period: 6 months (Jul 2025 - Jan 2026)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION - Match v3.4 exactly
# ============================================================
START_DATE = datetime(2025, 7, 1)
END_DATE = datetime(2026, 1, 31)
INITIAL_CAPITAL = 10000
MAX_POSITIONS = 3
POSITION_SIZE_PCT = 0.30  # 30% per position

# v3.4 Dynamic SL/TP parameters
ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 3.0
MIN_SL_PCT = 2.0
MAX_SL_PCT = 8.0
MIN_TP_PCT = 4.0
MAX_TP_PCT = 15.0

# Trailing parameters
TRAIL_ACTIVATION_PCT = 3.0
ATR_TRAIL_MULTIPLIER = 2.0

# Screening parameters (v3.4)
MIN_SCORE = 90
MIN_ATR_PCT = 2.5


@dataclass
class Position:
    """Active position with dynamic tracking"""
    symbol: str
    entry_date: datetime
    entry_price: float
    shares: int
    initial_sl: float
    current_sl: float
    initial_tp: float
    current_tp: float
    highest_price: float
    trailing_active: bool
    sl_method: str
    tp_method: str


@dataclass
class Trade:
    """Completed trade record"""
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
    sl_method: str
    tp_method: str


class RealisticBacktestV34:
    """Realistic backtest using actual v3.4 logic"""

    # Universe (same as screener)
    UNIVERSE = [
        # AI/Semiconductor
        'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
        'QCOM', 'AMAT', 'LRCX', 'KLAC', 'INTC', 'TXN', 'ADI',
        # High beta tech
        'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG', 'NET', 'CRWD', 'ZS',
        # Mega cap tech
        'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT', 'ORCL',
        # Other
        'CRM', 'NOW', 'SHOP', 'PYPL', 'UBER', 'ABNB',
        'RIVN', 'LCID', 'ENPH', 'FSLR',
        'JPM', 'GS', 'MS', 'V', 'MA',
        'CAT', 'DE', 'BA', 'GE', 'HON',
        'NKE', 'LULU', 'SBUX', 'MCD',
        'ROKU', 'PATH', 'CHWY',
    ]

    def __init__(self):
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.capital = INITIAL_CAPITAL
        self.cash = INITIAL_CAPITAL
        self.daily_values: List[Dict] = []

    def load_all_data(self):
        """Load historical data for all symbols"""
        print("Loading historical data...")
        start = START_DATE - timedelta(days=60)
        end = END_DATE + timedelta(days=5)

        for symbol in self.UNIVERSE:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start, end=end, auto_adjust=True)
                if len(df) >= 30:
                    df.columns = [c.lower() for c in df.columns]
                    self.data_cache[symbol] = df
            except Exception as e:
                pass

        print(f"Loaded {len(self.data_cache)} symbols")

    def get_data_until(self, symbol: str, date: datetime) -> Optional[pd.DataFrame]:
        """Get data up to specific date (for realistic simulation)"""
        if symbol not in self.data_cache:
            return None
        df = self.data_cache[symbol]
        mask = df.index.date <= date.date()
        return df[mask].copy() if mask.any() else None

    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate all indicators needed for screening"""
        if len(df) < 20:
            return {}

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / close.iloc[-1]) * 100

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))

        # Momentum
        mom_1d = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0
        mom_5d = (close.iloc[-1] / close.iloc[-5] - 1) * 100 if len(close) >= 5 else 0
        mom_20d = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0

        # Yesterday's move
        yesterday_move = (close.iloc[-2] / close.iloc[-3] - 1) * 100 if len(close) >= 3 else 0

        # MAs
        sma5 = close.rolling(5).mean().iloc[-1]
        sma20 = close.rolling(20).mean().iloc[-1]
        ema5 = close.ewm(span=5).mean().iloc[-1]

        # Swing levels
        swing_low_5d = low.iloc[-5:].min()
        swing_high_20d = high.iloc[-20:].max()
        high_52w = high.max()

        # Today's candle
        today_open = df['open'].iloc[-1]
        today_close = close.iloc[-1]
        today_is_green = today_close > today_open

        return {
            'close': close.iloc[-1],
            'open': today_open,
            'atr': atr,
            'atr_pct': atr_pct,
            'rsi': rsi,
            'mom_1d': mom_1d,
            'mom_5d': mom_5d,
            'mom_20d': mom_20d,
            'yesterday_move': yesterday_move,
            'sma5': sma5,
            'sma20': sma20,
            'ema5': ema5,
            'swing_low_5d': swing_low_5d,
            'swing_high_20d': swing_high_20d,
            'high_52w': high_52w,
            'today_is_green': today_is_green,
        }

    def screen_stock(self, symbol: str, date: datetime) -> Optional[Dict]:
        """Screen a stock using v3.4 logic with dynamic SL/TP"""
        df = self.get_data_until(symbol, date)
        if df is None or len(df) < 20:
            return None

        ind = self.calculate_indicators(df)
        if not ind:
            return None

        current_price = ind['close']
        atr = ind['atr']
        atr_pct = ind['atr_pct']

        # ============ v3.3 BOUNCE CONFIRMATION FILTERS ============
        # FILTER 1: Yesterday MUST be down
        if ind['yesterday_move'] > -1.0:
            return None

        # FILTER 2: Today should show recovery
        if ind['mom_1d'] < -1.0:
            return None

        # FILTER 3: Green candle preferred
        if not ind['today_is_green'] and ind['mom_1d'] < 0.5:
            return None

        # FILTER 4: Skip big gap ups
        gap_pct = (ind['open'] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
        if gap_pct > 2.0:
            return None

        # FILTER 5: Not too extended
        if current_price > ind['sma5'] * 1.02:
            return None

        # FILTER 6: Minimum volatility
        if atr_pct < MIN_ATR_PCT:
            return None

        # ============ v3.3 SCORING ============
        score = 0
        reasons = []

        # Bounce confirmation
        if ind['today_is_green'] and ind['mom_1d'] > 0.5:
            score += 40
            reasons.append("Strong bounce")
        elif ind['today_is_green'] or ind['mom_1d'] > 0.3:
            score += 25
            reasons.append("Bounce")

        # Prior dip (5-day)
        if -12 <= ind['mom_5d'] <= -5:
            score += 40
            reasons.append(f"Deep dip {ind['mom_5d']:.1f}%")
        elif -5 < ind['mom_5d'] <= -3:
            score += 30
            reasons.append(f"Good dip")
        elif -3 < ind['mom_5d'] < 0:
            score += 15

        # Yesterday's dip
        if ind['yesterday_move'] <= -3:
            score += 30
            reasons.append(f"Big dip yesterday")
        elif ind['yesterday_move'] <= -1.5:
            score += 20
        else:
            score += 10

        # RSI
        if 25 <= ind['rsi'] <= 40:
            score += 20
            reasons.append(f"Oversold RSI")
        elif 40 < ind['rsi'] <= 50:
            score += 10

        # Check minimum score
        if score < MIN_SCORE:
            return None

        # ============ v3.4 FULLY DYNAMIC SL/TP ============

        # --- DYNAMIC STOP LOSS ---
        # Method 1: ATR-based
        atr_sl_distance = atr * ATR_SL_MULTIPLIER
        atr_based_sl = current_price - atr_sl_distance

        # Method 2: Swing Low based
        swing_low_sl = ind['swing_low_5d'] * 0.995

        # Method 3: EMA based
        ema_based_sl = ind['ema5'] * 0.99

        # Choose HIGHEST SL = best protection
        sl_options = {
            'ATR': atr_based_sl,
            'SwingLow': swing_low_sl,
            'EMA5': ema_based_sl
        }
        sl_method = max(sl_options, key=sl_options.get)
        stop_loss = sl_options[sl_method]

        # Apply safety caps
        sl_pct_raw = (current_price - stop_loss) / current_price * 100
        sl_pct = max(MIN_SL_PCT, min(sl_pct_raw, MAX_SL_PCT))
        stop_loss = current_price * (1 - sl_pct / 100)

        # --- DYNAMIC TAKE PROFIT ---
        # Method 1: ATR-based
        atr_based_tp = current_price + (atr * ATR_TP_MULTIPLIER)

        # Method 2: Resistance based
        resistance_tp = ind['swing_high_20d'] * 0.995

        # Method 3: 52-week high
        high_52w_tp = ind['high_52w'] * 0.98

        # Choose LOWEST TP = most realistic
        tp_options = {
            'ATR': atr_based_tp,
            'Resistance': resistance_tp,
            '52wHigh': high_52w_tp
        }
        tp_method = min(tp_options, key=tp_options.get)
        take_profit = tp_options[tp_method]

        # Apply safety caps
        tp_pct_raw = (take_profit - current_price) / current_price * 100
        tp_pct = max(MIN_TP_PCT, min(tp_pct_raw, MAX_TP_PCT))
        take_profit = current_price * (1 + tp_pct / 100)

        return {
            'symbol': symbol,
            'score': score,
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'sl_method': sl_method,
            'tp_method': tp_method,
            'atr_pct': atr_pct,
            'rsi': ind['rsi'],
            'reasons': reasons
        }

    def calculate_dynamic_trailing(self, symbol: str, current_price: float,
                                   highest_price: float, date: datetime) -> Tuple[float, float, str, str]:
        """Calculate dynamic trailing SL and TP (v3.4 portfolio manager logic)"""
        df = self.get_data_until(symbol, date)
        if df is None or len(df) < 14:
            # Fallback
            return highest_price * 0.965, highest_price * 1.06, 'fallback', 'fallback'

        close = df['close']
        high = df['high']
        low = df['low']

        # Calculate ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # ============ DYNAMIC SL ============
        # Method 1: ATR-based
        atr_based_sl = highest_price - (atr * ATR_TRAIL_MULTIPLIER)

        # Method 2: Swing Low
        swing_low_5d = low.iloc[-5:].min()
        swing_low_sl = swing_low_5d * 0.995

        # Method 3: EMA based
        ema5 = close.ewm(span=5).mean().iloc[-1]
        ema10 = close.ewm(span=10).mean().iloc[-1]
        if current_price > ema5:
            ema_based_sl = ema5 * 0.99
        else:
            ema_based_sl = ema10 * 0.98

        # Choose highest (best protection)
        sl_options = {'ATR': atr_based_sl, 'SwingLow': swing_low_sl, 'EMA': ema_based_sl}
        sl_method = max(sl_options, key=sl_options.get)
        new_sl = sl_options[sl_method]

        # Don't trail tighter than 1.5% from current
        min_distance = current_price * 0.015
        if current_price - new_sl < min_distance:
            new_sl = current_price - min_distance

        # ============ DYNAMIC TP ============
        # Method 1: ATR-based
        atr_based_tp = current_price + (atr * 3)

        # Method 2: Resistance
        swing_high_20d = high.iloc[-20:].max()
        resistance_tp = swing_high_20d * 0.995

        # Method 3: 52w high
        high_52w = high.max()
        high_52w_tp = high_52w * 0.98

        # Choose lowest (most realistic)
        tp_options = {'ATR': atr_based_tp, 'Resistance': resistance_tp, '52wHigh': high_52w_tp}
        tp_method = min(tp_options, key=tp_options.get)
        new_tp = tp_options[tp_method]

        # Ensure TP at least 4% above current
        min_tp = current_price * 1.04
        if new_tp < min_tp:
            new_tp = min_tp

        return new_sl, new_tp, sl_method, tp_method

    def run_backtest(self):
        """Run the full backtest"""
        print("=" * 60)
        print("REALISTIC BACKTEST v3.4 - FULLY DYNAMIC SL/TP")
        print("=" * 60)
        print(f"Period: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
        print(f"Initial Capital: ${INITIAL_CAPITAL:,.0f}")
        print()

        self.load_all_data()
        print()

        # Generate trading days
        trading_days = pd.date_range(START_DATE, END_DATE, freq='B')

        # Track monthly performance
        monthly_results = {}
        current_month = None
        month_start_value = INITIAL_CAPITAL

        scan_day = 0

        for date in trading_days:
            date_dt = date.to_pydatetime()

            # Track new month
            month_key = date_dt.strftime('%Y-%m')
            if month_key != current_month:
                if current_month is not None:
                    # Record previous month
                    month_end_value = self.get_portfolio_value(date_dt)
                    monthly_results[current_month] = {
                        'start': month_start_value,
                        'end': month_end_value,
                        'return_pct': (month_end_value / month_start_value - 1) * 100
                    }
                current_month = month_key
                month_start_value = self.get_portfolio_value(date_dt)

            # ============ CHECK EXISTING POSITIONS ============
            positions_to_close = []

            for symbol, pos in self.positions.items():
                df = self.get_data_until(symbol, date_dt)
                if df is None or len(df) == 0:
                    continue

                current_price = df['close'].iloc[-1]
                high_today = df['high'].iloc[-1]
                low_today = df['low'].iloc[-1]

                days_held = (date_dt - pos.entry_date).days
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100

                exit_reason = None
                exit_price = current_price

                # Check for new high and update trailing
                if high_today > pos.highest_price:
                    pos.highest_price = high_today

                    # Activate trailing after 3%
                    if pnl_pct >= TRAIL_ACTIVATION_PCT:
                        pos.trailing_active = True

                        # Calculate new dynamic SL/TP
                        new_sl, new_tp, sl_m, tp_m = self.calculate_dynamic_trailing(
                            symbol, current_price, pos.highest_price, date_dt
                        )

                        # Only raise SL
                        if new_sl > pos.current_sl:
                            pos.current_sl = new_sl
                            pos.sl_method = sl_m

                        # Only raise TP
                        if new_tp > pos.current_tp:
                            pos.current_tp = new_tp
                            pos.tp_method = tp_m

                # ============ CHECK EXIT CONDITIONS ============
                # 1. Stop Loss hit (check intraday low)
                if low_today <= pos.current_sl:
                    exit_reason = "TRAILING_SL" if pos.trailing_active else "STOP_LOSS"
                    exit_price = pos.current_sl

                # 2. Take Profit hit (check intraday high)
                elif high_today >= pos.current_tp:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = pos.current_tp

                # 3. Time stop (after 5 days with minimal gain)
                elif days_held >= 5 and pnl_pct < 1:
                    exit_reason = "TIME_STOP"
                    exit_price = current_price

                if exit_reason:
                    positions_to_close.append((symbol, exit_price, exit_reason, date_dt))

            # Close positions
            for symbol, exit_price, exit_reason, exit_dt in positions_to_close:
                self.close_position(symbol, exit_price, exit_reason, exit_dt)

            # ============ SCAN FOR NEW POSITIONS (Weekly on Monday) ============
            if date.dayofweek == 0:  # Monday
                scan_day += 1

                if len(self.positions) < MAX_POSITIONS:
                    signals = []
                    for symbol in self.UNIVERSE:
                        if symbol in self.positions:
                            continue
                        signal = self.screen_stock(symbol, date_dt)
                        if signal:
                            signals.append(signal)

                    # Sort by score
                    signals.sort(key=lambda x: x['score'], reverse=True)

                    # Open new positions
                    for signal in signals[:MAX_POSITIONS - len(self.positions)]:
                        self.open_position(signal, date_dt)

            # Record daily value
            portfolio_value = self.get_portfolio_value(date_dt)
            self.daily_values.append({
                'date': date_dt,
                'value': portfolio_value,
                'positions': len(self.positions)
            })

        # Record last month
        if current_month:
            month_end_value = self.get_portfolio_value(END_DATE)
            monthly_results[current_month] = {
                'start': month_start_value,
                'end': month_end_value,
                'return_pct': (month_end_value / month_start_value - 1) * 100
            }

        # Print results
        self.print_results(monthly_results)

    def open_position(self, signal: Dict, date: datetime):
        """Open a new position"""
        position_value = self.cash * POSITION_SIZE_PCT
        shares = int(position_value / signal['entry_price'])

        if shares < 1:
            return

        cost = shares * signal['entry_price']
        self.cash -= cost

        self.positions[signal['symbol']] = Position(
            symbol=signal['symbol'],
            entry_date=date,
            entry_price=signal['entry_price'],
            shares=shares,
            initial_sl=signal['stop_loss'],
            current_sl=signal['stop_loss'],
            initial_tp=signal['take_profit'],
            current_tp=signal['take_profit'],
            highest_price=signal['entry_price'],
            trailing_active=False,
            sl_method=signal['sl_method'],
            tp_method=signal['tp_method']
        )

        print(f"📈 {date.strftime('%Y-%m-%d')} BUY {signal['symbol']} x{shares} @ ${signal['entry_price']:.2f}")
        print(f"   SL: ${signal['stop_loss']:.2f} ({signal['sl_method']}) | TP: ${signal['take_profit']:.2f} ({signal['tp_method']})")

    def close_position(self, symbol: str, exit_price: float, exit_reason: str, date: datetime):
        """Close a position"""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        proceeds = pos.shares * exit_price
        self.cash += proceeds

        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
        pnl_usd = (exit_price - pos.entry_price) * pos.shares
        days_held = (date - pos.entry_date).days

        self.trades.append(Trade(
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
            sl_method=pos.sl_method,
            tp_method=pos.tp_method
        ))

        emoji = "✅" if pnl_pct >= 0 else "❌"
        print(f"{emoji} {date.strftime('%Y-%m-%d')} SELL {symbol} @ ${exit_price:.2f} | {pnl_pct:+.1f}% | {exit_reason}")
        if pos.trailing_active:
            print(f"   (Trailing was active, SL moved from ${pos.initial_sl:.2f} to ${pos.current_sl:.2f})")

        del self.positions[symbol]

    def get_portfolio_value(self, date: datetime) -> float:
        """Get total portfolio value"""
        value = self.cash
        for symbol, pos in self.positions.items():
            df = self.get_data_until(symbol, date)
            if df is not None and len(df) > 0:
                value += pos.shares * df['close'].iloc[-1]
        return value

    def print_results(self, monthly_results: Dict):
        """Print detailed results"""
        print()
        print("=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)

        # Trade statistics
        if self.trades:
            wins = [t for t in self.trades if t.pnl_pct > 0]
            losses = [t for t in self.trades if t.pnl_pct <= 0]

            print(f"\n📊 TRADE STATISTICS:")
            print(f"   Total Trades: {len(self.trades)}")
            print(f"   Winners: {len(wins)} ({len(wins)/len(self.trades)*100:.1f}%)")
            print(f"   Losers: {len(losses)} ({len(losses)/len(self.trades)*100:.1f}%)")

            if wins:
                print(f"   Avg Win: +{np.mean([t.pnl_pct for t in wins]):.2f}%")
            if losses:
                print(f"   Avg Loss: {np.mean([t.pnl_pct for t in losses]):.2f}%")

            print(f"   Avg Days Held: {np.mean([t.days_held for t in self.trades]):.1f}")

            # Exit reasons
            print(f"\n📋 EXIT REASONS:")
            reasons = {}
            for t in self.trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                pct = count / len(self.trades) * 100
                print(f"   {reason}: {count} ({pct:.1f}%)")

            # SL/TP Methods
            print(f"\n🎯 DYNAMIC SL/TP METHODS USED:")
            sl_methods = {}
            tp_methods = {}
            for t in self.trades:
                sl_methods[t.sl_method] = sl_methods.get(t.sl_method, 0) + 1
                tp_methods[t.tp_method] = tp_methods.get(t.tp_method, 0) + 1
            print(f"   SL Methods: {sl_methods}")
            print(f"   TP Methods: {tp_methods}")

        # Monthly results
        print(f"\n📅 MONTHLY RETURNS:")
        print("-" * 40)
        total_months = 0
        positive_months = 0
        total_return = 0

        for month, data in sorted(monthly_results.items()):
            ret = data['return_pct']
            total_return += ret
            total_months += 1
            if ret > 0:
                positive_months += 1
            emoji = "✅" if ret > 0 else "❌"
            print(f"   {month}: {emoji} {ret:+.2f}%")

        print("-" * 40)
        avg_monthly = total_return / total_months if total_months > 0 else 0
        print(f"   Average Monthly: {avg_monthly:+.2f}%")
        print(f"   Positive Months: {positive_months}/{total_months}")

        # Final results
        final_value = self.get_portfolio_value(END_DATE)
        total_return_pct = (final_value / INITIAL_CAPITAL - 1) * 100

        print(f"\n💰 FINAL RESULTS:")
        print(f"   Initial Capital: ${INITIAL_CAPITAL:,.0f}")
        print(f"   Final Value: ${final_value:,.0f}")
        print(f"   Total Return: {total_return_pct:+.2f}%")
        print(f"   Avg Monthly Return: {avg_monthly:+.2f}%")

        # Detailed trade list
        print(f"\n📜 ALL TRADES:")
        print("-" * 80)
        for t in self.trades:
            emoji = "✅" if t.pnl_pct > 0 else "❌"
            print(f"{emoji} {t.symbol:5} | {t.entry_date.strftime('%m/%d')}-{t.exit_date.strftime('%m/%d')} | "
                  f"${t.entry_price:.2f}→${t.exit_price:.2f} | {t.pnl_pct:+.1f}% | {t.exit_reason}")


if __name__ == "__main__":
    backtest = RealisticBacktestV34()
    backtest.run_backtest()
