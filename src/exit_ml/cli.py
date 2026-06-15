"""Exit ML v17c CLI — `python -m src.exit_ml.cli SYM [...]` or via exit_check.sh"""
from __future__ import annotations
import argparse, sqlite3, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import os
from src.exit_ml.inference import predict_exit, SPEC
from src.exit_ml.inference_v18 import predict_exit_v18
from src.exit_ml.inference_riser import predict_exit_riser, is_riser_pick

ROOT = Path(__file__).resolve().parents[2]
DB = str(ROOT / "data/trade_history.db")
JOURNAL = str(ROOT / "data/exit_ml_journal.db")
SCAN_JOURNAL = str(ROOT / "data/scan_journal.db")  # riser_picks table lives here


SCHEMA = """
CREATE TABLE IF NOT EXISTS exit_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  check_ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  sector TEXT,
  zone TEXT,
  entry_price REAL,
  entry_time TEXT,
  date TEXT,
  vix_at_entry REAL,
  ml_prob REAL,
  threshold REAL,
  dd_gate REAL,
  cur_pnl_pct REAL,
  verdict TEXT,
  reason TEXT,
  shadow_mode INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_checks_sym ON exit_checks(symbol);
CREATE INDEX IF NOT EXISTS idx_checks_date ON exit_checks(date);
"""


