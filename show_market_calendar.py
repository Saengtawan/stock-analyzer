#!/usr/bin/env python3
"""
MARKET CALENDAR & HOLIDAY SCHEDULE

แสดงตารางตลาดหุ้น และวันหยุดที่จะมาถึง

Usage:
    python show_market_calendar.py [days]

    days: Number of days to show (default: 14)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from engine.brokers import AlpacaBroker
from datetime import datetime, timedelta


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    print("=" * 70)
    print(f"📅 MARKET CALENDAR (Next {days} Days)")
    print("=" * 70)

    try:
        # Initialize broker
        broker = AlpacaBroker(paper=True)

        # Get calendar
        start_date = datetime.now().strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

        print(f"\n🔄 Fetching calendar from {start_date} to {end_date}...")
        calendar = broker.get_calendar(start=start_date, end=end_date)

        # Create trading day set
        trading_days = {day['date'] for day in calendar}

        # Display calendar
        print("\n" + "=" * 70)
        print("📅 TRADING SCHEDULE")
        print("=" * 70)
        print(f"  {'Date':<12} {'Day':<10} {'Status':<12} {'Hours':<20}")
        print("  " + "-" * 66)

        current = datetime.now()
        for i in range(days):
            check_date = current + timedelta(days=i)
            date_str = check_date.strftime('%Y-%m-%d')
            day_name = check_date.strftime('%A')

            if date_str in trading_days:
                # Find calendar entry
                cal_entry = next((c for c in calendar if c['date'] == date_str), None)
                if cal_entry:
                    open_time = cal_entry['open']
                    close_time = cal_entry['close']
                    hours = f"{open_time} - {close_time}"
                    status = "🟢 OPEN"
                else:
                    hours = ""
                    status = "🟢 OPEN"
            else:
                hours = ""
                if day_name in ['Saturday', 'Sunday']:
                    status = "⚫ Weekend"
                else:
                    status = "⚫ HOLIDAY"

            print(f"  {date_str:<12} {day_name:<10} {status:<12} {hours:<20}")

        # Get upcoming holidays
        print("\n" + "=" * 70)
        print("⚠️  UPCOMING HOLIDAYS")
        print("=" * 70)

        holidays = broker.get_upcoming_holidays(days=days)

        if holidays:
            print(f"  {'Date':<12} {'Day':<10} {'Days Away':>10}")
            print("  " + "-" * 36)

            for holiday in holidays:
                date_str = holiday['date']
                day_name = holiday['day_of_week']
                days_away = holiday['days_away']

                print(f"  {date_str:<12} {day_name:<10} {days_away:>10} days")

            # Warning for upcoming long weekends
            for holiday in holidays:
                if holiday['days_away'] <= 3:
                    print(f"\n  ⚠️  WARNING: Holiday in {holiday['days_away']} days ({holiday['date']})")
                    print(f"      Consider closing positions or avoiding new entries")
        else:
            print("  No holidays in the next {} days".format(days))

        # Check tomorrow
        print("\n" + "=" * 70)
        print("🔍 TOMORROW'S STATUS")
        print("=" * 70)

        is_open_tomorrow = broker.is_market_open_tomorrow()
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        tomorrow_day = (datetime.now() + timedelta(days=1)).strftime('%A')

        if is_open_tomorrow:
            print(f"  ✅ Market will be OPEN tomorrow ({tomorrow_date}, {tomorrow_day})")
            print(f"      → Safe to enter new positions today")
        else:
            print(f"  ⚠️  Market will be CLOSED tomorrow ({tomorrow_date}, {tomorrow_day})")
            print(f"      → Avoid new positions today (overnight risk)")

            # Find next trading day
            next_day = broker.get_next_market_day()
            if next_day:
                days_until = (datetime.strptime(next_day, '%Y-%m-%d') - datetime.now()).days
                print(f"      → Next trading day: {next_day} ({days_until} days away)")

        print("\n" + "=" * 70)
        print("✅ Calendar loaded!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
