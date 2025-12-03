"""
Enhanced Features for Stock Analysis
Version 2.0 - With Anti-Stop Hunt Protection

Core Features:
1. Real-Time Price Action + Entry Readiness
2. P&L Tracker + Target Progress (Auto-entry)
3. Trailing Stop Loss
4. Short Interest Data
5. Decision Matrix
6. Risk Status Change Alert

🆕 New Features (v2.0):
7. Liquidity Grab Detector - ตรวจจับการกวาด Stop Loss
8. Stop Loss Heatmap - แสดงจุดที่มี SL กองอยู่เยอะ
"""

from .real_time_monitor import RealTimePriceMonitor
from .pnl_tracker import ProfitLossTracker
from .trailing_stop import TrailingStopManager
from .short_interest import ShortInterestAnalyzer
from .decision_engine import DecisionMatrix
from .risk_alerts import RiskAlertManager
from .feature_integration import EnhancedAnalysis, analyze_stock

# 🆕 Anti-Stop Hunt Features
from .liquidity_grab_detector import LiquidityGrabDetector, format_liquidity_grab
from .sl_heatmap import StopLossHeatmap, format_sl_heatmap

__all__ = [
    # Core Features
    'RealTimePriceMonitor',
    'ProfitLossTracker',
    'TrailingStopManager',
    'ShortInterestAnalyzer',
    'DecisionMatrix',
    'RiskAlertManager',
    'EnhancedAnalysis',
    'analyze_stock',

    # 🆕 Anti-Stop Hunt Features (v2.0)
    'LiquidityGrabDetector',
    'format_liquidity_grab',
    'StopLossHeatmap',
    'format_sl_heatmap',
]

__version__ = '2.0.0'