def init_journal():
    con = sqlite3.connect(JOURNAL)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def get_vix(db_path: str, date: str | None = None) -> float | None:
    con = sqlite3.connect(db_path)
    if date:
        row = con.execute(
            "SELECT vix_close FROM macro_snapshots WHERE date<=? AND vix_close IS NOT NULL ORDER BY date DESC LIMIT 1",
            (date,)
        ).fetchone()
    else:
        row = con.execute(
            "SELECT vix_close FROM macro_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
    con.close()
    return float(row[0]) if row and row[0] is not None else None


def get_open_position(db_path: str, symbol: str) -> tuple | None:
    """Return (entry_price, entry_time_et_str, entry_date) from active_positions if exists."""
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT entry_price, entry_time FROM active_positions WHERE symbol=? LIMIT 1",
            (symbol,)
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    con.close()
    if not row: return None
    entry_price, entry_time_raw = row
    # entry_time format may be 'YYYY-MM-DD HH:MM:SS' (Bangkok) — assume already converted
    if " " in entry_time_raw:
        date_part, time_part = entry_time_raw.split(" ", 1)
        return float(entry_price), time_part[:5], date_part
    return float(entry_price), entry_time_raw[:5], None


def write_journal(symbol: str, result: dict, entry_price: float, entry_time: str, date: str | None, shadow_mode: bool):
    con = sqlite3.connect(JOURNAL)
    con.execute(
        """INSERT INTO exit_checks
           (check_ts, symbol, sector, zone, entry_price, entry_time, date,
            vix_at_entry, ml_prob, threshold, dd_gate, cur_pnl_pct, verdict, reason, shadow_mode)
           VALUES (datetime('now'),?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            symbol, result.get("sector"), result.get("zone"),
            entry_price, entry_time, date,
            result.get("vix_at_entry"),
            result.get("ml_prob"), result.get("threshold"), result.get("dd_gate"),
            result.get("cur_pnl_pct"),
            result.get("verdict"), result.get("reason"),
            1 if shadow_mode else 0,
        ),
    )
    con.commit()
    con.close()


def fmt_pct(x):
    if x is None: return "--"
    return f"{x:+.2f}%"


def format_output_riser(symbol: str, result: dict, entry_price: float, entry_time: str, date: str | None):
    v = result["verdict"]
    emoji = {"HOLD": "✅", "TRAIL_EXIT": "🟢", "ERROR": "❌"}.get(v, "?")
    print(f"=== Riser Exit: {symbol} @ {entry_time}{' ('+date+')' if date else ''} ===")
    print(f"Entry: ${entry_price:.2f}  {result.get('sector','?')}  [RISER lane]")
    if result.get("vix_at_entry") is not None:
        print(f"VIX:   {result['vix_at_entry']:.1f}  |  own_range(20m): {result.get('own_range',0):.2f}%")
    if result.get("cur_pnl_pct") is not None:
        cur_price = entry_price * (1 + result["cur_pnl_pct"] / 100.0)
        hw = f"  hwm {result['hwm_pct']:+.2f}%" if result.get("hwm_pct") is not None else ""
        print(f"Price: ${cur_price:.2f}  ({fmt_pct(result['cur_pnl_pct'])}){hw}")
    if result.get("exit_time"):
        print(f"Fired: @{result['exit_time']} ET")
    print(f"Verdict: {emoji} {v}")
    print(f"Reason:  {result.get('reason','')}")


def format_output_v18(symbol: str, result: dict, entry_price: float, entry_time: str, date: str | None):
    v = result["verdict"]
    emoji = {"HOLD": "✅", "SL_EXIT": "🔴", "TRAIL_EXIT": "🟢", "PL_EXIT": "🟡",
             "VIX_SKIP": "🛡️", "ERROR": "❌"}.get(v, "?")
    sector = result.get("sector", "?"); zone = result.get("zone", "?")
    print(f"=== Exit Check v18: {symbol} @ {entry_time}{' ('+date+')' if date else ''} ===")
    print(f"Entry: ${entry_price:.2f}  {zone} {sector}")
    if result.get("vix_at_entry") is not None:
        print(f"VIX:   {result['vix_at_entry']:.1f} (gate {'ON' if result['vix_at_entry']>=28 else 'OFF'}, cutoff 28)")
    if result.get("ml_prob") is not None:
        print(f"ML p:  {result['ml_prob']:.3f}  (PL thr 0.55)")
    if result.get("spy_dd") is not None:
        print(f"SPY dd: {result['spy_dd']:+.2f}%  (gate <= -0.30 for TRAIL/PL)")
    if result.get("cur_pnl_pct") is not None:
        cur_price = entry_price * (1 + result["cur_pnl_pct"] / 100.0)
        hw = f"  hwm {result['hwm_pct']:+.2f}%" if result.get("hwm_pct") is not None else ""
        print(f"Price: ${cur_price:.2f}  ({fmt_pct(result['cur_pnl_pct'])}){hw}")
    if result.get("exit_time"):
        print(f"Fired: @{result['exit_time']} ET")
    print(f"Verdict: {emoji} {v}")
    print(f"Reason:  {result.get('reason','')}")


def format_output(symbol: str, result: dict, entry_price: float, entry_time: str, date: str | None):
    v = result["verdict"]
    emoji = {"HOLD": "✅", "EXIT": "⚠️", "CRISIS_HOLD": "🛡️", "ERROR": "❌"}.get(v, "?")
    sector = result.get("sector", "?")
    zone = result.get("zone", "?")
    print(f"=== Exit Check: {symbol} @ {entry_time}{' ('+date+')' if date else ''} ===")
    print(f"Entry: ${entry_price:.2f}  {zone} {sector}")
    if "fill_price" in result:
        print(f"Fill:  ${result['fill_price']:.2f}")
    if result.get("vix_at_entry") is not None:
        gate = SPEC["vix_safety_gate"]["cutoff"]
        gate_state = "ON" if result["vix_at_entry"] >= gate else "OFF"
        print(f"VIX:   {result['vix_at_entry']:.1f} (safety gate {gate_state}, cutoff {gate})")
    if "ml_prob" in result:
        print(f"ML p:  {result['ml_prob']:.3f}  (thr={result['threshold']:.2f}"
              + (f", DD-gate={result['dd_gate']:+.2f}%" if result.get('dd_gate') is not None else "")
              + ")")
    if "cur_pnl_pct" in result:
        cur_price = result.get("fill_price", entry_price) * (1 + result["cur_pnl_pct"] / 100.0)
        print(f"Price: ${cur_price:.2f}  ({fmt_pct(result['cur_pnl_pct'])})")
    add = result.get("add_signal")
    if add:
        print(f"ADD:   🟢 {add['tier']} {add['zone']} {add['sector']} — DCA suggested @ ${add['dca_entry']:.2f}")
    elif "ml_prob" in result and result.get("ml_prob") is not None and result.get("threshold"):
        # show "no ADD" only when we had a real ML eval (not error/CRISIS_HOLD)
        print(f"ADD:   ⚪ no ADD (zone/sector/dip/p_ratio not eligible)")
    if "max_prob_so_far" in result:
        print(f"max_p: {result['max_prob_so_far']:.3f} (so far)")
    print(f"Verdict: {emoji} {v}")
    print(f"Reason:  {result.get('reason','')}")


def main():
    ap = argparse.ArgumentParser(description="Exit ML v17c manual check")
    ap.add_argument("symbol")
    ap.add_argument("--entry", type=float, help="entry price (else lookup active_positions)")
    ap.add_argument("--time", help="entry time ET 'HH:MM' (else lookup)")
    ap.add_argument("--date", help="date 'YYYY-MM-DD' (else latest)")
    ap.add_argument("--vix", type=float, help="VIX at entry (else lookup macro_snapshots)")
    ap.add_argument("--live", action="store_true",
                    help="LIVE mode — do not write to shadow journal (default = shadow)")
    ap.add_argument("--v17c", action="store_true",
                    help="rollback: use legacy v17c exit logic instead of v18 (default v18)")
    args = ap.parse_args()

    # v18 is the deployed default; EXIT_ML_VERSION=v17c or --v17c rolls back.
    use_v18 = not (args.v17c or os.environ.get("EXIT_ML_VERSION", "v18").lower() == "v17c")

    init_journal()

    entry_price, entry_time, date = args.entry, args.time, args.date
    if entry_price is None or entry_time is None:
        pos = get_open_position(DB, args.symbol)
        if pos:
            ep, et, dt = pos
            if entry_price is None: entry_price = ep
            if entry_time is None: entry_time = et
            if date is None and dt: date = dt
        else:
            print(f"❌ No open position for {args.symbol} — pass --entry and --time", file=sys.stderr)
            sys.exit(1)

    vix = args.vix if args.vix is not None else get_vix(DB, date=date)

    # Riser picks use the dedicated dynamic-trail exit (NOT v18 — v18 hurts risers).
    riser = is_riser_pick(args.symbol, date, SCAN_JOURNAL) and not args.v17c
    if riser:
        result = predict_exit_riser(
            args.symbol, entry_price, entry_time, DB,
            vix_at_entry=vix, date=date,
        )
        result.setdefault("vix_at_entry", vix)
        format_output_riser(args.symbol, result, entry_price, entry_time, date)
    elif use_v18:
        result = predict_exit_v18(
            args.symbol, entry_price, entry_time, DB,
            vix_at_entry=vix, date=date,
        )
        result.setdefault("vix_at_entry", vix)
        format_output_v18(args.symbol, result, entry_price, entry_time, date)
    else:
        result = predict_exit(
            args.symbol, entry_price, entry_time, DB,
            vix_at_entry=vix, date=date,
        )
        format_output(args.symbol, result, entry_price, entry_time, date)

    write_journal(args.symbol, result, entry_price, entry_time, date, shadow_mode=not args.live)
    journal_state = "shadow" if not args.live else "LIVE"
    ver = "riser-dyn" if riser else ("v18" if use_v18 else "v17c")
    print(f"\n[logged to exit_ml_journal.db — {journal_state} mode, {ver}]")


if __name__ == "__main__":
    main()
