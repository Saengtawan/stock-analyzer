"""
News Service - Central service for fetching financial news from various sources
"""
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger


class NewsService:
    """Central service for fetching financial news from various sources"""

    def __init__(self):
        self.timeout = 10  # seconds
        self.max_retries = 2

    def fetch_symbol_news(self, symbol: str, max_articles: int = 10) -> List[Dict[str, str]]:
        """
        ดึงข่าวเฉพาะสำหรับ symbol จาก Yahoo Finance และแหล่งข่าวอื่น

        Args:
            symbol: รหัสหุ้น
            max_articles: จำนวนข่าวสูงสุด

        Returns:
            List of news articles specific to the symbol
        """
        try:
            articles = []

            # 1. Try Yahoo Finance RSS for specific stock
            yahoo_articles = self._fetch_yahoo_finance_news(symbol)
            articles.extend(yahoo_articles)

            # 2. Try Google Finance RSS
            google_articles = self._fetch_google_finance_news(symbol)
            articles.extend(google_articles)

            # 3. Fallback: General financial news that mentions the symbol
            if len(articles) < 3:
                general_articles = self._fetch_general_financial_news(symbol)
                articles.extend(general_articles)

            # Remove duplicates based on title similarity
            articles = self._remove_duplicate_articles(articles)

            # Sort by most recent and limit
            articles = articles[:max_articles]
            logger.info(f"Total articles collected for {symbol}: {len(articles)}")

            return articles

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    def fetch_general_financial_news(self, max_articles: int = 10) -> List[Dict[str, str]]:
        """
        ดึงข่าวการเงินทั่วไปจากหลายแหล่ง

        Args:
            max_articles: จำนวนข่าวสูงสุดที่ต้องการ

        Returns:
            List of general financial news articles
        """
        try:
            # News sources from AIMarketAnalyst
            feeds = [
                "https://rss.cnn.com/rss/money_topstories.rss",
                "https://feeds.reuters.com/reuters/businessNews",
                "https://www.cnbc.com/id/10001147/device/rss/rss.html",
                "https://feeds.marketwatch.com/marketwatch/topstories/"
            ]

            all_articles = []

            for feed_url in feeds:
                try:
                    logger.info(f"Fetching general news from: {feed_url}")
                    feed = feedparser.parse(feed_url)

                    for entry in feed.entries[:5]:  # Limit per source
                        article = self._parse_feed_entry(entry, feed_url)
                        if article:
                            all_articles.append(article)

                    logger.info(f"Fetched {len(feed.entries)} articles from {feed_url}")

                except Exception as e:
                    logger.warning(f"Failed to fetch from {feed_url}: {e}")
                    continue

            # Sort by most recent and limit
            all_articles = all_articles[:max_articles]
            logger.info(f"Total general articles collected: {len(all_articles)}")

            return all_articles

        except Exception as e:
            logger.error(f"Error fetching general financial news: {e}")
            return []

    def _fetch_yahoo_finance_news(self, symbol: str) -> List[Dict[str, str]]:
        """Fetch news from Yahoo Finance RSS feeds"""
        articles = []
        yahoo_feeds = [
            f"https://finance.yahoo.com/rss/headline?s={symbol}",
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        ]

        for feed_url in yahoo_feeds:
            try:
                logger.info(f"Fetching Yahoo Finance news for {symbol}: {feed_url}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:5]:
                    article = self._parse_feed_entry(entry, 'Yahoo Finance')
                    if article:
                        articles.append(article)

                logger.info(f"Fetched {len(feed.entries)} articles from Yahoo Finance for {symbol}")

            except Exception as e:
                logger.warning(f"Failed to fetch from Yahoo Finance {feed_url}: {e}")
                continue

        return articles

    def _fetch_google_finance_news(self, symbol: str) -> List[Dict[str, str]]:
        """Fetch news from Google Finance RSS feeds"""
        articles = []

        try:
            google_feed = f"https://www.google.com/finance/company_news?q={symbol}&output=rss"
            logger.info(f"Fetching Google Finance news for {symbol}")
            feed = feedparser.parse(google_feed)

            for entry in feed.entries[:3]:
                article = self._parse_feed_entry(entry, 'Google Finance')
                if article:
                    articles.append(article)

            logger.info(f"Fetched {len(feed.entries)} articles from Google Finance for {symbol}")

        except Exception as e:
            logger.warning(f"Failed to fetch from Google Finance: {e}")

        return articles

    def _fetch_general_financial_news(self, symbol: str) -> List[Dict[str, str]]:
        """Fetch general financial news that mentions the symbol"""
        articles = []
        general_feeds = [
            "https://feeds.reuters.com/reuters/businessNews",
            "https://www.cnbc.com/id/10001147/device/rss/rss.html",
            "https://feeds.marketwatch.com/marketwatch/topstories/"
        ]

        for feed_url in general_feeds:
            try:
                logger.info(f"Fetching general news from {feed_url} for {symbol}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:10]:  # Check more entries for mentions
                    # Check if symbol is mentioned in title or summary
                    title = entry.title if hasattr(entry, 'title') else ''
                    summary = entry.summary if hasattr(entry, 'summary') else ''

                    if symbol.upper() in title.upper() or symbol.upper() in summary.upper():
                        article = self._parse_feed_entry(entry, feed_url.split('/')[2])
                        if article:
                            articles.append(article)

            except Exception as e:
                logger.warning(f"Failed to fetch from {feed_url}: {e}")
                continue

        return articles

    def _parse_feed_entry(self, entry, source: str) -> Optional[Dict[str, str]]:
        """Parse RSS feed entry into standardized article format"""
        try:
            # Extract summary from various possible fields
            summary = ""
            if hasattr(entry, 'summary'):
                summary = entry.summary
            elif hasattr(entry, 'description'):
                summary = entry.description
            elif hasattr(entry, 'content') and entry.content:
                summary = entry.content[0].value if isinstance(entry.content, list) else str(entry.content)

            # Clean HTML tags if any
            if summary:
                summary = BeautifulSoup(summary, 'html.parser').get_text()

            # Extract published date
            published = entry.published if hasattr(entry, 'published') else 'Unknown date'

            article = {
                'title': entry.title if hasattr(entry, 'title') else 'No title',
                'summary': summary[:400] + '...' if len(summary) > 400 else summary,
                'published': published,
                'link': entry.link if hasattr(entry, 'link') else '',
                'source': source if isinstance(source, str) else str(source)
            }

            # Validate article has meaningful content
            if article['title'] != 'No title' and len(article['summary']) > 20:
                return article

            return None

        except Exception as e:
            logger.warning(f"Failed to parse feed entry: {e}")
            return None

    def _remove_duplicate_articles(self, articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove duplicate articles based on title similarity"""
        seen_titles = set()
        unique_articles = []

        for article in articles:
            title_lower = article['title'].lower()

            # Simple duplicate detection - check if similar title exists
            is_duplicate = False
            for seen_title in seen_titles:
                if self._titles_similar(title_lower, seen_title):
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_titles.add(title_lower)
                unique_articles.append(article)

        return unique_articles

    def _titles_similar(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """Check if two titles are similar (simple word overlap check)"""
        words1 = set(title1.split())
        words2 = set(title2.split())

        if len(words1) == 0 or len(words2) == 0:
            return False

        overlap = len(words1.intersection(words2))
        union = len(words1.union(words2))

        similarity = overlap / union if union > 0 else 0
        return similarity >= threshold

    def health_check(self) -> bool:
        """Check if news sources are accessible"""
        try:
            # Test with a simple general news fetch
            articles = self.fetch_general_financial_news(max_articles=1)
            return len(articles) > 0
        except Exception as e:
            logger.error(f"News service health check failed: {e}")
            return False


# Global instance
news_service = NewsService()


def main():
    """Test the news service"""
    service = NewsService()

    print("Testing News Service...")

    # Health check
    if service.health_check():
        print("✅ News Service is accessible")
    else:
        print("❌ News Service is not accessible")
        return

    # Test symbol-specific news
    symbol = "AAPL"
    print(f"\nTesting symbol-specific news for {symbol}...")
    symbol_news = service.fetch_symbol_news(symbol, max_articles=5)

    if symbol_news:
        print(f"✅ Found {len(symbol_news)} articles for {symbol}")
        for i, article in enumerate(symbol_news[:2], 1):
            print(f"  {i}. {article['title'][:60]}... (Source: {article['source']})")
    else:
        print(f"❌ No articles found for {symbol}")

    # Test general financial news
    print(f"\nTesting general financial news...")
    general_news = service.fetch_general_financial_news(max_articles=3)

    if general_news:
        print(f"✅ Found {len(general_news)} general articles")
        for i, article in enumerate(general_news[:2], 1):
            print(f"  {i}. {article['title'][:60]}... (Source: {article['source']})")
    else:
        print("❌ No general articles found")


if __name__ == "__main__":
    main()