#!/usr/bin/env python3
"""
RAPID TRADER v4 - IMPROVED VERSION
====================================
แก้ปัญหาจาก v3:
1. Win rate 33% → ต้องได้ 55%+
2. 64% โดน SL → ต้องลดให้เหลือ 30%-
3. Jan -13% → ต้องมี market regime filter

การปรับปรุงใหม่:
1. MARKET REGIME FILTER - ไม่เทรดตอน SPY ลง
2. BOUNCE CONFIRMATION - รอ price bounce ก่อนเข้า
3. SECTOR FILTER - เลือกเฉพาะ sector ที่แข็งแรง
4. WIDER STOPS - กันโดน whipsaw
5. HIGHER SCORE THRESHOLD - เข้าเฉพาะ high conviction
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


FULL_UNIVERSE = {
    'Technology': [
        'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX', 'CRM', 'ORCL', 'ADBE',
        'NOW', 'PANW', 'SNOW', 'DDOG', 'ZS', 'CRWD', 'NET', 'PLTR',
    ],
    'Semiconductors': [
        'NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI',
        'MCHP', 'NXPI', 'ON', 'MRVL',
    ],
    'Finance': [
        'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'V', 'MA', 'AXP', 'PYPL', 'BLK',
    ],
    'Industrial': [
        'CAT', 'DE', 'BA', 'RTX', 'LMT', 'HON', 'GE', 'MMM', 'EMR', 'UNP', 'FDX', 'UPS',
    ],
    'Healthcare': [
        'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'AMGN', 'GILD', 'REGN', 'VRTX',
        'MDT', 'ABT', 'TMO', 'DHR', 'ISRG', 'UNH',
    ],
    'Consumer': [
        'HD', 'LOW', 'TJX', 'ROST', 'LULU', 'NKE', 'MCD', 'SBUX', 'CMG',
        'MAR', 'HLT', 'ABNB', 'BKNG', 'TSLA', 'WMT', 'COST', 'TGT', 'KO', 'PEP',
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'EOG', 'OXY', 'DVN', 'SLB', 'HAL',
        'MPC', 'VLO', 'WMB', 'KMI', 'OKE',
    ],
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL',
    ],
    'Real_Estate': [
        'PLD', 'SPG', 'O', 'EQIX', 'DLR', 'AMT', 'CCI', 'AVB', 'EQR', 'PSA',
    ],
}


@dataclass
class Trade:
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
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0
    peak_pct: float = 0.0


class ImprovedRapidTraderV4:
    """
    IMPROVED RAPID TRADER v4

    Key Improvements:
    1. MARKET REGIME - Skip bear markets (SPY < SMA20)
    2. BOUNCE CONFIRM - Wait for green candle after dip
    3. SECTOR STRENGTH - Prioritize strong sectors
    4. WIDER STOPS - 2-3% instead of 1.5-2.5%
    5. HIGHER THRESHOLD - Score >= 70 (was 60)
    """

    # IMPROVED parameters
    BASE_SL_PCT = 2.0       # Wider SL (was 1.5%)
    MAX_SL_PCT = 3.0        # Wider max SL (was 2.5%)
    BASE_TP_PCT = 5.0       # Higher TP (was 4%)
    MAX_TP_PCT = 8.0        # Higher max TP (was 6%)
    TRAIL_ACTIVATE_PCT = 3.0
    TRAIL_PCT = 0.65
    MAX_HOLD_DAYS = 5
    MIN_SCORE = 70          # Higher threshold (was 60)

    def __init__(self):
        self.trades: List[Trade] = []
        self.universe = self._build_universe()
        self.spy_cache = None
        print(f"Loaded {len(self.universe)} stocks")

    def _build_universe(self) -> List[Tuple[str, str]]:
        universe = []
        for sector, symbols in FULL_UNIVERSE.items():
            for symbol in symbols:
                universe.append((symbol, sector))
        return universe

    def get_market_regime(self, date: str) -> str:
        """Check SPY to determine market regime"""
        if self.spy_cache is None:
            end = datetime.strptime(date, '%Y-%m-%d')
            start = end - timedelta(days=60)
            ticker = yf.Ticker('SPY')
            self.spy_cache = ticker.history(start=start, end=end + timedelta(days=1))

        if len(self.spy_cache) < 20:
            return "UNKNOWN"

        mask = self.spy_cache.index <= pd.Timestamp(date)
        data = self.spy_cache[mask]

        if len(data) < 20:
            return "UNKNOWN"

        current = data['Close'].iloc[-1]
        sma20 = data['Close'].tail(20).mean()
        mom_5d = ((current / data['Close'].iloc[-5]) - 1) * 100 if len(data) >= 5 else 0

        if current > sma20 and mom_5d > -1:
            return "BULL"
        elif current < sma20 * 0.98 or mom_5d < -3:
            return "BEAR"
        else:
            return "NEUTRAL"

    def get_sector_strength(self, sector: str, date: str) -> str:
        """Check if sector is strong or weak"""
        sector_etfs = {
            'Technology': 'XLK',
            'Semiconductors': 'SMH',
            'Finance': 'XLF',
            'Industrial': 'XLI',
            'Healthcare': 'XLV',
            'Consumer': 'XLY',
            'Energy': 'XLE',
            'Utilities': 'XLU',
            'Real_Estate': 'XLRE',
        }

        etf = sector_etfs.get(sector)
        if not etf:
            return "NEUTRAL"

        try:
            end = datetime.strptime(date, '%Y-%m-%d')
            start = end - timedelta(days=30)
            ticker = yf.Ticker(etf)
            hist = ticker.history(start=start, end=end + timedelta(days=1))

            if len(hist) < 10:
                return "NEUTRAL"

            current = hist['Close'].iloc[-1]
            sma10 = hist['Close'].tail(10).mean()
            mom_5d = ((current / hist['Close'].iloc[-5]) - 1) * 100

            if current > sma10 and mom_5d > 0:
                return "STRONG"
            elif current < sma10 * 0.98 or mom_5d < -2:
                return "WEAK"
            else:
                return "NEUTRAL"
        except:
            return "NEUTRAL"

    def check_bounce_confirmation(self, hist: pd.DataFrame) -> Tuple[bool, str]:
        """
        CRITICAL: Entry only when price is BOUNCING, not falling

        Conditions:
        1. Yesterday was a dip (red candle)
        2. Today shows recovery (green candle OR close > open)
        3. Volume is reasonable
        """
        if len(hist) < 3:
            return False, "Not enough data"

        today = hist.iloc[-1]
        yesterday = hist.iloc[-2]
        day_before = hist.iloc[-3]

        # Yesterday was a dip?
        yesterday_change = (yesterday['Close'] - day_before['Close']) / day_before['Close'] * 100

        if yesterday_change > 0.5:
            return False, "Yesterday wasn't a dip"

        # Today bouncing?
        today_change = (today['Close'] - yesterday['Close']) / yesterday['Close'] * 100

        # Must show some recovery
        if today_change < -0.3:
            return False, "Still falling"

        # Bullish candle preferred
        if today['Close'] >= today['Open']:
            return True, f"Bounce! Yesterday {yesterday_change:.1f}%, Today {today_change:.1f}%"

        # Allow small red candle if overall recovery
        if today_change > 0:
            return True, f"Recovery: Today {today_change:.1f}%"

        return False, "No bounce signal"

    def calculate_improved_sl_tp(self, hist: pd.DataFrame, entry_price: float) -> Tuple[float, float, float, float]:
        """Calculate WIDER SL/TP for v4"""
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

        # WIDER SL (2-3%)
        if atr_pct > 5:
            sl_pct = self.MAX_SL_PCT  # 3%
        elif atr_pct > 3.5:
            sl_pct = 2.5
        else:
            sl_pct = self.BASE_SL_PCT  # 2%

        # HIGHER TP (5-8%)
        tp_multiplier = min(1.6, max(1.0, atr_pct / 3))
        tp_pct = self.BASE_TP_PCT * tp_multiplier

        # Ensure R:R >= 2.0
        if tp_pct / sl_pct < 2.0:
            tp_pct = sl_pct * 2.0

        stop_loss = entry_price * (1 - sl_pct / 100)
        take_profit = entry_price * (1 + tp_pct / 100)

        return stop_loss, take_profit, sl_pct, tp_pct

    def screen_candidates(self, date: str) -> List[Dict]:
        """Screen with IMPROVED criteria"""

        # 1. CHECK MARKET REGIME FIRST
        regime = self.get_market_regime(date)
        if regime == "BEAR":
            print(f"    ⚠️ Market BEAR - SKIP trading")
            return []

        candidates = []
        end_date = datetime.strptime(date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=40)

        for symbol, sector in self.universe:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date + timedelta(days=1))

                if len(hist) < 20:
                    continue

                current_price = hist['Close'].iloc[-1]

                # 2. CHECK BOUNCE CONFIRMATION
                is_bouncing, bounce_reason = self.check_bounce_confirmation(hist)
                if not is_bouncing:
                    continue

                # 3. CHECK SECTOR STRENGTH
                sector_strength = self.get_sector_strength(sector, date)
                if sector_strength == "WEAK":
                    continue

                # Calculate indicators
                sma5 = hist['Close'].tail(5).mean()
                sma20 = hist['Close'].tail(20).mean()

                if len(hist) >= 5:
                    mom_5d = ((current_price / hist['Close'].iloc[-5]) - 1) * 100
                else:
                    continue

                # Volume
                avg_vol = hist['Volume'].tail(20).mean()
                today_vol = hist['Volume'].iloc[-1]
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1

                # RSI
                delta = hist['Close'].diff().tail(14)
                gain = delta.where(delta > 0, 0).mean()
                loss = (-delta.where(delta < 0, 0)).mean()
                rs = gain / loss if loss != 0 else 100
                rsi = 100 - (100 / (1 + rs))

                # Distance from high
                high_20d = hist['High'].tail(20).max()
                dist_from_high = ((current_price / high_20d) - 1) * 100

                # Calculate SL/TP
                sl, tp, sl_pct, tp_pct = self.calculate_improved_sl_tp(hist, current_price)

                # === SCORING (Higher threshold) ===
                score = 0

                # Bounce confirmed (critical)
                score += 20

                # Sector strength bonus
                if sector_strength == "STRONG":
                    score += 15
                else:
                    score += 5

                # Volume
                if vol_ratio > 1.5:
                    score += 15
                elif vol_ratio > 1.0:
                    score += 5

                # RSI sweet spot (30-50)
                if 30 <= rsi <= 45:
                    score += 15
                elif 45 < rsi <= 55:
                    score += 10
                elif rsi > 65:
                    continue

                # Near high (within 8%)
                if dist_from_high > -5:
                    score += 15
                elif dist_from_high > -8:
                    score += 10
                elif dist_from_high < -15:
                    continue

                # Uptrend
                if current_price > sma20:
                    score += 15
                elif current_price > sma20 * 0.97:
                    score += 5
                else:
                    continue

                # R:R
                rr = tp_pct / sl_pct
                if rr >= 2.5:
                    score += 15
                elif rr >= 2.0:
                    score += 10

                # HIGHER THRESHOLD: 70+
                if score >= self.MIN_SCORE:
                    candidates.append({
                        'symbol': symbol,
                        'sector': sector,
                        'entry_price': current_price,
                        'stop_loss': sl,
                        'take_profit': tp,
                        'sl_pct': sl_pct,
                        'tp_pct': tp_pct,
                        'score': score,
                        'rsi': rsi,
                        'market_regime': regime,
                        'sector_strength': sector_strength
                    })

            except Exception as e:
                continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:5]

    def simulate_trade(self, c: Dict, entry_date: str) -> Optional[Trade]:
        """Simulate trade with improved parameters"""
        symbol = c['symbol']
        entry_price = c['entry_price']
        sl = c['stop_loss']
        tp = c['take_profit']

        trade = Trade(
            symbol=symbol,
            sector=c['sector'],
            entry_date=entry_date,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            sl_pct=c['sl_pct'],
            tp_pct=c['tp_pct'],
            score=c['score'],
            market_regime=c['market_regime']
        )

        try:
            start = datetime.strptime(entry_date, '%Y-%m-%d')
            end = start + timedelta(days=30)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, end=end)

            if hist.empty:
                return None
        except:
            return None

        sl_pct = -c['sl_pct']
        tp_pct = c['tp_pct']
        peak_price = entry_price
        trailing_stop = None

        for day_idx, (date, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            high = row['High']
            low = row['Low']
            close = row['Close']

            peak_price = max(peak_price, high)
            pnl_pct = ((close - entry_price) / entry_price) * 100
            peak_pnl = ((peak_price - entry_price) / entry_price) * 100
            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100

            # 1. Stop Loss
            if low_pnl <= sl_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = sl
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.days_held = day_idx
                break

            # 2. Trailing
            if trailing_stop is not None and low <= trailing_stop:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = trailing_stop
                trade.exit_reason = "TRAILING"
                trade.pnl_pct = ((trailing_stop - entry_price) / entry_price) * 100
                trade.days_held = day_idx
                break

            # 3. Take Profit
            if high_pnl >= tp_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = tp
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.days_held = day_idx
                break

            # 4. Activate trailing
            if peak_pnl >= self.TRAIL_ACTIVATE_PCT:
                trail_level = entry_price * (1 + (peak_pnl * self.TRAIL_PCT) / 100)
                if trailing_stop is None or trail_level > trailing_stop:
                    trailing_stop = trail_level

            # 5. Max hold
            if day_idx >= self.MAX_HOLD_DAYS:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = pnl_pct
                trade.days_held = day_idx
                break

        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100

        if not trade.exit_date:
            return None

        return trade

    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """Run improved backtest"""
        print(f"\n{'='*70}")
        print(f"RAPID TRADER v4 - IMPROVED BACKTEST")
        print(f"{'='*70}")
        print(f"IMPROVEMENTS:")
        print(f"  1. Market Regime Filter (skip BEAR)")
        print(f"  2. Bounce Confirmation (no falling knives)")
        print(f"  3. Sector Strength Filter")
        print(f"  4. Wider SL: {self.BASE_SL_PCT}%-{self.MAX_SL_PCT}%")
        print(f"  5. Higher TP: {self.BASE_TP_PCT}%-{self.MAX_TP_PCT}%")
        print(f"  6. Higher Score Threshold: {self.MIN_SCORE}+")
        print(f"{'='*70}\n")

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current = start
        week_count = 0

        while current <= end:
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime('%Y-%m-%d')
            week_count += 1

            # Reset SPY cache for each week
            self.spy_cache = None

            print(f"\n[Week {week_count}] {date_str}")

            candidates = self.screen_candidates(date_str)

            if candidates:
                print(f"  Found {len(candidates)} high-quality candidates")

                for c in candidates[:2]:  # Only top 2
                    print(f"    -> {c['symbol']} ({c['sector']}): Score={c['score']}, Sector={c['sector_strength']}")

                    trade = self.simulate_trade(c, date_str)

                    if trade:
                        self.trades.append(trade)
                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"       {emoji} Exit: {trade.exit_reason} @ {trade.pnl_pct:+.2f}%")
            else:
                print(f"  No qualified candidates")

            current += timedelta(days=7)

        return self._calculate_results()

    def _calculate_results(self) -> Dict:
        if not self.trades:
            print("\n❌ No trades")
            return {}

        valid = [t for t in self.trades if t.exit_reason]

        if not valid:
            return {}

        total = len(valid)
        winners = [t for t in valid if t.pnl_pct > 0]
        losers = [t for t in valid if t.pnl_pct <= 0]

        win_rate = len(winners) / total * 100
        total_pnl = sum(t.pnl_pct for t in valid)
        avg_pnl = total_pnl / total

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        gross_profit = sum(t.pnl_pct for t in winners)
        gross_loss = abs(sum(t.pnl_pct for t in losers))
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Monthly
        monthly = {}
        for t in valid:
            m = t.entry_date[:7]
            if m not in monthly:
                monthly[m] = {'pnl': 0, 'trades': 0, 'wins': 0}
            monthly[m]['pnl'] += t.pnl_pct
            monthly[m]['trades'] += 1
            if t.pnl_pct > 0:
                monthly[m]['wins'] += 1

        # Exit breakdown
        exits = {}
        for t in valid:
            exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

        print(f"\n{'='*70}")
        print(f"v4 IMPROVED RESULTS")
        print(f"{'='*70}")

        print(f"\n📊 STATS:")
        print(f"  Total: {total} | Winners: {len(winners)} ({win_rate:.1f}%) | Losers: {len(losers)}")

        print(f"\n💰 RETURNS:")
        print(f"  Total P&L: {total_pnl:+.2f}%")
        print(f"  Avg Trade: {avg_pnl:+.2f}%")
        print(f"  Avg Win:   {avg_win:+.2f}%")
        print(f"  Avg Loss:  {avg_loss:+.2f}%")
        print(f"  Profit Factor: {pf:.2f}")

        print(f"\n🎯 EXITS:")
        for r, c in sorted(exits.items(), key=lambda x: -x[1]):
            trades = [t for t in valid if t.exit_reason == r]
            avg = sum(t.pnl_pct for t in trades) / len(trades)
            print(f"  {r}: {c} ({c/total*100:.0f}%) avg {avg:+.2f}%")

        print(f"\n📅 MONTHLY:")
        for m in sorted(monthly.keys()):
            d = monthly[m]
            wr = d['wins'] / d['trades'] * 100 if d['trades'] > 0 else 0
            print(f"  {m}: {d['pnl']:+.2f}% | {d['trades']} trades | {wr:.0f}% WR")

        monthly_returns = [d['pnl'] for d in monthly.values()]
        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\n{'='*70}")
        print(f"MONTHLY AVERAGE: {avg_monthly:+.2f}%")
        print(f"TARGET: +5% to +15%")

        if avg_monthly >= 5:
            print(f"✅ TARGET ACHIEVED!")
        elif avg_monthly >= 0:
            print(f"🟡 Profitable but needs improvement")
        else:
            print(f"❌ Not profitable yet")

        return {
            'total_trades': total,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'profit_factor': pf,
            'avg_monthly': avg_monthly,
            'monthly': monthly
        }


def main():
    trader = ImprovedRapidTraderV4()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    results = trader.run_backtest(start_date, end_date)

    if results:
        print(f"\n{'='*70}")
        print(f"COMPARISON: v3 vs v4")
        print(f"{'='*70}")
        print(f"""
v3 (Original):
  Win Rate:     33.3%
  Avg Monthly:  -0.58%
  Profit Factor: 0.95

v4 (Improved):
  Win Rate:     {results['win_rate']:.1f}%
  Avg Monthly:  {results['avg_monthly']:+.2f}%
  Profit Factor: {results['profit_factor']:.2f}

Improvement: {'+' if results['avg_monthly'] > -0.58 else ''}{results['avg_monthly'] - (-0.58):.2f}% per month
        """)


if __name__ == "__main__":
    main()
