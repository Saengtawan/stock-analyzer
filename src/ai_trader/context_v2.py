"""Stage 2 — assemble the context the AI reasons over, across the BROAD universe.

For the day: macro narrative + regime. For each mover: gap direction, sector, and its
recent news/story (DB; flag web-search where absent). Code only gathers — the AI judges.
"""
from __future__ import annotations
import argparse, sqlite3
from .universe import gather_universe
from .premarket import gather_preopen

DB = "data/trade_history.db"


def _sector(p, sym, _c={}):
    if sym in _c:
        return _c[sym]
    r = p.execute("SELECT sector FROM stock_fundamentals WHERE symbol=? LIMIT 1", (sym,)).fetchone()
    _c[sym] = (r[0] if r and r[0] else "?")
    return _c[sym]


def _news(p, sym, date, days=4):
    return list(p.execute(
        "SELECT scan_date_et, sentiment_label, headline FROM news_events "
        "WHERE symbol=? AND scan_date_et<=? AND scan_date_et>=date(?, '-%d day') "
        "ORDER BY published_at DESC LIMIT 3" % days, (sym, date, date)))


def build(date, top=100, db=DB, sim_minute=None):
    p = sqlite3.connect(db)
    macro = gather_preopen(date)
    if sim_minute:
        from .universe_sim import gather_universe_sim
        movers = gather_universe_sim(date, minute=sim_minute, db=db)
    else:
        movers = gather_universe(top=top, db=db)

    L = [f"=== CONTEXT v2 {date} ===",
         f"prior VIX {macro.get('vix_prior')} | macro/fed/geo sentiment {macro.get('macro_sent')} | "
         f"regime {macro.get('spy_regime_prior')}",
         "", "MACRO NARRATIVE (why the tape is where it is):"]
    for s, imp, h in (macro.get("macro_neg_headlines") or [])[:6]:
        L.append(f"  [{s:+.2f}] {h}")
    if not macro.get("macro_neg_headlines"):
        L.append("  (no negative macro flagged)")

    ups = [m for m in movers if m.direction == "up"]
    downs = [m for m in movers if m.direction == "down"]
    # focus the reading: gap-down names (reversal hunting ground) by depth, top up-movers.
    def _gap(m):
        return (m.price / m.prev_close - 1) * 100 if m.prev_close else 0.0
    down_focus = sorted([m for m in downs if _gap(m) <= -1.5], key=_gap)[:25] or \
                 sorted(downs, key=lambda m: m.pct_change)[:25]
    up_focus = sorted(ups, key=lambda m: -m.pct_change)[:15]
    L += ["", f"THE FIELD — {len(movers)} liquid movers ({len(ups)} up / {len(downs)} down); "
          f"showing {len(down_focus)} gap-down + {len(up_focus)} top-up.",
          "Read each STORY, assign an archetype, judge in context. Setups are PRIORS not gates."]
    for label, group in (("GAPPED DOWN (reversal hunting ground — deepest gap first)", down_focus),
                         ("TOP MOVING UP (breakout / momentum / catalyst)", up_focus)):
        L.append(f"\n {label}:")
        for m in group:
            gap = f"{(m.price/m.prev_close-1)*100:+.1f}%" if m.prev_close else "?"
            L.append(f"  {m.sym:6} day{m.pct_change:+6.1f}% ${m.price:.2f} gap-vs-prevclose {gap}"
                     f"  {_sector(p, m.sym)}")
            nw = _news(p, m.sym, date)
            if nw:
                for d, lab, h in nw[:2]:
                    L.append(f"        [{d} {lab}] {h[:76]}")
            else:
                L.append(f"        (no DB news -> web-search 'why is {m.sym} moving today')")
    L += ["", "DECIDE -> write plans/decisions/<date>.json (archetype + picks + exit + reason, or abstain)."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=100)
    print(build(ap.parse_args().date, top=ap.parse_args().top))


if __name__ == "__main__":
    main()
