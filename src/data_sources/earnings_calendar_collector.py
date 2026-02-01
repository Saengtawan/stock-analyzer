#!/usr/bin/env python3
"""
Earnings Calendar Collector - ดึงข้อมูลปฏิทินประกาศผลประกอบการ

นี่คือปัจจัยสำคัญมาก!
- หุ้นอาจดูดี technical แต่พอประกาศงบไม่ดี ราคาตก 10-20%
- ควรหลีกเลี่ยงซื้อก่อนประกาศงบ 1-2 สัปดาห์
- Earnings surprise (ดี/แย่กว่าคาด) มีผลมาก

แหล่งข้อมูลฟรี:
- Yahoo Finance Calendar
- Finviz
- SEC EDGAR
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


class EarningsCalendarCollector:
    """
    ดึงข้อมูลปฏิทินประกาศผลประกอบการ

    สิ่งที่เก็บ:
    - วันประกาศงบ (earnings date)
    - EPS คาดการณ์ vs จริง
    - Revenue คาดการณ์ vs จริง
    - Surprise % (ดี/แย่กว่าคาด)
    - ประวัติ beat/miss
    """

    def __init__(self):
        self.cache_dir = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'earnings'
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_earnings_calendar(self, symbol: str) -> Dict:
        """Get earnings calendar for a stock"""
        earnings_info = {
            'symbol': symbol,
            'fetched_at': datetime.now().isoformat(),
            'next_earnings': None,
            'days_to_earnings': None,
            'earnings_history': [],
            'earnings_trend': None,
            'beat_rate': None,
            'warning': None,
        }

        if yf is None:
            return earnings_info

        try:
            ticker = yf.Ticker(symbol)

            # Get earnings calendar
            calendar = ticker.calendar
            if calendar is not None and not calendar.empty:
                if 'Earnings Date' in calendar.index:
                    earnings_date = calendar.loc['Earnings Date']
                    if hasattr(earnings_date, 'iloc'):
                        next_date = earnings_date.iloc[0]
                    else:
                        next_date = earnings_date

                    earnings_info['next_earnings'] = str(next_date)

                    # Calculate days to earnings
                    try:
                        earn_date = pd.to_datetime(next_date)
                        days = (earn_date - pd.Timestamp.now()).days
                        earnings_info['days_to_earnings'] = days

                        # Warning if earnings is soon
                        if days <= 7:
                            earnings_info['warning'] = 'EARNINGS_IMMINENT'
                        elif days <= 14:
                            earnings_info['warning'] = 'EARNINGS_SOON'
                    except:
                        pass

            # Get earnings history
            earnings = ticker.earnings_history
            if earnings is not None and not earnings.empty:
                history = []
                for _, row in earnings.iterrows():
                    rec = {
                        'date': str(row.name) if hasattr(row, 'name') else None,
                        'eps_actual': row.get('epsActual'),
                        'eps_estimate': row.get('epsEstimate'),
                        'surprise_pct': row.get('surprisePercent'),
                    }

                    # Determine beat/miss
                    if rec['eps_actual'] and rec['eps_estimate']:
                        if rec['eps_actual'] > rec['eps_estimate']:
                            rec['result'] = 'BEAT'
                        elif rec['eps_actual'] < rec['eps_estimate']:
                            rec['result'] = 'MISS'
                        else:
                            rec['result'] = 'MET'

                    history.append(rec)

                earnings_info['earnings_history'] = history

                # Calculate beat rate
                beats = sum(1 for h in history if h.get('result') == 'BEAT')
                if history:
                    earnings_info['beat_rate'] = beats / len(history) * 100

                # Trend (last 4 quarters)
                recent = history[-4:] if len(history) >= 4 else history
                recent_beats = sum(1 for h in recent if h.get('result') == 'BEAT')
                if len(recent) >= 4:
                    if recent_beats >= 3:
                        earnings_info['earnings_trend'] = 'CONSISTENT_BEATER'
                    elif recent_beats <= 1:
                        earnings_info['earnings_trend'] = 'CONSISTENT_MISSER'
                    else:
                        earnings_info['earnings_trend'] = 'MIXED'

            # Get analyst estimates
            try:
                analysis = ticker.analyst_price_targets
                if analysis is not None:
                    earnings_info['analyst_estimates'] = {
                        'target_mean': analysis.get('mean'),
                        'target_high': analysis.get('high'),
                        'target_low': analysis.get('low'),
                    }
            except:
                pass

        except Exception as e:
            earnings_info['error'] = str(e)

        return earnings_info

    def get_weekly_earnings_calendar(self) -> Dict[str, List]:
        """Get this week's earnings for major stocks"""
        weekly = {
            'week_start': datetime.now().strftime('%Y-%m-%d'),
            'stocks': [],
        }

        # Major stocks to track
        major_stocks = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
            'JPM', 'BAC', 'GS', 'V', 'MA',
            'JNJ', 'UNH', 'PFE', 'LLY',
            'XOM', 'CVX',
            'HD', 'LOW', 'COST', 'WMT', 'MCD',
            'CAT', 'HON', 'GE', 'BA',
            'AMD', 'INTC', 'QCOM', 'CRM', 'NFLX'
        ]

        for symbol in major_stocks:
            info = self.get_earnings_calendar(symbol)
            if info.get('days_to_earnings') is not None:
                if 0 <= info['days_to_earnings'] <= 7:
                    weekly['stocks'].append({
                        'symbol': symbol,
                        'earnings_date': info['next_earnings'],
                        'days': info['days_to_earnings'],
                        'beat_rate': info.get('beat_rate'),
                        'trend': info.get('earnings_trend'),
                    })

        # Sort by days to earnings
        weekly['stocks'].sort(key=lambda x: x['days'])

        return weekly

    def should_avoid_stock(self, symbol: str, days_threshold: int = 7) -> tuple:
        """
        Check if should avoid buying a stock due to upcoming earnings

        Returns:
            (should_avoid: bool, reason: str)
        """
        info = self.get_earnings_calendar(symbol)

        if info.get('days_to_earnings') is None:
            return False, "No earnings date found"

        days = info['days_to_earnings']

        if days < 0:
            return False, "Earnings already passed"

        if days <= days_threshold:
            trend = info.get('earnings_trend', 'UNKNOWN')
            beat_rate = info.get('beat_rate', 50)

            if trend == 'CONSISTENT_MISSER' or (beat_rate and beat_rate < 40):
                return True, f"AVOID: Earnings in {days} days, historically misses"
            else:
                return True, f"CAUTION: Earnings in {days} days (beat rate: {beat_rate:.0f}%)"

        return False, f"Earnings in {days} days - OK"

    def analyze_earnings_impact(self, symbol: str) -> Dict:
        """
        Analyze how earnings announcements typically impact this stock

        Looks at historical price moves after earnings
        """
        impact = {
            'symbol': symbol,
            'avg_beat_move': None,
            'avg_miss_move': None,
            'typical_volatility': None,
        }

        if yf is None:
            return impact

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='2y')
            earnings = ticker.earnings_history

            if hist.empty or earnings is None or earnings.empty:
                return impact

            beat_moves = []
            miss_moves = []

            for _, row in earnings.iterrows():
                try:
                    earn_date = pd.Timestamp(row.name)
                    # Find price 1 day after earnings
                    after_mask = hist.index > earn_date
                    if not after_mask.any():
                        continue

                    after_idx = hist.index[after_mask][0]
                    before_idx = hist.index[hist.index <= earn_date][-1]

                    before_price = float(hist.loc[before_idx, 'Close'])
                    after_price = float(hist.loc[after_idx, 'Close'])

                    pct_move = ((after_price - before_price) / before_price) * 100

                    result = row.get('surprisePercent', 0)
                    if result and result > 0:
                        beat_moves.append(pct_move)
                    elif result and result < 0:
                        miss_moves.append(pct_move)

                except:
                    continue

            if beat_moves:
                impact['avg_beat_move'] = sum(beat_moves) / len(beat_moves)
                impact['beat_count'] = len(beat_moves)

            if miss_moves:
                impact['avg_miss_move'] = sum(miss_moves) / len(miss_moves)
                impact['miss_count'] = len(miss_moves)

            all_moves = beat_moves + miss_moves
            if all_moves:
                impact['typical_volatility'] = sum(abs(m) for m in all_moves) / len(all_moves)

        except Exception as e:
            impact['error'] = str(e)

        return impact

    def print_upcoming_earnings(self, symbols: List[str] = None):
        """Print upcoming earnings for watchlist"""
        if symbols is None:
            symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

        print("=" * 80)
        print("UPCOMING EARNINGS CALENDAR")
        print("=" * 80)
        print(f"\n{'Symbol':<8} {'Earnings Date':<15} {'Days':<6} {'Beat Rate':<10} {'Status'}")
        print("-" * 60)

        for symbol in symbols:
            info = self.get_earnings_calendar(symbol)
            days = info.get('days_to_earnings', 'N/A')
            beat_rate = info.get('beat_rate', 'N/A')
            earn_date = info.get('next_earnings', 'Unknown')

            if isinstance(beat_rate, float):
                beat_str = f"{beat_rate:.0f}%"
            else:
                beat_str = str(beat_rate)

            warning = info.get('warning', '')
            status = ''
            if warning == 'EARNINGS_IMMINENT':
                status = 'AVOID!'
            elif warning == 'EARNINGS_SOON':
                status = 'Caution'
            else:
                status = 'OK'

            print(f"{symbol:<8} {str(earn_date)[:15]:<15} {str(days):<6} {beat_str:<10} {status}")

    def save_to_cache(self, symbol: str, data: Dict) -> str:
        """Save earnings data to cache"""
        filename = f"{symbol}_earnings_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.cache_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        return filepath


