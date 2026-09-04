"""Context brief — the FULL situational package the AI reasons over each morning.

The lesson that cost us: crude price-bucketing (SPY red/green, gain 2-6%, gap depth)
throws away the context that actually drives outcomes. The same price setup is +1.27
in one regime and -0.29 in another — the difference lives in the NEWS / narrative /
per-stock story, which a rule can't see but the AI can.

So this assembles, for the day's candidates: the price setup + every stock's recent
news (DB) + the macro narrative. Names with no DB news are flagged for live web-search.
The AI (a Claude session) reads this and judges like a trader — the price setups are
PRIORS it weighs in context, not rigid gates.
"""
from __future__ import annotations
import argparse, sqlite3
from .live_candidates import from_dump
from .premarket import gather_preopen

DB = "data/trade_history.db"


def _recent_news(p, sym, date, days=4):
    rows = list(p.execute(
        "SELECT scan_date_et, sentiment_label, headline FROM news_events "
        "WHERE symbol=? AND scan_date_et<=? AND scan_date_et>=date(?, '-%d day') "
        "ORDER BY published_at DESC LIMIT 3" % days, (sym, date, date)))
    return rows


def build(date, min_gain=2.0, max_gain=6.0, gap_max=-0.5):
    cands, ctx = from_dump(date)
    p = sqlite3.connect(DB)
    macro = gather_preopen(date)

    L = [f"=== CONTEXT BRIEF {date} ===",
         f"tape: SPY {ctx.spy_morning:+.2f}% at 09:36 | prior VIX {macro.get('vix_prior')} | "
         f"macro/fed/geo sentiment {macro.get('macro_sent')}",
         "",
         "MACRO NARRATIVE (why the tape is where it is):"]
    for s, imp, h in (macro.get("macro_neg_headlines") or [])[:6]:
        L.append(f"  [{s:+.2f}] {h}")
    if not macro.get("macro_neg_headlines"):
        L.append("  (no negative macro flagged)")

    # Show the FIELD, not a crude pre-crushed bucket. Everything that gapped down
    # (gap<0) is context the AI should weigh; the "classic" band (gain 2-6%, gap<-0.5)
    # is annotated as a PRIOR, not used to exclude. The AI decides what's interesting.
    field = sorted([c for c in cands if c.gap < 0], key=lambda c: c.gap)
    L += ["", f"THE FIELD — {len(field)} gapped-down movers (read each STORY, not just numbers):",
          "   ★ = fits the gap-down-reversal prior (gain 2-6%, gap<-0.5) — a hint, not a gate"]
    for c in field:
        star = "★" if (min_gain <= c.gain < max_gain and c.gap <= gap_max) else " "
        news = _recent_news(p, c.sym, date)
        L.append(f" {star}{c.sym:6} gain{c.gain:+.1f}% gap{c.gap:+.1f}% ${c.dollar_vol/1e6:.0f}M {c.sector}")
        if news:
            for d, lab, h in news:
                L.append(f"        [{d} {lab}] {h[:78]}")
        else:
            L.append(f"        (no DB news -> web-search 'why is {c.sym} down/gapping today')")
    if not field:
        L.append("   (nothing gapped down in the dump today)")
    L += ["",
          "JUDGE (like a trader, in context):",
          " - Is the tape weakness a real risk-off (war/rate/inflation) or a shakeable dip?",
          " - For each name: did it gap down on real idiosyncratic bad news in a healthy",
          "   context (buyers step in = reversal), or is it junk / a falling knife?",
          " - Pick the genuine reversals (or abstain). Write plans/name_verdicts/<date>.json",
          "   and, if the whole day is risk-off, plans/llm_verdicts.json."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    print(build(ap.parse_args().date))


if __name__ == "__main__":
    main()
