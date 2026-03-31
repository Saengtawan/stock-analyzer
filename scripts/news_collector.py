#!/usr/bin/env python3
"""
news_collector.py — v1.0
=========================
Collect financial news from:
  1. Alpaca News API  — per-symbol + general market
  2. Federal Reserve RSS — FOMC/rate decisions
  3. SEC EDGAR — 8-K material event filings

Classifies: category, event_type, sectors_affected
Scores: sentiment (VADER), impact

Cron schedule (TZ=America/New_York — auto-handles EDT/EST DST):
  30  5 * * 2-6  --mode symbol    # 5:30 AM ET Tue-Sat (after previous day close)
  0  14 * * 1-5  --mode pre_scan  # 2:00 PM ET Mon-Fri (before OVN scan at 3:45 PM)
  0  */2 * * *   --mode macro     # every 2h (Bangkok TZ, timezone-independent)

Usage:
  python3 scripts/news_collector.py                       # all modes
  python3 scripts/news_collector.py --mode symbol         # per-symbol only
  python3 scripts/news_collector.py --mode macro          # RSS + general only
  python3 scripts/news_collector.py --mode pre_scan       # pre-scan bundle
  python3 scripts/news_collector.py --backfill 2026-02-01 # historical fill
  python3 scripts/news_collector.py --dry-run             # preview counts
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import feedparser
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# -- Paths --
_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(_DIR, '..', '.env')

ET_ZONE  = ZoneInfo('America/New_York')
UTC_ZONE = ZoneInfo('UTC')

# -- Load env --
def _load_env() -> dict:
    env = {}
    try:
        for line in open(ENV_PATH):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env

ENV = _load_env()
ALPACA_KEY    = ENV.get('ALPACA_API_KEY', '')
ALPACA_SECRET = ENV.get('ALPACA_SECRET_KEY', '')

# -- Constants --
ALPACA_NEWS_URL = 'https://data.alpaca.markets/v1beta1/news'
FED_RSS_URL     = 'https://www.federalreserve.gov/feeds/press_all.xml'
SEC_EDGAR_URL   = 'https://efts.sec.gov/LATEST/search-index'
SEC_USER_AGENT  = 'StockAnalyzer/1.0 research@localhost'

VADER = SentimentIntensityAnalyzer()

# -- Classification tables --
SECTOR_KEYWORDS: dict[str, list[str]] = {
    'Technology':       ['tech', 'software', 'cloud', 'ai ', 'artificial intelligence',
                         'saas', 'cybersecurity', 'data center'],
    'Semiconductors':   ['semiconductor', 'chip', 'wafer', 'tsmc', 'nvidia', 'amd',
                         'intel', 'arm holdings', 'foundry'],
    'Financial Services':['bank', 'fed ', 'federal reserve', 'interest rate', 'jpmorgan',
                          'goldman', 'hedge fund', 'treasury', 'bond yield', 'credit',
                          'mortgage', 'insurance', 'fintech'],
    'Energy':           ['oil', 'crude', 'opec', 'petroleum', 'natural gas', 'lng',
                         'refinery', 'energy price', 'shale'],
    'Healthcare':       ['fda', 'drug', 'pharma', 'biotech', 'clinical trial', 'vaccine',
                         'hospital', 'health insurance', 'medicare'],
    'Consumer Cyclical':['retail', 'consumer spending', 'walmart', 'amazon', 'holiday sales',
                         'discretionary', 'auto sales'],
    'Industrials':      ['manufacturing', 'industrial', 'aerospace', 'defense', 'boeing',
                         'tariff', 'trade war', 'supply chain', 'factory'],
    'Materials':        ['steel', 'aluminum', 'mining', 'metals', 'copper', 'lithium',
                         'commodity', 'raw material'],
    'Real Estate':      ['real estate', 'reit', 'housing', 'home price', 'mortgage rate',
                         'commercial property'],
    'Utilities':        ['utility', 'electric grid', 'renewable', 'solar', 'wind energy',
                         'power plant'],
    'Communication':    ['media', 'streaming', 'telecom', 'broadband', 'social media',
                         'advertising revenue'],
}

EVENT_TYPE_RULES: dict[str, list[str]] = {
    # Macro / Fed
    'fed_rate_decision': ['federal reserve', 'fomc decision', 'interest rate decision',
                          'rate hike', 'rate cut', 'basis points cut', 'basis points hike',
                          'federal funds rate', 'rate unchanged'],
    'fomc_minutes':      ['fomc minutes', 'federal reserve minutes', 'meeting minutes',
                          'minutes of the'],
    'fomc_speech':       ['fed chair', 'jerome powell', 'fed president speaks',
                          'federal reserve bank of', 'fed governor', 'waller', 'jefferson',
                          'daly', 'barkin', 'bostic', 'kugler', 'cook'],
    'inflation_data':    ['cpi', 'consumer price index', 'inflation rate', 'pce',
                          'personal consumption expenditure', 'core inflation'],
    'jobs_report':       ['nonfarm payroll', 'unemployment rate', 'jobs report',
                          'labor department', 'jobless claims', 'adp employment'],
    'gdp_data':          ['gdp', 'gross domestic product', 'economic growth'],
    # Geo
    'geo_tariff':        ['tariff', 'import tax', 'trade war', 'trade deal',
                          'trade sanction', 'export ban', 'trade restriction'],
    'geo_conflict':      [' war ', 'military conflict', 'geopolitical tension',
                          'invasion', 'sanction', 'escalation'],
    # SEC / Regulatory
    'sec_8k':            ['8-k', 'sec filing', 'material event', 'form 8-k'],
    'regulatory_approval': ['fda approves', 'fda clears', 'fda granted', 'fda accepts',
                             'ce mark', 'ema recommends', 'ema approves', 'approved by',
                             'clearance granted', 'breakthrough designation', 'nda ', 'bla ',
                             'priority review', 'accelerated approval'],
    # Earnings — expanded to catch all common headline patterns
    'earnings_report':   ['earnings', 'quarterly results', 'q1 results', 'q2 results',
                          'q3 results', 'q4 results', 'full year results',
                          'eps beat', 'eps miss', ' eps ', 'adj. eps', 'adjusted eps',
                          'gaap eps', 'per share', 'beats estimate', 'misses estimate',
                          'beats $', 'misses $', ' beats ', ' misses ',
                          'revenue beat', 'revenue miss', 'sales beat', 'sales miss',
                          'guidance raised', 'guidance cut', 'guidance lowered',
                          'raises guidance', 'lowers guidance', 'sees fy', 'sees q1',
                          'sees q2', 'sees q3', 'sees q4', 'raises forecast',
                          'analyst forecast', 'analysts revise', 'analysts boost',
                          'analysts increase their forecast', 'revise their forecast'],
    # Analyst / price target actions
    'analyst_action':    ['price target', 'raises pt', 'lowers pt', 'pt to $',
                          'initiates coverage', 'initiates at', 'upgrades to buy',
                          'upgrades to outperform', 'downgrades to sell', 'downgrades to hold',
                          'downgrades to neutral', 'maintains buy', 'maintains sell',
                          'maintains hold', 'maintains neutral', 'maintains outperform',
                          'maintains underperform', 'overweight', 'underweight',
                          'outperform', 'market perform', 'buy rating', 'sell rating',
                          'bullish on', 'bearish on', 'raises price target', 'lowers price target'],
    # M&A / Corporate events
    'merger_acquisition': ['acquires', 'acquisition', 'merger', 'to buy ', 'takeover',
                            'buyout', 'deal to buy', 'deal valued', 'deal worth',
                            'to acquire', 'goes private', 'take-private', 'agreed to buy',
                            'agreed to acquire', 'completes acquisition', 'divests',
                            'sells unit', 'sells division', 'spinoff', 'spin-off'],
    'corporate_action':  ['buyback', 'share repurchase', 'stock repurchase', 'dividend',
                          'special dividend', 'stock split', 'reverse split',
                          'rights offering', 'secondary offering', 'follow-on offering',
                          'names new ceo', 'appoints ceo', 'ceo resigns', 'ceo steps down',
                          'cfo resigns', 'board appoints', 'names ', ' coo ', ' cfo ',
                          'depositary bank', 'adr program'],
    # Sector / product updates
    'product_launch':    ['launches', 'unveils', 'announces new', 'introduces',
                          'new product', 'new platform', 'new service', 'available now'],
    'sector_update':     ['deliveries', 'delivery numbers', 'monthly sales', 'shipments',
                          'production data', 'inventory data',
                          'reported delivery', 'reported deliveries', 'delivery of ',
                          'vehicles in ', 'units in january', 'units in february',
                          'units in march', 'cumulative deliveries'],
    'partnership':       ['partners with', 'partnership with', 'joint venture',
                          'collaboration with', 'strategic alliance', 'teams up with',
                          'agreement with', 'selects ', 'awarded contract', 'wins contract'],
}

CATEGORY_MAP: dict[str, list[str]] = {
    'fed':      ['federal reserve', 'fomc', 'rate hike', 'rate cut', 'powell',
                 'fed chair', 'federal funds'],
    'macro':    ['gdp', 'inflation', 'cpi', 'pce', 'jobs report', 'payroll',
                 'unemployment', 'economic growth', 'recession', 'treasury'],
    'geo':      ['tariff', 'trade war', 'war', 'conflict', 'geopolit',
                 'sanction', 'ukraine', 'taiwan', 'china trade'],
    'earnings': ['earnings', 'quarterly', 'eps', 'revenue', 'guidance',
                 'results', 'beats', 'misses'],
    'sector':   ['sector', 'industry', 'oil price', 'chip shortage', 'supply chain'],
    'company':  [],  # fallback for symbol-specific news
}


# -- Helpers --

def _content_hash(headline: str, published_at: str) -> str:
    return hashlib.md5(f"{headline}|{published_at}".encode()).hexdigest()


def _parse_utc(dt_str: str) -> datetime | None:
    """Parse ISO8601 or RFC2822 string -> aware UTC datetime."""
    if not dt_str:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z',
                '%a, %d %b %Y %H:%M:%S %Z', '%a, %d %b %Y %H:%M:%S %z'):
        try:
            dt = datetime.strptime(dt_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC_ZONE)
            return dt.astimezone(UTC_ZONE)
        except ValueError:
            pass
    return None


def _scan_date_et(published_utc: datetime) -> str:
    """
    Return the ET trading date that would first 'see' this news.
    News after 16:00 ET -> next business day.
    """
    et = published_utc.astimezone(ET_ZONE)
    d = et.date()
    if et.hour >= 16:
        d += timedelta(days=1)
        # skip weekends
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return d.isoformat()


def _market_session(published_utc: datetime) -> str:
    et = published_utc.astimezone(ET_ZONE)
    h = et.hour + et.minute / 60
    if 4.0 <= h < 9.5:
        return 'pre'
    elif 9.5 <= h < 16.0:
        return 'regular'
    elif 16.0 <= h < 20.0:
        return 'post'
    else:
        return 'overnight'


def _classify_event_type(txt: str, category: str | None = None) -> str | None:
    lower = txt.lower()
    for etype, keywords in EVENT_TYPE_RULES.items():
        if any(kw in lower for kw in keywords):
            return etype
    # Category-based fallback when no keyword matched
    _fallback = {
        'earnings': 'earnings_report',
        'fed':      'fed_announcement',
        'geo':      'geo_policy',
        'macro':    'macro_data',
        'sector':   'sector_update',
    }
    return _fallback.get(category or '', None)


def _classify_category(txt: str, symbol: str | None) -> str:
    lower = txt.lower()
    for cat, keywords in CATEGORY_MAP.items():
        if keywords and any(kw in lower for kw in keywords):
            return cat
    return 'company' if symbol else 'sector'


def _extract_sectors(txt: str) -> str | None:
    lower = txt.lower()
    found = [s for s, kws in SECTOR_KEYWORDS.items() if any(kw in lower for kw in kws)]
    return json.dumps(found) if found else None


def _sentiment(headline: str, summary: str | None = None) -> tuple[float, str]:
    txt = headline
    if summary:
        txt = headline + ' ' + summary[:200]
    scores = VADER.polarity_scores(txt)
    c = scores['compound']
    label = 'positive' if c >= 0.05 else ('negative' if c <= -0.05 else 'neutral')
    return round(c, 3), label


def _impact_score(source: str, category: str | None, event_type: str | None) -> float:
    base = {'alpaca': 0.5, 'rss_fed': 0.8, 'sec_edgar': 0.7}.get(source, 0.4)
    cat_boost = {'fed': 0.3, 'macro': 0.2, 'earnings': 0.2, 'geo': 0.15}.get(category or '', 0)
    etype_boost = {
        'fed_rate_decision': 0.2, 'inflation_data': 0.1, 'jobs_report': 0.1,
        'geo_conflict': 0.1, 'earnings_report': 0.1,
    }.get(event_type or '', 0)
    return round(min(1.0, base + cat_boost + etype_boost), 2)


def _market_context(session, published_at: str) -> tuple[float | None, float | None]:
    """Lookup nearest VIX + SPY price from intraday_snapshots."""
    try:
        pub_dt = _parse_utc(published_at)
        if not pub_dt:
            return None, None
        # Convert to ET for date + time_et matching
        et = pub_dt.astimezone(ET_ZONE)
        date_str = et.strftime('%Y-%m-%d')

        row = session.execute(text("""
            SELECT price FROM intraday_snapshots
            WHERE symbol = '^VIX' AND date = :p0
            ORDER BY ABS(CAST(SUBSTR(time_et,1,2) AS INT)*60 + CAST(SUBSTR(time_et,4,2) AS INT)
                       - :p1) ASC
            LIMIT 1
        """), {'p0': date_str, 'p1': int(et.hour)*60 + int(et.minute)}).fetchone()
        vix = float(row[0]) if row else None

        row = session.execute(text("""
            SELECT price FROM intraday_snapshots
            WHERE symbol = 'SPY' AND date = :p0
            ORDER BY ABS(CAST(SUBSTR(time_et,1,2) AS INT)*60 + CAST(SUBSTR(time_et,4,2) AS INT)
                       - :p1) ASC
            LIMIT 1
        """), {'p0': date_str, 'p1': int(et.hour)*60 + int(et.minute)}).fetchone()
        spy = float(row[0]) if row else None

        return vix, spy
    except Exception:
        return None, None


def _insert_news(session, rows: list[dict], dry_run: bool = False) -> int:
    """Insert news rows, skipping duplicates. Returns count inserted."""
    if not rows or dry_run:
        return len(rows)
    inserted = 0
    for row in rows:
        try:
            session.execute(text("""
                INSERT OR IGNORE INTO news_events
                    (published_at, collected_at, market_session, scan_date_et,
                     source, source_id, url,
                     symbol, symbols_mentioned, headline, summary,
                     category, event_type, sectors_affected,
                     sentiment_score, sentiment_label, impact_score,
                     vix_at_time, spy_price_at_time,
                     raw_json, content_hash)
                VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14,:p15,:p16,:p17,:p18,:p19,:p20)
            """), {
                'p0': row.get('published_at'), 'p1': row.get('collected_at'), 'p2': row.get('market_session'),
                'p3': row.get('scan_date_et'),
                'p4': row.get('source'), 'p5': row.get('source_id'), 'p6': row.get('url'),
                'p7': row.get('symbol'), 'p8': row.get('symbols_mentioned'),
                'p9': row.get('headline'), 'p10': row.get('summary'),
                'p11': row.get('category'), 'p12': row.get('event_type'), 'p13': row.get('sectors_affected'),
                'p14': row.get('sentiment_score'), 'p15': row.get('sentiment_label'), 'p16': row.get('impact_score'),
                'p17': row.get('vix_at_time'), 'p18': row.get('spy_price_at_time'),
                'p19': row.get('raw_json'), 'p20': row.get('content_hash'),
            })
            # Check if row was actually inserted (changes() for SQLite)
            chg = session.execute(text('SELECT changes()')).fetchone()[0]
            if chg:
                inserted += 1
        except Exception as e:
            pass
    return inserted


# -- Source 1: Alpaca News --

def collect_alpaca(session, symbols: list[str] | None = None,
                   start: str = None, end: str = None,
                   dry_run: bool = False) -> int:
    """
    Collect Alpaca news. If symbols=None -> general market news.
    start/end: YYYY-MM-DD ET dates.
    """
    if not ALPACA_KEY:
        print("  [alpaca] No API key — skipping")
        return 0

    headers = {'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET}
    collected_at = datetime.now(UTC_ZONE).isoformat()
    total = 0

    # Build symbol batches (max 10 per request to stay under rate limit)
    batches: list[list[str] | None] = []
    if symbols:
        for i in range(0, len(symbols), 10):
            batches.append(symbols[i:i+10])
    else:
        batches = [None]  # one batch for general news

    for batch in batches:
        params: dict = {'limit': 50}
        if batch:
            params['symbols'] = ','.join(batch)
        if start:
            params['start'] = f"{start}T00:00:00Z"
        if end:
            params['end'] = f"{end}T23:59:59Z"

        page_token = None
        pages = 0
        while pages < 20:  # max 20 pages per batch
            if page_token:
                params['page_token'] = page_token

            try:
                r = requests.get(ALPACA_NEWS_URL, headers=headers, params=params, timeout=15)
                if r.status_code == 429:
                    time.sleep(30)
                    continue
                if not r.ok:
                    break
                data = r.json()
            except Exception as e:
                print(f"  [alpaca] fetch error: {e}")
                break

            news_list = data.get('news', [])
            if not news_list:
                break

            news_rows = []
            for n in news_list:
                headline = n.get('headline', '').strip()
                if not headline:
                    continue
                pub_str  = n.get('created_at', '')
                pub_dt   = _parse_utc(pub_str)
                if not pub_dt:
                    continue

                syms_mentioned = n.get('symbols', [])
                if batch:
                    batch_sym = next((s for s in batch if s in syms_mentioned), None)
                    sym = batch_sym or (syms_mentioned[0] if syms_mentioned else None)
                elif len(syms_mentioned) == 1:
                    sym = syms_mentioned[0]
                else:
                    sym = None

                summary = (n.get('summary') or n.get('content') or '')[:500]
                sent_score, sent_label = _sentiment(headline, summary)
                category  = _classify_category(headline + ' ' + summary, sym)
                event_type = _classify_event_type(headline + ' ' + summary, category)
                sectors    = _extract_sectors(headline + ' ' + (summary or ''))
                vix, spy   = _market_context(session, pub_str)

                news_rows.append({
                    'published_at':    pub_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'collected_at':    collected_at,
                    'market_session':  _market_session(pub_dt),
                    'scan_date_et':    _scan_date_et(pub_dt),
                    'source':          'alpaca',
                    'source_id':       str(n.get('id', '')),
                    'url':             n.get('url', ''),
                    'symbol':          sym,
                    'symbols_mentioned': json.dumps(syms_mentioned) if syms_mentioned else None,
                    'headline':        headline,
                    'summary':         summary or None,
                    'category':        category,
                    'event_type':      event_type,
                    'sectors_affected': sectors,
                    'sentiment_score': sent_score,
                    'sentiment_label': sent_label,
                    'impact_score':    _impact_score('alpaca', category, event_type),
                    'vix_at_time':     vix,
                    'spy_price_at_time': spy,
                    'raw_json':        json.dumps(n),
                    'content_hash':    _content_hash(headline, pub_str),
                })

            n_ins = _insert_news(session, news_rows, dry_run)
            total += n_ins

            page_token = data.get('next_page_token')
            if not page_token:
                break
            pages += 1
            time.sleep(0.3)  # 200 req/min -> ~3 req/s safe

        time.sleep(0.2)  # between batches

    return total


# -- Source 2: Federal Reserve RSS --

def collect_fed_rss(session, dry_run: bool = False) -> int:
    """Collect Federal Reserve press releases from RSS feed."""
    collected_at = datetime.now(UTC_ZONE).isoformat()
    feed = feedparser.parse(FED_RSS_URL)

    if not feed.entries:
        print("  [fed_rss] No entries")
        return 0

    news_rows = []
    for entry in feed.entries:
        headline = entry.get('title', '').strip()
        if not headline:
            continue

        pub_str = entry.get('published', entry.get('updated', ''))
        pub_dt  = _parse_utc(pub_str)
        if not pub_dt:
            continue

        summary = entry.get('summary', '')[:500]
        sent_score, sent_label = _sentiment(headline, summary)
        event_type = _classify_event_type(headline + ' ' + summary, 'fed')
        if event_type is None:
            event_type = 'fed_announcement'
        vix, spy = _market_context(session, pub_dt.isoformat())

        news_rows.append({
            'published_at':    pub_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'collected_at':    collected_at,
            'market_session':  _market_session(pub_dt),
            'scan_date_et':    _scan_date_et(pub_dt),
            'source':          'rss_fed',
            'source_id':       entry.get('id', entry.get('link', ''))[:200],
            'url':             entry.get('link', ''),
            'symbol':          None,
            'symbols_mentioned': None,
            'headline':        headline,
            'summary':         summary or None,
            'category':        'fed',
            'event_type':      event_type,
            'sectors_affected': json.dumps(['Financial Services']),
            'sentiment_score': sent_score,
            'sentiment_label': sent_label,
            'impact_score':    _impact_score('rss_fed', 'fed', event_type),
            'vix_at_time':     vix,
            'spy_price_at_time': spy,
            'raw_json':        json.dumps(dict(entry)),
            'content_hash':    _content_hash(headline, pub_dt.strftime('%Y-%m-%dT%H:%M:%SZ')),
        })

    n_ins = _insert_news(session, news_rows, dry_run)
    return n_ins


# -- Source 3: SEC EDGAR 8-K --

def collect_sec_8k(session, start: str = None, end: str = None,
                   symbols: list[str] | None = None, dry_run: bool = False) -> int:
    """Collect SEC 8-K material event filings from EDGAR."""
    collected_at = datetime.now(UTC_ZONE).isoformat()
    today = date.today().isoformat()
    start = start or (date.today() - timedelta(days=2)).isoformat()
    end   = end or today

    try:
        r = requests.get(
            'https://efts.sec.gov/LATEST/search-index',
            params={'forms': '8-K', 'dateRange': 'custom', 'startdt': start, 'enddt': end},
            headers={'User-Agent': SEC_USER_AGENT},
            timeout=15,
        )
        if not r.ok:
            print(f"  [sec_edgar] HTTP {r.status_code}")
            return 0
        data = r.json()
    except Exception as e:
        print(f"  [sec_edgar] fetch error: {e}")
        return 0

    hits = data.get('hits', {}).get('hits', [])
    if not hits:
        return 0

    news_rows = []
    for hit in hits:
        src = hit.get('_source', {})
        display_names = src.get('display_names', [])
        display_str = display_names[0] if display_names else ''
        # Extract ticker from "Company Name  (TICK)  (CIK ...)" format
        ticker_match = re.search(r'\(([A-Z]{1,5})\)', display_str)
        ticker = ticker_match.group(1) if ticker_match else ''
        company = re.sub(r'\s+\(.*', '', display_str).strip()
        headline = f"{company} — 8-K Filing" if company else "8-K Filing"
        filed  = src.get('file_date', '')
        if not filed:
            continue

        # Filter by symbols if provided
        if symbols and ticker not in symbols:
            continue

        pub_str = f"{filed}T16:00:00Z"  # 8-Ks filed after market close
        pub_dt  = _parse_utc(pub_str)
        if not pub_dt:
            continue

        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id','')}&type=8-K&dateb=&owner=include&count=5"
        sent_score, sent_label = _sentiment(headline)
        vix, spy = _market_context(session, pub_str)

        news_rows.append({
            'published_at':    pub_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'collected_at':    collected_at,
            'market_session':  'post',
            'scan_date_et':    _scan_date_et(pub_dt),
            'source':          'sec_edgar',
            'source_id':       hit.get('_id', ''),
            'url':             url,
            'symbol':          ticker or None,
            'symbols_mentioned': json.dumps([ticker]) if ticker else None,
            'headline':        headline,
            'summary':         None,
            'category':        'company',
            'event_type':      'sec_8k',
            'sectors_affected': None,
            'sentiment_score': sent_score,
            'sentiment_label': sent_label,
            'impact_score':    _impact_score('sec_edgar', 'company', 'sec_8k'),
            'vix_at_time':     vix,
            'spy_price_at_time': spy,
            'raw_json':        json.dumps(src),
            'content_hash':    _content_hash(headline, pub_str),
        })

    n_ins = _insert_news(session, news_rows, dry_run)
    return n_ins


# -- Symbol list helpers --

def _get_active_symbols(session, days: int = 7) -> list[str]:
    """Symbols from signal_outcomes last N days + currently tracked universe."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = session.execute(text("""
        SELECT DISTINCT symbol FROM signal_outcomes
        WHERE scan_date >= :p0
        UNION
        SELECT symbol FROM active_positions
    """), {'p0': cutoff}).fetchall()
    return [r[0] for r in rows if r[0]]


# -- Backfill --

def backfill(session, start_date: str, dry_run: bool = False):
    """Collect historical news from start_date to today."""
    end_date = date.today().isoformat()
    symbols  = _get_active_symbols(session, days=60)
    print(f"Backfill {start_date} -> {end_date} | {len(symbols)} symbols")

    print("\n[1/3] Alpaca per-symbol news...")
    n = collect_alpaca(session, symbols=symbols, start=start_date, end=end_date, dry_run=dry_run)
    print(f"  inserted: {n}")

    print("\n[2/3] Alpaca general market news...")
    n = collect_alpaca(session, symbols=None, start=start_date, end=end_date, dry_run=dry_run)
    print(f"  inserted: {n}")

    print("\n[3/3] Fed RSS...")
    n = collect_fed_rss(session, dry_run=dry_run)
    print(f"  inserted: {n}")


# -- Modes --

def run_symbol_mode(session, dry_run: bool = False):
    """05:30 BKK — collect per-symbol news for last 2 days."""
    symbols = _get_active_symbols(session, days=7)
    start = (date.today() - timedelta(days=2)).isoformat()
    print(f"[symbol] {len(symbols)} symbols from {start}")
    n = collect_alpaca(session, symbols=symbols, start=start, dry_run=dry_run)
    print(f"  alpaca symbol news: {n} inserted")


def run_macro_mode(session, dry_run: bool = False):
    """Every 2h — collect macro/Fed/SEC news."""
    start = (date.today() - timedelta(days=1)).isoformat()

    print("[macro] Fed RSS...")
    n = collect_fed_rss(session, dry_run=dry_run)
    print(f"  fed_rss: {n} inserted")

    print("[macro] SEC 8-K...")
    n = collect_sec_8k(session, start=start, dry_run=dry_run)
    print(f"  sec_edgar: {n} inserted")

    print("[macro] Alpaca general news...")
    n = collect_alpaca(session, symbols=None, start=start, dry_run=dry_run)
    print(f"  alpaca general: {n} inserted")


def run_pre_scan_mode(session, dry_run: bool = False):
    """21:00 BKK — collect everything before the 21:32 market scan."""
    symbols = _get_active_symbols(session, days=3)
    start = (date.today() - timedelta(days=1)).isoformat()
    print(f"[pre_scan] Collecting fresh news before scan | {len(symbols)} symbols")

    n = collect_alpaca(session, symbols=symbols, start=start, dry_run=dry_run)
    print(f"  alpaca symbol: {n} inserted")
    n = collect_alpaca(session, symbols=None, start=start, dry_run=dry_run)
    print(f"  alpaca general: {n} inserted")
    n = collect_fed_rss(session, dry_run=dry_run)
    print(f"  fed_rss: {n} inserted")


# -- Main --

def main():
    parser = argparse.ArgumentParser(description='News collector v1.0')
    parser.add_argument('--mode', choices=['symbol', 'macro', 'pre_scan', 'all'],
                        default='all', help='Collection mode')
    parser.add_argument('--backfill', metavar='YYYY-MM-DD',
                        help='Historical backfill from date to today')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview counts without writing to DB')
    args = parser.parse_args()

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] news_collector.py starting — mode={args.mode}")

    with get_session() as session:
        if args.backfill:
            backfill(session, args.backfill, args.dry_run)
        elif args.mode == 'symbol':
            run_symbol_mode(session, args.dry_run)
        elif args.mode == 'macro':
            run_macro_mode(session, args.dry_run)
        elif args.mode == 'pre_scan':
            run_pre_scan_mode(session, args.dry_run)
        else:  # all
            run_symbol_mode(session, args.dry_run)
            run_macro_mode(session, args.dry_run)

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] news_collector.py done")


if __name__ == '__main__':
    main()
