"""gex_snapshot.py — daily per-stock GEX snapshot, forward OI accumulation (2026-06-24).

WHY: historical intraday options data is paywalled (OPRA) and expired contracts are not
listed, so we CANNOT backtest dealer-gamma (GEX). The only free path is to snapshot the
FULL option chain (strikes, expiries, OI, price -> self-computed IV+gamma) once a day and
accumulate forward. In ~3-4 weeks this yields REAL historical OI (not a current-OI proxy)
covering a regime flip, which is what's needed to (a) nail the GEX sign convention and
(b) test whether per-stock GEX separates riser winners from fades.

Stores BOTH the raw per-contract chain (so any sign/weighting can be recomputed later
without re-pulling) AND a daily aggregate with call_gex / put_gex kept SEPARATE — the whole
sign question is call-vs-put weighting, so we never bake in a convention.

Usage:
  python scripts/gex_snapshot.py                 # SPY + today's riser_picks
  python scripts/gex_snapshot.py SPY NVDA COIN   # explicit symbols
Tables in data/gex_snapshots.db: gex_daily (aggregate), gex_chain (raw per-contract).
Naive GEX shown = call_gex - put_gex (SqueezeMetrics convention) — UNVALIDATED sign.
"""
import os, sys, sqlite3, datetime as dt, requests
from math import erf, exp, log, sqrt, pi
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
for ln in (ROOT / ".env").read_text().splitlines():
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k, v = ln.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
HDR = {"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY"), "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY")}
ET = ZoneInfo("America/New_York")
DB = ROOT / "data" / "gex_snapshots.db"
DATA = "https://data.alpaca.markets"
PAPER = "https://paper-api.alpaca.markets"

STRIKE_PCT = float(os.environ.get("GEX_STRIKE_PCT", "15")) / 100   # gamma negligible beyond ~15%
MAX_DTE = int(os.environ.get("GEX_MAX_DTE", "60"))                  # near-term dominates GEX
RFR = 0.04


def spot_of(sym):
    r = requests.get(f"{DATA}/v2/stocks/{sym}/snapshot", headers=HDR, params={"feed": "iex"}, timeout=15)
    j = r.json()
    for grp, fld in [("latestTrade", "p"), ("dailyBar", "c"), ("prevDailyBar", "c"), ("latestQuote", "ap")]:
        v = j.get(grp) or {}
        if v.get(fld):
            return float(v[fld])
    return None


def chain(sym, spot, today):
    """All contracts within +-STRIKE_PCT of spot, expiring within MAX_DTE."""
    lo, hi = spot * (1 - STRIKE_PCT), spot * (1 + STRIKE_PCT)
    end = (today + dt.timedelta(days=MAX_DTE)).isoformat()
    out, pg = [], None
    for _ in range(12):
        p = {"underlying_symbols": sym, "limit": 1000, "expiration_date_gte": today.isoformat(),
             "expiration_date_lte": end, "strike_price_gte": str(int(lo)), "strike_price_lte": str(int(hi))}
        if pg:
            p["page_token"] = pg
        r = requests.get(f"{PAPER}/v2/options/contracts", headers=HDR, params=p, timeout=20)
        j = r.json(); out += j.get("option_contracts", []); pg = j.get("next_page_token")
        if not pg:
            break
    return out


def quotes(symbols):
    out = {}
    for i in range(0, len(symbols), 100):
        r = requests.get(f"{DATA}/v1beta1/options/snapshots", headers=HDR,
                         params={"symbols": ",".join(symbols[i:i + 100]), "feed": "indicative"}, timeout=20)
        out.update(r.json().get("snapshots", {}))
    return out


def _N(x): return 0.5 * (1 + erf(x / sqrt(2)))


def bsprice(S, K, T, sig, cp):
    if T <= 0 or sig <= 0:
        return max(0.0, (S - K) if cp == "C" else (K - S))
    d1 = (log(S / K) + (RFR + 0.5 * sig * sig) * T) / (sig * sqrt(T)); d2 = d1 - sig * sqrt(T)
    return S * _N(d1) - K * exp(-RFR * T) * _N(d2) if cp == "C" else K * exp(-RFR * T) * _N(-d2) - S * _N(-d1)


def gamma(S, K, T, sig):
    if T <= 0 or sig <= 0:
        return 0.0
    d1 = (log(S / K) + (RFR + 0.5 * sig * sig) * T) / (sig * sqrt(T))
    return exp(-0.5 * d1 * d1) / sqrt(2 * pi) / (S * sig * sqrt(T))


def implied_vol(price, S, K, T, cp):
    a, b = 1e-3, 5.0
    for _ in range(40):
        m = (a + b) / 2
        if bsprice(S, K, T, m, cp) > price:
            b = m
        else:
            a = m
    return (a + b) / 2


