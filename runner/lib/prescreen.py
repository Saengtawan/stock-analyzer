"""runner/lib/prescreen.py — MECHANICAL pre-screen (0 AI tokens, seconds).

Does the SLOW plumbing so the AI doesn't have to: pulls today's low-price gainer board and computes
each name's first-hour tape metrics (blow-off magnitude, higher-highs into the entry, HOD time, day
gain, distance from HOD, liquidity/halt). It RANKS and FLAGS — it does NOT decide. The AI then reads
this shortlist and JUDGES shape / reclaim quality / ETF-vs-stock / odds on it, keeping all the judgment
where it belongs (code = plumbing, AI = judgment). This is the "gather + narrow generously" design:
the shortlist is deliberately WIDE (~top 10 by momentum, flags not hard cuts) so the AI still sees the
borderline names (a blow-off that reclaimed, a name one notch under a threshold) and makes the call.

The mechanical thresholds here are the decide.md REFERENCE lines (blow-off ~-13%, HH>0, HOD recent) —
surfaced as booleans for convenience, NOT applied as gates. The AI weighs the whole shape.

CLI:
  python -m runner.lib.prescreen                 # entry=10:30, board as-of now, prints + writes JSON
  python -m runner.lib.prescreen --entry 10:20   # different entry bar
  python -m runner.lib.prescreen --out path.json
"""
from __future__ import annotations
import json, sys, warnings, zoneinfo, datetime, argparse
warnings.filterwarnings("ignore")
ET = zoneinfo.ZoneInfo("America/New_York")


def get_board(min_chg=8.0, lo=1.0, hi=10.0, min_vol=300_000, size=40):
    """Low-price gainer board via yfinance custom screener. Returns [(sym, price, chg, vol), ...]."""
    import yfinance as yf
    from yfinance import EquityQuery as Q
    q = Q("and", [Q("gt", ["percentchange", min_chg]), Q("gt", ["intradayprice", lo]),
                  Q("lt", ["intradayprice", hi]), Q("eq", ["region", "us"]),
                  Q("gt", ["dayvolume", min_vol])])
    r = yf.screen(q, sortField="percentchange", sortAsc=False, size=size)
    out = []
    for x in (r.get("quotes", []) if isinstance(r, dict) else []):
        s = x.get("symbol")
        if s:
            out.append((s, x.get("regularMarketPrice"), x.get("regularMarketChangePercent"),
                        x.get("regularMarketVolume")))
    return out


def _resolve_entry(entry):
    """'now' -> current ET HH:MM; otherwise pass through an HH:MM."""
    if entry == "now":
        return datetime.datetime.now(ET).strftime("%H:%M")
    return entry


def metrics(sym, date, entry="10:30"):
    """First-hour tape metrics for one name, computed on bars <= entry (replay-safe)."""
    import yfinance as yf
    entry = _resolve_entry(entry)
    d = datetime.date.fromisoformat(date)
    df = yf.download(sym, start=date, end=(d + datetime.timedelta(days=1)).isoformat(),
                     interval="1m", prepost=False, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    if hasattr(df.columns, "levels"):
        df.columns = [x[0] for x in df.columns]
    df = df.tz_convert(ET)
    rth = df[df.index.strftime("%H:%M") >= "09:30"]
    w = rth[rth.index.strftime("%H:%M") <= entry]
    if len(w) < 15:
        return None
    e = w[w.index.strftime("%H:%M") == entry]
    entry_px = float(e["Close"].iloc[0]) if len(e) else float(w["Close"].iloc[-1])
    o = float(w[w.index.strftime("%H:%M") == "09:30"]["Open"].iloc[0])
    hod = float(w["High"].max())
    hod_row = w.loc[w["High"].idxmax()].name
    hod_t = hod_row.strftime("%H:%M")
    blowoff = min((float(b["Low"]) / float(b["High"]) - 1) * 100 for _, b in w.iterrows())
    # --- everything relative to the ENTRY bar, so it works for ANY entry (10:30 OR a later rerun) ---
    eh, em = int(entry.split(":")[0]), int(entry.split(":")[1])
    entry_min = eh * 60 + em
    # higher-highs INTO the entry: the last ~10 min's high vs the ~15 min before that (recent momentum)
    recent = w.tail(10)
    prior = w.iloc[-25:-10] if len(w) >= 25 else w.iloc[: max(1, len(w) // 2)]
    rhi = float(recent["High"].max()); phi = float(prior["High"].max()) if len(prior) else o
    hh = (rhi / phi - 1) * 100 if phi else 0.0
    # HOD recency: minutes between the HOD print and the entry (small = still stamping new highs)
    hod_age = entry_min - (hod_row.hour * 60 + hod_row.minute)
    # halt/missing minutes: expected 1-min bars from 09:30 to the entry (inclusive) minus what printed
    expected = (entry_min - (9 * 60 + 30)) + 1
    halt = max(0, expected - len(w))
    vs_hod = (entry_px / hod - 1) * 100
    # RECENT SLAM: worst single-bar high->low drop in the LAST ~5 min. This is what separates an
    # IGNITION (new high held) from a SPIKE-AND-SLAM (new high then dumped) — the higher-highs metric
    # alone can't, because a spike that gets slammed still stamps a fresh HIGH (it flags offense_ok while
    # the name is actually crashing at the entry). Caught by AREN 08-28: hh +14% / HOD 2min but a -12.5%
    # slam one bar before entry. A grinder's recent bars are shallow; a slammed spike shows a deep one.
    recent5 = w.tail(5)
    recent_slam = min((float(b["Low"]) / float(b["High"]) - 1) * 100 for _, b in recent5.iterrows())
    return {
        "entry_px": round(entry_px, 4),
        "day_gain": round((entry_px / o - 1) * 100, 1) if o else None,
        "vs_hod": round(vs_hod, 1),
        "hod_time": hod_t,
        "hod_age_min": hod_age,
        "blowoff": round(blowoff, 1),
        "recent_slam": round(recent_slam, 1),
        "hh_into_entry": round(hh, 1),
        "halt_missing_min": halt,
        # REFERENCE booleans (decide.md lines, NOT gates — the AI judges the shape):
        "ref_no_blowoff": blowoff > -13,
        # offense = still building AND still HOLDING near the HOD (not spiked-then-slammed back) AND no
        # violent slam in the last few minutes. vs_hod > -5 kills the spike-and-slam that hh alone passes.
        "ref_offense_ok": hh > 0 and hod_age <= 20 and vs_hod > -5 and recent_slam > -8,
        "ref_liquid": halt <= 5,                       # >5 missing min hints a halt/thin book — verify
    }


def run(entry="10:30", date=None, top=10):
    entry = _resolve_entry(entry)
    date = date or datetime.datetime.now(ET).strftime("%F")
    board = get_board()
    rows = []
    for sym, price, chg, vol in board:
        m = metrics(sym, date, entry)
        if not m:
            continue
        m["sym"] = sym; m["screener_chg"] = round(chg, 1) if chg else None
        rows.append(m)
    rows.sort(key=lambda r: -(r.get("day_gain") or -999))
    return {"date": date, "entry": entry, "board_n": len(board), "with_data": len(rows),
            "shortlist": rows[:top]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", default="10:30")
    ap.add_argument("--date", default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(entry=a.entry, date=a.date, top=a.top)
    txt = json.dumps(res, indent=1)
    if a.out:
        with open(a.out, "w") as f:
            f.write(txt)
    print(txt)
    print(f"\n[prescreen] board={res['board_n']} with_data={res['with_data']} "
          f"-> shortlist top {len(res['shortlist'])} (entry {res['entry']})", file=sys.stderr)
