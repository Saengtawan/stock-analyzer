#!/usr/bin/env python3
"""Backfill FINRA daily short-sale volume (RegSHO CNMS consolidated files).

FREE, authoritative, settlement-date-accurate, daily (no bi-weekly staleness).
Source: https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
Format: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market

Stores short_vol_ratio = ShortVolume/TotalVolume = the day's short-sale pressure.
This is FLOW (daily) — distinct from bi-monthly short INTEREST (outstanding %float),
but fresher + free + backfillable. Use for the squeeze-pressure hypothesis re-test.

Resumable: skips dates already loaded. 404 (holidays) skipped gracefully.
Usage: python scripts/backfill_short_volume.py [START_YYYY-MM-DD] [END_YYYY-MM-DD]
"""
import sqlite3, sys, time, random, urllib.request, urllib.error
from datetime import date, timedelta, datetime
from pathlib import Path

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

ROOT = Path(__file__).resolve().parents[1]
DB = str(ROOT / "data/trade_history.db")
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_short_volume (
  date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  short_volume INTEGER,
  short_exempt INTEGER,
  total_volume INTEGER,
  short_vol_ratio REAL,
  PRIMARY KEY (date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_dsv_sym_date ON daily_short_volume(symbol, date);
"""


def loaded_dates(con):
    return {r[0] for r in con.execute("SELECT DISTINCT date FROM daily_short_volume").fetchall()}


def fetch(ymd):
    """Return text, or None for a genuine 404 (holiday). Retries 403/429/5xx with backoff."""
    url = URL.format(ymd=ymd)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # holiday / no file
            wait = min(60, 5 * (2 ** attempt)) + random.uniform(0, 3)  # backoff on 403/429/5xx
            print(f"  {ymd}: HTTP {e.code}, backoff {wait:.0f}s (attempt {attempt+1})", flush=True)
            time.sleep(wait)
        except Exception as e:
            print(f"  {ymd}: {e}, retry", flush=True)
            time.sleep(5)
    return "FAIL"


def parse_rows(text, iso):
    out = []
    for ln in text.splitlines()[1:]:  # skip header
        p = ln.split("|")
        if len(p) < 5 or p[1] == "":
            continue
        try:
            sv, se, tv = int(p[2]), int(p[3] or 0), int(p[4])
        except ValueError:
            continue
        ratio = sv / tv if tv > 0 else None
        out.append((iso, p[1], sv, se, tv, ratio))
    return out


def main():
    start = datetime.strptime(sys.argv[1], "%Y-%m-%d").date() if len(sys.argv) > 1 else date(2024, 5, 1)
    end = datetime.strptime(sys.argv[2], "%Y-%m-%d").date() if len(sys.argv) > 2 else date.today()

    con = sqlite3.connect(DB, timeout=60)
    con.executescript(SCHEMA)
    con.commit()
    done = loaded_dates(con)
    print(f"backfill {start} -> {end} | already loaded {len(done)} dates", flush=True)

    d = start
    n_files = n_rows = n_skip = 0
    while d <= end:
        if d.weekday() >= 5:  # weekend
            d += timedelta(days=1); continue
        iso = d.isoformat()
        if iso in done:
            d += timedelta(days=1); continue
        ymd = d.strftime("%Y%m%d")
        text = fetch(ymd)
        if text is None or text == "FAIL":
            n_skip += 1; d += timedelta(days=1); continue
        rows = parse_rows(text, iso)
        if rows:
            con.executemany(
                "INSERT OR REPLACE INTO daily_short_volume VALUES (?,?,?,?,?,?)", rows)
            con.commit()
            n_files += 1; n_rows += len(rows)
            if n_files % 20 == 0:
                print(f"  {iso}: {len(rows)} rows | total {n_files} files / {n_rows} rows", flush=True)
        time.sleep(0.6 + random.uniform(0, 0.4))  # polite + jitter to avoid rate-limit
        d += timedelta(days=1)

    print(f"DONE: {n_files} files, {n_rows} rows, {n_skip} skipped (holidays)", flush=True)
    con.close()


if __name__ == "__main__":
    main()
