#!/usr/bin/env python3
"""
Value Stock Screener
หาหุ้น value และ undervalued growth stocks ที่มีศักยภาพในการลงทุน
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

class ValueStockScreener:
    """Screen for value stocks and undervalued growth opportunities"""

    def __init__(self, stock_analyzer):
        """
        Initialize screener

        Args:
            stock_analyzer: StockAnalyzer instance
        """
        self.analyzer = stock_analyzer
        self.ai_generator = AIUniverseGenerator()

        # AI-only universe generation
        logger.info("Value stock screener initialized with AI-only universe generation")

    def screen_value_opportunities(self,
                                 max_pe_ratio: float = 50.0,
                                 max_pb_ratio: float = 10.0,
                                 min_roe: float = 1.0,
                                 max_debt_to_equity: float = 3.0,
                                 min_fundamental_score: float = 0.0,
                                 min_technical_score: float = 0.0,
                                 max_stocks: int = 25,
                                 screen_type: str = 'value',  # 'value', 'undervalued_growth'
                                 time_horizon: str = 'long'
) -> List[Dict[str, Any]]:
        """
        Screen for value stock opportunities

        Args:
            max_pe_ratio: Maximum P/E ratio (lower is more value-oriented)
            max_pb_ratio: Maximum P/B ratio (lower is more value-oriented)
            min_roe: Minimum Return on Equity percentage
            max_debt_to_equity: Maximum debt-to-equity ratio
            min_fundamental_score: Minimum fundamental score required
            min_technical_score: Minimum technical score required
            max_stocks: Maximum number of stocks to return
            screen_type: Type of screening ('value' or 'undervalued_growth')
            time_horizon: Investment time horizon

        Returns:
            List of value stock opportunities sorted by attractiveness
        """
        # Generate AI universe for value screening
        if not self.ai_generator:
            raise ValueError("AI universe generator not initialized. Cannot proceed without AI.")

        print(f"🤖 Generating AI-powered {screen_type} universe...")
        criteria = {
            'max_stocks': max_stocks,
            'time_horizon': time_horizon,
            'screen_type': screen_type,
            'max_pe_ratio': max_pe_ratio,
            'max_pb_ratio': max_pb_ratio,
            'min_roe': min_roe
        }
        stock_universe = self.ai_generator.generate_value_universe(criteria)
        print(f"✅ Generated {len(stock_universe)} AI-selected symbols")

        print(f"🔍 Screening {len(stock_universe)} stocks for {screen_type} opportunities...")

        opportunities = []

        # Use ThreadPoolExecutor for faster screening
        with ThreadPoolExecutor(max_workers=16) as executor:
            # Submit analysis tasks
            future_to_symbol = {
                executor.submit(self._analyze_stock_for_value, symbol, screen_type, time_horizon): symbol
                for symbol in stock_universe
            }

            # Collect results
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        opportunities.append(result)
                        print(f"✅ {symbol}: Found {screen_type} opportunity")
                    else:
                        print(f"❌ {symbol}: No {screen_type} opportunity")

                except Exception as e:
                    print(f"⚠️  {symbol}: Analysis failed - {e}")
                    logger.warning(f"Value analysis failed for {symbol}: {e}")
                    continue

        # Filter based on criteria
        print(f"\n🔍 Filtering {len(opportunities)} analyzed stocks with criteria:")
        print(f"   P/E ≤ {max_pe_ratio}, P/B ≤ {max_pb_ratio}, ROE ≥ {min_roe}%")
        print(f"   D/E ≤ {max_debt_to_equity}, Fund ≥ {min_fundamental_score}, Tech ≥ {min_technical_score}")

        filtered_opportunities = []
        for opp in opportunities:
            symbol = opp.get('symbol', 'UNKNOWN')

            # Check P/E ratio
            pe_ratio = opp.get('pe_ratio', 999)
            if pe_ratio > max_pe_ratio:
                print(f"   ❌ {symbol}: P/E {pe_ratio:.1f} > {max_pe_ratio}")
                continue

            # Check P/B ratio
            pb_ratio = opp.get('pb_ratio', 999)
            if pb_ratio > max_pb_ratio:
                print(f"   ❌ {symbol}: P/B {pb_ratio:.1f} > {max_pb_ratio}")
                continue

            # Check ROE (convert to percentage for comparison)
            roe = opp.get('roe', 0)
            roe_percent = roe * 100 if roe < 1 else roe  # Handle both decimal and percentage formats
            if roe_percent < min_roe:
                print(f"   ❌ {symbol}: ROE {roe_percent:.1f}% < {min_roe}%")
                continue

            # Check debt-to-equity
            debt_equity = opp.get('debt_to_equity', 999)
            if debt_equity > max_debt_to_equity:
                print(f"   ❌ {symbol}: D/E {debt_equity:.2f} > {max_debt_to_equity}")
                continue

            # Check fundamental score
            fundamental_score = opp.get('fundamental_score', 0)
            if fundamental_score < min_fundamental_score:
                print(f"   ❌ {symbol}: Fund {fundamental_score:.1f} < {min_fundamental_score}")
                continue

            # Check technical score
            technical_score = opp.get('technical_score', 0)
            if technical_score < min_technical_score:
                print(f"   ❌ {symbol}: Tech {technical_score:.1f} < {min_technical_score}")
                continue

            print(f"   ✅ {symbol}: PASSED all criteria")
            filtered_opportunities.append(opp)

        # Sort by value attractiveness score
        filtered_opportunities.sort(key=lambda x: x.get('value_score', 0), reverse=True)

        return filtered_opportunities[:max_stocks]

    def _analyze_stock_for_value(self, symbol: str, screen_type: str, time_horizon: str) -> Optional[Dict[str, Any]]:
        """
        Analyze individual stock for value opportunity

        Args:
            symbol: Stock symbol
            screen_type: Type of screening ('value' or 'undervalued_growth')
            time_horizon: Investment time horizon

        Returns:
            Dictionary with value opportunity details or None
        """
        try:
            # Use fast analysis for screening - much faster than full analysis
            results = self.analyzer.analyze_stock_fast(symbol, time_horizon=time_horizon)

            if 'error' in results:
                return None

            # Check if this is an ETF
            is_etf = results.get('is_etf', False)

            # Get fundamental analysis
            fundamental_analysis = results.get('fundamental_analysis', {})

            # The data is directly in fundamental_analysis, not in a nested financial_ratios dict
            # Key value metrics
            pe_ratio = fundamental_analysis.get('pe_ratio', None)
            pb_ratio = fundamental_analysis.get('price_to_book', None)  # Note: it's 'price_to_book' not 'pb_ratio'
            roe = fundamental_analysis.get('return_on_equity', None)  # Note: it's 'return_on_equity' not 'roe'
            debt_to_equity = fundamental_analysis.get('debt_to_equity', None)

            # Handle missing financial data more gracefully
            # Only require at least 2 out of 4 critical metrics to be present
            available_metrics = [pe_ratio, pb_ratio, roe, debt_to_equity]
            valid_metrics = [m for m in available_metrics if m is not None]

            if len(valid_metrics) < 2:
                return None  # Need at least 2 valid metrics

            # Use default values for missing metrics to allow analysis
            if pe_ratio is None:
                pe_ratio = 999  # High P/E will likely be filtered out later
            if pb_ratio is None:
                pb_ratio = 999  # High P/B will likely be filtered out later
            if roe is None:
                roe = 0.0  # Low ROE will likely be filtered out later
            if debt_to_equity is None:
                debt_to_equity = 0.0  # Conservative assumption

            # Basic value filtering - skip extremely overvalued stocks
            if (pe_ratio != 999 and pe_ratio > 100) or (pb_ratio != 999 and pb_ratio > 20) or debt_to_equity > 5.0:
                return None

            # Get additional metrics - handle None values properly
            current_price = results.get('current_price', 0) or 0
            revenue_growth = fundamental_analysis.get('revenue_growth', 0) or 0
            profit_margin = fundamental_analysis.get('profit_margin', 0) or 0

            # Get scores - handle None values properly
            fundamental_score = fundamental_analysis.get('overall_score', 0) or 0
            technical_analysis = results.get('technical_analysis', {})
            technical_score = technical_analysis.get('technical_score', {}).get('total_score', 0) or 0

            # Calculate intrinsic value metrics
            book_value_per_share = current_price / pb_ratio if pb_ratio > 0 else 0
            earnings_per_share = current_price / pe_ratio if pe_ratio > 0 else 0

            # Calculate value score based on screen type
            value_score = self._calculate_value_score(
                pe_ratio, pb_ratio, roe, debt_to_equity,
                revenue_growth, profit_margin, fundamental_score,
                technical_score, screen_type
            )

            # Get recommendation
            signal_analysis = results.get('signal_analysis', {})
            recommendation = signal_analysis.get('recommendation', {}).get('recommendation', 'HOLD')

            result = {
                'symbol': symbol,
                'current_price': current_price,
                'pe_ratio': pe_ratio,
                'pb_ratio': pb_ratio,
                'roe': roe,
                'debt_to_equity': debt_to_equity,
                'revenue_growth': revenue_growth,
                'profit_margin': profit_margin,
                'book_value_per_share': book_value_per_share,
                'earnings_per_share': earnings_per_share,
                'fundamental_score': fundamental_score,
                'technical_score': technical_score,
                'value_score': value_score,
                'screen_type': screen_type,
                'recommendation': recommendation,
                'upside_potential': self._calculate_upside_potential(pe_ratio, pb_ratio, roe),
                'margin_of_safety': self._calculate_margin_of_safety(current_price, book_value_per_share, pe_ratio),
                'analysis_date': datetime.now().isoformat(),
                'is_etf': is_etf
            }

            return result

        except Exception as e:
            logger.warning(f"Value analysis failed for {symbol}: {e}")
            return None

    def _calculate_value_score(self, pe_ratio: float, pb_ratio: float, roe: float,
                             debt_to_equity: float, revenue_growth: float,
                             profit_margin: float, fundamental_score: float,
                             technical_score: float, screen_type: str) -> float:
        """
        Calculate overall value attractiveness score

        Args:
            pe_ratio: Price-to-Earnings ratio
            pb_ratio: Price-to-Book ratio
            roe: Return on Equity
            debt_to_equity: Debt-to-Equity ratio
            revenue_growth: Revenue growth rate
            profit_margin: Profit margin percentage
            fundamental_score: Fundamental analysis score
            technical_score: Technical analysis score
            screen_type: Type of screening ('value' or 'undervalued_growth')

        Returns:
            Score from 0-10 indicating value attractiveness
        """
        score = 0

        # P/E ratio scoring (lower is better, max 2 points)
        if pe_ratio < 10:
            score += 2.0
        elif pe_ratio < 15:
            score += 1.5
        elif pe_ratio < 20:
            score += 1.0
        elif pe_ratio < 25:
            score += 0.5

        # P/B ratio scoring (lower is better, max 1.5 points)
        if pb_ratio < 1:
            score += 1.5
        elif pb_ratio < 2:
            score += 1.0
        elif pb_ratio < 3:
            score += 0.5

        # ROE scoring (higher is better, max 2 points)
        if roe > 20:
            score += 2.0
        elif roe > 15:
            score += 1.5
        elif roe > 10:
            score += 1.0
        elif roe > 5:
            score += 0.5

        # Debt-to-equity scoring (lower is better, max 1 point)
        if debt_to_equity < 0.3:
            score += 1.0
        elif debt_to_equity < 0.5:
            score += 0.7
        elif debt_to_equity < 1.0:
            score += 0.3

        # Growth component (different weighting based on screen type)
        if screen_type == 'undervalued_growth':
            # Growth-oriented scoring (max 2 points)
            if revenue_growth > 15:
                score += 2.0
            elif revenue_growth > 10:
                score += 1.5
            elif revenue_growth > 5:
                score += 1.0
            elif revenue_growth > 0:
                score += 0.5
        else:
            # Value-oriented scoring (max 1 point)
            if revenue_growth > 5:
                score += 1.0
            elif revenue_growth > 0:
                score += 0.5

        # Profitability scoring (max 1 point)
        if profit_margin > 15:
            score += 1.0
        elif profit_margin > 10:
            score += 0.7
        elif profit_margin > 5:
            score += 0.4

        # Quality scores (max 0.5 points)
        score += min(fundamental_score / 20, 0.3)
        score += min(technical_score / 50, 0.2)

        return min(score, 10)

    def _calculate_upside_potential(self, pe_ratio: float, pb_ratio: float, roe: float) -> float:
        """Calculate estimated upside potential percentage"""
        try:
            # Simple Graham-style intrinsic value estimation
            # Fair P/E based on growth and quality
            fair_pe = min(15, max(8, roe * 0.7))  # Conservative fair P/E
            fair_pb = min(2.5, max(1.0, roe * 0.1))  # Conservative fair P/B

            # Upside based on P/E
            pe_upside = ((fair_pe / pe_ratio) - 1) * 100 if pe_ratio > 0 else 0

            # Upside based on P/B
            pb_upside = ((fair_pb / pb_ratio) - 1) * 100 if pb_ratio > 0 else 0

            # Take conservative average
            upside = (pe_upside + pb_upside) / 2

            return max(0, min(upside, 200))  # Cap at 200% upside
        except:
            return 0

    def _calculate_margin_of_safety(self, current_price: float, book_value: float, pe_ratio: float) -> float:
        """Calculate margin of safety percentage"""
        try:
            # Conservative intrinsic value (lower of book value multiple or earnings multiple)
            book_based_value = book_value * 1.2  # 20% premium to book
            earnings_based_value = current_price * (12 / max(pe_ratio, 1))  # P/E of 12 target

            intrinsic_value = min(book_based_value, earnings_based_value)

            margin = ((intrinsic_value / current_price) - 1) * 100 if current_price > 0 else 0

            return max(0, min(margin, 100))  # Cap at 100% margin
        except:
            return 0

    def format_results(self, opportunities: List[Dict[str, Any]], screen_type: str = 'value') -> str:
        """Format screening results for display"""
        if not opportunities:
            return f"🔍 No {screen_type} opportunities found with current criteria."

        output = [f"\n📊 Found {len(opportunities)} {screen_type.title()} Opportunities:\n"]
        output.append("=" * 90)

        for i, opp in enumerate(opportunities, 1):
            symbol = opp['symbol']
            current_price = opp['current_price']
            pe_ratio = opp['pe_ratio']
            pb_ratio = opp['pb_ratio']
            roe = opp['roe']
            debt_equity = opp['debt_to_equity']
            value_score = opp['value_score']
            upside = opp['upside_potential']
            margin_safety = opp['margin_of_safety']
            recommendation = opp['recommendation']

            # Add ETF tag if applicable
            etf_tag = " [ETF]" if opp.get('is_etf', False) else ""
            output.append(f"{i}. {symbol}{etf_tag} - Value Score: {value_score:.1f}/10")
            output.append(f"   💰 Price: ${current_price:.2f} | P/E: {pe_ratio:.1f} | P/B: {pb_ratio:.1f}")
            output.append(f"   📊 ROE: {roe:.1f}% | Debt/Eq: {debt_equity:.2f}")
            output.append(f"   🎯 Upside: {upside:.1f}% | Safety Margin: {margin_safety:.1f}%")
            output.append(f"   💡 Recommendation: {recommendation}")
            output.append("-" * 90)

        return "\n".join(output)

    def screen_small_mid_cap_opportunities(self,
                                          market_cap_type: str = 'both',  # 'small', 'mid', 'both'
                                          min_revenue_growth: float = 10.0,
                                          min_earnings_growth: float = 10.0,
                                          min_momentum_score: float = 4.0,
                                          volume_trend: str = 'any',  # 'increasing', 'stable', 'any'
                                          min_fundamental_score: float = 3.0,
                                          min_technical_score: float = 3.0,
                                          max_stocks: int = 12,
                                          time_horizon: str = 'medium'
                                          ) -> List[Dict[str, Any]]:
        """
        Screen for Small/Mid Cap growth stock opportunities

        Args:
            market_cap_type: Type of market cap ('small', 'mid', 'both')
            min_revenue_growth: Minimum revenue growth rate (%)
            min_earnings_growth: Minimum earnings growth rate (%)
            min_momentum_score: Minimum momentum score (1-10)
            volume_trend: Volume trend requirement
            min_fundamental_score: Minimum fundamental score
            min_technical_score: Minimum technical score
            max_stocks: Maximum number of stocks to return
            time_horizon: Investment time horizon

        Returns:
            List of small/mid cap growth opportunities
        """
        logger.info(f"🚀 Starting Small/Mid Cap Growth screening ({market_cap_type}) for {max_stocks} stocks")

        # Generate AI universe focused on growth stocks
        universe_prompt = self._get_growth_universe_prompt(market_cap_type, min_revenue_growth, min_earnings_growth)
        target_symbols = max_stocks * 3

        print(f"\n🎯 Requesting {target_symbols} symbols from AI...")
        symbols = self.ai_generator.generate_universe(universe_prompt, target_count=target_symbols)

        if not symbols:
            logger.warning("No symbols generated for Small/Mid Cap growth screening")
            print("❌ AI failed to generate any symbols. Using fallback list...")
            # Fallback with known growth stocks
            symbols = [
                'PLTR', 'STX', 'WDC', 'GEV', 'KTOS', 'AVAV', 'AMSC',
                'SMCI', 'NVDA', 'AMD', 'TSM', 'ASML', 'ANET', 'CRWD',
                'ZS', 'OKTA', 'NET', 'DDOG', 'SNOW', 'MDB', 'RBLX',
                'RIVN', 'LCID', 'SOFI', 'UPST', 'AFRM', 'SQ', 'PYPL',
                'ROKU', 'UBER', 'LYFT', 'DASH', 'ABNB', 'COIN', 'HOOD'
            ][:target_symbols]

        print(f"📋 Using {len(symbols)} symbols for analysis: {symbols[:10]}...")

        opportunities = []
        print(f"\n🎯 Analyzing {len(symbols)} potential Small/Mid Cap growth stocks...")

        # Analyze each symbol with threading for performance
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_symbol = {
                executor.submit(self._analyze_stock_for_growth, symbol, market_cap_type, time_horizon): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    opportunity = future.result()
                    if opportunity:
                        opportunities.append(opportunity)
                        growth_score = opportunity.get('growth_score', 0)
                        upside = opportunity.get('upside_potential', 0)
                        market_cap = opportunity.get('market_cap', 0)
                        rev_growth = opportunity.get('revenue_growth', 0)
                        earn_growth = opportunity.get('earnings_growth', 0)
                        print(f"✅ {symbol}: Growth {growth_score:.1f}/10, Upside {upside:.0f}%, Rev {rev_growth:.1f}%, Earn {earn_growth:.1f}%")
                    else:
                        print(f"❌ {symbol}: Analysis returned None - no opportunity found")

                except Exception as e:
                    print(f"⚠️  {symbol}: Analysis failed - {e}")
                    logger.warning(f"Growth analysis failed for {symbol}: {e}")
                    continue

        # Filter based on growth criteria
        print(f"\n🔍 Filtering {len(opportunities)} analyzed stocks with growth criteria:")
        print(f"   Revenue Growth ≥ {min_revenue_growth}%, Earnings Growth ≥ {min_earnings_growth}%")
        print(f"   Momentum ≥ {min_momentum_score}, Fund ≥ {min_fundamental_score}, Tech ≥ {min_technical_score}")

        filtered_opportunities = []
        for opp in opportunities:
            symbol = opp.get('symbol', 'UNKNOWN')

            # Check revenue growth (more lenient for missing data)
            revenue_growth = opp.get('revenue_growth', 0)
            if revenue_growth > 0 and revenue_growth < min_revenue_growth:
                print(f"   ❌ {symbol}: Revenue Growth {revenue_growth:.1f}% < {min_revenue_growth}%")
                continue
            elif revenue_growth <= 0:
                print(f"   ⚠️  {symbol}: Revenue Growth data missing or invalid ({revenue_growth:.1f}%)")
                # Don't exclude if data is missing - let it pass for further analysis

            # Check earnings growth (more lenient for missing data)
            earnings_growth = opp.get('earnings_growth', 0)
            if earnings_growth > 0 and earnings_growth < min_earnings_growth:
                print(f"   ❌ {symbol}: Earnings Growth {earnings_growth:.1f}% < {min_earnings_growth}%")
                continue
            elif earnings_growth <= 0:
                print(f"   ⚠️  {symbol}: Earnings Growth data missing or invalid ({earnings_growth:.1f}%)")
                # Don't exclude if data is missing - let it pass

            # Check momentum score
            momentum_score = opp.get('momentum_score', 0)
            if momentum_score < min_momentum_score:
                print(f"   ❌ {symbol}: Momentum {momentum_score:.1f} < {min_momentum_score}")
                continue

            # Check fundamental score
            fundamental_score = opp.get('fundamental_score', 0)
            if fundamental_score < min_fundamental_score:
                print(f"   ❌ {symbol}: Fund {fundamental_score:.1f} < {min_fundamental_score}")
                continue

            # Check technical score
            technical_score = opp.get('technical_score', 0)
            if technical_score < min_technical_score:
                print(f"   ❌ {symbol}: Tech {technical_score:.1f} < {min_technical_score}")
                continue

            print(f"   ✅ {symbol}: PASSED all growth criteria")
            filtered_opportunities.append(opp)

        # Sort by growth score
        filtered_opportunities.sort(key=lambda x: x.get('growth_score', 0), reverse=True)

        return filtered_opportunities[:max_stocks]

    def _get_growth_universe_prompt(self, market_cap_type: str, min_revenue_growth: float, min_earnings_growth: float) -> str:
        """Generate universe prompt for Small/Mid Cap growth stocks"""

        market_cap_desc = {
            'small': 'Small Cap companies ($300M - $2B market cap)',
            'mid': 'Mid Cap companies ($2B - $10B market cap)',
            'both': 'Small to Mid Cap companies ($300M - $10B market cap)'
        }.get(market_cap_type, 'Small to Mid Cap companies')

        return f"""Generate a diverse list of {market_cap_desc} US stocks with PROFITABLE GROWTH potential that are CURRENTLY PUBLICLY TRADED as of 2024-2025.

