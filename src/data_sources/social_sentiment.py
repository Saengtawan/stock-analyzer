#!/usr/bin/env python3
"""
Social Media Sentiment Data Source
Track Reddit, Twitter mentions and sentiment
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, List
import re

logger = logging.getLogger(__name__)


class SocialSentimentTracker:
    """Track social media sentiment for stocks"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=6)  # Shorter cache for social data

    def get_reddit_sentiment(self, symbol: str) -> Optional[Dict]:
        """
        Get Reddit sentiment from wallstreetbets and other stock subreddits

        Returns:
            Dict with sentiment data or None if unavailable
            {
                'mentions_24h': int,  # Number of mentions in last 24h
                'mentions_7d': int,  # Number of mentions in last 7 days
                'sentiment_score': float,  # -100 (bearish) to +100 (bullish)
                'sentiment': str,  # 'bullish', 'bearish', 'neutral'
                'trending': bool,  # Mentions increasing rapidly
                'social_score': float,  # 0-100 overall social score
                'top_subreddits': List[str]  # Where it's being discussed
            }
        """

        # Check cache
        cache_key = f"{symbol}_social"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug(f"{symbol}: Using cached social sentiment")
                return cached_data

        try:
            # Try to get data from free Reddit JSON API
            # Note: This is a simplified version. In production, use Reddit API with authentication
            result = self._scrape_reddit_mentions(symbol)

            if result:
                # Cache result
                self.cache[cache_key] = (result, datetime.now())
                return result

            return None

        except Exception as e:
            logger.error(f"{symbol}: Error fetching social sentiment: {e}")
            return None

    def _scrape_reddit_mentions(self, symbol: str) -> Optional[Dict]:
        """
        Scrape Reddit for mentions (simplified version)

        Note: For production, use PRAW (Python Reddit API Wrapper) with proper authentication
        """

        try:
            # List of stock-related subreddits
            subreddits = ['wallstreetbets', 'stocks', 'investing', 'StockMarket']

            total_mentions = 0
            sentiment_scores = []

            headers = {
                'User-Agent': 'Stock Analyzer Bot 1.0'
            }

            for subreddit in subreddits:
                try:
                    # Reddit JSON API (public, no auth needed)
                    url = f"https://www.reddit.com/r/{subreddit}/search.json"
                    params = {
                        'q': f'${symbol}',
                        'restrict_sr': True,
                        'sort': 'new',
                        'limit': 25,
                        't': 'day'  # Last 24 hours
                    }

                    response = requests.get(url, headers=headers, params=params, timeout=10)

                    if response.status_code == 200:
                        data = response.json()
                        posts = data.get('data', {}).get('children', [])

                        for post in posts:
                            post_data = post.get('data', {})
                            title = post_data.get('title', '').lower()
                            body = post_data.get('selftext', '').lower()

                            # Check if symbol mentioned
                            if f'${symbol.lower()}' in title or f'${symbol.lower()}' in body or symbol.lower() in title:
                                total_mentions += 1

                                # Simple sentiment analysis
                                text = f"{title} {body}"
                                sentiment = self._analyze_text_sentiment(text)
                                sentiment_scores.append(sentiment)

                except Exception as e:
                    logger.debug(f"Error scraping r/{subreddit}: {e}")
                    continue

            # If no mentions found
            if total_mentions == 0:
                return {
                    'mentions_24h': 0,
                    'mentions_7d': 0,
                    'sentiment_score': 0.0,
                    'sentiment': 'neutral',
                    'trending': False,
                    'social_score': 0.0,
                    'top_subreddits': []
                }

            # Calculate average sentiment
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

            # Determine overall sentiment
            if avg_sentiment > 0.2:
                sentiment_label = 'bullish'
            elif avg_sentiment < -0.2:
                sentiment_label = 'bearish'
            else:
                sentiment_label = 'neutral'

            # Calculate social score
            # More mentions + positive sentiment = higher score
            mention_score = min(total_mentions * 5, 50)  # Max 50 points for mentions
            sentiment_bonus = avg_sentiment * 50  # -50 to +50 points
            social_score = max(0, min(100, mention_score + sentiment_bonus))

            # Check if trending (simplified - would need historical data)
            trending = total_mentions > 10

            return {
                'mentions_24h': total_mentions,
                'mentions_7d': total_mentions,  # Would need to scrape 7d data
                'sentiment_score': avg_sentiment * 100,  # Convert to -100 to +100
                'sentiment': sentiment_label,
                'trending': trending,
                'social_score': social_score,
                'top_subreddits': subreddits[:3]
            }

        except Exception as e:
            logger.error(f"Error in _scrape_reddit_mentions: {e}")
            return None

    def _analyze_text_sentiment(self, text: str) -> float:
        """
        Simple sentiment analysis based on keywords
        Returns: -1.0 (bearish) to +1.0 (bullish)
        """

        # Bullish keywords
        bullish_words = [
            'moon', 'rocket', 'buy', 'calls', 'bullish', 'pump', 'squeeze',
            'to the moon', 'hodl', 'diamond hands', 'breakout', 'rally',
            'undervalued', 'strong', 'growth', 'earnings beat'
        ]

        # Bearish keywords
        bearish_words = [
            'sell', 'puts', 'bearish', 'dump', 'crash', 'tank', 'drop',
            'overvalued', 'weak', 'miss', 'decline', 'fall', 'short',
            'bubble', 'red flags'
        ]

        text = text.lower()

        bullish_count = sum(1 for word in bullish_words if word in text)
        bearish_count = sum(1 for word in bearish_words if word in text)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        sentiment = (bullish_count - bearish_count) / total
        return sentiment

    def get_batch_social_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get social sentiment for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_reddit_sentiment(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    tracker = SocialSentimentTracker()

    # Test with meme stocks
    test_symbols = ['GME', 'TSLA', 'NVDA', 'AAPL']

    print("\n" + "="*80)
    print("💬 SOCIAL SENTIMENT TEST")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        data = tracker.get_reddit_sentiment(symbol)
        if data:
            print(f"  Mentions (24h): {data['mentions_24h']}")
            print(f"  Sentiment: {data['sentiment']} ({data['sentiment_score']:+.1f})")
            print(f"  Social score: {data['social_score']:.1f}/100")
            print(f"  Trending: {data['trending']}")
        else:
            print("  No data available")
