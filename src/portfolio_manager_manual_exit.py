#!/usr/bin/env python3
"""
Portfolio Manager with Manual Exit Confirmation
================================================

แทนที่จะ auto-exit หุ้นทันที ระบบจะ:
1. ตรวจสอบ exit rules ทุกวัน
2. เมื่อมี exit signal → เปลี่ยนสถานะเป็น "exit_signal"
3. ผู้ใช้ตัดสินใจเองว่าจะ exit จริงหรือไม่

Status ของหุ้น:
- "active" - หุ้นปกติ ยังไม่มี exit signal
- "exit_signal" - มี exit signal แล้ว รอผู้ใช้ตัดสินใจ
- "exited" - ออกแล้ว (moved to closed)

Fields ใหม่:
- status: str - สถานะปัจจุบัน
- exit_signal: dict or None - ข้อมูล exit signal
  {
    "rule": "TARGET_HIT",
    "detected_date": "2026-01-09",
    "price_at_signal": 104.5,
    "pnl_at_signal": 4.5,
    "reason": "Hit target 4.5% >= 4.0%"
  }
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from loguru import logger
import yfinance as yf

try:
    from exit_rules_engine import ExitRulesEngine, MarketData
except ImportError:
    from src.exit_rules_engine import ExitRulesEngine, MarketData


class PortfolioManagerManualExit:
    """
    Portfolio Manager with Manual Exit Confirmation

    ไม่ auto-exit แต่ให้ผู้ใช้ตัดสินใจเอง
    """

    def __init__(self, portfolio_file: str = 'portfolio.json'):
        self.portfolio_file = portfolio_file
        self.exit_rules = ExitRulesEngine()
        self.portfolio = self._load_portfolio()

    def _load_portfolio(self) -> Dict:
        """Load portfolio from JSON file"""
        if not os.path.exists(self.portfolio_file):
            return {
                'active': [],
                'closed': [],
                'stats': {
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'avg_winner': 0.0,
                    'avg_loser': 0.0
                }
            }

        with open(self.portfolio_file, 'r') as f:
            portfolio = json.load(f)

        # Migrate old format to new format (add status if missing)
        for position in portfolio.get('active', []):
            if 'status' not in position:
                position['status'] = 'active'
            if 'exit_signal' not in position:
                position['exit_signal'] = None

        return portfolio

    def _save_portfolio(self):
        """Save portfolio to JSON file"""
        with open(self.portfolio_file, 'w') as f:
            json.dump(self.portfolio, f, indent=2, default=str)

    def add_position(self,
                    symbol: str,
                    entry_price: float,
                    amount: float,
                    entry_date: str = None) -> Dict:
        """
        Add new position to portfolio

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            amount: Dollar amount invested
            entry_date: Entry date (YYYY-MM-DD), defaults to today

        Returns:
            Position dict
        """
        if entry_date is None:
            entry_date = datetime.now().strftime('%Y-%m-%d')

        shares = amount / entry_price

        position = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'highest_price': entry_price,
            'amount': amount,
            'shares': shares,
            'status': 'active',
            'exit_signal': None,
            'days_held': 0,
            'filters_at_entry': {
                'source': 'manual'
            }
        }

        self.portfolio['active'].append(position)
        self._save_portfolio()

        logger.info(f"✅ Added {symbol} to portfolio: ${entry_price:.2f} x {shares:.2f} shares = ${amount:.2f}")

        return position

    def monitor_positions(self, update_signals: bool = True) -> Dict[str, Any]:
        """
        Monitor all active positions and detect exit signals

        Args:
            update_signals: If True, update exit_signal status when detected

        Returns:
            Summary dict with exit signals
        """
        logger.info("=" * 80)
        logger.info("🔍 MONITORING PORTFOLIO POSITIONS")
        logger.info("=" * 80)

        summary = {
            'total_positions': len(self.portfolio['active']),
            'active_no_signal': 0,
            'exit_signals_new': 0,
            'exit_signals_existing': 0,
            'positions': []
        }

        for position in self.portfolio['active']:
            result = self._check_position(position, update_signals)
            summary['positions'].append(result)

            if result['exit_signal']:
                if position['exit_signal'] is None and update_signals:
                    summary['exit_signals_new'] += 1
                else:
                    summary['exit_signals_existing'] += 1
            else:
                summary['active_no_signal'] += 1

        if update_signals:
            self._save_portfolio()

        # Print summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Positions: {summary['total_positions']}")
        logger.info(f"  Active (no signal): {summary['active_no_signal']}")
        logger.info(f"  Exit signals (new): {summary['exit_signals_new']}")
        logger.info(f"  Exit signals (existing): {summary['exit_signals_existing']}")

        if summary['exit_signals_new'] > 0:
            logger.warning("")
            logger.warning("⚠️  NEW EXIT SIGNALS DETECTED!")
            logger.warning(f"   {summary['exit_signals_new']} positions need your attention")
            logger.warning("   Use 'list_exit_signals()' to see details")
            logger.warning("   Use 'manual_exit()' to close positions")

        return summary

    def _check_position(self, position: Dict, update_signals: bool) -> Dict:
        """Check a single position for exit signals"""
        symbol = position['symbol']

        logger.info(f"\n📍 {symbol}:")
        logger.info(f"   Entry: ${position['entry_price']:.2f} on {position['entry_date']}")
        logger.info(f"   Status: {position['status']}")

        # Get current data
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='3mo')

            if hist.empty:
                logger.warning(f"   ⚠️  No price data available")
                return {
                    'symbol': symbol,
                    'status': position['status'],
                    'error': 'No price data',
                    'exit_signal': None
                }

            current_price = hist['Close'].iloc[-1]

            # Update highest price
            if current_price > position['highest_price']:
                position['highest_price'] = current_price

            # Calculate days held
            entry_date = datetime.strptime(position['entry_date'], '%Y-%m-%d')
            days_held = (datetime.now() - entry_date).days
            position['days_held'] = days_held

            # Calculate PnL
            pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
            pnl_dollar = (current_price - position['entry_price']) * position['shares']

            logger.info(f"   Current: ${current_price:.2f} ({pnl_pct:+.2f}%)")
            logger.info(f"   PnL: ${pnl_dollar:+.2f} | Days: {days_held}")

            # Prepare market data for exit rules
            close_prices = hist['Close'].tolist()[-30:]
            open_prices = hist['Open'].tolist()[-30:]
            volume_data = hist['Volume'].tolist()[-30:]

            market_data = MarketData(
                current_price=current_price,
                entry_price=position['entry_price'],
                highest_price=position['highest_price'],
                close_prices=close_prices,
                open_prices=open_prices,
                volume_data=volume_data,
                days_held=days_held
            )

            # Check exit rules
            exit_rule = self.exit_rules.evaluate(market_data, symbol)

            if exit_rule:
                # Exit signal detected!
                logger.warning(f"   🚨 EXIT SIGNAL: {exit_rule}")

                # Get rule details
                rule_obj = next((r for r in self.exit_rules.rules if r.name == exit_rule), None)

                exit_signal_data = {
                    'rule': exit_rule,
                    'detected_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'price_at_signal': current_price,
                    'pnl_pct_at_signal': pnl_pct,
                    'pnl_dollar_at_signal': pnl_dollar,
                    'days_held': days_held,
                    'category': rule_obj.category.value if rule_obj else 'unknown',
                    'priority': rule_obj.priority.name if rule_obj else 'unknown'
                }

                # Update position if requested
                if update_signals and position['exit_signal'] is None:
                    position['exit_signal'] = exit_signal_data
                    position['status'] = 'exit_signal'
                    logger.warning(f"   ⚠️  Status changed to: exit_signal")
                elif position['exit_signal']:
                    logger.info(f"   ℹ️  Exit signal already recorded on {position['exit_signal']['detected_date']}")

                return {
                    'symbol': symbol,
                    'status': 'exit_signal',
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                    'pnl_dollar': pnl_dollar,
                    'exit_signal': exit_signal_data
                }
            else:
                # No exit signal
                logger.info(f"   ✅ Active (no exit signal)")

                return {
                    'symbol': symbol,
                    'status': position['status'],
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                    'pnl_dollar': pnl_dollar,
                    'exit_signal': None
                }

        except Exception as e:
            logger.error(f"   ❌ Error checking {symbol}: {e}")
            return {
                'symbol': symbol,
                'status': position['status'],
                'error': str(e),
                'exit_signal': None
            }

    def list_exit_signals(self) -> List[Dict]:
        """List all positions with exit signals"""
        exit_signal_positions = [
            p for p in self.portfolio['active']
            if p.get('status') == 'exit_signal' or p.get('exit_signal') is not None
        ]

        if not exit_signal_positions:
            logger.info("✅ No exit signals - all positions are active")
            return []

        logger.info("=" * 80)
        logger.info("🚨 POSITIONS WITH EXIT SIGNALS")
        logger.info("=" * 80)

        for i, pos in enumerate(exit_signal_positions, 1):
            signal = pos['exit_signal']
            logger.info(f"\n{i}. {pos['symbol']}")
            logger.info(f"   Entry: ${pos['entry_price']:.2f} on {pos['entry_date']}")
            logger.info(f"   Exit Signal: {signal['rule']} ({signal['priority']})")
            logger.info(f"   Detected: {signal['detected_date']}")
            logger.info(f"   Price: ${signal['price_at_signal']:.2f}")
            logger.info(f"   PnL: {signal['pnl_pct_at_signal']:+.2f}% (${signal['pnl_dollar_at_signal']:+.2f})")
            logger.info(f"   Days Held: {signal['days_held']}")

        logger.info("")
        logger.info("=" * 80)
        logger.info("💡 Actions:")
        logger.info("   - Review each position")
        logger.info("   - Use manual_exit('SYMBOL') to close position")
        logger.info("   - Use clear_exit_signal('SYMBOL') to ignore signal and keep holding")
        logger.info("=" * 80)

        return exit_signal_positions

    def manual_exit(self, symbol: str, exit_price: float = None) -> Optional[Dict]:
        """
        Manually exit a position

        Args:
            symbol: Stock symbol to exit
            exit_price: Exit price (if None, fetches current price)

        Returns:
            Closed position dict or None if not found
        """
        # Find position
        position = None
        position_idx = None

        for i, pos in enumerate(self.portfolio['active']):
            if pos['symbol'].upper() == symbol.upper():
                position = pos
                position_idx = i
                break

        if not position:
            logger.error(f"❌ {symbol} not found in active positions")
            return None

        # Get exit price
        if exit_price is None:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='1d')
                exit_price = hist['Close'].iloc[-1]
                logger.info(f"Using current price: ${exit_price:.2f}")
            except Exception as e:
                logger.error(f"❌ Failed to get current price: {e}")
                return None

        # Calculate final PnL
        pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
        pnl_dollar = (exit_price - position['entry_price']) * position['shares']

        # Create closed position
        closed_position = {
            **position,
            'exit_date': datetime.now().strftime('%Y-%m-%d'),
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'pnl_dollar': pnl_dollar,
            'status': 'exited'
        }

        # Move to closed
        self.portfolio['closed'].append(closed_position)
        self.portfolio['active'].pop(position_idx)

        # Update stats
        self._update_stats(pnl_pct, pnl_dollar)

        self._save_portfolio()

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ CLOSED POSITION: {symbol}")
        logger.info("=" * 80)
        logger.info(f"Entry: ${position['entry_price']:.2f} on {position['entry_date']}")
        logger.info(f"Exit:  ${exit_price:.2f} on {closed_position['exit_date']}")
        logger.info(f"PnL:   {pnl_pct:+.2f}% (${pnl_dollar:+.2f})")
        logger.info(f"Days:  {position['days_held']}")

        if position.get('exit_signal'):
            logger.info(f"Exit Signal: {position['exit_signal']['rule']}")

        logger.info("=" * 80)

        return closed_position

    def clear_exit_signal(self, symbol: str) -> bool:
        """
        Clear exit signal and keep holding

        Use this when you decide to ignore the exit signal

        Args:
            symbol: Stock symbol

        Returns:
            True if cleared, False if not found
        """
        for position in self.portfolio['active']:
            if position['symbol'].upper() == symbol.upper():
                if position.get('exit_signal'):
                    logger.info(f"🔄 Clearing exit signal for {symbol}")
                    logger.info(f"   Previous signal: {position['exit_signal']['rule']}")

                    position['exit_signal'] = None
                    position['status'] = 'active'

                    self._save_portfolio()

                    logger.info(f"   ✅ Status changed to: active")
                    logger.info(f"   Continuing to hold {symbol}")

                    return True
                else:
                    logger.info(f"ℹ️  {symbol} has no exit signal to clear")
                    return True

        logger.error(f"❌ {symbol} not found in active positions")
        return False

    def _update_stats(self, pnl_pct: float, pnl_dollar: float):
        """Update portfolio statistics"""
        stats = self.portfolio['stats']

        stats['total_trades'] += 1
        stats['total_pnl'] += pnl_dollar

        # Update winners/losers
        if pnl_pct > 0:
            wins = stats.get('wins', 0) + 1
            stats['wins'] = wins

            total_winner_pnl = stats.get('total_winner_pnl', 0) + pnl_dollar
            stats['total_winner_pnl'] = total_winner_pnl
            stats['avg_winner'] = total_winner_pnl / wins
        else:
            losses = stats.get('losses', 0) + 1
            stats['losses'] = losses

            total_loser_pnl = stats.get('total_loser_pnl', 0) + pnl_dollar
            stats['total_loser_pnl'] = total_loser_pnl
            stats['avg_loser'] = total_loser_pnl / losses

        # Calculate win rate
        if stats['total_trades'] > 0:
            stats['win_rate'] = stats.get('wins', 0) / stats['total_trades']

    def show_portfolio(self):
        """Display portfolio summary"""
        logger.info("=" * 80)
        logger.info("📊 PORTFOLIO SUMMARY")
        logger.info("=" * 80)

        active = self.portfolio['active']
        closed = self.portfolio['closed']
        stats = self.portfolio['stats']

        logger.info(f"\n📈 Active Positions: {len(active)}")

        active_no_signal = [p for p in active if p.get('status') == 'active']
        exit_signals = [p for p in active if p.get('status') == 'exit_signal']

        logger.info(f"   Active (no signal): {len(active_no_signal)}")
        logger.info(f"   Exit signals: {len(exit_signals)}")

        if exit_signals:
            logger.warning("")
            logger.warning("⚠️  Exit signals pending:")
            for pos in exit_signals:
                logger.warning(f"   - {pos['symbol']}: {pos['exit_signal']['rule']}")

        logger.info(f"\n📉 Closed Positions: {len(closed)}")
        logger.info(f"\n📊 Statistics:")
        logger.info(f"   Total Trades: {stats['total_trades']}")
        logger.info(f"   Win Rate: {stats.get('win_rate', 0)*100:.1f}%")
        logger.info(f"   Total PnL: ${stats.get('total_pnl', 0):+.2f}")
        logger.info(f"   Avg Winner: ${stats.get('avg_winner', 0):+.2f}")
        logger.info(f"   Avg Loser: ${stats.get('avg_loser', 0):+.2f}")

        logger.info("")
        logger.info("=" * 80)


if __name__ == "__main__":
    # Example usage
    logger.info("Portfolio Manager with Manual Exit Confirmation")
    logger.info("=" * 80)

    manager = PortfolioManagerManualExit('portfolio.json')

    # Monitor positions
    summary = manager.monitor_positions(update_signals=True)

    # Show exit signals if any
    if summary['exit_signals_new'] > 0 or summary['exit_signals_existing'] > 0:
        manager.list_exit_signals()

    # Show portfolio
    manager.show_portfolio()