PRIORITIZE COMPANIES WITH BOTH REVENUE AND EARNINGS GROWTH:
- MPWR (Monolithic Power) - Semiconductor growth with strong earnings
- AMSC (American Superconductor) - Clean energy with revenue acceleration
- SOFI (SoFi Technologies) - FinTech turning profitable
- UPST (Upstart Holdings) - AI lending with improving margins
- PLUG (Plug Power) - Hydrogen fuel improving profitability
- KTOS (Kratos Defense) - Defense tech with consistent earnings
- BLDP (Ballard Power) - Fuel cell technology

GROWTH SECTORS CURRENTLY PERFORMING:
- AI Infrastructure: Semiconductor, data center, cloud storage stocks
- Clean Energy: Solar, hydrogen, battery storage companies
- Defense & Aerospace: Military contractors, drone technology
- FinTech: Digital banking, payment processing, lending platforms
- Healthcare Tech: Biotech, medical devices, digital health
- Industrial Automation: Robotics, IoT, smart manufacturing
- Cybersecurity: Network security, cloud protection
- Cannabis/Biotech: Medical marijuana, pharmaceutical services

CRITICAL REQUIREMENTS:
- Market cap: $300M - $50B (updated realistic range)
- BOTH revenue growth >15% AND earnings growth >10% preferred
- Positive earnings trajectory (improving or already profitable)
- Strong momentum in 2024-2025 timeframe
- Realistic growth stories, not hype-driven

