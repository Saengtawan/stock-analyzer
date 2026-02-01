#!/usr/bin/env python3
"""
Test what Yahoo Finance actually returns for pre-market data
"""

import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime

def test_yahoo_premarket():
    """Test Yahoo Finance pre-market data"""

    symbol = 'TSLA'
    print("=" * 80)
    print(f"Testing Yahoo Finance Pre-market Data for {symbol}")
    print("=" * 80)

    # Check current time
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    print(f"\nCurrent Time (ET): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Day: {now.strftime('%A')}")

    ticker = yf.Ticker(symbol)

    # Test different period and interval combinations
    test_configs = [
        ("1d", "5m"),
        ("1d", "1m"),
        ("2d", "5m"),
        ("5d", "5m"),
    ]

    for period, interval in test_configs:
        print("\n" + "-" * 80)
        print(f"Testing: period={period}, interval={interval}")
        print("-" * 80)

        try:
            data = ticker.history(period=period, interval=interval, prepost=True)

            if data.empty:
                print(f"❌ No data returned")
                continue

            print(f"✅ Got {len(data)} bars")

            # Reset index and convert to ET
            data = data.reset_index()

            # Check column names
            print(f"\nColumns: {list(data.columns)}")

            # Convert to Eastern time
            datetime_col = 'Datetime' if 'Datetime' in data.columns else 'Date'

            if datetime_col in data.columns:
                data[datetime_col] = pd.to_datetime(data[datetime_col])

                if data[datetime_col].dt.tz is not None:
                    data[datetime_col] = data[datetime_col].dt.tz_convert(eastern)
                else:
                    data[datetime_col] = data[datetime_col].dt.tz_localize('UTC').dt.tz_convert(eastern)

                # Show first few bars
                print(f"\nFirst 5 bars:")
                for idx, row in data.head(5).iterrows():
                    dt = row[datetime_col]
                    print(f"  {dt.strftime('%Y-%m-%d %H:%M:%S %Z')} - Close: ${row['Close']:.2f}, Volume: {int(row['Volume']):,}")

                # Show last few bars
                print(f"\nLast 5 bars:")
                for idx, row in data.tail(5).iterrows():
                    dt = row[datetime_col]
                    print(f"  {dt.strftime('%Y-%m-%d %H:%M:%S %Z')} - Close: ${row['Close']:.2f}, Volume: {int(row['Volume']):,}")

                # Check for pre-market data (4:00-9:30 AM)
                premarket = data[
                    ((data[datetime_col].dt.hour >= 4) & (data[datetime_col].dt.hour < 9)) |
                    ((data[datetime_col].dt.hour == 9) & (data[datetime_col].dt.minute < 30))
                ]

                print(f"\n🔍 Pre-market bars (4:00-9:30 AM ET): {len(premarket)}")

                if not premarket.empty:
                    print("\nPre-market bars:")
                    for idx, row in premarket.iterrows():
                        dt = row[datetime_col]
                        print(f"  {dt.strftime('%Y-%m-%d %H:%M:%S %Z')} - Close: ${row['Close']:.2f}, Volume: {int(row['Volume']):,}")

                # Check for regular hours data (9:30-16:00)
                regular = data[
                    ((data[datetime_col].dt.hour == 9) & (data[datetime_col].dt.minute >= 30)) |
                    ((data[datetime_col].dt.hour >= 10) & (data[datetime_col].dt.hour < 16))
                ]
                print(f"\n🔍 Regular hours bars (9:30-16:00 ET): {len(regular)}")

                # Check for after hours data (16:00-20:00)
                afterhours = data[
                    (data[datetime_col].dt.hour >= 16) & (data[datetime_col].dt.hour < 20)
                ]
                print(f"🔍 After hours bars (16:00-20:00 ET): {len(afterhours)}")
            else:
                print(f"❌ No datetime column found")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

    # Also test with prepost parameter
    print("\n" + "=" * 80)
    print("Testing with prepost=True parameter")
    print("=" * 80)

    try:
        data = ticker.history(period="1d", interval="5m", prepost=True)

        if not data.empty:
            data = data.reset_index()
            datetime_col = 'Datetime' if 'Datetime' in data.columns else 'Date'

            if datetime_col in data.columns:
                data[datetime_col] = pd.to_datetime(data[datetime_col])
                if data[datetime_col].dt.tz is not None:
                    data[datetime_col] = data[datetime_col].dt.tz_convert(eastern)
                else:
                    data[datetime_col] = data[datetime_col].dt.tz_localize('UTC').dt.tz_convert(eastern)

                print(f"\n✅ Got {len(data)} total bars with prepost=True")

                # Show time range
                print(f"Time range: {data[datetime_col].min().strftime('%Y-%m-%d %H:%M')} to {data[datetime_col].max().strftime('%Y-%m-%d %H:%M')}")

                # Check for pre-market
                premarket = data[
                    ((data[datetime_col].dt.hour >= 4) & (data[datetime_col].dt.hour < 9)) |
                    ((data[datetime_col].dt.hour == 9) & (data[datetime_col].dt.minute < 30))
                ]
                print(f"\n🔍 Pre-market bars with prepost=True: {len(premarket)}")

                if not premarket.empty:
                    print("\nPre-market data found! Sample:")
                    for idx, row in premarket.head(10).iterrows():
                        dt = row[datetime_col]
                        print(f"  {dt.strftime('%H:%M')} - ${row['Close']:.2f}, Vol: {int(row['Volume']):,}")
        else:
            print("❌ No data with prepost=True")

    except Exception as e:
        print(f"❌ Error with prepost=True: {e}")

if __name__ == '__main__':
    test_yahoo_premarket()
