#!/usr/bin/env python3
"""
News & Sentiment Collector - ดึงข่าวและวิเคราะห์ sentiment

ข่าวมีผลต่อราคาหุ้นมาก!
- ข่าวดี = ราคาขึ้น
- ข่าวร้าย = ราคาลง
- Analyst upgrade/downgrade
- Insider buying/selling
- M&A rumors
- Product launches
- Lawsuits

แหล่งข้อมูลฟรี:
- Yahoo Finance News
- Google News (RSS)
- Reddit (r/stocks, r/wallstreetbets)
- SEC EDGAR (Insider trades)
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import requests
except ImportError:
    requests = None


class NewsSentimentCollector:
    """
    ดึงข่าวและวิเคราะห์ sentiment ของหุ้น

    สิ่งที่เก็บ:
    - ข่าวล่าสุด
    - Analyst ratings (upgrade/downgrade)
    - Insider trading (buy/sell)
    - Social sentiment
    """

    # Keywords ที่มีผลต่อราคา
    POSITIVE_KEYWORDS = [
        'beat', 'beats', 'exceeds', 'surge', 'soar', 'rally', 'jump',
        'upgrade', 'buy rating', 'outperform', 'strong buy',
        'growth', 'record', 'breakthrough', 'partnership', 'deal',
        'acquisition', 'buyback', 'dividend increase', 'innovation',
        'expands', 'launches', 'approves', 'wins', 'awarded'
    ]

    NEGATIVE_KEYWORDS = [
        'miss', 'misses', 'below', 'plunge', 'crash', 'drop', 'fall',
        'downgrade', 'sell rating', 'underperform', 'hold',
        'decline', 'loss', 'layoffs', 'lawsuit', 'investigation',
        'recall', 'delay', 'warning', 'cut', 'reduces', 'concern',
        'disappoints', 'fails', 'fraud', 'scandal', 'bankruptcy'
    ]

    MAJOR_EVENT_KEYWORDS = [
        'earnings', 'guidance', 'forecast', 'outlook',
        'merger', 'acquisition', 'buyout', 'spinoff',
        'ceo', 'leadership', 'resign', 'departure',
        'fda', 'approval', 'reject',
        'sec', 'investigation', 'probe',
        'tariff', 'trade', 'sanction'
    ]

    def __init__(self):
        self.cache_dir = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'news'
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_stock_news(self, symbol: str) -> Dict:
        """Get recent news for a stock"""
        news_data = {
            'symbol': symbol,
            'fetched_at': datetime.now().isoformat(),
            'news': [],
            'sentiment_score': 0,
            'sentiment_label': 'NEUTRAL',
            'major_events': [],
        }

        if yf is None:
            return news_data

        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news

            if news:
                for item in news[:20]:  # Last 20 news items
                    title = item.get('title', '')
                    summary = item.get('summary', '')
                    text = f"{title} {summary}".lower()

                    # Analyze sentiment
                    positive_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
                    negative_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)

                    if positive_count > negative_count:
                        sentiment = 'POSITIVE'
                    elif negative_count > positive_count:
                        sentiment = 'NEGATIVE'
                    else:
                        sentiment = 'NEUTRAL'

                    # Check for major events
                    major_events = [kw for kw in self.MAJOR_EVENT_KEYWORDS if kw in text]

                    news_item = {
                        'title': title,
                        'publisher': item.get('publisher', ''),
                        'link': item.get('link', ''),
                        'published': datetime.fromtimestamp(
                            item.get('providerPublishTime', 0)
                        ).isoformat() if item.get('providerPublishTime') else None,
                        'sentiment': sentiment,
                        'major_events': major_events if major_events else None,
                    }

                    news_data['news'].append(news_item)

                    if major_events:
                        news_data['major_events'].extend(major_events)

                # Calculate overall sentiment
                sentiments = [n['sentiment'] for n in news_data['news']]
                pos = sentiments.count('POSITIVE')
                neg = sentiments.count('NEGATIVE')

                news_data['sentiment_score'] = (pos - neg) / len(sentiments) if sentiments else 0

                if news_data['sentiment_score'] > 0.3:
                    news_data['sentiment_label'] = 'POSITIVE'
                elif news_data['sentiment_score'] < -0.3:
                    news_data['sentiment_label'] = 'NEGATIVE'
                else:
                    news_data['sentiment_label'] = 'NEUTRAL'

                # Dedupe major events
                news_data['major_events'] = list(set(news_data['major_events']))

        except Exception as e:
            news_data['error'] = str(e)

        return news_data

    def get_analyst_ratings(self, symbol: str) -> Dict:
        """Get analyst ratings and price targets"""
        ratings = {
            'symbol': symbol,
            'fetched_at': datetime.now().isoformat(),
            'recommendation': None,
            'target_price': None,
            'current_price': None,
            'upside': None,
            'analyst_count': None,
            'recent_changes': [],
        }

        if yf is None:
            return ratings

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Current recommendation
            ratings['recommendation'] = info.get('recommendationKey')
            ratings['target_price'] = info.get('targetMeanPrice')
            ratings['current_price'] = info.get('currentPrice') or info.get('regularMarketPrice')
            ratings['analyst_count'] = info.get('numberOfAnalystOpinions')

            # Calculate upside
            if ratings['target_price'] and ratings['current_price']:
                upside = ((ratings['target_price'] - ratings['current_price'])
                          / ratings['current_price']) * 100
                ratings['upside'] = round(upside, 2)

            # Recent recommendation changes
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                recent = recs.tail(10)
                for _, row in recent.iterrows():
                    change = {
                        'date': str(row.name) if hasattr(row, 'name') else None,
                        'firm': row.get('Firm', ''),
                        'from_grade': row.get('From Grade', ''),
                        'to_grade': row.get('To Grade', ''),
                        'action': row.get('Action', ''),
                    }

                    # Determine if upgrade or downgrade
                    grades_rank = {
                        'Strong Buy': 5, 'Buy': 4, 'Outperform': 4,
                        'Hold': 3, 'Neutral': 3, 'Market Perform': 3,
                        'Underperform': 2, 'Sell': 1, 'Strong Sell': 0
                    }

                    from_rank = grades_rank.get(change['from_grade'], 3)
                    to_rank = grades_rank.get(change['to_grade'], 3)

                    if to_rank > from_rank:
                        change['direction'] = 'UPGRADE'
                    elif to_rank < from_rank:
                        change['direction'] = 'DOWNGRADE'
                    else:
                        change['direction'] = 'MAINTAIN'

                    ratings['recent_changes'].append(change)

            # Count recent upgrades vs downgrades
            upgrades = sum(1 for c in ratings['recent_changes'] if c['direction'] == 'UPGRADE')
            downgrades = sum(1 for c in ratings['recent_changes'] if c['direction'] == 'DOWNGRADE')
            ratings['recent_upgrades'] = upgrades
            ratings['recent_downgrades'] = downgrades
            ratings['rating_trend'] = 'UP' if upgrades > downgrades else ('DOWN' if downgrades > upgrades else 'FLAT')

        except Exception as e:
            ratings['error'] = str(e)

        return ratings

    def get_insider_trading(self, symbol: str) -> Dict:
        """Get insider trading activity"""
        insider = {
            'symbol': symbol,
            'fetched_at': datetime.now().isoformat(),
            'transactions': [],
            'net_activity': None,
            'signal': None,
        }

        if yf is None:
            return insider

        try:
            ticker = yf.Ticker(symbol)
            transactions = ticker.insider_transactions

            if transactions is not None and not transactions.empty:
                for _, row in transactions.head(20).iterrows():
                    trans = {
                        'insider': row.get('Insider', ''),
                        'relation': row.get('Relationship', ''),
                        'date': str(row.get('Start Date', '')),
                        'transaction': row.get('Transaction', ''),
                        'shares': row.get('Shares', 0),
                        'value': row.get('Value', 0),
                    }
                    insider['transactions'].append(trans)

                # Calculate net activity (buys - sells)
                buys = sum(t['shares'] for t in insider['transactions']
                          if t['shares'] > 0 and 'Buy' in str(t.get('transaction', '')))
                sells = sum(abs(t['shares']) for t in insider['transactions']
                           if t['shares'] < 0 or 'Sell' in str(t.get('transaction', '')))

                insider['total_buys'] = buys
                insider['total_sells'] = sells

                if buys > sells * 1.5:
                    insider['net_activity'] = 'STRONG_BUYING'
                    insider['signal'] = 'BULLISH'
                elif buys > sells:
                    insider['net_activity'] = 'NET_BUYING'
                    insider['signal'] = 'BULLISH'
                elif sells > buys * 1.5:
                    insider['net_activity'] = 'STRONG_SELLING'
                    insider['signal'] = 'BEARISH'
                elif sells > buys:
                    insider['net_activity'] = 'NET_SELLING'
                    insider['signal'] = 'BEARISH'
                else:
                    insider['net_activity'] = 'MIXED'
                    insider['signal'] = 'NEUTRAL'

        except Exception as e:
            insider['error'] = str(e)

        return insider

    def get_institutional_holders(self, symbol: str) -> Dict:
        """Get institutional ownership info"""
        institutions = {
            'symbol': symbol,
            'fetched_at': datetime.now().isoformat(),
            'major_holders': [],
            'institutional_pct': None,
            'changes': None,
        }

        if yf is None:
            return institutions

        try:
            ticker = yf.Ticker(symbol)

            # Major holders
            holders = ticker.institutional_holders
            if holders is not None and not holders.empty:
                for _, row in holders.head(10).iterrows():
                    holder = {
                        'name': row.get('Holder', ''),
                        'shares': row.get('Shares', 0),
                        'date_reported': str(row.get('Date Reported', '')),
                        'pct_out': row.get('% Out', 0),
                        'value': row.get('Value', 0),
                    }
                    institutions['major_holders'].append(holder)

            # Institutional percentage
            info = ticker.info
            institutions['institutional_pct'] = info.get('heldPercentInstitutions')
            institutions['insider_pct'] = info.get('heldPercentInsiders')

        except Exception as e:
            institutions['error'] = str(e)

        return institutions

    def get_comprehensive_sentiment(self, symbol: str) -> Dict:
        """Get all sentiment data combined"""
        sentiment = {
            'symbol': symbol,
            'fetched_at': datetime.now().isoformat(),
            'overall_sentiment': 'NEUTRAL',
            'confidence': 0,
            'factors': {},
            'warnings': [],
            'signals': [],
        }

        # News sentiment
        news = self.get_stock_news(symbol)
        sentiment['factors']['news'] = {
            'score': news['sentiment_score'],
            'label': news['sentiment_label'],
        }
        if news['major_events']:
            sentiment['warnings'].append(f"Major events in news: {', '.join(news['major_events'])}")

        # Analyst ratings
        ratings = self.get_analyst_ratings(symbol)
        sentiment['factors']['analyst'] = {
            'recommendation': ratings['recommendation'],
            'upside': ratings['upside'],
            'trend': ratings.get('rating_trend'),
        }
        if ratings['upside'] and ratings['upside'] > 20:
            sentiment['signals'].append(f"Strong upside potential: {ratings['upside']:.0f}%")
        if ratings.get('rating_trend') == 'DOWN':
            sentiment['warnings'].append("Recent analyst downgrades")

        # Insider trading
        insider = self.get_insider_trading(symbol)
        sentiment['factors']['insider'] = {
            'activity': insider['net_activity'],
            'signal': insider['signal'],
        }
        if insider['signal'] == 'BULLISH':
            sentiment['signals'].append("Insiders buying")
        elif insider['signal'] == 'BEARISH':
            sentiment['warnings'].append("Insiders selling")

        # Institutions
        institutions = self.get_institutional_holders(symbol)
        sentiment['factors']['institutions'] = {
            'institutional_pct': institutions.get('institutional_pct'),
        }

        # Calculate overall sentiment
        scores = []

        # News score (-1 to 1)
        scores.append(news['sentiment_score'])

        # Analyst score
        rec = ratings['recommendation']
        if rec == 'strong_buy':
            scores.append(1)
        elif rec == 'buy':
            scores.append(0.5)
        elif rec == 'hold':
            scores.append(0)
        elif rec == 'sell':
            scores.append(-0.5)
        elif rec == 'strong_sell':
            scores.append(-1)

        # Insider score
        if insider['signal'] == 'BULLISH':
            scores.append(0.5)
        elif insider['signal'] == 'BEARISH':
            scores.append(-0.5)

        # Overall
        if scores:
            avg_score = sum(scores) / len(scores)
            sentiment['confidence'] = abs(avg_score) * 100

            if avg_score > 0.3:
                sentiment['overall_sentiment'] = 'BULLISH'
            elif avg_score < -0.3:
                sentiment['overall_sentiment'] = 'BEARISH'
            else:
                sentiment['overall_sentiment'] = 'NEUTRAL'

        return sentiment

    def print_sentiment_report(self, symbol: str):
        """Print a comprehensive sentiment report"""
        print("=" * 80)
        print(f"SENTIMENT REPORT: {symbol}")
        print("=" * 80)

        sentiment = self.get_comprehensive_sentiment(symbol)

        print(f"\nOverall Sentiment: {sentiment['overall_sentiment']}")
        print(f"Confidence: {sentiment['confidence']:.0f}%")

        print("\nFactors:")
        for factor, data in sentiment['factors'].items():
            print(f"  {factor}:")
            for k, v in data.items():
                if v is not None:
                    print(f"    {k}: {v}")

        if sentiment['signals']:
            print("\nBullish Signals:")
            for signal in sentiment['signals']:
                print(f"  + {signal}")

        if sentiment['warnings']:
            print("\nWarnings:")
            for warning in sentiment['warnings']:
                print(f"  ! {warning}")

    def save_to_cache(self, symbol: str, data: Dict) -> str:
        """Save sentiment data to cache"""
        filename = f"{symbol}_sentiment_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.cache_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        return filepath


def demo():
    """Demo the collector"""
    collector = NewsSentimentCollector()

    symbols = ['AAPL', 'TSLA', 'NVDA']

    for symbol in symbols:
        collector.print_sentiment_report(symbol)
        print()


if __name__ == '__main__':
    demo()
