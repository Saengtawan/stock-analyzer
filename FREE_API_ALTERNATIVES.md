# Free API Alternatives to FMP

## Problem
FMP Free tier: Only 250 requests/day
Current usage: ~60-300 requests/day for screening
**Too close to limit!**

## ✅ Solution 1: Tiingo Fundamentals (Best - Already Have!)

### Why Tiingo?
- ✅ **Already configured** in system
- ✅ **1,000 requests/hour** (4x more than Yahoo!)
- ✅ **Fundamentals API available** (just not implemented yet)
- ✅ **No credit card** required
- ✅ **Free forever**

### What Tiingo Provides:

**Already Using**:
- ✅ Price data (daily, weekly, monthly)
- ✅ Real-time prices
- ✅ Company info (name, exchange)
- ✅ Crypto data

**NOT Using Yet** (Available in Free Tier):
- ❌ **Fundamentals** (P/E, EPS, Market Cap, etc.)
- ❌ **News sentiment**
- ❌ **Institutional holdings**
- ❌ **Meta data** (sector, industry, description)

### How to Add Tiingo Fundamentals:

**Step 1**: Update `tiingo_client.py` to add fundamentals endpoint

```python
# src/api/tiingo_client.py

def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
    """
    Get fundamental data from Tiingo

    Tiingo fundamentals endpoint:
    https://api.tiingo.com/tiingo/fundamentals/{symbol}/daily?token=YOUR_TOKEN

    Returns:
        Dictionary with fundamental data including:
        - Market cap, P/E ratio, EPS
        - Revenue, profit margins
        - 52-week high/low
        - Beta, shares outstanding
    """
    try:
        # Tiingo fundamentals endpoint (daily updates)
        endpoint = f"https://api.tiingo.com/tiingo/fundamentals/{symbol}/daily"
        params = {
            'token': self.api_key,
            'startDate': '2024-01-01',  # Get latest year
            'format': 'json'
        }

        response = self._make_request(endpoint, params)

        if 'detail' in response:
            raise APIError(f"Tiingo error: {response['detail']}")

        if not response:
            raise APIError(f"No fundamental data found for {symbol}")

        # Get most recent data
        latest = response[-1] if isinstance(response, list) else response

        # Extract useful metrics
        statement_data = latest.get('statementData', {})
        daily_data = latest.get('dailyData', {})

        return {
            'symbol': symbol,
            'date': latest.get('date'),

            # Valuation metrics
            'marketCap': daily_data.get('marketCap'),
            'enterpriseVal': daily_data.get('enterpriseVal'),
            'peRatio': daily_data.get('peRatio'),
            'pbRatio': daily_data.get('pbRatio'),
            'trailingPEG1Y': daily_data.get('trailingPEG1Y'),

            # Per share metrics
            'eps': statement_data.get('eps'),
            'epsGrowth': statement_data.get('epsGrowth'),
            'bookValuePerShare': statement_data.get('bookValuePerShare'),

            # Profitability
            'profitMargin': statement_data.get('profitMargin'),
            'grossMargin': statement_data.get('grossMargin'),
            'operatingMargin': statement_data.get('operatingMargin'),
            'roe': statement_data.get('roe'),  # Return on equity
            'roa': statement_data.get('roa'),  # Return on assets

            # Growth metrics
            'revenueGrowth': statement_data.get('revenueGrowth'),
            'netIncomeGrowth': statement_data.get('netIncomeGrowth'),

            # Financial health
            'debtToEquity': statement_data.get('debtToEquity'),
            'currentRatio': statement_data.get('currentRatio'),
            'freeCashFlow': statement_data.get('freeCashFlow'),

            # Share data
            'sharesBasic': statement_data.get('sharesBasic'),
            'sharesDiluted': statement_data.get('sharesDiluted'),

            # Additional
            'beta': daily_data.get('beta'),
            'week52High': daily_data.get('week52High'),
            'week52Low': daily_data.get('week52Low'),
        }

    except Exception as e:
        logger.error(f"Failed to get fundamentals for {symbol}: {e}")
        raise APIError(f"Failed to get fundamentals: {e}")


def get_meta_data(self, symbol: str) -> Dict[str, Any]:
    """
    Get company meta data from Tiingo

    Endpoint: https://api.tiingo.com/tiingo/fundamentals/{symbol}/meta?token=YOUR_TOKEN

    Returns sector, industry, description, etc.
    """
    try:
        endpoint = f"https://api.tiingo.com/tiingo/fundamentals/{symbol}/meta"
        params = {'token': self.api_key}

        response = self._make_request(endpoint, params)

        if 'detail' in response:
            raise APIError(f"Tiingo error: {response['detail']}")

        return {
            'symbol': symbol,
            'name': response.get('name'),
            'description': response.get('description'),
            'sector': response.get('sector'),
            'industry': response.get('industry'),
            'sicCode': response.get('sicCode'),
            'sicSector': response.get('sicSector'),
            'sicIndustry': response.get('sicIndustry'),
            'reportingCurrency': response.get('reportingCurrency'),
            'location': response.get('location'),
            'companyWebsite': response.get('companyWebsite'),
            'secFilingWebsite': response.get('secFilingWebsite'),
            'statementLastUpdated': response.get('statementLastUpdated'),
            'dailyLastUpdated': response.get('dailyLastUpdated'),
        }

    except Exception as e:
        logger.error(f"Failed to get meta data for {symbol}: {e}")
        raise APIError(f"Failed to get meta data: {e}")
```

