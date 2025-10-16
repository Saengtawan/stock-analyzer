#!/usr/bin/env python3
"""
Support Level Stock Screener
หาหุ้นที่อยู่ใกล้หรือต่ำกว่าแนวรับและน่าลงทุน
"""

import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_universe_generator import AIUniverseGenerator

class SupportLevelScreener:
    """Screen stocks near or below support levels with good fundamentals"""

    def __init__(self, stock_analyzer):
        """
        Initialize screener

        Args:
            stock_analyzer: StockAnalyzer instance
        """
        self.analyzer = stock_analyzer
        self.ai_generator = AIUniverseGenerator()

        # AI-only universe generation - no fallback needed
        logger.info("Support level screener initialized with AI-only universe generation")

    def screen_support_opportunities(self,
                                   max_distance_from_support: float = 0.05,  # 5% below support
                                   min_fundamental_score: float = 5.0,
                                   min_technical_score: float = 4.0,
                                   min_momentum_score: float = 5.0,  # Minimum momentum score
                                   max_stocks: int = 10,
                                   time_horizon: str = 'medium',
) -> List[Dict[str, Any]]:
        """
        Screen for stocks near support levels with good opportunities

        Args:
            max_distance_from_support: Maximum distance below support (as percentage)
            min_fundamental_score: Minimum fundamental score required
            min_technical_score: Minimum technical score required
            min_momentum_score: Minimum momentum score required (0-10 scale, default 5.0)
            max_stocks: Maximum number of stocks to return
            time_horizon: Investment time horizon

        Returns:
            List of stock opportunities sorted by attractiveness
        """
        # Always use AI universe generation - no fallback
        if not self.ai_generator:
            raise ValueError("AI universe generator not initialized. Cannot proceed without AI.")

        print("🤖 Generating AI-powered support level universe...")
        criteria = {
            'max_stocks': max_stocks,
            'time_horizon': time_horizon,
            'max_distance_from_support': max_distance_from_support
        }
        stock_universe = self.ai_generator.generate_support_level_universe(criteria)
        print(f"✅ Generated {len(stock_universe)} AI-selected symbols")

        print(f"🔍 Screening {len(stock_universe)} stocks for support level opportunities...")

        opportunities = []

        # Use ThreadPoolExecutor for faster screening
        with ThreadPoolExecutor(max_workers=16) as executor:
            # Submit analysis tasks
            future_to_symbol = {
                executor.submit(self._analyze_stock_for_support, symbol, time_horizon): symbol
                for symbol in stock_universe
            }

            # Collect results
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        opportunities.append(result)
                        print(f"✅ {symbol}: Found opportunity")
                    else:
                        print(f"❌ {symbol}: No opportunity")

                except Exception as e:
                    print(f"⚠️  {symbol}: Analysis failed - {e}")
                    continue

        # Filter based on criteria
        filtered_opportunities = []
        for opp in opportunities:
            # Check distance from support
            distance_from_support = opp.get('distance_from_support', 1.0)
            if distance_from_support > max_distance_from_support:
                continue

            # Check fundamental score
            fundamental_score = opp.get('fundamental_score', 0)
            if fundamental_score < min_fundamental_score:
                continue

            # Check technical score
            technical_score = opp.get('technical_score', 0)
            if technical_score < min_technical_score:
                continue

            # Check momentum score
            momentum_score = opp.get('momentum_score', 5.0)
            if momentum_score < min_momentum_score:
                continue

            # Categorize by momentum tier
            if momentum_score >= 7.0:
                opp['momentum_tier'] = 'Strong'
            elif momentum_score >= 5.0:
                opp['momentum_tier'] = 'Moderate'
            else:
                opp['momentum_tier'] = 'Weak'

            filtered_opportunities.append(opp)

        # Sort by attractiveness score
        filtered_opportunities.sort(key=lambda x: x.get('attractiveness_score', 0), reverse=True)

        return filtered_opportunities[:max_stocks]

    def _analyze_stock_for_support(self, symbol: str, time_horizon: str) -> Optional[Dict[str, Any]]:
        """
        Analyze individual stock for support level opportunity using calculation-only approach

        Args:
            symbol: Stock symbol
            time_horizon: Investment time horizon

        Returns:
            Dictionary with opportunity details or None
        """
        try:
            # Use analysis without AI recommendations (for faster screening)
            results = self.analyzer.analyze_stock(symbol, time_horizon=time_horizon, account_value=100000, include_ai_analysis=False)

            if 'error' in results:
                return None

            # Check if this is an ETF
            is_etf = results.get('is_etf', False)

            current_price = results.get('current_price', 0)
            if not current_price:
                return None

            # Get technical analysis
            tech_analysis = results.get('technical_analysis', {})
            indicators = tech_analysis.get('indicators', {})
            support_resistance = indicators.get('support_resistance', {})

            support_1 = support_resistance.get('support_1', current_price)
            support_2 = support_resistance.get('support_2', current_price * 0.95)
            resistance_1 = support_resistance.get('resistance_1', current_price * 1.05)

            # Calculate distance from support
            distance_from_support = (current_price - support_1) / support_1 if support_1 > 0 else 1.0

            # Only consider stocks at or below support, or very close to it
            if distance_from_support > 0.02:  # More than 2% above support
                return None

            # Get scores
            fundamental_analysis = results.get('fundamental_analysis', {})
            fundamental_score = fundamental_analysis.get('overall_score', 0)

            technical_score = tech_analysis.get('technical_score', {}).get('total_score', 0)

            # Get other indicators
            rsi = indicators.get('rsi', 50)
            macd_line = indicators.get('macd_line', 0)

            # Get price_data for ATR and volume calculations
            price_data = results.get('price_data')

            # Initialize defaults
            atr_zones_data = {'zones': [], 'atr': 0, 'atr_percent': 0}
            volume_data = self._volume_placeholder()

            # Calculate ATR zones, relative volume, and momentum breakdown if price_data available
            momentum_data = None
            if price_data is not None and not price_data.empty:
                atr_zones_data = self._calculate_atr_zones(
                    price_data, current_price, support_1, resistance_1
                )
                volume_data = self._analyze_relative_volume(price_data)
                momentum_data = self._calculate_detailed_momentum(indicators, price_data)
            else:
                logger.warning(f"{symbol}: price_data not available, using defaults")

            # Calculate volume analysis (legacy format for attractiveness score)
            volume_analysis = self._analyze_volume_at_support(results)

            # Calculate attractiveness score
            attractiveness_score = self._calculate_attractiveness_score(
                distance_from_support, fundamental_score, technical_score,
                rsi, volume_analysis, current_price, support_1, resistance_1
            )

            # Get recommendation from AI results
            signal_analysis = results.get('signal_analysis', {})
            recommendation = signal_analysis.get('recommendation', {}).get('recommendation', 'HOLD')

            return {
                'symbol': symbol,
                'current_price': current_price,
                'support_1': support_1,
                'support_2': support_2,
                'resistance_1': resistance_1,
                'distance_from_support': distance_from_support,
                'distance_from_support_pct': distance_from_support * 100,
                'fundamental_score': fundamental_score,
                'technical_score': technical_score,
                'rsi': rsi,
                'macd_line': macd_line,
                'volume_analysis': volume_analysis,
                'attractiveness_score': attractiveness_score,
                'recommendation': recommendation,
                'risk_reward_ratio': (resistance_1 - current_price) / (current_price - support_2) if (current_price - support_2) > 0 else 0,
                'upside_to_resistance': ((resistance_1 - current_price) / current_price) * 100,
                'atr_zones': atr_zones_data['zones'],
                'atr': atr_zones_data['atr'],
                'atr_percent': atr_zones_data['atr_percent'],
                'relative_volume_data': volume_data,
                'momentum_breakdown': momentum_data,
                'momentum_score': momentum_data['overall_score'] if momentum_data else 5.0,
                'analysis_date': datetime.now().isoformat(),
                'is_etf': is_etf
            }

        except Exception as e:
            logger.warning(f"Analysis failed for {symbol}: {e}")
            return None

    def _analyze_relative_volume(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Comprehensive relative volume analysis

        Args:
            price_data: DataFrame with OHLC and Volume data

        Returns:
            Dictionary with volume analysis details
        """
        try:
            volume_col = self._get_column_name(price_data, ['Volume', 'volume', 'VOLUME'])
            close_col = self._get_column_name(price_data, ['Close', 'close', 'CLOSE', 'Adj Close'])

            if not volume_col or not close_col:
                return self._volume_placeholder()

            current_volume = price_data[volume_col].iloc[-1]
            avg_volume_20 = price_data[volume_col].rolling(20).mean().iloc[-1]
            avg_volume_50 = price_data[volume_col].rolling(50).mean().iloc[-1]

            # Relative Volume (current vs 20-day average)
            rel_volume = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1.0

            # Volume Trend (last 5 days)
            recent_volumes = price_data[volume_col].tail(5)
            if len(recent_volumes) >= 2:
                volume_trend_pct = ((recent_volumes.iloc[-1] - recent_volumes.iloc[0]) /
                                   recent_volumes.iloc[0] * 100) if recent_volumes.iloc[0] > 0 else 0
            else:
                volume_trend_pct = 0

            # Unusual Volume Alert
            unusual = rel_volume > 2.0

            # Volume-Price Correlation
            returns = price_data[close_col].pct_change()
            volume_changes = price_data[volume_col].pct_change()
            if len(returns) >= 20 and len(volume_changes) >= 20:
                correlation = returns.tail(20).corr(volume_changes.tail(20))
                correlation = correlation if not pd.isna(correlation) else 0
            else:
                correlation = 0

            # Scoring
            volume_score = 5.0  # Base score

            if rel_volume > 1.5:
                volume_score += 2.0  # High interest
            elif rel_volume < 0.7:
                volume_score -= 1.5  # Low interest

            if correlation > 0.5:
                volume_score += 1.0  # Volume confirms price moves

            if unusual:
                volume_score += 1.0  # Institutional activity

            volume_score = max(0, min(10, volume_score))

            # Signal
            if rel_volume > 1.5:
                signal = "⚡ Above average"
            elif rel_volume < 0.7:
                signal = "📉 Below average"
            else:
                signal = "➡️ Normal"

            # Interpretation
            interpretation = self._interpret_volume(rel_volume, correlation, unusual)

            return {
                'current_volume': int(current_volume),
                'avg_volume_20': int(avg_volume_20),
                'avg_volume_50': int(avg_volume_50),
                'relative_volume': round(rel_volume, 2),
                'volume_trend_pct': round(volume_trend_pct, 1),
                'unusual_volume': unusual,
                'volume_price_correlation': round(correlation, 2),
                'volume_score': round(volume_score, 1),
                'signal': signal,
                'interpretation': interpretation
            }

        except Exception as e:
            logger.warning(f"Relative volume analysis failed: {e}")
            return self._volume_placeholder()

    def _interpret_volume(self, rel_volume: float, correlation: float, unusual: bool) -> str:
        """Generate volume interpretation"""
        if unusual and correlation > 0.5:
            return "Institutional accumulation - breakout likely"
        elif unusual and correlation < -0.3:
            return "Distribution pattern - exercise caution"
        elif rel_volume > 1.3:
            return "Higher interest - monitor for momentum"
        elif rel_volume < 0.7:
            return "Low participation - wait for confirmation"
        else:
            return "Normal trading activity"

    def _volume_placeholder(self) -> Dict[str, Any]:
        """Return placeholder volume data when calculation fails"""
        return {
            'current_volume': 0,
            'avg_volume_20': 0,
            'avg_volume_50': 0,
            'relative_volume': 1.0,
            'volume_trend_pct': 0,
            'unusual_volume': False,
            'volume_price_correlation': 0,
            'volume_score': 5.0,
            'signal': 'Unknown',
            'interpretation': 'Volume data unavailable'
        }

    def _analyze_volume_at_support(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy method - redirects to new comprehensive analysis"""
        # This is kept for backward compatibility
        # Extract price_data from results if available
        try:
            # Simplified - return basic values
            return {
                'volume_trend': 'normal',
                'volume_score': 5.0,
                'volume_confirmation': True
            }
        except:
            return {
                'volume_trend': 'unknown',
                'volume_score': 5.0,
                'volume_confirmation': False
            }

    def _calculate_attractiveness_score(self, distance_from_support: float,
                                      fundamental_score: float, technical_score: float,
                                      rsi: float, volume_analysis: Dict[str, Any],
                                      current_price: float, support: float,
                                      resistance: float) -> float:
        """
        Calculate overall attractiveness score for the opportunity

        Returns:
            Score from 0-10 indicating how attractive the opportunity is
        """
        score = 0

        # Distance from support (closer = better, max 2 points)
        if distance_from_support <= -0.02:  # Below support
            score += 2.0
        elif distance_from_support <= 0:    # At support
            score += 1.8
        elif distance_from_support <= 0.01: # Very close to support
            score += 1.5
        else:                               # Close to support
            score += 1.0

        # Fundamental score (max 3 points)
        score += min(fundamental_score / 10 * 3, 3)

        # Technical score (max 2 points)
        score += min(technical_score / 10 * 2, 2)

        # RSI oversold bonus (max 1.5 points)
        if rsi < 30:
            score += 1.5
        elif rsi < 40:
            score += 1.0
        elif rsi < 50:
            score += 0.5

        # Risk/Reward ratio (max 1.5 points)
        risk_reward = (resistance - current_price) / (current_price - support) if (current_price - support) > 0 else 0
        if risk_reward > 3:
            score += 1.5
        elif risk_reward > 2:
            score += 1.0
        elif risk_reward > 1:
            score += 0.5

        return min(score, 10)

    def _get_current_price(self, price_data: pd.DataFrame) -> Optional[float]:
        """Get current price from price data"""
        try:
            # Check for column names (case sensitive)
            close_col = None
            for col in ['Close', 'close', 'CLOSE', 'Adj Close']:
                if col in price_data.columns:
                    close_col = col
                    break

            if close_col is None:
                return None

            return float(price_data[close_col].iloc[-1])
        except:
            return None

    def _calculate_atr(self, price_data: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average True Range (ATR)

        Args:
            price_data: DataFrame with OHLC data
            period: ATR period (default 14)

        Returns:
            ATR value
        """
        try:
            # Get column names
            high_col = self._get_column_name(price_data, ['High', 'high', 'HIGH'])
            low_col = self._get_column_name(price_data, ['Low', 'low', 'LOW'])
            close_col = self._get_column_name(price_data, ['Close', 'close', 'CLOSE', 'Adj Close'])

            if not all([high_col, low_col, close_col]):
                return 0.0

            high = price_data[high_col]
            low = price_data[low_col]
            close = price_data[close_col]

            # Calculate True Range
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean().iloc[-1]

            return float(atr) if not pd.isna(atr) else 0.0

        except Exception as e:
            logger.warning(f"ATR calculation failed: {e}")
            return 0.0

    def _get_column_name(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """Find column name from list of possibilities"""
        for name in possible_names:
            if name in df.columns:
                return name
        return None

    def _calculate_atr_zones(self, price_data: pd.DataFrame, current_price: float,
                           support: float, resistance: float) -> Dict[str, Any]:
        """
        Calculate precise entry zones based on ATR

        Args:
            price_data: Historical price data
            current_price: Current stock price
            support: Support level
            resistance: Resistance level

        Returns:
            Dictionary with entry zones and ATR info
        """
        try:
            atr = self._calculate_atr(price_data)

            if atr == 0:
                # Fallback to percentage-based zones
                atr = current_price * 0.02  # 2% of price as fallback

            zones = []

            # Zone 1: Near Support (0.5 ATR width)
            zone1_center = support * 1.005  # 0.5% above support
            zone1 = {
                'name': 'Near Support',
                'entry_low': round(zone1_center - (atr * 0.25), 2),
                'entry_high': round(zone1_center + (atr * 0.25), 2),
                'stop_loss': round(support - (atr * 0.5), 2),
                'target': round(resistance, 2),
                'type': 'bounce_play',
                'description': 'Support bounce play'
            }

            # Calculate R:R
            risk = zone1['entry_high'] - zone1['stop_loss']
            reward = zone1['target'] - zone1['entry_low']
            zone1['risk_reward'] = round(reward / risk, 2) if risk > 0 else 0
            zone1['width'] = round(zone1['entry_high'] - zone1['entry_low'], 2)
            zone1['width_atr'] = round(zone1['width'] / atr, 2) if atr > 0 else 0

            if zone1['risk_reward'] >= 1.5:
                zones.append(zone1)

            # Zone 2: Mid Range / Breakout (1.0 ATR width)
            if resistance > current_price * 1.03:  # Only if resistance is meaningful
                zone2_center = (support + resistance) / 2
                zone2 = {
                    'name': 'Mid Range',
                    'entry_low': round(zone2_center - (atr * 0.5), 2),
                    'entry_high': round(zone2_center + (atr * 0.5), 2),
                    'stop_loss': round(support - (atr * 0.5), 2),
                    'target': round(resistance * 1.05, 2),
                    'type': 'consolidation_break',
                    'description': 'Breakout after consolidation'
                }

                risk = zone2['entry_high'] - zone2['stop_loss']
                reward = zone2['target'] - zone2['entry_low']
                zone2['risk_reward'] = round(reward / risk, 2) if risk > 0 else 0
                zone2['width'] = round(zone2['entry_high'] - zone2['entry_low'], 2)
                zone2['width_atr'] = round(zone2['width'] / atr, 2) if atr > 0 else 0

                if zone2['risk_reward'] >= 1.5:
                    zones.append(zone2)

            return {
                'zones': zones,
                'atr': round(atr, 2),
                'atr_percent': round((atr / current_price) * 100, 2)
            }

        except Exception as e:
            logger.warning(f"ATR zones calculation failed: {e}")
            return {'zones': [], 'atr': 0, 'atr_percent': 0}

    def _calculate_detailed_momentum(self, indicators: Dict[str, Any], price_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate detailed momentum breakdown with individual component scores

        Args:
            indicators: Technical indicators dict from analysis
            price_data: Historical price data

        Returns:
            Dictionary with momentum breakdown and overall score
        """
        try:
            momentum_components = {}

            # 1. RSI Component (0-10 scale)
            rsi = indicators.get('rsi', 50)
            if rsi < 30:
                rsi_score = 10.0
                rsi_signal = "Oversold - Strong buy"
            elif rsi < 40:
                rsi_score = 8.0
                rsi_signal = "Oversold - Buy"
            elif rsi < 50:
                rsi_score = 6.5
                rsi_signal = "Weak - Neutral/Buy"
            elif rsi < 60:
                rsi_score = 5.0
                rsi_signal = "Neutral"
            elif rsi < 70:
                rsi_score = 4.0
                rsi_signal = "Strong - Caution"
            else:
                rsi_score = 2.0
                rsi_signal = "Overbought - Avoid"

            momentum_components['rsi'] = {
                'value': round(rsi, 1),
                'score': rsi_score,
                'signal': rsi_signal,
                'weight': 0.35
            }

            # 2. MACD Component (0-10 scale)
            macd_line = indicators.get('macd_line', 0)
            macd_signal = indicators.get('macd_signal', 0)
            macd_histogram = indicators.get('macd_histogram', 0)

            # MACD scoring based on line position and histogram
            macd_score = 5.0  # Base neutral
            macd_signal_text = "Neutral"

            if macd_line > macd_signal and macd_histogram > 0:
                if macd_histogram > abs(macd_line) * 0.1:  # Strong bullish
                    macd_score = 9.0
                    macd_signal_text = "Strong bullish crossover"
                else:
                    macd_score = 7.0
                    macd_signal_text = "Bullish crossover"
            elif macd_line < macd_signal and macd_histogram < 0:
                if macd_histogram < -abs(macd_line) * 0.1:  # Strong bearish
                    macd_score = 2.0
                    macd_signal_text = "Strong bearish crossover"
                else:
                    macd_score = 3.5
                    macd_signal_text = "Bearish crossover"
            elif macd_line > 0 and macd_histogram > 0:
                macd_score = 6.5
                macd_signal_text = "Bullish momentum"
            elif macd_line < 0 and macd_histogram < 0:
                macd_score = 4.0
                macd_signal_text = "Bearish momentum"

            momentum_components['macd'] = {
                'line': round(macd_line, 3),
                'signal': round(macd_signal, 3),
                'histogram': round(macd_histogram, 3),
                'score': macd_score,
                'signal': macd_signal_text,
                'weight': 0.30
            }

            # 3. EMA Trend Component (0-10 scale)
            close_col = self._get_column_name(price_data, ['Close', 'close', 'CLOSE', 'Adj Close'])

            if close_col and len(price_data) >= 50:
                current_price = price_data[close_col].iloc[-1]
                ema_9 = price_data[close_col].ewm(span=9).mean().iloc[-1]
                ema_21 = price_data[close_col].ewm(span=21).mean().iloc[-1]
                ema_50 = price_data[close_col].ewm(span=50).mean().iloc[-1]

                # EMA alignment scoring
                ema_score = 5.0  # Base neutral
                ema_signal_text = "Neutral"

                if current_price > ema_9 > ema_21 > ema_50:
                    ema_score = 9.5
                    ema_signal_text = "Strong uptrend - All EMAs aligned"
                elif current_price > ema_9 > ema_21:
                    ema_score = 7.5
                    ema_signal_text = "Uptrend - Short-term bullish"
                elif current_price > ema_21:
                    ema_score = 6.0
                    ema_signal_text = "Mild uptrend"
                elif current_price < ema_9 < ema_21 < ema_50:
                    ema_score = 1.5
                    ema_signal_text = "Strong downtrend - All EMAs aligned"
                elif current_price < ema_9 < ema_21:
                    ema_score = 3.0
                    ema_signal_text = "Downtrend - Short-term bearish"
                elif current_price < ema_21:
                    ema_score = 4.0
                    ema_signal_text = "Mild downtrend"

                momentum_components['ema'] = {
                    'ema_9': round(ema_9, 2),
                    'ema_21': round(ema_21, 2),
                    'ema_50': round(ema_50, 2),
                    'current_price': round(current_price, 2),
                    'score': ema_score,
                    'signal': ema_signal_text,
                    'weight': 0.35
                }
            else:
                # Fallback if not enough data
                momentum_components['ema'] = {
                    'ema_9': 0,
                    'ema_21': 0,
                    'ema_50': 0,
                    'current_price': 0,
                    'score': 5.0,
                    'signal': 'Insufficient data',
                    'weight': 0.35
                }

            # 4. Calculate weighted overall momentum score
            total_score = (
                momentum_components['rsi']['score'] * momentum_components['rsi']['weight'] +
                momentum_components['macd']['score'] * momentum_components['macd']['weight'] +
                momentum_components['ema']['score'] * momentum_components['ema']['weight']
            )

            # Overall momentum interpretation
            if total_score >= 7.5:
                overall_signal = "🚀 Strong momentum - High probability bounce"
            elif total_score >= 6.0:
                overall_signal = "✅ Good momentum - Favorable setup"
            elif total_score >= 5.0:
                overall_signal = "⚖️ Moderate momentum - Wait for confirmation"
            elif total_score >= 3.5:
                overall_signal = "⚠️ Weak momentum - Exercise caution"
            else:
                overall_signal = "🛑 Poor momentum - Avoid entry"

            return {
                'components': momentum_components,
                'overall_score': round(total_score, 1),
                'overall_signal': overall_signal,
                'rsi_component': momentum_components['rsi'],
                'macd_component': momentum_components['macd'],
                'ema_component': momentum_components['ema']
            }

        except Exception as e:
            logger.warning(f"Momentum breakdown calculation failed: {e}")
            return {
                'components': {},
                'overall_score': 5.0,
                'overall_signal': 'Calculation error',
                'rsi_component': {'score': 5.0, 'signal': 'N/A', 'weight': 0.35},
                'macd_component': {'score': 5.0, 'signal': 'N/A', 'weight': 0.30},
                'ema_component': {'score': 5.0, 'signal': 'N/A', 'weight': 0.35}
            }

    def _calculate_volume_analysis(self, price_data: pd.DataFrame, support_level: float) -> Dict[str, Any]:
        """Analyze volume patterns near support level"""
        try:
            # Check for column names
            close_col, volume_col = None, None
            for col in ['Close', 'close', 'CLOSE', 'Adj Close']:
                if col in price_data.columns:
                    close_col = col
                    break
            for col in ['Volume', 'volume', 'VOLUME']:
                if col in price_data.columns:
                    volume_col = col
                    break

            if close_col is None or volume_col is None:
                return {'volume_trend': 'unknown', 'volume_score': 5.0, 'volume_confirmation': False}

            # Get recent data
            recent_data = price_data.tail(10)
            avg_volume = recent_data[volume_col].mean()
            current_volume = recent_data[volume_col].iloc[-1]

            # Volume trend
            volume_trend = 'normal'
            if current_volume > avg_volume * 1.5:
                volume_trend = 'increasing'
            elif current_volume < avg_volume * 0.7:
                volume_trend = 'decreasing'

            # Volume score
            volume_score = 5.0
            if volume_trend == 'increasing':
                volume_score += 2.0
            elif volume_trend == 'decreasing':
                volume_score -= 1.0

            # Volume confirmation (simplified)
            volume_confirmation = current_volume > avg_volume

            return {
                'volume_trend': volume_trend,
                'volume_score': min(volume_score, 10.0),
                'volume_confirmation': volume_confirmation
            }
        except:
            return {'volume_trend': 'unknown', 'volume_score': 5.0, 'volume_confirmation': False}

    def _generate_recommendation(self, distance_from_support: float, fundamental_score: float, technical_score: float) -> str:
        """Generate simple recommendation based on scores"""
        try:
            total_score = fundamental_score + technical_score

            # Strong buy conditions
            if distance_from_support <= 0 and total_score >= 12:
                return 'BUY'
            elif distance_from_support <= 0.01 and total_score >= 10:
                return 'BUY'
            elif total_score >= 8:
                return 'WATCH'
            else:
                return 'HOLD'
        except:
            return 'HOLD'

    def format_results(self, opportunities: List[Dict[str, Any]]) -> str:
        """Format screening results for display"""
        if not opportunities:
            return "🔍 No support level opportunities found with current criteria."

        output = [f"\n📈 Found {len(opportunities)} Support Level Opportunities:\n"]
        output.append("=" * 80)

        for i, opp in enumerate(opportunities, 1):
            symbol = opp['symbol']
            current_price = opp['current_price']
            support_1 = opp['support_1']
            distance_pct = opp['distance_from_support_pct']
            attractiveness = opp['attractiveness_score']
            fundamental_score = opp['fundamental_score']
            technical_score = opp['technical_score']
            rsi = opp['rsi']
            risk_reward = opp['risk_reward_ratio']
            upside = opp['upside_to_resistance']
            recommendation = opp['recommendation']

            # Add ETF tag if applicable
            etf_tag = " [ETF]" if opp.get('is_etf', False) else ""
            output.append(f"{i}. {symbol}{etf_tag} - Score: {attractiveness:.1f}/10")
            output.append(f"   💰 Current: ${current_price:.2f} | Support: ${support_1:.2f}")
            output.append(f"   📊 Distance from Support: {distance_pct:.1f}%")
            output.append(f"   📈 Fundamental: {fundamental_score:.1f}/10 | Technical: {technical_score:.1f}/10")
            output.append(f"   🎯 RSI: {rsi:.1f} | Risk/Reward: {risk_reward:.1f}:1")
            output.append(f"   🚀 Upside to Resistance: {upside:.1f}%")
            output.append(f"   💡 Recommendation: {recommendation}")
            output.append("-" * 80)

        return "\n".join(output)


def main():
    """Example usage"""
    import sys
    sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')
    from main import StockAnalyzer

    # Initialize
    analyzer = StockAnalyzer()
    screener = SupportLevelScreener(analyzer)

    # Screen for opportunities
    opportunities = screener.screen_support_opportunities(
        max_distance_from_support=0.03,  # 3% below support max
        min_fundamental_score=5.0,
        min_technical_score=4.0,
        max_stocks=5,
        time_horizon='medium'
    )

    # Display results
    print(screener.format_results(opportunities))


if __name__ == "__main__":
    main()