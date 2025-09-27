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
                                   max_stocks: int = 10,
                                   time_horizon: str = 'medium',
) -> List[Dict[str, Any]]:
        """
        Screen for stocks near support levels with good opportunities

        Args:
            max_distance_from_support: Maximum distance below support (as percentage)
            min_fundamental_score: Minimum fundamental score required
            min_technical_score: Minimum technical score required
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

            # Calculate volume analysis
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
                'analysis_date': datetime.now().isoformat(),
                'is_etf': is_etf
            }

        except Exception as e:
            logger.warning(f"Analysis failed for {symbol}: {e}")
            return None

    def _analyze_volume_at_support(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze volume characteristics at support level"""
        try:
            # This is a simplified volume analysis
            # In reality, you'd want to analyze volume patterns more deeply
            return {
                'volume_trend': 'normal',  # Could be 'increasing', 'decreasing', 'normal'
                'volume_score': 5.0,       # Score out of 10
                'volume_confirmation': True # Whether volume confirms the support
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