**Step 2**: Update `tiingo_client.py` rate limit

```python
# Line 16: Update from 500 to 1000
def __init__(self, api_key: str):
    super().__init__(api_key, rate_limit=1000)  # Tiingo allows 1000/hour on free tier
```

**Step 3**: Use Tiingo as primary for fundamentals

```python
# src/api/data_manager.py

def get_financial_data(self, symbol: str) -> Dict[str, Any]:
    """Get financial data with fallback"""

    # Try Tiingo first (1000/hr, better than FMP's 250/day!)
    if self.tiingo_client:
        try:
            fundamentals = self.tiingo_client.get_fundamentals(symbol)
            meta = self.tiingo_client.get_meta_data(symbol)

            # Combine data
            return {
                **fundamentals,
                **meta,
                'source': 'tiingo'
            }
        except Exception as e:
            logger.warning(f"Tiingo fundamentals failed for {symbol}: {e}")

    # Fallback to Yahoo
    try:
        return self.yahoo_client.get_financial_data(symbol)
    except Exception as e:
        logger.warning(f"Yahoo fundamentals failed for {symbol}: {e}")

    # Last resort: FMP
    if self.fmp_client:
        try:
            return self.fmp_client.get_financial_data(symbol)
        except Exception as e:
            logger.error(f"FMP fundamentals also failed for {symbol}: {e}")

    raise APIError(f"Failed to get financial data for {symbol} from all sources")
```

### Benefits:
- **API Calls**: 0 FMP calls → use Tiingo instead
- **Limit**: 250/day → 1,000/hour (96x increase!)
- **Cost**: $0 (already configured)
- **Setup**: Just add 2 methods to existing client

---

## 🔥 Solution 2: Add Finnhub (Best Coverage)

### Why Finnhub?
- ✅ **60 calls/minute** = 3,600/hour
- ✅ **Best free tier** among all providers
- ✅ **More data** than FMP free (earnings, news, sentiment)
- ✅ **No credit card** required

### Setup:

**Step 1**: Get free API key
```bash
# Visit: https://finnhub.io/register
# Free tier: 60 calls/min, no credit card needed
```

**Step 2**: Create `finnhub_client.py`

