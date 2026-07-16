"""Stage 2 — assemble the context the AI reasons over, across the BROAD universe.

For the day: macro narrative + regime. For each mover: gap direction, sector, and its
recent news/story (DB; flag web-search where absent). Code only gathers — the AI judges.
"""
from __future__ import annotations
import argparse, sqlite3, datetime, zoneinfo
from .universe import gather_universe
from .premarket import gather_preopen

DB = "data/trade_history.db"
ET = zoneinfo.ZoneInfo("America/New_York")


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

    # TIME context — the AI must know the clock: a reversal at 09:35 has all day to play
    # out; at 15:00 there's little time left. Live = now; sim = the reconstructed minute.
    if sim_minute:
        sh, sm = divmod(sim_minute, 60)
        scan_label = f"~{sh:02d}:{sm:02d} ET (SIMULATED point-in-time)"
        mins_left = 16 * 60 - sim_minute
    else:
        now = datetime.datetime.now(ET)
        scan_label = now.strftime("%H:%M ET %a")
        mins_left = 16 * 60 - (now.hour * 60 + now.minute)
    mins_left = max(0, mins_left)

    L = [f"=== CONTEXT v2 {date} ===",
         f"SCAN TIME: {scan_label} — {mins_left} min ({mins_left/60:.1f}h) until the 16:00 ET close.",
         "  OBJECTIVE: pick the name(s) that, bought AT THE CURRENT PRICE right now, will be",
         "  GREEN at your exit (EOD or the pick's stop/trail). Every number below is AS OF NOW",
         "  — judge from the current price + the momentum trajectory, NOT the from-open level.",
         "  A name now far BELOW its peak (off-peak very negative) has already SPENT its move —",
         "  buying it = the ABT trap (bought after +5% but it peaked an hour ago and is fading).",
         "  A name now far ABOVE its low (up from trough) is freshly reclaiming. The move must",
         "  still have runway from HERE to the 16:00 close — reason each to 'where at 16:00?'.",
         "  For EACH pick, ESTIMATE the room left from the CURRENT price to the close (roughly",
         "  how many % higher, and how likely) and confirm that forward upside beats the stop.",
         "  A name that has already run most of its move has little room LEFT even if it hasn't",
         "  faded yet — 'near peak, never red' is not enough; there must be profit FROM HERE.",
         "  Put the from-here upside estimate in each pick's reason.",
         f"prior VIX {macro.get('vix_prior')} | macro/fed/geo sentiment {macro.get('macro_sent')} | "
         f"regime {macro.get('spy_regime_prior')}",
         "", "MACRO NARRATIVE (why the tape is where it is):"]
    for s, imp, h in (macro.get("macro_neg_headlines") or [])[:6]:
        L.append(f"  [{s:+.2f}] {h}")
    if not macro.get("macro_neg_headlines"):
        L.append("  (no negative macro flagged)")

    # Reversal hunting ground = GAPPED DOWN vs prev close (regardless of from-open
    # direction) — a gap-down recovering to green is exactly the reversal, so we must
    # key off gap, not from-open, or we'd file NOW-type names under "up" and miss them.
    def _gap(m):
        return (m.price / m.prev_close - 1) * 100 if m.prev_close else 0.0
    gapped_down = [m for m in movers if _gap(m) <= -1.5]
    down_focus = sorted(gapped_down, key=_gap)[:14]
    up_focus = sorted([m for m in movers if _gap(m) > -1.5 and m.pct_change > 0],
                      key=lambda m: -m.pct_change)[:8]
    L += ["", f"THE FIELD — {len(movers)} liquid movers ({len(gapped_down)} gapped down); "
          f"showing {len(down_focus)} gap-down + {len(up_focus)} top-up.",
          "Read each STORY, assign an archetype, judge in context. Setups are PRIORS not gates."]
    for label, group in (("GAPPED DOWN vs prev close (reversal ground — deepest gap first; "
                          "note from-open % to see who's already recovering)", down_focus),
                         ("TOP MOVING UP FROM OPEN (breakout / momentum / catalyst)", up_focus)):
        L.append(f"\n {label}:")
        for m in group:
            gap = f"{(m.price/m.prev_close-1)*100:+.1f}%" if m.prev_close else "?"
            # momentum trajectory AS OF NOW: peak/low + how far off — a name now far below
            # its peak has already SPENT its move (the ABT trap); one now far above its low
            # is freshly reclaiming. Judge buyability from the CURRENT price, not the level.
            L.append(f"  {m.sym:6} now{m.pct_change:+6.1f}% [pk{m.peak_pct:+.1f} off{m.off_peak:+.1f} | "
                     f"low{m.trough_pct:+.1f} up{m.off_trough:+.1f}] ${m.price:.2f} gap{gap} {_sector(p, m.sym)}")
            nw = _news(p, m.sym, date)
            if nw:
                d, lab, h = nw[0]
                L.append(f"        [{lab}] {h[:74]}")
            else:
                L.append(f"        (no DB news)")
    L += ["", "DECIDE -> write plans/decisions/<date>.json (archetype + picks + exit + reason, or abstain)."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=100)
    print(build(ap.parse_args().date, top=ap.parse_args().top))


if __name__ == "__main__":
    main()
