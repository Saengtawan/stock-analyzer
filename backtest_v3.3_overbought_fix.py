#!/usr/bin/env python3
"""
Growth Catalyst v3.3 - EXTREME OVERBOUGHT FIX (แก้ปัญหาที่พบจริงๆ!)

🎯 เป้าหมาย: 10-15% กำไรต่อเดือน

🔍 สาเหตุที่พบจาก Deep Dive Analysis:

ปัญหาที่ 1: EXTREME OVERBOUGHT (มิ.ย./ก.ค. แพ้)
- มิ.ย./ก.ค. มี RSI 83-84 (extreme overbought!)
- หุ้นพีคที่ +7-9% แล้ว แต่ trailing stop กว้างเกินไป
- ออกได้แค่ +1-4% แทนที่จะได้ +7-9%

ปัญหาที่ 2: FLASH CRASH (ตุลา แพ้หนัก -26%)
- ตลาดกลับเป็น BEAR ใน 6 วัน
- Hard stop -6% ถึง -8% = ขาดทุนเยอะ

✨ v3.3 แก้ไขอย่างไร:

1. 🚨 NEW! Exit on Extreme Overbought
   - ถ้า SPY RSI > 80 AND profit > 2% → ออกทันที!
   - แก้: มิ.ย./ก.ค. จะออกได้ +7-9%

2. 🎯 Tighter Trailing Stop: -2% (จาก -3% ถึง -4%)

3. 🎯 Stricter RSI Entry: < 70 (จาก 75)

4. 🛡️ Tighter Hard Stop: -5% (จาก -6% ถึง -8%)

📊 คาดว่า:
- มิ.ย./ก.ค. เปลี่ยนจากแพ้ → ชนะ!
- กันยายน ยังชนะ
- ตุลา แพ้น้อยลง
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


class OverboughtFixFilters:
    """v3.3 - แก้ปัญหา extreme overbought!"""

    FILTERS = {
        # v3.0 stock filters (เก็บไว้)
        'beta_min': 0.8,
        'beta_max': 2.0,
        'volatility_min': 35.0,
        'rs_min': 5.0,
        'sector_score_min': 60,
        'momentum_30d_min': 8.0,
        'valuation_score_min': 20,

        # v3.3 FIX - BULL market quality filters (เข้มงวดขึ้น!)
        'regime_strength_min': 50,      # อนุญาต BULL recoveries
        'spy_5d_min': -1.5,             # อนุญาต healthy pullbacks
        'spy_20d_min': 0.0,             # Overall trend ต้องขึ้น
        'spy_rsi_max': 70.0,            # เข้มงวดขึ้น! (จาก 75 → 70)
        'spy_rsi_extreme': 80.0,        # NEW! Extreme overbought threshold
    }


class AdaptiveTPSL:
    """คำนวณ TP/SL แบบ Adaptive"""

    def calculate(self, volatility: float, rs: float, regime_strength: int, days_held: int) -> Dict:
        """คำนวณ TP/SL ที่เข้มงวดขึ้น (v3.3)"""

        # 1. HARD STOP - เข้มงวดขึ้น! (v3.3 FIX)
        if volatility < 30:
            hard_stop = -4.0  # จาก -5.0
        elif volatility < 50:
            hard_stop = -5.0  # จาก -6.0
        else:
            hard_stop = -6.0  # จาก -8.0

        # 2. TAKE PROFIT - ปรับตาม RS + Regime
        if rs > 10:
            base_target = 15.0
        elif rs > 5:
            base_target = 12.0
        else:
            base_target = 10.0

        # Adjust by regime strength
        if regime_strength >= 70:
            regime_multiplier = 1.2
        elif regime_strength >= 60:
            regime_multiplier = 1.1
        else:
            regime_multiplier = 1.0

        take_profit = base_target * regime_multiplier

        # 3. TRAILING STOP - เข้มงวดขึ้น! (v3.3 FIX)
        # จับกำไรเร็วขึ้น ไม่ให้กลับทุนมาก
        trailing_stop = -2.0  # แทนที่จะเป็น -3% ถึง -4%

        if days_held < 5:
            trailing_trigger = 5.0
        elif days_held < 15:
            trailing_trigger = 4.0
        else:
            trailing_trigger = 3.0

        return {
            'hard_stop': hard_stop,
            'take_profit': take_profit,
            'trailing_stop': trailing_stop,
            'trailing_trigger': trailing_trigger,
        }


class BacktestV33OverboughtFix:
    """Backtest v3.3 - แก้ปัญหา extreme overbought!"""

    def __init__(self, lookback_months=2):
        self.lookback_months = lookback_months
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=lookback_months * 30)

        self.entry_filters = OverboughtFixFilters.FILTERS
        self.regime_detector = MarketRegimeDetector()
        self.tpsl_calculator = AdaptiveTPSL()

        print(f"📊 Backtest Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print(f"   Strategy: v3.3 - Extreme Overbought FIX!")

    def check_bull_momentum_entry(self, symbol: str, entry_date: datetime) -> Tuple[bool, Dict]:
        """เช็คทั้งหุ้น + คุณภาพของ BULL market!"""
        try:
            # Check BULL market FIRST
            regime_info = self.regime_detector.get_current_regime(entry_date)

            if regime_info['regime'] != 'BULL':
                return False, {'reason': f"Not BULL"}

            # v3.3 OVERBOUGHT_FIX - Check BULL QUALITY (ไม่เข้มเกินไป!)
            spy_details = regime_info['details']

            # 1. Regime strength >= 50 (อนุญาต BULL recoveries)
            if regime_info['strength'] < self.entry_filters['regime_strength_min']:
                return False, {'reason': f"BULL too weak (strength: {regime_info['strength']})"}

            # 2. SPY 5-day > -1.5% (อนุญาต healthy pullbacks)
            if spy_details['ret_5d'] < self.entry_filters['spy_5d_min']:
                return False, {'reason': f"SPY 5d too weak ({spy_details['ret_5d']:.2f}%)"}

            # 3. SPY 20-day > 0% (overall trend ต้องขึ้น) - NEW!
            if spy_details['ret_20d'] < self.entry_filters['spy_20d_min']:
                return False, {'reason': f"SPY 20d negative ({spy_details['ret_20d']:.2f}%)"}

            # 4. RSI < 70 (v3.3 FIX: เข้มงวดขึ้น!)
            if spy_details['rsi'] > self.entry_filters['spy_rsi_max']:
                return False, {'reason': f"RSI too high ({spy_details['rsi']:.1f})"}

            # 5. SPY trend still good (เก็บไว้)
            if spy_details['dist_ma20'] < -2.0 or spy_details['dist_ma50'] < -3.0:
                return False, {'reason': f"SPY trend weak"}

            # Stock filters
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date - timedelta(days=90),
                                 end=entry_date + timedelta(days=1))

            if hist.empty or len(hist) < 50:
                return False, {'reason': 'Insufficient data'}

            info = ticker.info
            entry_price = hist['Close'].iloc[-1]

            # Beta
            beta = info.get('beta', 1.0) or 1.0
            if beta < self.entry_filters['beta_min'] or beta > self.entry_filters['beta_max']:
                return False, {'reason': f'Beta {beta:.2f}'}

            # Volatility - STRICT!
            returns = hist['Close'].pct_change().dropna()
            if len(returns) >= 20:
                volatility = returns.std() * (252 ** 0.5) * 100
                if volatility < self.entry_filters['volatility_min']:
                    return False, {'reason': f'Vol {volatility:.1f}% too low'}
            else:
                return False, {'reason': 'Insufficient data for volatility'}

            # Relative Strength - STRICT!
            if len(hist) >= 30:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(start=entry_date - timedelta(days=90),
                                      end=entry_date + timedelta(days=1))

                if len(spy_hist) >= 30:
                    stock_ret = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
                    spy_ret = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-30]) - 1) * 100
                    rs = stock_ret - spy_ret

                    if rs < self.entry_filters['rs_min']:
                        return False, {'reason': f'RS {rs:.1f}% too low'}
                else:
                    return False, {'reason': 'Insufficient SPY data'}
            else:
                return False, {'reason': 'Insufficient data for RS'}

            # Momentum 30d
            if len(hist) >= 30:
                momentum_30d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
                if momentum_30d < self.entry_filters['momentum_30d_min']:
                    return False, {'reason': f'Momentum {momentum_30d:.1f}% too low'}
            else:
                return False, {'reason': 'Insufficient data for momentum'}

            # Sector score (simplified)
            sector_score = min(100, max(0, int(rs * 5 + 50)))
            if sector_score < self.entry_filters['sector_score_min']:
                return False, {'reason': f'Sector {sector_score} too low'}

            # Valuation
            pe = info.get('trailingPE', 0)
            if pe and pe > 100:
                return False, {'reason': f'P/E {pe:.1f} too high'}

            # All filters passed!
            return True, {
                'beta': beta,
                'volatility': volatility,
                'rs': rs,
                'momentum_30d': momentum_30d,
                'sector_score': sector_score,
                'pe': pe,
                'entry_price': entry_price,
                'regime': regime_info['regime'],
                'regime_strength': regime_info['strength'],
                'spy_5d': spy_details['ret_5d'],
                'spy_rsi': spy_details['rsi'],
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}

    def simulate_with_adaptive(self, symbol: str, entry_date: datetime, details: Dict, max_days: int = 30) -> Dict:
        """Simulate with adaptive TP/SL + regime monitoring"""
        try:
            ticker = yf.Ticker(symbol)
            entry_price = details['entry_price']
            volatility = details['volatility']
            rs = details['rs']
            regime_strength = details['regime_strength']

            # Get data
            end_sim = min(entry_date + timedelta(days=max_days + 10), self.end_date)
            hist = ticker.history(start=entry_date, end=end_sim)

            if hist.empty or len(hist) < 2:
                return None

            # Track
            highest_price = entry_price
            peak_return = 0
            peak_day = 0
            days_held = 0
            exit_price = entry_price
            exit_reason = 'MAX_HOLD'
            exit_date = entry_date

            # Simulate
            for i, (date, row) in enumerate(hist.iterrows()):
                if i == 0:
                    continue

                current_price = row['Close']
                days_held = i

                date_naive = date.to_pydatetime().replace(tzinfo=None) if hasattr(date, 'to_pydatetime') else date
                exit_date = date_naive
                exit_price = current_price

                current_return = ((current_price - entry_price) / entry_price) * 100

                # Update peak
                if current_price > highest_price:
                    highest_price = current_price
                    peak_return = current_return
                    peak_day = i

                # Get adaptive parameters
                params = self.tpsl_calculator.calculate(volatility, rs, regime_strength, days_held)

                # Check regime (BEAR exit immediately)
                current_regime = self.regime_detector.get_current_regime(date_naive)
                if current_regime['regime'] == 'BEAR':
                    exit_reason = 'REGIME_BEAR'
                    break

                # REGIME_WEAK exit
                if current_regime['regime'] == 'SIDEWAYS' and not current_regime['should_trade']:
                    if current_return < 1.0:
                        exit_reason = 'REGIME_WEAK'
                        break

                # v3.3 NEW! - EXTREME OVERBOUGHT EXIT
                # ถ้า SPY RSI > 80 AND มีกำไร > 2% → ออกทันที!
                current_spy_rsi = current_regime['details']['rsi']
                if current_spy_rsi > self.entry_filters['spy_rsi_extreme'] and current_return > 2.0:
                    exit_reason = 'EXTREME_OVERBOUGHT'
                    break

                # Hard stop
                if current_return <= params['hard_stop']:
                    exit_reason = 'HARD_STOP'
                    break

                # Take profit
                if current_return >= params['take_profit']:
                    exit_reason = 'TARGET_HIT'
                    break

                # Trailing stop (from peak)
                if peak_return >= params['trailing_trigger']:
                    drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100
                    if drawdown_from_peak <= params['trailing_stop']:
                        exit_reason = 'TRAILING_PEAK'
                        break

                # Max hold
                if i >= max_days:
                    exit_reason = 'TIME_STOP'
                    break

            final_return = ((exit_price - entry_price) / entry_price) * 100

            return {
                'symbol': symbol,
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_date': exit_date.strftime('%Y-%m-%d') if hasattr(exit_date, 'strftime') else str(exit_date),
                'exit_price': exit_price,
                'days_held': days_held,
                'return': final_return,
                'peak_return': peak_return,
                'peak_day': peak_day,
                'exit_reason': exit_reason,
                'win': final_return >= 5.0,
            }

        except Exception as e:
            print(f"⚠️  Error simulating {symbol}: {e}")
            return None

    def run_backtest(self):
        """Run backtest with BULL momentum filters"""

        print("\n" + "="*100)
        print("🧪 BACKTEST v3.3 - EXTREME OVERBOUGHT FIX")
        print("="*100)

        print("\n📋 Configuration:")
        print(f"   Stock Filters (v3.0):")
        print(f"      - Beta: {self.entry_filters['beta_min']:.1f} - {self.entry_filters['beta_max']:.1f}")
        print(f"      - Volatility: > {self.entry_filters['volatility_min']:.0f}%")
        print(f"      - RS: > {self.entry_filters['rs_min']:.0f}%")
        print(f"      - Momentum 30d: > {self.entry_filters['momentum_30d_min']:.0f}%")
        print(f"      - Sector: > {self.entry_filters['sector_score_min']}")

        print(f"\n   v3.3 FIX - BULL Market Quality:")
        print(f"      - Regime Strength: >= {self.entry_filters['regime_strength_min']}")
        print(f"      - SPY 5d: > {self.entry_filters['spy_5d_min']:.1f}%")
        print(f"      - SPY 20d: > {self.entry_filters['spy_20d_min']:.0f}%")
        print(f"      - SPY RSI Entry: < {self.entry_filters['spy_rsi_max']:.0f} (เข้มงวดขึ้น! จาก 75→70)")
        print(f"      - SPY RSI Extreme Exit: > {self.entry_filters['spy_rsi_extreme']:.0f} (NEW! ออกทันที)")

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
            # Check regime first
            regime = self.regime_detector.get_current_regime(entry_date)

            print(f"\n📅 Entry Date: {entry_date.strftime('%Y-%m-%d')}")
            print(f"   Regime: {regime['regime']} (Strength: {regime['strength']})")
            print(f"   SPY 5d: {regime['details']['ret_5d']:+.2f}%, RSI: {regime['details']['rsi']:.1f}")

            if regime['regime'] != 'BULL':
                print(f"   ❌ BLOCKED: Not BULL market")
                continue

            if regime['strength'] < self.entry_filters['regime_strength_min']:
                print(f"   ❌ BLOCKED: BULL too weak (strength: {regime['strength']} < {self.entry_filters['regime_strength_min']})")
                continue

            if regime['details']['ret_5d'] < self.entry_filters['spy_5d_min']:
                print(f"   ❌ BLOCKED: SPY 5d negative ({regime['details']['ret_5d']:.2f}%)")
                continue

            if regime['details']['rsi'] > self.entry_filters['spy_rsi_max']:
                print(f"   ❌ BLOCKED: RSI overbought ({regime['details']['rsi']:.1f})")
                continue

            print(f"   ✅ BULL QUALITY PASSED!")

            passed_count = 0
            for symbol in TEST_STOCKS:
                # Check entry filters
                passes, details = self.check_bull_momentum_entry(symbol, entry_date)

                if passes:
                    passed_count += 1
                    # Simulate
                    result = self.simulate_with_adaptive(
                        symbol,
                        entry_date,
                        details
                    )

                    if result:
                        result['entry_details'] = details
                        all_trades.append(result)

                        status = "✅ WIN" if result['win'] else "❌ LOSS"
                        print(f"  {symbol:6s}: {status} {result['return']:+6.2f}% ({result['days_held']}d) "
                              f"[Peak: {result['peak_return']:+.2f}% d{result['peak_day']}] - {result['exit_reason']}")

            print(f"   Total passed filters: {passed_count}/{len(TEST_STOCKS)} ({passed_count/len(TEST_STOCKS)*100:.1f}%)")

        # Analyze results
        return self.analyze_results(all_trades)

    def analyze_results(self, trades: List[Dict]) -> Dict:
        """Analyze results"""

        if not trades:
            print("\n❌ No trades found!")
            return {}

        print("\n" + "="*100)
        print("📊 BACKTEST RESULTS - v3.3 EXTREME OVERBOUGHT FIX")
        print("="*100)

        # Calculate metrics
        total_trades = len(trades)
        winners = [t for t in trades if t['win']]
        losers = [t for t in trades if not t['win']]

        win_rate = len(winners) / total_trades * 100

        returns = [t['return'] for t in trades]
        avg_return = np.mean(returns)

        avg_days = np.mean([t['days_held'] for t in trades])
        trades_per_month = 30 / avg_days if avg_days > 0 else 0
        monthly_return = avg_return * trades_per_month

        # Print summary
        print(f"\n🎯 Overall Performance:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"   Losers: {len(losers)} ({100-win_rate:.1f}%)")
        print(f"")
        print(f"   Average Return: {avg_return:+.2f}%")
        print(f"   Average Days Held: {avg_days:.1f} days")
        print(f"   Trades per Month: {trades_per_month:.1f}")
        print(f"   📈 MONTHLY RETURN ESTIMATE: {monthly_return:+.2f}%")

        # Exit reasons
        print(f"\n🚪 Exit Reasons:")
        exit_reasons = {}
        for t in trades:
            reason = t['exit_reason']
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
            pct = count / total_trades * 100
            print(f"   {reason}: {count} ({pct:.1f}%)")

        # Stock quality
        print(f"\n📊 Stock Quality (at entry):")
        avg_rs = np.mean([t['entry_details']['rs'] for t in trades])
        avg_vol = np.mean([t['entry_details']['volatility'] for t in trades])
        avg_momentum = np.mean([t['entry_details']['momentum_30d'] for t in trades])
        avg_regime_str = np.mean([t['entry_details']['regime_strength'] for t in trades])
        avg_spy_5d = np.mean([t['entry_details']['spy_5d'] for t in trades])
        avg_spy_rsi = np.mean([t['entry_details']['spy_rsi'] for t in trades])

        print(f"   Average RS: {avg_rs:+.1f}%")
        print(f"   Average Volatility: {avg_vol:.1f}%")
        print(f"   Average Momentum 30d: {avg_momentum:+.1f}%")
        print(f"   Average Regime Strength: {avg_regime_str:.0f}")
        print(f"   Average SPY 5d: {avg_spy_5d:+.2f}%")
        print(f"   Average SPY RSI: {avg_spy_rsi:.1f}")

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
            month_winners = [t for t in month_trades if t['win']]
            month_win_rate = len(month_winners) / len(month_trades) * 100
            month_avg = np.mean([t['return'] for t in month_trades])
            month_total = sum([t['return'] for t in month_trades])

            print(f"\n{month}:")
            print(f"   Trades: {len(month_trades)}")
            print(f"   Win Rate: {month_win_rate:.1f}%")
            print(f"   Avg Return: {month_avg:+.2f}%")
            print(f"   Total Return: {month_total:+.2f}%")

        # Top/Bottom performers
        print(f"\n🏆 Top 5 Winners:")
        sorted_trades = sorted(trades, key=lambda x: x['return'], reverse=True)
        for i, t in enumerate(sorted_trades[:5], 1):
            print(f"   {i}. {t['symbol']:6s}: {t['return']:+6.2f}% ({t['days_held']}d) - {t['entry_date']}")

        print(f"\n💔 Top 5 Losers:")
        for i, t in enumerate(sorted_trades[-5:], 1):
            print(f"   {i}. {t['symbol']:6s}: {t['return']:+6.2f}% ({t['days_held']}d) - {t['entry_date']}")

        print("\n" + "="*100)
        print("✅ BACKTEST COMPLETE")
        print("="*100)

        print(f"\n🎯 Key Metrics:")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Avg Return: {avg_return:+.2f}%")
        print(f"   📈 MONTHLY RETURN: {monthly_return:+.2f}%")

        if monthly_return >= 10.0:
            print(f"\n💡 Result:")
            print(f"   ✅ EXCELLENT! Monthly return {monthly_return:+.1f}% meets 10-15% target!")
        elif monthly_return >= 5.0:
            print(f"\n💡 Result:")
            print(f"   ✅ GOOD! Monthly return {monthly_return:+.1f}% is positive")
        elif monthly_return >= 0:
            print(f"\n💡 Result:")
            print(f"   ⚠️ BREAK-EVEN. Monthly return {monthly_return:+.1f}% needs improvement")
        else:
            print(f"\n💡 Result:")
            print(f"   ❌ LOSING. Monthly return {monthly_return:+.1f}% - still has issues")

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'monthly_return': monthly_return,
            'all_trades': trades
        }


def main():
    print("🚀 Starting v3.3 EXTREME OVERBOUGHT FIX Backtest...")
    print("   แก้ปัญหาที่พบจาก Deep Dive Analysis:")
    print("   1. Exit when SPY RSI > 80 (extreme overbought)")
    print("   2. Tighter trailing stop (-2%)")
    print("   3. Stricter RSI entry (< 70)")
    print("   4. Tighter hard stop (-5%)")
    print("   This will take 5-10 minutes...\n")

    backtest = BacktestV33OverboughtFix(lookback_months=6)
    results = backtest.run_backtest()


if __name__ == "__main__":
    main()
