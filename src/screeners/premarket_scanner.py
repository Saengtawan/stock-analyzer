#!/usr/bin/env python3
"""
Pre-market Gap Scanner
Find Gap Up stocks before market open (7:00-9:30 AM ET) ready to buy at 9:30 AM
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ai_universe_generator import AIUniverseGenerator


class PremarketScanner:
    """Scanner for pre-market gap opportunities (Yahoo Finance only - 100% FREE)"""

    def __init__(self, yahoo_finance_client):
        """
        Initialize pre-market scanner

        Args:
            yahoo_finance_client: YahooFinanceClient instance
        """
        self.client = yahoo_finance_client
        self.ai_generator = AIUniverseGenerator()
        logger.info("✅ Pre-market scanner initialized (FREE - Yahoo Finance + Smart Indicators)")

    def scan_premarket_opportunities(self,
                                    min_gap_pct: float = 2.0,
                                    max_gap_pct: float = 4.0,
                                    min_volume_ratio: float = 3.0,
                                    min_price: float = 5.0,
                                    market_caps: List[str] = ['large', 'mid'],
                                    prioritize_tech: bool = True,
                                    max_stocks: int = 20,
                                    demo_mode: bool = False) -> List[Dict[str, Any]]:
        """
        Scan for pre-market gap up opportunities

        Args:
            min_gap_pct: Minimum gap percentage (default 2.0% - Sweet Spot Start)
            max_gap_pct: Maximum gap percentage (default 4.0% - Moderate Range)
            min_volume_ratio: Minimum pre-market volume vs average (default 3x)
            min_price: Minimum stock price to filter penny stocks (default $5)
            market_caps: List of market cap categories ['large', 'mid', 'small']
            prioritize_tech: Prioritize technology sector
            max_stocks: Maximum number of opportunities to return
            demo_mode: If True, ignore volume requirements (for testing outside pre-market hours)

        Returns:
            List of pre-market opportunities sorted by gap quality score

        NOTE: Gap 2-3% = 41% trap rate (best), Gap 3-4% = ~50% trap, Gap 4-5% = 64% trap
        """
        # Check if market is in pre-market session
        market_status = self.client.is_market_open()
        market_state = market_status.get('market_state', 'UNKNOWN')

        # Auto-enable demo mode if not in pre-market hours
        if market_state != 'PRE':
            if not demo_mode:
                logger.warning(f"Market is not in PRE-MARKET state (current: {market_state}). Using Smart Filter Mode.")
                demo_mode = True
            else:
                logger.info(f"Smart Filter Mode - using alternative quality indicators")

        # IMPORTANT: Yahoo Finance free API doesn't provide pre-market volume
        # Always use "Smart Filter Mode" which uses alternative indicators
        if not demo_mode and market_state == 'PRE':
            logger.info("Pre-market hours detected. Using Smart Filter Mode (volume unavailable from free APIs).")
            logger.info("📊 Using: Gap Quality + Price Momentum + Yesterday Volume + Sector/Float filters")
            demo_mode = True

        if demo_mode:
            logger.info(f"🔍 Starting pre-market gap scan in SMART FILTER MODE (min_gap={min_gap_pct}%)")
            logger.info(f"📊 Quality filters: Gap Quality + Price Momentum + Yesterday Volume + Smart Scoring")
        else:
            logger.info(f"🔍 Starting pre-market gap scan (min_gap={min_gap_pct}%, min_volume={min_volume_ratio}x)")

        # Generate AI-powered stock universe
        if not self.ai_generator:
            raise ValueError("AI universe generator not initialized")

        logger.info("🤖 Generating AI-powered pre-market universe...")
        criteria = {
            'min_gap_pct': min_gap_pct,
            'market_caps': market_caps,
            'prioritize_tech': prioritize_tech,
            'max_stocks': max_stocks
        }
        stock_universe = self.ai_generator.generate_premarket_universe(criteria)
        logger.info(f"✅ Generated {len(stock_universe)} AI-selected symbols")

        opportunities = []

        # Parallel processing with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=16) as executor:
            future_to_symbol = {
                executor.submit(self._analyze_premarket_stock, symbol, min_gap_pct, min_volume_ratio, min_price, demo_mode): symbol
                for symbol in stock_universe
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        opportunities.append(result)
                        logger.info(f"✅ {symbol}: Gap {result['gap_percent']:.2f}%, Score {result['gap_score']:.1f}/10")
                    else:
                        logger.debug(f"❌ {symbol}: Did not meet gap criteria")

                except Exception as e:
                    logger.warning(f"⚠️  {symbol}: Analysis failed - {e}")
                    continue

        # Filter by criteria (v8.0 - ADDED MAX GAP!)
        if demo_mode:
            # In demo mode, only filter by gap % (ignore volume)
            filtered_opportunities = [
                opp for opp in opportunities
                if min_gap_pct <= opp['gap_percent'] <= max_gap_pct and
                   opp['gap_direction'] == 'up'
            ]
        else:
            # Normal mode: filter by both gap and volume
            filtered_opportunities = [
                opp for opp in opportunities
                if min_gap_pct <= opp['gap_percent'] <= max_gap_pct and
                   opp['gap_direction'] == 'up' and
                   opp['volume_ratio'] >= min_volume_ratio
            ]

        # Sort by trade_confidence (highest first) - NEW smart sorting!
        filtered_opportunities.sort(key=lambda x: x.get('trade_confidence', 0), reverse=True)

        # No fallback - if no stocks meet criteria, return empty results
        if len(filtered_opportunities) == 0:
            logger.warning(f"⚠️  No stocks meet criteria (Gap {min_gap_pct}%-{max_gap_pct}%) - Try adjusting the gap range")
        else:
            logger.info(f"✅ Found {len(filtered_opportunities)} pre-market gap opportunities")

        # Return both opportunities and demo_mode status
        return {
            'opportunities': filtered_opportunities[:max_stocks],
            'demo_mode': demo_mode,
            'market_state': market_state
        }

    def _analyze_premarket_stock(self,
                                 symbol: str,
                                 min_gap_pct: float,
                                 min_volume_ratio: float,
                                 min_price: float,
                                 demo_mode: bool = False) -> Optional[Dict[str, Any]]:
        """
        Analyze individual stock for pre-market gap opportunity

        Returns:
            Dictionary with gap analysis or None if doesn't meet criteria
        """
        try:
            # Get pre-market data
            pm_data = self.client.get_premarket_data(symbol, interval="5m")

            if not pm_data.get('has_premarket_data', False):
                return None

            # Extract key metrics
            gap_percent = pm_data['gap_percent']
            gap_direction = pm_data['gap_direction']
            current_price = pm_data['current_premarket_price']
            previous_close = pm_data['previous_close']
            premarket_volume = pm_data['premarket_volume']
            premarket_high = pm_data['premarket_high']
            premarket_low = pm_data['premarket_low']

            # HARD FILTER: Reject penny stocks below minimum price
            if current_price < min_price:
                logger.debug(f"❌ {symbol}: Price ${current_price:.2f} below minimum ${min_price:.2f}")
                return None

            # Quick filter: Must be gap up (keep all gap-up stocks for fallback logic)
            if gap_direction != 'up':
                return None

            # Get company info for market cap, sector, and additional factors
            try:
                company_info = self.client.get_company_info(symbol)
                market_cap = company_info.get('market_cap', 0)
                sector = company_info.get('sector', 'Unknown')
                float_shares = company_info.get('float_shares', 0)
                short_percent = company_info.get('short_percent_of_float', 0)
                beta = company_info.get('beta', 1.0)
                shares_outstanding = company_info.get('shares_outstanding', 0)
                earnings_date = company_info.get('earnings_date', None)
            except:
                market_cap = 0
                sector = 'Unknown'
                float_shares = 0
                short_percent = 0
                beta = 1.0
                shares_outstanding = 0
                earnings_date = None

            # Get average volume for ratio calculation
            avg_volume_5min = self.client.get_average_volume(symbol, days=20)

            # Get yesterday's total volume (alternative indicator since PM volume unavailable)
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                hist_data = ticker.history(period="5d", interval="1d", prepost=False)
                if not hist_data.empty and len(hist_data) >= 1:
                    yesterday_volume = int(hist_data['Volume'].iloc[-1])
                    avg_daily_volume = int(avg_volume_5min * 78) if avg_volume_5min > 0 else 0  # 78 bars in regular session
                    yesterday_volume_ratio = yesterday_volume / avg_daily_volume if avg_daily_volume > 0 else 1.0
                else:
                    yesterday_volume = 0
                    yesterday_volume_ratio = 1.0
            except Exception as e:
                logger.debug(f"Failed to get yesterday volume for {symbol}: {e}")
                yesterday_volume = 0
                yesterday_volume_ratio = 1.0

            # Calculate volume ratio (PM volume - but will be 0 from Yahoo Finance)
            # Pre-market has ~66 bars (5min intervals from 4:00-9:30 AM)
            # Compare total pre-market volume to equivalent regular hour volume
            if avg_volume_5min > 0:
                expected_volume = avg_volume_5min * 66  # 66 five-minute bars
                volume_ratio = premarket_volume / expected_volume if expected_volume > 0 else 0
            else:
                volume_ratio = 0

            # Since PM volume is 0, use yesterday's volume ratio as proxy
            if volume_ratio == 0 and yesterday_volume_ratio > 0:
                volume_ratio = yesterday_volume_ratio  # Use yesterday's activity as indicator

            # Note: Volume filtering is done later to allow fallback logic to work
            # (removed early filter to keep all gap-up stocks for fallback)

            # Calculate float percentage (smaller float = more volatile)
            float_percent = (float_shares / shares_outstanding * 100) if shares_outstanding > 0 else 100

            # Calculate gap quality score (0-10 scale)
            gap_score = self._calculate_gap_score(
                gap_percent=gap_percent,
                volume_ratio=volume_ratio,
                market_cap=market_cap,
                sector=sector,
                premarket_bars=pm_data['premarket_bars'],
                current_price=current_price,
                premarket_high=premarket_high,
                premarket_low=premarket_low,
                float_shares=float_shares,
                short_percent=short_percent or 0,
                beta=beta or 1.0,
                float_percent=float_percent,
                earnings_date=earnings_date,
                previous_close=previous_close
            )

            # Calculate risk indicators
            risk_indicators = self._calculate_risk_indicators(
                pm_data['premarket_bars'],
                current_price,
                premarket_high,
                premarket_low,
                previous_close,
                gap_percent=gap_percent,
                earnings_date=earnings_date
            )

            # Categorize market cap
            if market_cap >= 10_000_000_000:
                market_cap_category = 'Large Cap'
            elif market_cap >= 2_000_000_000:
                market_cap_category = 'Mid Cap'
            elif market_cap >= 300_000_000:
                market_cap_category = 'Small Cap'
            else:
                market_cap_category = 'Micro Cap'

            # Calculate consistency ratio (% of positive bars)
            consistency_ratio = None
            premarket_bars = pm_data['premarket_bars']
            if not premarket_bars.empty:
                price_changes = premarket_bars['close'].pct_change().dropna()
                if len(price_changes) > 0:
                    positive_bars = (price_changes > 0).sum()
                    consistency_ratio = positive_bars / len(price_changes)

            # Calculate trade confidence (0-100 scale for easy visual)
            trade_confidence = self._calculate_trade_confidence(
                gap_score=gap_score,
                gap_percent=gap_percent,
                risk_indicators=risk_indicators,
                volume_ratio=volume_ratio,
                current_price=current_price,
                premarket_high=premarket_high,
                premarket_low=premarket_low,
                consistency_ratio=consistency_ratio
            )

            return {
                'symbol': symbol,
                'current_price': current_price,
                'previous_close': previous_close,
                'gap_amount': current_price - previous_close,
                'gap_percent': gap_percent,
                'gap_direction': gap_direction,
                'premarket_volume': premarket_volume,
                'volume_ratio': volume_ratio,
                'yesterday_volume': yesterday_volume,  # NEW: Yesterday's volume
                'yesterday_volume_ratio': yesterday_volume_ratio,  # NEW: Yesterday vs avg
                'premarket_high': premarket_high,
                'premarket_low': premarket_low,
                'gap_score': gap_score,
                'trade_confidence': trade_confidence,
                'market_cap': market_cap,
                'market_cap_category': market_cap_category,
                'sector': sector,
                'risk_indicators': risk_indicators,
                'recommendation': self._generate_recommendation(gap_score, risk_indicators),
                'analysis_date': datetime.now().isoformat(),
                'is_etf': False,  # Can enhance to detect ETFs

                # Additional scoring factors
                'float_shares': float_shares,
                'float_percent': float_percent,
                'short_percent': short_percent or 0,
                'beta': beta or 1.0,
            }

        except Exception as e:
            logger.error(f"Failed to analyze pre-market for {symbol}: {e}")
            return None

    def _calculate_gap_score(self,
                            gap_percent: float,
                            volume_ratio: float,
                            market_cap: float,
                            sector: str,
                            premarket_bars: pd.DataFrame,
                            current_price: float,
                            premarket_high: float,
                            premarket_low: float,
                            float_shares: float,
                            short_percent: float,
                            beta: float,
                            float_percent: float,
                            earnings_date=None,
                            previous_close: float = 0) -> float:
        """
        REVISED gap quality score based on backtest findings (0-10 scale)

        v7.0 UPDATE (2025-12-17 Backtest):
        - Gap 2-3%: 41% trap rate (BEST!)
        - Gap 3-5%: 63% trap rate (WORST!)
        - Gap 5-7%: 47% trap rate
        - Gap 7%+: 50% trap rate

        Scoring factors (total 10 points):
        - Gap SIZE (15%): INVERTED - 2-3% scores highest → 1.5 pts, 3-5% heavily penalized
        - Gap QUALITY (25%): Earnings/news detection, penalize 3-5% → 2.5 pts
        - Price consistency (25%): Steady climb vs volatile chop → 2.5 pts
        - Volume ratio (20%): Higher volume = stronger conviction → 2.0 pts
        - Float analysis (10%): Smaller float = higher volatility → 1.0 pt
        - Other factors (5%): Market cap, sector, beta → 0.5 pts
        """
        score = 0.0

        # 1. Gap SIZE score (0-1.5 points) - INVERTED LOGIC! (v8.0 UPDATED)
        # BACKTEST v8.0 (2025-12-18): Gap 2-3% = 41% trap, Gap 3-4% = ~50% trap, Gap 4-5% = 64% trap
        # Sweet spot: 2-3% gaps score highest, 3-4% moderate, 4-5%+ is WORST!
        if gap_percent >= 15:
            gap_size_score = 0.2  # Very risky - likely news/earnings fade
        elif gap_percent >= 10:
            gap_size_score = 0.3  # High risk - extreme sentiment
        elif gap_percent >= 7:
            gap_size_score = 0.5  # Still risky (50% trap rate)
        elif gap_percent >= 5:
            gap_size_score = 0.6  # Still risky (47% trap rate)
        elif gap_percent >= 4:
            gap_size_score = 0.4  # High risk - 64% gap trap rate
        elif gap_percent >= 3:
            gap_size_score = 1.0  # MODERATE - acceptable (~50% trap rate)
        elif gap_percent >= 2:
            gap_size_score = 1.5  # SWEET SPOT - best win rate (41% trap)
        else:  # < 2%
            gap_size_score = 0.8  # Too small - may not have enough momentum

        score += gap_size_score

        # 2. Gap QUALITY score (0-2.5 points) - NEW FACTOR!
        # Distinguish earnings/news gaps (fade) from momentum gaps (continue)
        gap_quality_score = 2.5  # Start with max, then reduce for red flags

        # RED FLAG: Earnings within 7 days (massive penalty)
        if earnings_date:
            from datetime import datetime, timezone
            try:
                now = datetime.now(timezone.utc)
                if hasattr(earnings_date, 'replace'):
                    ed = earnings_date.replace(tzinfo=timezone.utc) if earnings_date.tzinfo is None else earnings_date
                else:
                    ed = earnings_date

                days_to_earnings = abs((ed - now).days)

                if days_to_earnings <= 1:  # Today or tomorrow
                    gap_quality_score *= 0.2  # Reduce by 80% - earnings gaps almost always fade
                elif days_to_earnings <= 3:
                    gap_quality_score *= 0.5  # Reduce by 50%
                elif days_to_earnings <= 7:
                    gap_quality_score *= 0.7  # Reduce by 30%
            except:
                pass  # Keep full score if can't calculate

        # RED FLAG: Extreme gap size indicates news event (v8.0 UPDATED)
        if gap_percent >= 10:
            gap_quality_score *= 0.3  # Likely news-driven, will fade
        elif gap_percent >= 7:
            gap_quality_score *= 0.5  # High risk
        elif gap_percent >= 5:
            gap_quality_score *= 0.6  # Still risky
        elif gap_percent >= 4:
            gap_quality_score *= 0.5  # High risk - 64% trap rate
        elif gap_percent >= 3:
            gap_quality_score *= 0.75  # MODERATE - acceptable (~50% trap rate)

        # GREEN FLAG: Gap in sweet spot with volume
        if 2 <= gap_percent <= 3 and volume_ratio >= 3:
            gap_quality_score = min(2.5, gap_quality_score * 1.5)  # Bigger bonus for ideal setup
        elif 3 < gap_percent <= 4 and volume_ratio >= 3:
            gap_quality_score = min(2.5, gap_quality_score * 1.2)  # Moderate bonus for 3-4% range

        score += gap_quality_score

        # 3. Volume ratio score (0-2.0 points)
        # IMPORTANT: If volume is 0 (data unavailable), give neutral score instead of penalty
        if volume_ratio > 0:
            # 2x = 1.0, 3x = 1.5, 5x = 2.0, 8x+ = 2.0
            volume_score = min(2.0, (volume_ratio / 4.0) * 2.0)
        else:
            # Volume data unavailable - give neutral score (not penalty)
            volume_score = 1.0  # Neutral score
        score += volume_score

        # 4. Price action consistency score (0-2.5 points) - INCREASED!
        if not premarket_bars.empty:
            # Calculate price momentum consistency
            price_changes = premarket_bars['close'].pct_change().dropna()
            positive_bars = (price_changes > 0).sum()
            total_bars = len(price_changes)

            if total_bars > 0:
                consistency_ratio = positive_bars / total_bars
                # IMPROVED: Better scoring for consistency
                # 80%+ positive bars = 2.5, 60% = 1.6, 50% = 1.0, <50% = 0.5
                if consistency_ratio >= 0.8:
                    consistency_score = 2.5  # INCREASED to max
                elif consistency_ratio >= 0.6:
                    consistency_score = 1.6  # INCREASED
                elif consistency_ratio >= 0.5:
                    consistency_score = 1.0  # INCREASED
                else:
                    consistency_score = 0.5
            else:
                consistency_score = 1.0

            # Check if price is near pre-market high (strength indicator)
            if premarket_high > premarket_low:
                price_position = (current_price - premarket_low) / (premarket_high - premarket_low)
                if price_position >= 0.9:  # Within top 10% of range
                    consistency_score *= 1.3  # Bonus for strength
                elif price_position >= 0.7:  # Upper half
                    consistency_score *= 1.15
                elif price_position <= 0.5:  # Below midpoint
                    consistency_score *= 0.7  # Penalty for weakness

            score += min(2.5, consistency_score)  # INCREASED max to 2.5
        else:
            score += 1.0  # Neutral if no bars

        # 5. Float analysis score (0-1.0 point) - REDUCED from 1.5!
        # Smaller float = more volatile = higher potential
        if float_shares > 0:
            float_millions = float_shares / 1_000_000

            # Scaled down from previous version
            if 25 <= float_millions <= 100:
                float_score = 1.0  # Ideal range for gap moves
            elif 15 <= float_millions < 25:
                float_score = 0.9  # Very small float - high volatility
            elif 100 < float_millions <= 200:
                float_score = 0.8
            elif 200 < float_millions <= 500:
                float_score = 0.6  # Large cap stocks
            elif 500 < float_millions <= 1000:
                float_score = 0.5  # Very large float
            elif float_millions < 15:
                float_score = 0.5  # Too small - risky, illiquid
            else:  # > 1000M
                float_score = 0.3  # Mega cap - very hard to move

            score += float_score
        else:
            # Estimate from market cap if float missing
            if market_cap > 0:
                estimated_float_score = 0.5  # Neutral assumption
                score += estimated_float_score
            else:
                score += 0.5  # Neutral if no data

        # 6. Other factors bonus (0-0.5 point total) - COMBINED & REDUCED!
        # Market cap, sector, beta, short interest all combined into small bonus
        other_bonus = 0.0

        # Market cap (max 0.2)
        if market_cap >= 10_000_000_000:  # Large cap $10B+
            other_bonus += 0.2
        elif market_cap >= 2_000_000_000:  # Mid cap $2B+
            other_bonus += 0.15
        elif market_cap >= 300_000_000:  # Small cap $300M+
            other_bonus += 0.1

        # Sector (max 0.15)
        if sector and 'Technology' in sector:
            other_bonus += 0.15
        elif sector and sector in ['Healthcare', 'Consumer Cyclical', 'Communication Services']:
            other_bonus += 0.08

        # Beta (max 0.1)
        if beta and beta > 0:
            if beta >= 1.5:
                other_bonus += 0.1  # High beta
            elif beta >= 1.2:
                other_bonus += 0.05  # Moderate beta

        # Short interest (max 0.05) - minimal weight, data often missing
        if short_percent and short_percent > 0:
            short_pct = short_percent * 100 if short_percent < 1 else short_percent
            if short_pct >= 20:
                other_bonus += 0.05
            elif short_pct >= 10:
                other_bonus += 0.03

        score += min(0.5, other_bonus)

        # Normalize to 0-10 scale
        return round(min(10.0, score), 1)

    def _calculate_risk_indicators(self,
                                   premarket_bars: pd.DataFrame,
                                   current_price: float,
                                   premarket_high: float,
                                   premarket_low: float,
                                   previous_close: float,
                                   gap_percent: float = 0,
                                   earnings_date=None) -> Dict[str, Any]:
        """
        IMPROVED risk indicators based on backtest findings (v8.0)

        CRITICAL INSIGHT: Gap size matters!
        - Gaps 2-3%: Best success rate (59% win, 41% trap)
        - Gaps 3-4%: Moderate (expect ~50% trap rate)
        - Gaps 4-5%: High risk (64% trap rate)
        - Gaps >5%: Very high fade risk

        Returns:
            Dictionary with risk metrics
        """
        risk_indicators = {
            'gap_and_trap_risk': 'Low',
            'false_breakout_risk': 'Low',
            'volatility_risk': 'Low',
            'fade_probability': 'Low',
            'gap_size_risk': 'Low',  # NEW!
            'earnings_risk': 'Low'   # NEW!
        }

        # NEW: Gap size risk (CRITICAL - based on backtest v8.0)
        if gap_percent >= 15:
            risk_indicators['gap_size_risk'] = 'Extreme'
            risk_indicators['fade_probability'] = 'Extreme'
        elif gap_percent >= 10:
            risk_indicators['gap_size_risk'] = 'High'
            risk_indicators['fade_probability'] = 'High'
        elif gap_percent >= 7:
            risk_indicators['gap_size_risk'] = 'Moderate-High'
            risk_indicators['fade_probability'] = 'Moderate-High'
        elif gap_percent >= 5:
            risk_indicators['gap_size_risk'] = 'Moderate'
            risk_indicators['fade_probability'] = 'Moderate'
        elif gap_percent >= 4:
            risk_indicators['gap_size_risk'] = 'Moderate'
            risk_indicators['fade_probability'] = 'Moderate'

        # NEW: Earnings risk
        if earnings_date:
            from datetime import datetime, timezone
            try:
                now = datetime.now(timezone.utc)
                if hasattr(earnings_date, 'replace'):
                    ed = earnings_date.replace(tzinfo=timezone.utc) if earnings_date.tzinfo is None else earnings_date
                else:
                    ed = earnings_date

                days_to_earnings = abs((ed - now).days)

                if days_to_earnings <= 1:
                    risk_indicators['earnings_risk'] = 'Extreme'
                    risk_indicators['fade_probability'] = 'Extreme'
                elif days_to_earnings <= 3:
                    risk_indicators['earnings_risk'] = 'High'
                    if risk_indicators['fade_probability'] == 'Low':
                        risk_indicators['fade_probability'] = 'High'
                elif days_to_earnings <= 7:
                    risk_indicators['earnings_risk'] = 'Moderate'
            except:
                pass

        if premarket_bars.empty:
            return risk_indicators

        # 1. Gap & Trap detection (rapid fade from high)
        if premarket_high > 0:
            fade_from_high = (premarket_high - current_price) / premarket_high * 100
            if fade_from_high > 3.0:  # Faded >3% from high
                risk_indicators['gap_and_trap_risk'] = 'High'
                # Upgrade fade probability if not already higher
                if risk_indicators['fade_probability'] in ['Low', 'Moderate']:
                    risk_indicators['fade_probability'] = 'High'
            elif fade_from_high > 1.5:
                risk_indicators['gap_and_trap_risk'] = 'Moderate'
                if risk_indicators['fade_probability'] == 'Low':
                    risk_indicators['fade_probability'] = 'Moderate'

        # 2. False breakout detection (choppy price action)
        price_range = premarket_high - premarket_low
        avg_price = (premarket_high + premarket_low) / 2
        if avg_price > 0:
            volatility_pct = (price_range / avg_price) * 100
            if volatility_pct > 5.0:
                risk_indicators['volatility_risk'] = 'High'
            elif volatility_pct > 3.0:
                risk_indicators['volatility_risk'] = 'Moderate'

        # 3. Reversal pattern detection
        if len(premarket_bars) >= 5:
            recent_closes = premarket_bars['close'].tail(5).values
            # Check if last 3 bars are declining
            if len(recent_closes) >= 3:
                if recent_closes[-1] < recent_closes[-2] < recent_closes[-3]:
                    risk_indicators['false_breakout_risk'] = 'High'
                    if risk_indicators['fade_probability'] in ['Low', 'Moderate']:
                        risk_indicators['fade_probability'] = 'High'

        return risk_indicators

    def _generate_recommendation(self,
                                gap_score: float,
                                risk_indicators: Dict[str, Any]) -> str:
        """
        Generate trading recommendation based on gap score and risk

        Returns:
            Recommendation string: 'Strong Buy', 'Buy', 'Hold', 'Caution'
        """
        # Check for high-risk conditions
        high_risk_count = sum([
            1 for v in risk_indicators.values()
            if v == 'High'
        ])

        if high_risk_count >= 2:
            return 'Caution'

        if gap_score >= 8.0 and high_risk_count == 0:
            return 'Strong Buy'
        elif gap_score >= 6.5 and high_risk_count <= 1:
            return 'Buy'
        elif gap_score >= 5.0:
            return 'Hold'
        else:
            return 'Caution'

    def _calculate_trade_confidence(self,
                                   gap_score: float,
                                   gap_percent: float,
                                   risk_indicators: Dict[str, Any],
                                   volume_ratio: float,
                                   current_price: float,
                                   premarket_high: float,
                                   premarket_low: float,
                                   consistency_ratio: float = None) -> int:
        """
        Calculate trade confidence score (0-100) for easy visual ranking

        BACKTEST VALIDATED RANGES (v7.0 - 2025-12-17):
        - 70-79: BEST RANGE - 60% win rate, 40% gap trap rate
        - 60-69: MODERATE - 51% win rate, 49% gap trap rate
        - <60: AVOID - High gap trap rates (65%+)

        KEY IMPROVEMENTS (v7.0 - Based on 60-day backtest):
        1. HEAVY penalty for gap 3-5% (-25) - 63% gap trap rate proven!
        2. HEAVY penalty for price $15-50 (-20) - 78% gap trap rate proven!
        3. Increased bonus for gap 2-3% (+15) - 41% gap trap rate (best)
        4. Penalizes very high consistency (>95%) as overbought warning
        5. Price risk penalty for low-priced stocks ($5-15 range)

        Returns:
            Integer confidence score 0-100
        """
        confidence = 50  # Start at 50

        # Factor 1: Gap Score (max +25)
        confidence += (gap_score - 5.0) * 5  # Scale from gap_score 5-10

        # Factor 2: Gap Size Sweet Spot (max +15, IMPROVED v8.0)
        # BACKTEST FINDING (2025-12-18): Gap 2-3% = 41% trap, Gap 3-4% = ~50% trap, Gap 4-5% = 64% trap
        # Expanded to 2-4% range for more opportunities with moderate risk
        if 2.0 <= gap_percent <= 3.0:
            confidence += 15  # SWEET SPOT - best win rate (41% trap rate)
        elif 3.0 < gap_percent <= 4.0:
            confidence += 5   # MODERATE - acceptable (~50% trap rate)
        elif 1.5 <= gap_percent < 2.0:
            confidence += 3   # Too small but okay
        elif 4.0 < gap_percent <= 5.0:
            confidence -= 20  # HIGH RISK - 64% gap trap rate
        elif 5.0 < gap_percent <= 7.0:
            confidence -= 15  # Still risky (47% trap rate)
        elif gap_percent > 7.0:
            confidence -= 20  # Very high fade risk (50% trap rate)

        # Factor 3: Risk Indicators (max -30)
        high_risk_count = sum(1 for v in risk_indicators.values() if v in ['High', 'Extreme'])
        moderate_risk_count = sum(1 for v in risk_indicators.values() if v in ['Moderate', 'Moderate-High'])
        confidence -= high_risk_count * 10
        confidence -= moderate_risk_count * 5

        # Factor 4: Price Position (max +10)
        if premarket_high > premarket_low:
            price_position = (current_price - premarket_low) / (premarket_high - premarket_low)
            if price_position >= 0.85:  # Near high
                confidence += 10
            elif price_position >= 0.70:
                confidence += 5
            elif price_position <= 0.30:  # Near low - weak
                confidence -= 10

        # Factor 5: Volume (max +10)
        # IMPORTANT: If volume is 0 (data unavailable), don't penalize
        if volume_ratio > 0:
            if volume_ratio >= 5:
                confidence += 10
            elif volume_ratio >= 3:
                confidence += 5
            elif volume_ratio < 2:
                confidence -= 5
        # else: volume_ratio == 0, no bonus/penalty (neutral)

        # Factor 6: Price Action Consistency (max +10, penalty up to -30, IMPROVED v6.0)
        # CRITICAL FIX: Very high consistency (>95%) = OVERBOUGHT = REVERSAL RISK!
        # BACKTEST FINDING: All 4 trades with 100% consistency FAILED (0% win rate)
        # This occurs when stock has 5+ consecutive up days = likely due for pullback
        if consistency_ratio is not None:
            if consistency_ratio >= 0.95:  # 95%+ positive bars
                confidence -= 5   # OVERBOUGHT WARNING (was +15!)
            elif consistency_ratio >= 0.8:  # 80-95% positive
                confidence += 8   # Good momentum (reduced from +15)
            elif consistency_ratio >= 0.6:  # 60-80% positive
                confidence += 10  # SWEET SPOT - strong but not overbought
            elif consistency_ratio >= 0.5:  # 50-60% positive
                confidence += 5   # Moderate momentum
            elif consistency_ratio >= 0.4:  # 40-50% positive
                confidence += 0   # Neutral - mixed action
            elif consistency_ratio >= 0.3:  # 30-40% positive
                confidence -= 15  # WEAK - mostly down bars
            else:  # < 30% positive
                confidence -= 30  # VERY WEAK - strong down pressure

        # Factor 7: Price Risk Penalty (v8.0 - REMOVED $15-50 penalty!)
        # Only penalize very low prices (< $15)
        if current_price < 10:  # $5-10 range
            confidence -= 10  # Higher risk - wider spreads, more volatile
        elif current_price < 15:  # $10-15 range
            confidence -= 5   # Moderate risk
        # REMOVED: $15-50 penalty (based on only 8 stocks - insufficient data!)

        # Clamp to 0-100 range
        return max(0, min(100, int(confidence)))
