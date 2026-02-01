#!/usr/bin/env python3
"""
Growth Catalyst v3.0 - COMPLETE SYSTEM (รวมทุกอย่างที่ดีที่สุด!)

🎯 เป้าหมาย: 10-15% กำไรต่อเดือน

รวมทุกอย่างที่ดีที่สุด:
1. ✅ STRICT Entry Filters - เลือกแต่หุ้นที่ดีที่สุด
   - RS > +5% (แข็งแรงกว่าตลาดเยอะ)
   - Vol > 35% (มี momentum แรง)
   - Sector > 60 (sector แข็งแรงมาก)
   - Momentum 30d > +8% (กำลังขึ้นอยู่แล้ว)
   - BULL market only (ไม่เข้าตอน BEAR)

2. ✅ Adaptive TP/SL - ปรับตาม context ของแต่ละหุ้น
   - TP ปรับตาม RS, regime, volatility
   - SL ปรับตาม volatility
   - Trailing ปรับตาม days held

3. ✅ Smart Peak Detection - จับจุดสูงสุดให้ได้
   - Trailing stop เข้มงวดขึ้นเมื่อถือนาน
   - ออกที่จุดสูงสุด ไม่รอถึงวันที่ 30

4. ✅ Proper Monthly Calculation - คำนวณกำไรต่อเดือนจริง
   - ถือเฉลี่ย X วัน = ทำได้ 30/X trades ต่อเดือน
   - กำไรต่อเดือน = กำไรต่อ trade × trades ต่อเดือน
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


class StrictEntryFilters:
    """กรองหุ้นอย่างเข้มงวด - เลือกแต่ที่ดีที่สุด!"""

    FILTERS = {
        'beta_min': 0.8,
        'beta_max': 2.0,
        'volatility_min': 35.0,      # เพิ่มจาก 25% → 35% (มี momentum แรง!)
        'rs_min': 5.0,               # เพิ่มจาก 0% → +5% (แข็งแรงกว่าตลาดเยอะ!)
        'sector_score_min': 60,      # เพิ่มจาก 40 → 60 (sector แข็งแรงมาก!)
        'momentum_30d_min': 8.0,     # ใหม่! กำลังขึ้น +8% ใน 30 วัน
        'valuation_score_min': 20,
    }


class AdaptiveTPSL:
    """คำนวณ TP/SL แบบ Adaptive"""

    def calculate(self, volatility: float, rs: float, regime_strength: int, days_held: int) -> Dict:
        """คำนวณ TP/SL ที่เหมาะกับหุ้น"""

        # 1. Hard Stop - ปรับตาม Volatility
        if volatility < 40:
            hard_stop = -5.0
        elif volatility < 60:
            hard_stop = -6.0
        else:
            hard_stop = -8.0

        # 2. Take Profit - ปรับตาม RS
        if rs > 15:
            base_target = 18.0
        elif rs > 10:
            base_target = 15.0
        elif rs > 7:
            base_target = 12.0
        else:
            base_target = 10.0

        # Adjust by regime
        if regime_strength >= 70:
            regime_mult = 1.2
        elif regime_strength >= 50:
            regime_mult = 1.0
        else:
            regime_mult = 0.9

        take_profit = min(25.0, base_target * regime_mult)

        # 3. Trailing Stop - เข้มงวดขึ้นเมื่อถือนาน (จับ peak!)
        if days_held < 7:
            trailing_stop = -4.0
            trailing_trigger = 6.0
        elif days_held < 14:
            trailing_stop = -3.0
            trailing_trigger = 5.0
        else:
            # ถือนานแล้ว → เข้มงวดมาก! ออกที่ peak
            trailing_stop = -2.0
            trailing_trigger = 4.0

        return {
            'hard_stop': hard_stop,
            'take_profit': take_profit,
            'trailing_stop': trailing_stop,
            'trailing_trigger': trailing_trigger,
        }


class BacktestV30Complete:
    """v3.0 - Complete System รวมทุกอย่างที่ดีที่สุด!"""

    def __init__(self, lookback_months=2):
        self.lookback_months = lookback_months
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=lookback_months * 30)

        self.entry_filters = StrictEntryFilters.FILTERS
        self.adaptive_tpsl = AdaptiveTPSL()
        self.regime_detector = MarketRegimeDetector()

        print(f"📊 Backtest Period: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        print(f"   Strategy: v3.0 COMPLETE - เลือกแต่หุ้นที่ดีที่สุด + ออกที่จุดสูงสุด!")

    def check_strict_entry(self, symbol: str, entry_date: datetime) -> Tuple[bool, Dict]:
        """กรองหุ้นอย่างเข้มงวด!"""
        try:
            # Must be BULL market
            regime_info = self.regime_detector.get_current_regime(entry_date)

            if regime_info['regime'] != 'BULL':
                return False, {'reason': f"Not BULL"}

            # SPY must be strong
            spy_details = regime_info['details']
            if spy_details['dist_ma20'] < -2.0 or spy_details['dist_ma50'] < -3.0:
                return False, {'reason': f"SPY weak"}

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
                return False, {'reason': 'Insufficient data'}

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

                    # Momentum 30d - NEW!
                    momentum_30d = stock_ret
                    if momentum_30d < self.entry_filters['momentum_30d_min']:
                        return False, {'reason': f'Momentum {momentum_30d:.1f}% too low'}
                else:
                    return False, {'reason': 'No SPY data'}
            else:
                return False, {'reason': 'Insufficient data'}

            # Sector Score - STRICT! (simplified - use RS as proxy)
            sector_score = max(0, min(100, rs * 5 + 50))
            if sector_score < self.entry_filters['sector_score_min']:
                return False, {'reason': f'Sector {sector_score:.0f} too low'}

            # Valuation
            pe = info.get('trailingPE', 0)
            if pe > 100:
                return False, {'reason': f'P/E {pe:.0f} too high'}

            # ALL FILTERS PASSED!
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
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}

    def simulate_complete(self, symbol: str, entry_date: datetime, details: Dict, max_days: int = 30) -> Dict:
        """Simulate with complete v3.0 system"""
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

                drawdown_from_peak = ((current_price - highest_price) / highest_price) * 100

                # Calculate adaptive params for TODAY
                params = self.adaptive_tpsl.calculate(volatility, rs, regime_strength, days_held)

                # Exit checks

                # 1. Hard Stop
                if current_return <= params['hard_stop']:
                    exit_reason = f"HARD_STOP"
                    break

                # 2. Take Profit
                if current_return >= params['take_profit']:
                    exit_reason = f"TAKE_PROFIT_{params['take_profit']:.0f}%"
                    break

                # 3. Trailing Stop (จับ peak!)
                if peak_return >= params['trailing_trigger']:
                    if drawdown_from_peak <= params['trailing_stop']:
                        exit_reason = f"TRAILING_PEAK"
                        break

                # 4. Regime Exit
                regime_info = self.regime_detector.get_current_regime(date_naive)
                if regime_info['regime'] == 'BEAR':
                    exit_reason = 'REGIME_BEAR'
                    break

                # 5. Max Hold
                if i >= max_days or date_naive >= self.end_date:
                    exit_reason = 'MAX_HOLD_30D'
                    break

            final_return = ((exit_price - entry_price) / entry_price) * 100

            return {
                'symbol': symbol,
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'exit_date': exit_date.strftime('%Y-%m-%d') if hasattr(exit_date, 'strftime') else str(exit_date),
                'entry_price': entry_price,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'days_held': days_held,
                'return_pct': final_return,
                'peak_return': peak_return,
                'peak_day': peak_day,
                'winner': final_return >= 0,
                'volatility': volatility,
                'rs': rs,
                'momentum_30d': details['momentum_30d'],
            }

        except Exception as e:
            print(f"⚠️  {symbol}: {e}")
            return None

    def run_backtest(self):
        """Run complete backtest"""

        print("\n" + "="*100)
        print("🧪 BACKTEST v3.0 - COMPLETE SYSTEM")
        print("   รวมทุกอย่างที่ดีที่สุด!")
        print("="*100)

        print("\n📋 STRICT Entry Filters:")
        print(f"   ✅ Regime: BULL only (SPY > MA20/MA50)")
        print(f"   ✅ RS: > +{self.entry_filters['rs_min']:.0f}% (แข็งแรงกว่าตลาดเยอะ!)")
        print(f"   ✅ Volatility: > {self.entry_filters['volatility_min']:.0f}% (momentum แรง!)")
        print(f"   ✅ Sector: > {self.entry_filters['sector_score_min']:.0f} (sector แข็งแรงมาก!)")
        print(f"   ✅ Momentum 30d: > +{self.entry_filters['momentum_30d_min']:.0f}% (กำลังขึ้นอยู่!)")
        print(f"   ✅ Beta: {self.entry_filters['beta_min']:.1f} - {self.entry_filters['beta_max']:.1f}")

        print("\n📋 Adaptive TP/SL:")
        print(f"   ✨ TP: 10-18% (ปรับตาม RS, regime)")
        print(f"   ✨ SL: -5% ถึง -8% (ปรับตาม volatility)")
        print(f"   ✨ Trailing: -2% ถึง -4% (เข้มงวดขึ้นเมื่อถือนาน)")

        # Test
        entry_dates = []
        current = self.start_date
        while current < self.end_date - timedelta(days=30):
            entry_dates.append(current)
            current += timedelta(days=7)

        all_trades = []

        print(f"\n🔍 Testing {len(TEST_STOCKS)} stocks at {len(entry_dates)} entry points...")
        print(f"   (เข้มงวดมาก - คาดว่าผ่านแค่ 20-30%)\n")

        for entry_date in entry_dates:
            regime = self.regime_detector.get_current_regime(entry_date)

            if regime['regime'] != 'BULL':
                print(f"📅 {entry_date.strftime('%Y-%m-%d')} - SKIP ({regime['regime']})")
                continue

            print(f"📅 {entry_date.strftime('%Y-%m-%d')} - BULL ✅ (Strength: {regime['strength']})")

            passed_count = 0
            for symbol in TEST_STOCKS:
                passes, details = self.check_strict_entry(symbol, entry_date)

                if passes:
                    passed_count += 1
                    result = self.simulate_complete(symbol, entry_date, details)

                    if result:
                        all_trades.append(result)
                        status = "✅" if result['winner'] else "❌"
                        print(f"  {symbol:6s}: {status} {result['return_pct']:+6.2f}% ({result['days_held']:2d}d) "
                              f"Peak:{result['peak_return']:+.1f}% (d{result['peak_day']:2d}) - {result['exit_reason']} "
                              f"[RS:{result['rs']:+.1f}% Vol:{result['volatility']:.0f}%]")

            print(f"  → Passed strict filters: {passed_count}/{len(TEST_STOCKS)} ({passed_count/len(TEST_STOCKS)*100:.0f}%)\n")

        return self.analyze_results(all_trades)

    def analyze_results(self, trades: List[Dict]) -> Dict:
        """Analyze with focus on monthly returns"""

        if not trades:
            print("\n❌ No trades found! Filters too strict?")
            return {}

        print("\n" + "="*100)
        print("📊 RESULTS - v3.0 COMPLETE SYSTEM")
        print("="*100)

        total = len(trades)
        winners = [t for t in trades if t['winner']]
        losers = [t for t in trades if not t['winner']]
        win_rate = len(winners) / total * 100

        returns = [t['return_pct'] for t in trades]
        avg_return = np.mean(returns)
        avg_winner = np.mean([t['return_pct'] for t in winners]) if winners else 0
        avg_loser = np.mean([t['return_pct'] for t in losers]) if losers else 0

        avg_days = np.mean([t['days_held'] for t in trades])
        avg_peak = np.mean([t['peak_return'] for t in trades])
        avg_peak_day = np.mean([t['peak_day'] for t in trades])

        # Quality metrics
        avg_rs = np.mean([t['rs'] for t in trades])
        avg_vol = np.mean([t['volatility'] for t in trades])
        avg_momentum = np.mean([t['momentum_30d'] for t in trades])

        # Exit reasons
        exit_reasons = {}
        for t in trades:
            reason = t['exit_reason'].split('_')[0] if '_' in t['exit_reason'] else t['exit_reason']
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        total_return = sum(returns)

        print(f"\n🎯 Performance:")
        print(f"   Trades: {total}")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Avg Return: {avg_return:+.2f}%")
        print(f"   Avg Winner: {avg_winner:+.2f}%")
        print(f"   Avg Loser: {avg_loser:+.2f}%")
        print(f"   Total Return: {total_return:+.2f}%")

        print(f"\n📊 Holding Period:")
        print(f"   Avg Days Held: {avg_days:.1f} days")
        print(f"   Avg Peak: {avg_peak:+.2f}% (day {avg_peak_day:.0f})")

        print(f"\n✨ Stock Quality (passed strict filters):")
        print(f"   Avg RS: {avg_rs:+.1f}%")
        print(f"   Avg Volatility: {avg_vol:.1f}%")
        print(f"   Avg Momentum 30d: {avg_momentum:+.1f}%")

        print(f"\n📊 Exit Reasons:")
        for reason in sorted(exit_reasons.keys(), key=lambda x: exit_reasons[x], reverse=True):
            count = exit_reasons[reason]
            pct = count / total * 100
            print(f"   {reason:15s}: {count:3d} ({pct:5.1f}%)")

        # Top performers
        print(f"\n🏆 Top 10:")
        sorted_trades = sorted(trades, key=lambda x: x['return_pct'], reverse=True)
        for i, t in enumerate(sorted_trades[:10], 1):
            print(f"   {i:2d}. {t['symbol']:6s}: {t['return_pct']:+6.2f}% ({t['days_held']:2d}d) "
                  f"Peak:{t['peak_return']:+.1f}%(d{t['peak_day']}) - {t['exit_reason']}")

        # Monthly breakdown
        print(f"\n📅 Monthly Breakdown:")
        monthly = {}
        for t in trades:
            month = t['entry_date'][:7]
            if month not in monthly:
                monthly[month] = []
            monthly[month].append(t)

        for month in sorted(monthly.keys()):
            m_trades = monthly[month]
            m_win = sum(1 for t in m_trades if t['winner']) / len(m_trades) * 100
            m_avg = np.mean([t['return_pct'] for t in m_trades])
            m_total = sum([t['return_pct'] for t in m_trades])
            m_days = np.mean([t['days_held'] for t in m_trades])

            print(f"\n{month}:")
            print(f"   Trades: {len(m_trades)}")
            print(f"   Win Rate: {m_win:.1f}%")
            print(f"   Avg Return: {m_avg:+.2f}%")
            print(f"   Total Return: {m_total:+.2f}%")
            print(f"   Avg Days: {m_days:.1f}")

        print("\n" + "="*100)
        print("✅ COMPLETE")
        print("="*100)

        # Monthly return estimate
        trades_per_month = 30 / avg_days if avg_days > 0 else 0
        monthly_est = avg_return * trades_per_month

        print(f"\n💰 MONTHLY RETURN ESTIMATE:")
        print(f"   Avg holding: {avg_days:.1f} days")
        print(f"   Trades/month potential: {trades_per_month:.1f}")
        print(f"   Avg return/trade: {avg_return:+.2f}%")
        print(f"   📈 MONTHLY RETURN: {monthly_est:+.2f}%")

        if monthly_est >= 10.0:
            print(f"\n🎉 SUCCESS! {monthly_est:.1f}%/month >= 10% target!")
        elif monthly_est >= 5.0:
            print(f"\n✅ GOOD! {monthly_est:.1f}%/month")
        else:
            print(f"\n⚠️ Below target: {monthly_est:.1f}%/month")

        return {'total': total, 'win_rate': win_rate, 'avg_return': avg_return,
                'monthly_est': monthly_est, 'trades': trades}


def main():
    print("🚀 v3.0 COMPLETE SYSTEM")
    print("   เข้มงวดที่ Entry + ฉลาดที่ Exit = กำไร 10-15%/เดือน!")
    print("   This will take 2-3 minutes...\n")

    backtest = BacktestV30Complete(lookback_months=2)
    results = backtest.run_backtest()


if __name__ == "__main__":
    main()
