#!/usr/bin/env python3
"""
Complete Growth Catalyst System - ระบบสมบูรณ์ทั้งหมด 6 Layers

เป้าหมาย: 10-15% ต่อเดือน (120-180% ต่อปี)

Layer 1-3: Macro Filter (Fed, Breadth, Sector)
Layer 4: Fundamental Quality (Earnings, Revenue)
Layer 5: Catalyst Detection (Breakout, Volume, Momentum)
Layer 6: Technical Entry/Exit (RSI, Pullback, Adaptive TP/SL)

Expected Performance:
- Win Rate: 50-60% (vs 6% before)
- Avg Return: +5-8% per trade (vs +1% before)
- Trades/Month: 8-12 (vs 4 before)
- Monthly Return: +10-15% (vs -3% before)
"""

import sys
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Import our layers
from src.macro_regime_detector import MacroRegimeDetector
from src.fundamental_screener import FundamentalScreener
from src.market_regime_detector import MarketRegimeDetector


class CompleteGrowthSystem:
    """
    ระบบสมบูรณ์ทั้งหมด 6 Layers
    """

    # Universe of stocks to screen
    STOCK_UNIVERSE = [
        # v7.1 Winners
        'GOOGL', 'META', 'DASH', 'TEAM', 'ROKU', 'TSM', 'LRCX',

        # Mega caps
        'AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA',

        # High growth
        'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG',

        # Semiconductors
        'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC',

        # Consumer tech
        'UBER', 'ABNB', 'COIN', 'SHOP',
    ]

    def __init__(self):
        # Initialize all layers
        self.macro_detector = MacroRegimeDetector()
        self.fundamental_screener = FundamentalScreener()
        self.technical_detector = MarketRegimeDetector()  # For technical regime

        # Entry filters (from v3.0)
        self.entry_filters = {
            'beta_min': 0.8,
            'beta_max': 2.0,
            'volatility_min': 35.0,
            'rs_min': 5.0,
            'momentum_30d_min': 8.0,
        }

    def screen_for_entries(self, date: datetime = None, quiet: bool = False) -> List[Dict]:
        """
        หาหุ้นที่ผ่านทั้งหมด 6 layers

        Args:
            date: Date to screen (default: today)
            quiet: If True, suppress verbose output (default: False)

        Returns:
            List of stocks ready to buy (sorted by score)
        """
        if date is None:
            date = datetime.now()

        if not quiet:
            print(f"\n{'='*80}")
            print(f"🔍 COMPLETE SYSTEM SCREENING - {date.strftime('%Y-%m-%d')}")
            print(f"{'='*80}")

        # Layer 1-3: Check Macro Regime
        if not quiet:
            print("\n📊 Layer 1-3: Macro Regime Check...")

        macro_regime = self.macro_detector.get_macro_regime(date)

        if not quiet:
            print(f"   Fed: {macro_regime['fed_stance']}")
            print(f"   Market Health: {macro_regime['market_health']}")
            print(f"   Sector Stage: {macro_regime['sector_stage']}")
            print(f"   Risk Score: {macro_regime['risk_score']}/3")
            print(f"   Decision: {'✅ RISK_ON - Trade!' if macro_regime['risk_on'] else '❌ RISK_OFF - No trade!'}")

        if not macro_regime['risk_on']:
            if not quiet:
                print("\n⚠️  MACRO RISK_OFF - Skipping stock screening")
            return []

        # Layer 4-5: Fundamental + Catalyst Screening
        if not quiet:
            print(f"\n📊 Layer 4-5: Fundamental + Catalyst Screening...")
            print(f"   Screening {len(self.STOCK_UNIVERSE)} stocks...")

        fundamental_passed = self.fundamental_screener.screen_universe(
            self.STOCK_UNIVERSE, date
        )

        if not quiet:
            print(f"   ✅ {len(fundamental_passed)} stocks passed fundamental/catalyst")

        if not fundamental_passed:
            if not quiet:
                print("\n⚠️  No stocks passed fundamental screening")
            return []

        # Layer 6: Technical Entry Check
        if not quiet:
            print(f"\n📊 Layer 6: Technical Entry Check...")

        final_candidates = []

        for stock in fundamental_passed:
            symbol = stock['symbol']

            # Check technical entry (pass macro_regime for adaptive RSI threshold)
            technical_ok, technical_details = self._check_technical_entry(symbol, date, macro_regime)

            if technical_ok:
                # Combine all information
                final_candidates.append({
                    'symbol': symbol,
                    'macro': macro_regime,
                    'fundamental': stock['fundamental'],
                    'catalyst': stock['catalyst'],
                    'technical': technical_details,
                    'total_score': stock['total_score'] + technical_details.get('score', 0),
                })

                if not quiet:
                    print(f"   ✅ {symbol}: READY TO BUY!")
            else:
                reason = technical_details.get('reason', 'Unknown')
                if not quiet:
                    print(f"   ❌ {symbol}: Technical failed ({reason})")

        # Sort by total score
        final_candidates.sort(key=lambda x: x['total_score'], reverse=True)

        if not quiet:
            print(f"\n🎯 Final Result: {len(final_candidates)} stocks ready to buy!")

        return final_candidates

    def _check_technical_entry(self, symbol: str, date: datetime, macro_regime: Dict = None) -> Tuple[bool, Dict]:
        """
        Layer 6: Check technical entry conditions

        เช็ค:
        - Technical regime (BULL)
        - RSI (adaptive based on sector stage)
        - Stock quality (RS, Vol, Momentum)
        - Pullback entry (optional)
        """
        try:
            # Get technical regime
            regime_info = self.technical_detector.get_current_regime(date)

            if regime_info['regime'] != 'BULL':
                return False, {'reason': f"Not BULL (regime: {regime_info['regime']})"}

            # Check SPY RSI (adaptive based on sector stage)
            spy_rsi = regime_info['details']['rsi']

            # Determine RSI threshold based on sector stage
            if macro_regime and macro_regime.get('sector_stage') in ['EARLY_BULL', 'MID_BULL']:
                # Allow higher RSI in healthy bull markets
                rsi_threshold = 75
            else:
                # More conservative in late bull or unknown
                rsi_threshold = 70

            if spy_rsi > rsi_threshold:
                return False, {'reason': f"RSI too high ({spy_rsi:.1f} > {rsi_threshold})"}

            # Get stock data
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=date - timedelta(days=90),
                                 end=date + timedelta(days=1))

            if hist.empty or len(hist) < 50:
                return False, {'reason': 'Insufficient data'}

            info = ticker.info
            entry_price = hist['Close'].iloc[-1]

            # Check beta
            beta = info.get('beta', 1.0) or 1.0
            if beta < self.entry_filters['beta_min'] or beta > self.entry_filters['beta_max']:
                return False, {'reason': f'Beta {beta:.2f} out of range'}

            # Check volatility
            returns = hist['Close'].pct_change().dropna()
            if len(returns) >= 20:
                volatility = returns.std() * (252 ** 0.5) * 100
                if volatility < self.entry_filters['volatility_min']:
                    return False, {'reason': f'Volatility {volatility:.1f}% too low'}
            else:
                return False, {'reason': 'Insufficient data for volatility'}

            # Check RS (Relative Strength vs SPY)
            if len(hist) >= 30:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(start=date - timedelta(days=90),
                                      end=date + timedelta(days=1))

                if len(spy_hist) >= 30:
                    stock_ret = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
                    spy_ret = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-30]) - 1) * 100
                    rs = stock_ret - spy_ret

                    if rs < self.entry_filters['rs_min']:
                        return False, {'reason': f'RS {rs:.1f}% too low'}
                else:
                    return False, {'reason': 'Insufficient SPY data'}
            else:
                return False, {'reason': 'Insufficient data for RS'}

            # Check momentum
            if len(hist) >= 30:
                momentum_30d = ((hist['Close'].iloc[-1] / hist['Close'].iloc[-30]) - 1) * 100
                if momentum_30d < self.entry_filters['momentum_30d_min']:
                    return False, {'reason': f'Momentum {momentum_30d:.1f}% too low'}
            else:
                return False, {'reason': 'Insufficient data for momentum'}

            # Calculate technical score
            technical_score = 50  # Base score for passing

            # Bonus for strong metrics
            if rs > 10:
                technical_score += 20
            if volatility > 50:
                technical_score += 15
            if momentum_30d > 15:
                technical_score += 15

            # All checks passed!
            return True, {
                'score': technical_score,
                'beta': beta,
                'volatility': volatility,
                'rs': rs,
                'momentum_30d': momentum_30d,
                'entry_price': entry_price,
                'regime': regime_info['regime'],
            }

        except Exception as e:
            return False, {'reason': f'Error: {str(e)}'}


