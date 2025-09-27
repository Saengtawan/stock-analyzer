# 🚀 Quick Setup Guide

## Prerequisites

- Python 3.8+
- Git
- Internet connection

## 1-Minute Setup

### Step 1: Clone and Install
```bash
git clone https://github.com/your-username/stock-analyzer.git
cd stock-analyzer
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
```

### Step 2: Get API Keys (Free)

1. **FMP API Key** (2 minutes):
   - Go to: https://financialmodelingprep.com/developer/docs
   - Sign up (free)
   - Copy your API key

2. **Tiingo API Key** (2 minutes):
   - Go to: https://api.tiingo.com/
   - Sign up (free)
   - Copy your API key

### Step 3: Configure Environment
```bash
cp .env.example .env
# Edit .env file and add your API keys:
# FMP_API_KEY=your_fmp_key_here
# TIINGO_API_KEY=your_tiingo_key_here
```

### Step 4: Test Installation
```bash
python src/test_main.py
```

### Step 5: Run Analysis
```bash
python src/main.py analyze --symbol AAPL
```

## Done! 🎉

Your stock analyzer is ready to use.

## Quick Commands

```bash
# Analyze a stock
python src/main.py analyze --symbol AAPL

# Screen multiple stocks
python src/main.py screen --symbols AAPL MSFT GOOGL

# Run backtest
python src/main.py backtest --symbols AAPL --start-date 2023-01-01

# Start web interface
cd src/web && python app.py
```

## Need Help?

- 📖 Read [README.md](README.md) for detailed documentation
- 🔄 Check [API_MIGRATION_GUIDE.md](API_MIGRATION_GUIDE.md) for API details
- 🐛 Report issues on GitHub