#!/usr/bin/env python3
"""
REALISTIC COMPARISON: v3 (Buy Dip) vs v4 (Bounce Confirmation)
===============================================================
เทสตามความจริงทุกประการ:
1. ใช้หุ้นจาก AI Universe จริง (ไม่ใช่หุ้นเดิมซ้ำๆ)
2. Screen หุ้นทุกสัปดาห์ (หุ้นจะต่างกันไป)
3. Simulate การซื้อขายตามจริง
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


@dataclass
class Trade:
    symbol: str
    strategy: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    score: int
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0


# Full universe for testing
FULL_UNIVERSE = [
    # Tech
    'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX', 'NVDA', 'AMD', 'TSLA',
    'CRM', 'ORCL', 'ADBE', 'NOW', 'PANW', 'SNOW', 'DDOG', 'PLTR', 'CRWD',
    # Semiconductors
    'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI', 'MRVL', 'NXPI',
    # Finance
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'PYPL', 'BLK',
    # Industrial
    'CAT', 'DE', 'BA', 'RTX', 'LMT', 'HON', 'GE', 'UNP', 'FDX', 'UPS',
    # Healthcare
    'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'AMGN', 'GILD', 'REGN', 'MDT', 'ABT',
    # Consumer
    'HD', 'LOW', 'TJX', 'LULU', 'NKE', 'MCD', 'SBUX', 'CMG', 'ABNB', 'BKNG',
    'WMT', 'COST', 'TGT', 'KO', 'PEP', 'DIS', 'CMCSA',
    # Energy
    'XOM', 'CVX', 'COP', 'EOG', 'OXY', 'SLB', 'HAL', 'MPC', 'VLO',
    # Others
    'NEE', 'DUK', 'SO', 'PLD', 'EQIX', 'AMT', 'CCI',
]


class RealisticComparison:
    """Compare v3 vs v4 using real screening"""

    SL_PCT = 2.0
    TP_PCT = 5.0
    MAX_HOLD = 4

    def __init__(self):
        self.trades_v3: List[Trade] = []
        self.trades_v4: List[Trade] = []

    def get_historical_data(self, symbol: str, end_date: datetime) -> Optional[pd.DataFrame]:
        """Get historical data up to specific date"""
        try:
            start_date = end_date - timedelta(days=40)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date + timedelta(days=1))
            if len(hist) >= 20:
                return hist
        except:
            pass
        return None

    def screen_v3(self, date: datetime) -> List[Dict]:
        """
        v3 screening: Buy when price is FALLING (original logic)
        - mom_1d < 0 (today is down)
        - price < SMA5
        """
        candidates = []

        for symbol in FULL_UNIVERSE:
            hist = self.get_historical_data(symbol, date)
            if hist is None or len(hist) < 10:
                continue

            try:
                close = hist['Close']
                current = close.iloc[-1]
                prev = close.iloc[-2]
                sma5 = close.tail(5).mean()
                sma20 = close.tail(20).mean()

                mom_1d = ((current / prev) - 1) * 100
                mom_5d = ((current / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0

                # v3: Enter when FALLING
                if mom_1d > 0.5:  # Not a dip
                    continue
                if current > sma5 * 1.01:  # Not below SMA5
                    continue

                # Calculate score
                score = 0
                if -8 <= mom_5d <= -3:
                    score += 35
                elif -3 < mom_5d <= 0:
                    score += 25
                if mom_1d <= -1.5:
                    score += 15
                if current > sma20:
                    score += 20

                if score >= 50:
                    sl = current * (1 - self.SL_PCT / 100)
                    tp = current * (1 + self.TP_PCT / 100)
                    candidates.append({
                        'symbol': symbol,
                        'entry_price': current,
                        'stop_loss': sl,
                        'take_profit': tp,
                        'score': score,
                        'reason': f"v3: Dip {mom_1d:.1f}%, mom5d {mom_5d:.1f}%"
                    })
            except:
                continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:5]

    def screen_v4(self, date: datetime) -> List[Dict]:
        """
        v4 screening: Buy AFTER bounce confirmation
        - yesterday was down
        - today is up (green candle)
        """
        candidates = []

        for symbol in FULL_UNIVERSE:
            hist = self.get_historical_data(symbol, date)
            if hist is None or len(hist) < 10:
                continue

            try:
                close = hist['Close']
                open_prices = hist['Open']
                current = close.iloc[-1]
                sma5 = close.tail(5).mean()
                sma20 = close.tail(20).mean()

                # Yesterday's change
                mom_yesterday = ((close.iloc[-2] / close.iloc[-3]) - 1) * 100
                # Today's change
                mom_1d = ((current / close.iloc[-2]) - 1) * 100
                mom_5d = ((current / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0

                today_open = open_prices.iloc[-1]

                # v4: Enter when BOUNCING
                if mom_yesterday >= -0.5:  # Yesterday wasn't a dip
                    continue
                if mom_1d < -0.3:  # Still falling today
                    continue
                if current < today_open:  # Not a green candle
                    if mom_1d <= 0.3:  # And not strong recovery
                        continue

                # Should still be in oversold zone
                if current > sma5 * 1.03:
                    continue

                # Calculate score
                score = 25  # Base for bounce confirmation
                if -8 <= mom_5d <= -3:
                    score += 20
                if mom_1d > 1.0:
                    score += 15
                if current > sma20:
                    score += 20

                if score >= 50:
                    sl = current * (1 - self.SL_PCT / 100)
                    tp = current * (1 + self.TP_PCT / 100)
                    candidates.append({
                        'symbol': symbol,
                        'entry_price': current,
                        'stop_loss': sl,
                        'take_profit': tp,
                        'score': score,
                        'reason': f"v4: Yesterday {mom_yesterday:.1f}%, Today {mom_1d:.1f}%"
                    })
            except:
                continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:5]

    def simulate_trade(self, candidate: Dict, entry_date: datetime, strategy: str) -> Optional[Trade]:
        """Simulate trade from entry to exit"""
        symbol = candidate['symbol']
        entry_price = candidate['entry_price']
        sl = candidate['stop_loss']
        tp = candidate['take_profit']

        trade = Trade(
            symbol=symbol,
            strategy=strategy,
            entry_date=entry_date.strftime('%Y-%m-%d'),
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            score=candidate['score']
        )

        sl_pct = ((sl - entry_price) / entry_price) * 100
        tp_pct = ((tp - entry_price) / entry_price) * 100

        try:
            end = entry_date + timedelta(days=20)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date, end=end)

            if hist.empty:
                return None
        except:
            return None

        for day_idx, (date, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            low = row['Low']
            high = row['High']
            close = row['Close']

            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100
            close_pnl = ((close - entry_price) / entry_price) * 100

            if low_pnl <= sl_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = sl
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.days_held = day_idx
                return trade

            if high_pnl >= tp_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = tp
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.days_held = day_idx
                return trade

            if day_idx >= self.MAX_HOLD:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = close_pnl
                trade.days_held = day_idx
                return trade

        return None

    def run_comparison(self, weeks_back: int = 8):
        """Run comparison over historical weeks"""
        print(f"\n{'='*70}")
        print(f"REALISTIC v3 vs v4 COMPARISON")
        print(f"{'='*70}")
        print(f"\nv3: Buy when price is FALLING (original)")
        print(f"v4: Buy AFTER bounce confirmation (new)")
        print(f"\nPeriod: Last {weeks_back} weeks")
        print(f"Universe: {len(FULL_UNIVERSE)} stocks")
        print(f"{'='*70}\n")

        end = datetime.now()

        for week in range(weeks_back):
            date = end - timedelta(days=7 * (weeks_back - week))

            # Skip weekends
            while date.weekday() >= 5:
                date += timedelta(days=1)

            date_str = date.strftime('%Y-%m-%d')
            print(f"\n[Week {week+1}] {date_str}")

            # Screen v3
            v3_candidates = self.screen_v3(date)
            if v3_candidates:
                for c in v3_candidates[:2]:
                    print(f"  v3: {c['symbol']} Score={c['score']} - {c['reason']}")
                    trade = self.simulate_trade(c, date, "v3")
                    if trade:
                        self.trades_v3.append(trade)
                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"      {emoji} {trade.exit_reason} {trade.pnl_pct:+.2f}%")

            # Screen v4
            v4_candidates = self.screen_v4(date)
            if v4_candidates:
                for c in v4_candidates[:2]:
                    print(f"  v4: {c['symbol']} Score={c['score']} - {c['reason']}")
                    trade = self.simulate_trade(c, date, "v4")
                    if trade:
                        self.trades_v4.append(trade)
                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"      {emoji} {trade.exit_reason} {trade.pnl_pct:+.2f}%")

            if not v3_candidates and not v4_candidates:
                print(f"  No candidates from either strategy")

        self._show_results()

    def _show_results(self):
        """Show comparison results"""
        print(f"\n{'='*70}")
        print(f"FINAL COMPARISON RESULTS")
        print(f"{'='*70}")

        for name, trades in [("v3 (ซื้อตอนตก)", self.trades_v3),
                             ("v4 (รอ bounce)", self.trades_v4)]:
            if not trades:
                print(f"\n{name}: No trades")
                continue

            total = len(trades)
            winners = [t for t in trades if t.pnl_pct > 0]
            losers = [t for t in trades if t.pnl_pct <= 0]

            win_rate = len(winners) / total * 100
            total_pnl = sum(t.pnl_pct for t in trades)
            avg_pnl = total_pnl / total

            sl_count = len([t for t in trades if t.exit_reason == "STOP_LOSS"])

            print(f"\n{name}:")
            print(f"  Trades: {total}")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Total P&L: {total_pnl:+.2f}%")
            print(f"  Avg Trade: {avg_pnl:+.2f}%")
            print(f"  Stop Loss hits: {sl_count} ({sl_count/total*100:.0f}%)")

        if self.trades_v3 and self.trades_v4:
            v3_wr = len([t for t in self.trades_v3 if t.pnl_pct > 0]) / len(self.trades_v3) * 100
            v4_wr = len([t for t in self.trades_v4 if t.pnl_pct > 0]) / len(self.trades_v4) * 100

            v3_avg = sum(t.pnl_pct for t in self.trades_v3) / len(self.trades_v3)
            v4_avg = sum(t.pnl_pct for t in self.trades_v4) / len(self.trades_v4)

            v3_sl = len([t for t in self.trades_v3 if t.exit_reason == "STOP_LOSS"]) / len(self.trades_v3) * 100
            v4_sl = len([t for t in self.trades_v4 if t.exit_reason == "STOP_LOSS"]) / len(self.trades_v4) * 100

            print(f"\n{'='*70}")
            print(f"COMPARISON SUMMARY")
            print(f"{'='*70}")
            print(f"\n  Win Rate:      v3={v3_wr:.1f}% vs v4={v4_wr:.1f}%  {'✅ v4' if v4_wr > v3_wr else '⚠️ v3'}")
            print(f"  Avg Trade:     v3={v3_avg:+.2f}% vs v4={v4_avg:+.2f}%  {'✅ v4' if v4_avg > v3_avg else '⚠️ v3'}")
            print(f"  SL Rate:       v3={v3_sl:.0f}% vs v4={v4_sl:.0f}%  {'✅ v4' if v4_sl < v3_sl else '⚠️ v3'}")

            if v4_wr > v3_wr and v4_avg > v3_avg and v4_sl < v3_sl:
                print(f"\n  🏆 v4 (Bounce Confirmation) WINS!")
            elif v3_wr > v4_wr and v3_avg > v4_avg:
                print(f"\n  ⚠️ v3 ดีกว่าในช่วงนี้")
            else:
                print(f"\n  🟡 ผลใกล้เคียง - ต้องทดสอบเพิ่ม")


def main():
    comparison = RealisticComparison()
    comparison.run_comparison(weeks_back=8)


if __name__ == "__main__":
    main()
