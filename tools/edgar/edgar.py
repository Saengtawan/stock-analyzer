"""tools/edgar/edgar.py — pull the authoritative filing from SEC EDGAR (FREE, open API, no bot/login).

WHAT: ticker -> CIK -> latest earnings filing (8-K / 6-K Ex-99.1 press release; also reports latest
10-Q/10-K) -> the operating detail behind the headline: GAAP-vs-non-GAAP/ADJUSTED reconciliation,
ONE-TIME-item language (deferred-tax release / impairment / discrete tax = the AFRM $4.62-GAAP-beat trap),
guidance, gross-margin. AUTHORITATIVE source (filed with the SEC), not a wire/aggregator — the raw feed
for the operating-number gate. No Playwright needed: plain HTTPS with SEC's required "name email" UA.

ISOLATION: read-only external fetch, writes to NO system DB, touches nothing in resonance/overnight/
runner/swing. Surfaces RAW extracted text + ref_* flags (references the AI weighs, NOT gates).

CLI:  ~/.pyenv/versions/cc/bin/python -m tools.edgar.edgar AFRM NIO
Import: from tools.edgar.edgar import fetch_edgar; rows = fetch_edgar(["AFRM"])
"""
from __future__ import annotations
import urllib.request, json, os, re, sys

# SEC fair-use: UA must be a descriptive name + contact email (a browser UA gets 403). Generic contact.
_UA = {"User-Agent": os.environ.get("SEC_UA", "stock-analyzer-research contact@example.com")}
_EARNINGS_FORMS = ("8-K", "6-K")            # earnings press release (Ex-99.1) lives here
_PERIODIC_FORMS = ("10-Q", "10-K", "20-F", "40-F")
ONETIME = ["one-time", "one time", "valuation allowance", "deferred tax", "impairment",
           "gain on", "settlement", "release of", "non-recurring", "nonrecurring", "discrete tax"]


def _get(url, as_json=False, timeout=30):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read().decode("utf-8", "replace")
    return json.loads(data) if as_json else data


def _cik_map():
    tk = _get("https://www.sec.gov/files/company_tickers.json", as_json=True)
    return {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in tk.values()}


def _strip_html(html):
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = text.replace("&#160;", " ").replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", text)).strip()


def _grab(text, pattern, length):
    m = re.search(pattern, text, re.I)
    return re.sub(r"\s+", " ", text[m.start():m.start() + length]).strip() if m else None


def _doc_url_for(cik, acc, primary, prefer_pr=False):
    """Build the best document URL in an accession folder. prefer_pr=True hunts the earnings
    press-release/shareholder-letter exhibit; else use the primary document. Returns (url, image_based)."""
    cik_int = str(int(cik))
    folder = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc.replace('-', '')}/"
    if not prefer_pr:
        return folder + primary, False
    try:
        idx = _get(folder + "index.json", as_json=True)
        items = idx.get("directory", {}).get("item", [])
        htms = [(it["name"], int(it.get("size", 0) or 0)) for it in items
                if it["name"].lower().endswith((".htm", ".html"))
                and not re.search(r"index|filingsummary|^r\d+\.htm|_htm\.xml", it["name"], re.I)]
        n_jpg = sum(1 for it in items if it["name"].lower().endswith((".jpg", ".png", ".gif")))
        # prefer a press-release/letter/earnings exhibit; else the largest content htm
        pr = [h for h in htms if re.search(r"ex[-_]?99|shareholder|letter|earning|press|result|financ", h[0], re.I)]
        pick = max(pr or htms, key=lambda h: h[1]) if (pr or htms) else (primary, 0)
        name, size = pick if isinstance(pick, tuple) else (pick, 0)
        image_based = bool(size < 12000 and n_jpg >= 5)   # tiny htm + many images = image-based letter
        return folder + name, image_based
    except Exception:
        return folder + primary, False


# AS-OF CUTOFF for replays. EDGAR's submissions feed is a LIVE index: "the latest filing" always
# resolves to the real current date, so replaying a past morning surfaces filings from days that had
# not happened yet. Three replay agents hit this and disclosed it — one was handed an 8-K dated three
# sessions after the morning it was deciding. Unset (the live path) nothing changes and the newest
# filing is used, which is correct at 09:00 on the real day. The replay harness sets EDGAR_AS_OF to
# the session date and every filing accepted after it is skipped.
def _as_of():
    v = (os.environ.get("EDGAR_AS_OF") or "").strip()
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None


