"""
Backfill 3 critical ETFs for ETF rotation strategy:
  BIL — cash proxy (no equivalent in universe)
  DBC — broad commodities (vs USO oil-only)
  AGG — total bond market (vs TLT/IEF specific)

Save to extended_macro.pkl (append).
"""
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')

NEW_TICKERS = {
    'BIL': 'Cash Proxy (1-3M T-Bills)',
    'DBC': 'Broad Commodities',
    'AGG': 'Total Bond Market',
}

START = '2020-01-01'
END = datetime.now().strftime('%Y-%m-%d')


def main():
    print(f"== Backfill 3 critical ETFs ({START} to {END}) ==", flush=True)

    new_data = []
    for ticker, name in NEW_TICKERS.items():
        try:
            df = yf.Ticker(ticker).history(start=START, end=END, auto_adjust=True)
            if len(df) == 0:
                print(f"  {ticker:6s} {name:25s} NO DATA", flush=True)
                continue
            df.index = df.index.tz_localize(None)
            df['date'] = df.index.normalize()
            df = df.reset_index(drop=True)[['date', 'Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            df['symbol'] = ticker
            new_data.append(df)
            print(f"  {ticker:6s} {name:25s} {len(df)} rows ({df['date'].min().date()} → {df['date'].max().date()})", flush=True)
        except Exception as e:
            print(f"  {ticker:6s} ERROR: {e}", flush=True)

    if not new_data:
        print("Nothing pulled!")
        return

    # Load existing + merge
    existing = pd.read_pickle(CACHE / 'extended_macro.pkl')
    print(f"\nExisting symbols: {sorted(existing['symbol'].unique())}", flush=True)
    print(f"Existing rows: {len(existing):,}", flush=True)

    new_combined = pd.concat(new_data, ignore_index=True)
    merged = pd.concat([existing, new_combined], ignore_index=True)
    merged = merged.drop_duplicates(subset=['symbol', 'date']).sort_values(['symbol', 'date']).reset_index(drop=True)

    print(f"\nMerged symbols: {sorted(merged['symbol'].unique())}", flush=True)
    print(f"Merged rows: {len(merged):,}", flush=True)
    print(f"New ETFs added: {sorted(NEW_TICKERS.keys())}", flush=True)

    # Save
    merged.to_pickle(CACHE / 'extended_macro.pkl')
    print(f"\n✅ Saved → {CACHE / 'extended_macro.pkl'}", flush=True)

    # Verify
    df_check = pd.read_pickle(CACHE / 'extended_macro.pkl')
    for t in NEW_TICKERS:
        sub = df_check[df_check['symbol'] == t]
        if len(sub) > 0:
            print(f"  ✅ {t}: {len(sub)} rows verified", flush=True)
        else:
            print(f"  ❌ {t}: missing!", flush=True)


if __name__ == '__main__':
    main()
