"""
Pull missing macro data from yfinance for swing v2.1 enhancement.

Targets:
  Sector ETFs:  XLF, XLE, XLK, XLV, XLU, XLI, XLY, XLP, XLB, XLRE, XLC
  Other:        IWM (small cap), USO (oil), MOVE (bond vol)
  Already have: QQQ, SMH, EEM in stock_daily_ohlc

Save to: backtests/cache_swing/extended_macro.pkl
"""
import yfinance as yf
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')

TICKERS = {
    # Sectors
    'XLF': 'Financials',
    'XLE': 'Energy',
    'XLK': 'Technology',
    'XLV': 'Healthcare',
    'XLU': 'Utilities',
    'XLI': 'Industrials',
    'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples',
    'XLB': 'Materials',
    'XLRE': 'Real Estate',
    'XLC': 'Communication',
    # Broader market
    'IWM': 'Small Cap',
    # Commodities
    'USO': 'Oil ETF',
    'GLD': 'Gold ETF',
    # Bond vol proxy (MOVE not in yfinance, use ^MOVE)
    '^MOVE': 'Bond Volatility',
    # Volatility ratio
    '^VIX': 'VIX (re-verify)',
}

START = '2020-01-01'
END = datetime.now().strftime('%Y-%m-%d')


def main():
    print(f"== Pull Extended Macro Data ({START} to {END}) ==", flush=True)

    all_data = {}
    for ticker, name in TICKERS.items():
        try:
            df = yf.Ticker(ticker).history(start=START, end=END, auto_adjust=True)
            if len(df) == 0:
                print(f"  {ticker:6s} {name:25s} NO DATA", flush=True)
                continue
            df.index = df.index.tz_localize(None)  # strip timezone
            df['date'] = df.index.normalize()
            df = df.reset_index(drop=True)[['date', 'Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            df['symbol'] = ticker
            all_data[ticker] = df
            print(f"  {ticker:6s} {name:25s} {len(df)} rows ({df['date'].min().date()} to {df['date'].max().date()})", flush=True)
        except Exception as e:
            print(f"  {ticker:6s} ERROR: {e}", flush=True)

    if not all_data:
        print("No data pulled!")
        return

    combined = pd.concat(all_data.values(), ignore_index=True)
    out_path = CACHE / 'extended_macro.pkl'
    combined.to_pickle(out_path)
    print(f"\n✅ Saved to {out_path} ({len(combined):,} rows)", flush=True)

    # Quick sanity check — does data match for overlapping dates?
    print("\n== Sanity check: cross-verify with macro_snapshots ==", flush=True)
    con = sqlite3.connect(str(DB))
    macro = pd.read_sql("SELECT date, vix_close FROM macro_snapshots WHERE date >= '2025-01-01' AND date <= '2025-12-31'", con)
    con.close()
    macro['date'] = pd.to_datetime(macro['date'])

    vix_yf = combined[combined['symbol'] == '^VIX'][['date', 'close']]
    merged = macro.merge(vix_yf, on='date', how='inner')
    if len(merged) > 0:
        diff = (merged['close'] - merged['vix_close']).abs().mean()
        print(f"  VIX yfinance vs macro_snapshots: {len(merged)} overlap days, avg diff {diff:.3f}", flush=True)


if __name__ == '__main__':
    main()
