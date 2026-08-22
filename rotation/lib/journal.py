"""rotation/lib/journal.py — the rotation (cross-asset / theme forecaster) data layer.

HYBRID STORAGE by design (each data type in the format that fits it):
  1. SQLite  data/rotation.db      — numeric time-series + graded predictions + the LINKAGE REGISTRY
                                      + regime tags. Queryable (lead-lag, hit-rate, which leads hold).
  2. JSON    rotation/plans/<date>.json  — the AI's full daily forecast (flexible; the brain writes it).
  3. Markdown rotation/memory.md    — the AI's narrative lessons + a human mirror of the top linkages.

The "brain that learns forward" lives in the LINKAGES table: each candidate lead (trigger→target)
carries a running forward tally + a status (unconfirmed/holding/broken). It is only weighted once it
earns a record — that is what makes the forecaster NOT a coin flip over time (many dimensions per day
+ a forward record + promote-only-what-holds), rather than one constant read.

Fully isolated: writes ONLY to data/rotation.db and rotation/*. Reads market data via yfinance.
NEVER touches resonance/overnight/exec_ai/swing. It FORECASTS; it does not trade.

Tables:
  snapshots   — (date, asset): daily cross-asset numeric snapshot (LONG; add an asset = new rows).
                Derived market internals (breadth, curve slope, credit) are stored as pseudo-assets
                under class='internal' with details in `extra`.
  predictions — (date, horizon, theme): the forward call + kind (mechanism/event) + how it graded.
  linkages    — (id): the learned lead registry — trigger→target with a forward tally + status.
  regimes     — (date): the day's regime tag (for learning regime transitions).

CLI:
  python -m rotation.lib.journal recent      # predictions + hit-rate + linkage registry
  python -m rotation.lib.journal linkages    # the linkage registry only
"""
from __future__ import annotations
import os, sqlite3, json, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                  "data", "rotation.db")


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        date TEXT, asset TEXT, class TEXT, close REAL,
        ret_1d REAL, ret_5d REAL, ret_20d REAL, rvol REAL, extra TEXT,
        PRIMARY KEY (date, asset))""")
    c.execute("""CREATE TABLE IF NOT EXISTS predictions (
        date TEXT, horizon TEXT, theme TEXT, lean TEXT, names TEXT,
        kind TEXT,            -- 'mechanism' (driver known -> lean direction) | 'event' (~coin flip) | 'regime'
        priced TEXT,          -- 'unspent' | 'priced' | NULL  (is the move still ahead or already in?)
        confidence REAL, falsifiable TEXT, reason TEXT,
        graded INTEGER DEFAULT 0, outcome TEXT, correct INTEGER,
        PRIMARY KEY (date, horizon, theme))""")
    c.execute("""CREATE TABLE IF NOT EXISTS linkages (
        id TEXT PRIMARY KEY,  -- short slug, e.g. 'liquidity->gold', 'yields_up->KRE_down'
        trigger TEXT, transmission TEXT, target TEXT, lag_days INTEGER,
        kind TEXT,            -- 'mechanism' | 'event' | 'regime'
        fwd_hits INTEGER DEFAULT 0, fwd_n INTEGER DEFAULT 0,
        status TEXT DEFAULT 'unconfirmed',   -- 'unconfirmed' | 'holding' | 'broken'
        note TEXT, updated TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS regimes (
        date TEXT PRIMARY KEY, label TEXT, features TEXT, note TEXT)""")
    # migration: add columns if an older DB predates them
    have = {r[1] for r in c.execute("PRAGMA table_info(predictions)")}
    for col in ("kind", "priced"):
        if col not in have:
            c.execute(f"ALTER TABLE predictions ADD COLUMN {col} TEXT")
    return c


# ---- snapshots ----
def log_snapshot(date, asset, cls, close, ret_1d=None, ret_5d=None, ret_20d=None, rvol=None, extra=None):
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO snapshots (date,asset,class,close,ret_1d,ret_5d,ret_20d,rvol,extra)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (date, asset, cls, close, ret_1d, ret_5d, ret_20d, rvol,
               json.dumps(extra) if extra is not None else None))
    c.commit(); c.close()


def snapshot_asof(date):
    c = _conn()
    rows = [dict(zip(("asset", "class", "close", "ret_1d", "ret_5d", "ret_20d", "rvol", "extra"), r))
            for r in c.execute("""SELECT asset,class,close,ret_1d,ret_5d,ret_20d,rvol,extra FROM snapshots
                                  WHERE date=? ORDER BY class,asset""", (date,))]
    c.close(); return rows


# ---- predictions ----
def log_prediction(date, horizon, theme, lean, names=None, kind=None, priced=None,
                   confidence=None, falsifiable=None, reason=None):
    c = _conn()
    c.execute("""INSERT OR REPLACE INTO predictions
                 (date,horizon,theme,lean,names,kind,priced,confidence,falsifiable,reason)
                 VALUES (?,?,?,?,?,?,?,?,?,?)""",
              (date, horizon, theme, lean, names, kind, priced, confidence, falsifiable, reason))
    c.commit(); c.close()
    print(f"[rotation] pred {horizon}/{theme} lean={lean} kind={kind} conf={confidence}")


def grade_prediction(date, horizon, theme, outcome, correct):
    c = _conn()
    c.execute("""UPDATE predictions SET outcome=?, correct=?, graded=1
                 WHERE date=? AND horizon=? AND theme=?""", (outcome, int(correct), date, horizon, theme))
    c.commit(); c.close()


def ungraded():
    c = _conn()
    rows = [dict(zip(("date", "horizon", "theme", "lean", "kind", "names", "falsifiable"), r))
            for r in c.execute("""SELECT date,horizon,theme,lean,kind,names,falsifiable FROM predictions
                                  WHERE graded=0 ORDER BY date""")]
    c.close(); return rows


# ---- linkages (the learned lead registry — the 'brain' that grows) ----
def upsert_linkage(id, trigger=None, transmission=None, target=None, lag_days=None,
                   kind=None, note=None):
    """Create or touch a linkage. Does NOT change the tally — use record_linkage() to score it."""
    c = _conn()
    exists = c.execute("SELECT 1 FROM linkages WHERE id=?", (id,)).fetchone()
    if exists:
        c.execute("""UPDATE linkages SET trigger=COALESCE(?,trigger),transmission=COALESCE(?,transmission),
                     target=COALESCE(?,target),lag_days=COALESCE(?,lag_days),kind=COALESCE(?,kind),
                     note=COALESCE(?,note) WHERE id=?""",
                  (trigger, transmission, target, lag_days, kind, note, id))
    else:
        c.execute("""INSERT INTO linkages (id,trigger,transmission,target,lag_days,kind,note,updated)
                     VALUES (?,?,?,?,?,?,?,datetime())""",
                  (id, trigger, transmission, target, lag_days, kind, note))
    c.commit(); c.close()


def record_linkage(id, held, note=None):
    """Score one forward observation of a linkage (held=True/False), update tally + status.
    status: <5 obs = unconfirmed; >=5 obs & >=70% = holding; >=5 obs & <=40% = broken; else unconfirmed."""
    c = _conn()
    row = c.execute("SELECT fwd_hits,fwd_n FROM linkages WHERE id=?", (id,)).fetchone()
    if not row:
        c.execute("INSERT INTO linkages (id,updated) VALUES (?,datetime())", (id,))
        hits, n = 0, 0
    else:
        hits, n = row
    hits = (hits or 0) + (1 if held else 0)
    n = (n or 0) + 1
    rate = hits / n if n else 0
    status = "unconfirmed"
    if n >= 5 and rate >= 0.70:
        status = "holding"
    elif n >= 5 and rate <= 0.40:
        status = "broken"
    c.execute("""UPDATE linkages SET fwd_hits=?,fwd_n=?,status=?,note=COALESCE(?,note),updated=datetime()
                 WHERE id=?""", (hits, n, status, note, id))
    c.commit(); c.close()
    print(f"[rotation] linkage {id}: {hits}/{n} ({100*rate:.0f}%) -> {status}")


def linkage_registry(status=None):
    c = _conn()
    q = "SELECT id,kind,fwd_hits,fwd_n,status,target,note FROM linkages"
    args = ()
    if status:
        q += " WHERE status=?"; args = (status,)
    q += " ORDER BY (CAST(fwd_hits AS REAL)/MAX(fwd_n,1)) DESC, fwd_n DESC"
    rows = [dict(zip(("id", "kind", "fwd_hits", "fwd_n", "status", "target", "note"), r))
            for r in c.execute(q, args)]
    c.close(); return rows


# ---- regimes ----
def log_regime(date, label, features=None, note=None):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO regimes (date,label,features,note) VALUES (?,?,?,?)",
              (date, label, json.dumps(features) if features is not None else None, note))
    c.commit(); c.close()


def regime_history(n=15):
    c = _conn()
    rows = [dict(zip(("date", "label", "note"), r))
            for r in c.execute("SELECT date,label,note FROM regimes ORDER BY date DESC LIMIT ?", (n,))]
    c.close(); return rows


def recent(n=30):
    c = _conn()
    print("== recent predictions ==")
    for r in c.execute("""SELECT date,horizon,theme,lean,kind,confidence,graded,correct FROM predictions
                          ORDER BY date DESC LIMIT ?""", (n,)):
        print(r)
    print("== hit rate by horizon+kind (graded) ==")
    for r in c.execute("""SELECT horizon,kind,COUNT(*) n,SUM(correct) hits FROM predictions
                          WHERE graded=1 GROUP BY horizon,kind"""):
        h, k, nn, hits = r
        print(f"  {h}/{k}: {hits or 0}/{nn} = {100*(hits or 0)/nn:.0f}%")
    print("== linkage registry (holding first) ==")
    for lk in linkage_registry():
        print(f"  [{lk['status']}] {lk['id']}: {lk['fwd_hits']}/{lk['fwd_n']} ({lk['kind']})")
    c.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    if cmd == "grade":
        print("Ungraded predictions (grade via rotation/run/daily.sh -> brain/learn.md):")
        for r in ungraded():
            print(" ", r)
    elif cmd == "linkages":
        for lk in linkage_registry():
            print(lk)
    else:
        recent()
