# API Migration Guide: Alpha Vantage → FMP + Tiingo

## 📋 Overview

This guide explains the migration from Alpha Vantage to Financial Modeling Prep (FMP) and Tiingo APIs for improved data quality and reliability.

## 🔄 What Changed

### **Before (v1.0.0)**
- **Primary**: Yahoo Finance
- **Backup**: Alpha Vantage (5 calls/minute)
- **Limited**: Poor rate limits and data quality

### **After (v1.1.0)**
- **Primary**: Yahoo Finance
- **Backup**: FMP (300 calls/day)
- **Price Backup**: Tiingo (500 calls/hour)
- **Improved**: Better rate limits and data quality

## 🆕 New API Clients

### 1. Financial Modeling Prep (FMP)
```python
from src.api.fmp_client import FMPClient

# Initialize with API key
client = FMPClient(api_key="your_fmp_key")

# Get price data
price_data = client.get_price_data("AAPL", period="1y")

# Get comprehensive financial data
financial_data = client.get_financial_data("AAPL")

# Get real-time price
real_time = client.get_real_time_price("AAPL")
```

**Features:**
- ✅ Comprehensive fundamental data
- ✅ Key financial ratios
- ✅ Income statement, balance sheet, cash flow
- ✅ Company profiles and metrics
- ✅ Historical and real-time price data
- ✅ 300 free API calls per day

### 2. Tiingo API
```python
from src.api.tiingo_client import TiingoClient

# Initialize with API key
client = TiingoClient(api_key="your_tiingo_key")

# Get high-quality price data
price_data = client.get_price_data("AAPL", period="1y")

# Get intraday data
intraday = client.get_intraday_data("AAPL", interval="5min")

# Get crypto data
crypto_data = client.get_crypto_data("btcusd")
```

**Features:**
- ✅ High-quality price data
- ✅ Intraday data (1min, 5min, 15min, 30min, 1hour)
- ✅ Cryptocurrency support
- ✅ 500 free requests per hour
- ❌ No fundamental data (use FMP for this)

## 🔧 Environment Setup

### Required API Keys

1. **FMP API Key** (Free)
   - Sign up: https://financialmodelingprep.com/developer/docs
   - Free tier: 300 calls/day
   - Environment variable: `FMP_API_KEY`

2. **Tiingo API Key** (Free)
   - Sign up: https://api.tiingo.com/
   - Free tier: 500 requests/hour
   - Environment variable: `TIINGO_API_KEY`

### Environment Variables
```bash
# Add to your .env file
FMP_API_KEY=your_fmp_api_key_here
TIINGO_API_KEY=your_tiingo_api_key_here

# Or export directly
export FMP_API_KEY="your_fmp_api_key_here"
export TIINGO_API_KEY="your_tiingo_api_key_here"
```

## 🎛 Configuration Changes

### settings.yaml Updates
```yaml
# Data Sources
data_sources:
  primary: "yfinance"     # Yahoo Finance (free, no key required)
  backup: "fmp"           # Financial Modeling Prep
  price_backup: "tiingo"  # Tiingo for price data
  financial_data: "fmp"   # FMP for fundamentals

# API Rate Limits
rate_limits:
  fmp: 300              # calls per day (free tier)
  tiingo: 500           # calls per hour (free tier)
  yfinance: 2000        # calls per hour
```

## 📊 Data Source Strategy

### Fallback Hierarchy

1. **Price Data**:
   - Primary: Yahoo Finance (yfinance)
   - Backup: FMP
   - Price Backup: Tiingo

2. **Fundamental Data**:
   - Primary: Yahoo Finance
   - Backup: FMP (preferred for comprehensive data)

3. **Real-time Data**:
   - Primary: Yahoo Finance
   - Backup: FMP
   - Fallback: Tiingo

### Smart Data Routing
```python
# DataManager automatically handles fallbacks
data_manager = DataManager(config)

# Will try Yahoo → FMP → Tiingo for price data
price_data = data_manager.get_price_data("AAPL")

# Will try Yahoo → FMP for fundamental data
financial_data = data_manager.get_financial_data("AAPL")
```

## 🔍 Key Improvements

### 1. **Better Rate Limits**
- FMP: 300 calls/day (vs Alpha Vantage: 5 calls/minute)
- Tiingo: 500 calls/hour (vs Alpha Vantage: 5 calls/minute)

### 2. **Higher Data Quality**
- FMP: Comprehensive fundamental metrics
- Tiingo: Professional-grade price data
- Better error handling and data validation

### 3. **Enhanced Reliability**
- 3-tier fallback system
- Multiple data sources for redundancy
- Automatic retry and error recovery

### 4. **More Features**
- Intraday data from Tiingo
- Cryptocurrency support
- Better financial ratios from FMP
- Enhanced company profiles

## 🧪 Testing Your Setup

### Basic Test
```python
from src.api.data_manager import DataManager

# Test data manager with new APIs
dm = DataManager()

# Test price data (will use fallback if needed)
price_data = dm.get_price_data('AAPL', period='5d')
print(f"Retrieved {len(price_data)} price points")

# Test financial data
financial_data = dm.get_financial_data('AAPL')
print(f"P/E Ratio: {financial_data.get('pe_ratio')}")

# Test real-time data
real_time = dm.get_real_time_price('AAPL')
print(f"Current price: ${real_time.get('current_price')}")
```

### Run System Test
```bash
# Run the existing test suite
python src/test_main.py

# Or run specific API tests
python -c "
from src.api.data_manager import DataManager
dm = DataManager()
print('✓ DataManager working with new APIs')
"
```

## 🚨 Breaking Changes

### **Removed**
- `alpha_vantage_client.py` - Deleted
- Alpha Vantage references in configuration
- `alpha-vantage` package dependency

### **Modified**
- `data_manager.py` - Updated to use FMP + Tiingo
- `settings.yaml` - New API configuration
- `requirements.txt` - Removed alpha-vantage dependency

### **Added**
- `fmp_client.py` - New FMP client
- `tiingo_client.py` - New Tiingo client
- Enhanced fallback mechanisms

## 🔒 Security Notes

- Store API keys in environment variables, never in code
- Use `.env` file for local development
- Add `.env` to `.gitignore`
- Rotate API keys regularly
- Monitor API usage to avoid rate limits

## 🆘 Troubleshooting

### Common Issues

1. **"FMP API key not found"**
   ```bash
   export FMP_API_KEY="your_key_here"
   ```

2. **"Tiingo rate limit exceeded"**
   - Check your usage at https://api.tiingo.com/
   - Wait for rate limit reset
   - Use caching to reduce API calls

3. **"No data available"**
   - Check if all API keys are set
   - Verify internet connection
   - Check API service status

### Debug Mode
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test individual clients
from src.api.fmp_client import FMPClient
client = FMPClient("your_key")
data = client.get_price_data("AAPL")
```

## 📞 Support

- 📧 Create GitHub issue for bugs
- 📖 Check API documentation:
  - FMP: https://financialmodelingprep.com/developer/docs
  - Tiingo: https://api.tiingo.com/docs/
- 🔍 Enable debug logging for troubleshooting

---

**Migration completed successfully! 🎉**

The new API setup provides better reliability, higher rate limits, and improved data quality for your stock analysis needs.