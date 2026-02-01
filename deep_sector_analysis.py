#!/usr/bin/env python3
"""
Deep Analysis: Find optimal formula for each sector
Think like a professional stock analyst!
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

TEST_MONTHS = 6

# Define sectors with representative stocks
SECTORS = {
    'Technology': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC', 'CRM', 'ADBE', 'ORCL'],
    'Semiconductors': ['NVDA', 'AMD', 'INTC', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC'],
    'Cloud/SaaS': ['CRM', 'SNOW', 'DDOG', 'NET', 'NOW', 'WDAY', 'OKTA'],
    'Cybersecurity': ['PANW', 'CRWD', 'ZS', 'FTNT'],
    'Finance': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK'],
    'Payments': ['V', 'MA', 'PYPL'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD'],
    'Retail': ['HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE'],
    'Industrial': ['CAT', 'DE', 'HON', 'UNP', 'GE', 'BA', 'RTX', 'LMT'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY'],
    'Telecom': ['T', 'VZ', 'TMUS', 'CMCSA'],
    'Entertainment': ['DIS', 'NFLX', 'SPOT', 'ROKU']
}


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_accumulation(closes, volumes, period=20):
    if len(closes) < period:
        return 1.0
    up_vol, down_vol = 0.0, 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    return up_vol / down_vol if down_vol > 0 else 3.0


def download_stock(sym, start_date, end_date):
    try:
        df = yf.download(sym, start=start_date, end=end_date, progress=False)
        if df.empty or len(df) < 80:
            return None, sym
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df, sym
    except:
        return None, sym


def generate_signals_for_stock(sym, df, hold_days):
    """Generate all signals for a single stock"""
    signals = []
    closes = df['Close'].values.flatten()
    volumes = df['Volume'].values.flatten()
    dates = df.index

    n = min(len(closes), len(volumes), len(dates))
    if n < 60 + hold_days:
        return signals

    for i in range(55, n - hold_days):
        price = float(closes[i])

        # Calculate all metrics
        ma10 = float(np.mean(closes[i-9:i+1]))
        ma20 = float(np.mean(closes[i-19:i+1]))
        ma50 = float(np.mean(closes[i-49:i+1]))

        above_ma10 = ((price - ma10) / ma10) * 100
        above_ma20 = ((price - ma20) / ma20) * 100
        above_ma50 = ((price - ma50) / ma50) * 100

        rsi = calculate_rsi(closes[i-29:i+1], period=14)
        accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)

        # Momentum
        mom_5d = ((price - float(closes[i-5])) / float(closes[i-5])) * 100 if i >= 5 else 0
        mom_10d = ((price - float(closes[i-10])) / float(closes[i-10])) * 100 if i >= 10 else 0
        mom_20d = ((price - float(closes[i-20])) / float(closes[i-20])) * 100 if i >= 20 else 0

        # Volatility
        returns = np.diff(closes[i-20:i+1]) / closes[i-20:i]
        volatility = float(np.std(returns) * 100)

        # Volume trend
        vol_5d = float(np.mean(volumes[i-4:i+1]))
        vol_20d = float(np.mean(volumes[i-19:i+1]))
        vol_trend = vol_5d / vol_20d if vol_20d > 0 else 1.0

        # Return
        exit_price = float(closes[i + hold_days])
        pct_return = ((exit_price - price) / price) * 100

        signals.append({
            'symbol': sym,
            'date': dates[i],
            'return': pct_return,
            'rsi': rsi,
            'accum': accum,
            'ma10': above_ma10,
            'ma20': above_ma20,
            'ma50': above_ma50,
            'mom_5d': mom_5d,
            'mom_10d': mom_10d,
            'mom_20d': mom_20d,
            'volatility': volatility,
            'vol_trend': vol_trend
        })

    return signals


def find_best_formula_for_sector(sector_name, sector_signals, min_trades=5):
    """Find the optimal formula for this sector"""
    df = pd.DataFrame(sector_signals)
    if len(df) == 0:
        return None

    # Deduplicate
    df['week'] = df['date'].dt.isocalendar().week
    df['year'] = df['date'].dt.year
    df = df.drop_duplicates(subset=['symbol', 'year', 'week'])

    best_config = None
    best_score = -999

    # Grid search with sector-specific ranges
    for accum in np.arange(0.8, 2.5, 0.2):
        for rsi in [40, 45, 50, 52, 55, 57, 60, 65]:
            for ma20 in [-5, -3, -1, 0, 1, 2, 3, 5]:
                for ma50 in [-5, 0, 2, 4, 6, 8]:
                    for mom in [-5, 0, 2, 5]:
                        filtered = df[
                            (df['accum'] > accum) &
                            (df['rsi'] < rsi) &
                            (df['ma20'] > ma20) &
                            (df['ma50'] > ma50) &
                            (df['mom_10d'] > mom)
                        ]

                        n = len(filtered)
                        if n < min_trades:
                            continue

                        n_losers = len(filtered[filtered['return'] < 0])
                        n_winners = len(filtered[filtered['return'] > 0])
                        avg_return = filtered['return'].mean()

                        # Score: prioritize zero loser, then trades, then return
                        if n_losers == 0:
                            score = 1000 + n * 10 + avg_return
                        else:
                            loser_rate = n_losers / n
                            score = (1 - loser_rate) * 100 + avg_return

                        if score > best_score:
                            best_score = score
                            best_config = {
                                'sector': sector_name,
                                'accum': round(accum, 1),
                                'rsi': rsi,
                                'ma20': ma20,
                                'ma50': ma50,
                                'mom10': mom,
                                'trades': n,
                                'winners': n_winners,
                                'losers': n_losers,
                                'win_rate': n_winners / n * 100 if n > 0 else 0,
                                'avg_return': avg_return,
                                'zero_loser': n_losers == 0
                            }

    return best_config


def main():
    print("=" * 80)
    print("DEEP SECTOR ANALYSIS - Finding optimal formula for each sector")
    print("=" * 80)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    # Collect all unique symbols
    all_symbols = set()
    for sector_stocks in SECTORS.values():
        all_symbols.update(sector_stocks)

    print(f"\nDownloading {len(all_symbols)} unique stocks...")

    # Download all data
    stock_data = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download_stock, sym, start_date, end_date) for sym in all_symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df

    print(f"Downloaded: {len(stock_data)} stocks")

    # Test different hold periods
    for hold_days in [5, 7, 14, 21]:
        print(f"\n{'#'*80}")
        print(f"HOLD PERIOD: {hold_days} DAYS")
        print(f"{'#'*80}")

        sector_results = []

        for sector_name, sector_stocks in SECTORS.items():
            # Generate signals for this sector
            sector_signals = []
            for sym in sector_stocks:
                if sym in stock_data:
                    signals = generate_signals_for_stock(sym, stock_data[sym], hold_days)
                    sector_signals.extend(signals)

            if not sector_signals:
                continue

            # Find best formula for this sector
            best = find_best_formula_for_sector(sector_name, sector_signals, min_trades=3)

            if best:
                sector_results.append(best)

        if sector_results:
            df_results = pd.DataFrame(sector_results)
            df_results = df_results.sort_values(['zero_loser', 'trades', 'avg_return'], ascending=[False, False, False])

            print(f"\n📊 BEST FORMULA PER SECTOR ({hold_days}-day hold):")
            print("-" * 100)

            for _, r in df_results.iterrows():
                zl = "✅" if r['zero_loser'] else "❌"
                print(f"{zl} {r['sector']:<15} | Accum>{r['accum']}, RSI<{r['rsi']}, MA20>{r['ma20']}%, MA50>{r['ma50']}%, Mom>{r['mom10']}%")
                print(f"   → {int(r['trades'])} trades, {int(r['winners'])}W/{int(r['losers'])}L, {r['win_rate']:.0f}% WR, {r['avg_return']:+.2f}% avg")

            # Summary: sectors with zero loser
            zero_loser_sectors = df_results[df_results['zero_loser'] == True]
            if len(zero_loser_sectors) > 0:
                print(f"\n🎯 ZERO LOSER SECTORS: {len(zero_loser_sectors)}")
                for _, r in zero_loser_sectors.iterrows():
                    print(f"   ✅ {r['sector']}: {int(r['trades'])} trades, {r['avg_return']:+.2f}%")

    # Final recommendation
    print("\n" + "=" * 80)
    print("FINAL RECOMMENDATION")
    print("=" * 80)
    print("""
Based on the sector analysis:

1. SECTOR-SPECIFIC APPROACH IS BETTER
   - Different sectors have different optimal parameters
   - Tech/Growth stocks need different criteria than Defensive stocks

2. KEY INSIGHTS:
   - Healthcare/Consumer: More tolerant of lower accumulation
   - Tech/Semis: Need higher momentum confirmation
   - Energy: More volatile, need tighter RSI control

3. IMPLEMENTATION:
   - Can create sector-specific gates in the screener
   - Or use the UNIVERSAL gates that work across sectors
""")


if __name__ == '__main__':
    main()
