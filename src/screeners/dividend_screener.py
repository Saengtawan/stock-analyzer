"""
Dividend Growth Screener for Long-term Investment
หาหุ้นที่มีปันผลสูงและเหมาะสำหรับการถือระยะยาว 1-3 ปี
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

from main import StockAnalyzer
from ai_universe_generator import AIUniverseGenerator


class DividendGrowthScreener:
    """Screener for high-dividend, long-term investment opportunities"""

    def __init__(self, stock_analyzer: StockAnalyzer):
        """
        Initialize dividend screener

        Args:
            stock_analyzer: Main stock analyzer instance
        """
        self.analyzer = stock_analyzer
        self.ai_generator = AIUniverseGenerator()

        # AI-only universe generation - no fallback needed
        logger.info(f"Dividend screener initialized with AI-only universe generation")

    def screen_dividend_opportunities(self,
                                    min_dividend_yield: float = 3.0,
                                    min_dividend_growth_rate: float = 5.0,
                                    min_payout_ratio: float = 30.0,
                                    max_payout_ratio: float = 70.0,
                                    min_fundamental_score: float = 5.0,
                                    min_years_of_growth: int = 5,
                                    max_stocks: int = 15) -> List[Dict[str, Any]]:
        """
        Screen for high-quality dividend growth stocks

        Args:
            min_dividend_yield: Minimum dividend yield (%)
            min_dividend_growth_rate: Minimum dividend growth rate (%)
            min_payout_ratio: Minimum payout ratio (%)
            max_payout_ratio: Maximum payout ratio (%)
            min_fundamental_score: Minimum fundamental analysis score
            min_years_of_growth: Minimum years of consistent dividend growth
            max_stocks: Maximum number of stocks to return

        Returns:
            List of dividend investment opportunities
        """
        logger.info("Starting dividend growth screening...")

        # Always use AI universe generation - no fallback
        if not self.ai_generator:
            raise ValueError("AI universe generator not initialized. Cannot proceed without AI.")

        logger.info("🤖 Generating AI-powered dividend universe...")
        criteria = {
            'min_dividend_yield': min_dividend_yield,
            'max_stocks': max_stocks
        }
        dividend_universe = self.ai_generator.generate_dividend_universe(criteria)
        logger.info(f"✅ Generated {len(dividend_universe)} AI-selected symbols")

        opportunities = []

        # Use ThreadPoolExecutor for parallel analysis
        with ThreadPoolExecutor(max_workers=16) as executor:
            # Submit analysis tasks
            future_to_symbol = {
                executor.submit(self._analyze_dividend_stock, symbol): symbol
                for symbol in dividend_universe
            }

            # Collect results
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        opportunities.append(result)
                        logger.info(f"✅ {symbol}: Added to dividend opportunities")
                    else:
                        logger.info(f"❌ {symbol}: Did not meet dividend criteria")

                except Exception as e:
                    logger.warning(f"⚠️ {symbol}: Analysis failed - {e}")

        # Filter based on criteria
        filtered_opportunities = []
        for opp in opportunities:
            dividend_data = opp.get('dividend_analysis', {})
            fundamental = opp.get('fundamental_analysis', {})

            # Check dividend yield (must have some dividend)
            dividend_yield = dividend_data.get('dividend_yield', 0)
            if dividend_yield <= 0:  # Skip stocks with no dividend
                continue
            if dividend_yield < min_dividend_yield:
                continue

            # Check dividend growth (more flexible for AI-generated universe)
            dividend_growth = dividend_data.get('dividend_growth_rate', 0)
            if min_dividend_growth_rate > 0 and dividend_growth < (min_dividend_growth_rate * 0.5):  # 50% of target
                continue

            # Check payout ratio (more flexible range)
            payout_ratio = dividend_data.get('payout_ratio')
            if payout_ratio is not None and payout_ratio > 0:  # Only check if payout ratio is available
                # Allow wider range: 20% to 90% instead of strict min/max
                if payout_ratio < 20 or payout_ratio > 90:
                    continue

            # Check fundamental score (more flexible for calculation-based scoring)
            fund_score = fundamental.get('overall_score', 0)
            if fund_score > 0 and fund_score < (min_fundamental_score * 0.6):  # 60% of target
                continue

            # AI-only universe (no sector filtering needed)

            # Calculate dividend sustainability score
            sustainability_score = self._calculate_dividend_sustainability(opp)
            opp['dividend_sustainability_score'] = sustainability_score

            # Calculate long-term attractiveness
            attractiveness_score = self._calculate_long_term_attractiveness(opp)
            opp['long_term_attractiveness'] = attractiveness_score

            filtered_opportunities.append(opp)

        # Sort by combined score (dividend sustainability + fundamental strength + attractiveness)
        def combined_score(opp):
            sustainability = opp.get('dividend_sustainability_score', 0)
            fundamental = opp.get('fundamental_analysis', {}).get('overall_score', 0)
            attractiveness = opp.get('long_term_attractiveness', 0)
            return (sustainability * 0.4) + (fundamental * 0.3) + (attractiveness * 0.3)

        filtered_opportunities.sort(key=combined_score, reverse=True)

        # Limit results
        final_opportunities = filtered_opportunities[:max_stocks]

        logger.info(f"Dividend screening summary:")
        logger.info(f"  - Total analyzed stocks: {len(opportunities)}")
        logger.info(f"  - Stocks with dividend data: {len([o for o in opportunities if o.get('dividend_analysis', {}).get('dividend_yield', 0) > 0])}")
        logger.info(f"  - After filtering: {len(filtered_opportunities)}")
        logger.info(f"  - Final opportunities: {len(final_opportunities)}")

        # Debug: Show some examples of what we found
        if len(opportunities) > 0 and len(final_opportunities) == 0:
            logger.info("Debug: Showing sample dividend data from analyzed stocks:")
            for i, opp in enumerate(opportunities[:3]):
                dividend_data = opp.get('dividend_analysis', {})
                fund_data = opp.get('fundamental_analysis', {})
                payout_ratio = dividend_data.get('payout_ratio')
                payout_str = f"{payout_ratio:.1f}%" if payout_ratio is not None else "N/A%"
                logger.info(f"  {opp.get('symbol', 'N/A')}: yield={dividend_data.get('dividend_yield', 0):.2f}%, "
                           f"growth={dividend_data.get('dividend_growth_rate', 0):.1f}%, "
                           f"payout={payout_str}, "
                           f"fund_score={fund_data.get('overall_score', 0):.1f}")

        return final_opportunities

    def _analyze_dividend_stock(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Analyze individual stock for dividend investing"""
        try:
            # Get analysis without AI recommendations (for faster screening)
            analysis = self.analyzer.analyze_stock(symbol, time_horizon='long', account_value=100000, include_ai_analysis=False)

            if 'error' in analysis:
                return None

            # Get financial data for dividend analysis
            financial_data = self.analyzer.data_manager.get_financial_data(symbol)

            # Perform dividend-specific analysis
            dividend_analysis = self._analyze_dividend_metrics(financial_data)

            if not dividend_analysis:
                return None

            # Add dividend analysis to the result
            analysis['dividend_analysis'] = dividend_analysis
            analysis['symbol'] = symbol
            analysis['analysis_date'] = datetime.now().isoformat()

            return analysis

        except Exception as e:
            logger.warning(f"Failed to analyze {symbol}: {e}")
            return None

    def _analyze_dividend_metrics(self, financial_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze dividend-specific metrics"""
        try:
            dividend_metrics = {}

            # Basic dividend data
            dividend_yield = financial_data.get('dividend_yield', 0)
            payout_ratio_raw = financial_data.get('payout_ratio', 0)

            if dividend_yield <= 0:
                return None  # Skip stocks with no dividend

            # Detect if this is an ETF (no sector/industry info typically)
            sector = financial_data.get('sector')
            industry = financial_data.get('industry')
            symbol = financial_data.get('symbol', '')

            is_etf = (sector is None and industry is None) or any(etf_indicator in symbol for etf_indicator in ['SPYI', 'VYM', 'DVY', 'HDV', 'SCHD', 'VIG', 'DGRO', 'FDV', 'RDVY', 'NOBL'])

            # Convert payout ratio from decimal to percentage if needed
            payout_ratio = None
            if payout_ratio_raw is not None:
                if payout_ratio_raw < 1.0:  # Decimal format (0.70) -> convert to percentage (70%)
                    payout_ratio = payout_ratio_raw * 100
                else:  # Already percentage format
                    payout_ratio = payout_ratio_raw

            dividend_metrics['dividend_yield'] = dividend_yield
            dividend_metrics['payout_ratio'] = payout_ratio
            dividend_metrics['is_etf'] = is_etf

            # Calculate dividend growth rate (estimated)
            revenue_growth = financial_data.get('revenue_growth', 0)
            earnings_growth = financial_data.get('earnings_growth', 0)

            # Estimate dividend growth based on earnings and revenue growth
            estimated_dividend_growth = 0
            if earnings_growth is not None and revenue_growth is not None:
                estimated_dividend_growth = min(earnings_growth * 100, revenue_growth * 100)
            elif earnings_growth is not None:
                estimated_dividend_growth = earnings_growth * 100
            elif revenue_growth is not None:
                estimated_dividend_growth = revenue_growth * 100

            dividend_metrics['dividend_growth_rate'] = max(0, estimated_dividend_growth)

            # Dividend safety metrics
            dividend_metrics['dividend_safety'] = self._assess_dividend_safety(financial_data)

            # Coverage ratios with null safety
            eps = financial_data.get('eps')
            if eps is not None and eps > 0 and payout_ratio is not None and payout_ratio > 0:
                dividend_per_share = eps * (payout_ratio / 100)
                dividend_metrics['dividend_per_share_estimated'] = dividend_per_share
                dividend_metrics['dividend_coverage_ratio'] = 1 / (payout_ratio / 100)
            else:
                dividend_metrics['dividend_per_share_estimated'] = 0
                dividend_metrics['dividend_coverage_ratio'] = 0

            # Free cash flow coverage with null safety
            free_cash_flow = financial_data.get('free_cash_flow')
            market_cap = financial_data.get('market_cap')
            if free_cash_flow is not None and market_cap is not None and free_cash_flow > 0 and market_cap > 0:
                fcf_yield = (free_cash_flow / market_cap) * 100
                dividend_metrics['fcf_dividend_coverage'] = fcf_yield / dividend_yield if dividend_yield > 0 else 0
            else:
                dividend_metrics['fcf_dividend_coverage'] = 0

            return dividend_metrics

        except Exception as e:
            logger.warning(f"Failed to analyze dividend metrics: {e}")
            return None

    def _assess_dividend_safety(self, financial_data: Dict[str, Any]) -> str:
        """Assess dividend safety based on financial metrics"""
        safety_score = 0

        # Payout ratio assessment with null safety
        payout_ratio = financial_data.get('payout_ratio')
        if payout_ratio is not None:
            if payout_ratio < 40:
                safety_score += 3
            elif payout_ratio < 60:
                safety_score += 2
            elif payout_ratio < 80:
                safety_score += 1

        # Debt levels
        debt_to_equity = financial_data.get('debt_to_equity', 0)
        if debt_to_equity is not None:
            if debt_to_equity < 0.3:
                safety_score += 2
            elif debt_to_equity < 0.6:
                safety_score += 1

        # Profitability
        roe = financial_data.get('return_on_equity', 0)
        if roe is not None and roe > 0.15:
            safety_score += 2
        elif roe is not None and roe > 0.10:
            safety_score += 1

        # Cash flow with null safety
        free_cash_flow = financial_data.get('free_cash_flow')
        if free_cash_flow is not None and free_cash_flow > 0:
            safety_score += 1

        # Revenue growth
        revenue_growth = financial_data.get('revenue_growth', 0)
        if revenue_growth is not None and revenue_growth > 0:
            safety_score += 1

        # Convert to rating
        if safety_score >= 8:
            return "Very High"
        elif safety_score >= 6:
            return "High"
        elif safety_score >= 4:
            return "Moderate"
        elif safety_score >= 2:
            return "Low"
        else:
            return "Very Low"

    def _calculate_dividend_sustainability(self, opportunity: Dict[str, Any]) -> float:
        """Calculate dividend sustainability score (0-10)"""
        score = 0

        dividend_data = opportunity.get('dividend_analysis', {})
        fundamental = opportunity.get('fundamental_analysis', {})

        # Check if this is an ETF
        is_etf = dividend_data.get('is_etf', False)

        if is_etf:
            # ETF scoring - different criteria
            return self._calculate_etf_sustainability(opportunity)

        # Regular stock scoring continues below...

        # Payout ratio (25% weight)
        payout_ratio = dividend_data.get('payout_ratio')
        if payout_ratio is not None:
            if 30 <= payout_ratio <= 60:
                score += 2.5
            elif 20 <= payout_ratio <= 70:
                score += 2.0
            elif payout_ratio <= 80:
                score += 1.0

        # Dividend coverage (25% weight)
        coverage = dividend_data.get('dividend_coverage_ratio', 0)
        if coverage >= 2.0:
            score += 2.5
        elif coverage >= 1.5:
            score += 2.0
        elif coverage >= 1.2:
            score += 1.0

        # Financial health (25% weight)
        ratios = fundamental.get('financial_ratios', {})
        debt_to_equity = ratios.get('debt_to_equity', float('inf'))
        current_ratio = ratios.get('current_ratio')

        if (debt_to_equity is not None and debt_to_equity < 0.4 and
            current_ratio is not None and current_ratio > 1.5):
            score += 2.5
        elif (debt_to_equity is not None and debt_to_equity < 0.7 and
              current_ratio is not None and current_ratio > 1.2):
            score += 2.0
        elif current_ratio is not None and current_ratio > 1.0:
            score += 1.0

        # Profitability trend (25% weight)
        roe = ratios.get('roe', 0)
        profit_margin = ratios.get('profit_margin', 0)

        if roe is not None and roe > 0.15 and profit_margin is not None and profit_margin > 0.10:
            score += 2.5
        elif roe is not None and roe > 0.10 and profit_margin is not None and profit_margin > 0.05:
            score += 2.0
        elif roe is not None and roe > 0.05:
            score += 1.0

        return min(score, 10.0)

    def _calculate_long_term_attractiveness(self, opportunity: Dict[str, Any]) -> float:
        """Calculate long-term investment attractiveness (0-10)"""
        score = 0

        dividend_data = opportunity.get('dividend_analysis', {})
        fundamental = opportunity.get('fundamental_analysis', {})
        technical = opportunity.get('technical_analysis', {})

        # Dividend yield attractiveness (20% weight)
        dividend_yield = dividend_data.get('dividend_yield', 0)
        if dividend_yield >= 6.0:
            score += 2.0
        elif dividend_yield >= 4.0:
            score += 1.5
        elif dividend_yield >= 3.0:
            score += 1.0

        # Dividend growth potential (20% weight)
        growth_rate = dividend_data.get('dividend_growth_rate', 0)
        if growth_rate >= 10:
            score += 2.0
        elif growth_rate >= 7:
            score += 1.5
        elif growth_rate >= 5:
            score += 1.0

        # Business quality (30% weight)
        fund_score = fundamental.get('overall_score', 0)
        score += (fund_score / 10) * 3.0

        # Valuation attractiveness (20% weight)
        ratios = fundamental.get('financial_ratios', {})
        pe_ratio = ratios.get('pe_ratio', float('inf'))
        pb_ratio = ratios.get('pb_ratio', float('inf'))

        if pe_ratio is not None and pe_ratio < 15 and pb_ratio is not None and pb_ratio < 2:
            score += 2.0
        elif pe_ratio is not None and pe_ratio < 20 and pb_ratio is not None and pb_ratio < 3:
            score += 1.5
        elif pe_ratio is not None and pe_ratio < 25:
            score += 1.0

        # Technical trend (10% weight)
        if technical and technical.get('trend_direction') == 'Bullish':
            score += 1.0
        elif technical and technical.get('trend_direction') == 'Neutral':
            score += 0.5

        return min(score, 10.0)

    def _calculate_etf_sustainability(self, opportunity: Dict[str, Any]) -> float:
        """Calculate ETF dividend sustainability score (0-10) - different criteria than stocks"""
        score = 0

        dividend_data = opportunity.get('dividend_analysis', {})
        symbol = opportunity.get('symbol', '')

        # Dividend yield (40% weight) - ETFs typically have lower yields than individual stocks
        dividend_yield = dividend_data.get('dividend_yield', 0)
        if dividend_yield >= 8.0:  # Very high dividend ETF
            score += 4.0
        elif dividend_yield >= 6.0:  # High dividend ETF
            score += 3.5
        elif dividend_yield >= 4.0:  # Good dividend ETF
            score += 3.0
        elif dividend_yield >= 2.0:  # Moderate dividend ETF
            score += 2.0
        elif dividend_yield >= 1.0:  # Low dividend ETF
            score += 1.0

        # ETF Type and Quality (30% weight) - based on known dividend ETF quality
        etf_quality_scores = {
            'SPYI': 3.0,  # SPDR Portfolio High Dividend ETF
            'VYM': 3.0,   # Vanguard High Dividend Yield ETF
            'DVY': 3.0,   # iShares Select Dividend ETF
            'HDV': 3.0,   # iShares Core High Dividend ETF
            'SCHD': 3.0,  # Schwab US Dividend Equity ETF
            'VIG': 2.5,   # Vanguard Dividend Appreciation ETF
            'DGRO': 2.5,  # iShares Core Dividend Growth ETF
            'NOBL': 2.5,  # ProShares S&P 500 Dividend Aristocrats ETF
            'FDV': 2.0,   # Fidelity High Dividend ETF
            'RDVY': 2.0,  # First Trust Rising Dividend Achievers ETF
        }

        score += etf_quality_scores.get(symbol, 1.5)  # Default moderate quality for unknown ETFs

        # Track record and consistency (20% weight)
        # Since we don't have historical data, use dividend yield as proxy for consistency
        if dividend_yield >= 5.0 and dividend_yield <= 15.0:  # Sweet spot for sustainable dividends
            score += 2.0
        elif dividend_yield >= 3.0 and dividend_yield <= 20.0:  # Reasonable range
            score += 1.5
        elif dividend_yield >= 1.0:  # Some dividend
            score += 1.0

        # Market conditions and volatility (10% weight)
        # ETFs are generally more stable than individual stocks
        score += 1.0  # Base score for ETF stability

        return min(score, 10.0)

    def _calculate_fundamental_metrics(self, financial_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate fundamental metrics using formula-based calculations only"""
        try:
            fundamental_analysis = {}

            # Financial ratios
            ratios = {}

            # Basic ratios from financial data
            ratios['pe_ratio'] = financial_data.get('pe_ratio', 0)
            ratios['pb_ratio'] = financial_data.get('pb_ratio', 0)
            ratios['debt_to_equity'] = financial_data.get('debt_to_equity', 0)
            ratios['current_ratio'] = financial_data.get('current_ratio', 0)
            ratios['roe'] = financial_data.get('return_on_equity', 0)
            ratios['profit_margin'] = financial_data.get('profit_margin', 0)

            fundamental_analysis['financial_ratios'] = ratios

            # Calculate overall score based on dividend-focused metrics
            score = 0

            # ROE scoring (25% weight)
            roe = ratios.get('roe', 0)
            if roe is not None and roe > 0:
                if roe > 0.20:  # 20%+ ROE
                    score += 2.5
                elif roe > 0.15:  # 15%+ ROE
                    score += 2.0
                elif roe > 0.10:  # 10%+ ROE
                    score += 1.5
                elif roe > 0.05:  # 5%+ ROE
                    score += 1.0

            # Profit margin scoring (25% weight)
            profit_margin = ratios.get('profit_margin', 0)
            if profit_margin is not None and profit_margin > 0:
                if profit_margin > 0.20:  # 20%+ margin
                    score += 2.5
                elif profit_margin > 0.15:  # 15%+ margin
                    score += 2.0
                elif profit_margin > 0.10:  # 10%+ margin
                    score += 1.5
                elif profit_margin > 0.05:  # 5%+ margin
                    score += 1.0

            # Debt management scoring (25% weight)
            debt_to_equity = ratios.get('debt_to_equity', float('inf'))
            if debt_to_equity is not None:
                if debt_to_equity < 0.3:  # Low debt
                    score += 2.5
                elif debt_to_equity < 0.5:  # Moderate debt
                    score += 2.0
                elif debt_to_equity < 0.8:  # Higher debt but manageable
                    score += 1.0

            # Liquidity scoring (25% weight)
            current_ratio = ratios.get('current_ratio', 0)
            if current_ratio is not None:
                if current_ratio > 2.0:  # Very liquid
                    score += 2.5
                elif current_ratio > 1.5:  # Good liquidity
                    score += 2.0
                elif current_ratio > 1.2:  # Adequate liquidity
                    score += 1.5
                elif current_ratio > 1.0:  # Minimal liquidity
                    score += 1.0

            fundamental_analysis['overall_score'] = min(score, 10.0)
            fundamental_analysis['calculation_method'] = 'formula_based'

            return fundamental_analysis

        except Exception as e:
            logger.warning(f"Failed to calculate fundamental metrics: {e}")
            return {'overall_score': 0, 'financial_ratios': {}}

    def _calculate_basic_technical_metrics(self, symbol: str) -> Dict[str, Any]:
        """Calculate basic technical indicators without AI"""
        try:
            # Get price data
            price_data = self.analyzer.data_manager.get_price_data(symbol, period='6mo')

            if price_data is None or price_data.empty:
                return {'trend_direction': 'Unknown', 'calculation_method': 'data_unavailable'}

            # Check for column names (case sensitive)
            close_col = None
            for col in ['Close', 'close', 'CLOSE']:
                if col in price_data.columns:
                    close_col = col
                    break

            if close_col is None:
                return {'trend_direction': 'No_Price_Data', 'calculation_method': 'missing_close_column'}

            # Calculate basic trend using moving averages
            if len(price_data) >= 50:
                # 20-day and 50-day moving averages
                ma20 = price_data[close_col].rolling(window=20).mean()
                ma50 = price_data[close_col].rolling(window=50).mean()

                current_price = price_data[close_col].iloc[-1]
                current_ma20 = ma20.iloc[-1]
                current_ma50 = ma50.iloc[-1]

                # Determine trend
                if current_price > current_ma20 > current_ma50:
                    trend_direction = 'Bullish'
                elif current_price < current_ma20 < current_ma50:
                    trend_direction = 'Bearish'
                else:
                    trend_direction = 'Neutral'

                # Calculate price momentum (% change over 3 months)
                if len(price_data) >= 60:
                    price_3m_ago = price_data[close_col].iloc[-60]
                    momentum = ((current_price - price_3m_ago) / price_3m_ago) * 100
                else:
                    momentum = 0

                return {
                    'trend_direction': trend_direction,
                    'current_price': float(current_price),
                    'ma20': float(current_ma20),
                    'ma50': float(current_ma50),
                    'momentum_3m': momentum,
                    'calculation_method': 'moving_averages'
                }
            else:
                return {
                    'trend_direction': 'Insufficient_Data',
                    'calculation_method': 'insufficient_history'
                }

        except Exception as e:
            logger.warning(f"Failed to calculate technical metrics for {symbol}: {e}")
            return {'trend_direction': 'Error', 'calculation_method': 'calculation_error'}

