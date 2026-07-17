"""Stage 2 — assemble the context the AI reasons over, across the BROAD universe.

For the day: macro narrative + regime. For each mover: gap direction, sector, and its
recent news/story (DB; flag web-search where absent). Code only gathers — the AI judges.
"""
from __future__ import annotations
import argparse, sqlite3, datetime, zoneinfo, requests, json, os
from .universe import gather_universe, _keys
from .premarket import gather_preopen
from . import journal

DB = "data/trade_history.db"
ET = zoneinfo.ZoneInfo("America/New_York")
FIELD_DIR = "plans/field"


def _alpaca_news(syms):
    """Recent news headlines per symbol (Alpaca news API, one batched call) so the AI reads
    catalysts straight from the brief instead of spending turns web-searching."""
    if not syms:
        return {}
    try:
        r = requests.get("https://data.alpaca.markets/v1beta1/news", headers=_keys(),
                         params={"symbols": ",".join(syms), "limit": 50, "sort": "desc"},
                         timeout=15).json()
    except Exception:
        return {}
    out = {}
    # prefer name-specific items (few symbols), most-recent first
    for n in sorted(r.get("news", []), key=lambda n: len(n.get("symbols", []) or [])):
        h = (n.get("headline") or "")[:80]
        # summary gives the AI the actual catalyst (beat/raise/PT/denial) so it rarely needs
        # to spend a web-search turn — same Alpaca call, one extra field
        summ = " ".join((n.get("summary") or "").split())[:150]
        when = (n.get("created_at") or "")[:16]
        for s in (n.get("symbols") or []):
            if s in syms and len(out.get(s, [])) < 2 and h not in [x[1] for x in out.get(s, [])]:
                out.setdefault(s, []).append((when, h, summ))
    return out


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
    warn = []
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
        # A2: the "room to close" framing only holds during RTH — refuse to mislead otherwise
        mins_now = now.hour * 60 + now.minute
        if now.weekday() >= 5:
            warn.append("⚠️ WEEKEND — market closed; this field is stale/empty. Do NOT trade.")
        elif mins_now < 9 * 60 + 30:
            warn.append("⚠️ BEFORE THE OPEN (pre-09:30 ET) — no intraday field yet; the 'room to "
                        "close' numbers are not meaningful. Treat as a preview only, do NOT emit picks.")
        elif mins_now >= 16 * 60:
            warn.append("⚠️ AFTER THE CLOSE (post-16:00 ET) — session over; this is replay, not a "
                        "tradeable scan.")
    mins_left = max(0, mins_left)

    # A4: an empty field during RTH almost always means a DATA-PIPE failure (expired key,
    # rate-limit, bars outage) — NOT a genuine no-mover day. Say so loudly so a pipeline
    # outage can't masquerade as a clean 'nothing to trade' abstain.
    if not movers and not warn:
        warn.append("⚠️ EMPTY FIELD during market hours — this is almost certainly a DATA-PIPE "
                    "FAILURE (Alpaca key/rate-limit/bars outage), not a real no-mover day. "
                    "ABSTAIN and flag PIPELINE ERROR; do not conclude 'nothing tradeable'.")

    # B2: persist the live field snapshot so the outcome step can realize a mechanical
    # baseline (deepest gap-down already reclaiming) as a control arm vs the AI's picks.
    if not sim_minute and movers:
        try:
            os.makedirs(FIELD_DIR, exist_ok=True)
            snap = [{"sym": m.sym, "gain": m.pct_change, "gap": round((m.price/m.prev_close-1)*100, 2)
                     if m.prev_close else None, "peak": m.peak_pct, "trough": m.trough_pct,
                     "off_trough": round(m.off_trough, 2), "slope10": m.slope10,
                     "vwap_dist": m.vwap_dist, "rel_vol": m.rel_vol} for m in movers]
            json.dump(snap, open(os.path.join(FIELD_DIR, f"{date}.json"), "w"))
        except Exception:
            pass

    L = [f"=== CONTEXT v2 {date} ==="]
    for w in warn:                       # A2/A4: loud banner if the scan is invalid/suspect
        L += [w]
    # B1 — FEEDBACK LOOP: show the AI its own recent realized picks so it isn't blind to how
    # its judgment has actually been doing (not hardcoded anecdotes — the live journal).
    try:
        rec = journal.recent_outcomes(8)
    except Exception:
        rec = []
    if rec:
        wins = sum(1 for *_, o in rec if o is not None and o > 0)
        nres = sum(1 for *_, o in rec if o is not None)
        L += ["", f"YOUR RECENT LIVE PICKS ({wins}/{nres} closed green) — the realized record:"]
        for d, sym, arch, o in rec:
            L.append(f"  {d} {sym:6} [{arch}] -> {o:+.2f}%" if o is not None else
                     f"  {d} {sym:6} [{arch}] -> (open)")
    L += [
         f"SCAN TIME: {scan_label} — {mins_left} min ({mins_left/60:.1f}h) until the 16:00 ET close.",
         "  OBJECTIVE: you enter now and exit by 16:00 ET — maximize the position's P&L at the",
         "  close. Every number below is a RAW FACT as of now. What makes a good entry, which",
         "  signals matter, whether/when to act or abstain — reason it out yourself from the data",
         "  (and query history via scripts/ai_trader_data.sh if a fact would help). Nothing here",
         "  prescribes a setup.",
         f"prior VIX {macro.get('vix_prior')} | macro/fed/geo sentiment {macro.get('macro_sent')} | "
         f"regime {macro.get('spy_regime_prior')}",
         "", "MACRO — recent negative-leaning headlines (sentiment score, raw):"]
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
    # Third slice = the highest relative-volume names not already shown above, so a name that's
    # extreme on neither gap nor gain but is trading unusual volume isn't invisible. Neutral:
    # ranked by rv, no threshold, no direction filter — the AI decides what the volume means.
    shown = {m.sym for m in down_focus + up_focus}
    vol_reclaim = sorted([m for m in movers if m.sym not in shown and m.rel_vol is not None],
                         key=lambda m: -(m.rel_vol or 0))[:8]
    anews = _alpaca_news([m.sym for m in down_focus + up_focus + vol_reclaim])  # catalysts pre-fetched
    L += ["", f"THE FIELD — {len(movers)} liquid movers ({len(gapped_down)} gapped down). Below are "
          f"three RAW slices ({len(down_focus)} by gap, {len(up_focus)} by gain, {len(vol_reclaim)} "
          "by volume); the full field is far larger — query it if you want more.",
          "  COLUMN DEFINITIONS (raw facts, no interpretation): now = % vs 09:30 open. "
          "pk/low = highest/lowest % vs open so far; off = now−pk; up = now−low. Δ10m = % change "
          "over the last ~10 min (n/a if <11 bars). vwap = % of price vs session VWAP. rv = "
          "today's volume so far ÷ its time-adjusted 20d average. gap = % vs prev close."]
    for label, group in (("GAPPED DOWN vs prev close (largest gap first)", down_focus),
                         ("UP FROM OPEN (largest gain first)", up_focus),
                         ("HIGHEST RELATIVE VOLUME among names not shown above", vol_reclaim)):
        L.append(f"\n {label}:")
        for m in group:
            gap = f"{(m.price/m.prev_close-1)*100:+.1f}%" if m.prev_close else "?"
            # momentum trajectory AS OF NOW: peak/low + how far off — a name now far below
            # its peak has already SPENT its move (the ABT trap); one now far above its low
            # is freshly reclaiming. Judge buyability from the CURRENT price, not the level.
            rv = f"{m.rel_vol:.1f}x" if m.rel_vol is not None else "?"
            sl = f"{m.slope10:+.1f}" if m.slope10 is not None else "n/a"
            L.append(f"  {m.sym:6} now{m.pct_change:+6.1f}% [pk{m.peak_pct:+.1f} off{m.off_peak:+.1f} | "
                     f"low{m.trough_pct:+.1f} up{m.off_trough:+.1f}] Δ10m{sl} "
                     f"vwap{m.vwap_dist:+.1f} rv{rv} ${m.price:.2f} gap{gap} {_sector(p, m.sym)}")
            an = anews.get(m.sym)
            if an:
                for when, h, summ in an:
                    L.append(f"        [{when}] {h}")
                    if summ:
                        L.append(f"           {summ}")
            else:
                nw = _news(p, m.sym, date)
                L.append(f"        [{nw[0][1]}] {nw[0][2][:74]}" if nw else "        (no news found)")
    L += ["", "DECIDE -> write plans/decisions/<date>.json (archetype + picks + exit + reason, or abstain)."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=100)
    print(build(ap.parse_args().date, top=ap.parse_args().top))


if __name__ == "__main__":
    main()
