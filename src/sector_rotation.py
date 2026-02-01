#!/usr/bin/env python3
"""
Sector Rotation Detector
Identify hot/cold sectors to improve stock selection timing
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class SectorRotationDetector:
    """Detect sector momentum and rotation patterns"""

    def __init__(self):
        # Sector ETFs for momentum tracking
        self.sector_etfs = {
            'Technology': 'XLK',
            'Healthcare': 'XLV',
            'Financials': 'XLF',
            'Energy': 'XLE',
            'Materials': 'XLB',
            'Industrials': 'XLI',
            'Consumer Discretionary': 'XLY',
            'Consumer Staples': 'XLP',
            'Utilities': 'XLU',
            'Real Estate': 'XLRE',
            'Communication Services': 'XLC',
        }

        # Specific theme ETFs
        self.theme_etfs = {
            'Semiconductors': 'SOXX',
            'Cloud Computing': 'SKYY',
            'Cybersecurity': 'HACK',
            'Biotech': 'XBI',
            'Gold Miners': 'GDX',
            'Silver': 'SLV',
            'Oil & Gas': 'XOP',
            'Clean Energy': 'ICLN',
            'AI & Robotics': 'BOTZ',
        }

        self.cache = {}
        self.cache_duration = timedelta(hours=6)  # Refresh every 6 hours

    def get_sector_momentum(self, periods: Dict[str, int] = None) -> Dict:
        """
        Calculate momentum for all sectors across multiple timeframes

        Args:
            periods: Dict of {'period_name': days}, default is {'7d': 7, '30d': 30}

        Returns:
            Dict with sector momentum data
        """

        if periods is None:
            periods = {'7d': 7, '30d': 30, '90d': 90}

        # Check cache
        cache_key = 'sector_momentum'
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug("Using cached sector momentum data")
                return cached_data

        try:
            all_sectors = {**self.sector_etfs, **self.theme_etfs}
            sector_data = {}

            for sector_name, etf_symbol in all_sectors.items():
                try:
                    momentum = self._calculate_etf_momentum(etf_symbol, periods)
                    if momentum:
                        sector_data[sector_name] = momentum
                except Exception as e:
                    logger.debug(f"Error calculating momentum for {sector_name}: {e}")
                    continue

            # Classify sectors
            result = {
                'sectors': sector_data,
                'hot_sectors': self._identify_hot_sectors(sector_data),
                'cold_sectors': self._identify_cold_sectors(sector_data),
                'neutral_sectors': self._identify_neutral_sectors(sector_data),
                'timestamp': datetime.now()
            }

            # Cache result
            self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.error(f"Error calculating sector momentum: {e}")
            return None

    def _calculate_etf_momentum(self, etf_symbol: str, periods: Dict[str, int]) -> Dict:
        """Calculate momentum for a single ETF across multiple periods"""

        try:
            # Get historical data
            max_days = max(periods.values()) + 10
            end_date = datetime.now()
            start_date = end_date - timedelta(days=max_days)

            ticker = yf.Ticker(etf_symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                return None

            momentum = {}
            current_price = hist['Close'].iloc[-1]

            for period_name, days in periods.items():
                if len(hist) > days:
                    past_price = hist['Close'].iloc[-days]
                    change_pct = ((current_price - past_price) / past_price) * 100
                    momentum[period_name] = round(change_pct, 2)

            # Calculate overall momentum score (weighted average)
            if '30d' in momentum:
                # 30-day is most important for our timeframe
                momentum['score'] = momentum['30d']
            elif '7d' in momentum:
                momentum['score'] = momentum['7d']
            else:
                momentum['score'] = 0

            return momentum

        except Exception as e:
            logger.debug(f"Error calculating ETF momentum for {etf_symbol}: {e}")
            return None

    def _identify_hot_sectors(self, sector_data: Dict, threshold: float = 3.0) -> List[str]:
        """Identify sectors with strong positive momentum"""

        hot = []
        for sector, momentum in sector_data.items():
            if momentum and momentum.get('score', 0) > threshold:
                hot.append(sector)

        # Sort by momentum
        hot.sort(key=lambda x: sector_data[x]['score'], reverse=True)
        return hot

    def _identify_cold_sectors(self, sector_data: Dict, threshold: float = -3.0) -> List[str]:
        """Identify sectors with strong negative momentum"""

        cold = []
        for sector, momentum in sector_data.items():
            if momentum and momentum.get('score', 0) < threshold:
                cold.append(sector)

        # Sort by worst momentum first
        cold.sort(key=lambda x: sector_data[x]['score'])
        return cold

    def _identify_neutral_sectors(self, sector_data: Dict) -> List[str]:
        """Identify sectors with neutral momentum"""

        neutral = []
        for sector, momentum in sector_data.items():
            if momentum:
                score = momentum.get('score', 0)
                if -3.0 <= score <= 3.0:
                    neutral.append(sector)

        return neutral

    def get_stock_sector_status(self, symbol: str, sector: str = None) -> Dict:
        """
        Get sector status for a specific stock

        Args:
            symbol: Stock symbol
            sector: Sector name (if known), otherwise will try to detect

        Returns:
            Dict with sector status
        """

        # Get sector momentum
        sector_momentum = self.get_sector_momentum()

        if not sector_momentum:
            return {
                'sector': sector,
                'status': 'unknown',
                'momentum_score': 0,
                'recommendation': 'neutral'
            }

        # Get sector and industry info
        industry = None
        if not sector:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', '')
            except:
                sector = 'Unknown'
                industry = ''
        else:
            # If sector provided, try to get industry too
            try:
                ticker = yf.Ticker(symbol)
                industry = ticker.info.get('industry', '')
            except:
                industry = ''

        # Find matching sector in our data
        # PRIORITY 1: Match specific theme ETFs first (more granular)
        sector_score = 0
        sector_status = 'neutral'
        matched_sector = sector

        # Try to match industry to theme ETFs first
        if industry:
            for theme_name, momentum in sector_momentum['sectors'].items():
                if theme_name in self.theme_etfs:  # Only check theme ETFs
                    # Check for semiconductor companies
                    if 'semiconductor' in industry.lower() and 'Semiconductor' in theme_name:
                        sector_score = momentum.get('score', 0)
                        matched_sector = theme_name
                        logger.debug(f"{symbol}: Matched to {theme_name} via industry '{industry}'")
                        break
                    # Check for other themes
                    elif theme_name.lower() in industry.lower():
                        sector_score = momentum.get('score', 0)
                        matched_sector = theme_name
                        logger.debug(f"{symbol}: Matched to {theme_name} via industry '{industry}'")
                        break

        # PRIORITY 2: If no theme match, try broad sector match
        if sector_score == 0 and sector:
            for sector_name, momentum in sector_momentum['sectors'].items():
                if sector.lower() in sector_name.lower():
                    sector_score = momentum.get('score', 0)
                    matched_sector = sector_name
                    logger.debug(f"{symbol}: Matched to {sector_name} via sector '{sector}'")
                    break

        # Determine status
        if sector_score > 3:
            sector_status = 'hot'
            recommendation = 'BUY - Strong sector momentum'
        elif sector_score < -3:
            sector_status = 'cold'
            recommendation = 'AVOID - Weak sector momentum'
        else:
            sector_status = 'neutral'
            recommendation = 'NEUTRAL - No strong sector bias'

        return {
            'sector': matched_sector,  # Return the matched sector (could be theme or broad)
            'status': sector_status,
            'momentum_score': sector_score,
            'momentum_30d': sector_score,
            'recommendation': recommendation
        }

    def get_sector_boost(self, sector: str) -> float:
        """
        Calculate score boost/penalty based on sector momentum

        Returns:
            Float between 0.8 (cold sector) and 1.2 (hot sector)
        """

        sector_momentum = self.get_sector_momentum()

        if not sector_momentum:
            return 1.0  # No adjustment

        # Find sector score
        sector_score = 0
        for sector_name, momentum in sector_momentum['sectors'].items():
            if sector and sector.lower() in sector_name.lower():
                sector_score = momentum.get('score', 0)
                break

        # Convert to multiplier
        # Hot sector (+10%): 1.2x
        # Neutral (0%): 1.0x
        # Cold sector (-10%): 0.8x

        if sector_score > 5:
            return 1.2
        elif sector_score > 3:
            return 1.1
        elif sector_score < -5:
            return 0.8
        elif sector_score < -3:
            return 0.9
        else:
            return 1.0

    def print_sector_report(self):
        """Print a formatted sector rotation report"""

        momentum = self.get_sector_momentum()

        if not momentum:
            print("❌ Unable to fetch sector momentum data")
            return

        print("\n" + "="*80)
        print("📊 SECTOR ROTATION REPORT")
        print("="*80)

        # Hot sectors
        if momentum['hot_sectors']:
            print(f"\n🔥 HOT SECTORS (Strong Momentum):")
            for sector in momentum['hot_sectors'][:5]:  # Top 5
                data = momentum['sectors'][sector]
                print(f"   {sector:<30} {data['score']:>+6.1f}% (30d: {data.get('30d', 0):>+6.1f}%)")

        # Cold sectors
        if momentum['cold_sectors']:
            print(f"\n❄️  COLD SECTORS (Weak Momentum):")
            for sector in momentum['cold_sectors'][:5]:  # Bottom 5
                data = momentum['sectors'][sector]
                print(f"   {sector:<30} {data['score']:>+6.1f}% (30d: {data.get('30d', 0):>+6.1f}%)")

        # Neutral
        if momentum['neutral_sectors']:
            print(f"\n➡️  NEUTRAL SECTORS:")
            for sector in momentum['neutral_sectors'][:3]:
                data = momentum['sectors'][sector]
                print(f"   {sector:<30} {data['score']:>+6.1f}%")

        print("\n" + "="*80)


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    detector = SectorRotationDetector()

    # Print sector report
    detector.print_sector_report()

    # Test specific stock
    print("\n" + "="*80)
    print("🔍 STOCK SECTOR ANALYSIS")
    print("="*80)

    test_stocks = [
        ('NVDA', 'Technology'),
        ('PFE', 'Healthcare'),
        ('XOM', 'Energy'),
        ('GLD', None)  # Will auto-detect
    ]

    for symbol, sector in test_stocks:
        status = detector.get_stock_sector_status(symbol, sector)
        print(f"\n{symbol} ({status['sector']}):")
        print(f"  Status: {status['status']}")
        print(f"  Momentum: {status['momentum_score']:+.1f}%")
        print(f"  {status['recommendation']}")
