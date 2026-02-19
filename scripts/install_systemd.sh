#!/bin/bash
#
# Install Auto Trading Engine as Systemd Service
# Usage: sudo ./scripts/install_systemd.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "======================================"
echo "  SYSTEMD SERVICE INSTALLATION"
echo "======================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Please run as root: sudo ./scripts/install_systemd.sh${NC}"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)
PROJECT_DIR="$ACTUAL_HOME/work/project/cc/stock-analyzer"

echo "User: $ACTUAL_USER"
echo "Home: $ACTUAL_HOME"
echo "Project: $PROJECT_DIR"
echo ""

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ Project directory not found: $PROJECT_DIR${NC}"
    exit 1
fi

# Check if service file exists
SERVICE_FILE="$PROJECT_DIR/scripts/auto-trading.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}❌ Service file not found: $SERVICE_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Service file found${NC}"
echo ""

# Stop service if running
if systemctl is-active --quiet auto-trading; then
    echo "⚠️  Auto Trading service is running. Stopping..."
    systemctl stop auto-trading
    echo -e "${GREEN}✅ Service stopped${NC}"
fi

# Copy service file
echo "📋 Copying service file..."
cp "$SERVICE_FILE" /etc/systemd/system/auto-trading.service
echo -e "${GREEN}✅ Service file copied to /etc/systemd/system/${NC}"
echo ""

# Reload systemd
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload
echo -e "${GREEN}✅ Systemd reloaded${NC}"
echo ""

# Enable service (auto-start on boot)
echo "🚀 Enabling auto-start on boot..."
systemctl enable auto-trading
echo -e "${GREEN}✅ Auto-start enabled${NC}"
echo ""

# Create logs directory if not exists
LOGS_DIR="$PROJECT_DIR/logs"
if [ ! -d "$LOGS_DIR" ]; then
    mkdir -p "$LOGS_DIR"
    chown $ACTUAL_USER:$ACTUAL_USER "$LOGS_DIR"
    echo -e "${GREEN}✅ Logs directory created${NC}"
fi

# Check .env file
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}⚠️  .env file not found!${NC}"
    echo ""
    echo "Please create .env file with:"
    echo "  ALPACA_API_KEY=your_key"
    echo "  ALPACA_SECRET_KEY=your_secret"
    echo "  ALPACA_PAPER=true"
    echo ""
    echo "Service installed but will not start without .env"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

echo ""
echo "======================================"
echo "  INSTALLATION COMPLETE"
echo "======================================"
echo ""
echo "Service: auto-trading.service"
echo "Status:  Installed & Enabled"
echo ""
echo "📋 Management Commands:"
echo ""
echo "  Start:   sudo systemctl start auto-trading"
echo "  Stop:    sudo systemctl stop auto-trading"
echo "  Restart: sudo systemctl restart auto-trading"
echo "  Status:  sudo systemctl status auto-trading"
echo "  Logs:    sudo journalctl -u auto-trading -f"
echo ""
echo "======================================"
echo ""

# Ask to start now
read -p "Start Auto Trading Engine now? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Starting Auto Trading Engine..."
    systemctl start auto-trading
    sleep 2

    if systemctl is-active --quiet auto-trading; then
        echo -e "${GREEN}✅ Service started successfully!${NC}"
        echo ""
        echo "Check status:"
        systemctl status auto-trading --no-pager
    else
        echo -e "${RED}❌ Service failed to start${NC}"
        echo ""
        echo "Check logs:"
        echo "  sudo journalctl -u auto-trading -n 50"
    fi
else
    echo ""
    echo "Service installed but not started."
    echo "To start: sudo systemctl start auto-trading"
fi

echo ""
echo "======================================"
echo "  SETUP COMPLETE"
echo "======================================"
echo ""
