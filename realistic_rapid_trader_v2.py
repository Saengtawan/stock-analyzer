#!/usr/bin/env python3
"""
RAPID TRADER v2 - IMPROVED VERSION
===================================
แก้ไขปัญหาจาก v1:
1. Win rate 36% → ต้องได้ 55%+
2. 60% โดน SL → ต้องลดให้เหลือ 30%-

การปรับปรุง:
1. ไม่ซื้อวันแรกที่ dip - รอ confirmation
2. ตรวจ market regime - ไม่เทรดตอน bear
3. Entry เฉพาะหุ้นที่ bounce จาก dip แล้ว
4. Volume confirmation ต้องมี
5. RSI ต้องกลับตัวจาก oversold
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Trade:
    """Single trade record"""
    symbol: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    atr_pct: float
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0
    peak_price: float = 0.0
    peak_pct: float = 0.0
    trough_price: float = 0.0
    trough_pct: float = 0.0
    entry_reason: str = ""


class ImprovedRapidTrader:
    """
    IMPROVED RAPID TRADER v2

    Key Changes:
    1. BOUNCE CONFIRMATION - ไม่ซื้อวันแรกที่ลง
    2. MARKET FILTER - ไม่เทรดตอน SPY ลง
    3. WIDER STOPS - กันโดน whipsaw
    4. VOLUME + RSI CONFIRM - double confirmation
    """

    # IMPROVED Exit parameters
    STOP_LOSS_BASE = 2.0       # Base SL 2% (was 1.5%)
    STOP_LOSS_MAX = 3.0        # Max SL 3% (was 2.5%)
    TAKE_PROFIT_MIN = 4.0      # Min TP 4%
    TAKE_PROFIT_MAX = 8.0      # Max TP 8% (was 6%)
    TRAIL_ACTIVATE_PCT = 3.0   # Start trail at 3% (was 2.5%)
    TRAIL_PCT = 0.65           # Trail 65% of profit (was 60%)
    MAX_HOLD_DAYS = 5          # 5 days (was 4)

    def __init__(self):
        self.trades: List[Trade] = []
        self.spy_data: pd.DataFrame = None

    def get_market_regime(self, date: str) -> str:
        """Check if market is bullish or bearish using SPY"""
        if self.spy_data is None:
            end = datetime.strptime(date, '%Y-%m-%d')
            start = end - timedelta(days=60)
            ticker = yf.Ticker('SPY')
            self.spy_data = ticker.history(start=start, end=end + timedelta(days=1))

        if len(self.spy_data) < 20:
            return "UNKNOWN"

        # Get data up to this date
        mask = self.spy_data.index <= pd.Timestamp(date)
        data = self.spy_data[mask]

        if len(data) < 20:
            return "UNKNOWN"

        current = data['Close'].iloc[-1]
        sma20 = data['Close'].tail(20).mean()
        sma50 = data['Close'].tail(50).mean() if len(data) >= 50 else sma20

        # Calculate momentum
        mom_5d = ((current / data['Close'].iloc[-5]) - 1) * 100 if len(data) >= 5 else 0

        if current > sma20 and mom_5d > -2:
            return "BULL"
        elif current < sma20 * 0.98:
            return "BEAR"
        else:
            return "NEUTRAL"

    def calculate_improved_sl_tp(self, hist: pd.DataFrame, entry_price: float) -> Tuple[float, float, float]:
        """
        IMPROVED SL/TP calculation
        - Wider SL to avoid whipsaws
        - Higher TP for better R:R
        """
        # Calculate ATR
        if len(hist) < 14:
            atr = entry_price * 0.025
        else:
            high = hist['High'].tail(14)
            low = hist['Low'].tail(14)
            close = hist['Close'].tail(14)

            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.mean()

        atr_pct = (atr / entry_price) * 100

        # IMPROVED: Wider SL range (2-3% instead of 1.5-2.5%)
        if atr_pct > 5:
            sl_pct = self.STOP_LOSS_MAX  # 3%
        elif atr_pct > 3.5:
            sl_pct = 2.5
        else:
            sl_pct = self.STOP_LOSS_BASE  # 2%

        # IMPROVED: Higher TP (4-8% instead of 4-6%)
        tp_multiplier = min(2.0, max(1.0, atr_pct / 2.5))
        tp_pct = self.TAKE_PROFIT_MIN * tp_multiplier

        # Ensure R:R >= 2.0
        if tp_pct / sl_pct < 2.0:
            tp_pct = sl_pct * 2.0

        stop_loss = entry_price * (1 - sl_pct / 100)
        take_profit = entry_price * (1 + tp_pct / 100)

        return stop_loss, take_profit, atr_pct

    def check_bounce_confirmation(self, hist: pd.DataFrame) -> Tuple[bool, str]:
        """
        CRITICAL: Check if price is BOUNCING, not still falling

        Confirmation criteria:
        1. Yesterday was down (dip)
        2. Today is UP or flat
        3. Close > Open today (bullish candle)
        4. Volume today > average
        """
        if len(hist) < 3:
            return False, "Not enough data"

        today = hist.iloc[-1]
        yesterday = hist.iloc[-2]
        day_before = hist.iloc[-3]

        # Check yesterday was a dip
        yesterday_change = (yesterday['Close'] - day_before['Close']) / day_before['Close'] * 100
        if yesterday_change > 0:
            return False, "Yesterday wasn't a dip"

        # Check today is bouncing
        today_change = (today['Close'] - yesterday['Close']) / yesterday['Close'] * 100
        if today_change < -0.5:
            return False, "Still falling today"

        # Bullish candle (close > open)
        if today['Close'] < today['Open']:
            return False, "Bearish candle today"

        # Volume confirmation
        avg_vol = hist['Volume'].tail(20).mean()
        if today['Volume'] < avg_vol * 0.8:
            return False, "Low volume"

        return True, f"Bounce confirmed: yesterday {yesterday_change:.1f}%, today {today_change:.1f}%"

    def check_rsi_reversal(self, hist: pd.DataFrame) -> Tuple[bool, float]:
        """Check if RSI is reversing from oversold"""
        if len(hist) < 15:
            return False, 50

        delta = hist['Close'].diff()
        gain = delta.where(delta > 0, 0).tail(14)
        loss = (-delta.where(delta < 0, 0)).tail(14)

        avg_gain = gain.mean()
        avg_loss = loss.mean()

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        # Want RSI 30-50 (oversold but starting to recover)
        if 30 <= rsi <= 50:
            return True, rsi
        elif rsi < 30:
            return False, rsi  # Too oversold, wait more
        else:
            return False, rsi  # Not oversold

    def simulate_trade(self, symbol: str, entry_date: str,
                       entry_price: float, stop_loss: float,
                       take_profit: float, atr_pct: float) -> Trade:
        """Simulate trade with IMPROVED exit rules"""
        trade = Trade(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_pct=atr_pct
        )

        try:
            start_date = datetime.strptime(entry_date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=30)

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                trade.exit_reason = "NO_DATA"
                return trade

        except Exception as e:
            trade.exit_reason = f"ERROR: {e}"
            return trade

        sl_pct = ((stop_loss - entry_price) / entry_price) * 100
        tp_pct = ((take_profit - entry_price) / entry_price) * 100

        peak_price = entry_price
        trough_price = entry_price
        trailing_stop = None

        for day_idx, (date, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            current_price = row['Close']
            high_price = row['High']
            low_price = row['Low']

            peak_price = max(peak_price, high_price)
            trough_price = min(trough_price, low_price)

            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100

            # 1. Check SL
            low_pnl = ((low_price - entry_price) / entry_price) * 100
            if low_pnl <= sl_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.days_held = day_idx
                break

            # 2. Check trailing stop
            if trailing_stop is not None:
                if low_price <= trailing_stop:
                    trade.exit_date = date.strftime('%Y-%m-%d')
                    trade.exit_price = trailing_stop
                    trade.exit_reason = "TRAILING_STOP"
                    trade.pnl_pct = ((trailing_stop - entry_price) / entry_price) * 100
                    trade.days_held = day_idx
                    break

            # 3. Check TP
            high_pnl = ((high_price - entry_price) / entry_price) * 100
            if high_pnl >= tp_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = take_profit
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.days_held = day_idx
                break

            # 4. Activate trailing at 3%+
            if peak_pnl_pct >= self.TRAIL_ACTIVATE_PCT:
                trail_level = entry_price * (1 + (peak_pnl_pct * self.TRAIL_PCT) / 100)
                if trailing_stop is None or trail_level > trailing_stop:
                    trailing_stop = trail_level

            # 5. Max hold (5 days)
            if day_idx >= self.MAX_HOLD_DAYS:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = current_price
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = pnl_pct
                trade.days_held = day_idx
                break

        if not trade.exit_date:
            trade.exit_reason = "STILL_HOLDING"
            trade.days_held = len(hist) - 1

        trade.peak_price = peak_price
        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trade.trough_price = trough_price
        trade.trough_pct = ((trough_price - entry_price) / entry_price) * 100

        return trade

    def find_improved_candidates(self, universe: List[str], date: str) -> List[Tuple]:
        """
        IMPROVED candidate finding with:
        1. Market regime check
        2. Bounce confirmation
        3. RSI reversal
        4. Volume confirmation
        """
        # Check market regime first
        regime = self.get_market_regime(date)
        if regime == "BEAR":
            print(f"  ⚠️ Market BEAR - skip trading")
            return []

        candidates = []
        end_date = datetime.strptime(date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=40)

        for symbol in universe:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date + timedelta(days=1))

                if len(hist) < 20:
                    continue

                current_price = hist['Close'].iloc[-1]

                # CRITICAL: Check bounce confirmation
                is_bouncing, bounce_reason = self.check_bounce_confirmation(hist)
                if not is_bouncing:
                    continue

                # Check RSI reversal
                rsi_ok, rsi = self.check_rsi_reversal(hist)
                if not rsi_ok:
                    continue

                # Calculate indicators
                sma20 = hist['Close'].tail(20).mean()
                sma50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else sma20

                # Must be in overall uptrend
                if current_price < sma50 * 0.95:
                    continue

                # Not too far from high (within 15%)
                high_20d = hist['High'].tail(20).max()
                dist_from_high = ((current_price / high_20d) - 1) * 100
                if dist_from_high < -15:
                    continue

                # Volume surge
                avg_vol = hist['Volume'].tail(20).mean()
                today_vol = hist['Volume'].iloc[-1]
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1

                if vol_ratio < 1.0:
                    continue

                # Calculate improved SL/TP
                sl, tp, atr_pct = self.calculate_improved_sl_tp(hist, current_price)

                # Calculate score
                score = 0
                reasons = []

                # Bounce confirmation (critical)
                score += 25
                reasons.append("Bounce confirmed")

                # RSI reversal
                score += 15
                reasons.append(f"RSI {rsi:.0f}")

                # Volume
                if vol_ratio > 1.5:
                    score += 15
                    reasons.append(f"Vol {vol_ratio:.1f}x")
                else:
                    score += 5

                # Uptrend
                if current_price > sma20:
                    score += 15
                    reasons.append("Above SMA20")

                # Near high
                if dist_from_high > -5:
                    score += 10
                    reasons.append(f"{dist_from_high:.0f}% from high")

                # R:R ratio
                risk = current_price - sl
                reward = tp - current_price
                rr = reward / risk if risk > 0 else 0
                if rr >= 2.5:
                    score += 15
                    reasons.append(f"R:R {rr:.1f}")
                elif rr >= 2.0:
                    score += 10

                if score >= 60:
                    candidates.append((symbol, current_price, sl, tp, atr_pct, score, reasons))

            except Exception as e:
                continue

        # Sort by score
        candidates.sort(key=lambda x: x[5], reverse=True)
        return [(c[0], c[1], c[2], c[3], c[4]) for c in candidates[:3]]

    def run_backtest(self, start_date: str, end_date: str, universe: List[str] = None) -> Dict:
        """Run improved backtest"""
        if universe is None:
            universe = [
                'NVDA', 'AMD', 'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
                'AVGO', 'MU', 'MRVL', 'QCOM', 'AMAT',
                'PLTR', 'COIN', 'SNOW', 'DDOG', 'NET', 'CRWD',
                'CRM', 'ORCL', 'NOW', 'SHOP',
                'UBER', 'JPM', 'GS', 'V', 'MA'
            ]

        print(f"\n{'='*60}")
        print(f"IMPROVED RAPID TRADER v2 BACKTEST")
        print(f"{'='*60}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Universe: {len(universe)} stocks")
        print(f"\nIMPROVEMENTS:")
        print(f"  1. Bounce confirmation (no falling knives)")
        print(f"  2. Market regime filter (skip bear markets)")
        print(f"  3. Wider SL: {self.STOP_LOSS_BASE}%-{self.STOP_LOSS_MAX}%")
        print(f"  4. Higher TP: {self.TAKE_PROFIT_MIN}%-{self.TAKE_PROFIT_MAX}%")
        print(f"  5. RSI reversal confirmation")
        print(f"{'='*60}\n")

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current = start
        total_trades = 0

        while current <= end:
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime('%Y-%m-%d')
            candidates = self.find_improved_candidates(universe, date_str)

            if candidates:
                print(f"\n{date_str}: Found {len(candidates)} qualified candidates")

                for symbol, entry_price, sl, tp, atr_pct in candidates:
                    sl_pct = ((sl - entry_price) / entry_price) * 100
                    tp_pct = ((tp - entry_price) / entry_price) * 100
                    print(f"  -> {symbol}: Entry=${entry_price:.2f}, SL={sl_pct:.1f}%, TP={tp_pct:.1f}%")

                    trade = self.simulate_trade(symbol, date_str, entry_price, sl, tp, atr_pct)

                    if trade.exit_reason and trade.exit_reason not in ["NO_DATA", "ERROR"]:
                        self.trades.append(trade)
                        total_trades += 1

                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"     {emoji} Exit: {trade.exit_reason} = {trade.pnl_pct:+.2f}% ({trade.days_held}d)")

            current += timedelta(days=7)

        return self._calculate_results()

    def _calculate_results(self) -> Dict:
        """Calculate and display results"""
        if not self.trades:
            print("\n❌ No trades executed")
            return {}

        valid_trades = [t for t in self.trades if t.exit_reason not in ["NO_DATA", "STILL_HOLDING", ""] and "ERROR" not in str(t.exit_reason)]

        if not valid_trades:
            print("\n❌ No valid trades")
            return {}

        total_trades = len(valid_trades)
        winners = [t for t in valid_trades if t.pnl_pct > 0]
        losers = [t for t in valid_trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total_trades * 100
        total_pnl = sum(t.pnl_pct for t in valid_trades)
        avg_pnl = total_pnl / total_trades

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        gross_profit = sum(t.pnl_pct for t in winners)
        gross_loss = abs(sum(t.pnl_pct for t in losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        exit_counts = {}
        for t in valid_trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        print(f"\n{'='*60}")
        print(f"IMPROVED RESULTS")
        print(f"{'='*60}")
        print(f"\nTrade Statistics:")
        print(f"  Total Trades:    {total_trades}")
        print(f"  Winners:         {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers:          {len(losers)} ({100-win_rate:.1f}%)")

        print(f"\nReturns:")
        print(f"  Total P&L:       {total_pnl:+.2f}%")
        print(f"  Avg per Trade:   {avg_pnl:+.2f}%")
        print(f"  Avg Win:         {avg_win:+.2f}%")
        print(f"  Avg Loss:        {avg_loss:+.2f}%")
        print(f"  Profit Factor:   {profit_factor:.2f}")

        print(f"\nExit Breakdown:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total_trades * 100
            trades_by_reason = [t for t in valid_trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}%")

        # Monthly breakdown
        print(f"\nMonthly Breakdown:")
        monthly_pnl = {}
        for t in valid_trades:
            month = t.entry_date[:7]
            if month not in monthly_pnl:
                monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
            monthly_pnl[month]['pnl'] += t.pnl_pct
            monthly_pnl[month]['trades'] += 1
            if t.pnl_pct > 0:
                monthly_pnl[month]['wins'] += 1

        for month in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            print(f"  {month}: {data['pnl']:+6.2f}% | {data['trades']:2} trades | {wr:.0f}% win rate")

        # Check targets
        monthly_returns = [data['pnl'] for data in monthly_pnl.values()]
        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\n{'='*60}")
        print(f"COMPARISON vs v1")
        print(f"{'='*60}")
        print(f"  Win Rate:     v1=36% → v2={win_rate:.1f}%")
        print(f"  Profit Factor: v1=0.72 → v2={profit_factor:.2f}")
        print(f"  Monthly Avg:  v1=-4.08% → v2={avg_monthly:+.2f}%")

        if avg_monthly >= 5:
            print(f"\n  ✅ บรรลุเป้า 5%+ ต่อเดือน!")
        elif avg_monthly >= 0:
            print(f"\n  🟡 กำไรแล้ว แต่ยังไม่ถึง 5%")
        else:
            print(f"\n  ❌ ยังขาดทุน ต้องปรับปรุงต่อ")

        return {
            'total_trades': total_trades,
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'monthly': monthly_pnl,
            'avg_monthly': avg_monthly
        }


def main():
    """Run improved backtest"""
    trader = ImprovedRapidTrader()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    universe = [
        'NVDA', 'AMD', 'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
        'AVGO', 'MU', 'MRVL', 'QCOM', 'AMAT',
        'PLTR', 'COIN', 'SNOW', 'DDOG', 'NET', 'CRWD',
        'CRM', 'ORCL', 'NOW', 'SHOP',
        'UBER', 'JPM', 'GS', 'V', 'MA'
    ]

    results = trader.run_backtest(start_date, end_date, universe)

    if results:
        print(f"\n{'='*60}")
        print(f"FINAL VERDICT")
        print(f"{'='*60}")

        if results['avg_monthly'] >= 5:
            print("""
✅ IMPROVED VERSION WORKS!
   - Monthly target 5%+ achieved
   - Ready for production
            """)
        else:
            print(f"""
⚠️ NEEDS MORE IMPROVEMENT
   Current: {results['avg_monthly']:+.2f}%/month
   Target: +5% to +15%/month

   Next steps to try:
   1. Stricter entry (higher score threshold)
   2. Even wider SL (3-4%)
   3. Focus on fewer, higher quality trades
   4. Add sector rotation filter
   5. Only trade top 3 sectors
            """)


if __name__ == "__main__":
    main()
