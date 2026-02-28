"""yfinance fetch helpers with retry (v6.73)"""
import time
import random
from typing import Optional
import pandas as pd

_RATE_LIMIT_KEYWORDS = ('429', 'rate', 'too many', 'unauthorized', 'crumb')


def fetch_history(symbol: str, period: str = '30d', interval: str = '1d',
                  max_retries: int = 3) -> Optional[pd.DataFrame]:
    """
    Fetch yfinance ticker history with exponential backoff on rate limit.
    Returns DataFrame or None (never raises).
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    for attempt in range(max_retries):
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
            if df is not None and not df.empty:
                return df
            return None  # Empty result — no point retrying
        except Exception as e:
            err = str(e).lower()
            is_rate_limit = any(k in err for k in _RATE_LIMIT_KEYWORDS)
            if attempt < max_retries - 1:
                wait = (5 * (2 ** attempt) if is_rate_limit else 2) + random.uniform(0, 1.5)
                time.sleep(wait)
    return None
