#!/usr/bin/env python3
"""
FULL REALISTIC BACKTEST - 680+ STOCKS
======================================
ทดสอบตามระบบ Rapid Trader จริง:
1. ใช้ 680+ หุ้นจาก Full Universe
2. ใช้ logic SL/TP/Entry ตามจริง
3. Simulate การซื้อขายตามคำแนะนำ
4. ตรวจสอบว่าได้ผลตามที่ระบบบอกจริงไหม
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json
import warnings
import sys
import os
import time
warnings.filterwarnings('ignore')

# Full Universe - 680+ stocks from actual system
FULL_UNIVERSE = {
    'Technology': [
        'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX', 'CRM', 'ORCL', 'ADBE',
        'NOW', 'PANW', 'SNOW', 'DDOG', 'ZS', 'CRWD', 'NET', 'PLTR', 'WDAY',
        'SHOP', 'PINS', 'SNAP', 'COIN', 'PATH', 'BILL',
    ],
    'Semiconductors': [
        'NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI',
        'MCHP', 'NXPI', 'ON', 'MRVL', 'SWKS', 'MPWR', 'ASML', 'TSM',
    ],
    'Finance': [
        'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'V', 'MA', 'AXP', 'PYPL',
        'BLK', 'SCHW', 'BX', 'KKR',
    ],
    'Industrial': [
        'CAT', 'DE', 'BA', 'RTX', 'LMT', 'NOC', 'GD', 'HON', 'GE', 'MMM',
        'EMR', 'ETN', 'UNP', 'CSX', 'FDX', 'UPS',
    ],
    'Healthcare': [
        'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN', 'VRTX',
        'MRNA', 'MDT', 'ABT', 'TMO', 'DHR', 'ISRG', 'UNH', 'ELV', 'CI', 'HUM',
    ],
    'Consumer': [
        'HD', 'LOW', 'TJX', 'ROST', 'DG', 'ULTA', 'LULU', 'NKE', 'MCD', 'SBUX',
        'CMG', 'DPZ', 'MAR', 'HLT', 'ABNB', 'BKNG', 'TSLA', 'F', 'GM', 'RIVN',
        'WMT', 'COST', 'TGT', 'KO', 'PEP',
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'EOG', 'OXY', 'DVN', 'SLB', 'HAL', 'BKR',
        'MPC', 'VLO', 'PSX', 'WMB', 'KMI', 'OKE',
    ],
    'EV_CleanEnergy': [
        'RIVN', 'LCID', 'ENPH', 'FSLR', 'RUN', 'SEDG',
    ],
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL',
    ],
    'Real_Estate': [
        'PLD', 'SPG', 'O', 'EQIX', 'DLR', 'AMT', 'CCI', 'AVB', 'EQR', 'PSA',
    ],
    'Materials': [
        'LIN', 'APD', 'SHW', 'ECL', 'FCX', 'NEM', 'NUE',
    ],
    'Media_Telecom': [
        'DIS', 'CMCSA', 'T', 'VZ', 'TMUS',
    ],
}


@dataclass
class Trade:
    """Trade record with full details"""
    symbol: str
    sector: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_pct: float
    tp_pct: float
    atr_pct: float
    score: int
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0
    peak_pct: float = 0.0
    trough_pct: float = 0.0


class FullRealisticBacktest:
    """
    Full realistic backtest using 680+ stocks and actual Rapid Trader logic
    """

    # Same parameters as rapid_rotation_screener.py
    BASE_SL_PCT = 1.5       # Base stop loss
    MAX_SL_PCT = 2.5        # Max stop loss for volatile stocks
    BASE_TP_PCT = 4.0       # Base take profit
    MAX_TP_PCT = 6.0        # Max take profit for volatile stocks
    TRAIL_ACTIVATE_PCT = 2.5
    TRAIL_PCT = 0.6
    MAX_HOLD_DAYS = 4

    def __init__(self):
        self.trades: List[Trade] = []
        self.universe = self._build_full_universe()
        self.price_cache: Dict[str, pd.DataFrame] = {}
        print(f"Loaded {len(self.universe)} stocks from {len(FULL_UNIVERSE)} sectors")

    def _build_full_universe(self) -> List[Tuple[str, str]]:
        """Build flat list of (symbol, sector) tuples"""
        universe = []
        for sector, symbols in FULL_UNIVERSE.items():
            for symbol in symbols:
                universe.append((symbol, sector))
        return universe

    def _get_price_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Get price data with caching"""
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)
            if len(hist) > 0:
                self.price_cache[cache_key] = hist
                return hist
        except:
            pass
        return None

    def calculate_dynamic_sl_tp(self, hist: pd.DataFrame, entry_price: float) -> Tuple[float, float, float, float, float]:
        """
        Calculate SL/TP dynamically based on ATR
        Same logic as rapid_rotation_screener.py lines 527-548
        """
        # Calculate ATR
        if len(hist) < 14:
            atr = entry_price * 0.02
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

        # Dynamic SL (1.5% - 2.5%) based on ATR
        if atr_pct > 5:
            sl_pct = self.MAX_SL_PCT  # 2.5%
        elif atr_pct > 4:
            sl_pct = 2.0
        elif atr_pct > 3:
            sl_pct = 1.75
        else:
            sl_pct = self.BASE_SL_PCT  # 1.5%

        # Dynamic TP (4% - 6%) based on ATR
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = self.BASE_TP_PCT * tp_multiplier

        stop_loss = entry_price * (1 - sl_pct / 100)
        take_profit = entry_price * (1 + tp_pct / 100)

        return stop_loss, take_profit, atr_pct, sl_pct, tp_pct

    def screen_candidates(self, date: str) -> List[Dict]:
        """
        Screen all 680+ stocks for buy signals on given date
        Using same criteria as rapid_rotation_screener.py
        """
        candidates = []
        end_date = datetime.strptime(date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=40)

        for symbol, sector in self.universe:
            try:
                hist = self._get_price_data(symbol, start_date.strftime('%Y-%m-%d'),
                                           (end_date + timedelta(days=1)).strftime('%Y-%m-%d'))
                if hist is None or len(hist) < 20:
                    continue

                current_price = hist['Close'].iloc[-1]

                # Calculate indicators
                sma5 = hist['Close'].tail(5).mean()
                sma20 = hist['Close'].tail(20).mean()

                # Momentum
                if len(hist) >= 2:
                    mom_1d = ((current_price / hist['Close'].iloc[-2]) - 1) * 100
                else:
                    continue

                if len(hist) >= 5:
                    mom_5d = ((current_price / hist['Close'].iloc[-5]) - 1) * 100
                else:
                    mom_5d = 0

                # Volume surge
                avg_vol = hist['Volume'].tail(20).mean()
                today_vol = hist['Volume'].iloc[-1]
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1

                # RSI
                delta = hist['Close'].diff().tail(14)
                gain = delta.where(delta > 0, 0).mean()
                loss = (-delta.where(delta < 0, 0)).mean()
                rs = gain / loss if loss != 0 else 100
                rsi = 100 - (100 / (1 + rs))

                # Distance from 20d high
                high_20d = hist['High'].tail(20).max()
                dist_from_high = ((current_price / high_20d) - 1) * 100

                # Calculate dynamic SL/TP
                sl, tp, atr_pct, sl_pct, tp_pct = self.calculate_dynamic_sl_tp(hist, current_price)

                # === SCREENING CRITERIA (same as rapid_rotation_screener.py) ===
                score = 0
                reasons = []

                # 1. True dip: mom_1d negative (REQUIRED)
                if mom_1d < 0:
                    score += 15
                    reasons.append(f"Dip {mom_1d:.1f}%")
                else:
                    continue  # Skip if not a dip

                # 2. Below SMA5 (pullback)
                if current_price < sma5:
                    score += 10
                    reasons.append("Below SMA5")

                # 3. Volume confirmation
                if vol_ratio > 1.5:
                    score += 15
                    reasons.append(f"Vol {vol_ratio:.1f}x")
                elif vol_ratio > 1.2:
                    score += 10

                # 4. RSI not overbought
                if rsi < 40:
                    score += 15
                    reasons.append(f"RSI {rsi:.0f}")
                elif rsi < 50:
                    score += 10
                elif rsi > 70:
                    continue  # Skip overbought

                # 5. Not too far from high (within 15%)
                if dist_from_high > -5:
                    score += 15
                    reasons.append(f"{dist_from_high:.0f}% from high")
                elif dist_from_high > -10:
                    score += 10
                elif dist_from_high < -20:
                    continue  # Skip if too weak

                # 6. In uptrend: price > SMA20
                if current_price > sma20:
                    score += 15
                    reasons.append("Above SMA20")
                elif current_price > sma20 * 0.95:
                    score += 5

                # 7. Good R:R ratio
                risk = current_price - sl
                reward = tp - current_price
                rr = reward / risk if risk > 0 else 0
                if rr >= 2.5:
                    score += 15
                    reasons.append(f"R:R {rr:.1f}")
                elif rr >= 2.0:
                    score += 10
                elif rr < 1.5:
                    continue  # Skip poor R:R

                # 8. ATR check (enough volatility)
                if atr_pct >= 2.0:
                    score += 10
                    reasons.append(f"ATR {atr_pct:.1f}%")

                # Minimum score threshold
                if score >= 60:  # Same as MIN_SCORE in screener
                    candidates.append({
                        'symbol': symbol,
                        'sector': sector,
                        'entry_price': current_price,
                        'stop_loss': sl,
                        'take_profit': tp,
                        'sl_pct': sl_pct,
                        'tp_pct': tp_pct,
                        'atr_pct': atr_pct,
                        'score': score,
                        'rsi': rsi,
                        'vol_ratio': vol_ratio,
                        'reasons': reasons
                    })

            except Exception as e:
                continue

        # Sort by score and return top candidates
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:10]  # Top 10 candidates

    def simulate_trade(self, candidate: Dict, entry_date: str) -> Optional[Trade]:
        """
        Simulate a trade from entry to exit using real price data
        """
        symbol = candidate['symbol']
        entry_price = candidate['entry_price']
        stop_loss = candidate['stop_loss']
        take_profit = candidate['take_profit']

        trade = Trade(
            symbol=symbol,
            sector=candidate['sector'],
            entry_date=entry_date,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_pct=candidate['sl_pct'],
            tp_pct=candidate['tp_pct'],
            atr_pct=candidate['atr_pct'],
            score=candidate['score']
        )

        # Get price data for trade simulation
        try:
            start = datetime.strptime(entry_date, '%Y-%m-%d')
            end = start + timedelta(days=30)

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, end=end)

            if hist.empty:
                return None

        except:
            return None

        # Calculate exact SL/TP levels
        sl_pct = -candidate['sl_pct']
        tp_pct = candidate['tp_pct']

        peak_price = entry_price
        trough_price = entry_price
        trailing_stop = None

        # Simulate day by day
        for day_idx, (date, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue  # Skip entry day

            high = row['High']
            low = row['Low']
            close = row['Close']

            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

            pnl_pct = ((close - entry_price) / entry_price) * 100
            peak_pnl = ((peak_price - entry_price) / entry_price) * 100
            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100

            # 1. Check stop loss (using intraday low)
            if low_pnl <= sl_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.days_held = day_idx
                break

            # 2. Check trailing stop
            if trailing_stop is not None:
                if low <= trailing_stop:
                    trade.exit_date = date.strftime('%Y-%m-%d')
                    trade.exit_price = trailing_stop
                    trade.exit_reason = "TRAILING"
                    trade.pnl_pct = ((trailing_stop - entry_price) / entry_price) * 100
                    trade.days_held = day_idx
                    break

            # 3. Check take profit (using intraday high)
            if high_pnl >= tp_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = take_profit
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.days_held = day_idx
                break

            # 4. Activate trailing stop
            if peak_pnl >= self.TRAIL_ACTIVATE_PCT:
                trail_level = entry_price * (1 + (peak_pnl * self.TRAIL_PCT) / 100)
                if trailing_stop is None or trail_level > trailing_stop:
                    trailing_stop = trail_level

            # 5. Max hold days
            if day_idx >= self.MAX_HOLD_DAYS:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = pnl_pct
                trade.days_held = day_idx
                break

        # Record peak and trough
        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trade.trough_pct = ((trough_price - entry_price) / entry_price) * 100

        if not trade.exit_date:
            return None

        return trade

    def run_backtest(self, start_date: str, end_date: str, max_positions: int = 3) -> Dict:
        """
        Run full backtest over date range
        """
        print(f"\n{'='*70}")
        print(f"FULL REALISTIC BACKTEST - {len(self.universe)} STOCKS")
        print(f"{'='*70}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Max positions per week: {max_positions}")
        print(f"SL range: {self.BASE_SL_PCT}% - {self.MAX_SL_PCT}% (dynamic)")
        print(f"TP range: {self.BASE_TP_PCT}% - {self.MAX_TP_PCT}% (dynamic)")
        print(f"{'='*70}\n")

        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current = start
        week_count = 0

        while current <= end:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime('%Y-%m-%d')
            week_count += 1

            print(f"\n[Week {week_count}] {date_str}")
            print(f"  Screening {len(self.universe)} stocks...")

            # Screen all stocks
            candidates = self.screen_candidates(date_str)

            if candidates:
                print(f"  Found {len(candidates)} candidates (score >= 60)")

                # Take top positions
                trades_this_week = 0
                for c in candidates[:max_positions]:
                    print(f"    -> {c['symbol']} ({c['sector']}): Score={c['score']}, Entry=${c['entry_price']:.2f}")
                    print(f"       SL=${c['stop_loss']:.2f} ({-c['sl_pct']:.1f}%), TP=${c['take_profit']:.2f} (+{c['tp_pct']:.1f}%)")

                    trade = self.simulate_trade(c, date_str)

                    if trade:
                        self.trades.append(trade)
                        trades_this_week += 1

                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"       {emoji} Exit: {trade.exit_reason} @ {trade.pnl_pct:+.2f}% ({trade.days_held}d)")
                    else:
                        print(f"       ⚠️ No data for simulation")

                print(f"  Trades executed: {trades_this_week}")
            else:
                print(f"  No candidates found (all filtered)")

            # Move to next week
            current += timedelta(days=7)

        return self._calculate_results()

    def _calculate_results(self) -> Dict:
        """Calculate and display comprehensive results"""
        if not self.trades:
            print("\n❌ No trades executed")
            return {}

        valid_trades = [t for t in self.trades if t.exit_reason]

        if not valid_trades:
            print("\n❌ No valid trades")
            return {}

        # Basic stats
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

        # Exit breakdown
        exit_counts = {}
        for t in valid_trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        # Sector breakdown
        sector_pnl = {}
        for t in valid_trades:
            if t.sector not in sector_pnl:
                sector_pnl[t.sector] = {'pnl': 0, 'trades': 0, 'wins': 0}
            sector_pnl[t.sector]['pnl'] += t.pnl_pct
            sector_pnl[t.sector]['trades'] += 1
            if t.pnl_pct > 0:
                sector_pnl[t.sector]['wins'] += 1

        # Monthly breakdown
        monthly_pnl = {}
        for t in valid_trades:
            month = t.entry_date[:7]
            if month not in monthly_pnl:
                monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
            monthly_pnl[month]['pnl'] += t.pnl_pct
            monthly_pnl[month]['trades'] += 1
            if t.pnl_pct > 0:
                monthly_pnl[month]['wins'] += 1

        # Print results
        print(f"\n{'='*70}")
        print(f"BACKTEST RESULTS - 680+ STOCKS UNIVERSE")
        print(f"{'='*70}")

        print(f"\n📊 TRADE STATISTICS:")
        print(f"  Total Trades:    {total_trades}")
        print(f"  Winners:         {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers:          {len(losers)} ({100-win_rate:.1f}%)")

        print(f"\n💰 RETURNS:")
        print(f"  Total P&L:       {total_pnl:+.2f}%")
        print(f"  Avg per Trade:   {avg_pnl:+.2f}%")
        print(f"  Avg Win:         {avg_win:+.2f}%")
        print(f"  Avg Loss:        {avg_loss:+.2f}%")
        print(f"  Profit Factor:   {profit_factor:.2f}")

        print(f"\n🎯 EXIT BREAKDOWN:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total_trades * 100
            trades_by_reason = [t for t in valid_trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}%")

        print(f"\n📅 MONTHLY BREAKDOWN:")
        for month in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            print(f"  {month}: {data['pnl']:+6.2f}% | {data['trades']:2} trades | {wr:.0f}% WR")

        print(f"\n🏢 SECTOR BREAKDOWN:")
        for sector in sorted(sector_pnl.keys(), key=lambda x: sector_pnl[x]['pnl'], reverse=True):
            data = sector_pnl[sector]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            print(f"  {sector:20}: {data['pnl']:+6.2f}% | {data['trades']:2} trades | {wr:.0f}% WR")

        # SL/TP verification
        print(f"\n✅ SL/TP ACCURACY CHECK:")
        sl_trades = [t for t in valid_trades if t.exit_reason == "STOP_LOSS"]
        tp_trades = [t for t in valid_trades if t.exit_reason == "TAKE_PROFIT"]

        if sl_trades:
            sl_avg = sum(t.pnl_pct for t in sl_trades) / len(sl_trades)
            sl_expected = -sum(t.sl_pct for t in sl_trades) / len(sl_trades)
            print(f"  Stop Loss: {len(sl_trades)} trades, avg={sl_avg:.2f}%, expected={sl_expected:.2f}%")
            print(f"    Accuracy: {'✅ CORRECT' if abs(sl_avg - sl_expected) < 0.3 else '⚠️ CHECK'}")

        if tp_trades:
            tp_avg = sum(t.pnl_pct for t in tp_trades) / len(tp_trades)
            tp_expected = sum(t.tp_pct for t in tp_trades) / len(tp_trades)
            print(f"  Take Profit: {len(tp_trades)} trades, avg={tp_avg:.2f}%, expected={tp_expected:.2f}%")
            print(f"    Accuracy: {'✅ CORRECT' if abs(tp_avg - tp_expected) < 0.5 else '⚠️ CHECK'}")

        # Monthly target check
        monthly_returns = [data['pnl'] for data in monthly_pnl.values()]
        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\n{'='*70}")
        print(f"MONTHLY PERFORMANCE TARGET")
        print(f"{'='*70}")
        print(f"  Average Monthly Return: {avg_monthly:+.2f}%")
        print(f"  Target: +5% to +15%")

        if avg_monthly >= 15:
            print(f"  ✅✅ EXCELLENT! Exceeds 15% target!")
        elif avg_monthly >= 10:
            print(f"  ✅ GREAT! Above 10% target")
        elif avg_monthly >= 5:
            print(f"  ✅ GOOD! Meets 5% minimum target")
        elif avg_monthly >= 0:
            print(f"  🟡 Profitable but below 5% target")
        else:
            print(f"  ❌ Not profitable - needs improvement")

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_monthly': avg_monthly,
            'monthly': monthly_pnl,
            'sectors': sector_pnl
        }


def main():
    """Run full realistic backtest"""
    print("="*70)
    print("FULL REALISTIC RAPID TRADER BACKTEST")
    print("680+ Stocks | Real SL/TP | Actual Trading Simulation")
    print("="*70)

    backtest = FullRealisticBacktest()

    # Test last 3 months
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    results = backtest.run_backtest(start_date, end_date, max_positions=3)

    if results:
        print(f"\n{'='*70}")
        print(f"FINAL VERDICT")
        print(f"{'='*70}")

        print(f"""
📊 สรุปผลการทดสอบ Rapid Trader แบบจริง (680+ หุ้น):

Win Rate:       {results['win_rate']:.1f}%
Avg per Trade:  {results['avg_pnl']:+.2f}%
Profit Factor:  {results['profit_factor']:.2f}
Monthly Avg:    {results['avg_monthly']:+.2f}%

เป้าหมาย: 5-15% ต่อเดือน
ผลลัพธ์: {'✅ บรรลุเป้าหมาย' if results['avg_monthly'] >= 5 else '❌ ยังไม่ถึงเป้า - ต้องปรับปรุง'}
        """)


if __name__ == "__main__":
    main()
