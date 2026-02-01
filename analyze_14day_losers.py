#!/usr/bin/env python3
"""
วิเคราะห์หุ้นที่แพ้ใน 14 วัน @ 5%
หาสาเหตุและวิธีแก้ไข
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 9 หุ้นที่ติดลบใน 14 วัน @ 5%
LOSERS_14D = ['UBER', 'DDOG', 'CRWD', 'SNOW', 'AMAT', 'GOOGL', 'AAPL', 'AMD', 'QCOM']

# 13 หุ้นที่ชนะใน 14 วัน @ 5%
WINNERS_14D = ['ROKU', 'LRCX', 'ABNB', 'TSLA', 'PLTR', 'SHOP', 'NET', 'TSM', 'AVGO', 'DASH', 'META', 'COIN', 'KLAC']

# 4 หุ้นที่ไม่ถึง target แต่ยังกำไร
MISS_POSITIVE = ['NVDA', 'AMZN', 'TEAM', 'MSFT']


def analyze_stock_characteristics(symbol, label):
    """วิเคราะห์ลักษณะของหุ้น"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period='6mo')

        if hist.empty:
            return None

        # Get current data (14 days ago for backtest)
        entry_idx = -14
        current_price = hist['Close'].iloc[entry_idx]

        # Calculate metrics at entry point (14 days ago)
        recent_data = hist.iloc[:entry_idx]

        if len(recent_data) < 50:
            return None

        # 1. Momentum indicators
        close = recent_data['Close']

        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_entry = rsi.iloc[-1]

        # Moving averages
        ma20 = close.rolling(window=20).mean().iloc[-1]
        ma50 = close.rolling(window=50).mean().iloc[-1]

        # Distance from MA
        dist_from_ma20 = ((current_price - ma20) / ma20) * 100
        dist_from_ma50 = ((current_price - ma50) / ma50) * 100

        # 2. Volatility
        returns = close.pct_change().dropna()
        volatility_14d = returns.tail(14).std() * (252 ** 0.5) * 100
        volatility_30d = returns.tail(30).std() * (252 ** 0.5) * 100

        # 3. Recent momentum (7-day, 14-day)
        price_7d_ago = close.iloc[-7]
        price_14d_ago = close.iloc[-14] if len(close) >= 14 else close.iloc[0]

        momentum_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
        momentum_14d = ((current_price - price_14d_ago) / price_14d_ago) * 100

        # 4. Trend
        if current_price > ma20 > ma50:
            trend = 'STRONG_BULLISH'
        elif current_price > ma20:
            trend = 'BULLISH'
        elif current_price < ma20 < ma50:
            trend = 'BEARISH'
        else:
            trend = 'WEAK'

        # 5. Volume trend
        volume = recent_data['Volume']
        avg_volume_20d = volume.tail(20).mean()
        recent_volume_5d = volume.tail(5).mean()
        volume_ratio = recent_volume_5d / avg_volume_20d if avg_volume_20d > 0 else 1.0

        # 6. Support/Resistance
        high_52w = close.tail(252).max() if len(close) >= 252 else close.max()
        low_52w = close.tail(252).min() if len(close) >= 252 else close.min()

        dist_from_high = ((high_52w - current_price) / high_52w) * 100
        dist_from_low = ((current_price - low_52w) / low_52w) * 100

        # 7. Beta
        beta = info.get('beta', 1.0)

        # 8. Relative Strength vs SPY
        spy = yf.Ticker('SPY')
        spy_hist = spy.history(period='1mo')

        if not spy_hist.empty and len(spy_hist) >= 20:
            stock_return_14d = momentum_14d
            spy_return_14d = ((spy_hist['Close'].iloc[-14] / spy_hist['Close'].iloc[-28]) - 1) * 100 if len(spy_hist) >= 28 else 0
            relative_strength = stock_return_14d - spy_return_14d
        else:
            relative_strength = 0

        return {
            'symbol': symbol,
            'label': label,
            'rsi': rsi_entry,
            'dist_from_ma20': dist_from_ma20,
            'dist_from_ma50': dist_from_ma50,
            'volatility_14d': volatility_14d,
            'volatility_30d': volatility_30d,
            'momentum_7d': momentum_7d,
            'momentum_14d': momentum_14d,
            'trend': trend,
            'volume_ratio': volume_ratio,
            'dist_from_high': dist_from_high,
            'dist_from_low': dist_from_low,
            'beta': beta,
            'relative_strength': relative_strength,
            'current_price': current_price,
            'ma20': ma20,
            'ma50': ma50
        }

    except Exception as e:
        print(f"  ⚠️  {symbol}: {e}")
        return None


