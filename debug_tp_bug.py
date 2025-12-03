"""Debug script to investigate TP calculation bug for DIS"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from main import StockAnalyzer
import yfinance as yf

# Setup logger
logger.remove()
logger.add(sys.stdout, level="INFO")

def debug_dis_analysis():
    """Debug DIS to find TP bug"""
    symbol = 'DIS'
    analysis_date = datetime(2024, 11, 7)  # From backtest that showed bug

    analyzer = StockAnalyzer()

    print(f"\n{'='*70}")
    print(f"🔍 DEBUG: {symbol} Analysis on {analysis_date.date()}")
    print(f"{'='*70}\n")

    # Get historical data up to analysis_date
    start_date = analysis_date - timedelta(days=400)

    print(f"📊 Fetching data from {start_date.date()} to {analysis_date.date()}...")

    # Get data using yfinance directly
    ticker_obj = yf.Ticker(symbol)
    hist_data = ticker_obj.history(
        start=start_date.strftime('%Y-%m-%d'),
        end=(analysis_date + timedelta(days=1)).strftime('%Y-%m-%d'),
        interval='1d'
    )

    # Convert to expected format
    price_data = hist_data.reset_index()
    price_data.columns = price_data.columns.str.lower()
    price_data['symbol'] = symbol
    price_data = price_data[price_data.index <= len(price_data) - 1]  # Remove future data

    # Truncate to analysis date
    hist_data = hist_data[hist_data.index.date <= analysis_date.date()]
    price_data = hist_data.reset_index()
    price_data.columns = price_data.columns.str.lower()
    price_data['symbol'] = symbol

    if price_data.empty:
        print(f"❌ No data available for {symbol}")
        return

    print(f"✅ Got {len(price_data)} days of data\n")

    # Run analysis
    result = analyzer.analyze_stock(
        symbol=symbol,
        time_horizon='short',
        account_value=100000,
        include_ai_analysis=False,
        historical_price_data=price_data,
        analysis_date=analysis_date
    )

    # Extract key values from unified_recommendation (where TP/SL are now stored)
    unified = result.get('unified_recommendation', {})

    # Debug: print all available keys
    print(f"🔍 Available keys in unified_recommendation:")
    print(f"   {list(unified.keys())}\n")

    # Get entry from entry_levels
    entry_levels = unified.get('entry_levels', {})
    entry_price = entry_levels.get('recommended', 0)  # or 'aggressive', 'moderate', 'conservative'

    take_profit = unified.get('target_price', 0)
    stop_loss = unified.get('stop_loss', 0)

    # Get internal calculation details
    technical = result.get('technical_analysis', {})
    indicators = technical.get('indicators', {})
    current_price = indicators.get('current_price', 0)

    print(f"💰 PRICES:")
    print(f"  Current Price: ${current_price:.2f}")
    print(f"  Entry Price:   ${entry_price:.2f}")
    print(f"  Take Profit:   ${take_profit:.2f}")
    print(f"  Stop Loss:     ${stop_loss:.2f}")

    # Print entry/tp/sl details if available
    if 'entry_details' in unified:
        print(f"\n📊 ENTRY DETAILS:")
        entry_details = unified['entry_details']
        print(f"   {entry_details}")

    print()

    # Calculate returns
    tp_return = ((take_profit - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    sl_return = ((stop_loss - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    rr_ratio = abs(tp_return / sl_return) if sl_return != 0 else 0

    print(f"📈 RETURNS:")
    print(f"  TP Return: {tp_return:+.2f}%")
    print(f"  SL Return: {sl_return:+.2f}%")
    print(f"  R/R Ratio: {rr_ratio:.2f}")
    print()

    # Check if TP < Entry (THE BUG!)
    if take_profit < entry_price:
        print(f"🚨 BUG DETECTED! TP (${take_profit:.2f}) < Entry (${entry_price:.2f})")
        print(f"   This would result in a LOSS of {tp_return:.2f}% if TP is hit!\n")

    # Try to extract swing levels from technical analysis
    # Look for swing_high and swing_low
    print(f"🔍 TECHNICAL DETAILS:")
    print(f"  Market State: {technical.get('market_state', 'N/A')}")

    # Check if there are swing levels in support_resistance
    support_resistance = indicators.get('support_resistance', {})
    print(f"  Support: {support_resistance.get('support', 'N/A')}")
    print(f"  Resistance: {support_resistance.get('resistance', 'N/A')}")

    # Print recent price action to understand swing points
    recent_data = price_data.tail(20)
    print(f"\n📊 RECENT PRICE ACTION (last 20 days):")
    print(f"  High: ${recent_data['high'].max():.2f}")
    print(f"  Low:  ${recent_data['low'].min():.2f}")
    print(f"  Last Close: ${recent_data['close'].iloc[-1]:.2f}")
    print()

    # Print recommendation
    unified = result.get('unified_recommendation', {})
    print(f"💡 RECOMMENDATION:")
    print(f"  {unified.get('recommendation', 'N/A')} (Score: {unified.get('score', 0):.1f}/10)")
    print(f"  Confidence: {unified.get('confidence', 'N/A')}")
    print()

    print(f"{'='*70}\n")

if __name__ == '__main__':
    debug_dis_analysis()
