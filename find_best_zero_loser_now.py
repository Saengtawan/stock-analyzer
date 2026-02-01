#!/usr/bin/env python3
"""
Find BEST zero loser config with current data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

TEST_MONTHS = 6
MIN_TRADES = 5


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
    up_vol = 0.0
    down_vol = 0.0
    for i in range(-period+1, 0):
        if closes[i] > closes[i-1]:
            up_vol += volumes[i]
        elif closes[i] < closes[i-1]:
            down_vol += volumes[i]
    if down_vol == 0:
        return 3.0
    return up_vol / down_vol


def get_universe():
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'AMD', 'INTC', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC', 'MRVL',
        'CRM', 'ADBE', 'ORCL', 'NOW', 'INTU', 'WDAY', 'SNOW', 'DDOG', 'NET', 'ZS',
        'PANW', 'CRWD', 'FTNT', 'OKTA',
        'CSCO', 'ANET',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK', 'SCHW',
        'V', 'MA', 'PYPL', 'SQ',
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'ISRG', 'MDT',
        'HD', 'LOW', 'COST', 'WMT', 'TGT', 'MCD', 'SBUX', 'NKE', 'DIS',
        'CAT', 'DE', 'HON', 'UNP', 'UPS', 'GE', 'MMM', 'BA', 'RTX', 'LMT',
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY',
        'T', 'VZ', 'TMUS', 'CMCSA',
        'GM', 'F', 'RIVN', 'LCID',
        'NFLX', 'ROKU', 'SPOT',
        'SHOP', 'UBER', 'LYFT', 'ABNB', 'BKNG',
        'SQ', 'COIN', 'RBLX', 'PLTR', 'U',
    ]


def download_data(symbols, start_date, end_date):
    stock_data = {}
    def download(sym):
        try:
            df = yf.download(sym, start=start_date, end=end_date, progress=False)
            if df.empty or len(df) < 80:
                return None, sym
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            result = pd.DataFrame({
                'date': df.index,
                'close': df['Close'].values.flatten().astype(float),
                'volume': df['Volume'].values.flatten().astype(float),
            })
            result = result.set_index('date')
            daily_returns = result['close'].pct_change().abs()
            if daily_returns.max() > 0.20:
                return None, sym
            return result, sym
        except:
            return None, sym

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(download, sym) for sym in symbols]
        for future in as_completed(futures):
            df, sym = future.result()
            if df is not None:
                stock_data[sym] = df
    return stock_data


def generate_signals(stock_data, hold_days):
    signals = []
    for symbol, df in stock_data.items():
        closes = df['close'].values
        volumes = df['volume'].values
        dates = df.index
        if len(closes) < 60 + hold_days:
            continue
        for i in range(55, len(closes) - hold_days):
            price = closes[i]
            ma20 = np.mean(closes[i-19:i+1])
            ma50 = np.mean(closes[i-49:i+1])
            above_ma20 = ((price - ma20) / ma20) * 100
            above_ma50 = ((price - ma50) / ma50) * 100
            rsi = calculate_rsi(closes[i-29:i+1], period=14)
            accum = calculate_accumulation(closes[:i+1], volumes[:i+1], period=20)
            exit_price = closes[i + hold_days]
            pct_return = ((exit_price - price) / price) * 100
            signals.append({
                'symbol': symbol,
                'entry_date': dates[i],
                'return_pct': pct_return,
                'rsi': rsi,
                'accum': accum,
                'above_ma20': above_ma20,
                'above_ma50': above_ma50,
            })
    return pd.DataFrame(signals)


def grid_search(df, hold_days):
    """Find all zero loser configs"""
    configs = []

    for accum in np.arange(1.0, 2.5, 0.1):
        for rsi in [40, 42, 45, 48, 50, 52, 55, 57, 60]:
            for ma20 in [-5, -3, -2, -1, 0, 1, 2, 3, 4, 5]:
                for ma50 in [-5, 0, 2, 4, 6, 8, 10]:
                    filtered = df[
                        (df['accum'] > accum) &
                        (df['rsi'] < rsi) &
                        (df['above_ma20'] > ma20) &
                        (df['above_ma50'] > ma50)
                    ]
                    n = len(filtered)
                    if n < MIN_TRADES:
                        continue
                    n_losers = len(filtered[filtered['return_pct'] < 0])
                    if n_losers == 0:
                        avg_ret = filtered['return_pct'].mean()
                        configs.append({
                            'accum': round(accum, 1),
                            'rsi': rsi,
                            'ma20': ma20,
                            'ma50': ma50,
                            'trades': n,
                            'avg_return': avg_ret,
                            'hold_days': hold_days
                        })
    return configs


def main():
    print("=" * 70)
    print("FINDING BEST ZERO LOSER CONFIG WITH CURRENT DATA")
    print("=" * 70)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=TEST_MONTHS * 30 + 70)

    symbols = get_universe()
    print(f"Universe: {len(symbols)} stocks")

    stock_data = download_data(symbols, start_date, end_date)
    print(f"Downloaded: {len(stock_data)} stocks")

    all_configs = []

    for hold_days in [5, 7, 10, 14, 21, 30]:
        print(f"\n--- Testing {hold_days}-day hold ---")
        df = generate_signals(stock_data, hold_days)
        print(f"  Raw: {len(df)} signals")

        df['week'] = df['entry_date'].dt.isocalendar().week
        df['year'] = df['entry_date'].dt.year
        df = df.drop_duplicates(subset=['symbol', 'year', 'week'])
        print(f"  Dedup: {len(df)} signals")

        configs = grid_search(df, hold_days)
        print(f"  Found: {len(configs)} zero loser configs")
        all_configs.extend(configs)

    if all_configs:
        df_results = pd.DataFrame(all_configs)
        df_results = df_results.sort_values(['trades', 'avg_return'], ascending=[False, False])

        print("\n" + "=" * 70)
        print("TOP ZERO LOSER CONFIGURATIONS")
        print("=" * 70)
        print(df_results.head(30).to_string(index=False))

        # Best config
        best = df_results.iloc[0]
        print(f"\n🏆 BEST ZERO LOSER CONFIG:")
        print(f"   Hold:     {best['hold_days']} days")
        print(f"   Accum:    > {best['accum']}")
        print(f"   RSI:      < {best['rsi']}")
        print(f"   MA20:     > {best['ma20']}%")
        print(f"   MA50:     > {best['ma50']}%")
        print(f"   Trades:   {best['trades']}")
        print(f"   Avg Ret:  {best['avg_return']:.2f}%")

        # Save
        df_results.to_csv('best_zero_loser_current.csv', index=False)
        print(f"\n💾 Saved to: best_zero_loser_current.csv")

        # Return best config for implementation
        return {
            'hold_days': int(best['hold_days']),
            'accum_min': float(best['accum']),
            'rsi_max': int(best['rsi']),
            'ma20_min': float(best['ma20']),
            'ma50_min': float(best['ma50']),
            'trades': int(best['trades']),
            'avg_return': float(best['avg_return'])
        }
    else:
        print("\n❌ No zero loser configs found")
        return None


if __name__ == '__main__':
    best = main()
    if best:
        print("\n" + "=" * 70)
        print("IMPLEMENTATION RECOMMENDATION")
        print("=" * 70)
        print(f"""
def _passes_momentum_gates(metrics):
    # {best['hold_days']}-DAY ZERO LOSER CONFIG
    # Tested: {best['trades']} trades, 0 losers, {best['avg_return']:.2f}% avg return

    accum = metrics.get('accumulation', 0)
    if accum <= {best['accum_min']}:
        return False, f"Accumulation {{accum:.2f}} <= {best['accum_min']}"

    rsi = metrics.get('rsi', 50)
    if rsi >= {best['rsi_max']}:
        return False, f"RSI {{rsi:.0f}} >= {best['rsi_max']}"

    ma20 = metrics.get('price_above_ma20', 0)
    if ma20 <= {best['ma20_min']}:
        return False, f"MA20 {{ma20:.1f}}% <= {best['ma20_min']}%"

    ma50 = metrics.get('price_above_ma50', 0)
    if ma50 <= {best['ma50_min']}:
        return False, f"MA50 {{ma50:.1f}}% <= {best['ma50_min']}%"

    return True, ""
""")
