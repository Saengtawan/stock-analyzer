#!/usr/bin/env python3
"""
Insider Trading Data Source - Using Yahoo Finance (v2)
Track when CEOs, CFOs, and directors buy/sell their own company stock
Much more reliable than SEC EDGAR API
"""

import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional

from .rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class InsiderTradingTracker:
    """Track insider trading activity using Yahoo Finance (more reliable)"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=24)

    def get_insider_activity(self, symbol: str) -> Optional[Dict]:
        """
        Get recent insider trading activity for a symbol using Yahoo Finance

        Returns:
            Dict with insider activity data or None if unavailable
            {
                'insider_buys_30d': int,  # Number of insider buy transactions
                'insider_sells_30d': int,  # Number of insider sell transactions
                'net_insider_shares': int,  # Net shares bought
                'insider_sentiment': str,  # 'bullish', 'bearish', 'neutral'
                'insider_score': float,  # 0 to +100
                'latest_transaction_date': str,
                'has_recent_buying': bool  # Insider bought in last 30 days (lowered from 7)
            }
        """

        # Check cache
        cache_key = f"{symbol}_insider"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug(f"{symbol}: Using cached insider data")
                return cached_data

        try:
            # Use yfinance to get insider transactions (via rate limiter)
            limiter = get_rate_limiter()
            ticker = limiter.get_ticker(symbol)

            # Try to get insider purchases
            try:
                insider_purchases = ticker.insider_purchases
            except:
                insider_purchases = None

            # Try to get institutional holders as a proxy
            try:
                institutional = ticker.institutional_holders
            except:
                institutional = None

            # Analyze insider activity
            result = self._analyze_insider_data(insider_purchases, institutional, symbol)

            # Cache result
            if result:
                self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.debug(f"{symbol}: Error fetching insider data: {e}")
            # Return neutral score instead of None
            return {
                'insider_buys_30d': 0,
                'insider_sells_30d': 0,
                'net_insider_shares': 0,
                'insider_sentiment': 'neutral',
                'insider_score': 50.0,  # Neutral score
                'latest_transaction_date': None,
                'has_recent_buying': False
            }

    def _analyze_insider_data(self, insider_purchases, institutional, symbol: str) -> Dict:
        """
        Analyze insider data from yfinance

        insider_purchases structure (summary for last 6 months):
        Row 0: Purchases (shares purchased)
        Row 1: Sales (shares sold)
        Row 2: Net Shares Purchased (Sold)
        Row 3: Total Insider Shares Held
        Row 4: % Net Shares Purchased (Sold)
        """

        # Default values
        purchase_shares = 0
        sale_shares = 0
        net_shares = 0
        purchase_trans = 0
        sale_trans = 0
        has_recent_buying = False

        # Analyze insider purchases if available
        if insider_purchases is not None and not insider_purchases.empty:
            try:
                # Parse the summary table
                # Row 0 is "Purchases", Row 1 is "Sales", Row 2 is "Net Shares Purchased (Sold)"
                if len(insider_purchases) >= 3:
                    # Get shares purchased and sold
                    purchase_shares = insider_purchases.iloc[0].get('Shares', 0)
                    sale_shares = insider_purchases.iloc[1].get('Shares', 0)
                    net_shares = insider_purchases.iloc[2].get('Shares', 0)

                    # Get number of transactions
                    purchase_trans = insider_purchases.iloc[0].get('Trans', 0)
                    sale_trans = insider_purchases.iloc[1].get('Trans', 0)

                    # Convert to numeric (handle NaN)
                    purchase_shares = float(purchase_shares) if pd.notna(purchase_shares) else 0
                    sale_shares = float(sale_shares) if pd.notna(sale_shares) else 0
                    net_shares = float(net_shares) if pd.notna(net_shares) else 0
                    purchase_trans = int(purchase_trans) if pd.notna(purchase_trans) else 0
                    sale_trans = int(sale_trans) if pd.notna(sale_trans) else 0

                    # Has recent buying if net purchases > 0 OR purchase transactions > 0
                    has_recent_buying = (net_shares > 0 or purchase_trans > 0)

                    logger.debug(f"{symbol}: Insider - Purchases: {purchase_shares:,.0f} shares ({purchase_trans} trans), "
                               f"Sales: {sale_shares:,.0f} shares ({sale_trans} trans), "
                               f"Net: {net_shares:,.0f}")

            except Exception as e:
                logger.debug(f"{symbol}: Error parsing insider purchases: {e}")

        # Calculate insider score (0-100)
        # Based on net shares and number of purchase transactions
        if net_shares > 100000 or purchase_trans >= 10:
            insider_score = 90.0
            sentiment = 'bullish'
        elif net_shares > 50000 or purchase_trans >= 5:
            insider_score = 80.0
            sentiment = 'bullish'
        elif net_shares > 10000 or purchase_trans >= 3:
            insider_score = 70.0
            sentiment = 'bullish'
        elif net_shares > 0 or purchase_trans >= 1:
            insider_score = 65.0
            sentiment = 'neutral'
        elif net_shares < -50000 or sale_trans >= 10:
            # Heavy insider selling
            insider_score = 40.0
            sentiment = 'bearish'
        else:
            # Check institutional holders as additional signal
            if institutional is not None and not institutional.empty:
                insider_score = 55.0
                sentiment = 'neutral'
            else:
                insider_score = 50.0
                sentiment = 'neutral'

        return {
            'insider_buys_30d': purchase_trans,
            'insider_sells_30d': sale_trans,
            'net_insider_shares': int(net_shares),
            'insider_sentiment': sentiment,
            'insider_score': insider_score,
            'latest_transaction_date': 'Last 6 months',
            'has_recent_buying': has_recent_buying
        }

    def get_batch_insider_data(self, symbols: list) -> Dict[str, Dict]:
        """Get insider data for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_insider_activity(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    tracker = InsiderTradingTracker()

    # Test with a few symbols
    test_symbols = ['AAPL', 'TSLA', 'NVDA', 'MU']

    print("\n" + "="*80)
    print("🔍 INSIDER TRADING TEST (v2 - Yahoo Finance)")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        data = tracker.get_insider_activity(symbol)
        if data:
            print(f"  Recent purchases (30d): {data['insider_buys_30d']}")
            print(f"  Sentiment: {data['insider_sentiment']}")
            print(f"  Score: {data['insider_score']:.1f}")
            print(f"  Recent buying: {data['has_recent_buying']}")
        else:
            print("  No data available")
