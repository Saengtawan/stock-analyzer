#!/usr/bin/env python3
"""
Pullback Catalyst Screener - Web UI Integration

Scans for stocks with catalyst events that are pulling back to support levels.
Strategy: Wait for catalyst (volume spike + breakout), then enter on pullback.
"""

import numpy as np
from datetime import datetime, timedelta
from loguru import logger


class PullbackCatalystScreener:
    """Screener for pullback catalyst opportunities"""

    def __init__(self, analyzer):
        """Initialize with stock analyzer"""
        self.analyzer = analyzer
        self.data_manager = analyzer.data_manager

        # Best sectors from backtesting
        self.best_sectors = [
            'Finance_Banks',
            'Healthcare_Pharma',
            'Semiconductors',
            'Tech_Software',
            'Consumer_Discretionary',
        ]

    def screen_pullback_opportunities(
        self,
        min_price: float = 20.0,
        max_price: float = 500.0,
        min_volume_ratio: float = 1.8,
        min_catalyst_score: float = 45.0,
        max_rsi: float = 76.0,
        max_stocks: int = 20,
        lookback_days: int = 5,
    ) -> list:
        """
        Screen for pullback catalyst opportunities.

        Returns stocks that:
        1. Had a catalyst event in the last N days (volume spike + breakout)
        2. Are now pulling back to support (MA10 or ATR-based)
        3. Meet quality filters (RSI, price, sector)
        """
        logger.info("🎯 Starting Pullback Catalyst Screening")
        logger.info(f"   Filters: Price ${min_price}-${max_price}, Vol Ratio >= {min_volume_ratio}x")
        logger.info(f"   Catalyst Score >= {min_catalyst_score}, RSI <= {max_rsi}")

        opportunities = []

        # Get universe from AI generator or use default quality stocks
        try:
            from ai_universe_generator import AIUniverseGenerator
            universe_gen = AIUniverseGenerator()
            universe = universe_gen.get_ai_universe(
                multiplier=3,
                sectors=self.best_sectors,
                min_price=min_price,
                max_price=max_price
            )
            symbols = [s['symbol'] for s in universe]
            logger.info(f"   Using AI universe: {len(symbols)} stocks")
        except Exception as e:
            logger.warning(f"AI universe failed: {e}, using default quality stocks")
            # Fallback to default quality stocks
            symbols = self._get_sector_symbols(min_price, max_price)

        # Analyze each symbol
        for symbol in symbols:
            try:
                result = self._analyze_pullback_opportunity(
                    symbol,
                    min_volume_ratio=min_volume_ratio,
                    min_catalyst_score=min_catalyst_score,
                    max_rsi=max_rsi,
                    lookback_days=lookback_days,
                )
                if result:
                    opportunities.append(result)
            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")
                continue

        # Sort by catalyst score (higher = better)
        opportunities.sort(key=lambda x: x.get('catalyst_score', 0), reverse=True)

        # Limit results
        opportunities = opportunities[:max_stocks]

        logger.info(f"✅ Found {len(opportunities)} pullback opportunities")

        return opportunities

    def _get_sector_symbols(self, min_price: float, max_price: float) -> list:
        """Get symbols from best sectors - use default quality stocks"""
        # Quality stocks from best performing sectors in backtesting
        default_symbols = [
            # Tech/Software
            'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX', 'CRM', 'ADBE', 'NOW', 'ORCL',
            # Semiconductors
            'NVDA', 'AMD', 'AVGO', 'QCOM', 'MU', 'INTC', 'AMAT', 'LRCX', 'KLAC', 'MRVL',
            # Finance/Banks
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'V', 'MA',
            # Healthcare/Pharma
            'JNJ', 'PFE', 'UNH', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'VRTX',
            # Consumer Discretionary
            'TSLA', 'HD', 'NKE', 'SBUX', 'MCD', 'LOW', 'TGT', 'COST', 'DIS', 'CMG',
            # Energy
            'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'PSX', 'VLO', 'MPC', 'HES',
            # Industrials
            'CAT', 'DE', 'UNP', 'HON', 'GE', 'BA', 'LMT', 'RTX', 'UPS', 'FDX',
        ]
        logger.info(f"   Using default universe: {len(default_symbols)} quality stocks")
        return default_symbols

    def _analyze_pullback_opportunity(
        self,
        symbol: str,
        min_volume_ratio: float,
        min_catalyst_score: float,
        max_rsi: float,
        lookback_days: int,
    ) -> dict | None:
        """Analyze a single symbol for pullback opportunity"""

        # Get price data
        try:
            data = self.data_manager.get_stock_data(symbol, period='3mo')
            if data is None or len(data) < 40:
                return None
        except Exception:
            return None

        closes = data['Close'].values if 'Close' in data.columns else data['close'].values
        highs = data['High'].values if 'High' in data.columns else data['high'].values
        lows = data['Low'].values if 'Low' in data.columns else data['low'].values
        volumes = data['Volume'].values if 'Volume' in data.columns else data['volume'].values

        if len(closes) < 40:
            return None

        current_price = closes[-1]

        # Check for catalyst in last N days
        catalyst_info = self._detect_catalyst(
            closes, highs, lows, volumes,
            min_volume_ratio, min_catalyst_score, lookback_days
        )

        if not catalyst_info:
            return None

        # Check RSI
        rsi = self._calculate_rsi(closes)
        if rsi > max_rsi:
            return None

        # Check if pulling back to support
        pullback_info = self._check_pullback(closes, highs, lows, catalyst_info)

        if not pullback_info['is_pullback']:
            return None

        # Calculate entry and exit levels
        entry_price = pullback_info['entry_target']
        stop_loss = entry_price * 0.975  # -2.5% stop
        target1 = entry_price * 1.05     # +5% T1
        target2 = entry_price * 1.085    # +8.5% T2
        target3 = entry_price * 1.13     # +13% T3

        # Get additional info
        try:
            info = self.data_manager.yahoo_client.get_stock_info(symbol)
            sector = info.get('sector', 'Unknown')
            market_cap = info.get('marketCap', 0)
            company_name = info.get('shortName', symbol)
        except Exception:
            sector = 'Unknown'
            market_cap = 0
            company_name = symbol

        return {
            'symbol': symbol,
            'company_name': company_name,
            'sector': sector,
            'market_cap': market_cap,
            'current_price': current_price,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'target1': target1,
            'target2': target2,
            'target3': target3,
            'catalyst_score': catalyst_info['score'],
            'catalyst_date': catalyst_info['date'],
            'catalyst_price': catalyst_info['price'],
            'volume_ratio': catalyst_info['volume_ratio'],
            'pullback_pct': pullback_info['pullback_pct'],
            'rsi': rsi,
            'days_since_catalyst': catalyst_info['days_ago'],
            'signal_type': 'PULLBACK_CATALYST',
            'risk_reward': (target2 - entry_price) / (entry_price - stop_loss) if entry_price > stop_loss else 0,
            'recommendation': self._get_recommendation(catalyst_info['score'], pullback_info['pullback_pct'], rsi),
        }

    def _detect_catalyst(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
        min_volume_ratio: float,
        min_catalyst_score: float,
        lookback_days: int,
    ) -> dict | None:
        """Detect if there was a catalyst event in recent days"""

        # Check last N days for catalyst
        for days_ago in range(1, lookback_days + 1):
            idx = -1 - days_ago

            if abs(idx) >= len(closes) - 20:
                continue

            # Volume ratio
            vol_avg = np.mean(volumes[idx-20:idx])
            vol_ratio = volumes[idx] / vol_avg if vol_avg > 0 else 1

            if vol_ratio < min_volume_ratio:
                continue

            # Calculate catalyst score
            score = 0

            # Volume score
            if vol_ratio > 4:
                score += 40
            elif vol_ratio > 3:
                score += 32
            elif vol_ratio > 2:
                score += 24
            else:
                score += 18

            # Breakout score
            recent_high = max(closes[idx-20:idx])
            if closes[idx] > recent_high * 1.025:
                score += 32
            elif closes[idx] > recent_high * 1.01:
                score += 22
            elif closes[idx] > recent_high:
                score += 12

            # Momentum score
            if idx > -len(closes):
                mom_1d = (closes[idx] / closes[idx-1] - 1) * 100
                if mom_1d > 5:
                    score += 28
                elif mom_1d > 3.5:
                    score += 20
                elif mom_1d > 2:
                    score += 12

            if score >= min_catalyst_score:
                return {
                    'score': score,
                    'date': datetime.now() - timedelta(days=days_ago),
                    'price': closes[idx],
                    'volume_ratio': vol_ratio,
                    'days_ago': days_ago,
                }

        return None

    def _check_pullback(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        catalyst_info: dict,
    ) -> dict:
        """Check if stock is pulling back to support"""

        current_price = closes[-1]
        catalyst_price = catalyst_info['price']

        # Calculate support levels
        ma10 = np.mean(closes[-10:])

        # ATR for support calculation
        tr = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1]))
              for j in range(-14, 0)]
        atr = np.mean(tr)

        # Pullback target
        pullback_target = max(ma10, catalyst_price - atr * 1.25)

        # Check if currently at or near pullback target
        pullback_pct = (current_price / catalyst_price - 1) * 100

        is_pullback = (
            current_price <= pullback_target * 1.02 and  # Near support
            current_price >= catalyst_price * 0.88       # Not dropped too much
        )

        return {
            'is_pullback': is_pullback,
            'entry_target': min(current_price, pullback_target),
            'pullback_pct': pullback_pct,
            'ma10': ma10,
            'atr': atr,
        }

    def _calculate_rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calculate RSI"""
        if len(closes) < period + 1:
            return 50

        deltas = np.diff(closes[-period-1:])
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _get_recommendation(self, catalyst_score: float, pullback_pct: float, rsi: float) -> str:
        """Generate recommendation based on signals"""

        if catalyst_score >= 70 and pullback_pct <= -3 and rsi < 60:
            return "STRONG BUY - High conviction pullback"
        elif catalyst_score >= 55 and pullback_pct <= -2 and rsi < 65:
            return "BUY - Good pullback entry"
        elif catalyst_score >= 45 and pullback_pct <= -1:
            return "CONSIDER - Watch for better entry"
        else:
            return "MONITOR - Wait for deeper pullback"
