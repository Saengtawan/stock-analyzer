"""IBKR broker — execution layer (orders + positions). Data still from Alpaca.

Connects to IB Gateway running on localhost:4002 (paper).
Uses ib_insync for synchronous API access.
"""
import os
from typing import Optional
from dataclasses import dataclass

try:
    from ib_insync import IB, Stock, MarketOrder, Order, util
except ImportError:
    raise ImportError("pip install ib_insync")


GATEWAY_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
GATEWAY_PORT = int(os.getenv('IBKR_PORT', '4002'))  # 4002 paper / 4001 live
CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', '1'))
PER_TRADE_BUDGET = float(os.getenv('IBKR_BUDGET', '1500'))  # $3000 total / 2 picks = $1500 each


@dataclass
class IBKRPosition:
    symbol: str
    qty: int
    avg_cost: float
    market_price: float
    unrealized_pnl: float


class IBKRBroker:
    """Thin wrapper around ib_insync for the operations our system needs."""

    def __init__(self, host=GATEWAY_HOST, port=GATEWAY_PORT, client_id=CLIENT_ID):
        self.ib = IB()
        self.host = host; self.port = port; self.client_id = client_id

    def connect(self):
        if not self.ib.isConnected():
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
        return self.ib.isConnected()

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()

    def account_summary(self) -> dict:
        """Get key account fields: cash, equity, settled."""
        s = {a.tag: a.value for a in self.ib.accountSummary()}
        return {
            'account': s.get('AccountCode',''),
            'net_liq': float(s.get('NetLiquidation', 0)),
            'cash': float(s.get('TotalCashValue', 0)),
            'settled_cash': float(s.get('SettledCash', 0)),  # critical for cash account
            'buying_power': float(s.get('BuyingPower', 0)),
        }

    def get_positions(self) -> list:
        out = []
        for p in self.ib.positions():
            tickers = self.ib.reqTickers(p.contract)
            mp = tickers[0].marketPrice() if tickers else 0
            out.append(IBKRPosition(
                symbol=p.contract.symbol,
                qty=int(p.position),
                avg_cost=float(p.avgCost),
                market_price=float(mp or 0),
                unrealized_pnl=float((mp - p.avgCost) * p.position) if mp else 0,
            ))
        return out

    def buy_with_dynamic_trail(self, symbol: str, entry_price: float,
                                 budget: float = PER_TRADE_BUDGET,
                                 initial_trail_pct: float = 3.0) -> tuple:
        """Place buy market order + initial trailing stop.
        Returns (qty, buy_trade, stop_trade) — stop_trade can be modified later
        as profit grows (called by position monitor for dynamic tightening).
        """
        contract = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)
        qty = int(budget / entry_price)
        if qty < 1:
            return 0, None, None

        # Market buy
        buy_order = MarketOrder('BUY', qty)
        buy_trade = self.ib.placeOrder(contract, buy_order)

        # Trailing stop sell — start at initial_trail_pct
        stop_order = Order(
            action='SELL',
            orderType='TRAIL',
            totalQuantity=qty,
            trailingPercent=initial_trail_pct,
            tif='DAY',
            outsideRth=False,
        )
        stop_trade = self.ib.placeOrder(contract, stop_order)
        return qty, buy_trade, stop_trade

    def update_trail_pct(self, symbol: str, new_trail_pct: float):
        """Tighten trailing stop on existing position. Cancel + replace."""
        contract = Stock(symbol, 'SMART', 'USD')
        # Find existing trailing stop order
        for trade in self.ib.openTrades():
            if (trade.contract.symbol == symbol and
                    trade.order.orderType == 'TRAIL' and
                    trade.order.action == 'SELL'):
                qty = trade.order.totalQuantity
                self.ib.cancelOrder(trade.order)
                # Place new tighter trail
                new_order = Order(
                    action='SELL', orderType='TRAIL',
                    totalQuantity=qty,
                    trailingPercent=new_trail_pct,
                    tif='DAY', outsideRth=False,
                )
                return self.ib.placeOrder(contract, new_order)
        return None

    def close_position(self, symbol: str):
        for p in self.ib.positions():
            if p.contract.symbol == symbol and p.position > 0:
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                # Cancel any open stops first
                for trade in self.ib.openTrades():
                    if trade.contract.symbol == symbol:
                        self.ib.cancelOrder(trade.order)
                # Sell market
                order = MarketOrder('SELL', int(p.position))
                return self.ib.placeOrder(contract, order)
        return None


if __name__ == '__main__':
    # Smoke test
    b = IBKRBroker()
    if not b.connect():
        print("FAILED to connect — is Gateway running on", GATEWAY_PORT, "?")
        raise SystemExit(1)
    print("Connected")
    print("Account:", b.account_summary())
    print("Positions:", b.get_positions())
    b.disconnect()