def main():
    print("=" * 100)
    print("🔍 วิเคราะห์หุ้นที่แพ้ vs ชนะ ใน 14 วัน @ 5%")
    print("=" * 100)

    # Analyze all stocks
    print("\n📊 กำลังวิเคราะห์...")

    losers_data = []
    winners_data = []
    miss_data = []

    for symbol in LOSERS_14D:
        data = analyze_stock_characteristics(symbol, 'LOSER')
        if data:
            losers_data.append(data)

    for symbol in WINNERS_14D:
        data = analyze_stock_characteristics(symbol, 'WINNER')
        if data:
            winners_data.append(data)

    for symbol in MISS_POSITIVE:
        data = analyze_stock_characteristics(symbol, 'MISS')
        if data:
            miss_data.append(data)

    # Convert to DataFrames
    df_losers = pd.DataFrame(losers_data)
    df_winners = pd.DataFrame(winners_data)
    df_miss = pd.DataFrame(miss_data)

    print(f"✅ วิเคราะห์เสร็จ: {len(losers_data)} LOSERS, {len(winners_data)} WINNERS, {len(miss_data)} MISS")

    # Compare averages
    print("\n" + "=" * 100)
    print("📈 เปรียบเทียบค่าเฉลี่ย: LOSERS vs WINNERS")
    print("=" * 100)

    metrics = [
        'rsi', 'dist_from_ma20', 'dist_from_ma50',
        'volatility_14d', 'volatility_30d',
        'momentum_7d', 'momentum_14d',
        'volume_ratio', 'dist_from_high', 'dist_from_low',
        'beta', 'relative_strength'
    ]

    comparison = []

    print(f"\n{'Metric':<25} | {'LOSERS':>12} | {'WINNERS':>12} | {'MISS':>12} | {'Difference':>12}")
    print("-" * 100)

    for metric in metrics:
        loser_avg = df_losers[metric].mean()
        winner_avg = df_winners[metric].mean()
        miss_avg = df_miss[metric].mean() if len(df_miss) > 0 else 0
        diff = winner_avg - loser_avg

        comparison.append({
            'metric': metric,
            'loser_avg': loser_avg,
            'winner_avg': winner_avg,
            'miss_avg': miss_avg,
            'difference': diff
        })

        print(f"{metric:<25} | {loser_avg:>12.2f} | {winner_avg:>12.2f} | {miss_avg:>12.2f} | {diff:>+12.2f}")

    # Identify key differences
    print("\n" + "=" * 100)
    print("🎯 ความแตกต่างที่สำคัญ (Difference > 5)")
    print("=" * 100)

    significant_diffs = sorted(comparison, key=lambda x: abs(x['difference']), reverse=True)

    print("\n🔴 ลักษณะของหุ้นที่แพ้ (LOSERS):")
    for item in significant_diffs[:5]:
        if abs(item['difference']) > 5:
            direction = "สูงกว่า" if item['loser_avg'] > item['winner_avg'] else "ต่ำกว่า"
            print(f"  • {item['metric']}: {item['loser_avg']:.2f} ({direction} WINNERS {abs(item['difference']):.2f})")

    print("\n🟢 ลักษณะของหุ้นที่ชนะ (WINNERS):")
    for item in significant_diffs[:5]:
        if abs(item['difference']) > 5:
            direction = "สูงกว่า" if item['winner_avg'] > item['loser_avg'] else "ต่ำกว่า"
            print(f"  • {item['metric']}: {item['winner_avg']:.2f} ({direction} LOSERS {abs(item['difference']):.2f})")

    # Trend distribution
    print("\n" + "=" * 100)
    print("📊 การกระจายของ Trend")
    print("=" * 100)

    print("\n🔴 LOSERS Trend:")
    for trend in ['STRONG_BULLISH', 'BULLISH', 'BEARISH', 'WEAK']:
        count = len(df_losers[df_losers['trend'] == trend])
        pct = count / len(df_losers) * 100 if len(df_losers) > 0 else 0
        print(f"  {trend}: {count} ({pct:.1f}%)")

    print("\n🟢 WINNERS Trend:")
    for trend in ['STRONG_BULLISH', 'BULLISH', 'BEARISH', 'WEAK']:
        count = len(df_winners[df_winners['trend'] == trend])
        pct = count / len(df_winners) * 100 if len(df_winners) > 0 else 0
        print(f"  {trend}: {count} ({pct:.1f}%)")

    # Proposed filters
    print("\n" + "=" * 100)
    print("💡 แนะนำ Filters เพื่อหลีกเลี่ยง LOSERS")
    print("=" * 100)

    # Find thresholds
    proposals = []

    # RSI
    rsi_threshold = df_winners['rsi'].quantile(0.25)  # 25th percentile of winners
    print(f"\n1. ✅ RSI Filter:")
    print(f"   LOSERS avg: {df_losers['rsi'].mean():.1f}")
    print(f"   WINNERS avg: {df_winners['rsi'].mean():.1f}")
    print(f"   แนะนำ: RSI > {rsi_threshold:.1f}")

    # Momentum
    momentum_7d_threshold = df_winners['momentum_7d'].quantile(0.25)
    print(f"\n2. ✅ Momentum 7-day Filter:")
    print(f"   LOSERS avg: {df_losers['momentum_7d'].mean():.1f}%")
    print(f"   WINNERS avg: {df_winners['momentum_7d'].mean():.1f}%")
    print(f"   แนะนำ: Momentum 7d > {momentum_7d_threshold:.1f}%")

    # Relative Strength
    rs_threshold = df_winners['relative_strength'].quantile(0.25)
    print(f"\n3. ✅ Relative Strength Filter:")
    print(f"   LOSERS avg: {df_losers['relative_strength'].mean():.1f}%")
    print(f"   WINNERS avg: {df_winners['relative_strength'].mean():.1f}%")
    print(f"   แนะนำ: RS > {rs_threshold:.1f}%")

    # Distance from MA20
    ma20_threshold = df_winners['dist_from_ma20'].quantile(0.25)
    print(f"\n4. ✅ Distance from MA20 Filter:")
    print(f"   LOSERS avg: {df_losers['dist_from_ma20'].mean():.1f}%")
    print(f"   WINNERS avg: {df_winners['dist_from_ma20'].mean():.1f}%")
    print(f"   แนะนำ: Price > MA20 - {abs(ma20_threshold):.1f}%")

    # Volume ratio
    volume_threshold = df_winners['volume_ratio'].quantile(0.25)
    print(f"\n5. ✅ Volume Ratio Filter:")
    print(f"   LOSERS avg: {df_losers['volume_ratio'].mean():.2f}x")
    print(f"   WINNERS avg: {df_winners['volume_ratio'].mean():.2f}x")
    print(f"   แนะนำ: Volume Ratio > {volume_threshold:.2f}x")

    # Test filters
    print("\n" + "=" * 100)
    print("🧪 ทดสอบ Filters")
    print("=" * 100)

    # Apply filters to losers
    losers_filtered_out = 0
    winners_kept = 0

    for _, stock in df_losers.iterrows():
        if (stock['rsi'] < rsi_threshold or
            stock['momentum_7d'] < momentum_7d_threshold or
            stock['relative_strength'] < rs_threshold or
            stock['dist_from_ma20'] < ma20_threshold):
            losers_filtered_out += 1

    for _, stock in df_winners.iterrows():
        if (stock['rsi'] >= rsi_threshold and
            stock['momentum_7d'] >= momentum_7d_threshold and
            stock['relative_strength'] >= rs_threshold and
            stock['dist_from_ma20'] >= ma20_threshold):
            winners_kept += 1

    print(f"\n✅ ผลการทดสอบ:")
    print(f"  LOSERS ถูกกรองออก: {losers_filtered_out}/{len(df_losers)} ({losers_filtered_out/len(df_losers)*100:.1f}%)")
    print(f"  WINNERS ยังอยู่:     {winners_kept}/{len(df_winners)} ({winners_kept/len(df_winners)*100:.1f}%)")

    # Estimate new win rate
    new_total = winners_kept + (len(df_losers) - losers_filtered_out)
    new_win_rate = winners_kept / new_total * 100 if new_total > 0 else 0

    print(f"\n📈 ประมาณการ Win Rate หลังใช้ Filters:")
    print(f"  เดิม: 50.0% (13/26)")
    print(f"  ใหม่: {new_win_rate:.1f}% ({winners_kept}/{new_total})")
    print(f"  ปรับปรุง: +{new_win_rate - 50.0:.1f}%")

    print("\n" + "=" * 100)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
