#!/bin/bash
# Restart Stock Analyzer Web Server

echo "🔄 Restarting Stock Analyzer Web Server..."
echo "=========================================="

# Kill existing processes
echo "🛑 Stopping existing server..."
pkill -f "python.*run_app.py" || echo "   No existing server found"
sleep 2

# Go to project directory
cd /home/saengtawan/work/project/cc/stock-analyzer

# Start new server
echo "🚀 Starting new server..."
echo "   Port: 5002"
echo "   URL: http://localhost:5002"
echo ""
python src/run_app.py --port 5002

