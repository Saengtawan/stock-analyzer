#!/usr/bin/env python3
"""
NEWS COLLECTOR - เก็บข่าวจาก Free APIs

Free News APIs:
1. NewsAPI.org - Free tier: 100 requests/day
2. Alpha Vantage News - Free with API key
3. Finnhub - Free tier available
4. RSS Feeds - Free, unlimited

Features:
- ดึงข่าวตาม sector
- วิเคราะห์ sentiment (positive/negative/neutral)
- หา breaking news ที่กระทบหุ้น
"""

import os
import json
import sqlite3
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')

# API Keys (set as environment variables)
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_KEY', '')
FINNHUB_KEY = os.environ.get('FINNHUB_KEY', '')


class NewsCollector:
    """Collect and analyze news from multiple sources"""

    def __init__(self):
        self.db_path = DB_PATH
        self._init_tables()

        # Sector keywords for filtering
        self.sector_keywords = {
            'Technology': ['tech', 'software', 'cloud', 'AI', 'artificial intelligence', 'microsoft', 'apple', 'google'],
            'Semiconductors': ['chip', 'semiconductor', 'nvidia', 'amd', 'intel', 'fab', 'gpu'],
            'Financials': ['bank', 'finance', 'interest rate', 'fed', 'jpmorgan', 'goldman', 'credit'],
            'Healthcare': ['pharma', 'drug', 'fda', 'biotech', 'healthcare', 'medical', 'vaccine'],
            'Energy': ['oil', 'gas', 'energy', 'opec', 'crude', 'exxon', 'chevron', 'pipeline'],
            'Consumer': ['retail', 'consumer', 'amazon', 'walmart', 'spending', 'sales'],
            'Industrial': ['manufacturing', 'industrial', 'factory', 'supply chain', 'caterpillar'],
        }

        # Sentiment keywords
        self.positive_words = [
            'beat', 'surge', 'jump', 'rally', 'record', 'growth', 'strong', 'upgrade',
            'bullish', 'gain', 'rise', 'positive', 'outperform', 'buy', 'boom'
        ]
        self.negative_words = [
            'miss', 'fall', 'drop', 'crash', 'plunge', 'weak', 'downgrade', 'bearish',
            'loss', 'decline', 'negative', 'underperform', 'sell', 'cut', 'layoff'
        ]

    def _init_tables(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                source TEXT,
                title TEXT,
                description TEXT,
                url TEXT,
                sector TEXT,
                sentiment TEXT,
                sentiment_score REAL,
                symbols TEXT,
                created_at TEXT,
                UNIQUE(url)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_sentiment (
                date TEXT,
                sector TEXT,
                positive_count INTEGER,
                negative_count INTEGER,
                neutral_count INTEGER,
                sentiment_score REAL,
                PRIMARY KEY (date, sector)
            )
        """)

        conn.commit()
        conn.close()

    def fetch_from_newsapi(self, query: str = 'stock market', category: str = 'business') -> List[Dict]:
        """Fetch news from NewsAPI.org"""
        if not NEWSAPI_KEY:
            print("⚠️ NEWSAPI_KEY not set")
            print("Get free key at: https://newsapi.org/register")
            return []

        url = "https://newsapi.org/v2/top-headlines"
        params = {
            'apiKey': NEWSAPI_KEY,
            'category': category,
            'country': 'us',
            'pageSize': 50,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data.get('status') == 'ok':
                articles = []
                for article in data.get('articles', []):
                    articles.append({
                        'source': article.get('source', {}).get('name', 'Unknown'),
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', ''),
                        'published_at': article.get('publishedAt', '')[:10],
                    })
                return articles
        except Exception as e:
            print(f"Error fetching from NewsAPI: {e}")

        return []

    def fetch_from_alpha_vantage(self, symbols: List[str] = None) -> List[Dict]:
        """Fetch news from Alpha Vantage"""
        if not ALPHA_VANTAGE_KEY:
            print("⚠️ ALPHA_VANTAGE_KEY not set")
            print("Get free key at: https://www.alphavantage.co/support/#api-key")
            return []

        # Alpha Vantage news sentiment endpoint
        url = "https://www.alphavantage.co/query"

        articles = []

        # Get market news
        params = {
            'function': 'NEWS_SENTIMENT',
            'apikey': ALPHA_VANTAGE_KEY,
            'topics': 'earnings,ipo,technology,finance,economy',
            'limit': 50,
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            for article in data.get('feed', []):
                articles.append({
                    'source': article.get('source', 'Alpha Vantage'),
                    'title': article.get('title', ''),
                    'description': article.get('summary', ''),
                    'url': article.get('url', ''),
                    'published_at': article.get('time_published', '')[:10],
                    'sentiment_score': article.get('overall_sentiment_score', 0),
                    'sentiment_label': article.get('overall_sentiment_label', 'Neutral'),
                })
        except Exception as e:
            print(f"Error fetching from Alpha Vantage: {e}")

        return articles

    def fetch_from_finnhub(self, category: str = 'general') -> List[Dict]:
        """Fetch news from Finnhub"""
        if not FINNHUB_KEY:
            print("⚠️ FINNHUB_KEY not set")
            print("Get free key at: https://finnhub.io/register")
            return []

        url = f"https://finnhub.io/api/v1/news"
        params = {
            'token': FINNHUB_KEY,
            'category': category,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            articles = []
            for article in data[:50]:
                articles.append({
                    'source': article.get('source', 'Finnhub'),
                    'title': article.get('headline', ''),
                    'description': article.get('summary', ''),
                    'url': article.get('url', ''),
                    'published_at': datetime.fromtimestamp(article.get('datetime', 0)).strftime('%Y-%m-%d'),
                })
            return articles
        except Exception as e:
            print(f"Error fetching from Finnhub: {e}")

        return []

    def analyze_sentiment(self, text: str) -> Tuple[str, float]:
        """Simple sentiment analysis"""
        if not text:
            return 'neutral', 0

        text_lower = text.lower()

        positive_count = sum(1 for word in self.positive_words if word in text_lower)
        negative_count = sum(1 for word in self.negative_words if word in text_lower)

        total = positive_count + negative_count
        if total == 0:
            return 'neutral', 0

        score = (positive_count - negative_count) / total

        if score > 0.2:
            return 'positive', score
        elif score < -0.2:
            return 'negative', score
        else:
            return 'neutral', score

    def categorize_sector(self, text: str) -> List[str]:
        """Categorize news into sectors"""
        if not text:
            return []

        text_lower = text.lower()
        sectors = []

        for sector, keywords in self.sector_keywords.items():
            if any(kw.lower() in text_lower for kw in keywords):
                sectors.append(sector)

        return sectors if sectors else ['General']

    def collect_all_news(self) -> List[Dict]:
        """Collect news from all available sources"""
        print("="*60)
        print("📰 COLLECTING NEWS")
        print("="*60)

        all_articles = []

        # Try NewsAPI
        print("\n📡 NewsAPI...")
        articles = self.fetch_from_newsapi()
        print(f"   Found: {len(articles)} articles")
        all_articles.extend(articles)

        # Try Alpha Vantage
        print("\n📡 Alpha Vantage...")
        articles = self.fetch_from_alpha_vantage()
        print(f"   Found: {len(articles)} articles")
        all_articles.extend(articles)

        # Try Finnhub
        print("\n📡 Finnhub...")
        articles = self.fetch_from_finnhub()
        print(f"   Found: {len(articles)} articles")
        all_articles.extend(articles)

        print(f"\n✅ Total articles: {len(all_articles)}")

        # Process and save
        processed = []
        for article in all_articles:
            text = f"{article.get('title', '')} {article.get('description', '')}"

            sentiment, score = self.analyze_sentiment(text)
            sectors = self.categorize_sector(text)

            for sector in sectors:
                processed.append({
                    'date': article.get('published_at', datetime.now().strftime('%Y-%m-%d')),
                    'source': article.get('source', 'Unknown'),
                    'title': article.get('title', ''),
                    'description': article.get('description', ''),
                    'url': article.get('url', ''),
                    'sector': sector,
                    'sentiment': sentiment,
                    'sentiment_score': score,
                })

        # Save to database
        self._save_articles(processed)

        return processed

    def _save_articles(self, articles: List[Dict]):
        """Save articles to database"""
        conn = sqlite3.connect(self.db_path)

        for article in articles:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO news_articles
                    (date, source, title, description, url, sector, sentiment, sentiment_score, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article['date'],
                    article['source'],
                    article['title'],
                    article['description'],
                    article['url'],
                    article['sector'],
                    article['sentiment'],
                    article['sentiment_score'],
                    datetime.now().isoformat(),
                ))
            except:
                pass

        conn.commit()
        conn.close()

    def get_sector_sentiment(self, date: str = None) -> Dict:
        """Get sentiment by sector"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(self.db_path)

        cursor = conn.execute("""
            SELECT sector, sentiment, COUNT(*) as count
            FROM news_articles
            WHERE date >= date(?, '-7 days')
            GROUP BY sector, sentiment
        """, (date,))

        results = {}
        for row in cursor.fetchall():
            sector, sentiment, count = row
            if sector not in results:
                results[sector] = {'positive': 0, 'negative': 0, 'neutral': 0}
            results[sector][sentiment] = count

        conn.close()

        # Calculate sentiment scores
        for sector in results:
            total = sum(results[sector].values())
            if total > 0:
                results[sector]['score'] = (
                    (results[sector]['positive'] - results[sector]['negative']) / total
                )
            else:
                results[sector]['score'] = 0

        return results

    def get_breaking_news(self, hours: int = 24) -> List[Dict]:
        """Get recent breaking news"""
        conn = sqlite3.connect(self.db_path)

        cursor = conn.execute("""
            SELECT source, title, sector, sentiment, sentiment_score, created_at
            FROM news_articles
            WHERE created_at >= datetime('now', ?)
            ORDER BY created_at DESC
            LIMIT 20
        """, (f'-{hours} hours',))

        news = []
        for row in cursor.fetchall():
            news.append({
                'source': row[0],
                'title': row[1],
                'sector': row[2],
                'sentiment': row[3],
                'score': row[4],
                'time': row[5],
            })

        conn.close()
        return news

    def generate_news_report(self) -> Dict:
        """Generate comprehensive news report"""
        print("\n" + "="*60)
        print("📊 NEWS SENTIMENT REPORT")
        print("="*60)

        # Collect fresh news
        articles = self.collect_all_news()

        # Get sector sentiment
        sentiment = self.get_sector_sentiment()

        print(f"\n{'Sector':<20} {'Positive':>10} {'Negative':>10} {'Score':>10}")
        print("-"*55)

        for sector in sorted(sentiment.keys(), key=lambda x: sentiment[x].get('score', 0), reverse=True):
            data = sentiment[sector]
            emoji = "🟢" if data['score'] > 0.2 else "🔴" if data['score'] < -0.2 else "🟡"
            print(f"{sector:<20} {data['positive']:>10} {data['negative']:>10} {data['score']:>+9.2f} {emoji}")

        # Get breaking news
        print("\n" + "="*60)
        print("📰 RECENT HEADLINES")
        print("="*60)

        breaking = self.get_breaking_news(24)
        for news in breaking[:10]:
            emoji = "🟢" if news['sentiment'] == 'positive' else "🔴" if news['sentiment'] == 'negative' else "⚪"
            print(f"{emoji} [{news['sector']}] {news['title'][:60]}...")

        # Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'articles_count': len(articles),
            'sector_sentiment': sentiment,
            'breaking_news': breaking[:20],
        }

        report_path = os.path.join(DATA_DIR, 'predictions', 'news_report.json')
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n✅ Report saved to: {report_path}")

        return report


def main():
    """Main entry point"""
    collector = NewsCollector()

    # Check for API keys
    print("="*60)
    print("📰 NEWS COLLECTOR")
    print("="*60)

    if not any([NEWSAPI_KEY, ALPHA_VANTAGE_KEY, FINNHUB_KEY]):
        print("\n⚠️ No API keys configured!")
        print("\nTo use news features, set environment variables:")
        print("  export NEWSAPI_KEY='your_key'")
        print("  export ALPHA_VANTAGE_KEY='your_key'")
        print("  export FINNHUB_KEY='your_key'")
        print("\nFree API keys:")
        print("  • NewsAPI: https://newsapi.org/register")
        print("  • Alpha Vantage: https://www.alphavantage.co/support/#api-key")
        print("  • Finnhub: https://finnhub.io/register")
        return

    # Generate report
    report = collector.generate_news_report()


if __name__ == '__main__':
    main()