def compute(sym, today):
    spot = spot_of(sym)
    if not spot:
        return None
    cs = chain(sym, spot, today)
    snaps = quotes([c["symbol"] for c in cs])
    rows = []
    for c in cs:
        oi = float(c.get("open_interest") or 0)
        if oi <= 0:
            continue
        s = snaps.get(c["symbol"]) or {}
        q = s.get("latestQuote") or {}
        bid, ask = q.get("bp"), q.get("ap")
        if bid and ask and ask > 0:
            mid = (bid + ask) / 2
        else:
            mid = ((s.get("latestTrade") or {}).get("p") or (s.get("dailyBar") or {}).get("c") or 0)
        if not mid or mid <= 0:
            continue
        K = float(c["strike_price"]); cp = "C" if c["type"] == "call" else "P"
        T = (dt.date.fromisoformat(c["expiration_date"]) - today).days / 365
        if T <= 0:
            continue
        iv = implied_vol(mid, spot, K, T, cp)
        g = gamma(spot, K, T, iv)
        rows.append((c["symbol"], K, c["expiration_date"], cp, oi, mid, iv, g))
    # call/put gex kept SEPARATE (units: $ notional gamma per 1% move). Sign convention deferred.
    def leg(t):
        return sum(g * oi * 100 * spot * spot * 0.01 for (_s, _K, _e, cp, oi, _m, _iv, g) in rows if cp == t)
    call_gex, put_gex = leg("C"), leg("P")
    call_oi = sum(r[4] for r in rows if r[3] == "C")
    put_oi = sum(r[4] for r in rows if r[3] == "P")
    return dict(spot=spot, rows=rows, call_gex=call_gex, put_gex=put_gex,
                gex_naive=call_gex - put_gex, n=len(rows), call_oi=call_oi, put_oi=put_oi)


def ensure_db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS gex_daily(
        snap_date TEXT, snap_ts TEXT, underlying TEXT, spot REAL,
        call_gex REAL, put_gex REAL, gex_naive REAL, n_contracts INT, call_oi REAL, put_oi REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS gex_chain(
        snap_date TEXT, underlying TEXT, opt_symbol TEXT, strike REAL, expiry TEXT,
        type TEXT, oi REAL, mid REAL, iv REAL, gamma REAL, spot REAL)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_daily ON gex_daily(snap_date, underlying)")


def main():
    now = dt.datetime.now(ET)
    today = now.date()
    syms = [s.upper() for s in sys.argv[1:]]
    if not syms:
        # SPY (index sign anchor) + a fixed liquid basket (cross-section for faster sign validation)
        # + today's riser picks (the selection question). Basket tunable via GEX_BASKET.
        basket = os.environ.get("GEX_BASKET", "SPY,QQQ,NVDA,TSLA,AAPL,AMD,COIN").split(",")
        syms = [s.strip().upper() for s in basket if s.strip()]
        try:
            j = sqlite3.connect(ROOT / "data" / "scan_journal.db")
            syms += [r[0] for r in j.execute(
                "SELECT DISTINCT symbol FROM riser_picks WHERE scan_date=?", (today.isoformat(),)).fetchall()]
            j.close()
        except Exception:
            pass
        # + in-band riser candidates from the persisted dumps (gain 2-6). Today's so GEX can be
        # tested vs each candidate's outcome; the last ~30 days so the cache covers RECURRING
        # candidates (gex_live reads the latest cached chain -> a name seen before stays warm and
        # has live GEX at the 09:37 pick). Disable: GEX_CANDIDATES=0.
        if os.environ.get("GEX_CANDIDATES", "1") != "0":
            try:
                import glob as _g, json as _j
                dumpdirs = sorted(_g.glob(str(ROOT / "data" / "riser_dumps" / "*")))[-30:]
                seen = set()
                for dd in dumpdirs:
                    for f in _g.glob(str(Path(dd) / "min_*.jsonl")):
                        for ln in open(f):
                            try:
                                r = _j.loads(ln)
                            except Exception:
                                continue
                            if 0 <= r.get("mfo", 99) <= 9 and r.get("gain") and 2.0 <= r["gain"] <= 6.0:
                                seen.add(r["sym"])
                syms += sorted(seen)
            except Exception:
                pass
        syms = list(dict.fromkeys(syms))  # dedupe, preserve order
    con = sqlite3.connect(DB); ensure_db(con)
    for sym in syms:
        # idempotent: one snapshot per (date, underlying)
        if con.execute("SELECT 1 FROM gex_daily WHERE snap_date=? AND underlying=?",
                       (today.isoformat(), sym)).fetchone():
            print(f"  {sym}: already snapshotted {today} — skip"); continue
        try:
            res = compute(sym, today)
        except Exception as e:
            print(f"  {sym}: ERROR {type(e).__name__}: {e}"); continue
        if not res:
            print(f"  {sym}: no spot/chain — skip"); continue
        con.execute("INSERT INTO gex_daily VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (today.isoformat(), now.strftime("%Y-%m-%d %H:%M:%S"), sym, res["spot"],
                     res["call_gex"], res["put_gex"], res["gex_naive"], res["n"], res["call_oi"], res["put_oi"]))
        con.executemany("INSERT INTO gex_chain VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        [(today.isoformat(), sym, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], res["spot"]) for r in res["rows"]])
        con.commit()
        sign = "POS" if res["gex_naive"] > 0 else "NEG"
        print(f"  {sym}: spot {res['spot']:.2f} | naive GEX {res['gex_naive']:,.0f} ({sign}) | "
              f"call {res['call_gex']:,.0f} put {res['put_gex']:,.0f} | {res['n']} contracts "
              f"(callOI {res['call_oi']:,.0f} putOI {res['put_oi']:,.0f})")
    con.close()
    print(f"[gex_snapshot] {today} done -> {DB}")


if __name__ == "__main__":
    main()
