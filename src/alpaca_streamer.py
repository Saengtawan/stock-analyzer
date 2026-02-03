#!/usr/bin/env python3
"""
ALPACA REAL-TIME PRICE STREAMER v1.1

Uses alpaca-py (official SDK) for real-time streaming.
Streams real-time price data from Alpaca and broadcasts via WebSocket.

Usage:
    streamer = AlpacaStreamer(api_key, secret_key, socketio)
    streamer.subscribe(['AMD', 'VICR'])
    streamer.start()
"""

import os
import asyncio
import threading
import time
from datetime import datetime
from typing import List, Set, Callable, Optional
from loguru import logger

# Alpaca-py SDK
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed


class AlpacaStreamer:
    """
    Real-time price streamer using Alpaca WebSocket API (alpaca-py)

    Free tier includes:
    - IEX exchange data (real-time)
    - All US stocks
    """

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        socketio=None,
        paper: bool = True
    ):
        self.api_key = api_key or os.getenv('ALPACA_API_KEY')
        self.secret_key = secret_key or os.getenv('ALPACA_SECRET_KEY')
        self.socketio = socketio
        self.paper = paper

        # Data feed - IEX is free real-time
        self.data_feed = DataFeed.IEX

        # State
        self.stream: Optional[StockDataStream] = None
        self.subscribed_symbols: Set[str] = set()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Price cache (latest prices)
        self.prices: dict = {}

        # Callbacks
        self.on_price_update: Optional[Callable] = None

        logger.info(f"AlpacaStreamer v1.1 initialized (paper={paper}, feed=IEX)")

    def _create_stream(self) -> StockDataStream:
        """Create Alpaca stream connection"""
        return StockDataStream(
            self.api_key,
            self.secret_key,
            feed=self.data_feed
        )

    async def _handle_trade(self, trade):
        """Handle real-time trade data"""
        try:
            symbol = trade.symbol
            price = float(trade.price)
            size = int(trade.size)
            timestamp = trade.timestamp

            # Update cache
            self.prices[symbol] = {
                'price': price,
                'size': size,
                'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                'type': 'trade'
            }

            # Broadcast via WebSocket
            if self.socketio:
                self.socketio.emit('price_update', {
                    'symbol': symbol,
                    'price': price,
                    'size': size,
                    'timestamp': self.prices[symbol]['timestamp'],
                    'type': 'trade'
                })

            # Custom callback
            if self.on_price_update:
                self.on_price_update(symbol, price, 'trade')

            logger.debug(f"Trade: {symbol} ${price:.2f} x{size}")

        except Exception as e:
            logger.error(f"Error handling trade: {e}")

    async def _handle_bar(self, bar):
        """Handle 1-minute bar data"""
        try:
            symbol = bar.symbol
            price = float(bar.close)

            # Update cache with bar data
            self.prices[symbol] = {
                'price': price,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': price,
                'volume': int(bar.volume),
                'timestamp': bar.timestamp.isoformat() if hasattr(bar.timestamp, 'isoformat') else str(bar.timestamp),
                'type': 'bar'
            }

            # Broadcast via WebSocket
            if self.socketio:
                self.socketio.emit('price_update', {
                    'symbol': symbol,
                    'price': price,
                    'open': self.prices[symbol]['open'],
                    'high': self.prices[symbol]['high'],
                    'low': self.prices[symbol]['low'],
                    'volume': self.prices[symbol]['volume'],
                    'timestamp': self.prices[symbol]['timestamp'],
                    'type': 'bar'
                })

            # Custom callback
            if self.on_price_update:
                self.on_price_update(symbol, price, 'bar')

            logger.debug(f"Bar: {symbol} O:{bar.open:.2f} H:{bar.high:.2f} L:{bar.low:.2f} C:{price:.2f}")

        except Exception as e:
            logger.error(f"Error handling bar: {e}")

    async def _handle_quote(self, quote):
        """Handle bid/ask quote updates"""
        try:
            symbol = quote.symbol
            bid = float(quote.bid_price)
            ask = float(quote.ask_price)
            mid = (bid + ask) / 2

            # Update cache
            self.prices[symbol] = {
                'price': mid,
                'bid': bid,
                'ask': ask,
                'bid_size': int(quote.bid_size),
                'ask_size': int(quote.ask_size),
                'timestamp': quote.timestamp.isoformat() if hasattr(quote.timestamp, 'isoformat') else str(quote.timestamp),
                'type': 'quote'
            }

            # Broadcast via WebSocket (less frequently for quotes)
            if self.socketio:
                self.socketio.emit('quote_update', {
                    'symbol': symbol,
                    'bid': bid,
                    'ask': ask,
                    'mid': mid,
                    'spread': ask - bid,
                    'timestamp': self.prices[symbol]['timestamp']
                })

        except Exception as e:
            logger.error(f"Error handling quote: {e}")

    def subscribe(self, symbols: List[str], trades: bool = True, bars: bool = True, quotes: bool = False):
        """
        Subscribe to symbols for real-time data

        Args:
            symbols: List of stock symbols
            trades: Subscribe to trade data (most real-time)
            bars: Subscribe to 1-minute bars
            quotes: Subscribe to bid/ask quotes
        """
        symbols = [s.upper() for s in symbols]
        self.subscribed_symbols.update(symbols)

        if self.stream and self.running:
            # Add to existing stream
            if trades:
                self.stream.subscribe_trades(self._handle_trade, *symbols)
            if bars:
                self.stream.subscribe_bars(self._handle_bar, *symbols)
            if quotes:
                self.stream.subscribe_quotes(self._handle_quote, *symbols)
            logger.info(f"Subscribed to: {symbols}")
        else:
            logger.info(f"Queued subscription for: {symbols}")

    def unsubscribe(self, symbols: List[str]):
        """Unsubscribe from symbols"""
        symbols = [s.upper() for s in symbols]
        self.subscribed_symbols.difference_update(symbols)

        if self.stream and self.running:
            self.stream.unsubscribe_trades(*symbols)
            self.stream.unsubscribe_bars(*symbols)
            logger.info(f"Unsubscribed from: {symbols}")

    def _run_stream(self):
        """Run stream in separate thread with retry logic"""
        retry_count = 0
        max_retries = 5
        retry_delay = 5

        while self.running and retry_count < max_retries:
            try:
                # Create new event loop for this thread
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

                # Create stream
                self.stream = self._create_stream()

                # Subscribe to queued symbols
                if self.subscribed_symbols:
                    symbols = list(self.subscribed_symbols)
                    self.stream.subscribe_trades(self._handle_trade, *symbols)
                    # Note: bars might not be available for IEX feed
                    # self.stream.subscribe_bars(self._handle_bar, *symbols)
                    logger.info(f"Streaming started for: {symbols}")

                # Run stream (blocking)
                self.stream.run()

            except ValueError as e:
                if "auth failed" in str(e):
                    retry_count += 1
                    logger.warning(f"Auth failed, retry {retry_count}/{max_retries} in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)  # Exponential backoff
                else:
                    logger.error(f"Stream error: {e}")
                    break

            except Exception as e:
                logger.error(f"Stream error: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)

        if retry_count >= max_retries:
            logger.error("Max retries reached, stopping streamer")
        self.running = False

    def start(self):
        """Start streaming in background thread"""
        if self.running:
            logger.warning("Streamer already running")
            return

        if not self.subscribed_symbols:
            logger.warning("No symbols to stream")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_stream, daemon=True)
        self.thread.start()
        logger.info("AlpacaStreamer started")

    def stop(self):
        """Stop streaming"""
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
            except:
                pass
        if self.loop:
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except:
                pass
        logger.info("AlpacaStreamer stopped")

    def get_price(self, symbol: str) -> Optional[float]:
        """Get latest cached price for symbol"""
        data = self.prices.get(symbol.upper())
        return data['price'] if data else None

    def get_all_prices(self) -> dict:
        """Get all cached prices"""
        return {s: d['price'] for s, d in self.prices.items()}


# Global streamer instance
_streamer: Optional[AlpacaStreamer] = None


def get_streamer() -> Optional[AlpacaStreamer]:
    """Get global streamer instance"""
    return _streamer


def init_streamer(socketio, api_key: str = None, secret_key: str = None) -> AlpacaStreamer:
    """Initialize global streamer"""
    global _streamer
    _streamer = AlpacaStreamer(
        api_key=api_key,
        secret_key=secret_key,
        socketio=socketio,
        paper=True
    )
    return _streamer


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    import time
    from dotenv import load_dotenv

    load_dotenv()

    print("=" * 50)
    print("ALPACA REAL-TIME STREAMER TEST v1.1")
    print("=" * 50)

    # Create streamer without socketio for testing
    streamer = AlpacaStreamer(
        api_key=os.getenv('ALPACA_API_KEY'),
        secret_key=os.getenv('ALPACA_SECRET_KEY'),
        paper=True
    )

    # Custom callback for testing
    def on_price(symbol, price, data_type):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {symbol}: ${price:.2f} ({data_type})")

    streamer.on_price_update = on_price

    # Subscribe to test symbols
    streamer.subscribe(['AMD', 'AAPL', 'TSLA'])

    # Start streaming
    streamer.start()

    print("\nStreaming started. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        streamer.stop()
        print("Done.")
