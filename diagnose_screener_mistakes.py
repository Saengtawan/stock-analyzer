#!/usr/bin/env python3
"""
Diagnose Growth Catalyst Screener Mistakes
===========================================

วิเคราะห์ว่าทำไม screener ถึงเลือกหุ้นผิด:
- เลือก RIVN, LULU, ARWR, BAC → ขาดทุน ❌
- ไม่เลือก SCCO, PATH, ILMN → กำไร ✅

จะวิเคราะห์:
1. Entry conditions: หุ้นที่ขาดทุน vs กำไร แตกต่างกันอย่างไร?
2. Screening criteria: rule ไหนที่ทำให้เลือกผิด?
3. Missing winners: ทำไมไม่จับหุ้นที่กำไร?
4. แก้ไข criteria และ test อีกรอบ
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os

# เพิ่ม path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))


def calculate_technical_indicators(hist: pd.DataFrame) -> Dict:
    """คำนวณ technical indicators ทั้งหมด"""

    if len(hist) < 50:
        return {}

    close = hist['Close']
    high = hist['High']
    low = hist['Low']
    volume = hist['Volume']

    # Moving averages
    ma20 = close.rolling(window=20).mean()
    ma50 = close.rolling(window=50).mean()

    current_price = close.iloc[-1]

    # Price vs MA
    price_vs_ma20 = ((current_price - ma20.iloc[-1]) / ma20.iloc[-1] * 100) if not pd.isna(ma20.iloc[-1]) else 0
    price_vs_ma50 = ((current_price - ma50.iloc[-1]) / ma50.iloc[-1] * 100) if not pd.isna(ma50.iloc[-1]) else 0

    # MA trend
    ma20_vs_ma50 = ((ma20.iloc[-1] - ma50.iloc[-1]) / ma50.iloc[-1] * 100) if not pd.isna(ma50.iloc[-1]) and not pd.isna(ma20.iloc[-1]) else 0

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    # Momentum
    mom_5d = ((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) > 5 else 0
    mom_10d = ((close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100) if len(close) > 10 else 0
    mom_30d = ((close.iloc[-1] - close.iloc[-31]) / close.iloc[-31] * 100) if len(close) > 30 else 0

    # Volume
    avg_volume = volume.rolling(window=20).mean().iloc[-1]
    current_volume = volume.iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    # Volatility (ATR %)
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=14).mean().iloc[-1]
    atr_pct = (atr / current_price * 100) if current_price > 0 else 0

    # 52-week high/low
    high_52w = high.rolling(window=252, min_periods=20).max().iloc[-1]
    low_52w = low.rolling(window=252, min_periods=20).min().iloc[-1]

    pct_from_high = ((current_price - high_52w) / high_52w * 100) if high_52w > 0 else 0
    pct_from_low = ((current_price - low_52w) / low_52w * 100) if low_52w > 0 else 0

    # Recent performance
    perf_1d = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100) if len(close) > 1 else 0
    perf_5d = mom_5d
    perf_1m = mom_30d

    return {
        'price': current_price,
        'rsi': current_rsi,
        'price_vs_ma20': price_vs_ma20,
        'price_vs_ma50': price_vs_ma50,
        'ma20_vs_ma50': ma20_vs_ma50,
        'mom_5d': mom_5d,
        'mom_10d': mom_10d,
        'mom_30d': mom_30d,
        'volume_ratio': volume_ratio,
        'atr_pct': atr_pct,
        'pct_from_52w_high': pct_from_high,
        'pct_from_52w_low': pct_from_low,
        'perf_1d': perf_1d,
        'perf_5d': perf_5d,
        'perf_1m': perf_1m,
    }


def analyze_stock_at_entry(symbol: str, entry_date: str) -> Dict:
    """
    วิเคราะห์หุ้น ณ จุด entry

    Args:
        symbol: หุ้น
        entry_date: วันที่ entry (YYYY-MM-DD)

    Returns:
        Dict with entry conditions and future performance
    """
    try:
        ticker = yf.Ticker(symbol)

        # Get data from 3 months before entry to 1 month after
        entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
        start_date = entry_dt - timedelta(days=90)
        end_date = entry_dt + timedelta(days=35)

        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty or len(hist) < 30:
            return None

        # Find entry point
        entry_idx = None
        for i, idx in enumerate(hist.index):
            if idx.date() >= entry_dt.date():
                entry_idx = i
                break

        if entry_idx is None or entry_idx < 20:
            return None

        # Get data at entry
        hist_at_entry = hist.iloc[:entry_idx+1]
        entry_price = hist_at_entry['Close'].iloc[-1]

        # Calculate indicators at entry
        indicators = calculate_technical_indicators(hist_at_entry)

        if not indicators:
            return None

        # Get future performance (30 days after entry)
        future_data = hist.iloc[entry_idx:]

        if len(future_data) < 30:
            # ถ้าข้อมูลไม่ครบ 30 วัน ใช้ข้อมูลที่มี
            days_available = len(future_data) - 1
            if days_available < 5:
                return None
        else:
            days_available = 30

        exit_price = future_data['Close'].iloc[min(30, len(future_data)-1)]
        max_price = future_data['High'].iloc[:min(31, len(future_data))].max()
        min_price = future_data['Low'].iloc[:min(31, len(future_data))].min()

        actual_return = ((exit_price - entry_price) / entry_price) * 100
        max_return = ((max_price - entry_price) / entry_price) * 100
        min_return = ((min_price - entry_price) / entry_price) * 100

        # Get company info
        try:
            info = ticker.info
            market_cap = info.get('marketCap', 0)
            sector = info.get('sector', 'Unknown')
            industry = info.get('industry', 'Unknown')
        except:
            market_cap = 0
            sector = 'Unknown'
            industry = 'Unknown'

        return {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'max_price': max_price,
            'min_price': min_price,
            'actual_return': actual_return,
            'max_return': max_return,
            'min_return': min_return,
            'days_tracked': days_available,
            'market_cap': market_cap,
            'sector': sector,
            'industry': industry,
            **indicators
        }

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None


def main():
    print("=" * 100)
    print("🔍 DIAGNOSING GROWTH CATALYST SCREENER")
    print("=" * 100)
    print()

    # หุ้นที่ screener เลือก แต่ขาดทุน
    losers_selected = [
        {'symbol': 'RIVN', 'entry_date': '2025-12-20'},
        {'symbol': 'LULU', 'entry_date': '2025-12-20'},
        {'symbol': 'ARWR', 'entry_date': '2025-12-20'},
        {'symbol': 'BAC', 'entry_date': '2025-12-20'},
    ]

    # หุ้นที่ screener ไม่เลือก แต่กำไร
    winners_missed = [
        {'symbol': 'SCCO', 'entry_date': '2025-12-20'},
        {'symbol': 'PATH', 'entry_date': '2025-12-20'},
        {'symbol': 'ILMN', 'entry_date': '2025-12-20'},
    ]

    # หุ้นอื่นๆ ทดสอบเพิ่ม
    other_stocks = [
        {'symbol': 'NVDA', 'entry_date': '2025-12-20'},
        {'symbol': 'TSLA', 'entry_date': '2025-12-20'},
        {'symbol': 'AAPL', 'entry_date': '2025-12-20'},
        {'symbol': 'MSFT', 'entry_date': '2025-12-20'},
        {'symbol': 'GOOGL', 'entry_date': '2025-12-20'},
        {'symbol': 'META', 'entry_date': '2025-12-20'},
        {'symbol': 'AMD', 'entry_date': '2025-12-20'},
        {'symbol': 'MU', 'entry_date': '2025-12-20'},
        {'symbol': 'INTC', 'entry_date': '2025-12-20'},
    ]

    print("Analyzing stocks...")
    print()

    # Analyze all stocks
    losers_data = []
    winners_data = []
    other_data = []

    print("📉 Analyzing losers (selected but lost):")
    for stock in losers_selected:
        print(f"   {stock['symbol']}...", end=' ')
        result = analyze_stock_at_entry(stock['symbol'], stock['entry_date'])
        if result:
            losers_data.append(result)
            print(f"✅ Return: {result['actual_return']:+.1f}%")
        else:
            print("❌ Failed")

    print()
    print("📈 Analyzing winners (missed by screener):")
    for stock in winners_missed:
        print(f"   {stock['symbol']}...", end=' ')
        result = analyze_stock_at_entry(stock['symbol'], stock['entry_date'])
        if result:
            winners_data.append(result)
            print(f"✅ Return: {result['actual_return']:+.1f}%")
        else:
            print("❌ Failed")

    print()
    print("📊 Analyzing other stocks:")
    for stock in other_stocks:
        print(f"   {stock['symbol']}...", end=' ')
        result = analyze_stock_at_entry(stock['symbol'], stock['entry_date'])
        if result:
            other_data.append(result)
            print(f"✅ Return: {result['actual_return']:+.1f}%")
        else:
            print("❌ Failed")

    # Convert to DataFrame
    losers_df = pd.DataFrame(losers_data)
    winners_df = pd.DataFrame(winners_data)
    other_df = pd.DataFrame(other_data)

    print()
    print("=" * 100)
    print("📊 ANALYSIS RESULTS")
    print("=" * 100)

    # Performance comparison
    print()
    print("1️⃣ PERFORMANCE COMPARISON")
    print("-" * 100)

    if not losers_df.empty:
        print(f"\n❌ LOSERS (Selected but lost):")
        print(f"   Count: {len(losers_df)}")
        print(f"   Avg Return: {losers_df['actual_return'].mean():+.2f}%")
        print(f"   Median: {losers_df['actual_return'].median():+.2f}%")
        print(f"   Best: {losers_df['actual_return'].max():+.2f}%")
        print(f"   Worst: {losers_df['actual_return'].min():+.2f}%")

        print(f"\n   Individual:")
        for _, row in losers_df.iterrows():
            print(f"   - {row['symbol']}: {row['actual_return']:+.2f}% (Max: {row['max_return']:+.2f}%)")

    if not winners_df.empty:
        print(f"\n✅ WINNERS (Missed by screener):")
        print(f"   Count: {len(winners_df)}")
        print(f"   Avg Return: {winners_df['actual_return'].mean():+.2f}%")
        print(f"   Median: {winners_df['actual_return'].median():+.2f}%")
        print(f"   Best: {winners_df['actual_return'].max():+.2f}%")
        print(f"   Worst: {winners_df['actual_return'].min():+.2f}%")

        print(f"\n   Individual:")
        for _, row in winners_df.iterrows():
            print(f"   - {row['symbol']}: {row['actual_return']:+.2f}% (Max: {row['max_return']:+.2f}%)")

    if not other_df.empty:
        print(f"\n📊 OTHER STOCKS:")
        print(f"   Count: {len(other_df)}")
        print(f"   Avg Return: {other_df['actual_return'].mean():+.2f}%")

        # Group by winners and losers
        other_winners = other_df[other_df['actual_return'] > 0]
        other_losers = other_df[other_df['actual_return'] <= 0]

        if not other_winners.empty:
            print(f"\n   Winners ({len(other_winners)}):")
            for _, row in other_winners.iterrows():
                print(f"   - {row['symbol']}: {row['actual_return']:+.2f}%")

        if not other_losers.empty:
            print(f"\n   Losers ({len(other_losers)}):")
            for _, row in other_losers.iterrows():
                print(f"   - {row['symbol']}: {row['actual_return']:+.2f}%")

    # Technical indicators comparison
    print()
    print("=" * 100)
    print("2️⃣ ENTRY CONDITIONS COMPARISON")
    print("-" * 100)

    indicators_to_compare = [
        'rsi', 'price_vs_ma20', 'price_vs_ma50', 'ma20_vs_ma50',
        'mom_5d', 'mom_10d', 'mom_30d', 'volume_ratio', 'atr_pct',
        'pct_from_52w_high', 'pct_from_52w_low'
    ]

    print()
    print("Losers vs Winners at Entry:")
    print()
    print(f"{'Indicator':<20} {'Losers (Avg)':<15} {'Winners (Avg)':<15} {'Difference':<15}")
    print("-" * 70)

    for indicator in indicators_to_compare:
        if indicator in losers_df.columns and indicator in winners_df.columns:
            loser_avg = losers_df[indicator].mean()
            winner_avg = winners_df[indicator].mean()
            diff = winner_avg - loser_avg

            print(f"{indicator:<20} {loser_avg:<15.2f} {winner_avg:<15.2f} {diff:+.2f}")

    # Find discriminating factors
    print()
    print("=" * 100)
    print("3️⃣ KEY DIFFERENCES (Why screener picked wrong stocks?)")
    print("-" * 100)

    significant_diffs = []

    for indicator in indicators_to_compare:
        if indicator in losers_df.columns and indicator in winners_df.columns:
            loser_avg = losers_df[indicator].mean()
            winner_avg = winners_df[indicator].mean()
            diff = winner_avg - loser_avg
            diff_pct = abs(diff / loser_avg * 100) if loser_avg != 0 else 0

            if diff_pct > 20:  # Significant difference > 20%
                significant_diffs.append({
                    'indicator': indicator,
                    'loser_avg': loser_avg,
                    'winner_avg': winner_avg,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    if significant_diffs:
        print()
        print("⚠️  Significant differences (>20%):")
        print()

        for item in sorted(significant_diffs, key=lambda x: abs(x['diff_pct']), reverse=True):
            print(f"   {item['indicator']}:")
            print(f"      Losers: {item['loser_avg']:.2f}")
            print(f"      Winners: {item['winner_avg']:.2f}")
            print(f"      Diff: {item['diff']:+.2f} ({item['diff_pct']:+.1f}%)")
            print()
    else:
        print("\n   No major differences found in entry conditions")

    # Recommendations
    print()
    print("=" * 100)
    print("4️⃣ RECOMMENDATIONS")
    print("-" * 100)
    print()

    # Analyze what criteria might be wrong
    recommendations = []

    # Check momentum
    if 'mom_30d' in losers_df.columns and 'mom_30d' in winners_df.columns:
        loser_mom = losers_df['mom_30d'].mean()
        winner_mom = winners_df['mom_30d'].mean()

        if winner_mom > loser_mom + 5:
            recommendations.append(
                f"✅ Increase momentum requirement: Winners had {winner_mom:.1f}% 30d momentum vs Losers {loser_mom:.1f}%"
            )

    # Check RSI
    if 'rsi' in losers_df.columns and 'rsi' in winners_df.columns:
        loser_rsi = losers_df['rsi'].mean()
        winner_rsi = winners_df['rsi'].mean()

        if abs(winner_rsi - loser_rsi) > 5:
            if winner_rsi > loser_rsi:
                recommendations.append(
                    f"✅ Prefer higher RSI: Winners had RSI {winner_rsi:.1f} vs Losers {loser_rsi:.1f}"
                )
            else:
                recommendations.append(
                    f"✅ Avoid overbought: Winners had RSI {winner_rsi:.1f} vs Losers {loser_rsi:.1f}"
                )

    # Check trend
    if 'ma20_vs_ma50' in losers_df.columns and 'ma20_vs_ma50' in winners_df.columns:
        loser_trend = losers_df['ma20_vs_ma50'].mean()
        winner_trend = winners_df['ma20_vs_ma50'].mean()

        if winner_trend > loser_trend + 2:
            recommendations.append(
                f"✅ Require stronger trend: Winners had MA20 vs MA50 {winner_trend:+.1f}% vs Losers {loser_trend:+.1f}%"
            )

    # Check position from 52w high
    if 'pct_from_52w_high' in losers_df.columns and 'pct_from_52w_high' in winners_df.columns:
        loser_pos = losers_df['pct_from_52w_high'].mean()
        winner_pos = winners_df['pct_from_52w_high'].mean()

        if winner_pos > loser_pos + 5:
            recommendations.append(
                f"✅ Prefer stocks closer to 52w high: Winners {winner_pos:.1f}% vs Losers {loser_pos:.1f}%"
            )

    # Check volatility
    if 'atr_pct' in losers_df.columns and 'atr_pct' in winners_df.columns:
        loser_vol = losers_df['atr_pct'].mean()
        winner_vol = winners_df['atr_pct'].mean()

        if abs(winner_vol - loser_vol) > 1:
            if winner_vol > loser_vol:
                recommendations.append(
                    f"⚠️  Winners were MORE volatile: {winner_vol:.2f}% vs {loser_vol:.2f}%"
                )
            else:
                recommendations.append(
                    f"⚠️  Winners were LESS volatile: {winner_vol:.2f}% vs {loser_vol:.2f}%"
                )

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
    else:
        print("   No clear patterns found - may need more data")

    print()
    print("=" * 100)
    print("5️⃣ PROPOSED FILTER IMPROVEMENTS")
    print("-" * 100)
    print()

    print("Based on analysis, consider:")
    print()

    # Create specific threshold recommendations
    if not losers_df.empty and not winners_df.empty:

        # Momentum threshold
        winner_mom_30d = winners_df['mom_30d'].mean()
        loser_mom_30d = losers_df['mom_30d'].mean()

        if winner_mom_30d > loser_mom_30d:
            suggested_mom_threshold = (winner_mom_30d + loser_mom_30d) / 2
            print(f"1. Momentum Filter (30d):")
            print(f"   Current: Possibly too lenient")
            print(f"   Winners avg: {winner_mom_30d:+.1f}%")
            print(f"   Losers avg: {loser_mom_30d:+.1f}%")
            print(f"   Suggested: Require 30d momentum > {suggested_mom_threshold:+.1f}%")
            print()

        # RSI threshold
        winner_rsi = winners_df['rsi'].mean()
        loser_rsi = losers_df['rsi'].mean()

        if abs(winner_rsi - loser_rsi) > 3:
            print(f"2. RSI Filter:")
            print(f"   Winners avg: {winner_rsi:.1f}")
            print(f"   Losers avg: {loser_rsi:.1f}")
            if winner_rsi > loser_rsi:
                print(f"   Suggested: Prefer RSI > {(winner_rsi + loser_rsi) / 2:.0f}")
            else:
                print(f"   Suggested: Avoid overbought RSI > {(winner_rsi + loser_rsi) / 2:.0f}")
            print()

        # Trend filter
        winner_trend = winners_df['ma20_vs_ma50'].mean()
        loser_trend = losers_df['ma20_vs_ma50'].mean()

        if winner_trend > loser_trend:
            print(f"3. Trend Strength:")
            print(f"   Winners: MA20 vs MA50 {winner_trend:+.1f}%")
            print(f"   Losers: MA20 vs MA50 {loser_trend:+.1f}%")
            print(f"   Suggested: Require MA20 > MA50 by at least {(winner_trend + loser_trend) / 2:+.1f}%")
            print()

    print()
    print("=" * 100)
    print("📊 SUMMARY")
    print("=" * 100)
    print()

    if not losers_df.empty:
        print(f"❌ Screener selected {len(losers_df)} losers: avg return {losers_df['actual_return'].mean():+.2f}%")

    if not winners_df.empty:
        print(f"✅ Screener missed {len(winners_df)} winners: avg return {winners_df['actual_return'].mean():+.2f}%")

    print()
    print("🎯 Next steps:")
    print("   1. Review recommendations above")
    print("   2. Adjust screening criteria")
    print("   3. Backtest with new criteria")
    print("   4. Iterate until performance improves")

    print()
    print("=" * 100)

    # Save results
    output_file = 'screener_diagnosis_results.csv'

    all_results = []

    for _, row in losers_df.iterrows():
        row_dict = row.to_dict()
        row_dict['category'] = 'loser_selected'
        all_results.append(row_dict)

    for _, row in winners_df.iterrows():
        row_dict = row.to_dict()
        row_dict['category'] = 'winner_missed'
        all_results.append(row_dict)

    for _, row in other_df.iterrows():
        row_dict = row.to_dict()
        if row['actual_return'] > 0:
            row_dict['category'] = 'other_winner'
        else:
            row_dict['category'] = 'other_loser'
        all_results.append(row_dict)

    if all_results:
        results_df = pd.DataFrame(all_results)
        results_df.to_csv(output_file, index=False)
        print(f"\n💾 Results saved to: {output_file}")

    print()


if __name__ == "__main__":
    main()
