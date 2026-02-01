#!/usr/bin/env python3
"""
Exit Rules Engine - Smart filter-based exits with safety nets
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class ExitRulesEngine:
    """
    Implements smart exit strategy:
    - Primary: Filter-based (check if stock still passes filters)
    - Safety: Hard stop loss (-10%)
    - Protection: Min holding (3 days), Max holding (20 days)
    """

    def __init__(self):
        self.filters = {
            'rsi_min': 49.0,
            'momentum_7d_min': 3.5,
            'rs_14d_min': 1.9,
            'dist_ma20_min': -2.8,
        }

        self.exit_config = {
            'min_holding_days': 3,
            'max_holding_days': 20,
            'hard_stop_loss': -10.0,
            'intraday_alert': -7.0,
            'score_threshold': 1,  # Exit if score <= 1 (fail ≥3 filters)
        }

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_filter_score(self, symbol: str, check_date: pd.Timestamp,
                               hist_data: pd.DataFrame, spy_data: pd.DataFrame) -> Tuple[int, Dict]:
        """
        Calculate filter score (0-4)
        Returns: (score, details)
        """
        try:
            # Get data up to check date
            data = hist_data[hist_data.index <= check_date].copy()

            if len(data) < 50:
                return 0, {'error': 'Insufficient data'}

            close = data['Close']
            current_price = close.iloc[-1]

            score = 0
            details = {}

            # Filter 1: RSI > 49
            rsi = self.calculate_rsi(close)
            rsi_value = rsi.iloc[-1]
            details['rsi'] = rsi_value
            if rsi_value >= self.filters['rsi_min']:
                score += 1
                details['rsi_pass'] = True
            else:
                details['rsi_pass'] = False

            # Filter 2: Momentum 7d > 3.5%
            if len(close) >= 7:
                price_7d_ago = close.iloc[-7]
                momentum_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
                details['momentum_7d'] = momentum_7d
                if momentum_7d >= self.filters['momentum_7d_min']:
                    score += 1
                    details['momentum_7d_pass'] = True
                else:
                    details['momentum_7d_pass'] = False

            # Filter 3: 14-day RS > 1.9%
            if len(close) >= 14:
                price_14d_ago = close.iloc[-14]
                stock_return = ((current_price / price_14d_ago) - 1) * 100

                # Get SPY return
                spy_at_date = spy_data[spy_data.index <= check_date]
                if len(spy_at_date) >= 14:
                    spy_price_now = spy_at_date['Close'].iloc[-1]
                    spy_price_14d_ago = spy_at_date['Close'].iloc[-14]
                    spy_return = ((spy_price_now / spy_price_14d_ago) - 1) * 100
                    rs_14d = stock_return - spy_return
                    details['rs_14d'] = rs_14d

                    if rs_14d >= self.filters['rs_14d_min']:
                        score += 1
                        details['rs_14d_pass'] = True
                    else:
                        details['rs_14d_pass'] = False

            # Filter 4: Distance from MA20 > -2.8%
            if len(close) >= 20:
                ma20 = close.rolling(window=20).mean().iloc[-1]
                dist_ma20 = ((current_price - ma20) / ma20) * 100
                details['dist_ma20'] = dist_ma20

                if dist_ma20 >= self.filters['dist_ma20_min']:
                    score += 1
                    details['dist_ma20_pass'] = True
                else:
                    details['dist_ma20_pass'] = False

                # Additional: MA20 slope (trend)
                if len(close) >= 25:
                    ma20_5d_ago = close.rolling(window=20).mean().iloc[-5]
                    ma20_slope = ((ma20 - ma20_5d_ago) / ma20_5d_ago) * 100
                    details['ma20_slope'] = ma20_slope
                    details['trend_up'] = ma20_slope > 0

            # Recent momentum (3-day) for lag protection
            if len(close) >= 3:
                price_3d_ago = close.iloc[-3]
                momentum_3d = ((current_price - price_3d_ago) / price_3d_ago) * 100
                details['momentum_3d'] = momentum_3d

            return score, details

        except Exception as e:
            return 0, {'error': str(e)}

    def check_exit(self, position: Dict, current_date: str,
                   hist_data: pd.DataFrame, spy_data: pd.DataFrame) -> Tuple[bool, str, Dict]:
        """
        Check if position should be exited
        Returns: (should_exit, reason, details)
        """

        symbol = position['symbol']
        entry_price = position['entry_price']
        days_held = position.get('days_held', 0)
        current_date_ts = pd.Timestamp(current_date)

        # Get current price
        try:
            current_data = hist_data[hist_data.index <= current_date_ts]
            if current_data.empty:
                return False, 'NO_DATA', {}

            current_price = current_data['Close'].iloc[-1]
            current_return = ((current_price - entry_price) / entry_price) * 100

        except Exception as e:
            return False, f'ERROR: {e}', {}

        # Rule 1: Emergency Stop Loss (-10%)
        if current_return <= self.exit_config['hard_stop_loss']:
            return True, 'STOP_LOSS', {'return': current_return, 'price': current_price}

        # Rule 2: Max Holding Period (20 days)
        if days_held >= self.exit_config['max_holding_days']:
            return True, 'MAX_HOLD', {'days': days_held, 'return': current_return}

        # Rule 3: Min Holding Protection (3 days)
        if days_held < self.exit_config['min_holding_days']:
            # Don't exit yet, still in protection period
            return False, 'MIN_HOLD_PROTECTION', {'days': days_held}

        # Rule 4: Filter-based Exit (Primary Logic)
        score, filter_details = self.calculate_filter_score(
            symbol, current_date_ts, hist_data, spy_data
        )

        filter_details['score'] = score
        filter_details['return'] = current_return
        filter_details['days_held'] = days_held

        # Score <= 1 means fail ≥3 filters
        if score <= self.exit_config['score_threshold']:
            # Additional check: Is trend still up?
            trend_up = filter_details.get('trend_up', False)
            momentum_3d = filter_details.get('momentum_3d', -999)

            # If trend still strong, hold a bit longer
            if trend_up and momentum_3d > -5:
                return False, 'WEAK_BUT_HOLDING', filter_details

            # Trend is down or recent weakness
            return True, 'FILTER_EXIT', filter_details

        # All checks passed, continue holding
        return False, 'HOLDING', filter_details

    def get_exit_summary(self, details: Dict) -> str:
        """Generate human-readable exit summary"""
        score = details.get('score', 0)
        lines = [f"Score: {score}/4"]

        if 'rsi' in details:
            status = "✅" if details.get('rsi_pass') else "❌"
            lines.append(f"{status} RSI: {details['rsi']:.1f}")

        if 'momentum_7d' in details:
            status = "✅" if details.get('momentum_7d_pass') else "❌"
            lines.append(f"{status} Momentum 7d: {details['momentum_7d']:+.1f}%")

        if 'rs_14d' in details:
            status = "✅" if details.get('rs_14d_pass') else "❌"
            lines.append(f"{status} RS 14d: {details['rs_14d']:+.1f}%")

        if 'dist_ma20' in details:
            status = "✅" if details.get('dist_ma20_pass') else "❌"
            lines.append(f"{status} MA20: {details['dist_ma20']:+.1f}%")

        if 'ma20_slope' in details:
            trend = "📈" if details.get('trend_up') else "📉"
            lines.append(f"{trend} Trend: {details['ma20_slope']:+.1f}%")

        return "\n   ".join(lines)


# Comparison: Fixed TP/SL Rules
class FixedTPSLRules:
    """Traditional fixed take profit / stop loss"""

    def __init__(self, take_profit: float = 5.0, stop_loss: float = -8.0,
                 max_hold: int = 14):
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_hold = max_hold

    def check_exit(self, position: Dict, current_date: str,
                   hist_data: pd.DataFrame) -> Tuple[bool, str, Dict]:
        """Check exit with fixed TP/SL"""

        entry_price = position['entry_price']
        days_held = position.get('days_held', 0)

        # Get max price in holding period
        try:
            entry_date = pd.Timestamp(position['entry_date'])
            current_date_ts = pd.Timestamp(current_date)

            holding_data = hist_data[
                (hist_data.index > entry_date) &
                (hist_data.index <= current_date_ts)
            ]

            if holding_data.empty:
                return False, 'NO_DATA', {}

            max_high = holding_data['High'].max()
            current_price = holding_data['Close'].iloc[-1]

            max_return = ((max_high - entry_price) / entry_price) * 100
            current_return = ((current_price - entry_price) / entry_price) * 100

        except Exception as e:
            return False, f'ERROR: {e}', {}

        details = {
            'max_return': max_return,
            'current_return': current_return,
            'days_held': days_held,
        }

        # Check take profit (on max high)
        if max_return >= self.take_profit:
            return True, 'TAKE_PROFIT', details

        # Check stop loss (on current price)
        if current_return <= self.stop_loss:
            return True, 'STOP_LOSS', details

        # Check max hold
        if days_held >= self.max_hold:
            return True, 'MAX_HOLD', details

        return False, 'HOLDING', details


if __name__ == "__main__":
    # Test
    engine = ExitRulesEngine()

    # Download test data
    tsla = yf.Ticker('TSLA')
    spy = yf.Ticker('SPY')

    tsla_hist = tsla.history(period='3mo')
    spy_hist = spy.history(period='3mo')

    # Test position
    test_position = {
        'symbol': 'TSLA',
        'entry_date': '2025-12-01',
        'entry_price': 380.50,
        'days_held': 5,
    }

    should_exit, reason, details = engine.check_exit(
        test_position, '2025-12-06', tsla_hist, spy_hist
    )

    print(f"Exit: {should_exit}")
    print(f"Reason: {reason}")
    print(f"\n{engine.get_exit_summary(details)}")
