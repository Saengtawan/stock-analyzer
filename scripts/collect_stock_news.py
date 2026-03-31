#!/usr/bin/env python3
"""
collect_stock_news.py — v7.8
==============================
Collect per-stock news headlines + sentiment for signal candidates.
Fills stock_news table — answers "was there a catalyst on entry day?"

Coverage:
  - Today's signal_outcomes (all action_taken types)
  - Today's screener_rejections (stocks evaluated by screeners)
  - Last 5 days of BOUGHT signals (context for open positions)

Uses yfinance Ticker.news (Google Finance RSS, free, ~20 articles/symbol).
Sentiment: VADER compound score (-1 very negative, +1 very positive).

Analysis enabled:
  - "Did positive news correlate with better DIP outcomes?"
  - "Did negative news cause early SL hit?"
  - "Was there an analyst upgrade before the move?"
  - "Did earnings-related headlines cause price reaction?"

Cron (TZ=America/New_York):
  40 16 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_stock_news.py >> logs/collect_stock_news.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text as sa_text
import os
import time
import argparse
from datetime import datetime, date, timedelta

import yfinance as yf
from zoneinfo import ZoneInfo

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False

ET = ZoneInfo('America/New_York')

LOOKBACK_DAYS = 5   # days of recent BOUGHT signals to include
DELAY_EVERY = 30
DELAY_SECS = 0.5


def get_sentiment(text_str: str, analyzer) -> float | None:
    """VADER sentiment compound score, or None if unavailable."""
    if not analyzer or not text_str:
        return None
    try:
        return round(analyzer.polarity_scores(text_str)['compound'], 4)
    except Exception:
        return None


def get_target_symbols(session: object, target_date: str) -> list[str]:
    """Get symbols to collect news for: today's candidates + recent buys."""
    syms = set()

    # Today's signal_outcomes
    rows = session.execute(sa_text("""
        SELECT DISTINCT symbol FROM signal_outcomes
        WHERE scan_date = :p0 AND symbol IS NOT NULL
    """), {"p0": target_date}).fetchall()
    syms.update(r[0] for r in rows)

    # Today's screener_rejections
    rows = session.execute(sa_text("""
        SELECT DISTINCT symbol FROM screener_rejections
        WHERE scan_date = :p0 AND symbol IS NOT NULL
    """), {"p0": target_date}).fetchall()
    syms.update(r[0] for r in rows)

    # Recent BOUGHT signals (last N days) — context for open positions
    cutoff = (datetime.strptime(target_date, '%Y-%m-%d') - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    rows = session.execute(sa_text("""
        SELECT DISTINCT symbol FROM signal_outcomes
        WHERE scan_date >= :p0 AND action_taken = 'BOUGHT'
        AND symbol IS NOT NULL
    """), {"p0": cutoff}).fetchall()
    syms.update(r[0] for r in rows)

    return sorted(syms)


def fetch_news(sym: str) -> list[dict]:
    """Fetch news articles from yfinance. Returns list of article dicts."""
    try:
        t = yf.Ticker(sym)
        news = t.news
        if not news:
            return []
        return news
    except Exception:
        return []


def parse_article(sym: str, article: dict, analyzer) -> dict | None:
    """Parse yfinance news article dict into DB row."""
    try:
        headline = article.get('title') or article.get('content', {}).get('title', '')
        if not headline:
            return None

        pub_ts = article.get('providerPublishTime') or \
                 article.get('content', {}).get('pubDate')
        published_at = None
        article_date = None

        if isinstance(pub_ts, (int, float)):
            dt = datetime.fromtimestamp(pub_ts)
            published_at = dt.isoformat()
            article_date = dt.strftime('%Y-%m-%d')
        elif isinstance(pub_ts, str):
            try:
                dt = datetime.fromisoformat(pub_ts.replace('Z', '+00:00'))
                published_at = dt.isoformat()
                article_date = dt.strftime('%Y-%m-%d')
            except Exception:
                pass

        source = article.get('publisher') or \
                 article.get('content', {}).get('provider', {}).get('displayName', '')
        url = article.get('link') or \
              article.get('content', {}).get('canonicalUrl', {}).get('url', '')

        sentiment = get_sentiment(headline, analyzer)

        return {
            'symbol':       sym,
            'date':         article_date,
            'headline':     headline[:500],
            'source':       source[:100] if source else None,
            'url':          url[:500] if url else None,
            'sentiment':    sentiment,
            'published_at': published_at,
        }
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Collect per-stock news for signal candidates')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    parser.add_argument('--no-sentiment', action='store_true', help='Skip VADER sentiment')
    args = parser.parse_args()

    target_date = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_stock_news "
          f"date={target_date} vader={VADER_AVAILABLE}")

    analyzer = None
    if VADER_AVAILABLE and not args.no_sentiment:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()

    with get_session() as session:
        if args.symbol:
            symbols = [args.symbol.upper()]
        else:
            symbols = get_target_symbols(session, target_date)

        print(f"  {len(symbols)} symbols to collect news for")

        total_inserted = 0
        total_failed = 0

        for i, sym in enumerate(symbols):
            articles = fetch_news(sym)
            inserted = 0

            for article in articles:
                row = parse_article(sym, article, analyzer)
                if not row or not row.get('published_at'):
                    continue
                try:
                    session.execute(sa_text("""
                        INSERT OR IGNORE INTO stock_news
                            (symbol, date, headline, source, url, sentiment, published_at)
                        VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6)
                    """), {"p0": row['symbol'], "p1": row['date'], "p2": row['headline'],
                           "p3": row['source'], "p4": row['url'], "p5": row['sentiment'],
                           "p6": row['published_at']})
                    inserted += 1
                except Exception:
                    pass

            if inserted > 0:
                total_inserted += inserted
            else:
                total_failed += 1

            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(symbols)}] articles={total_inserted} no_news={total_failed}")

            if (i + 1) % DELAY_EVERY == 0:
                time.sleep(DELAY_SECS)
    print(f"\n  Done. articles={total_inserted} no_news={total_failed} date={target_date}")


if __name__ == '__main__':
    main()
