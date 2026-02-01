#!/usr/bin/env python3
"""
Daily Portfolio Monitor v1.0

Runs DAILY to:
1. Check current market regime
2. Monitor all open positions
3. Auto-close positions if regime turns bad
4. Apply advanced exit rules to all positions
5. Send alerts/notifications

Usage:
    python daily_portfolio_monitor.py

Or set up as cron job:
    0 9 * * 1-5  cd /path/to/stock-analyzer && python3 src/daily_portfolio_monitor.py
    (Runs at 9 AM ET every weekday)
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import json
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, List, Any

try:
    from market_regime_detector import MarketRegimeDetector
    from advanced_exit_rules import AdvancedExitRules
except ImportError:
    # Fallback for testing
    logger.warning("Import error - using standalone mode")
    MarketRegimeDetector = None
    AdvancedExitRules = None


class DailyPortfolioMonitor:
    """
    Daily monitoring system for Growth Catalyst positions

    Checks:
    - Market regime (BULL/BEAR/SIDEWAYS)
    - Individual position health
    - Exit triggers (stop loss, trailing stop, regime change)

    Actions:
    - Auto-close positions if needed
    - Send alerts
    - Update portfolio file
    """

    def __init__(self, portfolio_file='portfolio.json'):
        self.portfolio_file = portfolio_file

        # Initialize components
        if MarketRegimeDetector:
            self.regime_detector = MarketRegimeDetector()
            logger.info("✅ Regime Detector initialized")
        else:
            self.regime_detector = None
            logger.warning("⚠️ Regime Detector not available")

        if AdvancedExitRules:
            self.exit_rules = AdvancedExitRules()
            logger.info("✅ Advanced Exit Rules initialized")
        else:
            self.exit_rules = None
            logger.warning("⚠️ Exit Rules not available")

        # Load portfolio
        self.positions = self._load_portfolio()

        # Alert settings
        self.alerts = []

    def run_daily_check(self):
        """
        Main daily check routine

        Returns:
            dict with summary of actions taken
        """
        logger.info("=" * 80)
        logger.info(f"🔍 DAILY PORTFOLIO CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        logger.info("=" * 80)

        summary = {
            'date': datetime.now().isoformat(),
            'regime': None,
            'positions_checked': 0,
            'positions_closed': 0,
            'alerts': [],
            'actions': []
        }

        # Step 1: Check Market Regime
        regime_info = self._check_market_regime()
        summary['regime'] = regime_info

        if not regime_info['should_trade']:
            # BEAR MARKET - Close all positions!
            logger.warning(f"🐻 BEAR MARKET DETECTED - Closing all positions")
            summary['actions'].append('CLOSE_ALL_POSITIONS')

            closed_count = self._close_all_positions('REGIME_BEAR')
            summary['positions_closed'] = closed_count

            alert = f"🚨 BEAR MARKET - Closed {closed_count} positions to protect capital"
            self._add_alert(alert, 'CRITICAL')
            summary['alerts'].append(alert)

            return summary

        # Step 2: Check individual positions
        if not self.positions:
            logger.info("📭 No open positions to monitor")
            return summary

        logger.info(f"📊 Monitoring {len(self.positions)} positions...")

        # Get SPY data for regime/filter checks
        spy_data = self._get_spy_data()

        # Check each position
        for symbol, position in list(self.positions.items()):
            summary['positions_checked'] += 1

            # Get stock data
            hist_data = self._get_stock_data(symbol)
            if hist_data is None:
                continue

            # Update position info
            position['days_held'] = (datetime.now() - pd.Timestamp(position['entry_date'])).days

            # Check if should exit
            should_exit, reason, exit_price = self._check_position_exit(
                position, hist_data, spy_data
            )

            if should_exit:
                # Close position
                logger.warning(f"❌ Closing {symbol}: {reason}")

                self._close_position(symbol, exit_price, reason)
                summary['positions_closed'] += 1
                summary['actions'].append(f"CLOSE_{symbol}_{reason}")

                # Calculate return
                entry_price = position['entry_price']
                return_pct = ((exit_price - entry_price) / entry_price) * 100

                alert = f"Closed {symbol}: {return_pct:+.2f}% ({reason})"
                self._add_alert(alert, 'HIGH' if return_pct < 0 else 'INFO')
                summary['alerts'].append(alert)
            else:
                # Update status
                current_price = float(hist_data['Close'].iloc[-1])
                current_return = ((current_price - position['entry_price']) / position['entry_price']) * 100

                logger.info(f"✅ {symbol}: Holding ({current_return:+.2f}%, {position['days_held']} days)")

        # Step 3: Save portfolio
        self._save_portfolio()

        # Step 4: Print summary
        logger.info("\n" + "=" * 80)
        logger.info("📊 DAILY CHECK SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Regime: {regime_info['regime']} ({regime_info['strength']}/100)")
        logger.info(f"Positions checked: {summary['positions_checked']}")
        logger.info(f"Positions closed: {summary['positions_closed']}")
        logger.info(f"Alerts: {len(summary['alerts'])}")

        if summary['alerts']:
            logger.info("\n🔔 Alerts:")
            for alert in summary['alerts']:
                logger.info(f"   - {alert}")

        logger.info("=" * 80)

        return summary

    def _check_market_regime(self):
        """Check current market regime"""
        if not self.regime_detector:
            return {
                'regime': 'UNKNOWN',
                'should_trade': True,
                'strength': 0,
                'position_size_multiplier': 1.0
            }

        try:
            regime_info = self.regime_detector.get_current_regime()

            logger.info(f"\n🌍 Market Regime:")
            logger.info(f"   Regime: {regime_info['regime']}")
            logger.info(f"   Strength: {regime_info['strength']}/100")
            logger.info(f"   Should Trade: {regime_info['should_trade']}")
            logger.info(f"   Position Size: {regime_info['position_size_multiplier']*100:.0f}%")

            return regime_info

        except Exception as e:
            logger.error(f"Regime check error: {e}")
            return {
                'regime': 'UNKNOWN',
                'should_trade': True,
                'strength': 0,
                'position_size_multiplier': 1.0
            }

    def _check_position_exit(self, position, hist_data, spy_data):
        """Check if position should be exited"""
        if not self.exit_rules:
            # Fallback to simple checks
            current_price = float(hist_data['Close'].iloc[-1])
            entry_price = position['entry_price']
            return_pct = ((current_price - entry_price) / entry_price) * 100

            # Simple hard stop
            if return_pct <= -10:
                return True, 'SIMPLE_STOP', current_price

            # Simple max hold
            if position['days_held'] >= 20:
                return True, 'MAX_HOLD', current_price

            return False, None, current_price

        try:
            # Use advanced exit rules
            return self.exit_rules.should_exit(
                position,
                datetime.now(),
                hist_data,
                spy_data
            )

        except Exception as e:
            logger.error(f"Exit check error for {position['symbol']}: {e}")
            current_price = float(hist_data['Close'].iloc[-1])
            return False, None, current_price

    def _close_position(self, symbol, exit_price, reason):
        """Close a single position"""
        if symbol not in self.positions:
            return

        position = self.positions[symbol]
        entry_price = position['entry_price']
        entry_date = position['entry_date']

        # Calculate metrics
        return_pct = ((exit_price - entry_price) / entry_price) * 100
        days_held = (datetime.now() - pd.Timestamp(entry_date)).days

        # Log trade
        trade_log = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_date': datetime.now().isoformat(),
            'exit_price': exit_price,
            'return_pct': return_pct,
            'days_held': days_held,
            'exit_reason': reason
        }

        logger.info(f"📝 Trade Log: {json.dumps(trade_log, indent=2)}")

        # Remove from portfolio
        del self.positions[symbol]

        # Save to trade history
        self._save_trade_history(trade_log)

    def _close_all_positions(self, reason):
        """Close all open positions"""
        closed_count = 0

        for symbol, position in list(self.positions.items()):
            try:
                # Get current price
                ticker = yf.Ticker(symbol)
                current_price = ticker.info.get('currentPrice', position['entry_price'])

                # Close
                self._close_position(symbol, current_price, reason)
                closed_count += 1

            except Exception as e:
                logger.error(f"Error closing {symbol}: {e}")

        return closed_count

    def _get_stock_data(self, symbol, days=60):
        """Get stock price data"""
        try:
            ticker = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"⚠️ No data for {symbol}")
                return None

            return hist

        except Exception as e:
            logger.error(f"Error getting data for {symbol}: {e}")
            return None

    def _get_spy_data(self, days=60):
        """Get SPY data for market checks"""
        try:
            spy = yf.Ticker('SPY')
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            return spy.history(start=start_date, end=end_date)

        except Exception as e:
            logger.error(f"Error getting SPY data: {e}")
            return None

    def _load_portfolio(self):
        """Load portfolio from file"""
        try:
            if not os.path.exists(self.portfolio_file):
                logger.info("📂 No portfolio file found - starting fresh")
                return {}

            with open(self.portfolio_file, 'r') as f:
                data = json.load(f)

            positions = data.get('positions', {})
            logger.info(f"📂 Loaded {len(positions)} positions from {self.portfolio_file}")

            return positions

        except Exception as e:
            logger.error(f"Error loading portfolio: {e}")
            return {}

    def _save_portfolio(self):
        """Save portfolio to file"""
        try:
            data = {
                'positions': self.positions,
                'last_updated': datetime.now().isoformat()
            }

            with open(self.portfolio_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"💾 Saved portfolio ({len(self.positions)} positions)")

        except Exception as e:
            logger.error(f"Error saving portfolio: {e}")

    def _save_trade_history(self, trade_log):
        """Save closed trade to history"""
        try:
            history_file = 'trade_history.json'

            # Load existing history
            history = []
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    history = json.load(f)

            # Add new trade
            history.append(trade_log)

            # Save
            with open(history_file, 'w') as f:
                json.dump(history, f, indent=2)

            logger.info(f"📊 Saved to trade history")

        except Exception as e:
            logger.error(f"Error saving trade history: {e}")

    def _add_alert(self, message, priority='INFO'):
        """Add alert to list"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'priority': priority,
            'message': message
        }
        self.alerts.append(alert)

        # Could send email/SMS here in production
        if priority == 'CRITICAL':
            logger.critical(f"🚨 {message}")
        elif priority == 'HIGH':
            logger.warning(f"⚠️ {message}")
        else:
            logger.info(f"ℹ️ {message}")


def main():
    """Main entry point for daily monitoring"""
    print("=" * 80)
    print("🔍 GROWTH CATALYST - DAILY PORTFOLIO MONITOR")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 80)

    # Create monitor
    monitor = DailyPortfolioMonitor()

    # Run daily check
    summary = monitor.run_daily_check()

    # Exit code based on results
    if summary['regime']['regime'] == 'BEAR':
        print("\n🐻 BEAR MARKET - All positions closed")
        sys.exit(1)  # Non-zero exit for alerts

    if summary['positions_closed'] > 0:
        print(f"\n⚠️ Closed {summary['positions_closed']} positions")
        sys.exit(1)  # Non-zero exit for alerts

    print("\n✅ All positions healthy - no action needed")
    sys.exit(0)


if __name__ == "__main__":
    main()
