"""Pre-open context gatherer.

Collects the qualitative + regime inputs the AI layer reads BEFORE the open.
Everything here is knowable pre-09:30 (news with market_session in pre/overnight,
prior-day macro snapshot) — no lookahead.

Works for both live (today's premarket news) and replay (a historical date).
"""
from __future__ import annotations
import sqlite3
from statistics import mean

DB = "data/trade_history.db"
MACRO_CATS = ("macro", "fed", "geo")


def gather_preopen(date: str, db: str = DB) -> dict:
    """Return the pre-open context dict for `date`."""
    p = sqlite3.connect(db)
    rows = p.execute(
        "SELECT category, sentiment_score, impact_score, headline, symbol "
        "FROM news_events WHERE scan_date_et=? "
        "AND market_session IN ('pre','overnight')", (date,)).fetchall()

    macro = [s for cat, s, imp, h, sym in rows if cat in MACRO_CATS and s is not None]
    all_sent = [s for cat, s, imp, h, sym in rows if s is not None]
    # the actual bad-macro headlines, so the AI slot can READ them (not just avg)
    macro_neg = sorted(
        [(round(s, 3), round(imp or 0, 2), h) for cat, s, imp, h, sym in rows
         if cat in MACRO_CATS and s is not None and s < -0.2 and (imp or 0) >= 0.5],
        key=lambda x: x[0])[:10]

    m = p.execute(
        "SELECT date, vix_close, vix3m_close, spy_regime, yield_spread "
        "FROM macro_snapshots WHERE date < ? AND spy_close IS NOT NULL "
        "ORDER BY date DESC LIMIT 1", (date,)).fetchone()

    return {
        "date": date,
        "n_news": len(rows),
        "macro_sent": round(mean(macro), 3) if macro else None,
        "n_macro": len(macro),
        "macro_neg_headlines": macro_neg,          # [(sent, impact, headline), ...]
        "pre_sent": round(mean(all_sent), 3) if all_sent else None,
        "vix_prior": m[1] if m else None,
        "vix_term_prior": (m[1] - m[2]) if (m and m[1] and m[2]) else None,
        "spy_regime_prior": m[3] if m else None,
        "yield_spread_prior": m[4] if m else None,
    }
