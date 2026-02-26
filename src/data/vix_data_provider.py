"""
VIX Data Provider

Fetches and caches VIX (^VIX) data from yfinance.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class VIXDataProvider:
    """
    Provides VIX data with local caching.

    Features:
    - Fetches VIX from Yahoo Finance (^VIX)
    - Caches data locally to reduce API calls
    - Provides current and historical VIX values
    - Auto-refreshes on market open

    Usage:
        >>> provider = VIXDataProvider()
        >>> vix = provider.get_current_vix()
        >>> print(f"Current VIX: {vix:.2f}")
        Current VIX: 18.45
    """

    def __init__(self, cache_duration_hours: int = 1):
        """
        Initialize VIX data provider.

        Args:
            cache_duration_hours: How long to cache data (default 1 hour)
        """
        self.cache_duration = timedelta(hours=cache_duration_hours)
        self.vix_data: Optional[pd.DataFrame] = None
        self.last_fetch: Optional[datetime] = None

    def _needs_refresh(self) -> bool:
        """Check if cache needs refresh."""
        if self.vix_data is None or self.last_fetch is None:
            return True

        time_since_fetch = datetime.now() - self.last_fetch
        return time_since_fetch > self.cache_duration

    def fetch_vix_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Fetch VIX data from Yahoo Finance.

        Args:
            start_date: Start date (YYYY-MM-DD). Defaults to 1 year ago.
            end_date: End date (YYYY-MM-DD). Defaults to today.
            force_refresh: Force refresh even if cache is valid

        Returns:
            DataFrame with columns: ['date', 'vix']
        """
        # Check cache
        if not force_refresh and not self._needs_refresh():
            logger.debug("Using cached VIX data")
            return self.vix_data

        # Set default dates
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        if start_date is None:
            start = datetime.now() - timedelta(days=365)
            start_date = start.strftime('%Y-%m-%d')

        try:
            logger.info(f"Fetching VIX data from {start_date} to {end_date}")
            vix_ticker = yf.Ticker("^VIX")
            vix_df = vix_ticker.history(start=start_date, end=end_date)

            if vix_df.empty:
                logger.error("No VIX data returned from yfinance")
                raise ValueError("Failed to fetch VIX data")

            # Create clean DataFrame
            vix_data = pd.DataFrame(index=vix_df.index)
            vix_data['vix'] = vix_df['Close'].values
            vix_data.index = pd.to_datetime(vix_data.index).date

            # Cache
            self.vix_data = vix_data
            self.last_fetch = datetime.now()

            logger.info(f"✅ Fetched {len(vix_data)} days of VIX data")
            logger.info(f"   VIX range: {vix_data['vix'].min():.2f} - {vix_data['vix'].max():.2f}")

            return vix_data

        except Exception as e:
            logger.error(f"Failed to fetch VIX data: {e}")
            raise

    def get_current_vix(self, force_refresh: bool = False) -> float:
        """
        Get current VIX value.

        v6.56: Uses intraday (period='1d') bars to return live VIX during
        market hours. Falls back to cached daily data on error.

        Args:
            force_refresh: Force refresh from API

        Returns:
            Current VIX value
        """
        # v6.56: Try live intraday data first (period='1d' → 1m bars = live price)
        try:
            vix_ticker = yf.Ticker("^VIX")
            vix_intraday = vix_ticker.history(period='1d')
            if not vix_intraday.empty:
                val = float(vix_intraday['Close'].iloc[-1])
                if 5 <= val <= 100:
                    return val
        except Exception as e:
            logger.debug(f"VIX intraday fetch failed: {e} — using cached daily data")

        # Fallback: use cached daily historical data
        if self._needs_refresh() or force_refresh:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start = datetime.now() - timedelta(days=5)
            start_date = start.strftime('%Y-%m-%d')
            self.fetch_vix_data(start_date=start_date, end_date=end_date, force_refresh=True)

        if self.vix_data is None or len(self.vix_data) == 0:
            raise ValueError("No VIX data available")

        return float(self.vix_data['vix'].iloc[-1])

    def get_vix_history(
        self,
        days: int = 30,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Get VIX history for N days.

        Args:
            days: Number of days to look back
            force_refresh: Force refresh from API

        Returns:
            DataFrame with VIX history
        """
        if self._needs_refresh() or force_refresh:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start = datetime.now() - timedelta(days=days + 10)  # +10 buffer
            start_date = start.strftime('%Y-%m-%d')

            self.fetch_vix_data(start_date=start_date, end_date=end_date, force_refresh=True)

        if self.vix_data is None:
            raise ValueError("No VIX data available")

        return self.vix_data.tail(days).copy()

    def get_vix_for_date(self, date) -> Optional[float]:
        """
        Get VIX value for specific date.

        Args:
            date: Date (datetime.date or pd.Timestamp)

        Returns:
            VIX value or None if not available
        """
        if self.vix_data is None:
            logger.warning("No VIX data loaded")
            return None

        # Convert to date if needed
        if isinstance(date, pd.Timestamp):
            date = date.date()

        if date in self.vix_data.index:
            return float(self.vix_data.loc[date, 'vix'])
        else:
            # Fallback: use most recent available date (VIX may not have today's close yet)
            latest_date = self.vix_data.index[-1]
            latest_vix = float(self.vix_data['vix'].iloc[-1])
            logger.debug(
                f"VIX data not available for {date}, using latest available "
                f"({latest_date}: {latest_vix:.2f})"
            )
            return latest_vix

    def __repr__(self) -> str:
        if self.vix_data is None:
            return "VIXDataProvider(no data loaded)"

        days = len(self.vix_data)
        vix_range = f"{self.vix_data['vix'].min():.1f}-{self.vix_data['vix'].max():.1f}"
        return f"VIXDataProvider({days} days, VIX range: {vix_range})"