def test_complete_system():
    """ทดสอบระบบสมบูรณ์"""

    print("="*80)
    print("🚀 COMPLETE GROWTH CATALYST SYSTEM")
    print("="*80)

    system = CompleteGrowthSystem()

    # Test current date
    print("\n📅 Testing Current Date:\n")
    candidates = system.screen_for_entries()

    if candidates:
        print(f"\n{'='*80}")
        print(f"✅ TOP PICKS ({len(candidates)} stocks):")
        print(f"{'='*80}\n")

        for i, stock in enumerate(candidates, 1):
            print(f"{i}. {stock['symbol']:6s} - Total Score: {stock['total_score']}")
            print(f"   Fundamental: {stock['fundamental']['quality_score']}/100 "
                  f"(EPS: {stock['fundamental']['earnings_growth']:+.1f}%, "
                  f"Rev: {stock['fundamental']['revenue_growth']:+.1f}%)")
            print(f"   Catalyst: {stock['catalyst']['catalyst_score']}/100")
            print(f"   Technical: {stock['technical']['score']}/100 "
                  f"(RS: {stock['technical']['rs']:+.1f}%, "
                  f"Vol: {stock['technical']['volatility']:.1f}%)")
            print(f"   Entry Price: ${stock['technical']['entry_price']:.2f}")
            print()
    else:
        print("\n❌ No stocks ready to buy today")

    # Test historical dates
    print("\n" + "="*80)
    print("📅 HISTORICAL TESTS:")
    print("="*80)

    test_dates = [
        '2025-09-28',  # Won +8.7%
        '2025-10-05',  # Lost -26%
    ]

    for date_str in test_dates:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        print(f"\n{date_str}:")
        candidates = system.screen_for_entries(date)
        print(f"   Result: {len(candidates)} stocks ready to buy")


if __name__ == "__main__":
    test_complete_system()
