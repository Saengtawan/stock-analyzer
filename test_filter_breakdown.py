#!/usr/bin/env python3
"""
Detailed Filter Breakdown - See which filter is blocking stocks
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from main import StockAnalyzer
import yfinance as yf
import pandas as pd

def test_filter_breakdown():
    """Test each filter individually to see what's blocking stocks"""

    test_stocks = ['GOOGL', 'META', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN']

    print("=" * 100)
    print("🔍 DETAILED FILTER BREAKDOWN - Current Market Conditions")
    print("=" * 100)
    print("\nTesting filters on popular tech stocks...")
    print("-" * 100)

    analyzer = StockAnalyzer()

    for symbol in test_stocks:
        print(f"\n📊 {symbol}:")
        print("-" * 50)

        try:
            # Get basic data
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price_data = analyzer.data_manager.get_price_data(symbol, period='1mo')

            if price_data is None or price_data.empty:
                print(f"   ❌ No price data available")
                continue

            # Check each filter
            filters_status = {}

            # 1. Beta Filter (0.8 < Beta < 2.0)
            beta = info.get('beta', 1.0)
            if beta and 0.8 < beta < 2.0:
                filters_status['Beta'] = f'✅ {beta:.2f} (0.8-2.0)'
            else:
                filters_status['Beta'] = f'❌ {beta:.2f} (need 0.8-2.0)'

            # 2. Volatility Filter (>25%)
            if len(price_data) >= 20:
                close_col = 'close' if 'close' in price_data.columns else 'Close'
                returns = price_data[close_col].pct_change().dropna()
                volatility_annual = returns.std() * (252 ** 0.5) * 100
                if volatility_annual >= 25.0:
                    filters_status['Volatility'] = f'✅ {volatility_annual:.1f}% (need >25%)'
                else:
                    filters_status['Volatility'] = f'❌ {volatility_annual:.1f}% (need >25%)'
            else:
                filters_status['Volatility'] = '❌ Not enough data'

            # 3. Relative Strength Filter (>0%)
            if len(price_data) >= 30:
                close_col = 'close' if 'close' in price_data.columns else 'Close'
                stock_return_30d = ((price_data[close_col].iloc[-1] / price_data[close_col].iloc[-20]) - 1) * 100

                # Get SPY return
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(period='1mo')
                if not spy_hist.empty and len(spy_hist) >= 20:
                    market_return_30d = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-20]) - 1) * 100
                    relative_strength = stock_return_30d - market_return_30d

                    if relative_strength > 0:
                        filters_status['Relative Strength'] = f'✅ {relative_strength:+.1f}% (need >0%)'
                    else:
                        filters_status['Relative Strength'] = f'❌ {relative_strength:+.1f}% (need >0%)'
                else:
                    filters_status['Relative Strength'] = '❌ Cannot calculate (no SPY data)'
            else:
                filters_status['Relative Strength'] = '❌ Not enough data'

            # 4. Valuation Filter (>20 score)
            pe_ratio = info.get('trailingPE', None)
            forward_pe = info.get('forwardPE', None)

            valuation_score = 50.0
            if pe_ratio:
                if pe_ratio > 100:
                    valuation_score -= 25
                elif pe_ratio > 60:
                    valuation_score -= 15
                elif 15 <= pe_ratio <= 35:
                    valuation_score += 20

            if forward_pe:
                if forward_pe > 80:
                    valuation_score -= 30
                elif forward_pe > 50:
                    valuation_score -= 20
                elif 15 <= forward_pe <= 30:
                    valuation_score += 25

            if valuation_score > 20:
                filters_status['Valuation'] = f'✅ Score {valuation_score:.1f} (P/E: {pe_ratio:.1f if pe_ratio else "N/A"}, Fwd: {forward_pe:.1f if forward_pe else "N/A"})'
            else:
                filters_status['Valuation'] = f'❌ Score {valuation_score:.1f} (P/E: {pe_ratio:.1f if pe_ratio else "N/A"}, Fwd: {forward_pe:.1f if forward_pe else "N/A"})'

            # Print results
            passed_all = all('✅' in v for v in filters_status.values())

            for filter_name, status in filters_status.items():
                print(f"   {status:60s} {filter_name}")

            if passed_all:
                print(f"\n   🎯 {symbol} PASSES ALL HARD FILTERS!")
            else:
                failed_filters = [name for name, status in filters_status.items() if '❌' in status]
                print(f"\n   ⚠️  {symbol} FAILS: {', '.join(failed_filters)}")

        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n" + "=" * 100)
    print("🎯 SUMMARY")
    print("=" * 100)
    print("\nIf ALL stocks are failing:")
    print("1. Market conditions have changed since backtest")
    print("2. Hard filters are too strict for current environment")
    print("3. Need to RELAX filters (especially RS and Volatility)")
    print("\n")

if __name__ == "__main__":
    test_filter_breakdown()
