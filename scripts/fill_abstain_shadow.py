"""fill_abstain_shadow.py — fill eod_ret for abstain-day would-be picks (validate SPX-GEX gate).
EOD outcome: entry = recorded 09:36 entry_price, exit = 15:55 close from intraday_bars_5m.
Run after close. Idempotent. No args = fill all rows missing eod_ret."""
import sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sh=sqlite3.connect(str(ROOT/'data/riser_abstain_shadow.db'))
th=sqlite3.connect(str(ROOT/'data/trade_history.db'))
rows=sh.execute("SELECT date,sym,entry_price FROM abstain_shadow WHERE eod_ret IS NULL").fetchall()
n=0
for date,sym,ep in rows:
    r=th.execute("SELECT close FROM intraday_bars_5m WHERE symbol=? AND date=? AND time_et='15:55'",(sym,date)).fetchone()
    if r and r[0] and ep:
        ret=(r[0]/ep-1)*100
        sh.execute("UPDATE abstain_shadow SET eod_ret=? WHERE date=? AND sym=?",(ret,date,sym)); n+=1
        print(f"{date} {sym}: entry {ep} -> 15:55 {r[0]} = {ret:+.2f}%")
sh.commit()
print(f"filled {n} | gate-correct (would-be picks RED) validates abstain")
sh.close(); th.close()