```python
# src/api/finnhub_client.py

"""Finnhub API Client"""
import requests
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, timedelta
from loguru import logger

from .base_client import BaseAPIClient, DataCache, APIError


class FinnhubClient(BaseAPIClient):
    """Finnhub API client - Best free tier (60/min = 3,600/hour)"""

    def __init__(self, api_key: str):
        super().__init__(api_key, rate_limit=3600)  # 60/min
        self.base_url = "https://finnhub.io/api/v1"
        self.cache = DataCache(ttl_minutes=60)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote"""
        endpoint = f"{self.base_url}/quote"
        params = {'symbol': symbol, 'token': self.api_key}

        response = self._make_request(endpoint, params)

        return {
            'symbol': symbol,
            'current_price': response.get('c'),
            'change': response.get('d'),
            'change_percent': response.get('dp'),
            'high': response.get('h'),
            'low': response.get('l'),
            'open': response.get('o'),
            'previous_close': response.get('pc'),
            'timestamp': response.get('t'),
        }

    def get_profile(self, symbol: str) -> Dict[str, Any]:
        """Get company profile (sector, industry, market cap)"""
        endpoint = f"{self.base_url}/stock/profile2"
        params = {'symbol': symbol, 'token': self.api_key}

        response = self._make_request(endpoint, params)

        return {
            'symbol': symbol,
            'name': response.get('name'),
            'marketCap': response.get('marketCapitalization') * 1_000_000,  # Convert to dollars
            'sector': response.get('finnhubIndustry'),
            'country': response.get('country'),
            'currency': response.get('currency'),
            'exchange': response.get('exchange'),
            'ipo': response.get('ipo'),
            'phone': response.get('phone'),
            'sharesOutstanding': response.get('shareOutstanding') * 1_000_000,
            'weburl': response.get('weburl'),
            'logo': response.get('logo'),
        }

    def get_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get basic financials (P/E, EPS, Beta, etc.)"""
        endpoint = f"{self.base_url}/stock/metric"
        params = {'symbol': symbol, 'metric': 'all', 'token': self.api_key}

        response = self._make_request(endpoint, params)
        metric = response.get('metric', {})

        return {
            'symbol': symbol,
            # Valuation
            'peRatio': metric.get('peBasicExclExtraTTM'),
            'peForward': metric.get('peNormalizedAnnual'),
            'pbRatio': metric.get('pbAnnual'),
            'psRatio': metric.get('psAnnual'),
            'pegRatio': metric.get('peg5YAverage'),

            # Per share
            'eps': metric.get('epsBasicExclExtraItemsTTM'),
            'epsGrowth': metric.get('epsGrowth3Y'),
            'bookValuePerShare': metric.get('bookValuePerShareAnnual'),

            # Profitability
            'profitMargin': metric.get('netProfitMarginTTM'),
            'operatingMargin': metric.get('operatingMarginTTM'),
            'roe': metric.get('roeTTM'),
            'roa': metric.get('roaTTM'),

            # Growth
            'revenueGrowth': metric.get('revenueGrowth3Y'),
            'revenuePerShare': metric.get('salesPerShareTTM'),

            # Technical
            'beta': metric.get('beta'),
            'week52High': metric.get('52WeekHigh'),
            'week52Low': metric.get('52WeekLow'),

            # Dividend
            'dividendYield': metric.get('dividendYieldIndicatedAnnual'),
        }

    def get_earnings_calendar(self, symbol: str) -> List[Dict[str, Any]]:
        """Get earnings calendar"""
        endpoint = f"{self.base_url}/calendar/earnings"
        params = {'symbol': symbol, 'token': self.api_key}

        response = self._make_request(endpoint, params)

        return response.get('earningsCalendar', [])

    def get_news(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get company news"""
        from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')

        endpoint = f"{self.base_url}/company-news"
        params = {
            'symbol': symbol,
            'from': from_date,
            'to': to_date,
            'token': self.api_key
        }

        return self._make_request(endpoint, params)


# Add to data_manager.py
def __init__(self, config: Dict[str, Any] = None):
    # ... existing code ...

    # Finnhub client (optional, requires API key)
    finnhub_key = os.getenv('FINNHUB_API_KEY')
    self.finnhub_client = None
    if finnhub_key:
        from .finnhub_client import FinnhubClient
        self.finnhub_client = FinnhubClient(finnhub_key)
```