def _find_filings(cik):
    """Return dicts for the latest earnings (8-K/6-K) and latest periodic (10-Q/10-K/20-F).

    Honours EDGAR_AS_OF: filings dated after it are ignored (see the note above)."""
    sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json", as_json=True)
    rec = sub["filings"]["recent"]
    forms, dates, accs, docs = rec["form"], rec["filingDate"], rec["accessionNumber"], rec["primaryDocument"]
    cutoff = _as_of()
    earnings = periodic = None
    for i, f in enumerate(forms):
        if cutoff and dates[i] and dates[i] > cutoff:
            continue
        if earnings is None and f in _EARNINGS_FORMS:
            earnings = (f, dates[i], accs[i], docs[i])
        if periodic is None and f in _PERIODIC_FORMS:
            periodic = (f, dates[i], accs[i], docs[i])
        if earnings and periodic:
            break
    return earnings, periodic


def fetch_edgar(tickers, timeout=40):
    """Return list of dicts per ticker with the extracted operating detail + ref_* flags."""
    if not tickers:
        return []
    try:
        cmap = _cik_map()
    except Exception as e:
        return [{"sym": t.upper(), "ok": False, "error": f"cik map: {e}"} for t in tickers]
    out = []
    for t in tickers:
        rec = {"sym": t.upper(), "ok": False}
        try:
            cik = cmap.get(t.upper())
            if not cik:
                rec["error"] = "ticker not in EDGAR (foreign/ADR may differ)"
                out.append(rec); continue
            rec["cik"] = cik
            earnings, periodic = _find_filings(cik)
            rec["latest_periodic"] = f"{periodic[0]} {periodic[1]}" if periodic else None

            def extract(text):
                return dict(
                    guidance=_grab(text, r"(Business Outlook|Outlook\b|guidance|For the (?:first|second|third|fourth) quarter[^\n]*expect|expect[^\n]{0,40}(?:revenue|earnings|deliveries))", 500),
                    margin=_grab(text, r"gross margin[^\n.]{0,180}", 200),
                    nongaap=_grab(text, r"adjusted[^\n]{0,60}(?:non-GAAP|\(non-GAAP\))[^\n.]{0,160}", 240) or _grab(text, r"non-GAAP[^\n.]{0,200}", 220),
                    onetime_hits=[k for k in ONETIME if k in text.lower()])

            used = None
            if earnings:
                f, d, acc, primary = earnings
                url, image_based = _doc_url_for(cik, acc, primary, prefer_pr=True)
                text = _strip_html(_get(url))
                ex = extract(text)
                # earnings PR usable only if it's real text (not an image-based letter / thin cover)
                if not image_based and len(text) > 1500 and any([ex["guidance"], ex["nongaap"], ex["onetime_hits"]]):
                    used = (f, d, url, ex, len(text), "earnings-PR")
                else:
                    rec["note"] = "earnings PR image-based/thin — using periodic filing text"
            if used is None and periodic:
                f, d, acc, primary = periodic
                url, _ = _doc_url_for(cik, acc, primary, prefer_pr=False)
                text = _strip_html(_get(url))
                used = (f, d, url, extract(text), len(text), "periodic")
            if used:
                f, d, url, ex, n, src = used
                rec.update(form=f, filing_date=d, doc_url=url, chars=n, source=src, **ex)
                rec["ok"] = n > 800
            rec["ref_guidance_present"] = bool(rec.get("guidance"))
            rec["ref_has_nongaap"] = bool(rec.get("nongaap"))
            rec["ref_onetime_item"] = bool(rec.get("onetime_hits"))
        except Exception as e:
            rec["error"] = str(e)[:120]
        out.append(rec)
    return out


def _fmt(rec):
    if not rec.get("ok"):
        return f"  {rec['sym']:6} — no data ({rec.get('error') or 'n/a'})"
    lines = [f"  {rec['sym']:6} {rec.get('form')} {rec.get('filing_date')}  [source: {rec.get('source')}]  (latest periodic: {rec.get('latest_periodic')})"]
    if rec.get("note"):
        lines.append(f"    ⚑ {rec['note']}")
    lines.append(f"    {rec.get('doc_url')}")
    if rec.get("ref_onetime_item"):
        lines.append(f"    🚨 one-time-item language: {', '.join(rec['onetime_hits'])}  → verify GAAP vs adjusted")
    if rec.get("nongaap"):
        lines.append(f"    non-GAAP: {rec['nongaap'][:200]}")
    if rec.get("margin"):
        lines.append(f"    margin:   {rec['margin'][:160]}")
    if rec.get("guidance"):
        lines.append(f"    guidance: {rec['guidance'][:260]}")
    return "\n".join(lines)


if __name__ == "__main__":
    syms = sys.argv[1:]
    if not syms:
        print("usage: python -m tools.edgar.edgar AFRM NIO ...", file=sys.stderr); sys.exit(2)
    rows = fetch_edgar(syms)
    print("SEC EDGAR (authoritative filing) — REFERENCE, not gates:")
    for rec in rows:
        print(_fmt(rec))
    print(json.dumps(rows))
