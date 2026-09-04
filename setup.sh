#!/bin/bash
# Stock Analyzer — Quick Setup
echo "=== Stock Analyzer Setup ==="

# 1. Check Python
python3 --version || { echo "Need Python 3.11+"; exit 1; }

# 2. Install dependencies
pip install yfinance requests python-dotenv numpy pytz sqlalchemy

# 3. Check .env
if [ ! -f .env ]; then
    echo ""
    echo "=== สร้าง .env ==="
    echo "ต้องใส่ API keys:"
    echo ""
    cat > .env << 'EOF'
# Alpaca Paper Trading API
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
EOF
    echo "แก้ .env ใส่ Alpaca keys ก่อนรัน"
fi

# 4. Check DB
if [ ! -f data/trade_history.db ]; then
    echo ""
    echo "=== DB ไม่มี ==="
    echo "ต้อง copy จากเครื่องเดิม:"
    echo "  scp user@server:~/stock-analyzer/data/trade_history.db data/"
    echo ""
    echo "หรือสร้าง DB เปล่า (ไม่มี historical data):"
    echo "  mkdir -p data && python3 -c \"import sqlite3; sqlite3.connect('data/trade_history.db')\""
fi

echo ""
echo "=== Done ==="
echo "ทดสอบ: python3 -c \"from dotenv import load_dotenv; load_dotenv(); import os; print('Alpaca:', os.getenv('ALPACA_API_KEY','NOT SET')[:8])\""