class EarningsFilter:
    """
    Filter stocks based on earnings risk

    ใช้เพื่อหลีกเลี่ยงหุ้นที่กำลังจะประกาศงบ
    """

    def __init__(self, days_to_avoid: int = 7):
        self.collector = EarningsCalendarCollector()
        self.days_to_avoid = days_to_avoid

    def filter_stocks(self, symbols: List[str]) -> Dict[str, List]:
        """
        Filter stocks into safe/risky based on earnings

        Returns:
            {
                'safe': [symbols without imminent earnings],
                'risky': [symbols with earnings soon],
                'details': {symbol: info}
            }
        """
        result = {
            'safe': [],
            'risky': [],
            'details': {}
        }

        for symbol in symbols:
            should_avoid, reason = self.collector.should_avoid_stock(
                symbol, self.days_to_avoid
            )

            result['details'][symbol] = reason

            if should_avoid:
                result['risky'].append(symbol)
            else:
                result['safe'].append(symbol)

        return result


def demo():
    """Demo the collector"""
    collector = EarningsCalendarCollector()

    print("=" * 80)
    print("EARNINGS CALENDAR COLLECTOR DEMO")
    print("=" * 80)

    # Check major stocks
    stocks = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA']
    collector.print_upcoming_earnings(stocks)

    # Detailed analysis for one stock
    print("\n" + "=" * 80)
    print("DETAILED ANALYSIS: AAPL")
    print("=" * 80)

    info = collector.get_earnings_calendar('AAPL')

    print(f"\nNext Earnings: {info.get('next_earnings')}")
    print(f"Days to Earnings: {info.get('days_to_earnings')}")
    print(f"Beat Rate: {info.get('beat_rate'):.1f}%" if info.get('beat_rate') else "N/A")
    print(f"Trend: {info.get('earnings_trend')}")

    if info.get('earnings_history'):
        print("\nRecent Earnings History:")
        for h in info['earnings_history'][-4:]:
            print(f"  {h.get('date', 'N/A')}: {h.get('result', 'N/A')} "
                  f"(Surprise: {h.get('surprise_pct', 0):.1f}%)")

    # Impact analysis
    print("\n" + "=" * 80)
    print("EARNINGS IMPACT ANALYSIS")
    print("=" * 80)

    impact = collector.analyze_earnings_impact('AAPL')
    print(f"\nAverage move on BEAT: {impact.get('avg_beat_move', 'N/A')}")
    print(f"Average move on MISS: {impact.get('avg_miss_move', 'N/A')}")
    print(f"Typical volatility: {impact.get('typical_volatility', 'N/A')}")


if __name__ == '__main__':
    demo()
