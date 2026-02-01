#!/usr/bin/env python3
"""
Limited Capital Trader - สำหรับคนทุนจำกัด

Backtest Results (Score >= 92, SL -5%):
- 22 trades ใน 4 เดือน (~5-6 trades/month)
- 6 losers เท่านั้น (73% Win Rate)
- ขาดทุนเฉลี่ย -5% ต่อครั้ง (ยอมรับได้)
- Max Drawdown -10% (เงินไม่จมนาน)
- Total Return +107%

การใช้งาน:
    from limited_capital_trader import LimitedCapitalTrader

    trader = LimitedCapitalTrader()

    # ตรวจ portfolio ทุกวัน
    trader.daily_check()

    # ดูแนะนำการซื้อ
    trader.buy_recommendation('AAPL')
"""

import sys
sys.path.insert(0, '.')

from portfolio_manager import PortfolioManager
from datetime import datetime
from typing import List, Dict
import yfinance as yf


class LimitedCapitalTrader:
    """
    Trader สำหรับคนทุนจำกัด - เน้น loser น้อย, ตัด loss เร็ว
    """

    # Settings ที่ backtest แล้วได้ผลดีที่สุด
    MIN_SCORE = 92          # เข้มงวด = loser น้อย
    STOP_LOSS = -5.0        # ตัด loss เร็ว
    WARNING_LEVEL = -2.0    # เตือนเร็ว
    TIME_STOP_DAYS = 7      # ไม่รอนาน
    EARLY_DIP_PCT = -3.0    # ขายเร็วถ้า dip ใน 3 วันแรก

    def __init__(self, portfolio_file: str = 'portfolio.json'):
        self.pm = PortfolioManager(portfolio_file)

        print("=" * 60)
        print("LIMITED CAPITAL TRADER")
        print("=" * 60)
        print(f"   Min Score: {self.MIN_SCORE}")
        print(f"   Stop Loss: {self.STOP_LOSS}%")
        print(f"   Time Stop: {self.TIME_STOP_DAYS} days")
        print(f"   Early Dip: {self.EARLY_DIP_PCT}% in 3 days")
        print()
        print("   Backtest: 73% WR, 6 losers, +107% return")
        print("=" * 60)

    def daily_check(self, auto_sell: bool = False) -> Dict:
        """
        ตรวจ portfolio ทุกวัน - ขาย losers เร็ว

        Args:
            auto_sell: True = ขายอัตโนมัติ, False = แค่แนะนำ

        Returns:
            Dict with recommendations
        """
        print()
        print("=" * 60)
        print(f"DAILY CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)

        results = self.pm.check_stop_loss(
            hard_stop_pct=self.STOP_LOSS,
            warning_pct=self.WARNING_LEVEL,
            trailing_stop_pct=-4.0,
            time_stop_days=self.TIME_STOP_DAYS,
            early_dip_pct=self.EARLY_DIP_PCT,
            early_dip_days=3,
            enable_early_dip=True
        )

        # Summary
        sells_needed = len(results['sell_now']) + len(results['early_dip_exit'])

        if sells_needed == 0:
            print("\n Portfolio OK! No sells needed")
            return {'action': 'HOLD', 'sells': 0}

        if auto_sell:
            return self.pm.auto_stop_loss_sell(confirm=True, include_early_dip=True)
        else:
            print()
            print("=" * 60)
            print(f"   Recommend selling {sells_needed} positions")
            print("   Run daily_check(auto_sell=True) to execute")
            print("=" * 60)
            return {'action': 'SELL_RECOMMENDED', 'sells': sells_needed, 'details': results}

    def buy_recommendation(self, symbol: str, amount: float = 1000) -> Dict:
        """
        แนะนำการซื้อหุ้น พร้อมคำนวณ stop loss

        Args:
            symbol: ชื่อหุ้น
            amount: จำนวนเงิน (default $1000)

        Returns:
            Dict with buy recommendation
        """
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='5d')
            if hist.empty:
                return {'error': f'No data for {symbol}'}

            price = float(hist['Close'].iloc[-1])
            shares = int(amount / price)
            actual_amount = shares * price

            stop_price = price * (1 + self.STOP_LOSS/100)
            target_price = price * 1.10  # +10% target
            max_loss = actual_amount * (abs(self.STOP_LOSS)/100)

            print()
            print("=" * 60)
            print(f"BUY RECOMMENDATION: {symbol}")
            print("=" * 60)
            print(f"   Entry Price: ${price:.2f}")
            print(f"   Shares: {shares}")
            print(f"   Amount: ${actual_amount:,.2f}")
            print()
            print(f"   Target (+10%): ${target_price:.2f}")
            print(f"   Stop Loss ({self.STOP_LOSS}%): ${stop_price:.2f}")
            print(f"   Max Loss: ${max_loss:.2f}")
            print()
            print("   WARNING: If price hits Stop Loss -> SELL IMMEDIATELY!")
            print("   WARNING: If dip -3% in first 3 days -> SELL IMMEDIATELY!")

            return {
                'symbol': symbol,
                'entry_price': price,
                'shares': shares,
                'amount': actual_amount,
                'stop_loss': stop_price,
                'target': target_price,
                'max_loss': max_loss
            }

        except Exception as e:
            return {'error': str(e)}

    def portfolio_status(self):
        """แสดงสถานะ portfolio"""
        self.pm.display_status()

    def add_position(self, symbol: str, entry_price: float, amount: float = 1000):
        """เพิ่ม position ใหม่"""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.pm.add_position(
            symbol=symbol,
            entry_price=entry_price,
            entry_date=today,
            filters={'min_score': self.MIN_SCORE},
            amount=amount
        )


def main():
    """Demo usage"""
    print()
    print("LIMITED CAPITAL TRADER - DEMO")
    print()

    trader = LimitedCapitalTrader()

    # Show portfolio status
    trader.portfolio_status()

    # Daily check
    trader.daily_check(auto_sell=False)

    # Show buy recommendation
    trader.buy_recommendation('AAPL')


if __name__ == "__main__":
    main()
