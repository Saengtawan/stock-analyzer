#!/usr/bin/env python3
"""
Backtest v2.3 - ADAPTIVE TP/SL (ฉลาด! ปรับตามหุ้นแต่ละตัว)

Revolutionary Adaptive Exit System:
1. TP/SL ปรับตาม Volatility (vol สูง = stop กว้างกว่า)
2. TP/SL ปรับตาม Relative Strength (RS สูง = target สูงกว่า)
3. TP/SL ปรับตาม Market Regime (BULL แรง = target สูงกว่า)
4. Trailing Stop ปรับตาม Days Held (ถือนาน = เข้มงวดขึ้น)

Goal: TP/SL ที่เหมาะกับ context ของแต่ละหุ้น!
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

from market_regime_detector import MarketRegimeDetector

# Test stocks
TEST_STOCKS = [
    # v7.1 Winners
    'GOOGL', 'META', 'DASH', 'TEAM', 'ROKU', 'TSM', 'LRCX',

    # Mega caps
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA',

    # High growth
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG',

    # Semiconductors
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC',

    # Consumer tech
    'UBER', 'ABNB', 'COIN', 'SHOP', 'SQ',
]


class AdaptiveTPSLCalculator:
    """คำนวณ TP/SL ที่เหมาะกับแต่ละหุ้น"""

    def calculate_adaptive_stops(self,
                                 volatility: float,
                                 rs: float,
                                 regime: str,
                                 regime_strength: int,
                                 days_held: int) -> Dict:
        """
        คำนวณ TP/SL แบบ Adaptive

        Returns: {
            'hard_stop': float,
            'take_profit': float,
            'trailing_stop': float,
            'trailing_trigger': float
        }
        """

        # 1. HARD STOP - ปรับตาม Volatility
        if volatility < 30:
            # Vol ต่ำ = ราคาไม่ค่อยผันผวน → ใช้ stop แคบ
            hard_stop = -4.0
        elif volatility < 50:
            # Vol ปานกลาง → ใช้ stop ปกติ
            hard_stop = -6.0
        else:
            # Vol สูง = ราคาผันผวนมาก → ใช้ stop กว้าง (ไม่งั้นโดนหลุดง่าย)
            hard_stop = -8.0

        # 2. TAKE PROFIT - ปรับตาม RS + Regime + Volatility

        # Base target from RS
        if rs > 10:
            base_target = 15.0  # RS สูงมาก → เป้าสูง
        elif rs > 5:
            base_target = 12.0  # RS สูง → เป้าปานกลาง
        elif rs > 2:
            base_target = 10.0  # RS พอใช้ → เป้าปกติ
        else:
            base_target = 7.0   # RS ต่ำ → เป้าต่ำ

        # Adjust by regime strength
        if regime == 'BULL':
            if regime_strength >= 70:
                regime_multiplier = 1.2  # BULL แรงมาก → เพิ่ม 20%
            elif regime_strength >= 50:
                regime_multiplier = 1.0  # BULL ปกติ
            else:
                regime_multiplier = 0.9  # BULL อ่อน → ลด 10%
        else:
            regime_multiplier = 0.8  # SIDEWAYS → เป้าต่ำ

        # Adjust by volatility (high vol = higher targets possible)
        if volatility > 50:
            vol_multiplier = 1.1  # Vol สูง → เพิ่มเป้า 10%
        else:
            vol_multiplier = 1.0

        take_profit = base_target * regime_multiplier * vol_multiplier
        take_profit = min(20.0, take_profit)  # Cap ที่ 20%

        # 3. TRAILING STOP - ปรับตาม Days Held
        if days_held < 5:
            # ถือได้ไม่นาน → ใจเย็น ให้เวลามันขึ้น
            trailing_stop = -4.0
            trailing_trigger = 6.0  # เริ่มติดตามที่ +6%
        elif days_held < 15:
            # ถือปานกลาง → เริ่มเข้มงวด
            trailing_stop = -3.0
            trailing_trigger = 5.0  # เริ่มติดตามที่ +5%
        else:
            # ถือนานแล้ว → เข้มงวดมาก! ออกเร็วถ้ายังไม่ถึงเป้า
            trailing_stop = -2.0
            trailing_trigger = 4.0  # เริ่มติดตามที่ +4%

        return {
            'hard_stop': hard_stop,
            'take_profit': take_profit,
            'trailing_stop': trailing_stop,
            'trailing_trigger': trailing_trigger,
        }


class BacktestV23Adaptive:
    """Backtest with Adaptive TP/SL - ฉลาดปรับตามแต่ละหุ้น!"""

    def __init__(self, lookback_months=2):
        self.lookback_months = lookback_months
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=lookback_months * 30)

        # v7.1 Entry Filters
        self.entry_filters = {
            'beta_min': 0.8,
            'beta_max': 2.0,
            'volatility_min': 25.0,
            'rs_min': 0.0,
            'sector_score_min': 40,
            'valuation_score_min': 20,
        }

        # Adaptive calculator
        self.adaptive_calc = AdaptiveTPSLCalculator()

        # Regime detector
        self.regime_detector = MarketRegimeDetector()

        print(f"📊 Backtest Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print(f"   Strategy: v2.3 ADAPTIVE TP/SL")
        print(f"   TP/SL adjusts for each stock's context!")

    def check_entry_filters(self, symbol: str, entry_date: datetime) -> Tuple[bool, Dict]:
        """Check v7.1 filters + BULL regime"""
        try:
            # Check regime - must be BULL
            regime_info = self.regime_detector.get_current_regime(entry_date)

            if regime_info['regime'] != 'BULL':
                return False, {'reason': f"Not BULL (regime: {regime_info['regime']})"}

            # Check SPY trend
            spy_details = regime_info['details']
            if spy_details['dist_ma20'] < -3.0 or spy_details['dist_ma50'] < -5.0:
                return False, {'reason': f"SPY trend weak"}

            ticker = yf.Ticker(symbol)

            # Get historical data
            hist = ticker.history(start=entry_date - timedelta(days=90),
                                 end=entry_date + timedelta(days=1))

            if hist.empty or len(hist) < 50:
                return False, {'reason': 'Insufficient data'}

            info = ticker.info
            entry_price = hist['Close'].iloc[-1]

            # Filter 1: Beta
            beta = info.get('beta', 1.0)
            if beta is None:
                beta = 1.0
            if beta < self.entry_filters['beta_min'] or beta > self.entry_filters['beta_max']:
                return False, {'reason': f'Beta {beta:.2f} outside range'}

            # Filter 2: Volatility
            returns = hist['Close'].pct_change().dropna()
            if len(returns) >= 20:
                volatility = returns.std() * (252 ** 0.5) * 100
                if volatility < self.entry_filters['volatility_min']:
                    return False, {'reason': f'Volatility {volatility:.1f}% too low'}
            else:
                return False, {'reason': 'Insufficient data for volatility'}

            # Filter 3: Relative Strength
            if len(hist) >= 30:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(start=entry_date - timedelta(days=90),
                                      end=entry_date + timedelta(days=1))

                if len(spy_hist) >= 30:
                    stock_ret = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
                    spy_ret = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-30]) - 1) * 100
                    rs = stock_ret - spy_ret

                    if rs < self.entry_filters['rs_min']:
                        return False, {'reason': f'RS {rs:.1f}% below threshold'}
                else:
                    return False, {'reason': 'Insufficient SPY data'}
            else:
                return False, {'reason': 'Insufficient data for RS'}

            # Filter 4: Valuation
            pe = info.get('trailingPE', 0)
            if pe > 100:
                return False, {'reason': f'P/E {pe:.1f} too high'}

            # All passed
            return True, {
                'beta': beta,
                'volatility': volatility,
                'rs': rs,
                'pe': pe,
                'entry_price': entry_price,
                'regime': regime_info['regime'],
                'regime_strength': regime_info['strength'],
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}

    def simulate_adaptive_exit(self, symbol: str, entry_date: datetime,
                              entry_details: Dict, max_days: int = 30) -> Dict:
        """
        Simulate with ADAPTIVE TP/SL - ปรับทุกวันตาม context!
        """
        try:
            ticker = yf.Ticker(symbol)
            entry_price = entry_details['entry_price']
            volatility = entry_details['volatility']
            rs = entry_details['rs']
            regime = entry_details['regime']
            regime_strength = entry_details['regime_strength']

            # Get price data
            end_sim = min(entry_date + timedelta(days=max_days + 10), self.end_date)
            hist = ticker.history(start=entry_date, end=end_sim)

            if hist.empty or len(hist) < 2:
                return None

            # Track
            highest_price = entry_price
            peak_return = 0
            days_held = 0
            exit_price = entry_price
            exit_reason = 'MAX_HOLD'
            exit_date = entry_date

            # Track adaptive parameters used
            adaptive_params_used = []

            # Simulate day by day
            for i, (date, row) in enumerate(hist.iterrows()):
                if i == 0:
                    continue  # Skip entry day

                current_price = row['Close']
                days_held = i

                # Convert date
                date_naive = date.to_pydatetime().replace(tzinfo=None) if hasattr(date, 'to_pydatetime') else date
                exit_date = date_naive
                exit_price = current_price

                # Calculate returns
                current_return = ((current_price - entry_price) / entry_price) * 100

                # Update peak
                if current_price > highest_price:
                    highest_price = current_price
                    peak_return = current_return

                drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100

                # 🎯 CALCULATE ADAPTIVE TP/SL FOR THIS DAY
                adaptive_params = self.adaptive_calc.calculate_adaptive_stops(
                    volatility=volatility,
                    rs=rs,
                    regime=regime,
                    regime_strength=regime_strength,
                    days_held=days_held
                )

                # Store for analysis
                if i == 1:  # Store first day params
                    adaptive_params_used = adaptive_params.copy()

                # Exit checks with ADAPTIVE values

                # 1. ADAPTIVE HARD STOP
                if current_return <= adaptive_params['hard_stop']:
                    exit_reason = f"HARD_STOP_{adaptive_params['hard_stop']:.0f}%"
                    break

                # 2. ADAPTIVE TAKE PROFIT
                if current_return >= adaptive_params['take_profit']:
                    exit_reason = f"TAKE_PROFIT_{adaptive_params['take_profit']:.0f}%"
                    break

                # 3. ADAPTIVE TRAILING STOP
                if peak_return >= adaptive_params['trailing_trigger']:
                    if drawdown_from_peak <= adaptive_params['trailing_stop']:
                        exit_reason = f"TRAILING_{adaptive_params['trailing_stop']:.0f}%"
                        break

                # 4. REGIME EXIT
                regime_info = self.regime_detector.get_current_regime(date_naive)
                if regime_info['regime'] == 'BEAR':
                    exit_reason = 'REGIME_BEAR'
                    break

                # 5. MAX HOLD (30 days)
                if i >= max_days or date_naive >= self.end_date:
                    exit_reason = 'MAX_HOLD'
                    break

            # Calculate final return
            final_return = ((exit_price - entry_price) / entry_price) * 100

            return {
                'symbol': symbol,
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_date': exit_date.strftime('%Y-%m-%d') if hasattr(exit_date, 'strftime') else str(exit_date),
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'days_held': days_held,
                'return_pct': final_return,
                'peak_return': peak_return,
                'highest_price': highest_price,
                'winner': final_return >= 0,
                # Adaptive params used
                'adaptive_hard_stop': adaptive_params_used.get('hard_stop', 0),
                'adaptive_take_profit': adaptive_params_used.get('take_profit', 0),
                'adaptive_trailing': adaptive_params_used.get('trailing_stop', 0),
                'volatility': volatility,
                'rs': rs,
            }

        except Exception as e:
            print(f"⚠️  Error simulating {symbol}: {e}")
            return None

    def run_backtest(self):
        """Run backtest with adaptive TP/SL"""

        print("\n" + "="*100)
        print("🧪 BACKTEST v2.3 - ADAPTIVE TP/SL (ฉลาด! ปรับตามแต่ละหุ้น)")
        print("="*100)

        print("\n📋 Entry Filters (v7.1):")
        print(f"   - Beta: {self.entry_filters['beta_min']:.1f} - {self.entry_filters['beta_max']:.1f}")
        print(f"   - Volatility: > {self.entry_filters['volatility_min']:.0f}%")
        print(f"   - RS (30d): > {self.entry_filters['rs_min']:.0f}%")
        print(f"   - Regime: BULL only")

        print(f"\n📋 Exit Rules (v2.3 ADAPTIVE):")
        print(f"   ✨ ADAPTIVE based on:")
        print(f"      - Volatility (vol สูง = stop กว้างกว่า)")
        print(f"      - Relative Strength (RS สูง = target สูงกว่า)")
        print(f"      - Market Regime (BULL แรง = target สูงกว่า)")
        print(f"      - Days Held (ถือนาน = trailing เข้มงวดขึ้น)")

        # Test entry points
        entry_dates = []
        current = self.start_date
        while current < self.end_date - timedelta(days=30):
            entry_dates.append(current)
            current += timedelta(days=7)

        all_trades = []

        print(f"\n🔍 Testing {len(TEST_STOCKS)} stocks at {len(entry_dates)} entry points...")

        # Test each entry date
        for entry_date in entry_dates:
            # Check regime
            regime = self.regime_detector.get_current_regime(entry_date)

            if regime['regime'] != 'BULL':
                print(f"\n📅 {entry_date.strftime('%Y-%m-%d')} - SKIPPED ({regime['regime']})")
                continue

            print(f"\n📅 {entry_date.strftime('%Y-%m-%d')} - BULL ✅")

            for symbol in TEST_STOCKS:
                passes, details = self.check_entry_filters(symbol, entry_date)

                if passes:
                    result = self.simulate_adaptive_exit(symbol, entry_date, details)

                    if result:
                        all_trades.append(result)

                        status = "✅ WIN" if result['winner'] else "❌ LOSS"
                        print(f"  {symbol:6s}: {status} {result['return_pct']:+6.2f}% "
                              f"({result['days_held']:2d}d) - {result['exit_reason']} "
                              f"[TP:{result['adaptive_take_profit']:.0f}% SL:{result['adaptive_hard_stop']:.0f}%]")

        # Analyze results
        return self.analyze_results(all_trades)

    def analyze_results(self, trades: List[Dict]) -> Dict:
        """Analyze results"""

        if not trades:
            print("\n❌ No trades found!")
            return {}

        print("\n" + "="*100)
        print("📊 BACKTEST RESULTS - v2.3 ADAPTIVE TP/SL")
        print("="*100)

        # Calculate metrics
        total_trades = len(trades)
        winners = [t for t in trades if t['winner']]
        losers = [t for t in trades if not t['winner']]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0

        returns = [t['return_pct'] for t in trades]
        avg_return = np.mean(returns)
        avg_winner = np.mean([t['return_pct'] for t in winners]) if winners else 0
        avg_loser = np.mean([t['return_pct'] for t in losers]) if losers else 0

        days_held = [t['days_held'] for t in trades]
        avg_days = np.mean(days_held)

        # Adaptive params analysis
        avg_hard_stop = np.mean([abs(t['adaptive_hard_stop']) for t in trades])
        avg_take_profit = np.mean([t['adaptive_take_profit'] for t in trades])
        avg_volatility = np.mean([t['volatility'] for t in trades])
        avg_rs = np.mean([t['rs'] for t in trades])

        # Exit reasons
        exit_reasons = {}
        for t in trades:
            reason = t['exit_reason']
            # Simplify exit reason for grouping
            if 'HARD_STOP' in reason:
                reason = 'HARD_STOP'
            elif 'TAKE_PROFIT' in reason:
                reason = 'TAKE_PROFIT'
            elif 'TRAILING' in reason:
                reason = 'TRAILING_STOP'
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        # Monthly returns
        total_return = sum(returns)

        # Print summary
        print(f"\n🎯 Overall Performance:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"   Losers: {len(losers)} ({100-win_rate:.1f}%)")
        print(f"   ")
        print(f"   Average Return: {avg_return:+.2f}%")
        print(f"   Average Winner: {avg_winner:+.2f}%")
        print(f"   Average Loser: {avg_loser:+.2f}%")
        print(f"   ")
        print(f"   Average Days Held: {avg_days:.1f} days")
        print(f"   Total Return (sum): {total_return:+.2f}%")

        print(f"\n✨ Adaptive Parameters Used:")
        print(f"   Avg Hard Stop: -{avg_hard_stop:.1f}%")
        print(f"   Avg Take Profit: +{avg_take_profit:.1f}%")
        print(f"   Avg Volatility: {avg_volatility:.1f}%")
        print(f"   Avg RS: {avg_rs:+.1f}%")

        # Exit reasons
        print(f"\n📊 Exit Reasons:")
        for reason in sorted(exit_reasons.keys(), key=lambda x: exit_reasons[x], reverse=True):
            count = exit_reasons[reason]
            pct = count / total_trades * 100
            print(f"   {reason:15s}: {count:3d} ({pct:5.1f}%)")

        # Top/Worst performers
        print(f"\n🏆 Top 10 Winners:")
        sorted_trades = sorted(trades, key=lambda x: x['return_pct'], reverse=True)
        for i, t in enumerate(sorted_trades[:10], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+6.2f}% ({t['days_held']:2d}d) "
                  f"- {t['exit_reason']} - TP:{t['adaptive_take_profit']:.0f}% SL:{t['adaptive_hard_stop']:.0f}%")

        print(f"\n💔 Worst 10 Losers:")
        for i, t in enumerate(sorted_trades[-10:], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+6.2f}% ({t['days_held']:2d}d) "
                  f"- {t['exit_reason']} - TP:{t['adaptive_take_profit']:.0f}% SL:{t['adaptive_hard_stop']:.0f}%")

        # Monthly breakdown
        print(f"\n📅 MONTHLY BREAKDOWN:")
        monthly_stats = {}
        for t in trades:
            month = t['entry_date'][:7]
            if month not in monthly_stats:
                monthly_stats[month] = []
            monthly_stats[month].append(t)

        for month in sorted(monthly_stats.keys()):
            month_trades = monthly_stats[month]
            month_winners = sum(1 for t in month_trades if t['winner'])
            month_win_rate = month_winners / len(month_trades) * 100
            month_avg_return = np.mean([t['return_pct'] for t in month_trades])
            month_total_return = sum([t['return_pct'] for t in month_trades])
            month_avg_days = np.mean([t['days_held'] for t in month_trades])

            print(f"\n{month}:")
            print(f"   Trades: {len(month_trades)}")
            print(f"   Win Rate: {month_win_rate:.1f}%")
            print(f"   Avg Return: {month_avg_return:+.2f}%")
            print(f"   Total Return: {month_total_return:+.2f}%")
            print(f"   Avg Days Held: {month_avg_days:.1f} days")

        print("\n" + "="*100)
        print("✅ BACKTEST COMPLETE")
        print("="*100)

        print(f"\n🎯 Key Takeaways:")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Avg Return per Trade: {avg_return:+.2f}%")
        print(f"   Avg Days Held: {avg_days:.1f} days")

        # Calculate potential monthly return with reinvestment
        trades_per_month = 30 / avg_days if avg_days > 0 else 0
        monthly_return_estimate = avg_return * trades_per_month

        print(f"\n💰 Monthly Return Estimate (with reinvestment):")
        print(f"   Avg holding: {avg_days:.1f} days")
        print(f"   Potential trades/month: {trades_per_month:.1f}")
        print(f"   Estimated monthly return: {monthly_return_estimate:+.2f}%")

        if monthly_return_estimate >= 10.0:
            print(f"\n💡 Interpretation:")
            print(f"   ✅ EXCELLENT! Estimated {monthly_return_estimate:.1f}%/month >= 10% target!")
        elif monthly_return_estimate >= 5.0:
            print(f"\n💡 Interpretation:")
            print(f"   ✅ GOOD! Estimated {monthly_return_estimate:.1f}%/month")
        else:
            print(f"\n💡 Interpretation:")
            print(f"   ⚠️ BELOW TARGET. Estimated {monthly_return_estimate:.1f}%/month")

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'avg_days': avg_days,
            'monthly_return_estimate': monthly_return_estimate,
            'all_trades': trades
        }


def main():
    print("🚀 Starting v2.3 ADAPTIVE TP/SL Backtest...")
    print("   TP/SL ปรับตาม context ของแต่ละหุ้น!")
    print("   This will take 2-3 minutes...\n")

    backtest = BacktestV23Adaptive(lookback_months=2)
    results = backtest.run_backtest()


if __name__ == "__main__":
    main()
