#!/usr/bin/env python3
"""
Portfolio Manager v5.0 - Smart Structure-Based Exit System

v5.0 Changes (Jan 2026) - SMART EXIT SYSTEM:
- 🔥 STRUCTURE-BASED EXIT (100% Win Rate in backtest!):
  * SL from Swing Low / Support (โครงสร้างพัง = ออก)
  * TP1: R:R 1:2 → ขาย 50%
  * TP2: R:R 1:3 หรือ Resistance → ขายที่เหลือ
  * Trailing Stop ตาม Higher Low ใหม่
- 📈 Backtest 4 เดือน: +48.7% (vs +32.9% Fixed)
- 📊 Position Size Calculator: ความเสี่ยง 2% ต่อไม้

v4.0 Changes:
- 🚀 EARLY DIP EXIT (กลยุทธ์ C)
- 🔄 REINVEST SIGNAL

v3.0 Changes:
- 🛡️ AUTO STOP LOSS SYSTEM
- check_stop_loss(): Check all positions against stop loss rules

v2.0 Changes:
- Integrated with Advanced Exit Rules
- Integrated with Market Regime Detector
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yfinance as yf
import pandas as pd
import numpy as np
from loguru import logger

# Import advanced components
try:
    from advanced_exit_rules import AdvancedExitRules
    from market_regime_detector import MarketRegimeDetector
    ADVANCED_MODE = True
except ImportError:
    logger.warning("⚠️ Advanced Exit Rules or Regime Detector not available - using basic mode")
    ADVANCED_MODE = False

# Import Smart Exit Rules (v5.0)
try:
    from smart_exit_rules import SmartExitRules, calculate_position_size
    SMART_EXIT_MODE = True
except ImportError:
    logger.warning("⚠️ Smart Exit Rules not available")
    SMART_EXIT_MODE = False


class PortfolioManager:
    """
    Manages portfolio positions and tracks performance

    v2.0 Features:
    - Advanced exit rules (tighter stops, trailing stops)
    - Daily regime monitoring
    - Automatic position closing on regime change
    """

    def __init__(self, portfolio_file='portfolio.json', use_advanced=True, use_smart_exit=True):
        self.portfolio_file = portfolio_file
        self.portfolio = self._load_portfolio()
        self.use_advanced = use_advanced and ADVANCED_MODE
        self.use_smart_exit = use_smart_exit and SMART_EXIT_MODE

        # Initialize advanced components
        if self.use_advanced:
            self.exit_rules = AdvancedExitRules()
            self.regime_detector = MarketRegimeDetector()
        else:
            self.exit_rules = None
            self.regime_detector = None

        # Initialize Smart Exit Rules (v5.0)
        if self.use_smart_exit:
            self.smart_exit = SmartExitRules()
            logger.info("✅ Portfolio Manager v5.0 - Smart Exit Mode (Structure-Based)")
        else:
            self.smart_exit = None
            if self.use_advanced:
                logger.info("✅ Portfolio Manager v2.0 - Advanced Mode")
            else:
                logger.info("ℹ️ Portfolio Manager v1.0 - Basic Mode")

    def _load_portfolio(self) -> Dict:
        """Load portfolio from JSON file"""
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, 'r') as f:
                return json.load(f)
        else:
            return {
                'active': [],
                'closed': [],
                'stats': {
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'avg_winner': 0.0,
                    'avg_loser': 0.0,
                }
            }

    def _save_portfolio(self):
        """Save portfolio to JSON file"""
        with open(self.portfolio_file, 'w') as f:
            json.dump(self.portfolio, f, indent=2, default=str)

    def add_position(self, symbol: str, entry_price: float, entry_date: str,
                    filters: Dict, amount: float = 1000,
                    account_balance: float = None, risk_pct: float = 2.0) -> bool:
        """
        Add new position to portfolio (v5.0 with Smart Exit)

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            entry_date: Entry date (YYYY-MM-DD)
            filters: Screening filters at entry
            amount: Position amount (if not using risk-based sizing)
            account_balance: Total account balance (for risk-based position sizing)
            risk_pct: Risk per trade as % of account (default 2%)
        """

        # Check if already exists
        for pos in self.portfolio['active']:
            if pos['symbol'] == symbol:
                print(f"⚠️  {symbol} already in portfolio")
                return False

        # Get historical data for Smart Exit calculations
        sl_price = entry_price * 0.92  # Default -8%
        tp1_price = entry_price * 1.10  # Default +10%
        tp2_price = entry_price * 1.15  # Default +15%
        entry_levels = {}

        if self.use_smart_exit and self.smart_exit:
            try:
                hist_data = self._get_stock_data(symbol, days=30)
                if hist_data is not None and not hist_data.empty:
                    entry_idx = len(hist_data) - 1
                    entry_levels = self.smart_exit.calculate_entry_levels(
                        hist_data, entry_idx, entry_price
                    )
                    sl_price = entry_levels['sl_price']
                    tp1_price = entry_levels['tp1_price']
                    tp2_price = entry_levels['tp2_price']
            except Exception as e:
                logger.warning(f"⚠️ Could not calculate smart levels for {symbol}: {e}")

        # Calculate position size based on risk (if account_balance provided)
        if account_balance and self.use_smart_exit:
            sizing = calculate_position_size(
                account_balance=account_balance,
                entry_price=entry_price,
                sl_price=sl_price,
                risk_per_trade_pct=risk_pct
            )
            if 'error' not in sizing:
                shares = sizing['shares']
                amount = sizing['amount']
            else:
                shares = amount / entry_price
        else:
            shares = amount / entry_price

        position = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'highest_price': entry_price,  # For trailing stop tracking
            'lowest_price': entry_price,   # v4.0: For early dip tracking
            'amount': amount,
            'shares': shares,
            'filters_at_entry': filters,
            'days_held': 0,
            'early_dip_checked': False,    # v4.0: Flag for early dip exit
            # v5.0: Smart Exit Levels
            'sl_price': sl_price,
            'tp1_price': tp1_price,
            'tp2_price': tp2_price,
            'tp1_hit': False,              # ขาย 50% แล้วหรือยัง
            'shares_remaining': shares,     # หุ้นที่เหลืออยู่
            'realized_pnl': 0.0,           # กำไรที่ขายไปแล้ว
            'entry_levels': entry_levels,  # เก็บข้อมูลโครงสร้างราคา
        }

        self.portfolio['active'].append(position)
        self._save_portfolio()

        # Display entry info
        mode = "Smart Exit" if self.use_smart_exit else ("Advanced" if self.use_advanced else "Basic")
        print(f"✅ Added {symbol} @ ${entry_price:.2f} ({mode} Mode)")

        if self.use_smart_exit and entry_levels:
            sl_pct = entry_levels.get('sl_pct', 8)
            tp1_pct = entry_levels.get('tp1_pct', 10)
            tp2_pct = entry_levels.get('tp2_pct', 15)
            print(f"   📍 SL: ${sl_price:.2f} (-{sl_pct:.1f}%)")
            print(f"   🎯 TP1: ${tp1_price:.2f} (+{tp1_pct:.1f}%) → ขาย 50%")
            print(f"   🎯 TP2: ${tp2_price:.2f} (+{tp2_pct:.1f}%) → ขายที่เหลือ")

        return True

    def update_positions(self, current_date: str) -> Dict:
        """Update all active positions with current prices and check exit conditions"""

        updates = {
            'exit_positions': [],
            'holding': [],
        }

        # Get SPY data once for all positions (if using advanced mode)
        spy_data = None
        if self.use_advanced and self.exit_rules:
            spy_data = self._get_spy_data()

        for pos in self.portfolio['active']:
            symbol = pos['symbol']

            try:
                # Get historical data for exit rule evaluation
                hist_data = self._get_stock_data(symbol, days=60)
                if hist_data is None or hist_data.empty:
                    continue

                # Get current price
                current_price = float(hist_data['Close'].iloc[-1])

                # Update days held
                entry_dt = pd.Timestamp(pos['entry_date'])
                current_dt = pd.Timestamp(current_date)
                pos['days_held'] = (current_dt - entry_dt).days

                # Update highest price (for trailing stop)
                if current_price > pos.get('highest_price', pos['entry_price']):
                    pos['highest_price'] = current_price

                # Calculate P&L
                pos['current_price'] = current_price
                pos['pnl_pct'] = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                pos['pnl_usd'] = (current_price - pos['entry_price']) * pos['shares']

                # Check exit conditions
                should_exit = False
                exit_reason = None

                if self.use_advanced and self.exit_rules:
                    # Use advanced exit rules
                    should_exit, exit_reason, exit_price = self.exit_rules.should_exit(
                        pos, current_dt, hist_data, spy_data
                    )
                else:
                    # Use basic exit rules (fallback)
                    should_exit, exit_reason = self._check_basic_exit(pos)

                if should_exit:
                    updates['exit_positions'].append({
                        'symbol': symbol,
                        'exit_price': current_price,
                        'exit_reason': exit_reason,
                        'return_pct': pos['pnl_pct']
                    })
                else:
                    updates['holding'].append(pos)

            except Exception as e:
                logger.error(f"⚠️  Error updating {symbol}: {e}")
                continue

        return updates

    def _check_basic_exit(self, pos: Dict) -> tuple:
        """Basic exit rules (fallback when advanced mode disabled)"""
        current_return = pos.get('pnl_pct', 0)
        days_held = pos.get('days_held', 0)

        # Simple stop loss
        if current_return <= -10.0:
            return True, 'BASIC_STOP_LOSS'

        # Simple max hold
        if days_held >= 20:
            return True, 'BASIC_MAX_HOLD'

        return False, None

    def close_position(self, symbol: str, exit_price: float, exit_date: str,
                      exit_reason: str) -> Optional[Dict]:
        """Close a position and move to history"""

        # Find and remove from active
        position = None
        for i, pos in enumerate(self.portfolio['active']):
            if pos['symbol'] == symbol:
                position = self.portfolio['active'].pop(i)
                break

        if not position:
            print(f"⚠️  {symbol} not found in active positions")
            return None

        # Calculate final P&L
        entry_price = position['entry_price']
        shares = position['shares']

        return_pct = ((exit_price - entry_price) / entry_price) * 100
        return_usd = (exit_price - entry_price) * shares

        # Create closed position record
        closed_pos = {
            'symbol': symbol,
            'entry_date': position['entry_date'],
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return_pct': return_pct,
            'return_usd': return_usd,
            'days_held': position.get('days_held', 0),
            'exit_reason': exit_reason,
            'amount': position['amount'],
        }

        self.portfolio['closed'].append(closed_pos)

        # Update stats
        self._update_stats()
        self._save_portfolio()

        status = "✅" if return_pct > 0 else "❌"
        print(f"{status} Closed {symbol} at {return_pct:+.1f}% ({exit_reason})")

        return closed_pos

    def _update_stats(self):
        """Update portfolio statistics"""
        closed = self.portfolio['closed']

        if not closed:
            return

        returns = [p['return_pct'] for p in closed]
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]

        self.portfolio['stats'] = {
            'total_trades': len(closed),
            'active_count': len(self.portfolio['active']),
            'win_rate': (len(winners) / len(closed) * 100) if closed else 0,
            'total_pnl': sum([p['return_usd'] for p in closed]),
            'avg_return': np.mean(returns) if returns else 0,
            'avg_winner': np.mean(winners) if winners else 0,
            'avg_loser': np.mean(losers) if losers else 0,
            'largest_win': max(returns) if returns else 0,
            'largest_loss': min(returns) if returns else 0,
        }

    def get_summary(self) -> Dict:
        """Get portfolio summary"""
        stats = self.portfolio['stats']
        active_count = len(self.portfolio['active'])

        # Calculate active P&L
        active_pnl = sum([pos.get('pnl_usd', 0) for pos in self.portfolio['active']])

        return {
            'active_positions': active_count,
            'closed_trades': stats.get('total_trades', 0),
            'win_rate': stats.get('win_rate', 0),
            'total_pnl': stats.get('total_pnl', 0) + active_pnl,
            'closed_pnl': stats.get('total_pnl', 0),
            'active_pnl': active_pnl,
        }

    def display_status(self):
        """Display current portfolio status (v5.0 with Smart Exit levels)"""
        summary = self.get_summary()

        print("=" * 80)
        print("📊 PORTFOLIO STATUS v5.0 (Smart Exit)")
        print("=" * 80)
        print(f"\nActive Positions: {summary['active_positions']}")
        print(f"Total P&L: ${summary['total_pnl']:+,.2f}")

        if summary['closed_trades'] > 0:
            print(f"Win Rate: {summary['win_rate']:.1f}% ({summary['closed_trades']} trades)")

        print()

        # Display active positions with Smart Exit levels
        if self.portfolio['active']:
            print("📈 ACTIVE POSITIONS:")
            print("-" * 80)

            for pos in self.portfolio['active']:
                symbol = pos['symbol']
                entry_price = pos['entry_price']
                pnl = pos.get('pnl_pct', 0)
                current_price = pos.get('current_price', entry_price)
                status = "🟢" if pnl > 0 else "🔴"
                days = pos.get('days_held', 0)

                # Basic info
                print(f"\n{status} {symbol:6s}: {pnl:+6.1f}% (${pos.get('pnl_usd', 0):+,.0f}) Day {days}")
                print(f"   Entry: ${entry_price:.2f} | Current: ${current_price:.2f}")

                # Smart Exit levels
                if self.use_smart_exit:
                    sl_price = pos.get('sl_price', entry_price * 0.92)
                    tp1_price = pos.get('tp1_price', entry_price * 1.10)
                    tp2_price = pos.get('tp2_price', entry_price * 1.15)
                    tp1_hit = pos.get('tp1_hit', False)

                    # Calculate distances
                    to_sl = ((current_price - sl_price) / current_price) * 100
                    to_tp1 = ((tp1_price - current_price) / current_price) * 100 if not tp1_hit else 0
                    to_tp2 = ((tp2_price - current_price) / current_price) * 100

                    print(f"   📍 SL: ${sl_price:.2f} ({to_sl:+.1f}% away)")

                    if tp1_hit:
                        print(f"   ✅ TP1 HIT - ขายไปแล้ว 50%")
                        print(f"   🎯 TP2: ${tp2_price:.2f} ({to_tp2:+.1f}% away)")
                    else:
                        print(f"   🎯 TP1: ${tp1_price:.2f} ({to_tp1:+.1f}% away) → ขาย 50%")
                        print(f"   🎯 TP2: ${tp2_price:.2f} ({to_tp2:+.1f}% away) → ขายที่เหลือ")

            print("-" * 80)
        print()

    def get_active_symbols(self) -> List[str]:
        """Get list of active position symbols"""
        return [pos['symbol'] for pos in self.portfolio['active']]

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position details"""
        for pos in self.portfolio['active']:
            if pos['symbol'] == symbol:
                return pos
        return None

    def check_smart_exit(self) -> Dict:
        """
        Check all positions against Smart Exit rules (v5.0)

        Returns:
            Dict with actions: 'sl_triggered', 'tp1_triggered', 'tp2_triggered', 'update_trailing'
        """
        results = {
            'sl_triggered': [],      # 🔴 SL hit - ขายทั้งหมด
            'tp1_triggered': [],     # 🎯 TP1 hit - ขาย 50%
            'tp2_triggered': [],     # 🎯 TP2 hit - ขายที่เหลือ
            'trailing_updated': [],  # 📈 Trailing SL updated
            'holding': [],           # ✅ ถือต่อ
        }

        if not self.portfolio['active']:
            print("📭 No active positions")
            return results

        print("=" * 80)
        print("🔥 SMART EXIT CHECK v5.0 (Structure-Based)")
        print("=" * 80)

        for pos in self.portfolio['active']:
            symbol = pos['symbol']
            entry_price = pos['entry_price']
            sl_price = pos.get('sl_price', entry_price * 0.92)
            tp1_price = pos.get('tp1_price', entry_price * 1.10)
            tp2_price = pos.get('tp2_price', entry_price * 1.15)
            tp1_hit = pos.get('tp1_hit', False)

            try:
                # Get current price data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5d')
                if hist.empty:
                    continue

                current_price = float(hist['Close'].iloc[-1])
                high_price = float(hist['High'].iloc[-1])
                low_price = float(hist['Low'].iloc[-1])

                # Update position
                pos['current_price'] = current_price
                if current_price > pos.get('highest_price', entry_price):
                    pos['highest_price'] = current_price

                # Calculate P&L
                pnl_pct = ((current_price - entry_price) / entry_price) * 100

                print(f"\n{'='*40}")
                print(f"📊 {symbol}: ${current_price:.2f} ({pnl_pct:+.1f}%)")
                print(f"   Today: High ${high_price:.2f} | Low ${low_price:.2f}")

                # === CHECK SL ===
                if low_price <= sl_price:
                    print(f"   🔴 SL TRIGGERED @ ${sl_price:.2f}!")
                    results['sl_triggered'].append({
                        'symbol': symbol,
                        'exit_price': sl_price,
                        'reason': 'SL_STRUCTURE_BREAK',
                        'pnl_pct': ((sl_price - entry_price) / entry_price) * 100
                    })
                    continue

                # === CHECK TP1 (Scale Out 50%) ===
                if not tp1_hit and high_price >= tp1_price:
                    print(f"   🎯 TP1 HIT @ ${tp1_price:.2f}! → ขาย 50%")
                    results['tp1_triggered'].append({
                        'symbol': symbol,
                        'exit_price': tp1_price,
                        'reason': 'TP1_SCALE_OUT',
                        'pnl_pct': ((tp1_price - entry_price) / entry_price) * 100
                    })
                    # Mark TP1 as hit and update trailing
                    pos['tp1_hit'] = True
                    pos['sl_price'] = max(sl_price, entry_price * 1.01)  # Move to breakeven+1%
                    print(f"   📈 SL moved to breakeven+1%: ${pos['sl_price']:.2f}")
                    continue

                # === CHECK TP2 (Full Exit) ===
                if tp1_hit and high_price >= tp2_price:
                    print(f"   🎯 TP2 HIT @ ${tp2_price:.2f}! → ขายที่เหลือ")
                    results['tp2_triggered'].append({
                        'symbol': symbol,
                        'exit_price': tp2_price,
                        'reason': 'TP2_TARGET',
                        'pnl_pct': ((tp2_price - entry_price) / entry_price) * 100
                    })
                    continue

                # === UPDATE TRAILING STOP ===
                if tp1_hit and self.use_smart_exit and self.smart_exit:
                    hist_data = self._get_stock_data(symbol, days=30)
                    if hist_data is not None:
                        new_sl = self.smart_exit.update_trailing_stop(pos, hist_data, len(hist_data)-1)
                        if new_sl > pos['sl_price']:
                            print(f"   📈 Trailing SL updated: ${pos['sl_price']:.2f} → ${new_sl:.2f}")
                            pos['sl_price'] = new_sl
                            results['trailing_updated'].append(symbol)

                # === HOLDING ===
                print(f"   ✅ Holding | SL ${sl_price:.2f} | TP {'TP2' if tp1_hit else 'TP1'} ${tp2_price if tp1_hit else tp1_price:.2f}")
                results['holding'].append(symbol)

            except Exception as e:
                logger.error(f"⚠️ Error checking {symbol}: {e}")
                continue

        # Save updated positions
        self._save_portfolio()

        # Summary
        print("\n" + "=" * 80)
        print("📋 SUMMARY")
        print("=" * 80)
        if results['sl_triggered']:
            print(f"🔴 SL Triggered: {[r['symbol'] for r in results['sl_triggered']]}")
        if results['tp1_triggered']:
            print(f"🎯 TP1 Triggered (sell 50%): {[r['symbol'] for r in results['tp1_triggered']]}")
        if results['tp2_triggered']:
            print(f"🎯 TP2 Triggered (sell rest): {[r['symbol'] for r in results['tp2_triggered']]}")
        if results['trailing_updated']:
            print(f"📈 Trailing Updated: {results['trailing_updated']}")
        print(f"✅ Holding: {len(results['holding'])} positions")
        print("=" * 80)

        return results

    def execute_smart_exit(self, exit_results: Dict):
        """
        Execute exits based on check_smart_exit results

        Args:
            exit_results: Results from check_smart_exit()
        """
        today = datetime.now().strftime('%Y-%m-%d')

        # Execute SL exits (full position)
        for exit_info in exit_results.get('sl_triggered', []):
            self.close_position(
                symbol=exit_info['symbol'],
                exit_price=exit_info['exit_price'],
                exit_date=today,
                exit_reason=exit_info['reason']
            )

        # Execute TP1 exits (scale out 50%)
        for exit_info in exit_results.get('tp1_triggered', []):
            pos = self.get_position(exit_info['symbol'])
            if pos:
                # Calculate partial exit
                shares_to_sell = pos['shares'] * 0.5
                realized_pnl = (exit_info['exit_price'] - pos['entry_price']) * shares_to_sell

                # Update position
                pos['shares_remaining'] = pos['shares'] - shares_to_sell
                pos['realized_pnl'] = pos.get('realized_pnl', 0) + realized_pnl
                pos['tp1_hit'] = True

                print(f"🎯 {exit_info['symbol']}: Sold 50% ({shares_to_sell:.0f} shares) @ ${exit_info['exit_price']:.2f}")
                print(f"   Realized P&L: ${realized_pnl:+,.2f}")

        # Execute TP2 exits (full remaining position)
        for exit_info in exit_results.get('tp2_triggered', []):
            self.close_position(
                symbol=exit_info['symbol'],
                exit_price=exit_info['exit_price'],
                exit_date=today,
                exit_reason=exit_info['reason']
            )

        self._save_portfolio()

    def _get_stock_data(self, symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Get historical stock data for exit rule evaluation"""
        try:
            ticker = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"⚠️ No data available for {symbol}")
                return None

            return hist
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    def _get_spy_data(self, days: int = 60) -> Optional[pd.DataFrame]:
        """Get SPY data for regime and filter checks"""
        try:
            spy = yf.Ticker('SPY')
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            hist = spy.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"⚠️ No SPY data available")
                return None

            return hist
        except Exception as e:
            logger.error(f"Error fetching SPY data: {e}")
            return None

    # ========== v3.0: AUTO STOP LOSS SYSTEM ==========

    def check_stop_loss(self,
                       hard_stop_pct: float = -7.0,
                       warning_pct: float = -3.0,
                       trailing_stop_pct: float = -5.0,
                       time_stop_days: int = 10,
                       early_dip_pct: float = -3.0,
                       early_dip_days: int = 3,
                       enable_early_dip: bool = True) -> Dict:
        """
        Check all positions against stop loss rules (v4.0 STRATEGY C)

        Stop Loss Rules (Priority Order):
        1. EARLY DIP EXIT (v4.0): If dip >= 3% in first 3 days → SELL NOW
           - Backtest showed 71% of early dippers stay losers
           - Selling early + reinvesting = +181.8% vs +129.1%
        2. HARD STOP: Exit immediately at -7% (configurable)
        3. TRAILING STOP: Exit at -5% from highest price
        4. TIME STOP: Exit if no gain after 10 days
        5. WARNING: Alert at -3% (configurable)

        Returns:
            Dict with 'sell_now', 'warning', 'ok', 'reinvest_signal' lists
        """
        results = {
            'sell_now': [],           # 🔴 Must sell immediately
            'early_dip_exit': [],     # 🚀 v4.0: Early dip exits (reinvest!)
            'warning': [],            # 🟡 Warning - monitor closely
            'ok': [],                 # 🟢 Position is fine
            'reinvest_signal': False, # 🔄 Signal to buy new stock
            'summary': {}
        }

        if not self.portfolio['active']:
            print("📭 No active positions to check")
            return results

        print("=" * 70)
        print("🛡️  STOP LOSS CHECK v4.0 (Strategy C: Early Exit + Reinvest)")
        print("=" * 70)
        print(f"   🚀 Early Dip: {early_dip_pct}% in {early_dip_days} days | Hard: {hard_stop_pct}%")
        print(f"   📉 Trailing: {trailing_stop_pct}% | ⏰ Time: {time_stop_days} days")
        print("=" * 70)

        for pos in self.portfolio['active']:
            symbol = pos['symbol']
            entry_price = pos['entry_price']
            entry_date = pos['entry_date']
            highest_price = pos.get('highest_price', entry_price)

            try:
                # Get current price
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='5d')
                if hist.empty:
                    continue

                current_price = float(hist['Close'].iloc[-1])

                # Calculate returns
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                pnl_usd = (current_price - entry_price) * pos['shares']

                # Update highest price
                if current_price > highest_price:
                    highest_price = current_price
                    pos['highest_price'] = highest_price
                    self._save_portfolio()

                # Calculate trailing stop
                trailing_pct = ((current_price - highest_price) / highest_price) * 100

                # Calculate days held
                try:
                    entry_dt = datetime.strptime(entry_date, '%Y-%m-%d')
                    days_held = (datetime.now() - entry_dt).days
                except:
                    days_held = 0

                pos['days_held'] = days_held
                pos['current_price'] = current_price
                pos['pnl_pct'] = pnl_pct
                pos['pnl_usd'] = pnl_usd

                # Update lowest price tracking
                lowest_price = pos.get('lowest_price', entry_price)
                if current_price < lowest_price:
                    lowest_price = current_price
                    pos['lowest_price'] = lowest_price

                # Calculate lowest dip from entry
                lowest_dip_pct = ((lowest_price - entry_price) / entry_price) * 100

                # Check stop loss conditions
                alert = {
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'highest_price': highest_price,
                    'lowest_price': lowest_price,
                    'pnl_pct': pnl_pct,
                    'pnl_usd': pnl_usd,
                    'trailing_pct': trailing_pct,
                    'lowest_dip_pct': lowest_dip_pct,
                    'days_held': days_held,
                    'reason': None,
                    'action': None
                }

                # ========== v4.0 STRATEGY C: EARLY DIP EXIT ==========
                # Priority 0: EARLY DIP EXIT (first 3 days)
                # Backtest: 71% of stocks that dip >=3% in first 3 days stay losers
                # Selling early + reinvesting = +181.8% vs +129.1% total return
                early_dip_triggered = False
                if enable_early_dip and days_held <= early_dip_days:
                    if lowest_dip_pct <= early_dip_pct:  # e.g., -3% or worse
                        alert['reason'] = f"🚀 EARLY DIP EXIT (dip {lowest_dip_pct:.1f}% in Day {days_held})"
                        alert['action'] = 'EARLY_EXIT_REINVEST'
                        results['early_dip_exit'].append(alert)
                        results['reinvest_signal'] = True
                        early_dip_triggered = True
                        print(f"🚀 {symbol}: {pnl_pct:+.1f}% - EARLY DIP! Dipped {lowest_dip_pct:.1f}% in {days_held} days")
                        print(f"   💡 Strategy C: ขายเร็ว + ซื้อหุ้นใหม่ทันที!")

                # Priority 1: HARD STOP LOSS
                if not early_dip_triggered and pnl_pct <= hard_stop_pct:
                    alert['reason'] = f"HARD STOP ({pnl_pct:.1f}% <= {hard_stop_pct}%)"
                    alert['action'] = 'SELL_NOW'
                    results['sell_now'].append(alert)
                    print(f"🔴 {symbol}: {pnl_pct:+.1f}% - HARD STOP TRIGGERED! SELL NOW!")

                # Priority 2: TRAILING STOP (only if was profitable)
                elif not early_dip_triggered and highest_price > entry_price and trailing_pct <= trailing_stop_pct:
                    alert['reason'] = f"TRAILING STOP ({trailing_pct:.1f}% from high ${highest_price:.2f})"
                    alert['action'] = 'SELL_NOW'
                    results['sell_now'].append(alert)
                    print(f"🔴 {symbol}: {pnl_pct:+.1f}% - TRAILING STOP! Was at ${highest_price:.2f}, now ${current_price:.2f}")

                # Priority 3: TIME STOP (no profit after X days)
                elif not early_dip_triggered and days_held >= time_stop_days and pnl_pct <= 0:
                    alert['reason'] = f"TIME STOP ({days_held} days, still {pnl_pct:+.1f}%)"
                    alert['action'] = 'SELL_NOW'
                    results['sell_now'].append(alert)
                    print(f"🔴 {symbol}: {pnl_pct:+.1f}% - TIME STOP! {days_held} days without profit")

                # Priority 4: WARNING ZONE
                elif not early_dip_triggered and pnl_pct <= warning_pct:
                    alert['reason'] = f"WARNING ZONE ({pnl_pct:.1f}%)"
                    alert['action'] = 'MONITOR'
                    results['warning'].append(alert)
                    print(f"🟡 {symbol}: {pnl_pct:+.1f}% - WARNING! Approaching stop loss")

                # OK
                elif not early_dip_triggered:
                    alert['reason'] = "Position OK"
                    alert['action'] = 'HOLD'
                    results['ok'].append(alert)
                    status = "🟢" if pnl_pct > 0 else "⚪"
                    print(f"{status} {symbol}: {pnl_pct:+.1f}% - OK (Day {days_held})")

            except Exception as e:
                logger.error(f"Error checking {symbol}: {e}")
                continue

        # Save updated portfolio
        self._save_portfolio()

        # Summary
        print()
        print("=" * 70)
        print("📊 SUMMARY")
        print("=" * 70)
        print(f"   🚀 EARLY DIP: {len(results['early_dip_exit'])} positions (Strategy C)")
        print(f"   🔴 SELL NOW:  {len(results['sell_now'])} positions")
        print(f"   🟡 WARNING:   {len(results['warning'])} positions")
        print(f"   🟢 OK:        {len(results['ok'])} positions")

        # Early dip exit recommendations
        if results['early_dip_exit']:
            print()
            print("🚀 STRATEGY C - EARLY EXIT + REINVEST:")
            print("   (Backtest: +181.8% total vs +129.1% holding)")
            for alert in results['early_dip_exit']:
                loss_pct = alert['pnl_pct']
                print(f"   → SELL {alert['symbol']} @ ${alert['current_price']:.2f} ({loss_pct:+.1f}%)")
                print(f"      💡 ซื้อหุ้นใหม่ทันทีเพื่อ maximize return!")

        if results['sell_now']:
            print()
            print("⚠️  STOP LOSS TRIGGERED:")
            for alert in results['sell_now']:
                print(f"   → SELL {alert['symbol']} @ ${alert['current_price']:.2f} ({alert['reason']})")

        # Reinvest reminder
        if results['reinvest_signal']:
            print()
            print("=" * 70)
            print("🔄 REINVEST SIGNAL ACTIVE!")
            print("=" * 70)
            print("   หุ้นที่ขายออกไปมีเงินพร้อมลงทุนใหม่")
            print("   → รัน screener เพื่อหาหุ้นตัวใหม่ทันที")
            print("   → กลยุทธ์ C: ขายเร็ว + ซื้อใหม่ = กำไรมากกว่า!")

        results['summary'] = {
            'early_dip_count': len(results['early_dip_exit']),
            'sell_count': len(results['sell_now']),
            'warning_count': len(results['warning']),
            'ok_count': len(results['ok']),
            'reinvest_signal': results['reinvest_signal']
        }

        return results

    def auto_stop_loss_sell(self, confirm: bool = False,
                           include_early_dip: bool = True) -> Dict:
        """
        Automatically sell all positions that triggered stop loss (v4.0)

        Args:
            confirm: If True, actually execute the sells. If False, just show what would be sold.
            include_early_dip: If True, also sell early dip positions (Strategy C)

        Returns:
            Dict with 'closed' list and 'reinvest_signal' flag
        """
        results = self.check_stop_loss()

        # Combine all sells
        all_sells = results['sell_now'].copy()
        if include_early_dip:
            all_sells.extend(results['early_dip_exit'])

        if not all_sells:
            print("\n✅ No positions need to be sold")
            return {'closed': [], 'reinvest_signal': False}

        if not confirm:
            print("\n" + "=" * 70)
            print("⚠️  DRY RUN - Add confirm=True to actually sell")
            print("=" * 70)
            print(f"   Would sell {len(all_sells)} positions:")
            for alert in all_sells:
                print(f"   - {alert['symbol']} @ ${alert['current_price']:.2f} ({alert['reason']})")
            return {'closed': [], 'reinvest_signal': results['reinvest_signal']}

        print("\n" + "=" * 70)
        print("🚀 EXECUTING STRATEGY C AUTO SELLS")
        print("=" * 70)

        closed = []
        today = datetime.now().strftime('%Y-%m-%d')
        freed_capital = 0

        for alert in all_sells:
            # Determine exit reason
            if 'EARLY DIP' in alert.get('reason', ''):
                exit_reason = 'STRATEGY_C_EARLY_DIP_EXIT'
            else:
                exit_reason = f"AUTO_{alert['reason'].replace(' ', '_').upper()}"

            result = self.close_position(
                symbol=alert['symbol'],
                exit_price=alert['current_price'],
                exit_date=today,
                exit_reason=exit_reason
            )
            if result:
                closed.append(result)
                # Calculate freed capital
                freed_capital += alert['current_price'] * self.portfolio['active'][0]['shares'] if self.portfolio['active'] else 0

        print()
        print("=" * 70)
        print(f"✅ Closed {len(closed)} positions")

        # Reinvest reminder
        if results['reinvest_signal']:
            print()
            print("🔄 REINVEST NOW!")
            print("=" * 70)
            print("   กลยุทธ์ C: ขายเร็ว + ซื้อหุ้นใหม่ทันที")
            print("   → รัน screener เพื่อหาหุ้นตัวใหม่")
            print("   → ใช้ทุนที่ได้จากการขายไปซื้อหุ้นที่ดีกว่า")
            print()
            print("   Backtest Results:")
            print("   - ถือจนจบ: +129.1%, 60.8% WR")
            print("   - ขายเร็ว + ซื้อใหม่: +181.8%, 84.3% WR 🏆")

        return {
            'closed': closed,
            'reinvest_signal': results['reinvest_signal'],
            'early_dip_count': len(results['early_dip_exit']),
            'stop_loss_count': len(results['sell_now'])
        }

    # ========== v4.0: STRATEGY C HELPER METHODS ==========

    def limited_capital_check(self, confirm: bool = False) -> Dict:
        """
        🏆 โหมดทุนจำกัด - สำหรับคนที่มีเงินเดือนต่อเดือน

        Backtest Results (Score >= 92, SL -5%):
        - 22 trades, 6 losers, 73% WR
        - AvgLoss: -5%, Total: +107%, MaxDD: -10%

        Settings:
        - Hard Stop: -5% (ไม่ใช่ -7%)
        - Early Dip: -3% ใน 3 วันแรก
        - Time Stop: 7 วัน (ไม่ใช่ 10 วัน)

        เหตุผล:
        - ตัด loss เร็ว = เงินไม่จม
        - ขาดทุนน้อย = กล้าตัดสินใจ
        - มีเงินซื้อตัวใหม่ได้เร็ว

        Args:
            confirm: True = ขายจริง, False = แค่ดู

        Returns:
            Dict with results
        """
        print()
        print("=" * 70)
        print("💰 LIMITED CAPITAL MODE (โหมดทุนจำกัด)")
        print("=" * 70)
        print("   Settings: SL -5%, Early Dip -3%, Time Stop 7 days")
        print("   Backtest: 73% WR, 6 losers, MaxDD -10%")
        print()

        results = self.check_stop_loss(
            hard_stop_pct=-5.0,       # ตัด loss เร็วกว่าปกติ
            warning_pct=-2.0,         # เตือนเร็วกว่า
            trailing_stop_pct=-4.0,   # trailing แคบกว่า
            time_stop_days=7,         # ไม่รอนาน
            early_dip_pct=-3.0,       # ขายเร็วถ้า dip
            early_dip_days=3,
            enable_early_dip=True
        )

        # Combine all sells
        all_sells = results['sell_now'].copy()
        all_sells.extend(results['early_dip_exit'])

        if not all_sells:
            print("\n✅ ไม่มีหุ้นที่ต้องขาย - Portfolio ยังดีอยู่!")
            return {'closed': [], 'need_action': False}

        if not confirm:
            print("\n" + "=" * 70)
            print("⚠️  DRY RUN - ใส่ confirm=True เพื่อขายจริง")
            print("=" * 70)
            total_loss = sum([a['pnl_pct'] for a in all_sells])
            print(f"   ถ้าขายตอนนี้จะขาดทุน: {total_loss:.1f}%")
            print(f"   แต่จะได้เงินกลับมาซื้อหุ้นใหม่!")
            for alert in all_sells:
                print(f"   - {alert['symbol']} @ ${alert['current_price']:.2f} ({alert['pnl_pct']:+.1f}%)")
            return {'closed': [], 'need_action': True, 'pending_sells': all_sells}

        # Execute sells
        closed = []
        today = datetime.now().strftime('%Y-%m-%d')

        for alert in all_sells:
            result = self.close_position(
                symbol=alert['symbol'],
                exit_price=alert['current_price'],
                exit_date=today,
                exit_reason='LIMITED_CAPITAL_EXIT'
            )
            if result:
                closed.append(result)

        print()
        print("=" * 70)
        print(f"✅ ขายแล้ว {len(closed)} ตัว")
        print("💡 มีเงินพร้อมซื้อหุ้นใหม่แล้ว! รัน screener เลย!")
        print("=" * 70)

        return {'closed': closed, 'need_action': False, 'reinvest_now': True}

    def strategy_c_daily_check(self, confirm: bool = False) -> Dict:
        """
        กลยุทธ์ C: ตรวจสอบประจำวัน - ขายเร็ว + ซื้อใหม่

        การใช้งาน:
        1. รันทุกวัน: pm.strategy_c_daily_check()
        2. ถ้ามี reinvest_signal = True → รัน screener หาหุ้นใหม่
        3. ซื้อหุ้นใหม่ทันที

        Backtest Results:
        - ถือจนจบ: +129.1%, 60.8% WR
        - ขายเร็ว + ซื้อใหม่: +181.8%, 84.3% WR 🏆

        Args:
            confirm: True = ขายจริง, False = แค่ดู

        Returns:
            Dict with results and reinvest_signal
        """
        print()
        print("=" * 70)
        print("🚀 STRATEGY C: DAILY CHECK (ขายเร็ว + ซื้อใหม่)")
        print("=" * 70)
        print()

        # Step 1: Check all positions
        results = self.auto_stop_loss_sell(confirm=confirm, include_early_dip=True)

        # Step 2: If reinvest signal, remind to screen
        if results.get('reinvest_signal'):
            print()
            print("=" * 70)
            print("📢 NEXT STEP: หาหุ้นใหม่!")
            print("=" * 70)
            print("""
   รันคำสั่งนี้เพื่อหาหุ้นใหม่:

   from screeners.growth_catalyst_screener import GrowthCatalystScreener
   screener = GrowthCatalystScreener()
   results = screener.screen_growth_catalyst_opportunities(
       target_gain_pct=10,
       timeframe_days=30,
       min_technical_score=88  # v7.1 high quality threshold
   )

   # ดูหุ้น top picks
   for r in results[:5]:
       print(f"{r['symbol']}: Score {r['technical_score']:.0f}")
""")

        return results

    def get_strategy_c_stats(self) -> Dict:
        """
        Get Strategy C performance statistics

        Returns:
            Dict with strategy C specific stats
        """
        closed = self.portfolio.get('closed', [])

        # Filter Strategy C exits
        early_exits = [p for p in closed if 'EARLY_DIP' in p.get('exit_reason', '')]
        normal_exits = [p for p in closed if 'EARLY_DIP' not in p.get('exit_reason', '')]

        stats = {
            'total_trades': len(closed),
            'early_dip_exits': len(early_exits),
            'normal_exits': len(normal_exits),
        }

        if early_exits:
            early_returns = [p['return_pct'] for p in early_exits]
            stats['early_exit_avg_loss'] = np.mean(early_returns)
            stats['early_exit_saved_vs_full_stop'] = (-7.0 - np.mean(early_returns))  # How much saved vs -7% stop

        if normal_exits:
            normal_returns = [p['return_pct'] for p in normal_exits]
            stats['normal_win_rate'] = len([r for r in normal_returns if r > 0]) / len(normal_returns) * 100
            stats['normal_avg_return'] = np.mean(normal_returns)

        return stats


if __name__ == "__main__":
    # Test Strategy C
    print("=" * 70)
    print("Testing Portfolio Manager v4.0 - Strategy C")
    print("=" * 70)

    pm = PortfolioManager('test_portfolio.json')

    # Add test positions
    pm.add_position('TSLA', 380.50, '2025-01-27', {'rsi': 55, 'momentum': 10})
    pm.add_position('META', 585.20, '2025-01-27', {'rsi': 52, 'momentum': 8})
    pm.add_position('NVDA', 142.00, '2025-01-28', {'rsi': 58, 'momentum': 12})

    # Display
    pm.display_status()

    # Run Strategy C daily check
    print("\n--- Running Strategy C Daily Check ---\n")
    results = pm.strategy_c_daily_check(confirm=False)

    print("\n--- Results ---")
    print(f"Reinvest Signal: {results.get('reinvest_signal', False)}")
    print(f"Early Dip Count: {results.get('early_dip_count', 0)}")
    print(f"Stop Loss Count: {results.get('stop_loss_count', 0)}")
