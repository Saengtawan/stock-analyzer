"""Reseed stock_track_record with the LIVE-FAITHFUL riser label:
entry = close of 09:35 bar (=09:40 price, live 'buy at display'),
exit  = close of 15:55 bar (regular EOD, live eod_flatten).
This is the convention identity is significant on (p=0.010); pnl_EOD (exit ~16:10) was wrong."""
import sqlite3, sys, argparse
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.scan import stock_track_record as STR

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pkl', default=str(ROOT/'cache/bt_features/features_5yr_noleak.pkl')); _a = ap.parse_args()
    f = pd.read_pickle(_a.pkl)
    f = f.loc[:, ~f.columns.duplicated()]
    z = f[(f.mins_from_open == 5) & (f.gain_from_open > 0.5) & (f.date >= '2023-01-01')]
    keys = set(zip(z.sym, z.date))
    th = sqlite3.connect(str(ROOT / 'data/trade_history.db'))
    ent, ex = {}, {}
    for s, d, t, c in th.execute(
        "SELECT symbol,date,time_et,close FROM intraday_bars_5m "
        "WHERE time_et IN ('09:35','15:55') AND date>='2023-01-01'").fetchall():
        if (s, d) in keys:
            (ent if t == '09:35' else ex)[(s, d)] = c
    th.close()
    c = STR._conn(); c.execute("DELETE FROM stock_outcomes"); c.commit()
    rows = [(s, d, (ex[(s, d)] / ent[(s, d)] - 1) * 100, 'backtest_correct')
            for (s, d) in keys
            if (s, d) in ent and (s, d) in ex and ent[(s, d)] > 0]
    c.executemany("INSERT OR REPLACE INTO stock_outcomes VALUES (?,?,?,?)", rows)
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM stock_outcomes").fetchone()[0]
    sy = c.execute("SELECT COUNT(DISTINCT symbol) FROM stock_outcomes").fetchone()[0]
    c.close()
    print(f"reseeded {n} outcomes / {sy} symbols (correct label: entry 09:40 / exit 15:55)")

if __name__ == '__main__':
    main()