BALANCE THE MIX:
- 40% Established growth (profitable, $2B-$50B market cap)
- 30% Emerging leaders ($500M-$5B, turning profitable)
- 20% Small caps with breakout potential ($300M-$2B)
- 10% Recovery/turnaround stories in growth sectors

Focus on companies that combine growth with improving profitability, not just revenue growth alone."""

    def _analyze_stock_for_growth(self, symbol: str, market_cap_type: str, time_horizon: str) -> Optional[Dict[str, Any]]:
        """
        Analyze individual stock for Small/Mid Cap growth opportunity

        Args:
            symbol: Stock symbol
            market_cap_type: Market cap type filter
            time_horizon: Investment time horizon

        Returns:
            Dictionary with growth opportunity details or None
        """
        try:
            # Use fast analysis for screening
            results = self.analyzer.analyze_stock_fast(symbol, time_horizon=time_horizon)

            if 'error' in results:
                logger.debug(f"{symbol}: Analysis returned error: {results.get('error')}")
                return None

            # Check if this is an ETF (usually not growth-oriented for small/mid cap)
            is_etf = results.get('is_etf', False)
            if is_etf:
                logger.debug(f"{symbol}: Skipping ETF")
                return None  # Skip ETFs for growth screening

            # Get analysis components
            fundamental_analysis = results.get('fundamental_analysis', {})
            technical_analysis = results.get('technical_analysis', {})

            # Get market cap info
            market_cap = fundamental_analysis.get('market_cap', 0)
            logger.debug(f"{symbol}: Market cap = ${market_cap/1e6:.0f}M")

            # Apply market cap filter (more lenient for growth stocks)
            if market_cap > 0:  # Only filter if we have valid market cap data
                if market_cap_type == 'small' and (market_cap < 300e6 or market_cap > 5e9):  # Expanded small cap up to 5B
                    logger.debug(f"{symbol}: Outside expanded small cap range (${market_cap/1e6:.0f}M)")
                    return None
                elif market_cap_type == 'mid' and (market_cap < 2e9 or market_cap > 50e9):  # Expanded mid cap up to 50B
                    logger.debug(f"{symbol}: Outside expanded mid cap range (${market_cap/1e6:.0f}M)")
                    return None
                elif market_cap_type == 'both' and (market_cap < 300e6 or market_cap > 50e9):  # Allow up to 50B for 'both'
                    logger.debug(f"{symbol}: Outside expanded small/mid cap range (${market_cap/1e6:.0f}M)")
                    return None
            else:
                logger.debug(f"{symbol}: Market cap data missing, allowing through")

            # Get growth metrics - try multiple field names
            revenue_growth = (
                fundamental_analysis.get('revenue_growth_rate', 0) or
                fundamental_analysis.get('revenue_growth', 0) or
                fundamental_analysis.get('sales_growth', 0) or
                0
            )

            earnings_growth = (
                fundamental_analysis.get('earnings_growth_rate', 0) or
                fundamental_analysis.get('earnings_growth', 0) or
                fundamental_analysis.get('eps_growth', 0) or
                0
            )

            logger.debug(f"{symbol}: Raw growth data - Rev: {revenue_growth}, Earn: {earnings_growth}")

            # Convert growth rates from decimal to percentage if needed
            if 0 < revenue_growth < 1:
                revenue_growth *= 100
            if 0 < earnings_growth < 1:
                earnings_growth *= 100

            # Apply reasonable bounds for growth rates
            revenue_growth = max(0, min(500, revenue_growth))  # Cap at 500%
            earnings_growth = max(0, min(1000, earnings_growth))  # Cap at 1000%

            logger.debug(f"{symbol}: Processed growth - Rev: {revenue_growth:.1f}%, Earn: {earnings_growth:.1f}%")

            # Get other key metrics
            current_price = fundamental_analysis.get('current_price', 0) or 0
            pe_ratio = fundamental_analysis.get('pe_ratio', 0) or 0

            # Get profitability metrics
            profit_margin = (
                fundamental_analysis.get('profit_margin', 0) or
                fundamental_analysis.get('net_margin', 0) or
                fundamental_analysis.get('net_profit_margin', 0) or
                0
            )

            operating_margin = (
                fundamental_analysis.get('operating_margin', 0) or
                fundamental_analysis.get('operating_profit_margin', 0) or
                0
            )

            # Get cash flow metrics
            free_cash_flow = fundamental_analysis.get('free_cash_flow', 0) or 0
            operating_cash_flow = fundamental_analysis.get('operating_cash_flow', 0) or 0

            # Convert margins from decimal to percentage if needed
            if 0 < profit_margin < 1:
                profit_margin *= 100
            if 0 < operating_margin < 1:
                operating_margin *= 100

            logger.debug(f"{symbol}: Profitability - Profit Margin: {profit_margin:.1f}%, Operating Margin: {operating_margin:.1f}%")

            # Get scores
            fundamental_score = results.get('fundamental_score', 0)
            technical_score = results.get('technical_score', 0)

            logger.debug(f"{symbol}: Scores - Fund: {fundamental_score:.1f}, Tech: {technical_score:.1f}")

            # Even if growth data is missing, let's proceed with basic analysis
            if revenue_growth == 0 and earnings_growth == 0:
                logger.debug(f"{symbol}: Missing growth data, using default values")
                revenue_growth = 5.0  # Default conservative growth
                earnings_growth = 5.0

            # Calculate momentum score (simplified)
            momentum_score = self._calculate_momentum_score(technical_analysis)

            # Calculate growth score
            growth_score = self._calculate_growth_score(
                revenue_growth, earnings_growth, momentum_score,
                fundamental_score, technical_score, market_cap,
                profit_margin, operating_margin
            )

            # Get recommendation
            recommendation = results.get('investment_recommendation', {}).get('recommendation', 'Hold')

            # Calculate upside potential for growth stocks
            upside_potential = self._calculate_growth_upside_potential(
                revenue_growth, earnings_growth, momentum_score, pe_ratio,
                profit_margin, operating_margin
            )

            logger.debug(f"{symbol}: Final scores - Growth: {growth_score:.1f}, Upside: {upside_potential:.0f}%")

            # Ensure we have minimum viable data
            if current_price <= 0:
                current_price = 100.0  # Default price for display
                logger.debug(f"{symbol}: Using default price")

            result = {
                'symbol': symbol,
                'company_name': fundamental_analysis.get('company_name', symbol),
                'current_price': current_price,
                'market_cap': market_cap if market_cap > 0 else 1e9,  # Default 1B if missing
                'revenue_growth': revenue_growth,
                'earnings_growth': earnings_growth,
                'momentum_score': momentum_score,
                'growth_score': growth_score,
                'fundamental_score': fundamental_score,
                'technical_score': technical_score,
                'pe_ratio': pe_ratio if pe_ratio > 0 else 25.0,  # Default PE
                'recommendation': recommendation,
                'upside_potential': upside_potential,
                'market_cap_type': market_cap_type,
                'analysis_date': datetime.now().isoformat(),
                'is_etf': is_etf
            }

            logger.info(f"✓ {symbol}: Analysis complete - Growth {growth_score:.1f}/10")
            return result

        except Exception as e:
            logger.warning(f"Growth analysis failed for {symbol}: {e}")
            return None

    def _calculate_momentum_score(self, technical_analysis: Dict) -> float:
        """Calculate momentum score from technical analysis"""
        try:
            # Get various technical indicators
            rsi = technical_analysis.get('rsi', 50)
            trend_score = technical_analysis.get('trend_analysis', {}).get('trend_strength', 5)
            volume_trend = technical_analysis.get('volume_analysis', {}).get('volume_trend', 'stable')

            momentum = 5.0  # Base score

            # RSI momentum (optimal range 55-75 for growth stocks)
            if 55 <= rsi <= 75:
                momentum += 2.0
            elif 45 <= rsi <= 85:
                momentum += 1.0
            elif rsi > 85:
                momentum -= 1.0  # Overbought

            # Trend strength
            momentum += (trend_score - 5) * 0.4

            # Volume trend
            if volume_trend == 'increasing':
                momentum += 1.5
            elif volume_trend == 'stable':
                momentum += 0.5

            return max(0, min(10, momentum))

        except:
            return 5.0

    def _calculate_growth_score(self, revenue_growth: float, earnings_growth: float,
                               momentum_score: float, fundamental_score: float,
                               technical_score: float, market_cap: float,
                               profit_margin: float = 0, operating_margin: float = 0) -> float:
        """Calculate overall growth attractiveness score with emphasis on profitable growth"""

        score = 0

        # Revenue growth scoring (max 2.0 points - reduced from 2.5)
        if revenue_growth >= 50:
            score += 2.0
        elif revenue_growth >= 30:
            score += 1.6
        elif revenue_growth >= 20:
            score += 1.2
        elif revenue_growth >= 15:
            score += 0.8
        elif revenue_growth >= 10:
            score += 0.4

        # Earnings growth scoring (max 3.5 points - increased from 2.5)
        if earnings_growth >= 60:
            score += 3.5
        elif earnings_growth >= 40:
            score += 3.0
        elif earnings_growth >= 25:
            score += 2.5
        elif earnings_growth >= 15:
            score += 2.0
        elif earnings_growth >= 10:
            score += 1.5
        elif earnings_growth >= 5:
            score += 1.0
        elif earnings_growth > 0:
            score += 0.5
        else:
            # Penalty for no earnings growth
            score -= 1.0

        # Profitability scoring (max 1.0 points)
        if profit_margin >= 20:
            score += 1.0  # Excellent profitability
        elif profit_margin >= 15:
            score += 0.8  # Very good profitability
        elif profit_margin >= 10:
            score += 0.6  # Good profitability
        elif profit_margin >= 5:
            score += 0.4  # Moderate profitability
        elif profit_margin > 0:
            score += 0.2  # Barely profitable
        else:
            score -= 0.5  # Unprofitable penalty

        # Operating efficiency bonus (max 0.5 points)
        if operating_margin >= 20:
            score += 0.5
        elif operating_margin >= 10:
            score += 0.3
        elif operating_margin >= 5:
            score += 0.1

        # Profitable growth bonus: extra points when both revenue and earnings grow
        if revenue_growth > 15 and earnings_growth > 10:
            score += 1.0  # Profitable growth bonus
        elif revenue_growth > 20 and earnings_growth > 0:
            score += 0.5  # Partial bonus for revenue leaders turning profitable

        # Margin expansion bonus: reward improving profitability
        if profit_margin > 10 and earnings_growth > revenue_growth:
            score += 0.5  # Margin expansion bonus

        # Momentum score (max 1.0 points - reduced further)
        score += (momentum_score / 10) * 1.0

        # Fundamental and technical scores (max 0.8 + 0.7 = 1.5 points - reduced)
        score += (fundamental_score / 10) * 0.8
        score += (technical_score / 10) * 0.7

        return min(10, max(0, score))

    def _calculate_growth_upside_potential(self, revenue_growth: float, earnings_growth: float,
                                          momentum_score: float, pe_ratio: float,
                                          profit_margin: float = 0, operating_margin: float = 0) -> float:
        """
        Calculate upside potential for growth stocks with profitability consideration

        Enhanced to weight profitable growth higher than pure revenue growth
        """

        # Ensure all inputs are valid numbers
        revenue_growth = revenue_growth or 0
        earnings_growth = earnings_growth or 0
        momentum_score = momentum_score or 5.0
        pe_ratio = pe_ratio or 20.0
        profit_margin = profit_margin or 0
        operating_margin = operating_margin or 0

        base_upside = 25  # Base expectation for growth stocks

        # Earnings growth contribution (INCREASED WEIGHT - primary driver)
        if earnings_growth >= 50:
            base_upside += 35  # Exceptional earnings growth
        elif earnings_growth >= 30:
            base_upside += 25  # Strong earnings growth
        elif earnings_growth >= 20:
            base_upside += 18  # Good earnings growth
        elif earnings_growth >= 10:
            base_upside += 10  # Modest earnings growth

        # Revenue growth contribution (reduced weight vs earnings)
        if revenue_growth >= 40:
            base_upside += 20  # Strong revenue growth
        elif revenue_growth >= 25:
            base_upside += 15  # Good revenue growth
        elif revenue_growth >= 15:
            base_upside += 8   # Modest revenue growth

        # Profitability bonus (NEW - high margin companies get upside boost)
        if profit_margin >= 20:
            base_upside += 15  # Excellent margins
        elif profit_margin >= 15:
            base_upside += 10  # Strong margins
        elif profit_margin >= 10:
            base_upside += 5   # Good margins
        elif profit_margin < 0:
            base_upside -= 10  # Losing money reduces upside

        # Operating efficiency bonus (NEW)
        if operating_margin >= 25:
            base_upside += 10  # Excellent operating efficiency
        elif operating_margin >= 15:
            base_upside += 5   # Good operating efficiency

        # Profitable growth multiplier (NEW - when both growth and profitability are strong)
        if earnings_growth >= 20 and profit_margin >= 15:
            base_upside += 15  # Profitable growth premium
        elif earnings_growth >= 15 and profit_margin >= 10:
            base_upside += 8   # Good profitable growth

        # Momentum contribution
        base_upside += (momentum_score - 5) * 3

        # PE adjustment (reasonable PE for profitable growth)
        if profit_margin >= 10:  # For profitable companies
            if 15 <= pe_ratio <= 25:
                base_upside += 8  # Sweet spot for profitable growth
            elif pe_ratio > 40:
                base_upside -= 12  # Too expensive even if profitable
        else:  # For unprofitable companies
            if 15 <= pe_ratio <= 35:
                base_upside += 3  # More lenient PE for growth stories
            elif pe_ratio > 50:
                base_upside -= 15  # Too expensive for unprofitable

        return max(0, min(160, base_upside))  # Increased max to 160% for exceptional profitable growth


def main():
    """Example usage"""
    import sys
    sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')
    from main import StockAnalyzer

    # Initialize
    analyzer = StockAnalyzer()
    screener = ValueStockScreener(analyzer)

    # Screen for value opportunities
    print("=== Value Stock Screening ===")
    value_opportunities = screener.screen_value_opportunities(
        max_pe_ratio=20.0,
        max_pb_ratio=4.0,
        min_roe=8.0,
        max_debt_to_equity=0.8,
        min_fundamental_score=4.0,
        min_technical_score=3.0,
        max_stocks=25,
        screen_type='value',
        time_horizon='long'
    )

    print(screener.format_results(value_opportunities, 'value'))

    # Screen for undervalued growth opportunities
    print("\n=== Undervalued Growth Screening ===")
    growth_opportunities = screener.screen_value_opportunities(
        max_pe_ratio=25.0,
        max_pb_ratio=5.0,
        min_roe=15.0,
        max_debt_to_equity=0.7,
        min_fundamental_score=6.0,
        min_technical_score=5.0,
        max_stocks=10,
        screen_type='undervalued_growth',
        time_horizon='long'
    )

    print(screener.format_results(growth_opportunities, 'undervalued_growth'))


if __name__ == "__main__":
    main()