**Step 3**: Add to `.env`

```bash
FINNHUB_API_KEY=your_free_key_here
```

---

## 🌟 Solution 3: Add IEX Cloud (Best Monthly Limit)

### Why IEX Cloud?
- ✅ **50,000 messages/month** (≈1,667/day)
- ✅ **Real-time data**
- ✅ **Great for fundamentals**

### Setup:

```bash
# Get free key: https://iexcloud.io/cloud-login#/register
# Free tier: 50,000 messages/month
```

```python
# src/api/iex_client.py

class IEXClient(BaseAPIClient):
    """IEX Cloud API client"""

    def __init__(self, api_key: str):
        super().__init__(api_key, rate_limit=50000)  # Monthly limit
        self.base_url = "https://cloud.iexapis.com/stable"

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get quote (costs 1 message)"""
        endpoint = f"{self.base_url}/stock/{symbol}/quote"
        params = {'token': self.api_key}

        response = self._make_request(endpoint, params)

        return {
            'symbol': symbol,
            'current_price': response.get('latestPrice'),
            'change': response.get('change'),
            'change_percent': response.get('changePercent') * 100,
            'marketCap': response.get('marketCap'),
            'peRatio': response.get('peRatio'),
            'week52High': response.get('week52High'),
            'week52Low': response.get('week52Low'),
        }

    def get_stats(self, symbol: str) -> Dict[str, Any]:
        """Get key stats (costs 20 messages)"""
        endpoint = f"{self.base_url}/stock/{symbol}/stats"
        params = {'token': self.api_key}

        return self._make_request(endpoint, params)
```

---

## 📊 Recommendation Priority

### Immediate (Today):
1. ✅ **Enable Tiingo Fundamentals** (already have, just add methods)
   - Cost: $0
   - Effort: 30 minutes
   - Benefit: 1,000/hour vs FMP 250/day

### This Week:
2. 🔥 **Add Finnhub** (best free tier)
   - Cost: $0
   - Effort: 1 hour
   - Benefit: 3,600/hour, best coverage

### Optional:
3. 🌟 **Add IEX Cloud** (backup)
   - Cost: $0
   - Effort: 1 hour
   - Benefit: 50K/month

---

## 🎯 Final Architecture

```
Primary: Yahoo Finance (2,000/hr) - Prices + Quick Fundamentals
Backup 1: Tiingo (1,000/hr) - Prices + Fundamentals + Meta
Backup 2: Finnhub (3,600/hr) - Fundamentals + News + Earnings
Backup 3: IEX Cloud (50K/month) - Real-time + Stats
Last Resort: FMP (250/day) - Only if all others fail
```

### API Call Flow:
```python
1. Try Yahoo (fast, reliable)
   ↓ fail
2. Try Tiingo (1000/hr, fundamentals)
   ↓ fail
3. Try Finnhub (3600/hr, best free tier)
   ↓ fail
4. Try IEX Cloud (50K/month)
   ↓ fail
5. Try FMP (last resort, 250/day limit)
   ↓ fail
6. Use cached/estimated data (graceful degradation)
```

### Total Free Tier Capacity:
```
Yahoo:     2,000/hour
Tiingo:    1,000/hour
Finnhub:   3,600/hour
IEX:       1,667/day

Combined:  6,600/hour + 1,667/day
Screening: 60-300 calls/day

Usage:     60/6600 = 0.9% of hourly capacity
           300/1667 = 18% of IEX daily capacity

Risk:      🟢 VERY LOW
```

---

## Next Steps

1. **Immediate**: Add Tiingo fundamentals methods (30 min)
2. **Today**: Test Tiingo fundamentals with screener
3. **This week**: Add Finnhub as additional backup
4. **Monitor**: Track API usage, should never hit limits now

After these changes:
- **No more FMP rate limiting** (have 6,600/hour capacity!)
- **100% free tier**
- **Better data quality** (multiple sources)
- **Higher reliability** (4 backups instead of 1)
