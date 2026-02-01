#!/usr/bin/env python3
"""
Macro Regime Detector - Layer 1-3 ของระบบ

Layer 1: Fed Policy (Cutting, Pausing, Hiking)
Layer 2: Market Breadth (% stocks above MA50)
Layer 3: Sector Leadership (Tech, Industrial, Defensive)

เป้าหมาย: กรองออก 80% ของ bad periods (ตุลา/พฤศจิกายน crash)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')


class FedPolicyDetector:
    """
    Layer 1: Fed Policy Detector

    ตรวจสอบ Federal Reserve policy stance:
    - CUTTING: Fed กำลังลดดอกเบี้ย → BULL market friendly
    - PAUSING: Fed หยุดขึ้นดอกเบี้ย → Neutral
    - HIKING: Fed กำลังขึ้นดอกเบี้ย → BEAR market risk
    """

    def __init__(self):
        # Fed Fund Rate history (approximation using treasury yields)
        self.fed_proxy = "^IRX"  # 13-week Treasury Bill (proxy for Fed rate)

    def get_fed_stance(self, date: datetime = None) -> Dict:
        """
        ตรวจสอบ Fed policy stance

        Returns:
            {
                'stance': 'CUTTING' | 'PAUSING' | 'HIKING',
                'rate_3m_change': float,  # % change in 3 months
                'rate_6m_change': float,  # % change in 6 months
                'risk_on': bool,          # True if safe to trade
            }
        """
        if date is None:
            date = datetime.now()

        try:
            # Get treasury yield as Fed rate proxy
            treasury = yf.Ticker(self.fed_proxy)

            # Get 6 months of data
            start_date = date - timedelta(days=200)
            hist = treasury.history(start=start_date, end=date + timedelta(days=1))

            if hist.empty or len(hist) < 60:
                return {
                    'stance': 'UNKNOWN',
                    'rate_3m_change': 0,
                    'rate_6m_change': 0,
                    'risk_on': False,
                    'reason': 'Insufficient data'
                }

            # Get current rate and historical rates
            current_rate = hist['Close'].iloc[-1]

            # 3-month change (approx 60 trading days)
            if len(hist) >= 60:
                rate_3m_ago = hist['Close'].iloc[-60]
                change_3m = ((current_rate - rate_3m_ago) / rate_3m_ago) * 100
            else:
                change_3m = 0

            # 6-month change (approx 120 trading days)
            if len(hist) >= 120:
                rate_6m_ago = hist['Close'].iloc[-120]
                change_6m = ((current_rate - rate_6m_ago) / rate_6m_ago) * 100
            else:
                change_6m = change_3m

            # Determine stance
            if change_3m < -5 or change_6m < -10:
                stance = 'CUTTING'
                risk_on = True
            elif change_3m > 5 or change_6m > 10:
                stance = 'HIKING'
                risk_on = False
            else:
                stance = 'PAUSING'
                risk_on = True  # Pausing is okay, not as bad as hiking

            return {
                'stance': stance,
                'rate_3m_change': change_3m,
                'rate_6m_change': change_6m,
                'current_rate': current_rate,
                'risk_on': risk_on,
            }

        except Exception as e:
            return {
                'stance': 'UNKNOWN',
                'rate_3m_change': 0,
                'rate_6m_change': 0,
                'risk_on': False,
                'reason': f'Error: {str(e)}'
            }


class MarketBreadthCalculator:
    """
    Layer 2: Market Breadth Calculator

    คำนวณ % ของหุ้นที่อยู่เหนือ MA50:
    - > 60% = STRONG (early/mid bull)
    - 40-60% = MIXED (uncertain)
    - < 40% = WEAK (late bull or bear)
    """

    # Major stocks to check breadth
    # OPTIMIZED: Reduced from 49 to 12 for faster backtesting
    BREADTH_UNIVERSE = [
        # Tech (4)
        'AAPL', 'MSFT', 'NVDA', 'GOOGL',

        # Healthcare (2)
        'JNJ', 'UNH',

        # Financials (2)
        'JPM', 'BAC',

        # Consumer (2)
        'WMT', 'HD',

        # Industrial (1)
        'CAT',

        # Energy (1)
        'XOM',
    ]

    def get_market_breadth(self, date: datetime = None) -> Dict:
        """
        คำนวณ market breadth

        Returns:
            {
                'health': 'STRONG' | 'MIXED' | 'WEAK',
                'pct_above_ma50': float,
                'stocks_above': int,
                'stocks_total': int,
                'risk_on': bool,
            }
        """
        if date is None:
            date = datetime.now()

        stocks_above = 0
        stocks_checked = 0

        # Check each stock
        for symbol in self.BREADTH_UNIVERSE:
            try:
                ticker = yf.Ticker(symbol)

                # Get 100 days of data (for MA50)
                start_date = date - timedelta(days=120)
                hist = ticker.history(start=start_date, end=date + timedelta(days=1))

                if hist.empty or len(hist) < 50:
                    continue

                # Calculate MA50
                ma50 = hist['Close'].rolling(window=50).mean()

                # Check if current price above MA50
                current_price = hist['Close'].iloc[-1]
                current_ma50 = ma50.iloc[-1]

                if current_price > current_ma50:
                    stocks_above += 1

                stocks_checked += 1

            except Exception:
                continue

        if stocks_checked == 0:
            return {
                'health': 'UNKNOWN',
                'pct_above_ma50': 0,
                'stocks_above': 0,
                'stocks_total': 0,
                'risk_on': False,
            }

        # Calculate percentage
        pct_above = (stocks_above / stocks_checked) * 100

        # Determine health
        if pct_above >= 60:
            health = 'STRONG'
            risk_on = True
        elif pct_above >= 40:
            health = 'MIXED'
            risk_on = True  # Can still trade but cautious
        else:
            health = 'WEAK'
            risk_on = False

        return {
            'health': health,
            'pct_above_ma50': pct_above,
            'stocks_above': stocks_above,
            'stocks_total': stocks_checked,
            'risk_on': risk_on,
        }


class SectorRotationTracker:
    """
    Layer 3: Sector Rotation Tracker

    ตรวจสอบ sector ไหน leading:
    - TECH leading = Early bull (risk on!)
    - INDUSTRIAL leading = Mid bull (still good)
    - DEFENSIVE leading = Late bull (risk off!)
    """

    SECTOR_ETFS = {
        'TECH': 'XLK',          # Technology
        'DISCRETIONARY': 'XLY', # Consumer Discretionary
        'INDUSTRIAL': 'XLI',    # Industrials
        'FINANCIAL': 'XLF',     # Financials
        'HEALTHCARE': 'XLV',    # Healthcare
        'UTILITIES': 'XLU',     # Utilities (defensive)
        'STAPLES': 'XLP',       # Consumer Staples (defensive)
    }

    def get_sector_leadership(self, date: datetime = None, lookback_days: int = 30) -> Dict:
        """
        ตรวจสอบ sector rotation

        Returns:
            {
                'stage': 'EARLY_BULL' | 'MID_BULL' | 'LATE_BULL' | 'BEAR',
                'leading_sector': str,
                'sector_returns': dict,
                'risk_on': bool,
            }
        """
        if date is None:
            date = datetime.now()

        sector_returns = {}

        # Calculate returns for each sector
        for sector_name, etf_symbol in self.SECTOR_ETFS.items():
            try:
                ticker = yf.Ticker(etf_symbol)

                # Get extra days to ensure we have enough trading days
                start_date = date - timedelta(days=lookback_days * 2)
                hist = ticker.history(start=start_date, end=date + timedelta(days=1))

                if hist.empty or len(hist) < 20:  # Need at least 20 days
                    continue

                # Calculate return from available data
                # Use lookback_days or all available data (whichever is smaller)
                actual_lookback = min(lookback_days, len(hist) - 1)

                price_start = hist['Close'].iloc[-(actual_lookback + 1)]
                price_end = hist['Close'].iloc[-1]

                sector_return = ((price_end - price_start) / price_start) * 100
                sector_returns[sector_name] = sector_return

            except Exception as e:
                continue

        if not sector_returns:
            return {
                'stage': 'UNKNOWN',
                'leading_sector': 'NONE',
                'sector_returns': {},
                'risk_on': False,
            }

        # Find leading sector
        leading_sector = max(sector_returns, key=sector_returns.get)

        # Determine stage based on leader
        if leading_sector in ['TECH', 'DISCRETIONARY']:
            stage = 'EARLY_BULL'
            risk_on = True
        elif leading_sector in ['INDUSTRIAL', 'FINANCIAL']:
            stage = 'MID_BULL'
            risk_on = True
        elif leading_sector in ['UTILITIES', 'STAPLES', 'HEALTHCARE']:
            stage = 'LATE_BULL'
            risk_on = False  # Defensive leading = trouble ahead
        else:
            stage = 'UNKNOWN'
            risk_on = False

        return {
            'stage': stage,
            'leading_sector': leading_sector,
            'sector_returns': sector_returns,
            'risk_on': risk_on,
        }


class MacroRegimeDetector:
    """
    Complete Macro Regime Detector

    รวม 3 layers:
    1. Fed Policy
    2. Market Breadth
    3. Sector Rotation

    ผลลัพธ์: RISK_ON (เข้าได้) หรือ RISK_OFF (อย่าเข้า)
    """

    def __init__(self):
        self.fed_detector = FedPolicyDetector()
        self.breadth_calc = MarketBreadthCalculator()
        self.sector_tracker = SectorRotationTracker()

    def get_macro_regime(self, date: datetime = None) -> Dict:
        """
        ตรวจสอบ macro regime ทั้งหมด

        Returns:
            {
                'risk_on': bool,              # True = เข้าได้!
                'risk_score': int,            # 0-3 (3 = ดีที่สุด)
                'fed_stance': str,
                'market_health': str,
                'sector_stage': str,
                'details': dict,
            }
        """
        if date is None:
            date = datetime.now()

        # Get all 3 layers
        fed_info = self.fed_detector.get_fed_stance(date)
        breadth_info = self.breadth_calc.get_market_breadth(date)
        sector_info = self.sector_tracker.get_sector_leadership(date)

        # Calculate risk score (0-3)
        risk_score = 0
        if fed_info['risk_on']:
            risk_score += 1
        if breadth_info['risk_on']:
            risk_score += 1
        if sector_info['risk_on']:
            risk_score += 1

        # Overall decision
        # Need at least 2/3 to be risk_on
        risk_on = risk_score >= 2

        return {
            'risk_on': risk_on,
            'risk_score': risk_score,
            'fed_stance': fed_info['stance'],
            'market_health': breadth_info['health'],
            'sector_stage': sector_info['stage'],
            'details': {
                'fed': fed_info,
                'breadth': breadth_info,
                'sector': sector_info,
            }
        }

    def should_trade(self, date: datetime = None) -> bool:
        """
        คำตอบง่ายๆ: ควรเทรดไหม?

        Returns:
            True: เทรดได้! (RISK_ON)
            False: อย่าเทรด! (RISK_OFF)
        """
        regime = self.get_macro_regime(date)
        return regime['risk_on']


def test_macro_regime():
    """ทดสอบ macro regime detector"""

    print("="*80)
    print("🧪 Testing Macro Regime Detector")
    print("="*80)

    detector = MacroRegimeDetector()

    # Test current date
    print("\n📅 Current Date:")
    regime = detector.get_macro_regime()

    print(f"\n🎯 Overall: {'✅ RISK_ON' if regime['risk_on'] else '❌ RISK_OFF'}")
    print(f"   Risk Score: {regime['risk_score']}/3")
    print(f"\n   Fed Stance: {regime['fed_stance']}")
    print(f"   Market Health: {regime['market_health']}")
    print(f"   Sector Stage: {regime['sector_stage']}")

    print(f"\n📊 Details:")
    print(f"   Fed: {regime['details']['fed']}")
    print(f"   Breadth: {regime['details']['breadth']['pct_above_ma50']:.1f}% above MA50")
    print(f"   Sector: {regime['details']['sector']['leading_sector']} leading")

    # Test historical dates
    print("\n" + "="*80)
    print("📅 Historical Tests:")
    print("="*80)

    test_dates = [
        ('2025-06-29', 'June 29 (lost -2.3%)'),
        ('2025-09-28', 'Sept 28 (won +8.7%)'),
        ('2025-10-05', 'Oct 5 (lost -26%)'),
    ]

    for date_str, desc in test_dates:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        regime = detector.get_macro_regime(date)

        status = '✅ RISK_ON' if regime['risk_on'] else '❌ RISK_OFF'
        print(f"\n{desc}:")
        print(f"   {status} (Score: {regime['risk_score']}/3)")
        print(f"   Fed: {regime['fed_stance']}, Breadth: {regime['market_health']}, Sector: {regime['sector_stage']}")


if __name__ == "__main__":
    test_macro_regime()
