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
            current_price = results.get('current_price', 0) or 0  # Get from top-level results, not fundamental_analysis
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

    def screen_volatile_trading_opportunities(self,
                                             min_volatility: float = 35.0,
                                             min_avg_volume: float = 2000000,
                                             min_price_range: float = 8.0,
                                             min_momentum_score: float = 3.5,
                                             max_stocks: int = 20,
                                             time_horizon: str = 'short',
                                             min_atr_pct: float = 2.0,
                                             min_price: float = 5.0,
                                             exclude_falling_knife: bool = True,
                                             exclude_overextended: bool = False,
                                             only_uptrend: bool = False,
                                             require_dip: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Screen for volatile stocks suitable for short-term trading
        หาหุ้นที่มีความผันผวนสูง เหมาะสำหรับเทรดระยะสั้น

        Args:
            min_volatility: ความผันผวนขั้นต่ำ (%) - หุ้นที่มี ATR%/Volatility สูง (updated default: 40%)
            min_avg_volume: Volume เฉลี่ยต่อวันขั้นต่ำ (updated default: 2M)
            min_price_range: ช่วงราคาขั้นต่ำใน % (High-Low range) (updated default: 10%)
            min_momentum_score: คะแนน momentum ขั้นต่ำ (updated default: 5.0)
            max_stocks: จำนวนหุ้นสูงสุดที่จะส่งกลับ
            time_horizon: ระยะเวลาการเทรด (short, very_short)
            min_atr_pct: ATR% ขั้นต่ำ (NEW - Average True Range percentage)
            min_price: ราคาหุ้นขั้นต่ำ (NEW - exclude penny stocks)
            exclude_falling_knife: กรองหุ้น Falling Knife ออก (NEW)
            exclude_overextended: กรองหุ้น Overextended ออก (NEW)
            only_uptrend: เฉพาะหุ้นที่อยู่ใน Uptrend (NEW)
            require_dip: ต้องมี Dip Opportunity (NEW)

        Returns:
            List of volatile trading opportunities
        """
        # Generate AI universe for volatile trading
        if not self.ai_generator:
            raise ValueError("AI universe generator not initialized")

        logger.info(f"🤖 Generating AI-powered volatile trading universe...")
        criteria = {
            'max_stocks': max_stocks * 8,  # Generate more for filtering (increased from 6x to 8x)
            'time_horizon': time_horizon,
            'screen_type': 'volatile_trading',
            'min_volatility': min_volatility,
            'min_volume': min_avg_volume
        }
        stock_universe = self.ai_generator.generate_volatile_universe(criteria)

        # Fallback if AI returns empty
        if not stock_universe:
            logger.error("AI returned empty universe - cannot proceed")
            return []

        logger.info(f"✅ Generated {len(stock_universe)} AI-selected volatile symbols")

        logger.info(f"🔍 Screening {len(stock_universe)} stocks for volatile trading opportunities...")

        opportunities = []

        # Use ThreadPoolExecutor for faster screening
        with ThreadPoolExecutor(max_workers=16) as executor:
            future_to_symbol = {
                executor.submit(self._analyze_stock_for_volatility, symbol, time_horizon): symbol
                for symbol in stock_universe
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        opportunities.append(result)
                        # Log metrics even if found
                        metrics = result.get('volatility_metrics', {})
                        technical = result.get('technical_analysis', {})
                        logger.info(f"✅ {symbol}: vol={metrics.get('volatility_30d', 0):.1f}%, vol={metrics.get('avg_volume_30d', 0):,.0f}, range={metrics.get('price_range_pct', 0):.1f}%, momentum={technical.get('momentum_score', 0):.1f}")
                    else:
                        logger.debug(f"❌ {symbol}: Analysis returned None")
                except Exception as e:
                    logger.error(f"Error analyzing {symbol}: {e}")

        # Filter by criteria + additional quality filters
        filtered = []
        for opp in opportunities:
            metrics = opp.get('volatility_metrics', {})
            technical = opp.get('technical_analysis', {})
            fundamental = opp.get('fundamental_summary', {})
            recommendation = opp.get('recommendation', {})
            special_conditions = opp.get('special_conditions', {})

            vol = metrics.get('volatility_30d', 0)
            volume = metrics.get('avg_volume_30d', 0)
            price_range = metrics.get('price_range_pct', 0)
            momentum = technical.get('momentum_score', 0)
            trading_score = technical.get('trading_opportunity_score', 0)
            risk_level = recommendation.get('risk_level', '')
            strategy = recommendation.get('strategy', '')
            sector = fundamental.get('sector', '')
            market_cap = fundamental.get('market_cap', 0)
            current_price = opp.get('current_price', 0)
            # Use intraday_range_pct as ATR% (average true range percentage)
            atr_pct = metrics.get('intraday_range_pct', 0)
            market_state = technical.get('market_state', '')

            # NEW: Get special condition flags
            falling_knife = special_conditions.get('falling_knife', {})
            overextension = special_conditions.get('overextension', {})
            dip_opportunity = special_conditions.get('dip_opportunity', {})

            # Basic criteria check (including new parameters)
            if not (vol >= min_volatility and
                    volume >= min_avg_volume and
                    price_range >= min_price_range and
                    momentum >= min_momentum_score and
                    atr_pct >= min_atr_pct and
                    current_price >= min_price):
                reasons = []
                if vol < min_volatility: reasons.append(f"vol={vol:.1f}<{min_volatility}")
                if volume < min_avg_volume: reasons.append(f"volume={volume:,.0f}<{min_avg_volume:,.0f}")
                if price_range < min_price_range: reasons.append(f"range={price_range:.1f}<{min_price_range}")
                if momentum < min_momentum_score: reasons.append(f"momentum={momentum:.1f}<{min_momentum_score}")
                if atr_pct < min_atr_pct: reasons.append(f"atr%={atr_pct:.1f}<{min_atr_pct}")
                if current_price < min_price: reasons.append(f"price=${current_price:.2f}<${min_price}")
                logger.debug(f"✗ {opp['symbol']} filtered out: {', '.join(reasons)}")
                continue

            # NEW: Advanced filters (only apply if data is available)
            # 1. Exclude Falling Knife (if enabled AND data available)
            if exclude_falling_knife and special_conditions and falling_knife.get('detected', False):
                risk_level_fk = falling_knife.get('risk_level', 'UNKNOWN')
                if risk_level_fk in ['EXTREME', 'HIGH']:  # Only exclude severe cases (removed MODERATE)
                    logger.debug(f"✗ {opp['symbol']} filtered: Falling Knife ({risk_level_fk})")
                    continue

            # 2. Exclude Overextended (if enabled AND data available)
            if exclude_overextended and special_conditions and overextension.get('detected', False):
                severity = overextension.get('severity', 0)
                if severity >= 70:  # Only exclude high overextension (raised from 50 to 70)
                    logger.debug(f"✗ {opp['symbol']} filtered: Overextended (severity={severity})")
                    continue

            # 3. Only Uptrend (if enabled AND state is available)
            if only_uptrend and market_state:
                if market_state not in ['TRENDING_BULLISH', 'UPTREND', 'BULLISH']:
                    logger.debug(f"✗ {opp['symbol']} filtered: Not in uptrend (state={market_state})")
                    continue

            # 4. Require Dip Opportunity (if enabled AND data available)
            if require_dip and special_conditions:
                if not dip_opportunity.get('detected', False):
                    logger.debug(f"✗ {opp['symbol']} filtered: No dip opportunity")
                    continue
                # Require at least FAIR quality
                quality = dip_opportunity.get('quality', 'POOR')
                if quality not in ['EXCELLENT', 'GOOD', 'FAIR']:
                    logger.debug(f"✗ {opp['symbol']} filtered: Dip quality too low ({quality})")
                    continue

            # Additional quality filters (RELAXED for volatile screening)
            # 1. Filter out "Broken Stock" recommendations (KEEP THIS - truly bad stocks)
            if "Broken Stock" in strategy:
                logger.debug(f"✗ {opp['symbol']} filtered: Broken stock")
                continue

            # 2. REMOVED: "Wait for Pullback" filter - volatile stocks can still be good even if extended
            # Volatile traders may want stocks at highs with momentum

            # 3. REMOVED: "Monitor for Reversal" filter - too restrictive for volatile screening

            # 4. Filter out EXTREMELY high volatility (>100%) - too unpredictable
            # Raised from 80% to 100% to allow more extreme volatility
            if vol > 100.0:
                logger.debug(f"✗ {opp['symbol']} filtered: Extreme volatility ({vol:.1f}% > 100%)")
                continue

            # 5. Filter out large-cap STABLE stocks with low volatility
            # BUT KEEP large-cap volatile stocks (NVDA, TSLA, etc.)
            # Relaxed: Only filter if market cap > $500B AND volatility < 30% AND momentum < 3
            if market_cap > 500_000_000_000 and vol < 30 and momentum < 3:
                logger.debug(f"✗ {opp['symbol']} filtered: Large-cap stable low momentum (${market_cap/1e9:.0f}B, {vol:.1f}%, momentum {momentum:.1f})")
                continue

            # KEEP large-cap volatile stocks if they have good momentum and volatility
            # Example: NVDA ($3T market cap, 36% volatility, 2.5 momentum) should NOW PASS

            # 6. Require minimum trading opportunity score of 3.5 (quality threshold)
            # Lowered from 4.0 to 3.5 to include more quality volatile stocks
            if trading_score < 3.5:
                logger.debug(f"✗ {opp['symbol']} filtered: Low trading score ({trading_score:.1f} < 3.5)")
                continue

            # 4. Add trading_score to response (use this instead of volatility_score)
            opp['trading_score'] = trading_score

            # 5. Add trend category based on technical analysis
            opp['trend_category'] = self._categorize_stock_trend(opp)

            # 6. Add entry zone warning if price is far from entry zone
            opp['entry_zone_warning'] = self._check_entry_zone(opp)

            filtered.append(opp)
            logger.info(f"✓ {opp['symbol']}: trading_score={trading_score:.1f}, vol={vol:.1f}%, momentum={momentum:.1f}, category={opp['trend_category']}")

        # Sort by Trading Opportunity Score (not volatility score)
        filtered.sort(key=lambda x: x['trading_score'], reverse=True)

        logger.info(f"Found {len(filtered)} quality volatile trading opportunities")
        return filtered[:max_stocks]

    def _analyze_stock_for_volatility(self, symbol: str, time_horizon: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a single stock for volatile trading opportunities (BYPASS AI - use technical only)
        """
        try:
            # Get price data
            price_data = self.analyzer.data_manager.get_price_data(symbol, period='3mo')
            if price_data is None or price_data.empty:
                return None

            # Standardize column names to lowercase for consistency
            price_data.columns = price_data.columns.str.lower()

            # Get current price
            if 'close' not in price_data.columns or len(price_data) == 0:
                return None
            current_price = float(price_data['close'].iloc[-1])

            # Basic filtering criteria
            # 1. Price filter: $5-$1000 (relaxed to include more quality stocks)
            # Exclude true penny stocks (<$5) but allow high-priced quality stocks
            if current_price < 5.0 or current_price > 1000.0:
                return None

            # Get company info early for market cap check
            fundamental_summary = {}
            market_cap = 0
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                info = ticker.info
                market_cap = info.get('marketCap', 0)
                fundamental_summary = {
                    'market_cap': market_cap,
                    'sector': info.get('sector', 'Unknown'),
                    'beta': info.get('beta', 1.0)
                }
            except:
                fundamental_summary = {
                    'market_cap': 0,
                    'sector': 'Unknown',
                    'beta': 1.0
                }

            # 2. Market cap filter: Minimum $300M (lowered to catch more opportunities)
            # Exclude true micro-caps but allow small-cap volatility plays
            if market_cap > 0 and market_cap < 300_000_000:
                return None

            # Calculate volatility metrics
            volatility_metrics = self._calculate_volatility_metrics(price_data)

            # Validate volatility metrics
            if not volatility_metrics or volatility_metrics.get('volatility_30d', 0) == 0:
                return None

            # 3. ATR filter: Minimum 2% average true range for meaningful swings
            atr_pct = volatility_metrics.get('intraday_range_pct', 0)
            if atr_pct < 2.0:
                return None

            # Calculate technical indicators
            close = price_data['close']
            high = price_data['high'] if 'high' in price_data.columns else close
            volume = price_data['volume'] if 'volume' in price_data.columns else pd.Series([0] * len(price_data))

            # 4. Price position filter: Avoid stocks that already ran up too much
            # Calculate 52-week high and current distance from high
            high_52w = high.max() if len(high) >= 250 else high.tail(len(high)).max()
            high_30d = high.tail(30).max()

            # Distance from 52-week high (%)
            distance_from_52w_high = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else 0

            # Distance from 30-day high (%)
            distance_from_30d_high = ((high_30d - current_price) / high_30d * 100) if high_30d > 0 else 0

            # Exclude stocks too close to 52-week high (already extended)
            # If within 5% of 52-week high AND positive momentum = likely overextended
            if distance_from_52w_high < 5.0:  # Within 5% of 52-week high
                # Only exclude if it's been going up (not a breakout scenario)
                price_change_5d = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0
                if price_change_5d > 3:  # Been rallying
                    return None  # Too extended, skip

            # Prefer stocks with some pullback room (10-40% from highs is ideal for entry)
            # Stocks >50% from highs might be broken/failing
            if distance_from_52w_high > 50.0:
                # Check if it's a broken stock or just oversold
                price_change_60d = ((close.iloc[-1] - close.iloc[-60]) / close.iloc[-60] * 100) if len(close) >= 60 else 0
                if price_change_60d < -30:  # Down >30% in 60 days = likely broken
                    return None

            # RSI
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            current_rsi = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not pd.isna(rsi_series.iloc[-1]) else 50.0

            # Trend (SMA 20 vs 50)
            if len(close) >= 50:
                sma_20 = close.rolling(window=20).mean().iloc[-1]
                sma_50 = close.rolling(window=50).mean().iloc[-1]
                trend = 'bullish' if sma_20 > sma_50 else 'bearish' if sma_20 < sma_50 else 'neutral'
            else:
                trend = 'unknown'

            # IMPROVED MOMENTUM SCORE (0-10 scale)
            # Weight: Price momentum 60%, Volume 20%, RSI 20%

            # 1. Price Momentum Component (60% weight = 6.0 points max)
            price_5d = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0
            price_10d = ((close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] * 100) if len(close) >= 10 else 0
            price_20d = ((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100) if len(close) >= 20 else 0

            # Weighted price momentum: recent price changes weighted more heavily
            price_momentum = (price_5d * 0.5 + price_10d * 0.3 + price_20d * 0.2)
            price_score = 0.0
            if price_momentum > 15: price_score = 6.0
            elif price_momentum > 10: price_score = 5.0
            elif price_momentum > 5: price_score = 4.0
            elif price_momentum > 2: price_score = 3.0
            elif price_momentum > -2: price_score = 2.0
            elif price_momentum > -5: price_score = 1.0
            else: price_score = 0.0

            # 2. Volume Component (20% weight = 2.0 points max)
            avg_volume_20d = volume.tail(20).mean() if len(volume) >= 20 else volume.mean()
            recent_volume_5d = volume.tail(5).mean() if len(volume) >= 5 else volume.mean()
            volume_ratio = (recent_volume_5d / avg_volume_20d) if avg_volume_20d > 0 else 1.0

            volume_score = 0.0
            if volume_ratio > 2.0: volume_score = 2.0  # Volume surge
            elif volume_ratio > 1.5: volume_score = 1.5
            elif volume_ratio > 1.2: volume_score = 1.0
            elif volume_ratio > 0.8: volume_score = 0.5
            else: volume_score = 0.0  # Low volume = bad for trading

            # 3. RSI Component (20% weight = 2.0 points max)
            rsi_score = 0.0
            if 55 <= current_rsi <= 70: rsi_score = 2.0  # Strong but not overbought
            elif 50 <= current_rsi < 55: rsi_score = 1.5
            elif 45 <= current_rsi < 50: rsi_score = 1.0
            elif 70 < current_rsi <= 80: rsi_score = 1.0  # Overbought but could continue
            elif 30 <= current_rsi < 45: rsi_score = 0.5  # Oversold (could bounce)
            else: rsi_score = 0.0  # Extreme levels

            # Final momentum score (0-10)
            momentum_score = round(price_score + volume_score + rsi_score, 1)
            momentum_score = max(0, min(10, momentum_score))

            # Support/Resistance
            recent_30d = price_data.tail(30)
            support_level = float(recent_30d['low'].min()) if 'low' in recent_30d.columns else 0
            resistance_level = float(recent_30d['high'].max()) if 'high' in recent_30d.columns else 0

            # VOLATILITY QUALITY ASSESSMENT
            # Not just high volatility, but TRADEABLE volatility

            # 1. Directionality (is there a trend or just random noise?)
            directional_moves = 0
            for i in range(len(close) - 10, len(close)):
                if i > 0:
                    change = (close.iloc[i] - close.iloc[i-1]) / close.iloc[i-1] * 100
                    if abs(change) > 1.5:  # Significant move
                        directional_moves += 1
            directionality_score = min(directional_moves / 5.0, 1.0) * 2.0  # 0-2 scale

            # 2. Volume consistency (is volume reliable?)
            volume_std = volume.tail(20).std() if len(volume) >= 20 else 0
            volume_mean = volume.tail(20).mean() if len(volume) >= 20 else 1
            volume_cv = (volume_std / volume_mean) if volume_mean > 0 else 0
            volume_consistency_score = 2.0 if volume_cv < 0.5 else (1.0 if volume_cv < 1.0 else 0.0)

            # 3. Intraday range consistency
            if 'high' in price_data.columns and 'low' in price_data.columns:
                daily_ranges = (price_data['high'] - price_data['low']) / price_data['close'] * 100
                range_std = daily_ranges.tail(10).std()
                range_consistency_score = 2.0 if range_std < 2.0 else (1.0 if range_std < 4.0 else 0.0)
            else:
                range_consistency_score = 0.0

            # 4. Trend strength (ADX approximation)
            trend_strength_score = 0.0
            if trend == 'bullish':
                trend_strength_score = 2.0 if price_momentum > 5 else 1.0
            elif trend == 'bearish':
                trend_strength_score = 2.0 if price_momentum < -5 else 1.0
            else:
                trend_strength_score = 0.5  # Neutral/choppy

            # Volatility Quality Score (0-8 scale)
            volatility_quality = directionality_score + volume_consistency_score + range_consistency_score + trend_strength_score
            volatility_quality = round(volatility_quality, 1)

            # IMPROVED TRADING OPPORTUNITY SCORE (0-10 scale)
            # New weights: Momentum 40%, Volatility Quality 25%, Volume 20%, Raw Volatility 15%

            # Normalize components to 0-10 scale
            momentum_normalized = momentum_score  # Already 0-10
            volatility_quality_normalized = (volatility_quality / 8.0) * 10.0  # 0-8 → 0-10
            volume_normalized = volume_score * 5.0  # 0-2 → 0-10
            vol_raw_normalized = min((volatility_metrics.get('volatility_30d', 0) / 50.0) * 10.0, 10.0)  # Cap at 50%

            trading_opportunity_score = (
                momentum_normalized * 0.40 +         # 40% - Most important for trading
                volatility_quality_normalized * 0.25 +  # 25% - Quality of volatility
                volume_normalized * 0.20 +           # 20% - Volume confirmation
                vol_raw_normalized * 0.15            # 15% - Raw volatility bonus
            )

            # Boost for ideal price position (pullback zone)
            if 15 < distance_from_52w_high < 35:
                trading_opportunity_score += 1.0  # Ideal entry zone bonus

            # Boost for strong technical setup
            if trend == 'bullish' and current_rsi > 50 and volume_ratio > 1.2:
                trading_opportunity_score += 0.8
            elif trend == 'bearish' and current_rsi < 50 and volume_ratio > 1.2:
                trading_opportunity_score += 0.5

            trading_opportunity_score = round(min(trading_opportunity_score, 10.0), 1)

            technical_analysis = {
                'momentum_score': momentum_score,
                'trend': trend,
                'rsi': current_rsi,
                'support_level': support_level,
                'resistance_level': resistance_level,
                'volatility_quality': volatility_quality,
                'trading_opportunity_score': trading_opportunity_score,
                'volume_ratio': round(volume_ratio, 2),
                'price_momentum': round(price_momentum, 2),
                'distance_from_52w_high': round(distance_from_52w_high, 1),
                'distance_from_30d_high': round(distance_from_30d_high, 1),
                'high_52w': round(high_52w, 2),
                'high_30d': round(high_30d, 2)
            }

            # Build result
            result = {
                'symbol': symbol,
                'current_price': current_price,
                'volatility_metrics': volatility_metrics,
                'technical_analysis': technical_analysis,
                'fundamental_summary': fundamental_summary,
                'recommendation': self._generate_volatile_trading_recommendation(
                    volatility_metrics, technical_analysis, current_price
                ),
                'timestamp': datetime.now().isoformat()
            }

            return result

        except Exception as e:
            logger.error(f"Error analyzing {symbol} for volatility: {e}")
            return None

    def _calculate_volatility_metrics(self, price_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate various volatility metrics for trading
        """
        try:
            # Ensure we have the right columns (lowercase)
            if 'close' not in price_data.columns:
                return {}

            # 30-day volatility (annualized)
            returns = price_data['close'].pct_change().dropna()
            volatility_30d = returns.std() * (252 ** 0.5) * 100  # Annualized %

            # Average daily volume (30 days)
            avg_volume_30d = price_data['volume'].tail(30).mean() if 'volume' in price_data.columns else 0

            # Price range percentage (30 days)
            high_30d = price_data['high'].tail(30).max() if 'high' in price_data.columns else 0
            low_30d = price_data['low'].tail(30).min() if 'low' in price_data.columns else 0
            current_price = price_data['close'].iloc[-1]
            price_range_pct = ((high_30d - low_30d) / current_price * 100) if current_price > 0 else 0

            # Average intraday range (last 10 days)
            if 'high' in price_data.columns and 'low' in price_data.columns:
                recent_data = price_data.tail(10)
                intraday_ranges = (recent_data['high'] - recent_data['low']) / recent_data['close'] * 100
                intraday_range_pct = intraday_ranges.mean()
            else:
                intraday_range_pct = 0

            # Recent volatility trend (last 5 days vs previous 5 days)
            recent_vol = returns.tail(5).std() * 100
            previous_vol = returns.tail(10).head(5).std() * 100
            vol_trend = 'increasing' if recent_vol > previous_vol else 'decreasing'

            # Beta approximation (correlation with SPY if available)
            beta = 1.0  # Default neutral beta

            return {
                'volatility_30d': round(volatility_30d, 2),
                'avg_volume_30d': int(avg_volume_30d),
                'price_range_pct': round(price_range_pct, 2),
                'intraday_range_pct': round(intraday_range_pct, 2),
                'vol_trend': vol_trend,
                'beta': beta,
                'high_30d': round(high_30d, 2),
                'low_30d': round(low_30d, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating volatility metrics: {e}")
            return {}

    def _categorize_stock_trend(self, opportunity: Dict[str, Any]) -> str:
        """
        Categorize stock based on trend type for better organization

        Categories:
        - trending_up: Strong upward momentum
        - bouncing: Near support, showing reversal signs
        - breakout: Near resistance, potential breakout

        Args:
            opportunity: Stock opportunity data

        Returns:
            Trend category string
        """
        try:
            technical = opportunity.get('technical_analysis', {})
            momentum = technical.get('momentum_score', 0)
            trend = technical.get('trend', 'unknown')
            rsi = technical.get('rsi', 50)
            distance_from_52w = technical.get('distance_from_52w_high', 50)
            distance_from_30d = technical.get('distance_from_30d_high', 20)
            support_level = technical.get('support_level', 0)
            resistance_level = technical.get('resistance_level', 0)
            current_price = opportunity.get('current_price', 0)

            # Calculate distance from support and resistance
            if support_level > 0 and current_price > 0:
                distance_from_support = ((current_price - support_level) / support_level * 100)
            else:
                distance_from_support = 999

            if resistance_level > 0 and current_price > 0:
                distance_from_resistance = ((resistance_level - current_price) / current_price * 100)
            else:
                distance_from_resistance = 999

            # Categorization logic
            # 1. Trending Up: Strong momentum, bullish trend, not overextended
            if (momentum >= 6.0 and trend == 'bullish' and
                distance_from_52w > 10 and distance_from_support > 5):
                return 'trending_up'

            # 2. Bouncing: Near support, showing reversal signs
            elif (distance_from_support <= 5 or
                  (rsi < 40 and momentum >= 3.0) or
                  (distance_from_52w > 20 and momentum >= 4.0 and trend == 'bullish')):
                return 'bouncing'

            # 3. Breakout Potential: Near resistance with strong momentum
            elif (distance_from_resistance <= 5 and momentum >= 5.0) or \
                 (distance_from_52w < 10 and momentum >= 6.5):
                return 'breakout'

            # Default: Trending Up (if positive momentum) or Bouncing (if lower momentum)
            elif momentum >= 5.0:
                return 'trending_up'
            else:
                return 'bouncing'

        except Exception as e:
            logger.warning(f"Error categorizing trend: {e}")
            return 'trending_up'  # Default category

    def _check_entry_zone(self, opportunity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if current price is significantly different from entry zone
        and generate appropriate warning

        IMPROVED LOGIC:
        - For stocks far from highs (>20%): Use support level as entry zone
        - For stocks near highs (<20%): Use pullback zone (current -5% to -8%)
        - This prevents showing unrealistic entry zones for extended stocks

        Args:
            opportunity: Stock opportunity data

        Returns:
            Warning dict with message and severity, or None if no warning
        """
        try:
            technical = opportunity.get('technical_analysis', {})
            current_price = opportunity.get('current_price', 0)
            support_level = technical.get('support_level', 0)
            distance_from_52w = technical.get('distance_from_52w_high', 50)
            distance_from_30d = technical.get('distance_from_30d_high', 20)
            momentum = technical.get('momentum_score', 0)
            high_30d = technical.get('high_30d', 0)

            if current_price <= 0:
                return None

            # SMART ENTRY ZONE CALCULATION
            # 1. For stocks FAR from highs (>20% away) - use support-based entry
            if distance_from_52w > 20 and support_level > 0:
                entry_zone_low = support_level
                entry_zone_high = support_level * 1.03  # Support + 3%
                zone_type = "support"

            # 2. For stocks NEAR highs (<20% away) - use pullback zone
            else:
                # Entry zone = current price -5% to -10%
                # This is more realistic for stocks that already ran up
                entry_zone_high = current_price * 0.95  # Current -5%
                entry_zone_low = current_price * 0.90   # Current -10%
                zone_type = "pullback"

            # Check if current price is within entry zone
            if entry_zone_low <= current_price <= entry_zone_high:
                return None  # No warning, price is in entry zone

            # Calculate distance from entry zone
            if current_price > entry_zone_high:
                distance_pct = ((current_price - entry_zone_high) / entry_zone_high * 100)

                # Adjust messages based on zone type
                zone_desc = "Support Zone" if zone_type == "support" else "Pullback Zone"

                # Different severity levels based on distance
                if distance_pct > 15:
                    suggestion = f'รอราคาปรับลงใกล้ ${entry_zone_high:.2f}' if zone_type == "support" else f'รอ pullback 5-10% หรือรอ breakout confirmation'
                    return {
                        'severity': 'danger',
                        'message': f'⚠️ ราคาสูงกว่า {zone_desc} มาก (+{distance_pct:.1f}%) - แนะนำรอปรับฐานก่อนเข้า',
                        'suggestion': suggestion,
                        'entry_zone': f'${entry_zone_low:.2f} - ${entry_zone_high:.2f}',
                        'distance_pct': round(distance_pct, 1),
                        'zone_type': zone_type
                    }
                elif distance_pct > 8:
                    suggestion = f'รอราคาปรับลงใกล้ ${entry_zone_high:.2f}' if zone_type == "support" else 'รอ pullback 5-8% หรือเข้าด้วย position size เล็กกว่า'
                    return {
                        'severity': 'warning',
                        'message': f'⚠️ ราคาสูงกว่า {zone_desc} (+{distance_pct:.1f}%) - พิจารณารอจังหวะที่ดีกว่า',
                        'suggestion': suggestion,
                        'entry_zone': f'${entry_zone_low:.2f} - ${entry_zone_high:.2f}',
                        'distance_pct': round(distance_pct, 1),
                        'zone_type': zone_type
                    }
                elif distance_pct > 3:
                    return {
                        'severity': 'info',
                        'message': f'ℹ️ ราคาสูงกว่า {zone_desc} เล็กน้อย (+{distance_pct:.1f}%)',
                        'suggestion': 'สามารถเข้าได้ แต่ตั้ง Stop Loss ให้แน่น',
                        'entry_zone': f'${entry_zone_low:.2f} - ${entry_zone_high:.2f}',
                        'distance_pct': round(distance_pct, 1),
                        'zone_type': zone_type
                    }
            elif current_price < entry_zone_low:
                # Price below entry zone
                distance_pct = ((entry_zone_low - current_price) / current_price * 100)

                if zone_type == "support" and distance_pct > 5:
                    # Only warn about breakdown for support-based zones
                    return {
                        'severity': 'danger',
                        'message': f'⚠️ ราคาทะลุ Support แล้ว (-{distance_pct:.1f}%) - ระวัง breakdown',
                        'suggestion': 'รอให้มี confirmation ว่า support ใหม่เกิดขึ้นก่อนเข้า',
                        'entry_zone': f'${entry_zone_low:.2f} - ${entry_zone_high:.2f}',
                        'distance_pct': round(-distance_pct, 1),
                        'zone_type': zone_type
                    }
                # For pullback zones, being below is actually good (better entry)
                elif zone_type == "pullback" and distance_pct > 5:
                    return {
                        'severity': 'success',
                        'message': f'✅ ราคา pullback สวย (-{distance_pct:.1f}%) - เหมาะเข้าได้',
                        'suggestion': 'ราคาอยู่ในโซนที่ดี สามารถเข้าได้',
                        'entry_zone': f'${entry_zone_low:.2f} - ${entry_zone_high:.2f}',
                        'distance_pct': round(-distance_pct, 1),
                        'zone_type': zone_type
                    }

            return None  # No significant warning

        except Exception as e:
            logger.warning(f"Error checking entry zone: {e}")
            return None

    def _generate_volatile_trading_recommendation(self,
                                                  volatility_metrics: Dict[str, Any],
                                                  technical: Dict[str, Any],
                                                  current_price: float) -> Dict[str, str]:
        """
        Generate trading recommendations for volatile stocks (considering price position)
        """
        vol = volatility_metrics.get('volatility_30d', 0)
        momentum = technical.get('momentum_score', 0)
        trend = technical.get('trend', 'unknown')
        intraday_range = volatility_metrics.get('intraday_range_pct', 0)
        distance_from_52w = technical.get('distance_from_52w_high', 50)
        distance_from_30d = technical.get('distance_from_30d_high', 20)
        trading_score = technical.get('trading_opportunity_score', 5.0)
        volume_ratio = technical.get('volume_ratio', 1.0)
        rsi = technical.get('rsi', 50)

        # Check if price is extended (too high)
        is_extended = distance_from_52w < 10  # Within 10% of 52-week high
        is_overextended = distance_from_52w < 5  # Within 5% of 52-week high
        is_pullback_zone = 15 < distance_from_52w < 35  # Ideal pullback zone
        is_broken = distance_from_52w > 45  # Far from highs, possibly broken

        # Initialize action
        action = 'HOLD'

        # Determine trading strategy based on price position
        if is_overextended:
            strategy = 'Wait for Pullback'
            risk_level = 'Very High'
            thai_desc = '⚠️ ราคาพุ่งสูงเกินไปแล้ว - รอให้ปรับฐานก่อน'
            entry_suggestion = f'รอราคาปรับลง 10-15% จาก High (${technical.get("high_52w", 0):.2f})'
            exit_suggestion = 'ไม่แนะนำเข้าจุดนี้ - ความเสี่ยงสูงมาก'
            action = 'HOLD'  # Too extended, wait

        elif is_extended:
            strategy = 'Monitor for Reversal'
            risk_level = 'High'
            thai_desc = 'ราคาใกล้ high แล้ว - ระวัง reversal'
            entry_suggestion = 'รอ confirmation ว่าจะ breakout หรือ reversal'
            exit_suggestion = 'ถ้าเข้าแล้วต้องตั้ง Stop Loss แน่น 3-5%'
            # BUY only if very strong momentum + volume confirmation
            if momentum >= 7.0 and volume_ratio >= 1.5 and trend == 'bullish':
                action = 'BUY'  # Breakout continuation
            else:
                action = 'HOLD'

        elif is_pullback_zone and momentum >= 5 and trend == 'bullish':
            strategy = 'Swing Trading (2-5 days)'
            risk_level = 'Medium-High'
            thai_desc = '✅ ราคา pullback สวย - เหมาะซื้อ swing'
            entry_suggestion = f'เข้าได้ที่ราคาปัจจุบัน หรือรอ support ที่ ${technical.get("support_level", 0):.2f}'
            exit_suggestion = f'Target: ${technical.get("high_30d", 0):.2f}, Stop Loss: 5-7%'
            # STRONG BUY - ideal setup
            if trading_score >= 7.0 and volume_ratio >= 1.2:
                action = 'STRONG_BUY'
            else:
                action = 'BUY'

        elif is_pullback_zone and momentum >= 3:
            strategy = 'Short-term Position'
            risk_level = 'Medium'
            thai_desc = 'ราคาอยู่ในโซนที่น่าสนใจ - พิจารณาได้'
            entry_suggestion = f'รอสัญญาณ reversal ก่อน (RSI < 40 หรือ volume surge)'
            exit_suggestion = 'ตั้ง Stop Loss 7-10%, Take Profit ตาม R:R 1:2'
            # BUY if trading score is good
            if trading_score >= 6.5:
                action = 'BUY'
            else:
                action = 'HOLD'  # Wait for better setup

        elif is_broken:
            strategy = 'High Risk - Broken Stock?'
            risk_level = 'Very High'
            thai_desc = '⚠️ ราคาตกต่ำมาก - อาจมีปัญหาพื้นฐาน'
            entry_suggestion = 'ไม่แนะนำเว้นแต่มี catalyst ชัด (earnings, news)'
            exit_suggestion = 'ถ้าจะเข้าต้องเป็น speculation เท่านั้น'
            # SELL or AVOID - too risky unless strong reversal
            if momentum >= 6.0 and volume_ratio >= 2.0 and rsi < 35:
                action = 'BUY'  # Speculative bounce play
            else:
                action = 'SELL'  # Avoid broken stocks

        elif vol >= 50 and momentum >= 6:
            strategy = 'Aggressive Day Trading'
            risk_level = 'Very High'
            thai_desc = 'เหมาะ Day Trading - ความผันผวนสูงมาก'
            entry_suggestion = 'จับจังหวะ intraday - ใช้ technical indicators'
            exit_suggestion = 'ตั้ง target 3-5%, Stop Loss 2-3%'
            # BUY if momentum is strong
            if trading_score >= 7.0 and trend == 'bullish':
                action = 'BUY'
            else:
                action = 'HOLD'

        else:
            strategy = 'Monitor'
            risk_level = 'Medium'
            thai_desc = 'ติดตามต่อ - รอสัญญาณชัดเจน'
            entry_suggestion = 'รอให้มี setup ที่ดีกว่า'
            exit_suggestion = 'ตั้ง Stop Loss 5-8%'
            action = 'HOLD'

        # OVERRIDE: Universal BUY/SELL rules based on trading score + momentum
        # These override strategy-based actions for edge cases

        # STRONG BUY: Exceptional opportunity
        if trading_score >= 8.0 and momentum >= 6.5 and trend == 'bullish' and volume_ratio >= 1.3:
            action = 'STRONG_BUY'

        # BUY: Good opportunity
        elif trading_score >= 7.0 and momentum >= 5.0 and not is_overextended:
            if action not in ['STRONG_BUY', 'BUY']:  # Don't downgrade from STRONG_BUY
                action = 'BUY'

        # SELL: Poor setup or bearish
        elif trading_score < 4.0 or momentum < 2.0:
            action = 'SELL'
        elif trend == 'bearish' and momentum < 3.0 and distance_from_52w > 35:
            action = 'SELL'

        return {
            'action': action,  # NEW: BUY/HOLD/SELL/STRONG_BUY
            'strategy': strategy,
            'risk_level': risk_level,
            'description_thai': thai_desc,
            'entry_suggestion': entry_suggestion,
            'exit_suggestion': exit_suggestion,
            'timeframe': 'รายวัน - รายสัปดาห์',
            'key_indicator': f'Volatility: {vol:.1f}%, Distance from 52W High: {distance_from_52w:.1f}%, Score: {trading_score:.1f}'
        }


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